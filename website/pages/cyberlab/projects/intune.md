# Project: Windows Endpoint Management

**Status:** Not Started
**Priority:** Medium
**Dependencies:** Lab Foundation (complete), PKI Certificate Services (recommended)
**Duration:** 4 weeks
**Cost:** $8/user/month (Intune Plan 1)

---

## Summary

Implement unified Windows endpoint management using Microsoft Intune and Entra ID hybrid join. Centralize software deployment, patch management, security baselines, and compliance reporting while preserving the on-premises Active Directory environment.

## The Problem

- No centralized software deployment mechanism
- Windows Update is unmanaged — inconsistent patch levels across devices
- No device compliance visibility
- Security hardening is incomplete and inconsistent
- No cloud identity integration

## The Solution

### Hybrid Identity
- **Entra ID Connect** syncs on-premises AD to Entra ID (Azure AD)
- **Hybrid Entra Join** — devices are both domain-joined and Entra-registered
- **Auto-enrollment** — devices automatically enroll in Intune via MDM

### Security Baseline
- **OpenIntuneBaseline (OIB)** — community-maintained security baseline synthesizing NCSC, CIS, ACSC, and Microsoft guidance
- Covers OS hardening, Defender AV, Edge browser, BitLocker, LAPS, and ASR rules

### Patch Management
- **Windows Update for Business** with two deployment rings:
  - Pilot ring (immediate) for testing
  - Production ring (7-day deferral) for safety

### Endpoint Security
- **BitLocker** — full disk encryption with Entra-escrowed recovery keys
- **LAPS** — automated local administrator password rotation
- **ASR rules** — Attack Surface Reduction (audit mode first, then enforce)

## Phases

1. Entra ID Connect setup
2. Hybrid Entra Join + MDM enrollment GPO
3. Intune enrollment validation
4. OpenIntuneBaseline import and pilot
5. Windows Update for Business rings
6. BitLocker enforcement
7. LAPS configuration
8. Win32 app deployment
9. Compliance policies and reporting

## Skills Demonstrated

Microsoft Intune, Entra ID (Azure AD), hybrid identity, Group Policy, endpoint security, patch management, BitLocker, LAPS, compliance reporting

---

*[Full proposal available as PDF →]*
