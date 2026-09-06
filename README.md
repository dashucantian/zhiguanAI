# ZhiguanAI - EEG Biofeedback Training System

An open-source brain-computer interface (BCI) system for meditation and mindfulness training through real-time EEG biofeedback.

## Overview

ZhiguanAI combines EEG brainwave monitoring with adaptive audio and visual feedback to help practitioners develop deeper states of relaxation and focus. The system implements a closed-loop biofeedback paradigm where:

- **Baseline Phase**: Collects 2 minutes of personal EEG data to establish individual Alpha wave baseline
- **Closed-Loop Phase**: Real-time brainwave analysis drives adaptive audio (beat frequency + volume) and visual feedback (VR scene parameters)
- **Reward Mechanism**: When Alpha power exceeds baseline threshold, audio volume increases as positive reinforcement

## Core Features

### 1. Real-Time EEG Processing
- 4-channel EEG data acquisition via Muse headband (Bluetooth)
- Real-time band power calculation (Delta, Theta, Alpha, Beta, Gamma)
- Adaptive state detection (relaxed, drowsy, tense)

### 2. Adaptive Audio Engine
- Isochronic tone synthesis with phase-continuous frequency switching
- Beat frequency adapts to Theta/Beta ratio (drowsiness/tension detection)
- Smooth volume transitions with rate-limiting to avoid audio artifacts

### 3. VR Visual Feedback
- WebXR-based immersive VR scene (Three.js)
- Real-time visual parameter mapping from EEG band power:
  - Alpha → fog density, water surface ripples
  - Theta → particle system density
  - Attention → "Heart Pearl" brightness
  - Meditation → ripple expansion speed
- HTTPS with self-signed certificates for WebXR secure context

### 4. Web Console
- FastAPI-based backend with WebSocket real-time streaming
- Browser-based monitoring interface
- Experiment configuration management
- Data export and reporting

## Architecture

```
Muse Headband (BLE) → Python Backend → WebSocket → VR Browser
                          ↓
                    FastAPI Console (HTTP/HTTPS)
                          ↓
                    Web Monitoring UI
```

### Key Components

| File | Role |
|------|------|
| `console_server.py` | Main backend server (FastAPI + WebSocket) |
| `closedloop_experiment.py` | Closed-loop experiment orchestrator |
| `closedloop_controller.py` | Decision layer (threshold-based reward logic) |
| `closedloop_engine.py` | Real-time isochronic tone synthesis engine |
| `experiment_config_loader.py` | Configuration management with validation |
| `local_tls.py` | Self-signed certificate generation for HTTPS |
| `vr_feedback.html` | WebXR VR scene (Three.js) |
| `vr_assets/` | Localized Three.js engine (offline-capable) |

## Requirements

### Hardware
- **EEG Headband**: Muse 2 or Muse S (3rd generation)
- **VR Headset**: Pico 4 Ultra or any WebXR-compatible device
- **Computer**: Windows 10/11 with Bluetooth support

### Software
- Python 3.12
- Dependencies:
  ```bash
  pip install fastapi uvicorn numpy sounddevice websockets cryptography
  ```
- Additional: `muse2-repo/` (Muse SDK integration, not included in this repo)

## Quick Start

### 1. Start the Console Server

```bash
python console_server.py --port 8777
```

The server will start on `http://127.0.0.1:8777` (local) and `http://0.0.0.0:8777` (LAN).

### 2. Access the Web Console

Open your browser:
- **Local**: http://127.0.0.1:8777
- **LAN**: http://YOUR_IP:8777

### 3. Run a Closed-Loop Experiment

#### Simulation Mode (no headband required)
```bash
python closedloop_experiment.py --simulate --baseline 60 --duration 300
```

#### Real Device Mode
```bash
python closedloop_experiment.py --address 00:55:DA:XX:XX:XX --baseline 120 --duration 600
```

Replace `00:55:DA:XX:XX:XX` with your Muse headband's Bluetooth MAC address.

### 4. VR Visual Feedback

