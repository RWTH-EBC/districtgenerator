# -*- coding: utf-8 -*-

from __future__ import division
import numpy as np
import districtgenerator.functions.k_medoids as k_medoids
import time

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
    n = values.shape[1]
    d = np.zeros((n, n))

    for i in range(n):  # loop over first days
        for j in range(i + 1, n):  # loop second days -> only upper right triangle because d is symmetrical
            diff = np.abs(values[:, i] - values[:, j]) # difference between two days
            d[i, j] = np.sum(diff ** norm) ** (1 / norm) # normed distance

    # Fill the remaining entries
    d = d + d.T
    return d

def _normalize_input(inputs):
    """
    Normalize the inputs for clustering.
    Use min-max normalization to scale each input between 0 and 1.

    Parameters
    ----------
    inputs : numpy.ndarray
        2D array of input profiles with shape (n_profiles, n_timesteps).
        Each row represents a different input profile.

    Returns
    -------
    normalized_inputs : normalized input profiles; with the same shape as inputs.
    """
    # Min and max values for each profile
    min_vals = np.min(inputs, axis=1, keepdims=True)
    max_vals = np.max(inputs, axis=1, keepdims=True)

    # Normalize each profile, avoiding division by zero
    range_vals = max_vals - min_vals
    normalized_inputs = np.divide(
        inputs - min_vals,
        range_vals,
        out=np.zeros_like(inputs), # if not possible value is 0
        where=range_vals > 0
    )

    return normalized_inputs

def _denormalize_output(normalizedOutputsTransformed, original_inputs):
    """
    This function reverses the normalization applied in _normalize_input for the output cluster periods.

    Parameters
    ----------
    normalizedOutputsTransformed : 3-dimensional array Normalized output profiles; shape (n_clusters, n_inputs, len_cluster).
    original_inputs : 2-dimensional array Original input profiles; shape (n_inputs, total_timesteps).
    """
    n_inputs = original_inputs.shape[0]

    # Get the original min and max values for each profile.
    min_vals = np.min(original_inputs, axis=1, keepdims=True)
    max_vals = np.max(original_inputs, axis=1, keepdims=True)

    min_vals_base = min_vals.reshape(1, n_inputs, 1)
    max_vals_base = max_vals.reshape(1, n_inputs, 1)

    # Apply the denormalization formula. for each input profile
    denormalized_outputs = normalizedOutputsTransformed * (max_vals_base - min_vals_base) + min_vals_base
    return denormalized_outputs

def _compute_scaling_factors(inputsNormalizedTransformed, normTypicalClusters, clusters, z, nc):
    """
    Compute the scaling factors according to Eq. (12) from
    "Impact of different time series aggregation methods on optimal energy system design" (2018) (Kotzur et al.)
    """
    n_inputs = len(inputsNormalizedTransformed)
    n_clusters = len(clusters)

    scaling_factors = np.zeros((n_inputs, n_clusters)) # Individual scaling factor for each input and cluster

    for j in range(n_inputs):  # Loop over different inputs
        # Numerator: Sum of the normalized data in each cluster
        sums_of_all_periods = np.sum(inputsNormalizedTransformed[j], axis=0)
        true_cluster_sums_norm = z[clusters, :] @ sums_of_all_periods

        # Denominator: Sum of the normalized medoid values * number of periods in the cluster
        medoid_sums_norm = np.sum(normTypicalClusters[:, j, :], axis=1)
        denom = medoid_sums_norm * nc

        # Calculate the scaling factors
        scaling_factors[j, :] = np.divide(
            true_cluster_sums_norm,
            denom,
            out=np.ones(n_clusters),
            where=denom != 0
        )

    return scaling_factors

