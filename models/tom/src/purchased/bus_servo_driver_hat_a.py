"""Purchased bus servo driver hat a; dimensions preserved from supplied/catalog STEP."""
from pathlib import Path
from cadgen import read_step
from lib.imported_step_labels import decoded_labels
INPUT = Path(__file__).resolve().parents[2] / 'STEP/imported/electronics/bus_servo_driver_hat_a.step'

def bus_servo_driver_hat_a():
    return decoded_labels(read_step(INPUT))
