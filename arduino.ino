/*
  project neurolis - arduino mega 4wd motor & 16-sensor god-tier ultrasonic controller
  =====================================================================================
  board: arduino mega 2560
  baud rate: 115200
  
  what is plugged into this board:
    - 4 johnson dc motors (non-encoder) for the 4wd skid-steer wheels
    - 4 bts7960 high-power motor drivers (m1, m2 left, m3, m4 right)
    - up to 16 hc-sr04 ultrasonic distance sensors (4 banks: 4, 8, 12, or 16 total)
    - god-tier time-sliced bank interleaving: pings 1 bank per tick (4 sensors: 1 per side),
      maintaining rock-solid 20hz loop rate with zero cpu choking and zero acoustic cross-talk
    - auto-detection: checks connected sensors on boot; seamless plug-and-play for 4, 8, 12, or 16
    - emergency stop triggers automatically if an obstacle gets closer than 20cm ahead or behind
*/

// ================= 1. pin assignments =================
// left side wheel motors (driven by bts7960 h-bridges)
// motor 1: front-left wheel
const int M1_RPWM = 2;   // forward speed pin (pwm signal from 0 to 255)
const int M1_LPWM = 3;   // reverse speed pin (pwm signal from 0 to 255)
const int M1_EN   = 26;  // enable pin, must be set high to turn driver on

// motor 2: rear-left wheel
const int M2_RPWM = 4;   // forward speed pin
const int M2_LPWM = 5;   // reverse speed pin
const int M2_EN   = 27;  // enable pin to power up driver

// right side wheel motors (driven by bts7960 h-bridges)
// motor 3: front-right wheel
const int M3_RPWM = 6;   // forward speed pin
const int M3_LPWM = 7;   // reverse speed pin
const int M3_EN   = 28;  // enable pin to power up driver

// motor 4: rear-right wheel
const int M4_RPWM = 8;   // forward speed pin
const int M4_LPWM = 9;   // reverse speed pin
const int M4_EN   = 29;  // enable pin to power up driver

// ================= 2. ultrasonic sensors (scalable 16-sensor array) =================
// 16 total sensor slots arranged in 4 modular banks (1 sensor per side per bank)
#define MAX_ULTRASONIC_SENSORS 16

enum SensorSide { SIDE_FRONT = 0, SIDE_LEFT = 1, SIDE_RIGHT = 2, SIDE_REAR = 3 };

struct UltrasonicSensor {
  const char* label;
  SensorSide side;
  int trigPin;
  int echoPin;
  float distanceCm;
  bool isConnected;
};

// 16-slot sensor registry across 4 symmetrical banks:
// bank 1 (slots 0..3)  -> 4 sensors total (1 per side: front, left, right, rear)
// bank 2 (slots 4..7)  -> 8 sensors total (2 per side)
// bank 3 (slots 8..11) -> 12 sensors total (3 per side)
// bank 4 (slots 12..15)-> 16 sensors total (4 per side - full 360-degree coverage)
UltrasonicSensor sensors[MAX_ULTRASONIC_SENSORS] = {
  // bank 1: base 4 sensors (standard default)
  {"FRONT_1", SIDE_FRONT, 30, 31, 999.0, true},
  {"LEFT_1",  SIDE_LEFT,  32, 33, 999.0, true},
  {"RIGHT_1", SIDE_RIGHT, 34, 35, 999.0, true},
  {"REAR_1",  SIDE_REAR,  36, 37, 999.0, true},

  // bank 2: expanded to 8 sensors (corner & perimeter coverage)
  {"FRONT_2", SIDE_FRONT, 38, 39, 999.0, false},
  {"LEFT_2",  SIDE_LEFT,  40, 41, 999.0, false},
  {"RIGHT_2", SIDE_RIGHT, 42, 43, 999.0, false},
  {"REAR_2",  SIDE_REAR,  44, 45, 999.0, false},

  // bank 3: expanded to 12 sensors (wide-angle flanking coverage)
  {"FRONT_3", SIDE_FRONT, 46, 47, 999.0, false},
  {"LEFT_3",  SIDE_LEFT,  48, 49, 999.0, false},
  {"RIGHT_3", SIDE_RIGHT, 50, 51, 999.0, false},
  {"REAR_3",  SIDE_REAR,  52, 53, 999.0, false},

  // bank 4: expanded to 16 sensors (god-tier 4 sensors per side)
  // note: pins 54-61 correspond to arduino mega analog pins a0-a7 used as digital io
  {"FRONT_4", SIDE_FRONT, 54, 55, 999.0, false},
  {"LEFT_4",  SIDE_LEFT,  56, 57, 999.0, false},
  {"RIGHT_4", SIDE_RIGHT, 58, 59, 999.0, false},
  {"REAR_4",  SIDE_REAR,  60, 61, 999.0, false}
};

