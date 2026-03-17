# CyberFlight Program Management
## Master Project Tracker — rpc-cyberflight.com

**Program Owner:** Ron Craighead
**Last Updated:** 2026-03-16

---

## Program Overview

All projects under the CyberFlight umbrella, with dependencies and status tracking.

### Project Registry

| ID | Project | Status | Priority | Dependencies | Est. Duration |
|----|---------|--------|----------|--------------|---------------|
| P-01 | Lab Foundation (Proxmox + AD + Networking) | COMPLETE | Critical | None | — |
| P-02 | Monitoring Stack (LibreNMS + Graylog) | COMPLETE | High | P-01 | — |
| P-03 | Infrastructure Services (Nginx, Homarr, MkDocs, PrivacyIDEA) | COMPLETE | High | P-01, P-02 | — |
| P-04 | Local AI / Ollama (BigBrain GPU) | COMPLETE | Medium | P-01 | — |
| P-05 | OpenClaw Telegram Bot | COMPLETE | Medium | P-04 | — |
| P-06 | CyberFlight Website (Google Sites) | NOT STARTED | High | P-01 through P-05 (content) | 5 weeks |
| P-07 | PKI Certificate Services | NOT STARTED | High | P-01 | 4 weeks |
| P-08 | Windows Endpoint Management (Intune) | NOT STARTED | Medium | P-01, P-07 | 4 weeks |
| P-09 | Smart Home Infrastructure | NOT STARTED | Medium | P-01, P-04 | 6 weeks |
| P-10 | Digital Twin Flight Simulator | IN PROGRESS | Medium | None (standalone hardware) | Ongoing |
| P-11 | Kali Security Lab | IN PROGRESS | Medium | P-01 | 2 weeks |
| P-12 | SNMP Monitoring Expansion | COMPLETE | Low | P-02 | — |

---

## Dependency Map

```
P-01 Lab Foundation (COMPLETE)
 ├── P-02 Monitoring Stack (COMPLETE)
 │    └── P-03 Infrastructure Services (COMPLETE)
 │         └── P-06 Website ← also needs P-04, P-05 content
 │    └── P-12 SNMP Expansion (COMPLETE)
 ├── P-04 Local AI / Ollama (COMPLETE)
 │    ├── P-05 OpenClaw Bot (COMPLETE)
 │    └── P-09 Smart Home (needs GPU for Frigate AI)
 ├── P-07 PKI Certificate Services
 │    └── P-08 Windows Endpoint Management (needs certs for LDAPS, etc.)
 └── P-11 Kali Security Lab (IN PROGRESS)

P-10 Digital Twin Flight Sim (standalone, IN PROGRESS)
```

---

## Recommended Execution Order

Based on dependencies and value:

### Wave 1 — Active Now
1. **P-11 Kali Security Lab** — VM created, install in progress
2. **P-06 CyberFlight Website** — can start Phase 1-2 immediately (foundation + aviation content)

### Wave 2 — Next Up
3. **P-07 PKI Certificate Services** — unlocks P-08, improves security posture for all services
4. **P-06 Website Phase 3-4** — document lab and projects as they complete

### Wave 3 — After PKI
5. **P-08 Windows Endpoint Management** — depends on PKI for LDAPS/cert enrollment
6. **P-09 Smart Home** — independent but benefits from mature infrastructure

### Continuous
7. **P-06 Website Phase 5-6** — ongoing blog posts and project updates
8. **P-10 Digital Twin** — ongoing CAP program development

---

## Detailed Project Status

### P-11: Kali Security Lab

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| 1 | Create VM on bighost | DONE | VM 107, 4 vCPU, 4GB RAM, 60GB disk |
| 2 | Install Kali from ISO | IN PROGRESS | Booting from kali-linux-2025.4-installer-amd64.iso |
| 3 | SSH key deployment | PENDING | Copy id_claude key after install |
| 4 | Network configuration | PENDING | DHCP or static on 10.0.8.0/24 |
| 5 | SNMP agent setup | PENDING | Add to LibreNMS monitoring |
| 6 | DNS record | PENDING | Add A record on CADC01 |
| 7 | Tool configuration | PENDING | Security testing toolkit setup |

