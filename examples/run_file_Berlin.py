# -*- coding: utf-8 -*-

"""
Run this file for the connection to the Berlin heat cadastre.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import warnings



def run_opti(district_id, config_name):
    warnings.filterwarnings("ignore", category=FutureWarning)
    # Initialize District
    data = Datahandler(scenario_name = district_id, heat_map_berlin=True, env_path=".env.CONFIG." + config_name)
    topology_option = data.heat_grid_data["topology_option"]
    data.generateDistrictComplete(calcUserProfiles=True, saveUserProfiles=True, topology_option = topology_option)
    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calculateKPIs()

    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    # data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")
    return data


if __name__ == '__main__':
    # Name the district ID here --> should apply to the name of the csv-Input file
    district_id = "district_kulmer_str"
    # Name the config_name here --> should apply to the name of the .env file in the folder: data/envs
    config_name = "BERLIN"
    data = run_opti(district_id=district_id, config_name=config_name)


