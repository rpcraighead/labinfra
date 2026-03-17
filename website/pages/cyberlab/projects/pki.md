# Project: PKI Certificate Services

**Status:** Not Started
**Priority:** High
**Dependencies:** Lab Foundation (complete)
**Duration:** 4 weeks
**Cost:** $0

---

## Summary

Deploy a zero-cost Public Key Infrastructure using a two-tier Certificate Authority design: an offline Root CA for maximum security and an online Enterprise Issuing CA integrated with Active Directory. Public-facing certificates via Let's Encrypt with automated renewal.

## The Problem

- No internal Certificate Authority — services use self-signed certs that generate browser warnings
- No automated certificate lifecycle management
- RDP, WinRM, and LDAPS connections are unencrypted or use untrusted certificates
- Public HTTPS requires manual certificate management

## The Solution

### Two-Tier Private PKI
- **Offline Root CA** — issues only the Issuing CA certificate, then powers off. Maximum security.
- **Online Enterprise CA** — integrated with AD, auto-enrolls certificates to domain-joined machines via Group Policy

### Public Certificates
- **Let's Encrypt** via certbot with Cloudflare DNS-01 challenge for `rpc-cyberflight.com`
- Automated 60-day renewal

### Optional: Smallstep step-ca
- Internal ACME server for unified certificate workflow across Windows and Linux

## Certificate Map

| Service | Certificate Source | Renewal |
|---------|-------------------|---------|
| rpc-cyberflight.com HTTPS | Let's Encrypt | Auto (60 days) |
| RDP connections | Private ADCS (auto-enroll) | Auto (1 year) |
| WinRM over HTTPS | Private ADCS (auto-enroll) | Auto (1 year) |
| LDAPS | Private ADCS (auto-enroll) | Auto (1 year) |
| Internal web services | ADCS or step-ca | Auto |

## Phases

1. Deploy offline Root CA
2. Deploy Enterprise Issuing CA
3. Create certificate templates
4. Configure GPO auto-enrollment
5. Set up Let's Encrypt + certbot
6. Linux integration (Rocky Linux)
7. Optional step-ca deployment
8. Testing and validation
9. Documentation and runbook

## Skills Demonstrated

PKI architecture, Certificate Authority management, Group Policy, certbot, ACME protocol, TLS/SSL, LDAPS, Windows Server Certificate Services

---

*[Full proposal available as PDF →]*
