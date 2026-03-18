# Homelab Configuration — rpc-cyberflight.com

## Network Overview

| Network | Subnet | Purpose | DHCP |
|---------|--------|---------|------|
| LAN | 10.0.50.0/24 | Home network | GL-MT6000 router (10.0.50.1) |
| DMZ | 10.0.8.0/24 | Lab / servers | CADC01 (10.0.8.189) |

## Router — GL-MT6000

- **IP:** 10.0.50.1
- **OS:** OpenWrt (Linux 5.4.238, aarch64)
- **SSH:** root@10.0.50.1 (key auth via /etc/dropbear/authorized_keys)
- **DMZ DHCP:** Disabled (moved to CADC01)
- **LAN DHCP:** Active (10.0.50.100–250, 12h lease)
- **WireGuard Server:** wgserver interface, port 51820
  - Tunnel subnet: 10.0.0.0/24
  - Router tunnel IP: 10.0.0.1
  - Peers:
    | Peer | Tunnel IP | Purpose |
    |------|-----------|---------|
    | Ron mobile | 10.0.0.4 | Remote access |
    | Ron desktop | 10.0.0.3 | Remote access |
    | (unused) | 10.0.0.2 | Reserved |
    | cyberflight-wp (GCP) | 10.0.0.5 | Site-to-site: log forwarding, SNMP monitoring |
  - Firewall zones: wgserver↔dmz forwarding enabled (bidirectional), wgserver→wan forwarding enabled
  - DMZ route: cainfra01 has persistent route `10.0.0.0/24 via 10.0.8.1` for tunnel access

## Active Directory Domain

- **Domain:** rpc-cyberflight.com
- **NetBIOS:** RPCCYBER
- **Forest Level:** Windows2016Forest
- **DSRM Password:** (stored securely offline)

## Proxmox Cluster — rpc-cyber-dc-01

3-node cluster, Proxmox VE 6.17.2

| Node | IP | CPU | Cores / Threads | RAM | Disk | GPU | VMs |
|------|-----|-----|-----------------|-----|------|-----|-----|
| pve1 | 10.0.8.101 | Intel i9-13900H | 14 / 20 | 62 GB | 93 GB | — | 100, 101, 103, 105 |
| pve2 | 10.0.8.123 | Intel i5-4590 | 4 / 4 | 15 GB | 36 GB | — | 104 |
| bighost | 10.0.8.200 | Intel i5-12600K | 10 / 16 | 62 GB | 93 GB | RTX 4070 | 102, 107 |

### VM Inventory

| VMID | Name | Node | vCPU | RAM | Disk | OS | IP | Status |
|------|------|------|------|-----|------|----|----|--------|
| 100 | RonClaw | pve1 | 2 | 8 GB | 32G | Linux | 10.0.8.10 | running |
| 101 | BethClaw | pve1 | 2 | 8 GB | 32G | Linux | — | stopped |
| 102 | bigbrain | bighost | 12 | 40 GB | 256G | Linux | 10.0.8.50 | running |
| 103 | cainfra01 | pve1 | 2 | 8 GB | 128G | Rocky Linux 10.1 | 10.0.8.121 | running |
| 104 | cadc02 | pve2 | 4 | 12 GB | 256G (USB) | Windows | 10.0.8.132 | running |
| 105 | cadc01 | pve1 | 4 | 16 GB | — | Windows Server 2019 | 10.0.8.189 | running |
| 107 | Kali | bighost | 4 | 4 GB | 60G | Kali Linux 2025.4 | TBD | installing |

### bigbrain GPU Passthrough

- **GPU:** NVIDIA GeForce RTX 4070 (AD104)
- **PCI:** 0000:01:00.0 passed through to VM 102
- **CPU mode:** host (full passthrough)
- **Autostart:** yes
- **Purpose:** Ollama LLM inference (qwen3:8b, qwen3:14b, qwen3:32b)

## Servers

### CADC01 — Primary Domain Controller

