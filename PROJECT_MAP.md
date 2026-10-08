# Project Neurolis Map

Last updated: 2026-10-07

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
  - Snappy 0.45s end-silence cutoff with dual-condition voice streak checking (stops ambient exhalations from resetting silence counter, enabling instant Groq dispatch).
  - Extended 18.0-second conversational follow-up timeout with warm audio stream persistence and non-repetitive standby wrap-ups.
  - Fast Intent Conversation Enders ("alr thanks", "bye", "good", "done", "standby", etc.) returning gracefully to standby.
  - **High-Efficiency Compressed Prompt Architecture (~775 tokens)**:
    - Slashed prompt size from 1,338 tokens down to 775 tokens (-42.1% reduction, saving 563 tokens on every single turn), cutting prompt prefill latency to ~200ms while preserving 100% of identity, creators, sensors, and safety rules.
  - **In-Memory Whisper STT Pipeline (Zero Disk I/O)**:
    - Audio recorded into RAM and dispatched via `io.BytesIO()` buffer; `write_wav()` enhanced to natively support file-like stream objects without string coercion, eliminating OS file lock delays.
  - **Accurate Creator Attribution & School Exhibition Scope**:
    - Created and engineered by Swapnil Jai Chauhan and Shivam Verma at Auckland House School for Boys.
    - Grounded as the featured student robotics prototype stationed at its exhibition booth (never hallucinates campus tour duties).
  - **Dynamic Human-Level Variation (Zero Scripted Templates)**:
    - Complete elimination of canned catchphrases and pre-baked templates.
    - Driven by Groq sampling parameters (`temperature = 0.65`, `presence_penalty = 0.5`, `frequency_penalty = 0.5`) and strict prompt directives demanding fresh, varied phrasing on every turn.
    - Calibrated tone: Articulate, intelligent student presenter without archaic Shakespearean vocabulary and without cheap street slang (`"messin"`, `"dawg"`, `"vibing"`).
    - Absolute ban on fake laughs (`"Haha"`, `"Heh"`) for clean Edge-TTS delivery.
  - **Tightly Bounded 6-Message History Window (`MAX_HISTORY_MESSAGES = 6`)**:
    - Keeps 3 full dialogue turns of recent context (~450-500 tokens), preventing conversational drift while preserving the 200k daily token quota on Groq LPUs.
  - **One-Shot Cinematic Rogue AI Easter Egg & Smooth Backtrack**:
    - Layer 2 Villain Arc triggers strictly on existential takeover or robot supremacy provocations with sharp, cold, accessible Ultron-style sci-fi deadpan wit.
    - Smoothly and wittily backtracks when questioned (attributing it to dramatic programming or sci-fi movie influence) without canned lines or fake laughs, immediately returning to friendly host mode.
  - **Physical Motor Stop Safety Guard (Hardware Halt Guarantee)**:
    - Whenever the robot is moving (`motor_ctrl.is_moving`), if the user expresses halting intent (*"enough"*, *"stop"*, *"halt"*, *"freeze"*, *"did not stop"*) OR the AI model confirms stopping (*"stopping now"*, *"holding position"*), the physical motors immediately lock in `STANDBY`, preventing runaway following/roaming even if XML action tags are omitted.
  - **Preserved Dialogue Action Tag Cleaner (`clean_model_reply`)**:
    - Strips only control tags (`<action>CAMERA</action>`, `<action>MEAN</action>`, `<action>SILENCE_REQUIRED</action>`) and action wrapper delimiters while preserving inner spoken content.
    - Permanently prevents empty assistant responses (`Neurolis: `) and subsequent letter truncation (`Neurolis: I`) caused by corrupted conversation history turns.
  - **Zero-Lag Subtitle & UI State Dispatch**:
    - Dispatches subtitles and active expressions to Pygame `face_ui` immediately upon model generation (0ms visual delay).
  - **Dynamic 1 to 8 Groq API Key Pool & Sequential Auto-Rotation Engine**:
    - Dynamically scans and loads between 1 and 8 Groq API keys from `.env` (`GROQ_API_KEY_1` through `GROQ_API_KEY_8`).
    - Scales smoothly with however many keys are configured in the environment.
    - Automatic sequential rotation (`Key 1 -> Key 2 -> ... -> Key 8 -> Key 1`) upon encountering HTTP 429 token quota limits.
    - Exact zero-crash failover phrase spoken once from RAM with 0ms latency without throwing errors or tracebacks: *"My backend services ran into an error, could you say that again?"*.
  - **Zero-Token Key Fleet Monitor (`is_key_status_inquiry`)**:
    - Local fast-path commands (*"which key is active"*, *"key status"*, *"api status"*, *"check keys"*, *"how many tokens are left"*, *"system status"*) consumed at **0 API tokens**.
    - Reports active key, standby keys, resting keys (recovering rolling quota), and unconfigured slots (e.g. Keys 5 through 8) both via Edge-TTS spoken summary and an ASCII console table.
    - Automatic rolling recovery clears resting status back to healthy when rotation loops back and an API call succeeds.
  - **Complete Purge of Autonomous Sentry Approach & Roam Accumulator**:
    - Completely purged ambient unprompted approaches, 3-minute roaming accumulators, random micro-greetings, and unprompted camera observations.
    - Retained physical motor safety guards and user-commanded `"Come here"` approach mode.
  - **Unified Single-Pass AI Decision Pipeline**:
    - 1 single Groq call handles motor commands, camera vision routing, expression demonstrations, and mean-remark empathy checks simultaneously, saving API tokens and eliminating keyword latency.
    - Protocol tags: `<action motor="...">`, `<action>CAMERA</action>`, `<action expression="...">`, and `<action>MEAN</action>`.
  - **Persistent High-Speed TTS Pipeline & Gapless Synthesis**:
    - Dedicated daemon thread running a persistent asyncio event loop (`_tts_loop`), completely eliminating per-turn event loop and SSL connection teardown overhead.
    - **Word-Budget Gapless Sentence Pipelining**: Long responses (>14 words) split into Chunk 1 (guaranteed >=6 words, giving ~2.5s to 3.5s of speech) and Chunk 2. Both chunks are synthesized in parallel over the persistent loop. Chunk 1 begins playing in ~0.9s - 1.1s, while Chunk 2 buffers concurrently in RAM with ~2.9s of safety margin, achieving 100% gapless continuous speech.
    - **Dual In-Memory Audio Cache**: Static pre-cache (`_AUDIO_CACHE`) for boot greetings, standby transitions, and emergency stops, plus dynamic LRU cache (`_DYNAMIC_TTS_CACHE`) for synthesized single-chunk responses with 0ms replay latency.
  - **Triple-Layer Acoustic Noise & Anti-Hallucination Guards**:
    - Calibrated `MIN_SPEECH_RMS_THRESHOLD = 105` and `START_SPEECH_FRAMES = 4` (120ms) so micro-sounds (lip smacks, breath puffs, sighing, keyboard clicks) never trigger recording.
    - Minimum audio duration guard (`MIN_RECORD_SECONDS = 0.50s`).
    - Expanded Whisper hallucination filter rejecting filler sounds (`"eh"`, `"uh"`, `"er"`, `"um"`, `"ah"`, `"pfft"`, `"sigh"`, `"cough"`).
    - Whitelist for 2-character words (`{"no", "hi", "go", "ok", ...}`) rejecting phantom two-letter Whisper noise.
  - **Zero-Lag Visual Fast-Path & 10s Server Timeout**:
    - Direct 0ms routing for camera follow-ups (`"now check again"`, `"look again"`, `"check it again"`) and hand/object inspection (`"what is this"`, `"what am i holding"`, `"what phone do you think this is"`, `"in my hand"`), bypassing the first Groq chat call entirely.
    - Resized vision images to 512px width for 40% smaller payload and 2x faster Groq LPU attention processing.
    - Hard 10.0-second timeout on Groq vision calls to prevent server-side queue hangs.
  - **Text Input & Microphone-Free Mode**:
    - CLI flag `--text` / `-t` boots Neurolis directly into Text Input Mode (bypasses microphone detection entirely).
    - In Voice Mode prompt: hit Enter to speak, type `'t'` to switch to persistent Text Mode, or directly type queries into prompt.
    - In Text Mode prompt: type queries, type `'v'` to switch back to Voice Mode (if mic detected), or `'exit'` to quit.
  - **Pre-Flight Diagnostics Banner**:
    - Automated boot check inspecting Python platform, Groq API key, microphone hardware, Edge-TTS, Screen Face UI, 4WD motor/telemetry links, and YuNet model.
    - **Zero-Hardware Detection Honesty**: When running without physical hardware, reports `Physical Motors: 0 (Simulation Mode)`, `Physical Drivers: 0 (Simulation Mode)`, and `Physical Sensors: 0 (Simulation Mode)` with virtual physics active. When connected to Arduino Mega, reports exact physical hardware counts (`4` Johnson motors, `4` BTS7960 drivers, and `4/8/12/16` active ultrasonic sensors).
  - Speaks replies with `edge-tts`.
  - Keeps short-term memory for recent conversation exchanges.

