# -*- coding: utf-8 -*-

"""
This code runs through all """

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import warnings
import numpy as np
import pandas as pd
import os
import json
import time

SRCPATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def example9_economic_analysis():
    warnings.filterwarnings("ignore", category=FutureWarning)

    n_runs = 10  # Number of runs for averaging

    building_types = ['SFH', 'TH', 'MFH', 'AB'] #Building types to analyze, all types: ['SFH', 'TH', 'MFH', 'AB']

    heater_Types = ['H2BOI', 'BBOI', 'EH', 'HP', 'GHP', 'BHP', 'OHP', 'H2HP']  # Heater types to analyze, all types: ['H2BOI', 'BBOI', 'EH', 'HP', 'GHP', 'BHP', 'OHP', 'HBOI', 'H2HP']

    building_ages = {
        'SFH': [
            '1860 - 1918', '1919 - 1948', '1949 - 1957', '1958 - 1968', '1969 - 1978', 
            '1979 - 1983', '1984 - 1994', '1995 - 2001', '2002 - 2009', '2010 - 2015', '2016 - 2023'
        ],
        'TH': [
            '1860 - 1918', '1919 - 1948', '1949 - 1957', '1958 - 1968', '1969 - 1978', 
            '1979 - 1983', '1984 - 1994', '1995 - 2001', '2002 - 2009', '2010 - 2015', '2016 - 2023'
        ],
        'MFH': [
            '1860 - 1918', '1919 - 1948', '1949 - 1957', '1958 - 1968', '1969 - 1978', 
            '1979 - 1983', '1984 - 1994', '1995 - 2001', '2002 - 2009', '2010 - 2015', '2016 - 2023'
        ],
        'AB': [
            '1860 - 1918', '1919 - 1948', '1949 - 1957', '1958 - 1968', '1969 - 1978'
        ]
    }

    def map_building_area(b_type):
        area_mapping = {
            'SFH': 150,
            'TH': 120,
            'MFH': 1000,
            'AB': 2000
        }
        return area_mapping.get(b_type, None)
    
    def map_building_age(building_age_span):
        age_mapping = {
            '1860 - 1918': 1900,
            '1919 - 1948': 1935,
            '1949 - 1957': 1953,
            '1958 - 1968': 1963,
            '1969 - 1978': 1973,
            '1979 - 1983': 1981,
            '1984 - 1994': 1989,
            '1995 - 2001': 1998,
            '2002 - 2009': 2005,
            '2010 - 2015': 2012,
            '2016 - 2023': 2019
        }
        return age_mapping.get(building_age_span, None)
    
    for b_type in building_types:
        for b_age in building_ages[b_type]:

            temp_results_dict = {
                'design_load': [],
                'bivalent_load': [],
                'sh_demand': [],
                'dhw_demand': []
            }

            for heater in heater_Types: 
                temp_results_dict[heater] = {'CAPEX': [], 'OPEX': []}
            

            for n in range(n_runs):
                print(f"Running economic analysis for Building Type: {b_type}, Age: {map_building_age(b_age)} - Run {n+1}/{n_runs}")

            
                for i, heater in enumerate(heater_Types):
                    building_info = {
                        'id': 0,

                        'building': b_type,
                        'year': map_building_age(b_age),
                        'retrofit': 0,
                        'construction_type': '',
                        'night_setback': 0,
                        'area': map_building_area(b_type),
                        'heater': heater,
                        'cooling': 0,  # Standard
                        'PV': 0,
                        'STC': 0,  # Standard
                        'EV': 0,  # Standard
                        'BAT': 0,  # Standard
                        'f_TES': 35,  # Wie im Original
                        'f_BAT': 0,  # Wie im Original
                        'f_EV': 0,  # Wie im Original
                        'f_PV1': 0,  # Wie im Original
                        'f_PV2': 0,  # Wie im Original
                        'f_STC': 0,  # Wie im Original
                        'gamma_PV': 0,  # Wie im Original
                        'ev_charging': 'on_demand',  # Wie im Original
                        }

                    if i == 0: #For the first heater type, save the demands and reuse them for the other heater types for better comparability
                        capex, opex, design_load, bivalent_load, sh_demand, dhw_demand = run_economic_analysis(building_info, calcDemands=True)
                        temp_results_dict['design_load'].append(design_load)
                        temp_results_dict['bivalent_load'].append(bivalent_load)  # Placeholder if needed in future
                        temp_results_dict['sh_demand'].append(sh_demand)
                        temp_results_dict['dhw_demand'].append(dhw_demand)
                    else:
                        capex, opex, design_load, bivalent_load, sh_demand, dhw_demand = run_economic_analysis(building_info, calcDemands=False)
                    
                    temp_results_dict[heater]['CAPEX'].append(capex)
                    temp_results_dict[heater]['OPEX'].append(opex)
            
            for heater in heater_Types:
                avg_capex = np.mean(temp_results_dict[heater]['CAPEX'])
                avg_opex = np.mean(temp_results_dict[heater]['OPEX'])

                save_results_xlsx(
                    changing_building_info={
                        'building': b_type,
                        'year': map_building_age(b_age),
                        'col': heater
                    },
                    capex=avg_capex,
                    opex=avg_opex
                )
            
            avg_design_load = np.mean(temp_results_dict['design_load'])
            avg_bivalent_load = np.mean(temp_results_dict['bivalent_load'])
            avg_sh_demand = np.mean(temp_results_dict['sh_demand'])
            avg_dhw_demand = np.mean(temp_results_dict['dhw_demand'])

            # Add to each row the design load results and sh_demand and dhw_demand
            save_results_xlsx(changing_building_info={
                    'building': b_type,
                    'year': map_building_age(b_age),
                    'col': 'design_load (W)'
                },
                capex=avg_design_load,
                opex=avg_design_load
                )
            save_results_xlsx(
                changing_building_info={
                    'building': b_type,
                    'year': map_building_age(b_age),
                    'col': 'bivalent_load (W)'
                },
                capex=avg_bivalent_load,
                opex=avg_bivalent_load
                )
            save_results_xlsx(
                changing_building_info={
                    'building': b_type,
                    'year': map_building_age(b_age),
                    'col': 'sh_demand (kWh)'
                },
                capex=avg_sh_demand,
                opex=avg_sh_demand
                )
            save_results_xlsx(
                changing_building_info={
                    'building': b_type,
                    'year': map_building_age(b_age),
                    'col': 'dhw_demand (kWh)'
                },
                capex=avg_dhw_demand,
                opex=avg_dhw_demand
                )

    return None

