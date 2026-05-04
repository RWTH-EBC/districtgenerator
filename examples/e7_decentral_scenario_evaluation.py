# -*- coding: utf-8 -*-

"""
This is the seventh example to perform an evaluation of a decentralized scenario.
Therefore the optimized operation of the devices is simulated and the key performance indicators are calculated.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example7_decentral_scenario_evaluation():

    # Initialize District
    # To use specific parameters, you can provide your own .env.CONFIG file in the data/env folder (see e6)
    # Refer to it like this: Datahandler(env_path=".env.CONFIG.EXAMPLE") and put it in ./data
    data = Datahandler(scenario_name = "example_decentral", env_path=".env.CONFIG.EXAMPLE")

    # We directly generate a complete district.
    # Note that now more information in the .csv file are needed.
    # In order to simulate the optimal operation of decentralized supply systems,
    # the further information must be added for each building:
    # The following options are available for “heater”: "HP" (heat pump), "BOI" (boiler), "BBOI" (biogas boiler),
    # "OBOI" (oil boiler),"H2BOI" (hydrogen boiler), "FC" (fuel cell), "CHP" (combined heat and power),
    # "EH" (electric heater), "GHP" (Gas Hybrid Heat Pump), "BHP" (Biomass Hybrid Heat Pump),
    # "H2HP" (Hydrogen Hybrid Heat Pump), "OHP" (Oil Hybrid Heat Pump)
    # If “cooling” is set to 1, a compression chiller (CC) is always used to meet the cooling demand.
    # “f_TES” corresponds to the number of liters per kW of heating capacity.
    # “f_BAT” is multiplied by the peak output of the PV system.
    # ‘f_PV1’ and “f_PV2” correspond to the proportion of the roof area on the respective sides of the roof. The main
    # side 1 is aligned according to “gamma_PV” ( O° corresponds to south orientation). The other side of the roof
    # is aligned 180° in the other direction.
    # A value between 0 and 1 can be entered for “EV”. The value indicates the share of electric vehicles in the
    # building compared to the total number of vehicles. The total number of vehicles is estimated based on
    # the number of occupants in the building. The electric vehicle capacity is choosen based on the proportion
    # of electric vehicles in Germany (see data/car_segment.json).
    # In addition, you can choose between the following charging behaviors: on_demand, intelligent and bi_directional
    data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=False)

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calculateKPIs()
    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")
    return data


if __name__ == '__main__':
    data = example7_decentral_scenario_evaluation()


