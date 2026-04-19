# Rover Build Plan

Companion to [`docs/rover-design.md`](rover-design.md). The design doc is the "why" — decisions, tradeoffs, parts rationale. This doc is the "what do I do next" — phased task list from boxes-arriving to autonomous-patrol.

## Status Snapshot (2026-04-18)

### Ordered
- Waveshare IMX219-160IR camera (B07TXLF5H7)
- 22→15-pin CSI cable, 500mm (B0CVS264R1)
- AITIAO Mini-360 Buck 4-pack (B09N8N5B7F)
- LewanSoul Suspended Tracked Chassis (B0CTK7YHQK)
- Gens Ace 3S LiPo 5000mAh 50C (B01JCSOJIY)
- AEDIKO 3S 20A BMS 6-pack (B09MLXFH81)
- SKYRC iMAX B6AC V2 balance charger (B0722NGPBS)
- HiLetgo L298N 4-pack (B07BK1QL5T)
- WWZMDiB SG90 servos 3-pack (B0BKPL2Y21)
- Pan-tilt bracket SG90 (B09TFXGC21)
- HC-SR501 PIR sensor 3-pack (B0897BMKR3)
- IR cliff sensors 2-pack (B07PFCC76N)
- Adafruit INA219 (B09CBSLXN7)
- ELEGOO 120pc Dupont Jumper Wires (B01EV70C78)
- AIMUNOK 176pc M3 Brass Standoff Kit (B0CQ7Y6D7T)
- REZOSY 600pc Zip Ties Assorted (B097M825XG)
- BOJACK IRLZ44N MOSFETs 10-pack (B0FH6T96BP)
- E-Projects 10kΩ Resistors 100-pack (B07C93JL54)
- EC Buying INMP441 I2S Mic 5-pack (B0C1C64R8S)
- Generic MAX98357A I2S Amp 2-pack (B0DPJRLMDJ)
- Gikfun 40mm 4Ω 3W Speaker 2-pack (B01LN8ONG4)

### Deferred
- Univivi 850nm IR illuminator — can add to 2nd CSI port later if night vision becomes a priority
- RPLidar A1M8 — revisit after the rover drives manually under voice control

### Already Owned
- Jetson Orin Nano Super Dev Kit (JetPack 6.2, L4T R36.5, Ubuntu 22.04) — `akshay@10.0.0.7`
- Pico 2W boards (multiple)
- HC-SR04 ultrasonic
- MPU6050 accel/gyro
- Pi 5 mothership (runs PiAssistant server, not part of the rover)

---

## ⚠️ Read the Critical Assembly Notes Before Phase 2

See [`docs/rover-design.md`](rover-design.md) — "Critical Assembly Notes" section. The voltage calibration of the Mini-360 bucks is the single most dangerous step. If you're about to start Phase 2, re-read that section with a multimeter in hand.

---

## Phase 0 — Pre-Arrival Groundwork (Start Today)

**Goal**: When the boxes land, all the code is written and tested against stubs. Hardware integration becomes "swap stub for real I2C" plus wiring.

**Hardware-independent — everything here runs on Mac/dev or existing Jetson/Pico 2W.**

### 0.1 Jetson environment bring-up
- Confirm JetPack 6.2 (L4T R36.5) — already verified via SSH
- Enable I2C on 40-pin header: `sudo /opt/nvidia/jetson-io/jetson-io.py` → select I2C1 pins
- Verify: `ls /dev/i2c-*` shows the new bus; `i2cdetect -y <bus>` works
- Install Python 3.11 venv (or system Python 3.10), activate, `pip install smbus2`
- Clone PiAssistant repo: `git clone git@github.com:akshayadav/PiAssistant.git ~/piassistant`
- Install full requirements in a venv on the Jetson
- Set up `.env` on Jetson with rover-specific flags: `ROVER_ENABLED=true`, `LLM_BACKEND=local`, `LMSTUDIO_URL` pointing at local llama.cpp

