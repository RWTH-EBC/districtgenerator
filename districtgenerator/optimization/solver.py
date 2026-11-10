# -*- coding: utf-8 -*-
"""
This script provides functions to create a Pyomo solver instance based on a given configuration,
execute the optimization, and diagnose issues if the solver does not terminate with an optimal solution.
"""
import os
import pyomo.environ as pyo
from contextlib import redirect_stdout
from datetime import datetime

from pyomo.environ import SolverFactory
from districtgenerator.config.settings import PyomoConfig

# --- Global constants for solver ---
SUPPORTED_SOLVERS = ['gurobi', 'cbc', 'glpk', 'highs', 'scip']
OPTION_MAP = {
    # Time limit in seconds
    'time_limit': {
        'gurobi': 'TimeLimit',
        'highs': 'time_limit',
        'glpk': 'tmlim',
        'cbc': 'sec',
        'scip': 'limits/time',
    },
    # Relative MIP gap (e.g. 0.01 for 1%)
    'mip_gap': {
        'gurobi': 'MIPGap',
        'highs': 'mip_rel_gap',
        'glpk': 'mipgap',
        'cbc': 'ratio',
        'scip': 'limits/gap',
    },
    # Absolute MIP gap
    'mip_gap_abs': {
        'gurobi': 'MIPGapAbs',
        'highs': 'mip_abs_gap',
        'glpk': None,  # GLPK does not support a direct absolute gap
        'cbc': 'allowableGap',
        'scip': 'limits/absgap',
    },
    # Number of CPU threads to use
    'threads': {
        'gurobi': 'Threads',
        'highs': 'threads',
        'glpk': None,  # GLPK is single-threaded
        'cbc': 'threads',
        'scip': 'lp/threads',
    },
    # Control of log output in the terminal
    'log_output': {
        'gurobi': 'LogToConsole',  # 0=off, 1=on
        'highs': 'log_to_console',  # True/False
        'glpk': 'msg_lev',  # 0=none, 3=normal output
        'cbc': 'logLevel',  # 0 to 5
        'scip': 'display/verblevel',  # 0 to 5
    },
    # Primary feasibility tolerance
    'feasibility_tolerance': {
        'gurobi': 'FeasibilityTol',
        'highs': 'primal_feasibility_tolerance',
        'glpk': 'tol_bnd',  # Tolerance for variable bounds
        'cbc': 'primalTolerance',
        'scip': 'numerics/feastol',
    },
    # Tolerance for integrality
    'integer_tolerance': {
        'gurobi': 'IntFeasTol',
        'highs': 'mip_feasibility_tolerance',
        'glpk': 'tol_int',
        'cbc': 'integerTolerance',
        'scip': 'numerics/intfeastol',
    },
    # Enable/disable dual reductions in presolve (disabling helps to distinguish infeasible from unbounded)
    'dual_reductions': {
        'gurobi': 'DualReductions',
        'highs': None,    # HiGHS has no directly equivalent parameter
        'glpk': None,     # GLPK has no direct counterpart
        'cbc': None,      # CBC has no direct counterpart
        'scip': None,     # SCIP might control something similar via 'presolving/maxrestarts', but there is no exact mapping
    },
    # Allow non-convex models (if supported)
    'nonconvex': {
        'gurobi': 'NonConvex',
        'highs': None,    # HiGHS does not support non-convex QP/QCP
        'glpk': None,     # GLPK does not support non-convex QP/QCP
        'cbc': None,      # CBC does not support non-convex QP/QCP
        'scip': None,  # SCIP has no direct NonConvex parameter
    },
    # Enable/disable presolve
    'presolve': {
        'highs': 'presolve',
        'cbc': 'preprocess',
        'glpk': 'presol'
    },
    # Parallelization level or number of threads (if different)
    'parallel': {
        'gurobi': 'Threads',  # same as 'threads' in Gurobi
        'highs': 'parallel',
        'cbc': 'threads',
        'glpk': None  # GLPK is single-threaded
    },
    # Cutting plane settings
    'cuts': {
        'glpk': 'cuts',
        'cbc': 'cuts',
        'scip': 'separating/default'
    },
    # Heuristic search strategies
    'heuristics': {
        'glpk': 'fpump',
        'cbc': 'heuristics',
        'scip': 'heuristics/default'
    },
    # Backtracking control
    'backtrack': {
        'glpk': 'bt'
    },
    # Branching strategy
    'branching': {
        'glpk': 'br'
    },
    # Specific cut types
    'gomory_cuts': {
        'glpk': 'gomory'
    },
    'mir_cuts': {
        'glpk': 'mir'
    },
    'cover_cuts': {
        'glpk': 'cover'
    },
    'clique_cuts': {
        'glpk': 'clique'
    }
}

