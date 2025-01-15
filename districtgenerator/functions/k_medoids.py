# -*- coding: utf-8 -*-

from __future__ import division
import gurobipy as gp
import numpy as np


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

def k_medoids(distances, number_clusters, timelimit=100, mipgap=0.0001):
    """
    Solve the k-medoid clustering problem.

    Parameters
    ----------
    distances : 2d array
        Distances between each pair of node points. `distances` is a symmetrical matrix (dissimilarity matrix).
    number_clusters : integer
        Given number of clusters.
    timelimit : integer, optional
        Maximum time limit for the optimization. The default is 100.
    mipgap : float, optional
        Maximal relative gap between lower and upper bound for the solution of the problem. The default is 0.0001.

    Returns
    -------
    r_y : array_like
        Chosen clusters. 1 for chosen, 0 for not chosen.
    r_x.T : 2d array
        Assignments of nodes to clusters. 1 for assigned, 0 for not assigned.
    r_obj : float
        Objective value in the resulting optimum.
    """

    # Distances is a symmetrical matrix, extract its length
    length = distances.shape[0]

    # Create model
    model = gp.Model("k-Medoids-Problem")

    # Create variables
    x = {}  # Binary variables that are 1 if node i is assigned to cluster j
    y = {}  # Binary variables that are 1 if node j is chosen as a cluster
    for j in range(length):
        y[j] = model.addVar(vtype="B", name="y_" + str(j))

        for i in range(length):
            x[i, j] = model.addVar(vtype="B", name="x_" + str(i) + "_" + str(j))

    # Update to introduce the variables to the model
    model.update()

    # Set objective - equation 2.1, page 509, [1]
    obj = gp.quicksum(distances[i, j] * x[i, j]
                      for i in range(length)
                      for j in range(length))
    model.setObjective(obj, gp.GRB.MINIMIZE)

    # s.t.
    # Assign all nodes to clusters - equation 2.2, page 509, [1]
    # => x_i cannot be put in more than one group at the same time
    for i in range(length):
        model.addConstr(sum(x[i, j] for j in range(length)) == 1)

    # Maximum number of clusters - equation 2.3, page 509, [1]
    model.addConstr(sum(y[j] for j in range(length)) == number_clusters)

    # Prevent assigning without opening a cluster - equation 2.4, page 509, [1]
    for i in range(length):
        for j in range(length):
            model.addConstr(x[i, j] <= y[j])

    for j in range(length):
        model.addConstr(x[j, j] >= y[j])

    # Sum of main diagonal has to be equal to the number of clusters:
    model.addConstr(sum(x[j, j] for j in range(length)) == number_clusters)

    # Set solver parameters
    model.Params.TimeLimit = timelimit
    model.Params.MIPGap = mipgap
    model.Params.OutputFlag = False  # no console printing

    # Solve the model
    model.optimize()

    # Get results
    r_x = np.array([[x[i, j].X for j in range(length)]
                    for i in range(length)])

    r_y = np.array([y[j].X for j in range(length)])

    r_obj = model.ObjVal

    return r_y, r_x.T, r_obj