- **IP:** 10.0.8.189
- **MAC:** xx:xx:xx:xx:xx:xx
- **OS:** Windows Server 2019 Standard Evaluation (Build 17763)
- **Platform:** QEMU VM (SeaBIOS)
- **SSH:** Administrator@10.0.8.189 (key auth via C:\ProgramData\ssh\administrators_authorized_keys)
- **Roles:**
  - Active Directory Domain Services
  - DNS Server
  - DHCP Server (authorized in AD)

#### DHCP Configuration (DMZ Scope)

- **Scope:** 10.0.8.0/24 "DMZ"
- **Range:** 10.0.8.100 – 10.0.8.200
- **Exclusion:** 10.0.8.100 – 10.0.8.140 (static/server IPs)
- **Lease:** 8 hours
- **Options:**
  - Gateway: 10.0.8.1
  - DNS: 10.0.8.189 (CADC01)
  - Domain: rpc-cyberflight.com

#### DNS Records (rpc-cyberflight.com zone)

| Record | Type | Value |
|--------|------|-------|
| cainfra01 | A | 10.0.8.121 |
| dashboard | CNAME | cainfra01.rpc-cyberflight.com |
| librenms | CNAME | cainfra01.rpc-cyberflight.com |
| graylog | CNAME | cainfra01.rpc-cyberflight.com |
| docs | CNAME | cainfra01.rpc-cyberflight.com |
| mfa | CNAME | cainfra01.rpc-cyberflight.com |
| portainer | CNAME | cainfra01.rpc-cyberflight.com |
| git | CNAME | cainfra01.rpc-cyberflight.com |
| cyberflight | A | 34.168.189.230 (Google Cloud) |
| flightplanner | CNAME | ghs.googlehosted.com (Google Cloud Run) |

#### DHCP Reservations

| IP | MAC | Hostname |
|----|-----|----------|
| 10.0.8.121 | xx:xx:xx:xx:xx:xx | cainfra01 |
| 10.0.8.128 | xx:xx:xx:xx:xx:xx | TL-SG1024DE |
| 10.0.8.132 | xx:xx:xx:xx:xx:xx | cadc02 |
| 10.0.8.159 | xx:xx:xx:xx:xx:xx | Pi5Desktop |

### cadc02

- **IP:** 10.0.8.132
- **MAC:** xx:xx:xx:xx:xx:xx
- **Role:** TBD (second domain controller?)

### cainfra01 — Infrastructure / Monitoring Server

- **IP:** 10.0.8.121
- **MAC:** xx:xx:xx:xx:xx:xx
- **OS:** Rocky Linux 10.1 (Red Quartz), kernel 6.12.0
- **Platform:** QEMU VM (2 vCPU, 7.5 GB RAM, 70 GB disk)
- **SSH:** root@10.0.8.121 (key auth)
- **Container runtime:** Docker
- **Compose locations:** /opt/librenms/, /opt/graylog/, /opt/homarr/, /opt/mkdocs/, /opt/nginx-proxy/, /opt/privacyidea/, /opt/portainer/, /home/ron/wordpress/, /home/ron/gitea/

#### Nginx Reverse Proxy

- **Compose:** /opt/nginx-proxy/docker-compose.yml
- **Container:** nginx:alpine (port 80)
- **Config:** /opt/nginx-proxy/conf.d/default.conf
- **Vhosts:**
  - dashboard.rpc-cyberflight.com → Homarr (7575)
  - librenms.rpc-cyberflight.com → LibreNMS (8000)
  - graylog.rpc-cyberflight.com → Graylog (9000)
  - docs.rpc-cyberflight.com → MkDocs (8000)
  - mfa.rpc-cyberflight.com → PrivacyIDEA (8080)
  - portainer.rpc-cyberflight.com → Portainer (9443)
  - git.rpc-cyberflight.com → Gitea (3000)
  - cyberflight.rpc-cyberflight.com → (migrated to Google Cloud, vhost can be removed)
- **Default:** redirects to dashboard.rpc-cyberflight.com

#### PrivacyIDEA (Multi-Factor Authentication)

