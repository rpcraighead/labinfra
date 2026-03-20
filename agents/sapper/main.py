# Sapper — Network / Firewall Agent
# Manages network configuration, firewall rules, and routing via SSH to target hosts.

import os
import logging
import sys
import asyncio
import json
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncssh
from base import BaseAgent

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


class SapperAgent(BaseAgent):
    def __init__(self):
        super().__init__('sapper', port=8004)
        self.ssh_key_path = os.getenv('SSH_KEY_PATH', '')
        self.ssh_user = os.getenv('SSH_USER', 'root')
        self.firewall_host = os.getenv('FIREWALL_ENDPOINT', '')
        self.default_gateway = os.getenv('DEFAULT_GATEWAY', '')

    async def _ssh_exec(self, host: str, command: str, user: str = None) -> dict:
        """Execute a command on a remote host via SSH."""
        connect_kwargs = {
            'host': host,
            'username': user or self.ssh_user,
            'known_hosts': None,
        }
        if self.ssh_key_path and os.path.exists(self.ssh_key_path):
            connect_kwargs['client_keys'] = [self.ssh_key_path]

        async with asyncssh.connect(**connect_kwargs) as conn:
            result = await conn.run(command, check=False)
            return {
                'stdout': result.stdout.strip() if result.stdout else '',
                'stderr': result.stderr.strip() if result.stderr else '',
                'exit_code': result.exit_status,
            }

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        handlers = {
            'configure_network': self._configure_network,
            'update_firewall': self._update_firewall,
            'modify_routes': self._modify_routes,
            'apply_policy': self._apply_policy,
            'network_status': self._network_status,
            'ping_test': self._ping_test,
        }
        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unknown operation: {operation}")
        return await handler(params)

    # ==================== NETWORK CONFIGURATION ====================

    async def _configure_network(self, params: dict) -> dict:
        """Configure a network interface on a target host."""
        host = params.get('host')
        if not host:
            raise ValueError("host is required")

        interface = params.get('interface', 'eth0')
        ip_address = params.get('ip_address')
        netmask = params.get('netmask', '255.255.255.0')
        gateway = params.get('gateway', '')
        vlan = params.get('vlan')

        if not ip_address:
            raise ValueError("ip_address is required")

        # Build netplan-style config (Ubuntu/Debian)
        config_method = params.get('method', 'netplan')

        if config_method == 'netplan':
            iface_name = f"{interface}.{vlan}" if vlan else interface
            netplan_config = {
                'network': {
                    'version': 2,
                    'ethernets': {
                        iface_name: {
                            'addresses': [f"{ip_address}/{self._netmask_to_cidr(netmask)}"],
                        }
                    }
                }
            }
            if gateway:
                netplan_config['network']['ethernets'][iface_name]['routes'] = [
                    {'to': 'default', 'via': gateway}
                ]
            if vlan:
                netplan_config['network']['vlans'] = {
                    iface_name: {'id': int(vlan), 'link': interface}
                }
                del netplan_config['network']['ethernets'][iface_name]

            import yaml
            config_yaml = yaml.dump(netplan_config, default_flow_style=False)
            config_file = f"/etc/netplan/60-sapper-{iface_name}.yaml"

            # Write config and apply
            result = await self._ssh_exec(host,
                f"echo '{config_yaml}' | sudo tee {config_file} && sudo netplan apply"
            )
            if result['exit_code'] != 0:
                raise RuntimeError(f"netplan apply failed: {result['stderr']}")

            return {
                "host": host, "interface": iface_name,
                "ip_address": ip_address, "method": "netplan",
                "config_file": config_file, "status": "applied",
            }
        else:
            # Direct ip command (temporary)
            cidr = self._netmask_to_cidr(netmask)
            cmds = [f"sudo ip addr add {ip_address}/{cidr} dev {interface}"]
            if gateway:
                cmds.append(f"sudo ip route add default via {gateway} dev {interface}")

            result = await self._ssh_exec(host, ' && '.join(cmds))
            return {
                "host": host, "interface": interface,
                "ip_address": ip_address, "method": "ip_command",
                "status": "applied_temporary",
                "warning": "This config will not persist across reboots",
            }

    async def _update_firewall(self, params: dict) -> dict:
        """Add or remove firewall rules on a target host."""
        host = params.get('host') or self.firewall_host
        if not host:
            raise ValueError("host or FIREWALL_ENDPOINT is required")

        action = params.get('action', 'add')  # add | remove
        rule_type = params.get('rule_type', 'iptables')  # iptables | ufw | nftables
        chain = params.get('chain', 'INPUT')
        protocol = params.get('protocol', 'tcp')
        port = params.get('port')
        source = params.get('source', '')
        target_action = params.get('target', 'ACCEPT')
        comment = params.get('comment', 'sapper-managed')

        if not port:
            raise ValueError("port is required")

        if rule_type == 'ufw':
            if action == 'add':
                cmd = f"sudo ufw allow {port}/{protocol}"
                if source:
                    cmd = f"sudo ufw allow from {source} to any port {port} proto {protocol}"
            else:
                cmd = f"sudo ufw delete allow {port}/{protocol}"
            cmd += f" comment '{comment}'"

        elif rule_type == 'iptables':
            flag = '-A' if action == 'add' else '-D'
            cmd = f"sudo iptables {flag} {chain} -p {protocol} --dport {port}"
            if source:
                cmd += f" -s {source}"
            cmd += f" -j {target_action} -m comment --comment '{comment}'"
        else:
            raise ValueError(f"Unsupported rule_type: {rule_type}")

        result = await self._ssh_exec(host, cmd)
        if result['exit_code'] != 0:
            raise RuntimeError(f"Firewall update failed: {result['stderr']}")

        return {
            "host": host, "action": action, "rule_type": rule_type,
            "port": port, "protocol": protocol, "source": source,
            "target": target_action, "status": "applied",
        }

    async def _modify_routes(self, params: dict) -> dict:
        """Add or remove static routes on a target host."""
        host = params.get('host')
        if not host:
            raise ValueError("host is required")

        action = params.get('action', 'add')
        destination = params.get('destination')
        gateway = params.get('gateway')
        interface = params.get('interface', '')

        if not destination or not gateway:
            raise ValueError("destination and gateway are required")

        cmd = f"sudo ip route {action} {destination} via {gateway}"
        if interface:
            cmd += f" dev {interface}"

        result = await self._ssh_exec(host, cmd)
        if result['exit_code'] != 0:
            raise RuntimeError(f"Route modification failed: {result['stderr']}")

        return {
            "host": host, "action": action,
            "destination": destination, "gateway": gateway,
            "status": "applied",
        }

    async def _apply_policy(self, params: dict) -> dict:
        """Apply a named network policy (a set of firewall rules + routes)."""
        policy_name = params.get('policy')
        if not policy_name:
            raise ValueError("policy name is required")

        # Policies are defined as YAML files or inline
        rules = params.get('rules', [])
        if not rules:
            return {
                "status": "not_implemented",
                "message": f"Policy '{policy_name}' not found. Define rules inline or create a policy file.",
            }

        results = []
        for rule in rules:
            rule_type = rule.get('type', 'firewall')
            if rule_type == 'firewall':
                r = await self._update_firewall(rule)
            elif rule_type == 'route':
                r = await self._modify_routes(rule)
            else:
                r = {"error": f"Unknown rule type: {rule_type}"}
            results.append(r)

        return {"policy": policy_name, "rules_applied": len(results), "results": results}

    # ==================== READ OPERATIONS ====================

    async def _network_status(self, params: dict) -> dict:
        """Get network interface and routing info from a host."""
        host = params.get('host')
        if not host:
            raise ValueError("host is required")

        interfaces = await self._ssh_exec(host, "ip -j addr show")
        routes = await self._ssh_exec(host, "ip -j route show")
        fw_rules = await self._ssh_exec(host, "sudo iptables -L -n --line-numbers 2>/dev/null || sudo ufw status numbered 2>/dev/null || echo 'no firewall info'")

        ifaces = []
        if interfaces['exit_code'] == 0 and interfaces['stdout']:
            try:
                ifaces = json.loads(interfaces['stdout'])
            except json.JSONDecodeError:
                ifaces = interfaces['stdout']

        route_list = []
        if routes['exit_code'] == 0 and routes['stdout']:
            try:
                route_list = json.loads(routes['stdout'])
            except json.JSONDecodeError:
                route_list = routes['stdout']

        return {
            "host": host,
            "interfaces": ifaces,
            "routes": route_list,
            "firewall": fw_rules['stdout'],
        }

    async def _ping_test(self, params: dict) -> dict:
        """Connectivity test from a source host to a target."""
        host = params.get('host') or params.get('source', 'localhost')
        target = params.get('target')
        count = params.get('count', 3)
        if not target:
            raise ValueError("target is required")

        result = await self._ssh_exec(host, f"ping -c {int(count)} -W 3 {target}")
        return {
            "source": host, "target": target,
            "success": result['exit_code'] == 0,
            "output": result['stdout'],
        }

    # ==================== HELPERS ====================

    @staticmethod
    def _netmask_to_cidr(netmask: str) -> int:
        """Convert dotted netmask to CIDR prefix length."""
        return sum(bin(int(x)).count('1') for x in netmask.split('.'))


# ==================== MAIN ====================

agent = SapperAgent()
app = agent.create_app()

if __name__ == '__main__':
    agent.run()
