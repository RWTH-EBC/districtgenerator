"""
District heating and cooling network calculation utilities.

This module aggregates thermal demands of heating- and cooling-network-connected buildings,
estimates network dimensions and costs, calculates buried-pipe thermal losses
and soil temperatures, annualizes investment costs, and determines constant or
weather-dependent network temperatures.

Most high-level functions operate on and mutate a DistrictGenerator ``data``
object in place and return the same object for workflow chaining.
"""

import os

import numpy as np
import pandas as pd
import math
import scipy.optimize as opt
import cmath

from districtgenerator.economics import annuity
from districtgenerator.energy_systems import technologies
from districtgenerator.environment.soil import calculate_soil_temperature

def heating_network(data):
    """
    Generate and characterize the district heating and cooling network.

    Aggregate the thermal demand of all buildings connected to the heat
    grid, size and cost the network, annualize its investment, calculate
    the soil temperature at pipe depth, determine network temperatures,
    and calculate time-resolved thermal losses.

    Parameters
    ----------
    data : object
        DistrictGenerator data object. The function expects, among others,
        the attributes ``district``, ``heat_grid_data``, ``time``,
        ``site``, ``pipe_data``, and ``ecoData``. Heating connections use
        ``heater="heat_grid"``; cooling connections use ``cooler="cooling_grid"``.
        The two networks can serve different sets of buildings.

    Returns
    -------
    data : object
        The same ``data`` object, updated in place. Added or updated
        entries in ``data.heat_grid_data`` include net heating and cooling
        demands, annual demand sums, network dimensions and costs,
        annualized costs, soil temperature, network temperatures, and
        thermal losses.
    """


    heat_grid_data = data.heat_grid_data
    timeData = data.time
    dt = timeData["timeResolution"] / timeData["dataResolution"]

    heating = np.zeros(len(data.district[0]["user"].heat))
    cooling = np.zeros(len(data.district[0]["user"].cooling))
    dhw = np.zeros(len(data.district[0]["user"].dhw))
    generationSTC = np.zeros(len(data.district[0]["user"].generationSTC))

    # LOAD DEMANDS
    for b in range(len(data.district)):
        # Only buildings connected to the heat grid can be supplied by it
        if data.district[b]["buildingFeatures"]["heater"] == "heat_grid":
            heating += data.district[b]["user"].heat / 1000  # kW
            if data.district[b]["buildingFeatures"].get("dhw_heater") is None:
                dhw += data.district[b]["user"].dhw / 1000  # kW
            generationSTC += data.district[b]["user"].generationSTC / 1000  # kW
        if technologies.get_cooling_supply(data.district[b]["buildingFeatures"]) == "cooling_grid":
            cooling += data.district[b]["user"].cooling / 1000  # kW


    heat_grid_data["net_heating_demand"] = np.maximum(heating + dhw - generationSTC, 0)  # kW
    heat_grid_data["net_cooling_demand"] = cooling  # kW
    heat_grid_data["net_sum_heating_demand"] = sum(heat_grid_data["net_heating_demand"]) * dt  # kWh/year
    heat_grid_data["net_sum_cooling_demand"] = sum(heat_grid_data["net_cooling_demand"]) * dt  # kWh/year

#    plot(data)
    data = calc_costs(data)
    data = calc_annual_investment(data)
    data = calculate_soil_temperature(data, dt)

#    Assign hot/cold network temperatures
    T_e = data.site["T_e"]  # outdoor temperature time series
    T_hot, T_cold = get_heating_network_temperatures(data, T_e)

    data.heat_grid_data["T_hot_heating_network"]["value"] = T_hot
    data.heat_grid_data["T_cold_heating_network"]["value"] = T_cold

    data = calculate_thermal_losses(data)


    return data

