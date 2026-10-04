# Sensor detection accuracy: MEASURED IN SIMULATION

> **All sensor data here is simulated** (scripts/simulate_buses.py, no real hardware). Present these
> numbers as *measured in simulation*, never as field results. Regenerate with
> `.venv/bin/python scripts/simulate_buses.py --eval`.

Setup: the real detectors (`backend/sensor/detect.py`, `backend/sensor/lights.py`) run on simulated night rides over the fixed ground truth `data/demo/sim_world.json`: 5 lines (bus 171, 159, 107, 160; tram 17) x 2 directions x 10 seeds per condition. A detection counts if it is within 20 m (defects) / 25 m (lamps) of a true defect the vehicle drove over. Recall = share of passed defects detected; precision = share of detections that are real. One factor is changed at a time from the baseline (noise x1, normal speed, phone in a random pose, GPS 2.5 m).

| condition | rides | pothole/track defects passed | defect recall | defect precision | broken lamps passed | lamp recall | lamp precision |
|---|---|---|---|---|---|---|---|
| baseline | 100 | 560 | 100.0% | 99.8% | 200 | 97.5% | 100.0% |
| vibration noise x1.5 | 100 | 560 | 100.0% | 76.8% | 200 | 97.5% | 100.0% |
| vibration noise x2 | 100 | 560 | 100.0% | 34.5% | 200 | 97.5% | 100.0% |
| vibration noise x3 | 100 | 560 | 100.0% | 11.4% | 200 | 97.5% | 100.0% |
| slow traffic (speed x0.6) | 100 | 560 | 95.5% | 100.0% | 200 | 96.0% | 100.0% |
| fast (speed x1.3) | 100 | 560 | 100.0% | 98.2% | 200 | 99.0% | 100.0% |
| phone lying flat | 100 | 560 | 100.0% | 99.8% | 200 | 97.5% | 100.0% |
| phone upright (holder/pocket) | 100 | 560 | 100.0% | 99.8% | 200 | 97.5% | 100.0% |
| GPS error 5 m | 100 | 560 | 100.0% | 99.8% | 200 | 79.0% | 94.8% |
| GPS error 10 m | 100 | 560 | 85.7% | 85.6% | 200 | 65.5% | 33.5% |
| hard: noise x2 + slow + GPS 5 m | 100 | 560 | 94.5% | 86.3% | 200 | 79.0% | 95.3% |

Baseline by vehicle type:
- **bus (road potholes)**: recall 100.0%, precision 99.8%
- **tram (track defects)**: recall 100.0%, precision 100.0%

Not measured here: the fusion step (several rides -> one verified incident). In the end-to-end Docker run
of the fleet every ground-truth defect became exactly one incident; that is a single run, not a statistic.
