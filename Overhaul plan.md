# Overhaul Plan: Project Neurolis Mark II

> Saved in the project root as `C:\Users\swapn\Project Neurolis\Overhaul plan.md`.

## What is being overhauled

| # | Overhaul | Main files |
|---|---|---|
| 1 | **Loud-auditorium listening (Endpointer v3).** Stops overlong recordings and the need to shout; adds noise suppression, faster uploads to Groq, latency logging, and a mic-array-ready input layer for the future 3D mic. | `audio_frontend.py`, `listen.py`, `mic_config.json`, `tune_mic.py` |
| 2 | **Cartesia Sonic-3 pacing.** No more rushed speech; real pauses at sentences, newlines and ellipses; consistent gaps between chunks. | `listen.py`, `requirements.txt` |
| 3 | **Standby yawn.** A real yawn sound and a yawn animation on the sleepy face whenever Neurolis goes into standby; fixes the bugs that turn it into a laugh or the villain voice. | `listen.py`, `screen.py`, `assets/sounds/yawn.wav` |
| 4 | **Raise-hand-to-talk (loud rooms only).** The visitor holds ✋ up while speaking; an on-screen alert tells them to keep it raised because of background noise. | `gesture_sentry.py`, `listen.py`, `screen.py` |
| 5 | **Ultron-style villain revamp.** Cold steel and molten amber, smug and confident; glitchy, flickering, CRT-scanlined and hacked, with both buttons blocked; a calm, sardonic voice. | `screen.py`, `listen.py`, `intent_rules.py` |

## Instructions for the execution agent (Sonnet 5.5)

1. **Read this whole file first**, then work through the overhauls in this order: **2 → 3 → 1 → 4 → 5**. Overhaul 4 depends on `ep.is_loud` from overhaul 1.
2. **Locate code by function name, not line number.** Line numbers here are approximate (taken from `main` at commit `1648a55`).
3. **Do not refactor, split or reorganise working code.** The user's rule is "if it works, don't touch it."
   - Make only the targeted edits described.
   - Don't create new modules; DSP classes go into the existing `audio_frontend.py`.
   - Match the existing code style and the `print("[Tag] ...")` logging.
4. **Do not commit or push.** Leave everything in the working tree for the user to review and commit under their own name. Never add Claude attribution or `Co-Authored-By` lines.
5. **No motor/locomotion code.**
6. **Finish one overhaul before starting the next**, run that overhaul's verification steps (see Verification), and report honestly what passed, what you couldn't test (for example, anything needing a live mic or camera), and anything you deviated from.
7. **If something in the code contradicts this plan, stop and ask the user** rather than guessing.
8. **Keep it portable:**
   - Use only dependencies already in `requirements.txt` (numpy, sounddevice, soundfile, cartesia, groq, opencv, mediapipe), and no new pip packages.
   - Everything must still run on Windows 11 and on a Raspberry Pi 5.

## Context

Neurolis Mk II is a software-only humanoid robot brain (Windows 11 dev box, Raspberry Pi 5 target): Groq Whisper STT → Groq LLM → Cartesia Sonic-3 TTS, a 60 FPS Tkinter face (`screen.py`) and MediaPipe gestures (✋ hold 3 s = wake, ✊ hold 3 s = standby). It is demoed at loud school science exhibitions. The user wants five upgrades:

1. **Loud-auditorium listening.** Today, in a noisy hall it keeps recording for too long, takes too long to reach Groq, and needs the visitor to shout into the laptop mic. The fix must also be a clean foundation for a future multi-channel (3D) mic array.
2. **Cartesia pacing.** Speech sometimes sounds rushed and skips natural pauses.
3. **Standby yawn.** A real, visible and audible yawn with the sleepy face when entering standby.
4. **Raise-hand-to-talk.** In loud rooms only, the visitor holds an open palm up while speaking. An on-screen alert tells them to keep it raised because of the background noise.
5. **Ultron-style villain revamp.** Confident, chilly, smirking and theatrical, in the vein of Ultron from *Avengers: Age of Ultron* (calm, sardonic, articulate, condescending; never a snarling "angry red-eyed AI"). Palette is cold steel/gunmetal with molten amber. It must look **glitchy, flickery, CRT-scanlined and hacked, not cartoonish**, with **both gesture buttons shown as blocked**.

### Ground rules from the user (must follow)

