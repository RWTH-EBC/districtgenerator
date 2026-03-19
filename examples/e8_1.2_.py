# -*- coding: utf-8 -*-

"""
Optimized scenario evaluation that avoids redundant calculations.

For comparing multiple business models (BMs) on the same district:
- District generation, demands, and heating network are calculated ONCE
- Only optimization and KPIs are recalculated per BM

This significantly reduces computation time when evaluating multiple BMs.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import warnings
import pickle
import os
import copy


def save_district_state(data, filepath):
    """
    Save the district state after expensive calculations (network, clustering).

    This saves everything needed to run optimization without regenerating
    the heating network.

    Parameters
    ----------
    data : Datahandler
        The data object after generateDistrictComplete.
    filepath : str
        Path to save the pickle file.
    """
    state = {
        # Core district data
        'district': data.district,
        'scenario_name': data.scenario_name,
        'scenario': data.scenario,

        # Site and environment
        'site': data.site,
        'time': data.time,

        # Device data
        'decentral_device_data': data.decentral_device_data,
        'central_device_data': data.central_device_data,
        'centralDevices': getattr(data, 'centralDevices', {}),

        # Grid data
        'heat_grid_data': data.heat_grid_data,
        'el_grid_data': data.el_grid_data,
        'pipe_data': data.pipe_data,

        # Clustering results
        'clusters': getattr(data, 'clusters', None),
        'clusterAssignments': getattr(data, 'clusterAssignments', None),
        'clusterWeights': getattr(data, 'clusterWeights', None),
        'cluster_meta': getattr(data, 'cluster_meta', None),

        # Pipeline topology (expensive to compute)
        'pipeline_nodes': getattr(data, 'pipeline_nodes', None),
        'pipeline_topology': getattr(data, 'pipeline_topology', None),
        'pipeline': getattr(data, 'pipeline', {}),

        # Other necessary attributes
        'physics': data.physics,
        'calendar': data.calendar,
        'design_building_data': data.design_building_data,
        'params_ehdo_technical': data.params_ehdo_technical,
        'params_ehdo_model': data.params_ehdo_model,
        'pyomo_config': data.pyomo_config,
        'initial_day': data.initial_day,
        'total_building_area': data.total_building_area,
        'building_dict': data.building_dict,
        'counter': data.counter,
    }

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'wb') as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"District state saved to {filepath}")


def load_district_state(data, filepath):
    """
    Load a previously saved district state.

    Parameters
    ----------
    data : Datahandler
        The data object to populate.
    filepath : str
        Path to the pickle file.

    Returns
    -------
    bool
        True if loaded successfully, False otherwise.
    """
    if not os.path.exists(filepath):
        return False

    with open(filepath, 'rb') as f:
        state = pickle.load(f)

    # Restore all attributes
    data.district = state['district']
    data.scenario_name = state['scenario_name']
    data.scenario = state['scenario']
    data.site = state['site']
    data.time = state['time']
    data.decentral_device_data = state['decentral_device_data']
    data.central_device_data = state['central_device_data']
    data.centralDevices = state.get('centralDevices', {})
    data.heat_grid_data = state['heat_grid_data']
    data.el_grid_data = state['el_grid_data']
    data.pipe_data = state['pipe_data']
    data.clusters = state.get('clusters')
    data.clusterAssignments = state.get('clusterAssignments')
    data.clusterWeights = state.get('clusterWeights')
    data.cluster_meta = state.get('cluster_meta')
    data.pipeline_nodes = state.get('pipeline_nodes')
    data.pipeline_topology = state.get('pipeline_topology')
    data.pipeline = state.get('pipeline', {})
    data.physics = state['physics']
    data.calendar = state['calendar']
    data.design_building_data = state['design_building_data']
    data.params_ehdo_technical = state['params_ehdo_technical']
    data.params_ehdo_model = state['params_ehdo_model']
    data.pyomo_config = state['pyomo_config']
    data.initial_day = state['initial_day']
    data.total_building_area = state['total_building_area']
    data.building_dict = state['building_dict']
    data.counter = state['counter']

    print(f"District state loaded from {filepath}")
    return True


def run_single_scenario(scenario_name, env_path, topology_option="road",
                        calcUserProfiles=False, saveUserProfiles=False,
                        force_regenerate=False):
    """
    Generate or load a district scenario.

    Parameters
    ----------
    scenario_name : str
        Name of the scenario.
    env_path : str
        Path to the environment config file.
    topology_option : str
        Network topology option ("node" or "road").
    calcUserProfiles : bool
        Whether to calculate new user profiles.
    saveUserProfiles : bool
        Whether to save user profiles.
    force_regenerate : bool
        If True, regenerate even if cached state exists.

    Returns
    -------
    Datahandler
        The data object with district generated.
    """
    warnings.filterwarnings("ignore", category=FutureWarning)

    # Initialize District
    data = Datahandler(scenario_name=scenario_name, env_path=env_path)

    # Check for cached state
    cache_path = os.path.join(data.resultPath, 'cache', f"{scenario_name}_district_state.pkl")

    if not force_regenerate and load_district_state(data, cache_path):
        print(f"Loaded cached district state for '{scenario_name}'")
        # Still need to recalculate ecoData for potentially different BM
        data.all_sim_ecoData = data.calculate_ecoData_per_cluster()
        return data

    # Generate full district (expensive operations)
    print(f"Generating district '{scenario_name}' from scratch...")
    data.generateDistrictComplete(
        calcUserProfiles=calcUserProfiles,
        saveUserProfiles=saveUserProfiles,
        topology_option=topology_option
    )

    # Save state for future runs
    save_district_state(data, cache_path)

    return data


def run_optimization_for_bm(data, business_model, env_path):
    """
    Run optimization and KPI calculation for a specific business model.

    This reuses the already-generated district and only recalculates
    the BM-specific parts.

    Parameters
    ----------
    data : Datahandler
        The data object with district already generated.
    business_model : str
        Name of the business model (e.g., "mieterstrom", "contracting").
    env_path : str
        Path to the environment config file for this BM.

    Returns
    -------
    Datahandler
        The data object with optimization results for this BM.
    """
    from districtgenerator.data_handling.config import load_global_config

    # Load BM-specific config
    bm_config = load_global_config(env_file=env_path)

    # Update ecoData with BM-specific settings
    data.ecoData = {
        "business_model": bm_config.eco.business_model,
        "observation_time": bm_config.eco.observation_time,
        "interest_rate": bm_config.eco.interest_rate,
        "electricity_price": bm_config.eco.electricity_price,
        "electricity_price_increase": bm_config.eco.electricity_price_increase,
        "gas_price": bm_config.eco.gas_price,
        "gas_price_increase": bm_config.eco.gas_price_increase,
        "co2_price": bm_config.eco.co2_price,
        "co2_price_increase": bm_config.eco.co2_price_increase,
        "co2_el": bm_config.eco.co2_el,
        "co2_el_decrease": bm_config.eco.co2_el_decrease,
        "co2_gas": bm_config.eco.co2_gas,
        "electricity_feedin_price": bm_config.eco.electricity_feedin_price,
        "biomass_price": bm_config.eco.biomass_price,
        "biomass_price_increase": bm_config.eco.biomass_price_increase,
        "co2_biomass": bm_config.eco.co2_biomass,
        "subsidy_pv": bm_config.eco.subsidy_pv,
        "hydrogen_price": bm_config.eco.hydrogen_price,
        "hydrogen_price_increase": bm_config.eco.hydrogen_price_increase,
        "co2_hydrogen": bm_config.eco.co2_hydrogen,
        "oil_price": bm_config.eco.oil_price,
        "oil_price_increase": bm_config.eco.oil_price_increase,
        "co2_oil": bm_config.eco.co2_oil,
        "waste_price": bm_config.eco.waste_price,
        "waste_price_increase": bm_config.eco.waste_price_increase,
        "co2_waste": bm_config.eco.co2_waste,
        "district_heating_price": bm_config.eco.district_heating_price,
        "district_heating_price_increase": bm_config.eco.district_heating_price_increase,
        "co2_district_heating": bm_config.eco.co2_district_heating,
        "interpolation_points": bm_config.eco.interpolation_points,
    }

    # Recalculate economic data for simulated years
    data.all_sim_ecoData = data.calculate_ecoData_per_cluster()

    print(f"\n{'='*60}")
    print(f"Running optimization for Business Model: {business_model}")
    print(f"{'='*60}")

    # Run optimization
    data.optimizationClusters()

    # Calculate KPIs
    data.calculateKPIs()

    return data


def compare_business_models(scenario_name, bm_configs, topology_option="road",
                            calcUserProfiles=False, saveUserProfiles=False,
                            force_regenerate=False, plot_years=None):
    """
    Compare multiple business models on the same district scenario.

    This is the main entry point for BM comparison. It generates the district
    once and then runs optimization for each BM.

    Parameters
    ----------
    scenario_name : str
        Name of the scenario.
    bm_configs : dict
        Dictionary mapping BM names to their env_path.
        Example: {"mieterstrom": ".env.CONFIG.Mietstrom",
                  "contracting": ".env.CONFIG.Contracting"}
    topology_option : str
        Network topology option.
    calcUserProfiles : bool
        Whether to calculate new user profiles.
    saveUserProfiles : bool
        Whether to save user profiles.
    force_regenerate : bool
        If True, regenerate district even if cached.
    plot_years : list or int, optional
        Years to plot. If None, plots first year only.

    Returns
    -------
    dict
        Dictionary mapping BM names to their data objects with results.
    """
    from districtgenerator.classes.plots_balances import plot_all, plot_single_year

    results = {}

    # Use first BM config to generate base district
    first_bm = list(bm_configs.keys())[0]
    first_env = bm_configs[first_bm]

    print(f"\n{'#'*60}")
    print(f"# Generating base district using '{first_bm}' config")
    print(f"{'#'*60}\n")

    # Generate district once
    base_data = run_single_scenario(
        scenario_name=scenario_name,
        env_path=first_env,
        topology_option=topology_option,
        calcUserProfiles=calcUserProfiles,
        saveUserProfiles=saveUserProfiles,
        force_regenerate=force_regenerate
    )

    # Run optimization for each BM
    for bm_name, env_path in bm_configs.items():
        print(f"\n{'#'*60}")
        print(f"# Processing Business Model: {bm_name}")
        print(f"{'#'*60}\n")

        # Create a deep copy for this BM to avoid interference
        # Note: For memory efficiency, we could also just re-run on same object
        # but keeping copies allows comparing results afterwards
        data = copy.deepcopy(base_data)

        # Run BM-specific optimization
        data = run_optimization_for_bm(data, bm_name, env_path)

        # Generate plots
        if plot_years is None:
            plot_single_year(data, year=0)
        elif isinstance(plot_years, list):
            plot_all(data, years=plot_years)
        else:
            plot_single_year(data, year=plot_years)

        results[bm_name] = data

    print(f"\n{'#'*60}")
    print(f"# Comparison complete!")
    print(f"# Processed {len(bm_configs)} business models")
    print(f"{'#'*60}\n")

    return results


def example8_scenario_evaluation():
    """
    Original single-BM evaluation (backwards compatible).
    """
    warnings.filterwarnings("ignore", category=FutureWarning)
    from districtgenerator.classes.plots_balances import plot_single_year

    # Initialize District
    data = Datahandler(scenario_name="district_F_buildings_9", env_path=".env.CONFIG.Mietstrom")

    topology_option = data.heat_grid_data["topology_option"]

    data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=False, topology_option=topology_option)

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators
    data.calculateKPIs()

    # Create balance plots
    plot_single_year(data, year=0)

    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")
    return data


def example8_multi_bm_evaluation():
    """
    Example: Compare multiple business models on the same district.

    The heating network is calculated ONCE, then reused for all BMs.
    """
    # Define business models to compare
    bm_configs = {
        "mieterstrom": ".env.CONFIG.Mietstrom",
        "contracting": ".env.CONFIG.Contracting",
        "cooperative": ".env.CONFIG.Cooperative",
        "kundenanlage": ".env.CONFIG.Kundenanlage",
    }

    # Run comparison
    results = compare_business_models(
        scenario_name="district_F_buildings_9",
        bm_configs=bm_configs,
        topology_option="road",
        calcUserProfiles=False,
        saveUserProfiles=False,
        force_regenerate=False,  # Use cached district if available
        plot_years=0  # Plot only first support year
    )

    # Print summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)

    for bm_name, data in results.items():
        print(f"\n{bm_name}:")
        if hasattr(data, 'KPIs') and data.KPIs is not None:
            if hasattr(data.KPIs, 'tac'):
                print(f"  TAC: {data.KPIs.tac:,.2f} EUR/a")
            if hasattr(data.KPIs, 'lcoh'):
                print(f"  LCOH: {data.KPIs.lcoh:.4f} EUR/kWh")
            if hasattr(data.KPIs, 'co2_total'):
                print(f"  CO2: {data.KPIs.co2_total:,.2f} kg/a")

    return results


if __name__ == '__main__':
    # Option 1: Single BM evaluation (original behavior)
    # data = example8_scenario_evaluation()

    # Option 2: Multi-BM comparison (recommended for BM studies)
    results = example8_multi_bm_evaluation()