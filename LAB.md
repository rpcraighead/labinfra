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
| cyberflight | A | 34.182.15.235 (Google Cloud) |
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
- **Compose locations:** /opt/librenms/, /opt/graylog/, /opt/homarr/, /opt/mkdocs/, /opt/nginx-proxy/, /opt/privacyidea/, /opt/portainer/, /home/ron/wordpress/

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

#### WordPress (CyberFlight Website) — MIGRATED TO GOOGLE CLOUD

- **Web UI:** https://cyberflight.rpc-cyberflight.com
- **Hosting:** Google Cloud Compute Engine (project: cyberflight-web)
- **VM:** cyberflight-wp (e2-small, Ubuntu 24.04, us-west1-b)
- **External IP:** 34.182.15.235
- **SSL:** Let's Encrypt via Certbot (auto-renews, expires 2026-06-14)
- **Compose:** /opt/wordpress/docker-compose.yml (on GCE VM)
- **Containers:**
  - `wordpress-wordpress-1` — wordpress:latest (port 8181→80)
  - `wordpress-db-1` — mariadb:10.11
- **Reverse Proxy:** Nginx on GCE VM with SSL termination
- **Admin:** admin / (see secrets vault)
- **Theme:** Astra (dark custom CSS)
- **Site title:** Ron Craighead's CyberFlight
- **Tagline:** Cybersecurity | AI Infrastructure | Compliance
- **WP-CLI:** Installed in wordpress container (`wp --allow-root`)
- **Pages:** Home, About Ron (CISSP/AIGP), AI/CyberLab, Aviation, Blog, infrastructure sub-pages, project sub-pages
- **Nav menu:** Home | AI/CyberLab | Aviation | Blog | About Ron | LinkedIn
- **DNS:** cyberflight A → 34.182.15.235 (Google Domains + CADC01)
- **GitHub:** https://github.com/rpcraighead/cyberflight-website
- **Note:** Original WordPress on cainfra01 (/home/ron/wordpress/) is still running but no longer in use

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

## OpenClaw (ClawBot)

- **Host:** 10.0.8.10 (runs as user `openclaw`)
- **Container:** Podman rootless (ghcr.io/openclaw/openclaw:latest)
- **Ports:** 18789, 18790
- **Telegram Bot:** @RonBot247_bot
- **Model:** nvidia/moonshotai/kimi-k2.5 (via NVIDIA NIM API, openai-completions)
- **Fallback models:** ollama/qwen3:8b-nothink (on BigBrain at 10.0.8.50)
- **Skills:** gog (Google Workspace CLI — Gmail/Calendar read-only for rpcraighead@gmail.com)
- **Container env:** GOG_KEYRING_PASSWORD=openclaw
- **Note:** After container recreation, re-symlink gog: `ln -sf /home/node/.openclaw/bin/gog /home/node/.local/bin/gog`

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