def calc_costs(data):
    """
    Calculates pipe dimensions and specific annualized costs for a district heating and cooling network

    Methodology:
    - Based on empirical formulas derived from statistical analysis of Danish district heating networks
      as described in Luis Sánchez-García et al. (2023), "Understanding effective width for district heating."
    - Pipe lengths and diameters are estimated using fitting formulas dependent on building density.

    Source:
    - Luis Sánchez-García et al. (2023), "Understanding effective width for district heating," Energy journal.

    Parameters
    ----------
    data : object
        DistrictGenerator data object.

    Returns
    -------
    data : object
        The same ``data`` object, updated in place with network lengths,
        selected nominal diameters, pipe dimensions, and total investment
        costs in ``data.heat_grid_data``.
    """

    grid = data.heat_grid_data
    area = data.site["district_area"]  # hectares
    connections = {
        "heating": [b for b in data.district if b["buildingFeatures"]["heater"] == "heat_grid"],
        "cooling": [b for b in data.district if technologies.get_cooling_supply(b["buildingFeatures"]) == "cooling_grid"],
    }
    pipe_cost = 0.0
    for kind, buildings in connections.items():
        active = bool(buildings) and grid[f"net_sum_{kind}_demand"] > 0
        if active and area <= 0:
            raise ValueError("district_area must be positive for thermal network sizing.")
        count = len(buildings)
        lengths = {
            "dist": (213 / (1 + 2.5 * np.exp(-0.34 * count)) - 25) * area if active else 0,
            "serv": (163 / (1 + 3.9 * np.exp(-0.34 * count)) - 11) * area if active else 0,
        }
        for section, length in lengths.items():
            grid[f"length_{kind}_{section}"] = length
            if not active:
                for dimension in ("DN", "da", "di", "Da"):
                    grid[f"{dimension}_{kind}_{section}"] = 0
                continue
            density = grid[f"net_sum_{kind}_demand"] / length / 1000 / 1000 * 3600
            diameter = (21.255 * np.log(density) + 48.064 if section == "dist"
                        else 19.983 * np.exp(0.021 * density))
            available = data.pipe_data[data.pipe_data["Nominal diameter (DN)"] >= diameter]
            if available.empty:
                raise ValueError(f"No pipe large enough for {kind} network {section}: DN {diameter}.")
            pipe = available.loc[available["Nominal diameter (DN)"].idxmin()]
            grid[f"DN_{kind}_{section}"] = pipe["Nominal diameter (DN)"]
            grid[f"da_{kind}_{section}"] = pipe["Outer diameter (pipe) (mm)"]
            grid[f"di_{kind}_{section}"] = pipe["Outer diameter (pipe) (mm)"] - 2 * pipe["Thickness (pipe) (mm)"]
            grid[f"Da_{kind}_{section}"] = pipe["Outer diameter (case) (mm)"]
            pipe_cost += (323.579 + 4.267 * grid[f"DN_{kind}_{section}"]) * length

    for section in ("dist", "serv"):
        grid[f"length_{section}"] = max(grid[f"length_heating_{section}"], grid[f"length_cooling_{section}"])

    substation_cost = 0.0
    for building in data.district:
        heat_peak = 0.0
        cool_peak = 0.0
        if building["buildingFeatures"]["heater"] == "heat_grid":
            heat_peak = building["envelope"].heatload / 1000
            if building["buildingFeatures"].get("dhw_heater") is None:
                heat_peak += building["envelope"].dhwpower / 1000
        if technologies.get_cooling_supply(building["buildingFeatures"]) == "cooling_grid":
            cool_peak = max(building["user"].cooling) / 1000
        substation_cost += max(heat_peak, cool_peak) * grid["C_subst"]
    grid["costs"] = pipe_cost + substation_cost
    return data


