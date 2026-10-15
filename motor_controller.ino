/*
  Neurolis Standalone Motor Controller
  ------------------------------------
  Arduino Mega 2560

  Controls:
    - 4 DC motors
    - 4 BTS7960 motor drivers
    - 4 HC-SR04 ultrasonic sensors

  Communication:
    Raspberry Pi <-> USB Serial <-> Arduino Mega

  Commands:
    DRIVE,<speed>,<steer>
    STOP
    PING

  speed : -255 to +255
  steer : -255 to +255

  Differential drive:
    left  = speed + steer
    right = speed - steer

  Safety:
    - Motor watchdog
    - Front/rear obstacle protection
*/

#include <Arduino.h>

// ============================================================
// MOTOR PINS
// ============================================================

// Front Left
const uint8_t FL_RPWM = 2;
const uint8_t FL_LPWM = 3;

// Rear Left
const uint8_t RL_RPWM = 4;
const uint8_t RL_LPWM = 5;

// Front Right
const uint8_t FR_RPWM = 6;
const uint8_t FR_LPWM = 7;

// Rear Right
const uint8_t RR_RPWM = 8;
const uint8_t RR_LPWM = 9;


// ============================================================
// ULTRASONIC SENSOR PINS
// ============================================================

// Front Left
const uint8_t US_FL_TRIG = 30;
const uint8_t US_FL_ECHO = 31;

// Rear Left
const uint8_t US_RL_TRIG = 32;
const uint8_t US_RL_ECHO = 33;

// Front Right
const uint8_t US_FR_TRIG = 34;
const uint8_t US_FR_ECHO = 35;

// Rear Right
const uint8_t US_RR_TRIG = 36;
const uint8_t US_RR_ECHO = 37;


// ============================================================
// SETTINGS
// ============================================================

const long SERIAL_BAUD = 115200;

// Emergency obstacle distance
const float OBSTACLE_STOP_CM = 20.0;

// Distance at which we consider the sensor invalid
const float MAX_SENSOR_DISTANCE_CM = 400.0;

// If no command arrives within this time,
// the robot stops.
const unsigned long WATCHDOG_TIMEOUT_MS = 600;


// ============================================================
// STATE
// ============================================================

int currentSpeed = 0;
int currentSteer = 0;

unsigned long lastCommandTime = 0;

bool emergencyStop = false;


// ============================================================
// SENSOR DATA
// ============================================================

float distanceFL = 999.0;
float distanceRL = 999.0;
float distanceFR = 999.0;
float distanceRR = 999.0;


// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(SERIAL_BAUD);

  // Motor outputs
  pinMode(FL_RPWM, OUTPUT);
  pinMode(FL_LPWM, OUTPUT);

  pinMode(RL_RPWM, OUTPUT);
  pinMode(RL_LPWM, OUTPUT);

  pinMode(FR_RPWM, OUTPUT);
  pinMode(FR_LPWM, OUTPUT);

  pinMode(RR_RPWM, OUTPUT);
  pinMode(RR_LPWM, OUTPUT);


  // Ultrasonic sensors
  pinMode(US_FL_TRIG, OUTPUT);
  pinMode(US_FL_ECHO, INPUT);

  pinMode(US_RL_TRIG, OUTPUT);
  pinMode(US_RL_ECHO, INPUT);

  pinMode(US_FR_TRIG, OUTPUT);
  pinMode(US_FR_ECHO, INPUT);

  pinMode(US_RR_TRIG, OUTPUT);
  pinMode(US_RR_ECHO, INPUT);


  // Make sure trigger pins start LOW
  digitalWrite(US_FL_TRIG, LOW);
  digitalWrite(US_RL_TRIG, LOW);
  digitalWrite(US_FR_TRIG, LOW);
  digitalWrite(US_RR_TRIG, LOW);


  // Start with motors stopped
  stopAllMotors();

  lastCommandTime = millis();

  Serial.println("NEUROLIS MOTOR CONTROLLER READY");
  Serial.println("Arduino Mega 2560");
  Serial.println("Motors: 4");
  Serial.println("Ultrasonic sensors: 4");
}


