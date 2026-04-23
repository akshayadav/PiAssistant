# Rover Integration — Hardware Design Document

## Vision & Use Cases

PiAssistant is evolving from a stationary smart assistant into a **mobile AI rover** — a smart assistant on wheels that doubles as an autonomous security camera. The rover mounts a Pi 5 (or Jetson Orin Nano in future) on a 4WD chassis, with a Pico microcontroller handling real-time motor/sensor control via I2C.

### Operating Modes

| Mode | Behavior |
|---|---|
| **Assistant** | Drives to you when called, responds to voice, shows info on screen |
| **Security patrol** | Autonomous patrol routes, detects people/motion, alerts you, records clips |
| **Sentry** | Parks in a spot, monitors with camera + PIR, alerts on movement |
| **Remote control** | Drive from dashboard/phone anywhere via Cloudflare tunnel |

### Why Integrate with PiAssistant (Not Standalone)

PiAssistant already has the brain (LLM tool-use loop), the dashboard, the service abstraction, and the deployment infrastructure. Adding rover capabilities as new services + tools means:
- The LLM can plan multi-step navigation ("go to the kitchen and check if the stove is off")
- Dashboard gets a rover control widget alongside existing widgets
- Voice commands work immediately ("Hey Bunty, patrol the house")
- Security alerts flow through existing notification patterns

---

## Decision 1: Body Controller Architecture

**Problem**: Who drives the motors and reads sensors — the Pi/Jetson directly, or a dedicated microcontroller?

### Options Evaluated

