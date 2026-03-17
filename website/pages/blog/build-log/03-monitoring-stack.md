# See Everything: Deploying LibreNMS and Graylog with Docker

**Date:** March 2026
**Project:** Monitoring Stack
**Category:** Build Log
**Skills Demonstrated:** Docker Compose, SNMP, syslog, network monitoring, log management, MariaDB, MongoDB, OpenSearch

---

## The Problem

With multiple servers running, you need answers to two questions:
1. **Is everything healthy?** (monitoring)
2. **What just happened?** (logging)

Without centralized monitoring, you're blind. Without centralized logging, you're guessing.

## The Approach

Deploy two industry-standard tools on a single Rocky Linux VM using Docker Compose:
- **LibreNMS** for SNMP-based network monitoring
- **Graylog** for centralized log collection and search

Both are open-source and free.

## Step by Step

### 1. Set Up the Infrastructure VM

Create a Rocky Linux 10 VM on Proxmox (cainfra01):
- 2 vCPU, 8 GB RAM, 128 GB disk
- Install Docker and Docker Compose

### 2. Deploy LibreNMS

LibreNMS needs four containers: the app, a dispatcher, MariaDB, and Redis.

Create `/opt/librenms/docker-compose.yml` and `docker compose up -d`. The web UI appears on port 8000.

### 3. Configure SNMP on All Devices

For Linux and Proxmox hosts, install `snmpd` and configure SNMPv3:
- Create a user (`librenms`) with SHA authentication and AES encryption
- Restrict access to the monitoring server's IP

For Windows (which doesn't support SNMPv3), use SNMPv2c with a long random community string, restricted to accept queries only from the monitoring server.

### 4. Add Devices to LibreNMS

In the web UI: Devices → Add Device. Enter the IP, SNMP version, and credentials. LibreNMS auto-discovers services, ports, and metrics.

### 5. Deploy Graylog

Graylog needs three containers: the app, MongoDB, and OpenSearch.

Create `/opt/graylog/docker-compose.yml` and `docker compose up -d`. Web UI on port 7777.

### 6. Configure Log Inputs

In Graylog, create inputs:
- **Syslog UDP** on port 1514 — for Linux hosts and network devices
- **GELF UDP** on port 12201 — for Docker containers
- **Beats** on port 5044 — for Windows Event Logs via Winlogbeat

Point your devices' syslog to `10.0.8.121:1514`.

### 7. Set Up Nginx Reverse Proxy

Rather than remembering port numbers, set up nginx to route by hostname:
- `librenms.rpc-cyberflight.com` → port 8000
- `graylog.rpc-cyberflight.com` → port 7777

Add CNAME records in AD DNS pointing to the infrastructure server.

## What Went Wrong

OpenSearch is memory-hungry. With the default JVM heap size, it kept crashing on an 8 GB VM. Fix: set `OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g` in the compose file. 1 GB heap is enough for a lab.

Also: Docker containers on separate compose stacks can't see each other by container name. The nginx reverse proxy needs to be on every stack's network, or use the host IP directly.

## The Result

From a single dashboard, I can see CPU, RAM, disk, network, and temperature for every device. From Graylog, I can search every log message across every system. When something breaks, I know about it immediately — and I can see exactly what happened.

## What I Learned

- Docker Compose makes deploying complex stacks trivial
- SNMP is old but incredibly effective for infrastructure monitoring
- Centralized logging is a superpower for troubleshooting
- Memory management matters — containers need resource limits
- Reverse proxies turn port numbers into readable URLs

## Try It Yourself

**Minimum:** Linux VM with 4 GB RAM, Docker installed
**Recommended:** 8 GB RAM for both LibreNMS and Graylog
**Software:** All free and open-source
**Time:** 2–3 hours for basic setup, plus time to add devices

---

*Built with Claude Code. Lab documented at rpc-cyberflight.com.*
