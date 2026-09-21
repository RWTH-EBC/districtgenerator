# -*- coding: utf-8 -*-

from __future__ import division
import warnings
import time
import numpy as np
import pandas as pd
import tsam
from tsam import ClusterConfig

_TSAM_SOLVERS = {"gurobi", "cbc", "highs", "cplex"}


def _resolve_tsam_solver(pyomo_config):
    """
    Map the project's Pyomo solver configuration onto a solver supported by tsam's
    exact k-medoids MILP. tsam only supports gurobi/cbc/highs/cplex; glpk/scip
    (both otherwise supported by districtgenerator.functions.solver_config) fall
    back to highs.
    """
    solver_name = "gurobi"
    if pyomo_config:
        solver_name = pyomo_config.get("solver_name", solver_name) if isinstance(pyomo_config, dict) \
            else getattr(pyomo_config, "solver_name", solver_name)

    if solver_name not in _TSAM_SOLVERS:
        warnings.warn(
            f"Solver '{solver_name}' is not supported by tsam's k-medoids clustering; falling back to 'highs'."
        )
        return "highs"
    return solver_name


def cluster(inputs, number_clusters, len_cluster, norm=2, weights=None, scalings=None, pyomo_config=None):
    """
    Cluster a set of inputs into clusters by solving a k-medoid problem, using tsam's
    exact k-medoids implementation (tsam.aggregate with cluster method "kmedoids").

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
        Compute the distance according to this norm. Only the standard Euclidean-norm
        (norm=2) is supported, since that is the only distance metric tsam's exact
        k-medoids implementation offers.
    weights : 1-dimensional array, optional
        Weight for each input. If not provided, all inputs are treated equally.
    scalings : list of booleans, optional
        List indicating whether each input should be scaled to preserve energy demands.
    pyomo_config : dict, optional
        Solver settings (as stored on Datahandler.pyomo_config). Only `solver_name` is
        used, to pick the MILP solver tsam runs the k-medoids problem with. If None,
        defaults to 'gurobi'.

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
    assert norm == 2, "tsam's k-medoids implementation only supports the Euclidean norm (norm=2)."

    ################################################################
    # Step 1: Data validation and preprocessing
    ################################################################

    n_inputs = inputs.shape[0]
    total_timesteps = inputs.shape[1]

    num_periods = total_timesteps // len_cluster  # -> Integer division
    effective_timesteps = num_periods * len_cluster
    inputs_trimmed = inputs[:, :effective_timesteps]  # Trim inputs to ensure they fit into complete periods of length len_cluster

    # Set weights if not already given
    if weights is None:
        weights = np.ones(n_inputs, dtype=float)
    else:
        try:
            weights = np.array(weights, dtype=float)  # -> Go to except block if conversion fails due to non Number values
            if len(weights) != n_inputs:
                raise ValueError("Length of 'weights' must match number of input profiles")  # -> Go to except block
            if np.sum(weights) == 0 or np.isnan(np.sum(weights)):
                weights = np.ones(n_inputs, dtype=float)
        except Exception:
            weights = np.ones(n_inputs, dtype=float)
            print("Warning: 'weights' could not be processed. Check weight assignment. Using equal weights for all inputs.")
            time.sleep(5)  # Wait 5 seconds to make sure the user can see the warning

    # Default: No profile is scaled
    if scalings is None:
        scalings = [False] * n_inputs
    assert len(scalings) == n_inputs, "Length of 'scalings' must match number of input profiles"

    ################################################################
    # Step 2: Cluster with tsam
    ################################################################

    columns = [f"col_{j}" for j in range(n_inputs)]
    df = pd.DataFrame(inputs_trimmed.T, columns=columns)
    weights_dict = {col: float(w) for col, w in zip(columns, weights)}
    exclude_cols = [col for col, scale in zip(columns, scalings) if not scale]

    solver = _resolve_tsam_solver(pyomo_config)
    with warnings.catch_warnings():
        # Zero-weight profiles (e.g. dhw/heat/occ passengers, see clustering_processing.py)
        # are expected and intentional; tsam floors them to its min_weight and warns per
        # column, which is just noise here since we already know which profiles are unweighted.
        warnings.filterwarnings("ignore", message=r'weight of ".*" set to the minimal tolerable weighting')
        result = tsam.aggregate(
            df,
            n_clusters=number_clusters,
            period_duration=float(len_cluster),
            temporal_resolution=1.0,  # unitless "timesteps": only the period_duration/temporal_resolution ratio matters
            cluster=ClusterConfig(method="kmedoids", representation="medoid", solver=solver),
            weights=weights_dict,
            preserve_column_means=True,
            rescale_exclude_columns=exclude_cols,
        )

    ################################################################
    # Step 3: Reassemble outputs in the ascending-medoid-index convention
    # expected by callers (both get_params_central_devices.py and
    # clustering_processing.py independently re-derive cluster ordering by
    # scanning y/z in ascending original-period-index order, so nc and
    # scaled_typ_clusters_per_input must follow that same ordering here).
    ################################################################

    raw_centers = list(result.clustering.cluster_centers)  # tsam cluster id -> original period index
    order = sorted(range(len(raw_centers)), key=lambda cid: raw_centers[cid])  # position -> tsam cluster id

    nc = np.array([int(round(result.cluster_counts[order[p]])) for p in range(number_clusters)], dtype=int)

    scaled_typ_clusters_per_input = []
    for col in columns:
        pivot = result.cluster_representatives[col].unstack("timestep")
        scaled_typ_clusters_per_input.append(pivot.loc[[order[p] for p in range(number_clusters)]].to_numpy())

    y = np.zeros(num_periods)
    for idx in raw_centers:
        y[idx] = 1

    z = np.zeros((num_periods, num_periods))
    for day, cid in enumerate(result.cluster_assignments):
        z[raw_centers[cid], day] = 1

    inputsTransformed = [
        inputs_trimmed[i, :].reshape((len_cluster, num_periods), order="F")
        for i in range(n_inputs)
    ]

    return scaled_typ_clusters_per_input, nc, y, z, inputsTransformed