### 0.2 Local LLM on Jetson
- Install llama.cpp with CUDA build (or ollama if preferred) on the Jetson
- Pull a small model first — Qwen 2.5-3B or Gemma 2-2B — to verify GPU inference works
- Measure tok/s; tune GPU layer count in `llama.cpp` for best throughput on 8GB
- Expose OpenAI-compatible endpoint on localhost:1234 (matches `LMSTUDIO_URL` pattern)
- Later: upgrade to Qwen 2.5-7B once base works

### 0.3 `RoverService` skeleton
- Create `src/piassistant/services/rover.py`:
  - Extends `BaseService` — `name`, `initialize()`, `health_check()`
  - Constructor takes I2C bus number and Pico address (default `0x42`)
  - Methods: `move(left, right)`, `stop()`, `brake()`, `get_distance()`, `get_orientation()`, `get_battery()`, `look(pan, tilt)`, `get_status()`, `set_ir_leds(on)`
  - In stub mode: log what would be written/read, return canned data
  - Real mode: `smbus2.SMBus(bus).write_i2c_block_data(...)` / `read_i2c_block_data(...)` per register map
- Register in `main.py` service registry (gated on `ROVER_ENABLED` env var)
- Add `SERVICES.md` entry so developers discover it

### 0.4 Brain tools for rover
Add to `src/piassistant/brain/tools.py`:
- `rover_move(direction, speed, duration_ms)`
- `rover_stop()`
- `rover_distance()`
- `rover_orientation()`
- `rover_battery()`
- `rover_look(pan, tilt)`
- `rover_status()`
- `patrol_start(route_name)`
- `patrol_stop()`
- `security_arm()`
- `security_disarm()`

Update keyword filter rules so these surface on messages like "drive forward", "look left", "patrol", "keep watch", "battery", etc.

Update system prompt to mention rover capabilities.

### 0.5 Dashboard rover widget (skeleton)
- New section in `static/index.html` — rover widget with directional D-pad, camera `<img>` tag (MJPEG stream placeholder), pan-tilt sliders, battery bar, sensor readouts (distance, orientation, motion flags)
- JS in `static/js/dashboard.js` — poll `/api/rover/status` every 500ms, update UI
- CSS matches existing widget visual language
- Feature-flag off `config.rover_enabled` from `/api/config` so other devices don't see a broken widget

### 0.6 API routes
New file `src/piassistant/api/routes_rover.py`:
- `POST /api/rover/move` — body `{left, right, duration_ms}`
- `POST /api/rover/stop`
- `GET /api/rover/status` — all sensor readings + flags
- `POST /api/rover/look` — body `{pan, tilt}`
- `GET /api/rover/camera/mjpeg` — live MJPEG stream (added later in Phase 4)
- Use API-key middleware (dormant) the same way as other write routes

### 0.7 Pico 2W firmware skeleton
Separate repo or `firmware/pico2w/` subdirectory:
- Install latest MicroPython UF2 for RP2350 on a Pico 2W
- I2C peripheral at address 0x42 on I2C0 pins (GPIO 0 SDA, GPIO 1 SCL)
- Register file (stub): returns zeros for all reads, echoes writes into a dict
- Main loop: handle I2C events, no motor/sensor logic yet
- `boot.py`: explicitly do NOT import `network` (WiFi stays off)

### 0.8 Mock integration test
- With stub RoverService and Pico firmware stub on a dev Pico:
  - Start PiAssistant on Mac/Jetson
  - Open dashboard → click D-pad arrow → verify HTTP call hits `/api/rover/move`
  - RoverService logs the I2C write it would do
  - Optionally: real Pico on a USB-I2C adapter receives the write, echoes response
- pytest coverage for RoverService stub mode (no hardware in CI)

**Phase 0 acceptance**: End-to-end plumbing works with stubs. You can click dashboard buttons and trace the call all the way to an I2C write that the dev Pico 2W sees.

---

## Phase 1 — Inventory + Mechanical Assembly

**Trigger**: Hardware boxes arrive. Before any electronics.

### 1.1 Inventory
- Check every box against the ordered list above
- Flag missing/damaged items immediately while Amazon returns are easy
- Set aside the LiPo — do **not** leave it in extreme heat, do not puncture the foil

