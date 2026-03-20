# Sapper — Network / Firewall Agent
# Manages OpenWrt firewall (UCI), network configuration, and routing via SSH.
# Primary target: GL-MT6000 router running OpenWrt.

import os
import logging
import sys
import asyncio
import json
import shlex
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

    # ==================== UCI HELPERS ====================

    async def _uci_exec(self, command: str) -> dict:
        """Run a UCI command on the OpenWrt firewall host."""
        if not self.firewall_host:
            raise ValueError("FIREWALL_ENDPOINT not configured")
        return await self._ssh_exec(self.firewall_host, command)

    async def _uci_get(self, key: str) -> str:
        """Get a UCI config value."""
        result = await self._uci_exec(f"uci get {shlex.quote(key)}")
        if result['exit_code'] != 0:
            raise ValueError(f"uci get {key} failed: {result['stderr']}")
        return result['stdout']

    async def _uci_set(self, key: str, value: str) -> dict:
        """Set a UCI config value (does NOT commit)."""
        result = await self._uci_exec(f"uci set {shlex.quote(key + '=' + value)}")
        if result['exit_code'] != 0:
            raise RuntimeError(f"uci set failed: {result['stderr']}")
        return result

    async def _uci_commit_and_reload(self, subsystem: str = 'firewall') -> dict:
        """Commit UCI changes and reload the subsystem."""
        result = await self._uci_exec(
            f"uci commit {subsystem} && /etc/init.d/{subsystem} reload"
        )
        if result['exit_code'] != 0:
            raise RuntimeError(f"commit/reload {subsystem} failed: {result['stderr']}")
        self.logger.info(f"UCI {subsystem} committed and reloaded")
        return result

    async def _uci_show_parsed(self, config: str) -> list:
        """Run uci show <config> and parse into a list of dicts grouped by section."""
        result = await self._uci_exec(f"uci show {shlex.quote(config)}")
        if result['exit_code'] != 0:
            return []

        sections = {}
        for line in result['stdout'].splitlines():
            if '=' not in line:
                continue
            key, _, value = line.partition('=')
            value = value.strip("'\"")
            # key looks like: firewall.@rule[3].name
            parts = key.split('.', 2)
            if len(parts) < 2:
                continue
            section_id = parts[1] if len(parts) == 2 else parts[1]
            option = parts[2] if len(parts) == 3 else '_type'

            if section_id not in sections:
                sections[section_id] = {'_section': section_id}
            sections[section_id][option] = value

        return list(sections.values())

    # ==================== TASK HANDLER ====================

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        handlers = {
            # OpenWrt firewall (UCI)
            'fw_list_zones': self._fw_list_zones,
            'fw_list_rules': self._fw_list_rules,
            'fw_list_redirects': self._fw_list_redirects,
            'fw_list_forwarding': self._fw_list_forwarding,
            'fw_add_rule': self._fw_add_rule,
            'fw_delete_rule': self._fw_delete_rule,
            'fw_add_redirect': self._fw_add_redirect,
            'fw_delete_redirect': self._fw_delete_redirect,
            'fw_add_forwarding': self._fw_add_forwarding,
            'fw_status': self._fw_status,
            # Generic network (Linux hosts)
            'configure_network': self._configure_network,
            'update_firewall': self._update_firewall,
            'modify_routes': self._modify_routes,
            'network_status': self._network_status,
            'ping_test': self._ping_test,
        }
        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unknown operation: {operation}")
        return await handler(params)

    # ==================== OPENWRT FIREWALL — READ ====================

    async def _fw_status(self, params: dict) -> dict:
        """Get full OpenWrt firewall status: zones, rules, redirects, forwarding."""
        zones = await self._fw_list_zones(params)
        rules = await self._fw_list_rules(params)
        redirects = await self._fw_list_redirects(params)
        forwarding = await self._fw_list_forwarding(params)

        # Also grab iptables counters for traffic stats
        iptables = await self._uci_exec("iptables -L -n -v --line-numbers 2>/dev/null | head -80")

        return {
            "host": self.firewall_host,
            "zones": zones.get('zones', []),
            "rules": rules.get('rules', []),
            "redirects": redirects.get('redirects', []),
            "forwarding": forwarding.get('forwarding', []),
            "iptables_summary": iptables.get('stdout', ''),
        }

    async def _fw_list_zones(self, params: dict) -> dict:
        """List all firewall zones."""
        result = await self._uci_exec(
            "uci show firewall | grep '=zone$'"
        )
        zones = []
        if result['exit_code'] == 0:
            for line in result['stdout'].splitlines():
                section = line.split('=')[0].replace('firewall.', '')
                zone_data = await self._uci_exec(f"uci show firewall.{section}")
                zone = {'_section': section}
                for zl in zone_data['stdout'].splitlines():
                    if '=' not in zl:
                        continue
                    k, _, v = zl.partition('=')
                    option = k.split('.')[-1]
                    zone[option] = v.strip("'\"")
                zones.append(zone)
        return {"zones": zones}

    async def _fw_list_rules(self, params: dict) -> dict:
        """List all firewall traffic rules."""
        result = await self._uci_exec(
            "uci show firewall | grep '=rule$'"
        )
        rules = []
        if result['exit_code'] == 0:
            for line in result['stdout'].splitlines():
                section = line.split('=')[0].replace('firewall.', '')
                rule_data = await self._uci_exec(f"uci show firewall.{section}")
                rule = {'_section': section}
                for rl in rule_data['stdout'].splitlines():
                    if '=' not in rl:
                        continue
                    k, _, v = rl.partition('=')
                    option = k.split('.')[-1]
                    rule[option] = v.strip("'\"")
                rules.append(rule)
        return {"rules": rules}

    async def _fw_list_redirects(self, params: dict) -> dict:
        """List all port forwarding (DNAT) rules."""
        result = await self._uci_exec(
            "uci show firewall | grep '=redirect$'"
        )
        redirects = []
        if result['exit_code'] == 0:
            for line in result['stdout'].splitlines():
                section = line.split('=')[0].replace('firewall.', '')
                redir_data = await self._uci_exec(f"uci show firewall.{section}")
                redir = {'_section': section}
                for rl in redir_data['stdout'].splitlines():
                    if '=' not in rl:
                        continue
                    k, _, v = rl.partition('=')
                    option = k.split('.')[-1]
                    redir[option] = v.strip("'\"")
                redirects.append(redir)
        return {"redirects": redirects}

    async def _fw_list_forwarding(self, params: dict) -> dict:
        """List zone-to-zone forwarding rules."""
        result = await self._uci_exec(
            "uci show firewall | grep '=forwarding$'"
        )
        fwds = []
        if result['exit_code'] == 0:
            for line in result['stdout'].splitlines():
                section = line.split('=')[0].replace('firewall.', '')
                fwd_data = await self._uci_exec(f"uci show firewall.{section}")
                fwd = {'_section': section}
                for fl in fwd_data['stdout'].splitlines():
                    if '=' not in fl:
                        continue
                    k, _, v = fl.partition('=')
                    option = k.split('.')[-1]
                    fwd[option] = v.strip("'\"")
                fwds.append(fwd)
        return {"forwarding": fwds}

    # ==================== OPENWRT FIREWALL — WRITE ====================

    async def _fw_add_rule(self, params: dict) -> dict:
        """Add a traffic rule to the OpenWrt firewall via UCI.

        Params:
            name:       Rule name (required)
            src:        Source zone (e.g. 'wan', 'lan', 'dmz')
            dest:       Destination zone
            proto:      Protocol — 'tcp', 'udp', 'tcpudp', 'icmp', etc.
            dest_port:  Destination port or range (e.g. '443', '8000-8100')
            src_ip:     Source IP/CIDR to match
            dest_ip:    Destination IP/CIDR to match
            target:     'ACCEPT', 'DROP', 'REJECT' (default ACCEPT)
            enabled:    '1' or '0' (default '1')
            family:     'ipv4', 'ipv6', or 'any'
        """
        name = params.get('name')
        if not name:
            raise ValueError("rule name is required")

        # Add unnamed rule section
        result = await self._uci_exec("uci add firewall rule")
        if result['exit_code'] != 0:
            raise RuntimeError(f"uci add failed: {result['stderr']}")
        section = result['stdout'].strip()  # e.g. "cfg0a1234"

        # Set rule options
        uci_cmds = [f"uci set firewall.{section}.name={shlex.quote(name)}"]

        option_map = {
            'src': 'src', 'dest': 'dest', 'proto': 'proto',
            'dest_port': 'dest_port', 'src_port': 'src_port',
            'src_ip': 'src_ip', 'dest_ip': 'dest_ip',
            'target': 'target', 'family': 'family', 'enabled': 'enabled',
            'icmp_type': 'icmp_type',
        }
        for param_key, uci_key in option_map.items():
            value = params.get(param_key)
            if value is not None:
                uci_cmds.append(
                    f"uci set firewall.{section}.{uci_key}={shlex.quote(str(value))}"
                )

        # Default target to ACCEPT if not specified
        if 'target' not in params:
            uci_cmds.append(f"uci set firewall.{section}.target='ACCEPT'")

        cmd = ' && '.join(uci_cmds)
        result = await self._uci_exec(cmd)
        if result['exit_code'] != 0:
            raise RuntimeError(f"Failed setting rule options: {result['stderr']}")

        await self._uci_commit_and_reload('firewall')

        return {
            "action": "add_rule", "section": section, "name": name,
            "status": "applied",
        }

    async def _fw_delete_rule(self, params: dict) -> dict:
        """Delete a firewall rule by name or section ID.

        Params:
            name:    Rule name to search for and delete
            section: UCI section ID to delete directly (e.g. '@rule[3]' or 'cfg0a1234')
        """
        section = params.get('section')
        name = params.get('name')

        if not section and not name:
            raise ValueError("name or section is required")

        if not section:
            # Find section by name
            section = await self._find_fw_section('rule', name)

        result = await self._uci_exec(f"uci delete firewall.{section}")
        if result['exit_code'] != 0:
            raise RuntimeError(f"uci delete failed: {result['stderr']}")

        await self._uci_commit_and_reload('firewall')

        return {
            "action": "delete_rule", "section": section,
            "name": name, "status": "deleted",
        }

    async def _fw_add_redirect(self, params: dict) -> dict:
        """Add a port forward (DNAT redirect) to the OpenWrt firewall.

        Params:
            name:       Rule name (required)
            src:        Source zone (default 'wan')
            dest:       Destination zone (default 'dmz' or 'lan')
            proto:      Protocol (default 'tcp')
            src_dport:  External port to forward
            dest_ip:    Internal destination IP
            dest_port:  Internal destination port
            target:     'DNAT' (default) or 'SNAT'
            enabled:    '1' or '0'
        """
        name = params.get('name')
        if not name:
            raise ValueError("redirect name is required")

        result = await self._uci_exec("uci add firewall redirect")
        if result['exit_code'] != 0:
            raise RuntimeError(f"uci add redirect failed: {result['stderr']}")
        section = result['stdout'].strip()

        uci_cmds = [
            f"uci set firewall.{section}.name={shlex.quote(name)}",
            f"uci set firewall.{section}.target={shlex.quote(params.get('target', 'DNAT'))}",
            f"uci set firewall.{section}.src={shlex.quote(params.get('src', 'wan'))}",
        ]

        option_map = {
            'dest': 'dest', 'proto': 'proto', 'src_dport': 'src_dport',
            'dest_ip': 'dest_ip', 'dest_port': 'dest_port',
            'src_ip': 'src_ip', 'enabled': 'enabled', 'reflection': 'reflection',
        }
        for param_key, uci_key in option_map.items():
            value = params.get(param_key)
            if value is not None:
                uci_cmds.append(
                    f"uci set firewall.{section}.{uci_key}={shlex.quote(str(value))}"
                )

        # Default proto to tcp if not given
        if 'proto' not in params:
            uci_cmds.append(f"uci set firewall.{section}.proto='tcp'")

        cmd = ' && '.join(uci_cmds)
        result = await self._uci_exec(cmd)
        if result['exit_code'] != 0:
            raise RuntimeError(f"Failed setting redirect options: {result['stderr']}")

        await self._uci_commit_and_reload('firewall')

        return {
            "action": "add_redirect", "section": section, "name": name,
            "dest_ip": params.get('dest_ip'), "src_dport": params.get('src_dport'),
            "status": "applied",
        }

    async def _fw_delete_redirect(self, params: dict) -> dict:
        """Delete a port forward by name or section ID."""
        section = params.get('section')
        name = params.get('name')

        if not section and not name:
            raise ValueError("name or section is required")

        if not section:
            section = await self._find_fw_section('redirect', name)

        result = await self._uci_exec(f"uci delete firewall.{section}")
        if result['exit_code'] != 0:
            raise RuntimeError(f"uci delete failed: {result['stderr']}")

        await self._uci_commit_and_reload('firewall')

        return {"action": "delete_redirect", "section": section, "name": name, "status": "deleted"}

    async def _fw_add_forwarding(self, params: dict) -> dict:
        """Add a zone-to-zone forwarding rule.

        Params:
            src:  Source zone (required)
            dest: Destination zone (required)
        """
        src = params.get('src')
        dest = params.get('dest')
        if not src or not dest:
            raise ValueError("src and dest zones are required")

        result = await self._uci_exec("uci add firewall forwarding")
        if result['exit_code'] != 0:
            raise RuntimeError(f"uci add forwarding failed: {result['stderr']}")
        section = result['stdout'].strip()

        cmd = (
            f"uci set firewall.{section}.src={shlex.quote(src)} && "
            f"uci set firewall.{section}.dest={shlex.quote(dest)}"
        )
        result = await self._uci_exec(cmd)
        if result['exit_code'] != 0:
            raise RuntimeError(f"Failed setting forwarding: {result['stderr']}")

        await self._uci_commit_and_reload('firewall')

        return {"action": "add_forwarding", "section": section, "src": src, "dest": dest, "status": "applied"}

    async def _find_fw_section(self, section_type: str, name: str) -> str:
        """Find a firewall section ID by its name option."""
        result = await self._uci_exec(
            f"uci show firewall | grep '={section_type}$'"
        )
        if result['exit_code'] != 0 or not result['stdout']:
            raise ValueError(f"No {section_type} sections found")

        for line in result['stdout'].splitlines():
            section_key = line.split('=')[0].replace('firewall.', '')
            name_result = await self._uci_exec(
                f"uci get firewall.{section_key}.name 2>/dev/null"
            )
            if name_result['exit_code'] == 0 and name_result['stdout'] == name:
                return section_key

        raise ValueError(f"{section_type} named '{name}' not found")

    # ==================== GENERIC LINUX NETWORK ====================

    async def _configure_network(self, params: dict) -> dict:
        """Configure a network interface on a target host (netplan or ip command)."""
        host = params.get('host')
        if not host:
            raise ValueError("host is required")

        interface = params.get('interface', 'eth0')
        ip_address = params.get('ip_address')
        netmask = params.get('netmask', '255.255.255.0')
        gateway = params.get('gateway', '')

        if not ip_address:
            raise ValueError("ip_address is required")

        config_method = params.get('method', 'netplan')

        if config_method == 'netplan':
            import yaml
            cidr = self._netmask_to_cidr(netmask)
            netplan_config = {
                'network': {
                    'version': 2,
                    'ethernets': {
                        interface: {
                            'addresses': [f"{ip_address}/{cidr}"],
                        }
                    }
                }
            }
            if gateway:
                netplan_config['network']['ethernets'][interface]['routes'] = [
                    {'to': 'default', 'via': gateway}
                ]

            config_yaml = yaml.dump(netplan_config, default_flow_style=False)
            config_file = f"/etc/netplan/60-sapper-{interface}.yaml"

            result = await self._ssh_exec(host,
                f"echo '{config_yaml}' | sudo tee {config_file} && sudo netplan apply"
            )
            if result['exit_code'] != 0:
                raise RuntimeError(f"netplan apply failed: {result['stderr']}")

            return {
                "host": host, "interface": interface,
                "ip_address": ip_address, "method": "netplan",
                "config_file": config_file, "status": "applied",
            }
        else:
            cidr = self._netmask_to_cidr(netmask)
            cmds = [f"sudo ip addr add {ip_address}/{cidr} dev {interface}"]
            if gateway:
                cmds.append(f"sudo ip route add default via {gateway} dev {interface}")

            result = await self._ssh_exec(host, ' && '.join(cmds))
            return {
                "host": host, "interface": interface,
                "ip_address": ip_address, "method": "ip_command",
                "status": "applied_temporary",
            }

    async def _update_firewall(self, params: dict) -> dict:
        """Add/remove firewall rules on a Linux host (iptables/ufw). For OpenWrt use fw_* ops."""
        host = params.get('host')
        if not host:
            raise ValueError("host is required for generic firewall ops")

        action = params.get('action', 'add')
        rule_type = params.get('rule_type', 'ufw')
        protocol = params.get('protocol', 'tcp')
        port = params.get('port')
        source = params.get('source', '')
        target_action = params.get('target', 'ACCEPT')

        if not port:
            raise ValueError("port is required")

        if rule_type == 'ufw':
            if action == 'add':
                cmd = f"sudo ufw allow {port}/{protocol}"
                if source:
                    cmd = f"sudo ufw allow from {source} to any port {port} proto {protocol}"
            else:
                cmd = f"sudo ufw delete allow {port}/{protocol}"
        elif rule_type == 'iptables':
            flag = '-A' if action == 'add' else '-D'
            chain = params.get('chain', 'INPUT')
            cmd = f"sudo iptables {flag} {chain} -p {protocol} --dport {port}"
            if source:
                cmd += f" -s {source}"
            cmd += f" -j {target_action}"
        else:
            raise ValueError(f"Unsupported rule_type: {rule_type}")

        result = await self._ssh_exec(host, cmd)
        if result['exit_code'] != 0:
            raise RuntimeError(f"Firewall update failed: {result['stderr']}")

        return {
            "host": host, "action": action, "rule_type": rule_type,
            "port": port, "protocol": protocol, "status": "applied",
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

    async def _network_status(self, params: dict) -> dict:
        """Get network info from a host. If no host given, queries the OpenWrt firewall."""
        host = params.get('host') or self.firewall_host
        if not host:
            raise ValueError("host is required")

        interfaces = await self._ssh_exec(host, "ip -j addr show 2>/dev/null || ip addr show")
        routes = await self._ssh_exec(host, "ip -j route show 2>/dev/null || ip route show")

        ifaces = interfaces['stdout']
        try:
            ifaces = json.loads(interfaces['stdout'])
        except (json.JSONDecodeError, TypeError):
            pass

        route_list = routes['stdout']
        try:
            route_list = json.loads(routes['stdout'])
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "host": host,
            "interfaces": ifaces,
            "routes": route_list,
        }

    async def _ping_test(self, params: dict) -> dict:
        """Connectivity test from a source host to a target."""
        host = params.get('host') or params.get('source') or self.firewall_host
        target = params.get('target') or params.get('name')
        count = params.get('count', 3)
        if not target or target in ('', 'all', 'unknown'):
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
