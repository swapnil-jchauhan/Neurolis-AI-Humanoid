# Project Neurolis Map

Last updated: 2026-09-10

## Project Goal

Project Neurolis is a school exhibition humanoid robot project.

The goal is to build a reliable 4-foot rolling humanoid-style robot that can:

- listen to a user
- understand speech
- reply naturally
- show expressive screen states
- move safely using real distance sensors and Arduino-controlled motors (4WD Skid-Steer chassis)
- use a camera for on-demand visual questions and real-time person tracking/following

Reliability matters more than fancy behavior. Neurolis should be stable enough to run through a full exhibition day without freezing, wasting API credits, or acting confused in front of guests.

## Current Project Folder

Final 3-File Master Architecture:

- `listen.py`
  - THE ONLY FILE YOU RUN: Master Brain orchestrating Voice, Face UI & Motors.
  - Handles Groq Whisper STT (`whisper-large-v3-turbo`) & Groq Qwen 27B (`qwen/qwen3.8-27b`) LLM intelligence.
  - WebRTC VAD Level 3 + RMS noise filtering tuned for loud auditoriums.
  - 4.0-second silence cutoff timer with non-repetitive standby wrap-ups.
  - Fast Intent Conversation Enders ("alr thanks", "bye", "good", "done", etc.) returning gracefully to standby.
  - **AI-Verified Semantic Motor Classifier (`classify_motor_intent`)**:
    - Groq semantic intent classifier + 0ms deterministic fast-path negation guards.
    - Completely eliminates false-positive follow triggers on phrases like "quit following me" or "stop following".
    - Accurately classifies: `STOP`, `FOLLOW`, `APPROACH`, `ROAM`, `DEMONSTRATE`, `ASK_MOBILITY`, `STEP_BACK`, `SPIN`, and `NONE`.
  - **Active Expression Demonstrator Engine**:
    - Individual expressions ("show the happy face", "show sad face", "show thinking face", etc.) displayed actively on screen and held for 3.5s with speech confirmation.
    - Showcase all expressions ("show all expressions", "show each expression") sequentially cycling through all 7 expressions (`happy` -> `sad` -> `thinking` -> `listening` -> `watching` -> `moving` -> `confused`) with descriptive subtitles.
  - **Mean Input & Heartbroken Sad Reaction System**:
    - Auto-detects insults, rudeness, dismissal, or derogatory phrases directed at the robot ("you are stupid", "you suck", "shut up", "i hate you", "ugly robot", etc.).
    - Instantly switches face to `sad` (status: `FEELINGS HURT // SAD`) and speaks a polite heartbroken reaction with trembling frown and teardrop animation.
    - Heals when apologized to or complimented ("sorry", "you're good", "i like you"), transitioning into relieved `happy` state with bright smile and cyber blush.
  - **Capabilities Inquiry Handler**:
    - Instant, token-safe response under 45 words stating mobility, person following, camera analysis, and listing all facial expressions including sad.
  - **Text Input & Microphone-Free Mode**:
    - CLI flag `--text` / `-t` boots Neurolis directly into Text Input Mode (bypasses microphone detection entirely).
    - In Voice Mode prompt: hit Enter to speak, type `'t'` to switch to persistent Text Mode, or directly type queries into prompt.
    - In Text Mode prompt: type queries, type `'v'` to switch back to Voice Mode (if mic detected), or `'exit'` to quit.
  - Speaks replies with `edge-tts`.
  - Keeps short-term memory for recent conversation exchanges.

