# CyberFlight Website Proposal
## rpc-cyberflight.com — Google Sites

**Prepared by:** Ron Craighead
**Date:** March 2026
**Version:** 1.0 — DRAFT
**Platform:** Google Sites (existing domain on Google)

---

## 1. Executive Summary

Build a unified personal brand website at **rpc-cyberflight.com** on Google Sites that showcases Ron Craighead's dual expertise: **certified flight instructor** and **cybersecurity infrastructure professional**. The site replaces cfiron.com as the primary web presence and serves as both a professional portfolio and an educational resource demonstrating that anyone can build enterprise-grade IT infrastructure with modest hardware and AI-assisted tooling (Claude Code).

The site targets three audiences:
1. **Prospective flight students** — discovery, simulation curriculum, training resources
2. **IT/cybersecurity professionals and learners** — lab walkthroughs, project proposals, architecture documentation
3. **Employers and collaborators** — professional portfolio demonstrating hands-on infrastructure skills

---

## 2. Site Architecture

### Navigation Structure

```
Home
├── About
│   ├── Bio & Credentials
│   ├── Resume / CV
│   └── Contact
├── Aviation
│   ├── Discovery & Principles of Flight
│   ├── Flight Simulation Program
│   │   └── Digital Twin Flight Sim (AGAST)
│   ├── Flight Training Resources
│   └── Video Library
├── CyberLab
│   ├── Lab Overview & Philosophy
│   ├── Infrastructure
│   │   ├── Network Architecture
│   │   ├── Proxmox Cluster
│   │   ├── Active Directory & DNS
│   │   └── Monitoring Stack (LibreNMS, Graylog)
│   ├── Projects
│   │   ├── PKI Certificate Services
│   │   ├── Windows Endpoint Management (Intune)
│   │   ├── Smart Home Infrastructure
│   │   ├── Digital Twin Flight Simulator
│   │   └── Kali Linux Security Lab
│   └── Getting Started Guide
│       └── "Build Your Own Lab" tutorial series
├── Blog
│   ├── Build Log (chronological project documentation)
│   ├── Flight Stories
│   └── Lessons Learned
└── Projects Dashboard
    └── Status tracker (embedded Google Sheet or page)
```

### Page Descriptions

#### Home
Hero section with tagline: *"Where Aviation Meets Cybersecurity"*
Split visual — one side aviation imagery, one side server/terminal imagery. Brief intro, featured blog post, and calls to action for both tracks.

#### About
Professional bio combining aviation and IT credentials. Embry-Riddle degree, Navy/Army service, CAP volunteer work, CFI certifications, IT certifications and experience. Contact form. Downloadable resume.

#### Aviation Section
Migrated and enhanced content from cfiron.com:
- **Discovery & Principles of Flight** — educational articles ("learn in 20 minutes or less")
- **Flight Simulation Program** — the 53+ hour simulation curriculum, AGAST system details, hardware specs, training phases
- **Flight Training Resources** — San Diego area info packets, "become a student" pathway
- **Video Library** — curated CFI video collections organized by topic

#### CyberLab Section
The core differentiator — a documented, living homelab:
- **Lab Overview** — philosophy ("one old PC + Claude Code = enterprise skills"), hardware inventory, cost breakdown showing this is achievable on a budget
- **Infrastructure** — detailed walkthroughs of each component with architecture diagrams (from draw.io files), configuration explanations, and decision rationale
- **Projects** — web versions of each proposal document, presented as professional project plans with status indicators
- **Getting Started Guide** — step-by-step tutorial for readers who want to build their own lab, starting with a single Proxmox node

#### Blog
Chronological documentation of each build step. Every lab change, project milestone, and lesson learned gets a blog entry. Categories:
- **Build Log** — technical walkthroughs (e.g., "Setting up AdGuardHome conditional DNS forwarding")
- **Flight Stories** — aviation experiences (migrated from cfiron.com)
- **Lessons Learned** — retrospectives on what worked and what didn't

#### Projects Dashboard
Visual status tracker for all active projects. Could be an embedded Google Sheet with:
- Project name, phase, status, dependencies, completion percentage
- Links to the full proposal page
- Timeline/Gantt view

---

## 3. Content Migration from cfiron.com

