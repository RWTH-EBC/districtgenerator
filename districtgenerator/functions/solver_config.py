# -*- coding: utf-8 -*-

from pyomo.environ import SolverFactory
import os, sys
import json
from districtgenerator.data_handling.config import PyomoConfig
import pyomo.environ as pyo
from contextlib import redirect_stdout
from datetime import datetime

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
    # Allow non-convex models (if supported)
    'dual_reductions': {
        'gurobi': 'DualReductions',
        'highs': None,    # Highs unterstützt keinen direkten Äquivalentparameter
        'glpk': None,     # GLPK hat kein direktes Pendant
        'cbc': None,      # CBC hat kein direktes Pendant
        'scip': None,     # SCIP könnte evtl. 'presolving/maxrestarts' ähnlich steuern, aber kein exaktes Mapping
    },
    'nonconvex': {
        'gurobi': 'NonConvex',
        'highs': None,    # Highs unterstützt keine nichtkonvexen QP/QCP
        'glpk': None,     # GLPK unterstützt keine nichtkonvexen QP/QCP
        'cbc': None,      # CBC unterstützt keine nichtkonvexen QP/QCP
        'scip': None,  # SCIP hat keinen direkten NonConvex-Parameter
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
        'glpk': 'threads'  # GLPK has limited threading support
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

def create_solver(pyomo_config = None, solver_name=None,timelimit=_NO_INPUT, mipgap=None) -> tuple[SolverFactory, dict]:  # type: ignore
    """
    Returns a Pyomo solver instance based on the provided solver name.
    Creates the solver with options from a JSON file or function arguments.
    -------
    Parameters
    pyomo_config : PyomoConfig, optional
        PyomoConfig instance containing solver settings. if None the settings are directly loaded from the config file with the standard values.
    solver_name : str,
        name of the solver to use, e.g., 'gurobi', 'cbc', 'glpk', 'highs', 'scip' to override the JSON file setting
    timelimit : 
        int,        time limit for the solver in seconds to override the JSON file setting
        _NO_INPUT,  Use the value from the JSON file if None
        None,       set timelimit to None

    mipgap : float,
        MIP gap for the solver to override the JSON file setting

    -------
    Returns
    tuple: (SolverFactory instance, dict of solver options)
    """
    # If no PyomoConfig is provided, load the default configuration
    if pyomo_config is None:
        pyomo_config_obj = PyomoConfig()  # Load default config if none provided
        pyomo_config = pyomo_config_obj.__dict__

    if solver_name is None:
        solver_name = pyomo_config["solver_name"]
    solver_executable = pyomo_config["solver_executable"]
    solver_options = pyomo_config["solver_options"].copy()  # make a copy to avoid modifying the original


    # check if the solver name is valid
    if solver_name not in SUPPORTED_SOLVERS:
        raise ValueError(f"Invalid solver name: {solver_name}. Supported solvers are: {SUPPORTED_SOLVERS}.")

    # 2. Create the solver instance
    if solver_executable:
        solver = SolverFactory(solver_name, executable=solver_executable)
    else:
        # Use the default solver executable path if not specified
        solver = SolverFactory(solver_name)

    # 3. get solver specific options
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
    
    -------
    Parameters
    solver_name : str,
        name of the solver to use, e.g., 'gurobi', 'cbc', 'glpk', 'highs'
    solver_options : dict,
        dictionary of solver options to map to the solver-specific format
    
    -------
    Returns
    mapped_options: dict,
        dictionary of mapped solver options
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


def execute_and_diagnose(model, pyomo_config, model_name, result_dir):
    """
    Solves the given Pyomo model and triggers diagnosis if not solved to optimality.
    """
    # Initialize solver
    solver, solver_options = create_solver(pyomo_config=pyomo_config)

    # Save the model to an .lp file
    lp_filename = os.path.join(result_dir, f"{model_name}.lp")
    model.write(lp_filename, io_options={"symbolic_solver_labels": True})

    # temporary log-file for the solver
    solver_log_path = os.path.join(result_dir, f"solver_output_{model_name}.log")

    # Capture solver output in a log file by redirecting stdout:
    with open(solver_log_path, 'w', encoding='utf-8') as log_file:
        with redirect_stdout(log_file):
            results = solver.solve(model, tee=True, options=solver_options)

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

                if m.status == gp.GRB.OPTIMAL or m.status == 2:
                    print(f"Gurobi resolved with status: {m.status}. Objective value: {m.objVal}")
                    with open(errorfile_path, 'a') as f:
                        f.write(f"\nGurobi resolved with status: {m.status}. Objective value: {m.objVal}\n")
                        if term_cond == pyo.TerminationCondition.timeLimit:
                            f.write(f"The original solver reached the time limit. Using Gurobi the runtime was: {m.Runtime:.2f} seconds\n")

                elif m.status == gp.GRB.INFEASIBLE or m.status == 4:
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
