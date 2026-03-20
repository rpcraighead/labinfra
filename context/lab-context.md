# CyberFlight Lab — Infrastructure Context
# This file is mounted into agent containers for LLM context.

## Network
| Network | Subnet | Gateway | Purpose |
|---------|--------|---------|---------|
| LAN | 10.0.50.0/24 | 10.0.50.1 (GL-MT6000) | Home network |
| DMZ | 10.0.8.0/24 | 10.0.8.1 (GL-MT6000) | Lab / servers |
| WireGuard | 10.0.0.0/24 | 10.0.0.1 | VPN tunnel |

## Router — GL-MT6000 (OpenWrt)
- LAN IP: 10.0.50.1
- DMZ IP: 10.0.8.1
- SSH: root@10.0.8.1 (key auth, dropbear)
- Firewall: UCI-based (fw3), zones: lan, wan, guest, wgserver, dmz
- DMZ zone input policy: reject (explicit rules needed for access)

## Proxmox Cluster — rpc-cyber-dc-01
| Node | IP | CPU | RAM | GPU |
|------|-----|-----|-----|-----|
| pve1 | 10.0.8.101 | i9-13900H (14C/20T) | 62 GB | — |
| pve2 | 10.0.8.123 | i5-4590 (4C/4T) | 15 GB | — |
| bighost | 10.0.8.200 | i5-12600K (10C/16T) | 62 GB | RTX 4070 |

## VM Inventory
| VMID | Name | Node | OS | IP | Typical Status |
|------|------|------|----|----|----------------|
| 100 | RonClaw | pve1 | Linux | 10.0.8.10 | running |
| 101 | BethClaw | pve1 | Linux | — | stopped |
| 102 | bigbrain | bighost | Linux | 10.0.8.50 | running |
| 103 | cainfra01 | pve1 | Rocky Linux | 10.0.8.121 | running |
| 104 | cadc02 | pve2 | Windows | 10.0.8.132 | running |
| 105 | cadc01 | pve1 | Windows Server 2019 | 10.0.8.189 | running |
| 107 | Kali | bighost | Kali Linux | TBD | installing |

## Key Servers
- **cadc01** (10.0.8.189): Primary AD domain controller, DNS, DHCP for DMZ
- **cainfra01** (10.0.8.121): Docker host — LibreNMS, Graylog, Gitea, Homarr, MkDocs, PrivacyIDEA, Portainer, nginx proxy
- **cainfra02** (10.0.8.122): Agent swarm host — this stack runs here
- **bigbrain** (10.0.8.50): Ollama LLM inference (RTX 4070 GPU passthrough)
- **RonClaw** (10.0.8.10): OpenClaw AI assistant (Ralph the Raccoon)

## Domain
- AD Domain: rpc-cyberflight.com
- DNS Server: cadc01 (10.0.8.189)

## Agent Swarm (this system)
- Deployed on: cainfra02 (10.0.8.122)
- Conductor: port 8000
- Superintendent: port 8001 (Proxmox management)
- Mercury: port 8002 (Docker containers on cainfra02)
- DaVinci: port 8003 (IaC code generation)
- Sapper: port 8004 (OpenWrt firewall via SSH to 10.0.8.1)
- Monitor: port 8005, Scribe: port 8006, Judge: port 8007
- LLM: BigBrain Ollama at 10.0.8.55:11434
