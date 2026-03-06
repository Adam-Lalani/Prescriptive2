from __future__ import annotations

import sys
from typing import Optional, List, Tuple

from ortools.constraint_solver import pywrapcp
import math



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
        pass
    
        # TODO: your model goes here
        self.solver = pywrapcp.Solver("Scheduler")
        solver = self.solver
        # variables

        starts = [
            [solver.IntVar(-1,24-self.minConsecutiveWork, f"starts:{e}.{d}") for d in range(self.numDays)] 
            for e in range(self.numEmployees)
        ]
        ends = [
            [solver.IntVar(-1,24, f"ends:{e}.{d}") for d in range(self.numDays)] 
            for e in range(self.numEmployees)
        ]
        shifts = [
            [solver.IntVar(0,3, f"shifts:{e}.{d}") for d in range(self.numDays)] 
            for e in range(self.numEmployees)
        ]
        hours = [
            [solver.IntVar(0,self.maxDailyWork, f"hours:{e}.{d}") for d in range(self.numDays)] 
            for e in range(self.numEmployees)
        ]

        # linking variables together

        # link start / end
        # link off days
        # link shifts
        # link hours

        OFF_SHIFT = 0
        NIGHT_SHIFT = 1
        DAY_SHIFT = 2
        EVENING_SHIFT = 3

        allowed = [(0,-1,-1,0)] 

        
        # night
        for start in range(0,9-self.minConsecutiveWork):
            for end in range(start+self.minConsecutiveWork, 9):
                allowed.append((1, start, end, end - start))
        # day
        for start in range(8,17-self.minConsecutiveWork):
            for end in range(start+self.minConsecutiveWork, 17):
                allowed.append((2, start, end, end - start))

        # evening
        for start in range(16,25-self.minConsecutiveWork):
            for end in range(start+self.minConsecutiveWork, 25):
                allowed.append((3, start, end, end - start))
        
        # apply to all employees
        for e in range(self.numEmployees):
            for d in range(self.numDays):
                solver.Add(
                    solver.AllowedAssignments(
                        [shifts[e][d], starts[e][d], ends[e][d], hours[e][d]],
                        allowed
                    )
                )
        
        # add in constraints

        # employee can be only assigned to single shift (covered above)

        # minimum number of employees per shift
        for day in range(self.numDays):
            for shift in range(self.numShifts):
                in_shift = [
                    solver.IsEqualCstVar(shifts[e][day], shift) 
                    for e in range(self.numEmployees)
                ]
                solver.Add(
                    solver.Sum(in_shift) >= self.minDemandDayShift[day][shift]
                )
        
        # minimum number of hours per day
        for day in range(self.numDays):
            day_hours = [
                hours[e][day]
                for e in range(self.numEmployees)
            ]

            solver.Add(
                solver.Sum(day_hours) >= self.minDailyOperation
            )
        
        # first 4 days different shifts reuqirement
        for employee in range(self.numEmployees):
            first_four = [
                shifts[employee][day]
                for day in range(min(4, self.numDays))
            ]
   
            solver.Add(solver.AllDifferent(first_four))
        
        # employees can't work more than maxDailyWork
        for employee in range(self.numEmployees):
            for day in range(self.numDays):
                solver.Add(hours[employee][day] <= self.maxDailyWork)
        
        # employees must work at laest minConsecutiveWork (already taken care of by initial conditions) 
        
            
        # total number of hours an employee works per week must be between minWeeklyWork and maxWeeklyWork
        totalWeeks = math.ceil(self.numDays / 7)
        for employee in range(self.numEmployees):
            for week in range(totalWeeks):
                start_day = week * 7
                end_day = min(start_day + 7, self.numDays)
                week_hours = [
                                hours[employee][day]
                                for day in range(start_day,end_day)
                            ]
                solver.Add(solver.Sum(week_hours) >=self.minWeeklyWork)
                solver.Add(solver.Sum(week_hours) <= self.maxWeeklyWork)

        # employees can only work maxConsecutiveNightShift nights in a row
        for employee in range(self.numEmployees):
            for day in range(0, self.numDays - self.maxConsecutiveNightShift):
                start_day = day
                end_day = start_day + self.maxConsecutiveNightShift + 1

                window = [
                    solver.IsEqualCstVar(shifts[employee][d], NIGHT_SHIFT)
                    for d in range(start_day, end_day)
                ]

                solver.Add(solver.Sum(window) <= self.maxConsecutiveNightShift)

        # employees can only work maxTotalNightShift
        for employee in range(self.numEmployees):
            night_flags = [
                solver.IsEqualCstVar(shifts[employee][day], NIGHT_SHIFT)
                for day in range(self.numDays)
            ]
            solver.Add(solver.Sum(night_flags) <= self.maxTotalNightShift)

        # for e in range(self.numEmployees):
        #     for d in range(self.numDays):
                

        #         shift = shifts[e][d]
        #         start = starts[e][d]
        #         end = ends[e][d]
        #         hour = hours[e][d]

        #         # link start / end
        #         solver.Add((start + hour) == end)
        #         # possibly add in conditions to limit end from being 0,minConsecutiveWork
                
        #         # off days
        #         solver.Add(
        #             solver.AllowedAssignments(
        #                 [shift, start, end, hour],
        #                 [(0,-1,-1,0)]
        #             )
        #         )

        #         # link shifts (enforce only 1 shift)
        #         solver.Add(shift == (start % 8))
        #         solver.Add(shift == (end % 8))

        #         # link hours
        #         solver.Add(hour == (end - start))



        # constraints

        # solve
        # all_vars = [v for row in starts for v in row] + \
        #         [v for row in ends for v in row] + \
        #         [v for row in shifts for v in row] + \
        #         [v for row in hours for v in row]
        
        # db = solver.DefaultPhase(all_vars)
        shift_vars = [v for row in shifts for v in row]
        other_vars = [v for row in starts for v in row] + [v for row in ends for v in row] + [v for row in hours for v in row]
        db1 = solver.Phase(
            shift_vars, solver.CHOOSE_MIN_SIZE_HIGHEST_MAX, solver.ASSIGN_MAX_VALUE
        )
        db2 = solver.Phase(
            other_vars, solver.CHOOSE_MIN_SIZE_LOWEST_MIN, solver.ASSIGN_MIN_VALUE
        )
        db = solver.Compose([db1, db2])
        if time_limit_seconds is not None:
            limit = solver.TimeLimit(int(time_limit_seconds * 1000))
            solver.NewSearch(db, [limit])
        else:
            solver.NewSearch(db)

        if self.solver.NextSolution():
            schedule = [
                [(starts[e][d].Value(), ends[e][d].Value()) for d in range(self.numDays)]
                for e in range(self.numEmployees)
            ]
            return True, self.solver.Failures(), schedule
        else:
            return False, self.solver.Failures(), None

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