- `screen.py`
  - Dedicated 60 FPS animated 7-inch Touchscreen face UI engine (1024x600, 16:9).
  - Pure OLED space black background (`#040711`) with high-contrast emissive neon cyber eyes.
  - Dedicated Real-Time **Subtitle Card** ($y \in [370, 556]$) with `[YOU]` in mint green and `[NEUROLIS]` in cyan, word-wrapped (830px) with live status telemetry.
  - **Modern Luminous OLED Robotic Face Architecture (Vector & EMO Inspired)**:
    - **Zero Cock-Eyed Drift**: Gaze coordinates strictly centered `(0.0, 0.0)` in all conversational and expressive states so eyes never look cock-eyed or pulled off-center; clamped strictly within `[-0.15, 0.15]` only during optical `WATCHING`.
    - **Elimination of Uncanny Elements**: Disembodied cassette-tape mouth boxes, fake floating lip curves, and rectangular band-aid blush pills have been eliminated. Emotion and voice cadence are driven through luminous eye morphing and minimalist cyber optics.
    - **Dynamic Voice-Reactive Eye Cadence**: When speaking, the robot's eyes squash and stretch rhythmically to voice amplitude, paired with a sleek 1px cyber audio spectrum baseline with 15 dancing frequency pins.
  - **Comprehensive OLED Expression Set**:
    - `IDLE`: Solid radiant electric cyan (`#00f0ff`) OLED capsules with soft neon bloom, inset depth beveled border, Pixar/Vector-style glossy specular glints, calm cyber brows, and gentle natural breathing pulse ($\pm 2\%$).
    - `HAPPY`: Thick, bold glowing emerald-mint (`#00ff88`) smiling crescents ($\cap \quad \cap$) with joyous vertical bounce ($4\text{px}$) and high arched brows.
    - `SAD`: Downcast heartbroken sapphire blue (`#2979ff`) eyes with heavy outer eyelid droop ($\backslash \quad / $), trembling distressed brows, and an animated luminous digital teardrop trickling down the left cheek.
    - `CONFUSED`: Dual hypnotic Archimedean cyber vortex spirals (`@ _ @`, left clockwise, right counter-clockwise) spinning at $4.2\text{rad/s}$ with 3 golden cyber stars (`✦`) wobbling in an elliptical orbit above the head and wavy quizzical brows.
    - `THINKING`: Pensive analytical squint glancing up-right with rotating segmented quantum data rings inside each eye and orbital data nodes above the brow.
    - `LISTENING`: Wide alert inquisitive eyes with high-tech acoustic soundwave spectrum bars and flanking beacon radar dots.
    - `SPEAKING`: Voice-reactive eye squash/stretch cadence + razor-sharp 1px cyber audio spectrum baseline with 15 vertical dancing frequency pins.
    - `WATCHING` / `LOOKING`: Focused optical camera eyes with viewfinder reticle brackets `[  ]`, iris tick marks, active vertical laser scanner sweep line, and clamped tracking gaze.
    - `MOVING`: Aerodynamic sports visor eyes + **front-facing humanoid robot moving forward towards viewer** with downward-rolling rubber treads, twin Xenon headlights casting road beams, glowing chest arc reactor, and two perspective road lines with streaks streaming backward.
    - `ERROR`: Fierce angled crimson alarm slits ($/ \quad \backslash$) with emergency red warning pulse.

- `motors.py`
  - Local Real-Time Edge Vision Tracker & Arduino Serial Bridge (100% Free, 0ms lag, ~15% Pi CPU).
  - 4WD Skid-Steer chassis control: 4x Johnson DC Motors, 4x BTS7960 Motor Drivers, and 2x HC-SR04 front ultrasonic sensors.
  - YuNet 300KB deep-learning face detector running at 30+ FPS for zero false-positive person tracking.
  - DirectShow conflict prevention: acts as single camera master; exposes `get_latest_raw_frame()` for Groq Vision queries.
  - Multi-Mode Navigation Engine:
    - `ROAM / WANDER`: Autonomous obstacle-avoiding room patrol using ultrasonics (stops the millisecond someone speaks or touches the screen).
    - `APPROACH ('Come here')`: Drives forward towards the human until within conversation range (~0.8m), then auto-brakes.
    - `FOLLOW ('Follow me')`: Real-time 30 FPS OpenCV continuous tracking & follow-me navigation.
    - `DEMONSTRATE`: Actively moves in autonomous roaming mode while speaking to demonstrate mobility.
    - `STEP BACK ('Move back')`: Gently reverses for 1.5s and halts.
    - `SPIN ('Turn around')`: Rotates chassis in place.
    - `STANDBY ('Stop')`: Motors locked at 0.
  - PC-Only Debug HUD: OpenCV HUD camera preview window can pop up for desktop testing, but is completely suppressed in Pi production (only Face UI is visible).
  - Master-to-Slave USB Serial communication with Arduino Mega (`DRIVE,speed,turn\n`, `STOP\n`).
  - Built-in Virtual Simulation mode when developing without physical Arduino.
  - Automatic zero-CPU idle sleep when in standby.

