# Secrets Directory

This directory holds SSH keys and credentials used by the agent swarm.
It is excluded from git via `.gitignore`.

## Required Files

| File | Used By | Purpose |
|------|---------|---------|
| `sapper_ssh_key` | Sapper | SSH private key for OpenWrt firewall (GL-MT6000) and Linux hosts |

## Setup

```bash
# Generate a dedicated SSH key for Sapper
ssh-keygen -t ed25519 -f secrets/sapper_ssh_key -N "" -C "sapper-agent"

# Copy public key to the OpenWrt router
ssh-copy-id -i secrets/sapper_ssh_key.pub root@10.0.8.1

# Copy to any Linux hosts Sapper needs to manage
ssh-copy-id -i secrets/sapper_ssh_key.pub root@10.0.8.189
```

## Permissions

Ensure the private key has restricted permissions (the Docker container runs as UID 1000):

```bash
chmod 600 secrets/sapper_ssh_key
```
