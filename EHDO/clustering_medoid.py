#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool

Developed by:   E.ON Energy Research Center, 
                Institute for Energy Efficient Buildings and Indoor Climate, 
                RWTH Aachen University, 
                Germany
               
Contact:        Marco Wirtz 
                marco.wirtz@eonerc.rwth-aachen.de

                k-medoids clustering implemented by Thomas Schütz (2015).
"""

from __future__ import division
import numpy as np
import math
import districtgenerator.EHDO.k_medoids as k_medoids

def _distances(values, norm=2):
    """
    Compute distance matrix for all data sets (rows of values)
    
    Parameters
    ----------
    values : 2-dimensional array
        Rows represent days and columns values
    norm : integer, optional
        Compute the distance according to this norm. 2 is the standard
        Euklidean-norm.
    
    Return
    ------
    d : 2-dimensional array
        Distances between each data set
    """
    # Initialize distance matrix
    d = np.zeros((values.shape[1], values.shape[1]))

    # Define a function that computes the distance between two days
    dist = (lambda day1, day2, r: 
            math.pow(np.sum(np.power(np.abs(day1 - day2), r)), 1/r))

    # Remember: The d matrix is symmetrical!
    for i in range(values.shape[1]): # loop over first days
        for j in range(i+1, values.shape[1]): # loop second days
            d[i, j] = dist(values[:,i], values[:,j], norm)
    
    # Fill the remaining entries
    d = d + d.T
    
    return d


def cluster(inputs, number_clusters=12, norm=2, time_limit=300, mip_gap=0.0,
            weights=None):
    """
    Cluster a set of inputs into clusters by solving a k-medoid problem.
    
    Parameters
    ----------
    inputs : 2-dimensional array
        First dimension: Number of different input types "heat", "cool", "power", "hydrogen", "T_air", "GHI", "DHI", "wind_speed".
        Second dimension: Values for each time step of interes.
    number_clusters : integer, optional
        How many clusters shall be computed?
    norm : integer, optional
        Compute the distance according to this norm. 2 is the standard
        Euklidean-norm.
    time_limit : integer, optional
        Time limit for the optimization in seconds
    mip_gap : float, optional
        Optimality tolerance (0: proven global optimum)
    weights : 1-dimensional array, optional
        Weight for each input. If not provided, all inputs are treated equally.
    
    Returns
    -------
    scaled_typ_days : 
        Scaled typical demand days. The scaling is based on the annual demands.
    nc : array_like
        Weighting factors of each cluster
    z : 2-dimensional array
        Mapping of each day to the clusters
    """
    # Determine time steps per day
    len_day = int(inputs.shape[1] / 365)
    
    # Set weights if not already given
    if weights == None:
        weights = np.ones(inputs.shape[0])
    elif not sum(weights) == 1: # Rescale weights
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
        vals = inputs[i,:]
        if np.max(vals) == np.min(vals):
            temp = np.zeros_like(vals)
        else:
            temp = ((vals - np.min(vals)) / (np.max(vals) - np.min(vals))
                    * math.sqrt(weights[i]))
        inputsScaled.append(temp)
        inputsScaledTransformed.append(temp.reshape((len_day, 365), order="F"))
        inputsTransformed.append(vals.reshape((len_day, 365), order="F"))

    # Put the scaled and reshaped inputs together
    L = np.concatenate(tuple(inputsScaledTransformed))

    # Compute distances
    d = _distances(L, norm)

    # Execute optimization model
    (y, z, obj) = k_medoids.k_medoids(d, number_clusters, time_limit, mip_gap)

    # Section 2.3 and retain typical days
    typicalDays = []

    # nc contains how many days are there in each cluster
    nc = []
    for i in range(len(y)):
        temp = np.sum(z[i,:])
        if temp > 0:
            nc.append(temp)
            typicalDays.append([ins[:,i] for ins in inputsTransformed])

    typicalDays = np.array(typicalDays)
    nc = np.array(nc, dtype="int")

    # Scaling to preserve original demands
    scaling_factors = np.zeros((inputs.shape[0], number_clusters))

    # Compute scaling factors for each input and cluster
    clustered_days = [day for day, value in enumerate(y) if value == 1]
    for j in range(inputs.shape[0]):  # Loop over different inputs
        for c in range(number_clusters):  # Loop over clusters
            total_clustered = sum(inputsTransformed[j][:, clustered_days[c]]) * nc[c]
            total_input = sum([sum(inputsTransformed[j][:,a]) for a in range(365)]*z[clustered_days[c], :])
            scaling_factors[j, c] = total_input / total_clustered if total_clustered > 0 else 1

    # Apply scaling factors to typical days
    scaled_typ_days = []
    for j in range(inputs.shape[0]):  # Loop over input types
        cluster_data = np.zeros_like(typicalDays[:, j, :])
        for c in range(number_clusters):  # Loop over clusters
            cluster_data[c, :] = scaling_factors[j, c] * typicalDays[c, j, :]  # Apply scaling factor
        scaled_typ_days.append(cluster_data)  # Append the cluster data to the list

    return scaled_typ_days, nc, z