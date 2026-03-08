#!/usr/bin/env python3
from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpinstance import CPInstance


def shift_to_interval(shift: int, hours: int, width: int) -> tuple[int, int]:
    if shift == 0:
        return -1, -1
    start = (shift - 1) * width
    return start, start + hours


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Brute-force all valid schedules for 1 employee and write solution lines."
    )
    parser.add_argument(
        "instance_file",
        nargs="?",
        default="src/verifier/one_emp_7d.sched",
        help="Path to .sched instance (must have exactly 1 employee).",
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        default="src/verifier/one_emp_7d_result.sched",
        help="Path to output brute-force solutions file.",
    )
    args = parser.parse_args()

    inst = CPInstance(args.instance_file)
    if inst.numEmployees != 1:
        raise ValueError(f"This script only supports 1 employee, got {inst.numEmployees}.")
    if (inst.numShifts - 1) <= 0 or inst.numIntervalsInDay % (inst.numShifts - 1) != 0:
        raise ValueError("Bad shift structure: numIntervalsInDay must be divisible by (numShifts - 1).")
    if inst.minConsecutiveWork != inst.maxDailyWork:
        raise ValueError(
            "This script assumes fixed daily work hours (minConsecutiveWork == maxDailyWork)."
        )

    width = inst.numIntervalsInDay // (inst.numShifts - 1)
    fixed_hours = inst.minConsecutiveWork

    sols: list[str] = []
    for shifts in product(range(inst.numShifts), repeat=inst.numDays):
        t_days = min(4, inst.numDays)
        if len(set(shifts[:t_days])) != t_days:
            continue

        # weekly min / max
        workdays = sum(1 for s in shifts if s != 0)
        weekly_hours = fixed_hours * workdays
        if not (inst.minWeeklyWork <= weekly_hours <= inst.maxWeeklyWork):
            continue

        # max total night shifts
        total_nights = sum(1 for s in shifts if s == 1)
        if total_nights > inst.maxTotalNightShift:
            continue

        # max consecutive night shifts
        k = inst.maxConsecutiveNightShift
        if k is not None and k >= 0 and inst.numDays > k:
            bad = False
            for st in range(0, inst.numDays - k):
                win_nights = sum(1 for d in range(st, st + k + 1) if shifts[d] == 1)
                if win_nights > k:
                    bad = True
                    break
            if bad:
                continue
        
        # min daily hours + min shift per day
        ok = True
        for d in range(inst.numDays):
            counts = [0 for _ in range(inst.numShifts)]
            counts[shifts[d]] += 1
            if any(counts[s] < inst.minDemandDayShift[d][s] for s in range(inst.numShifts)):
                ok = False
                break
            day_hours = fixed_hours if shifts[d] != 0 else 0
            if day_hours < inst.minDailyOperation:
                ok = False
                break
        if not ok:
            continue

        parts: list[str] = []
        for d in range(inst.numDays):
            b, e = shift_to_interval(shifts[d], fixed_hours, width)
            parts.extend([str(b), str(e)])
        sols.append(" ".join(parts))

    sols = sorted(set(sols))
    Path(args.output_file).write_text("\n".join(sols) + ("\n" if sols else ""))
    print(f"wrote {len(sols)} solutions to {args.output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
