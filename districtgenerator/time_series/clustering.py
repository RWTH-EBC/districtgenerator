"""
Clustering of the district profiles into representative periods for the operation optimization.

clustering_processing clusters the profiles of all buildings, the site and (optionally) the central
energy supply with k-medoids (time_series.medoid). apply_design_clustering reuses the periods chosen
during the design of the central devices instead, so that design and operation use the same periods.
"""

import numpy as np
import districtgenerator.time_series.medoid as cm
import sys

# Profiles of each building (attributes of building["user"]), clustered as "<name>_cluster"
BUILDING_PROFILES = ("elec", "dhw", "heat", "cooling", "occ", "EV_carcharging_ondemand", "EV_carprofile",
                     "generationPV", "generationSTC")
# Profiles of each individual car, clustered as "<name>_cluster" (None if the car has no such profile)
CAR_PROFILES = ("availability_profile", "consumption_profile_wh", "on_demand_charging_profile_w", "fuel_profile_l")
CAR_METADATA = ("car_id", "type", "location", "battery_capacity_wh")
# Profiles of the central energy supply in heat_grid_data and centralDevices["generation"]
HEAT_GRID_PROFILES = ("total_losses_heating_network", "total_losses_cooling_network", "pump_power")
CENTRAL_GENERATION = {"Wind": "WT", "PV": "PV", "STC": "STC"}  # generation profile -> device in the capacities


def _save_item(container, key):
    """Function that saves a clustered profile as container[key]."""
    def save(clustered):
        container[key] = clustered
    return save


def _save_attribute(obj, name):
    """Function that saves a clustered profile as obj.<name>."""
    def save(clustered):
        setattr(obj, name, clustered)
    return save