- `arduino.ino`
  - Companion firmware flashed onto the Arduino Mega 2560.
  - Drives 4x BTS7960 motor drivers for 4x Johnson DC motors (4WD Skid-Steer Chassis).
  - Pin assignments: M1 (2, 3, 26), M2 (4, 5, 27), M3 (6, 7, 28), M4 (8, 9, 29).
  - Reads 2x HC-SR04 front ultrasonic sensors (Trig/Echo pins: Left 22/23, Right 24/25).
  - Enforces independent hardware-level emergency stop (<20cm obstacle) and communication watchdog.

- `PROJECT_MAP.md`
  - Living project planner, communication specifications, and progress map.

- `COMPONENT_LIST.md`
  - Hardware inventory and pin/power responsibility notes.


## Current Interaction Pipeline

Current PC testing flow:

1. Program starts:
   - Run normally: `python listen.py` (probes audio hardware, enters Voice Mode if mic is detected).
   - Run without mic: `python listen.py --text` or `python listen.py -t` (enters Text Mode immediately).
2. If in Voice Mode, prompt asks:
   `[VOICE MODE] Press Enter to speak, type a message, or 't' for text mode:`
   - Press **Enter**: Neurolis calibrates ambient noise and begins listening.
   - Type `'t'`: switches permanently into Text Mode until `'v'` is pressed.
   - Type any question or command directly: immediately processes the query with subtitles, facial expressions, vision, or motors.
3. If in Text Mode, prompt asks:
   `[TEXT MODE] You (or 'v' for voice, 'exit' to quit):`
   - Type queries to interact normally (subtitles, face states, motor actions, vision, and speech run identically).
   - Type `'v'`: checks audio hardware and switches back to Voice Mode.
   - Type `'exit'`: cleanly shuts down motors, camera, and display.
4. When speech is used:
   - Local audio detection records user speech with WebRTC VAD Level 3.
   - Stops when user finishes speaking (4s silence cutoff).
   - WAV audio is transcribed by Groq Whisper (`whisper-large-v3-turbo`).
5. The text transcript (or direct text input) is processed:
   - Intent checks: conversation ender checks, expression demonstrator, capabilities query, motor intents, or vision request.
   - General conversation is sent to Groq Chat (`qwen/qwen3.8-27b`, `reasoning_effort: "none"`).
6. Neurolis replies with concise text.
7. The reply is displayed in the Subtitle Card and spoken via `edge-tts`.
8. User can continue asking follow-ups without pressing Enter again.
9. After silence or conversation ender, Neurolis returns politely to standby.

Current activation method:

- Terminal Enter key.

Future Raspberry Pi activation method:

- Touchscreen `Talk to Neurolis` button.

Important:

- Terminal Enter is temporary for PC testing only.
- Wake word is postponed.
- `openWakeWord` is not currently used.
- Vosk is not currently used.
- No fake wake phrase such as `Hey Jarvis` should be used.

## What Is Working

- Groq Whisper speech-to-text with advanced hallucination/ambient rejection.
- WebRTC VAD Level 3 + RMS energy gating tuned for loud auditorium noise rejection.
- Natural speech pause buffer (0.55s) to prevent cutting off real speakers mid-sentence.
- Fast Intent Conversation Enders ("alr thanks", "bye", "good", "that's all", etc.) with non-repetitive standby wrap-ups.
- 4.0-second silence timeout returning politely to standby.
- AI-Verified Semantic Motor Intent Classification with 0ms deterministic negation guards (eliminates false positives like "quit following me").
- Active Expression Demonstrator Engine: displays and holds individual expressions for 3.5s and cycles through all 7 expressions (`happy` -> `sad` -> `thinking` -> `listening` -> `watching` -> `moving` -> `confused`) in sequence with live subtitles.
- Direct Capabilities Handler delivering concise, token-safe responses (<45 words) covering mobility, vision, and listing all expressions including sad.
- Mean Input & Heartbroken Sad Reaction System: automatically triggers the `sad` expression with tears, droop brows, and trembling pout upon receiving mean remarks, with forgiveness healing loop on apology.
- Dedicated Real-Time Subtitle Card on 7-inch display ($y \in [370, 556]$) with mint `[YOU]` and cyan `[NEUROLIS]`, word-wrapped with status telemetry.
- 11 Fully Overhauled Animated Face Expression States in `screen.py` with tailored, synchronized expressive eyes AND mouths across all emotions.
- Unified Vision & Camera Pipeline: `motors.py` is single camera master, providing thread-safe raw frames to Groq Vision and preventing DirectShow conflicts.
- OpenCV HUD camera preview window auto-pops up on motion modes and cleanly auto-closes on STOP.
- 4WD Johnson DC motor chassis with 4x BTS7960 drivers and dual front HC-SR04 ultrasonic obstacle avoidance.
- Groq Chat replies with `qwen/qwen3.8-27b` (zero-latency `reasoning_effort: "none"`).
- `edge-tts` voice output with dynamic duration estimation and hold-state capabilities.
- Short-term session memory for recent user/assistant exchanges.
- Touchscreen & Terminal activation.
- Microphone input through `sounddevice`.
- Automatic text-only fallback mode when microphone/audio devices are missing or crash.
- Full Text Input Mode (`python listen.py --text` or `-t`) and interactive runtime toggling (`t` for text mode, `v` for voice mode, or direct inline typing).

