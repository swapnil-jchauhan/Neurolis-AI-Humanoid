# Project Neurolis Component List

Last updated: 2026-09-04

This file tracks the hardware planned for Project Neurolis.

Project context:

- Swapnil is a development partner on Neurolis.
- A senior/project lead is guiding final hardware decisions.
- Unconfirmed hardware choices should stay marked as unresolved until confirmed.

======================================================================
1. MAIN COMPUTE AND CONTROL
======================================================================

1. Raspberry Pi 5, 4GB RAM
   Quantity: 1
   Role:
   - Main high-level brain.
   - Handles voice, AI, camera, touchscreen UI, high-level decisions,
     and serial commands to Arduino.
   Notes:
   - Needs stable high-current 5V power.
   - Should use cooling for long exhibition runtime.

2. Arduino Mega
   Quantity: 1
   Role:
   - Low-level motor and sensor controller.
   - Handles motors, encoders, distance sensors, and immediate movement commands.
   Notes:
   - Should handle movement safety independent of internet/API.

3. SD Card
   Quantity: 1
   Role:
   - Raspberry Pi storage.
   Notes:
   - Use a reliable card for exhibition day.

4. Raspberry Pi 5 Cooling Fan/Heatsink
   Quantity: 1
   Role:
   - Thermal management.
   Notes:
   - Important for long runtime.

======================================================================
2. VOICE, SCREEN, AND INTERACTION
======================================================================

1. Raspberry Pi 7-inch Touchscreen
   Quantity: 1
   Role:
   - Face/UI display.
   - Future `Talk to Neurolis` activation button.
   - Expression states: idle, listening, thinking, speaking, happy,
     confused, error.

2. Raspberry Pi Camera Module 5MP
   Quantity: 1
   Role:
   - Listed camera hardware.
   Notes:
   - Final role needs confirmation because the current final plan now uses
     a webcam for Neurolis vision.
   - Keep listed for now because it is part of the known hardware inventory.

3. Webcam
   Quantity: 1
   Role:
   - Final Neurolis camera for on-demand AI vision.
   Notes:
   - Activated only when the user asks a visual question.
   - Example use: user asks "What am I holding?", Neurolis captures
     one image and answers using Groq vision/multimodal API.
   - Should be kept fast by capturing one frame and asking for a short reply.
   - Should not run paid/API vision continuously.
   - Not used for continuous obstacle detection.
   - Not used as the main motor safety sensor.

4. Microphone
   Quantity: 1
   Role:
   - Voice input.
   Current assumption:
   - Exact type unknown.
   Preferred:
   - USB microphone for Raspberry Pi and Python compatibility.
   Avoid:
   - 3.5mm microphone unless using a USB sound card.

5. Speaker
   Quantity: 1
   Role:
   - Voice output.
   Current assumption:
   - Exact setup unknown.
   Important:
   - Raspberry Pi cannot directly drive a passive speaker loudly/safely.
   - Use an active speaker or amplifier module.

======================================================================
3. DRIVE SYSTEM
======================================================================

1. DC 12V 100RPM Johnson DC Motor (No Encoders)
   Quantity: 4
   Role:
   - 4WD Skid-Steer chassis (2 Left motors, 2 Right motors).
   - Driven via 4x BTS7960 motor drivers.
   - Distance and braking handled via vision box ratio and ultrasonics.

2. BTS7960 43A Motor Driver
   Quantity: 4
   Role:
   - High-current DC motor drivers (1 driver per motor).

3. Wheels
   Quantity: 4
   Role:
   - 4-Wheel Drive system.

4. Motor Bracket
   Quantity: 4
   Role:
   - Motor mounting to chassis.

======================================================================
4. SENSORS
======================================================================

1. HC-SR04 Ultrasonic Sensor
   Quantity: 2
   Role:
   - Dual-sensor front bumper (Front-Left & Front-Right).
   - Front-obstacle detection and <20cm emergency braking.
   Notes:
   - Useful for front/close-distance safety if stable.
   - Arduino handles real-time pinging and hardware emergency stop.

