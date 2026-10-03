# Sensor detection accuracy: MEASURED IN SIMULATION

> **All sensor data here is simulated** (scripts/simulate_buses.py, no real hardware). Present these
> numbers as *measured in simulation*, never as field results. Regenerate with
> `.venv/bin/python scripts/simulate_buses.py --eval`.

Setup: the real detectors (`backend/sensor/detect.py`, `backend/sensor/lights.py`) run on simulated night rides over the fixed ground truth `data/demo/sim_world.json`: 4 lines (bus MAR, JER, SWI; tram 17) x 2 directions x 10 seeds per condition. A detection counts if it is within 20 m (defects) / 25 m (lamps) of a true defect the vehicle drove over. Recall = share of passed defects detected; precision = share of detections that are real. One factor is changed at a time from the baseline (noise x1, normal speed, phone in a random pose, GPS 2.5 m).

| condition | rides | pothole/track defects passed | defect recall | defect precision | broken lamps passed | lamp recall | lamp precision |
|---|---|---|---|---|---|---|---|
| baseline | 80 | 380 | 100.0% | 100.0% | 180 | 98.3% | 100.0% |
| vibration noise x1.5 | 80 | 380 | 100.0% | 100.0% | 180 | 98.3% | 100.0% |
| vibration noise x2 | 80 | 380 | 100.0% | 90.7% | 180 | 98.3% | 100.0% |
| vibration noise x3 | 80 | 380 | 100.0% | 14.1% | 180 | 98.3% | 100.0% |
| slow traffic (speed x0.6) | 80 | 380 | 94.2% | 100.0% | 180 | 96.1% | 100.0% |
| fast (speed x1.3) | 80 | 380 | 100.0% | 100.0% | 180 | 98.9% | 100.0% |
| phone lying flat | 80 | 380 | 100.0% | 100.0% | 180 | 98.3% | 100.0% |
| phone upright (holder/pocket) | 80 | 380 | 100.0% | 100.0% | 180 | 98.3% | 100.0% |
| GPS error 5 m | 80 | 380 | 100.0% | 100.0% | 180 | 83.9% | 96.3% |
| GPS error 10 m | 80 | 380 | 88.4% | 88.4% | 180 | 60.6% | 50.8% |
| hard: noise x2 + slow + GPS 5 m | 80 | 380 | 92.6% | 100.0% | 180 | 76.1% | 93.4% |

Baseline by vehicle type:
- **bus (road potholes)**: recall 100.0%, precision 100.0%
- **tram (track defects)**: recall 100.0%, precision 100.0%

Not measured here: the fusion step (several rides -> one verified incident). In the end-to-end Docker run
of the fleet every ground-truth defect became exactly one incident; that is a single run, not a statistic.