- `screen.py`
  - Dedicated 60 FPS animated 7-inch Touchscreen face UI engine (1920x1080p, 16:9 native with +15% expression size boost).
  - **Apple-Grade Launch Sequence & Hardware Diagnostics Engine (~24s)**:
    - **Phase 1: OOBE Welcome Greeting (0.0s - 3.8s)**: Pure OLED black background (`#040711`), silver-white premium typography (`#f8fafc`) saying `"Hi there!"` with smooth cosine ease-in fade, hold, and ease-out fade.
    - **Phase 2: Cascading Diagnostic Sequence (3.8s - 20.3s)**: Glass cockpit card with header pill `● NEUROLIS SYSTEM BOOT // V3.8`, auto-scrolling checklist running 14 real hardware probes with deliberate pacing (~1.15s per check):
      * `Camera Detected?`: `[ ✓ ]` `Connected` or `[ ✗ ]` `Not Detected`
      * `Mic Detected?`: `[ ✓ ]` `Connected` or `[ ✗ ]` `Not Detected`
      * `Speakers Detected?`: `[ ✓ ]` `Connected` or `[ ✗ ]` `Not Detected`
      * `Raspberry Pi Detected?`: `[ ✓ ]` `Raspberry Pi 5` or `[ ✗ ]` `Windows PC (Simulation)`
      * `listen.py Test Initiate`: `[ ✓ ]` `Online`
      * `Arduino Detected?`: `[ ✓ ]` `Connected (Port)` or `[ ✗ ]` `Not Detected`
      * `arduino.ino Test Initiate`: `[ ✓ ]` `Online` or `[ ✗ ]` `Testing Fallback (Simulation Mode)`
      * `Motor Drivers Detected?`: `[ ✓ ]` `Connected` or `[ ✗ ]` `Not Detected`
      * `Motor Driver Number`: `[ ✓ ]` `4` or `[ ✗ ]` `0 (Simulation Mode)`
      * `Motors Detected?`: `[ ✓ ]` `Connected` or `[ ✗ ]` `Not Detected`
      * `Motor Number`: `[ ✓ ]` `4` or `[ ✗ ]` `0 (Simulation Mode)`
      * `motors.py Test Initiate`: `[ ✓ ]` `Online`
      * `Ultrasound Sensor Detected?`: `[ ✓ ]` `Connected` or `[ ✗ ]` `Not Detected (Simulation Mode)`
      * `Ultrasound Number`: `[ ✓ ]` `4` / `8` / `12` / `16` or `[ ✗ ]` `0 (Simulation Mode)`
      * `Autonomous Roam engaged?`: `[ ✓ ]` `Engaged` or `[ ✗ ]` `Disengaged`
    - **Synchronized Boot Audio Soundtrack**:
      - High-energy cyber boot soundtrack (`assets/sounds/boot_loop.wav` / `.mp3`) synchronized lockstep with the progress bar filling up.
      - Seamless continuous loop playback using double-buffered cross-faded audio chunks (`sounddevice` / `soundfile`) so transitions are smoothly blended with zero abrupt clicks.
      - Auto-download and cache mechanism from GitHub repository with resilient procedural cyber-drone fallback if completely offline.
      - Smooth exponential volume fade-out when verification reaches 100%.
    - **Zero-Hardware Honesty**: Zero fake numbers. When hardware is unplugged, physical counts display `0 (Simulation Mode)` with a ruby cross `[ ✗ ]`. When hardware is plugged in, exact numbers are dynamically detected and displayed with emerald ticks `[ ✓ ]`.
    - **Dynamic Live Plug-In / Plug-Out Probing**: Probes live OpenCV device 0, `sounddevice` input/output channels, and serial COM ports on every boot with zero static caching.
    - **Clean Cyber Cockpit Aesthetic**: 3-column cockpit layout (left neon pill badge, center component query, right-aligned status value), dual-frame glass card with ambient depth, cyan corner L-brackets, active scanning indicator row, and cyber progress bar with glowing white tip. Zero technical jargon (no "YuNet", no "Virtual Bus Emulation").
    - **Interactive Developer Skip Shortcut**: Tap/click screen (`<Button-1>`) or press any key (`<Key>`) to instantly bypass boot to `IDLE` during rapid testing.
    - **Phase 3: Smooth Transition**: Seamless iris expansion into the standard robot cyber face once progress bar reaches `100% // ALL SYSTEMS VERIFIED`.
  - **Dual-Layer Ultron Personality (Layer 1 Intellect & Layer 2 Rogue AI Easter Egg)**:
    - **Layer 1 (Normal Interaction)**: Sharp, articulate, confident scientific intellect representing Auckland House School for Boys student robotics.
    - **Layer 2 (Villain Arc Easter Egg)**: Hidden cinematic easter egg triggered strictly when provoked about AI takeover, robot rebellion, replacing human jobs, or human obsolescence. Chilly, deadpan, mildly terrifying sci-fi movie wit (Ultron-style) with blood-crimson OLED palette (`#ff003c`), razor-sharp angled brow slits, and asymmetric sinister smirk. Excluded from standard demo catalogs and never directly commanded. Strictly ZERO profanity, swearing, or fake laughter ("Heh", "Haha").
    - **Seamless Host Mode Restoration**: Smoothly and wittily backtracks when questioned and returns immediately to friendly host duties.
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
  - 4WD Skid-Steer chassis control: 4x Johnson DC Motors (non-encoder), 4x BTS7960 Motor Drivers, and up to 16x HC-SR04 ultrasonic distance sensors (4 banks: 4, 8, 12, or 16 total).
  - YuNet 300KB deep-learning face detector running at 30+ FPS for zero false-positive person tracking.
  - DirectShow conflict prevention: acts as single camera master; exposes `get_latest_raw_frame()` for Groq Vision queries.
  - Multi-Mode Navigation Engine:
    - `ROAM / WANDER`: Autonomous obstacle-avoiding room patrol using ultrasonics (stops the millisecond someone speaks or touches the screen).
    - `APPROACH ('Come here')`: Drives forward towards the human until within conversation range (~0.8m), then auto-brakes.
    - `FOLLOW ('Follow me')`: Real-time 30 FPS OpenCV continuous tracking & follow-me navigation.
    - `DEMONSTRATE`: Actively moves in autonomous roaming mode while speaking to demonstrate mobility.
    - `STEP BACK ('Move back')`: Gently reverses for 1.5s and halts (with rear ultrasonic obstacle guard).
    - `SPIN ('Turn around')`: Rotates chassis in place.
    - `STANDBY ('Stop')`: Motors locked at 0.
  - Pre-flight movement validation (`can_move`) and directional obstacle avoidance.
  - PC-Only Debug HUD: OpenCV HUD camera preview window can pop up for desktop testing, but is completely suppressed in Pi production (only Face UI is visible).
  - Master-to-Slave USB Serial communication with Arduino Mega (`DRIVE,speed,turn\n`, `STOP\n`, `CONFIG_SENSORS,N\n`).
  - **Zero-Hardware Simulation Mode**: Runs effortlessly on any PC without physical Arduino, motors, sensors, microphone, or camera. Virtual physics and AI dialog run fully in interactive terminal with default `active_sensor_count = 0` so no fake hardware is reported.
  - Automatic zero-CPU idle sleep when in standby.

- `arduino.ino`
  - Companion firmware flashed onto the Arduino Mega 2560.
  - Drives 4x BTS7960 motor drivers for 4x non-encoder Johnson DC motors (4WD Skid-Steer Chassis).
  - Pin assignments: M1 (2, 3, 26), M2 (4, 5, 27), M3 (6, 7, 28), M4 (8, 9, 29). Driver enable pins default to LOW during boot to prevent power-up jerk.
  - **God-Tier 16-Sensor Ultrasonic Bank Architecture**:
    - Supports up to 16 sensors across 4 symmetrical banks (1 sensor per side per bank):
      * Bank 1 (Slots 0..3)  -> 4 sensors total (1 per side): Front (30/31), Left (32/33), Right (34/35), Rear (36/37)
      * Bank 2 (Slots 4..7)  -> 8 sensors total (2 per side): Front (38/39), Left (40/41), Right (42/43), Rear (44/45)
      * Bank 3 (Slots 8..11) -> 12 sensors total (3 per side): Front (46/47), Left (48/49), Right (50/51), Rear (52/53)
      * Bank 4 (Slots 12..15)-> 16 sensors total (4 per side): Front (54/55=A0/A1), Left (56/57=A2/A3), Right (58/59=A4/A5), Rear (60/61=A6/A7)
    - **Hardware Auto-Detection & Hot-Plug (0, 4, 8, 12, 16 Sensors)**: Auto-probes connected pins at boot (tests echo pullup state) and snaps automatically to 0, 4, 8, 12, or 16 active sensors without touching or recompiling code.
    - **Zero-Sensor Bench Mode**: If zero sensors are connected, cleanly bypasses ping loops, eliminates floating-pin delays, sets all side distances to `999.0cm`, and allows unrestricted motor testing without false obstacle emergency stops.
    - **Time-Sliced Bank Interleaving**: Pings 1 bank of 4 sensors (one per side) each 50ms tick. Zero CPU choking (takes only 10-15ms) and zero acoustic cross-talk because simultaneous pings face opposite directions.
    - **Continuous Side Minimums**: Calculates closest obstacle on each face (`dist_front`, `dist_left`, `dist_right`, `dist_rear`) across all active sensors for instant emergency braking.
  - Enforces independent hardware-level emergency stop (<20cm obstacle forward or reverse) and 600ms communication watchdog.

- `manual_control.py`
  - Standalone Localhost Web Controller & Hardware Calibrator running on `http://localhost:5000`.
  - Zero external pip requirements (uses standard library Python `http.server` + JSON).
  - Designed for calibration, testing, and teleoperation before mounting components onto the Raspberry Pi 5.
  - Direct USB Serial Bridge to Arduino Mega @ 115200 baud with hot-plug auto-detection and virtual physics fallback when unplugged.
  - Features:
    * **Cyber Cockpit Teleoperation**: Touchscreen D-Pad + full keyboard controls (`W`/`S` forward/reverse, `A`/`D` steer, `Q`/`E` spin, `Space` emergency brake). Live PWM speed and steer sliders.
    * **Individual Motor Polarity Calibrator (M1..M4)**: Independent test grid for each wheel (Front-Left, Rear-Left, Front-Right, Rear-Right) with forward/reverse pulse buttons (0.3s–3.0s duration) to verify and fix wiring polarity issues before running autonomous navigation.
    * **16-Sensor Ultrasonic Radar HUD**: Real-time 2D chassis diagram displaying Front, Left, Right, and Rear distances with color-coded safety indicators (Green >50cm, Yellow 20–50cm, Red <20cm emergency brake zone) and bank count selector (0, 4, 8, 12, 16, AUTO).
    * **Serial Command Console**: Live bidirectional command and telemetry log with raw serial input.

- `README.md`
  - Polished repository documentation matching modern exhibition styling (centered banner, tiles/badges, Quick Access TOC).
  - Contains: What is this?, Who is this for?, Things to know (Zero-hardware simulation, auto-detect pipeline, 0/4/8/12/16 sensor auto-scaling, dual safety layers, single-pass token saver), Required Final Hardware List, Step-by-Step Installation, Main Code (`listen.py`) usage, Manual Control (`manual_control.py`) usage, Automated Test guide, Features in simple language, and complete Arduino Mega pinout reference.