3. SmartElex ToF Imager - VL53L5CX
   Quantity: 1 planned
   Role:
   - Main planned object/proximity detection sensor.
   - Gives an 8x8 multi-zone distance grid instead of a single distance point.
   - Better for detecting whether something is actually close in front of Neurolis.
   Notes:
   - Selected for object detection.
   - Best handled by Raspberry Pi because VL53L5CX requires firmware loading
     and more memory than simple Arduino sensors.
   - Pi should process the distance grid and send safe high-level decisions
     to Arduino, such as STOP or MOVE.
   - Use this for practical close-object detection before trusting camera logic.
   - Still test carefully before connecting any real motor movement.

======================================================================
5. POWER SYSTEM
======================================================================

1. GenX 11.1V 3S 8000mAh LiPo Battery
   Quantity: 1
   Role:
   - Main robot battery.
   Notes:
   - Powers motors and electronics through proper regulation.
   - Needs fuse, switch, safe charging, and safe storage.

2. IMAX B6 Battery Charger
   Quantity: 1
   Role:
   - LiPo battery charger.
   Notes:
   - Use correct 3S balance charge mode.

3. XL4015E1 5A Step-Down Module
   Quantity: 1
   Role:
   - Voltage regulation.
   Current assumption:
   - Likely 5V/5.1V for low-voltage electronics.
   Important:
   - Must be measured with a multimeter before connecting electronics.
   - Raspberry Pi 5 needs stable high-current 5V power.
   - Do not casually power the Pi from a weak converter without testing.

4. Power Switch
   Quantity: 1
   Role:
   - Main power control.
   Notes:
   - Must be accessible and properly rated.

5. Fuse Holder + Fuse
   Quantity: 1
   Role:
   - Electrical protection.
   Current status:
   - Fuse rating unknown.
   Important:
   - Do not guess.
   - Choose based on battery capability, motor stall current, wire gauge,
     and total load.

6. XT60 Connectors
   Quantity: 2
   Role:
   - Battery/high-current power connectors.

7. 8AWG Silicone Wire Red
   Quantity: 1
   Role:
   - High-current positive wiring.

8. 8AWG Silicone Wire Black
   Quantity: 1
   Role:
   - High-current ground wiring.

9. Heat Shrink Sleeve
   Quantity: 1
   Role:
   - Insulation and protection for solder joints/connectors.

======================================================================
6. WIRING AND PROTOTYPING
======================================================================

1. Male-Male Jumper Wires
   Quantity: 1 pack
   Role:
   - Signal/prototyping connections.
   Warning:
   - Do not use for motor or battery current.

2. Male-Female Jumper Wires
   Quantity: 1 pack
   Role:
   - Sensor/module wiring.
   Warning:
   - Do not use for motor or battery current.

3. Breadboard / PCB
   Quantity: 1
   Role:
   - Prototyping or final signal distribution.
   Notes:
   - Breadboard is fine for signals.
   - Do not run motor current through a breadboard.
   - Perfboard/PCB is better for reliable exhibition wiring.

======================================================================
7. CURRENT ASSUMPTIONS AND UNRESOLVED QUESTIONS
======================================================================

1. Third Johnson motor
   Status:
   - Unknown.
   Question:
   - Is it spare, third-drive, head/torso, arm, or another mechanism?

2. Drive layout
   Status:
   - Unknown.
   Question:
   - Two-wheel differential drive or a different layout?

3. Microphone type
   Status:
   - Unknown.
   Preferred:
   - USB microphone.

4. Speaker/amplifier setup
   Status:
   - Unknown.
   Requirement:
   - Active speaker or amplifier module needed.

5. Buck converter output
   Status:
   - Likely 5V/5.1V, but unconfirmed.
   Required action:
   - Measure before connecting electronics.

6. Fuse rating
   Status:
   - Unknown.
   Required action:
   - Choose after motor current and total load are known.

