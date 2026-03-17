# Proxmox Cluster

## Cluster: rpc-cyber-dc-01

A 3-node Proxmox VE cluster providing high-availability virtualization for all lab workloads.

### Cluster Diagram

*[Insert proxmox-cluster.drawio diagram here]*

---

## Nodes

| Node | IP | CPU | Cores/Threads | RAM | Disk | GPU | VMs |
|------|-----|-----|---------------|-----|------|-----|-----|
| pve1 | 10.0.8.101 | i9-13900H | 14/20 | 64 GB | 93 GB | — | 100, 101, 103, 105 |
| pve2 | 10.0.8.123 | i5-4590 | 4/4 | 16 GB | 36 GB | — | 104 |
| bighost | 10.0.8.200 | i5-12600K | 10/16 | 64 GB | 93 GB | RTX 4070 | 102, 107 |

### Why These Machines?

- **pve1** — A mini-PC with a laptop-class i9. Small, quiet, power-efficient, but packs 14 cores. Runs most of the lab.
- **pve2** — A 10-year-old desktop. Proves you don't need modern hardware. Runs a single Windows Server VM just fine on 4 cores and 16 GB.
- **bighost** — The muscle. A desktop-class i5-12600K with an RTX 4070 for GPU-accelerated AI workloads. Runs the Ollama inference server and Kali security lab.

---

## Storage

| Name | Type | Capacity | Content | Notes |
|------|------|----------|---------|-------|
| local | Directory | 93 GB | ISOs, backups, templates | Per-node local storage |
| local-lvm | LVM-thin | 337 GB | VM disks | Thin-provisioned, per-node |
| usbdisk | NFS | 916 GB | ISOs, VM disks, backups | Shared NFS export from pve1 via USB disk |

The NFS share (`usbdisk`) is key — it provides shared storage across all nodes without expensive SAN hardware. It's literally a USB hard drive plugged into pve1 and exported via NFS.

---

## VM Inventory

| VMID | Name | Node | vCPU | RAM | Disk | OS | IP | Status |
|------|------|------|------|-----|------|----|----|--------|
| 100 | RonClaw | pve1 | 2 | 8 GB | 32 GB | Linux | 10.0.8.10 | Running |
| 101 | BethClaw | pve1 | 2 | 8 GB | 32 GB | Linux | — | Stopped |
| 102 | BigBrain | bighost | 12 | 40 GB | 256 GB | Linux | 10.0.8.50 | Running |
| 103 | cainfra01 | pve1 | 2 | 8 GB | 128 GB | Rocky Linux 10.1 | 10.0.8.121 | Running |
| 104 | cadc02 | pve2 | 4 | 12 GB | 256 GB | Windows | 10.0.8.132 | Running |
| 105 | CADC01 | pve1 | 4 | 16 GB | — | Win Server 2019 | 10.0.8.189 | Running |
| 107 | Kali | bighost | 4 | 4 GB | 60 GB | Kali Linux | TBD | Installing |

---

## GPU Passthrough — BigBrain

The RTX 4070 on bighost is passed directly to VM 102 (BigBrain) for GPU-accelerated AI inference:

- **GPU:** NVIDIA GeForce RTX 4070 (AD104)
- **PCI address:** 0000:01:00.0
- **CPU mode:** host (full passthrough for best performance)
- **Purpose:** Ollama LLM server running Qwen3 models (8B, 14B, 32B parameter)
- **Autostart:** Yes — BigBrain comes up automatically on node boot

### What is GPU Passthrough?

Proxmox can pass a physical GPU directly to a VM, giving it bare-metal GPU performance. This lets you run AI inference, video transcoding, or any GPU workload inside a VM as if the GPU were physically installed in that machine.

---

## Cluster Features in Use

| Feature | How We Use It |
|---------|---------------|
| Corosync quorum | 3-node cluster ensures quorum even if one node goes down |
| Shared storage (NFS) | ISOs and backups accessible from any node |
| Live migration | Move VMs between nodes without downtime (for non-GPU VMs) |
| Autostart | Critical VMs (BigBrain, cainfra01, CADC01) start automatically |
| UEFI boot | Modern secure boot for newer VMs |

---

## What You Learn Building This

- **Hypervisor installation** — bare-metal Proxmox deployment
- **Cluster configuration** — Corosync, quorum, node management
- **VM creation** — resource allocation, disk provisioning, network bridging
- **Storage architecture** — local vs shared, LVM-thin, NFS exports
- **GPU passthrough** — IOMMU, PCI device assignment, driver isolation
- **Capacity planning** — balancing workloads across heterogeneous hardware
