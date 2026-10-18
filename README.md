<div align="center">

# Project Neurolis Mark II

### *An advanced humanoid AI software stack featuring a 22-expression 60 FPS OLED face UI, bilingual voice intelligence with emotional prosody, real-time live web search, and hands-free vision gesture control.*

[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20|%20Raspberry%20Pi%205-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://raspberrypi.com)
[![AI Engine](https://img.shields.io/badge/AI%20Engine-Groq%20LPU%20%7C%2014--Key%20Pool-F55036?style=for-the-badge&logo=fastapi&logoColor=white)](https://groq.com)
[![Voice](https://img.shields.io/badge/Voice-Bilingual%20%7C%20Emotional%20Prosody-00f0ff?style=for-the-badge)](https://github.com)
[![Vision](https://img.shields.io/badge/Vision-MediaPipe%20Gestures-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://developers.google.com/mediapipe)
[![Phase](https://img.shields.io/badge/Phase-Mark%20II%20Software%20Active-00ff88?style=for-the-badge)](https://github.com)

<br/>

> [!IMPORTANT]
> **Work on Project Neurolis Mark II has officially commenced on the software side!**  
> Developed on a Windows 11 primary workstation and verified/tested on Raspberry Pi 5. The physical motor pipeline, BTS7960 drivers, Johnson DC motors, and 2D LiDAR SLAM locomotion will be developed in **mid-2027**.

</div>

---

## Overview & Development Strategy: Software-First Excellence

Following the successful demonstration of the Mark 1 prototype at Auckland House School for Boys, **Project Neurolis Mark II** represents a full-scale architectural evolution.

Rather than wrestling with fragile mechanical hardware during rapid AI iteration, Mark II adopts a **strict software-first engineering paradigm**:
1. **Windows 11 Workstation Development**: Fast iteration, real-time DSP tuning, multi-model AI testing, and 60 FPS vector animation rendering.
2. **Raspberry Pi 5 Target Verification**: Continuous edge testing to ensure all audio, vision, gesture, and display pipelines run with sub-1.0s latency on embedded Linux.
3. **Mid-2027 Locomotion Roadmap**: All physical motor controller code, BTS7960 H-bridges, 12V Johnson DC motors, and 2D LiDAR SLAM navigation are officially scheduled for physical fabrication and integration in **mid-2027**. Until then, the software stack is maintained 100% clean of premature or unverified motor commands.

---

## Mark II Software Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       PROJECT NEUROLIS MARK II                          │
│        Primary Workstation: Windows 11  |  Edge Target: Raspberry Pi 5  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [INPUT PERCEPTION]                                                     │
│  ├── USB Camera (/dev/video0)                                           │
│  │   ├── MediaPipe Tasks Gesture Sentry (✋ Wake / ✊ Standby)          │
│  │   └── On-Demand Groq Vision Snapshot Analyzer                        │
│  │                                                                      │
│  └── 16kHz Studio Audio In                                              │
│      ├── Dynamic Rolling Noise Floor Tracker (Auditorium-grade)         │
│      ├── Sub-Utterance Vocal Tunnel DSP Bandpass (85Hz - 5.5kHz)        │
│      └── Groq Whisper Large v3 (Zero-Hallucination Bilingual STT)       │
│                                                                         │
│  [COGNITIVE CORE & KNOWLEDGE]                                           │
│  ├── 14-Key Groq LPU Auto-Rotating Fleet Manager (api_pool.py)          │
│  ├── Low-Latency Qwen 27B Conversational LLM Engine                     │
│  ├── Zero-Token Local Fast-Paths (Greetings, Capabilities, Diagnostics) │
│  └── Live Edge Knowledge Engine (edge_search.py)                        │
│      ├── Instant Atmospheric Telemetry (wttr.in)                        │
│      ├── Wikipedia Encyclopedic Entity Summaries                        │
│      └── DuckDuckGo Real-Time Web Search & Deep Research                │
│                                                                         │
│  [EXPRESSIVE OUTPUT ENGINES]                                            │
│  ├── 60 FPS HyperSmooth Face UI (screen.py)                             │
│  │   ├── 22 Animated Pixar/EMO-Grade Vector Emotion States              │
│  │   ├── Live Gesture Hold Progress Bar & Mutually Exclusive HUD        │
│  │   └── High-Contrast Subtitles with Romanized Hinglish Translation    │
│  │                                                                      │
│  └── Bilingual Speech Synthesis with Emotional Prosody                  │
│      ├── Microsoft Edge Neural TTS (AndrewMultilingual & MadhurNeural)   │
│      ├── ChatGPT-Style Pitch/Rate Dynamic Modulation                    │
│      └── Piper Neural Offline Local Fallback (en_US-lessac-low.onnx)   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Capabilities & Features

### 1. 22 Emotive Vector Face Expressions (`screen.py`)
Built from the ground up using pure scale-invariant Tkinter vector geometry rendering at a locked 60 FPS on pure space black (`#040711`):
* **Core Emotional States**: `IDLE`, `HAPPY`, `SAD`, `CONFUSED`, `THINKING`, `LISTENING`, `SPEAKING`, `WATCHING`, `MOVING`, `ERROR`, `VILLAIN`.
* **Extended Mark II Emotions**: `EXCITED`, `PROUD`, `COOL`, `CURIOUS`, `WINK`, `SURPRISED`, `LAUGHING`, `LOVE`, `SHY`, `SKEPTICAL`, `SLEEPY`.
* **Contextual Emotion Engine**: Analyzes conversation sentiment in real-time, mapping topics dynamically (e.g. Creator accomplishments &rarr; `PROUD`, witty comebacks &rarr; `WINK`, flattery &rarr; `SHY`, deep reasoning &rarr; `THINKING`).
* **Synchronous Expression Demonstration**: A guided voice-and-face presentation cycling all 21 public expressions side-by-side with varied natural phrasing.
* **Rogue AI Easter Egg (`VILLAIN`)**: A single-session sci-fi narrative mode with CRT scanlines and ghostly split-optic chromatic ghosting, strictly locked out of public demonstration loops.

### 2. Studio Bilingual Voice & Emotional Prosody (ChatGPT Voice Style)
* **Bilingual English & Hindi STT**: Uses unconstrained Groq Whisper with custom bilingual prefix priming (`Namaste, aap kaise hain? Hello, how are you?`), accurately transcribing pure English, Hindi, and code-mixed Hinglish without phonetic hallucinations.
* **Studio-Grade Neural Voices**:
  * English: `en-US-AndrewMultilingualNeural` (natural, human-like breath, warm cadence).
  * Hindi: `hi-IN-MadhurNeural` (rich, articulate male voice).
* **Dynamic Emotional Prosody**: Adjusts pitch and speech tempo in real-time based on the active emotion (e.g. cheeky winks gain $+8\text{Hz}$ pitch and $+16\%$ tempo; sad responses drop $-6\text{Hz}$ and slow down; rogue AI drops $-16\text{Hz}$ for an ominous delivery).
* **Romanized Hinglish Subtitles**: Automatically transliterates Devanagari text into clean Romanized Hinglish for instant on-screen readability.

### 3. Real-Time Live Web Search & Knowledge Engine (`edge_search.py`)
* **100% Free & Keyless Edge Architecture**:
  * *Live Weather*: Instant atmospheric telemetry via `wttr.in` for live temperature, humidity, and forecast updates.
  * *Wikipedia REST API*: Low-latency encyclopedic summaries for scientific, historical, and technical concepts.
  * *DuckDuckGo Search (`ddgs`)*: Real-time search for breaking news, current events, and deep research topics.
* **Sub-80 Token Salience Filter**: Injected search context is condensed into a concise snippet (< 60 words), keeping Groq prompt token usage strictly under 80 tokens with zero residual memory footprint.

### 4. Hands-Free MediaPipe Vision Gesture Sentry (`gesture_sentry.py`)
* Runs in a background thread at ~15 FPS on downscaled 320x240 RGB frames from `/dev/video0`.
* **3-Second Hold Validation**:
  * In **Standby**: ✋ **Open Palm held for 3.0s** wakes the robot into active conversation.
  * In **Active**: ✊ **Closed Fist held for 3.0s** forces the robot into standby.
* **Mutually Exclusive Progress HUD**: Dynamic on-screen fill gauge provides visual countdown feedback without text overlapping or visual clipping.

### 5. Auditorium-Grade Dynamic Acoustic Endpointer (Endpointer v2)
* Built specifically for high-noise venues like school auditoriums, exhibitions, and STEM halls (65–75 dBA).
* **Rolling Ambient Noise Floor Tracking**: Tracks median room energy over a 66-frame (~2.0s) window to dynamically set speech onset at $+6\text{ dB}$ SNR ($\text{floor} \times 2.0$), rejecting distant crowd murmur while picking up conversational voice effortlessly.
* **Vocal Tunnel Filter**: Real-time FFT bandpass ($85\text{Hz}\text{--}5500\text{Hz}$) with a $+2.6\text{ dB}$ consonant presence shelf ($2.0\text{kHz}\text{--}4.0\text{kHz}$).

### 6. Dynamic 14-Key Groq LPU Auto-Rotation Pool (`api_pool.py`)
* Auto-balances requests across up to 14 Groq API keys (`GROQ_API_KEY_1` to `GROQ_API_KEY_14`).
* On encountering rate limits (HTTP 429), it switches keys in ~10ms without dropping the user's conversation.

---

## Hardware & Target Deployment

| Subsystem | Current Mark II Software Stack | Mid-2027 Physical Locomotion Target |
| :--- | :--- | :--- |
| **Primary Workstation** | **Windows 11 PC (Fast Prototyping)** | Core AI brain & telemetry station |
| **Edge Compute** | **Raspberry Pi 5 (Debian Bookworm)** | Onboard SBC running Linux aarch64 |
| **Face Display** | **7-inch Display (1024x600)** | Emissive 60 FPS vector face & HUD |
| **Optical Vision** | **USB HD Webcam (720p / 1080p)** | MediaPipe gesture tracking & Groq vision |
| **Microphone** | **USB Studio Microphone / Audio Array** | Dynamic noise-floor acoustic endpointer |
| **Audio Output** | **Powered Speaker (USB / Bluetooth)** | Dual-engine neural voice output |
| **Locomotion Chassis** | *Clean Software Phase (No motors active)* | **4WD Skid-Steer Aluminum Chassis** |
| **Motor Drivers** | *Not connected in current phase* | **4x BTS7960 43A H-Bridge Drivers** |
| **DC Motors** | *Not connected in current phase* | **4x 12V Johnson High-Torque DC Motors** |
| **LiDAR Navigation** | *Not connected in current phase* | **2D LiDAR Scanner (360° SLAM Autonomy)** |

---

## Setup & Quickstart

### 1. Clone the Repository
```bash
git clone https://github.com/swapnil-jchauhan/Neurolis-AI-Humanoid.git
cd Neurolis-AI-Humanoid
```

### 2. Configure Environment & Dependencies
```bash
# Python 3.10+ virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate

# On Raspberry Pi 5 / Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Add API Keys
Create a `.env` file in the project root:
```env
GROQ_API_KEY_1=gsk_your_primary_key_here
GROQ_API_KEY_2=gsk_your_backup_key_here
```

### 4. Run Project Neurolis Mark II
```bash
# Full Interactive Launch (Voice + Gesture Sentry + 60 FPS Face UI)
python listen.py

# Text-Only Simulation Mode (Quiet terminal testing without mic)
python listen.py --text
```

---

## Project Roadmap

### Phase 1: Software Stack Perfection (Late 2026 - Early 2027) [ACTIVE]
- [x] 22 hyper-expressive 60 FPS OLED vector face expressions
- [x] Bilingual English + Hindi speech synthesis with ChatGPT-style emotional prosody
- [x] Zero-hallucination bilingual Whisper STT with Indic phonetic scrubber
- [x] Live edge web search and weather telemetry engine (`edge_search.py`)
- [x] MediaPipe Tasks vision hand gesture sentry (✋ Wake / ✊ Standby)
- [x] Auditorium-tuned dynamic acoustic endpointer (Endpointer v2)
- [x] Dynamic 14-Key Groq LPU auto-rotation pool with rate-limit failover
- [x] Purge all legacy Arduino controller code and obsolete motor commands

### Phase 2: Physical Locomotion & Robotics Hardware (Mid-2027)
- [ ] Low-level motor controller pipeline on Raspberry Pi 5 / microcontrollers
- [ ] 4x BTS7960 43A motor driver integration with 12V Johnson DC motors
- [ ] 2D LiDAR scanner integration (RPLiDAR A1 / C1) for 360° indoor SLAM
- [ ] Safe, obstacle-aware autonomous navigation and docking
- [ ] Full humanoid physical chassis assembly and power distribution

---

<div align="center">

### Designed & Developed by Swapnil Jai Chauhan
*Concept, Software Architecture, AI Brain, Vision Pipeline, and Face Engine*  
*(Early Mark 1 physical prototype chassis contributed by Shivam Verma)*

**Auckland House School for Boys**

</div>