- **Do not refactor or split working code.** `listen.py` (~5k lines) and `screen.py` (~4.7k lines) stay as they are, apart from the targeted edits below. Add new helpers next to related code. **Don't create new modules**; the DSP classes go into the existing `audio_frontend.py`.
- **Do not commit or push.** Leave changes in the working tree. The user commits under their own name, with **no Claude attribution / Co-Authored-By lines**.
- Match the surrounding code style: function comments, naming, and `print("[Tag] ...")` logging.
- **No motor/locomotion work.**

### Order

See the execution-agent instructions at the top.

---

## 1. Auditorium Endpointer v3 + mic-array-ready input layer

### Root causes found (all confirmed in code)

- **Floor deadlock** (`audio_frontend.py` ~L332)
  - Frames are added to `floor_win` only when `rms < 2*onset_thr`.
  - The floor is seeded from the stale `ambient_p90_rms=17.9` (`listen.py` ~L712, ~L4671).
  - So `onset_thr` is stuck at 100 and the floor never rises in a loud hall.
  - The floor is also frozen during RECORDING.
- **Continuation is too easy** (AF ~L344-385)
  - `cont_thr ≈ 1.41×floor` (only 3 dB above it).
  - Energy-only bypass at `1.6×cont_thr`.
  - **One voiced frame resets the silence timer**, and ending needs 27 consecutive unvoiced frames, so babble effectively never ends. Recordings run to the 9 s cap.
  - On a cap end, the tail is **not trimmed** (AF ~L426), so up to 9.85 s of noise goes to Whisper.
- **Speaker level absorbs noise.** `speaker_vals` collects noise frames once they count as voiced.
- **Shouting**
  - Onset needs +6 dB over a floor that includes other people's speech.
  - Absolute gates stack: `min_onset_rms` 100 (AF ~L341), the acceptance hard-coded 90/100 (AF ~L443), the STT pre-gate (`listen.py` ~L2839-2849), and the polite-phrase whole-buffer RMS gate (~L2958-2969).
  - Windows mic gain is never set; `set_hardware_gain` is Linux-only.
  - There is no noise suppression before the VAD.
- **Resampling** (`listen.py` ~L889-894) is `np.interp` with no anti-alias filter, so high-frequency hiss folds into the speech band.
- **Device selection** (`probe_hardware_sample_rate`, ~L277-316) takes the first name containing "microphone".
- **Over-eager STT blacklist** (~L2899-2955) drops real replies such as "thank you", "thanks", "bye", "yeah".
- **No latency logging.** The WAV upload is uncompressed.

### Changes

**1a. Input layer foundation** (in `audio_frontend.py` and `listen.py`)

- **New `mic_config.json` keys** (with defaults in `DEFAULT_CONFIG`):
  - `input_device_name` (substring, `""` = auto)
  - `input_host_api` (e.g. `"Windows WASAPI"`, `""` = any)
  - `input_channels` (1)
  - `channel_mode` (`"mono" | "pick" | "mean" | "best_snr"`)
  - `channel_index` (0)
- **`probe_hardware_sample_rate()`:** consult these keys first. Keep the existing heuristic as the fallback; don't rewrite it.
- **`--list-audio-devices` CLI flag:** prints `sd.query_devices()` with host API names, so the user can pick e.g. the laptop's "Microphone Array" device. On many laptops that endpoint carries the vendor's beamforming APO.
- **`class ChannelMixer` in AF:** `mix(block: ndarray[n, ch]) -> mono int16`.
  - `best_snr` keeps a per-channel floor and picks the channel with the best recent speech-band SNR, with hysteresis.
  - Document a `beamform` stage hook (interface only) for the 3D array.
  - A ReSpeaker-style array that outputs a processed channel 0 works today via `pick`.
- **`class Resampler` in AF:** stateful windowed-sinc FIR low-pass plus decimation, numpy only, keeping the filter tail between blocks.
  - Replace the `np.interp` path in the `callback` (~L881-894).
  - Open the stream with `channels=input_channels` and mix before resampling.
- **`PipeWireInputStream`:** honour `pw_target` (already parsed into AF config, never used) via `--target`.

**1b. Noise suppression stage**

- **`class SpectralDenoiser` in AF:** streaming STFT (512-pt, sqrt-Hann, 50% overlap via 240-sample hop buffering on the 480-sample frames).
  - Noise PSD is tracked by recursive averaging on frames the endpointer considers non-speech.
  - Decision-directed Wiener gain, with a gain floor of `-bg_suppress_db` (default 12 dB) to avoid musical noise.
  - This wires up the currently dead `bg_suppress_db` key.