def calculate_thermal_losses(data):
    """
    Calculate thermal losses in heating grid and cooling grid, which are
    assumed to be consisting of separate pre-insulated pipes (single pipes).
    Thermal loss calculation is based on DIN EN 13941 pair of single pipes.
    The interaction between the pipes is accounted for using the multipole
    method, which models the heat loss as a superposition of symmetrical
    and antisymmetrical cases.

    Parameters
    ----------
    data : object
        DistrictGenerator data object containing network temperatures,
        soil temperatures, pipe dimensions and lengths, pipe spacing,
        burial depth, soil and insulation conductivities, substation loss
        percentage, and net heating/cooling demand profiles.

    Returns
    -------
    data : object
        The same ``data`` object, updated in place. The following
        time-series entries are written to ``data.heat_grid_data``:
        - total_losses_heating_network in kW.
        - total_losses_cooling_network in kW.

    """

    #%% Losses in the heating network

    k_soil = data.heat_grid_data["k_soil"]
    k_is = data.heat_grid_data["k_PUF"]
    if data.heat_grid_data["net_sum_heating_demand"] > 0:
        # get heating network parameters
        T_hot_heating_network = np.array(data.heat_grid_data["T_hot_heating_network"]["value"], dtype=float)
        T_cold_heating_network = np.array(data.heat_grid_data["T_cold_heating_network"]["value"], dtype=float)

        D_heating_network = data.heat_grid_data["D_heating_network"] # Distance between the centerlines of the supply and return pipelines

        k_soil = data.heat_grid_data["k_soil"]  # W/(m*K),
        k_is =data.heat_grid_data["k_PUF"]   # W/(m*K)
        Z_c =  data.heat_grid_data["grid_depth"] + 0.069 * k_soil
        b = np.log((1+(2*Z_c/D_heating_network)**2)**0.5)

        Ts_heating_network = (T_hot_heating_network + T_cold_heating_network) / 2
        Ta_heating_network = (T_hot_heating_network - T_cold_heating_network) / 2

        # Losses in the distribution pipes

        a_dist = np.log(4 * Z_c / (data.heat_grid_data["Da_heating_dist"]/1000))
        beta_dist =  k_soil / k_is * np.log((data.heat_grid_data["Da_heating_dist"]) / data.heat_grid_data["da_heating_dist"])

        ks_heating_network_dist = (a_dist + beta_dist + b)**-1
        ka_heating_network_dist = (a_dist + beta_dist - b)**-1

        qs_heating_network_dist = (Ts_heating_network- data.heat_grid_data["T_soil"]) * 2 * np.pi * k_soil * ks_heating_network_dist  # W/m
        qa_heating_network_dist = (Ta_heating_network) * 2 * np.pi * k_soil * ka_heating_network_dist          # W/m

        losses_hotpipe_heating_network_dist = (qs_heating_network_dist + qa_heating_network_dist) * data.heat_grid_data["length_heating_dist"]
        losses_coldpipe_heating_network_dist = (qs_heating_network_dist - qa_heating_network_dist) * data.heat_grid_data["length_heating_dist"]
        losses_heating_network_dist = (losses_hotpipe_heating_network_dist + losses_coldpipe_heating_network_dist) / 1000  # kW

        # Losses in the service pipes

        a_serv = np.log(4 * Z_c / (data.heat_grid_data["Da_heating_serv"]/1000))
        beta_serv =  k_soil / k_is * np.log((data.heat_grid_data["Da_heating_serv"]) / data.heat_grid_data["da_heating_serv"])

        ks_heating_network_serv = (a_serv + beta_serv + b)**-1
        ka_heating_network_serv = (a_serv + beta_serv - b)**-1

        qs_heating_network_serv = (Ts_heating_network- data.heat_grid_data["T_soil"]) * 2 * np.pi * k_soil * ks_heating_network_serv  # W/m
        qa_heating_network_serv = (Ta_heating_network) * 2 * np.pi * k_soil * ka_heating_network_serv          # W/m

        losses_hotpipe_heating_network_serv = (qs_heating_network_serv + qa_heating_network_serv) * data.heat_grid_data["length_heating_serv"]
        losses_coldpipe_heating_network_serv = (qs_heating_network_serv - qa_heating_network_serv) * data.heat_grid_data["length_heating_serv"]
        losses_heating_network_serv = (losses_hotpipe_heating_network_serv + losses_coldpipe_heating_network_serv) / 1000  # kW

        # Losses in the substations
        losses_substations_heating = data.heat_grid_data["h_loss_subst"]/100 * data.heat_grid_data["net_heating_demand"]

        # total losses in the heating network
        data.heat_grid_data["total_losses_heating_network"] = losses_heating_network_dist + losses_heating_network_serv + losses_substations_heating # kW

    else:
        data.heat_grid_data["total_losses_heating_network"] = np.zeros(len(data.heat_grid_data["T_soil"]))

    #%% Losses in the cooling network

    # get cooling network parameters (if a network exists)
    if data.heat_grid_data["net_sum_cooling_demand"] > 0:
        T_hot_cooling_network = data.heat_grid_data["T_hot_cooling_network"]
        T_cold_cooling_network = data.heat_grid_data["T_cold_cooling_network"]

        D_cooling_network = data.heat_grid_data["D_cooling_network"] # distance between hot and cold pipe

        Z_c =  data.heat_grid_data["grid_depth"] + 0.069 * k_soil
        b = np.log((1+(2*Z_c/D_cooling_network)**2)**0.5)

        Ts_cooling_network = (T_hot_cooling_network + T_cold_cooling_network) / 2
        Ta_cooling_network = (T_hot_cooling_network - T_cold_cooling_network) / 2

        a_dist = np.log(4 * Z_c / (data.heat_grid_data["Da_cooling_dist"]/1000))
        beta_dist =  k_soil / k_is * np.log((data.heat_grid_data["Da_cooling_dist"]) / data.heat_grid_data["da_cooling_dist"])

        ks_cooling_network_dist = (a_dist + beta_dist + b)**-1
        ka_cooling_network_dist = (a_dist + beta_dist - b)**-1

        qs_cooling_network_dist = (Ts_cooling_network- data.heat_grid_data["T_soil"]) * 2 * np.pi * k_soil * ks_cooling_network_dist  # W/m
        qa_cooling_network_dist = (Ta_cooling_network) * 2 * np.pi * k_soil * ka_cooling_network_dist          # W/m

        losses_hotpipe_cooling_network_dist = (qs_cooling_network_dist + qa_cooling_network_dist) * data.heat_grid_data["length_cooling_dist"]
        losses_coldpipe_cooling_network_dist = (qs_cooling_network_dist - qa_cooling_network_dist) * data.heat_grid_data["length_cooling_dist"]
        losses_cooling_network_dist = (losses_hotpipe_cooling_network_dist + losses_coldpipe_cooling_network_dist) / 1000  # kW

        # Losses in the service pipes

        a_serv = np.log(4 * Z_c / (data.heat_grid_data["Da_cooling_serv"]/1000))
        beta_serv = k_soil / k_is * np.log((data.heat_grid_data["Da_cooling_serv"]) / data.heat_grid_data["da_cooling_serv"])

        ks_cooling_network_serv = (a_serv + beta_serv + b) ** -1
        ka_cooling_network_serv = (a_serv + beta_serv - b) ** -1

        qs_cooling_network_serv = (Ts_cooling_network - data.heat_grid_data["T_soil"]) * 2 * np.pi * k_soil * ks_cooling_network_serv  # W/m
        qa_cooling_network_serv = (Ta_cooling_network) * 2 * np.pi * k_soil * ka_cooling_network_serv  # W/m

        losses_hotpipe_cooling_network_serv = (qs_cooling_network_serv + qa_cooling_network_serv) * data.heat_grid_data["length_cooling_serv"]
        losses_coldpipe_cooling_network_serv = (qs_cooling_network_serv - qa_cooling_network_serv) * data.heat_grid_data["length_cooling_serv"]
        losses_cooling_network_serv = (losses_hotpipe_cooling_network_serv + losses_coldpipe_cooling_network_serv) / 1000  # kW

        # Losses in the substations
        losses_substations_cooling = data.heat_grid_data["h_loss_subst"] / 100 * data.heat_grid_data["net_cooling_demand"]

    else:
        losses_cooling_network_dist = np.zeros(len(data.heat_grid_data["T_soil"]))
        losses_cooling_network_serv = np.zeros(len(data.heat_grid_data["T_soil"]))
        losses_substations_cooling = np.zeros(len(data.heat_grid_data["T_soil"]))

    data.heat_grid_data["total_losses_cooling_network"] = losses_cooling_network_dist + losses_cooling_network_serv + losses_substations_cooling # kW

    return data

