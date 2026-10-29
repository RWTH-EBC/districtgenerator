"""
The buildings of a district: scenario file, initialization and creation of building models.
"""
import datetime
import os
import random as rd

import numpy as np
import pandas as pd
from teaser.project import Project

from districtgenerator.buildings import thermal
from districtgenerator.buildings.profiles.users import Users
from districtgenerator.buildings.typology import mixed_use, non_residential, residential
from districtgenerator.energy_systems.technologies import get_cooling_supply, get_heating_candidates
from districtgenerator.utilities.randomness import building_seed, seeded_random_state


def parse_position(val):
    """
    The building coordinates read directly from CSV files are often irregular and need correction.
    For example: ('1','2','.','3',',','4','5','.','6') → (12.3, 45.6)
    """
    # If the input is a string like "(12.3,45.6)", parse it into a tuple of floats.
    if isinstance(val, str):
        return tuple(float(x.strip()) for x in val.strip("()").split(","))
    # If the input is a tuple or list of characters like ('1', '2', '.', '3', ',', '4', '5', '.', '6')
    elif isinstance(val, (tuple, list)):
        pos_str = "".join(val)
        return tuple(float(x.strip()) for x in pos_str.strip("()").split(","))
    # For other data types, return the value as is.
    return val


def load_scenario(scenario_file_path, scenario_name):
    """
    Read the scenario file of a district and validate the supply selection of each building.

    Parameters
    ----------
    scenario_file_path : str
        Folder of the scenario files.
    scenario_name : str
        Name of the scenario file without extension.

    Returns
    -------
    pandas.DataFrame
        One row per building, indexed by building id.
    """
    # %% load scenario file with building information
    scenario = (pd.read_csv(os.path.join(scenario_file_path, f"{scenario_name}.csv"), delimiter=";",
                                 converters={"position": parse_position}).set_index("id", drop=False))

    # Determine for each building if an dhw_heater is set

    if "dhw_heater" not in scenario.columns:
        scenario["dhw_heater"] = None
    else: 
        # Replace empty values, NaNs, and 0 with None
        scenario["dhw_heater"] = scenario["dhw_heater"].replace({np.nan: None, "": None, 0: None, "0": None, 0.0: None})

        # Replace 1 values with "EH_DHW"
        scenario["dhw_heater"] = scenario["dhw_heater"].replace({1: "EH_DHW", "1": "EH_DHW", 1.0: "EH_DHW"})

    # Validate supply selections before generating buildings/demands.
    for building_id, features in scenario.iterrows():
        try:
            get_heating_candidates(features["heater"])
            get_cooling_supply(features)
        except ValueError as exc:
            raise ValueError(f"Building {building_id}: {exc}") from exc

    return scenario


def initialize_buildings(data):
    """
    Fill district with buildings from scenario file.

    Parameters
    ----------
    scenario_name: string, optional
        Name of scenario file to be read. The default is 'example'.

    Returns
    -------
    None.
    """
    duration = datetime.timedelta(minutes=1)
    num_sfh = 0
    num_mfh = 0
    name_pool = []
    data.building_dict = {}

    # initialize buildings for scenario
    # loop over all buildings
    for bldg_id, row in data.scenario.iterrows():
        bldg_id = int(bldg_id)
        building = {}

        # Store features of the observed building
        building["buildingFeatures"] = row.copy()
        building["buildingFeatures"]["original_bldg_id"] = bldg_id # Used for tracking the building throughout the mixed building splitting and combining process


        # Unique name = "<id>_<building type>"
        name = f"{data.scenario_name}_{bldg_id}_{row['building']}"
        if name in name_pool:
            print(f"Duplicate name: {name}, skipping")
            continue
        name_pool.append(name)

        building["unique_name"] = name
        data.district.append(building)
        data.building_dict[bldg_id] = len(data.district) - 1

        # Count for time estimate
        if row["building"] in ("SFH", "TH"):
            num_sfh += 1
        elif row["building"] in ("MFH", "AB"):
            num_mfh += 1

    # Rough time estimate
    duration += datetime.timedelta(seconds=3 * num_sfh + 12 * num_mfh)
    print(f"This calculation will take about {duration}.")

    mixed_use.split_mixed_buildings(data)


