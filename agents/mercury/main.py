# Mercury — Container deployment agent
# Manages Docker containers on remote hosts via the Docker API.

import os
import logging
import sys
import asyncio
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import docker
from docker.errors import DockerException, NotFound, APIError
from base import BaseAgent

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


class MercuryAgent(BaseAgent):
    def __init__(self):
        super().__init__('mercury', port=8002)
        self.docker_client: Optional[docker.DockerClient] = None

    async def connect(self):
        await super().connect()
        self._connect_docker()

    def _connect_docker(self):
        """Connect to Docker daemon (local socket or remote TCP)."""
        docker_host = os.getenv('DOCKER_HOST', '')
        tls_verify = os.getenv('DOCKER_TLS_VERIFY', '')
        cert_path = os.getenv('DOCKER_CERT_PATH', '')

        try:
            if docker_host:
                if tls_verify and cert_path:
                    tls_config = docker.tls.TLSConfig(
                        ca_cert=os.path.join(cert_path, 'ca.pem'),
                        client_cert=(
                            os.path.join(cert_path, 'cert.pem'),
                            os.path.join(cert_path, 'key.pem'),
                        ),
                        verify=True,
                    )
                    self.docker_client = docker.DockerClient(
                        base_url=docker_host, tls=tls_config
                    )
                else:
                    self.docker_client = docker.DockerClient(base_url=docker_host)
            else:
                self.docker_client = docker.from_env()

            info = self.docker_client.info()
            self.logger.info(
                f"Docker connected: {info.get('Name', '?')} "
                f"({info.get('ServerVersion', '?')}), "
                f"{info.get('Containers', 0)} containers"
            )
        except DockerException as e:
            self.logger.warning(f"Docker connection failed (non-fatal): {e}")

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        handlers = {
            'deploy_container': self._deploy_container,
            'docker_build': self._docker_build,
            'scale_service': self._scale_service,
            'list_containers': self._list_containers,
            'stop_container': self._stop_container,
            'remove_container': self._remove_container,
            'container_logs': self._container_logs,
            'pull_image': self._pull_image,
        }
        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unknown operation: {operation}")
        return await asyncio.to_thread(handler, params)

    # ==================== CONTAINER OPERATIONS ====================

    def _deploy_container(self, params: dict) -> dict:
        """Deploy a container from an image."""
        image = params.get('image')
        name = params.get('name', '')
        if not image:
            raise ValueError("image is required")

        # Pull latest image
        self.logger.info(f"Pulling image {image}")
        self.docker_client.images.pull(image)

        # Remove existing container with the same name if requested
        if name and params.get('replace', True):
            try:
                old = self.docker_client.containers.get(name)
                self.logger.info(f"Removing existing container {name}")
                old.stop(timeout=10)
                old.remove()
            except NotFound:
                pass

        # Build run kwargs
        run_kwargs = {
            'image': image,
            'detach': True,
        }
        if name:
            run_kwargs['name'] = name

        # Port mappings: {"8080": 80, "443": 443}
        ports = params.get('ports', {})
        if ports:
            run_kwargs['ports'] = {
                f"{container_port}/tcp": int(host_port)
                for host_port, container_port in ports.items()
            }

        # Environment variables
        env = params.get('environment', {})
        if env:
            run_kwargs['environment'] = env

        # Volume mounts: {"/host/path": {"bind": "/container/path", "mode": "rw"}}
        volumes = params.get('volumes', {})
        if volumes:
            run_kwargs['volumes'] = volumes

        # Network
        network = params.get('network')
        if network:
            run_kwargs['network'] = network

        # Restart policy
        restart = params.get('restart_policy', 'unless-stopped')
        run_kwargs['restart_policy'] = {'Name': restart}

        # Resource limits
        mem_limit = params.get('memory_limit')
        if mem_limit:
            run_kwargs['mem_limit'] = mem_limit
        cpu_count = params.get('cpus')
        if cpu_count:
            run_kwargs['nano_cpus'] = int(float(cpu_count) * 1e9)

        container = self.docker_client.containers.run(**run_kwargs)
        container.reload()

        self.logger.info(f"Container {container.short_id} ({name or image}) deployed")
        return {
            "container_id": container.short_id,
            "name": container.name,
            "image": image,
            "status": container.status,
            "ports": str(container.ports),
        }

    def _docker_build(self, params: dict) -> dict:
        """Build a Docker image from a Dockerfile path or URL."""
        path = params.get('path', '.')
        tag = params.get('tag')
        dockerfile = params.get('dockerfile', 'Dockerfile')
        if not tag:
            raise ValueError("tag is required")

        self.logger.info(f"Building image {tag} from {path}")
        image, build_log = self.docker_client.images.build(
            path=path,
            tag=tag,
            dockerfile=dockerfile,
            rm=True,
        )
        log_lines = []
        for chunk in build_log:
            if 'stream' in chunk:
                log_lines.append(chunk['stream'].strip())

        return {
            "image_id": image.short_id,
            "tag": tag,
            "status": "built",
            "log_tail": log_lines[-10:] if log_lines else [],
        }

    def _scale_service(self, params: dict) -> dict:
        """Scale a service by running multiple container replicas."""
        image = params.get('image')
        name_prefix = params.get('name', 'svc')
        replicas = int(params.get('replicas', 1))
        if not image:
            raise ValueError("image is required")

        created = []
        for i in range(replicas):
            container_name = f"{name_prefix}-{i}"
            result = self._deploy_container({
                **params,
                'name': container_name,
                'replace': True,
            })
            created.append(result)

        return {
            "service": name_prefix,
            "replicas": len(created),
            "containers": created,
        }

    def _list_containers(self, params: dict) -> dict:
        """List containers, optionally filtered by status or name."""
        show_all = params.get('all', True)
        name_filter = params.get('name', '')

        filters = {}
        if name_filter:
            filters['name'] = name_filter
        status_filter = params.get('status')
        if status_filter:
            filters['status'] = status_filter

        containers = self.docker_client.containers.list(
            all=show_all, filters=filters
        )
        return {
            "containers": [
                {
                    "id": c.short_id,
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:12],
                    "status": c.status,
                    "created": str(c.attrs.get('Created', '')),
                    "ports": str(c.ports) if c.ports else '',
                }
                for c in containers
            ]
        }

    def _stop_container(self, params: dict) -> dict:
        """Stop a running container by name or ID."""
        name = params.get('name') or params.get('container_id')
        if not name:
            raise ValueError("name or container_id is required")

        container = self.docker_client.containers.get(name)
        container.stop(timeout=int(params.get('timeout', 10)))
        return {"name": container.name, "status": "stopped"}

    def _remove_container(self, params: dict) -> dict:
        """Stop and remove a container."""
        name = params.get('name') or params.get('container_id')
        if not name:
            raise ValueError("name or container_id is required")

        container = self.docker_client.containers.get(name)
        force = params.get('force', False)
        container.remove(force=force)
        return {"name": name, "status": "removed"}

    def _container_logs(self, params: dict) -> dict:
        """Retrieve recent logs from a container."""
        name = params.get('name') or params.get('container_id')
        if not name:
            raise ValueError("name or container_id is required")

        tail = int(params.get('tail', 100))
        container = self.docker_client.containers.get(name)
        logs = container.logs(tail=tail, timestamps=True).decode('utf-8', errors='replace')
        return {
            "name": container.name,
            "lines": tail,
            "logs": logs,
        }

    def _pull_image(self, params: dict) -> dict:
        """Pull a Docker image."""
        image = params.get('image')
        if not image:
            raise ValueError("image is required")

        self.logger.info(f"Pulling image {image}")
        pulled = self.docker_client.images.pull(image)
        return {
            "image": image,
            "id": pulled.short_id,
            "tags": pulled.tags,
            "status": "pulled",
        }


# ==================== MAIN ====================

agent = MercuryAgent()
app = agent.create_app()


@app.get("/containers")
async def containers_endpoint():
    try:
        return await asyncio.to_thread(agent._list_containers, {})
    except Exception as e:
        return {"error": str(e), "containers": []}


if __name__ == '__main__':
    agent.run()