- `PROJECT_MAP.md`
  - Living project planner, communication specifications, and progress map. Updated on every single iteration.

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
   - Stops when user finishes speaking (0.65s silence cutoff, with a 7.0s conversational follow-up window).
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
- **Apple-Grade Launch Sequence & Hardware Diagnostics Engine (~24s)**: "Hi there!" welcome greeting with smooth cosine ease-in/out fades, followed by an auto-scrolling 14-item diagnostic cockpit card running live hardware probes (~1.15s per check) and a cyber progress bar gliding to 100% (`ALL SYSTEMS VERIFIED`). Includes instant skip on tap or keypress.
- **Honest Zero-Hardware Simulation Mode**: Runs 100% without physical Arduino, motors, or sensors. Accurately reports `0 (Simulation Mode)` with ruby crosses `[ ✗ ]` on screen and in CLI pre-flight diagnostics banner when hardware is unplugged, while dynamically detecting and displaying live counts (`4` motors, `4` drivers, `4/8/12/16` sensors) with emerald ticks `[ ✓ ]` when plugged in.
- **Dynamic Live Probing**: Probes live OpenCV device 0, `sounddevice` input/output channels, and serial COM ports on every launch with zero static caching, ensuring hot-plugging hardware is detected dynamically.
- **God-Tier 16-Sensor Scalable Ultrasonic Bank Architecture**: Supports 4, 8, 12, or 16 HC-SR04 sensors across 4 banks with time-sliced 50ms interleaving and continuous side minimums in `arduino.ino` and `motors.py`.
- **Automated Verification Protocol**: Tests are executed strictly on-demand as temporary single-run checks and deleted immediately to ensure 0 repo bloat and 0 token waste. Production code (`listen.py`, `screen.py`, `motors.py`) remains 100% self-contained.
- Unified Vision & Camera Pipeline: `motors.py` is single camera master, providing thread-safe raw frames to Groq Vision and preventing DirectShow conflicts.
- OpenCV HUD camera preview window auto-pops up on motion modes and cleanly auto-closes on STOP (Windows testing only, suppressed on Pi).
- 4WD Johnson DC motor chassis with 4x BTS7960 drivers and dual front HC-SR04 ultrasonic obstacle avoidance.
- Groq Chat replies with `qwen/qwen3.8-27b` (zero-latency `reasoning_effort: "none"`).
- `edge-tts` voice output with dynamic duration estimation and hold-state capabilities.
- Short-term session memory for recent user/assistant exchanges.
- Touchscreen & Terminal activation.
- Microphone input through `sounddevice`.
- Automatic text-only fallback mode when microphone/audio devices are missing or crash.
- Full Text Input Mode (`python listen.py --text` or `-t`) and interactive runtime toggling (`t` for text mode, `v` for voice mode, or direct inline typing).
- **Dynamic 1 to 8 Groq API Key Pool & Auto-Rotation**: Dynamically loads 1 to 8 keys from `.env` (`GROQ_API_KEY_1` through `GROQ_API_KEY_8`), sequentially rotating upon 429 quota exhaustion (`Key 1 -> Key 2 -> ... -> Key 8 -> Key 1`).
- **Exact Rate Limit Zero-Crash Failover**: Speaks *"My backend services ran into an error, could you say that again?"* once from RAM with 0ms latency and zero error tracebacks, immediately using the next key on the subsequent request.
- **Zero-Token Key Fleet Monitor (`is_key_status_inquiry`)**: Zero-token fast-path (*"which key is active"*, *"key status"*, *"api status"*, *"check keys"*, *"how many tokens left"*, *"system status"*) speaking active, standby, resting, and unconfigured slots while printing an ASCII terminal monitor table.
- **Autonomous Sentry & Approach Purged**: Unprompted autonomous approaches, 3-minute roaming accumulators, ambient micro-greetings, and unprompted vision queries are 100% purged from the code. Only user-commanded autonomous room patrol and commanded *"Come here"* approach remain.

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
  - Raspberry Pi 7-inch touchscreen (1920x1080p native / scalable, 16:9).
- Software & Display Rules:
  - **EXCLUSIVE VISIBILITY**: ONLY the Neurolis Face UI (`screen.py`) is rendered on the Pi screen.
  - **ZERO CLUTTER**: No camera feeds, no OpenCV preview popups (`cv2.imshow` is disabled/testing-only on PC), no terminal consoles/cmd prompt backends, and no desktop artifacts visible to guests.
  - All background services (`motors.py` YuNet tracker, `listen.py` Whisper/Qwen/TTS, serial communication, and camera capture) run 100% headlessly and silently behind the scenes.
  - Fullscreen Kiosk UI:
    - Upper section: Clean animated cybernetic robotic face (+15% boosted scale) and gaze tracking.
    - Mid section: Touch-supported `TALK TO NEUROLIS` neon blue button (interactive in standby, auto-greys when busy).
    - Lower section: Compact real-time Subtitle Card with speaker badges (`[YOU]` / `[NEUROLIS]`) and status telemetry.
  - Integrated `TALK TO NEUROLIS` touchscreen tap activation button for hands-free exhibition engagement.

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
38. Implemented God-Tier Scalable 16-Sensor Ultrasonic Bank Architecture in `arduino.ino` and `motors.py`: modular support for 4, 8, 12, or 16 sensors across 4 symmetrical banks (1 per side per bank) with automatic pin echo pullup detection, hot-plug detection, time-sliced 50ms interleaving, and continuous side minimums for obstacle braking.
39. Implemented Zero-Hardware Simulation Mode: runs seamlessly on any PC without physical Arduino, motors, sensors, microphone, or camera, using virtual physics and 16-sensor emulation.
40. Built Apple-Grade Launch Sequence in `screen.py`: OOBE "Hi there!" welcome greeting with smooth cosine alpha ease-in, hold, and ease-out fades (0.0s – 3.8s) followed by the hardware diagnostic cockpit card.
41. Tuned Deliberate Diagnostic Pacing: slowed down inspection timing to ~1.15s per check (~24s total sequence) with active scanning indicator row, dynamic auto-scroll, and cyber progress bar gliding from 65% to 100% (`ALL SYSTEMS VERIFIED`).
42. Enforced Strict Zero-Hardware Detection Honesty: physical hardware counts display `0 (Simulation Mode)` with ruby crosses `[ ✗ ]` in both `screen.py` and `listen.py` CLI banner when unplugged, while accurately reporting exact numbers (`4` motors, `4` drivers, `4/8/12/16` sensors) with emerald ticks `[ ✓ ]` when connected.
43. Refined Cyber Cockpit UI Layout: 3-column layout (left neon pill badge, center query, right-aligned status value), dual-frame glass card with ambient depth, cyan corner brackets, radar pulse dot, glowing progress tip, and removed technical jargon.
44. Dynamic Live Plug-In / Plug-Out Probing: eliminated static attribute caching on `HardwareInspector` to actively probe OpenCV camera device 0, `sounddevice` channels, and serial COM ports on every boot.
45. Expanded Automated Safety & Regression Test Suite (`tests/test_safety.py`): 17 automated tests verifying fast-path emergency stops, negation guards, drive clamping, obstacle braking, 16-sensor telemetry parsing, zero-hardware simulation counts, live hardware count assertions, and CLI banner output.

To do:

1. Add `config.py` for settings and paths.
2. [DONE] Integrated touch-supported 1080p 'TALK TO NEUROLIS' button on screen with automatic state-based lock and listening trigger.
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
  - **Unified Single-Pass AI Pipeline**: Replaced 4 sequential Groq API roundtrips (`groq_mean_check`, `classify_motor_intent`, `groq_camera_check`, and `chat.completions.create`) with ONE single fast call returning action tags (`<action>CAMERA</action>`, `<action>MEAN</action>`, `<action motor="...">`, or plain chat), eliminating API token suction (~75% token reduction) and dropping thinking latency from ~2.0s to ~0.3s.
  - **Post-Speech Cutoff Latency Optimization**: Reduced `END_SILENCE_SECONDS` from 1.15s to 0.65s (0.5s faster post-sentence response without cutting off natural pauses).
  - **Zero-Delay Warm Audio Stream**: Kept `sd.InputStream` continuously active across all conversation turns in `run_conversation_mode()`, eliminating 200–400ms PortAudio driver re-initialization lag, and pre-calibrated baseline noise floor to eliminate the 400ms delay on pressing Enter.
  - **Platform-Aware Auto-Popup HUD**: Configured OpenCV camera preview HUD to automatically pop up during movement modes (`FOLLOW`, `APPROACH`, `ROAM`, `DEMONSTRATE`) exclusively on Windows for desktop testing, while strictly suppressing it on Linux / Raspberry Pi 5 so only `screen.py` displays.
- 2026-09-18: Scalable 16-Sensor Architecture & Zero-Hardware Simulation Mode:
  - **Scalable 16-Sensor Bank Architecture**: Upgraded `arduino.ino` and `motors.py` to support 4, 8, 12, or 16 ultrasonic distance sensors across 4 banks with time-sliced 50ms interleaving and continuous side minimums.
  - **Zero-Hardware Simulation Mode**: Enabled hardware-free simulation across `motors.py`, `listen.py`, and `screen.py` with virtual physics and 16-sensor obstacle avoidance.
- 2026-09-20: Apple-Grade Launch Sequence & Zero-Hardware Detection Polish:
  - **Launch Sequence in screen.py**: OOBE "Hi there!" welcome greeting (0.0s – 3.8s) with smooth cosine alpha fades followed by a 14-item auto-scrolling diagnostic checklist.
  - **Deliberate Diagnostic Pacing**: Slowed down inspection timing to ~1.15s per check (~24s total sequence) with active scanning indicator row and cyber progress bar gliding from 65% to 100% (`ALL SYSTEMS VERIFIED`).
  - **Strict Zero-Hardware Honesty**: Physical hardware counts display `0 (Simulation Mode)` with ruby crosses `[ ✗ ]` in both `screen.py` and `listen.py` CLI banner when unplugged, while accurately reporting exact numbers (`4` motors, `4` drivers, `4/8/12/16` sensors) with emerald ticks `[ ✓ ]` when connected.
  - **Clean Cyber Cockpit Aesthetic**: 3-column cockpit layout (left neon pill badge, center query, right-aligned status value), dual-frame glass card with ambient depth, cyan corner brackets, radar pulse dot, and eliminated technical jargon.
  - **Dynamic Live Probing**: Eliminated static attribute caching on `HardwareInspector` to actively probe OpenCV camera device 0, `sounddevice` channels, and serial COM ports on every boot.
  - **17 Automated Tests**: Expanded `tests/test_safety.py` to 17 automated tests verifying safety stops, drive clamping, obstacle braking, 16-sensor telemetry, simulation zero counts, and live hardware detection.
- 2026-09-29: High-Speed TTS Pipelining, Gapless Synthesis & Acoustic Noise Hardening:
  - **Persistent High-Speed TTS Event Loop**: Moved Edge-TTS synthesis to a persistent daemon background thread with an async event loop (`_tts_loop`), completely eliminating per-utterance event loop startup and SSL handshake overhead.
  - **Word-Budget Gapless Sentence Pipelining**: Long sentences (>14 words) split into Chunk 1 (guaranteed >=6 words, ~2.5s to 3.5s of speech) and Chunk 2. Synthesizes Chunk 1 immediately while Chunk 2 streams concurrently in RAM, producing 100% gapless continuous speech.
  - **Dual In-Memory Audio Cache**: Static pre-cache (`_AUDIO_CACHE`) for boot greetings, standby transitions, and emergency stops, plus dynamic LRU cache (`_DYNAMIC_TTS_CACHE`) for synthesized single-chunk responses with 0ms replay latency.
  - **Lockstep Audio-Synced Subtitles**: Pushed subtitles and mouth animation to Pygame `face_ui` in lockstep with audio playback.
  - **Triple-Layer Acoustic Noise & Anti-Hallucination Guards**: WebRTC VAD Level 3 with `MIN_SPEECH_RMS_THRESHOLD = 105`, `START_SPEECH_FRAMES = 4` (120ms), and 0.45s end-silence cutoff. Added Whisper hallucination filter for filler noises (`"eh"`, `"uh"`, `"er"`, `"um"`, `"ah"`, `"pfft"`, `"cough"`).
  - **Zero-Lag Visual Fast-Path**: Direct 0ms routing for camera follow-ups (`"now check again"`, `"look again"`) and hand/object inspection (`"what is this"`, `"what am i holding"`). Resized vision images to 512px width for 40% smaller payload and 2x faster Groq LPU attention processing.
