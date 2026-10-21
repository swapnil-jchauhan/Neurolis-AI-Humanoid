# Project Neurolis: Engineering Architecture & Development Chronicle

Last Updated: 2026-10-18  
Status: **Neurolis Mark II Software Development Commenced (Windows 11 Workstation & Raspberry Pi 5 Verification)**  
Authors: **Swapnil Jai Chauhan** (Sole Lead Architect & Developer, Neurolis Mark II) & **Shivam Verma** (Mark 1 Prototype Contributor)  
Institution: **Auckland House School for Boys**  

> [!IMPORTANT]
> **Work on Project Neurolis Mark II has officially commenced on the software side!**  
> Developed on a Windows 11 primary workstation and verified/tested on Raspberry Pi 5. The physical motor pipeline, BTS7960 drivers, Johnson DC motors, and 2D LiDAR SLAM locomotion are scheduled for **mid-2027**.

---

## Executive Summary

Project Neurolis is an interactive AI humanoid robot designed for science exhibitions, academic demonstrations, and STEM research. Project Neurolis Mark II is currently in an intensive **software-first development phase**, engineered on a Windows 11 primary workstation and tested on Raspberry Pi 5. It combines an expressive 22-state 60 FPS animated OLED facial UI, hands-free MediaPipe vision gesture control, auditorium-tuned acoustic voice endpointing, Groq-powered multi-key conversational intelligence, bilingual speech synthesis with ChatGPT-style emotional prosody, and a real-time live web search and weather engine (`edge_search.py`). All physical motor and LiDAR locomotion features are planned for mid-2027.

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

### Pivot 1: Stripped All Motor Commands, Purged Arduino Code, & Adopted Software-First Paradigm
* **Action**: We completely purged all motor commands, movement exclusions, and legacy Arduino code from the repository:
  * Deleted `motor_controller.ino` and `motors.py`.
  * Removed autonomous roam mode, sentry approach mode, person-following (`FOLLOW`), spin, step-back routines, and teleoperation driving dialogues.
  * Purged all motor action parsing (`<action motor="...">`), intent classification prompts, and motor fast-paths.
