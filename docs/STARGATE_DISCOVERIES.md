# Project Stargate Discoveries

This document records experimentally verified observations about the QNAP
A125 front panel controller.

Only repeatable results produced by documented laboratory procedures should
be recorded here.

---

# Discovery 001

## Display Transmission Scaling

**Date**

2026-07-14

**Laboratory**

Display Timing Laboratory

**Experiment**

Measured host-side transmission latency while varying only the display
payload length. All measurements used documented write commands over the
standard 1200 baud serial interface.

Median latency was used to eliminate occasional operating-system scheduling
outliers.

### Results

| Payload (bytes) | Median Latency |
|---------------:|---------------:|
| 0 | 37.893 ms |
| 1 | 45.891 ms |
| 2 | 53.892 ms |
| 4 | 69.897 ms |
| 8 | 101.897 ms |
| 12 | 133.903 ms |
| 16 | 169.890 ms |

### Model

Latency ≈ 37.9 ms + (8.3 ms × payload bytes)

### Interpretation

Display transmission latency scales almost perfectly linearly with payload
length.

The measured per-byte transmission time closely matches the theoretical
transmission time of one byte over a 1200 baud serial connection.

No measurable nonlinear controller processing delay was observed during the
experiment.

### Confidence

★★★★★

Verified across multiple repeated laboratory runs.

### Evidence

- Display Timing Laboratory
- Payload Scaling Laboratory
- 175 successful documented write operations
- Median timing analysis