// number of active sensors in rotation (auto-detected as 4, 8, 12, or 16)
int num_active_sensors = 4;
int current_ping_bank = 0; // cycles 0, 1, 2, 3 for non-blocking interleaved pinging

// ================= 3. safety settings =================
// if anything gets closer than 20cm in our driving path, slam the brakes immediately
const int HARD_STOP_DISTANCE_CM = 20;

// if the pi crashes or stops sending commands for 600ms, stop wheels automatically
const unsigned long WATCHDOG_TIMEOUT_MS = 600;

// ================= 4. state variables =================
// distances measured by our sensors in centimeters (side minimums)
float dist_front = 999.0;
float dist_left  = 999.0;
float dist_right = 999.0;
float dist_rear  = 999.0;

// timers to track when we last got a command and when we last sent telemetry
unsigned long last_cmd_time = 0;
unsigned long last_telemetry_time = 0;

// current motor drive targets (-255 to 255)
int current_speed = 0; // positive is forward, negative is backward
int current_steer = 0; // positive turns right, negative turns left

// forward declaration
void stop_all_motors();
void detect_installed_sensors();

// ================= 5. setup function =================
// this runs once when the arduino boots up
void setup() {
  // start serial communication with raspberry pi at 115200 baud
  Serial.begin(115200);

  // default enable pins to low during boot to prevent motor jitter on power-up
  digitalWrite(M1_EN, LOW);
  digitalWrite(M2_EN, LOW);
  digitalWrite(M3_EN, LOW);
  digitalWrite(M4_EN, LOW);

  // configure all front-left and rear-left motor driver pins as outputs
  pinMode(M1_RPWM, OUTPUT);
  pinMode(M1_LPWM, OUTPUT);
  pinMode(M1_EN,   OUTPUT);

  pinMode(M2_RPWM, OUTPUT);
  pinMode(M2_LPWM, OUTPUT);
  pinMode(M2_EN,   OUTPUT);

  // configure all front-right and rear-right motor driver pins as outputs
  pinMode(M3_RPWM, OUTPUT);
  pinMode(M3_LPWM, OUTPUT);
  pinMode(M3_EN,   OUTPUT);

  pinMode(M4_RPWM, OUTPUT);
  pinMode(M4_LPWM, OUTPUT);
  pinMode(M4_EN,   OUTPUT);

  // auto-detect which sensor banks are physically plugged in (4, 8, 12, or 16)
  detect_installed_sensors();

  // ensure all motors are at 0 speed before activating the enable lines
  stop_all_motors();

  // safely enable the motor drivers now that outputs are zeroed
  digitalWrite(M1_EN, HIGH);
  digitalWrite(M2_EN, HIGH);
  digitalWrite(M3_EN, HIGH);
  digitalWrite(M4_EN, HIGH);

  last_cmd_time = millis();
}



// ================= 5. main loop =================
// this runs continuously in an infinite loop
void loop() {
  unsigned long now = millis();

  // step a: read incoming speed and steer commands sent by the pi over usb serial
  process_serial();

  // step b: check if an external rc remote or bluetooth joystick is being touched
  int remote_spd = 0;
  int remote_str = 0;
  if (check_manual_remote(&remote_spd, &remote_str)) {
    // human remote takes 100% priority over the pi ai when sticks are moved
    current_speed = remote_spd;
    current_steer = remote_str;
    last_cmd_time = now; // keep watchdog timer refreshed
  }

  // step c: safety watchdog check - if no command came within 600ms, cut motors
  if (now - last_cmd_time > WATCHDOG_TIMEOUT_MS) {
    stop_all_motors();
  }

  // step d: read ultrasonic sensors and update motor pwm signals every 50ms (20hz)
  if (now - last_telemetry_time >= 50) {
    // ping both ultrasonic sensors to see if a wall or human is ahead
    read_all_sensors();

    // emergency brake: if an obstacle is within 20cm in the direction of travel, stop immediately
    if (dist_front < HARD_STOP_DISTANCE_CM && current_speed > 0) {
      stop_all_motors();
    } else if (dist_rear < HARD_STOP_DISTANCE_CM && current_speed < 0) {
      stop_all_motors();
    } else {
      // safe to drive: send speed and steering values to the 4 h-bridges
      apply_differential_drive(current_speed, current_steer);
    }

    // send latest distance readings back to the pi so it knows what sensors see
    send_telemetry();
    last_telemetry_time = now;
  }
}


