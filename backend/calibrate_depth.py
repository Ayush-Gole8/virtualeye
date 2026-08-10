#!/usr/bin/env python3
"""
Linear calibration helper for metric depth.

Instructions:
1. Place a recognizable object (chair, person, box) at known distances: 1m, 2m, 3m.
   Use a tape measure from the camera to the front of the object.
2. Run the smoke test or server and note the *predicted* distance for each placement.
3. Record the pairs here in MEASUREMENTS (actual_m, predicted_m).
4. Run this script: it will fit a linear correction `actual = scale * pred + bias`
   and write the coefficients to depth_calibration.json.
5. In engine/depth.py, load that JSON and apply the correction in
   object_distance_from_depth() after the percentile step.

Example measurements (replace with your real tape-test data):
"""

import numpy as np
import json

# (actual_metres, predicted_metres) — add your tape-measured pairs here
MEASUREMENTS = [
    (1.0, 1.15),   # object at 1m, model said 1.15m
    (2.0, 2.30),   # object at 2m, model said 2.30m
    (3.0, 3.20),   # object at 3m, model said 3.20m
    # Add more pairs for better fit
]


def fit_linear(pairs):
    """Fit actual = scale * pred + bias using least squares."""
    preds = np.array([p for (_, p) in pairs])
    actuals = np.array([a for (a, _) in pairs])
    # polyfit(x, y, deg=1) returns [slope, intercept]
    coeffs = np.polyfit(preds, actuals, 1)
    scale, bias = coeffs[0], coeffs[1]
    return scale, bias


def main():
    if len(MEASUREMENTS) < 2:
        print("Error: need at least 2 (actual, predicted) pairs. "
              "Edit MEASUREMENTS in this script after doing the tape test.")
        return

    scale, bias = fit_linear(MEASUREMENTS)
    print(f"Linear calibration fit:")
    print(f"  actual = {scale:.4f} * predicted + {bias:.4f}")
    print()

    # Show before/after for each measurement
    print("Measurement check (before -> after):")
    for actual, pred in MEASUREMENTS:
        corrected = scale * pred + bias
        err_before = abs(pred - actual)
        err_after = abs(corrected - actual)
        print(f"  {actual:.1f}m actual: {pred:.2f}m -> {corrected:.2f}m  "
              f"(error {err_before:.2f}m -> {err_after:.2f}m)")

    # Write to JSON
    calib = {"scale": float(scale), "bias": float(bias)}
    with open("depth_calibration.json", "w") as f:
        json.dump(calib, f, indent=2)

    print("\nWrote depth_calibration.json")
    print("Next: load this in engine/depth.py and apply in object_distance_from_depth():")
    print()
    print("    import json")
    print("    with open('depth_calibration.json') as f:")
    print("        _calib = json.load(f)")
    print("    dist = float(np.median(patch))")
    print("    dist = _calib['scale'] * dist + _calib['bias']  # <-- calibration")
    print("    return max(0.2, min(dist, 20.0))")


if __name__ == "__main__":
    main()