### P-06: CyberFlight Website

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| 1 | Site foundation & navigation | NOT STARTED | Google Sites setup |
| 2 | Aviation content migration | NOT STARTED | From cfiron.com |
| 3 | CyberLab documentation | NOT STARTED | From LAB.md + draw.io |
| 4 | Project pages | NOT STARTED | Convert proposals to web pages |
| 5 | Blog & polish | NOT STARTED | Initial build log entries |
| 6 | Ongoing content | NOT STARTED | Blog as we build |

### P-07: PKI Certificate Services

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| 1 | Offline Root CA | NOT STARTED | Standalone Windows VM |
| 2 | Enterprise Issuing CA | NOT STARTED | On CADC01 or dedicated VM |
| 3 | Certificate templates | NOT STARTED | Web server, RDP, LDAPS |
| 4 | GPO auto-enrollment | NOT STARTED | Domain-joined machines |
| 5 | Let's Encrypt (public) | NOT STARTED | certbot + Cloudflare DNS-01 |
| 6 | Linux integration | NOT STARTED | certbot on Rocky Linux |
| 7 | Optional step-ca | NOT STARTED | Internal ACME server |
| 8-10 | Testing & documentation | NOT STARTED | Validation and runbook |

### P-08: Windows Endpoint Management

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| 1 | Entra ID Connect | NOT STARTED | AD → Entra sync |
| 2 | Hybrid Entra Join | NOT STARTED | SCP + GPO |
| 3 | Intune enrollment | NOT STARTED | Auto-MDM enrollment |
| 4 | OpenIntuneBaseline | NOT STARTED | Security baseline import |
| 5 | Windows Update for Business | NOT STARTED | Pilot + production rings |
| 6 | BitLocker | NOT STARTED | TPM 2.0 required |
| 7 | LAPS | NOT STARTED | Local admin password rotation |
| 8 | App deployment | NOT STARTED | Win32 + Store apps |
| 9 | Compliance policies | NOT STARTED | Reporting |

### P-09: Smart Home Infrastructure

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| 1 | Core platforms (HA, MQTT, Nginx) | NOT STARTED | Deploy on ronclaw |
| 2 | Frigate + GPU | NOT STARTED | BigBrain RTX 4070 |
| 3 | Pi camera rollout | NOT STARTED | Hardware purchase needed |
| 4 | Alexa + automations | NOT STARTED | Voice control integration |
| 5 | Hardening | NOT STARTED | TLS, access control |
| 6 | Facial recognition (optional) | NOT STARTED | Double-Take + CompreFace |

---

## Risk Register (Program-Level)

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| GPU contention (Ollama vs Frigate vs AI workloads) | High | Medium | Schedule workloads; Ollama can yield GPU when Frigate needs it |
| Resource exhaustion on Proxmox cluster | High | Low | Monitor via LibreNMS; bighost has headroom |
| Intune licensing cost ($8/user/month) | Medium | Certain | Budget; start with 1-2 seats for lab |
| PKI misconfiguration locks out services | High | Medium | Test in lab first; maintain break-glass access |
| Google Sites limitations for blog | Medium | Certain | Structured subpages; may migrate blog to Ghost/Hugo later |
| Scope creep across projects | Medium | High | Stick to proposal scopes; new ideas become new projects |

---

## Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-15 | AdGuardHome conditional DNS forward for rpc-cyberflight.com | Router iptables redirects DNS to AdGuardHome, not dnsmasq |
| 2026-03-16 | Kali VM on bighost (VM 107) | Bighost has available resources; security lab benefits from same network |
| 2026-03-16 | Google Sites for website | Already on Google platform; $0 cost; sufficient for portfolio/blog |