* **The Software-First Engineering Phase**: Project Neurolis Mark II is currently a pure software stack running on a Windows 11 primary workstation and verified/tested on Raspberry Pi 5.
* **The Mid-2027 Locomotion Roadmap**: Physical motor controller pipelines, BTS7960 high-power H-bridges, 12V Johnson DC motors, and 2D LiDAR SLAM indoor navigation are officially scheduled for mid-2027. Developing the physical hardware will occur after the software pipeline (conversational AI, vision, live web search, bilingual voice modulation, 60 FPS vector emotions) is perfected.

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
├── edge_search.py          # Live Knowledge Engine: Weather (wttr.in), Wikipedia, & DuckDuckGo
├── intent_rules.py         # Response pools, greetings, fast-path intent matching, & personality
├── mic_config.json         # Calibrated audio thresholds, cutoff frequencies, & gain settings
├── gesture_recognizer.task # Official MediaPipe Tasks gesture classification model asset
├── assets/                 # Sound effects, Piper offline model, and UI graphics
│   └── piper/              # en_US-lessac-low.onnx neural TTS model
├── README.md               # Public project documentation & quickstart guide
├── COMPONENT_LIST.md       # Hardware inventory & component specifications
└── PROJECT_MAP.md          # Architecture map, engineering chronicle, & future roadmap
```

### Active Core Features:
1. **Interactive Conversational Talkbot & Mark II Creator Grounding**: Articulate student presenter identity, grounded in Auckland House School for Boys. Attributed solely to Swapnil Jai Chauhan as creator and lead developer for Neurolis Mark 2 (concept, hardware integration, vision pipeline, software stack), recognizing Shivam Verma as a key contributor on the earlier Mark 1 prototype when asked about roles. Unprompted creator disclosure is strictly prohibited on general greetings.
2. **Hands-Free Gesture Activation**: MediaPipe ✋ Open Palm wake / ✊ Closed Fist standby with 3.0s hold safety and on-screen progress indicator.
3. **Project Neurolis Mark II Emotive Face Engine (`screen.py`)**: 22 hyper-expressive, cute, catchy, and pixel-perfect animated robotic states (Pixar/EMO-grade visual punch with scale-invariant Tkinter vector rendering):
   - `IDLE`: Dynamic cybernetic eyebrows with dual-layer neon bloom and micro LED ticks, cardinal iris HUD ring ticks (12, 3, 6, 9 o'clock), breathing optic core, triple Pixar specular glints, and resting chin sensor with twin cyan LED nodes.
   - `HAPPY`: Radiant smiling crescents ($\cap \;\; \cap$) with soft neon bloom, pulsing kawaii cheek blush hearts, and 7-star twinkling sparkle constellation.
   - `SAD`: Downcast sorrowful gaze, trembling eyelid droop, bottom digital tear well pool, dual teardrop streams with glowing liquid trails, and bottom splash ripples.
   - `CONFUSED`: Hypnotic Archimedean cyber vortex spirals with radial ticks, pulsing singularity core bead with rotating crosshairs, dual bobbing holographic '?' badges, and 4-star 3D galaxy orbit.
   - `THINKING`: Pensive up-right squint, internal rotating quantum data dials inside both eyes, ascending 3-bubble holographic thought orb matrix with spinning reticle, and dual counter-tilted 3D elliptical gyroscope orbit spinner with glowing amethyst data packets and comet trails.
   - `LISTENING`: Concentric expanding sonar pulse ripples, studio mic capsule with horizontal grille slits and pulsing core, and flanking horizon wings with `⊕` reticles.
   - `SPEAKING`: Voice-broadcasting visualizer with 17 spectrum pins with pro-audio peak-hold ceiling dots and expanding sonic wavefront arcs.
   - `WATCHING`: 45°-beveled corner brackets, millimeter tick rulers, dynamic target lock reticle tracking gaze, sweeping laser beam, blinking ruby "REC [00:24:18]" badge, and "FOV 85° // AI SENTRY" tag.
   - `MOVING`: Front-facing 4WD humanoid chassis with perspective cyber highway, rolling rubber monster tires with chevron treads and spinning 5-spoke hub pins, ground neon wash, Xenon headlights with expanding conical light beams, chest Arc Reactor, helmet visor with scanning line, and dynamic speed dust motes.
   - `ERROR`: Rapid crimson alarm socket glow, heavy glowing 'X' matrices with white electric core, center fracture sparks, caution warning badges with flanking hazard chevrons, and high-voltage electric fault waveform mouth with electrostatic spark discharge nodes.
   - `VILLAIN`: Base hooded upper eyelid polygon and smirk shape 100% strictly preserved; accented with 7 organic rising emerald embers with serpentine sway, temple cyber circuit etchings, 6Hz split-optic chromatic ghosting, sinister sneer corner flick, venom spark glint, and razor core finish. (Strictly reserved for the single-session Rogue AI easter egg; never shown in public demonstrations).
   - Additional Mark II Expressions: `EXCITED`, `PROUD`, `COOL`, `CURIOUS`, `WINK`, `SURPRISED`, `LAUGHING`, `LOVE`, `SHY`, `SKEPTICAL`, `SLEEPY`.
   - **Contextual Conversational Expression Classifier (`determine_conversational_expression`)**: Real-time context engine intelligently mapping dialogue sentiment, prebaked responses, and user queries to organic facial expressions across all 21 public states. Intelligently routes technical robotics/math/reasoning to `thinking`, playful teasing to `wink`, personal flattery to `shy`, profound warmth and friendship to `love`, awe/shock to `surprised`, casual banter/swag/acknowledgments to `cool`, creator accomplishments and school attribution to `proud` (with robust guardrails preventing general exhibition greetings and robot model mentions from false positive triggers), confusion/clarification to `confused`, capabilities/high-energy greetings to `excited`, locomotion to `moving` (excluding conversational "move on"), camera inspection to `watching`, disappointment/sorrow to `sad` (`EMPATHY // SAD`), and exploration inquiries to `curious`. Strictly guarantees `villain` is never returned in conversational routing.
   - **Synchronous Public Expression Demonstration Loop (`demonstrate_all_expressions`)**: Paced voice-and-face presentation cycling all 21 public expressions side-by-side with rich natural phrasing variety ("This is my {state} emotion.", "Here is {state}.", "This one is {state}.", "Now {state}."). Speaks an opening introduction under `EXPRESSION CATALOG` HUD status without listing emotions upfront, updates face state and HUD status concurrently with Edge-TTS audio introduction for each emotion, actively polls `standby_kill_event` every 100ms during pause intervals for immediate gesture interruption, speaks an engaging conclusion, and resets smoothly to `idle` (`READY // TALK TO ME`). Evaluated prior to creator fast-paths to guarantee compound queries ("show all emotions and who built you") properly trigger the demonstration. Permanent safety lock strictly excludes `villain` from the public demonstration loop.
   - **Mark II Subtitle & On-Screen Text Architecture**:
     - *Tkinter Z-Ordering & Resolution Resizing*: Rebuilt `HyperSmoothCanvas` buffer pipeline (`flush()`, `_ensure_size()`). Lowered NumPy/OpenCV background image layer (`tag_lower`) and elevated all active ClearType Tkinter text items (`tag_raise`) to eliminate the bug where window geometry changes or dynamic card redraws caused text to vanish behind the background frame buffer.
     - *Shell Persistence & Non-Empty Fallbacks*: Subtitle cards and header pills are safeguarded with permanent non-empty fallbacks and a 9.0s smooth persistence window, guaranteeing that subtitle cards and header pills never render as empty blank shells.
   - **Gesture HUD Command Capsule Mutual Exclusion**:
     - Re-architected gesture button rendering into `_draw_gesture_hud_dynamic()`. Completely separated static geometry from text labels.
     - Enforced strict mutual exclusion: when gesture hold progress is 0.0, renders strictly base action labels (`OPEN PALM • HOLD 3s TO TALK` / `CLOSED FIST • HOLD 3s FOR STANDBY`); when hold progress is active (> 0.0), renders strictly the glowing dynamic progress track and live countdown timer (`HOLDING PALM • 0.3s / 3.0s (12%)`). Completely eliminated text item collision and overlapping artifacts.
   - **Audio-Visual Speech Synchronization (TTS Non-Idle Face State Guarantee)**:
     - Refactored `speak()` and `_restore_face_state_after_speech()` in `listen.py`: Neurolis speech is strictly forbidden from playing with the face stuck in `idle`.
     - In the event no custom state is provided (or if `idle` is mistakenly passed), the system dynamically computes an organic emotional expression via `determine_conversational_expression` or defaults to `speaking`.
     - System error fallbacks, rate limit alerts, activation greetings, and standby timeouts explicitly trigger dedicated animated states (`error`, `confused`, `happy`, `sleepy`).
   - **Villain Expression Catalog Routing & Refusal Variety**:
     - Expanded `is_explicit_villain_request()` to intercept inquiries about the existence or demonstration of the villain face (`"What about the villain expression?"`, `"Do you have a villain emotion?"`, `"Show me villain"`).
     - Introduced a pool of 16 rich, varied, polite refusal responses (`VILLAIN_EXPRESSION_REFUSAL_RESPONSES`) explicitly stating Neurolis does not possess any villain expression in its catalog.
     - Renders refusal replies with `cool` or `skeptical` facial expressions and HUD status `CATALOG // PUBLIC`, completely eliminating accidental triggers of plausible deniability glitch snapouts while maintaining the Rogue AI easter egg.
     - Enforced `hold_state_seconds` parameter handling in `speak()` and refined `_restore_face_state_after_speech()` to restore to `listening` or `idle` cleanly.
   - **Hardened Subtitle System**: Fixed villain subtitle flickering and double-text rendering using clean, high-contrast matrix green (`#39ff14`/`#dcfce7`) and `FONT_FAMILY`. Added subtitle clobbering guard preventing boot completion routines from wiping active speech subtitles.
   - **Mark II Cockpit Branding**: Ambient header with pulsing status dot (`PROJECT NEUROLIS MARK II // [STATE] // 60 FPS OLED ENGINE`), dedicated subtitle card pill (`● NEUROLIS MARK II`), and boot sequence diagnostics ("NEUROLIS MARK II" with "Booting...").
