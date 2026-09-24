<div align="center">

# 🤖 Project Neurolis

### *An interactive, 4-foot AI humanoid robot with expressive 60 FPS OLED face, conversational voice, smart person tracking, and 4WD skid-steer mobility.*

[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205%20|%20Windows%20PC-0078D4?style=for-the-badge&logo=raspberrypi&logoColor=white)](https://raspberrypi.com)
[![Groq AI](https://img.shields.io/badge/AI%20Engine-Groq%20Whisper%20&%20Qwen-F55036?style=for-the-badge&logo=fastapi&logoColor=white)](https://groq.com)
[![Hardware](https://img.shields.io/badge/Hardware-Arduino%20Mega%202560-00979D?style=for-the-badge&logo=arduino&logoColor=white)](https://arduino.cc)
[![Chassis](https://img.shields.io/badge/Chassis-4WD%20Skid--Steer-00ff88?style=for-the-badge)](https://github.com)
[![Status](https://img.shields.io/badge/Status-Tested%20&%20Exhibition%20Ready-00f0ff?style=for-the-badge)](https://github.com)

<br/>

> **"Software architecture and entire ready-to-use code for anyone who wants to implement my pipeline for their humanoid AI robot project. Runs seamlessly with FULL physical hardware, or with ZERO hardware in instant PC simulation mode!"**

</div>

---

## 📌 Quick Access

- [1. What is this?](#1-what-is-this)
- [2. Who is this for?](#2-who-is-this-for)
- [3. Things to Know (The Smart Guardrails)](#3-things-to-know-the-smart-guardrails)
  - [Zero-Hardware Simulation Mode](#-zero-hardware-simulation-mode-test-on-any-pc)
  - [Automatic Hardware Detection & Pipeline Switch](#-automatic-hardware-detection--pipeline-switch)
  - [0, 4, 8, 12, or 16 Ultrasonic Sensors (Zero Code Changes!)](#-0-4-8-12-or-16-ultrasonic-sensors-zero-code-changes)
  - [Dual-Layer Safety & 0ms Emergency Stop](#-dual-layer-safety--0ms-emergency-stop)
  - [Unified Single-Pass AI Pipeline (Token Saver)](#-unified-single-pass-ai-pipeline-token-saver)
- [4. How to Use & Setup](#4-how-to-use--setup)
  - [Requirements & Dependencies](#-requirements--dependencies)
  - [Required Final Hardware List](#-required-final-hardware-list)
  - [Step-by-Step Installation](#-step-by-step-installation)
  - [Main Code: Running the Robot Brain (`listen.py`)](#-main-code-running-the-robot-brain-listenpy)
  - [Manual Control & Calibrator (`manual_control.py`)](#-manual-control--calibrator-manual_controlpy)
  - [Automated Safety Tests](#-automated-safety-tests)
- [5. Features (In Simple Language)](#5-features-in-simple-language)
- [6. Hardware Pinout Reference (Arduino Mega 2560)](#6-hardware-pinout-reference-arduino-mega-2560)

---

## 1. What is this?

**Project Neurolis** is an end-to-end software architecture and ready-to-use code pipeline for building an interactive 4-foot humanoid robot for minor projects, science fairs, and school exhibitions.

Instead of throwing everything into one messy script that crashes and lags, Neurolis uses a clean **distributed intelligence model**:

```
                       ┌──────────────────────────────────────────────┐
                       │       Raspberry Pi 5 (or Windows PC)         │
                       │──────────────────────────────────────────────│
                       │  • Groq Whisper Speech-to-Text (STT)         │
                       │  • Groq Qwen Fast Conversational LLM         │
                       │  • Edge-TTS Natural Voice Synthesis          │
                       │  • 60 FPS Animated OLED Face UI (7" Screen)  │
                       │  • OpenCV YuNet 30+ FPS Face/Person Tracking │
                       └──────────────────────┬───────────────────────┘
                                              │ USB Serial (115200 baud)
                                              ▼
                       ┌──────────────────────────────────────────────┐
                       │              Arduino Mega 2560               │
                       │──────────────────────────────────────────────│
                       │  • 4x BTS7960 High-Power Motor Drivers       │
                       │  • 4x 12V Johnson Non-Encoder DC Motors      │
                       │  • 16-Sensor Scalable Ultrasonic Radar Array │
                       │  • Independent Hardware Obstacle Hard-Brake  │
                       │  • 600ms Hardware Watchdog Motor Cutoff      │
                       └──────────────────────────────────────────────┘
```

* **High-Level Brain (Raspberry Pi 5 or Windows PC)**: Handles voice hearing, conversational thinking, speaking, 60 FPS screen expressions, camera vision, and face tracking.
* **Low-Level Motor & Safety Guardian (Arduino Mega 2560)**: Directly controls the wheels, pings distance sensors, and slams the brakes if anything gets too close — completely independent of internet connection or API status!

*(ONLY made for FOUR-WHEEL POWERED chassis, can be adapted to support two motors).*

---

## 2. Who is this for?

* **Students & Makers** building a school exhibition, college capstone, or STEM demonstration humanoid robot.
* **Robotics Enthusiasts** with a 4WD chassis who want full autonomous person-following, conversational AI, and expressive face UI without coding from scratch.
* **Anyone Without Hardware Yet**: You can test, develop, and present the full robot on your laptop right now using the built-in **Zero-Hardware Simulation Mode**!
* **Exhibition Builders** who need reliability: A robot that can run continuously for 6+ hours without freezing, running out of API tokens, or crashing when someone unplugs a cable.

---

## 3. Things to Know (The Smart Guardrails)

We spent massive engineering effort ensuring Neurolis is **bulletproof**. Here are the critical guardrails built directly into the system:

### 🛡️ Zero-Hardware Simulation Mode (Test on Any PC)
> **NOTE: YOU DO NOT NEED MOTORS, DRIVERS, SENSORS, OR AN ARDUINO TO DEVELOP OR TEST!**
* Guardrails have been added to make sure the software runs smoothly on your computer even if physical hardware is completely missing.
* When hardware is absent, the system activates **Virtual 4WD Physics & Distance Telemetry**.
* The screen displays exact real numbers: it honestly reports `Physical Motors: 0 (Simulation Mode)` with a ruby cross `[ ✗ ]` instead of fake numbers.
* You can converse, test facial expressions, verify vision, and test motor commands in the terminal with zero crashes.

### 🔌 Automatic Hardware Detection & Pipeline Switch
* The software probes USB serial COM ports, live webcams, microphones, and audio drivers on every launch.
* **Zero code edits**: As soon as you plug your Arduino Mega or USB camera in, the program automatically detects it and kicks in the real hardware task it was meant to do!

### 📡 0, 4, 8, 12, or 16 Ultrasonic Sensors (Zero Code Changes!)
* The Arduino firmware (`arduino.ino`) features an auto-detecting **16-Sensor Modular Array** divided into 4 symmetrical banks (1 sensor per side: Front, Left, Right, Rear):
  * **0 Sensors**: Plugged in on your desk with no sensors? The Arduino skips ultrasonic pings completely with zero delay, sets distances to `999.0 cm`, and lets you test motors freely without false obstacle stops.
  * **4 Sensors (Bank 1)**: Base perimeter (1 on each side).
  * **8 Sensors (Banks 1 & 2)**: Corner and perimeter coverage.
  * **12 Sensors (Banks 1, 2 & 3)**: Wide-angle flanking coverage.
  * **16 Sensors (All 4 Banks)**: Full 360° god-tier obstacle radar.
* **Time-Sliced Bank Interleaving**: Only pings 1 bank per 50ms tick. Zero CPU choking and zero acoustic cross-talk because simultaneous pings face opposite directions!

### 🚨 Dual-Layer Safety & 0ms Emergency Stop
* **0ms Intent Fast-Path**: Words like *"stop"*, *"freeze"*, or *"halt"* bypass the LLM API completely and execute in 0 milliseconds, immediately locking wheels.
* **Hardware Emergency Brake**: If any obstacle is closer than `20 cm` in the direction of travel, the Arduino firmware cuts PWM power to `0` directly in microcontroller machine code, overriding any high-level command.
* **600ms Watchdog**: If the Pi crashes or serial communication disconnects for >600ms, the Arduino cuts all motor power automatically.

### ⚡ Unified Single-Pass AI Pipeline (Token Saver)
* Previously, systems ran multiple LLM calls for motor intent, camera checks, and sentiment. 
* Neurolis combines speech reply, motor actions (`<action motor="...">`), vision triggers (`<action>CAMERA</action>`), and empathy checks (`<action>MEAN</action>`) into **ONE single Groq API pass**.
* This slashes token usage by over 60% and cuts response latency in half!

---

## 4. How to Use & Setup

### 📦 Requirements & Dependencies

#### Software Environment
* **Operating System**: Windows 10/11 (for PC testing) or Raspberry Pi OS Debian Bookworm 64-bit (for robot deploy).
* **Python**: `3.10`, `3.11`, or `3.12`.
* **Arduino IDE**: Version 1.8.x or 2.x (to flash the Mega once).
* **Groq API Key**: Free API key from [console.groq.com](https://console.groq.com).

---

### 📋 Required Final Hardware List

| Category | Component | Qty | Role & Notes |
| :--- | :--- | :---: | :--- |
| **Compute** | **Raspberry Pi 5 (4GB or 8GB)** | 1 | Master brain running Python, AI, voice, vision, and UI. Use active cooler/fan! |
| **Microcontroller** | **Arduino Mega 2560** | 1 | Real-time motor PWM driver and 16-sensor ultrasonic bank scanner. |
| **Chassis Motors** | **12V Non-Encoder Johnson DC Motors** | 4 | Heavy-duty drive motors for the 4WD skid-steer rolling base. |
| **Motor Drivers** | **BTS7960 43A High-Power H-Bridges** | 4 | Handles high motor current without burning out. (1 driver per motor). |
| **Obstacle Sensors** | **HC-SR04 Ultrasonic Distance Sensors** | 4 to 16 | Modular banks: start with 4 (1 per side), scale to 8, 12, or 16 without code edits. |
| **Face Screen** | **7-inch Touchscreen (1024x600)** | 1 | Displays the 60 FPS animated OLED robot face and subtitles. |
| **Camera** | **USB HD Webcam (720p or 1080p)** | 1 | DirectShow webcam for 30 FPS face-tracking and AI visual inspection. |
| **Audio In** | **USB Microphone** | 1 | Clean audio input for WebRTC VAD noise-gated voice recognition. |
| **Audio Out** | **Speaker (USB or 3.5mm Powered)** | 1 | Clear voice output for Edge-TTS speech replies. |
| **Power** | **12V High-Amperage Battery (3S LiPo/LiFePO4)** | 1 | Dedicated high-current power for 4x Johnson motors. |
| **Power Logic** | **5V 5A High-Current Step-Down Buck Converter**| 1 | Powers the Raspberry Pi 5 safely with common ground shared to Arduino. |

---

### 🚀 Step-by-Step Installation

#### 1. Clone or Download This Repository
```bash
git clone https://github.com/your-username/Project-Neurolis.git
cd Project-Neurolis
```

#### 2. Install Required Python Dependencies

* **On Windows PC (Testing)**:
  ```bash
  pip install -r requirements.txt
  ```

* **On Raspberry Pi 5 (Linux Terminal)**:
  ```bash
  # Install system audio, GUI, and OpenCV libraries
  sudo apt update && sudo apt install -y python3-pip python3-venv python3-tk portaudio19-dev libportaudio2 libasound2-dev libgl1-mesa-glx libglib2.0-0 alsa-utils

  # Create and activate a clean virtual environment
  python3 -m venv venv
  source venv/bin/activate

  # Install Python packages
  pip install -r requirements.txt
  ```

#### 3. Create Your `.env` File
Create a `.env` file in the project root to securely hold your Groq API key:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
```

#### 4. Upload Arduino Firmware
1. Open `arduino.ino` in the Arduino IDE.
2. Select **Tools → Board → Arduino Mega or Mega 2560**.
3. Select **Tools → Port → Your Arduino Mega COM / Serial Port**.
4. Click **Upload** (Arrow icon). That's it! You never need to touch the code again.

---

### 🧠 Main Code: Running the Robot Brain (`listen.py`)

`listen.py` is the **only master file you run** for full robot operation. It automatically launches the 60 FPS face UI, initializes vision tracking, and connects to the Arduino:

```bash
# Standard Launch (Auto-detects microphone; enters Voice Mode)
python listen.py

# Text-Only Mode (Bypasses microphone; ideal for noisy rooms or PC testing)
python listen.py --text
```

#### Interactive Terminal Controls:
* **In Voice Mode**: Press <kbd>Enter</kbd> to speak, type a message directly, or type `'t'` to switch to persistent Text Mode.
* **In Text Mode**: Type your questions or commands directly, type `'v'` to switch back to Voice Mode, or `'exit'` to cleanly quit.

---

### 🎮 Manual Control & Calibrator (`manual_control.py`)

Want to test, calibrate, or drive the robot manually before the Raspberry Pi arrives? Run our standalone cyber web cockpit:

```bash
python manual_control.py
```
Open your browser to **`http://localhost:5000`** (or browse to `http://<YOUR_PC_IP>:5000` from your phone on the same Wi-Fi!).

* **Keyboard Teleop**: <kbd>W</kbd> / <kbd>S</kbd> (Forward/Reverse), <kbd>A</kbd> / <kbd>D</kbd> (Steer), <kbd>Q</kbd> / <kbd>E</kbd> (Spin in place), <kbd>Space</kbd> (Emergency Brake).
* **Motor Polarity Calibrator (M1..M4)**: Pulse each wheel forward individually. If a wheel spins backwards, swap its wires on the driver before mounting!
* **16-Sensor Ultrasonic Radar HUD**: Real-time 2D chassis diagram displaying distance readings and safety zones.
* **Zero Dependencies**: Uses Python's standard library `http.server`.

---

### 🧪 Automated Safety Tests

Verify all 18 automated safety guardrails, emergency stop fast-paths, negation filters, and simulation fallbacks:

```bash
python -m unittest tests/test_safety.py
```

---

## 5. Features (In Simple Language)

* 🎨 **Apple-Grade OOBE Launch Sequence**: 
  When powered on, displays a sleek `"Hi there!"` greeting with smooth cosine fade, followed by a 14-point live cascading hardware probe checklist verifying every camera, mic, speaker, Arduino, motor driver, and ultrasonic sensor with zero fake numbers.
* 👁️ **60 FPS Animated OLED Robot Face**: 
  Minimalist cyber face (Vector & EMO inspired) with high-contrast emissive eyes on pure space black (`#040711`). Expresses **7 distinct emotional states**:
  * `IDLE`: Calm cyan glowing eyes with natural breathing pulse.
  * `HAPPY`: Emerald smiling crescents ($\cap \;\; \cap$) with vertical bounce.
  * `SAD`: Downcast sapphire eyes with an animated glowing teardrop trickling down the cheek.
  * `CONFUSED`: Hypnotic spinning cyber vortex spirals with orbital stars.
  * `THINKING`: Squinting eyes with spinning quantum data rings.
  * `SPEAKING`: Voice-reactive eye squash/stretch cadence with a 15-pin dynamic audio spectrum baseline.
  * `WATCHING`: Optical viewfinder reticle brackets with vertical laser scanner line.
  * `MOVING`: Front-facing humanoid robot rolling forward towards viewer with twin headlights.
* 💬 **Subtitle Card Telemetry**: 
  Real-time word-wrapped subtitles at the bottom of the screen showing `[YOU]` in mint green and `[NEUROLIS]` in cyan.
* 💔 **Feelings Hurt & Empathy Engine**: 
  If someone insults or is rude to the robot ("you are stupid", "shut up", "i hate you"), Neurolis immediately shows its sad face with a falling teardrop and expresses its hurt feelings. Apologizing ("sorry", "you're good") heals the robot into a relieved happy expression with cyber blush!
* 🚶 **Intelligent Person Following (`FOLLOW`)**: 
  Uses local deep-learning YuNet face detection at 30+ FPS to smoothly steer and track the user as they walk around the room.
* 🛑 **Smart Negation & Emergency Stop**: 
  Understands phrases like *"stop following me"* or *"don't move"* without false-triggering the follow mode. Hard stop triggers in 0ms.
* 🔍 **On-Demand Visual Question Answering**: 
  Ask *"What am I holding?"* or *"Look at this"*, and Neurolis captures a single camera frame to answer with Groq Vision without wasting tokens on continuous streaming.

---

## 6. Hardware Pinout Reference (Arduino Mega 2560)

### 🏎️ Motors (4x BTS7960 Drivers to 12V Non-Encoder Johnson Motors)

| Motor | Wheel Position | RPWM (Fwd) | LPWM (Rev) | EN (Enable) |
| :---: | :---: | :---: | :---: | :---: |
| **M1** | Front-Left | **Pin 2** | **Pin 3** | **Pin 26** |
| **M2** | Rear-Left | **Pin 4** | **Pin 5** | **Pin 27** |
| **M3** | Front-Right | **Pin 6** | **Pin 7** | **Pin 28** |
| **M4** | Rear-Right | **Pin 8** | **Pin 9** | **Pin 29** |

*(Driver EN pins default to LOW on boot to prevent power-on jerks).*

---

### 📡 Ultrasonic Sensors (16-Sensor Scalable God-Tier Bank Architecture)

| Bank | Sensor Label | Side | Trig Pin | Echo Pin | Coverage Level |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **Bank 1** | `FRONT_1` | Front | **Pin 30** | **Pin 31** | **Base 4 Sensors** |
| **Bank 1** | `LEFT_1`  | Left  | **Pin 32** | **Pin 33** | *(1 on each side)* |
| **Bank 1** | `RIGHT_1` | Right | **Pin 34** | **Pin 35** | |
| **Bank 1** | `REAR_1`  | Rear  | **Pin 36** | **Pin 37** | |
| **Bank 2** | `FRONT_2` | Front | **Pin 38** | **Pin 39** | **Expanded 8 Sensors** |
| **Bank 2** | `LEFT_2`  | Left  | **Pin 40** | **Pin 41** | *(Corner & Perimeter)* |
| **Bank 2** | `RIGHT_2` | Right | **Pin 42** | **Pin 43** | |
| **Bank 2** | `REAR_2`  | Rear  | **Pin 44** | **Pin 45** | |
| **Bank 3** | `FRONT_3` | Front | **Pin 46** | **Pin 47** | **Expanded 12 Sensors** |
| **Bank 3** | `LEFT_3`  | Left  | **Pin 48** | **Pin 49** | *(Wide-Angle Flanking)* |
| **Bank 3** | `RIGHT_3` | Right | **Pin 50** | **Pin 51** | |
| **Bank 3** | `REAR_3`  | Rear  | **Pin 52** | **Pin 53** | |
| **Bank 4** | `FRONT_4` | Front | **Pin 54 (A0)** | **Pin 55 (A1)** | **Full 16 Sensors** |
| **Bank 4** | `LEFT_4`  | Left  | **Pin 56 (A2)** | **Pin 57 (A3)** | *(God-Tier 360° Array)* |
| **Bank 4** | `RIGHT_4` | Right | **Pin 58 (A4)** | **Pin 59 (A5)** | |
| **Bank 4** | `REAR_4`  | Rear  | **Pin 60 (A6)** | **Pin 61 (A7)** | |

**Serial Baud Rate**: `115200` baud.

---

<div align="center">

### Built with ❤️ for Project Neurolis
*Exhibition-grade intelligence, bulletproof safety, and seamless hardware scalability.*

</div>