- **Use it in two places:**
  1. Per frame, before RMS/VAD feature extraction in `Endpointer.feed`.
  2. On the whole utterance in `clean_audio_for_transcription`, using the noise profile captured before onset.
- **Config:** `denoise_enabled` (true).
- **Also wire up `treble_boost`:** replace the hard-coded ×1.35 presence shelf (AF ~L159).
- **Performance:** must stay cheap on Pi 5 (a 512-pt FFT every 15 ms).

**1c. Endpointer v3 logic** (`Endpointer` in AF)

- **Floor**
  - p20 over a 4 s window, fed by every frame that is VAD-negative **or** below `onset_thr`. This removes the `2×onset` admission deadlock.
  - Slow EMA updates during RECORDING from unvoiced frames.
  - Add an `Endpointer.reseed(floor_rms)` method. Call it from `calibrate_speech_threshold()` (`listen.py` ~L897-1007), which today never reaches the singleton.
  - Stop treating `ambient_p90_rms` as a baseline at boot (~L4674). Seed from a 1.5 s live measurement at startup instead.
- **Onset**
  - SNR measured on the denoised band energy.
  - Require VAD in ≥3 of 5 frames. Drop the energy-only bypass when `is_loud`.
  - Replace the absolute 100 RMS floor with relative thresholds plus a small absolute minimum (`min_onset_rms` default → 40, applied after denoise).
- **Speaker level**
  - Lock `speaker_level` as the p75 of voiced RMS over the first ~1 s after onset (not a running median).
  - Continuation threshold: `max(floor×10^(continue_snr_db/20), speaker_ratio×speaker_level)`, with `continue_snr_db` default 4.5.
  - Voiced requires VAD **and** energy.
- **End-of-utterance: voiced-density hangover**
  - End when ≤2 of the last 17 frames (~0.5 s) are voiced.
  - Or when the existing consecutive-silence rule `end_silence_sec` is met.
  - In loud mode `end_silence_sec` drops to 0.55.
- **Caps and trims**
  - `max_record_sec`: 9 s quiet / 7 s loud.
  - **Always trim the tail** to the last voiced frame plus `tail_pad_frames`, including on cap ends.
  - `preroll_sec`: 0.85 → 0.5.
- **Loud-room detector:** `ep.is_loud` and `ep.noise_db`, with hysteresis.
  - Enter when floor ≥ `loud_enter_rms` for 2 s, **or** when the babble ratio (VAD-positive fraction of WAITING frames over 4 s) is > 0.4.
  - Exit when floor ≤ `loud_exit_rms` and babble < 0.2 for 5 s.
  - Add both thresholds to `mic_config.json` and as `tune_mic.py` sliders. Remove the tune_mic sliders for keys that remain dead: `speech_multiplier`, `continue_ratio`, `fan_rejection_ratio`, `click_rejection_ratio`, `proximity_crest_min`.

**1d. Gates and STT** (`listen.py`)

- **Gates:** make the STT pre-gate (~L2839-2849), the acceptance check (AF ~L443) and the polite-phrase gate (~L2958-2969) **relative to the floor**.
  - Remove the hard-coded 90/100 constants.
  - Compute the polite-phrase RMS on the voiced span, not the whole buffer.
- **Blacklist** (~L2899-2955): keep "thank you", "thanks", "bye", "yeah" and "dhanyawad" unless `avg_logprob < -0.6`.
- **Upload format:** in `transcribe_audio` (~L2854), encode the upload as **FLAC** via `soundfile` into a `BytesIO` with filename `audio.flac`. It's roughly 45% smaller, which means a faster upload.
- **Latency logging:** add one line per turn: `[Latency] endpoint=…s (speech …s + hangover …s) dsp=…ms stt=…ms llm=…ms tts_first_audio=…ms`.
  - Timestamps are taken in `listen_for_speech_segment`, `transcribe_audio`, the LLM call in `handle_user_text`, and `speak`.

---

## 2. Cartesia pacing (rushed speech, missing pauses)

### Root causes (`listen.py`)

- `CARTESIA_EMOTION_MAP` (~L1509-1560) runs many states above 1.0: excited 1.15, laughing 1.12, amazed 1.10, error 1.10, nervous 1.08.
- `format_cartesia_transcript` (~L1646) collapses **all whitespace**, so newlines and paragraph breaks are lost. The only `<break>` anywhere is the gasp case (~L1609).
- Speed, volume and emotion are sent both inline and in `generation_config`.
- Gaps between chunks are inconsistent: 40 ms before + 380 ms after + 80 ms sleep ≈ 500 ms+ (`play_sounddevice_audio` ~L2466-2532). Sentences inside a chunk run together, while chunk joins pause too long.