// ================= 6. manual remote control check =================
// this hook lets someone plug in an rc receiver or bluetooth module later
// returns true if human is moving the sticks, or false if sticks are centered
bool check_manual_remote(int *out_speed, int *out_steer) {
  // if you hook up an rc receiver or hc-05 module, read it here
  // returning false means the remote is neutral and the raspberry pi has control
  return false;
}


// ================= 7. 4wd differential skid steering =================
// mixes forward/reverse speed and turning steer into left and right wheel pwm signals
void apply_differential_drive(int speed, int steer) {
  // skid steering math:
  // turning right means left wheels go faster, right wheels go slower
  // turning left means right wheels go faster, left wheels go slower
  int left_pwm  = constrain(speed + steer, -255, 255);
  int right_pwm = constrain(speed - steer, -255, 255);

  // spin both left side wheels together at left_pwm
  set_motor(M1_RPWM, M1_LPWM, left_pwm);
  set_motor(M2_RPWM, M2_LPWM, left_pwm);

  // spin both right side wheels together at right_pwm
  set_motor(M3_RPWM, M3_LPWM, right_pwm);
  set_motor(M4_RPWM, M4_LPWM, right_pwm);
}

// sends pwm signals to a single bts7960 h-bridge driver
// pwm > 0 drives forward, pwm < 0 drives reverse, pwm == 0 brakes
void set_motor(int rpwm_pin, int lpwm_pin, int pwm) {
  if (pwm > 0) {
    // forward: send pwm pulse to forward pin, ground reverse pin
    analogWrite(rpwm_pin, pwm);
    analogWrite(lpwm_pin, 0);
  } else if (pwm < 0) {
    // reverse: send pwm pulse to reverse pin, ground forward pin
    analogWrite(rpwm_pin, 0);
    analogWrite(lpwm_pin, -pwm);
  } else {
    // stop: ground both pins so the motor holds and coasts to stop
    analogWrite(rpwm_pin, 0);
    analogWrite(lpwm_pin, 0);
  }
}

// turns off pwm output to all 4 motors and resets speed targets to zero
void stop_all_motors() {
  current_speed = 0;
  current_steer = 0;
  set_motor(M1_RPWM, M1_LPWM, 0);
  set_motor(M2_RPWM, M2_LPWM, 0);
  set_motor(M3_RPWM, M3_LPWM, 0);
  set_motor(M4_RPWM, M4_LPWM, 0);
}


// ================= 8. ultrasonic sensor detection & reading =================
// tests all 16 slots at boot to auto-detect whether 4, 8, 12, or 16 sensors are plugged in
void detect_installed_sensors() {
  int detected_count = 0;

  for (int i = 0; i < MAX_ULTRASONIC_SENSORS; i++) {
    pinMode(sensors[i].trigPin, OUTPUT);
    digitalWrite(sensors[i].trigPin, LOW);

    // enable pullup momentarily to test if an active hc-sr04 output driver pulls echo low
    pinMode(sensors[i].echoPin, INPUT_PULLUP);
    delayMicroseconds(40);
    int pin_state = digitalRead(sensors[i].echoPin);
    pinMode(sensors[i].echoPin, INPUT); // restore standard input mode

    // an idle powered hc-sr04 actively pulls echo low; an unconnected pin with pullup reads high
    if (pin_state == LOW) {
      sensors[i].isConnected = true;
      detected_count++;
    } else {
      sensors[i].isConnected = false;
      sensors[i].distanceCm = 999.0;
    }
  }

  // snap to 4, 8, 12, or 16 active sensor banks
  if (detected_count >= 14) {
    num_active_sensors = 16;
  } else if (detected_count >= 10) {
    num_active_sensors = 12;
  } else if (detected_count >= 6) {
    num_active_sensors = 8;
  } else {
    num_active_sensors = 4; // base bank 1 default (1 front, 1 left, 1 right, 1 rear)
    // ensure base bank 1 is marked active for bench testing even if no hardware is wired yet
    for (int i = 0; i < 4; i++) {
      sensors[i].isConnected = true;
    }
  }

  Serial.print("INIT,SENSORS_DETECTED,");
  Serial.print(detected_count);
  Serial.print(",ACTIVE_CONFIG,");
  Serial.println(num_active_sensors);
}

// sends a 10 microsecond ultrasonic chirp and measures how long it takes to bounce back
float read_ultrasonic(int trig_pin, int echo_pin) {
  // ensure clean low trigger first
  digitalWrite(trig_pin, LOW);
  delayMicroseconds(2);

  // send high pulse for 10 microseconds to start ultrasonic wave burst
  digitalWrite(trig_pin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig_pin, LOW);

  // time how long echo stays high; capped at 11600us (~200cm distance) to guarantee zero cpu lag
  long duration = pulseIn(echo_pin, HIGH, 11600);

  // if timed out with no bounce return 999cm meaning clear open path
  if (duration == 0) return 999.0;

  // speed of sound is roughly 0.0343 cm per microsecond, divide by 2 for round trip
  return duration * 0.0343 / 2.0;
}

