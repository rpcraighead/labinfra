# Active Directory & DNS

## Domain: rpc-cyberflight.com

A fully functional Active Directory environment providing centralized identity, DNS, and DHCP for the entire lab.

---

## Domain Configuration

| Setting | Value |
|---------|-------|
| Domain | rpc-cyberflight.com |
| NetBIOS | RPCCYBER |
| Forest Level | Windows 2016 |
| Primary DC | CADC01 (10.0.8.189) — Windows Server 2019 |
| Secondary DC | cadc02 (10.0.8.132) |

## CADC01 — Primary Domain Controller

Runs on pve1 as VM 105 (4 vCPU, 16 GB RAM, Windows Server 2019 Standard).

### Roles

- **AD DS** — Active Directory Domain Services (identity, authentication, Group Policy)
- **DNS Server** — authoritative for rpc-cyberflight.com zone
- **DHCP Server** — manages IP allocation for the entire DMZ

### DNS Zone: rpc-cyberflight.com

| Record | Type | Value | Purpose |
|--------|------|-------|---------|
| cainfra01 | A | 10.0.8.121 | Infrastructure server |
| dashboard | CNAME | cainfra01 | Homarr dashboard |
| librenms | CNAME | cainfra01 | Network monitoring |
| graylog | CNAME | cainfra01 | Log management |
| docs | CNAME | cainfra01 | MkDocs documentation |
| mfa | CNAME | cainfra01 | PrivacyIDEA MFA |

All services on cainfra01 get friendly DNS names via CNAME records. The nginx reverse proxy on cainfra01 routes requests to the correct Docker container based on the hostname.

### DHCP Scope: DMZ (10.0.8.0/24)

| Setting | Value |
|---------|-------|
| Range | 10.0.8.100 – 200 |
| Exclusion | 10.0.8.100 – 140 (reserved for static assignments) |
| Lease | 8 hours |
| Gateway | 10.0.8.1 |
| DNS | 10.0.8.189 (CADC01) |
| Domain suffix | rpc-cyberflight.com |

---

## How DNS Flows

Understanding DNS in this lab requires knowing there are two DNS paths:

### Path 1: DMZ Clients (lab devices)
```
Lab device → DHCP assigns DNS=10.0.8.189 → CADC01 resolves rpc-cyberflight.com
                                              → Forwards external queries upstream
```

### Path 2: LAN Clients (home devices)
```
Home device → DHCP assigns DNS=10.0.50.1 → AdGuardHome on router
  ├── rpc-cyberflight.com → conditional forward → CADC01 (10.0.8.189)
  └── everything else → 8.8.8.8 / 9.9.9.9
```

The conditional forward on the router is critical — without it, home devices can't resolve lab hostnames like `docs.rpc-cyberflight.com`.

---

## What You Learn Building This

- **Active Directory** — domain creation, organizational units, user/computer management
- **DNS** — zones, A/CNAME records, conditional forwarding, split-horizon DNS
- **DHCP** — scopes, exclusions, reservations, options (gateway, DNS, domain)
- **Group Policy** — centralized configuration management
- **Windows Server administration** — roles, features, PowerShell management
- **Multi-factor authentication** — PrivacyIDEA LDAP integration with AD