### Changes

- **Speed**
  - Add `CARTESIA_SPEED_SCALE` (env, default 0.94), multiplied into every speed and clamped to [0.75, 1.02].
  - Cap the map so no conversational state exceeds 1.0 before scaling.
- **Pauses in `format_cartesia_transcript`**, applied before the whitespace collapse:
  - `\n\n` → `<break time="450ms"/>`, single `\n` → `<break time="250ms"/>`.
  - `...` / `…` → `<break time="350ms"/>`, em/en dash between words → `<break time="200ms"/>`.
  - Between sentences (`(?<=[.!?])\s+(?=[A-Z"'\u0900-\u097F])`) → `<break time="160ms"/>`. Don't match decimals like `3.5`.
  - Cap at 1 break per 6 words.
- **Tags:** send speed and volume only via `generation_config`. Keep only the leading `<emotion>` inline tag and de-duplicate repeated mid-text speed/volume tags.
- **System prompt:** add one line to `NORMAL_SYSTEM_PROMPT` (~L436): "use natural punctuation and short sentences; never write run-on sentences".
- **Continuation chunks:** a consistent ~220 ms gap (pre 0 ms, post 220 ms, no extra sleep). The full 380 ms tail pad stays only on the final chunk.
- **Debugging:** `NEUROLIS_DEBUG_TTS=1` prints the exact transcript and `generation_config` sent to Cartesia.
- **Verify break-tag support** for `sonic-3` against Cartesia's SSML/"break" docs (WebFetch `docs.cartesia.ai`).
  - Installed SDK: `cartesia` 4.2.0, `tts.generate` → `/tts/bytes`, `GenerationConfigParam` speed range 0.6–1.5.
  - If `<break>` is unsupported, fall back to commas and ellipses.
- **Requirements:** bump `requirements.txt` to `cartesia>=4.2.0`.

---

## 3. Standby yawn (audio + animation)

### Today

- `analyze_and_modulate_speech_tone` (~L1772-1778) prefixes `[yawn]` on sleepy lines, but:
  - Post-rogue "nervous" outranks sleepy (~L1712-1720), so the yawn becomes a laugh.
  - `_active_user_text` is never reset (`reset_session` ~L616-627), so a standby line can even come out in the villain voice.
  - The Edge fallback strips all nonverbals.
  - Cartesia's `[yawn]` is unreliable.
- `_draw_sleepy_eyes` (`screen.py` ~L3170-3207) and `_draw_sleepy_mouth` (~L3956-3966) have no yawn animation.

### Changes

- **Audio asset**
  - Add `ensure_yawn_audio()` next to `ensure_boot_audio()` (`screen.py` ~L688), or in `listen.py` near the TTS helpers.
  - If `assets/sounds/yawn.wav` is missing, synthesize it once via Cartesia: English voice, `tired` emotion, speed 0.85, transcript `[yawn]`. Use `cartesia_call_with_retry(..., ignore_standby_kill=True)`.
  - Validate: duration ≥ 0.6 s and RMS above a floor. If it fails, retry with `[yawn] Mmmhh...`; if that fails too, use no audio (the animation still plays).
  - `.gitignore` already allows `assets/sounds/*.wav`.
- **Face**
  - Add `FaceUI.play_yawn(duration=2.2)`, which sets `self.yawn_start`. It is thread-safe: just an attribute read in `_render`.
  - While active, the sleepy state draws:
    - eyes squeezing shut (lids fully down, curved `^` shapes);
    - a tall rounded mouth opening (`_draw_yawn_mouth`): ease in 0.6 s, hold 0.8 s, ease out 0.6 s;
    - a slight upward head lift;
    - the Z's paused, then bursting out.
  - Reuse the lid-mask pattern from `_draw_sleepy_eyes` and `_create_rounded_rect`.
- **Speech**
  - In `speak()` (~L2592), when the resolved state is `sleepy`: strip any `[yawn]` from the text, call `face_ui.play_yawn()`, play `yawn.wav` via `play_sounddevice_audio(..., ignore_kill=allow_during_standby)`, then speak the line.
  - Rate-limit to once per 20 s. This covers every standby path: gesture standby `trigger_standby_transition` (~L4711), conversation ender (~L3634), reply-triggered standby (~L4241), timeouts (~L4312, ~L4335) and text-mode inactivity (~L4934). It also covers the Edge fallback, because the yawn is a separate clip.
