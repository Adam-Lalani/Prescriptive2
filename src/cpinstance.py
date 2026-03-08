from __future__ import annotations

import sys
from typing import Optional, List, Tuple

import numpy as np
from ortools.constraint_solver import pywrapcp



class CPInstance:
    # BUSINESS parameters
    numWeeks: int
    numDays: int
    numEmployees: int
    numShifts: int
    numIntervalsInDay: int
    minDemandDayShift: list[list[int]]
    minDailyOperation: int
    
    # EMPLOYEE parameters
    minConsecutiveWork: int
    maxDailyWork: int
    minWeeklyWork: int
    maxWeeklyWork: int
    maxConsecutiveNightShift: int
    maxTotalNightShift: int

    # Solver
    solver: pywrapcp.Solver

    def __init__(self, filename: str):
        self.load_from_file(filename)
        self.solver = None

    def load_from_file(self, f: str):
        """
        Reads in a file and populates the instance parameters.
        """
        params = {} 
        if not f:
            print("No file provided")
            return
        with open(f, "r") as fl:
            lines = fl.readlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("Business_"):
                    key, value = line.split(":")
                    if key != "Business_minDemandDayShift":
                        params[key] = int(value)
                    else:
                        params[key] = [int(x) for x in value.split()]
                elif line.startswith("Employee_"):
                    key, value = line.split(":")
                    params[key] = int(value)
                
        self.numWeeks = params.get("Business_numWeeks")
        self.numDays = params.get("Business_numDays")
        self.numEmployees = params.get("Business_numEmployees")
        self.numShifts = params.get("Business_numShifts")
        self.numIntervalsInDay = params.get("Business_numIntervalsInDay")
        
        raw = params.get("Business_minDemandDayShift", [])
        self.minDemandDayShift = []
        if raw:
            for i in range(0, self.numDays * self.numShifts, self.numShifts):
                self.minDemandDayShift.append(raw[i : i + self.numShifts])
                
        self.minDailyOperation = params.get("Business_minDailyOperation")
        self.minConsecutiveWork = params.get("Employee_minConsecutiveWork")
        self.maxDailyWork = params.get("Employee_maxDailyWork")
        self.minWeeklyWork = params.get("Employee_minWeeklyWork")
        self.maxWeeklyWork = params.get("Employee_maxWeeklyWork")
        self.maxConsecutiveNightShift = params.get("Employee_maxConsecutiveNigthShift")
        self.maxTotalNightShift = params.get("Employee_maxTotalNigthShift")


    def solve(
        self,
        time_limit_seconds: Optional[float] = None,
    ):
        """
        Employee Scheduling Model
        """
        self.solver = pywrapcp.Solver("EmployeeScheduling")
        solver = self.solver

        E = self.numEmployees
        D = self.numDays
        W = self.numWeeks
        S = self.numShifts

        # ── Decision Variables ──────────────────────────────────────────────
        start = [
            [solver.IntVar(-1, 23, f"start_{e}_{d}") for d in range(D)]
            for e in range(E)
        ]
        end = [
            [solver.IntVar(-1, 24, f"end_{e}_{d}") for d in range(D)]
            for e in range(E)
        ]
        shift = [
            [solver.IntVar(0, S - 1, f"shift_{e}_{d}") for d in range(D)]
            for e in range(E)
        ]
        hours = [
            [solver.IntVar(0, self.maxDailyWork, f"hours_{e}_{d}") for d in range(D)]
            for e in range(E)
        ]

        # ── AllowedAssignments: valid (start, end, shift) tuples ────────────
        # Tighter table: only include tuples where end-start >= minConsecutiveWork
        min_cw = self.minConsecutiveWork
        valid_tuples = [(-1, -1, 0)]
        for s_val in range(0, 8 - min_cw + 1):
            for e_val in range(s_val + min_cw, 9):
                valid_tuples.append((s_val, e_val, 1))
        for s_val in range(8, 16 - min_cw + 1):
            for e_val in range(s_val + min_cw, 17):
                valid_tuples.append((s_val, e_val, 2))
        for s_val in range(16, 24 - min_cw + 1):
            for e_val in range(s_val + min_cw, 25):
                valid_tuples.append((s_val, e_val, 3))

        # ── Linking Constraints ─────────────────────────────────────────────
        is_working = [[None] * D for _ in range(E)]
        is_night = [[None] * D for _ in range(E)]

        for e in range(E):
            for d in range(D):
                solver.Add(solver.AllowedAssignments(
                    [start[e][d], end[e][d], shift[e][d]], valid_tuples))

                solver.Add(hours[e][d] == end[e][d] - start[e][d])

                is_working[e][d] = solver.IsGreaterOrEqualCstVar(shift[e][d], 1)
                is_night[e][d] = solver.IsEqualCstVar(shift[e][d], 1)

        # ── Training: AllDifferent on first 4 days ──────────────────────────
        if D >= 4:
            for e in range(E):
                solver.Add(solver.AllDifferent([shift[e][d] for d in range(4)]))

        # ── Demand: min employees per work shift per day ────────────────────
        for d in range(D):
            for s in range(1, S):
                on_shift = [solver.IsEqualCstVar(shift[e][d], s) for e in range(E)]
                solver.Add(solver.Sum(on_shift) >= self.minDemandDayShift[d][s])

        # ── Demand: min daily operation hours ───────────────────────────────
        for d in range(D):
            solver.Add(
                solver.Sum([hours[e][d] for e in range(E)]) >= self.minDailyOperation
            )

        # ── Contractual: min consecutive work when working ──────────────────
        for e in range(E):
            for d in range(D):
                solver.Add(
                    hours[e][d] >= is_working[e][d] * self.minConsecutiveWork
                )

        # ── Contractual: weekly hours bounds ────────────────────────────────
        for e in range(E):
            for w in range(W):
                week_hours = [hours[e][w * 7 + dd] for dd in range(7) if w * 7 + dd < D]
                solver.Add(solver.Sum(week_hours) >= self.minWeeklyWork)
                solver.Add(solver.Sum(week_hours) <= self.maxWeeklyWork)

        # ── Night shift: no consecutive night shifts ────────────────────────
        for e in range(E):
            for d in range(D - 1):
                solver.Add(
                    is_night[e][d] + is_night[e][d + 1] <= self.maxConsecutiveNightShift
                )

        # ── Night shift: total limit across horizon ─────────────────────────
        for e in range(E):
            solver.Add(
                solver.Sum([is_night[e][d] for d in range(D)]) <= self.maxTotalNightShift
            )

        # ── Search ──────────────────────────────────────────────────────────
        all_vars = []
        for e in range(E):
            for d in range(D):
                all_vars.extend([start[e][d], end[e][d], shift[e][d]])

        db = solver.DefaultPhase(all_vars)
        if time_limit_seconds:
            solver.NewSearch(db, solver.TimeLimit(int(time_limit_seconds * 1000)))
        else:
            solver.NewSearch(db)

        if solver.NextSolution():
            parts = []
            sched = [[None] * D for _ in range(E)]
            for e in range(E):
                for d in range(D):
                    s_val = start[e][d].Value()
                    e_val = end[e][d].Value()
                    parts.append(str(s_val))
                    parts.append(str(e_val))
                    sched[e][d] = (s_val, e_val)
            self.schedule = sched
            sol_string = " ".join(parts)
            solver.EndSearch()
            return True, solver.Failures(), sol_string
        else:
            solver.EndSearch()
            return False, solver.Failures(), None
            

    def prettyPrint(self, numEmployees, numDays, sched):
        """
        Poor man's Gantt chart.
        Displays the employee schedules on the command line. 
        Each row corresponds to a single employee. 
        A "+" refers to a working hour and "." means no work
        The shifts are separated with a "|"
        The days are separated with "||"
        
        This might help you analyze your solutions. 
        
        @param numEmployees the number of employees
        @param numDays the number of days
        @param sched sched[e][d] = (begin, end) hours for employee e on day d
        """
        for e in range(numEmployees):
            print(f"E{e+1}: ", end="")
            if e < 9: print(" ", end="")
            for d in range(numDays):
                begin = sched[e][d][0]
                end = sched[e][d][1]
                for i in range(self.numIntervalsInDay):
                    if i % 8 == 0: print("|", end="")
                    if begin != end and i >= begin and i < end:
                         print("+", end="")
                    else:
                         print(".", end="")
                print("|", end="")
            print(" ")

    def generateVisualizerInput(self, numEmployees, numDays, sched):
        solString = f"{numDays} {numEmployees}\n"
        for d in range(numDays):
            for e in range(numEmployees):
                solString += f"{sched[e][d][0]} {sched[e][d][1]}\n"

        fileName = f"{numDays}_{numEmployees}_sol.txt"
        try:
            with open(fileName, "w") as fl:
                fl.write(solString)
            print(f"File created: {fileName}")
        except IOError as e:
            print(f"An error occured: {e}")
