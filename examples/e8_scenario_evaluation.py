# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import warnings
#from districtgenerator.functions.industrie_optimierung_diagnose import pruefe_industrie_optimierung
from districtgenerator.functions import industrie_optimierung_bridge as wh_bridge



def example8_scenario_evaluation():
    warnings.filterwarnings("ignore", category=FutureWarning)


    # Initialize District
    data = Datahandler(scenario_name = "district_F_seed_1_buildings_30_industrie_G20", env_path=".env.CONFIG.PAPER")

    # We directly generate a complete district.
    # This includes the use of the EHDO tool to obtain an optimized energy central for neighborhoods.
    # EHDO is a tool for planning and designing complex energy systems.
    # Its key feature is the coupling of different sectors (e.g., electricity, heating, cooling).
    # In the early planning phases of energy supply concepts for neighborhoods,
    # the tool provides an initial assessment of the optimal system configuration, sizing,
    # and economic efficiency.
    # As input, EHDO requires data on energy demands and location (weather),
    # which are provided directly from the output of the district generator.
    # Additional information about the technologies to be considered for the dimensioning
    # of the energy central and the economic parameters are read from additional
    # .csv and .json data sources.

    topology_option = data.heat_grid_data["topology_option"]

    wh_bridge.WH_HP_TEST_FIXED_KW = 0.0

    data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=False, topology_option = topology_option, gen_cars=True)

    if getattr(data, "industry_optimization", None) is not None:
        capacities = data.centralDevices.get("capacities", {})

    print("\n[WH1-CHECK] Auslegung der Industrie-Wärmepumpe:")
    print(
        "  Ausgelegte Leistung [kW]:",
        capacities.get("industry_hp_capacity_kW", "NICHT VORHANDEN")
    )
    print(
        "  Jährliche Kapazitätskosten [EUR/a]:",
        capacities.get("industry_hp_annuity_EUR_a", "NICHT VORHANDEN")
    )

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    #if (
    #        data.heat_grid_data.get("heatgrid_generation") == "4G"
    #        and getattr(data, "industry_optimization", None) is not None
    #):
    #    pruefe_industrie_optimierung(data)

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calculateKPIs()

    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    data.KPIs.create_certificate(data=data, result_path=data.resultPath)
    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")
    return data


if __name__ == '__main__':
    data = example8_scenario_evaluation()


