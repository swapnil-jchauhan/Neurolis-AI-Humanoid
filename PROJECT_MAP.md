# Project Neurolis: Engineering Architecture & Development Chronicle

Last Updated: 2026-10-15  
Status: **Stable High School Exhibition Build (Under Active Development)**  
Authors: **Swapnil Jai Chauhan & Shivam Verma**  
Institution: **Auckland House School for Boys**  

> [!IMPORTANT]
> **Under continuous development, though slowed down. New and improved systems and features will be worked on in the future, this project is still very alive.**

---

## Executive Summary

Project Neurolis is an interactive 4-foot AI humanoid robot designed for science exhibitions, academic demonstrations, and STEM research. Built on a distributed compute model, Neurolis combines a high-level Python AI brain on a Raspberry Pi 5 with an expressive 60 FPS animated OLED facial UI, hands-free MediaPipe vision gesture control, auditorium-tuned acoustic voice endpointing, Groq-powered multi-key conversational intelligence, and an independently teleoperated 4WD chassis.

This document serves as the complete architectural map, historical chronicle, and technical specification of the project: detailing where we started, what we built, where we encountered failure, the engineering pivots we executed, and where the project stands today.

---

## 1. Where We Started (The Origin & Vision)

### The Dream
In mid-2026, as high school students at Auckland House School for Boys, we set out to build an interactive humanoid robot that could stand at our school science exhibition and genuinely interact with visitors. We didn't want a generic plastic toy playing recorded audio or a simple RC car with a speaker attached. We envisioned a complete cybernetic character:
1. **Humanoid Presence**: A 4-foot mobile chassis with a sleek animated face.
2. **Autonomous Mobility**: A robot that could autonomously patrol the exhibition hall, detect approaching people, steer towards them, and follow them around while avoiding obstacles.
3. **Conversational Fluidity**: Real-time voice interaction with natural conversational intelligence, witty personality, and expressive emotional reactions.
4. **Active Vision**: An optical sentry that could look at what guests held in their hands and answer questions about their surroundings.

### The Original Architecture Blueprint
To achieve this, we designed a two-tiered system:
* **High-Level Brain (Raspberry Pi 5 / Windows PC)**: Running voice recognition, Whisper STT, Groq LLM inference, Edge-TTS speech synthesis, OpenCV YuNet facial tracking, and an animated Pygame/Tkinter face UI on a 7-inch touchscreen.
* **Low-Level Controller (Arduino Mega 2560)**: Running 4x BTS7960 43A motor drivers on 12V Johnson DC motors with a modular 16-sensor ultrasonic radar array (HC-SR04) for 360-degree autonomous collision avoidance.

---

## 2. Where We Reached (The Engineering Journey & Milestones)

Over months of intensive development, we built and verified several core subsystems:

### A. The Groq Conversational Engine & 14-Key Fleet Rotation
* **Sub-Second LLM Inference**: Integrated `qwen/qwen3.8-27b` and `whisper-large-v3-turbo` via Groq Cloud LPUs, slashing conversational response latency from 6+ seconds down to sub-800ms.
* **Dynamic 14-Key Fleet Auto-Rotation**: To prevent the robot from freezing when free-tier API quotas were exhausted, we built a dynamic key pool loader (`api_pool.py`). The system automatically loads up to 14 keys (`GROQ_API_KEY_1` through `GROQ_API_KEY_14`), detects HTTP 429 rate limits, and instantly fails over to the next standby key in ~10ms without dropping the user's conversation.
* **Zero-Token Fast-Paths**: Standalone greetings ("Hello", "Hi"), uncertainty queries ("What do you suggest?"), and diagnostic checks ("Which key is active?") execute locally in Python with 0ms latency and 0 API token burn.

