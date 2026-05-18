# -*- coding: utf-8 -*-

from pyomo.environ import SolverFactory
from districtgenerator.data_handling.config import PyomoConfig

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
