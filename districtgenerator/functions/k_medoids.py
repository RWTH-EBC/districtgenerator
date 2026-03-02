# -*- coding: utf-8 -*-

from __future__ import division
import pyomo.environ as pyo
import numpy as np
import districtgenerator.functions.solver_config as solver_config
import time

# Implementation of the k-medoids problem, as it is applied in
# "Selection of typical demand days for CHP optimization"
# by Fernando Domínguez-Muñoz, José M. Cejudo-López, Antonio Carrillo-Andrés and Manuel Gallardo-Salazar
# in Energy and Buildings, Vol 43, Issue 11 (November 2011), pp. 3036-3043

# Original formulation (hereafter referred to as [1]) can be found in:

# "Integer Programming and the Theory of Grouping"
# by Hrishikesh D. Vinod
# in Journal of the American Statistical Association. Vol. 64, No. 326 (June 1969)
# pp. 506-519
# Stable URL: http://www.jstor.org/stable/2283635

def k_medoids(distances, number_clusters, timelimit=None, mipgap=None, pyomo_config=None):
    """
    Solves the k-medoids clustering problem using Pyomo.

    The solver configuration is created by the `create_solver` function.
    The function arguments for 'timelimit' and 'mipgap' can override the settings
    from the JSON file for a single call. If None is passed, the values from the JSON file are used.

    Parameters
    ----------
    distances : 2d array
        Distances between each pair of node points. `distances` is a symmetrical matrix (dissimilarity matrix).
    number_clusters : integer
        Given number of clusters.
    timelimit : integer, optional
        Maximum time limit for the optimization in seconds. Overrides the value from the JSON file.
        Default is None (uses JSON setting).
    mipgap : float, optional
        Maximum relative gap between the lower and upper bounds for the solution.
        Overrides the value from the JSON file. Default is None (uses JSON setting).

    Returns
    -------
    r_y : array_like
        Selected clusters. 1 for selected, 0 for not selected.
    r_x.T : 2d array
        Assignment of nodes to clusters. 1 for assigned, 0 for not assigned.
    r_obj : float
        Value of the objective function in the found optimum.
    """
    start_time = time.time()

    # Build the model
    model = pyo.ConcreteModel(name="k-Medoids-Problem")
    build_model(model, distances, number_clusters)
    model_building_time = time.time() - start_time

    # Solve the model and extract results
    r_y, r_x_transposed, r_obj = solve_model_and_extract_results(model, timelimit, mipgap, pyomo_config=pyomo_config)
    model_solve_time = time.time() - start_time - model_building_time

    # Calculate total time
    total_time = time.time() - start_time


    # Maybe record the times into a log file

    # print(f"\n Time needed for building the model: {model_building_time:.2f} seconds.")
    # print(f" Time needed for solving the model: {model_solve_time:.2f} seconds.")
    # print(f" Total time needed: {total_time:.2f} seconds.")

    return r_y, r_x_transposed, r_obj


def build_model(model, distances, number_clusters):
    """
    Build the Pyomo k-medoids optimization model.

    Parameters
    ----------
    distances : 2d array
        Distances between each pair of node points. `distances` is a symmetrical matrix (dissimilarity matrix).
    number_clusters : integer
        Given number of clusters.

    Returns
    -------
    model : pyo.ConcreteModel
        The built Pyomo model ready for solving.
    """
    # Extract the length of the symmetric distance matrix
    length = distances.shape[0]

    # Definition of index sets
    model.nodes = pyo.RangeSet(0, length - 1)

    # Definition of binary decision variables
    model.y = pyo.Var(model.nodes, within=pyo.Binary)
    model.x = pyo.Var(model.nodes, model.nodes, within=pyo.Binary)

    # Definition of the objective function (Equation 2.1, page 509, [1])
    def objective_rule(model):
        return sum(distances[i, j] * model.x[i, j] for i in model.nodes for j in model.nodes)

    model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

    # Definition of constraints
    model.constraints = pyo.ConstraintList()

    # Each node must be assigned to exactly one cluster (Equation 2.2)
    for i in model.nodes:
        model.constraints.add(sum(model.x[i, j] for j in model.nodes) == 1)

    # The exact number of clusters must be selected (Equation 2.3)
    model.constraints.add(sum(model.y[j] for j in model.nodes) == number_clusters)

    # Assignment to node j is only possible if j is a cluster center (Equation 2.4)
    for i in model.nodes:
        for j in model.nodes:
            model.constraints.add(model.x[i, j] <= model.y[j])

    # If j is a cluster center, it must be assigned to itself
    for j in model.nodes:
        model.constraints.add(model.x[j, j] >= model.y[j])

    # The sum of the main diagonal must equal the number of clusters
    model.constraints.add(sum(model.x[j, j] for j in model.nodes) == number_clusters)

    return model


def solve_model_and_extract_results(model, timelimit=None, mipgap=None, pyomo_config=None):
    """
    Solve the k-medoids model and extract results.

    Parameters
    ----------
    model : pyo.ConcreteModel
        The Pyomo model to solve.
    timelimit : integer, optional
        Maximum time limit for the optimization in seconds. Overrides the value from the JSON file.
        Default is None (uses JSON setting).
    mipgap : float, optional
        Maximum relative gap between the lower and upper bounds for the solution.
        Overrides the value from the JSON file. Default is None (uses JSON setting).

    Returns
    -------
    r_y : array_like
        Selected clusters. 1 for selected, 0 for not selected.
    r_x.T : 2d array
        Assignment of nodes to clusters. 1 for assigned, 0 for not assigned.
    r_obj : float
        Value of the objective function in the found optimum.
    """
    # Extract length from model
    length = len(model.nodes)

    # Solve the model
    solver, specific_options = solver_config.create_solver(pyomo_config = pyomo_config, timelimit=timelimit, mipgap=mipgap)
    results = solver.solve(model, tee=False, options=specific_options)

    # Check if an optimal solution was found
    if (results.solver.status == pyo.SolverStatus.ok) and (
            results.solver.termination_condition == pyo.TerminationCondition.optimal):
        # Extract the results if the solution is optimal
        r_x = np.array([[pyo.value(model.x[i, j]) for j in range(length)] for i in range(length)])
        r_y = np.array([pyo.value(model.y[j]) for j in range(length)])
        r_obj = pyo.value(model.objective)
    else:
        # Fallback if no optimal solution was found
        print(
            f"Solver could not find an optimal solution. Status: {results.solver.status}, Termination condition: {results.solver.termination_condition}")
        r_x = np.zeros((length, length))
        r_y = np.zeros(length)
        r_obj = -1

    return r_y, r_x.T, r_obj