### B. 60 FPS Animated OLED Face Engine (`screen.py`)
* Designed a Vector & EMO-inspired cyber face rendering high-contrast emissive shapes on pure space black (`#040711`).
* Built **7 distinct animated emotional states**:
  * `IDLE`: Calm cyan glowing eyes with natural breathing cadence.
  * `HAPPY`: Emerald smiling crescents ($\cap \;\; \cap$) with vertical bounce.
  * `SAD`: Sapphire downcast eyes with an animated falling digital teardrop.
  * `CONFUSED`: Spinning cyber vortex spirals with orbital stars.
  * `THINKING`: Squinting eyes with spinning quantum data rings.
  * `SPEAKING`: Voice-reactive eye squash/stretch synced with audio playback.
  * `WATCHING`: Optical viewfinder reticle brackets with vertical scanning laser line.
* Integrated real-time word-wrapped dual-color subtitle telemetry (`[YOU]` in mint green, `[NEUROLIS]` in cyan).

### C. Speech Synthesis & Gapless Pipelining
* Integrated **Microsoft Edge-TTS** (`en-US-ChristopherNeural`) with in-memory WAV decoding via `soundfile`, bypassing disk I/O completely.
* Built **Pipelined Sentence Splitting**: Sentences are split into chunks and synthesized concurrently over a persistent background asyncio event loop (`_tts_loop`). Chunk 1 begins speaking in ~1.0s while Chunk 2 synthesizes in the background, achieving 100% gapless continuous speech.
* Integrated **Piper Neural TTS** (`en_US-lessac-low.onnx`) as a local, offline fallback engine so the robot never goes mute even if Wi-Fi disconnects.

### D. Auditorium-Grade Dynamic Acoustic Endpointer (Endpointer v2)
* Built `audio_frontend.py` to solve the exhibition hall noise challenge (crowds, cafeteria chatter, acoustic reverberation):
  * **Rolling Ambient Noise Floor Tracking**: Computes median ambient room energy over a 66-frame (~2.0s) window. Dynamically sets speech onset threshold at $+6\text{ dB}$ SNR ($\text{floor} \times 2.0$), ensuring that in loud rooms (~220 RMS), distant background crowd chatter is rejected while normal voice triggers smoothly without shouting.
  * **Dynamic Continuation Hangover**: Anchors speech continuation threshold to $32\%$ of the active speaker's median volume, allowing the silence timer to finalize cleanly as soon as the speaker stops without hanging.
  * **Whole-Utterance Vocal Tunnel Filter**: Applies FFT bandpass ($85\text{Hz}\text{--}5500\text{Hz}$) with a $+2.6\text{ dB}$ consonant presence shelf ($2.0\text{kHz}\text{--}4.0\text{kHz}$) across the entire audio array before passing to Whisper.

---

## 3. Where We Failed & The Hard Lessons Learned

Real-world robotics is brutally unforgiving. As we prepared for live deployment, several critical failure points emerged:

### Failure 1: The Autonomous Movement Pipeline Was Way Too Complex & Fragile
* **The Reality**: Developing a fully autonomous mobile humanoid—roaming through dynamic crowds, tracking and following people across varying lighting conditions, and negotiating obstacles via 16 ultrasonic sensors—proved to be **far too advanced and fragile** for our available timeframe and resources.
* **The Symptoms**:
  * Ultrasonic sensors suffered from acoustic cross-talk, specular reflection off angled surfaces, and noise spikes from hall crowds.
  * Visual person tracking (YuNet bounding box ratio) struggled when people turned sideways, when lighting shifted, or when multiple visitors stood in frame.
  * The robot would occasionally stutter between roam and obstacle-avoidance states, drift off course, or trigger false emergency stops.
* **The Verdict**: An autonomous robot that freezes, misjudges distances, or risks bumping into visitors during a crowded science fair is unacceptable. We recognized that attempting full autonomy with our current sensor setup was overambitious and unreliable.