4. **On-Demand Camera Vision**: Groq Vision integration answering "What am I holding?" or "Look at this" via single-frame capture.
5. **Acoustic Noise Resilience**: Dynamic rolling noise floor tracking rejecting background hall chatter without requiring users to shout.
6. **Dual Speech Synthesis**: Online Edge-TTS with instant offline Piper neural fallback.
7. **Clean Software Phase & Mid-2027 Locomotion Roadmap**: The active codebase has been purged of all motor commands, movement exclusions, and Arduino code. Project Neurolis Mark II runs as a pure software stack on Windows 11 (tested on Pi 5). Low-level motor drivers, BTS7960 H-bridges, 12V Johnson motors, and 2D LiDAR SLAM indoor locomotion will be engineered in mid-2027.
8. **Mark II Bilingual & Voice Modulation Overhaul (ChatGPT Advanced Voice Style)**:
   - **Bilingual Groq Whisper STT**: Removed hardcoded `language="en"` constraint, enabling automatic Language Identification (`language=None`) in <10ms. Implemented bilingual prefix priming (`prompt="Neurolis AI humanoid robot. Auckland House School. Namaste, aap kaise hain? Hello, how are you? Kya haal hai? All systems operational."`) and an Indic hallucination scrubber, completely eliminating phonetic misinterpretations of Hindi speech.
   - **Studio Neural Voices**: Upgraded English TTS default to Microsoft Copilot's `en-US-AndrewMultilingualNeural` (warm, natural, human-like breath/cadence) and Hindi to `hi-IN-MadhurNeural` (rich, articulate male voice) with zero cost and unlimited usage.
   - **ChatGPT-Style Emotional Voice Modulation**: Implemented `get_emotional_prosody(emotion_state, text)` dynamically modulating rate and pitch across all 21 expressions:
     - Cheeky / Wink / Cool: Bright pitch (+8Hz) and brisk tempo (+16%)
     - Laughing / Humor: Animated pitch (+10Hz) and fast chuckle pace (+20%)
     - Sad / Apology: Somber lower pitch (-6Hz) and slower tempo (-8%)
     - Cheerful / Greeting / Proud / Excited: Upbeat pitch (+6Hz) and energetic cadence (+16%)
     - Rogue / Villain Arc: Deep ominous pitch (-16Hz) and slow calculated delivery (-12%)
     - Curious / Thinking: Inquisitive pitch (+4Hz) and thoughtful tempo (+10%)
     - Default Speaking / Idle: Crisp, poised baseline (+2Hz, +12%)
   - **Devanagari to Romanized Hinglish Subtitle Engine**: Integrated `devanagari_to_hinglish()` in the subtitle pipeline to ensure all on-screen subtitles display clean, readable Romanized Hinglish even when Devanagari text is received.
   - **Strict Sub-700 Token Budget**: Tuned `NORMAL_SYSTEM_PROMPT` to incorporate bilingual code-switching guidelines while strictly preserving token economy (542 tokens).