- **Web UI:** http://mfa.rpc-cyberflight.com (direct: http://10.0.8.121:5001)
- **Compose:** /opt/privacyidea/docker-compose.yml
- **Container:** gpappsoft/privacyidea-docker:latest (port 5001→8080)
- **Admin login:** admin / (see secrets vault)
- **LDAP Resolver:** ad-resolver → ldap://10.0.8.189 (CADC01)
- **Realm:** rpc-cyberflight (default)
- **Enrolled tokens:**
  - Administrator — TOTP0000AE42
  - roncraighead — TOTP0001265D

#### LibreNMS (Network Monitoring)

- **Web UI:** http://librenms.rpc-cyberflight.com (direct: http://10.0.8.121:8000)
- **Compose:** /opt/librenms/docker-compose.yml
- **Containers:**
  - `librenms-librenms-1` — librenms/librenms:latest (port 8000)
  - `librenms-dispatcher-1` — librenms/librenms:latest (sidecar dispatcher)
  - `librenms-db-1` — mariadb:10.5
  - `librenms-redis-1` — redis:7-alpine
- **Database:** MariaDB (librenms/librenms)
- **Timezone:** America/New_York
- **Volumes:** db (MariaDB data), librenms-data (app data)

#### Graylog (Log Management)

- **Web UI:** http://graylog.rpc-cyberflight.com (direct: http://10.0.8.121:7777)
- **Compose:** /opt/graylog/docker-compose.yml
- **Containers:**
  - `graylog-graylog-1` — graylog/graylog:5.2 (web UI on 7777->9000)
  - `graylog-mongodb-1` — mongo:6.0
  - `graylog-opensearch-1` — opensearchproject/opensearch:2.4.0
- **Inputs:**
  - Syslog UDP/TCP: port 1514
  - GELF UDP: port 12201
  - Beats: port 5044
- **OpenSearch:** single-node, 1 GB heap, security plugin disabled
- **Timezone:** America/New_York
- **Volumes:** mongo_data, os_data, graylog_data

#### MkDocs (Lab Documentation)

- **Web UI:** http://docs.rpc-cyberflight.com (direct: http://10.0.8.121:8080)
- **Compose:** /opt/mkdocs/docker-compose.yml
- **Container:** squidfunk/mkdocs-material:latest (port 8080→8000)
- **Docs source:** /opt/mkdocs/docs/
- **Theme:** Material (slate/dark)

#### Homarr (Dashboard)

- **Web UI:** http://dashboard.rpc-cyberflight.com (direct: http://10.0.8.121:7676)
- **Compose:** /opt/homarr/docker-compose.yml
- **Container:** ghcr.io/homarr-labs/homarr:latest (port 7676→7575)
- **Login:** admin / (see secrets vault)
- **Board:** "default" (public) — links to all services, Proxmox nodes, and VM consoles

#### Portainer (Container Management)

- **Web UI:** http://portainer.rpc-cyberflight.com (direct: https://10.0.8.121:9443)
- **Compose:** /opt/portainer/docker-compose.yml
- **Container:** portainer/portainer-ce:latest (port 9443)
- **Volume:** portainer_data (persistent data)

#### Gitea (Git Server)

- **Web UI:** http://git.rpc-cyberflight.com (direct: http://10.0.8.121:3000)
- **Compose:** /home/ron/gitea/docker-compose.yml
- **Container:** gitea/gitea:latest (ports 3000 HTTP, 2222 SSH)
- **Database:** SQLite3
- **ROOT_URL:** http://git.rpc-cyberflight.com/
- **Registration:** Disabled (admin creates accounts)
- **Admin:** ron / (see secrets vault)
- **Agent user:** agent (read-only API access for lab agents)
- **Repositories:**
  - `ron/labinfra` — Lab infrastructure documentation (mirrored from local)
- **DNS:** git.rpc-cyberflight.com → CNAME to cainfra01.rpc-cyberflight.com (CADC01 + AdGuardHome rewrite)
- **Network:** Connected to nginx-proxy_proxy Docker network for reverse proxy access