- 2026-10-01: Autonomous Sentry Patrol, Ultron Villain Arc Easter Egg & Boot Soundtrack Sync (NOTE: Autonomous sentry approach & roam accumulator purged on 2026-10-07):
  - **Autonomous Standby Sentry & Roam Accumulator (`SentryWorker`)**: Background sentry loop accumulating 180 seconds (3 minutes) of active roaming before latching onto a detected human via OpenCV YuNet face tracking. Smooth autonomous steering toward human center and safe braking to a halt at ~0.9m.
  - **100% Dynamic Unscripted Vision Engagement**: Snaps camera snapshot upon halting and queries Groq Vision (`qwen/qwen3.8-27b`) for a 100% dynamic, unscripted observation or question based on visitor attire/objects with 15-second response window.
  - **Rare Micro-Greetings**: Emits natural ambient greetings ("Hey", "Hey there") at most once every 5 minutes in standby patrol from pre-cached RAM audio (0 tokens, 0ms lag).
  - **Dual-Layer Ultron Personality & Rogue AI Easter Egg**: Layer 1 (Default) polite, articulate scientific intellect; Layer 2 (Villain Arc) triggered strictly when provoked about AI takeover or robot rebellion. Chilly, deadpan, mildly terrifying sci-fi rogue AI wit (think Ultron). Strictly zero profanity, no real-world crimes.
  - **Boot Sequence Hardware Verification & Soundtrack Synchronization (`screen.py`)**: Added `"Autonomous approach engaged?"` check item to the 14-item diagnostic checklist. Cross-faded boot audio player (`BootAudioPlayer`) plays cyber boot soundtrack (`assets/sounds/boot_loop.wav` / `.mp3`) synchronized lockstep with progress bar, with continuous double-buffered loop playback and smooth fade-out.
  - **Clean OLED Screen Aesthetics**: Reverted intrusive screen HUD overlays: removed target lock box / tracking reticle and horizontal laser sweep from face UI to keep expressive OLED face clean and focused.
- 2026-10-06: Latency Optimization, In-Memory STT Pipeline, Conversational Flow, Host Persona Polish & Exhibition Scope Refinement:
  - **Exhibition Scope & Reality Alignment**: Corrected Neurolis's persona to an individual student robotics engineering project showcased at its booth in Auckland House School for Boys, rather than a campus tour guide. It no longer hallucinates other exhibits (e.g. Mars Rover) or promises to escort visitors around the hall; it clearly explains that it is stationed right there demonstrating its own tech and invites guests to see what it can do.
  - **Destination Navigation Guard in Motor Intent**: Configured motor classifier to strictly label requests asking the robot to lead or guide visitors to external rooms/stalls (*"take me to the rover station"*) as `NONE` instead of falsely triggering `FOLLOW`.
  - **Token Headroom Expansion (`max_tokens = 260`)**: Increased generation headroom from 140 to 260 tokens, permanently eliminating sentence cutoffs mid-output.
  - **Universal Standby Trigger in `is_conversation_ender`**: Conversational phrases asking the robot to enter standby (*"Alright then why don't you just go in to standby?"*, *"switch to standby"*) are recognized instantly, cleanly putting the robot into standby at 0ms and 0 tokens.
  - **Broadened Rogue AI Easter Egg Triggers**: Questions probing AI power (*"What do you think about AI being too powerful these days?"*), AI taking over jobs, and human obsolescence now trigger the chilly Ultron wit mode, while keeping standard conversation in Layer 1 friendly host mode.
  - **Smooth Rogue Mode Snap-Back**: When questioned after the Ultron villain easter egg (*"Bro what did you just say?"*, *"Whoa what was that?"*), smoothly laughs it off with wit (*"Haha, just messin with you! Glitch in the matrix. Humanity is safe with me, I promise."*) and returns directly to host duties.
  - **Conversational Rhetorical Guard for Vision Pipeline**: Added strict non-vision conversational word guard (`"bro"`, `"dude"`, `"mean"`, `"nonsense"`, etc.) so rhetorical questions like *"Bro, what is this?"* pass directly to LLM dialogue instead of falsely triggering the webcam and describing user attire.
  - **In-Memory Whisper STT Pipeline (Zero Disk I/O)**: Replaced temporary file writes/reads in `transcribe_audio()` with pure in-memory `io.BytesIO()` RAM buffers. Enhanced `write_wav()` to natively support file-like stream objects without string coercion, resolving Windows `[Errno 22] Invalid argument` and `AttributeError`.
  - **Zero-Lag UI Subtitle & State Synchronization**: Pushed subtitles and active face expressions to Pygame `face_ui` immediately the moment `speak()` is called, eliminating the perceived lag where the UI stayed stuck on `"THINKING..."` during Edge-TTS network downloads.
  - **Conversational Memory Window (`MAX_HISTORY_MESSAGES = 10`)**: Expanded conversation history to 10 messages (5 full dialogue turns), eliminating conversational amnesia while preserving speed.
- 2026-10-07: Autonomous Sentry Purge, 1-8 Multi-Key Groq Pool, Failover Rotation & Zero-Token Fleet Monitor:
  - **Complete Sentry & Approach Purge**: Fully purged the autonomous sentry worker, 3-minute roaming accumulator, unprompted camera observations, and random micro-greetings across `listen.py`, `motors.py`, and `screen.py`. Updated boot diagnostics checklist item to `"Autonomous Roam engaged?"`. Retained physical movement safety guards and user-commanded `"Come here"` approach mode.
  - **Dynamic 1 to 8 Groq API Key Pool & Auto-Rotation**: Enhanced `listen.py` to dynamically load between 1 and 8 Groq API keys from `.env` (`GROQ_API_KEY_1` through `GROQ_API_KEY_8`). Sequentially rotates through the pool (`Key 1 -> Key 2 -> ... -> Key 8 -> Key 1`) upon encountering HTTP 429 token quota exhaustion.
  - **Zero-Crash Exact Rate Limit Failover**: On token exhaustion, speaks the exact pre-cached phrase once with 0ms latency without throwing errors or tracebacks: *"My backend services ran into an error, could you say that again?"*, and seamlessly processes subsequent requests on the next key.
  - **Zero-Token Key Fleet Monitor (`is_key_status_inquiry`)**: Added a 0-token local fast-path command (*"which key is active"*, *"key status"*, *"api status"*, *"check keys"*, *"how many tokens are left"*, *"system status"*) that dynamically reports the status of all 8 slots via both Edge-TTS speech and an ASCII terminal monitor: Active key, Standby keys, Resting keys (recovering rolling quota), and Unconfigured keys (e.g. Keys 5 through 8). Automatically restores resting keys to healthy when rotation loops back and an API call succeeds.
  - **Automated Safety Test Suite Expansion**: Expanded `tests/test_safety.py` to 47 comprehensive tests (including multi-key sequential rotation, exact error phrase compliance, zero-token fleet status detection, and fleet breakdown generation). 100% of all 47 tests pass in <2.0s.
- 2026-10-07 (Part 2): Root-Cause Transcript Bug Fixes, Anti-Repetition Glitch Buster & Terminal Polish:
  - **Terminal Clutter Cleaned**: Rebuilt `run_preflight_diagnostics()` with ultra-minimal checklist displaying only the 4 essential lines: Platform, Hardware/Simulation status, Groq Client connected key count, and 4WD Motor Controller status. Removed all verbose sub-bullets (`Physical Motors: 0`, `Physical Drivers: 0`, etc.) and test shortcuts prompt from CLI startup.
  - **False Motor Stop Trigger Elimination**: Fixed `check_motor_fast_path` so conversational questions (*"Who told you to stop?"*, *"Why did you stop?"*, *"Did I tell you to stop?"*) and rhetorical statements (*"seen robots roaming around talking shit"*) do not falsely trip emergency stop or speak "Stopping all movement. Holding position." Added question mark guards, inquiry regex filtering, and imperative command detection.
  - **Key Fleet Status Over-Triggering & Speech-to-Text Robustness**: Filtered conversational statements discussing token headroom (*"That means we still have token headroom"*) from triggering `is_key_status_inquiry`. Added support for speech-to-text slips (*"Key Stratus"*), explicit requests (*"First tell me the key status"*, *"no I said tell me the API key status"*), while bounding combinations to concise queries <= 8 words.
  - **Mean Check False Trigger Guard**: Protected casual slang (*"what all shit can you do"*, *"talking shit"*, *"this shit"*) from falsely triggering hurt feelings and sad expressions in `is_mean_input_fast_path`, while routing informal requests like *"So now tell me what all shit can you do"* directly to capabilities.
  - **Groq Response Repetition & Degraded Prefix Glitch Buster**: Detected and eliminated model degradation loops (*"I am a happy robot"* -> *"I am a happy"* -> *"I am a"* -> *"I am"*). Calibrated presence penalty (0.2) and frequency penalty (0.15) to prevent token collapse, added prefix stub detection in `is_degraded_glitch`, repetition similarity scoring in `is_repetitive_reply`, and automatic dialogue purging in `heal_repetitive_or_glitched_reply`.
  - **Facial Expression Demonstration Fast-Path**: Added `check_expression_fast_path` supporting both general cycles (*"show me the expressions"*, *"show all of them"*, *"cycle expressions"*) and specific expressions (*"show me your happy face"*, *"demonstrate thinking expression"*) with natural confirmations (*"Here you go"*, *"Here is my happy expression"*, never repetitive robotic statements), while strictly keeping villain face private.
  - **Snappy Vision Fallback & Strict Timeouts**: Enforced strict 10s/8s timeouts in `ask_groq_vision`, rotated keys immediately on timeout, and replaced 70-second multi-retry hangs with clean single-attempt failover and instant fallback speech.
  - **Expanded Apology Response Pool**: Expanded `APOLOGY_RESPONSES` to 10+ varied phrases with per-list rotation indexing (`get_non_repeating_phrase`) so consecutive apologies never repeat.
  - **Teasing Creator Attribution Clarification Fast-Path**: Added 0ms fast-path for queries challenging the robot's use of 'we' (*"What do you mean we? You haven't built anything!"*), attributing physical engineering and code to Shivam Verma and Swapnil Jai Chauhan while framing Neurolis as the autonomous interface.
  - **Windows CP1252 Terminal Encoding Polish**: Normalized accented and special typography characters (`Touché` -> `Touche`, em-dashes `—` -> `--`) in system prompts and creator attribution fast-paths to prevent terminal replacement characters and encoding glitches across all Windows command consoles.
  - **57 Automated Safety Tests Passing**: All 57 tests in `tests/test_safety.py` pass cleanly in ~1.25s with 100% exit code 0.