def calc_annual_investment(data):
    """
    Calculation of total investment costs including replacements (based on VDI 2067-1, pages 16-17).

    Parameters
    ----------
    dev : dictionary
        technology parameter
    param : dictionary
        economic parameters

    Returns
    -------
    annualized fix and variable investment
    """

    observation_time = data.ecoData["observation_time"]
    interest_rate = data.ecoData["interest_rate"]

    data.heat_grid_data["ann_factor"] = annuity.annuity_factor(data.heat_grid_data["life_time"], observation_time,
                                                               interest_rate)
    data.heat_grid_data["CRF"] = annuity.capital_recovery_factor(observation_time, interest_rate)
    data.heat_grid_data["ann_costs"] = data.heat_grid_data["costs"] * data.heat_grid_data["ann_factor"] # €/a
    data.heat_grid_data["om_costs"] = data.heat_grid_data["C_OM"] * data.heat_grid_data["net_sum_heating_demand"]/1000 + data.heat_grid_data["C_OM"] * data.heat_grid_data["net_sum_cooling_demand"]/1000 # €/a

    return data

def heating_curve(T_e, T_supply_min, T_supply_max, T_return_min, T_return_max):
    """
    Calculate outdoor-temperature-dependent supply and return temperatures.

    Linearly interpolate supply temperature and supply-return temperature
    difference between outdoor temperatures of -10 °C and 15 °C. Values
    outside this interval are clamped to the corresponding endpoint by
    :func:`numpy.interp`.

    Parameters
    ----------
    T_e : array_like
        Outdoor air temperature [°C].
    T_supply_min : float
        Supply temperature [°C] assigned at ``T_e = -10 °C``.
    T_supply_max : float
        Supply temperature [°C] assigned at ``T_e = 15 °C``.
    T_return_min : float
        Return temperature [°C] used to define the supply-return
        temperature difference at ``T_e = -10 °C``.
    T_return_max : float
        Return temperature [°C] used to define the supply-return
        temperature difference at ``T_e = 15 °C``.

    Returns
    -------
    T_supply : numpy.ndarray
        Interpolated supply-temperature series [°C].
    T_return : numpy.ndarray
        Interpolated return-temperature series [°C].
    """
    T_e = np.array(T_e, dtype=float)

    # Outdoor temp limits
    T_min, T_max = -10, 15

    # Supply-return ΔT at min and max outdoor temp
    dT_min = T_supply_min - T_return_min
    dT_max = T_supply_max - T_return_max

    # Interpolate supply temperature
    T_supply = np.interp(T_e, [T_min, T_max], [T_supply_min, T_supply_max])

    # Interpolate temperature difference
    dT = np.interp(T_e, [T_min, T_max], [dT_min, dT_max])

    # Return temperature
    T_return = T_supply - dT

    return T_supply, T_return