def run_economic_analysis(building_info, calcDemands):
    """
    Change the scenario according to the building_info dictionary.
    Then run the economic analysis for this building n_runs times and return average CAPEX and OPEX.
    """
    # Change building CSV according to building_info
    change_building_csv(building_info)

    # Initialize District
    data = Datahandler(scenario_name = "building")

    # We directly generate a complete district.
    if calcDemands:
        data.generateDistrictComplete(calcUserProfiles=True, saveUserProfiles=True, gen_cars=False)

    else:
        data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=False, gen_cars=False)

    building = data.district[0]
    # Change investment data to match the design and bivalent load of the building energy system
    design_load = building["bes_obj"].design_load_heating # Space heating design load + DHW design load
    bivalent_load = building["bes_obj"].bivalent_load_heating  # 

    change_device_inv_data(design_load, bivalent_load, building_info['heater'])

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calulateKPIs()

    # Extract CAPEX and OPEX from KPIs
    capex, opex = get_economic_indicators(data)

    building = data.district[0]
    design_load = building["bes_obj"].design_load_heating # Space heating design load + DHW design load
    bivalent_load = building["bes_obj"].bivalent_load_heating  # 

    sh_demand = sum(building["user"].heat) * data.time["timeResolution"] / 3600.0 / 1000 # in kWh
    dhw_demand = sum(building["user"].dhw) * data.time["timeResolution"] / 3600.0 / 1000 # in kWh

    return capex, opex, design_load, bivalent_load, sh_demand, dhw_demand

def change_building_csv(building_info):
    output_path = os.path.join(SRCPATH, 'districtgenerator', 'data', 'scenarios','building.csv')
    building_df = pd.DataFrame([building_info])
    building_df.to_csv(output_path, sep=';', index=False)