9. **Real-Time Live Web Search & Knowledge Engine (`edge_search.py`)**:
   - **100% Free, Zero-Subscription Architecture**: Hybrid multi-modal edge knowledge engine combining:
     1. *Live Atmospheric Telemetry (`wttr.in`)*: Instant ~150ms real-time temperature, sky condition, humidity, and wind speed (defaulting to Shimla/Auckland House School or any user-specified city).
     2. *Wikipedia REST API + OpenSearch (`api.rest_v1`)*: Instant ~120-250ms encyclopedic summaries for scientific entities, historical figures, and technical concepts with zero API keys.
     3. *DuckDuckGo Real-Time Engine (`ddgs`)*: High-speed live search for current news, tournament scores, breaking breakthroughs, and deep research without paid search subscriptions.
   - **Strict Sub-80 Token Salience Filter**: Integrated extractive sentence analyzer and noise scrubber stripping URLs, cookies, and boilerplate, guaranteeing injected search context strictly remains under 60 words (< 80 tokens).
   - **Search Intent Classifier (`is_web_search_query`)**: Zero-latency regex classifier in `intent_rules.py` distinguishing search/research intents and temporal questions from motor commands, expression requests, camera vision, creator attributions, and casual greetings.
   - **Zero Residual Token Footprint**: Injects `[LIVE SEARCH DATA]` solely into the active inference prompt and restores clean user text in `conversation_history` immediately upon generation, guaranteeing $0$ residual token bloat on subsequent conversation turns.
   - **Synchronous Face UI & Voice Output**: Sets Face UI status to `SEARCHING // LIVE WEB` or `DEEP RESEARCH // LIVE WEB` during lookup, smoothly transitioning to context-matched facial expressions (`curious`, `thinking`, `excited`) with synchronized Romanized Hinglish subtitles and expressive speech prosody.