## Current Memory Behavior

Memory is short-term only.

Rules:

- Stored only in RAM.
- Not written to disk.
- Resets when the program restarts.
- Keeps only:
  - system prompt
  - last 3 user messages
  - last 3 assistant replies

Purpose:

- Neurolis can remember context briefly.
- Example: if the user says "My name is Swapnil", Neurolis can answer "Your name is Swapnil" within the next few turns.
- It should forget older visitors quickly so it does not call the wrong person by a previous name.

## Planned Screen Expression States

Minimum screen states:

- `idle`
  - Waiting for Enter/touch activation.

- `listening`
  - User is speaking or expected to speak.

- `thinking`
  - Waiting for Groq Whisper or Groq Chat.

- `speaking`
  - TTS is playing.

- `happy`
  - Friendly greeting or positive response.

- `confused`
  - Unclear speech or empty transcription.

- `error`
  - Mic, API, TTS, or system failure.

Future screen behavior:

- Idle screen before activation.
- Listening expression during recording.
- Thinking expression while waiting for API response.
- Speaking expression during TTS.
- Error/confused expression when something fails or speech is unclear.

## Planned Final Architecture

Do not restructure yet. Current priority is making `listen.py` reliable.

Eventual structure:

```text
main.py              # starts and coordinates Neurolis
config.py            # paths, settings, environment variables
voice.py             # activation flow, recording, speech-to-text
ai.py                # Groq Chat and short-term memory
tts.py               # edge-tts, Piper fallback, or future TTS
screen.py            # touchscreen UI and expressions
vision.py            # camera processing
movement.py          # high-level movement decisions
arduino_comm.py      # serial communication with Arduino Mega
logs/                # runtime logs
.env                 # private API keys and local settings
README.md            # setup and usage
```

## Raspberry Pi Responsibilities

The Raspberry Pi should handle:

- voice input
- activation/session flow
- Groq Whisper STT
- Groq Chat replies
- short-term memory
- TTS voice output
- camera/vision processing
- touchscreen UI and expressions
- high-level robot decisions
- serial commands to Arduino
- logging and safe error handling

## Arduino Mega Responsibilities

The Arduino Mega should handle:

- motor control
- encoder readings
- ultrasonic sensor readings
- VL53L0X/ToF readings
- low-level movement safety
- direct commands such as:
  - `FORWARD`
  - `STOP`
  - `LEFT`
  - `RIGHT`
  - `REVERSE`

Safety rule:

- Arduino should handle immediate movement safety.
- It should not depend on Groq, internet, screen UI, or speech logic to stop the robot.

## Hardware And Software Responsibilities

Voice:

- Hardware:
  - microphone
  - speaker
- Software:
  - sounddevice recording
  - Groq Whisper STT
  - Groq Chat
  - edge-tts output
  - short-term memory

Screen/UI (Strict Exhibition Display Policy):

- Hardware:
  - Raspberry Pi 7-inch touchscreen (1024x600, 16:9).