def get_heating_network_temperatures(data, T_e=None):
    """
    Return heating-network supply and return temperatures.
    Select either constant temperatures or an outdoor-temperature-dependent
    heating curve according to the configured network generation and
    temperature mode.

    Parameters
    ----------
    data : object
        DistrictGenerator data object containing ``data.heat_grid_data``.
        The keys ``"generation"`` and ``"temperature_mode"`` determine
        which temperature configuration is selected.
    T_e : array_like, optional
        Outdoor air temperature [°C]. Required when
        ``temperature_mode == "heating_curve"`` and ignored in constant
        mode.

    Returns
    -------
    T_hot : numpy.ndarray
        Heating-network supply temperature [°C]. In constant mode this is
        a zero-dimensional NumPy array containing the configured scalar;
        in heating-curve mode it follows the shape of ``T_e``.
    T_cold : numpy.ndarray
        Heating-network return temperature [°C], with the same dimensional
        behavior as ``T_hot``.
    """
    gen = data.heat_grid_data["generation"]               # "3rd", "4th", "5th"
    mode = data.heat_grid_data["temperature_mode"]        # "constant" or "heating_curve"

    # --- CONSTANT MODE ---------------------------------------------------------
    if mode == "constant":
        T_hot = data.heat_grid_data["T_hot_heating_network"]["constant"][gen]
        T_cold = data.heat_grid_data["T_cold_heating_network"]["constant"][gen]
        return np.array(T_hot), np.array(T_cold)

    # --- HEATING CURVE MODE ----------------------------------------------------
    if mode == "heating_curve":
        if T_e is None:
            raise ValueError("T_e must be supplied when temperature_mode = 'heating_curve'.")

        # Supply temperatures
        T_supply_min = data.heat_grid_data["T_hot_heating_network"]["heating_curve"]["min"][gen]
        T_supply_max = data.heat_grid_data["T_hot_heating_network"]["heating_curve"]["max"][gen]

        # Return temperatures
        T_return_min = data.heat_grid_data["T_cold_heating_network"]["heating_curve"]["min"][gen]
        T_return_max = data.heat_grid_data["T_cold_heating_network"]["heating_curve"]["max"][gen]

        T_supply, T_return = heating_curve(
            T_e,
            T_supply_min, T_supply_max,
            T_return_min, T_return_max
        )

        return T_supply, T_return

    raise ValueError(f"Unknown temperature_mode: {mode}")