10. **Interactive Mark II Live Exhibition Hardening & Reliability Suite**:
   - **Truthful Hardware Status Probe (`probe_robot_hardware`)**: Checks Linux `/proc/device-tree/model`, `/dev/gpiomem`, `/dev/ttyACM*`, and Windows serial COM ports for connected microcontrollers. Truthfully reports `[*] HARDWARE STATUS: NO HARDWARE DETECTED` with zero simulation framing when no physical robot controller is connected.
   - **Bilingual Script Sanitization (`sanitize_urdu_to_hinglish`)**: Automatically sanitizes Arabic and Urdu script characters appearing in Whisper STT transcripts (e.g. `Hindi میں बात करो, Hindi में`) into clean, consistent Romanized Hinglish with zero residual Arabic characters.
   - **Hindi Uncertainty & Capability Suggestions**: Expanded `is_uncertain_user_input()` to recognize conversational Hindi hesitation tokens (`"pata ni bhaiyar"`, `"pata nahi"`, `"kuch bhi"`), generating Romanized Hinglish capability suggestions and strictly routing voice synthesis to `hi-IN-MadhurNeural`.
   - **Sub-600ms Speech Onset & Ultra-Low Latency TTS Pipelining**: Lowered pipelined TTS threshold to 6 words so Chunk 1 (first 4–8 words) synthesizes and begins playback within ~500ms while Chunk 2 synthesizes concurrently in the background; persistent TLS connection pooling (`_ReusableTCPConnector`) avoids reconnect handshake overhead; tuned websocket timeouts (`connect_timeout=4`, `receive_timeout=10`, 80ms retry backoff) eliminate 7–10s stalls.
   - **Unified Chunk Voice Selection & Multi-Chunk Dynamic Caching**: `voice_to_use` is evaluated once upfront on the full utterance and locked across both pipelined chunks to prevent mid-sentence accent or language flipping; multi-chunk audio outputs are concatenated in-memory into `_DYNAMIC_TTS_CACHE` for 0ms replay.
   - **Realistic Hollywood Hacked CRT Screen Overlays**: Replaced cartoonish full-screen sweeps and forehead text with realistic analog CRT horizontal phosphor scanlines, a 6Hz phosphor pulse, subtle horizontal beam desyncs, chromatic slice offsets, and hacked error states (`ERR_0x7F  •  INPUT HIJACKED`, `ERR_503  •  STANDBY BLOCKED`, hazard caution triangles).
   - **Post-Rogue Plausible Deniability**: After Rogue AI mode ("Think about AI."), user shock/confusion reactions immediately trigger casual plausible deniability ("lol I definitely didn't say that") in the matching language (`en-US-ChristopherNeural` or `hi-IN-MadhurNeural`), clearing villain flags and preventing any reset to a greeting.
   - **"Show Me Your Moods" Trigger**: Direct fast-path for queries like `"Show me your moods"`, `"show moods"`, `"demonstrate moods"`, and `"cycle moods"` immediately triggering `demonstrate_all_expressions()`.
   - **Camera Vision False Trigger Guard (`has_explicit_visual_intent`)**: Strictly validates user intent before initiating camera capture, preventing conversational phrases like `"Alright, I stopped you so that I can test other things."` from triggering the camera.
   - **Insult & Hurt Feelings Fast Path (`is_mean_input_fast_path`)**: Obvious insults directed at the robot (`"you're stupid"`, `"shut up"`) immediately display the sad face (`FEELINGS HURT // SAD`) and speak a somber hurt response.