_NO_INPUT = object()

def create_solver(pyomo_config = None, solver_name=None,timelimit=_NO_INPUT, mipgap=None) -> tuple[object, dict]:
    """
    Returns a Pyomo solver instance based on the provided solver name.
    Creates the solver with options from the configuration or function arguments.

    Parameters
    ----------
    pyomo_config : dict, optional
        Solver settings as dictionary (e.g. ``PyomoConfig().__dict__``) with the keys
        'solver_name', 'solver_executable' and 'solver_options'. If None, the default
        settings of PyomoConfig are loaded.
    solver_name : str, optional
        Name of the solver to use ('gurobi', 'cbc', 'glpk', 'highs' or 'scip').
        Overrides the configuration setting.
    timelimit : int or None, optional
        Time limit for the solver in seconds. Overrides the configuration setting.
        If not given, the value from the configuration is used.
        If None, a default time limit of 3600 seconds is used.
    mipgap : float, optional
        Relative MIP gap for the solver. Overrides the configuration setting.

    Returns
    -------
    solver : object
        Pyomo solver instance created by SolverFactory.
    specific_options : dict
        Solver options mapped to the solver-specific option names.

    Raises
    ------
    ValueError
        If the solver name is not supported.
    """
    # 1. Load the default configuration if no PyomoConfig is provided
    if pyomo_config is None:
        pyomo_config_obj = PyomoConfig()  # Load default config if none provided
        pyomo_config = pyomo_config_obj.__dict__

    if solver_name is None:
        solver_name = pyomo_config["solver_name"]
    solver_executable = pyomo_config["solver_executable"]
    solver_options = pyomo_config["solver_options"].copy()  # make a copy to avoid modifying the original


    # 2. Check if the solver name is valid
    if solver_name not in SUPPORTED_SOLVERS:
        raise ValueError(f"Invalid solver name: {solver_name}. Supported solvers are: {SUPPORTED_SOLVERS}.")

    # 3. Create the solver instance
    if solver_executable:
        solver = SolverFactory(solver_name, executable=solver_executable)
    else:
        # Use the default solver executable path if not specified
        solver = SolverFactory(solver_name)

    # 4. Get solver specific options
    if timelimit is _NO_INPUT:
        pass  # Use the value from the JSON file if no Input is provided
    elif timelimit is None:
        solver_options["time_limit"] = 3600 # if None a default time limit of 3600 seconds is set (1hour)
    else:
        solver_options["time_limit"] = timelimit

    if mipgap is not None:
        solver_options["mip_gap"] = mipgap
    
    specific_options = _map_options(solver_name, solver_options)


    return solver, specific_options

def _map_options(solver_name, solver_options):
    """
    Map solver options to the appropriate format for the specified solver.

    Options without a counterpart for the given solver (None or missing in OPTION_MAP) are skipped.

    Parameters
    ----------
    solver_name : str
        Name of the solver to use, e.g. 'gurobi', 'cbc', 'glpk', 'highs' or 'scip'.
    solver_options : dict
        Generic solver options (keys of OPTION_MAP) to map to the solver-specific format.

    Returns
    -------
    mapped_options : dict
        Solver options with solver-specific option names.

    Raises
    ------
    ValueError
        If an option is not contained in OPTION_MAP.
    """

    mapped_options = {}
    for key, value in solver_options.items():
        if key in OPTION_MAP:
            mapped_key = OPTION_MAP[key].get(solver_name)
            if mapped_key is not None:
                mapped_options[mapped_key] = value
        else: 
            # Raise an error if the option is not supported. If it is needed it can be added to the OPTION_MAP 
            raise ValueError(f"Unsupported option '{key}' for solver '{solver_name}'. Supported options are: {list(OPTION_MAP.keys())}.")
    return mapped_options

def _reset_highs_scheduler(solver):
    """
    Reset the thread scheduler of HiGHS before a solve.

    HiGHS creates one thread scheduler per process with the thread count of the first solve. A later
    solve in the same process with a different 'threads' option stops immediately and Pyomo reports the
    termination condition 'unknown', e.g. when several scenarios or tests with different settings run in
    one process. Resetting the scheduler lets every solve use its own thread count.

    Parameters
    ----------
    solver : object
        Pyomo solver instance created by create_solver.

    Returns
    -------
    None.
    """
    if getattr(solver, "name", None) != "highs":
        return
    try:
        import highspy
    except ImportError:
        return
    highspy.Highs.resetGlobalScheduler(True)