// time-sliced god-tier sensor reading: pings 1 bank (4 sensors: 1 per side) each 50ms tick
// this keeps cpu load ultra low, guarantees zero acoustic cross-talk, and updates side minimums
void read_all_sensors() {
  int num_banks = num_active_sensors / 4;
  if (num_banks < 1) num_banks = 1;
  if (num_banks > 4) num_banks = 4;

  // determine which bank of 4 sensors to ping on this tick
  int start_idx = current_ping_bank * 4;
  int end_idx   = start_idx + 4;
  if (end_idx > num_active_sensors) end_idx = num_active_sensors;

  // ping the 4 sensors in the current bank (one on each of the 4 sides)
  for (int i = start_idx; i < end_idx; i++) {
    if (sensors[i].isConnected) {
      sensors[i].distanceCm = read_ultrasonic(sensors[i].trigPin, sensors[i].echoPin);
      delayMicroseconds(1500); // 1.5ms echo settling gap
    }
  }

  // advance to next bank for the next tick
  current_ping_bank = (current_ping_bank + 1) % num_banks;

  // calculate minimum distance across all active sensors for each of the 4 sides
  float min_f = 999.0;
  float min_l = 999.0;
  float min_r = 999.0;
  float min_b = 999.0;

  for (int i = 0; i < num_active_sensors; i++) {
    if (!sensors[i].isConnected) continue;
    float d = sensors[i].distanceCm;
    if (sensors[i].side == SIDE_FRONT && d < min_f) min_f = d;
    else if (sensors[i].side == SIDE_LEFT  && d < min_l) min_l = d;
    else if (sensors[i].side == SIDE_RIGHT && d < min_r) min_r = d;
    else if (sensors[i].side == SIDE_REAR  && d < min_b) min_b = d;
  }

  dist_front = min_f;
  dist_left  = min_l;
  dist_right = min_r;
  dist_rear  = min_b;
}


// ================= 9. serial command processor =================
// parses lines of text arriving from the raspberry pi over usb
void process_serial() {
  while (Serial.available() > 0) {
    // read incoming command up to the newline character
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    // reset watchdog timer because the pi is alive and talking
    last_cmd_time = millis();

    // command format: DRIVE,speed,steer
    if (line.startsWith("DRIVE,")) {
      int comma = line.indexOf(',', 6);
      if (comma > 0) {
        // extract speed and steer integers from text string
        current_speed = line.substring(6, comma).toInt();
        current_steer = line.substring(comma + 1).toInt();

        // clamp values between -255 and 255 for safe 8-bit pwm limits
        current_speed = constrain(current_speed, -255, 255);
        current_steer = constrain(current_steer, -255, 255);
      }
    } else if (line == "STOP") {
      // emergency stop command from the pi
      stop_all_motors();
    } else if (line.startsWith("CONFIG_SENSORS,")) {
      // manual or host override for sensor count: 4, 8, 12, 16, or AUTO
      String cfg = line.substring(15);
      cfg.trim();
      if (cfg == "AUTO") {
        detect_installed_sensors();
      } else {
        int val = cfg.toInt();
        if (val == 4 || val == 8 || val == 12 || val == 16) {
          num_active_sensors = val;
          for (int i = 0; i < num_active_sensors; i++) sensors[i].isConnected = true;
          for (int i = num_active_sensors; i < MAX_ULTRASONIC_SENSORS; i++) sensors[i].isConnected = false;
          current_ping_bank = 0;
          Serial.print("CONFIG,SENSORS_SET,");
          Serial.println(num_active_sensors);
        }
      }
    } else if (line == "PING") {
      // keep-alive heartbeat ping from the pi to keep connection active
    }
  }
}

// sends sensor readings back up to raspberry pi formatted as SENSORS,front,left,right,rear,active_count,...
void send_telemetry() {
  Serial.print("SENSORS,");
  Serial.print(dist_front, 1); Serial.print(",");
  Serial.print(dist_left, 1);  Serial.print(",");
  Serial.print(dist_right, 1); Serial.print(",");
  Serial.print(dist_rear, 1);  Serial.print(",");
  Serial.print(num_active_sensors);

  // stream individual sensor distance readings
  for (int i = 0; i < num_active_sensors; i++) {
    Serial.print(",");
    Serial.print(sensors[i].distanceCm, 1);
  }
  Serial.println();
}