| cfiron.com Section | CyberFlight Destination | Action |
|---|---|---|
| Home / Hero | Home | Rewrite with dual-brand messaging |
| Principles of Flight | Aviation > Discovery | Migrate content |
| Flight Simulation | Aviation > Simulation + CyberLab > Projects > AGAST | Migrate + expand with lab integration |
| Flight Training Resources | Aviation > Training | Migrate content |
| Video Links | Aviation > Video Library | Migrate and reorganize |
| Contact | About > Contact | Migrate form |
| Blog posts (e.g., "First Business Trip") | Blog > Flight Stories | Migrate posts |

---

## 4. Design Guidelines

### Branding
- **Name:** CyberFlight / rpc-cyberflight.com
- **Tagline:** "Where Aviation Meets Cybersecurity"
- **Color Palette:**
  - Primary: Deep navy blue (#1a237e) — authority, aviation, tech
  - Secondary: Amber/gold (#ff8f00) — warmth, aviation instruments
  - Accent: Cyan (#00bcd4) — tech, terminal, cyber
  - Background: Dark slate (#1e1e2e) for tech sections, white for aviation
- **Typography:** Clean sans-serif (Roboto or similar, available in Google Sites)
- **Imagery:** Mix of aviation photography and terminal/infrastructure screenshots. Diagrams from draw.io files exported as images.

### Google Sites Considerations
- Use section layouts and collapsible text for dense technical content
- Embed Google Sheets for project tracker
- Embed Google Docs for proposals (or convert to native pages)
- Use Google Forms for contact
- Image carousels for lab hardware and flight sim setup photos
- Embed draw.io diagrams as exported PNGs/SVGs

---

## 5. Google Sites Limitations & Workarounds

| Limitation | Workaround |
|---|---|
| No native blog engine | Use a dedicated "Blog" page with subpages per post, reverse-chronological linking on main blog page |
| No dynamic content | Embed Google Sheets for live project status |
| Limited custom code | Use embed blocks for any interactive elements |
| No custom CSS/JS | Work within Google Sites themes; use section backgrounds and layouts for visual variety |
| No database/backend | All content is static pages; use Google Forms for input |
| No comments | Link to a Google Form or embed Disqus via iframe if needed |

---

## 6. Implementation Phases

### Phase 1: Foundation (Week 1)
- Create Google Sites project at rpc-cyberflight.com
- Set up navigation structure
- Design home page with dual-brand hero
- Create About page with bio, credentials, contact form
- Set up Blog section structure

### Phase 2: Aviation Content (Week 2)
- Migrate Principles of Flight content from cfiron.com
- Migrate Flight Simulation curriculum
- Migrate Flight Training Resources
- Migrate Video Library
- Migrate existing blog posts

### Phase 3: CyberLab Core (Week 3)
- Create Lab Overview page with philosophy and hardware inventory
- Export and embed network and cluster diagrams
- Write Infrastructure walkthrough pages (Network, Proxmox, AD, Monitoring)
- Create "Getting Started" guide outline

### Phase 4: Projects (Week 4)
- Convert all four proposals to web pages:
  - PKI Certificate Services
  - Windows Endpoint Management
  - Smart Home Infrastructure
  - Digital Twin Flight Simulator
- Add Kali Security Lab project page
- Create Projects Dashboard with embedded Google Sheet

### Phase 5: Blog & Polish (Week 5)
- Write initial build log entries documenting lab setup to date
- Write "How I Built This with Claude Code" introductory post
- Cross-link all sections
- SEO basics (page titles, descriptions)
- Test all navigation paths
- Publish and redirect cfiron.com

### Phase 6: Ongoing
- Blog entries for each project milestone
- Update project dashboard as work progresses
- Add new projects as they're conceived
- Update infrastructure pages as lab evolves

---

## 7. Success Criteria

- [ ] All cfiron.com content migrated or superseded
- [ ] All four project proposals available as web pages
- [ ] Lab infrastructure documented with diagrams
- [ ] Blog section with at least 5 initial posts
- [ ] Projects dashboard showing all active work
- [ ] Contact form functional
- [ ] Site accessible at rpc-cyberflight.com
- [ ] Mobile-responsive (built into Google Sites)
- [ ] cfiron.com visitors directed to new site

---

## 8. Cost

| Item | Cost |
|---|---|
| Google Sites | $0 (included with Google Workspace / free tier) |
| Domain (rpc-cyberflight.com) | Already owned |
| Content creation | Time investment only |
| **Total** | **$0** |
