# Project: Smart Home Infrastructure

**Status:** Not Started
**Priority:** Medium
**Dependencies:** Lab Foundation (complete), Local AI/GPU (complete)
**Duration:** 6 weeks
**Cost:** ~$60–100 per camera node (Raspberry Pi + camera module)

---

## Summary

Build a privacy-first smart home platform using Home Assistant, Frigate NVR with GPU-accelerated AI object detection on the RTX 4070, and Alexa voice integration — all running on existing lab infrastructure.

## The Problem

Commercial smart home systems (Ring, Nest, etc.) send video and data to the cloud. We want:
- Local processing — video never leaves the house
- AI-powered detection — person, vehicle, animal classification in real-time
- Integration with existing lab infrastructure
- Zero monthly fees

## The Solution

### Core Platforms
- **Home Assistant** — central automation hub
- **Frigate NVR** — network video recorder with real-time AI object detection
- **Mosquitto MQTT** — message broker for device communication
- **RTX 4070** — GPU-accelerated inference via TensorRT (supports 10–20+ cameras)

### Camera Network
- **Raspberry Pi cameras** — Pi Camera Module v2/v3 with hardware ISP via CSI
- **Ring cameras** — integrated via Home Assistant (cloud-dependent, no Frigate support)
- **USB cameras** — fallback option with ffmpeg

### AI Detection
Frigate uses the RTX 4070 with TensorRT backend for real-time object detection:
- Person, car, bicycle, motorcycle, bus, truck
- Bird, cat, dog, horse, bear
- Custom models possible

### Voice Control
- Alexa Smart Home Skill for voice control of Home Assistant devices
- Echo devices for TTS announcements ("Person detected at front door")

## Phases

1. Core platform deployment (Home Assistant, MQTT, Nginx, TLS)
2. Frigate + GPU integration
3. Pi camera rollout
4. Alexa integration + automations
5. Hardening and optimization
6. Facial recognition (optional — Double-Take + CompreFace)

## Skills Demonstrated

Home Assistant, MQTT protocol, NVR systems, AI/ML inference, GPU computing, Raspberry Pi, RTSP streaming, Docker Compose, TLS certificates, voice assistant integration

---

*[Full proposal available as PDF →]*