def save_results_xlsx(changing_building_info, capex, opex):
    save_output_path = os.path.join(SRCPATH, 'districtgenerator', 'results','economic_analysis_results.xlsx')

    b_type = str(changing_building_info['building']) # -> Sheet
    b_age = str(changing_building_info['year']) # -> Row
    col = str(changing_building_info['col']) # -> Column

    sheet_name_capex = f"{b_type}_CAPEX"
    sheet_name_opex = f"{b_type}_OPEX"
    sheet_name_total = f"{b_type}_Total_Costs"

    # Loading existing Excel file
    if os.path.exists(save_output_path):
        try: 
            all_sheets = pd.read_excel(save_output_path, sheet_name=None, index_col=0, dtype={'Unnamed: 0': str})
        
            for sheet_name in all_sheets:
                if not all_sheets[sheet_name].empty:
                    all_sheets[sheet_name].index = all_sheets[sheet_name].index.astype(str)
        except ValueError:
            all_sheets = {}
    else:
        all_sheets = {}
    
    # Load or create DataFrames for CAPEX and OPEX
    df_opex = all_sheets.get(sheet_name_opex, pd.DataFrame())
    df_capex = all_sheets.get(sheet_name_capex, pd.DataFrame())
    df_total = all_sheets.get(sheet_name_total, pd.DataFrame())

    # Add values to DataFrames
    df_capex.at[b_age, col] = capex
    df_opex.at[b_age, col] = opex
    if "demand" in col or "load" in col:
        df_total.at[b_age, col] = capex  
    else:
        df_total.at[b_age, col] = capex + opex

    # Sort indices and columns
    df_capex = df_capex.sort_index()
    df_opex = df_opex.sort_index()
    df_total = df_total.sort_index()

    # Update all_sheets dictionary
    all_sheets[sheet_name_capex] = df_capex
    all_sheets[sheet_name_opex] = df_opex
    all_sheets[sheet_name_total] = df_total

    # Save all sheets back to Excel
    with pd.ExcelWriter(save_output_path, engine='openpyxl') as writer:
        for sheet_name, df in all_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index =True)

def get_economic_indicators(data):
    """
    Function to extract CAPEX and OPEX from data.KPIs
    """

    capex = data.KPIs.annual_fixed_costs_decentral + data.KPIs.annual_fixed_costs_central # Decentral + Central annualized investment costs
    opex = data.KPIs.operationCosts # Annual operation costs of i

    return capex, opex

