"""
Script to ....
"""

import numpy as np
import districtgenerator.functions.clustering_medoid as cm
import sys

def clustering_processing(time, site, district, heat_grid_data, centralDevices, pyomo_config, centralEnergySupply=False):
    """
    Perform time series aggregation for profiles by using the k-medoids clustering algorithm.

    Returns
    -------
    None.
    """

    # calculate cluster time horizon
    initialArrayLenght = int(time["clusterLength"] / time["timeResolution"])
    num_clusters = len(site["T_e"]) // initialArrayLenght
    lengthArray = num_clusters * initialArrayLenght

    # adjust profiles with calculated array length
    adjProfiles = {}
    # loop over buildings
    for i, b in enumerate(district):
        adjProfiles[i] = {}
        adjProfiles[i]["elec"] = b["user"].elec[0:lengthArray]
        adjProfiles[i]["dhw"] = b["user"].dhw[0:lengthArray]
        adjProfiles[i]["heat"] = b["user"].heat[0:lengthArray]
        adjProfiles[i]["cooling"] = b["user"].cooling[0:lengthArray]
        adjProfiles[i]["occ"] = b["user"].occ[0:lengthArray]
        adjProfiles[i]["EV_carcharging_ondemand"] = b["user"].EV_carcharging_ondemand[0:lengthArray]
        adjProfiles[i]["EV_carprofile"] = b["user"].EV_carprofile[0:lengthArray]
        adjProfiles[i]["generationPV"] = b["user"].generationPV[0:lengthArray]
        adjProfiles[i]["generationSTC"] = b["user"].generationSTC[0:lengthArray]

        # Individual car profiles
        adjProfiles[i]["individual_cars"] = []

        for car in b["user"].individual_car_profiles:
            adj_car = {
                "availability_profile": car["availability_profile"][0:lengthArray] if car["availability_profile"] is not None else None,
                "consumption_profile_wh": car["consumption_profile_wh"][0:lengthArray] if car["consumption_profile_wh"] is not None else None,
                "on_demand_charging_profile_w": car["on_demand_charging_profile_w"][0:lengthArray] if car["on_demand_charging_profile_w"] is not None else None,
                "fuel_profile_l": car["fuel_profile_l"][0:lengthArray] if car["fuel_profile_l"] is not None else None
            }
            adjProfiles[i]["individual_cars"].append(adj_car)

    if centralEnergySupply == True:

        adjProfiles["losses_heating_network"] = heat_grid_data["total_losses_heating_network"][0:lengthArray]
        adjProfiles["losses_cooling_network"] = heat_grid_data["total_losses_cooling_network"][0:lengthArray]
        adjProfiles["pump_power"] = heat_grid_data["pump_power"][0:lengthArray]

        if centralDevices["capacities"]["WT"]["cap"] > 0:
            adjProfiles["generationCentralWT"] = centralDevices["generation"]["Wind"][0:lengthArray]
        else:
            # no central WT exists; but array with just zeros leads to problem while clustering
            adjProfiles["generationCentralWT"] = np.ones(lengthArray) * sys.float_info.epsilon

        if centralDevices["capacities"]["PV"]["cap"] > 0:
            adjProfiles["generationCentralPV"] = centralDevices["generation"]["PV"][0:lengthArray]
        else:
            # no central PV exists; but array with just zeros leads to problem while clustering
            adjProfiles["generationCentralPV"] = np.ones(lengthArray) * sys.float_info.epsilon

        if centralDevices["capacities"]["STC"]["cap"] > 0:
            adjProfiles["generationCentralSTC"] = centralDevices["generation"]["STC"][0:lengthArray]
        else:
            # no central STC exists; but array with just zeros leads to problem while clustering
            adjProfiles["generationCentralSTC"] = np.ones(lengthArray) * sys.float_info.epsilon

    # wind speed, solar radiance, ambient temperature and soil temperature
    adjProfiles["wind_speed"] = site["wind_speed"][0:lengthArray]
    adjProfiles["SunTotal"] = site["SunTotal"][0:lengthArray]
    adjProfiles["T_e"] = site["T_e"][0:lengthArray]
    adjProfiles["T_soil"] = heat_grid_data["T_soil"][0:lengthArray]

    # Prepare clustering
    # weights for clustering algorithm indicating the focus onto this profile
    # The relevant features for clustering are
    # 1. electricity demand of the buildings (each building with weight 1)
    # 2. outdoor temperature (weight = number of buildings)
    # 3. Windspeed (weight = number of buildings) - only if central WT exists
    # 4. Solar Radiation (weight = number of buildings if central PV or STC exist and + 1 for each building with PV or STC)
    # The profiles are not scaled currently. If otherwise desired set scalings.append(True) for the relevant profiles.

    inputsClustering, weights, scalings = [], [], []

    # loop over buildings
    for i in range(len(district)):
        inputsClustering.append(adjProfiles[i]["elec"])
        weights.append(1)
        scalings.append(False)

        inputsClustering.append(adjProfiles[i]["dhw"])
        weights.append(0)
        scalings.append(False)

        inputsClustering.append(adjProfiles[i]["heat"])
        weights.append(0)
        scalings.append(False)

        inputsClustering.append(adjProfiles[i]["cooling"])
        weights.append(0)
        scalings.append(False)

        inputsClustering.append(adjProfiles[i]["occ"])
        weights.append(0)
        scalings.append(False)

        inputsClustering.append(adjProfiles[i]["EV_carcharging_ondemand"])
        weights.append(0)      # This profile is not used at all for clustering
        scalings.append(False)  # This profile is not scaled

        inputsClustering.append(adjProfiles[i]["EV_carprofile"])
        weights.append(0)      # This profile is not used at all for clustering
        scalings.append(False)  # This profile is not scaled

        inputsClustering.append(adjProfiles[i]["generationPV"])
        weights.append(0)
        scalings.append(False)

        inputsClustering.append(adjProfiles[i]["generationSTC"])
        weights.append(0)
        scalings.append(False)

    # Add individual car profiles
    index_individual_cars_start = len(inputsClustering)
    for i in range(len(district)):
        for car in adjProfiles[i]["individual_cars"]:
            # 4 profiles per car

            if car["availability_profile"] is not None:
                inputsClustering.append(car["availability_profile"])
                weights.append(0) # Vorerst kein Gewicht
                scalings.append(False)

            if car["consumption_profile_wh"] is not None:
                inputsClustering.append(car["consumption_profile_wh"])
                weights.append(0)
                scalings.append(False)

            if car["on_demand_charging_profile_w"] is not None:
                inputsClustering.append(car["on_demand_charging_profile_w"])
                weights.append(0)
                scalings.append(False)

            if car["fuel_profile_l"] is not None:
                inputsClustering.append(car["fuel_profile_l"])
                weights.append(0)
                scalings.append(False)


    # Add central energy supply profiles
    index_central = len(inputsClustering) # Index of the first entry of central energy profiles

    if centralEnergySupply == True:

        # Heating and cooling networks losses
        inputsClustering.append(adjProfiles["losses_heating_network"])
        weights.append(0)
        scalings.append(False)

        inputsClustering.append(adjProfiles["losses_cooling_network"])
        weights.append(0)
        scalings.append(False)

        # central pump power
        inputsClustering.append(adjProfiles["pump_power"])
        weights.append(0)
        scalings.append(False)

        # central renewable generation
        inputsClustering.append(adjProfiles["generationCentralWT"])
        weights.append(0)
        scalings.append(False)

        inputsClustering.append(adjProfiles["generationCentralPV"])
        weights.append(0)
        scalings.append(False)

        inputsClustering.append(adjProfiles["generationCentralSTC"])
        weights.append(0)
        scalings.append(False)

    # Wind speed (only relevant for clustering)
    inputsClustering.append(adjProfiles["wind_speed"])
    if centralEnergySupply == True and centralDevices["capacities"]["WT"]["cap"] > 0: weights.append(len(district))
    else: weights.append(0)
    scalings.append(False)

    # Solar radiation (only relevant for clustering)
    inputsClustering.append(adjProfiles["SunTotal"])
    # determine weight for solar radiation
    solar_weight = 0
    if centralEnergySupply == True:
        if (centralDevices["capacities"]["PV"]["cap"] > 0 or
                centralDevices["capacities"]["STC"]["cap"] > 0):
            solar_weight += len(district)

    for i in range(len(district)):
        if (district[i]["buildingFeatures"]["f_PV1"] > 0 or
                district[i]["buildingFeatures"]["f_PV2"] > 0 or
                district[i]["buildingFeatures"]["f_STC"] > 0):
            solar_weight += 1

    weights.append(solar_weight)
    scalings.append(False)

    # ambient temperature
    inputsClustering.append(adjProfiles["T_e"])
    weights.append(len(district))
    scalings.append(False)

    # soil temperature
    inputsClustering.append(adjProfiles["T_soil"])
    weights.append(0)
    scalings.append(False)

    # Perform clustering
    (newProfiles, nc, y, z, transfProfiles) = cm.cluster(np.array(inputsClustering),
                                                         number_clusters=time["clusterNumber"],
                                                         len_cluster=int(initialArrayLenght),
                                                         weights=weights,
                                                         scalings=scalings,
                                                         pyomo_config=pyomo_config)

    # safe clustered profiles of all buildings
    for i in range(len(district)):
        index_house = int(9)    # number of profiles per building
        district[i]["user"].elec_cluster = newProfiles[index_house * i]
        district[i]["user"].dhw_cluster = newProfiles[index_house * i + 1]
        district[i]["user"].heat_cluster = newProfiles[index_house * i + 2]
        district[i]["user"].cooling_cluster = newProfiles[index_house * i + 3]
        district[i]["user"].occ_cluster = newProfiles[index_house * i + 4]
        district[i]["user"].EV_carcharging_ondemand_cluster = newProfiles[index_house * i + 5]
        district[i]["user"].EV_carprofile_cluster = newProfiles[index_house * i + 6]
        district[i]["user"].generationPV_cluster = newProfiles[index_house * i + 7]
        district[i]["user"].generationSTC_cluster = newProfiles[index_house * i + 8]

    # Get individual car profiles
    profile_counter = index_individual_cars_start
    for i in range(len(district)):
        district[i]["user"].individual_car_profiles_cluster = []
        for car in district[i]["user"].individual_car_profiles:
            profiles_car_counter = 0
            clustered_car_data = {
                # Get important metadata from the original
                "car_id": car.get("car_id"),
                "type": car.get("type"),
                "location": car.get("location"),
                "battery_capacity_wh": car.get("battery_capacity_wh"),
            }
            if car["availability_profile"] is not None:
                clustered_car_data["availability_profile_cluster"] = newProfiles[profile_counter]
                profiles_car_counter += 1
            else:
                clustered_car_data["availability_profile_cluster"] = None

            if car["consumption_profile_wh"] is not None:
                clustered_car_data["consumption_profile_wh_cluster"] = newProfiles[profile_counter + profiles_car_counter]
                profiles_car_counter += 1
            else:
                clustered_car_data["consumption_profile_wh_cluster"] = None

            if car["on_demand_charging_profile_w"] is not None:
                clustered_car_data["on_demand_charging_profile_w_cluster"] = newProfiles[profile_counter + profiles_car_counter]
                profiles_car_counter += 1
            else:
                clustered_car_data["on_demand_charging_profile_w_cluster"] = None

            if car["fuel_profile_l"] is not None:
                clustered_car_data["fuel_profile_l_cluster"] = newProfiles[profile_counter + profiles_car_counter]
                profiles_car_counter += 1
            else:
                clustered_car_data["fuel_profile_l_cluster"] = None

            district[i]["user"].individual_car_profiles_cluster.append(clustered_car_data)
            # Increment counter for the next car by 4
            profile_counter += profiles_car_counter


    if centralEnergySupply == True:
        heat_grid_data["total_losses_heating_network_cluster"] = newProfiles[index_central]
        heat_grid_data["total_losses_cooling_network_cluster"] = newProfiles[index_central + 1]
        heat_grid_data["pump_power_cluster"] = newProfiles[index_central + 2]
        centralDevices["generation"]["Wind_cluster"] = newProfiles[index_central + 3]
        centralDevices["generation"]["PV_cluster"] = newProfiles[index_central + 4]
        centralDevices["generation"]["STC_cluster"] = newProfiles[index_central + 5]

    site["T_e_cluster"] = newProfiles[-2]
    heat_grid_data["T_soil_cluster"] = newProfiles[-1]

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