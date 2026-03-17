# Active Directory in Your Living Room

**Date:** March 2026
**Project:** Lab Foundation
**Category:** Build Log
**Skills Demonstrated:** Windows Server, Active Directory Domain Services, DNS, DHCP, Group Policy

---

## The Problem

Active Directory is the backbone of almost every enterprise network. If you want to work in IT, you need to understand it. But AD requires Windows Server, which seems expensive and complicated.

Spoiler: it's neither. Windows Server 2019 Evaluation is free for 180 days (and can be extended). Setting up a basic domain takes about an hour.

## The Approach

Create a Windows Server 2019 VM on Proxmox, promote it to a domain controller, and configure DNS and DHCP. This single VM becomes the identity and network foundation for the entire lab.

## Step by Step

### 1. Create the VM

In Proxmox:
- **CPU:** 4 cores
- **RAM:** 16 GB (you can get away with 8 GB, but 16 is comfortable)
- **Disk:** 60 GB
- **Network:** bridged to your lab network

Install Windows Server 2019 Standard (Desktop Experience) from the evaluation ISO.

### 2. Promote to Domain Controller

Open Server Manager → Add Roles and Features:
- Check **Active Directory Domain Services**
- After installation, click the notification flag → "Promote this server to a domain controller"
- Choose "Add a new forest"
- Root domain name: `rpc-cyberflight.com` (use your own domain)
- Set the DSRM password (store it securely — this is your break-glass recovery password)

The server reboots. You now have a domain.

### 3. Configure DNS

AD automatically creates a DNS zone for your domain. Add records for your other servers:

```
cainfra01    A      10.0.8.121
dashboard    CNAME  cainfra01.rpc-cyberflight.com
librenms     CNAME  cainfra01.rpc-cyberflight.com
graylog      CNAME  cainfra01.rpc-cyberflight.com
docs         CNAME  cainfra01.rpc-cyberflight.com
```

Now `librenms.rpc-cyberflight.com` resolves to your monitoring server. Professional.

### 4. Configure DHCP

Add the DHCP Server role. Create a scope for your lab subnet:
- **Range:** 10.0.8.100 – 200
- **Exclusions:** 100 – 140 (for static servers)
- **Gateway:** 10.0.8.1
- **DNS:** point at this server (10.0.8.189)
- **Domain:** rpc-cyberflight.com

Authorize the DHCP server in AD. Lab devices now get IP addresses and DNS automatically.

## What Went Wrong

DNS is always what goes wrong. My home network used a different DNS server (the router), so my laptop couldn't resolve lab hostnames. The fix: conditional DNS forwarding on the router so `rpc-cyberflight.com` queries go to the domain controller while everything else goes to public DNS.

## The Result

One VM provides centralized identity (AD), name resolution (DNS), and IP management (DHCP) for the entire lab. Every device that joins the domain gets Group Policy, authentication, and DNS — just like a real enterprise.

## What I Learned

- Active Directory is not as scary as it looks
- DNS is always the problem (and the solution)
- DHCP reservations prevent IP chaos
- Group Policy is incredibly powerful (and we've barely scratched the surface)

## Try It Yourself

**Minimum:** Proxmox VM with 4 vCPU, 8 GB RAM, 40 GB disk
**Software:** Windows Server 2019 Evaluation (free, 180-day trial)
**Time:** 1–2 hours for basic setup

---

*Built with Claude Code. Lab documented at rpc-cyberflight.com.*
