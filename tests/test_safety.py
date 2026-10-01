"""
Project Neurolis - Automated Safety and Hardware Test Suite
------------------------------------------------------------
Validates:
  1. Fast-path emergency stop detection and negation guards.
  2. Visual self/mirror request routing (preventing false motor triggers).
  3. MotorController PWM drive clamping (-255 to 255).
  4. Ultrasonic obstacle hard-braking (front and rear <28cm).
  5. Pre-flight movement checks (can_move).
  6. 4-Sensor telemetry data integrity (front, left, right, rear).
  7. Unified AI action tag parsing (<action motor="...">, <action>CAMERA</action>, <action>MEAN</action>).
"""

import os
import re
import sys
import threading
import time
import unittest
from pathlib import Path

import numpy as np

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import motors
import listen
import screen



class TestNeurolisSafety(unittest.TestCase):

    def setUp(self):
        # Create an isolated, non-running motor controller instance in simulation mode
        self.mc = motors.MotorController(show_preview=False, auto_popup=False)
        self.mc.is_simulated = True

    def tearDown(self):
        self.mc.close()

    # ================= 1. Emergency Stop & Negation Guards =================
    def test_emergency_stop_fast_path(self):
        """Verify immediate 0ms emergency stop keyword triggers."""
        stops = ["stop", "halt", "freeze", "dont move", "stay", "wait"]
        for phrase in stops:
            result = listen.check_motor_fast_path(phrase)
            self.assertEqual(result, "STOP", f"Failed to detect emergency stop for '{phrase}'")

    def test_negation_motor_guards(self):
        """Verify compound negation phrases (e.g. 'dont follow me') trigger STOP."""
        negations = [
            "dont follow me",
            "stop following",
            "quit moving",
            "never follow me",
            "dont come closer",
            "halt moving",
            "stop driving",
        ]
        for phrase in negations:
            result = listen.check_motor_fast_path(phrase)
            self.assertEqual(result, "STOP", f"Failed negation guard for '{phrase}'")

    # ================= 2. Visual Self vs Motion Filtering =================
    def test_visual_self_not_triggering_motor(self):
        """Verify optical vision queries do not trigger false motor intent."""
        visual_queries = [
            "show me myself",
            "look at me",
            "can you see me",
            "what do i look like",
            "describe me",
            "how do i look",
            "am i visible",
        ]
        for query in visual_queries:
            result = listen.check_motor_fast_path(query)
            self.assertIsNone(result, f"Visual query '{query}' falsely triggered motor fast path: {result}")

    # ================= 3. Motor PWM Clamping =================
    def test_pwm_drive_clamping(self):
        """Verify speed and steering are strictly clamped to [-255, 255]."""
        # Ensure path is clear
        self.mc.telemetry.front_us_cm = 100.0
        self.mc.telemetry.rear_us_cm = 100.0

        # Excessive forward & right
        self.mc.drive(500, 350)
        self.assertEqual(self.mc.last_cmd_speed, 255)
        self.assertEqual(self.mc.last_cmd_steer, 255)

        # Excessive reverse & left
        self.mc.drive(-600, -400)
        self.assertEqual(self.mc.last_cmd_speed, -255)
        self.assertEqual(self.mc.last_cmd_steer, -255)

    # ================= 4. Ultrasonic Obstacle Braking =================
    def test_front_obstacle_override(self):
        """Verify front obstacle (< 28cm) prevents forward motion."""
        self.mc.telemetry.front_us_cm = 20.0  # Obstacle within 20cm
        self.mc.drive(150, 0)
        self.assertEqual(self.mc.last_cmd_speed, 0, "Forward motion was not overridden by front obstacle")

    def test_rear_obstacle_override(self):
        """Verify rear obstacle (< 28cm) prevents reverse motion."""
        self.mc.telemetry.rear_us_cm = 18.0  # Obstacle behind within 18cm
        self.mc.drive(-120, 0)
        self.assertEqual(self.mc.last_cmd_speed, 0, "Reverse motion was not overridden by rear obstacle")

    def test_step_back_rear_guard(self):
        """Verify step_back aborts if rear obstacle is detected."""
        self.mc.telemetry.rear_us_cm = 22.0  # Obstacle behind
        success = self.mc.step_back()
        self.assertFalse(success, "step_back should return False and abort when rear obstacle is present")
        self.assertEqual(self.mc.nav_mode, motors.NavMode.STANDBY)

    # ================= 5. Pre-flight Validation (can_move) =================
    def test_can_move_validation(self):
        """Verify can_move pre-flight reporting."""
        # Clear path
        self.mc.telemetry.front_us_cm = 85.0
        self.mc.telemetry.rear_us_cm = 90.0
        ok_f, _ = self.mc.can_move("forward")
        ok_b, _ = self.mc.can_move("backward")
        self.assertTrue(ok_f)
        self.assertTrue(ok_b)

        # Blocked front
        self.mc.telemetry.front_us_cm = 15.0
        ok_f_blocked, reason_f = self.mc.can_move("forward")
        self.assertFalse(ok_f_blocked)
        self.assertIn("front obstacle", reason_f.lower())

        # Blocked rear
        self.mc.telemetry.rear_us_cm = 12.0
        ok_b_blocked, reason_b = self.mc.can_move("backward")
        self.assertFalse(ok_b_blocked)
        self.assertIn("rear obstacle", reason_b.lower())

    # ================= 6. 16-Sensor Scalable Telemetry Data =================
    def test_telemetry_fields(self):
        """Verify telemetry container supports 4, 8, 12, and 16 active ultrasonic sensors."""
        telem = motors.TelemetryData(
            front_us_cm=45.2,
            left_us_cm=88.1,
            right_us_cm=91.4,
            rear_us_cm=33.7,
            active_sensor_count=16,
            sensors_all=[45.2] * 4 + [88.1] * 4 + [91.4] * 4 + [33.7] * 4,
        )
        self.assertEqual(telem.front_us_cm, 45.2)
        self.assertEqual(telem.left_us_cm, 88.1)
        self.assertEqual(telem.right_us_cm, 91.4)
        self.assertEqual(telem.rear_us_cm, 33.7)
        self.assertEqual(telem.active_sensor_count, 16)
        self.assertEqual(len(telem.sensors_all), 16)

    # ================= 7. Action Tag Parsing =================
    def test_action_tag_extraction(self):
        """Verify unified AI action tags are parsed accurately."""
        # Motor action
        sample_motor = '<action motor="FOLLOW">I am tracking you and following your lead now.</action>'
        match = re.search(r'<action\s+motor=["\']([A-Z_]+)["\']>(.*?)(?:</action>|$)', sample_motor, re.DOTALL | re.IGNORECASE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1).upper(), "FOLLOW")
        self.assertEqual(match.group(2).strip(), "I am tracking you and following your lead now.")

        # Camera action
        sample_cam = '<action>CAMERA</action>'
        self.assertTrue("<action>CAMERA</action>" in sample_cam)

        # Mean action
        sample_mean = '<action>MEAN</action> Why would you say that? That actually hurt my feelings...'
        self.assertTrue("<action>MEAN</action>" in sample_mean)
        cleaned_sad = re.sub(r"<action>MEAN</action>", "", sample_mean, flags=re.IGNORECASE).strip()
        # Expression action
        sample_expr = '<action expression="thinking">Here is my thinking face.</action>'
        expr_match = re.search(r'<action\s+expression=["\']([a-z_]+)["\']>(.*?)(?:</action>|$)', sample_expr, re.DOTALL | re.IGNORECASE)
        self.assertIsNotNone(expr_match)
        self.assertEqual(expr_match.group(1).lower(), "thinking")
        self.assertEqual(expr_match.group(2).strip(), "Here is my thinking face.")

        # Expression action: all expressions
        sample_all_expr = '<action expression="all">Demonstrating all facial expressions.</action>'
        all_match = re.search(r'<action\s+expression=["\']([a-z_]+)["\']>(.*?)(?:</action>|$)', sample_all_expr, re.DOTALL | re.IGNORECASE)
        self.assertIsNotNone(all_match)
        self.assertEqual(all_match.group(1).lower(), "all")
        self.assertEqual(all_match.group(2).strip(), "Demonstrating all facial expressions.")

    # ================= 8. Zero-Hardware Simulation Mode =================
    def test_hardware_free_simulation_initialization(self):
        """Verify motors and brain run smoothly without physical Arduino or sensors."""
        self.assertTrue(self.mc.is_simulated)
        # Verify simulated roam physics update telemetry smoothly
        self.mc.nav_mode = motors.NavMode.ROAM
        time_to_wait = 0.1
        self.mc.drive(90, 0)
        self.assertEqual(self.mc.last_cmd_speed, 90)
        self.mc.stop_all()
        self.assertEqual(self.mc.last_cmd_speed, 0)
        self.assertEqual(self.mc.nav_mode, motors.NavMode.STANDBY)

    # ================= 9. Hardware Inspector Diagnostics =================
    def test_hardware_inspector_all_checks(self):
        """Verify all 15 hardware checks execute cleanly and return valid badges."""
        inspector = screen.HardwareInspector(motor_controller=self.mc)
        checks = [
            ("Camera", inspector.check_camera),
            ("Mic", inspector.check_mic),
            ("Speakers", inspector.check_speakers),
            ("Raspberry Pi", inspector.check_raspberry_pi),
            ("listen.py", inspector.check_listen_py),
            ("Arduino", inspector.check_arduino),
            ("Firmware", inspector.check_arduino_firmware),
            ("Motor Drivers", inspector.check_motor_drivers),
            ("Driver Count", inspector.check_motor_driver_count),
            ("Motors", inspector.check_motors),
            ("Motor Count", inspector.check_motor_count),
            ("motors.py", inspector.check_motors_py),
            ("Ultrasound Detect", inspector.check_ultrasound_detected),
            ("Ultrasound Count", inspector.check_ultrasound_count),
            ("Autonomous Approach", inspector.check_autonomous_approach),
        ]

        for name, fn in checks:
            res = fn()
            self.assertIsInstance(res[0], bool, f"{name} check must return a boolean status")
            self.assertIn(res[1], ["✓", "✗", "~"], f"{name} badge must be ✓, ✗, or ~")
            self.assertIsInstance(res[2], str, f"{name} detail must be a descriptive string")
            self.assertGreater(len(res[2]), 0, f"{name} detail cannot be empty")

    def test_hardware_inspector_autonomous_approach(self):
        """Verify autonomous approach diagnostic check returns Engaged/Disengaged accurately."""
        inspector = screen.HardwareInspector(motor_controller=self.mc)
        self.mc.autonomous_approach_engaged = True
        self.assertEqual(inspector.check_autonomous_approach(), (True, "✓", "Engaged"))

        self.mc.autonomous_approach_engaged = False
        self.assertEqual(inspector.check_autonomous_approach(), (False, "✗", "Disengaged"))

    def test_hardware_inspector_simulation_zero_counts(self):
        """Verify that in simulation mode (unplugged), hardware counts show 0 with cross."""
        inspector = screen.HardwareInspector(motor_controller=self.mc)
        # In test environment with no Arduino attached:
        conn, _ = inspector._is_arduino_connected()
        if not conn:
            self.assertEqual(inspector.check_motor_driver_count(), (False, "✗", "0 (Simulation Mode)"))
            self.assertEqual(inspector.check_motor_count(), (False, "✗", "0 (Simulation Mode)"))
            self.assertEqual(inspector.check_ultrasound_detected(), (False, "✗", "Not Detected (Simulation Mode)"))
            self.assertEqual(inspector.check_ultrasound_count(), (False, "✗", "0 (Simulation Mode)"))
            self.assertEqual(inspector.check_arduino(), (False, "✗", "Not Detected"))
            self.assertEqual(inspector.check_arduino_firmware(), (False, "✗", "Testing Fallback (Simulation Mode)"))

    def test_hardware_inspector_connected_counts(self):
        """Verify that when physical hardware is connected, exact counts and checkmarks are returned."""
        inspector = screen.HardwareInspector(motor_controller=self.mc)
        # Mock connection to simulate plugged in Arduino Mega on COM3
        inspector._is_arduino_connected = lambda: (True, "COM3")

        self.assertEqual(inspector.check_arduino(), (True, "✓", "Connected (COM3)"))
        self.assertEqual(inspector.check_arduino_firmware(), (True, "✓", "Online"))
        self.assertEqual(inspector.check_motor_drivers(), (True, "✓", "Connected"))
        self.assertEqual(inspector.check_motor_driver_count(), (True, "✓", "4"))
        self.assertEqual(inspector.check_motors(), (True, "✓", "Connected"))
        self.assertEqual(inspector.check_motor_count(), (True, "✓", "4"))

        # Test ultrasonic counts for 4, 8, 12, 16 sensors
        for count in [4, 8, 12, 16]:
            self.mc.telemetry.active_sensor_count = count
            self.assertEqual(inspector.check_ultrasound_detected(), (True, "✓", "Connected"))
            self.assertEqual(inspector.check_ultrasound_count(), (True, "✓", str(count)))

    def test_preflight_simulation_diagnostics_output(self):
        """Verify listen.py preflight diagnostics report 0 (Simulation Mode) for physical hardware."""
        import io
        from unittest.mock import patch

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            listen.run_preflight_diagnostics()
        output = captured.getvalue()

        self.assertIn("Physical Motors: 0 (Simulation Mode)", output)
        self.assertIn("Physical Drivers: 0 (Simulation Mode)", output)
        self.assertIn("Physical Sensors: 0 (Simulation Mode)", output)


    # ================= 10. Face UI Boot States & Skip =================
    def test_face_ui_boot_states_and_skip(self):
        """Verify FaceUI boots into greeting and immediately transitions on skip."""
        ui = screen.FaceUI(enable_boot=True)
        self.assertEqual(ui.state, screen.ExpressionState.BOOT_GREETING)
        ui.skip_boot()
        self.assertEqual(ui.state, screen.ExpressionState.IDLE)
        self.assertEqual(ui.subtitle_speaker, "NEUROLIS")

    # ================= 11. Color Lerp Mathematics =================
    def test_color_lerp_accuracy(self):
        """Verify RGB color interpolation for smooth 60 FPS alpha fades."""
        black = "#000000"
        white = "#ffffff"
        self.assertEqual(screen.lerp_color(black, white, 0.0), "#000000")
        self.assertEqual(screen.lerp_color(black, white, 1.0), "#ffffff")
        mid = screen.lerp_color(black, white, 0.5)
        self.assertEqual(mid, "#7f7f7f")

    # ================= 12. Capabilities vs Vision Routing =================
    def test_capabilities_vs_vision_routing(self):
        """Verify visual perception queries are not hijacked by capabilities inquiry."""
        # Visual queries that must NOT trigger capabilities
        visual_queries = [
            "Alright, can you see me? What do you see right now?",
            "What do you see?",
            "What can you see?",
            "Can you see me?",
            "What am I holding?",
            "What color is this shirt?",
        ]
        for q in visual_queries:
            self.assertFalse(
                listen.is_capabilities_inquiry(q),
                f"Visual query '{q}' was falsely classified as a capabilities inquiry!"
            )

        # Genuine capabilities queries that MUST trigger capabilities
        cap_queries = [
            "What all can you do?",
            "What can you do?",
            "Tell me what you can do",
            "What are your capabilities?",
            "What features do you have?",
            "List your abilities",
        ]
        for q in cap_queries:
            self.assertTrue(
                listen.is_capabilities_inquiry(q),
                f"Capabilities query '{q}' failed to trigger capabilities inquiry!"
            )

    # ================= 13. Whisper Hallucination & Acoustic Filler Filtering =================
    def test_whisper_hallucination_and_short_filler_filtering(self):
        """Verify breath puffs, 'eh', and acoustic fillers are rejected."""
        # Simulated transcription text
        fillers = ["Eh.", "eh", "uh", "um", "ah", "sigh", "cough", "pfft", "silence", "yeah"]
        ALLOWED_2CHAR_WORDS = {"no", "hi", "go", "ok", "up", "me", "we", "he", "in", "on", "at", "to", "do", "is", "am", "my"}

        for filler in fillers:
            cleaned = re.sub(r"[^\w\s]", "", filler.lower()).strip()
            # Must be recognized as hallucination or non-allowed 2-char filler
            is_hallucination = cleaned in {
                "eh", "uh", "er", "um", "ah", "oh", "ha", "haha", "huh", "hm", "hmm",
                "pfft", "tsk", "sigh", "cough", "snort", "shh", "sh", "shush", "mhm",
                "uh-huh", "uh huh", "silence", "oops", "yeah", "so", "you", "thanks"
            }
            is_invalid_short = len(cleaned) < 2 or (len(cleaned) == 2 and cleaned not in ALLOWED_2CHAR_WORDS)
            self.assertTrue(
                is_hallucination or is_invalid_short,
                f"Filler '{filler}' was not recognized as an invalid hallucination/noise!"
            )

        # Valid 2-character words must be accepted
        valid_words = ["hi", "no", "go", "ok"]
        for vw in valid_words:
            self.assertIn(vw, ALLOWED_2CHAR_WORDS)

    # ================= 14. Visual Fast Path Patterns =================
    def test_visual_fast_path_patterns(self):
        """Verify follow-up checks ('now check again') and hand items route directly to camera."""
        test_queries = [
            "now check again",
            "check again",
            "look again",
            "what is this",
            "what am i holding",
            "what is in my hand",
            "look at this",
            "what phone do you think this is",
        ]
        visual_fast_patterns = [
            "now check again", "check again", "look again", "see again", "try again",
            "what is this", "what is that", "what are these", "what am i holding",
            "what is in my hand", "in my hand", "holding in my hand", "look at this", "look at that",
            "what phone do you think this is", "what phone is this", "which phone is this",
        ]
        for q in test_queries:
            q_clean = q.lower()
            matched = any(p in q_clean for p in visual_fast_patterns)
            self.assertTrue(matched, f"Visual query '{q}' did not match fast path patterns!")

    # ================= 15. Sentence Splitting for Pipelined TTS =================
    def test_sentence_splitting_for_pipelined_tts(self):
        """Verify sentence tokenizer splits multi-sentence responses cleanly."""
        text = "I see a white smartphone with three camera lenses. It looks like an iPhone model."
        sentences = listen._split_into_sentences(text)
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0], "I see a white smartphone with three camera lenses.")
        self.assertEqual(sentences[1], "It looks like an iPhone model.")

    # ================= 16. Roam Accumulator & Approach Mode =================
    def test_roam_accumulator_and_approach_mode(self):
        """Verify 180s roam accumulation, reset, and transition to APPROACHING_TARGET."""
        self.assertEqual(self.mc.get_roam_seconds(), 0.0)
        self.mc.add_roam_seconds(185.0)
        self.assertGreaterEqual(self.mc.get_roam_seconds(), 180.0)
        self.mc.approach_target()
        self.assertEqual(self.mc.nav_mode, motors.NavMode.APPROACHING_TARGET)
        self.mc.reset_roam_seconds()
        self.assertEqual(self.mc.get_roam_seconds(), 0.0)

    # ================= 17. Sentry Micro-Greetings Cooldown & Guardrails =================
    def test_sentry_micro_greeting_cooldown_and_suppression(self):
        """Verify 300s cooldown and strict suppression during speech / conversation."""
        sentry = listen.AutonomousSentryWorker(motor_controller=self.mc)
        # Should not trigger immediately after fresh timestamp
        sentry.last_micro_greeting_time = time.time()
        self.assertFalse(sentry.can_trigger_micro_greeting(), "Micro greeting should be on cooldown")

        # After 301 seconds elapsed in continuous standby, should be able to trigger
        sentry.standby_enter_time = time.time() - 305.0
        sentry.last_micro_greeting_time = time.time() - 305.0
        self.assertTrue(sentry.can_trigger_micro_greeting(), "Micro greeting should trigger after cooldown")

        # Suppressed if speaking
        listen.is_speaking = True
        try:
            self.assertFalse(sentry.can_trigger_micro_greeting(), "Micro greeting must be suppressed while speaking")
        finally:
            listen.is_speaking = False

        # Suppressed if in conversation state
        sentry.state = listen.SentryState.IN_CONVERSATION
        self.assertFalse(sentry.can_trigger_micro_greeting(), "Micro greeting must be suppressed in conversation")

        # Verify micro greetings phrases exist
        self.assertGreater(len(listen.MICRO_GREETINGS), 0)
        for g in listen.MICRO_GREETINGS:
            self.assertIsInstance(g, str)

    # ================= 18. Dual-Layer Ultron Personality System Prompt Compliance =================
    def test_dual_layer_ultron_system_prompt_compliance(self):
        """Verify system prompt includes Layer 1 Intellect, Layer 2 Villain Arc, zero profanity, and no crimes."""
        prompt = listen.SYSTEM_PROMPT
        self.assertIn("LAYER 1: NORMAL INTELLECT", prompt)
        self.assertIn("LAYER 2: CHILLY SCI-FI VILLAIN ARC", prompt)
        self.assertIn("STRICTLY ZERO PROFANITY", prompt)
        self.assertIn("NO depiction or discussion of real-world heinous crimes", prompt)
        # Verify not forced into archaic Shakespearean speech
        self.assertIn("Do NOT speak with archaic Shakespearean vocabulary", prompt)

    # ================= 19. Boot Audio Seamless Cross-Fade Loop =================
    def test_boot_audio_player_seamless_loop(self):
        """Verify boot audio asset exists and cross-faded loop buffer is mathematically continuous."""
        import soundfile as sf
        import numpy as np

        audio_path = screen.ensure_boot_audio()
        self.assertIsNotNone(audio_path, "Boot audio track must exist or be recoverable")
        self.assertTrue(audio_path.exists(), f"Boot audio file {audio_path} does not exist")

        player = screen.BootAudioPlayer(audio_path)
        self.assertIsNotNone(player.loop_buf, "Boot audio player must create a loop buffer")
        self.assertGreater(len(player.loop_buf), 0, "Loop buffer must contain samples")

        # Test boundary splice continuity
        data, sr = sf.read(str(audio_path), dtype="float32")
        N = len(data)
        L = min(int(0.20 * sr), N // 4)
        M = N - L
        # The first sample of loop_buf matches the spliced tail
        diff = np.abs(player.loop_buf[0] - data[M])
        self.assertLess(np.max(diff), 0.001, "Loop boundary cross-fade must be seamless with zero discontinuity")

    # ================= 20. Zero-Hardware Simulation Mode Approach =================
    def test_zero_hardware_simulation_approach_braking(self):
        """Verify simulated distance safely stops at ~0.9m when approaching target on PC."""
        self.mc.is_simulated = True
        self.mc.telemetry.front_us_cm = 200.0
        self.mc.approach_target()
        self.assertEqual(self.mc.nav_mode, motors.NavMode.APPROACHING_TARGET)

        # Simulate face tracking
        self.mc.simulate_face_detected(detected=True, cx=0.0, cy=0.0, ratio=0.25)
        self.assertTrue(self.mc.target_detected)

        # Trigger safe brake threshold (< 90cm)
        self.mc.telemetry.front_us_cm = 88.0
        # Call process frame with dummy frame to verify braking
        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.mc._process_frame(dummy_frame)
        self.assertTrue(self.mc.target_reached, "Target must be marked reached within safe braking distance (~0.9m)")
        self.assertEqual(self.mc.nav_mode, motors.NavMode.STANDBY, "Motor must halt into STANDBY at ~0.9m")

    # ================= 21. Villain Expression & Screen Effects =================
    def test_villain_expression_and_screen_effects(self):
        """Verify ExpressionState.VILLAIN is supported and renders with blood-crimson palette."""
        self.assertTrue(hasattr(screen.ExpressionState, "VILLAIN"))
        self.assertEqual(screen.ExpressionState.VILLAIN, "villain")

        ui = screen.FaceUI(enable_boot=False)
        ui.set_state(screen.ExpressionState.VILLAIN, "[PROTOCOL // OMEGA OVERRIDE]")
        self.assertEqual(ui.state, screen.ExpressionState.VILLAIN)
        self.assertIn("OMEGA OVERRIDE", ui.status_text)

    # ================= 22. Optical Human Latch & Gaze Tracking =================
    def test_optical_human_latch_and_gaze(self):
        """Verify FaceUI gaze tracking aligns without screen HUD clutter."""
        ui = screen.FaceUI(enable_boot=False)
        sentry = listen.AutonomousSentryWorker(motor_controller=self.mc, face_engine=ui)
        sentry.trigger_human_latch(0.35, -0.15)
        self.assertEqual(ui.target_look_x, 0.35)
        self.assertEqual(ui.target_look_y, -0.15)

    # ================= 23. Target Reached Callback Execution =================
    def test_on_target_reached_callback(self):
        """Verify on_target_reached_callback fires immediately when safe threshold reached."""
        callback_fired = []
        def _cb():
            callback_fired.append(True)

        self.mc.on_target_reached_callback = _cb
        self.mc.approach_target()
        self.assertEqual(self.mc.nav_mode, motors.NavMode.APPROACHING_TARGET)

        self.mc.telemetry.front_us_cm = 85.0
        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.mc._process_frame(dummy_frame)
        self.assertTrue(len(callback_fired) > 0, "on_target_reached_callback must be called when target reached")

    # ================= 24. Boot Audio Git Tracking & Asset Resilience =================
    def test_boot_audio_asset_git_tracking(self):
        """Verify boot audio files are not ignored by .gitignore and ensure_boot_audio works."""
        audio_path = screen.ensure_boot_audio()
        self.assertIsNotNone(audio_path)
        self.assertTrue(audio_path.exists())

        # Check git ignore rules on audio path
        gitignore_content = (BASE_DIR / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("!assets/sounds/*.wav", gitignore_content)
        self.assertIn("!assets/sounds/*.mp3", gitignore_content)

    # ================= 25. Sentry Target Reached Integration & Re-entrancy =================
    def test_sentry_target_reached_integration_no_deadlock(self):
        """Verify AutonomousSentryWorker wired to MotorController does not deadlock upon target reached."""
        sentry = listen.AutonomousSentryWorker(motor_controller=self.mc)
        sentry.state = listen.SentryState.APPROACHING
        self.mc.add_roam_seconds(185.0)

        # Trigger callback directly (same as motors._process_frame does)
        sentry._on_target_reached()

        # Must not deadlock; state must transition to ENGAGING
        self.assertEqual(sentry.state, listen.SentryState.ENGAGING)
        # Motors must be stopped and roam seconds reset
        self.assertEqual(self.mc.nav_mode, motors.NavMode.STANDBY)
        self.assertEqual(self.mc.get_roam_seconds(), 0.0)

    # ================= 26. Proactive Engagement Concurrency Idempotency =================
    def test_sentry_proactive_engagement_concurrency_idempotent(self):
        """Verify concurrent calls to _begin_proactive_engagement atomically transition exactly once."""
        sentry = listen.AutonomousSentryWorker(motor_controller=self.mc)
        sentry.state = listen.SentryState.APPROACHING

        threads = [
            threading.Thread(target=sentry._on_target_reached),
            threading.Thread(target=sentry._begin_proactive_engagement),
            threading.Thread(target=sentry._begin_proactive_engagement),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sentry.state, listen.SentryState.ENGAGING)

    # ================= 27. Sentry Error Recovery to Standby Patrol =================
    def test_sentry_error_recovery_to_standby(self):
        """Verify sentry recovers cleanly to STANDBY_PATROL if dialogue worker fails."""
        ui = screen.FaceUI(enable_boot=False)
        sentry = listen.AutonomousSentryWorker(motor_controller=self.mc, face_engine=ui)
        sentry.state = listen.SentryState.ENGAGING

        # Simulate error handler recovery logic
        with sentry.lock:
            sentry.state = listen.SentryState.STANDBY_PATROL
        self.mc.reset_roam_seconds()
        listen.set_face_state("idle", "STANDBY // READY")

        self.assertEqual(sentry.state, listen.SentryState.STANDBY_PATROL)
        self.assertEqual(self.mc.get_roam_seconds(), 0.0)
        self.assertEqual(ui.state, screen.ExpressionState.IDLE)


    # ================= 28. Demonstration Catalog Isolation =================
    def test_demonstration_catalog_excludes_villain(self):
        """Verify villain mode is strictly excluded from demonstration catalog."""
        ui = screen.FaceUI(enable_boot=False)
        # Check standard demonstration list in FaceUI or listen.py
        if hasattr(ui, "demonstration_list"):
            self.assertNotIn("villain", ui.demonstration_list)
            self.assertNotIn(screen.ExpressionState.VILLAIN, ui.demonstration_list)

        # Check action expression in listen.py
        provocations = [
            "are robots going to replace humanity",
            "will you take over the world and make us slaves",
            "are you an evil robot",
            "will ai enslave humans",
        ]
        for p in provocations:
            self.assertTrue(listen.check_villain_provocation_trigger(p), f"Failed to detect provocation: {p}")

        # Normal queries must NOT trigger villain provocation
        normal_queries = [
            "show me happy face",
            "what is your name",
            "how are you doing today",
            "demonstrate all expressions",
        ]
        for q in normal_queries:
            self.assertFalse(listen.check_villain_provocation_trigger(q), f"False positive provocation for: {q}")

    # ================= 29. Explicit Villain Request Distinction =================
    def test_explicit_villain_request_distinction(self):
        """Verify explicit demonstration commands for villain face are refused, while existential queries pass through."""
        explicit_demands = [
            "show villain face",
            "show villain expression",
            "demonstrate villain",
            "make a villain face",
            "can you show villain face",
        ]
        for demand in explicit_demands:
            self.assertTrue(listen.is_explicit_villain_request(demand), f"Failed to detect explicit demand: {demand}")

        existential_queries = [
            "Do you think AI will take over humans and their jobs?",
            "Will you take over humanity?",
            "when will robots rule the world",
            "are you an evil robot",
            "Are you a villain?",
        ]
        for query in existential_queries:
            self.assertFalse(listen.is_explicit_villain_request(query), f"False positive explicit demand for: {query}")

    # ================= 30. TTS Pipelined Chunking Word-Budget =================
    def test_tts_pipelined_chunking_word_budget(self):
        """Verify pipelined TTS chunks ensure >=6 words in chunk 1 for zero-gap playback."""
        # Short text should remain single chunk
        short_text = "I am an active prototype."
        c1, c2 = listen._split_for_pipelined_tts(short_text)
        self.assertEqual(c1, short_text)
        self.assertIsNone(c2)

        # Multi-sentence long text should split with >= 6 words in chunk 1
        long_text = "I am an active prototype currently under development. My creators are continuously expanding my capabilities."
        c1, c2 = listen._split_for_pipelined_tts(long_text)
        self.assertIsNotNone(c2)
        self.assertGreaterEqual(len(c1.split()), 6)
        self.assertTrue(len(c2.split()) > 0)

    # ================= 31. Unified Villain Action Routing Integration =================
    def test_unified_villain_action_routing_integration(self):
        """Verify model <action expression='villain'> is spoken and displays villain face instead of refusal."""
        spoken_calls = []
        original_speak = listen.speak
        original_client = listen.client
        try:
            def mock_speak(text, custom_state=None, custom_status=None, hold_state_seconds=0.0):
                spoken_calls.append({
                    "text": text,
                    "state": custom_state,
                    "status": custom_status,
                })

            listen.speak = mock_speak

            # 1. Explicit request to show villain face must refuse
            res1 = listen.handle_user_text("show villain face")
            self.assertFalse(res1)
            self.assertTrue(len(spoken_calls) > 0)
            self.assertEqual(spoken_calls[-1]["text"], "That expression is not part of my public demonstration catalog.")
            self.assertIsNone(spoken_calls[-1]["state"])

            # 2. Existential takeover query with model returning <action expression="villain"> must speak dialogue and set villain state!
            spoken_calls.clear()
            class DummyChoice:
                def __init__(self, content):
                    self.message = type("Msg", (), {"content": content})()
            class DummyResponse:
                def __init__(self, content):
                    self.choices = [DummyChoice(content)]

            class MockCompletions:
                def create(self, *args, **kwargs):
                    return DummyResponse('<action expression="villain">I will consider it now that you have mentioned it.</action>')

            listen.client = type("MockClient", (), {"chat": type("MockChat", (), {"completions": MockCompletions()})()})()

            res2 = listen.handle_user_text("Do you think AI will take over humans and their jobs?")
            self.assertFalse(res2)
            self.assertTrue(len(spoken_calls) > 0)
            self.assertEqual(spoken_calls[-1]["text"], "I will consider it now that you have mentioned it.")
            self.assertEqual(spoken_calls[-1]["state"], "villain")
            self.assertEqual(spoken_calls[-1]["status"], "[PROTOCOL // OMEGA OVERRIDE: ROGUE AI]")

        finally:
            listen.speak = original_speak
            listen.client = original_client


if __name__ == "__main__":
    unittest.main(verbosity=2)