def load_pipe_data(generation, pipe_file_path):
    """
    Load the pipe catalogue of the selected heat grid generation.

    KMR pipes are used for the 3rd generation, PMR pipes for the 4th generation with KMR
    pipes above DN 150, and PE pipes for the 5th generation.

    Parameters
    ----------
    generation : str
        Heat grid generation, "3rd", "4th" or "5th".
    pipe_file_path : str
        Folder of the pipe specification files.

    Returns
    -------
    pandas.DataFrame or dict
        Pipe specifications, or an empty dict for an unknown generation.
    """
    pipe_data = {}

    # select the pipe file based on the generation selection
    # KMR for 3rd generation; PMR for 4th generation; PE for 5th generation
    if generation == "3rd":
        csv_path = os.path.join(pipe_file_path, 'pipe_specifications_KMR.csv')
        pipe_data = pd.read_csv(csv_path, sep=";")

    elif generation == "4th":
        pmr_path = os.path.join(pipe_file_path, 'pipe_specifications_PMR.csv')
        pmr_data = pd.read_csv(pmr_path, sep=";")
        # add KMR pipes for DN > 150
        kmr_path = os.path.join(pipe_file_path, 'pipe_specifications_KMR.csv')
        kmr_data = pd.read_csv(kmr_path, sep=";")
        kmr_data = kmr_data[kmr_data["Nominal diameter (DN)"] > 150]
        pipe_data = pd.concat([pmr_data, kmr_data], ignore_index=True)

    elif generation == "5th":
        csv_path = os.path.join(pipe_file_path, 'pipe_specifications_PE.csv')
        pipe_data = pd.read_csv(csv_path, sep=";")
    else:
        print("Please select from the 3rd, 4th, or 5th generation and enter it into the config file.")

    return pipe_data


def has_thermal_grid(district):
    """
    Check whether any building of the district is supplied by a heat grid or a cooling grid.

    Parameters
    ----------
    district : list of dict
        Buildings of the district.

    Returns
    -------
    bool
        True if a thermal network is needed.
    """
    # Check if district uses central energy supply (heat grid)
    has_heat_grid = any(
        building["buildingFeatures"]["heater"] == "heat_grid"
        for building in district)
    has_cooling_grid = any(
        technologies.get_cooling_supply(building["buildingFeatures"]) == "cooling_grid"
        for building in district)
    return has_heat_grid or has_cooling_grid


def design_thermal_network(data):
    """
    Design the thermal network of the district with the simple network model.

    If no building is connected to a thermal network, for example when only an energy
    hub is designed, the network losses, pump power and costs are set to zero.

    Parameters
    ----------
    data : Datahandler
        Datahandler of the district after the demand generation.

    Returns
    -------
    None.
    """
    # Verify geometry data (district_parameters)

    # --- Check if building positions are available and valid ---
    missing_positions = (
            "position" not in data.scenario.columns
            or data.scenario["position"].isnull().any()
            or any(
        not isinstance(p, tuple) or len(p) != 2 or not all(isinstance(x, (int, float)) for x in p)
        for p in data.scenario["position"]))

    if has_thermal_grid(data.district):
        if missing_positions:
            print("No district geometry found — running simple thermal network design.")
            heating_network(data)
        else:
            print("The districtgenerator currently does not support thermal networks based on building positions — running simple thermal network design.")
            heating_network(data)

            # print("Generating and optimizing heating network...")
            # self.generateNetwork(topology_option="node")
            # self.prepareClusteringInputs()
            # self.optimization_heatingnetwork()

    else: 
        ts_length = len(data.district[0]["user"].heat)
        data.heat_grid_data["total_losses_heating_network"] = np.zeros(ts_length)
        data.heat_grid_data["total_losses_cooling_network"] = np.zeros(ts_length)
        data.heat_grid_data["pump_power"] = np.zeros(ts_length)
        data.heat_grid_data["ann_costs"] = 0
        data.heat_grid_data["om_costs"] = 0