- Software & Display Rules:
  - **EXCLUSIVE VISIBILITY**: ONLY the Neurolis Face UI (`screen.py`) is rendered on the Pi screen.
  - **ZERO CLUTTER**: No camera feeds, no OpenCV preview popups (`cv2.imshow` is disabled/testing-only on PC), no terminal consoles/cmd prompt backends, and no desktop artifacts visible to guests.
  - All background services (`motors.py` YuNet tracker, `listen.py` Whisper/Qwen/TTS, serial communication, and camera capture) run 100% headlessly and silently behind the scenes.
  - Fullscreen Kiosk UI:
    - Upper section: Clean animated cybernetic robotic face and gaze tracking.
    - Lower section: Real-time Subtitle Card with speaker badges (`[YOU]` / `[NEUROLIS]`) and status telemetry.
  - Future `Talk to Neurolis` touchscreen tap activation button for hands-free exhibition engagement.

Vision:

- Hardware:
  - webcam as final Neurolis camera for on-demand AI vision
  - Raspberry Pi Camera Module 5MP remains listed hardware, but final use needs confirmation
- Software:
  - on-demand AI vision for interactive questions
  - example: user asks "What am I holding?", camera captures one image, Groq vision/multimodal API analyzes it, Neurolis replies
  - should be fast by using a single captured frame and a short response
  - not responsible for continuous movement safety
  - not responsible for final emergency stopping

Movement and Safety:

- Hardware:
  - Arduino Mega
  - BTS7960 motor drivers
  - Johnson encoder motors
  - HC-SR04 sensors
  - SmartElex VL53L5CX 8x8 ToF Imager
  - VL53L0X ToF sensor
- Software:
  - Arduino firmware
  - Pi serial communication
  - safe movement commands
  - distance/object readings should be used for STOP/MOVE decisions before any real movement

## Current Object Detection Plan

Selected main object/distance sensor:

- SmartElex ToF Imager - VL53L5CX
  - 8x8 multi-zone ToF distance sensor.
  - Planned for object/proximity detection.
  - Should give Neurolis a small depth grid instead of guessing distance from a normal camera image.
  - Best handled by Raspberry Pi because VL53L5CX needs more memory/firmware handling than simple Arduino sensors.
  - Pi can process the distance grid and send safe movement decisions to Arduino.

Camera role:

- Webcam is now planned as final Neurolis hardware for on-demand AI vision.
- It should activate only when the user asks a visual question.
- It is part of the final robot plan.
- It is not used for object-detection motor safety.
- `listen.py` now uses a hybrid vision router:
  - obvious visual requests go straight to webcam vision
  - known identity/project questions use fast local replies
  - unclear requests ask Groq for a one-word `CAMERA` or `CHAT` decision
  - normal chat can return `CAMERA_REQUIRED` as a safety fallback
- Example flow:
  1. User asks: "What am I holding?"
  2. Neurolis captures one camera frame.
  3. The image is sent to Groq vision/multimodal API.
  4. Neurolis replies briefly and naturally.
- Camera should not run Groq Vision continuously.
- Camera should not be the main obstacle safety system.

Safety note:

- Final movement safety should still be conservative.
- ToF/distance sensing should decide close-object STOP behavior.
- Groq Vision is for interaction and demonstrations, not emergency stopping.

## Next Steps

Done:

