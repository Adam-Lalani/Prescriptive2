#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Tuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1])) 
from cpinstance import CPInstance

OFF_SHIFT = 0
NIGHT_SHIFT = 1


def get_shift_bounds(instance: CPInstance) -> dict[int, tuple[int, int]]:
    work_shifts = instance.numShifts - 1
    if work_shifts <= 0:
        raise ValueError("numShifts must be at least 2 (off + at least one work shift).")
    if instance.numIntervalsInDay % work_shifts != 0:
        raise ValueError(
            f"numIntervalsInDay={instance.numIntervalsInDay} must be divisible by "
            f"(numShifts-1)={work_shifts}."
        )

    width = instance.numIntervalsInDay // work_shifts
    bounds: dict[int, tuple[int, int]] = {}
    for s in range(1, instance.numShifts):
        lo = (s - 1) * width
        hi = s * width
        bounds[s] = (lo, hi)
    return bounds


def decode_interval(
    begin: int,
    end: int,
    instance: CPInstance,
    shift_bounds: dict[int, tuple[int, int]],
) -> tuple[int | None, int | None, str | None]:
    if begin == -1 and end == -1:
        return OFF_SHIFT, 0, None

    if begin == -1 or end == -1:
        return None, None, f"invalid off encoding ({begin}, {end}); off must be (-1, -1)"
    if begin < 0 or end < 0:
        return None, None, f"negative time(s): ({begin}, {end})"
    if end <= begin:
        return None, None, f"end must be > begin: ({begin}, {end})"
    if end > instance.numIntervalsInDay:
        return None, None, f"end {end} exceeds numIntervalsInDay={instance.numIntervalsInDay}"

    for shift, (lo, hi) in shift_bounds.items():
        if lo <= begin < hi and end <= hi:
            return shift, end - begin, None

    return None, None, f"interval crosses shift boundary: ({begin}, {end})"


def extract_solution_string(line: str) -> str:
    line = line.strip()
    if not line:
        raise ValueError("Selected line is empty.")

    if line.startswith("{"):
        obj = json.loads(line)
        if "Solution" not in obj:
            raise ValueError("JSON line does not have a 'Solution' field.")
        return str(obj["Solution"]).strip()

    return line


def read_solution_line(solution_file: str, solution_line: int) -> str:
    with open(solution_file, "r") as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]

    if not lines:
        raise ValueError(f"No non-empty lines in {solution_file}")

    idx = solution_line if solution_line >= 0 else len(lines) + solution_line
    if idx < 0 or idx >= len(lines):
        raise ValueError(
            f"--solution-line {solution_line} out of range; file has {len(lines)} non-empty lines."
        )

    return extract_solution_string(lines[idx])


def solution_to_schedule(
    solution_str: str,
    num_employees: int,
    num_days: int,
) -> List[List[Tuple[int, int]]]:
    vals = [int(x) for x in solution_str.split()] if solution_str.strip() else []
    expected = 2 * num_employees * num_days
    if len(vals) != expected:
        raise ValueError(
            f"Solution has {len(vals)} ints, expected {expected} "
            f"(2 * {num_employees} employees * {num_days} days)."
        )

    sched: List[List[Tuple[int, int]]] = []
    k = 0
    for _e in range(num_employees):
        row = []
        for _d in range(num_days):
            row.append((vals[k], vals[k + 1]))
            k += 2
        sched.append(row)
    return sched