def clustering_processing(time, site, district, heat_grid_data, centralDevices, pyomo_config, centralEnergySupply=False):
    """
    Perform time series aggregation for profiles by using the k-medoids clustering algorithm.

    The periods are chosen by the electricity demand of the buildings, the ambient temperature and,
    if relevant, wind speed and solar radiation. All other profiles have weight 0 and are only
    cut into the same periods. The clustered profiles are saved as "<profile>_cluster" next to the
    original profiles (e.g. user.elec_cluster, site["T_e_cluster"]).

    Parameters
    ----------
    time : dict
        Time settings with "clusterLength" [s], "timeResolution" [s] and "clusterNumber".
    site : dict
        Site data with the profiles "T_e", "wind_speed" and "SunTotal".
    district : list of dict
        Buildings with their user profiles and building features (f_PV1, f_PV2, f_STC).
    heat_grid_data : dict
        Heat grid data with "T_soil" and, for central energy supply, the network losses and pump power.
    centralDevices : dict
        Capacities and generation profiles of the central devices. Only used for central energy supply.
    pyomo_config : dict
        Solver settings, only "solver_name" is used for the k-medoids problem.
    centralEnergySupply : bool, optional
        If True, the profiles of the central energy supply are clustered as well. The default is False.

    Returns
    -------
    clusters : list of int
        Index of the medoid period of each cluster, in ascending order.
    clusterAssignments : dict
        Periods represented by each cluster, {medoid: [period indices]}.
    clusterWeights : dict
        Number of periods represented by each cluster, {medoid: number}.
    site : dict
        Site data with the clustered profiles added.
    district : list of dict
        Buildings with the clustered profiles added.
    heat_grid_data : dict
        Heat grid data with the clustered profiles added.
    """

    # number of time steps per period and number of complete periods in the year
    steps_per_period = int(time["clusterLength"] / time["timeResolution"])
    num_periods = len(site["T_e"]) // steps_per_period
    lengthArray = num_periods * steps_per_period

    # Profiles to cluster as (profile, weight, function that saves the clustered profile or None).
    # The weights indicate the focus of the clustering onto this profile. The relevant features are
    # 1. electricity demand of the buildings (each building with weight 1)
    # 2. outdoor temperature (weight = number of buildings)
    # 3. Windspeed (weight = number of buildings) - only if central WT exists
    # 4. Solar Radiation (weight = number of buildings if central PV or STC exist and + 1 for each building with PV or STC)
    # All other profiles have weight 0 and are only cut into the chosen periods. No profile is scaled.
    inputs = []

    def add(profile, weight, save):
        inputs.append((profile[0:lengthArray], weight, save))

    # Profiles of the buildings
    for building in district:
        user = building["user"]
        for name in BUILDING_PROFILES:
            add(getattr(user, name), 1 if name == "elec" else 0, _save_attribute(user, f"{name}_cluster"))

    # Individual car profiles (only the existing ones)
    clustered_cars = {}
    for i, building in enumerate(district):
        clustered_cars[i] = []
        for car in building["user"].individual_car_profiles:
            clustered_car = {key: car.get(key) for key in CAR_METADATA}
            for name in CAR_PROFILES:
                clustered_car[f"{name}_cluster"] = None
                if car[name] is not None:
                    add(car[name], 0, _save_item(clustered_car, f"{name}_cluster"))
            clustered_cars[i].append(clustered_car)

    # Central energy supply: network losses, pump power and renewable generation
    if centralEnergySupply:
        for name in HEAT_GRID_PROFILES:
            add(heat_grid_data[name], 0, _save_item(heat_grid_data, f"{name}_cluster"))
        generation = centralDevices["generation"]
        for name, device in CENTRAL_GENERATION.items():
            if centralDevices["capacities"][device]["cap"] > 0:
                profile = generation[name]
            else:
                # no central device exists; but array with just zeros leads to problem while clustering
                profile = np.ones(lengthArray) * sys.float_info.epsilon
            add(profile, 0, _save_item(generation, f"{name}_cluster"))

    # Wind speed and solar radiation (only relevant for clustering)
    wind_weight = len(district) if centralEnergySupply and centralDevices["capacities"]["WT"]["cap"] > 0 else 0
    add(site["wind_speed"], wind_weight, None)

    solar_weight = 0
    if centralEnergySupply:
        if (centralDevices["capacities"]["PV"]["cap"] > 0 or
                centralDevices["capacities"]["STC"]["cap"] > 0):
            solar_weight += len(district)
    for building in district:
        if (building["buildingFeatures"]["f_PV1"] > 0 or
                building["buildingFeatures"]["f_PV2"] > 0 or
                building["buildingFeatures"]["f_STC"] > 0):
            solar_weight += 1
    add(site["SunTotal"], solar_weight, None)

    # ambient temperature and soil temperature
    add(site["T_e"], len(district), _save_item(site, "T_e_cluster"))
    add(heat_grid_data["T_soil"], 0, _save_item(heat_grid_data, "T_soil_cluster"))

    # Perform clustering
    (newProfiles, nc, y, z, transfProfiles) = cm.cluster(np.array([profile for profile, _, _ in inputs]),
                                                         number_clusters=time["clusterNumber"],
                                                         len_cluster=int(steps_per_period),
                                                         weights=[weight for _, weight, _ in inputs],
                                                         scalings=[False] * len(inputs),
                                                         pyomo_config=pyomo_config)

    # save the clustered profiles
    for (_, _, save), clustered in zip(inputs, newProfiles):
        if save is not None:
            save(clustered)
    for i, building in enumerate(district):
        building["user"].individual_car_profiles_cluster = clustered_cars[i]

    # clusters
    clusters = []
    for i in range(len(y)):
        if y[i] != 0:
            clusters.append(i)

    # clusters and their assigned nodes (days/weeks/etc)
    clusterAssignments = {}
    for c in clusters:
        clusterAssignments[c] = []
        temp = z[c]
        for i in range(len(temp)):
            if temp[i] == 1:
                clusterAssignments[c].append(i)

    # weights indicating how often a cluster appears
    clusterWeights = {}
    for c in clusters:
        clusterWeights[c] = len(clusterAssignments[c])


    return clusters, clusterAssignments, clusterWeights, site, district, heat_grid_data