#### WordPress (CyberFlight Website — Production) — Google Cloud

- **Web UI:** https://cyberflight.rpc-cyberflight.com
- **Hosting:** Google Cloud Compute Engine (project: cyberflight-web)
- **VM:** cyberflight-wp (e2-small, Ubuntu 24.04, us-west1-b)
- **External IP:** 34.168.189.230
- **SSL:** Let's Encrypt via Certbot (auto-renews, expires 2026-06-14)
- **Compose:** /opt/wordpress/docker-compose.yml (on GCE VM)
- **Containers:**
  - `wordpress-wordpress-1` — wordpress:latest (port 127.0.0.1:8181→80, localhost-bound)
  - `wordpress-db-1` — mariadb:10.11
- **Reverse Proxy:** Nginx on GCE VM with SSL termination
- **Credentials:** .env file at /opt/wordpress/.env (0600 root:root), referenced via env_file in compose
- **Admin:** ron / (see secrets vault)
- **Theme:** Astra (dark custom CSS)
- **Site title:** Ron Craighead's CyberFlight
- **Tagline:** Cybersecurity | AI Infrastructure | Compliance
- **WP-CLI:** Installed in wordpress container (`wp --allow-root`)
- **Pages:** Home, About Ron (CISSP/AIGP), AI/CyberLab, Aviation, Blog, infrastructure sub-pages, project sub-pages
- **Nav menu:** Home | AI/CyberLab | Aviation | Blog | About Ron | LinkedIn
- **DNS:** cyberflight A → 34.168.189.230 (Google Domains + CADC01)
- **GitHub:** https://github.com/rpcraighead/cyberflight-website
- **Dev site:** http://10.0.8.121:8181 (cainfra01, /home/ron/wordpress/) — local dev/staging instance
- **WireGuard tunnel:** wg0 interface, tunnel IP 10.0.0.5/24, endpoint 108.247.32.130:51820 (home router)
  - AllowedIPs: 10.0.0.0/24, 10.0.8.0/24 (full lab access over tunnel)
  - PersistentKeepalive: 25s
  - Auto-starts on boot (systemd wg-quick@wg0)
- **Log forwarding:** rsyslog → Graylog at 10.0.8.121:1514 (syslog UDP over WireGuard tunnel)
  - System logs: all facilities/severities
  - Nginx access/error logs: via imfile module (tagged nginx-access, nginx-error)
  - Config: /etc/rsyslog.d/60-graylog.conf, /etc/rsyslog.d/61-nginx.conf
- **SNMP:** SNMPv3 (authPriv: SHA + AES), listening on 10.0.0.5:161 (WireGuard only)
  - User: librenms (same credentials as lab hosts)
  - Monitored by LibreNMS as device "cyberflight-wp (GCP)"
  - Disk, process (dockerd, nginx), and load monitoring enabled

#### N499CP Flight Planner — Google Cloud Run

- **Web UI:** https://flightplanner.rpc-cyberflight.com (also: https://flight-planner-383916130890.us-west1.run.app)
- **Hosting:** Google Cloud Run (project: cyberflight-web, region: us-west1)
- **Memory:** 512Mi, Timeout: 120s
- **Stack:** Python Flask, vanilla JS, Leaflet.js, SQLite
- **Features:** Route planning, VFR/IFR charts, terrain profile, airport diagrams, weather briefing, W&B, performance
- **DNS:** flightplanner CNAME → ghs.googlehosted.com (Google Domains + CADC01)
- **GitHub:** https://github.com/rpcraighead/flight-planner-n499cp-v2

### Pi5Desktop

- **IP:** 10.0.8.159 (DMZ) / 10.0.50.114 (LAN)
- **MAC:** xx:xx:xx:xx:xx:xx (DMZ) / xx:xx:xx:xx:xx:xx (LAN)
- **Role:** Raspberry Pi 5

### TL-SG1024DE