def validate_schedule(instance: CPInstance, schedule: List[List[Tuple[int, int]]]) -> list[str]:
    errors: list[str] = []
    E = instance.numEmployees
    D = instance.numDays
    shift_bounds = get_shift_bounds(instance)

    if len(schedule) != E:
        errors.append(f"employee row count mismatch: got {len(schedule)}, expected {E}")
        return errors
    for e in range(E):
        if len(schedule[e]) != D:
            errors.append(
                f"day count mismatch for employee {e}: got {len(schedule[e])}, expected {D}"
            )
            return errors

    shifts = [[None for _ in range(D)] for _ in range(E)]
    hours = [[0 for _ in range(D)] for _ in range(E)]

    # decode + per-day duration bounds
    for e in range(E):
        for d in range(D):
            b, en = schedule[e][d]
            s, h, err = decode_interval(b, en, instance, shift_bounds)
            if err is not None:
                errors.append(f"[e={e}, d={d}] {err}")
                continue

            shifts[e][d] = s
            hours[e][d] = h if h is not None else 0

            if s != OFF_SHIFT:
                if h < instance.minConsecutiveWork:
                    errors.append(
                        f"[e={e}, d={d}] minConsecutiveWork violated: {h} < {instance.minConsecutiveWork}"
                    )
                if h > instance.maxDailyWork:
                    errors.append(
                        f"[e={e}, d={d}] maxDailyWork violated: {h} > {instance.maxDailyWork}"
                    )

    # daily shift demand + min daily operation
    for d in range(D):
        counts = [0 for _ in range(instance.numShifts)]
        total_h = 0
        for e in range(E):
            s = shifts[e][d]
            if s is None:
                continue
            counts[s] += 1
            total_h += hours[e][d]

        for s in range(instance.numShifts):
            need = instance.minDemandDayShift[d][s]
            have = counts[s]
            if have < need:
                errors.append(
                    f"[day={d}, shift={s}] minDemandDayShift violated: have {have}, need {need}"
                )

        if total_h < instance.minDailyOperation:
            errors.append(
                f"[day={d}] minDailyOperation violated: have {total_h}, need {instance.minDailyOperation}"
            )

    # first 4 days all different shifts per employee
    t_days = min(4, D)
    for e in range(E):
        seen = set()
        for d in range(t_days):
            s = shifts[e][d]
            if s in seen:
                errors.append(
                    f"[e={e}] training requirement violated in first {t_days} days: repeated shift {s}"
                )
                break
            seen.add(s)

    # weekly min/max hours
    for e in range(E):
        for w in range(instance.numWeeks):
            st = 7 * w
            if st >= D:
                break
            en = min(st + 7, D)
            wh = sum(hours[e][d] for d in range(st, en))
            if wh < instance.minWeeklyWork:
                errors.append(
                    f"[e={e}, week={w}] minWeeklyWork violated: have {wh}, need {instance.minWeeklyWork}"
                )
            if wh > instance.maxWeeklyWork:
                errors.append(
                    f"[e={e}, week={w}] maxWeeklyWork violated: have {wh}, max {instance.maxWeeklyWork}"
                )

    # night constraints
    k = instance.maxConsecutiveNightShift
    for e in range(E):
        total_nights = sum(1 for d in range(D) if shifts[e][d] == NIGHT_SHIFT)
        if total_nights > instance.maxTotalNightShift:
            errors.append(
                f"[e={e}] maxTotalNightShift violated: have {total_nights}, max {instance.maxTotalNightShift}"
            )

        if k is not None and k >= 0 and D > k:
            for st in range(0, D - k):
                win_nights = sum(
                    1 for d in range(st, st + k + 1) if shifts[e][d] == NIGHT_SHIFT
                )
                if win_nights > k:
                    errors.append(
                        f"[e={e}] maxConsecutiveNightShift violated on days {st}..{st+k}: "
                        f"nights={win_nights}, max={k}"
                    )
                    break

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a schedule from a solution file against one instance."
    )
    parser.add_argument("instance_file", type=str, help="Path to .sched instance file")
    parser.add_argument("solution_file", type=str, nargs="?", default="src/verifier/temp_solution", help="Path to file containing solution output")
    parser.add_argument(
        "--solution-line",
        type=int,
        default=-1,
        help="Which non-empty line to read from solution_file (default: -1, last line)",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=100,
        help="Max number of violations to print",
    )
    args = parser.parse_args()

    instance = CPInstance(args.instance_file)
    solution_str = read_solution_line(args.solution_file, args.solution_line)
    schedule = solution_to_schedule(solution_str, instance.numEmployees, instance.numDays)

    errors = validate_schedule(instance, schedule)
    if errors:
        print(f"INVALID: {len(errors)} violation(s)")
        show = min(len(errors), args.max_errors)
        for i in range(show):
            print(f"{i + 1}. {errors[i]}")
        if len(errors) > show:
            print(f"... and {len(errors) - show} more")
        return 1

    print("VALID: schedule satisfies all checked constraints.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
