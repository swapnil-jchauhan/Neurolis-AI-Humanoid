/*
  project neurolis - arduino mega 4wd motor & dual ultrasonic controller
  ======================================================================
  board: arduino mega 2560
  baud rate: 115200
  
  what is plugged into this board:
    - 4 johnson dc motors for the 4wd wheels
    - 4 bts7960 high-power motor drivers (2 drivers on left, 2 on right)
    - 2 hc-sr04 ultrasonic distance sensors mounted on the front bumper
    - emergency stop triggers automatically if anything gets closer than 20cm
*/

// ================= 1. pin assignments =================
// left side wheel motors (driven by bts7960 h-bridges)
// motor 1: front-left wheel
const int M1_RPWM = 2;   // forward speed pin (pwm signal from 0 to 255)
const int M1_LPWM = 3;   // reverse speed pin (pwm signal from 0 to 255)
const int M1_EN   = 26;  // enable pin, must be set high to turn the driver on

// motor 2: rear-left wheel
const int M2_RPWM = 4;   // forward speed pin
const int M2_LPWM = 5;   // reverse speed pin
const int M2_EN   = 27;  // enable pin to power up the driver

// right side wheel motors (driven by bts7960 h-bridges)
// motor 3: front-right wheel
const int M3_RPWM = 6;   // forward speed pin
const int M3_LPWM = 7;   // reverse speed pin
const int M3_EN   = 28;  // enable pin to power up the driver

// motor 4: rear-right wheel
const int M4_RPWM = 8;   // forward speed pin
const int M4_LPWM = 9;   // reverse speed pin
const int M4_EN   = 29;  // enable pin to power up the driver

// ultrasonic distance sensors mounted on front bumper
// left side sensor: sends sonic chirp on trig, times the echo return on echo
const int US_LEFT_TRIG  = 30; // trigger pin sends out sound burst
const int US_LEFT_ECHO  = 31; // echo pin listens for the bounce

// right side sensor: sends sonic chirp on trig, times the echo return on echo
const int US_RIGHT_TRIG = 32; // trigger pin sends out sound burst
const int US_RIGHT_ECHO = 33; // echo pin listens for the bounce


// ================= 2. safety settings =================
// if anything gets closer than 20cm ahead, slam the brakes immediately
const int HARD_STOP_DISTANCE_CM = 20;

// if the pi crashes or stops sending commands for 600ms, stop wheels automatically
const unsigned long WATCHDOG_TIMEOUT_MS = 600;


// ================= 3. state variables =================
// distances measured by our front sensors in centimeters
float dist_left  = 999.0;
float dist_right = 999.0;
float dist_front = 999.0; // tracks whichever side has an obstacle closer

// timers to track when we last got a command and when we last sent telemetry
unsigned long last_cmd_time = 0;
unsigned long last_telemetry_time = 0;

// current motor drive targets (-255 to 255)
int current_speed = 0; // positive is forward, negative is backward
int current_steer = 0; // positive turns right, negative turns left


// ================= 4. setup function =================
// this runs once when the arduino boots up
void setup() {
  // start serial communication with raspberry pi at 115200 baud
  Serial.begin(115200);

  // configure all front-left and rear-left motor driver pins as outputs
  pinMode(M1_RPWM, OUTPUT);
  pinMode(M1_LPWM, OUTPUT);
  pinMode(M1_EN,   OUTPUT);
  digitalWrite(M1_EN, HIGH); // turn on front-left driver chip

  pinMode(M2_RPWM, OUTPUT);
  pinMode(M2_LPWM, OUTPUT);
  pinMode(M2_EN,   OUTPUT);
  digitalWrite(M2_EN, HIGH); // turn on rear-left driver chip

  // configure all front-right and rear-right motor driver pins as outputs
  pinMode(M3_RPWM, OUTPUT);
  pinMode(M3_LPWM, OUTPUT);
  pinMode(M3_EN,   OUTPUT);
  digitalWrite(M3_EN, HIGH); // turn on front-right driver chip

  pinMode(M4_RPWM, OUTPUT);
  pinMode(M4_LPWM, OUTPUT);
  pinMode(M4_EN,   OUTPUT);
  digitalWrite(M4_EN, HIGH); // turn on rear-right driver chip

  // configure ultrasonic trigger pins as output (sound out) and echo as input (sound in)
  pinMode(US_LEFT_TRIG,  OUTPUT);
  pinMode(US_LEFT_ECHO,  INPUT);
  pinMode(US_RIGHT_TRIG, OUTPUT);
  pinMode(US_RIGHT_ECHO, INPUT);

  // make sure all wheels are stopped right after booting up
  stop_all_motors();
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

    // emergency brake: if an obstacle is within 20cm and we are driving forward, stop immediately
    if (dist_front < HARD_STOP_DISTANCE_CM && current_speed > 0) {
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


// ================= 8. ultrasonic sensor reading =================
// sends a 10 microsecond ultrasonic chirp and measures how long it takes to bounce back
float read_ultrasonic(int trig_pin, int echo_pin) {
  // make sure trigger pin is clean and low first
  digitalWrite(trig_pin, LOW);
  delayMicroseconds(2);

  // send high pulse for 10 microseconds to start ultrasonic wave burst
  digitalWrite(trig_pin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig_pin, LOW);

  // time how long echo pin stays high (capped at 15ms to avoid hanging the loop)
  long duration = pulseIn(echo_pin, HIGH, 15000);

  // if timed out with no bounce return 999cm meaning clear open path
  if (duration == 0) return 999.0;

  // speed of sound is roughly 0.0343 cm per microsecond, divide by 2 for round trip
  return duration * 0.0343 / 2.0;
}

// reads both left and right bumper sensors and picks whichever obstacle is closer
void read_all_sensors() {
  dist_left  = read_ultrasonic(US_LEFT_TRIG,  US_LEFT_ECHO);
  dist_right = read_ultrasonic(US_RIGHT_TRIG, US_RIGHT_ECHO);

  // closest obstacle is the one we care about for braking
  dist_front = min(dist_left, dist_right);
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
    } else if (line == "PING") {
      // keep-alive heartbeat ping from the pi to keep connection active
    }
  }
}

// sends sensor readings back up to raspberry pi formatted as SENSORS,front,left,right
void send_telemetry() {
  Serial.print("SENSORS,");
  Serial.print(dist_front, 1); Serial.print(",");
  Serial.print(dist_left, 1);  Serial.print(",");
  Serial.println(dist_right, 1);
}
