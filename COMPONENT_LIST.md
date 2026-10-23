# Project Neurolis Component List

Last updated: 2026-10-18

This file tracks the hardware and physical inventory for Project Neurolis.

Project Context:
- Developed by Swapnil Jai Chauhan (Sole Architect & Developer, Neurolis Mark II; Mark 1 prototype chassis contributed by Shivam Verma) at Auckland House School for Boys.
- Build Version: Neurolis Mark II Software Development Phase (Windows 11 Workstation & Raspberry Pi 5 Verification).
- NOTE: Sections 1 (Arduino Mega) and 3 (drive and power system) list PLANNED mid-2027 hardware; none of it is connected or driven by the current software.
- The codebase is currently in a 100% software-first architecture. Physical motor drivers, BTS7960 H-bridges, 12V Johnson DC motors, and 2D LiDAR SLAM locomotion will be developed in mid-2027.

======================================================================
1. MAIN COMPUTE AND CONTROL
======================================================================

1. Raspberry Pi 5, 4GB/8GB RAM
   Quantity: 1
   Role:
   - Master high-level brain.
   - Runs Python 3.13, MediaPipe gesture sentry, audio endpointer v2, Groq LLM brain, Cartesia Sonic-3 voice engine (Edge-TTS/Piper/pyttsx3 fallbacks), and 60 FPS Face UI.
   Notes:
   - Uses active cooling fan/heatsink to ensure continuous operation across exhibition hours.
   - Powered via high-current 5V 5A step-down buck converter.

2. Arduino Mega 2560
   Quantity: 1
   Role:
   - Dedicated chassis and motor driver interface.
   - Receives wireless RF/RC teleoperation signals from the student operator's remote controller.
   - Directly drives 4x BTS7960 motor driver modules.
   Notes:
   - Isolated from high-level AI brain to prevent software crashes from affecting motor safety.

3. MicroSD Card (High Endurance 32GB/64GB)
   Quantity: 1
   Role:
   - OS and software storage for Raspberry Pi 5.

4. Raspberry Pi Active Cooler
   Quantity: 1
   Role:
   - Thermal regulation for continuous exhibition runtime.

======================================================================
2. VISION, DISPLAY, AND AUDIO INTERACTION
======================================================================

1. 7-inch Display (1024x600 HDMI/DSI)
   Quantity: 1
   Role:
   - Dedicated 60 FPS animated OLED robot face monitor and subtitle screen.
   - Displays real-time MediaPipe gesture HUD progress bar above subtitles.
   Notes:
   - Touch digitizer was broken during assembly. Touch interaction has been completely removed in software.
   - All wake/standby control is handled hands-free via MediaPipe camera gestures.

2. USB HD Webcam (720p / 1080p)
   Quantity: 1 (Stationed on /dev/video0)
   Role:
   - Continuous Vision Sentry: Downscaled 320x240 frames processed by MediaPipe Tasks Gesture Recognizer in background thread (~15 FPS).
     * ✋ Open Palm (held 3s): Wakes robot from Standby into active conversation.
     * ✊ Closed Fist (held 3s): Forces active robot into Standby mode.
   - On-Demand AI Vision: When user asks visual questions ("What am I holding?", "Look at this"), captures a single frame for Groq Vision analysis.

3. Microphone (USB Mic / Phone Mic over ADB PipeWire)
   Quantity: 1
   Role:
   - High-fidelity 16kHz mono audio input.
   - Connected to Endpointer v2 and WebRTC VAD Level 2 for dynamic ambient noise floor tracking in noisy exhibition halls.

4. Powered Speaker (USB / Bluetooth A2DP / 3.5mm Powered)
   Quantity: 1
   Role:
   - Clean audio output for Cartesia Sonic-3 neural speech (with Edge-TTS and Piper offline fallbacks).

======================================================================
3. DRIVE AND POWER SYSTEM
======================================================================

1. DC 12V 100RPM Johnson DC Motors (No Encoders)
   Quantity: 4
   Role:
   - 4-Wheel Drive (4WD) skid-steer chassis (2 Left motors, 2 Right motors).
   - Manually driven via remote control teleoperation.

2. BTS7960 43A High-Power H-Bridge Motor Drivers
   Quantity: 4
   Role:
   - High-current motor drivers (1 driver per Johnson DC motor) capable of handling heavy chassis loads without overheating.

3. Heavy-Duty 4WD Aluminum Chassis & Wheels
   Quantity: 1 chassis, 4 wheels
   Role:
   - Physical platform carrying the humanoid torso, display, battery, and compute.

4. Wireless Teleoperation Remote & Receiver
   Quantity: 1 pair
   Role:
   - Manual driver controls operated by student team during demonstrations.

5. 12V High-Amperage Battery Pack
   Quantity: 1
   Role:
   - Dedicated high-current power for 4x Johnson motors and BTS7960 drivers.

6. 5V 5A High-Current Step-Down Buck Converter
   Quantity: 1
   Role:
   - Steps 12V battery power down to clean 5V to power the Raspberry Pi 5 safely with common ground.