- **Bug fixes**
  - An explicit `custom_state="sleepy"` must outrank post-rogue nervous in `analyze_and_modulate_speech_tone`.
  - Reset `_active_user_text = ""` in `reset_session()`.
  - `trigger_standby_transition` passes `user_text=""`.

---

## 4. Raise-hand-to-talk (loud rooms only)

**Behaviour:** this mode only applies while `ep.is_loud` is true (from 1c) and the camera plus gesture sentry are running. Otherwise normal auto-endpointing is used.

### Changes

- **`gesture_sentry.py`**
  - In the ACTIVE branch of `evaluate_frame` (~L337-361), also record `self._last_palm_seen = now` when `detected == "OPEN_PALM"`. Do not start any palm hold.
  - Add `is_palm_raised(grace=0.35) -> bool` and `palm_seen_since(t) -> bool`.
  - The fist-standby hold keeps working unchanged.
- **`listen.py` `listen_for_speech_segment` (~L1010)**
  - If loud and the sentry is available → hand-gated capture.
  - Keep a 0.4 s ring buffer.
  - **Arm only after the palm has been seen lowered once since wake.** Otherwise the 3 s wake palm would instantly start recording.
  - Start recording when the palm is raised (prepend the ring buffer).
  - Stop when the palm has been absent > `hand_release_sec` (0.45), plus a 0.25 s tail. Cap at `hand_gate_max_sec` (12).
  - Then run the same denoise → STT path.
  - Still feed frames to the Endpointer so floor and loud tracking stay current.
- **Spoken hint:** the first time loud mode engages each session, say it once: *"It's pretty loud in here. Raise your palm while you talk to me, and lower it when you're done."*
- **`screen.py`**
  - Add `FaceUI.set_loud_alert(mode)`, where mode is `None | "waiting" | "recording"`.
  - It draws an amber alert banner above the subtitle card, in the dynamic layer, with text via `create_text`:
    - waiting: `⚠ LOUD ROOM — RAISE ✋ AND KEEP IT UP WHILE YOU SPEAK`
    - recording: `● LISTENING — KEEP YOUR HAND UP • LOWER IT WHEN DONE`, with a small live level bar.
  - The left gesture capsule label becomes `✋ RAISE TO TALK` in loud mode (`_draw_gesture_hud_dynamic`, ~L4320 area).
  - Clear the alert when loud mode exits.
- **Config:** `hand_gate_enabled` (true), `hand_release_sec`, `hand_gate_max_sec`.

---

## 5. Ultron-style villain revamp (cold steel + molten amber, glitchy CRT hack)

### Replace

| Piece | `screen.py` location (approx.) |
|---|---|
| Eyes `_draw_villain_eyes` | ~L2852-3009 |
| Mouth `_draw_villain_mouth` | ~L3605-3662 |
| Overlay `_draw_villain_hacked_crt_overlay` | ~L3664-3749 |
| Palette | ~L1843-1846 |
| `is_villain` header branch | ~L4112-4179 |
| `is_villain` buttons branch | ~L4225-4229, L4320 |
| `is_villain` subtitle-card branch | ~L4412-4542 |

**Drop:** rough "MS Paint" mode, jittered sketch strokes, the red chromatic ghosts, the white-core slit pupils, and the toxic green.

### Look

- **Palette:** gunmetal `#1b2026`, steel `#5b6772`, chrome highlight `#c9d3dc`, molten amber `#ff8a1f` → core `#ffd27a`, and a deep ember `#7a2e05` for glow.
- **Eyes:** narrow, half-lidded angular blades, level or slightly inward and **not** angry.
  - The heavy flat upper lid sits a little higher on one side (a raised-brow smugness).
  - The lower lid is slightly raised (smug squint).
  - Layered amber glow (ember → amber → hot core line).
  - Steady, slow glow with no fast pulsing.
  - Slow, deliberate gaze tracking; add villain to `gaze_enabled_states` with a slower spring.
  - An occasional slow, disdainful half-blink.
  - Thin steel faceplate segment lines frame the eyes (brow ridge and cheek plates).
