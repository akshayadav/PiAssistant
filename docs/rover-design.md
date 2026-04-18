# Rover Integration — Hardware Design Document

## Vision & Use Cases

PiAssistant is evolving from a stationary smart assistant into a **mobile AI rover** — a smart assistant on tracks that doubles as an autonomous security camera. The rover mounts a **Jetson Orin Nano Super Dev Kit** on a tracked suspended chassis (LewanSoul/Hiwonder), with a **Pico 2W microcontroller** (WiFi disabled, used purely as an I2C peripheral) handling real-time motor/sensor control.

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

## ⚠️ Critical Assembly Notes

**READ THESE BEFORE CONNECTING ANY POWER WIRE.**

### 1. Calibrate every Mini-360 buck to 5.0V BEFORE connecting anything

The AITIAO / generic Mini-360 buck converters ship at a **random factory-set output voltage** — often 12V or higher. Connecting a Pico 2W, servos, or audio amp directly to an uncalibrated module will fry them instantly.

**Calibration procedure (do this for every module, every time):**

1. Connect the input side to the 11.1V LiPo (or any 6-12V source in range).
2. Put a multimeter on the OUT+ and OUT− pads. **Do not yet connect any load.**
3. Turn the tiny brass screw on the blue potentiometer — it is a **multi-turn** pot, usually needing 15-20+ turns. Clockwise decreases, counter-clockwise increases.
4. Adjust until the multimeter reads **5.00V ± 0.05V**.
5. Verify under load: connect a cheap 100Ω resistor across the output and confirm the voltage is still ~5V.
6. Only now wire the module into the Pico / servo / audio rail.
7. After soldering/wiring changes, re-verify the output with a multimeter before first power-on.

### 2. Common ground across all boards

The LiPo negative terminal must be tied to the Jetson GND, Pico GND, L298N GND, and all Mini-360 buck GND pins. Without a common ground, I2C communication will fail silently or randomly, and motor PWM will behave erratically.

### 3. Camera cable orientation

The 22-pin to 15-pin FFC cable has **contacts on one side only**, and orientation matters. The blue stiffener tab on each end goes away from the connector's gold contacts. Pushing the wrong way in, or installing with the ribbon twisted, will damage the connector or the camera.

### 4. Power sequence for first boot

Bring up the Pico 2W rail first, then the Jetson. The Pico should reach its safe-default state (motors off) before any I2C traffic is possible. If both come up simultaneously, there is a brief window where the Jetson could write to an uninitialized Pico register map.

---

## Decision 1: Body Controller Architecture

**Problem**: Who drives the motors and reads sensors — the Jetson directly, or a dedicated microcontroller?

### Options Evaluated

