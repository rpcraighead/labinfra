# DaVinci — IaC / Code Generation Agent
# Generates infrastructure-as-code configs, applies templates, and manages git operations.

import os
import logging
import sys
import asyncio
import json
import tempfile
import shutil
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import httpx
import jinja2
from git import Repo, GitCommandError
from base import BaseAgent

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


class DaVinciAgent(BaseAgent):
    def __init__(self):
        super().__init__('davinci', port=8003)
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://ollama:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'qwen3:8b-nothink')
        self.workspace = Path(os.getenv('WORKSPACE_PATH', '/workspace'))
        self.repo_url = os.getenv('CODE_REPO_URL', '')
        self.template_dir = Path(os.getenv('TEMPLATE_DIR', '/app/templates'))
        self.ollama_available = False

    async def connect(self):
        await super().connect()
        await self._check_ollama()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.template_dir.mkdir(parents=True, exist_ok=True)

    async def _check_ollama(self):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f'{self.ollama_url}/api/tags')
                if resp.status_code == 200:
                    self.ollama_available = True
                    models = [m['name'] for m in resp.json().get('models', [])]
                    self.logger.info(f"Ollama available, models: {models}")
                    return
        except Exception:
            pass
        self.ollama_available = False
        self.logger.info("Ollama not available — template-only mode")

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        handlers = {
            'generate_code': self._generate_code,
            'apply_config': self._apply_config,
            'create_iac': self._create_iac,
            'git_commit': self._git_commit,
            'render_template': self._render_template,
            'list_templates': self._list_templates,
        }
        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unknown operation: {operation}")
        return await handler(params)

    # ==================== CODE GENERATION (LLM) ====================

    async def _generate_code(self, params: dict) -> dict:
        """Generate code/config using Ollama LLM."""
        prompt = params.get('prompt')
        if not prompt:
            raise ValueError("prompt is required")

        language = params.get('language', 'yaml')
        context = params.get('context', '')
        output_file = params.get('output_file', '')

        system_prompt = (
            f"You are DaVinci, an infrastructure code generation agent. "
            f"Generate clean, production-ready {language} code. "
            f"Output ONLY the code block, no explanations.\n"
        )
        if context:
            system_prompt += f"\nContext: {context}"

        if not self.ollama_available:
            return {
                "status": "error",
                "message": "Ollama LLM not available. Cannot generate code.",
            }

        import re
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f'{self.ollama_url}/api/chat', json={
                'model': self.ollama_model,
                'messages': [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                'stream': False,
            })
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama returned {resp.status_code}")
            generated = resp.json().get('message', {}).get('content', '')

        # Strip think tags
        import re
        generated = re.sub(r'<think>.*?</think>', '', generated, flags=re.DOTALL).strip()

        # Extract code block if fenced
        code_match = re.search(r'```(?:\w+)?\s*\n(.*?)```', generated, re.DOTALL)
        code = code_match.group(1).strip() if code_match else generated

        # Optionally write to file
        if output_file:
            out_path = self.workspace / output_file
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(code)
            self.logger.info(f"Generated code written to {out_path}")

        return {
            "language": language,
            "code": code,
            "output_file": output_file or None,
            "status": "generated",
        }

    # ==================== TEMPLATE RENDERING ====================

    async def _render_template(self, params: dict) -> dict:
        """Render a Jinja2 template with provided variables."""
        template_name = params.get('template')
        variables = params.get('variables', {})
        output_file = params.get('output_file', '')

        if not template_name:
            raise ValueError("template name is required")

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)),
            undefined=jinja2.StrictUndefined,
        )

        try:
            template = env.get_template(template_name)
        except jinja2.TemplateNotFound:
            raise ValueError(f"Template '{template_name}' not found in {self.template_dir}")

        rendered = template.render(**variables)

        if output_file:
            out_path = self.workspace / output_file
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered)

        return {
            "template": template_name,
            "output_file": output_file or None,
            "rendered": rendered,
            "status": "rendered",
        }

    async def _list_templates(self, params: dict) -> dict:
        """List available templates."""
        templates = []
        if self.template_dir.exists():
            for f in self.template_dir.rglob('*'):
                if f.is_file():
                    templates.append(str(f.relative_to(self.template_dir)))
        return {"templates": templates, "template_dir": str(self.template_dir)}

    # ==================== IaC GENERATION ====================

    async def _create_iac(self, params: dict) -> dict:
        """Generate infrastructure-as-code for a resource."""
        resource_type = params.get('type', 'vm')
        name = params.get('name', 'unnamed')
        iac_format = params.get('format', 'docker-compose')

        # Built-in generators for common resource types
        generators = {
            ('vm', 'proxmox-cli'): self._gen_proxmox_vm,
            ('container', 'docker-compose'): self._gen_docker_compose,
            ('container', 'dockerfile'): self._gen_dockerfile,
        }

        generator = generators.get((resource_type, iac_format))
        if generator:
            code = await asyncio.to_thread(generator, params)
            output_file = params.get('output_file', f'{name}.{iac_format}.yml')
            out_path = self.workspace / output_file
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(code)
            return {
                "resource_type": resource_type,
                "format": iac_format,
                "output_file": output_file,
                "code": code,
                "status": "generated",
            }

        # Fallback: use LLM if available
        if self.ollama_available:
            return await self._generate_code({
                'prompt': f"Generate {iac_format} config for a {resource_type} named '{name}' with these parameters: {json.dumps(params)}",
                'language': iac_format,
                'output_file': params.get('output_file', ''),
            })

        return {"status": "error", "message": f"No generator for ({resource_type}, {iac_format}) and LLM unavailable"}

    def _gen_docker_compose(self, params: dict) -> str:
        """Generate a docker-compose service definition."""
        import yaml
        name = params.get('name', 'service')
        image = params.get('image', 'alpine:latest')
        ports = params.get('ports', {})
        environment = params.get('environment', {})
        volumes = params.get('volumes', [])
        restart = params.get('restart_policy', 'unless-stopped')

        service = {
            'image': image,
            'container_name': name,
            'restart': restart,
        }
        if ports:
            service['ports'] = [f"{hp}:{cp}" for hp, cp in ports.items()]
        if environment:
            service['environment'] = environment
        if volumes:
            service['volumes'] = volumes

        compose = {'services': {name: service}}
        return yaml.dump(compose, default_flow_style=False, sort_keys=False)

    def _gen_dockerfile(self, params: dict) -> str:
        """Generate a basic Dockerfile."""
        base_image = params.get('base_image', 'python:3.11-slim')
        workdir = params.get('workdir', '/app')
        install_cmd = params.get('install_cmd', '')
        copy_files = params.get('copy_files', ['.'])
        entrypoint = params.get('entrypoint', '')
        cmd = params.get('cmd', '')
        expose = params.get('expose', '')

        lines = [f"FROM {base_image}", f"WORKDIR {workdir}"]
        if install_cmd:
            lines.append(f"RUN {install_cmd}")
        for src in copy_files:
            lines.append(f"COPY {src} {workdir}/")
        if expose:
            lines.append(f"EXPOSE {expose}")
        if entrypoint:
            lines.append(f'ENTRYPOINT {json.dumps(entrypoint.split())}')
        if cmd:
            lines.append(f'CMD {json.dumps(cmd.split())}')
        return '\n'.join(lines) + '\n'

    def _gen_proxmox_vm(self, params: dict) -> str:
        """Generate a Proxmox VM creation script."""
        vmid = params.get('vmid', '<VMID>')
        name = params.get('name', 'new-vm')
        memory = params.get('memory', 2048)
        cores = params.get('cores', 2)
        disk_size = params.get('disk_size', '32G')
        storage = params.get('storage', 'local-lvm')
        bridge = params.get('bridge', 'vmbr0')
        iso = params.get('iso', '')
        node = params.get('node', '<NODE>')

        lines = [
            "#!/bin/bash",
            f"# Create VM: {name} (VMID: {vmid})",
            f"# Generated by DaVinci agent",
            "",
            f"qm create {vmid} \\",
            f"  --name {name} \\",
            f"  --memory {memory} \\",
            f"  --cores {cores} \\",
            f"  --cpu host \\",
            f"  --net0 virtio,bridge={bridge} \\",
            f"  --scsihw virtio-scsi-single \\",
            f"  --scsi0 {storage}:{disk_size} \\",
            f"  --ostype l26 \\",
            f"  --boot order=scsi0",
        ]
        if iso:
            lines[-1] = f"  --boot order=ide2\\;scsi0"
            lines.insert(-1, f"  --ide2 {iso},media=cdrom \\")

        lines.extend(["", f"echo 'VM {vmid} ({name}) created on {node}'"])
        return '\n'.join(lines) + '\n'

    # ==================== GIT OPERATIONS ====================

    async def _apply_config(self, params: dict) -> dict:
        """Apply a generated config: write to workspace and optionally commit."""
        config_content = params.get('content', '')
        file_path = params.get('file_path', '')
        if not config_content or not file_path:
            raise ValueError("content and file_path are required")

        out_path = self.workspace / file_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(config_content)

        result = {
            "file_path": str(out_path),
            "status": "written",
        }

        if params.get('commit', False):
            commit_result = await self._git_commit({
                'files': [file_path],
                'message': params.get('commit_message', f'DaVinci: apply config {file_path}'),
            })
            result['git'] = commit_result

        return result

    async def _git_commit(self, params: dict) -> dict:
        """Commit files in the workspace to git."""
        files = params.get('files', [])
        message = params.get('message', 'DaVinci auto-commit')

        repo_path = self.workspace
        try:
            repo = Repo(str(repo_path))
        except Exception:
            # Init if needed
            repo = Repo.init(str(repo_path))
            self.logger.info(f"Initialized git repo at {repo_path}")

        if files:
            repo.index.add(files)
        else:
            repo.git.add(A=True)

        if not repo.is_dirty(index=True):
            return {"status": "no_changes", "message": "Nothing to commit"}

        commit = repo.index.commit(message)
        self.logger.info(f"Git commit: {commit.hexsha[:8]} — {message}")

        result = {
            "commit": commit.hexsha[:8],
            "message": message,
            "status": "committed",
        }

        # Push if remote is configured
        if params.get('push', False) and repo.remotes:
            try:
                repo.remotes.origin.push()
                result['pushed'] = True
            except GitCommandError as e:
                result['push_error'] = str(e)

        return result

    def create_app(self):
        app = super().create_app()

        @app.get("/templates")
        async def templates():
            return await self._list_templates({})

        @app.get("/workspace")
        async def workspace():
            files = []
            if self.workspace.exists():
                for f in self.workspace.rglob('*'):
                    if f.is_file():
                        files.append(str(f.relative_to(self.workspace)))
            return {"workspace": str(self.workspace), "files": files}

        return app


# ==================== MAIN ====================

agent = DaVinciAgent()
app = agent.create_app()

if __name__ == '__main__':
    agent.run()
