from __future__ import annotations

from typing import Optional
import itertools 


from ortools.constraint_solver import pywrapcp
import math

OFF_SHIFT = 0
NIGHT_SHIFT = 1
DAY_SHIFT = 2
EVENING_SHIFT = 3

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

    def _build_model_and_db(self):
        solver = pywrapcp.Solver("Scheduler")

        shiftOfEmpDay = [
            [solver.IntVar(0,self.numShifts - 1, f"shifts:{e}.{d}") for d in range(self.numDays)] 
            for e in range(self.numEmployees)
        ]
        durationOfEmpDay = [
            [solver.IntVar([0] + list(range(self.minConsecutiveWork, self.maxDailyWork+1)), f"duration:{e}.{d}") for d in range(self.numDays)] 
            for e in range(self.numEmployees)
        ]

        # linking shifts together with duration of work via an AllowedAssignments table.
        # allowed pairs: (OFF_SHIFT, 0) and (working_shift, d) for d in [minConsecutiveWork, maxDailyWork]
        # this handles: off days have 0 hours, working days are bounded by min/max consecutive work,
        # employees can't work more than maxDailyWork, employees must work at least minConsecutiveWork,
        # and each employee is assigned to a single shift per day.
        allowed_shift_dur = [(OFF_SHIFT, 0)]
        for s in [NIGHT_SHIFT, DAY_SHIFT, EVENING_SHIFT]:
            for d in range(self.minConsecutiveWork, self.maxDailyWork + 1):
                allowed_shift_dur.append((s, d))

        for e in range(self.numEmployees):
            for d in range(self.numDays):
                solver.Add(
                    solver.AllowedAssignments(
                        [shiftOfEmpDay[e][d], durationOfEmpDay[e][d]],
                        allowed_shift_dur,
                    )
                )
        
        # minimum number of employees per shift
        work_shifts = [NIGHT_SHIFT, DAY_SHIFT, EVENING_SHIFT]
        card_max = [self.numEmployees] * len(work_shifts)
        for day in range(self.numDays):
            day_shifts = [shiftOfEmpDay[e][day] for e in range(self.numEmployees)]

            card_min = [self.minDemandDayShift[day][shift] for shift in work_shifts]
            solver.Add(solver.Distribute(day_shifts, work_shifts, card_min, card_max))
        
        # minimum number of hours per day
        for day in range(self.numDays):
            day_hours = [durationOfEmpDay[e][day] for e in range(self.numEmployees)]
            solver.Add(solver.Sum(day_hours) >= self.minDailyOperation)

        # first 4 days different shifts requirement 
        training_days = min(4, self.numDays)
        perm_var = None
        # use perm first when we're dealing with bigger variables
        use_perm_first = (
            training_days == 4
            and self.numShifts == 4
            and self.numEmployees >= 50
            and self.numDays >= 25
        )

        if use_perm_first:
            PERM_TABLE = list(itertools.permutations([0, 1, 2, 3]))
            # TRAIN_DAY_VALUES[0] = all day 0 values across the 24 permutations
            # TRAIN_DAY_VALUES[1] = all day 1 values ...
            # etc
            TRAIN_DAY_VALUES = [
                [perm[d] for perm in PERM_TABLE]
                for d in range(4)
            ]

            # variable to represent which permutation of the first 4 days an employee is
            perm_var = [
                solver.IntVar(0, len(PERM_TABLE) - 1, f"perm:{e}")
                for e in range(self.numEmployees)
            ]
            for e in range(self.numEmployees):
                for d in range(4):
                     # assigning the specific shift that an employee has based on the permutation variation they have selected
                    solver.Add(shiftOfEmpDay[e][d] == solver.Element(TRAIN_DAY_VALUES[d], perm_var[e]))
        else:
            for e in range(self.numEmployees):
                solver.Add(
                    solver.AllDifferent([shiftOfEmpDay[e][d] for d in range(training_days)])
                )
        
        # total number of hours an employee works per week must be between minWeeklyWork and maxWeeklyWork
        for employee in range(self.numEmployees):
            for week in range(self.numWeeks):
                start_day = week * 7
                end_day = min(start_day + 7, self.numDays)

                week_hours = [durationOfEmpDay[employee][d] for d in range(start_day,end_day)]
                total_week_hours = solver.Sum(week_hours)

                solver.Add(total_week_hours >= self.minWeeklyWork)
                solver.Add(total_week_hours <= self.maxWeeklyWork)

        # employees can only work maxConsecutiveNightShift nights in a row
        # only need to check 4th and 5th element (specialized for this assignment)
        if self.numDays >= 5:
            for e in range(self.numEmployees):
                solver.Add(
                    solver.IsEqualCstVar(shiftOfEmpDay[e][3], NIGHT_SHIFT) +
                    solver.IsEqualCstVar(shiftOfEmpDay[e][4], NIGHT_SHIFT)
                    <= self.maxConsecutiveNightShift
                )

        # employees can only work maxTotalNightShift
        for employee in range(self.numEmployees):
            night_count = solver.IntVar(0, self.numDays, f"night_count:{employee}")
            solver.Add(solver.Count(shiftOfEmpDay[employee], NIGHT_SHIFT, night_count))
            solver.Add(night_count <= self.maxTotalNightShift)
        
        # HELPER CONSTRAINTS (redundant)
                
        # reduces symmetry redundancy (excpet in the case where two shifts are 'equal')
        for e in range(self.numEmployees - 1):
            solver.Add(solver.LexicalLessOrEqual(
                shiftOfEmpDay[e],
                shiftOfEmpDay[e + 1]
            ))

        # solve
        shift_vars = [
            shiftOfEmpDay[e][d]
            for d in range(self.numDays)
            for e in range(self.numEmployees)
        ]
        duration_vars = [
            durationOfEmpDay[e][d]
            for d in range(self.numDays)
            for e in range(self.numEmployees)
        ]

        phases = []
        if perm_var is not None:
            phases.append(
                solver.Phase(
                    perm_var,
                    solver.CHOOSE_FIRST_UNBOUND,
                    solver.ASSIGN_MIN_VALUE,
                )
            )

        phases.append(
            solver.Phase(
                shift_vars,
                solver.CHOOSE_FIRST_UNBOUND,
                solver.ASSIGN_MAX_VALUE,
            )
        )
        phases.append(
            solver.Phase(
                duration_vars,
                solver.CHOOSE_MIN_SIZE_LOWEST_MIN,
                solver.ASSIGN_MIN_VALUE,
            )
        )

        db = solver.Compose(phases)
        vars_dict = {
            "shift": shiftOfEmpDay,
            "duration": durationOfEmpDay,
        }
        if perm_var is not None:
            vars_dict["perm"] = perm_var
        return solver, db, vars_dict


    def solve(
        self,
        time_limit_seconds: Optional[float] = None,
    ):
        """
        Employee Scheduling Model 
        """
        solver, db, vars_dict = self._build_model_and_db()
        self.solver = solver

        if time_limit_seconds is not None:
            limit = solver.TimeLimit(int(time_limit_seconds * 1000))
            solver.NewSearch(db, [limit])
        else:
            solver.NewSearch(db)

        if self.solver.NextSolution():
            schedule = [
                [(self.shift_to_interval(vars_dict["shift"][e][d].Value(), vars_dict["duration"][e][d].Value())) for d in range(self.numDays)]
                for e in range(self.numEmployees)
            ]
            return True, self.solver.Failures(), schedule
        else:
            return False, self.solver.Failures(), None

    def enumerate_solution_strings(self, max_solutions: int = 200000) -> set[str]:
        solver, db, vars_dict = self._build_model_and_db()
        out = set()
        solver.NewSearch(db)
        try:
            while solver.NextSolution():
                parts = []
                for e in range(self.numEmployees):
                    for d in range(self.numDays):
                        begin, end = self.shift_to_interval(
                            vars_dict["shift"][e][d].Value(),
                            vars_dict["duration"][e][d].Value(),
                        )
                        parts.append(str(begin))
                        parts.append(str(end))
                out.add(" ".join(parts))
                if len(out) >= max_solutions:
                    raise RuntimeError(f"Hit max_solutions={max_solutions}; increase it.")
        finally:
            solver.EndSearch()
        return out

    def shift_to_interval(self,shift, duration):
        if shift == OFF_SHIFT:
            return (-1, -1)
        if shift == NIGHT_SHIFT:
            return (0, duration)
        if shift == DAY_SHIFT:
            return (8, 8 + duration)
        if shift == EVENING_SHIFT:
            return (16, 16 + duration)
        raise ValueError(f"Unknown shift: {shift}")
            
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