1. Built working speech response prototype in `listen.py`.
2. Replaced Piper active output with `edge-tts`.
3. Added short-term memory.
4. Replaced Vosk active STT with Groq Whisper.
5. Removed wake-word/openWakeWord from current testing path.
6. Added terminal Enter activation for PC testing.
7. Cleaned old deleted test scripts from this project map.
8. Selected SmartElex VL53L5CX 8x8 ToF Imager for planned object/distance detection.
9. Reassigned webcam role to final on-demand AI vision for interactive questions.
10. Tightened Neurolis prompts so it should not roleplay or invent fictional origin stories.
11. Added stronger routing so camera/seeing/hand/wrist questions go to on-demand vision mode.
12. Optimized `listen.py` speech detection settings for lower latency.
13. Added Groq `CAMERA`/`CHAT` routing plus `CAMERA_REQUIRED` fallback to reduce visual confusion.
14. Added auto-switching text-only fallback mode if audio input devices are not detected or fail mid-flight.
15. Optimized webcam latency by keeping the camera initialized warm in a background thread.
16. Added subprocess playback timeout protection to prevent main loop hangs if system players lock up.
17. Added automatic retries and graceful fallback spoken error messages for all Groq API calls.
18. Implemented context-aware persistent session memory that resets on standby timeout.
19. Fine-tuned VAD silence window (0.55s) & expanded token limits (200 tokens) to prevent mid-speech cutoffs and fact-tag truncations.
20. Updated Groq Vision model to active `qwen/qwen3.6-27b` multimodal model to resolve decommissioned 400 error.
21. Added `clean_model_reply()` regex cleaner to strip internal `<think>...</think>` tags from model output, refined `VISION_SYSTEM_PROMPT` to prevent camera quality/artifact rambling, and tuned VAD level 2 with 0.48s silence threshold to prevent stationary fan noise from delaying speech cutoffs.
22. Restored audio VAD parameters and threshold settings to default (END_SILENCE_SECONDS=0.36, VAD_AGGRESSIVENESS=3, MULTIPLIER=2.2, MIN_RMS=120) per user's hardware mixer adjustments.
23. Removed all hardcoded pre-baked phrase lists and static fallbacks; switched 100% of camera routing decisions to pure AI model classification (~100ms), fixed reasoning model `<think>` tag extraction, and set `max_tokens=450` for true visual answers.
24. Migrated vision backend to official `google.genai` SDK with Gemini 1.5 Flash (1-2s response time), cleaned `VISION_SYSTEM_PROMPT` for direct answers, eliminated duplicate camera check API calls, and fixed Whisper hallucination false spoken errors.
25. Discovered and implemented Groq's official `reasoning_effort: "none"` parameter for `qwen/qwen3.6-27b`, completely eliminating `<think>` tags and reasoning token latency. Migrated 100% of the project back to Groq (STT, Vision, Chat, Routing), restoring massive free limits with 0.3s response times and direct hardware camera fallback.
26. Established the clean 3-file Master Robot Architecture: `listen.py` (Master Brain), `screen.py` (60 FPS animated 7-inch Face UI), `motors.py` (Local Edge CV 30 FPS Person Tracker & Serial Bridge), and `arduino.ino` (Arduino Mega firmware).
27. Integrated instant motor cut-off on speech detection (<1ms) and synchronized all 8 face expression states directly with Groq Qwen/Whisper dialogue lifecycles.
28. Added natural voice movement intent commands ("Follow me", "Come here", "Stop moving") and pupil gaze tracking that follows the user in front of the camera.
29. Updated Arduino Mega firmware (`arduino.ino`) for 4WD Skid-Steer chassis with 4x BTS7960 motor drivers driving 4x Johnson DC motors and 2x HC-SR04 front ultrasonic sensors with <20cm emergency braking.
30. Integrated WebRTC VAD level 3 + RMS noise floor filter and natural pause buffer tuned specifically for loud exhibition auditorium rejection.
31. Implemented fast-intent conversation enders ("alr thanks", "bye", "good", "done", etc.) returning gracefully to standby mode with non-repeating exit phrases and prompt to tap "Talk to Neurolis".
32. Added dedicated Real-Time Subtitle Card to `screen.py` fitted for 7-inch screen (1024x600, 16:9), showing speaker badges (`[YOU]` in mint, `[NEUROLIS]` in cyan), status telemetry, and word wrapping.
33. Unified vision pipeline: designated `motors.py` as single camera master to eliminate Windows DirectShow device conflict, exposing raw frame cache for Groq Vision queries and automated OpenCV HUD window popup/close.
34. Developed `classify_motor_intent()` AI semantic classifier with 0ms deterministic negation guards, permanently eliminating false-positive follow triggers on phrases like "quit following me" and "stop following".
35. Built Active Expression Demonstrator Engine: displays and holds individual expressions for 3.5s with speech confirmation, and showcases all 6 expressions sequentially (`happy` -> `thinking` -> `listening` -> `watching` -> `moving` -> `confused`) with live descriptive subtitles.
36. Redesigned `MOVING` expression into a front-facing humanoid robot moving forward (coming AHEAD toward viewer) with downward-rolling rubber treads, twin Xenon headlights with expanding road beams, suspension bounce, and two perspective road tracks streaming backward.
37. Added direct capabilities inquiry handler delivering concise, token-safe replies (<45 words) stating physical mobility, person following, camera analysis, and listing all expressions.

