# -*- coding: utf-8 -*-

from __future__ import division
import numpy as np
import math
import districtgenerator.functions.k_medoids as k_medoids


def _distances(values, norm=2):
    """
    Compute distance matrix for all data sets (rows of values).
    
    Parameters
    ----------
    values : 2-dimensional array
        Rows represent days and columns values.
    norm : integer, optional
        Compute the distance according to this norm. 2 is the standard Euclidean-norm. The default is 2.
    
    Return
    ------
    d : 2-dimensional array
        Distances between each data set.
    """
    # Initialize distance matrix
    d = np.zeros((values.shape[1], values.shape[1]))

    # Define a function that computes the distance between two days
    dist = (lambda day1, day2, r:
            math.pow(np.sum(np.power(np.abs(day1 - day2), r)), 1 / r))

    # Remember: The d matrix is symmetrical!
    for i in range(values.shape[1]):  # loop over first days
        for j in range(i + 1, values.shape[1]):  # loop second days
            d[i, j] = dist(values[:, i], values[:, j], norm)

    # Fill the remaining entries
    d = d + d.T

    return d


def cluster(inputs, number_clusters, len_cluster, norm=2, time_limit=300, mip_gap=0.0, weights=None):
    """
    Cluster a set of inputs into clusters by solving a k-medoid problem.
    
    Parameters
    ----------
    inputs : 2-dimensional array
        First dimension: Number of different input types.
        Second dimension: Values for each time step of interest.
    number_clusters : integer, optional
        How many clusters shall be computed? The default is 12.
    len_day : integer, optional
        Number of time steps per day. The default is 24.
    norm : integer, optional
        Compute the distance according to this norm. 2 is the standard Euclidean-norm. The default is 2.
    time_limit : integer, optional
        Time limit for the optimization in seconds. The default is 300.
    mip_gap : float, optional
        Optimality tolerance (0: proven global optimum). The default is 0.0.
    weights : 1-dimensional array, optional
        Weight for each input. If not provided, all inputs are treated equally.
    
    Returns
    -------
    scaled_typ_days : list
        Scaled typical demand days. The scaling is based on the annual demands.
    nc : array_like
        Weighting factors of each cluster.
    y : array_like
        Chosen clusters. 1 for chosen, 0 for not chosen.
    z : 2-dimensional array
        Mapping of each day to the clusters.
    inputsTransformed : list
        One entry for each row of the original 'input'.
        Entries are arrays with rows for each time step and columns for each day.
    """

    num_periods = int(inputs.shape[1] / len_cluster)
    # Set weights if not already given
    try:
        if weights == None:
            weights = np.ones(inputs.shape[0])
        elif not sum(weights) == 1:  # Rescale weights
            weights = np.array(weights) / sum(weights)
    except:
        if weights.all() == None:
            weights = np.ones(inputs.shape[0])
        elif not sum(weights) == 1:  # Rescale weights
            weights = np.array(weights) / sum(weights)

    # Manipulate inputs
    # Initialize arrays
    inputsTransformed = []
    inputsScaled = []
    inputsScaledTransformed = []

    # Fill and reshape
    # Scaling to values between 0 and 1, thus all inputs shall have the same
    # weight and will be clustered equally in terms of quality 
    for i in range(inputs.shape[0]):
        vals = inputs[i, :]
        temp = ((vals - np.min(vals)) / (np.max(vals) - np.min(vals))
                * math.sqrt(weights[i]))
        inputsScaled.append(temp)
        inputsScaledTransformed.append(temp.reshape((len_cluster, num_periods), order="F"))
        inputsTransformed.append(vals.reshape((len_cluster, num_periods), order="F"))
        # inputsScaledTransformed.append(temp.reshape((len_day, 52), order="F"))
        # inputsTransformed.append(vals.reshape((len_day, 52), order="F"))

    # Put the scaled and reshaped inputs together
    L = np.concatenate(tuple(inputsScaledTransformed))

    # Compute distances
    d = _distances(L, norm)

    # Execute optimization model
    (y, z, obj) = k_medoids.k_medoids(d, number_clusters, time_limit, mip_gap)

    # Section 2.3 and retain typical days
    nc = np.zeros_like(y)
    typicalClusters = []

    # nc contains how many days are there in each cluster
    nc = []
    for i in range(len(y)):
        temp = np.sum(z[i, :])
        if temp > 0:
            nc.append(temp)
            typicalClusters.append([ins[:, i] for ins in inputsTransformed])

    typicalClusters = np.array(typicalClusters)
    nc = np.array(nc, dtype="int")
    nc_cumsum = np.cumsum(nc) * len_cluster

    # Construct (yearly) load curves
    # ub = upper bound, lb = lower bound
    clustered = np.zeros_like(inputs)
    for i in range(len(nc)):
        if i == 0:
            lb = 0
        else:
            lb = nc_cumsum[i - 1]
        ub = nc_cumsum[i]

        for j in range(len(inputsTransformed)):
            clustered[j, lb:ub] = np.tile(typicalClusters[i][j], nc[i])

    # Scaling to preserve original demands
    sums_inputs = [np.sum(inputs[j, :]) for j in range(inputs.shape[0])]
    scaled = np.array([nc[day] * typicalClusters[day, :, :]
                       for day in range(number_clusters)])
    sums_scaled = [np.sum(scaled[:, j, :]) for j in range(inputs.shape[0])]
    scaling_factors = [sums_inputs[j] / sums_scaled[j]
                       for j in range(inputs.shape[0])]
    scaled_typ_clusters = [scaling_factors[j] * typicalClusters[:, j, :]
                       for j in range(inputs.shape[0])]

    return scaled_typ_clusters, nc, y, z, inputsTransformed