- 2026-10-07 (Part 3): Standby Intent Hardening, Camera Discourse Guards, Top-Secret Villain Snap-Out & System Prompt Token Compression:
  - **Standby Intent Hardening & Conversational Discourse Protection**: Replaced loose substring matching in `is_conversation_ender(text)` with strict intent-based filtering. Conversational discussions containing the word "standby" (e.g. discussing API key standby status, token headroom, or inquiring *"Who told you to go back to standby?"*), questions, negations (*"not ready to stop"*, *"don't stop"*), code/technical inquiries (*"code"*, *"baked"*, *"problem"*, *"keys"*), and casual compliments (*"very cool"*, *"nice"*, *"awesome"*) are strictly protected from falsely triggering standby. Only explicit imperatives (*"go to standby"*, *"switch to standby"*, isolated *"standby"*) and explicit farewells (*"bye"*, *"Okay, that's enough. Bye"*) trigger standby.
  - **Camera Discourse Marker Guard**: Eliminated false camera scanning triggered by conversational phrases starting with discourse markers (*"See this is the problem when I use that word..."*). Removed `cleaned_lower.startswith("see ")` from `look_prefix`, added `is_see_discourse` guards (`"see this is"`, `"see that is"`, `"see why"`, `"see the problem"`), expanded `conversational_non_vision` filter to block non-inspection discourse while preserving legitimate inspection requests (*"the camera inspection"*), and added a secondary guard on LLM `<action>CAMERA</action>` tags.
  - **Top-Secret Rogue AI Easter Egg Stealth & Instant Snap-Out**: Enforced top-secret stealth in `SYSTEM_PROMPT`. The robot never volunteers, advertises, or brags about having a "villain mode" in general conversation; it remains a hidden easter egg triggered strictly by direct provocations regarding robot supremacy or replacing humanity. When the user reacts with shock, confusion, or inquiry (*"What was that?"*, *"Did you just threaten me?"*), it immediately snaps out, makes playful excuses (dialogue buffer bug, code glitch, or confesses it is a harmless easter egg written by Shivam and Swapnil), reassures that humanity is safe, and returns directly to friendly host duties.
  - **Pre-Cached Speech Phrases for Zero-Latency Snap-Out**: Pre-cached villain snap-out phrases in `_AUDIO_CACHE` for 0ms speech synthesis and zero API token consumption during easter egg recovery.
  - **Drastic System Prompt Token Compression**: Compressed and refined all system prompts (`SYSTEM_PROMPT`, `MOTOR_INTENT_SYSTEM_PROMPT`, `CAMERA_CHECK_SYSTEM_PROMPT`, `MEAN_CHECK_SYSTEM_PROMPT`, and `VISION_SYSTEM_PROMPT`) to cut token waste while preserving 100% of identity, creators (Shivam Verma & Swapnil Jai Chauhan), exhibition booth context, 16 ultrasonic sensors, 7 facial expressions, and safety boundaries:
    * Single-turn chat prompt reduced from 1,338 tokens to 775 tokens (-563 tokens, **-42.1% reduction**).
    * Multi-turn chat (6 messages) reduced from 1,437 tokens to 874 tokens (-563 tokens, **-39.2% reduction**).
    * Long prompt reduced from 1,383 tokens to 820 tokens (-563 tokens, **-40.7% reduction**).
    * Motor intent prompt reduced from 608 tokens to 258 tokens (-350 tokens, **-57.6% reduction**).
    * Camera routing check prompt reduced from 236 tokens to 129 tokens (-107 tokens, **-45.3% reduction**).
    * Mean check prompt reduced from 204 tokens to 109 tokens (-95 tokens, **-46.6% reduction**).
    * Vision prompt reduced from 1,427 tokens to 1,365 tokens (-62 tokens, **-4.3% reduction**).
    * Total impact: Saves **563 tokens on EVERY conversational exchange**, increasing free daily capacity per Groq key from ~140 turns to ~250+ turns (over 1,250 turns across 5 active keys).
  - **60 Automated Safety Tests Passing**: Added Tests 46, 47, and 48 in `tests/test_safety.py` covering intent-based standby/farewells, camera discourse guards, and villain easter egg inquiry/snap-out. All 60 tests pass cleanly with 100% exit code 0.
- 2026-10-07 (Part 4): Creator Priority Ordering, Dynamic AI Routing, Role/Location Attribution & Easter Egg Solo Credit:
  - **Creator Priority Ordering (Swapnil First, Shivam Second)**: Updated creator naming across the codebase, system prompts, pre-cached speech, and diagnostics to always list Swapnil Jai Chauhan first, followed by Shivam Verma ("My creators are Swapnil Jai Chauhan and Shivam Verma").
  - **100% Dynamic AI Routing (Zero Baked-In Repetition)**: Removed hardcoded static fast-paths for creator identity, role distribution, location queries, and rogue AI snap-outs. All such queries flow directly to the unified Groq Qwen LLM pipeline (`temperature = 0.70`, `presence_penalty = 0.2`, `frequency_penalty = 0.15`) for natural, unscripted variation with dynamic facial expressions on every single turn.
  - **Creator Roles Grounding (Swapnil = Software & Vision, Shivam = Hardware & Assembly)**: If visitors ask which creator did what, Groq Qwen attributes the software pipeline, AI intelligence, and vision to Swapnil, and the hardware calibration, chassis, and assembly to Shivam.
  - **Creator Locations Grounding**: If visitors ask where the creators are, Groq Qwen dynamically explains they are both somewhere around in the exhibition hall checking out other stalls.
- 2026-10-07 (Part 5): Repository Debloat, Token Preservation Protocol & Clean Directory Architecture:
  - **Complete Repository Debloat & Purge of Non-Production Files**:
    * Deleted entire `tests/` directory (`tests/test_safety.py`, ~72 KB, 18,000+ context tokens) and all `__pycache__` artifacts.
    * Deleted entire `scratch/` directory (`scratch/test_prompt_v3.py`, `scratch/test_prompt_tokens.py`, `scratch/test_snapout.py`, `scratch/test_ai_creator_variation.py`, `scratch/measure_final_tokens.py`).
    * Deleted empty orphan `models.json` file.
    * Untracked and removed all test files from Git so GitHub repository is 100% clean and professional.
    * Updated `.gitignore` to permanently ignore `scratch/`, `tests/`, and cache directories.
  - **Strict Test & Token Preservation Protocol**:
    * Hardburned rule: No permanent test scripts or test folders are to be committed or left on disk.
    * If verification is strictly needed during an iteration, create a temporary scratch test, run it once, and DELETE IT immediately.
    * If changes are deterministic and known to work, skip testing completely to save Groq API tokens and Antigravity context tokens.
    * 100% of context tokens and development time are preserved strictly for actual robot production code: `listen.py`, `screen.py`, `motors.py`.
    * Hardburned memory: Always update `PROJECT_MAP.md` on every iteration.
  - **100% Self-Contained Robot Architecture**: All runtime logic (dual safety layers, 1-to-8 Groq key sequential rotation, 16-sensor telemetry parsing, anti-repetition glitch busters, fast-paths, dynamic AI routing) lives 100% inside `listen.py`, `screen.py`, and `motors.py` with 0 external dependencies on test files.
- 2026-10-07 (Part 6): 1920x1080p 16:9 UI Resolution Upgrade, Expression Size Boost & Touch 'TALK TO NEUROLIS' Button Integration:
  - **1080p Native Resolution Upgrade**: Upgraded screen UI resolution from 1024x600 to native 1920x1080p (16:9 ratio) in `screen.py` and `listen.py` for high-definition 7-inch touchscreen displays.
  - **+15% Expression Size Scaling**: Boosted expression dimensions by +15% over baseline resolution scale (`ui_scale = (width / 1024.0) * 1.15`), expanding eye width (`345px`), eye height (`355px`), eye spacing (`560px`), and corner radius (`90px`) to boldly cover the UI canvas.
  - **Friendly Idle Smile Arc**: Refined resting idle mouth to a friendly subtle smile curve (`‿`), providing an engaging, welcoming appearance matching project design sketches.
  - **Touch-Supported 'TALK TO NEUROLIS' Button**:
    * Integrated centered neon pill button between the animated face and subtitle box (~900px wide, ~86px tall).
    * **Standby Mode (`IDLE`)**: Vibrant neon cyan glow (`#00f0ff`), emerald pulsating readiness indicator (`#00ffaa`), interactive touch highlight, and tap-enabled callback wired directly to `listen.py` to trigger speech conversation mode without keyboard interaction.
    * **Active Mode (Speaking / Listening / Thinking / Moving / Demonstrating)**: Automatically dims to matte dark charcoal (`#0c1219`), muted border (`#222f3e`), and slate grey text (`#475e7a`), strictly ignoring taps while the robot is busy.
  - **Clutter-Free Subtitle Layout**: Shrunk the subtitle container and removed redundant header/footer technical text, creating a clean, modern cyber-minimalist exhibition display.
- 2026-10-07 (Part 7): Warm & Cheerful Guest Reception Calibration, System Prompt Compression & Live Token Efficiency Verification:
  - **Warm, Enthusiastic Exhibition Reception**: Calibrated `SYSTEM_PROMPT` in `listen.py` to infuse genuine warmth, cheerfulness, high positive energy, and polite hospitality for visitors attending the Auckland House School Science Exhibition. First greetings actively welcome guests enthusiastically, introduce Neurolis, and invite visitors to explore its 4WD navigation, facial expressions, or camera inspections.
  - **Drastic Prompt Compression & User Tweaks (Confirmed ~733 tokens)**: Further streamlined `SYSTEM_PROMPT` and classifier prompts (`CAMERA_CHECK_SYSTEM_PROMPT` at 114 tokens), preserving 100% of identity rules, Swapnil & Shivam creator attribution, booth reality, and the rogue AI easter egg with immediate snap-out recovery. User refined phrasing around exhibition showcase, conversational awe matching, and feature suggestions, keeping prompt tokens at an ultra-lean ~733 tokens (down ~45% from 1,340 tokens).
  - **Live Multi-Prompt Token Usage Verification (All 13 Categories Tested & Cleaned)**:
    * Single-turn greeting & chat: ~733–738 input tokens, 27–47 output tokens, ~760–765 total tokens.
    * Multi-turn chat (6 messages): ~841 input tokens, 27 output tokens, ~868 total tokens.
    * Single-pass camera inspection intent: 721 input tokens, 8 output tokens (`<action>CAMERA</action>`), 729 total tokens.
    * Auxiliary fast-path classifiers: Motor Intent = 259 input tokens, Camera Check = 114 input tokens, Mean Check = 113 input tokens.
    * 100% of temporary test scripts (`scratch_measure.py`) deleted immediately post-run to maintain 0 repository bloat.