def generate_buildings(data):
    """
    Create the building models of the district: geometry, envelope, users and design loads.

    Returns
    -------
    None.
    """

    # %% load general building information
    # contains definitions and parameters that affect all buildings
    bldgs = data.design_building_data

    # %% create TEASER project
    # create one project for the whole district
    prj = Project()
    prj.name = data.scenario_name

    for building in data.district:
        seed = building_seed(data.random_seed, building["buildingFeatures"], "geometry")
        building_random = rd if seed is None else rd.Random(seed)

        # convert short names into designation needed for TEASER
        building_type = bldgs["buildings_long"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])]

        # add buildings to TEASER project
        if building_type in {"single_family_house", "multi_family_house", "terraced_house", "apartment_block"}:
            construction_data = residential.add_residential_building(prj, building, building_type, bldgs,
                                                                     building_random)

            # %% create envelope object
            # containing all physical data of the envelope
            building["thermal_model"] = data.design_building_data["thermal_model_type"]
            Envelope = thermal.get_envelope_class(building["thermal_model"])

            building["envelope"] = Envelope(prj=prj,
                                            building_params=building["buildingFeatures"],
                                            construction_data=construction_data,
                                            physics=data.physics,
                                            design_building_data=data.design_building_data,
                                            file_path=data.filePath,
                                            SIA2024=data.SIA2024)
            if hasattr(building["envelope"], "compute_heating_curve"):
                building["envelope"].compute_heating_curve(
                    data.site, mode="unclustered"
                )

        else: # Non-residential buildings
            nrb_prj, construction_type = non_residential.create_non_residential_building(
                building, bldgs, data.total_building_area)

            # %% create envelope object
            # containing all physical data of the envelope
            # NOTE: For non-residential buildings, the available input data
            # only supports the 5R1C thermal model. A 7R2C mode is not
            # feasible here due to missing parameters for VDI 6007 modeling.

            building["thermal_model"] = "5R1C"
            Envelope = thermal.get_envelope_class(building["thermal_model"])

            building["envelope"] = Envelope(prj=nrb_prj,
                                            building_params=building["buildingFeatures"],
                                            construction_data=construction_type,
                                            physics=data.physics,
                                            design_building_data=data.design_building_data,
                                            file_path=data.filePath,
                                            SIA2024=data.SIA2024)
            building["envelope"].compute_heating_curve(
                data.site, mode="unclustered"
            )

        # %% create user object
        # containing number occupants, electricity demand,...
        user_seed = building_seed(data.random_seed, building["buildingFeatures"], "users")
        with seeded_random_state(user_seed):
            building["user"] = Users(building=building["buildingFeatures"]["building"],
                                     area=building["buildingFeatures"]["area"],
                                     year_of_construction=building["buildingFeatures"]["year"],
                                     retrofit=building["buildingFeatures"]["retrofit"],
                                     SIA2024=data.SIA2024, random_seed=user_seed)

        night_setback = building["buildingFeatures"]["night_setback"]
        # %% calculate design heat loads
        # at norm outside temperature
        building["envelope"].heatload = building["envelope"].calcHeatLoad(site=data.site, method="design", night_setback = night_setback)
        # at bivalent temperature
        building["envelope"].bivalent = building["envelope"].calcHeatLoad(site=data.site, method="bivalent", night_setback = night_setback)
        # at heating limit temperature
        building["envelope"].heatlimit = building["envelope"].calcHeatLoad(site=data.site, method="heatlimit", night_setback = night_setback)
        # for drinking hot water
        building["envelope"].dhwpower = bldgs["dhwpower"][bldgs["buildings_short"].index(building["user"].building)] * building["buildingFeatures"]["area"]

        # %% calculate design cooling load
        building["envelope"].coolingload = building["envelope"].calcCoolingLoad(site=data.site, nb_occ=np.sum(building["user"].nb_occ))

        index = bldgs["buildings_short"].index(building["buildingFeatures"]["building"])
        building["buildingFeatures"] = building["buildingFeatures"].copy()
        building["buildingFeatures"]["mean_drawoff_dhw"] = bldgs["mean_drawoff_vol_per_day"][index]