7. Common ground
   Status:
   - To be confirmed.
   Note:
   - Pi/Arduino/motor driver logic usually need common ground, but wiring
     must be planned carefully.

8. Chassis layout
   Status:
   - Unknown.
   Required action:
   - Confirm with senior/project lead.

9. SmartElex VL53L5CX mounting location
   Status:
   - To be decided.
   Current plan:
   - Mount on the front body panel where it has a clear view ahead.
   Requirement:
   - Should look clean and should not be blocked by body panels, wires,
     hands, decorations, or the touchscreen.

10. Webcam / Raspberry Pi camera final role
    Status:
    - Partly confirmed.
    Current plan:
    - Webcam is final Neurolis hardware for on-demand AI vision only.
    - Webcam is not just for PC testing.
    - Do not use webcam/camera as the main motor safety sensor.
    Remaining question:
    - Should the Raspberry Pi Camera Module 5MP stay as backup/spare,
      or be removed from the final build plan?

======================================================================
8. RESPONSIBILITY SPLIT
======================================================================

Raspberry Pi 5 should handle:

- voice input
- activation/session logic
- Groq Whisper STT
- Groq Chat replies
- short-term memory
- edge-tts or future TTS
- camera/vision processing
- VL53L5CX distance-grid processing
- touchscreen UI and expressions
- high-level decisions
- serial commands to Arduino

Arduino Mega should handle:

- BTS7960 motor driver control
- motor encoder reading
- HC-SR04 ultrasonic readings
- simple ToF readings if a simple ToF sensor is used
- direct movement commands:
  - FORWARD
  - STOP
  - LEFT
  - RIGHT
  - REVERSE
- low-level safety stop behavior

======================================================================
9. SAFETY NOTES
======================================================================

- Do not power motors through the Raspberry Pi or Arduino.
- Do not use jumper wires for high-current motor or battery wiring.
- Use a fuse between the LiPo battery and main power distribution.
- Measure buck converter output before connecting electronics.
- Keep motor power and logic wiring organized to reduce random resets.
- Use the IMAX B6 correctly in 3S balance charge mode.
- Real movement safety should come from Arduino-read sensors.
- Do not rely on Groq Vision or camera-only detection for motor safety.
- During motor tests, lift the robot or keep wheels off the ground first.

======================================================================
10. PLANNED HARDWARE INTEGRATION ORDER
======================================================================

1. Confirm power architecture with senior/project lead.
2. Confirm microphone and speaker/amplifier choices.
3. Measure and set buck converter output.
4. Test Raspberry Pi voice pipeline from stable power.
5. Test Arduino Mega separately over USB.
6. Test one BTS7960 with one motor.
7. Read one motor encoder reliably on Arduino.
8. Add serial command protocol between Pi and Arduino.
9. Add `STOP` as the first command.
10. Add ultrasonic sensors one at a time.
11. Test SmartElex VL53L5CX on Raspberry Pi and read its 8x8 distance grid.
12. Decide final close-object STOP threshold from real readings.
13. Add VL53L0X/ToF sensor if still useful as backup or extra close sensor.
14. Add on-demand camera vision for interactive questions.
15. Add movement commands slowly:
    - forward
    - reverse
    - left
    - right
16. Integrate screen states after voice behavior is stable.
17. Run long-duration tests before exhibition day.

======================================================================
11. CHANGE LOG
======================================================================

- 2026-05-20:
  - Created initial component list from supplied parts.

- 2026-05-20:
  - Added assumptions:
    - third motor unknown
    - USB microphone preferred
    - speaker/amplifier unknown
    - buck likely 5V/5.1V but must be measured
    - fuse rating unknown until current draw is known
    - senior/project lead should confirm final hardware decisions

- 2026-05-25:
  - Reformatted file into a plain, Notepad-friendly grouped list.

- 2026-05-25:
  - Added SmartElex ToF Imager - VL53L5CX as the selected planned
    object/proximity detection sensor.
  - Updated webcam role to final on-demand AI vision for interactive
    questions, not PC testing and not continuous obstacle detection.