def change_device_inv_data(design_load, bivalent_load, heater):
    """
    Function to change the investment data of devices according to the design load and bivalent load of the building energy system.
    """

    def heater_data_mapping(heater, design_load, bivalent_load):
        
        design_load_kw = design_load / 1000  # Convert to kW
        bivalent_load_kw = bivalent_load / 1000  # Convert to kW
        remaining_load_kw = design_load_kw - bivalent_load_kw

        # Device data from Technikkatalog 2025
        bboi_data = {
            10 : {'eta_th': 0.90, 'life_time': 20, 'inv_var': 2200, 'cost_om': 210/(10*2200)}, 
            20 : {'eta_th': 0.90, 'life_time': 20, 'inv_var': 1510, 'cost_om': 290/(20*1510)},
            30 : {'eta_th': 0.90, 'life_time': 20, 'inv_var': 1040, 'cost_om': 320/(30*1040)},
            60 : {'eta_th': 0.90, 'life_time': 20, 'inv_var': 770, 'cost_om': 460/(60*770)},
            100 : {'eta_th': 0.90, 'life_time': 20, 'inv_var': 570, 'cost_om': 580/(100*570)},
        }
        boi_data = {
            10 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 420, 'cost_om': 130/(10*420)},
            20 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 270, 'cost_om': 160/(20*270)},
            30 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 180, 'cost_om': 160/(30*180)},
            60 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 150, 'cost_om': 270/(60*150)},
            100 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 110, 'cost_om': 330/(100*110)}
        }
        oboi_data = {
            20 : {'eta_th': 0.93, 'life_time': 20, 'inv_var': 380, 'cost_om': 270/(20*380)},
            30 : {'eta_th': 0.93, 'life_time': 20, 'inv_var': 250, 'cost_om': 260/(30*250)},
            60 : {'eta_th': 0.93, 'life_time': 20, 'inv_var': 170, 'cost_om': 360/(60*170)},
            100 : {'eta_th': 0.93, 'life_time': 20, 'inv_var': 200, 'cost_om': 700/(100*200)},
        }
        h2boi_data = {
            10 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 490, 'cost_om': 150/(10*490)},
            20 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 300, 'cost_om': 180/(20*300)},
            30 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 200, 'cost_om': 180/(30*200)},
            60 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 160, 'cost_om': 290/(60*160)},
            100 : {'eta_th': 0.99, 'life_time': 20, 'inv_var': 110, 'cost_om': 330/(100*110)},
        }
        eh_data = {
            2 : {'eta_th': 1.00, 'life_time': 25, 'inv_var': 890, 'cost_om': 20/(2*890)},
            5 : {'eta_th': 1.00, 'life_time': 25, 'inv_var': 730, 'cost_om': 40/(5*730)},
            10 : {'eta_th': 1.00, 'life_time': 25, 'inv_var': 620, 'cost_om': 60/(10*620)},
            20 : {'eta_th': 1.00, 'life_time': 25, 'inv_var': 530, 'cost_om': 110/(20*530)},
            30 : {'eta_th': 1.00, 'life_time': 25, 'inv_var': 480, 'cost_om': 140/(30*480)},
        }
        hp_data = {
            5 : {'grade': 0.4, 'life_time': 20, 'inv_var': 2240, 'cost_om': 350/(5*2240)},
            10 : {'grade': 0.4, 'life_time': 20, 'inv_var': 1660, 'cost_om': 440/(10*1660)},
            20 : {'grade': 0.4, 'life_time': 20, 'inv_var': 1380, 'cost_om': 690/(20*1380)},
            30 : {'grade': 0.4, 'life_time': 20, 'inv_var': 1220, 'cost_om': 900/(30*1220)},
            40 : {'grade': 0.4, 'life_time': 20, 'inv_var': 1300, 'cost_om': 1190/(40*1300)},
            50 : {'grade': 0.4, 'life_time': 20, 'inv_var': 1260, 'cost_om': 1420/(50*1260)},
            60 : {'grade': 0.4, 'life_time': 20, 'inv_var': 1220, 'cost_om': 1620/(60*1220)},
            80 : {'grade': 0.4, 'life_time': 20, 'inv_var': 1170, 'cost_om': 2030/(80*1170)},
            100 : {'grade': 0.4, 'life_time': 20, 'inv_var': 1080, 'cost_om': 2330/(100*1080)},
        }

        all_data = {
            'BBOI': bboi_data,
            'H2BOI': h2boi_data,
            'OBOI': oboi_data,
            'BOI': boi_data,
            'EH': eh_data,
            'HP': hp_data,
        }

        def find_optimal_size(device_data, target_load_kw):
            current_distance = float('inf')
            opt_size = None
            for size in sorted(device_data.keys()):
                distance = abs(size - target_load_kw)
                if distance < current_distance:
                    current_distance = distance
                    opt_size = size
            return opt_size
        
        heater_dict = {}

        if heater in ['HP', 'GHP', 'BHP', 'OHP', 'H2HP']: # These are bivalent heat pumps
            device = all_data['HP']  # Assuming all heat pumps share the same data structure for sizing
            opt_size_bivalent = find_optimal_size(device, bivalent_load_kw)
            heater_dict['HP'] = device[opt_size_bivalent]

            for dev in ['BOI', 'BBOI', 'OBOI', 'H2BOI']:
                device = all_data[dev]
                opt_size_remaining = find_optimal_size(device, remaining_load_kw)
                heater_dict[dev] = device[opt_size_remaining]

        else: # If not bivalent heat pump, size all devices for the design load
            device = all_data[heater]
            opt_size = find_optimal_size(device, design_load_kw)
            heater_dict[heater] = device[opt_size]  

        return heater_dict
    
    change_data = heater_data_mapping(heater, design_load, bivalent_load)

    print(f"Changing investment data for heater: {heater} with design load: {design_load} W and bivalent load: {bivalent_load} W")
    print(change_data)

    # Change the json file 

    path_decentral_device_data = os.path.join(SRCPATH, 'districtgenerator', 'data', 'decentral_device_data.json')

    # Open the json file and change the relevant fields
    with open(path_decentral_device_data, 'r') as f:
        decentral_device_data = json.load(f)

    for dev_key, specs in change_data.items():
        for entry in decentral_device_data:
            if entry.get("abbreviation") == dev_key:
                for spec in entry.get("specifications", []):
                    spec_name = spec.get("name")

                    if spec_name in specs:
                        spec['value'] = specs[spec_name]

                break  # Exit loop after finding the device

    # Save the changed json file
    with open(path_decentral_device_data, 'w') as f:
        json.dump(decentral_device_data, f, indent=4)
    print(f"Updated investment data saved to {path_decentral_device_data}")
    time.sleep(30)  # Small delay to ensure file write completion

                

if __name__ == '__main__':
    example9_economic_analysis()