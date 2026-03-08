#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1])) 
from cpinstance import CPInstance

def canonical_solution_line(line: str) -> str:
    s = line.strip()
    if not s or s.startswith("#"):
        return ""
    if s.startswith("{"):
        obj = json.loads(s)
        s = str(obj.get("Solution", "")).strip()
    return " ".join(s.split())


def read_brutefile(path: str) -> set[str]:
    sols = set()
    for raw in Path(path).read_text().splitlines():
        c = canonical_solution_line(raw)
        if c:
            sols.add(c)
    return sols


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "instance_file",
        nargs="?",
        default="src/verifier/one_emp_7d.sched",
        type=str,
    )
    parser.add_argument(
        "brutefile",
        nargs="?",
        default="src/verifier/one_emp_7d_result.sched",
        type=str,
    )
    parser.add_argument("--max-solutions", type=int, default=200000)
    parser.add_argument("--show-diff", type=int, default=20)
    args = parser.parse_args()

    instance = CPInstance(args.instance_file)
    solver_set = instance.enumerate_solution_strings(args.max_solutions)
    brute_set = read_brutefile(args.brutefile)

    only_solver = sorted(solver_set - brute_set)
    only_brute = sorted(brute_set - solver_set)

    print(f"solver_solutions={len(solver_set)}")
    print(f"brutefile_solutions={len(brute_set)}")
    print(f"only_in_solver={len(only_solver)}")
    print(f"only_in_brutefile={len(only_brute)}")

    if only_solver:
        print("\nExamples only in solver:")
        for s in only_solver[: args.show_diff]:
            print(s)

    if only_brute:
        print("\nExamples only in brutefile:")
        for s in only_brute[: args.show_diff]:
            print(s)

    if not only_solver and not only_brute:
        print("\nMATCH")
        return 0
    print("\nMISMATCH")
    return 1


if __name__ == "__main__":
    sys.exit(main())