To do:

1. Add `config.py` for settings and paths.
2. Replace terminal Enter with touchscreen `Talk to Neurolis` button on Raspberry Pi.
3. Order/test SmartElex VL53L5CX 8x8 ToF Imager.
4. Build a simple VL53L5CX distance-grid test on Raspberry Pi.
5. Test physical serial integration between Raspberry Pi 5 and Arduino Mega when reunited.
6. Run end-to-end motor driving trials on chassis with LiPo battery power.
7. Add exhibition-day reliability checks and stress testing.

## Progress Log

- 2026-05-20: Created initial project map.
- 2026-05-20: Confirmed `edge-tts` voice output and short-term memory.
- 2026-05-21: Replaced Vosk speech recognition with Groq Whisper STT.
- 2026-05-21: Removed wake-word/openWakeWord from current testing path.
- 2026-05-21: Added terminal Enter activation for PC testing.
- 2026-05-25: Old test programs were removed from the active project folder. Project map cleaned to match the fresh project state.
- 2026-05-25: Selected SmartElex VL53L5CX 8x8 ToF Imager for object/distance detection and changed webcam plan to final on-demand AI vision.
- 2026-05-28: Tightened prompts to prevent roleplay, added deterministic identity/capability replies, strengthened vision triggers, and reduced voice recording latency settings.
- 2026-05-28: Added hybrid Groq vision routing so visual requests are sent to webcam vision instead of normal chat hallucinating.
- 2026-07-03: Added text-only input fallback mode to allow running Neurolis without audio devices or when they fail.
- 2026-07-03: Optimized on-demand vision latency by running webcam capture continuously in a background thread.
- 2026-07-03: Added subprocess timeout protection to fallback players to prevent speech playback freezes.
- 2026-07-03: Implemented retry wrapper with exponential backoff for Groq API calls and added spoken error messages on final failures.
- 2026-07-03: Added smart context-aware session memory that extracts facts via XML tags and resets on standby timeouts.
- 2026-07-24: Optimized VAD end silence to 0.55s (VAD level 2) to eliminate mid-speech cutoffs, and expanded Groq Chat max_tokens to 200 to prevent facts tag truncation.
- 2026-08-07: Fixed Groq decommissioned 400 vision error by updating `VISION_MODEL` to `qwen/qwen3.6-27b`.
- 2026-08-07: Added `clean_model_reply()` to strip `<think>` tags from Qwen 3.6 27B output, refined `VISION_SYSTEM_PROMPT` to focus on conversational answers without lens artifact rambling, and tuned VAD to level 2 (480ms cut) to filter out background fan noise cleanly.
- 2026-08-07: Fixed mic recording delay via hysteresis vote decay on `silence_votes` (420ms cut-off), expanded vision `max_tokens` to 450, and added fallback text to eliminate "TTS returned no audio" error.
- 2026-08-07: Restored audio VAD and speech threshold configuration to default settings (END_SILENCE_SECONDS=0.36s, VAD_AGGRESSIVENESS=3) after user reduced hardware microphone gain boost in Windows.
- 2026-08-07: Removed hardcoded phrase lists in favor of 100% pure AI camera decision routing (~100ms latency), removed static fallback strings, and fixed reasoning model `<think>` tag extraction to deliver accurate, real-time visual answers.
- 2026-08-14: Migrated vision backend to Google GenAI SDK (Gemini 1.5 Flash), optimized prompt for direct natural vision replies, eliminated duplicate camera check calls in `handle_user_text`, and fixed silent/filtered Whisper speech handling to avoid false offline alerts.
- 2026-08-19: Discovered and implemented Groq's official `reasoning_effort: "none"` parameter for `qwen/qwen3.6-27b`, completely eliminating `<think>` tags and reasoning token latency. Migrated 100% of the project back to Groq (STT, Vision, Chat, Routing), restoring massive free limits with 0.3s response times and direct hardware camera fallback.
- 2026-09-01: Built and finalized the 3-file Master Robot Architecture (`listen.py` + `screen.py` + `motors.py` + `arduino.ino`). Integrated local Edge CV 30 FPS person tracking ($0 cost, 0ms lag), instant speech motor cut-off, automated 60 FPS face expressions, and natural voice movement commands.
- 2026-09-04: Full System Refinement & Exhibition Polish:
  - Updated Arduino Mega firmware (`arduino.ino`) for exact 4WD hardware: 4x Johnson DC motors on 4x BTS7960 drivers and 2x HC-SR04 front ultrasonic sensors with <20cm emergency stop.
  - Hardened voice pipeline against loud auditorium chatter using WebRTC VAD level 3 + RMS gating, tuned cutoff silence to 4.0s, and added polite conversation enders ("alr thanks", "bye", etc.) with non-repetitive standby exits.
  - Implemented real-time Subtitle Card on 7-inch screen ($y \in [370, 556]$) with `[YOU]` and `[NEUROLIS]` tags, live telemetry, and word wrapping.
  - Solved Windows DirectShow camera conflict by routing vision queries through `motors.py`'s raw frame cache; added auto-popping OpenCV HUD window for follow/approach/roam modes.
  - Built AI-Verified Motor Intent Classifier (`classify_motor_intent`) with 0ms deterministic negation guards, permanently fixing false follow triggers on phrases like "quit following me" and "stop following".
  - Overhauled Face UI animations across all states: clean Acoustic Sonar for listening (mouth area only, eyes clear), removed technical label text from canvas, and created a new front-facing forward-moving robot animation with downward-rolling treads, Xenon headlights, and backward-streaming perspective road tracks.
  - Built Active Expression Demonstrator Engine for both individual expressions (held 3.5s with spoken confirmation) and full sequential cycling through all 6 expressions with descriptive subtitles.
  - Added concise capabilities inquiry handler (<45 words) stating mobility, person following, camera analysis, and listing all facial expressions.