def _rescale_profiles(normTypicalClusters, inputs, inputsNormalizedTransformed, clusters, z, nc, scalings):
    """
    Scaling of the clusters to preserve original demands.

    The scaling follows the procedure described in:
    "Impact of different time series aggregation methods on optimal energy system design"
    Kotzur et al. / Renewable Energy 117 (2018) pp. 478 (Scaling of aggregated time series)

    Steps:
    1. It calculates scaling factors to preserve the energy sum in the normalized space.
    2. It applies these factors if scalings[i] is True, caps peaks at 1.0, and redistributes the energy deficit.
    3. It denormalizes the scaled profiles back to the original physical scale.

    Parameters
    ----------
    normTypicalClusters : 3-dimensional array that contains the normalized typical clusters. (n_clusters x n_inputs x len_cluster)
    inputs : 2-dimensional array that contains the original input profiles. (n_inputs x total_timesteps)
    inputsNormalizedTransformed : All input profiles normalized and reshaped into periods.
    clusters : list of indices of chosen clusters.
    z : 2-dimensional array that maps each period to the cluster it was assigned to.
    nc : array that contains information about how many periods are in each cluster.

    Returns
    -------
    scaled_typ_clusters : 3-dimensional array that contains the scaled typical clusters. (n_clusters x n_inputs x len_cluster)
    """
    n_inputs = inputs.shape[0]
    n_clusters = len(clusters)

    # Step 1: Compute scaling factors
    scaling_factors = _compute_scaling_factors(inputsNormalizedTransformed, normTypicalClusters, clusters, z, nc)

    # Step 2: Apply scaling factors and handle peak capping
    scaled_normed_typ_clusters = np.zeros_like(normTypicalClusters)

    for j in range(n_inputs):  # Loop over different inputs
        if scalings[j]:
            for k in range(n_clusters):
                norm_profile = normTypicalClusters[k, j, :]

                # Apply the scaling factor
                scaled_norm_profile = norm_profile * scaling_factors[j, k]
                target_sum = np.sum(scaled_norm_profile)
                final_norm_profile = np.copy(scaled_norm_profile)

                # Initialize indices of time steps that can still be scaled
                idx_scalable = (final_norm_profile > 0) & (final_norm_profile < 1.0)

                # If peaks exceed 1.0, cap them and redistribute the excess energy
                while any(final_norm_profile > 1.0) and np.any(idx_scalable):
                    # cap peaks at 1.0
                    final_norm_profile[final_norm_profile > 1.0] = 1.0
                    current_sum = np.sum(final_norm_profile)
                    deficit = target_sum - current_sum

                    if deficit <= target_sum * 1e-6:
                        break  # Exit if deficit is negligible

                    # Scale the remaining time steps to redistribute the deficit
                    total_scalable = np.sum(final_norm_profile[idx_scalable])
                    scal_factor = 1 + (deficit / total_scalable)

                    final_norm_profile[idx_scalable] *= scal_factor
                    # Update the indices of time steps that can still be scaled
                    idx_scalable = (final_norm_profile > 0) & (final_norm_profile < 1.0)

                # if at the end there are still peaks above 1.0, cap them. Excess energy is not distributed
                final_norm_profile[final_norm_profile > 1.0] = 1.0

                scaled_normed_typ_clusters[k, j, :] = final_norm_profile

        else: # if no scaling is desired, just copy the original normalized profile
            scaled_normed_typ_clusters[:, j, :] = normTypicalClusters[:, j, :]


    # Step 3: Denormalize the scaled profiles back to original scale

    scaled_typ_clusters = _denormalize_output(scaled_normed_typ_clusters, inputs)

    return scaled_typ_clusters