| Option | Description | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A: Pi GPIO direct** | Pi drives motors/sensors via GPIO | Simplest wiring, no extra board | Linux isn't real-time — jitter in PWM timing, unreliable microsecond echo measurement, bad motor code can hang the whole assistant | **Rejected** |
| **B: Pico W via WiFi HTTP** | Same pattern as PicoWeather — Pico W runs HTTP server, Pi sends commands over WiFi | Matches existing codebase pattern, wireless | Adds 5-50ms latency per command, WiFi can drop, costs more (Pico W vs Pico), requires WiFi infrastructure — all downsides for devices on the same chassis | **Rejected** |
| **C: Pico via I2C** | Pico as I2C peripheral, Pi as I2C controller, wired connection | Microsecond latency, rock solid, no WiFi needed, crash isolation (Pico crash doesn't take down Pi), cheaper (plain Pico ~$4 vs Pico W ~$6) | 2 data wires + GND needed (~1m max, fine on a rover), different code pattern than PicoWeather | **Chosen** |
| **D: Arduino/Teensy via USB UART** | Traditional robotics approach — Arduino handles motors, Pi sends serial commands | Well-documented in robotics community, real-time capable | Pico is cheaper, MicroPython matches existing codebase (vs C++ for Arduino), Pico has sufficient capability, USB cable adds bulk | **Not chosen** |

### Why I2C Wins

| Factor | I2C (wired) | WiFi HTTP |
|---|---|---|
| Latency | ~microseconds | ~5-50ms per request |
| Reliability | Rock solid, no network issues | WiFi can drop, reconnect delays |
| Power | No WiFi radio needed (plain Pico) | Pico W draws ~40mA extra for WiFi |
| Wiring | 2 data wires (SDA + SCL) + GND, short runs | Zero wires, but needs WiFi network |
| Range | ~1 meter max (on a rover, this is fine) | Unlimited on LAN |
| Throughput | 400kHz typical, plenty for motor commands | Way more than needed |
| Complexity | Pico is I2C peripheral, Pi is controller | HTTP server on Pico, HTTP client on Pi |
| Cost | Regular Pico (~$4) | Pico W (~$6) |

**Decision**: Pico via I2C. Both boards are physically on the same chassis — WiFi adds latency and failure modes for zero benefit. I2C gives microsecond response times for motor control and obstacle avoidance.

---

## Decision 2: Communication Protocol

### Why I2C Over Other Wired Options

| Protocol | Speed | Wires | Addressing | Verdict |
|---|---|---|---|---|
| **I2C** | 100-400kHz | 2 (SDA + SCL) + GND | Built-in addressing, multi-device | **Chosen** — simplest wiring, Pi has native support, Pico has 2 hardware I2C peripherals |
| **SPI** | Up to 50MHz | 4+ (MOSI, MISO, CLK, CS per device) | Chip select per device | Not chosen — more wires, overkill speed for motor commands, no multi-device addressing |
| **UART** | Up to 115200 baud typical | 2 (TX + RX) | Point-to-point only | Not chosen — no addressing (can't share bus with other I2C sensors), need framing protocol |
| **USB** | 12Mbps+ | 1 cable | Enumeration-based | Not chosen — bulky cable, Pi has limited USB ports, more latency than I2C |

### I2C Register Map

Standard register-based protocol, same pattern used by I2C sensors like MPU6050:

| Register | R/W | Size | Purpose |
|---|---|---|---|
| `0x01` | W | 1 byte (int8) | Left motors speed (-100 to +100) |
| `0x02` | W | 1 byte (int8) | Right motors speed (-100 to +100) |
| `0x03` | W | 1 byte | Command: 0=stop, 1=brake, 2=coast |
| `0x04` | W | 1 byte | Pan servo angle (0-180) |
| `0x05` | W | 1 byte | Tilt servo angle (0-180) |
| `0x06` | W | 1 byte | IR LEDs: 0=off, 1=on |
| `0x10` | R | 2 bytes (uint16) | Ultrasonic distance (cm) |
| `0x12` | R | 1 byte | Cliff sensors: bit0=left, bit1=right (1=edge detected) |
| `0x13` | R | 1 byte | PIR motion detected (0/1) |
| `0x20` | R | 2 bytes (int16) | IMU accel X |
| `0x22` | R | 2 bytes (int16) | IMU accel Y |
| `0x24` | R | 2 bytes (int16) | IMU accel Z |
| `0x26` | R | 2 bytes (int16) | IMU gyro X |
| `0x28` | R | 2 bytes (int16) | IMU gyro Y |
| `0x2A` | R | 2 bytes (int16) | IMU gyro Z |
| `0x30` | R | 2 bytes (uint16) | Battery voltage (mV) |
| `0x32` | R | 2 bytes (int16) | Battery current (mA) |
| `0x34` | R | 1 byte | Status flags: bit0=obstacle, bit1=cliff, bit2=battery_low, bit3=watchdog_active |
| `0xFE` | R | 1 byte | Firmware version |
| `0xFF` | R/W | 1 byte | Pico I2C address (default 0x42) |

### Dual I2C Bus Design

The Pico has two hardware I2C peripherals. Using both prevents bus contention:

| Bus | Controller | Peripheral(s) | Purpose |
|---|---|---|---|
| **I2C0 (Pico)** | Pi/Jetson (GPIO 2, 3) | Pico (address 0x42) | Pi sends motor commands, reads sensor data |
| **I2C1 (Pico)** | Pico (GPIO 14, 15) | MPU6050 (0x68), INA219 (0x40) | Pico reads IMU + battery locally for fast safety decisions |

**Why two buses**: The Pico needs to read the IMU at high frequency (100Hz+) for orientation and the INA219 for battery monitoring. If these shared the bus with Pi commands, there'd be contention. Separate buses mean the Pico can read sensors in a tight local loop while the Pi reads/writes at its own pace.

---

## Decision 3: Chassis

**Problem**: Need a platform large enough to carry Pi/Jetson + battery + camera + sensors, durable enough for daily use.

### Options Evaluated

| Chassis | Size | Material | Suspension | Motors | Mounting space | Price | Verdict |
|---|---|---|---|---|---|---|---|
| **~~Yahboom Suspension 4WD~~** | 30x28cm | Aluminum | Yes | 12V, 75:1 metal gearbox | Extensive | ~$80-120 | ~~Originally chosen~~ — **DISCONTINUED** (Pololu, 2026) |
| **Yahboom Suspension 4WD** | 23x20x13.5cm | Aluminum (3-layer) | Yes (pendulum) | 12V 520 DC with encoders, 1:56 ratio | 3-layer plates with screw holes for lidar/camera/boards | ~$60-80 | **Chosen** (replacement) |
| **Devastator Tank (DFRobot)** | 22.5x22x10.8cm | Aluminum + tank treads | No (tracks absorb some) | **6V** (2-7.5V), 45:1, 133RPM | Moderate | ~$60-80 | **Rejected** |
| **Yahboom 4WD (no suspension)** | 23x20cm | Aluminum | No | 12V 520 DC with encoders | Flat plate with mounting holes | ~$40-50 | Not chosen |
| **Acrylic hobby chassis** | ~20x15cm | Acrylic (laser-cut) | No | TT motors (3-6V, plastic gears) | Minimal | ~$15-20 | Rejected |

### Detailed Rationale

**Yahboom Suspension 4WD (DISCONTINUED)**:
- Was the gold standard — aluminum, suspension on all 4 wheels, 12V motors, 30x28cm platform
- **Discontinued by Pololu/Dagu as of 2026** — no longer available for purchase
- The Yahboom Suspension 4WD is the closest modern equivalent with comparable or better specs

**Yahboom Suspension 4WD (Chosen)**:
- **Pendulum suspension** on all 4 wheels — keeps all wheels in contact with ground over uneven terrain, same key advantage as the discontinued Wild Thumper
- 3-layer aluminum alloy construction (3.25mm thick plates) — extremely sturdy, 2kg payload capacity
- **12V 520 DC motors with encoders included** — encoders enable speed feedback, straight-line PID control, and odometry out of the box (Wild Thumper didn't include encoders)
- 1:56 gear reduction ratio — good balance of speed and torque
- Pre-designed mounting holes for lidar, camera, display, main control board
- Compatible with Raspberry Pi 5, Jetson Nano, Arduino
- Available on Amazon with good reviews and Yahboom support
- ~$60-80 — actually cheaper than the Wild Thumper was
- **Advantage over Wild Thumper**: Built-in motor encoders (Wild Thumper motors had no encoders)

**Devastator Tank (Rejected)**:
- Tank treads provide excellent traction on smooth floors and can climb over cables/thresholds
- Metal construction is durable, 3kg payload capacity
- **Critical problem: motors are rated 6V (2-7.5V operating range)** — incompatible with our 3S LiPo (11.1V). Would need a separate voltage regulator for motors, adding complexity and defeating the single-battery design
- Smaller platform — tighter fit for all components
- Tracks wear over time and need replacement
- Cannot strafe (no mecanum wheel upgrade path)
- Only 2 motors (not 4WD) — less traction than 4-motor setup
- **When to choose instead**: Only if using a 2S LiPo (7.4V) or separate motor battery, and tank-tread aesthetic/traction is a priority

**Yahboom 4WD without suspension (Not chosen)**:
- Same great 520 encoder motors and aluminum construction
- But no suspension — electronics bounce on uneven surfaces
- Risk of connector loosening, SD card corruption from vibration
- ~$20 cheaper than suspension version — not worth the savings
- **When to choose**: Budget-constrained builds on perfectly smooth floors only

**Acrylic hobby chassis (Rejected)**:
- Too fragile — acrylic cracks under stress, flexes under weight
- Too small for Pi + battery + camera + sensors
- TT motors with plastic gears are too weak for heavy payload
- No meaningful mounting options
- Only suitable for ultralight hobby projects, not a production rover

---

## Decision 4: Motors

**Constraint**: Must match chassis and battery voltage (3S LiPo = 11.1V nominal, 12.6V fully charged).

### Options Evaluated

| Motor | Voltage | Gearbox | Gear ratio | Stall current | Encoders | Price | Verdict |
|---|---|---|---|---|---|---|---|
| **Yahboom 520 DC (included)** | 12V | Metal | 1:56 | ~2.5A | Yes (built-in) | Included with chassis | **Chosen** |
| ~~Wild Thumper included~~ | 12V | Metal | 75:1 | ~2.5A | No | ~~Included~~ | ~~Was chosen~~ — chassis discontinued |
| **JGA25-371 with encoders** | 12V | Metal | 21.3:1 to 378:1 | ~2A | Yes (quadrature) | ~$12 each ($48 for 4) | Best standalone option |
| **TT motors (yellow hobby)** | 3-6V | Plastic | ~48:1 | ~0.8A | No | ~$2 each | **Rejected** |

### Detailed Rationale

**Yahboom 520 DC with encoders (Chosen)**:
- Come pre-mounted in the Yahboom Suspension 4WD chassis — no compatibility guessing
- 12V rated — perfect for 3S LiPo (11.1V nominal)
- Metal gearbox — won't strip under load like plastic
- 1:56 ratio — good torque for carrying a heavy payload (Pi + battery + sensors)
- **Built-in encoders** — quadrature encoders enable straight-line PID control, odometry (distance tracking), and speed feedback out of the box. This is an upgrade over the discontinued Wild Thumper motors which had no encoders.
- ~2.5A stall per motor — well within L298N and 3S LiPo capabilities

**JGA25-371 with encoders (Not chosen, but recommended standalone)**:
- Best option if buying a chassis without motors
- Built-in quadrature encoders enable: straight-line driving (PID control), distance measurement (odometry), speed feedback
- Multiple gear ratios available — 34:1 is ideal balance of speed and torque for indoor rovers
- **When to choose**: If building on a custom chassis

**TT motors / yellow hobby motors (Rejected)**:
- Plastic gears strip under load — a rover carrying Pi + battery + sensors is heavy
- 3-6V rated — doesn't match 3S LiPo voltage without a regulator
- Too weak for a production rover
- Only suitable for ultralight hobby projects

---

## Decision 5: Wheels & Treads

### Options Evaluated

| Type | Movement | Traction | Complexity | Price | Verdict |
|---|---|---|---|---|---|
| **Rubber tires (standard)** | Forward/back + tank steering | Good on most surfaces | Simple — left/right speed differential | Included with Wild Thumper | **Chosen** |
| **Mecanum wheels** | Omnidirectional (strafe, diagonal, rotate) | Moderate on smooth floors, poor on carpet | Complex — each wheel needs independent speed + direction | ~$30-50 for set of 4 | Future upgrade |
| **Tank treads** | Forward/back + tank steering | Excellent — climbs cables, thresholds | Simple — same as rubber tires | Included with Devastator | Alternative |

### Detailed Rationale

**Rubber tires (Chosen)**:
- Included with Wild Thumper chassis
- Good grip on hardwood, tile, and low carpet
- Simple tank-style steering: left wheels and right wheels at different speeds
- Predictable behavior

**Mecanum wheels (Future upgrade)**:
- Enable omnidirectional movement — strafe sideways through doorways, rotate in place
- Each wheel has angled rollers that create lateral force when spinning at different speeds
- Requires independent speed control for all 4 motors (current L298N setup drives left pair + right pair, would need upgrade)
- More complex control code (4 independent PWM channels)
- Reduced traction compared to standard rubber (rollers slip on carpet)
- **When to upgrade**: If navigating tight spaces becomes a priority

**Tank treads (Not chosen)**:
- Highest traction — climbs over cables, door thresholds
- Good for outdoor use
- Tracks wear over time and create more noise on hard floors
- Cannot upgrade to mecanum (different mounting)
- **When to choose**: Paired with Devastator chassis if traction is the top priority

---

## Decision 6: Camera

**Requirements**: Security patrol (day + night), AI vision analysis, wide coverage area.

### Options Evaluated

| Camera | Resolution | Night vision | FOV | Interface | Price | Verdict |
|---|---|---|---|---|---|---|
| **Pi Camera Module 3** | 12MP, 1080p video | No | 66° (standard) | CSI ribbon | ~$25 | **Rejected** |
| **Pi Camera Module 3 NoIR** | 12MP, 1080p video | Yes (with IR LEDs) | 66° (standard) | CSI ribbon | ~$25 | **Rejected** |
| **Pi Camera Module 3 Wide NoIR** | 12MP, 1080p video | Yes (with IR LEDs) | 120° (wide) | CSI ribbon | ~$35 | **Chosen** |
| **USB webcam** | Varies | Varies | Varies | USB | Varies | **Rejected** |

### Detailed Rationale

**Pi Camera Module 3 Wide NoIR (Chosen)**:
- 120° FOV covers more area per frame — critical for security patrol, fewer head turns needed
- NoIR (No Infrared filter) means the sensor can see IR light — paired with IR LEDs, enables night vision invisible to humans
- 12MP, autofocus, 1080p video — plenty for AI vision analysis via Gemma 3 12B
- CSI ribbon cable — direct connection to Pi/Jetson, lowest latency, no USB port used
- Native support in both Pi OS and JetPack

**Pi Camera Module 3 standard (Rejected)**:
- Same great sensor but no night vision — IR filter blocks IR light
- 66° standard FOV is too narrow for security (need to pan more frequently)
- **When to choose**: If the rover is only used during daytime

**Pi Camera Module 3 NoIR (Rejected)**:
- Has night vision capability (no IR filter)
- But standard 66° FOV is too narrow for security patrol
- **When to choose**: If budget is tight ($10 savings) and narrow FOV is acceptable

**USB webcam (Rejected)**:
- Higher latency than CSI (USB stack overhead)
- No native night vision
- Consumes a USB port (Pi 5 has 4, but battery monitoring/RPLidar may need them)
- Variable quality and driver support
- **When to choose**: Never for this use case

---

## Decision 7: Camera Mount

**Problem**: A fixed-mount camera only sees where the rover points. A pan-tilt mount lets the camera look around independently.

### Design Choice

**SG90 pan-tilt bracket kit** — 2x SG90 micro servos + plastic bracket

| Feature | Detail |
|---|---|
| Horizontal range | 180° (pan) |
| Vertical range | ~90° (tilt) |
| Servo torque | 1.8 kg-cm (plenty for a camera) |
| Power | 5V from Pico |
| Control | PWM from Pico GPIO pins |
| Price | ~$8-12 |

**Why pan-tilt over fixed mount**:
- Camera can scan a room without the rover turning — useful in sentry mode
- LLM can use `camera_look(pan, tilt)` tool — "look left", "look up"
- Security patrol: scan side-to-side while driving forward
- Face tracking: follow a person's face in frame

**Alternatives not chosen**:
- **Fixed mount**: Simpler but requires rover to turn its body to look around. For a security camera, this wastes time and battery. Rejected.
- **Gimbal (brushless)**: Smoother movement, better stabilization. But $50+ and overkill for an indoor rover. Not chosen.

---

## Decision 8: Sensor Suite

### 8.1 Distance / Obstacle Avoidance

| Sensor | Range | Coverage | Interface | Price | Verdict |
|---|---|---|---|---|---|
| **HC-SR04 ultrasonic** | 2-400cm | ~15° cone | GPIO (trigger + echo) | Already owned | **Keep** — primary front obstacle detection |
| **RPLidar A1** | 0.15-12m | 360° sweep | USB serial | ~$100 | **Recommended upgrade** (add later) |
| **VL53L0X ToF laser** | 0-200cm | Point measurement | I2C | ~$5 | **Not chosen** |

**HC-SR04 (Keeping)**:
- Already owned
- Good for primary collision avoidance — detects obstacles in front at up to 4 meters
- Simple GPIO interface — Pico reads it in microseconds
- Limitation: 15° cone only covers directly ahead. Blind to sides and rear.

**RPLidar A1 (Recommended future upgrade)**:
- Spinning laser scanner — 360° distance measurements, 8000 samples/second
- Enables SLAM (Simultaneous Localization and Mapping) — the rover builds a floor plan of your house
- Enables autonomous navigation — "go to the living room" with path planning around furniture
- Connects to Pi/Jetson via USB (shows as serial device)
- This is what Roombas and warehouse robots use
- $100 is significant but transformative for autonomous capability
- **Can be added later** — the rover works fine with ultrasonic-only for remote control and simple patrol routes

**VL53L0X ToF laser (Not chosen)**:
- Point measurement only — even narrower than ultrasonic
- Similar effective range (2m practical vs 4m for ultrasonic)
- Would need multiple sensors for coverage, adding wiring complexity
- **When to choose**: If precise close-range measurement is needed (e.g., docking into a charging station)

### 8.2 Orientation / Motion (IMU)

| Sensor | Axes | Features | Interface | Price | Verdict |
|---|---|---|---|---|---|
| **MPU6050** | 6 (3 accel + 3 gyro) | Basic orientation | I2C (0x68) | Already owned | **Keep** |
| **MPU9250** | 9 (3 accel + 3 gyro + 3 magnetometer) | Orientation + compass heading | I2C | ~$8 | **Not chosen** |
| **BNO055** | 9 + onboard sensor fusion | Heading without software math | I2C | ~$25 | **Not chosen** |

**MPU6050 (Keeping)**:
- Already owned
- 6-axis: accelerometer (tilt/impact detection) + gyroscope (rotation rate)
- Sufficient for: detecting collisions/bumps, knowing if rover is tilted/stuck, basic orientation tracking
- Connected to Pico's I2C1 bus — Pico reads at 100Hz+ for fast safety reactions

**MPU9250 (Not chosen)**:
- Adds magnetometer for absolute compass heading (north/south/east/west)
- Better for outdoor navigation where GPS heading matters
- Indoor navigation doesn't benefit much from magnetometer — compass is unreliable indoors due to metal/wiring interference
- **When to upgrade**: If the rover goes outdoor

**BNO055 (Not chosen)**:
- Best IMU available — onboard Cortex M0 does sensor fusion, outputs quaternions directly
- No need for complementary/Kalman filter in software
- But $25+ and MPU6050 is already owned and sufficient for indoor use
- **When to upgrade**: If software IMU fusion becomes a bottleneck or if precise heading is needed

### 8.3 Security / Motion Detection

| Sensor | Detection method | Range | Coverage | Price | Verdict |
|---|---|---|---|---|---|
| **HC-SR501 PIR** | Passive infrared (body heat) | ~7m | ~120° cone | ~$2 | **Chosen** |
| **RCWL-0516 microwave radar** | Doppler microwave | ~7m | 360° (through walls) | ~$3 | **Not chosen** |

**HC-SR501 PIR (Chosen)**:
- Detects human body heat — works even in complete darkness without any illumination
- Low power, simple GPIO output (high = motion detected)
- Perfect for sentry mode: camera can be off, PIR wakes the system when someone enters the room
- $2 — trivial cost for high-value security feature
- Mounted on rover body, facing forward

**RCWL-0516 microwave radar (Not chosen)**:
- Detects motion through walls and obstacles — sounds cool but causes false positives indoors
- Picks up ceiling fan motion, HVAC airflow, pets in other rooms
- 360° detection makes it hard to know which direction the motion came from
- **When to choose**: Outdoor perimeter security where through-wall detection is useful

### 8.4 Safety Sensors

| Sensor | Purpose | Interface | Price | Verdict |
|---|---|---|---|---|
| **IR cliff sensors (x2)** | Detect floor edge / stairs | GPIO (Pico) | ~$3 each | **Chosen** |
| **Mechanical bumper switches** | Detect physical contact | GPIO (Pico) | ~$2 each | **Not chosen** |

**IR cliff sensors (Chosen)**:
- Critical safety — prevents the rover from driving off stairs, ledges, or table edges
- IR LED + photodiode pair: LED shines down, photodiode detects reflection. No reflection = no floor = stop immediately
- Mount two on the front underside of the chassis, at left and right edges
- Pico handles this locally — emergency stop without waiting for Pi
- **Non-negotiable for any home with stairs**

**Mechanical bumper switches (Not chosen)**:
- Detect physical contact with obstacles
- Redundant if ultrasonic sensor is working — should detect obstacles before contact
- Add mechanical complexity (spring-loaded bumper bar)
- **When to add**: If ultrasonic proves insufficient (blind spots to the sides)

### 8.5 Power Monitoring

| Sensor | Measures | Interface | Price | Verdict |
|---|---|---|---|---|
| **INA219** | Voltage + current | I2C (0x40) | ~$4 | **Chosen** |
| **Voltage divider** | Voltage only | ADC | ~$0.50 | **Not chosen** |

**INA219 (Chosen)**:
- Measures both voltage AND current draw — enables accurate battery percentage and power consumption tracking
- I2C interface — connects to Pico's I2C1 bus alongside MPU6050
- Dashboard can show "Battery: 67%, 2.1A draw, ~1.5 hours remaining"
- Alerts when battery drops below threshold — rover can return to charging station
- $4 for complete power visibility

**Voltage divider (Not chosen)**:
- Only measures voltage — can estimate percentage but not current draw or remaining time
- Requires ADC pin on Pico (limited analog inputs)
- Less accurate than INA219
- **When to choose**: If I2C bus is full (it's not)

### 8.6 Night Vision Illumination

| Component | Wavelength | Visibility | Camera sensitivity | Price | Verdict |
|---|---|---|---|---|---|
| **850nm IR LEDs** | 850nm | Faint red glow (barely visible) | High | ~$5 for 4-6 LEDs | **Chosen** |
| **940nm IR LEDs** | 940nm | Completely invisible | Lower | ~$5 | **Not chosen** |
| **White LED spotlight** | Visible | Bright white | N/A | ~$3 | **Not chosen** |

**850nm IR LEDs (Chosen)**:
- NoIR camera is most sensitive at 850nm — best illumination for night vision
- Barely visible to humans (faint red glow, only noticeable if you stare at the LED directly)
- Simple GPIO control — Pico turns on/off via register 0x06
- 4-6 LEDs around the camera provide even illumination

**940nm IR LEDs (Not chosen)**:
- Completely invisible to humans — slightly stealthier
- But NoIR camera sensor is less sensitive at 940nm — dimmer image, more LEDs needed
- The 850nm glow is so faint it's not a practical concern indoors
- **When to choose**: If operating in a context where even a faint LED glow is unacceptable

**White LED spotlight (Not chosen)**:
- Alerts intruders that a camera is watching — defeats stealth security purpose
- Disturbs sleeping occupants during night patrol
- Doesn't work with NoIR camera's IR sensitivity
- **When to choose**: Never for security. Could add as a separate "flashlight" feature for utility.

### 8.7 Audio

#### Microphone

| Component | Interface | Noise | Price | Verdict |
|---|---|---|---|---|
| **INMP441 I2S mic** | I2S (digital) | Very low | ~$4 | **Chosen** |
| **USB microphone** | USB | Analog noise | ~$10 | **Not chosen** |

**INMP441 I2S (Chosen)**:
- Digital I2S output — no analog-to-digital conversion noise
- Connects directly to Pi/Jetson I2S pins
- Enables: "Hey Bunty" wake word, voice commands while roving, glass-breaking detection for security
- Tiny form factor, easy to mount on rover

**USB microphone (Not chosen)**:
- Analog signal introduces noise (especially on a rover with motors)
- Consumes a USB port
- Larger form factor
- **When to choose**: If I2S pins are unavailable

#### Speaker

| Component | Interface | Power | Price | Verdict |
|---|---|---|---|---|
| **MAX98357A I2S DAC + 3W speaker** | I2S (digital) | 3W | ~$8 total | **Chosen** |
| **3.5mm speaker via Pi audio jack** | Analog | Varies | ~$5 | **Not chosen** |

**MAX98357A + 3W speaker (Chosen)**:
- I2S digital audio — clean output, no analog noise from motor interference
- 3W is plenty loud for TTS responses and security siren
- Same I2S bus as the microphone (different pins)
- Works with Pi OS Lite (no PulseAudio/PipeWire needed)

**3.5mm audio jack (Not chosen)**:
- Pi OS Lite doesn't configure audio server by default — extra setup
- Analog output picks up electrical noise from motors
- Pi 5 doesn't have a 3.5mm jack (removed in Pi 5)
- **When to choose**: Never for Pi 5 (no jack). On older Pi models, only if I2S is unavailable.

---

## Decision 9: Power System

**Requirements**:
1. Charge without shutting down (UPS behavior)
2. Single charge port for entire rover
3. Separate clean power for brain vs noisy power for motors
4. Enough capacity for 2+ hours of operation

### Options Evaluated (Brain Power)

| Option | Output | Capacity | Charge-while-run | Jetson compatible | Price | Verdict |
|---|---|---|---|---|---|---|
| **V8 18650 shield** (user owns) | 5V/3A + 3V/1A | 2x 18650 (~6000mAh) | Yes (micro USB) | No (3A too low) | Already owned | **Prototype only** |
| **Waveshare UPS HAT (C)** | 5V via GPIO | 2x 18650 (~6000mAh) | Yes (USB-C) | No (5V output only) | ~$20 | **Not chosen** |
| **PiSugar 3** | 5V, 5000mAh built-in | 5000mAh | Yes (USB-C) | No (5V output only) | ~$40 | **Not chosen** |
| **Single 3S LiPo + BMS + buck converter** | 11.1V → 5V/5A regulated | 5000mAh @ 11.1V (~55Wh) | Yes (USB-C via BMS) | Yes (11.1V direct) | ~$57 total | **Chosen** |

### Detailed Rationale

**Single 3S LiPo + BMS + Buck (Chosen)**:
- One battery, one charge port, two isolated output rails
- 3S LiPo (11.1V) feeds motors directly via H-bridge AND steps down to 5V for Pi via buck converter
- BMS handles cell balancing, over-discharge protection, USB-C passthrough charging
- Pololu D24V50F5 buck converter provides clean 5V/5A with low ripple — no Pi brownouts
- 11.1V is directly usable by Jetson Orin Nano (accepts 5-19V) — future-proof
- 5000mAh at 11.1V = ~55Wh — enough for 2-3 hours of mixed use
- Noise isolation: buck converter's LC filter separates motor noise from Pi power rail

**V8 18650 shield (Prototype only)**:
- User already owns it — good for initial testing
- 5V/3A output is tight for Pi 5 under load (draws up to 3A with peripherals)
- 3V/1A output could power Pico directly
- Micro USB charging (not USB-C)
- **Will not work for Jetson** — insufficient voltage and current
- **Use for**: Early software development and I2C testing before final battery arrives

**Waveshare UPS HAT (Not chosen)**:
- Good product but designed for stationary Pi UPS use
- 5V output only — can't power motors or Jetson directly
- Would need a second battery for motors, defeating the "charge once" requirement
- 18650 capacity limited vs a dedicated LiPo pack

**PiSugar 3 (Not chosen)**:
- Compact pogo-pin attachment — neat for stationary Pi
- 5000mAh is good capacity
- But 5V output only — same problem as Waveshare, can't power motors
- $40 is expensive for what it provides
- **When to choose**: If building a portable Pi project without motors

### Why Single Battery with Two Rails (Not Two Batteries)

User requirement: "charge once and both rails should be charged." Two separate batteries would mean two chargers, two BMS boards, and the user needs to remember to charge both. A single battery with two regulated outputs is simpler:

```
                    ┌──────────────┐
  USB-C PD in ──→   │  3S BMS Board │
  (single port)     │  (balances,   │
                    │   protects,   │
                    │   charges)    │
                    └──────┬───────┘
                           │
                     3S LiPo Pack
                     11.1V 5000mAh
                           │
              ┌────────────┴────────────┐
              │                         │
     ┌────────┴────────┐      ┌────────┴────────┐
     │ Pololu D24V50F5 │      │  Direct 11.1V   │
     │ 5V/5A buck      │      │  to L298N       │
     │ (LC filtered)   │      │  H-Bridge       │
     └────────┬────────┘      └────────┬────────┘
              │                         │
      RAIL 1: Brain             RAIL 2: Motors
      Clean 5V                  Noisy 11.1V
      Pi + Pico                 4x DC motors
```

Noise isolation is achieved by the buck converter's LC filter, not by separate batteries. Motor current spikes and back-EMF stay on the 11.1V rail and don't propagate through the regulated 5V output.

### Specific Parts

| Part | Spec | Rationale | ~Price |
|---|---|---|---|
| **3S LiPo 11.1V 5000mAh 20C+** | ~55Wh, XT60 connector | 20C = 100A burst capacity — handles motor stall currents (4x 2.5A = 10A worst case) with massive headroom. 5000mAh provides 2-3 hours runtime | ~$25-35 |
| **3S BMS with USB-C PD** | 12.6V charge, 10-20A continuous | Cell balancing prevents individual cell damage. Over-discharge protection prevents deep discharge. USB-C passthrough enables charge-while-running | ~$8-15 |
| **Pololu D24V50F5** | 5V/5A output, 6-38V input, low ripple | Clean regulated 5V for Pi. Handles input voltage range from full charge (12.6V) to near-empty (9.9V). Low ripple prevents random Pi reboots. 5A handles Pi 5 peak draws | ~$15 |

### Motor Driver Decision

| Driver | Channels | Max voltage | Max current/ch | Efficiency | Price | Verdict |
|---|---|---|---|---|---|---|
| **L298N** | 2 | 46V | 2A (3A peak) | ~70% (linear, voltage drop) | ~$3-5 | **Chosen** |
| **TB6612FNG** | 2 per board | 13.5V | 1.2A (3.2A peak) | ~95% (MOSFET) | ~$4-6 | **Rejected for 3S** |
| **BTS7960** | 1 per board | 27V | 43A | ~95% | ~$8 | **Not chosen** |

**L298N (Chosen)**:
- Handles 11.1-12.6V from 3S LiPo safely (max 46V — huge margin)
- 2 channels: left pair (2 motors in parallel) + right pair (2 motors in parallel) = tank steering from one board
- 2A continuous per channel, 3A peak — sufficient for Wild Thumper motors
- ~70% efficiency means some voltage drop (1.5-2V) — motors see ~9-10V instead of 11.1V, still plenty
- Cheap, widely available, well-documented, proven in thousands of rover projects
- Built-in 5V regulator (though we'll use the Pololu instead for cleaner power)

**TB6612FNG (Rejected for 3S LiPo)**:
- Far more efficient (~95%, MOSFET-based) — less heat, more battery life
- But maximum voltage is 13.5V — a fully charged 3S LiPo is 12.6V, leaving only 0.9V margin
- A voltage spike from motor back-EMF could exceed 13.5V and damage the chip
- **When to choose**: With 2S LiPo (7.4V, 8.4V max) — comfortably within limits. If future build uses 2S, prefer TB6612FNG over L298N.

**BTS7960 (Not chosen)**:
- Massive overkill — 43A continuous, designed for heavy-duty motors (e-bikes, power wheels)
- One channel per board — need 2 boards for left/right ($16 total)
- More board space consumed
- **When to choose**: Large outdoor rover with high-stall-current motors

---

## Decision 10: Brain — Pi 5 Now, Jetson Later

| Factor | Pi 5 (8GB) | Jetson Orin Nano (8GB) |
|---|---|---|
| Available now | Yes (already owned) | No (future purchase) |
| I2C for Pico | GPIO 2, 3 (same pinout) | GPIO 2, 3 (same pinout) |
| Local LLM | Needs Mac Mini (LM Studio) | Runs locally — 1024 CUDA cores, ~30-40 tok/s (7B) |
| Vision inference | Needs Mac Mini (Gemma 3 12B) | Runs locally — real-time object detection |
| Camera | Pi Camera Module (CSI) | Same CSI connector, same camera works |
| TTS/STT | Needs Mac Mini (Kokoro) | Can run locally |
| Power | 5V/3A via USB-C (from buck converter) | 5-19V barrel jack (can use 11.1V more directly) |
| RoverService code | Identical Python (smbus2 for I2C) | Identical Python (smbus2 for I2C) |
| WiFi for dashboard | Built-in | Built-in |
| Mac Mini needed? | Yes, for LLM + vision + TTS | Optional — Jetson handles most locally |

**Decision**: Start with Pi 5. The software (RoverService, I2C protocol, tools, dashboard widget) is identical on both platforms. Migration to Jetson is a hardware swap + config change, not a rewrite. The service abstraction in PiAssistant already accommodates this — `LLMService` doesn't care if it talks to Mac Mini or a local GPU.

**When to migrate to Jetson**:
- When autonomous security patrol needs real-time object detection (Jetson GPU vs Mac Mini network hop)
- When you want the rover to operate independently without Mac Mini on the network
- When Jetson Orin Nano is purchased and available

---

## Complete Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      ROVER CHASSIS (Yahboom Suspension 4WD)            │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Pi 5 / Jetson Orin Nano (BRAIN)                        │     │
│  │    ├── WiFi → home network / Cloudflare tunnel          │     │
│  │    ├── Pi Camera Module 3 Wide NoIR (CSI ribbon)        │     │
│  │    ├── RPLidar A1 (USB serial) [future upgrade]         │     │
│  │    ├── INMP441 I2S microphone                           │     │
│  │    ├── MAX98357A I2S DAC + 3W speaker                   │     │
│  │    ├── I2C0 ──→ Pico (address 0x42)                     │     │
│  │    └── PiAssistant server (FastAPI)                     │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Pico (BODY CONTROLLER, I2C peripheral)                 │     │
│  │    ├── I2C0: peripheral to Pi (address 0x42)            │     │
│  │    ├── I2C1: controller for MPU6050 (0x68) + INA219     │     │
│  │    │         (0x40)                                     │     │
│  │    ├── PWM: L298N H-Bridge → 4x DC motors              │     │
│  │    ├── PWM: SG90 pan servo + SG90 tilt servo            │     │
│  │    ├── GPIO: HC-SR04 ultrasonic (trigger + echo)        │     │
│  │    ├── GPIO: HC-SR501 PIR sensor                        │     │
│  │    ├── GPIO: IR cliff sensors (x2, front left + right)  │     │
│  │    └── GPIO: IR LED array (on/off)                      │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Power System                                           │     │
│  │    3S LiPo 11.1V 5000mAh                                │     │
│  │    ├── 3S BMS (USB-C charge, passthrough, protection)   │     │
│  │    ├── Pololu D24V50F5 → 5V/5A → Pi + Pico (RAIL 1)    │     │
│  │    └── Direct 11.1V → L298N H-Bridge → motors (RAIL 2)  │     │
│  │                                                         │     │
│  │    Common GND tied between all boards                   │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Wiring Detail

```
3S LiPo (+) ──→ BMS ──→ 3S LiPo (-)
                 │
                 ├── USB-C charge port (input)
                 │
                 ├──→ Pololu D24V50F5 (VIN)
                 │         └── 5V OUT ──→ Pi 5 USB-C power
                 │                    ──→ Pico VSYS (5V)
                 │
                 └──→ L298N VCC (motor power, 11.1V)
                           ├── OUT1/OUT2 → Left motors (2 in parallel)
                           └── OUT3/OUT4 → Right motors (2 in parallel)

Pi GPIO 2 (SDA) ────→ Pico GPIO 0 (I2C0 SDA)
Pi GPIO 3 (SCL) ────→ Pico GPIO 1 (I2C0 SCL)
Pi GND ─────────────→ Pico GND

Pico GPIO 14 (SDA) ──→ MPU6050 SDA + INA219 SDA (I2C1 bus)
Pico GPIO 15 (SCL) ──→ MPU6050 SCL + INA219 SCL (I2C1 bus)

Pico GPIO 2 ──→ L298N IN1 (left motors)
Pico GPIO 3 ──→ L298N IN2 (left motors)
Pico GPIO 4 ──→ L298N IN3 (right motors)
Pico GPIO 5 ──→ L298N IN4 (right motors)
Pico GPIO 6 ──→ L298N ENA (left PWM speed)
Pico GPIO 7 ──→ L298N ENB (right PWM speed)

Pico GPIO 8  ──→ HC-SR04 Trigger
Pico GPIO 9  ──→ HC-SR04 Echo
Pico GPIO 10 ──→ Pan servo PWM
Pico GPIO 11 ──→ Tilt servo PWM
Pico GPIO 12 ──→ PIR sensor (digital input)
Pico GPIO 13 ──→ IR LEDs (digital output via transistor)
Pico GPIO 16 ──→ Left cliff sensor (digital input)
Pico GPIO 17 ──→ Right cliff sensor (digital input)
```

---

## Pico Safety Features

The Pico handles all safety locally — no network latency between sensor reading and emergency response.

| Safety feature | Trigger | Action | Latency |
|---|---|---|---|
| **Watchdog** | No I2C command from Pi in 500ms | Stop all motors | <1ms |
| **Cliff detection** | IR cliff sensor reads no floor | Emergency stop + set cliff flag | <1ms |
| **Obstacle avoidance** | Ultrasonic < 10cm | Emergency stop + set obstacle flag | ~5ms |
| **Battery low** | INA219 voltage < 10.2V (3.4V/cell) | Set battery_low flag, alert Pi | <1ms |
| **Tilt detection** | MPU6050 tilt > 45° | Stop motors (rover is stuck/tipping) | <1ms |

The Pi reads these status flags via register 0x34 and can display alerts on the dashboard, but the Pico acts immediately without waiting for Pi commands.

---

## Shopping List

### Must Have (Initial Build)

| # | Part | Qty | ~Price | Where to Buy |
|---|---|---|---|---|
| 1 | Yahboom Suspension 4WD chassis (with 520 encoder motors) | 1 | $70 | [Amazon - Suspension 4WD (M)](https://www.amazon.com/Yahboom-Chassis-Suspension-Eduactional-Science/dp/B0BR9QBZSP) · [Amazon - Suspension 4WD (newer)](https://www.amazon.com/Yahboom-Suspension-Compatible-Raspberry-Absorption/dp/B0CWTZ4Q3Q) · [Yahboom direct](https://category.yahboom.net/products/ros-chassis) |
| 2 | Pico (plain, not W) | 1 | $4 | [Amazon](https://www.amazon.com/Raspberry-Pi-Pico/dp/B09KVB8LVR) · [PiShop.us](https://www.pishop.us/product/raspberry-pi-pico/) · [Official](https://www.raspberrypi.com/products/raspberry-pi-pico/) |
| 3 | Pi Camera Module 3 Wide NoIR | 1 | $35 | [Amazon](https://www.amazon.com/Raspberry-Pi-Camera-Module-NoIR/dp/B0BRY6VLR6) · [PiShop.us](https://www.pishop.us/product/raspberry-pi-camera-module-3-wide-noir/) · [Official](https://www.raspberrypi.com/products/camera-module-3/) |
| 4 | SG90 micro servo motors (x2 for pan-tilt) | 1 pack | $7 | [Amazon - 3-pack](https://www.amazon.com/WWZMDiB-SG90-Control-Servos-Arduino/dp/B0BKPL2Y21) · [Amazon - 2-pack](https://www.amazon.com/Sipytoph-Helicopter-Airplane-Walking-Control/dp/B09185SC1W) |
| 5 | Pan-tilt bracket (servos not included) | 1 | $5 | [Amazon - single](https://www.amazon.com/Platform-Anti-Vibration-Aircraft-Dedicated-VE223P0-3/dp/B09TFXGC21) · [Amazon - 2-pack](https://www.amazon.com/ThtRht-Anti-Vibration-Photography-ESP32-CAM-Raspberry/dp/B0CL9CDKQV) |
| 6 | 3S LiPo 11.1V 5000mAh 50C (XT60) | 1 | $30 | [Amazon - Gens Ace 5000mAh](https://www.amazon.com/Gens-ace-5000mAh-Battery-Brushless/dp/B01JCSOJIY) · [Amazon - HRB 5000mAh](https://www.amazon.com/HRB-50C-100C-Quadcopter-Helicopter-Airplane/dp/B06XNTHQRZ) · [Amazon - Venom 20C 2-pack](https://www.amazon.com/Venom-5000mAh-Battery-Universal-Traxxas/dp/B00FE0ORV4) |
| 7 | 3S BMS with USB-C charging | 1 | $10 | [Amazon - 3S 4A USB-C BMS 3-pack](https://www.amazon.com/Lithium-Battery-Charger-Step-up-Polymer/dp/B0BZC7TWC7) · [Amazon - Adeept 3S USB-C 2-pack](https://www.amazon.com/Adeept-Lithium-Battery-Charging-Step-Up/dp/B0BWTQ3JPK) |
| 8 | Pololu D24V50F5 (5V/5A step-down) | 1 | $15 | [Amazon](https://www.amazon.com/Pololu-Step-Down-Voltage-Regulator-D24V50F5/dp/B01M659ER2) · [Pololu direct](https://www.pololu.com/product/2851) · [Walmart](https://www.walmart.com/ip/Pololu-2851-5V-5A-Step-Down-Voltage-Regulator-D24V50F5/326787941) |
| 9 | L298N motor driver | 1 | $5 | [Amazon - single](https://www.amazon.com/MOPFOL-L298N-Bridge-Driver-Module/dp/B0GHQ6ZKP9) · [Amazon - 4-pack HiLetgo](https://www.amazon.com/HiLetgo-Controller-Stepper-H-Bridge-Mega2560/dp/B07BK1QL5T) |
| 10 | HC-SR501 PIR sensor | 1 | $6 | [Amazon - 3-pack](https://www.amazon.com/HC-SR501-PIR-Motion-Sensor-Detector/dp/B0897BMKR3) · [Amazon - 5-pack w/ brackets](https://www.amazon.com/VKLSVAN-HC-SR501-Infrared-Bracket-Screwdriver/dp/B0DPW57YS7) |
| 11 | 850nm IR illuminator | 1 | $12 | [Amazon - Univivi 6-LED 90°](https://www.amazon.com/Univivi-Infrared-Illuminator-Waterproof-Security/dp/B01G6K407Q) · [Amazon - 120° wide angle](https://www.amazon.com/Infrared-Illuminator-Degree-Waterproof-Security/dp/B07CP66631) |
| 12 | IR cliff sensors (obstacle avoidance) | 2 | $6 | [Amazon - 2-pack](https://www.amazon.com/Infrared-Avoidance-Transmitting-Receiving-Photoelectric/dp/B07PFCC76N) · [Amazon - 10-pack OSOYOO](https://www.amazon.com/OSOYOO-Infrared-Obstacle-Avoidance-Arduino/dp/B01I57HIJ0) |
| 13 | INA219 current/voltage sensor | 1 | $8 | [Amazon - Adafruit INA219](https://www.amazon.com/Adafruit-Industries-INA219-Current-Breakout/dp/B09CBSLXN7) · [Amazon - HiLetgo INA219](https://www.amazon.com/HiLetgo-INA219-Bi-directional-Current-Breakout/dp/B01ICN5OAM) · [Amazon - HiLetgo 2-pack](https://www.amazon.com/HiLetgo-INA219-Bi-Directional-Current-Breakout/dp/B07VL8NY32) |
| 14 | Jumper wires, standoffs, zip ties | misc | $10 | Search Amazon for "jumper wire kit" + "M3 standoff kit" |
| | | | **~$213** | |

### Should Have (Audio)

| # | Part | Qty | ~Price | Where to Buy |
|---|---|---|---|---|
| 15 | INMP441 I2S microphone | 1 | $4 | [Amazon - DAOKI single w/ cables](https://www.amazon.com/DAOKI-Omnidirectional-Microphone-Interface-Precision/dp/B0821521CV) · [Amazon - 5-pack EC Buying](https://www.amazon.com/EC-Buying-INMP441-Omnidirectional-Microphone/dp/B0C1C64R8S) |
| 16 | MAX98357A I2S DAC amplifier | 1 | $8 | [Amazon - Adafruit MAX98357A](https://www.amazon.com/Adafruit-I2S-Class-Amplifier-Breakout/dp/B01K5GCFA6) · [Amazon - 2-pack generic](https://www.amazon.com/MAX98357-MAX98357A-Amplifier-Interface-Raspberry/dp/B0DPJRLMDJ) · [Adafruit direct](https://www.adafruit.com/product/3006) |
| 17 | 3W 4-ohm speaker | 1 | $3 | Search Amazon for "3W 4 ohm speaker small" (pairs with MAX98357A) |
| | | | **+$15** | |

### Game Changer (LIDAR)

| # | Part | Qty | ~Price | Where to Buy |
|---|---|---|---|---|
| 18 | RPLidar A1M8 360° laser scanner | 1 | $100 | [Amazon - Stemedu RPLidar A1M8-R6](https://www.amazon.com/RPLiDAR-Degree-Laser-Scanner-Range/dp/B07L89TT6F) · [Amazon - Waveshare RPLidar A1](https://www.amazon.com/RPLIDAR-A1-Omnidirectional-High-Speed-Acquisition/dp/B0B6B5MWSJ) · [Adafruit](https://www.adafruit.com/product/4010) · [RobotShop](https://www.robotshop.com/products/rplidar-a1m8-360-degree-laser-scanner-development-kit) |
| | | | **+$100** | |

### Already Owned

| Part | Status |
|---|---|
| Pi 5 (8GB) | Have — brain |
| HC-SR04 ultrasonic | Have — front obstacle detection |
| MPU6050 accel/gyro | Have — orientation/tilt |
| V8 18650 battery shield | Have — prototype power only |
| 4x DC motors | Have — part of existing rover kit |

### Total Cost

| Tier | Parts | Cost |
|---|---|---|
| Must Have | #1-14 | ~$213 |
| Must Have + Audio | #1-17 | ~$228 |
| Full Build | #1-18 | ~$328 |

### Shopping Notes

- **Wild Thumper is discontinued** (Pololu/Dagu, confirmed 2026-03-30). The Yahboom Suspension 4WD is the replacement — comparable aluminum + suspension design, and includes encoder motors (an upgrade over Wild Thumper).
- **3S LiPo**: Gens Ace 50C recommended over 20C — same price, higher discharge rate handles motor stalls better. XT60 connector matches most RC chargers.
- **SG90 servos** are separate from the pan-tilt bracket — order both (#4 and #5).
- **IR illuminator**: The Univivi is a pre-built 12V module (6 LEDs, powered separately). If you prefer bare 5mm LEDs to wire at 3.3V from Pico GPIO, search "850nm IR LED 5mm" instead.
- **Speaker**: The MAX98357A is just the amplifier board — you need a separate small speaker (#17) to pair with it.
- **Multi-packs**: Many sensors come in multi-packs (3-pack PIR, 5-pack INMP441, etc.) which are better value if you want spares.

---

## Software Integration Preview

This section outlines how the rover hardware connects to PiAssistant's existing software architecture. Detailed implementation will be planned separately.

### New Service: RoverService

Follows the `BaseService` pattern. Uses `smbus2` library to communicate with Pico over I2C:

```python
# Reads/writes I2C registers on Pico (address 0x42)
class RoverService(BaseService):
    name = "rover"
    async def move(self, left_speed, right_speed) -> None
    async def stop(self) -> None
    async def get_distance(self) -> int  # cm
    async def get_orientation(self) -> dict  # accel + gyro
    async def get_battery(self) -> dict  # voltage, current, percentage
    async def look(self, pan, tilt) -> None  # camera pan-tilt
    async def get_status(self) -> dict  # all sensor readings + flags
```

### New LLM Tools

| Tool | Parameters | Description |
|---|---|---|
| `rover_move` | direction, speed, duration_ms | Move rover (forward, backward, left, right, spin) |
| `rover_stop` | — | Emergency stop |
| `rover_distance` | — | Read ultrasonic distance |
| `rover_orientation` | — | Read IMU data |
| `rover_battery` | — | Read battery status |
| `rover_look` | pan, tilt | Point camera |
| `rover_status` | — | Full sensor dump |
| `patrol_start` | route_name | Start autonomous patrol |
| `patrol_stop` | — | Stop patrol |
| `security_arm` | — | Enter sentry mode |
| `security_disarm` | — | Exit sentry mode |

### Dashboard Widget

Rover control widget with:
- Directional pad (forward/back/left/right/stop)
- Camera view (MJPEG stream or periodic snapshots)
- Pan-tilt sliders
- Battery indicator
- Sensor readouts (distance, orientation, motion)
- Security mode toggle
- Patrol route selector

---

## Decision Log

| Date | Decision | Options Considered | Chosen | Key Rationale |
|---|---|---|---|---|
| 2026-03-30 | Body controller | Pi GPIO, Pico W WiFi, Pico I2C, Arduino UART | Pico I2C | Real-time control, microsecond latency, crash isolation |
| 2026-03-30 | Communication | I2C, SPI, UART, USB, WiFi | I2C | 2-wire simplicity, native Pi/Jetson support, multi-device addressing |
| 2026-03-30 | Chassis | ~~Wild Thumper~~ (discontinued), Devastator (6V motors — incompatible), Yahboom Suspension 4WD, Yahboom no-suspension, Acrylic | Yahboom Suspension 4WD | Suspension, aluminum 3-layer, 12V 520 encoder motors, 2kg payload |
| 2026-03-30 | Motors | Yahboom 520 DC (included), JGA25-371, TT hobby | Yahboom 520 DC with encoders | Pre-mounted, 12V, metal gearbox, built-in encoders |
| 2026-03-30 | Wheels | Rubber, Mecanum, Tracks | Rubber (standard) | Included, simple, good grip |
| 2026-03-30 | Camera | Pi Cam 3, NoIR, Wide NoIR, USB | Pi Cam 3 Wide NoIR | 120° FOV + night vision for security |
| 2026-03-30 | Camera mount | Pan-tilt, Fixed, Gimbal | SG90 pan-tilt | Independent look direction, LLM controllable |
| 2026-03-30 | Distance sensor | HC-SR04, RPLidar A1, VL53L0X | HC-SR04 (keep) + RPLidar A1 (later) | Already owned; RPLidar is game-changing upgrade |
| 2026-03-30 | IMU | MPU6050, MPU9250, BNO055 | MPU6050 (keep) | Already owned, sufficient for indoor use |
| 2026-03-30 | Motion sensor | HC-SR501 PIR, RCWL-0516 radar | HC-SR501 PIR | $2, detects body heat, low false positives |
| 2026-03-30 | Safety sensors | IR cliff, bumper switches | IR cliff sensors (x2) | Critical stair safety, ultrasonic covers collision |
| 2026-03-30 | Battery monitor | INA219, voltage divider | INA219 | Voltage + current, I2C, accurate percentage |
| 2026-03-30 | Night vision | 850nm IR, 940nm IR, white LED | 850nm IR LEDs | Best camera sensitivity, barely visible |
| 2026-03-30 | Microphone | INMP441 I2S, USB mic | INMP441 I2S | Digital (low noise), no USB port used |
| 2026-03-30 | Speaker | MAX98357A I2S, 3.5mm jack | MAX98357A I2S + 3W | Digital (no motor noise), Pi 5 has no 3.5mm |
| 2026-03-30 | Power (brain) | V8 shield, Waveshare UPS, PiSugar 3, 3S LiPo+BMS+buck | 3S LiPo + BMS + Pololu buck | Single charge, both rails, Jetson-compatible |
| 2026-03-30 | Motor driver | L298N, TB6612FNG, BTS7960 | L298N | Handles 12.6V safely (46V max), proven |
| 2026-03-30 | Brain | Pi 5 now, Jetson later | Pi 5 (start) → Jetson (upgrade) | Pi 5 owned, software identical, Jetson = hardware swap |