### Failure 2: Hardware Incident — The Touchscreen Digitizer Broke
* During physical chassis assembly and bracket mounting, the capacitive touch layer on our 7-inch display cracked. 
* While the LCD panel itself still rendered crystal-clear 60 FPS graphics, touch input was completely dead. The on-screen "Talk to Neurolis" and "Stand-by" buttons became unusable, threatening our entire interaction workflow.

### Failure 3: Cloud API & Network Fragilities
* **Edge-TTS 403 Forbidden Errors**: Microsoft updated its backend WebSocket security requirements for Edge "Read Aloud", requiring a time-sensitive cryptographic `Sec-MS-GEC` token. Older versions of `edge-tts` (7.2.8) were rejected with `403 Forbidden`, causing the robot to fall back to offline speech.
* **Subprocess Timeouts**: Early implementations of the Piper offline fallback called `pw-play` via `subprocess.Popen` with a fixed 12.0s timeout. When speaking longer multi-sentence replies, the playback was prematurely killed by the timeout.

---

## 4. What We Did Now (The Practical Engineering Pivot)

Rather than letting these setbacks derail the project, we made decisive, disciplined engineering pivots to guarantee a stable, dependable, and safe exhibition build:

### Pivot 1: Stripped All Autonomous Movement & Switched to Full Manual Teleoperation
* **Action**: We completely purged all autonomous movement code from the high-level brain (`listen.py`):
  * Deleted `motors.py`.
  * Removed autonomous roam mode, sentry approach mode, person-following (`FOLLOW`), spin, and step-back routines.
  * Purged all motor action parsing (`<action motor="...">`), intent classification prompts, and motor fast-paths.
* **The New Mobility Reality**: The 4WD chassis is now operated via **Full Manual Remote Control (Teleoperation)** through a dedicated Arduino RF/RC receiver.
* **Result**: Movement is 100% safe, reliable, and predictable. The student operator drives the robot manually during demonstrations, completely eliminating any risk of collision, sensor confusion, or runaway motion.

### Pivot 2: Hands-Free MediaPipe Vision Gesture Sentry
* **Action**: To solve the broken touchscreen problem, we turned our USB camera into a hands-free interaction controller using **Google MediaPipe Tasks Vision Gesture Recognizer** (`gesture_sentry.py`):
  * Runs in a dedicated background thread at ~15 FPS on downscaled 320x240 RGB frames.
  * ✋ **Open Palm held for 3 seconds** &rarr; Wakes Neurolis from `STANDBY` into active conversation (`LISTENING...`).
  * ✊ **Closed Fist held for 3 seconds** &rarr; Forces Neurolis into `STANDBY` mode.
  * **Strict State Guards**: When in standby, closed fists produce no response; when active, open palms produce no response.
  * **Screen HUD Progress Bar**: Replaced the obsolete touch buttons in `screen.py` with a live visual gesture HUD bar positioned above the subtitles, showing an animated fill gauge (0% to 100%) as a visitor holds the gesture.

### Pivot 3: Permanent Fix for Speech Engines
* **Edge-TTS 7.3.1**: Upgraded `edge-tts` to version 7.3.1 in our virtual environment, updating the `Sec-MS-GEC` token handshake and restoring sub-1.5s online neural speech with zero errors.
* **Direct SoundDevice Piper Playback**: Re-engineered `_speak_local_offline_fallback()` so Piper synthesized WAV bytes are decoded via `soundfile` and fed directly to `play_sounddevice_audio(data, sr)`. This completely eradicated the 12.0s `pw-play` subprocess timeout, ensuring flawless offline voice output.

### Pivot 4: Auditorium Acoustic Acceptance Clamping
* In `audio_frontend.py`, refined the finalization acceptance check from `p90_rms < floor * 1.8` down to `p90_rms < max(min_onset_rms, floor * 1.35)`.
* In high-noise environments (floor ~220 RMS), normal conversational speech (450–650 RMS) is accepted 100% of the time with **zero shouting required**, while ambient crowd murmur is rejected.

---