def execute_and_diagnose(model, pyomo_config, model_name, result_dir):
    """
    Solves the given Pyomo model and triggers diagnosis if not solved to optimality.

    The model is written to an .lp file in result_dir before solving. The solution is loaded into
    the model only if the solver found one, so an infeasible model returns its termination
    condition instead of raising an error (e.g. with HiGHS).

    Parameters
    ----------
    model : pyomo.environ.ConcreteModel
        Optimization model to solve.
    pyomo_config : dict
        Solver settings, see create_solver.
    model_name : str
        Name of the model, used for the names of the output files.
    result_dir : str
        Directory for the .lp file and diagnosis files.

    Returns
    -------
    results : pyomo.opt.SolverResults
        Results object returned by the solver.
    """
    # Initialize solver
    solver, solver_options = create_solver(pyomo_config=pyomo_config)

    # Save the model to an .lp file
    lp_filename = os.path.join(result_dir, f"{model_name}.lp")
    model.write(lp_filename, io_options={"symbolic_solver_labels": True})

    # temporary log-file for the solver
    solver_log_path = os.path.join(result_dir, f"solver_output_{model_name}.log")    

    _reset_highs_scheduler(solver)

    # Capture solver output in a log file by redirecting stdout:
    with open(solver_log_path, 'w', encoding='utf-8') as log_file:
        with redirect_stdout(log_file):
            results = solver.solve(model, tee=True, options=solver_options, load_solutions=False)

    # Load the solution only if one exists. With automatic loading, some solvers (e.g. HiGHS) raise an
    # error for infeasible models instead of returning the termination condition.
    if len(results.solution) > 0:
        model.solutions.load_from(results)

    term_cond = results.solver.termination_condition

    if term_cond != pyo.TerminationCondition.optimal:
        _diagnose_solution(model, term_cond, result_dir, model_name, lp_filename, solver_log_path)
        # Add potential further analysis here for the different termination conditions
        if term_cond == pyo.TerminationCondition.infeasible:
            pass
        elif term_cond == pyo.TerminationCondition.unbounded:
            pass

        elif term_cond == pyo.TerminationCondition.infeasibleOrUnbounded:
            pass

    # Remove temporary solver log file
    if os.path.exists(solver_log_path):
        os.remove(solver_log_path)

    return results