- **IP:** 10.0.8.128
- **MAC:** xx:xx:xx:xx:xx:xx
- **Role:** TP-Link managed switch

## OpenClaw (Ralph the Raccoon)

- **Host:** RonClaw (10.0.8.10), runs as user `openclaw`
- **Container:** Podman rootless (ghcr.io/openclaw/openclaw:latest)
- **Ports:** 18789 (gateway), 18790, 18791 (browser control)
- **Telegram Bot:** @RonBot247_bot
- **Model:** anthropic/claude-haiku-4-5-20251001 (Anthropic API)
- **Alternative models:** nvidia/moonshotai/kimi-k2.5 (NVIDIA NIM API), ollama/qwen3:8b-nothink (on BigBrain at 10.0.8.50)
- **Built-in skills:** gog (Google Workspace CLI — Gmail/Calendar read-only for rpcraighead@gmail.com)
- **Container env:** GOG_KEYRING_PASSWORD=(see secrets vault)
- **Note:** After container recreation, re-symlink gog: `ln -sf /home/node/.openclaw/bin/gog /home/node/.local/bin/gog`

### Custom Sysadmin Skills

Skills live at `/home/openclaw/.openclaw/custom-skills/` and must be **copied** (not symlinked) into `/app/skills/` inside the container. After any container restart, run:
```bash
podman exec openclaw /home/node/.openclaw/custom-skills/install-skills.sh
```

| Skill | Description |
|-------|-------------|
| proxmox | Proxmox VE cluster management via REST API (token: root@pam!ralph-agent) |
| lab-infra | SSH to hosts, DNS (AdGuardHome), Gitea API, LibreNMS/Graylog queries |
| containers | Docker on cainfra01, Podman on RonClaw, nginx reverse proxy management |

### Restart Procedure

**Always use the restart script** instead of `podman restart`:
```bash
sudo /home/openclaw/restart-ralph.sh
```
This script stops the container, waits 35s for any stale Telegram long-poll to expire, clears pending updates, starts the container, and reinstalls custom skills. Direct `podman restart` causes a Telegram 409 Conflict because the old getUpdates long-poll (30s timeout) is still active when the new instance starts polling.

## SNMP Monitoring

All devices are monitored via LibreNMS at http://10.0.8.121:8000.

### SNMPv3 Devices (authPriv: SHA + AES)

| Device | IP | User | Auth | Priv |
|--------|-----|------|------|------|
| pve1 | 10.0.8.101 | librenms | SHA | AES |
| pve2 | 10.0.8.123 | librenms | SHA | AES |
| bighost | 10.0.8.200 | librenms | SHA | AES |
| cainfra01 | 10.0.8.121 | librenms | SHA | AES |
| RonClaw | 10.0.8.10 | librenms | SHA | AES |
| bigbrain | 10.0.8.50 | librenms | SHA | AES |
| cyberflight-wp (GCP) | 10.0.0.5 | librenms | SHA | AES |

- **Auth password:** (see secrets vault)
- **Priv password:** (see secrets vault)
- **Extend scripts** (Proxmox hosts only): `/opt/snmp-scripts/` — cpu-temp, smart-status, lvm-usage

### SNMPv2c Devices (IP-restricted to 10.0.8.121)

| Device | IP | Community |
|--------|-----|-----------|
| CADC01 | 10.0.8.189 | (see secrets vault) |
| cadc02 | 10.0.8.132 | (see secrets vault) |
| GL-MT6000 | 10.0.8.1 | (see secrets vault) |

**Risk acceptance:** Windows Server 2019 and OpenWrt do not support SNMPv3 natively.
Net-SNMP Windows binaries are unavailable for recent versions.
Mitigations: 32-char random community string, queries accepted only from 10.0.8.121
(LibreNMS), on an isolated 10.0.8.0/24 DMZ network.

## Security Hardening

### Credential Management

