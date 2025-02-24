# -*- coding: utf-8 -*-


import pandas as pd

def read_SIA_data():

    data = pd.read_excel('../districtgenerator/data/SIA2024.xlsx', sheet_name='SIA2024', header=1)
    df = pd.DataFrame(data, columns=['number', 'Zone_name_GER', 'T_summer', 'T_winter',	'area_room', 'dQ_persons_perA',
                                     't_fullLoad_persons', 'P_vent_perVh', 'P_vent_perA', 'W_per_person',
                                     'Q_domHotWater_perA_year',	'window_wall_ratio', 'wwr_faktor_windowframes',
                                     'heatCapacity_WhperAK', 'airFlow_perA_perh', 'airFlow_perPerson_perh',])
    df2 = pd.DataFrame(data, columns=['E_devices_year_kwh_s', 'E_light_year_kwh_s', 'E_vent_year_kwh_s',
                                     'E_devices_year_kwh_g', 'E_light_year_kwh_g', 'E_vent_year_kwh_g',
                                     'E_devices_year_kwh_e', 'E_light_year_kwh_e', 'E_vent_year_kwh_e'])
    df3 = pd.DataFrame(data, columns=['p_1', 'p_2', 'p_3', 'p_4', 'p_5', 'p_6', 'p_7','p_8', 'p_9', 'p_10', 'p_11',
                                     'p_12', 'p_13', 'p_14', 'p_15', 'p_16', 'p_17', 'p_18', 'p_19', 'p_20', 'p_21',
                                     'p_22', 'p_23', 'p_24',
                                     'd_1', 'd_2', 'd_3', 'd_4', 'd_5', 'd_6', 'd_7', 'd_8', 'd_9', 'd_10', 'd_11',
                                     'd_12', 'd_13', 'd_14', 'd_15', 'd_16', 'd_17', 'd_18', 'd_19', 'd_20', 'd_21',
                                     'd_22', 'd_23', 'd_24',
                                     'm_1', 'm_2', 'm_3', 'm_4', 'm_5', 'm_6', 'm_7', 'm_8', 'm_9', 'm_10', 'm_11',
                                     'm_12'])
    df4 = pd.DataFrame(data, columns=['Living: MFH', 'Living: SFH', 'OB', 'School', 'Grocery_store'])

    SIA2024 = {}
    for row in range(0, 45):
        SIA2024[str(df['number'][row])] = {}  # dict for each zone
        SIA2024[str(df['number'][row])]['E_devices_year_kwh'] = {}
        SIA2024[str(df['number'][row])]['E_light_year_kwh'] = {}
        SIA2024[str(df['number'][row])]['E_vent_year_kwh'] = {}
        SIA2024[str(df['number'][row])]['profile_people'] = {}
        profile_people_list = []
        SIA2024[str(df['number'][row])]['profile_devices'] = {}
        profile_devices_list = []
        SIA2024[str(df['number'][row])]['profile_month'] = {}
        profile_month_list = []
        for col in df.loc[:, df.columns != 'number']:
            SIA2024[str(df['number'][row])][col] = df[col][row]
        for val in ['standard', 'goal', 'existing']:
            SIA2024[str(df['number'][row])]['E_devices_year_kwh'][val] = df2['E_devices_year_kwh_' + val[0]][row]
            SIA2024[str(df['number'][row])]['E_light_year_kwh'][val] = df2['E_light_year_kwh_' + val[0]][row]
            SIA2024[str(df['number'][row])]['E_vent_year_kwh'][val] = df2['E_vent_year_kwh_' + val[0]][row]
        for val in range(1, 25):
            profile_people_list.append(df3['p_' + str(val)][row])
            profile_devices_list.append(df3['d_' + str(val)][row])
        for val in range(1, 13):
            profile_month_list.append(df3['m_' + str(val)][row])
        SIA2024[str(df['number'][row])]['profile_people'] = profile_people_list
        SIA2024[str(df['number'][row])]['profile_devices'] = profile_devices_list
        SIA2024[str(df['number'][row])]['profile_month'] = profile_month_list
    for col in df4.columns:
        SIA2024[col] = {}
        for i in range(len(df)):
            zone_name = df['Zone_name_GER'][i]
            value = df4[col][i]
            SIA2024[col][zone_name] = value

    return SIA2024