// ============================================================
// MAIN LOOP
// ============================================================

void loop() {

  // ----------------------------------------------------------
  // 1. Read commands from Raspberry Pi
  // ----------------------------------------------------------

  processSerial();


  // ----------------------------------------------------------
  // 2. Read ultrasonic sensors
  // ----------------------------------------------------------

  readUltrasonicSensors();


  // ----------------------------------------------------------
  // 3. Obstacle protection
  // ----------------------------------------------------------

  checkObstacles();


  // ----------------------------------------------------------
  // 4. Watchdog
  // ----------------------------------------------------------

  checkWatchdog();


  // ----------------------------------------------------------
  // 5. Telemetry
  // ----------------------------------------------------------

  sendTelemetry();


  // Small delay to prevent excessive serial traffic
  delay(20);
}


// ============================================================
// MOTOR CONTROL
// ============================================================

void setMotor(uint8_t rpwmPin, uint8_t lpwmPin, int speed) {

  speed = constrain(speed, -255, 255);

  if (speed > 0) {

    // Forward
    analogWrite(rpwmPin, speed);
    analogWrite(lpwmPin, 0);

  }
  else if (speed < 0) {

    // Reverse
    analogWrite(rpwmPin, 0);
    analogWrite(lpwmPin, -speed);

  }
  else {

    // Stop
    analogWrite(rpwmPin, 0);
    analogWrite(lpwmPin, 0);
  }
}


// ============================================================
// DRIVE
// ============================================================

void drive(int speed, int steer) {

  speed = constrain(speed, -255, 255);
  steer = constrain(steer, -255, 255);

  int leftSpeed = speed + steer;
  int rightSpeed = speed - steer;

  leftSpeed = constrain(leftSpeed, -255, 255);
  rightSpeed = constrain(rightSpeed, -255, 255);


  // Left side
  setMotor(FL_RPWM, FL_LPWM, leftSpeed);
  setMotor(RL_RPWM, RL_LPWM, leftSpeed);

  // Right side
  setMotor(FR_RPWM, FR_LPWM, rightSpeed);
  setMotor(RR_RPWM, RR_LPWM, rightSpeed);
}


// ============================================================
// STOP ALL MOTORS
// ============================================================

void stopAllMotors() {

  analogWrite(FL_RPWM, 0);
  analogWrite(FL_LPWM, 0);

  analogWrite(RL_RPWM, 0);
  analogWrite(RL_LPWM, 0);

  analogWrite(FR_RPWM, 0);
  analogWrite(FR_LPWM, 0);

  analogWrite(RR_RPWM, 0);
  analogWrite(RR_LPWM, 0);

  currentSpeed = 0;
  currentSteer = 0;
}


// ============================================================
// ULTRASONIC READING
// ============================================================

float readDistance(uint8_t trigPin, uint8_t echoPin) {

  // Make sure trigger starts LOW
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  // 10 µs trigger pulse
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // Wait for echo
  unsigned long duration = pulseIn(
    echoPin,
    HIGH,
    25000
  );

  // No echo
  if (duration == 0) {
    return 999.0;
  }

  // Convert microseconds to centimeters
  float distance = duration * 0.0343 / 2.0;

  if (distance <= 0 || distance > MAX_SENSOR_DISTANCE_CM) {
    return 999.0;
  }

  return distance;
}


// ============================================================
// READ ALL ULTRASONIC SENSORS
// ============================================================

void readUltrasonicSensors() {

  /*
    Sensors are read sequentially to reduce ultrasonic
    cross-talk.
  */

  distanceFL = readDistance(
    US_FL_TRIG,
    US_FL_ECHO
  );

  delay(5);

  distanceFR = readDistance(
    US_FR_TRIG,
    US_FR_ECHO
  );

  delay(5);

  distanceRL = readDistance(
    US_RL_TRIG,
    US_RL_ECHO
  );

  delay(5);

  distanceRR = readDistance(
    US_RR_TRIG,
    US_RR_ECHO
  );

  delay(5);
}


