# Welcome to my first Project, for anyone who wants to implement my pipeline for their humanoid AI robot project.

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

### Motors (4x BTS7960 Drivers to 12V Johnson Motors)
- Front-Left: RPWM = 2, LPWM = 3, EN = 26
- Rear-Left: RPWM = 4, LPWM = 5, EN = 27
- Front-Right: RPWM = 6, LPWM = 7, EN = 28
- Rear-Right: RPWM = 8, LPWM = 9, EN = 29[cite: 9]

### Ultrasonic Sensors (HC-SR04 Bumper)
- Left Sensor: Trigger = Pin 30, Echo = Pin 31[cite: 9]
- Right Sensor: Trigger = Pin 32, Echo = Pin 33[cite: 9]

Serial Baud Rate: `115200`[cite: 9]

---

## Prerequisites

1. Python 3.12 (recommended for audio package compatibility).
2. Arduino IDE (to flash the microcontroller).
3. A USB webcam and an audio input/output device.
4. An active Groq API key (available at console.groq.com).
5. Pip libraries

---

## Setup Instructions

### 1. Install Dependencies

CRUCIAL!!!

Clone the repository and install the required Python packages:

```bash
git clone [https://github.com/YOUR-USERNAME/Project-Neurolis.git](https://github.com/YOUR-USERNAME/Project-Neurolis.git)
cd Project-Neurolis
pip install groq edge-tts opencv-python sounddevice soundfile numpy pyserial webrtcvad python-dotenv
```

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

THANKS FOR VIEWING !!! ;)