### 1.2 Chassis assembly
- Follow Hiwonder's instruction PDF/video for the LewanSoul tracked chassis
- Attach motors to gearbox mounts
- Install tracks over drive sprockets and idler wheels
- Install suspension springs (8-channel carbon steel) — these thread through specific holes per the manual
- Confirm tracks rotate freely when you turn each motor shaft by hand
- Confirm suspension flexes smoothly without binding

### 1.3 Plan board layout
- With a pencil and the empty assembled chassis: mark where Jetson, Pico 2W, L298N, BMS, LiPo bay, and the two Mini-360 bucks will live
- Prioritize: LiPo low + centered (mass), Jetson somewhere with airflow, L298N near motors (short motor wires), Pico 2W near the L298N (short control wires), camera on top on the pan-tilt mount
- M3 standoffs at marked positions — choose heights so boards don't touch each other or the chassis

### 1.4 Servo bench test
- **Before mounting** on the pan-tilt bracket, test each SG90:
  - 5V bench supply (or a single Mini-360 calibrated to 5V per Phase 2.1)
  - Pulse pin driven by any available microcontroller with 20ms PWM, 1-2ms pulse width
  - Sweep 0-180° and confirm smooth motion, no dead zones, no chattering
- Mount both servos in the pan-tilt bracket. Do NOT yet bolt the bracket to the chassis — keep it free for easy rework.

### 1.5 Sensor bench tests (cheap, fast, prevents debugging later)
- INA219 — wire to a spare Pico 2W's I2C, run MicroPython `from machine import I2C` and read voltage/current. Connect to a known voltage source and verify measurement.
- MPU6050 — same pattern. Read accel/gyro, tilt the sensor by hand, confirm values change plausibly.
- HC-SR04 — trigger + echo on two GPIOs, measure pulse width in µs, convert to cm. Wave hand in front, verify reading.
- HC-SR501 PIR — 5V supply, GPIO reads high when you walk past.
- IR cliff sensors — shine LED down at a desk vs over the edge, GPIO should toggle.

**Phase 1 acceptance**: Chassis is fully mechanically assembled with tracks moving. All sensors have been individually validated. Standoff positions planned.

---

## Phase 2 — Power System (⚠️ Voltage Calibration Critical)

**This phase requires a multimeter. Do not skip the calibration step.**

### 2.1 Calibrate Mini-360 bucks
For each Mini-360 (need 2 for the build + any spares you want to pre-calibrate):
1. Connect input (IN+, IN−) to the LiPo or any 6-12V source
2. Probe output (OUT+, OUT−) with a multimeter set to DC volts
3. **No load connected to output**
4. Turn the brass trim pot — multi-turn, typically 15-20 turns total range
   - Clockwise = voltage decreases
   - Counter-clockwise = voltage increases
5. Adjust until multimeter reads **5.00V ± 0.05V**
6. Verify under load: attach ~100Ω resistor across output, confirm voltage holds ~5V
7. Mark the pot with a nail-polish dot so you know it's been set

### 2.2 LiPo first charge
- Plug the LiPo's balance connector into the iMax B6AC V2
- Select LiPo, 3S, 1A-2A charge rate, BALANCE mode
- Charge to storage voltage first (~3.85V/cell, ~11.55V total) for the first cycle — gentle on a brand-new pack
- Later full charge to 12.6V when ready to run the rover
- Never leave unattended; use a LiPo-safe bag if you have one

### 2.3 Build the power distribution
Per the topology in the design doc:

```
LiPo (3S 11.1V)
  │
  └── BMS (AEDIKO 20A) ─── discharge leads to XT60 pigtail
         │
         ├── Balance leads stay accessible for charging
         │
         └── XT60 → distribution (terminal block or bus bar) with a main switch

Distribution (+11.1V rail)
  ├── Jetson barrel jack (direct, 11.1V nominal)
  ├── Mini-360 #1 (calibrated 5V) → Pico 2W VSYS
  ├── Mini-360 #2 (calibrated 5V) → SG90 servos V+, MAX98357A VIN
  └── L298N VCC (11.1V motor power)

Common GND: LiPo (−) tied to Jetson GND, Pico GND, L298N GND, both Mini-360 GNDs
```