#### Generate HTTPS Certificates
```bash
python local_tls.py
```

This creates `vr_assets/tls/cert.pem` and `key.pem` (self-signed, valid 825 days).

#### Start HTTPS Server
The console server automatically starts HTTPS on port 8778 when certificates are present.

#### Access VR Scene
On your VR headset browser:
```
https://YOUR_IP:8778/vr
```

**Note**: First visit will show a certificate warning. Click "Advanced" → "Proceed" to trust the self-signed certificate.

## Configuration

Edit `experiment_config.json` to customize:

```json
{
  "experiment": {
    "baseline_seconds": 120,
    "duration_seconds": 600,
    "tag": "closedloop"
  },
  "controller": {
    "target_band": "alpha",
    "reward_threshold_db": 1.0,
    "vol_max": 0.35,
    "beat_default": 10.0,
    "beat_drowsy": 12.0,
    "beat_tense": 8.0
  },
  "audio": {
    "carrier_hz": 220.0
  }
}
```

### Key Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `baseline_seconds` | Baseline collection duration | 120s |
| `duration_seconds` | Total experiment duration | 600s |
| `reward_threshold_db` | Alpha power above baseline to trigger reward | 1.0 dB |
| `beat_default` | Default beat frequency (Alpha guidance) | 10.0 Hz |
| `beat_drowsy` | Beat frequency when drowsy (Theta/Beta high) | 12.0 Hz |
| `beat_tense` | Beat frequency when tense (Theta/Beta low) | 8.0 Hz |

## Project Structure

```
zhiguanAI/
├── console_server.py              # Main FastAPI server
├── closedloop_experiment.py       # Experiment orchestrator
├── closedloop_controller.py       # Decision layer
├── closedloop_engine.py           # Audio synthesis engine
├── experiment_config_loader.py    # Configuration management
├── local_tls.py                   # Certificate generation
├── vr_feedback.html               # WebXR VR scene
├── vr_assets/                     # Three.js engine (localized)
│   ├── three.module.js
│   └── jsm/
├── 01_项目管理/案例库/             # Case library (Chinese)
│   ├── 00_案例库说明.md
│   ├── 决策判语/                  # Architecture decisions
│   ├── 踩坑档案/                  # Troubleshooting guides
│   └── 复现路径/                  # Reproduction guides
└── README.md                      # This file
```

## Case Library

The `案例库/` directory contains detailed documentation (in Chinese) covering:

- **Architecture Decisions**: Rationale for technology choices (WebXR vs Unity, MoE vs Dense models, etc.)
- **Troubleshooting Guides**: Common issues and solutions (WebXR secure context, Bluetooth stability, PowerShell quirks, etc.)
- **Reproduction Guides**: Step-by-step instructions for setting up the complete system

## Security Notes

- **Private Keys**: `vr_assets/tls/key.pem` is excluded from this repository via `.gitignore`. Generate your own certificates using `local_tls.py`.
- **Network**: The server binds to `0.0.0.0` by default for LAN access. For internet exposure, use a reverse proxy with proper TLS termination.
- **EEG Data**: Raw EEG data (`.npz` files) is excluded from this repository. Handle participant data according to your local privacy regulations.

## Limitations

- **Hardware Dependency**: Requires Muse 2/S headband (Bluetooth protocol not documented in this repo)
- **Platform**: Tested on Windows 10/11 only. Linux/macOS support may require adjustments.
- **VR Browser**: WebXR support varies across VR browsers. Tested on Pico Browser.

## License

This project is open source. See individual file headers for specific licensing.

## Acknowledgments

- **Muse SDK**: Interaxon Inc. for Muse headband hardware and SDK
- **Three.js**: mrdoob and contributors for the 3D engine
- **FastAPI**: Sebastián Ramírez for the web framework

## Contact

For questions or contributions, please open an issue on GitHub.

---

**Note**: This is a research/educational project. The system is not a medical device and should not be used for diagnostic or therapeutic purposes without proper clinical validation.