def cluster(inputs, number_clusters, len_cluster, norm=2, time_limit=300, mip_gap=0.0, weights=None, scalings=None, pyomo_config=None):
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
    scalings : list of booleans, optional
        List indicating whether each input should be scaled to preserve energy demands.
    pyomo_config : PyomoConfig, optional
        PyomoConfig instance containing solver settings passed down. if None the settings are directly loaded from the config file with the standard values.

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

    #! Save inputs to an excel for debugging purposes
    # import pandas as pd
    # df = pd.DataFrame(inputs)
    # df.to_excel("debugging_inputs.xlsx", index=False)


    ################################################################
    # Step 1: Data validation and preprocessing
    ################################################################

    n_inputs = inputs.shape[0]
    total_timesteps = inputs.shape[1]
    # print(f"Number of inputs: {n_inputs}, Total time steps: {total_timesteps}")

    num_periods = total_timesteps // len_cluster # -> Integer division

    # Set weights if not already given
    if weights  is None:
        weights = np.ones(n_inputs, dtype=float)
    else:
        try:
            weights = np.array(weights, dtype=float) # -> Go to except block if conversion fails due to non Number values
            if len(weights) != n_inputs:
                raise ValueError("Length of 'weights' must match number of input profiles") # -> Go to except block
            if np.sum(weights) == 0 or np.isnan(np.sum(weights)):
                weights = np.ones(n_inputs, dtype=float)
        except:
            weights = np.ones(n_inputs, dtype=float)
            #! Log warning or raise exception?
            print("Warning: 'weights' could not be processed. Check weight assignment. Using equal weights for all inputs.")
            time.sleep(5) # Wait 5 seconds to make sure the user can see the warning
    # Normalize weights
    weights = weights / np.sum(weights)


    # Default: No profile is scaled
    if scalings is None:
        scalings = [False] * n_inputs
    assert len(scalings) == n_inputs, "Length of 'scalings' must match number of input profiles"

    assert norm > 0, "'norm' must be positive"

    ################################################################
    # Step 2: Prepare inputs for clustering
    ################################################################

    # Normalize the inputs
    normalized_inputs = _normalize_input(inputs=inputs)

    # Reshape the original profiles into periods (e.g. days/weeks)
    inputsTransformed = [
    inputs[i, :].reshape((len_cluster, num_periods), order="F")
    for i in range(inputs.shape[0])
    ]

    # Reshape the normalized profiles into periods
    inputsNormalizedTransformed = [
    normalized_inputs[i, :].reshape((len_cluster, num_periods), order="F")
    for i in range(normalized_inputs.shape[0])
    ]

    # Apply weighting and prepare for distance calculation
    applied_weights = weights ** (1 / norm)
    inputsScaledTransformed = [
        inputsNormalizedTransformed[i] * applied_weights[i]
        for i in range(len(weights))
    ]

    # Put the normalized and reshaped inputs together
    L = np.concatenate(tuple(inputsScaledTransformed))

    ################################################################
    # Step 3: Clustering (k-medoids)
    ################################################################

    # Compute distances
    d = _distances(L, norm)

    # Execute optimization model
    y, z, obj = k_medoids.k_medoids(d, number_clusters, time_limit, mip_gap, pyomo_config=pyomo_config)

    # Get chosen Medoids
    clusters = [c for c, value in enumerate(y) if value == 1]
    n_clusters = len(clusters)
    nc = np.array([int(np.sum(z[c, :])) for c in clusters], dtype=int) # Number of periods in each cluster

    # get normalized typical clusters and their values for each input
    normTypicalClusters = np.zeros((n_clusters, n_inputs, len_cluster))
    for k, c in enumerate(clusters):
        for j in range(n_inputs):
            normTypicalClusters[k, j, :] = inputsNormalizedTransformed[j][:, c]

    ################################################################
    # Step 4: Scaling of the clusters to preserve energy demands
    ################################################################

    scaled_typ_clusters = _rescale_profiles(normTypicalClusters, inputs, inputsNormalizedTransformed, clusters, z, nc, scalings)

    # transform scaled_typ_clusters to list of arrays for each input
    # (n_clusters x n_inputs x len_cluster) -> list of n_inputs arrays with (n_clusters x len_cluster)
    scaled_typ_clusters_per_input = [scaled_typ_clusters[:, j, :] for j in range(n_inputs)]
    return scaled_typ_clusters_per_input, nc, y, z, inputsTransformed