- All plaintext credentials removed from LAB.md and docker-compose files (2026-03-16)
- Secrets referenced as `(see secrets vault)` — actual values stored in `.env` files on each host
- `.env` files permissions: `0600 root:root` (owner-read only)
- Docker Compose files use `env_file:` or `${VARIABLE}` references instead of inline passwords
- See [SECRETS_VAULT_README.md](SECRETS_VAULT_README.md) for secret locations and rotation schedule

### GCP VM Hardening (cyberflight-wp)

| Control | Configuration | Date |
|---------|--------------|------|
| **Firewall — RDP** | `default-allow-rdp` rule deleted (tcp:3389 was open to 0.0.0.0/0) | 2026-03-16 |
| **Firewall — SSH** | `default-allow-ssh` restricted to home IP (108.247.32.130/32) + GCP IAP (35.235.240.0/20) | 2026-03-16 |
| **Docker port binding** | WordPress port 8181 bound to `127.0.0.1` only (not 0.0.0.0) — prevents bypass of nginx/SSL | 2026-03-16 |
| **fail2ban** | 3 jails active: `sshd` (3 attempts, 7200s ban), `wordpress` (5 attempts, 3600s ban), `nginx-http-auth` (5 attempts, 3600s ban) | 2026-03-16 |
| **UFW** | Host firewall enabled — default deny incoming, allow 22/80/443 tcp only | 2026-03-16 |
| **SSL/TLS** | Let's Encrypt certificate with auto-renewal via Certbot; HTTP→HTTPS redirect enforced by nginx | 2026-03-16 |
| **Unattended upgrades** | Ubuntu automatic security patching enabled | default |

**Note:** If home IP changes (dynamic ISP), update the SSH firewall rule:
```bash
gcloud compute firewall-rules update default-allow-ssh \
  --project=cyberflight-web \
  --source-ranges="NEW_IP/32,35.235.240.0/20"
```
GCP IAP range (35.235.240.0/20) provides fallback SSH access via the GCP Console.

### Public Exposure Redaction

All publicly accessible content has been scrubbed of internal network details (2026-03-16):

| Control | Scope | Detail |
|---------|-------|--------|
| **WordPress IP redaction** | All 8 pages/posts containing private IPs | `192.168.x.y` addresses replaced with `192.168.x.x` (last two octets masked) |
| **draw.io diagram (public)** | `lab-network-public.drawio` | All IPs, ports, subnet ranges, MAC addresses, and device-specific hostnames removed |
| **WordPress diagram upload** | Network Architecture page (post ID 21) | Uses redacted PNG export; no internal IPs visible |
| **GitHub repos** | `labinfra` (private), `cyberflight-website` (public), `flight-planner-n499cp-v2` (public) | `labinfra` is private; public repos contain no internal IPs or credentials |
| **LAB.md credential scrub** | All credentials in LAB.md | Replaced with `(see secrets vault)` references |
| **Public DNS servers preserved** | 8.8.8.8, 9.9.9.9 | Well-known public IPs left unredacted on website |

**Files:**

- Internal (full detail): `lab-network.drawio` — private `labinfra` repo only
- Public (redacted): `lab-network-public.drawio` + PNG export on WordPress

### Remaining Risk Register

| # | Risk | Severity | Status |
|---|------|----------|--------|
| 1 | Root SSH as default access (cainfra01, Proxmox, router) | High | Open |
| 2 | Single SSH key (id_claude) across all hosts | High | Open |
| 3 | No TLS on internal services (PrivacyIDEA MFA, LDAP bind, nginx vhosts) | High | Open |
| 4 | OpenSearch security plugin disabled (Graylog) | High | Open |
| 5 | Flat DMZ — Kali on same subnet as domain controllers | Medium | Open |
| 6 | Windows Server 2019 Evaluation expiration | Medium | Open |
| 7 | WireGuard VPN has no MFA | Low | Open |
| 8 | No log forwarding from GCP VM to Graylog | Low | **Resolved** — rsyslog + WireGuard tunnel (2026-03-17) |
| 9 | Docker containers running as root (cainfra01) | Low | Open |
| 10 | SNMPv2c cleartext on Windows DCs and router | Medium | Accepted |

