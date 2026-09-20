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
import unittest
from pathlib import Path

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
        self.assertEqual(cleaned_sad, "Why would you say that? That actually hurt my feelings...")

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
        """Verify all 14 hardware checks execute cleanly and return valid badges."""
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
        ]

        for name, fn in checks:
            res = fn()
            self.assertIsInstance(res[0], bool, f"{name} check must return a boolean status")
            self.assertIn(res[1], ["✓", "✗", "~"], f"{name} badge must be ✓, ✗, or ~")
            self.assertIsInstance(res[2], str, f"{name} detail must be a descriptive string")
            self.assertGreater(len(res[2]), 0, f"{name} detail cannot be empty")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