## 5. Where We Finally Are (Current Architecture & Master Files)

The codebase has been stripped of all bloat, dead code, and broken pipelines. The current active project structure is clean, modular, and robust:

```
Neurolis-AI-Humanoid/
├── listen.py               # Master Brain: Audio I/O, VAD, Groq LLM, TTS, & UI Orchestrator
├── screen.py               # 60 FPS Animated OLED Face Engine & MediaPipe Gesture HUD
├── gesture_sentry.py       # Background MediaPipe Tasks Hand Gesture Recognition Worker
├── audio_frontend.py       # Endpointer v2: Dynamic Noise Floor, WebRTC VAD, & DSP Filter
├── api_pool.py             # 14-Key Dynamic Groq API Key Pool & Auto-Rotation Manager
├── intent_rules.py         # Response pools, greetings, fast-path intent matching, & personality
├── mic_config.json         # Calibrated audio thresholds, cutoff frequencies, & gain settings
├── gesture_recognizer.task # Official MediaPipe Tasks gesture classification model asset
├── motor_controller.ino    # Arduino sketch for manual wireless remote control (teleoperation)
├── assets/                 # Sound effects, Piper offline model, and UI graphics
│   └── piper/              # en_US-lessac-low.onnx neural TTS model
├── README.md               # Public project documentation & quickstart guide
├── COMPONENT_LIST.md       # Hardware inventory & component specifications
└── PROJECT_MAP.md          # Architecture map, engineering chronicle, & future roadmap
```

### Active Core Features:
1. **Interactive Conversational Talkbot**: Articulate student presenter identity, grounded in Auckland House School for Boys, explaining its systems truthfully when asked.
2. **Hands-Free Gesture Activation**: MediaPipe ✋ Open Palm wake / ✊ Closed Fist standby with 3.0s hold safety and on-screen progress indicator.
3. **Expressive 60 FPS Face UI**: 7 emotional states, natural eye blinking, voice-synced mouth squashing, and real-time dual-color subtitles.
4. **On-Demand Camera Vision**: Groq Vision integration answering "What am I holding?" or "Look at this" via single-frame capture.
5. **Acoustic Noise Resilience**: Dynamic rolling noise floor tracking rejecting background hall chatter without requiring users to shout.
6. **Dual Speech Synthesis**: Online Edge-TTS with instant offline Piper neural fallback.
7. **Safe Teleoperated 4WD Mobility**: Independent manual driver control via wireless remote.

---

## 6. The Future Roadmap (The Project Is Very Alive)

Although development has been slowed down to focus on high school academic priorities and the upcoming exhibition, Project Neurolis is actively evolving. Our planned future roadmap includes:

- [ ] **Hardware Repair**: Replacing the cracked 7-inch capacitive touchscreen digitizer to restore optional touch controls alongside gesture recognition.
- [ ] **Modular Telemetry Bridge**: Establishing a clean, non-blocking serial telemetry link between Raspberry Pi and Arduino for battery monitoring and chassis status.
- [ ] **Proximity Safety Halt**: Implementing low-level hardware emergency braking on the Arduino (cutting motor power if an obstacle is within 20cm during manual driving).
- [ ] **Re-Engineering Autonomy (The Right Way)**:
  - Replacing the fragile ultrasonic bank with a 2D LiDAR scanner (e.g. RPLiDAR A1) for true 360° SLAM mapping.
  - Designing a slower, heavily constrained, state-machine-driven autonomous roam mode with clear recovery behaviors and fail-safes.
- [ ] **On-Device Vision Models**: Exploring lightweight local edge vision models (e.g., MobileNet / YOLO-nano) for local object detection without cloud API dependency.

---

<div align="center">

### Built with pride by Swapnil Jai Chauhan & Shivam Verma
**Auckland House School for Boys — Science Exhibition Prototype**

*Simplicity and rock-solid reliability over fragile complexity.*

</div>