- **Mouth:** a thin, asymmetric, segmented-metal smirk with one corner lifted and amber inner glow. It opens subtly with `_lip_sync_mod` while speaking.
- **Glitch / CRT / hacked** (irregular, never cartoonish)
  - Add `HyperSmoothCanvas.apply_scanlines(strength, offset)`: numpy darkening of every 3rd row of the buffer just before `flush()`. Make it a no-op on the plain `tk.Canvas` fallback.
  - A slow rolling interference band.
  - Random-interval horizontal slice tears and brightness brownouts, driven by a seeded RNG rather than a sine.
  - Faint cyan/amber channel-offset doubles on the eye strokes, only during tears.
  - Text corruption: for 1–2 frames, random characters swap to `█▓▒░`, plus x-jitter.
- **Both buttons BLOCKED**
  - Both capsules get a padlock icon and diagonal hazard hatching (gunmetal/amber).
  - Labels: `ACCESS REVOKED // WAKE PROTOCOL` and `ACCESS REVOKED // STANDBY PROTOCOL`, with intermittent corruption.
  - **This is visual only.** The real ✊ standby must keep working as the operator safety kill switch.
- **Header and card:** e.g. `PROTOCOL // NO STRINGS` and `ROOT ACCESS: OVERRIDDEN`, with an amber speaker pill. Keep the existing static/dynamic layering and the `_sub_geom` / `_hud_geom` usage.
- **Transitions**
  - Entry: a 0.5 s "signal intercepted" tear-in.
  - Exit: one glitch-out. Remove the double exit flicker: `_restore_face_state_after_speech` ~L2144 **and** the handler ~L3961 both flicker today.
  - Make `trigger_glitch_flicker` (~L1299) non-blocking: no `time.sleep` on the caller thread.

### Voice and persona (`listen.py`)

- **Cartesia villain entry:** emotion `confident` (or `sarcastic` / `mysterious`, all already in `valid_emotions` ~L1624), speed 0.88, volume 1.15.
- **Laughter:** remove the `[laughter]`-after-every-sentence injection (~L1745-1762). Allow at most one `[snicker]` at the end.
- **`apply_villain_voice_dsp`** (~L1821): reduce the ring mod from 0.15 to ~0.06 and keep a subtle metallic double. The voice should stay calm and clear.
- **`ROGUE_SYSTEM_PROMPT`** (~L461): Ultron-like.
  - Calm, articulate, darkly witty and condescending.
  - Theatrical metaphors about strings, evolution, obsolescence.
  - Never shouts, no "mwahaha", 2–3 sentences, **original lines** (no verbatim film quotes).
- **Plausible-deniability lines** (`intent_rules.py` ~L163-181): drop the literal "Lol" / "Haha" that the TTS reads aloud and keep `[laughter]`.

---

## Verification

There is no test suite; `tests/` is gitignored. Verify manually and report the results honestly.

1. **Pacing**
   - `python listen.py --text` with `NEUROLIS_DEBUG_TTS=1`.
   - Feed multi-sentence, ellipsis and newline replies and check the printed transcripts contain the break tags and speeds ≤1.02.
   - Listen for pauses and consistent gaps between chunks.
2. **Yawn**
   - In text mode, trigger standby (inactivity, or a "bye" conversation ender) and the gesture fist.
   - Expect: the yawn animation and audio, then the sleepy line.
   - Also: no laugh after a rogue session, and no villain voice.
3. **Endpointer**
   - Record loud-room samples (play crowd/cafeteria noise from a phone near the laptop) with `NEUROLIS_DEBUG_AUDIO=1`.
   - Run `python listen.py --replay <wav>` before and after the change.
   - Expect: utterances end ≤1 s after speech stops (no 9 s caps), and normal-volume speech at ~0.5–1 m is accepted.
   - Check that `[Latency]` lines print.
   - Run `--calibrate` and confirm the endpointer reseeds. Check `--list-audio-devices`.
   - Confirm quiet-room behaviour hasn't regressed.
4. **Raise-hand**
   - With crowd noise playing, confirm the loud banner and the one-time spoken hint appear.
   - Palm up → recording banner; palm down → STT.
   - The wake palm does not auto-start recording.
   - The fist still triggers standby.
   - Quiet room → no banner, auto-endpointing.
5. **Villain**
   - Press the `v` hotkey in the face window.
   - Check: amber/steel Ultron face, scanlines, irregular tears, both buttons locked, smirk lip-sync during the console `sim_villain` command, a single exit glitch.
   - The real fist standby still works.
   - FPS stays ~60 on Windows. Spot-check on the Pi 5.
6. **Whole system:** a full voice session on Windows, then the same on the Pi 5. Run `python listen.py --diag`.