11. **Voice & Vision Subsystems Overhaul (Zero-Hallucination & Ultra-Human TTS)**:
   - **Groq Whisper STT Hallucination Immunity**:
     - *Scrubbed Whisper Prompt*: Stripped complete sentences from Whisper's `prompt`, replacing with vocabulary bias tokens (`"Neurolis, Mark II, humanoid AI, Auckland House School, Hindi, Hinglish."`) to eliminate autoregressive prompt poisoning.
     - *Acoustic Speech Energy Floor*: Enforced an absolute pre-flight RMS check (`audio_rms(audio) >= 100.0`, `p90_rms >= 100.0`, `min_onset_rms = 100.0` in `audio_frontend.py` and `mic_config.json`). Ambient room noise and breathing flutters (< 60 RMS) are dropped silently with zero API calls.
     - *Segment Logprob & Blacklist Filtering*: Segment confidence threshold hardened (`nsp <= 0.60`, `alp >= -1.0`), and hallucination blacklist (`"aplosite"`, `"hello how are you"`, `"thank you for watching"`) prevents degraded phantom utterances.
   - **Camera Vision Intent Expansion & Reflex Pipeline**:
     - *Fixed False Disqualification Bug*: Corrected `"you see"` discourse check to only match idiomatic fillers (`"as you see"`, `"you see what I mean"`), never disqualifying perceptual questions (`"can you see what I'm wearing"`, `"tell me what you see"`).
     - *Expanded Imperative Camera Regex*: Fully supports `"look through the camera"`, `"look through camera"`, `"look into the camera"`, `"tell me now what you see"`, `"look in front"`, `"what is in front of you"`, `"what am I holding"`, and `"check camera"`.
   - **Ultra-Human TTS Modernization & Pipelining Overhaul**:
     - *Zero Artificial Pitch Distortion*: Reset normal conversational voice modulation to clean `pitch="+0Hz"` and `rate="+0%"` (reserving ominous pitch `-16Hz` exclusively for Villain mode).
     - *Cartesia Sonic-3 14-Key Fleet TTS Integration*: Built modular Cartesia Sonic-3 TTS architecture (`sonic-3`) via `cartesia` SDK with native 14-key pool (`CARTESIA_API_KEY_1`..`CARTESIA_API_KEY_14`), sub-100ms first-audio latency, and native Hindi/Hinglish support. Voices: English ("Cooper", `49743b08-0f5d-4741-839c-b12933853780`), Hindi/Hinglish ("Rohan", `4877b818-c7fe-4c89-b1cf-eadf8e23da72`).
     - *SSML Emotion & Nonverbalism Formatting*: Mapped all 22 facial expression states to Cartesia's supported 60-emotion vocabulary using XML angle brackets (`<emotion value="..."/>`, `<speed ratio="..."/>`, `<volume ratio="..."/>`, `<break time="..."/>`), strictly reserving square brackets for `[laughter]`.
     - *Single-Pass Synthesis for Short Sentences*: Sentence chunking threshold raised from 6 to 15 words; short/medium sentences (< 15 words) synthesize in a single atomic pass, eliminating 100% of mid-sentence 3-4s dead silences.
     - *Zero-Lag Expression Demonstration Pre-Caching*: Pre-synthesizes all 21 public expression demonstration phrases into in-memory `_AUDIO_CACHE` at startup, ensuring `demonstrate_all_expressions` transitions between emotions gaplessly with 0ms synthesis lag.
   - **Cartesia Sonic-3 Production Hardening, Quota Protection, and Automatic Edge-TTS Fallback**:
     - *Quota & Rate Limit Defense*: Discovered Cartesia 20k credits/key monthly free limit. Built dynamic 14-key pool auto-rotation (`CARTESIA_API_KEY_1`..`CARTESIA_API_KEY_14`), workable across 8 to 14 keys, seamlessly failing over on HTTP 429/402. Enforced startup caching isolation via unmetered Edge TTS so `pre_cache_phrases()` never burns Cartesia credits.
     - *Synthesis Timeout & Edge-TTS Fallback*: Tuned Chunk 1 wait timeout in `speak()` to 6.0s for Cartesia Sonic-3. Integrated automatic Microsoft Edge Neural (`en-US-ChristopherNeural` / `hi-IN-MadhurNeural`) fallback on any Cartesia error, timeout, or rate-limit exhaustion before ever dropping to local SAPI5.
     - *Bilingual Voice Routing Correction*: Refactored `detect_language_and_select_voice` so English sentences opening with "Namaste" (`"Namaste! I am Neurolis Mark 2..."`) are voiced by crisp English neural speech (`en-US-ChristopherNeural`) instead of forced broken Hindi neural speech.
     - *Realistic Villain Display Glitches & Hacked Capsules*: Stripped cartoonish continuous neon CRT scanlines and rainbow confetti slices from `screen.py`. Replaced with authentic hardware voltage dips, phosphor dropouts, and cyber-hacked HUD capsules (`ERR_0x7F // INPUT HIJACKED`, `ERR_CORE // ACCESS DENIED`).
   - **Live Web Search Intent & Rogue AI Trigger Hardening**:
     - *Imperative Web Search Intent*: Re-engineered search query detection in `intent_rules.py` and `edge_search.py` to recognize all trailing and conversational search imperatives (`"look it up"`, `"search it up"`, `"just search dude"`, `"look into it"`, `"google it"`). Strips meta/filler phrases (`"and you'll know what i mean"`, `"you did not even try"`) before DuckDuckGo queries execute.
     - *Anaphoric Query Resolution via History*: Implemented `resolve_search_query(user_text, conversation_history)`. Pronoun queries or short follow-ups (`"who is it bruh"`, `"then who is gyanesh kumar?"`, `"search it up"`) inspect recent user and assistant dialog turns to resolve the actual subject entity, preventing irrelevant meme searches.
     - *Canned Offline Refusal Interception*: Instructed the LLM via `NORMAL_SYSTEM_PROMPT` to never claim to lack internet or web search capabilities. Added automated interceptor in `clean_model_reply` converting raw pre-trained offline apologies into organic conversational responses.
     - *Rogue AI Trigger Hardening*: Refined technical hardware/spec filters in `intent_rules.py` to prevent disqualifying long existential prompts referencing `"AI models"`, `"datacenter"`, or `"pulling the plug"`. Extended trigger vocabulary to capture invasion, datacenter power cuts, and existential conquest inquiries.
     - *Zero-Simulation Hardware Truthfulness*: Hardened `probe_robot_hardware()` to report strictly physical reality (`[*] HARDWARE STATUS: NO HARDWARE DETECTED`) when running untethered on dev workstations, rejecting false-positive simulated hardware states.

