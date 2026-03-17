# Monitoring Stack

## See Everything, Log Everything

Two core monitoring systems run on cainfra01 (Rocky Linux 10.1) as Docker containers:

- **LibreNMS** — network monitoring via SNMP (what's up, what's slow, what's broken)
- **Graylog** — centralized log management (what happened, when, and why)

Together they provide complete observability across the lab.

---

## LibreNMS — Network Monitoring

**URL:** http://librenms.rpc-cyberflight.com

### What It Monitors

Every device in the lab reports metrics via SNMP:

| Device | IP | SNMP Version | Metrics |
|--------|-----|-------------|---------|
| pve1 | 10.0.8.101 | v3 (SHA/AES) | CPU, RAM, disk, network, temperature |
| pve2 | 10.0.8.123 | v3 (SHA/AES) | CPU, RAM, disk, network, temperature |
| bighost | 10.0.8.200 | v3 (SHA/AES) | CPU, RAM, disk, network, temperature |
| cainfra01 | 10.0.8.121 | v3 (SHA/AES) | CPU, RAM, disk, network |
| RonClaw | 10.0.8.10 | v3 (SHA/AES) | CPU, RAM, disk, network |
| BigBrain | 10.0.8.50 | v3 (SHA/AES) | CPU, RAM, disk, network |
| CADC01 | 10.0.8.189 | v2c | CPU, RAM, disk, network |
| cadc02 | 10.0.8.132 | v2c | CPU, RAM, disk, network |
| GL-MT6000 | 10.0.8.1 | v2c | CPU, RAM, interfaces |

### SNMP v3 vs v2c

SNMPv3 uses authentication (SHA) and encryption (AES) — credentials are never sent in cleartext. All Linux and Proxmox hosts use v3.

Windows Server 2019 and OpenWrt don't support SNMPv3 natively, so those devices use SNMPv2c with a 32-character random community string, restricted to accept queries only from LibreNMS (10.0.8.121).

### Custom Extend Scripts

Proxmox hosts run custom SNMP extend scripts in `/opt/snmp-scripts/` for metrics that standard SNMP MIBs don't cover:

- **cpu-temp** — CPU temperature monitoring
- **smart-status** — disk health via S.M.A.R.T.
- **lvm-usage** — LVM thin pool utilization

### Architecture

```
LibreNMS (Docker)
├── librenms/librenms:latest — web UI + poller (:8000)
├── librenms/librenms:latest — dispatcher sidecar
├── mariadb:10.5 — database
└── redis:7-alpine — caching
```

---

## Graylog — Log Management

**URL:** http://graylog.rpc-cyberflight.com

### What It Collects

All devices send logs to Graylog for centralized analysis:

| Input | Port | Protocol | Sources |
|-------|------|----------|---------|
| Syslog | 1514 | UDP/TCP | Linux hosts, Proxmox, router |
| GELF | 12201 | UDP | Docker containers |
| Beats | 5044 | TCP | Winlogbeat (Windows event logs) |

### Architecture

```
Graylog (Docker)
├── graylog/graylog:5.2 — web UI + processing (:7777→9000)
├── mongo:6.0 — configuration database
└── opensearchproject/opensearch:2.4.0 — log storage + search
```

### Why Centralized Logging?

When something breaks at 2 AM, you don't want to SSH into six machines to read log files. Graylog collects everything in one searchable interface. You can:

- Search across all hosts simultaneously
- Set up alerts for specific patterns (failed logins, disk errors, service crashes)
- Correlate events across systems (DNS change → service outage)
- Retain logs for compliance and forensics

---

## What You Learn Building This

- **SNMP** — MIBs, OIDs, community strings, v2c vs v3, extend scripts
- **Network monitoring** — device discovery, alerting, dashboards, capacity planning
- **Log management** — syslog, GELF, Beats, log parsing, search queries
- **Docker Compose** — multi-container applications, volumes, networking
- **MariaDB / MongoDB / OpenSearch** — database administration fundamentals
- **Observability** — the difference between monitoring (is it up?) and observability (why is it slow?)