def select_profile_periods(profile, typedays, cluster_horizon, length_array):
    """
    Select representative periods from a full-year profile using medoid indices,
    instead of clustering the profile itself.

    Parameters
    ----------
    profile : array_like or None
        Profile of the whole year.
    typedays : array_like of int
        Indices of the periods to select (e.g. the medoids of the clustering).
    cluster_horizon : int
        Number of time steps per period.
    length_array : int
        Number of time steps that are used, a multiple of cluster_horizon. Later time steps
        (an incomplete last period) are ignored.

    Returns
    -------
    numpy.ndarray or None
        Selected periods with one row per period in the order of typedays, or None if the
        profile is None.
    """
    if profile is None:
        return None

    arr = np.asarray(profile)[0:length_array]
    num_periods = int(length_array / cluster_horizon)
    transformed = arr.reshape((cluster_horizon, num_periods), order="F")
    return np.array([transformed[:, int(day)] for day in typedays])


def apply_design_clustering(data):
    """
    Reuse the design-stage clustering (already computed while dimensioning the
    central devices) as the operational clustering, instead of independently
    re-clustering the per-building profiles a second time.

    The same profiles as in clustering_processing (with central energy supply) are cut into the
    design periods. Afterwards the clustered heating curves of the buildings are computed.

    Parameters
    ----------
    data : Datahandler
        Datahandler with the designed central devices, including
        centralDevices["capacities"]["cluster_meta"] (period length in time steps, medoid
        indices and cluster matrix of the design clustering).

    Returns
    -------
    None
        The clustered profiles are saved in data (as in clustering_processing), as well as
        data.clusters, data.clusterAssignments and data.clusterWeights.
    """
    print("Applying design clustering to operation profiles...")

    cluster_meta = data.centralDevices["capacities"]["cluster_meta"]
    cluster_horizon = int(cluster_meta["clusterLength"])
    typedays = np.asarray(cluster_meta["typedays"], dtype=int)
    cluster_matrix = np.asarray(cluster_meta["clusterMatrix"])

    length_array = len(data.site["T_e"]) // cluster_horizon * cluster_horizon  # complete periods only

    def select(profile):
        return select_profile_periods(profile, typedays, cluster_horizon, length_array)

    for building in data.district:
        user = building["user"]
        for name in BUILDING_PROFILES:
            setattr(user, f"{name}_cluster", select(getattr(user, name)))

        user.individual_car_profiles_cluster = []
        for car in user.individual_car_profiles:
            clustered_car = {key: car.get(key) for key in CAR_METADATA}
            for name in CAR_PROFILES:
                clustered_car[f"{name}_cluster"] = select(car.get(name))
            user.individual_car_profiles_cluster.append(clustered_car)

    for name in HEAT_GRID_PROFILES + ("T_soil",):
        data.heat_grid_data[f"{name}_cluster"] = select(data.heat_grid_data[name])

    for name in CENTRAL_GENERATION:
        data.centralDevices["generation"][f"{name}_cluster"] = select(data.centralDevices["generation"][name])

    data.site["T_e_cluster"] = select(data.site["T_e"])

    for building in data.district:
        envelope = building.get("envelope")
        if envelope is not None and hasattr(envelope, "compute_heating_curve"):
            envelope.compute_heating_curve(data.site, mode="clustered")

    # clusters / clusterAssignments / clusterWeights, keyed by original-period
    # index of each medoid (same convention as clustering_processing.clustering_processing)
    data.clusters = [int(medoid) for medoid in typedays]
    data.clusterAssignments = {}
    for medoid in data.clusters:
        data.clusterAssignments[medoid] = [
            i for i in range(cluster_matrix.shape[1]) if cluster_matrix[medoid][i] == 1
        ]
    data.clusterWeights = {
        medoid: len(data.clusterAssignments[medoid]) for medoid in data.clusters
    }