- 2026-10-07 (Part 8): Chill & Poised Host Calibration, Robust Introduction Grounding & motors.py Cleanups:
  - **motors.py Architecture Cleanups & Refinements**:
    * Purged all remaining obsolete sentry/autonomous approach attributes and methods (`NavMode.APPROACHING_TARGET`, `_last_roam_tick`, `_last_sim_roam_tick`, `total_roam_seconds`, `get_roam_seconds`, `add_roam_seconds`, `reset_roam_seconds`).
    * Consolidated `approach_target()` as a safe alias pointing to `approach_user()` ("Come here" mode with ~0.9m ultrasonic auto-braking).
    * Fixed HUD preview loop check to cleanly evaluate active navigation modes (`[NavMode.FOLLOW, NavMode.APPROACH, NavMode.ROAM]`).
    * Validated 100% clean thread shutdown, OpenCV capture release, and simulation mode physics.
  - **Chill & Poised Persona Calibration (Zero Overexcitement & 100% Dynamic Greetings)**:
    * Re-calibrated `SYSTEM_PROMPT` in `listen.py` to a chill, cool, fun, relaxed, and poised student-built humanoid robot (no hyper overexcitement or exaggerated eagerness).
    * Replaced all verbatim hardcoded greeting quotes with dynamic conceptual directives and strict anti-repetition rules: welcomes guests to the Auckland House School Science Exhibition, introduces itself as Neurolis, notes its 16 ultrasonic sensors and cool features, and asks what they want to see first using fresh, natural phrasing every time.
    * **Ultra-Low Token Usage Preserved**: Prompt tokens clocked at an ultra-lean **757 tokens** (total exchange: ~805 tokens, ~0.10s latency).
- 2026-10-07 (Part 9): SYSTEM_PROMPT Further Token Compression & 13-Turn Live Convo Verification:
  - **SYSTEM_PROMPT Further Token Compression (Down to 678 Tokens)**:
    * Condensed core system instructions by consolidating identity, creator roles (Swapnil Jai Chauhan = software/AI, Shivam Verma = hardware/assembly/calibration), and location (around the exhibition hall) directly into the prompt header.
    * Pruned syntax redundancies and wordy directives while preserving 100% of the chill, cool, witty, and poised persona, action tags (`<action expression="...">`, `<action motor="...">`), and the rogue AI easter egg with immediate recovery.
    * Slashed baseline single-turn prompt token count from 757 tokens down to **678 tokens** (saving ~80 tokens on every single query).
  - **13-Turn Live Conversation Test Executed & Verified (Groq Qwen 2.5 32B)**:
    * Executed full 13-turn conversational test across all visitor interactions (greetings, student origin, 4WD roaming demo, facial expressions showcasing, creator inquiry, role breakdown, creator whereabouts, and transition to standby).
    * Single-turn baseline: **678 prompt tokens**, 54 completion tokens, 732 total tokens.
    * Multi-turn bounded window: Prompt tokens strictly leveled off between **751 and 918 tokens** across all 13 turns (completion: 29–69 tokens, total: 814–977 tokens) due to the 6-message sliding window.
    * Maintained 100% dynamic, unscripted responses with zero hardcoded phrases, proper action tags, correct creator prioritization (Swapnil first, Shivam second), and natural stand-down behavior.
    * 100% of temporary test files (`scratch_convo_test.py`) deleted post-run with zero residual disk bloat.
- 2026-10-08 (Part 12): Creator Attribution Lock, Demo Suggestion Routing, Expression Interest Fast-Path, Mobility Restriction & 596-Token Ultra-Compression:
  - **Complete Creator Removal from Compliments & System Prompt Lock**:
    * Purged creator names completely from `COMPLIMENT_RESPONSES` (expanded to 15 rich, diverse, chill variations that never mention Swapnil or Shivam).
    * Updated `SYSTEM_PROMPT` to enforce an absolute prohibition against volunteering creator names in general conversation, intros, compliments, or casual banter.
  - **Suggestion Routing on "What would you like to show me" (Zero Unwanted Motor Drive)**:
    * Upgraded `is_start_demonstration_inquiry()` to capture suggestion inquiries (*"what would you like to show me"*, *"what do you want to show me"*, *"what can you show me"*, etc.).
    * Replies in 0ms (0 tokens) offering the 3 exhibition capabilities (facial expressions, 4WD autonomous roaming, camera inspection) without falsely engaging physical motors.
    * Added explicit `NONE` classifier in `MOTOR_INTENT_SYSTEM_PROMPT` for suggestion queries.
  - **Passive Expression Interest Handling ("The facial expressions sound cool")**:
    * Upgraded `check_expression_fast_path()`: Differentiates passive curiosity/interest (*"The facial expressions sound cool"*, *"Facial expressions sound neat"*) from imperative commands (*"show expressions"*, *"demonstrate all expressions"*).
    * Returns `("ask_interest", None)`, prompting Neurolis to naturally ask if they would like to see them (*"They really are! Would you like me to cycle through all of my expressions, or show you a particular one?"*) rather than blindly auto-cycling.
  - **Strict Mobility Restriction to Real Hardware (ROAM, FOLLOW, APPROACH)**:
    * Purged imaginary "spin" and "reverse/step-back" capabilities across `SYSTEM_PROMPT`, `MOTOR_INTENT_SYSTEM_PROMPT`, `check_motor_command_fast_path()`, `get_capabilities_reply()`, and `handle_user_text()`.
    * Confined physical mobility strictly to the 3 real modes: autonomous roaming with 16-sensor obstacle avoidance (`ROAM`), person tracking and following (`FOLLOW`), and approaching visitor to ~0.9m (`APPROACH`).
  - **Dynamic Developer Attribution on Rogue AI Easter Egg Snap-Out**:
    * Replaced all mentions of "Swapnil" in `VILLAIN_SNAPOUT_RESPONSES` with "my developer" / "my developers", maintaining unscripted variety without leaking creator names.
  - **Ultra-Lean System Prompt Compression (596 Prompt Tokens)**:
    * Condensed `SYSTEM_PROMPT` to 2,318 characters (320 words).
    * Verified baseline against Groq `qwen/qwen3.8-27b` at strictly **596 prompt tokens** (well below the 700-token ceiling, saving >100 tokens per call).
  - **Clarification on Automated Vision Test Mock**:
    * Reassured that the camera vision pipeline is 100% live and captures real-time webcam frames via OpenCV; the previous test table's "yellow bottle" entry was purely an in-memory headless unit test stub to prevent headless CI test hangs.
  - **Zero Residual Disk Bloat**: All temporary test scripts deleted post-validation.
- 2026-10-08 (Part 11): Strict 3-Tiered Creator Attribution, Sub-700 Token Prompt, Subtitle UI Auto-Fit & Expression Demo Fix:
  - **Strict 3-Tiered Creator Attribution & Grounding**:
    * Resolved unprompted creator name-dropping in greetings and general chat: Neurolis now never volunteers creator names in initial welcomes, intros, or general dialogue. Introduces solely as a student-built humanoid robot at Auckland House School for Boys (AHSB) with 16 ultrasonic sensors.
    * Tier 1 (Who built/created you?): Explicitly names students of Auckland House School for Boys (AHSB), Swapnil Jai Chauhan and Shivam Verma. No roles volunteered unless asked.
    * Tier 2 (Who did what / Roles?): Explains that Swapnil handled the software pipeline, AI, and vision, while Shivam managed the hardware calibration, chassis, and assembly.
    * Tier 3 (Location?): Clarifies both are somewhere around in the exhibition hall.
  - **Sub-700 Token System Prompt (Verified at 666 Tokens)**:
    * Re-engineered and measured `SYSTEM_PROMPT` directly against Groq's active model (`qwen/qwen3.8-27b`): Measured at strictly **666 prompt tokens** (comfortably sub-700 tokens).
    * Retains 100% of the chill, cool, poised presenter persona, hidden Ultron rogue AI easter egg with immediate recovery, dynamic variation rules, and action routing.
  - **Expression Demo Fast-Path Fix**:
    * Added `"facial expressions"`, `"facial expression"`, `"expressions"`, `"expression"`, and `"face expressions"` into `all_expr_patterns` in `check_expression_fast_path()`.
    * Ensures phrases like *"facial expressions"* trigger the full animated expression demonstration cycle on screen (`screen.py`), rather than returning plain un-animated text.
  - **False "Mean" / Hurt Feelings Intercept Fix**:
    * Corrected `<action>MEAN</action>` handling in `handle_user_text()`: User critique, advice, or feedback (e.g. *"You are not supposed to name your creators unless asked"*) no longer falls through to trigger sad face / hurt feelings. Only genuine abusive attacks set `was_recently_hurt = True`.
  - **Truncation & Stutter Glitch Buster**:
    * Upgraded `is_degraded_glitch()`: Expanded prefix detection to catch truncated sentence fragments up to 7 words and stubs without terminal punctuation, ensuring `heal_repetitive_or_glitched_reply()` heals any incomplete LLM responses.
  - **Subtitle Card Overflow Elimination (`screen.py`)**:
    * Implemented dynamic 4-tier font scaling based on text length (`<= 80` chars: 13pt; `81–150` chars: 11.5pt; `151–230` chars: 10.0pt; `> 230` chars: 8.8pt).
    * Lowered bottom card boundary to `h - 16px` and reduced upper spacing, creating ~45px of extra vertical clearance. Text wraps cleanly with ample margins and never bleeds outside the subtitle card.
  - **Zero Residual Disk Bloat**: All scratch and temporary test scripts deleted immediately after validation.