| Option | Description | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A: Jetson GPIO direct** | Jetson drives motors/sensors via GPIO | Simplest wiring, no extra board | Linux isn't real-time — jitter in PWM timing, unreliable microsecond echo measurement, bad motor code can hang the whole assistant | **Rejected** |
| **B: Pico 2W via WiFi HTTP** | Same pattern as PicoWeather — Pico 2W runs HTTP server, Jetson sends commands over WiFi | Matches existing codebase pattern, wireless | Adds 5-50ms latency per command, WiFi can drop, WiFi radio is energy hungry, requires WiFi infrastructure — all downsides for two devices on the same chassis | **Rejected** |
| **C: Pico 2W via I2C** | Pico 2W as I2C peripheral (WiFi disabled), Jetson as I2C controller, wired connection | Microsecond latency, rock solid, no WiFi needed, crash isolation (Pico crash doesn't take down Jetson), leverages hardware already owned | 2 data wires + GND needed (~1m max, fine on a rover), different code pattern than PicoWeather | **Chosen** |
| **D: Arduino/Teensy via USB UART** | Traditional robotics approach — Arduino handles motors, Jetson sends serial commands | Well-documented in robotics community, real-time capable | Pico 2W is already owned, MicroPython matches existing codebase (vs C++ for Arduino), RP2350 has sufficient capability, USB cable adds bulk | **Not chosen** |

### Why Pico 2W (Not Plain Pico)

Originally the plan called for a plain Pico (RP2040). The user already owns Pico 2W boards, and the RP2350 silicon is strictly better for this job:

| Factor | Plain Pico (RP2040) | **Pico 2W (RP2350) — chosen** |
|---|---|---|
| CPU | Dual Cortex-M0+ | Dual Cortex-M33 + dual RISC-V (pick at boot) |
| RAM | 264 KB | 520 KB |
| FPU | Software emulation | **Hardware FPU** — faster PID / IMU fusion math |
| I2C peripherals | 2 | 2 (same pinout, drop-in replacement) |
| Register map | As originally designed | Unchanged — exact same I2C protocol |
| WiFi | No | Yes, but **disabled** to save ~30 mA and avoid RF contention |
| Current draw | ~30-80 mA | ~50-100 mA (WiFi off) |
| Cost | $4 | $0 — already owned |

The hardware FPU is especially useful for quadrature encoder math, IMU sensor fusion (complementary or Kalman filter), and PID motor control. Keeping WiFi disabled in firmware is a one-line change (`rp2.country(None)` or simply never importing `network`).

### Why I2C Wins Over WiFi

| Factor | I2C (wired) | WiFi HTTP |
|---|---|---|
| Latency | ~microseconds | ~5-50ms per request |
| Reliability | Rock solid, no network issues | WiFi can drop, reconnect delays |
| Power | No WiFi radio needed | Pico 2W draws ~30 mA extra with WiFi on |
| Wiring | 2 data wires (SDA + SCL) + GND, short runs | Zero wires, but needs WiFi network |
| Range | ~1 meter max (on a rover, this is fine) | Unlimited on LAN |
| Throughput | 400kHz typical, plenty for motor commands | Way more than needed |
| Complexity | Pico is I2C peripheral, Jetson is controller | HTTP server on Pico, HTTP client on Jetson |

**Decision**: Pico 2W via I2C, WiFi explicitly disabled. Both boards are physically on the same chassis — WiFi adds latency and failure modes for zero benefit. I2C gives microsecond response times for motor control and obstacle avoidance.

---

## Decision 2: Communication Protocol

### Why I2C Over Other Wired Options

| Protocol | Speed | Wires | Addressing | Verdict |
|---|---|---|---|---|
| **I2C** | 100-400kHz | 2 (SDA + SCL) + GND | Built-in addressing, multi-device | **Chosen** — simplest wiring, Jetson has native support, Pico has 2 hardware I2C peripherals |
| **SPI** | Up to 50MHz | 4+ (MOSI, MISO, CLK, CS per device) | Chip select per device | Not chosen — more wires, overkill speed for motor commands, no multi-device addressing |
| **UART** | Up to 115200 baud typical | 2 (TX + RX) | Point-to-point only | Not chosen — no addressing, need framing protocol |
| **USB** | 12Mbps+ | 1 cable | Enumeration-based | Not chosen — bulky cable, more latency than I2C |

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

The Pico 2W has two hardware I2C peripherals. Using both prevents bus contention:

| Bus | Controller | Peripheral(s) | Purpose |
|---|---|---|---|
| **I2C0 (Pico)** | Jetson (40-pin header, physical pins 3 + 5) | Pico 2W (address 0x42) | Jetson sends motor commands, reads sensor data |
| **I2C1 (Pico)** | Pico 2W (GPIO 14, 15) | MPU6050 (0x68), INA219 (0x40) | Pico reads IMU + battery locally for fast safety decisions |

**Why two buses**: The Pico needs to read the IMU at high frequency (100Hz+) for orientation and the INA219 for battery monitoring. If these shared the bus with Jetson commands, there'd be contention. Separate buses mean the Pico can read sensors in a tight local loop while the Jetson reads/writes at its own pace.

---

## Decision 3: Chassis

**Problem**: Need a platform large enough to carry Jetson + battery + camera + sensors, durable enough for daily use.

### Chassis Search — What Happened

The original pick was the **Yahboom Suspension 4WD (B0BR9QBZSP)** to replace the discontinued Wild Thumper. When it came time to order (2026-04-18), that SKU was out of stock. The closely related Yahboom Suspension Mecanum 4WD (B0BR9PTTB3) was also out of stock. A brand-agnostic search of the market surfaced these classes:

- **Rubber-wheel 4WD with 12V encoders** (what we originally wanted) — only Yahboom SKUs fit this, and they were all out of stock. Generic alternatives either had TT motors (rejected) or no encoders.
- **Mecanum 4WD with 12V encoders** — Hiwonder/XiaoR Geek options in stock, but require a 4-channel motor driver swap and new firmware math. Capable but more integration.
- **Tracked suspended chassis with 12V encoders** — LewanSoul/Hiwonder B0CTK7YHQK in stock, with legitimate spring-based suspension and 12V encoder motors. Keeps 2-channel tank steering (no firmware/driver changes).

### Options Evaluated (Updated)

| Chassis | Drivetrain | Motors | Suspension | Material | ~Price | Verdict |
|---|---|---|---|---|---|---|
| **~~Wild Thumper 4WD~~** | 4WD rubber | 12V 75:1 | Yes | Aluminum | ~$80-120 | Discontinued 2026 |
| **~~Yahboom Suspension 4WD (B0BR9QBZSP)~~** | 4WD rubber | 12V 520 encoder | Yes (pendulum) | Aluminum 3-layer | ~$60-80 | ~~First pick~~ — out of stock 2026-04-18 |
| **~~Yahboom Suspension Mecanum (B0BR9PTTB3)~~** | 4WD mecanum | 12V 520 encoder | Yes | Aluminum | ~$90-110 | Out of stock 2026-04-18 |
| **Yahboom 4WD no-suspension (B0F3CYLFJF)** | 4WD rubber | 12V 520 encoder | No | Aluminum | ~$55 | Fallback only; no suspension |
| **Hiwonder 4WD Mecanum (B0BB72LPDH / B09ZQF3FKR)** | 4WD mecanum | 12V encoder | No (or minimal) | Aluminum | ~$90-130 | Capable but requires 4-channel driver + firmware math |
| **LewanSoul Suspended Tracked (B0CTK7YHQK)** | 2× tank treads | **JGB3865-520R45-12, 12V, Hall encoder, 45:1** | Yes — 8-ch carbon steel tension springs + bearings | Anodized aluminum, double layer | ~$120 | **Chosen** ✅ Ordered 2026-04-18 |
| **Tank Car Chassis no encoder (B0BDYHVS2P)** | 2× tank treads | 6-12V DC, no encoder | Shock absorbing (vague) | Full-metal | Cheaper | Rejected — no encoders |
| **Devastator Tank (DFRobot)** | 2× tank treads | **6V** 45:1 | Tracks only | Aluminum | ~$60-80 | Rejected — 6V motors incompatible with 3S LiPo |
| **TT-motor kits (LewanSoul/generic 4WD and mecanum)** | Various | TT motor, 3-6V, plastic gears | None | Aluminum | ~$25-50 | Rejected — plastic gears, wrong voltage |

### Why LewanSoul Suspended Tracked Chassis Won

- **12V encoder motors confirmed on the manufacturer's own site** (hiwonder.com) — not guessed from Amazon scrape. Model JGB3865-520R45-12, 45:1 reduction, 150 rpm after gearbox, Hall encoder, 7-13V operating range. Our 3S LiPo (9.9-12.6V) sits in this range.
- **Real suspension** — 8-channel carbon steel tension springs with micro bearings. Not a marketing line; this is a physical spring-damper system.
- **Anodized aluminum alloy, double-layer chassis** — rigid, mounting holes for Jetson/Pi/Pico/camera/lidar.
- **Available in stock** when Yahboom SKUs weren't — this is a meaningful practical criterion for a 2026 build.
- **LewanSoul is owned by Hiwonder** — reputable robotics brand with active manufacturer documentation and ROS/Jetson tutorial coverage.
- **2-channel tank steering** maps directly to our existing L298N wiring and Pico 2W firmware — no code or driver changes from the original plan.
- **Bonus: per-channel motor current is lower** than a 4WD with parallel motors, because only 1 motor per L298N channel instead of 2 in parallel.
- **5 kg payload** (per the sibling B0BDYHVS2P listing; LewanSoul/Hiwonder doesn't publish this explicitly but they share the platform) — plenty for Jetson + LiPo + camera + sensors.

### Tracked Drivetrain Tradeoffs (Honest)

Accepted downsides of tank treads vs rubber wheels:

| Downside | Mitigation |
|---|---|
| Noisier on hardwood (clack-clack) | Drive slowly in sentry mode; most patrol time will be on carpet anyway |
| Tracks wear and stretch | Replacement tracks are cheap and generic; budget for one set every ~1-2 years of heavy use |
| Can't upgrade to mecanum later | Accepted — mecanum was already a "future upgrade" in the original plan, not critical |
| Slightly messier turn-in-place (tracks slip laterally during pivot) | Acceptable for indoor use; encoders help compensate |

**Advantages that came with the switch**:
- Better traction on thresholds, cables, carpet edges (tracks span gaps wheels would drop into)
- Genuinely robust spring suspension (vs Yahboom's pendulum, which was already good)
- Tank aesthetic matches the "security rover" use case
- Only 2 motors to wire (simpler and cheaper on L298N loading)

### Why Not Mecanum Instead

Mecanum would have given us strafing and rotate-in-place. Real capability gain. But:
- Needs a 4-channel motor driver (swap L298N for two L298Ns or similar) — extra integration
- Firmware math change — 4 independent PWM computations per command
- Lower traction on carpet (rollers slip)
- Tracks give us suspension; Hiwonder's in-stock mecanum kits don't have real suspension

If the goal had been aggressive indoor mobility (narrow doorways, peek-around-corners), mecanum would've won. For a security patrol rover that needs to be robust over variable floors and terrain, tracks win.

---

## Decision 4: Motors

**Constraint**: Must match chassis and battery voltage (3S LiPo = 11.1V nominal, 12.6V fully charged).

**Chosen**: **JGB3865-520R45-12** — come pre-mounted in the LewanSoul Suspended Tracked Chassis. Specs (from hiwonder.com manufacturer page, not an Amazon scrape):

| Spec | Value |
|---|---|
| Rated voltage | 12V |
| Operating range | 7-13V (3S LiPo 9.9-12.6V fits) |
| Gear reduction | 45:1 |
| Post-reduction speed | 150 ± 10 rpm |
| Encoder | Hall sensor (quadrature) |
| Rated no-load current | 0.1A (stall likely ~2-3A for this motor class) |

Built-in Hall encoders enable speed feedback, straight-line PID control, and odometry — same capability as the original Yahboom 520 plan.

Alternatives (JGA25-371 with encoders, TT hobby motors) evaluated and rejected — see decision log at the bottom.

---

## Decision 5: Wheels vs Tracks

**Chosen**: **Tank treads (2× nylon tracks, driven by 2 motors — one per side)**. Replaces the rubber-wheel option from the original plan.

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Rubber wheels (4WD) | Standard, quieter on hardwood, turn-in-place is clean, upgrade path to mecanum exists | Suspension-less rubber wheel chassis with 12V encoders were all out of stock on Amazon at build time | ~~Originally chosen~~ |
| **Tank tracks (suspended)** | Excellent traction on thresholds/cables/carpet, real spring suspension, 2-channel tank steering matches existing wiring | Noisier on hardwood, tracks wear, no mecanum upgrade path | **Chosen** |
| Mecanum wheels | Omnidirectional (strafe, rotate-in-place) | Needs 4-channel motor driver + new firmware math, low traction on carpet | Not chosen (integration cost, no suspension in in-stock options) |

Future-upgrade notes: mecanum is **no longer on the roadmap** — tank tread mounting doesn't accept mecanum wheels. If omnidirectional movement becomes a priority later, it would require a chassis swap, not an accessory swap.

---

## Decision 6: Camera

**Requirements**: Security patrol (day + night), AI vision analysis, wide coverage area, **must work with JetPack 6.2 in-tree drivers** (no custom kernel modules).

### Options Evaluated

| Camera | Sensor | Jetson JP 6.2 Driver | FOV | NoIR / Night Vision | Price | Verdict |
|---|---|---|---|---|---|---|
| ~~Pi Camera Module 3 Wide NoIR~~ | IMX708 | Community-only, flaky across JP updates | 120° | Yes | ~$35 | **Dropped** — no official Jetson driver |
| **Waveshare IMX219-160IR** | IMX219 | **In-tree, plug-and-play** | **160°** | **Yes (NoIR)** | ~$28 | **Chosen** |
| Arducam IMX219 Autofocus 160° (B0GS5814J8) | IMX219 | In-tree, plug-and-play | 160° | No (IR filter present) | ~$30 | Not chosen — daytime-only |
| Arducam IMX219 Low-Distortion (B082W4ZSM9) | IMX219 | In-tree, plug-and-play | 105° | No | ~$25 | Not chosen — narrower, not NoIR |
| Arducam IMX477 HQ NoIR | IMX477 | In-tree | Depends on lens | Yes | ~$60 + lens | Overkill for 8GB Orin Nano, pricier |
| Pi Cam 3 Wide NoIR | IMX708 | Community patches only | 120° | Yes | ~$35 | Rejected |

### Why Waveshare IMX219-160IR (Chosen)

- **Sensor is IMX219** — exactly the same chip as the Pi Camera v2, officially supported by JetPack 6.2's in-tree `tegra-camera-platform` driver. First `nvgstcapture-1.0` after flash produces video.
- **NoIR** — IR-cut filter is omitted, so 850nm IR LEDs illuminate the scene for night vision.
- **160° diagonal FOV** — wider than the 120° Pi Cam 3 Wide the original plan specced.
- **8MP / 3280 × 2464** — plenty for Gemma vision on-device and 1080p security recording.
- **~$28** — cheaper than the Pi Cam 3.
- Ships with 2× IR LED boards included, and a 15-pin FFC cable.

### Required Cable Adapter

The Orin Nano Dev Kit has **22-pin CSI connectors** (same as Pi 5). The Waveshare camera board has a **15-pin** connector. The cable in the Waveshare box is 15-pin on both ends, which won't reach the Jetson.

**Solution**: [Official Raspberry Pi CSI FPC Flexible Cable, 22-pin to 15-pin, 500mm](https://www.amazon.com/Flexible-Raspberry-Suitable-Modules-Connecting/dp/B0CVS264R1) (~$6). The 500mm length matters — the camera is on a pan-tilt mount on top of the chassis, and the Jetson is at the base. Shorter cables won't reach once everything is mounted.

### Ordered

| Item | Link | Status |
|---|---|---|
| Waveshare IMX219-160IR camera | [Amazon B07TXLF5H7](https://www.amazon.com/8MP-IMX219-160IR-Camera-Resolution-Recognition/dp/B07TXLF5H7) | ✅ Ordered |
| 22→15-pin CSI cable, 500mm | [Amazon B0CVS264R1](https://www.amazon.com/Flexible-Raspberry-Suitable-Modules-Connecting/dp/B0CVS264R1) | ✅ Ordered |

---

## Decision 7: Camera Mount

**Chosen**: SG90 pan-tilt bracket kit — 2× SG90 micro servos + plastic bracket.

| Feature | Detail |
|---|---|
| Horizontal range | 180° (pan) |
| Vertical range | ~90° (tilt) |
| Servo torque | 1.8 kg-cm (plenty for a camera) |
| Power | 5V from the "noisy" buck rail (servo transients should stay off the Pico/brain rails) |
| Control | PWM from Pico GPIO |

Pan-tilt beats a fixed mount because the camera can scan a room without the rover turning. Gimbal is $50+ and overkill indoors.

---

## Decision 8: Sensor Suite

All sensors are unchanged from the original plan — none of the camera/power/brain changes affected them.

### Summary

| Purpose | Part | Notes |
|---|---|---|
| Front obstacle | **HC-SR04 ultrasonic** (owned) | 2-400cm, ~15° cone, read by Pico |
| Orientation / tilt | **MPU6050** (owned) | 6-axis, I2C on Pico's I2C1 bus (0x68) |
| Motion detection | **HC-SR501 PIR** | ~7m, ~120° cone, wakes system in sentry mode |
| Safety (stairs) | **IR cliff sensors ×2** | Pico stops motors locally if floor reflection lost |
| Battery | **INA219** | Voltage + current over I2C1 (0x40), feeds percentage calc |
| Night vision illumination | **850nm IR LED array** | NoIR camera is most sensitive at 850nm; 940nm dimmer |
| Microphone | **INMP441 I2S** | Digital, no analog noise from motors |
| Speaker | **MAX98357A I2S + 3W speaker** | 5V on noisy buck rail alongside servos |

Full tradeoff tables preserved in git history (commit 0be2738). Skipped here because nothing changed post-Jetson-pivot.

**Future upgrade**: [RPLidar A1](https://www.amazon.com/RPLiDAR-Degree-Laser-Scanner-Range/dp/B07L89TT6F) for 360° SLAM + autonomous navigation. Jetson has the GPU compute to do SLAM locally (Pi 5 didn't).

---

## Decision 9: Power System

**Requirements**:
1. Charge without shutting down (UPS behavior)
2. Single charge port for entire rover
3. Separate clean power for brain vs noisy power for motors/servos
4. Enough capacity for 2+ hours of operation
5. **Pico stays alive if Jetson crashes** (watchdog safety — see Decision 9.1)

### Options Evaluated (Brain Power)

| Option | Output | Capacity | Charge-while-run | Jetson compatible | Price | Verdict |
|---|---|---|---|---|---|---|
| **V8 18650 shield** (owned) | 5V/3A + 3V/1A | 2x 18650 (~6000mAh) | Yes (micro USB) | No (Jetson needs 9-20V) | Already owned | **Prototype only** |
| **Waveshare UPS HAT (C)** | 5V via GPIO | 2x 18650 (~6000mAh) | Yes (USB-C) | No (5V output only) | ~$20 | **Not chosen** |
| **PiSugar 3** | 5V, 5000mAh built-in | 5000mAh | Yes (USB-C) | No (5V output only) | ~$40 | **Not chosen** |
| **Single 3S LiPo + BMS, direct to Jetson + Mini-360 bucks** | 11.1V brain + 5V Pico + 5V servo rail + 11.1V motor rail | 5000mAh @ 11.1V (~55Wh) | Yes (USB-C via BMS) | Yes (Jetson accepts 9-20V directly) | ~$46 total | **Chosen** |

### Why This Is Simpler Than the Original Pi-Based Plan

The original plan (Pi 5 brain) required a Pololu D24V50F5 5V/5A buck because the Pi 5 only accepts 5V via USB-C. The Jetson Orin Nano Dev Kit accepts **9-20V directly** via the barrel jack — our 11.1V LiPo fits perfectly. **No buck converter needed for the brain.**

| Component | Old plan (Pi 5) | New plan (Jetson) |
|---|---|---|
| Buck for brain | Pololu D24V50F5 (5V/5A, ~$15) | **None needed** — 11.1V direct to barrel jack |
| Buck for Pico | Tapped off Pi 5V header | **Dedicated Mini-360** (see Decision 9.1) |
| Buck for servos/audio | Tapped off Pi 5V header | **Dedicated Mini-360** (noisy loads isolated) |
| Battery | 3S LiPo 11.1V 5000mAh + BMS | Same |
| Motor power | Direct 11.1V to L298N | Same |
| Charge port | USB-C via BMS | Same |

Net savings: **−$13** (drop $15 Pololu, add 2× $1 Mini-360 modules from a 4-pack).

### Decision 9.1: Dedicated Mini-360 Buck for the Pico 2W (Watchdog Integrity)

**Problem**: should the Pico 2W tap the Jetson's 40-pin 5V header, or have its own buck converter?

| Factor | Tap Jetson 5V header | Dedicated Mini-360 buck |
|---|---|---|
| Cost | $0 | +~$2 (from the 4-pack already bought) |
| Wiring complexity | Simpler (one jumper) | One more component |
| **Pico survives Jetson crash / reboot** | ❌ — dies with Jetson | ✅ — stays alive, motors safe-stop |
| **Watchdog works as designed** | ❌ — if Pico dies with Jetson, watchdog never fires | ✅ — watchdog detects Jetson silence (500ms), stops motors |
| Bench testing Pico without Jetson | ❌ | ✅ |
| Header current budget | Tight (~1A shared) | Irrelevant |
| Clean boot sequence | Pico + Jetson race | Pico boots instantly into safe state |

**Decision**: **Dedicated Mini-360 for Pico**. The watchdog is designed to stop motors when the Jetson stops talking (see Decision 10 — Pico Safety Features, register `0x34`). If the Pico dies alongside the Jetson during a kernel panic mid-drive, the motors keep running until the battery dies. That is the exact failure mode the watchdog is supposed to prevent. Spending $2 on the buck to preserve the safety guarantee is a clear trade.

### 5V Topology (Final)

```
11.1V LiPo ─┬─→ Jetson barrel jack (direct, no buck)
            │
            ├─→ Mini-360 #1 (calibrate 5.0V) ──→ Pico 2W (clean, isolated, always-on)
            │
            ├─→ Mini-360 #2 (calibrate 5.0V) ──→ SG90 servos + MAX98357A amp (noisy)
            │
            └─→ L298N VCC (11.1V direct) ──→ 2× track motors

Common GND: tied between LiPo(−), Jetson, Pico, L298N, and both Mini-360 modules.
```

### Specific Parts

| Part | Spec | Rationale | ~Price | Link |
|---|---|---|---|---|
| **3S LiPo 11.1V 5000mAh 50C (XT60)** | ~55Wh, 100A+ burst | Handles 4x motor stall worst case (10A) with huge headroom; 2-3 hours runtime | ~$30 | [Gens Ace 5000mAh](https://www.amazon.com/Gens-ace-5000mAh-Battery-Brushless/dp/B01JCSOJIY) |
| **3S BMS with USB-C PD** | 12.6V charge, 10-20A cont. | Cell balancing + over-discharge protection + USB-C passthrough charging | ~$10 | [3S USB-C BMS 3-pack](https://www.amazon.com/Lithium-Battery-Charger-Step-up-Polymer/dp/B0BZC7TWC7) |
| **AITIAO Mini-360 Buck 4-pack** | 4.75-23V in, 1-17V adj. out, 1.8A cont. / 3A peak, 30mV ripple | Two used (Pico rail + servo/audio rail), two spares | ~$4 | [AITIAO 4-pack B09N8N5B7F](https://www.amazon.com/AITIAO-Converter-Regulator-Adjustable-Step-Down/dp/B09N8N5B7F) |

### Motor Driver

**Chosen**: **L298N** — handles 11.1-12.6V from 3S LiPo safely (max 46V), 2 channels (left pair + right pair, tank steering), ~2A continuous / 3A peak per channel, well documented.

TB6612FNG rejected: max 13.5V is too close to our 12.6V peak — back-EMF spike could fry it. (If future build uses 2S LiPo instead, prefer TB6612FNG for its 95% efficiency.)

BTS7960 not chosen: 43A continuous is massive overkill for a ~2.5A-stall motor.

---

## Decision 10: Brain — Jetson Orin Nano Super Dev Kit

**Chosen**: **NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super** (8GB), already owned. Running **JetPack 6.2 (L4T R36.5) / Ubuntu 22.04**.

Confirmed via SSH during planning:
- Board: `NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super`
- L4T: `R36.5.0`
- Ubuntu: `22.04.5 LTS`
- Kernel: `5.15.185-tegra`

The "Super" bin has 67 TOPS (vs 40 TOPS on the original Orin Nano) and higher memory bandwidth (102 GB/s vs 68 GB/s), at ~25W max (15W default mode).

### Why Jetson Over Pi 5

Originally the plan called for Pi 5 → Jetson later. Now that the Jetson is in hand, everything moves up:

| Factor | Pi 5 | **Jetson Orin Nano Super (chosen)** |
|---|---|---|
| GPU | None | 1024 Ampere CUDA cores, 32 Tensor cores, 67 TOPS |
| Local LLM | Needs Mac Mini (LM Studio) | Runs locally (~30-40 tok/s, 7B model via llama.cpp or ollama) |
| Vision (Gemma) | Mac Mini network hop | Runs locally on GPU |
| Whisper STT | Mac Mini only | Near-realtime locally |
| Object detection | Mac Mini round trip | **Real-time YOLO on-device** (enables follow-me, sentry smart alerts) |
| Storage | microSD | NVMe M.2 (faster, more durable on a rover) |
| Power input | 5V USB-C (strict 5A) | 9-20V barrel jack — simpler power chain |
| Mac Mini needed? | Yes | **Optional** (fallback LLM/TTS backend only) |
| Current draw | ~15-25W peak | ~7-25W depending on power mode |

### What Jetson Unlocks Over the Original Plan

- Real-time object detection on camera feed (person vs pet vs package) for sentry mode
- Follow-me / face tracking at frame rate
- On-device Whisper STT — voice commands while roving, no network needed
- Local Gemma vision — no Mac Mini round trip
- Fully autonomous operation off-network
- Future SLAM with RPLidar (Pi 5 was too slow for this)

### Mac Mini Role

Moves from **required** to **optional fallback**. Config:

```
LLM_BACKEND=local              # default — runs on Jetson (llama.cpp / ollama)
LLM_BACKEND_FALLBACK=anthropic # or set LMSTUDIO_URL=http://10.0.0.131:1234 for Mac Mini
```

Jetson handles everything on-device; Mac Mini stays reachable as a quality-ladder option (e.g., for tasks needing a larger model than fits in 8GB).

---

## Complete Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│              ROVER CHASSIS (LewanSoul Suspended Tracked — B0CTK7YHQK)│
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  Jetson Orin Nano Super Dev Kit (BRAIN)                    │      │
│  │    ├── WiFi → home network / Cloudflare tunnel             │      │
│  │    ├── Waveshare IMX219-160IR (22-pin CSI via 500mm FFC)   │      │
│  │    ├── RPLidar A1 (USB serial) [future upgrade]            │      │
│  │    ├── INMP441 I2S microphone (40-pin header)              │      │
│  │    ├── MAX98357A I2S DAC + 3W speaker                      │      │
│  │    ├── I2C0 (pins 3, 5) ──→ Pico 2W (address 0x42)         │      │
│  │    └── PiAssistant server (FastAPI) + local LLM + vision   │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  Pico 2W (BODY CONTROLLER, I2C peripheral, WiFi disabled)  │      │
│  │    ├── I2C0: peripheral to Jetson (address 0x42)           │      │
│  │    ├── I2C1: controller for MPU6050 (0x68) + INA219 (0x40) │      │
│  │    ├── PWM: L298N H-Bridge → 2x track motors (L + R)       │      │
│  │    ├── PWM: SG90 pan servo + SG90 tilt servo               │      │
│  │    ├── GPIO: HC-SR04 ultrasonic (trigger + echo)           │      │
│  │    ├── GPIO: HC-SR501 PIR sensor                           │      │
│  │    ├── GPIO: IR cliff sensors (x2, front left + right)     │      │
│  │    └── GPIO: IR LED array (on/off)                         │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  Power System                                              │      │
│  │    3S LiPo 11.1V 5000mAh                                   │      │
│  │    ├── 3S BMS (USB-C charge, passthrough, protection)      │      │
│  │    ├── Direct 11.1V → Jetson barrel jack (RAIL A)          │      │
│  │    ├── Mini-360 #1 → 5V clean → Pico 2W (RAIL B, calibrated)│     │
│  │    ├── Mini-360 #2 → 5V noisy → SG90s + MAX98357A (RAIL C) │      │
│  │    └── Direct 11.1V → L298N H-Bridge → track motors (RAIL D)     │      │
│  │                                                            │      │
│  │    Common GND tied between all boards                      │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Wiring Detail

```
3S LiPo (+) ──→ BMS ──→ 3S LiPo (-)
                 │
                 ├── USB-C charge port (input)
                 │
                 ├──→ Jetson barrel jack (direct, 11.1V)
                 │
                 ├──→ Mini-360 #1 (calibrate to 5.0V) ──→ Pico 2W VSYS
                 │
                 ├──→ Mini-360 #2 (calibrate to 5.0V) ──→ SG90 pan V+, SG90 tilt V+, MAX98357A VIN
                 │
                 └──→ L298N VCC (motor power, 11.1V)
                           ├── OUT1/OUT2 → Left track motor (1 motor, JGB3865-520R45-12)
                           └── OUT3/OUT4 → Right track motor (1 motor, JGB3865-520R45-12)

Jetson 40-pin header pin 3 (SDA) ────→ Pico 2W GPIO 0 (I2C0 SDA)
Jetson 40-pin header pin 5 (SCL) ────→ Pico 2W GPIO 1 (I2C0 SCL)
Jetson GND (pin 6) ──────────────────→ Pico 2W GND

Waveshare IMX219-160IR 15-pin ──→ 22-pin FFC adapter ──→ Jetson CAM0 (22-pin CSI)

Pico 2W GPIO 14 (SDA) ──→ MPU6050 SDA + INA219 SDA (I2C1 bus)
Pico 2W GPIO 15 (SCL) ──→ MPU6050 SCL + INA219 SCL (I2C1 bus)

Pico 2W GPIO 2 ──→ L298N IN1 (left motors)
Pico 2W GPIO 3 ──→ L298N IN2 (left motors)
Pico 2W GPIO 4 ──→ L298N IN3 (right motors)
Pico 2W GPIO 5 ──→ L298N IN4 (right motors)
Pico 2W GPIO 6 ──→ L298N ENA (left PWM speed)
Pico 2W GPIO 7 ──→ L298N ENB (right PWM speed)

Pico 2W GPIO 8  ──→ HC-SR04 Trigger
Pico 2W GPIO 9  ──→ HC-SR04 Echo
Pico 2W GPIO 10 ──→ Pan servo PWM
Pico 2W GPIO 11 ──→ Tilt servo PWM
Pico 2W GPIO 12 ──→ PIR sensor (digital input)
Pico 2W GPIO 13 ──→ IR LEDs (digital output via transistor)
Pico 2W GPIO 16 ──→ Left cliff sensor (digital input)
Pico 2W GPIO 17 ──→ Right cliff sensor (digital input)
```

---

## Pico Safety Features

The Pico 2W handles all safety locally — no network latency between sensor reading and emergency response. **Dedicated Mini-360 power for the Pico preserves these guarantees when the Jetson is unavailable.**

| Safety feature | Trigger | Action | Latency |
|---|---|---|---|
| **Watchdog** | No I2C command from Jetson in 500ms | Stop all motors | <1ms |
| **Cliff detection** | IR cliff sensor reads no floor | Emergency stop + set cliff flag | <1ms |
| **Obstacle avoidance** | Ultrasonic < 10cm | Emergency stop + set obstacle flag | ~5ms |
| **Battery low** | INA219 voltage < 10.2V (3.4V/cell) | Set battery_low flag, alert Jetson | <1ms |
| **Tilt detection** | MPU6050 tilt > 45° | Stop motors (rover is stuck/tipping) | <1ms |

The Jetson reads these status flags via register 0x34 and can display alerts on the dashboard, but the Pico acts immediately without waiting for Jetson commands.

---

## Shopping List

### Ordered (2026-04-18)

| # | Part | Qty | ~Price | Link |
|---|---|---|---|---|
| A | Waveshare IMX219-160IR camera | 1 | $28 | [Amazon B07TXLF5H7](https://www.amazon.com/8MP-IMX219-160IR-Camera-Resolution-Recognition/dp/B07TXLF5H7) |
| B | 22-pin to 15-pin CSI FFC cable, 500mm | 1 | $6 | [Amazon B0CVS264R1](https://www.amazon.com/Flexible-Raspberry-Suitable-Modules-Connecting/dp/B0CVS264R1) |
| C | AITIAO Mini-360 Buck Converter 4-pack | 1 | $4 | [Amazon B09N8N5B7F](https://www.amazon.com/AITIAO-Converter-Regulator-Adjustable-Step-Down/dp/B09N8N5B7F) |
| D | **LewanSoul Suspended Tracked Chassis** (with JGB3865-520R45-12 encoder motors, 12V, double-layer aluminum, spring suspension) | 1 | ~$120 | [Amazon B0CTK7YHQK](https://www.amazon.com/Tracked-Suspension-Absorption-Full-Metal-Platform/dp/B0CTK7YHQK) |

### Still to Order

| # | Part | Qty | ~Price | Suggested Link |
|---|---|---|---|---|
| 1 | SG90 micro servo motors (x2 for pan-tilt) | 1 pack | $7 | [WWZMDiB 3-pack B0BKPL2Y21](https://www.amazon.com/WWZMDiB-SG90-Control-Servos-Arduino/dp/B0BKPL2Y21) |
| 2 | Pan-tilt bracket (SG90, no servos) | 1 | $5 | [Amazon B09TFXGC21](https://www.amazon.com/Platform-Anti-Vibration-Aircraft-Dedicated-VE223P0-3/dp/B09TFXGC21) |
| 3 | 3S LiPo 11.1V 5000mAh 50C (XT60) | 1 | $30 | [Gens Ace B01JCSOJIY](https://www.amazon.com/Gens-ace-5000mAh-Battery-Brushless/dp/B01JCSOJIY) |
| 4 | **AEDIKO 3S 20A BMS** (6-pack) — replaces the 4A USB-C BMS from earlier drafts | 1 pack | $10 | [AEDIKO B09MLXFH81](https://www.amazon.com/AEDIKO-Lithium-Protection-Over-Discharge-Over-Current/dp/B09MLXFH81) |
| 5 | **SKYRC iMAX B6AC V2 balance charger** (new — required because 20A BMS has no built-in charger) | 1 | $45 | [Amazon B0722NGPBS](https://www.amazon.com/Genuine-Professional-Battery-Balance-Discharger/dp/B0722NGPBS) |
| 6 | L298N motor driver | 1 | $5 | [HiLetgo 4-pack B07BK1QL5T](https://www.amazon.com/HiLetgo-Controller-Stepper-H-Bridge-Mega2560/dp/B07BK1QL5T) |
| 7 | HC-SR501 PIR sensor | 1 | $6 | [Amazon 3-pack B0897BMKR3](https://www.amazon.com/HC-SR501-PIR-Motion-Sensor-Detector/dp/B0897BMKR3) |
| 8 | 850nm IR illuminator (12V) | 1 | $12 | [Univivi 6-LED B01G6K407Q](https://www.amazon.com/Univivi-Infrared-Illuminator-Waterproof-Security/dp/B01G6K407Q) |
| 9 | IR cliff sensors | 2 | $6 | [Amazon 2-pack B07PFCC76N](https://www.amazon.com/Infrared-Avoidance-Transmitting-Receiving-Photoelectric/dp/B07PFCC76N) |
| 10 | Adafruit INA219 current/voltage sensor | 1 | $8 | [Amazon B09CBSLXN7](https://www.amazon.com/Adafruit-Industries-INA219-Current-Breakout/dp/B09CBSLXN7) |
| 11 | Jumper wires, M3 standoffs, zip ties, logic MOSFETs, 10kΩ resistors | misc | $30 | Search Amazon |

### Should Have (Audio)

| # | Part | Qty | ~Price | Link |
|---|---|---|---|---|
| 12 | INMP441 I2S microphone | 1 | $4 | [Amazon 5-pack](https://www.amazon.com/EC-Buying-INMP441-Omnidirectional-Microphone/dp/B0C1C64R8S) |
| 13 | MAX98357A I2S DAC amplifier | 1 | $8 | [Adafruit MAX98357A](https://www.amazon.com/Adafruit-I2S-Class-Amplifier-Breakout/dp/B01K5GCFA6) |
| 14 | 3W 4-ohm speaker | 1 | $3 | Search Amazon "3W 4 ohm speaker small" |

### Game Changer (Future)

| # | Part | Qty | ~Price | Link |
|---|---|---|---|---|
| 15 | RPLidar A1M8 360° laser scanner | 1 | $100 | [Stemedu RPLidar A1M8](https://www.amazon.com/RPLiDAR-Degree-Laser-Scanner-Range/dp/B07L89TT6F) |

### Already Owned

| Part | Status |
|---|---|
| Jetson Orin Nano Super Dev Kit (8GB) | Have — brain |
| Pico 2W boards | Have — body controller (WiFi disabled) |
| Pi 5 (8GB) | Have — PiAssistant mothership (dashboard/hub), not used on rover |
| HC-SR04 ultrasonic | Have |
| MPU6050 accel/gyro | Have |
| 4x DC motors | Have (will be replaced by Yahboom chassis's 520 encoder motors) |
| V8 18650 battery shield | Have — prototype power only |

### Total Cost

| Tier | Parts | Cost |
|---|---|---|
| Must Have | A, B, C, D + #1-11 | ~$290 |
| Must Have + Audio | + #12-14 | ~$305 |
| Full Build | + #15 (RPLidar) | ~$405 |

### Net Cost Deltas vs Original Pi-Based Plan

| Change | Delta |
|---|---|
| Drop Pi Cam 3 Wide NoIR ($35) → Waveshare IMX219-160IR ($28) + cable ($6) | −$1 |
| Drop Pololu D24V50F5 buck ($15) → 2× Mini-360 modules from 4-pack ($4 total) | −$11 |
| Plain Pico ($4) → Pico 2W (owned) | −$4 |
| **Chassis**: Yahboom Suspension 4WD ($70) → LewanSoul Tracked Suspended ($120) | +$50 |
| **BMS**: 4A USB-C BMS ($10) → 20A AEDIKO BMS ($10) + SKYRC iMAX B6AC charger ($45) | +$45 |
| **Net change** | **+$79** |

The +$79 reflects real capability upgrades: a proper 20A-rated BMS for our actual current profile (vs the underspecced 4A USB-C board), a real RC-grade LiPo balance charger, and a suspended tracked chassis (vs waiting indefinitely for a specific out-of-stock Yahboom SKU).

---

## Software Integration Preview

### New Service: RoverService

Follows the `BaseService` pattern. Uses `smbus2` library to communicate with Pico 2W over I2C:

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

Rover control widget with directional pad, camera view (MJPEG), pan-tilt sliders, battery indicator, sensor readouts, security mode toggle, patrol route selector.

### Jetson-Specific New Capabilities

Capabilities that were not feasible on Pi 5 but are now in scope on Jetson:
- **Local Whisper STT** on the Jetson (replaces need for Mac Mini for voice input)
- **Real-time YOLO object detection** on the camera feed — enables "follow me" and smart security alerts
- **Local Gemma vision** — no Mac Mini network hop for image analysis
- **RPLidar SLAM** (future) — GPU-accelerated mapping and navigation

---

## Decision Log

| Date | Decision | Options Considered | Chosen | Key Rationale |
|---|---|---|---|---|
| 2026-03-30 | Body controller | Jetson GPIO, Pico 2W WiFi, Pico 2W I2C, Arduino UART | Pico 2W I2C | Real-time control, microsecond latency, crash isolation |
| 2026-03-30 | Communication | I2C, SPI, UART, USB, WiFi | I2C | 2-wire simplicity, native Jetson/Pi support, multi-device addressing |
| 2026-03-30 | Chassis | ~~Wild Thumper~~ (discontinued), Devastator (6V motors), Yahboom Suspension 4WD, Yahboom no-suspension, Acrylic | Yahboom Suspension 4WD | Suspension, aluminum 3-layer, 12V 520 encoder motors, 2kg payload |
| 2026-03-30 | Motors | Yahboom 520 DC (included), JGA25-371, TT hobby | Yahboom 520 DC with encoders | Pre-mounted, 12V, metal gearbox, built-in encoders |
| 2026-03-30 | Wheels | Rubber, Mecanum, Tracks | Rubber (standard) | Included, simple, good grip |
| 2026-03-30 | Camera mount | Pan-tilt, Fixed, Gimbal | SG90 pan-tilt | Independent look direction, LLM controllable |
| 2026-03-30 | Distance sensor | HC-SR04, RPLidar A1, VL53L0X | HC-SR04 (keep) + RPLidar A1 (later) | Already owned; RPLidar is game-changing upgrade |
| 2026-03-30 | IMU | MPU6050, MPU9250, BNO055 | MPU6050 (keep) | Already owned, sufficient for indoor use |
| 2026-03-30 | Motion sensor | HC-SR501 PIR, RCWL-0516 radar | HC-SR501 PIR | $2, detects body heat, low false positives |
| 2026-03-30 | Safety sensors | IR cliff, bumper switches | IR cliff sensors (x2) | Critical stair safety, ultrasonic covers collision |
| 2026-03-30 | Battery monitor | INA219, voltage divider | INA219 | Voltage + current, I2C, accurate percentage |
| 2026-03-30 | Night vision | 850nm IR, 940nm IR, white LED | 850nm IR LEDs | Best camera sensitivity, barely visible |
| 2026-03-30 | Microphone | INMP441 I2S, USB mic | INMP441 I2S | Digital (low noise), no USB port used |
| 2026-03-30 | Speaker | MAX98357A I2S, 3.5mm jack | MAX98357A I2S + 3W | Digital (no motor noise) |
| 2026-03-30 | Motor driver | L298N, TB6612FNG, BTS7960 | L298N | Handles 12.6V safely, proven |
| 2026-04-17 | **Brain** | Pi 5 now → Jetson later, or Jetson now | **Jetson Orin Nano Super (now)** | User purchased it; unlocks on-device LLM/vision/STT, removes Mac Mini dependency, simpler power chain (direct 11.1V) |
| 2026-04-17 | **Camera** | Pi Cam 3 Wide NoIR (IMX708), Arducam 105° (B082W4ZSM9), Arducam 160° autofocus (B0GS5814J8), **Waveshare IMX219-160IR (B07TXLF5H7)** | **Waveshare IMX219-160IR** | In-tree JetPack 6.2 driver, NoIR for night vision with 850nm IR LEDs, 160° FOV (wider than old plan), ~$28 |
| 2026-04-17 | Camera cable | Shipped 15-pin-only cable, 22-to-15-pin 200mm, **22-to-15-pin 500mm** | 500mm 22-to-15-pin | Camera is on pan-tilt away from Jetson board; short cables won't reach |
| 2026-04-17 | Body controller SKU | Plain Pico (RP2040), Pico 2W (RP2350) | **Pico 2W, WiFi disabled** | Already owned (−$4), hardware FPU helps PID/IMU math, drop-in I2C pinout, same register map |
| 2026-04-17 | Brain power rail | Pololu D24V50F5 buck ($15), direct 11.1V | **Direct 11.1V to barrel jack** | Jetson accepts 9-20V; no buck needed for brain — save $15 |
| 2026-04-17 | Pico 5V source | Tap Jetson 5V header, **dedicated Mini-360 buck** | **Dedicated Mini-360** | Preserves watchdog safety guarantee (Pico survives Jetson crash); $2 insurance |
| 2026-04-18 | Mini-360 buck SKU | 12-pack (B09N8T7ZK4), **4-pack (B09N8N5B7F)** | **4-pack** | Sufficient (2 used + 2 spares); avoids excess inventory |
| 2026-04-18 | Mac Mini role | Required backend, **Optional fallback** | **Optional fallback** | Jetson runs LLM/vision/STT locally; Mac Mini kept as `LLM_BACKEND_FALLBACK` for larger-model quality ladder |
| 2026-04-18 | BMS | 4A USB-C BMS (B0BZC7TWC7), 20A+ standalone BMS, USB-C PD trigger + charger sandwich | **AEDIKO 3S 20A BMS (B09MLXFH81)** | 4A USB-C BMS can't handle 13A peak discharge; high-current USB-C BMS boards are rare/expensive; accept separate charger workflow like all RC hobbyists |
| 2026-04-18 | LiPo charger | Wall-wart 12.6V, hobby balance charger, USB-C PD trigger | **SKYRC iMAX B6AC V2 (B0722NGPBS)** | AC-powered (no separate brick), proper balance charging prevents cell damage, industry standard for RC LiPo |
| 2026-04-18 | **Chassis** | Yahboom Suspension 4WD (B0BR9QBZSP — out of stock), Yahboom Suspension Mecanum (B0BR9PTTB3 — out of stock), Yahboom 4WD no-suspension (B0F3CYLFJF), Hiwonder Mecanum (B0BB72LPDH/B09ZQF3FKR), **LewanSoul Suspended Tracked (B0CTK7YHQK)**, TT-motor kits | **LewanSoul Suspended Tracked (B0CTK7YHQK)** | Yahboom rubber-wheel SKUs all out of stock; only in-stock option with real suspension + 12V Hall encoders + aluminum; 2-channel tank steering keeps L298N wiring unchanged; 12V JGB3865-520R45-12 motors confirmed from hiwonder.com manufacturer page (not Amazon scrape) |
| 2026-04-18 | Drivetrain | Rubber wheels (4WD), Mecanum (4WD), **Tank tracks** | **Tank tracks** | Consequence of chassis choice; accept noisier hardwood operation, lose mecanum upgrade path, gain threshold/cable traction and spring suspension |
