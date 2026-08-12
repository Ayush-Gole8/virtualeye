#!/usr/bin/env python3
"""
Telemetry analysis for the naive-vs-priority user study.

Reads one or more study_logs/*.jsonl files and produces summary stats:
- total words spoken (cognitive load proxy)
- announcement count
- latency percentiles (50th, 95th, 99th)
- path-clear vs obstacle ratio

Usage:
    python analyze_study.py study_logs/naive_trial1.jsonl study_logs/priority_trial1.jsonl
    python analyze_study.py study_logs/*.jsonl  (all sessions)

Output is a Markdown table ready to paste into the 40-day report.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
import glob

def load_session(path):
    """Load a JSONL telemetry file into a list of frame records."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def analyze(records):
    """Compute summary stats from a list of frame records."""
    if not records:
        return {
            "frames": 0, "words": 0, "announcements": 0,
            "lat_p50": 0, "lat_p95": 0, "lat_p99": 0,
            "path_clear_pct": 0,
        }

    total_words = sum(r.get("words", 0) for r in records)
    announcements = sum(1 for r in records if r.get("speech") and r["speech"].strip())
    latencies = [r["latency_ms"] for r in records if "latency_ms" in r]
    latencies.sort()

    def percentile(data, p):
        if not data:
            return 0
        idx = int(len(data) * p / 100.0)
        return data[min(idx, len(data) - 1)]

    path_records = [r for r in records if "path" in r and r["path"]]
    path_clear_count = sum(1 for r in path_records if r["path"].get("clear"))
    path_clear_pct = (100.0 * path_clear_count / len(path_records)
                      if path_records else 0)

    return {
        "frames": len(records),
        "words": total_words,
        "announcements": announcements,
        "lat_p50": percentile(latencies, 50),
        "lat_p95": percentile(latencies, 95),
        "lat_p99": percentile(latencies, 99),
        "path_clear_pct": path_clear_pct,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_study.py study_logs/*.jsonl")
        print("Reads telemetry logs and outputs summary table.")
        sys.exit(1)

    paths = sorted(Path(p) for argv in sys.argv[1:]
               for p in glob.glob(argv))
    by_mode = defaultdict(list)

    for path in paths:
        records = load_session(path)
        if not records:
            print(f"Warning: {path} is empty, skipping.", file=sys.stderr)
            continue
        mode = records[0].get("mode", "unknown")
        by_mode[mode].extend(records)

    print("# User Study Telemetry Summary\n")
    print("| Mode     | Frames | Words Spoken | Announcements | Latency p50 (ms) | Latency p95 (ms) | Path Clear (%) |")
    print("|----------|--------|--------------|---------------|------------------|------------------|----------------|")

    for mode in sorted(by_mode.keys()):
        stats = analyze(by_mode[mode])
        print(f"| {mode:8s} | {stats['frames']:6d} | {stats['words']:12d} | "
              f"{stats['announcements']:13d} | {stats['lat_p50']:16.0f} | "
              f"{stats['lat_p95']:16.0f} | {stats['path_clear_pct']:14.1f} |")

    # Comparison line
    if "naive" in by_mode and "priority" in by_mode:
        n_stats = analyze(by_mode["naive"])
        p_stats = analyze(by_mode["priority"])
        word_reduction = (100.0 * (n_stats["words"] - p_stats["words"]) / n_stats["words"]
                          if n_stats["words"] > 0 else 0)
        print(f"\n**Priority mode reduced spoken words by {word_reduction:.1f}%** "
              f"({n_stats['words']} → {p_stats['words']}).")


if __name__ == "__main__":
    main()
