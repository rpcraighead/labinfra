# Secrets Vault

All credentials have been removed from LAB.md and docker-compose files.

## Where secrets are stored

Secrets are stored in `.env` files on each host, with permissions restricted to root (0600).

| Host | Path | Contains |
|------|------|----------|
| cainfra01 | /opt/wordpress/.env | WordPress DB passwords |
| cainfra01 | /opt/librenms/.env | LibreNMS DB passwords |
| cainfra01 | /opt/graylog/.env | Graylog/OpenSearch passwords |
| cainfra01 | /opt/privacyidea/.env | PrivacyIDEA admin password |
| cainfra01 | /opt/homarr/.env | Homarr admin password |
| GCP VM | /opt/wordpress/.env | WordPress DB passwords |

## SNMP credentials

Stored in `/etc/snmp/snmpd.conf` on each Linux host (root-readable only).
SNMPv2c community strings are in SNMP service configs on Windows DCs and router.

## Accessing secrets

```bash
# On cainfra01 or GCP VM:
sudo cat /opt/wordpress/.env
```

## Rotation schedule

- Rotate all passwords quarterly
- Rotate SSH keys annually
- Rotate SNMP credentials after any staff change
