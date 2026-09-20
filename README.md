# AI Humanoid 4 Wheel Chassis - Software architecture and entire ready to use code, for anyone who wants to implement my pipeline for their humanoid AI robot project.

( ONLY made for FOUR WHEEL POWERED chassis, can be changed to support two motors. )

(NOTE: YOU DO NOT NEED MOTORS, DRIVERS, SENSORS FOR TESTING THE PROGRAM, GUARDRAILS HAVE BEEN ADDED TO MAKE SURE THE SIMULATION STILL RUNS OR SKIPS IT ENTIRELY IF CERTAIN REQUIRED HARDWARE IS NOT CONNECTED, ONCE CONNECTED, THE PROGRAM KICKS IN THE TASK IT'S SUPPOSED TO DO ON THAT HARDWARE )

Project Neurolis is an end-to-end software and hardware pipeline designed to build an interactive, humanoid robot for minor projects. It integrates voice conversation using Groq's API, you may use other APIs provided it is multimodal, an expressive animated face UI, local computer vision for person tracking and interaction, and an Arduino-controlled 4WD skid-steer mobility platform[cite: 9, 12, 14, 15].

The pipeline uses distributed roles[cite: 10, 15]:
- High-level intelligence (voice processing, UI rendering, vision tracking) runs on the main computer or a Raspberry Pi 5[cite: 10, 15].
- Low-level motor driving, ultrasonic obstacle detection, and physical fail-safes run on an Arduino Mega 2560[cite: 9, 10].

---

## Core Components

- `listen.py`: Master controller. Manages audio streaming, voice activity detection (WebRTC VAD), speech-to-text via Groq Whisper, conversation logic via Groq LLM, speech synthesis via Edge-TTS, and motor intent routing[cite: 11, 15].
- `screen.py`: 60 FPS animated OLED-style face UI designed for 1024x600 displays ( Made for Pi Display 7 Inch )[cite: 14, 15]. Renders dynamic eye expressions, conversational cadence, and live subtitles[cite: 14, 15].
- `motors.py`: Real-time edge vision engine using OpenCV YuNet face detection for person tracking and serial bridge to the Arduino Mega[cite: 12, 15].
- `arduino.ino`: C++ firmware for the Arduino Mega 2560[cite: 9, 15]. Drives 4x BTS7960 motor controllers, reads dual HC-SR04 ultrasonic sensors, and enforces a hardware-level safety stop[cite: 9, 15].

---

## Hardware Pin Mapping (Arduino Mega 2560)

CHANGE AS PER YOUR SETUP.

### Motors (4x BTS7960 Drivers to 12V Non-Encoder Johnson Motors)
- Front-Left: RPWM = 2, LPWM = 3, EN = 26
- Rear-Left: RPWM = 4, LPWM = 5, EN = 27
- Front-Right: RPWM = 6, LPWM = 7, EN = 28
- Rear-Right: RPWM = 8, LPWM = 9, EN = 29
*(Motor driver enable pins default to LOW during boot to prevent power-up jerk)*

### Ultrasonic Sensors (16-Sensor Scalable God-Tier Bank Architecture)
The firmware is pre-configured for up to 16 sensors across 4 banks and auto-detects connected sensors at boot (supports 4, 8, 12, or 16 plugged in without touching code):
- **Bank 1 (Base 4 Sensors - 1 per side)**:
  * Front 1: Trig = Pin 30, Echo = Pin 31
  * Left 1:  Trig = Pin 32, Echo = Pin 33
  * Right 1: Trig = Pin 34, Echo = Pin 35
  * Rear 1:  Trig = Pin 36, Echo = Pin 37
- **Bank 2 (Expanded to 8 Sensors - 2 per side)**:
  * Front 2: Trig = Pin 38, Echo = Pin 39
  * Left 2:  Trig = Pin 40, Echo = Pin 41
  * Right 2: Trig = Pin 42, Echo = Pin 43
  * Rear 2:  Trig = Pin 44, Echo = Pin 45
- **Bank 3 (Expanded to 12 Sensors - 3 per side)**:
  * Front 3: Trig = Pin 46, Echo = Pin 47
  * Left 3:  Trig = Pin 48, Echo = Pin 49
  * Right 3: Trig = Pin 50, Echo = Pin 51
  * Rear 3:  Trig = Pin 52, Echo = Pin 53
- **Bank 4 (Expanded to 16 Sensors - 4 per side)**:
  * Front 4: Trig = Pin 54 (A0), Echo = Pin 55 (A1)
  * Left 4:  Trig = Pin 56 (A2), Echo = Pin 57 (A3)
  * Right 4: Trig = Pin 58 (A4), Echo = Pin 59 (A5)
  * Rear 4:  Trig = Pin 60 (A6), Echo = Pin 61 (A7)

Serial Baud Rate: `115200`

---

## Zero-Hardware Simulation Mode (Testing on PC)

You **DO NOT** need any motors, drivers, sensors, microphone, or Arduino connected to test Neurolis!
- Launch with: `python listen.py` (or `python listen.py --text` for text-only mode).
- The system automatically detects missing hardware and launches in **Zero-Hardware Simulation Mode**.
- You can converse with Neurolis, test facial animations on the 7-inch UI, test computer vision, and trigger virtual 4WD obstacle-avoiding physics directly in your terminal.

---

## Setup Instructions

### 1. Raspberry Pi 5 Quickstart (Run in Pi Terminal)

If you are deploying to a Raspberry Pi 5 running Raspberry Pi OS (Debian Bookworm):

```bash
# A. Install system audio, GUI, and OpenCV libraries
sudo apt update && sudo apt install -y python3-pip python3-venv python3-tk portaudio19-dev libportaudio2 libasound2-dev libgl1-mesa-glx libglib2.0-0 alsa-utils

# B. Create and activate a clean virtual environment
python3 -m venv venv
source venv/bin/activate

# C. Install Python packages
pip install -r requirements.txt
```

*(On Windows or macOS development PCs, simply run `pip install -r requirements.txt`)*

---

## 2. Customize System Prompt for Project Personalization

Open `listen.py` in an editor and navigate to the `SYSTEM_PROMPT` configuration. Customize the prompt with your robot's name, role, school or creator information, and any domain-specific rules you want the robot to follow.

```python
SYSTEM_PROMPT = (
    "You are [Robot Name], a humanoid robot prototype built for [Your Project]. "
    "Keep responses conversational, concise, and factual. or whatever u want it to do.... :) "
    "..."
)
```

You can also customize the text-to-speech voice used by the robot by changing the `EDGE_TTS_VOICE` value in `listen.py`. For example:

access voices here: [Edge TTS Voices](https://tts.travisvn.com/)

```python
EDGE_TTS_VOICE = "en-US-GuyNeural"
```

or:

```python
EDGE_TTS_VOICE = "en-US-AriaNeural"
```

---

## 3. Create `.env` File

Create a file named `.env` in the folder where u saved all programs. This file is used to securely store your API key without putting it directly into the Python source code.

```env
GROQ_API_KEY=your key here
```

## 4. Upload Arduino Firmware

Open `arduino.ino` in the Arduino IDE.

Under **Tools → Board**, select **Arduino Mega or Mega 2560**. Then, under **Tools → Port**, select the active COM/Serial port for your Arduino Mega.

Once the correct board and port are selected, connect the Arduino to your computer and click **Upload**.

Make sure the pin assignments in `arduino.ino` match your actual wiring before connecting or powering the motors. We don't want fireworks :)

---

## Running the Robot

To launch the complete Neurolis pipeline, including voice conversation, the animated face UI, vision tracking, and motor control, run: 

this automatically calls motors.py / screen.py, just keep em all in ONE place... 

```bash
python listen.py
```

---

## Running Automated Safety Tests

To run the automated safety test suite (negation guards, emergency stop, PWM clamping, 4-sensor obstacle avoidance, and action parsing):

```bash
python tests/test_safety.py
```

THANKS FOR VIEWING !!! ;)

