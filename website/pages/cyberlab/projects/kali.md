# Project: Kali Security Lab

**Status:** In Progress (VM created, OS installing)
**Priority:** Medium
**Dependencies:** Lab Foundation (complete)
**Duration:** 2 weeks
**Cost:** $0

---

## Summary

Deploy a Kali Linux security testing environment within the Proxmox cluster to practice penetration testing, vulnerability assessment, and security auditing against the lab's own infrastructure.

## The Setup

| Setting | Value |
|---------|-------|
| VM ID | 107 |
| Host | bighost (10.0.8.200) |
| CPU | 4 vCPU |
| RAM | 4 GB |
| Disk | 60 GB (local-lvm) |
| Network | vmbr0 (DMZ — 10.0.8.0/24) |
| Boot | UEFI |
| OS | Kali Linux 2025.4 |

## Why a Security Lab?

Every infrastructure builder should also be an infrastructure breaker. Understanding attack techniques makes you better at defense. With the lab running real services (AD, DNS, DHCP, web servers, SSH), there are real attack surfaces to test:

- **Active Directory attacks** — Kerberoasting, AS-REP roasting, password spraying
- **Network reconnaissance** — Nmap scanning, service enumeration, SNMP walks
- **Web application testing** — proxy interception, injection testing
- **Credential testing** — password policy validation, brute force detection
- **Vulnerability scanning** — OpenVAS/Nessus against lab hosts

## Phases

1. ~~Create VM on bighost~~ (Done)
2. Install Kali from ISO (In Progress)
3. SSH key deployment and remote access
4. Network configuration (DHCP or static IP)
5. DNS record on CADC01
6. SNMP agent setup for LibreNMS monitoring
7. Tool configuration and customization

## The Learning Loop

```
Build infrastructure (CyberLab)
    → Attack it (Kali)
        → Fix what you find (hardening)
            → Document it (Blog)
                → Build more → repeat
```

This cycle — build, break, fix, document — is how real security skills are developed.

## Skills Demonstrated

Penetration testing, vulnerability assessment, network reconnaissance, Active Directory security, web application security, security hardening, incident response

---

*All testing is performed against owned infrastructure only. Authorized security testing in a controlled lab environment.*