def _diagnose_solution(model, term_cond, result_dir, model_name, lp_filename, solver_log_path):
    """
    Diagnose the optimization result when the solver does not terminate with an optimal solution. 
    Utilizes Gurobi (if available) to analyze infeasibility or unboundedness and saves an error log for further analysis.

    Parameters
    ----------
    model : pyomo.environ.ConcreteModel
        Optimization model that was not solved to optimality.
    term_cond : pyomo.opt.TerminationCondition
        Termination condition returned by the solver.
    result_dir : str
        Directory for the error file and, if infeasible, the IIS file.
    model_name : str
        Name of the model, used for the names of the output files.
    lp_filename : str
        Path of the .lp file of the model.
    solver_log_path : str
        Path of the solver log file, whose content is copied to the error file.

    Returns
    -------
    None.
    """
    errorfile_path = os.path.join(result_dir, f"errorfile_{model_name}.txt")

    n_vars = sum(1 for _ in model.component_data_objects(pyo.Var, active=True))
    n_cons = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))

    # Basic error logging for all errors
    with open(errorfile_path, 'w') as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Solver terminated with condition: {term_cond}\n")
        f.write(f"Model Statistics:\n")
        f.write(f"  - Variables: {n_vars}\n")
        f.write(f"  - Constraints: {n_cons}\n")
        f.write(f"Model-File located at: {lp_filename}\n\n")

        try:
            if os.path.exists(solver_log_path):
                with open(solver_log_path, 'r', encoding='utf-8') as log_file:
                    f.write("Solver Log:\n")
                    f.write("\n"+"-" * 40 + "\n")
                    f.write(log_file.read())
                    f.write("\n"+ "-" * 40 + "\n")
        except Exception as e:
            f.write(f"Could not read solver log: {e}\n")

    print(f"Solver terminated with condition: {term_cond}\nFor further analysis see {errorfile_path}")

    # Check if Gurobi is available for further analysis
    try:
        import gurobipy as gp
        with gp.Env(empty=True) as env:
            env.setParam("OutputFlag", 0) # Suppress the license printout
            env.start()                   # Trigger the license check
        gurobi_available = True

    except Exception as e:
        with open(errorfile_path, 'a') as f:
            f.write(f"\nGurobi analysis not possible as no local installation could be found. Error: {e}\n")
        gurobi_available = False

    # Attempt to solve the same model with Gurobi to get more detailed information about infeasibility or unboundedness, if Gurobi is available
    if gurobi_available:
        try:
            model.write("debug_model.lp", io_options={'symbolic_solver_labels': True})
            with gp.Env(empty=True) as env:
                env.setParam("OutputFlag", 0) # Use a silent environment to avoid Gurobi output in the console
                env.start()
                m = gp.read("debug_model.lp", env=env)
                m.setParam('DualReductions', 0) # Disable presolving reductions to get more accurate IIS
                print("Running Gurobi optimization to determine source of termination...")
                m.optimize()

                if m.status == gp.GRB.OPTIMAL:
                    print(f"Gurobi resolved with status: {m.status}. Objective value: {m.objVal}")
                    with open(errorfile_path, 'a') as f:
                        f.write(f"\nGurobi resolved with status: {m.status}. Objective value: {m.objVal}\n")
                        if term_cond == pyo.TerminationCondition.maxTimeLimit:
                            f.write(f"The original solver reached the time limit. Using Gurobi the runtime was: {m.Runtime:.2f} seconds\n")

                elif m.status == gp.GRB.INFEASIBLE:
                    m.computeIIS()
                    iis_filename = os.path.join(result_dir, f"iis_{model_name}.ilp")
                    m.write(iis_filename)
                    print(f"Gurobi model is infeasible. For further information, see {errorfile_path}")

                    with open(errorfile_path, 'a') as f:
                        f.write(f"\nGurobi confirmed infeasible. IIS saved to: {iis_filename}\n")

                elif m.status == gp.GRB.UNBOUNDED:
                    print("Gurobi model is unbounded.")
                    with open(errorfile_path, 'a') as f:
                        f.write("\nGurobi confirmed unbounded.\n")

                elif m.status == gp.GRB.INF_OR_UNBD:
                    print("Gurobi model is either infeasible or unbounded.")
                    with open(errorfile_path, 'a') as f:
                        f.write("\nGurobi returned INF_OR_UNBD. Further diagnostics required.\n")

                elif m.status in [gp.GRB.TIME_LIMIT, gp.GRB.ITERATION_LIMIT, gp.GRB.NODE_LIMIT]:
                    print(f"Gurobi reached a limit (Code: {m.status}) before finishing.")
                    with open(errorfile_path, 'a') as f:
                        f.write(f"\nGurobi stopped due to a limit. Status code: {m.status}\n")

                elif m.status == gp.GRB.NUMERIC:
                    print("Gurobi encountered numerical issues.")
                    with open(errorfile_path, 'a') as f:
                        f.write("\nGurobi stopped due to numeric instability.\n")

                else:
                    print(f"Gurobi resolved with status: {m.status}")
                    with open(errorfile_path, 'a') as f:
                        f.write(f"\nGurobi resolved with status: {m.status}\n")

        except Exception as e:
            print(f"Gurobi analysis failed. For further information, see {errorfile_path}")
            with open(errorfile_path, 'a') as f:
                f.write(f"\nGurobi analysis failed: {e}\n")
        
        if os.path.exists("debug_model.lp"):
            os.remove("debug_model.lp")
    
    else: 
        # TODO: Add IIS analysis if Gurobi is not available. e.g. using an elastic programming approach might be utilized to identify violated constraints (as described by https://web.mit.edu/lpsolve/doc/Infeasible.htm)
        with open(errorfile_path, 'a') as f:
            f.write("\nCurrently no infeasibility analysis implemented if gurobi is not available.\n")

def write_solution_file(model, model_name, result_dir):
    """
    Writes the solution of the optimization model to a file.

    The file 'solution_file_<model_name>.txt' contains the objective value and all
    variable values that are not None. Errors while writing are only printed as warning.

    Parameters
    ----------
    model : pyomo.environ.ConcreteModel
        Solved optimization model with an objective named 'objective'.
    model_name : str
        Name of the model, used for the file name.
    result_dir : str
        Directory of the solution file.

    Returns
    -------
    None.
    """
    file_path = os.path.join(result_dir, f"solution_file_{model_name}.txt")
    try:
        with open(file_path, 'w') as f:
            f.write("# Solution file\n")
            f.write(f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Objective value: {pyo.value(model.objective)}\n")
            f.write("# Variable values\n")

            # Write all variable values
            for var in model.component_objects(pyo.Var, active=True):
                if var.is_indexed():
                    for index in var:
                        if var[index].value is not None:
                            f.write(f"{var.name}[{index}] {var[index].value:.6f}\n")
                else:
                    if var.value is not None:
                        f.write(f"{var.name} {var.value:.6f}\n")

            f.write("# End of solution\n")
        print(f"Solution written to {file_path}")

    except Exception as e:
        print(f"Warning: Could not write solution file {file_path}: {e}")