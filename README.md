# CyberFlight Lab — AI Infrastructure Lab

**Author:** Ron Craighead, CISSP · AIGP · CompTIA SecurityX
**Domain:** rpc-cyberflight.com
**Site:** [cyberflight.rpc-cyberflight.com](https://cyberflight.rpc-cyberflight.com)

---

## What This Is

CyberFlight is a self-hosted AI infrastructure lab I designed and built from the ground up. The goal was simple: stop reading about AI infrastructure and start operating it.

The lab runs a production-architecture stack — local LLM inference with GPU passthrough, a multi-agent AI swarm with custom orchestration, a full observability pipeline, identity and MFA, centralized log management, and a hybrid cloud extension to GCP. Everything is documented, version-controlled, and maintained against a formal risk register.

This isn't a tutorial setup. It's the kind of environment I'd build professionally — with security controls, observability, and operational discipline baked in from the start.

---

## Why I Built It

I've spent 20+ years designing and securing enterprise infrastructure. As AI moved from a research topic to an infrastructure problem, I wanted hands-on depth in the systems layer: how do you deploy and serve LLMs at scale? How do you build reliable agent workflows? How do you monitor and audit an AI system the same way you'd monitor a production network?

The CyberFlight lab is the answer to those questions — built, broken, and rebuilt until it worked properly.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    CYBERFLIGHT LAB (DMZ)                    │
│                     192.168.x.x/24                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Proxmox VE Cluster (3 nodes)               │   │
│  │  pve1: i9-13900H / 62GB   pve2: i5-4590 / 15GB       │   │
│  │  bighost: i5-12600K / 62GB + NVIDIA RTX 4070         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│   bigbrain (VM)          cainfra02 (VM)    cainfra01 (VM)   │
│   LLM Inference          AI Agent Swarm    Services Host    │
│   Ollama + RTX 4070      14 containers     Docker stack     │
│   Qwen3 8b/14b/32b       RabbitMQ/Redis    Monitoring/Logs  │
│                          PostgreSQL        MFA / Gitea      │
│                                                             │
│   cadc01 / cadc02 (VMs)      RonClaw (VM)                   │
│   Active Directory           OpenClaw AI Assistant          │
│   DNS / DHCP / MFA (LDAP)    Claude Haiku + custom skills   │
└─────────────────────────────────────────────────────────────┘
          │ WireGuard VPN (site-to-site)
          ▼
┌─────────────────────────┐
│   Google Cloud Platform │
│   WordPress (GCE)       │
│   Flight Planner (Run)  │
│   Log forwarding via VPN│
└─────────────────────────┘
```

---

## Key Components

### LLM Inference (bigbrain)
- **NVIDIA RTX 4070** passed through via PCIe to a dedicated Rocky Linux VM
- **Ollama** serving Qwen3 8b, 14b, and 32b models — model selection tuned per-agent for latency vs. quality
- Bound on all interfaces; consumed by the agent swarm and OpenClaw assistant

### AI Agent Swarm (cainfra02)
A 14-service containerized agent system deployed via layered Docker Compose:

| Agent | Role |
|---|---|
| **conductor** | LLM orchestrator + web UI |
| **superintendent** | Proxmox VM lifecycle management |
| **mercury** | Docker container management |
| **davinci** | Infrastructure-as-code generation |
| **sapper** | OpenWrt firewall and network management |
| **monitor** | Independent safety observer |
| **scribe** | Audit documentation logger |
| **judge** | Arbitration and rollback authority |

Supporting infrastructure: RabbitMQ (AMQP message broker), Redis (distributed cache), PostgreSQL (audit log database), N8N (non-AI workflow automation and access gating), Prometheus + Grafana (metrics and dashboards).

### AI Assistant (OpenClaw / RonClaw VM)
- Claude Haiku (Anthropic API) running in a rootless Podman container
- Custom infrastructure skills: Proxmox REST API, Docker/Podman management, AdGuardHome DNS, Gitea API, LibreNMS/Graylog queries
- Accessible via Telegram bot for mobile infrastructure management

### Observability & Monitoring
- **Prometheus + Grafana** — metrics collection and dashboards
- **LibreNMS** — SNMPv3 (SHA/AES) network monitoring across all lab hosts, including GCP VM over WireGuard tunnel
- **Graylog** — centralized log management (OpenSearch + MongoDB); syslog, GELF, and Beats inputs; rsyslog forwarding from GCP over the site-to-site tunnel

### Identity & Network
- **Active Directory** domain (rpc-cyberflight.com) on Windows Server 2019 with DNS and DHCP
- **PrivacyIDEA** MFA (TOTP) integrated via LDAP against AD
- **GL-MT6000 OpenWrt** router with segmented LAN / DMZ / WireGuard zones
- **WireGuard VPN** — remote client access and site-to-site tunnel to GCP
- **AdGuardHome** DNS with upstream filtering and conditional forward to AD DNS

### Security Posture
- Formal risk register (10 items, severity-rated, tracked to resolution)
- Credentials vault — all plaintext credentials removed from documentation and compose files; secrets stored in `.env` files with `0600` permissions
- GCP hardening: RDP disabled, SSH IP-restricted + GCP IAP, fail2ban (3 jails), UFW, Let's Encrypt TLS
- Public documentation scrubbed of internal IPs, ports, and credentials
- Internal (full detail) and public (redacted) versions of network diagrams maintained separately

---

## Technology Stack

**Virtualization:** Proxmox VE 9.1, KVM/QEMU, PCIe passthrough
**AI/LLM:** Ollama, Qwen3.5 (9b), Anthropic Claude API, OpenClaw
**Containers:** Docker, Podman (rootless), Docker Compose (layered)
**Messaging:** RabbitMQ 3.12, Redis 7, PostgreSQL 15
**Observability:** Prometheus, Grafana, LibreNMS, Graylog 5.2, OpenSearch
**Identity:** Active Directory (Windows Server 2019), PrivacyIDEA, LDAP
**Network:** OpenWrt, WireGuard, Nginx reverse proxy, AdGuardHome
**Cloud:** Google Cloud Compute Engine, Google Cloud Run, WireGuard site-to-site
**OS:** Rocky Linux 10, Ubuntu 24.04, Kali Linux, Windows Server 2019, Debian 13
**Languages/Tools:** Python, Flask, Bash, N8N, MkDocs, Gitea

---

## What This Demonstrates

- **AI infrastructure deployment** — end-to-end LLM serving with GPU compute, model management, and agent integration
- **Multi-agent system design** — orchestration patterns, safety controls (monitor/judge), message queuing, and audit logging
- **Security-first thinking** — a risk register, credential management, network segmentation, and hardening aren't afterthoughts here; they're built in
- **Operational discipline** — SNMPv3 monitoring, centralized logging, MFA, and version-controlled documentation on a home lab is the same discipline that matters in production
- **Hybrid cloud integration** — site-to-site VPN, log forwarding, and application deployment across on-prem and GCP

---

## Professional Background

I'm a 20-year infrastructure and security professional (CISSP, AIGP) currently targeting AI Infrastructure Engineer roles. This lab is the hands-on complement to that experience.

Full resume and background at [cyberflight.rpc-cyberflight.com](https://cyberflight.rpc-cyberflight.com) · [LinkedIn](https://www.linkedin.com/in/ron-craighead-cissp-aigp)
