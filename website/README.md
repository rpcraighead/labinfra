# CyberFlight Website — Content & Assets

Content files for rpc-cyberflight.com (Google Sites).

## How to use

Each file in `pages/` is ready to copy-paste into a Google Sites page.
Assets in `assets/` should be uploaded to Google Sites or embedded.

## Structure

```
pages/
├── home.md                          → Home page
├── about.md                         → About / Bio / Contact
├── aviation/
│   ├── discovery.md                 → Principles of Flight
│   ├── simulation.md                → Flight Simulation Program
│   ├── training.md                  → Flight Training Resources
│   └── videos.md                    → Video Library
├── cyberlab/
│   ├── overview.md                  → Lab Overview & Philosophy
│   ├── infrastructure/
│   │   ├── network.md               → Network Architecture
│   │   ├── proxmox.md               → Proxmox Cluster
│   │   ├── active-directory.md      → AD & DNS
│   │   └── monitoring.md            → LibreNMS & Graylog
│   └── projects/
│       ├── pki.md                   → PKI Certificate Services
│       ├── intune.md                → Windows Endpoint Management
│       ├── smarthome.md             → Smart Home Infrastructure
│       ├── agast.md                 → Digital Twin Flight Sim
│       └── kali.md                  → Kali Security Lab
└── blog/
    ├── build-log/
    │   ├── 01-one-old-pc.md         → First blog post
    │   ├── 02-active-directory.md
    │   └── 03-monitoring-stack.md
    └── flight-stories/
        └── first-business-trip.md

assets/
├── diagrams/                        → Exported draw.io PNGs/SVGs
└── images/                          → Photos, screenshots
```
