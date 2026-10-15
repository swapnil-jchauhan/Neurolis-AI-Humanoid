<div align="center">

# Project Neurolis

### *An interactive, 4-foot AI humanoid robot with expressive 60 FPS OLED face, conversational voice, vision gesture control, and 4WD teleoperated mobility.*

[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205%20|%20Linux%20|%20Windows%20PC-0078D4?style=for-the-badge&logo=raspberrypi&logoColor=white)](https://raspberrypi.com)
[![Groq AI](https://img.shields.io/badge/AI%20Engine-Groq%20Whisper%20&%20Qwen%2027B-F55036?style=for-the-badge&logo=fastapi&logoColor=white)](https://groq.com)
[![Vision](https://img.shields.io/badge/Vision%20Sentry-MediaPipe%20Gestures-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://developers.google.com/mediapipe)
[![Chassis](https://img.shields.io/badge/Chassis-4WD%20Teleoperated-00ff88?style=for-the-badge)](https://github.com)
[![Status](https://img.shields.io/badge/Status-Stable%20High%20School%20Build-00f0ff?style=for-the-badge)](https://github.com)

<br/>

> [!IMPORTANT]
> **Under continuous development, though slowed down. New and improved systems and features will be worked on in the future, this project is still very alive.**

</div>

---

## Current Build Status: Stable Exhibition Architecture

For our high school science exhibition at Auckland House School for Boys, we made the deliberate engineering decision to fall back to a **much safer, rock-solid, and dependable build**. 

The autonomous movement pipeline was overly complex, fragile, and prone to breaking in dynamic, crowded hall environments. At the same time, an accidental hardware incident cracked our capacitive touch digitizer, making touchscreen buttons unusable.

Rather than running unreliable autonomous code or risking collisions, we simplified the system to ensure 100% stability:
1. **Mobility**: Completely removed all autonomous roaming, approach, and person-following algorithms. The 4WD chassis is now operated via **Full Manual Remote Control (Teleoperation)**, keeping movement 100% safe and human-guided.
2. **Hands-Free Control**: Replaced broken touchscreen buttons with a continuous **MediaPipe Vision Hand Gesture Sentry**:
   * ✋ **Open Palm held for 3 seconds** &rarr; Wakes Neurolis up into active conversation (`LISTENING...`).
   * ✊ **Closed Fist held for 3 seconds** &rarr; Forces Neurolis into `STANDBY` mode.
   * Features a live visual progress fill gauge on screen above the subtitle card.
3. **Conversational Talkbot**: Fully focused on natural dialogue, expressive facial emotion, real-time auditory endpointer filtering, and on-demand camera visual inspection.

---

## System Architecture

```
                       ┌──────────────────────────────────────────────┐
                       │        Raspberry Pi 5 (or PC Simulation)     │
                       │──────────────────────────────────────────────│
                       │  • MediaPipe Tasks Vision Gesture Sentry     │
                       │    (✋ Open Palm Wake / ✊ Closed Fist Standby)│
                       │  • Endpointer v2 + WebRTC VAD Noise Gate     │
                       │  • Groq Whisper Speech-to-Text (STT)         │
                       │  • Groq Qwen 27B Fast LLM Intelligence      │
                       │  • 14-Key Fleet Auto-Rotation Engine         │
                       │  • Edge-TTS 7.3.1 + Piper Offline Voice      │
                       │  • 60 FPS Animated OLED Face UI (7" Screen)  │
                       │  • On-Demand Groq Vision Camera Inspection   │
                       └──────────────────────────────────────────────┘

                                      [PHYSICALLY ISOLATED]

                       ┌──────────────────────────────────────────────┐
                       │           4WD Teleoperated Chassis           │
                       │──────────────────────────────────────────────│
                       │  • Arduino Mega / Dedicated Controller       │
                       │  • 4x BTS7960 43A High-Power Motor Drivers   │
                       │  • 4x 12V Johnson Non-Encoder DC Motors      │
                       │  • Wireless Remote Control Receiver (RF/RC)  │
                       │  • Full Manual Driver Control (Zero Hazard)  │
                       └──────────────────────────────────────────────┘
```

---

## Core Capabilities & Features

### 1. Hands-Free Vision Gesture Sentry (MediaPipe Tasks)
* Operates continuously in the background using the USB camera on `/dev/video0`.
* Downscaled 320x240 RGB frames processed at ~15 FPS with minimal CPU overhead.
* **3-Second Hold Validation**:
  * In **Standby**: An open palm held continuously for 3.0 seconds wakes the robot. Closed fists are ignored.
  * In **Active**: A closed fist held continuously for 3.0 seconds forces the robot into standby. Open palms are ignored.
* **Live On-Screen HUD**: Animated progress bar visually fills above the subtitles as the gesture is held, providing immediate feedback.

### 2. Auditorium-Tuned Acoustic Endpointer (Endpointer v2)
* Built specifically for high-noise venues like school auditoriums, science halls, and busy cafeterias (65–75 dBA).
* **Rolling Ambient Noise Floor Tracking**: Computes median ambient room energy over a 66-frame (~2.0s) window to dynamically set speech onset threshold at $+6\text{ dB}$ SNR ($\text{floor} \times 2.0$).
* **Dynamic Speaker Hangover**: While the visitor speaks, the continuation threshold rises dynamically to $32\%$ of the speaker's median volume, preventing background crowd chatter from keeping the recording open.
* **Zero Shouting Required**: Normal conversational speech ($450\text{--}800\text{ RMS}$) is accepted cleanly, while distant chatter ($120\text{--}220\text{ RMS}$) is rejected.
* **Sub-Utterance Vocal Tunnel Filter**: Performs FFT bandpass ($85\text{Hz}\text{--}5500\text{Hz}$) with a $+2.6\text{ dB}$ consonant presence shelf ($2.0\text{kHz}\text{--}4.0\text{kHz}$) across the entire audio array before passing to Whisper.

### 3. High-Speed Conversational Intelligence (Groq Qwen 27B)
* Sub-second conversational responses powered by Groq LPUs.
* **Dynamic 14-Key Auto-Rotation**: Automatically balances and rotates across up to 14 Groq API keys (`GROQ_API_KEY_1` to `GROQ_API_KEY_14`). When a key encounters a rate limit (HTTP 429), it instantly fails over to the next standby key without crashing.
* **Zero-Token Fast-Paths**: Standalone greetings ("Hello", "Hi"), uncertainty queries, and key status inquiries ("Which key is active?") execute locally with 0ms latency and 0 API tokens.
* **Safe, Polite Student Tone**: Natural, articulate personality representing Auckland House School for Boys. Knows its creators (Swapnil Jai Chauhan & Shivam Verma) and explains its prototype systems only when asked or praised.

### 4. Dual-Engine Speech Synthesis (Online + Local Offline)
* **Primary (Edge-TTS 7.3.1)**: Crystal-clear neural voice (`en-US-ChristopherNeural`) synthesized in memory with parallel sentence pipelining for sub-1.5s speech playback.
* **Instant Offline Contingency (Piper Neural TTS)**: If internet drops or DNS fails, synthesizes speech locally via Piper (`en_US-lessac-low.onnx`) directly through `sounddevice` with zero timeouts.

### 5. 60 FPS Animated OLED Face Engine (`screen.py`)
* Minimalist emissive cyber face on pure space black (`#040711`).
* **7 Expressive Emotional States**:
  * `IDLE`: Calm cyan glowing eyes with natural breathing cadence.
  * `HAPPY`: Cheerful emerald smiling crescents ($\cap \;\; \cap$) with smooth bounce.
  * `SAD`: Sapphire downcast eyes with an animated falling digital teardrop.
  * `CONFUSED`: Spinning cyber vortex spirals with orbital stars.
  * `THINKING`: Analytical squint with rotating quantum data rings.
  * `SPEAKING`: Voice-reactive eye squash/stretch synced with audio playback.
  * `WATCHING`: Optical viewfinder reticle brackets with scanning laser sweep.
* Real-time dual-color subtitles: `[YOU]` in mint green, `[NEUROLIS]` in cyan.

### 6. On-Demand Visual Inspection (Groq Vision)
* Ask *"What am I holding?"*, *"Look at this"*, or *"What is in my hand?"*.
* Neurolis switches to its `WATCHING` expression, captures a single snapshot from the camera, and provides a quick, concise answer using Groq Vision.

---

## Hardware Specification

| Category | Component | Role & Notes |
| :--- | :--- | :--- |
| **Compute Brain** | **Raspberry Pi 5 (4GB or 8GB)** | Runs Python 3.13, MediaPipe gesture sentry, audio endpointer, AI brain, and face UI. |
| **Camera** | **USB HD Webcam (720p / 1080p)** | Stationed on `/dev/video0`. Runs background MediaPipe gesture detection and on-demand AI vision. |
| **Audio In** | **USB Microphone / Phone Mic over ADB** | High-fidelity 16kHz mono audio input connected to PipeWire / ALSA. |
| **Audio Out** | **Powered Speaker (USB or Bluetooth)** | Audio playback for Edge-TTS and Piper speech synthesis. |
| **Face Display** | **7-inch Display (1024x600)** | Dedicated to 60 FPS animated Face UI and gesture progress HUD. |
| **Chassis** | **4WD Skid-Steer Aluminum Base** | 4x 12V Johnson DC motors and 4x BTS7960 high-power drivers. |
| **Chassis Control** | **Manual RC / Wireless Teleoperation** | Controlled manually by the student demonstrator via remote control. |
| **Chassis Power** | **12V High-Amperage Battery Pack** | Independent power supply for motors and drivers. |

---

## Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/swapnil-jchauhan/Neurolis-AI-Humanoid.git
cd Neurolis-AI-Humanoid
```

### 2. Configure Environment & Dependencies
On Raspberry Pi 5 (Raspberry Pi OS Bookworm) or Linux:
```bash
# Create and activate virtual environment
python3 -m venv myenv
source myenv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Add API Keys
Create a `.env` file in the project root:
```env
GROQ_API_KEY_1=gsk_your_primary_key_here
GROQ_API_KEY_2=gsk_your_backup_key_here
```

### 4. Run Neurolis
```bash
# Standard Launch (Voice + Camera Gesture Sentry + Face UI)
python listen.py

# Text-Only Mode (Bypasses microphone; for quiet terminal testing)
python listen.py --text
```

---

## Project Roadmap & Future Vision

While we simplified the current build for safety and reliability at the exhibition, Project Neurolis remains under active development.

* [x] MediaPipe Tasks vision gesture sentry (✋ Wake / ✊ Standby)
* [x] Auditorium-grade dynamic noise floor acoustic endpointer (Endpointer v2)
* [x] 14-Key Groq API pool with sequential rate-limit failover
* [x] Edge-TTS 7.3.1 integration with Piper offline contingency
* [x] 60 FPS animated OLED facial expression engine
* [ ] Hardware repair: Replace broken capacitive touch digitizer
* [ ] Modular motor interface: Clean, isolated teleoperation serial bridge
* [ ] Next-gen obstacle avoidance: Proximity-based safety halt for manual teleoperation
* [ ] Re-evaluating autonomous navigation: Implementing safer, slower, and more predictable movement algorithms in future revisions

---

<div align="center">

### Built with pride by Swapnil Jai Chauhan & Shivam Verma
**Auckland House School for Boys — Science Exhibition Prototype**

*Simplicity and rock-solid reliability over fragile complexity.*

</div>
