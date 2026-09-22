# Storage bay temperature LED policy

The TruePanel TVS-671 controller has independent channels: a flashing-red
identify channel, a steady-red error channel, and a green presence channel.
A temperature warning in the dashboard is not itself a drive failure.

## Thresholds

* Storage-health telemetry retains its existing 45°C advisory threshold.
  This change does **not** change SMART classification or disk-health alerts.
* For a drive whose current persistent warning is **temperature-only**, the
  flashing-red bay indicator activates after two consecutive successful
  storage-health polls at or above 48°C, or immediately at or above 50°C.
  With the default 300-second poll interval, two hot observations span one
  additional poll after the first.
* The temperature-driven flashing indicator clears when an observed drive
  reaches 45°C or lower. At 46–47°C, its previously established state is
  retained to avoid flicker.
* A non-temperature storage warning still uses the flashing-red channel
  without temperature gating. A persistent critical condition and a missing
  drive still use the steady-red error channel.

The implementation examines normalized, effective health snapshots at every
successful storage poll, even if the snapshot produces no new event. This
reconciles thermal LED state without relying on a recovered event, which is
not necessarily generated when the health state remains WARNING.

These values are conservative operator policy choices, **not** a claim about
a drive's certified maximum operating temperature. Verify the specific model's
documentation before changing them. If the drive exceeds its recommended
operating conditions, take appropriate cooling action rather than relying
on an LED threshold alone.

## Configuration

Under `mission_control.storage_health`:

```yaml
bay_leds_enabled: true
bay_led_temperature_on_c: 48
bay_led_temperature_off_c: 45
bay_led_temperature_immediate_c: 50
bay_led_temperature_consecutive_polls: 2
```

The health report and advisory logic remain unchanged. The flashing-red
identify channel is cleared only on unambiguous, fresh, known healthy or
low-temperature observations. Unknown or duplicate physical-bay mappings do
not authorize a clear. Snapshot reconciliation does not clear the steady-red
error channel. Critical errors require the existing explicit recovery event.

Startup safety: `bay_leds_clear_on_start: true` clears the flashing
identify channels only, never steady-red critical-error LEDs. If initial
health-condition emission is disabled, startup clearing is suppressed entirely.
A successful subsequent poll reasserts any observed critical state.

No disk, ZFS, fan, storage configuration, or boot actions are performed by
this policy. Keep changes in development until tests, operator review, and a
separate live deployment/hardware gate have been completed.