### 2.4 First power-on (graduated)
1. Everything wired up, **but Pico 2W and Jetson NOT connected yet**
2. Multimeter on each output rail:
   - 11.1V rail reads ~12.6V (full charge) or ~11.1V (nominal)
   - Mini-360 #1 output reads 5.00V
   - Mini-360 #2 output reads 5.00V
3. Connect a small load to each 5V rail (LED with 330Ω resistor is fine) — voltage stays stable
4. Power cycle. Reboot. No sparks, no smell, no heat.
5. Now connect the **Pico 2W** (powered only, no I2C yet). Boot into MicroPython REPL over USB. Wait 2+ min. No heat, no smell.
6. Finally connect the **Jetson**. Power-on via the 11.1V barrel jack. Boot to login prompt. Wait 5 min. No heat anywhere unexpected.

### 2.5 Wire the I2C bus and common ground
- Jetson 40-pin pin 3 (SDA) → Pico 2W GPIO 0
- Jetson 40-pin pin 5 (SCL) → Pico 2W GPIO 1
- Jetson GND (pin 6) → Pico 2W GND
- Keep these wires short (< 20cm) to avoid I2C signal integrity issues

### 2.6 Motor + servo + sensor wiring
Per the wiring detail in the design doc. Key check: **add 10kΩ pulldowns on each L298N input** (IN1-IN4, ENA, ENB) so motors default OFF when the Pico is reflashing.

**Phase 2 acceptance**: All rails at their target voltages under light load. Pico 2W and Jetson both boot and stay stable. I2C wires connect (no traffic yet). No heat anywhere.

---

## Phase 3 — Pico 2W Firmware

The biggest block of real engineering work. Budget 2-3 weekends.

### 3.1 I2C peripheral bring-up
- Configure I2C0 in peripheral mode at address 0x42
- Handle read and write callbacks
- Register file: a dict/array in RAM, 256 bytes addressable
- Test from Jetson: `i2cget -y <bus> 0x42 0x01` and `i2cset -y <bus> 0x42 0x01 0x40`
- Verify the Pico LED blinks or REPL logs show the transaction

### 3.2 Register map — write side
- `0x01` left motor speed (int8)
- `0x02` right motor speed (int8)
- `0x03` command (stop/brake/coast)
- `0x04` pan servo angle (0-180)
- `0x05` tilt servo angle (0-180)
- `0x06` IR LEDs on/off (register exists even though illuminator is deferred)

### 3.3 Motor control
- PWM setup on GPIOs 2-7 for L298N IN1/IN2/IN3/IN4/ENA/ENB
- Function: given left_speed (−100 to +100), generate correct IN1/IN2 polarity and ENA duty cycle
- Same for right
- **Test with wheels off the ground first** — lift the rover so tracks spin freely in air before any real commands
- Verify direction matches the Jetson command (forward +100 should drive both tracks forward, not one each direction)