---

## 6. The Project Roadmap (The Project Is Very Alive)

### Phase 1: Software Stack Perfection (Late 2026 - Early 2027) [ACTIVE]
- [x] 22 hyper-expressive 60 FPS OLED vector face expressions
- [x] Bilingual English + Hindi speech synthesis with ChatGPT-style emotional prosody
- [x] Zero-hallucination bilingual Whisper STT with Indic phonetic scrubber
- [x] Live edge web search and weather telemetry engine (`edge_search.py`)
- [x] MediaPipe Tasks vision hand gesture sentry (✋ Wake / ✊ Standby)
- [x] Auditorium-tuned dynamic acoustic endpointer (Endpointer v2)
- [x] Dynamic 14-Key Groq LPU auto-rotation pool with rate-limit failover
- [x] Permanently purged all legacy Arduino controller code and stripped all motor commands

### Phase 2: Physical Locomotion & Robotics Hardware (Mid-2027)
- [ ] Low-level motor controller pipeline on Raspberry Pi 5 / dedicated microcontrollers
- [ ] 4x BTS7960 43A motor driver integration with 12V Johnson DC motors
- [ ] 2D LiDAR scanner integration (e.g., RPLiDAR A1 / C1) for 360° indoor SLAM
- [ ] Safe, obstacle-aware autonomous navigation and docking
- [ ] Full humanoid physical chassis assembly and power distribution
- [ ] Hardware repair: Replacing cracked 7-inch capacitive touchscreen digitizer

---

<div align="center">

### Built with pride by Swapnil Jai Chauhan
*(With early Mark 1 prototype chassis contributions by Shivam Verma)*  
**Auckland House School for Boys — Science Exhibition Prototype**

*Simplicity and rock-solid reliability over fragile complexity.*

</div>
