<div align="center">

# Project Neurolis Mark II

### *An advanced humanoid AI software stack featuring a 21-expression 60 FPS OLED face UI, bilingual voice intelligence with Cartesia Sonic-3 neural speech, real-time live web search, and hands-free vision gesture control.*

[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12%20|%203.13-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20|%20Raspberry%20Pi%205-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://raspberrypi.com)
[![AI Engine](https://img.shields.io/badge/AI%20Engine-Groq%20LPU%20%7C%2014--Key%20Pool-F55036?style=for-the-badge&logo=fastapi&logoColor=white)](https://groq.com)
[![Voice](https://img.shields.io/badge/Voice-Cartesia%20Sonic--3-00f0ff?style=for-the-badge&logo=soundcharts&logoColor=white)](https://cartesia.ai)
[![Vision](https://img.shields.io/badge/Vision-MediaPipe%20Gestures-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://developers.google.com/mediapipe)
[![Phase](https://img.shields.io/badge/Phase-Mark%20II%20Software%20Active-00ff88?style=for-the-badge)](https://github.com)

<br/>

> [!IMPORTANT]
> **Work on Project Neurolis Mark II has officially commenced on the software side!**  
> Developed on a Windows 11 primary workstation and verified/tested on Raspberry Pi 5. The physical motor pipeline, motor drivers, DC motors, and LiDAR SLAM locomotion will be developed in **mid-2027**.*  
> <small><em>*Subject to change throughout development and requirement changes</em></small>

</div>

---

## Overview & Development Strategy: Software-First Excellence

Following the successful demonstration of the Mark 1 prototype at Auckland House School for Boys, **Project Neurolis Mark II** represents a full-scale architectural evolution.

Rather than wrestling with fragile mechanical hardware during rapid AI iteration, Mark II adopts a **strict software-first engineering paradigm**:
1. **Windows 11 Workstation Development**: Fast iteration, real-time DSP tuning, multi-model AI testing, and 60 FPS vector animation rendering.
2. **Raspberry Pi 5 Target Verification**: Continuous edge testing to ensure all audio, vision, gesture, and display pipelines run with sub-1.0s latency on embedded Linux.
3. **Mid-2027 Locomotion Roadmap**: All physical motor controller code, motor drivers, high-torque DC motors, and LiDAR SLAM navigation are officially scheduled for physical fabrication and integration in **mid-2027**.*  
   <small><em>*Subject to change throughout development and requirement changes</em></small>  
   Until then, the software stack is maintained 100% clean of premature or unverified motor commands.

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
│  └── 360° Omnidirectional Far-Field Audio Input Array                    │
│      ├── Spatial Beamforming & Active Acoustic Noise Suppression        │
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
│  │   ├── 21 Animated Pixar/EMO-Grade Vector Emotion States              │
│  │   ├── Live Gesture Hold Progress Bar & Mutually Exclusive HUD        │
│  │   └── High-Contrast Subtitles with Romanized Hinglish Translation    │
│  │                                                                      │
│  └── Bilingual Speech Synthesis with Expressive Emotion Engine          │
│      ├── Cartesia Sonic-3 Ultra-Low Latency Neural TTS (14-Key Fleet)   │
│      ├── Real-Time SSML Emotion & Nonverbal Modulation (<emotion/>)     │
│      └── Multi-Tier Zero-Crash Offline Voice Fallback                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Capabilities & Features

### 1. 21 Emotive Vector Face Expressions (`screen.py`)
Built from the ground up using pure scale-invariant Tkinter vector geometry rendering at a locked 60 FPS on pure space black (`#040711`):
* **Core Emotional States**: `IDLE`, `HAPPY`, `SAD`, `CONFUSED`, `THINKING`, `LISTENING`, `SPEAKING`, `WATCHING`, `MOVING`, `ERROR`.
* **Extended Mark II Emotions**: `EXCITED`, `PROUD`, `COOL`, `CURIOUS`, `WINK`, `SURPRISED`, `LAUGHING`, `LOVE`, `SHY`, `SKEPTICAL`, `SLEEPY`.
* **Contextual Emotion Engine**: Analyzes conversation sentiment in real-time, mapping topics dynamically (e.g. Creator accomplishments &rarr; `PROUD`, witty comebacks &rarr; `WINK`, flattery &rarr; `SHY`, deep reasoning &rarr; `THINKING`).
* **Synchronous Expression Demonstration**: A guided voice-and-face presentation cycling all 21 public expressions side-by-side with varied natural phrasing.

### 2. Studio Bilingual Voice & Expressive Emotion Engine (`Cartesia Sonic-3`)
* **Ultra-Low Latency Streaming**: Powered by Cartesia Sonic-3 with sub-150ms Time-To-First-Audio (TTFA) for near-instant conversational responsiveness.
* **Studio-Grade Bilingual Neural Voices**:
  * English: `Cooper` (`49743b08-0f5d-4741-839c-b12933853780`) — articulate, natural cadence.
  * Hindi & Hinglish: `Rohan` (`4877b818-c7fe-4c89-b1cf-eadf8e23da72`) — fluent, native Indian pronunciation.
* **Dynamic SSML Emotion & Nonverbal Modulation**:
  * Automatically maps active conversation states into XML SSML emotion tags (`<emotion value="..."/>`, `<speed ratio="..."/>`, `<volume ratio="..."/>`).
  * Injects authentic nonverbal vocalizations into speech delivery: audible laughter (`[laughter]`) on amusement/humor, vocal sobbing cadence on sadness, and a natural yawn (`[yawn]`) when entering standby mode.
* **Multi-Key Auto-Rotating Fleet**: Integrated 14-key pool (`CARTESIA_API_KEY_1` to `CARTESIA_API_KEY_14`) with automatic failover on rate limits and credit exhaustion.
* **Zero-Crash Redundancy**: Seamless multi-tier fallback ensures the robot never stalls or goes silent during network drops.
* **Romanized Hinglish Subtitles**: Automatically transliterates Devanagari text into clean Romanized Hinglish on the face display for instant audience readability.

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

### 5. 360° Omnidirectional Audio Input & Acoustic Endpointer
* **360° Omnidirectional Far-Field Microphone Array**: Uses spatial beamforming and active acoustic noise suppression engineered specifically for crowded, reverberant exhibition halls (65–75 dBA) to isolate the human speaker without requiring them to shout.
* **Rolling Ambient Noise Floor Tracking**: Tracks median room energy over a 66-frame (~2.0s) window to dynamically set speech onset at $+6\text{ dB}$ SNR ($\text{floor} \times 2.0$), rejecting distant crowd murmur while picking up conversational voice effortlessly.
* **Vocal Tunnel Filter**: Real-time FFT bandpass ($85\text{Hz}\text{--}5500\text{Hz}$) with a $+2.6\text{ dB}$ consonant presence shelf ($2.0\text{kHz}\text{--}4.0\text{kHz}$).
* **Bilingual Whisper STT Priming**: Biased with conversational Hinglish and exhibition vocabulary to accurately capture English, Hindi, and code-mixed speech without language misidentification.

### 6. Dynamic 14-Key Groq LPU Auto-Rotation Pool (`api_pool.py`)
* Auto-balances requests across up to 14 Groq API keys (`GROQ_API_KEY_1` to `GROQ_API_KEY_14`).
* On encountering rate limits (HTTP 429), it switches keys in ~10ms without dropping the user's conversation.

---

## Hardware & Target Deployment

| Subsystem | Current Mark II Software Stack | Mid-2027 Physical Locomotion Target* |
| :--- | :--- | :--- |
| **Primary Workstation** | **Windows 11 PC (Fast Prototyping)** | Core AI brain & telemetry station* <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **Edge Compute** | **Raspberry Pi 5 (Debian Bookworm)** | Onboard SBC running Linux aarch64* <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **Face Display** | **7-inch Display (1024x600)** | Emissive 60 FPS vector face & HUD* <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **Optical Vision** | **USB HD Webcam (720p / 1080p)** | MediaPipe gesture tracking & Groq vision* <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **Microphone** | **360° Omnidirectional Far-Field Microphone Array** | Spatial beamforming & active noise suppression* <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **Audio Output** | **Powered Speaker (USB / Bluetooth)** | Dual-engine neural voice output* <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **Locomotion Chassis** | *Clean Software Phase (No motors active)* | **4WD Skid-Steer Aluminum Chassis*** <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **Motor Drivers** | *Not connected in current phase* | **High-Current H-Bridge Motor Drivers*** <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **DC Motors** | *Not connected in current phase* | **High-Torque DC Motors*** <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |
| **LiDAR Navigation** | *Not connected in current phase* | **LiDAR (360° SLAM Autonomy)*** <br/><small><em>*Subject to change throughout development and requirement changes</em></small> |

<small><em>*All hardware targets and mechanical components are subject to change throughout development and requirement changes.</em></small>

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
Create a `.env` file in the project root with your multi-key fleet configuration:

```env
# ==============================================================================
# PROJECT NEUROLIS - MULTI-KEY GROQ API CONFIGURATION (1 TO 14 KEYS SUPPORTED)
# ==============================================================================
GROQ_API_KEY_1=gsk_your_primary_groq_key
GROQ_API_KEY_2=gsk_your_backup_key_2
GROQ_API_KEY_3=gsk_your_backup_key_3
GROQ_API_KEY_4=gsk_your_backup_key_4
GROQ_API_KEY_5=gsk_your_backup_key_5
GROQ_API_KEY_6=gsk_your_backup_key_6
GROQ_API_KEY_7=gsk_your_backup_key_7
GROQ_API_KEY_8=gsk_your_backup_key_8
GROQ_API_KEY_9=gsk_your_backup_key_9
GROQ_API_KEY_10=gsk_your_backup_key_10
GROQ_API_KEY_11=gsk_your_backup_key_11
GROQ_API_KEY_12=gsk_your_backup_key_12
GROQ_API_KEY_13=gsk_your_backup_key_13
GROQ_API_KEY_14=gsk_your_backup_key_14

# ==============================================================================
# PROJECT NEUROLIS - MULTI-KEY CARTESIA SONIC-3 TTS POOL (1 TO 14 KEYS SUPPORTED)
# ==============================================================================
CARTESIA_VOICE_EN=49743b08-0f5d-4741-839c-b12933853780
CARTESIA_VOICE_HI=4877b818-c7fe-4c89-b1cf-eadf8e23da72
CARTESIA_API_KEY_1=sk_car_your_primary_cartesia_key
CARTESIA_API_KEY_2=sk_car_your_cartesia_key_2
CARTESIA_API_KEY_3=sk_car_your_cartesia_key_3
CARTESIA_API_KEY_4=sk_car_your_cartesia_key_4
CARTESIA_API_KEY_5=sk_car_your_cartesia_key_5
CARTESIA_API_KEY_6=sk_car_your_cartesia_key_6
CARTESIA_API_KEY_7=sk_car_your_cartesia_key_7
CARTESIA_API_KEY_8=sk_car_your_cartesia_key_8
CARTESIA_API_KEY_9=sk_car_your_cartesia_key_9
CARTESIA_API_KEY_10=sk_car_your_cartesia_key_10
CARTESIA_API_KEY_11=sk_car_your_cartesia_key_11
CARTESIA_API_KEY_12=sk_car_your_cartesia_key_12
CARTESIA_API_KEY_13=sk_car_your_cartesia_key_13
CARTESIA_API_KEY_14=sk_car_your_cartesia_key_14
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
- [x] 21 hyper-expressive 60 FPS OLED vector face expressions
- [x] Bilingual English + Hindi speech synthesis via Cartesia Sonic-3 with SSML emotions
- [x] Zero-hallucination bilingual Whisper STT with Indic phonetic scrubber
- [x] Live edge web search and weather telemetry engine (`edge_search.py`)
- [x] MediaPipe Tasks vision hand gesture sentry (✋ Wake / ✊ Standby)
- [x] 360° Omnidirectional far-field acoustic endpointer with noise floor tracking
- [x] Dynamic 14-Key Groq LPU auto-rotation pool with rate-limit failover
- [x] Multi-key Cartesia Sonic-3 auto-rotation pool with quota protection
- [x] Purge all legacy Arduino controller code and obsolete motor commands

### Phase 2: Physical Locomotion & Robotics Hardware (Mid-2027)*  
<small><em>*Subject to change throughout development and requirement changes</em></small>
- [ ] Low-level motor controller pipeline on Raspberry Pi 5 / microcontrollers
- [ ] High-current motor driver integration with high-torque DC motors
- [ ] LiDAR integration for 360° indoor SLAM
- [ ] Safe, obstacle-aware autonomous navigation and docking
- [ ] Full humanoid physical chassis assembly and power distribution

---

<div align="center">

### Designed & Developed by Swapnil Jai Chauhan
*Concept, Software Architecture, AI Brain, Vision Pipeline, and Face Engine*  
*(Early Mark 1 physical prototype chassis contributed by Shivam Verma)*

**Auckland House School for Boys**

</div>