### 3.4 Servo control
- PWM on GPIOs 10-11 for pan/tilt, 50 Hz frequency, 1-2 ms pulse
- Test endpoint limits (don't strain the SG90)

### 3.5 Register map — read side
Implement each sensor read in a background loop (main thread reads peripherals, interrupt thread handles I2C):
- `0x10` ultrasonic distance (uint16 cm) — HC-SR04 trigger + echo timing, 10Hz sample rate
- `0x12` cliff flags (bit0=L, bit1=R) — GPIO read, interrupt-driven for safety
- `0x13` PIR motion (0/1) — GPIO read
- `0x20-0x2A` IMU accel X/Y/Z + gyro X/Y/Z — I2C1 read from MPU6050 at 100Hz
- `0x30-0x32` battery voltage + current — I2C1 read from INA219 at 1Hz
- `0x34` status flags — computed from local safety loops

### 3.6 Safety loops (critical — act without waiting for Jetson)
- **Watchdog**: timer resets on every I2C command from Jetson. If no command for 500ms → motor stop + set watchdog flag.
- **Cliff**: GPIO interrupt → immediate motor stop + set cliff flag
- **Obstacle**: ultrasonic < 10cm → motor stop + set obstacle flag
- **Tilt**: MPU6050 accel magnitude deviates > 45° from gravity → motor stop + set tilt flag
- **Battery low**: INA219 voltage < 10.2V (3.4V/cell) → set battery_low flag (do not auto-stop — let Jetson decide)

### 3.7 Encoder reading
- RP2350 has PIO state machines — ideal for quadrature encoder decoding
- One PIO SM per motor (2 total), each counts ticks
- Expose tick count in additional registers (e.g., `0x40-0x43` for left, `0x44-0x47` for right)
- This enables PID + odometry on the Jetson side

**Phase 3 acceptance**: Jetson can read every sensor and send motor commands. All safety loops trip appropriately when you set off the condition. Encoders count correctly in both directions.

---

## Phase 4 — Jetson Bring-Up + Camera

### 4.1 Camera
- Connect Waveshare IMX219-160IR via 22→15-pin cable to CAM0 on Jetson
- **Verify cable orientation**: blue tab away from gold contacts on both ends
- Test capture: `nvgstcapture-1.0 --sensor-id=0` should open a preview window
- Or: `gst-launch-1.0 nvarguscamerasrc ! 'video/x-raw(memory:NVMM),width=1920,height=1080,framerate=30/1' ! nvvidconv ! xvimagesink`

### 4.2 Camera API
- Add `GET /api/rover/camera/mjpeg` to PiAssistant — streams MJPEG from `gstreamer` pipeline
- Low-res 640×480 is fine for dashboard, 1080p for Gemma analysis calls
- Feed into dashboard `<img src="/api/rover/camera/mjpeg">`

### 4.3 RoverService un-stub
- Swap the `smbus2` stub for real calls
- Config: `i2c_bus=7` (or whichever bus the jetson-io tool enabled), `pico_address=0x42`
- Health check: attempt to read firmware version from `0xFE`; pass if returns expected value

### 4.4 Systemd service on Jetson
- Copy `deploy/piassistant.service` pattern, adapt for Jetson paths
- `WorkingDirectory=/home/akshay/piassistant`
- `ExecStart=/home/akshay/piassistant/.venv/bin/python -m piassistant`
- Environment pulls from `.env`
- Enable + start + verify via `systemctl status`

**Phase 4 acceptance**: Dashboard served from Jetson shows live camera and real sensor readings from the Pico.

---

## Phase 5 — Software Integration

### 5.1 Un-stub the 11 rover tools
- Replace stub dispatch in `brain/agent.py` with real RoverService calls
- Test each tool through `/api/chat` — e.g. "drive forward for 2 seconds" should result in a `rover_move` tool call

### 5.2 System prompt + keyword filtering
- Update the assistant's system prompt to list rover skills
- Add keyword triggers: "drive", "move", "turn", "forward", "back", "stop", "patrol", "sentry", "camera", "look left/right/up/down", "what do you see"
- Verify via `LLM_BACKEND=local` that a ~2B model picks the right rover tool on realistic user phrasings

### 5.3 Dashboard widget finalization
- Live camera view embedded via MJPEG
- D-pad maps to `rover_move` with fixed 200ms pulses — click-and-release for stop
- Pan-tilt sliders → `rover_look`
- Battery % (derived from INA219 voltage)
- Sensor tiles (distance, tilt, motion, cliff flags)
- Sentry-mode toggle

### 5.4 Integration tests
- pytest against mock rover: verify `/api/chat` "drive forward" → tool call → service call → I2C write
- Manual smoke test via dashboard: every button maps to the right behavior

**Phase 5 acceptance**: End-to-end voice/chat command or dashboard click drives the rover. Dashboard shows real sensor data. Tests pass.

---

## Phase 6 — First Drive → Autonomous

### 6.1 Manual drive
- Put the rover on the floor (or up on blocks for initial tests)
- Drive around via dashboard D-pad
- Fix direction sign errors (if forward drives backward, flip IN1/IN2 on the offending side)
- Tune speed curve — probably want 30-60% PWM for indoor, 100% reserved for carpet climbs
- Test turn-in-place (L forward, R reverse)

### 6.2 Straight-line PID
- Encoder feedback → PID loop in RoverService (or on Pico if latency matters)
- Input: desired (left_speed, right_speed) as ticks/sec
- Target: rover drives 2m forward, drifts <5° from straight
- Tune Kp, Ki, Kd empirically

### 6.3 Odometry
- From encoder ticks + track spacing → position (x, y, θ) in rover-local frame
- Use MPU6050 yaw rate to correct θ drift
- Surface position on dashboard as a small 2D map overlay

### 6.4 Obstacle avoidance verification
- Drive toward a wall — ultrasonic should trigger stop at 10cm
- Drive toward the edge of a table (with a net below) — cliff sensor should trigger stop
- Both already implemented on the Pico; this is integration testing

### 6.5 Sentry mode
- Park rover, camera pan scan every few seconds
- PIR fires → wake camera, grab frame, send to Gemma for "is this a person/pet/package?"
- If person → alert via existing notification flow (dashboard toast + optional TTS)
- Disarm via dashboard toggle or voice command

### 6.6 Patrol mode
- Drive the rover manually via dashboard, press "record waypoint" at each stopping point
- Save as named route: `kitchen`, `front door`, `living room`
- `patrol_start('kitchen')` → rover drives waypoint-to-waypoint using odometry + obstacle avoidance
- Without RPLidar, relies purely on odometry — expect drift over long distances. For initial build, keep routes short and topologically simple.

### 6.7 Voice on rover (audio)
- Wire INMP441 I2S mic to Jetson I2S pins
- Wire MAX98357A amp + speaker to the same I2S bus (different slots)
- Configure ALSA/PipeWire on Jetson for I2S capture + playback
- Extend existing STTService to accept audio from Jetson mic (not just browser)
- "Hey Bunty" wake word while roving → Whisper on Jetson transcribes → chat endpoint → tool dispatch
- TTS responses play out the on-rover speaker (fallback to dashboard speaker if rover audio fails)

**Phase 6 acceptance**: You can tell Bunty "drive to the kitchen" and the rover executes. Sentry mode catches someone walking in. Manual drive works cleanly via voice or dashboard.

---

## Time Estimates

| Phase | Effort | Parallelizable? |
|---|---|---|
| 0 — Groundwork | 1-2 evenings | While hardware ships |
| 1 — Inventory + mechanical | 1 evening | Can start while LiPo ships separately |
| 2 — Power & wiring | 1 evening (if calibration goes clean) | No |
| 3 — Pico firmware | 2-3 weekends | Can start with 0.7 skeleton before hardware |
| 4 — Jetson + camera | 1 weekend | No |
| 5 — Integration | 1 weekend | Most of it done in Phase 0 stubs |
| 6 — First drive → autonomous | Ongoing — manual drive in 1 day, full autonomous 3-5 weekends | No |

**To first manual drive**: 3-4 weekends of concentrated work.
**To full autonomous patrol + voice**: 6-10 weekends.

## Parallelization Strategy

- **Day 0 (today)**: Start Phase 0 software groundwork. Write RoverService stub, tool definitions, dashboard widget skeleton.
- **Hardware arriving over ~1 week**: Continue Phase 0. Bench-test any early arrivals.
- **All hardware arrived**: Phase 1 mechanical assembly → Phase 2 power. Can run Phase 3 Pico firmware on a breadboard in parallel with Phase 2 wiring.
- **Phase 3 + Phase 4 in parallel**: Pico firmware doesn't block Jetson camera setup. Split attention as needed.
- **Phase 5 + Phase 6 interleave**: Integration testing naturally overlaps with first-drive debugging.

---

## Exit Criteria for This Project

The rover is "done" when:
1. Manual drive works from the dashboard and via voice ("Bunty, drive forward")
2. All safety features work (watchdog stops motors on Jetson crash, cliff detection on stairs)
3. Sentry mode catches real motion and alerts
4. Patrol mode executes a recorded route
5. The full test suite (existing 100+ tests plus new rover tests) passes
6. The rover runs for 2+ hours on a charge
7. CLAUDE.md and memory reflect the shipped state, not the planned state

Future upgrades (RPLidar SLAM, 2nd NoIR camera for night vision, additional sensors, audio-on-rover if deferred) can land in follow-up iterations.
