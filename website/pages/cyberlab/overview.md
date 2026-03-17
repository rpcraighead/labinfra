# CyberLab Overview

## One Old PC + Claude Code = Enterprise Skills

You don't need a data center to learn enterprise IT. You need one computer, free software, and the willingness to break things.

My lab started with a single refurbished mini-PC with 16 GB of RAM. Today it's a 3-node Proxmox cluster running Active Directory, network monitoring, log management, multi-factor authentication, AI model inference, and more. Total hardware cost: under $1,500. Software cost: $0.

Every piece of this infrastructure was built with the help of Claude Code — an AI pair programmer that turns "I want to set up a domain controller" into a working Active Directory environment in an afternoon.

This section documents the entire lab: what it runs, how it's built, and how you can build your own.

---

## The Hardware

| Node | CPU | RAM | Disk | GPU | Cost (approx) |
|------|-----|-----|------|-----|----------------|
| pve1 | Intel i9-13900H | 64 GB | 93 GB | — | ~$600 (mini-PC) |
| pve2 | Intel i5-4590 | 16 GB | 36 GB | — | ~$100 (refurb desktop) |
| bighost | Intel i5-12600K | 64 GB | 93 GB | RTX 4070 | ~$800 (custom build) |

**You don't need all three.** Start with one. Pve2 — a 10-year-old i5 with 16 GB — runs a Windows Server VM that handles Active Directory, DNS, and DHCP for the entire lab. That's a $100 computer doing the job of a $5,000 server.

## What's Running

### Virtual Machines (6 total)

| VM | Purpose | Node | Key Skills |
|----|---------|------|------------|
| CADC01 | Primary Domain Controller — AD DS, DNS, DHCP | pve1 | Active Directory, DNS, DHCP, Group Policy |
| cadc02 | Secondary Domain Controller | pve2 | AD replication, redundancy |
| cainfra01 | Monitoring & Infrastructure | pve1 | Docker, nginx, reverse proxy, Linux admin |
| BigBrain | AI Inference Server | bighost | GPU passthrough, Ollama, LLM deployment |
| RonClaw | Telegram Bot Host | pve1 | Podman, API integration, bot development |
| Kali | Security Testing Lab | bighost | Penetration testing, security assessment |

### Services Stack (all on cainfra01, Docker)

| Service | Purpose | What You Learn |
|---------|---------|----------------|
| LibreNMS | Network monitoring | SNMP, device discovery, alerting |
| Graylog | Log management | Syslog, GELF, log analysis, OpenSearch |
| Nginx | Reverse proxy | Virtual hosts, proxy_pass, TLS termination |
| Homarr | Dashboard | Service organization, internal portals |
| MkDocs | Documentation | Technical writing, Material theme |
| PrivacyIDEA | Multi-factor auth | TOTP, LDAP integration, zero-cost MFA |

### Network

- **LAN** (10.0.50.0/24) — home network, GL-MT6000 router with OpenWrt + AdGuardHome
- **DMZ** (10.0.8.0/24) — lab network, AD-integrated DNS/DHCP
- WireGuard VPN for remote access

---

## The Philosophy

1. **Start small.** One computer, one hypervisor, one VM. You can run Proxmox on almost anything.
2. **Use real tools.** Don't simulate — actually deploy Active Directory, actually configure SNMP, actually write firewall rules.
3. **Break things.** That's what snapshots are for. The lab is your crash pad.
4. **Document everything.** If you can't explain it, you don't understand it.
5. **Let AI help.** Claude Code doesn't replace learning — it accelerates it. You still need to understand what's being built.

---

## Getting Started: Build Your Own

**Minimum hardware:**
- Any x86_64 computer with 8+ GB RAM
- USB drive for Proxmox installer
- Network cable

**Step 1:** Download Proxmox VE from proxmox.com and install it on bare metal.
**Step 2:** Create your first VM — start with a lightweight Linux (Debian or Rocky).
**Step 3:** Pick a project — monitoring, AD, Docker — and build it.
**Step 4:** Document what you did. Blog about it. Add it to your resume.

The detailed walkthroughs are in the Infrastructure section. Start with whichever interests you most.

[Network Architecture →]
[Proxmox Cluster →]
[Active Directory & DNS →]
[Monitoring Stack →]