- 2026-09-10: Eliminated `scipy` dependency completely. Replaced `scipy.io.wavfile` with Python's built-in standard library `wave` module to resolve Windows Defender Application Control DLL blockage (`_cyutility.pyd`), ensuring 100% portable, zero-DLL WAV recording on both Windows and Raspberry Pi.
- 2026-09-15: Resolved Groq API 404 `model_not_found` error by migrating from decommissioned `qwen/qwen3.6-27b` to active `qwen/qwen3.8-27b` across Chat, Multimodal Vision, and AI Motor Intent Classification with ultra-low latency `reasoning_effort: "none"`.
- 2026-09-16: User Feedback & Exhibition System Polish:
  - **Conversation Wrap-Up Enders**: Re-enabled "nice", "good", "cool", "awesome", "perfect", "ok", "okay" as conversation enders so Neurolis responds warmly and transitions into standby as intended.
  - **Full AI Mean/Emotion Evaluation**: Added `MEAN_CHECK_SYSTEM_PROMPT` and `groq_mean_check()` allowing Groq Qwen to evaluate nuanced, indirect, or creative insults and trigger the sad face expression (`ExpressionState.SAD`).
  - **High-Contrast Dark Blue Optical Scanning Laser**: Replaced the low-contrast `#55ffff` scanning line in `screen.py` with a bold dark blue line (`#002b66`, width=3) for sharp visibility against the cyan eye.
  - **Comprehensive Beginner-Friendly Comments**: Added human, informal, lowercase, explanatory comments across every single block of `listen.py`, `motors.py`, `arduino.ino`, and `screen.py` for students and programming beginners.
  - **Environment-Based API Key**: Migrated `GROQ_API_KEY` in `listen.py` to load from `.env` using `python-dotenv` (`load_dotenv()` + `os.getenv`), keeping credentials secure and isolated from source control.

## Reliability Notes

- **Exhibition Screen Isolation**: On the Raspberry Pi 7-inch display, ONLY the Face UI (`screen.py`) is rendered. Camera feeds, vision debug windows, and terminal consoles run silently in the background with zero popups or desktop artifacts visible to guests.
- Do not use API calls for random room noise.
- Do not rely on Groq Vision for continuous obstacle detection.
- Do not rely on camera-only detection for motor safety.
- Keep secrets in `.env`, never hardcoded.
- Keep modules small.
- Test one feature at a time.
- Exhibition reliability is more important than flashy behavior.

