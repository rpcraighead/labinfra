# One Old PC: Installing Proxmox and Your First VM

**Date:** March 2026
**Project:** Lab Foundation
**Category:** Build Log
**Skills Demonstrated:** Hypervisor installation, VM creation, basic Linux administration

---

## The Problem

I wanted to learn enterprise IT infrastructure — Active Directory, network monitoring, log management, security testing. But enterprise hardware costs thousands of dollars and cloud labs charge by the hour.

The answer: virtualization. One physical computer running Proxmox can host a dozen virtual machines, each acting as its own server.

## What You Need

- Any x86_64 computer with 8+ GB of RAM (I started with a refurbished i5 desktop — $100)
- A USB drive (8 GB+) for the installer
- A network cable
- 30 minutes

## Step by Step

### 1. Download Proxmox VE

Go to proxmox.com/en/downloads and grab the latest ISO. Flash it to a USB drive using Rufus (Windows) or `dd` (Linux/Mac).

### 2. Install

Boot from the USB. The installer is straightforward:
- Accept the license
- Select the target disk (this will erase it)
- Set your country and timezone
- Choose a hostname (e.g., `pve1.local`) and a static IP on your network
- Set a root password

Installation takes about 5 minutes. Reboot, remove the USB.

### 3. Access the Web UI

Open a browser and go to `https://YOUR-IP:8006`. Log in as `root` with the password you set. You now have a hypervisor.

### 4. Upload an ISO

Go to your local storage → ISO Images → Upload. Grab a Debian or Rocky Linux ISO — these are free and lightweight.

### 5. Create Your First VM

Click "Create VM":
- **Name:** test-vm
- **ISO:** select the one you uploaded
- **Disk:** 20 GB is plenty to start
- **CPU:** 2 cores
- **RAM:** 2 GB
- **Network:** leave defaults (bridge mode)

Click "Finish" and start the VM. Open the console. You're installing Linux inside a virtual machine running on your old PC.

## What Went Wrong

On my first install, I chose a disk that still had an old Windows partition table. Proxmox installed fine but the LVM thin pool was tiny. Lesson: use a clean disk, or wipe the partition table first with `wipefs -a /dev/sdX` from a live USB.

## The Result

One $100 computer now runs as many servers as I need. My current cluster has three nodes and seven VMs — but it all started with one.

## What I Learned

- Proxmox is free and installs in minutes
- Virtualization makes hardware constraints almost irrelevant
- Snapshots mean you can experiment fearlessly — break it, roll back, try again
- The web UI is good enough for everything; CLI is there when you need it

## Try It Yourself

**Minimum:** Any PC with 8 GB RAM, USB drive, 30 minutes
**Recommended:** 16+ GB RAM for running multiple VMs comfortably
**Cost:** $0 (software) + whatever you spend on hardware

---

*Built with Claude Code. Lab documented at rpc-cyberflight.com.*