// ============================================================
// OBSTACLE SAFETY
// ============================================================

void checkObstacles() {

  bool frontBlocked =
    (distanceFL < OBSTACLE_STOP_CM) ||
    (distanceFR < OBSTACLE_STOP_CM);

  bool rearBlocked =
    (distanceRL < OBSTACLE_STOP_CM) ||
    (distanceRR < OBSTACLE_STOP_CM);


  // Robot moving forward
  if (currentSpeed > 0 && frontBlocked) {

    stopAllMotors();

    emergencyStop = true;

    Serial.println("OBSTACLE,FRONT");
  }


  // Robot moving backward
  else if (currentSpeed < 0 && rearBlocked) {

    stopAllMotors();

    emergencyStop = true;

    Serial.println("OBSTACLE,REAR");
  }
}


// ============================================================
// WATCHDOG
// ============================================================

void checkWatchdog() {

  if (millis() - lastCommandTime > WATCHDOG_TIMEOUT_MS) {

    if (currentSpeed != 0 || currentSteer != 0) {

      stopAllMotors();

      Serial.println("WATCHDOG,STOP");
    }
  }
}


// ============================================================
// SERIAL COMMAND PROCESSOR
// ============================================================

void processSerial() {

  if (!Serial.available()) {
    return;
  }

  String command = Serial.readStringUntil('\n');

  command.trim();


  // ----------------------------------------------------------
  // STOP
  // ----------------------------------------------------------

  if (command == "STOP") {

    stopAllMotors();

    emergencyStop = false;

    lastCommandTime = millis();

    Serial.println("OK,STOP");

    return;
  }


  // ----------------------------------------------------------
  // PING
  // ----------------------------------------------------------

  if (command == "PING") {

    Serial.println("PONG");

    return;
  }


  // ----------------------------------------------------------
  // DRIVE,speed,steer
  // ----------------------------------------------------------

  if (command.startsWith("DRIVE,")) {

    int comma1 = command.indexOf(',');
    int comma2 = command.indexOf(',', comma1 + 1);

    if (comma2 == -1) {

      Serial.println("ERROR,BAD_DRIVE_COMMAND");

      return;
    }


    String speedText =
      command.substring(comma1 + 1, comma2);

    String steerText =
      command.substring(comma2 + 1);


    int speed = speedText.toInt();
    int steer = steerText.toInt();


    speed = constrain(speed, -255, 255);
    steer = constrain(steer, -255, 255);


    // If emergency stop is active,
    // don't allow movement until STOP is received.
    if (emergencyStop) {

      Serial.println("BLOCKED,EMERGENCY_STOP");

      return;
    }


    currentSpeed = speed;
    currentSteer = steer;

    drive(currentSpeed, currentSteer);

    lastCommandTime = millis();


    Serial.print("OK,DRIVE,");
    Serial.print(currentSpeed);
    Serial.print(",");
    Serial.println(currentSteer);

    return;
  }


  // ----------------------------------------------------------
  // Unknown command
  // ----------------------------------------------------------

  Serial.println("ERROR,UNKNOWN_COMMAND");
}


// ============================================================
// TELEMETRY
// ============================================================

void sendTelemetry() {

  static unsigned long lastTelemetry = 0;

  // Send telemetry every 200 ms
  if (millis() - lastTelemetry < 200) {
    return;
  }

  lastTelemetry = millis();


  Serial.print("SENSORS,");

  Serial.print(distanceFL);
  Serial.print(",");

  Serial.print(distanceFR);
  Serial.print(",");

  Serial.print(distanceRL);
  Serial.print(",");

  Serial.print(distanceRR);
  Serial.print(",");

  Serial.print(currentSpeed);
  Serial.print(",");

  Serial.print(currentSteer);
  Serial.print(",");

  Serial.println(emergencyStop ? 1 : 0);
}