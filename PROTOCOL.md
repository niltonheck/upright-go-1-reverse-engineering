# Upright GO V.1 — BLE Protocol Reference

The complete GATT map of the Upright GO V.1, with decoded semantics and expected
behaviors for every characteristic. As of the 2026-07-03 hardware sessions,
**every characteristic the device exposes is either fully decoded or explicitly
catalogued with its observed values** — nothing in the map is unaccounted for.

All findings were verified on real hardware (PCB UR-01x, firmware `B 1.1.4`,
iOS client via [react-native-ble-plx](https://github.com/dotintent/react-native-ble-plx))
during the development of
[Open Posture Companion](https://github.com/niltonheck/open-posture-companion),
an open-source replacement for the discontinued official app. Methodology is
described [at the end](#methodology).

> ⚠️ **Read this first — firmware writes brick devices.** The device accepts
> firmware operations without integrity checking; one device was corrupted this
> way during early exploration. Every finding below was obtained with **reads,
> notification subscriptions, and writes only to characteristics whose behavior
> was already documented**. Never write to a characteristic you cannot name,
> and never blanket-write `\x01` across the GATT tree.

---

## Device identification

| Property | Value |
| --- | --- |
| BLE advertised name | `UprightGO` |
| Manufacturer string (`2a29`) | `UpRightPose` |
| Firmware revision (`2a26`) | `B 1.1.4` |
| Hardware revision (`2a27`) | `B0_B1` |
| Model number (`2a24`) | `2` |
| SoC | Texas Instruments CC2540 |
| Accelerometer | BMA250 / LIS2xx / ADXL362 (varies by PCB revision) |
| Battery | 3.7 V single-cell LiPo (115 mAh) |

All vendor characteristics use the Bluetooth base UUID template
`0000XXXX-0000-1000-8000-00805f9b34fb`, where `XXXX` is the short UUID used
throughout this document.

## Full GATT service map

Captured via full service discovery (2026-07-03):

```
service 180a  Device Information (standard)
  2a23 2a24 2a26 2a27 2a29                       [read]
service aaa0  power/charging (partially decoded)
  aaa1 aaa2 aaa3 [read,indicate]  aaa4 [write]  aaa5 [read,write]
service aab0  calibration
  aab1 [write]  aab2 [read,indicate]  aab3 [read,indicate]
service aac0  posture sensing & training state
  aac1 aac2 [read,write]  aac3 [read,indicate]  aac4 [read,notify]
  aac5 [read]  aac6 aac7 [read,write,notify]  aac8 [read,write]
  aac9 aaca [read,notify]
service aad0  outputs & power telemetry
  aad1 aad2 [read,notify]  aad3 aad4 aad6 [write]
service aae0  unknown (suspected firmware/OTA — DO NOT TOUCH)
  aae1 [read]  aae2 aae5 [write]  aae3 [read,notify]  aae4 [read,write,notify]
```

Notable absences:

- **There is no `aad5`** (earlier docs listed it as a blue LED — see
  [Corrections](#corrections-to-earlier-documentation)).
- **There is no standard Battery Service (`180f`)** — battery lives on the
  vendor characteristic `aad2`.
- **There is no `aaa6`** — an early code sample used it for calibration; it was
  a typo for `aab1`.

---

## Decoded characteristics

### Calibration (`aab0`)

#### `aab1` — Calibrate (write)

Write `0x01` to trigger calibration — equivalent to the physical
double-button-press. The device samples **the wearer's posture at that
moment** as the new baseline and acknowledges with a **double vibration**.

Expected behavior after a successful calibration:

- The stored calibration record (`aab3`) is overwritten with the new baseline.
- The calibration flag (`aab2`) reads `0x02`.
- **Training mode arms**: the device vibrates continuously while the wearer's
  forward tilt exceeds *baseline + 12°*, stopping when they straighten.
- The tilt stream (`aaca`) is **not** re-baselined — it stays absolute.

There is no way to write a baseline value directly; the device always samples
the current posture.

#### `aab2` — Calibration state flag (read, indicate)

| Value | Meaning |
| --- | --- |
| `0x00` | Not calibrated — training mode disarmed |
| `0x02` | Calibrated — training mode armed |

Persistence, verified across sessions:

- **Survives BLE disconnect/reconnect** (stays `0x02`, vibration keeps working).
- **Resets to `0x00` on a device power cycle.** Training mode dies with it: a
  freshly powered-on device never vibrates, no matter how hard the wearer
  slouches, until it is calibrated again. Every power-on requires a fresh
  calibration.

#### `aab3` — Stored calibration record (read, indicate)

**Not a live angle** (early docs guessed "raw angle"). Four bytes: two
**big-endian** uint16 values in tenths of a degree:

```
[baseline_hi baseline_lo threshold_hi threshold_lo]
```

Examples observed: `01 52 01 ca` = baseline 338 (33.8°), threshold 458 (45.8°);
`01 9d 02 15` = baseline 413, threshold 533.

- **`threshold = baseline + 120`** (+12.0°) in every observed calibration —
  the device's training-mode threshold is **calibration-relative**, not fixed.
- Persists in **flash across power cycles** — but goes stale: after a power
  cycle `aab2` reads `0x00` while `aab3` still holds the old record. Only
  trust `aab3` when `aab2` reads `0x02`.
- ⚠️ Byte order is the **opposite** of the little-endian `aaca` stream.

### Posture sensing & training state (`aac0`)

#### `aaca` — Continuous tilt stream (notify, read)

**A continuous absolute forward-tilt angle, NOT a status byte.** uint16
**little-endian**, in tenths of a degree, streaming several times per second:

| Reading | Condition |
| --- | --- |
| ~200–450 | Worn, upright (mounting-dependent) |
| rising monotonically | Slouching forward |
| ~800 | Torso near horizontal |
| ~898 | Unworn, dangling |

Values are absolute (not calibration-relative); calibration does not
re-baseline the stream. The old claim that a `0x02` byte here means
"slouching" was a misreading of the little-endian angle payload — the real
status byte is `aac4`.

#### `aac4` — Posture status (notify, read)

The device's own posture state machine — this is where the historical
"`0x02` = slouching" claim actually belongs:

| Value | Meaning |
| --- | --- |
| `0x00` | Upright (below threshold) |
| `0x01` | Slouched past threshold — grace period, not vibrating yet |
| `0x02` | Slouched — vibrating (training mode) |

A **grace period of ~57 s** was observed between crossing the threshold
(`0x01`) and the vibration starting (`0x02`). Requires calibration
(`aab2 = 0x02`) for the `0x01`/`0x02` states to be reachable.

#### `aac3` — Worn sensor (notify, read)

| Value | Meaning |
| --- | --- |
| `0x01` | Being worn |
| `0x00` | Not worn (dangling/handled) |

Bounces between `01`/`00` for under a second while the device is being taken
off, then settles. Useful to gate posture displays — an unworn device still
streams (meaningless) tilt on `aaca`.

#### `aac6` — Button (notify, read)

Toggles between `0x01` and `0x00` on each physical button press (a toggle, not
a momentary press/release pair).

#### `aac7` — Pause mode (notify, read, **write — verified**)

The training pause toggled by a single physical button press:

| Value | Meaning |
| --- | --- |
| `0x01` | Paused — device keeps sensing (tilt stream continues, `aac4` keeps updating) but never vibrates |
| `0x00` | Active — normal training-mode behavior |

**Writing works** (verified 2026-07-03 with a gated null-write → pause →
resume probe): writing `0x01`/`0x00` pauses/resumes exactly like a button
press. Caveat: **the firmware notifies `aac7` on button toggles but does NOT
notify the writer of its own write** — after writing, read back or track the
state locally.

#### `aac9` — Per-minute telemetry summary (notify, read)

A rolling one-minute posture summary, emitted on the device's ~60 s
housekeeping tick (same cadence as `aad2`), **re-emitted even when unchanged**.
Bitfield:

| Bit | Meaning |
| --- | --- |
| bit 7 (`0x80`) | Currently slouched past threshold at tick time |
| bit 6 (`0x40`) | Pause mode active |
| low bits | Count of slouch excursions (threshold crossings) during the preceding interval — counts even while paused, so excursions, not vibrations |

Examples: `0x00` upright/active/quiet minute · `0x40` upright/paused ·
`0xc0` slouched/paused · `0x02` two slouch excursions in the last minute.

Verified tick-by-tick: 1 excursion → `0x01`, 2 → `0x02`. Counter saturation
untested. A read returns the latest tick's value — this is a **rolling
summary, not persistent state** (early sessions misread it as a sticky flag).
Almost certainly the official app's data source for per-minute posture stats:
subscribing to this single byte gives a posture timeline without streaming
`aaca`.

#### Catalogued but undecoded (`aac0` service)

| UUID | Properties | Observed | Notes |
| --- | --- | --- | --- |
| `aac1` | read, write | `03` | constant across sessions |
| `aac2` | read, write | `28 00 0a 1e` (= 40, 0, 10, 30) | constant; smells like config parameters (possibly timing/threshold settings — untested) |
| `aac5` | read | e.g. `8b 0d 07 00` → `23 0f 07 00` | uint32 LE counter, increments steadily — uptime/tick counter |
| `aac8` | read, write | `01` | constant across sessions |

### Outputs & power telemetry (`aad0`)

#### `aad3` — Vibration motor (write)

| Value | Meaning |
| --- | --- |
| `0x01` | Motor on (runs continuously until stopped) |
| `0x00` | Motor off |

**The value space is fully probed** (2026-07-03): the characteristic accepts
**exactly one byte** — multi-byte writes are rejected at the GATT level. Every
single-byte value other than `0x01` is accepted but is a **complete no-op**:
it neither starts the motor nor stops a running one (verified by writing
`0x05`/`0xff` mid-buzz — the motor kept running until an explicit `0x00`).

**There is no pattern, intensity, or duration interface.** The device's
composed patterns (double-buzz calibration ack, continuous training buzz) are
firmware-generated. Client-side patterns must be shaped by timing `0x01`/`0x00`
writes.

#### `aad4` — Red LED (write)

`0x01` on (steady) / `0x00` off. Hardware-confirmed.

#### `aad6` — Green LED (write)

`0x01` on / `0x00` off — but the green LED **blinks while on** (firmware
pattern, not steady). Additionally, the firmware blinks this LED on its own
for a few seconds right after a BLE connection (connection indicator,
independent of writes) — do not use it to infer any app-controllable state.
**This is the characteristic earlier docs mislabeled as a blue LED on `aad5`;
`aad5` does not exist and there is no blue LED.**

#### `aad2` — Battery voltage (notify, read)

uint16 **little-endian**, in **millivolts**. Notifies on the ~60 s
housekeeping tick. Observed range ~3550–4130 mV, matching a single 4.2 V LiPo
cell; the value **jumps upward the moment the charger connects** (e.g.
4037 → 4120 mV). Convert to a percentage with any standard LiPo
open-circuit-voltage curve (≈4.15 V full, ≈3.5 V empty).

This replaces the missing standard Battery Service.

#### `aad1` — Accelerometer vector (notify, read)

Eight bytes = four **little-endian int16** values. The first three move with
device orientation and scale like raw accelerometer axes (~1082 counts ≈ 1 g);
the fourth equals the current `aaca` tilt value. Layout:

```
[accel_x accel_y accel_z tilt_decidegrees]  (int16 LE each)
```

Axis assignment unverified; treat as `[a, b, c, tilt]`.

### Power/charging (`aaa0`)

#### `aaa2` — Charger connected (notify, read)

`0x01` charger connected / `0x00` disconnected. Fires immediately on
plug/unplug. Pair with `aad2` for a full battery display.

#### Catalogued but undecoded (`aaa0` service)

| UUID | Properties | Observed | Notes |
| --- | --- | --- | --- |
| `aaa1` | read, indicate | `03`, `0b`, `0c` across sessions | varies; meaning unknown |
| `aaa3` | read, indicate | `00` | constant |
| `aaa4` | write | — | never written (unknown function) |
| `aaa5` | read, write | `04 00 00` | constant |

### Unknown service (`aae0`) — suspected firmware/OTA

| UUID | Properties | Observed |
| --- | --- | --- |
| `aae1` | read | `16 00 bb 0b` (constant) |
| `aae2`, `aae5` | write | never written |
| `aae3` | read, notify | 20 bytes, all zero |
| `aae4` | read, write, notify | 18 bytes, all zero |

The zero-filled multi-byte read/write/notify characteristics are consistent
with a firmware-update (OTA) data path. **Given the confirmed brick risk, this
service should never be written to.**

### Device Information (`180a`)

Standard service: `2a23` System ID, `2a24` Model Number (`2`), `2a26` Firmware
Revision (`B 1.1.4`), `2a27` Hardware Revision (`B0_B1`), `2a29` Manufacturer
(`UpRightPose`).

---

## Behavior reference

### Calibration lifecycle

1. Fresh power-on: `aab2 = 0x00`, training mode disarmed — **the device never
   vibrates**, regardless of posture. `aab3` still holds the previous (stale)
   record.
2. Write `0x01` to `aab1` while the wearer holds their ideal posture → double
   vibration ack, `aab2 → 0x02`, `aab3 → [baseline, baseline+120]`, training
   mode armed.
3. Training mode: slouch past *baseline + 12°* → `aac4 = 0x01` (grace,
   ~57 s) → `0x02` + continuous vibration until the wearer straightens.
4. BLE disconnects do **not** affect calibration; power cycles reset it
   (step 1).

### Pause/resume

A single physical button press — or a write to `aac7` — toggles pause. While
paused the device senses normally (`aaca`, `aac4`, `aac9` all keep updating)
but never vibrates. Direct motor writes (`aad3`) still work while paused.

### The ~60-second housekeeping tick

`aad2` (battery) and `aac9` (telemetry) both notify on a shared ~60 s cadence,
re-emitting unchanged values. Event-driven characteristics (`aaca`, `aac3`,
`aac4`, `aac6`, `aac7`, `aaa2`) notify on change instead.

### Connection behavior

- The device stops advertising while a BLE connection is held — release
  connections you no longer need, or rescans will never find the device.
- The green LED blinks on its own for a few seconds after a connection is
  established (firmware indicator, not client-controllable).
- On iOS the adapter reports `unknown` briefly after central creation — wait
  for `poweredOn` before scanning.

---

## Corrections to earlier documentation

Findings that **overturn** claims in the original exploration (all
hardware-verified 2026-07-03):

| Old claim | Reality |
| --- | --- |
| `aad5` = blue LED | **`aad5` does not exist.** The second LED is green, on `aad6`, and blinks while on. There is no blue LED. |
| `aaca` ends with `0x02` when slouched | `aaca` is a continuous little-endian tilt angle; a `0x02` byte there is just part of the angle value. The real status byte (`0x00`/`0x01`/`0x02`) is **`aac4`**. |
| `aab3` = raw angle read | `aab3` is the **stored calibration record** (baseline + threshold, big-endian) — not a live reading. |
| Calibration via `aaa6` (code sample) | Typo — `aaa6` does not exist anywhere in the GATT tree. Calibration is `aab1`. |
| Vibration `\x0` "pauses" | `0x00` stops the motor outright; the *pause* concept lives on `aac7`. |

## Methodology

Findings were produced with a deliberately conservative, read-first protocol
(no firmware service was ever touched):

1. **Full GATT discovery** and tree logging on connection.
2. **Read snapshots** of every readable characteristic, diffed across
   controlled state transitions: before/after calibration, across
   BLE-disconnect-only, and across power cycles — this isolated `aab2`/`aab3`
   and the persistence matrix.
3. **Notify monitoring** of every notify/indicate characteristic with
   timestamps during scripted wear sessions (upright → slouch → buzz →
   straighten → remove → button → charger on/off) — this decoded `aac3`,
   `aac4`, `aac7`, `aad2`, `aaa2`, and the 60 s tick.
4. **Controlled tick-by-tick sessions** with one variable changed per ~60 s
   interval — this decoded the `aac9` bitfield (and falsified two earlier
   hypotheses about it along the way).
5. **Bounded write probes** only on already-documented characteristics: a
   value sweep + mid-buzz semantics probe on `aad3`, and a gated null-write →
   pause → resume probe on `aac7`.

The probe implementations are open source in the
[Open Posture Companion dev harness](https://github.com/niltonheck/open-posture-companion).