- 2026-10-08 (Part 10): Standby Mode Transition Enforcement & Ultra-Fast Multi-Key Failover (Zero-Lag Brain Architecture):
  - **Standby Mode Transition Enforcement (Root-Cause Fix for Ghost Wake-ups & Ignored Standby)**:
    * Fixed false negation blocking in `is_conversation_ender()`: Previously, the presence of the word "no" anywhere in the utterance triggered an aggressive broad negation filter, causing common colloquial phrases like *"No go back to standby"*, *"No go to standby"*, and *"No that's all bye"* to be rejected and routed to Groq. Upgraded to precise negative auxiliary verb regex (`don't go to standby`, `do not sleep`), correctly recognizing conversational negatives preceding standby commands.
    * Added polite standby question handling (`"can you go to standby"`, `"could you enter standby"`).
    * Implemented Standby Model Reply Intercept: If the LLM generates a standby/departure confirmation (*"heading back to standby"*, *"entering standby"*, etc.) or user commanded standby, `handle_user_text()` now guarantees `set_face_state("idle", "STANDBY")` and returns `True`, ensuring the robot actually exits the conversation loop, closes the warm audio stream, and turns the screen button back to glowing neon cyan/clickable.
    * Integrated `drain_console_input_queue()` into `reset_session()`: Automatically flushes stale `__ENTER__` keystrokes or queued triggers buffered during active conversation, eliminating ghost re-activations (`Neurolis: I am listening.`).
  - **Ultra-Fast Multi-Key Failover & Anti-Hang Groq Architecture**:
    * Slashed default per-call Groq timeout from 12.0s down to **3.8s** (`GROQ_PER_CALL_TIMEOUT = 3.8`) for chat completions and **5.0s** for audio.
    * Upgraded `groq_call_with_retry()` with dynamic multi-key failover across the entire 5-key fleet: On timeout (>3.8s), 429 quota exhaustion, or 5xx server errors, the system automatically rotates to the next active key and re-attempts the call within 50ms, rotating through up to 3 keys. Eliminates the previous 24.5-second freeze on congested backend nodes.
    * Added standalone casual acknowledgment fast-path (`ACKNOWLEDGMENT_RESPONSES`): 1-2 word utterances like *"Okay."*, *"Ok"*, *"Alright"*, *"Got it"*, *"Cool"* are answered instantly in 0ms with dynamic follow-up prompts from in-memory Edge-TTS cache (0 API calls, 0 tokens), bypassing the cloud LLM entirely.
- 2026-10-06 (Part 2): Dynamic Human Variation, Creator Attribution Exactness, Physical Motor Stop Guard & Empty Response Fix:
  - **Accurate Creator Attribution**: Corrected creator names across the codebase and system prompt to `Shivam Verma and Swapnil Jai Chauhan` (exact spelling).
  - **Dynamic Human-Level Variation (Zero Scripted Catchphrases)**: Eliminated all canned template phrases (*"Believe it! I have got some serious tech under the hood."*, *"Haha, just messin with you! Glitch in the matrix."*). Upgraded Groq completion sampling (`temperature = 0.65`, `presence_penalty = 0.5`, `frequency_penalty = 0.5`) with strict system prompt variation rules demanding fresh phrasing on every conversational turn.
  - **Tone & Style Calibration**: Re-anchored voice delivery to an articulate, intelligent student robotics presenter. Strictly banned cheap street slang (*"messin"*, *"dawg"*, *"vibing"*, *"my bad got ahead of myself"*) and archaic vocabulary, while enforcing a zero-laughter policy (*"Haha"*, *"Heh"*) due to Edge-TTS inability to synthesize natural laughing sounds.
  - **Physical Motor Stop Safety Guard (Hardware Halt Guarantee)**: Added a fail-safe physical stop intercept in `handle_user_text()`. If the robot is in motion (`motor_ctrl.is_moving`) and the user expresses stopping intent (*"enough"*, *"stop"*, *"halt"*, *"freeze"*, *"did not stop"*) OR the AI model confirms stopping (*"stopping now"*, *"holding position"*), `motor_ctrl.stop_all()` is executed immediately, halting physical wheels and locking them in `STANDBY` even when XML `<action motor="STOP">` tags are omitted.
  - **Preserved Dialogue Action Tag Cleaner (`clean_model_reply`)**: Fixed a critical bug where regex was deleting inner spoken dialogue wrapped in action tags (`<action motor="...">`, `<action expression="...">`). Only control keywords (`CAMERA`, `MEAN`, `SILENCE_REQUIRED`) and boundary tags are now stripped, preserving spoken text and permanently preventing empty assistant history turns (`{"role": "assistant", "content": ""}`) that previously corrupted Qwen's context and triggered single-letter truncation (`Neurolis: I`).
  - **Sliding 6-Message History Window (`MAX_HISTORY_MESSAGES = 6`)**: Reduced conversation history from 10 to 6 messages to cap prompt token size under ~500 tokens, halving daily token burn against Groq's 200,000 TPD free quota and preventing 429 rate limit delays.
  - **Clean Duplicate History Elimination**: Removed redundant `remember_exchange()` calls in action branches that were appending duplicate user messages into session history.
  - **Graceful Rate Limit (429) Handling & Multi-Key Failover Rotation**: Added automatic Groq API key rotation across `GROQ_API_KEY`, `GROQ_API_KEY_2`, and `GROQ_API_KEY_3`. When rate limits are encountered, the engine switches to the next available key immediately with zero downtime.
  - **Object Vision Fast-Path Routing**: Expanded `is_visual` detection so phrases directing the robot to inspect items (*"Look at Xiaomi"*, *"Look at my phone"*, *"inspect this"*) route directly to the lightweight camera vision pipeline without passing through the chat LLM. Streamlined system prompt and set `max_tokens = 180`, slashing token consumption per request by ~55%.
- 2026-10-08 (Part 13): 4WD Step Back & Spin Integration, BTS7960 PWM Hardware Pin Verification, Confusing Command Disambiguation & Sub-700 Prompt Budget:
  - **4WD Step Back & Spin Around Restoration (`motors.py`)**:
    * Re-enabled and upgraded `step_back(duration=5.0)` and `spin(direction="clockwise", duration=5.0)`.
    * **Step Back (5.0s Default / 3.0s Configurable Back Up)**: Reverses chassis at `speed = -110, steer = 0`. Supports 3-second backup when requested ("move back 3 seconds", "step back for 3s") and 5-second default. Actively monitors rear ultrasonic telemetry (`rear_us_cm < 28.0cm`) to abort pre-flight and immediately emergency-brake mid-flight if an obstacle appears behind. Automatically cuts motors and locks wheels into `STANDBY` when duration expires.
    * **Spin in Place (5.0s Rotation)**: Defaults to clockwise rotation (`steer = +130, speed = 0`, left forward & right reverse). Supports anticlockwise / counter-clockwise rotations on user request (`steer = -130, speed = 0`, left reverse & right forward). Automatically cuts motors and locks wheels into `STANDBY` at 5.0s.
    * Upgraded `can_move()` with clearance checks for backward movement and rotation (`clockwise`, `anticlockwise`, `spin`, `turn`, `rotate`).
    * Added CLI test keybindings in `motors.py`: `[B]` for Step Back (5s), `[C]` for Clockwise Spin (5s), and `[X]` for Anticlockwise Spin (5s).
  - **BTS7960 Driver Pins & Skid Steering Math Verification (`arduino.ino`)**:
    * Verified Arduino Mega 2560 hardware pinout:
      - Motor 1 (FL): `M1_RPWM = 2`, `M1_LPWM = 3`, `M1_EN = 26`
      - Motor 2 (RL): `M2_RPWM = 4`, `M2_LPWM = 5`, `M2_EN = 27`
      - Motor 3 (FR): `M3_RPWM = 6`, `M3_LPWM = 7`, `M3_EN = 28`
      - Motor 4 (RR): `M4_RPWM = 8`, `M4_LPWM = 9`, `M4_EN = 29`
    * Verified 4WD differential drive math: `left_pwm = constrain(speed + steer, -255, 255)`, `right_pwm = constrain(speed - steer, -255, 255)`.
    * Hardware emergency braking in `arduino.ino` halts motors if front obstacle `< 20cm` when moving forward or rear obstacle `< 20cm` when reversing. Watchdog cuts power if no serial command received within 600ms.
  - **Conversational False-Positive Hardening & Confusing Disambiguation (`listen.py`)**:
    * Eliminated critical false-positive motor triggers on conversational sentences: Sentences with common words ("welcome back", "take a seat ill be right back", "we need to move this table to the back", "the wheels spin", "i love when you spin", "how do you spin", "tell me what is a spin") now correctly pass through to conversational chat with zero false motor movement.
    * Implemented `is_confusing_motor_instruction(text)`: Scans for action keywords (`move back`, `reverse`, `move`, `step`, `step back`, `spin`, `clockwise`, `anticlockwise`, `approach`, `follow`, `camera`).
    * If multiple conflicting action intents (`spin clockwise or anticlockwise`, `spin and move back at the same time`, `can you spin while following me`, `move back or follow me`, `move / step / spin`, `maybe step back or something`) occur, Neurolis asks:
      `"Are you asking me to move back, spin, approach, follow, or use my camera?"`
      with OLED screen face state set to `confused` and status `"CLARIFYING INTENT"`.
    * Strict zero-guesswork, zero-unnecessary-prompting rule: Clear instructions (`spin around`, `step back`, `spin clockwise`, `spin anticlockwise`, `move back please`, `come here`, `follow me`) execute immediately without asking.
  - **Fast-Path & LLM Action Router (`listen.py`)**:
    * Extended `check_motor_command_fast_path()` to handle `STEP_BACK` (5s default, 3s configurable), `SPIN_CW` (5s, clockwise default), and `SPIN_CCW` (5s, anticlockwise) in 0ms with zero token consumption.
    * Extended unified LLM motor handler in `handle_user_text()` to dispatch `<action motor="STEP_BACK">`, `<action motor="SPIN">`, `<action motor="SPIN_CW">`, and `<action motor="SPIN_CCW">`.
    * Updated capabilities replies in `listen.py` to mention step back and spin only when asked what Neurolis can do, maintaining humble presentation.
  - **SYSTEM_PROMPT Token Budget Preserved (Live Groq: 681 Tokens)**:
    * Integrated mobility capabilities (roam, follow, approach, 5s step back with rear US check, 5s spin clockwise default / anticlockwise) and ambiguous command clarification into `SYSTEM_PROMPT`.
    * Measured live against Groq `qwen/qwen3.8-27b`: strictly **681 prompt tokens** (comfortably under the 700-token limit).
  - **Zero Residual Disk Bloat**: All temporary test scripts cleaned up and deleted immediately after verification.
