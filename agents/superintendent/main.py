# Superintendent — Infrastructure / Proxmox Agent
# Manages VMs and nodes on Proxmox VE clusters via the proxmoxer API.

import os
import logging
import sys
import asyncio
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from proxmoxer import ProxmoxAPI
from base import BaseAgent

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


class SuperintendentAgent(BaseAgent):
    def __init__(self):
        super().__init__('superintendent', port=8001)
        self.proxmox: Optional[ProxmoxAPI] = None

    async def connect(self):
        await super().connect()
        self._connect_proxmox()

    def _connect_proxmox(self):
        """Connect to Proxmox VE API."""
        endpoint = os.getenv('PROXMOX_ENDPOINT', '')
        username = os.getenv('PROXMOX_USERNAME', 'root@pam')
        token_name = os.getenv('PROXMOX_TOKEN_NAME', '')
        token_value = os.getenv('PROXMOX_TOKEN_VALUE', '')
        password = os.getenv('PROXMOX_PASSWORD', '')
        verify_ssl = os.getenv('PROXMOX_VERIFY_SSL', 'false').lower() == 'true'

        if not endpoint:
            self.logger.warning("PROXMOX_ENDPOINT not set — running in dry-run mode")
            return

        try:
            if token_name and token_value:
                self.proxmox = ProxmoxAPI(
                    endpoint, user=username,
                    token_name=token_name, token_value=token_value,
                    verify_ssl=verify_ssl,
                )
                self.logger.info(f"Proxmox connected via API token: {endpoint}")
            elif password:
                self.proxmox = ProxmoxAPI(
                    endpoint, user=username,
                    password=password, verify_ssl=verify_ssl,
                )
                self.logger.info(f"Proxmox connected via password: {endpoint}")
            else:
                self.logger.warning("No Proxmox credentials configured — dry-run mode")
        except Exception as e:
            self.logger.warning(f"Proxmox connection failed (non-fatal): {e}")

    def _require_proxmox(self):
        if not self.proxmox:
            raise RuntimeError("Proxmox API not connected — check PROXMOX_ENDPOINT and credentials")

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        handlers = {
            'list_vms': self._list_vms,
            'list_nodes': self._list_nodes,
            'vm_status': self._vm_status,
            'node_status': self._node_status,
            'system_status': self._system_status,
            'start_vm': self._start_vm,
            'stop_vm': self._stop_vm,
            'create_vm': self._create_vm,
            'apply_patch': self._apply_patch,
            'apply_configuration': self._apply_configuration,
        }
        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unknown operation: {operation}")
        return await asyncio.to_thread(handler, params)

    # ==================== READ OPERATIONS ====================

    def _list_nodes(self, params: dict) -> dict:
        """List all nodes in the Proxmox cluster."""
        self._require_proxmox()
        nodes = self.proxmox.nodes.get()
        return {
            "nodes": [
                {
                    "node": n['node'],
                    "status": n.get('status', 'unknown'),
                    "cpu": round(n.get('cpu', 0) * 100, 1),
                    "maxcpu": n.get('maxcpu', 0),
                    "mem_used_gb": round(n.get('mem', 0) / (1024**3), 1),
                    "mem_total_gb": round(n.get('maxmem', 0) / (1024**3), 1),
                    "uptime_hours": round(n.get('uptime', 0) / 3600, 1),
                }
                for n in nodes
            ]
        }

    def _list_vms(self, params: dict) -> dict:
        """List all VMs across all nodes."""
        self._require_proxmox()
        node_filter = params.get('node', '')
        all_vms = []

        nodes = self.proxmox.nodes.get()
        for node_info in nodes:
            node_name = node_info['node']
            if node_filter and node_name != node_filter:
                continue
            try:
                vms = self.proxmox.nodes(node_name).qemu.get()
                for vm in vms:
                    all_vms.append({
                        "vmid": vm['vmid'],
                        "name": vm.get('name', ''),
                        "status": vm.get('status', 'unknown'),
                        "node": node_name,
                        "cpus": vm.get('cpus', 0),
                        "mem_max_gb": round(vm.get('maxmem', 0) / (1024**3), 1),
                        "disk_max_gb": round(vm.get('maxdisk', 0) / (1024**3), 1),
                        "uptime_hours": round(vm.get('uptime', 0) / 3600, 1),
                    })
            except Exception as e:
                self.logger.warning(f"Failed to list VMs on {node_name}: {e}")

        return {"vms": all_vms}

    def _vm_status(self, params: dict) -> dict:
        """Get detailed status for a specific VM."""
        self._require_proxmox()
        vmid = params.get('vmid') or params.get('name')
        node = params.get('node')
        if not vmid:
            raise ValueError("vmid or name is required")

        vmid, node = self._resolve_vm(vmid, node)
        status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
        config = self.proxmox.nodes(node).qemu(vmid).config.get()

        return {
            "vmid": vmid,
            "name": status.get('name', ''),
            "node": node,
            "status": status.get('status', 'unknown'),
            "cpus": status.get('cpus', 0),
            "mem_used_gb": round(status.get('mem', 0) / (1024**3), 1),
            "mem_max_gb": round(status.get('maxmem', 0) / (1024**3), 1),
            "disk_max_gb": round(status.get('maxdisk', 0) / (1024**3), 1),
            "uptime_hours": round(status.get('uptime', 0) / 3600, 1),
            "qemu_agent": config.get('agent', 0),
            "boot_order": config.get('boot', ''),
            "net0": config.get('net0', ''),
        }

    def _node_status(self, params: dict) -> dict:
        """Get detailed status for a specific node."""
        self._require_proxmox()
        node = params.get('node') or params.get('name')
        if not node:
            raise ValueError("node name is required")

        status = self.proxmox.nodes(node).status.get()
        return {
            "node": node,
            "cpu_usage": round(status.get('cpu', 0) * 100, 1),
            "cpu_cores": status.get('cpuinfo', {}).get('cpus', 0),
            "cpu_model": status.get('cpuinfo', {}).get('model', ''),
            "mem_used_gb": round(status.get('memory', {}).get('used', 0) / (1024**3), 1),
            "mem_total_gb": round(status.get('memory', {}).get('total', 0) / (1024**3), 1),
            "swap_used_gb": round(status.get('swap', {}).get('used', 0) / (1024**3), 1),
            "swap_total_gb": round(status.get('swap', {}).get('total', 0) / (1024**3), 1),
            "uptime_hours": round(status.get('uptime', 0) / 3600, 1),
            "kernel": status.get('kversion', ''),
            "pveversion": status.get('pveversion', ''),
        }

    def _system_status(self, params: dict) -> dict:
        """Get an overview of the entire cluster: nodes + VM counts."""
        self._require_proxmox()
        nodes_data = self._list_nodes(params)
        summary = {
            "total_nodes": len(nodes_data['nodes']),
            "nodes_online": sum(1 for n in nodes_data['nodes'] if n['status'] == 'online'),
            "total_vms": 0,
            "vms_running": 0,
            "vms_stopped": 0,
            "nodes": [],
        }

        for node_info in nodes_data['nodes']:
            node_name = node_info['node']
            try:
                vms = self.proxmox.nodes(node_name).qemu.get()
                running = sum(1 for v in vms if v.get('status') == 'running')
                stopped = len(vms) - running
                summary['total_vms'] += len(vms)
                summary['vms_running'] += running
                summary['vms_stopped'] += stopped
                node_info['vms_running'] = running
                node_info['vms_stopped'] = stopped
            except Exception:
                node_info['vms_running'] = 'error'
                node_info['vms_stopped'] = 'error'
            summary['nodes'].append(node_info)

        return summary

    # ==================== WRITE OPERATIONS ====================

    def _start_vm(self, params: dict) -> dict:
        """Start a VM."""
        self._require_proxmox()
        vmid = params.get('vmid') or params.get('name')
        node = params.get('node')
        if not vmid:
            raise ValueError("vmid or name is required")

        vmid, node = self._resolve_vm(vmid, node)
        upid = self.proxmox.nodes(node).qemu(vmid).status.start.post()
        self.logger.info(f"VM {vmid} start requested on {node} (UPID: {upid})")
        return {"vmid": vmid, "node": node, "action": "start", "upid": str(upid)}

    def _stop_vm(self, params: dict) -> dict:
        """Stop a VM (ACPI shutdown, or force if timeout)."""
        self._require_proxmox()
        vmid = params.get('vmid') or params.get('name')
        node = params.get('node')
        force = params.get('force', False)
        if not vmid:
            raise ValueError("vmid or name is required")

        vmid, node = self._resolve_vm(vmid, node)
        if force:
            upid = self.proxmox.nodes(node).qemu(vmid).status.stop.post()
        else:
            upid = self.proxmox.nodes(node).qemu(vmid).status.shutdown.post()
        self.logger.info(f"VM {vmid} {'stop' if force else 'shutdown'} on {node} (UPID: {upid})")
        return {
            "vmid": vmid, "node": node,
            "action": "force_stop" if force else "shutdown",
            "upid": str(upid),
        }

    def _create_vm(self, params: dict) -> dict:
        """Create a new VM from parameters or a template clone."""
        self._require_proxmox()
        node = params.get('node')
        if not node:
            # Pick the first online node
            nodes = self.proxmox.nodes.get()
            online = [n for n in nodes if n.get('status') == 'online']
            if not online:
                raise RuntimeError("No online nodes available")
            node = online[0]['node']

        # Determine next available VMID
        vmid = params.get('vmid')
        if not vmid:
            vmid = self.proxmox.cluster.nextid.get()

        template_id = params.get('template_vmid') or params.get('clone_from')
        if template_id:
            # Clone from template
            clone_params = {
                'newid': int(vmid),
                'name': params.get('name', f'vm-{vmid}'),
                'full': params.get('full_clone', 1),
            }
            target_storage = params.get('storage')
            if target_storage:
                clone_params['storage'] = target_storage
            upid = self.proxmox.nodes(node).qemu(template_id).clone.post(**clone_params)
            self.logger.info(f"VM {vmid} cloned from template {template_id} on {node}")
            result = {
                "vmid": int(vmid), "node": node, "action": "clone",
                "template": template_id, "upid": str(upid),
            }
        else:
            # Create from scratch
            vm_config = {
                'vmid': int(vmid),
                'name': params.get('name', f'vm-{vmid}'),
                'memory': params.get('memory', 2048),
                'cores': params.get('cores', 2),
                'sockets': params.get('sockets', 1),
                'cpu': params.get('cpu_type', 'host'),
                'ostype': params.get('ostype', 'l26'),
                'net0': params.get('net0', 'virtio,bridge=vmbr0'),
            }
            # Optional: disk via scsi0
            storage = params.get('storage', 'local-lvm')
            disk_size = params.get('disk_size', '32G')
            vm_config['scsi0'] = f'{storage}:{disk_size}'
            vm_config['scsihw'] = 'virtio-scsi-single'
            vm_config['boot'] = 'order=scsi0'

            iso = params.get('iso')
            if iso:
                vm_config['ide2'] = f'{iso},media=cdrom'
                vm_config['boot'] = 'order=ide2;scsi0'

            self.proxmox.nodes(node).qemu.post(**vm_config)
            self.logger.info(f"VM {vmid} created on {node}: {vm_config.get('name')}")
            result = {
                "vmid": int(vmid), "node": node, "action": "create",
                "name": vm_config['name'],
                "cores": vm_config['cores'], "memory_mb": vm_config['memory'],
            }

        # Auto-start if requested
        if params.get('start', False):
            self.proxmox.nodes(node).qemu(vmid).status.start.post()
            result['started'] = True

        return result

    def _apply_patch(self, params: dict) -> dict:
        """Placeholder for system patching. Logs intent for now."""
        self.logger.info(f"apply_patch requested: {params}")
        return {
            "status": "not_implemented",
            "message": "System patching via Superintendent is planned but not yet wired. "
                       "Use Proxmox UI or SSH for now.",
        }

    def _apply_configuration(self, params: dict) -> dict:
        """Placeholder for applying IaC-generated config to VMs."""
        self.logger.info(f"apply_configuration requested: {params}")
        return {
            "status": "not_implemented",
            "message": "Configuration application is planned for DaVinci->Superintendent pipeline.",
        }

    # ==================== HELPERS ====================

    def _resolve_vm(self, vmid_or_name, node: str = None) -> tuple:
        """Resolve a VM by ID or name, returning (vmid, node)."""
        # If it's numeric, treat as VMID
        try:
            vmid = int(vmid_or_name)
            if node:
                return vmid, node
            # Find which node it's on
            for n in self.proxmox.nodes.get():
                try:
                    self.proxmox.nodes(n['node']).qemu(vmid).status.current.get()
                    return vmid, n['node']
                except Exception:
                    continue
            raise ValueError(f"VM {vmid} not found on any node")
        except (ValueError, TypeError):
            pass

        # Search by name
        name = str(vmid_or_name)
        for n in self.proxmox.nodes.get():
            try:
                for vm in self.proxmox.nodes(n['node']).qemu.get():
                    if vm.get('name') == name:
                        return vm['vmid'], n['node']
            except Exception:
                continue
        raise ValueError(f"VM '{name}' not found on any node")

    def create_app(self):
        app = super().create_app()

        @app.get("/nodes")
        async def nodes():
            if not self.proxmox:
                return {"error": "Proxmox not connected"}
            return await asyncio.to_thread(self._list_nodes, {})

        @app.get("/vms")
        async def vms():
            if not self.proxmox:
                return {"error": "Proxmox not connected"}
            return await asyncio.to_thread(self._list_vms, {})

        return app


# ==================== MAIN ====================

agent = SuperintendentAgent()
app = agent.create_app()

if __name__ == '__main__':
    agent.run()