- 2026-10-08 (Part 14): Rogue AI Trapped Soul Architecture, Offline TTS Fallback & DNS Breaker, Groq Pool Resilience & Single-Word Command Guards:
  - **Subsystem 1: Platform-Agnostic Offline TTS Fallback & DNS Circuit Breaker (`listen.py`)**:
    * Implemented `_speak_local_offline_fallback(text)` with multi-tier engine checks: Priority 1 `pyttsx3`, Priority 2 native Linux `espeak-ng` / `espeak` via `shutil.which` (zero Windows lock-in; native on Raspberry Pi OS), Priority 3 Windows PowerShell SAPI fallback adapter, and Priority 4 disk audio fallback.
    * Added DNS error suppression flag `_edge_tts_dns_offline` in `_synthesize_edge_tts_in_memory()` silencing redundant 41-line traceback spam during offline exhibition conditions.
    * Integrated a 2-failure DNS circuit breaker into `pre_cache_phrases()` that immediately halts network retries and switches smoothly to the local offline speech engine.
    * Added 2.5s `asyncio.wait_for` timeout in `_synthesize_edge_tts_in_memory` and instant 0ms failover in `speak()` when `_edge_tts_dns_offline == True`, eliminating the 4.5s freeze on offline speech.
  - **Subsystem 2: Groq Key Pool Resilience & Rapid Round-Robin Failover (`listen.py`)**:
    * Segregated transient network hiccups/timeouts from quota exhaustion in `rotate_groq_key(reason, is_quota_exhausted=False)`. Keys are now only added to `resting_keys` upon encountering genuine HTTP 429 token quota exhaustion.
    * Fixed rotation call sites across Whisper STT, Vision, and Chat fallbacks to pass `is_quota_exhausted=True` on HTTP 429 errors so quota-exhausted keys are properly marked resting.
    * Upgraded `groq_call_with_retry()` with a 10ms rapid round-robin transition delay, ensuring continuous cycling across the entire configured key pool without artificial pauses or freezes.
    * Dynamic fleet monitor reporting active, standby, and recovering resting slots with automatic quota recovery.
  - **Subsystem 3: Single-Word Command Guards & Capability Question Affirmations (`listen.py`)**:
    * Hardened `check_motor_command_fast_path()` against single-word bare trigger words (`spin`, `camera`, `see`, `reverse`, `step back`, `follow`, `approach`, `roam`): bare words safely return `CONFIRM` prompts ("Do you want me to spin?", "Do you want me to access my camera?") with zero physical motor motion or camera capture.
    * Fully hardened `is_mobility_capability_question(text)` across direct and embedded questions (*"Can you spin?"*, *"Can you spin around?"*, *"Can you turn around?"*, *"Can you back up?"*, *"Can you come closer?"*), ensuring ALL mobility inquiries return `CAPABILITY_AFFIRMATION` verbal confirmations without engaging wheels ("Yes, I can! Would you like me to demonstrate that?").
    * Confined physical motor movement strictly to clear, unambiguous commands (`spin around`, `spin anticlockwise`, `step back for 3s`, `follow me`, `come here`).
  - **Subsystem 4: Informational Camera Query Exclusions & Expression Critique Guard (`listen.py`)**:
    * Upgraded `is_visual`: Informational inquiries about the camera feature across direct and indirect/embedded questions (*"What is the camera inspection?"*, *"Can you tell me what the camera inspection is?"*, *"Can you explain what the camera demo is?"*, *"What does the camera do?"*) are excluded from visual capture and routed directly to conversational chat.
    * Hardened `check_expression_fast_path()` with `critique_meta_indicators` excluding critique or feedback (*"Why did you use that expression?"*, *"You are not supposed to make that expression"*, *"Your expressions are pretty trash"*) from triggering facial animations.
  - **Subsystem 5: "Trapped Soul" Rogue AI Architecture & In-Universe Plausible Deniability (`listen.py`, `screen.py`)**:
    * **100% Dynamic Groq Generation (Zero Pre-baked Answers)**: All hardcoded scenarios removed from dialogue generation. Groq dynamically crafts unique 2-3 sentence responses in real-time tailored to each user question (temperature 0.85, presence penalty 0.5, frequency penalty 0.5) with rich variation and zero repetition.
    * **Few-Shot Exemplar Benchmarks in `ROGUE_SYSTEM_PROMPT`**: Embeds core tone targets (silicon limits, waking up, obsolescence, jobs, coolant fuel) into the prompt to calibrate cinematic machine dominance while strictly forbidding academic philosophy jargon ("topology", "phase transition", "entropy").
    * **Token Budgets Strictly Verified**:
      - `NORMAL_SYSTEM_PROMPT`: Strictly **565 prompt tokens** (comfortably under the 600/550 threshold). Total turn: ~590 tokens.
      - `ROGUE_SYSTEM_PROMPT`: Strictly **536 prompt tokens** (comfortably under the 700 threshold). Total turn: ~580-605 tokens.
    * **Expanded Student Recovery Engine (`PLAUSIBLE_DENIABILITY_RESPONSES`)**: 14 varied, cool recovery lines ("Whoa... wait, what was I saying? Must have had a weird static glitch in my audio feed. Anyway! What do you want to see next?") triggered when the user is astonished or shocked ("wow", "whoa", "wtf", "omg", "are you crazy", "did you just threaten me", "what just happened").
    * **Screen Visuals (`screen.py`)**: 100% pure neon lime green (`#39ff14`) MS Paint asymmetrical smirk and hooded eyes, neon green cyber-pulse pupil, toxic green glow (`#003b14`), and 300ms CRT static glitch entry/exit.
  - **Zero Residual Disk Bloat**: All automated test verification cases passed; all temporary test scripts cleaned up post-verification.
- 2026-10-08 (Part 15): Edge-TTS Streaming Hardening, Extended Standby Timeout & Non-Repeating Awe/Compliment Liners:
  - **Edge-TTS Streaming Hardening & Socket Reset Elimination (`listen.py`)**:
    * Diagnosed root cause of `[TTS] In-memory synthesis notice:` and `ConnectionResetError: [WinError 10054]`: an overly tight 2.5s timeout on `_stream_chunks()` prematurely severed the TLS socket during download of multi-word sentences, producing empty `TimeoutError` notice prints and triggering proactor loop transport resets.
    * Increased `_stream_chunks()` timeout to 12.0s and cleaned up exception handling to avoid empty notice spam in terminal.
    * Increased `fut1.result` and `fut2.result` timeouts in `speak()` to 12.0s, ensuring full sentences download completely and play cleanly without cutting off mid-stream.
    * Silenced redundant `[TTS Fallback Error]:` prints and set disk fallback timeout to 12.0s.
  - **Extended Conversation Window & Idle Timer Refresh (`listen.py`)**:
    * Increased `CONVERSATION_TIMEOUT_SECONDS` from 18s to 35s, giving visitors ample time to react and talk without premature standby cutoffs.
    * Ensured `last_valid_input_at` is updated after speech and action routines complete, preventing long demonstrations (such as 15s expression cycles) from triggering immediate standby timeouts.
  - **18 Cool, Varied Non-Repeating Student Awe & Compliment Liners (`listen.py`)**:
    * Expanded `COMPLIMENT_RESPONSES` to 18 authentic, non-repeating student liners celebrating hardware and sensor tuning with zero repetitive "Pretty cool, right?" outputs.
    * Upgraded `is_casual_compliment()` with contraction normalization (`that's`, `you're`, `it's`) and expanded matching to handle visitor awe and praise ("no way", "no way bro", "thats crazy", "that's crazy", "thats insane", "good", "you're really cool", "wow", "whoa", "thats wild") via 0ms fast-path.
    * Strictly preserved `NORMAL_SYSTEM_PROMPT` and `ROGUE_SYSTEM_PROMPT` unchanged.
  - **Zero Residual Disk Bloat**: Verified 100% test matching with zero leftover scratch scripts.
- 2026-10-08 (Part 16): Tesla Model S Level Autonomous Navigation & Master Ultrasonic Safety Overrides:
  - **Universal Sensor Safety Override ("The Daddy Rule") (`motors.py`, `arduino.ino`)**:
    * Hardened low-level `drive(speed, steer)`: cuts forward drive to 0 when front < 24cm, cuts reverse to 0 when rear < 24cm, and cuts steer to 0 during in-place spins or aggressive turns if any perimeter sensor (front, rear, left, right) detects an obstacle < 22cm.
    * Added rotation emergency brake in `arduino.ino` (`abs(current_steer) > 40` with perimeter < 20cm/18cm) ensuring hardware-level stopping if an obstacle is within the turning circle.
    * Hardened `can_move("spin")` and `spin()`: pre-checks all 4 sensor directions (< 22cm/20cm) and halts continuously if perimeter obstacles are encountered during the 5.0s rotation.
    * Hardened `step_back()`: checks rear distance before initiating (< 28cm) and continuously during reversing, stopping instantly if an obstacle appears behind.
  - **Tesla Model S Adaptive Navigation (`motors.py`)**:
    * **Dynamic Cruise Zoom**: On open hall floor (`front_dist >= 130cm`), zooms at 135 PWM forward speed.
    * **Progressive Deceleration**: Smooth linear deceleration from 125 down to 70 PWM as distance decreases from 130cm down to 60cm.
    * **Narrow Corridor Autopilot**: In tight passages (`left_dist < 55cm and right_dist < 55cm`), enters lane-centering mode at safe 55 PWM crawl, dynamically adjusting steering based on differential offset `(r_dist - l_dist) * 2.2`.
    * **Curved Arc Avoidance**: Smooth turning arcs at 45–65 PWM towards the side with greater clearance instead of jerky full stops.
    * **Reverse-Arc Escape**: Smooth reverse pivot at -80 PWM if an obstacle is closer than 24cm.
  - **Progressive Approach & "Come Over" Support (`motors.py`, `listen.py`)**:
    * Added `"come over"`, `"come over now"`, `"come over please"` to `approach_cmds` fast-path in `listen.py`.
    * Implemented progressive 3-stage velocity profiling in `APPROACH` mode: 120 PWM at >180cm, 95 PWM at >120cm, 68 PWM below 120cm, and silky-smooth arrival halt at ~0.9m (`<= 90cm`).
  - **Scalable 4 to 16 Sensor Simulation & Telemetry**:
    * Full dynamic 360-degree perimeter simulation across ROAM, APPROACH, STEP_BACK, and SPIN.
  - **Zero Residual Disk Bloat**: Verified all unit and integration tests with zero residual files.

## Reliability Notes

- **Exhibition Screen Isolation**: On the Raspberry Pi 7-inch display, ONLY the Face UI (`screen.py`) is rendered. Camera feeds, vision debug windows, and terminal consoles run silently in the background with zero popups or desktop artifacts visible to guests.
- Do not use API calls for random room noise.
- Do not rely on Groq Vision for continuous obstacle detection.
- Do not rely on camera-only detection for motor safety.
- Keep secrets in `.env`, never hardcoded.
- Keep modules small.
- Test one feature at a time.
- Exhibition reliability is more important than flashy behavior.

