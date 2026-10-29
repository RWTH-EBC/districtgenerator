"""
Mixed-use buildings: split into main and secondary parts, and recombine their demands.

A mixed-use building is written as ``"MAIN+SECONDARY"`` in the scenario file, for example
``"MFH+RETAIL"``. Each part is modelled as its own building and combined again after the
demand generation.
"""
import copy
import os
import random as rd

import numpy as np
import pandas as pd

from districtgenerator.buildings.typology.non_residential import NonResidential
from districtgenerator.buildings.typology.residential import one_floor_area_range
from districtgenerator.storage import profile_store
from districtgenerator.utilities.randomness import building_seed


def is_mixed_building(building_type):
    """
    Check if a building type is a mixed-use building (contains "+").

    Parameters
    ----------
    building_type : str
        The building type string (e.g., "MFH+RETAIL").

    Returns
    -------
    bool
        True if the building type contains "+", False otherwise.
    """
    return "+" in building_type


def combine_mixed_building_demands(data, saveUserProfiles):
    """
    Combine demand profiles from split mixed-use buildings back into a single building.
    This should be called after generateDemands() but before designDecentralDevices().

    Creates a new combined building with summed demand profiles.
    Both main and secondary buildings are deleted, replaced by the combined building.
    An Excel file is created for each combined building showing all demand profiles.

    Returns
    -------
    None
    """
    # Find all mixed building parts grouped by parent ID
    mixed_buildings = {}
    for idx, building in enumerate(data.district):
        if building["buildingFeatures"].get("is_mixed_part", False):
            parent_id = building["buildingFeatures"]["mixed_parent_id"]
            if parent_id not in mixed_buildings:
                mixed_buildings[parent_id] = []
            mixed_buildings[parent_id].append((idx, building))

    if mixed_buildings:
        print(f"Found {len(mixed_buildings)} mixed-use building groups to recombine.")

    # Combine each group of mixed buildings
    buildings_to_remove = []
    buildings_to_add = []

    for parent_id, buildings in mixed_buildings.items():
        if len(buildings) < 2:
            continue

        # Find main and secondary buildings
        main_idx, main_building = None, None
        secondary_idx, secondary_building = None, None

        for idx, building in buildings:
            if building["buildingFeatures"]["mixed_role"] == "main":
                main_idx, main_building = idx, building
            elif building["buildingFeatures"]["mixed_role"] == "secondary":
                secondary_idx, secondary_building = idx, building

        if main_building is None or secondary_building is None:
            continue

        # Create a NEW combined building based on the original building features
        combined_building = {}

        # Copy building features from main building (which has original_bldg_id)
        combined_building["buildingFeatures"] = main_building["buildingFeatures"].copy()

        # Update building type to show it's mixed
        main_type = main_building["buildingFeatures"]["building"]
        secondary_type = secondary_building["buildingFeatures"]["building"]
        combined_building["buildingFeatures"]["building"] = f"{main_type}+{secondary_type}"

        # Sum up total area from both parts
        combined_building["buildingFeatures"]["area"] = (
            main_building["buildingFeatures"]["area"] +
            secondary_building["buildingFeatures"]["area"])

        # Mark as combined and remove mixed-part flags
        combined_building["buildingFeatures"]["is_mixed_combined"] = True
        if "is_mixed_part" in combined_building["buildingFeatures"]:
            del combined_building["buildingFeatures"]["is_mixed_part"]
        if "mixed_role" in combined_building["buildingFeatures"]:
            del combined_building["buildingFeatures"]["mixed_role"]
        if "mixed_parent_id" in combined_building["buildingFeatures"]:
            del combined_building["buildingFeatures"]["mixed_parent_id"]

        # Create unique name for combined building
        combined_building["unique_name"] = f"{data.scenario_name}_{parent_id}_{main_type}+{secondary_type}"

        # Copy envelope and user objects from main building
        combined_building["envelope"] = copy.deepcopy(main_building["envelope"])

        # Create new user object with combined demands
        combined_building["user"] = copy.deepcopy(main_building["user"])

        # Combine all demand profiles by summing (element-wise with numpy arrays)
        combined_building["user"].elec = np.array(np.array(main_building["user"].elec) + np.array(secondary_building["user"].elec))
        combined_building["user"].dhw = np.array(np.array(main_building["user"].dhw) + np.array(secondary_building["user"].dhw))
        combined_building["user"].dhw_minutely = np.array(np.array(main_building["user"].dhw_minutely) + np.array(secondary_building["user"].dhw_minutely))
        combined_building["user"].heat = np.array(np.array(main_building["user"].heat) + np.array(secondary_building["user"].heat))
        combined_building["user"].cooling = np.array(np.array(main_building["user"].cooling) + np.array(secondary_building["user"].cooling))
        combined_building["user"].gains = np.array(np.array(main_building["user"].gains) + np.array(secondary_building["user"].gains))
        combined_building["user"].occ = np.array(np.array(main_building["user"].occ) + np.array(secondary_building["user"].occ))

        combined_building["user"].EV_carcharging_ondemand = np.array(np.array(main_building["user"].EV_carcharging_ondemand) + np.array(secondary_building["user"].EV_carcharging_ondemand))
        combined_building["user"].EV_carprofile = np.array(np.array(main_building["user"].EV_carprofile) + np.array(secondary_building["user"].EV_carprofile))
        combined_building["user"].ice_carprofile = np.array(np.array(main_building["user"].ice_carprofile) + np.array(secondary_building["user"].ice_carprofile))

        # Combine EV capacities
        cap_main = main_building["user"].ev_capacity if main_building["user"].ev_capacity is not None else []
        cap_sec = secondary_building["user"].ev_capacity if secondary_building["user"].ev_capacity is not None else []

        # Ensure values are lists to prevent addition errors
        if isinstance(cap_main, (int, float)): cap_main = [cap_main]
        if isinstance(cap_sec, (int, float)): cap_sec = [cap_sec]

        combined_building["user"].ev_capacity = [float(x) for x in (list(cap_main) + list(cap_sec))]

        # Combine individual car profiles and reassign unique IDs
        cars_main = main_building["user"].individual_car_profiles.copy() if hasattr(main_building["user"], "individual_car_profiles") and main_building["user"].individual_car_profiles else []
        cars_sec = secondary_building["user"].individual_car_profiles.copy() if hasattr(secondary_building["user"], "individual_car_profiles") and secondary_building["user"].individual_car_profiles else []

        combined_building["user"].individual_car_profiles = []
        new_car_id = 0

        for car in cars_main:
            car_copy = car.copy()
            car_copy["car_id"] = new_car_id
            combined_building["user"].individual_car_profiles.append(car_copy)
            new_car_id += 1

        for car in cars_sec:
            car_copy = car.copy()
            car_copy["car_id"] = new_car_id
            combined_building["user"].individual_car_profiles.append(car_copy)
            new_car_id += 1

        # Sum up user counts differentiate if residential or non-residential
        if main_type in {"SFH", "TH", "MFH", "AB"}:
            combined_building["user"].nb_res_flats = main_building["user"].nb_units
            combined_building["user"].nb_res_occ = main_building["user"].nb_occ.copy()
            combined_building["user"].nb_nonres_flats = secondary_building["user"].nb_units
            combined_building["user"].nb_nonres_occ = secondary_building["user"].nb_occ
        elif secondary_type in {"SFH", "TH", "MFH", "AB"}:
            combined_building["user"].nb_res_flats = secondary_building["user"].nb_units
            combined_building["user"].nb_res_occ = secondary_building["user"].nb_occ.copy()
            combined_building["user"].nb_nonres_flats = main_building["user"].nb_units
            combined_building["user"].nb_nonres_occ = main_building["user"].nb_occ
        else: raise Exception(f"At least one part of the mixed building has to be residential. Please check building types for {combined_building['unique_name']}.")

        combined_building["user"].nb_units = main_building["user"].nb_units + secondary_building["user"].nb_units
        occ_main = np.atleast_1d(main_building["user"].nb_occ)
        occ_sec = np.atleast_1d(secondary_building["user"].nb_occ)
        combined_building["user"].nb_occ = [int(x) for x in np.concatenate([occ_main, occ_sec])]

        # sum up the design loads for heating and cooling
        combined_building["envelope"].heatload = main_building["envelope"].heatload + secondary_building["envelope"].heatload
        combined_building["envelope"].bivalent = main_building["envelope"].bivalent + secondary_building["envelope"].bivalent
        combined_building["envelope"].heatlimit = main_building["envelope"].heatlimit + secondary_building["envelope"].heatlimit
        combined_building["envelope"].coolingload = main_building["envelope"].coolingload + secondary_building["envelope"].coolingload

        # Adjust areas from envelope:
        combined_building["envelope"].A = {}

        main_A = main_building["envelope"].A
        sec_A = secondary_building["envelope"].A

        # 1. Sum total area:
        combined_building["envelope"].A['f'] = main_A['f']+ sec_A['f']

        # 2. Sum up all opaque areas (walls, roof, floor, etc.)
        combined_building["envelope"].A['opaque'] = {}
        all_keys = set(main_A.get('opaque', {}).keys()).union(set(sec_A.get('opaque', {}).keys()))
        for key in all_keys:
            combined_building["envelope"].A['opaque'][key] = main_A['opaque'].get(key, 0) + sec_A['opaque'].get(key, 0)

        # 3. Sum up all window areas
        combined_building["envelope"].A['window'] = {}
        all_keys = set(main_A.get('window', {}).keys()).union(set(sec_A.get('window', {}).keys()))
        for key in all_keys:
            combined_building["envelope"].A['window'][key] = main_A['window'].get(key, 0) + sec_A['window'].get(key, 0)

        # Sum up DHW power and generation
        combined_building["envelope"].dhwpower = main_building["envelope"].dhwpower + secondary_building["envelope"].dhwpower

        print(f"Combined mixed building {parent_id}: "
              f"{main_type} + {secondary_type} → NEW combined building")

        # Save combined profiles to Excel file
        if saveUserProfiles:
            profile_store.save_profiles(time_cfg=data.time,
                                           name=combined_building["unique_name"],
                              elec=combined_building["user"].elec,
                              dhw=combined_building["user"].dhw,
                              dhw_minutely=combined_building["user"].dhw_minutely,
                              occ=combined_building["user"].occ,
                              gains=combined_building["user"].gains,
                              EV_carcharging_ondemand=combined_building["user"].EV_carcharging_ondemand,
                              EV_carprofile=combined_building["user"].EV_carprofile,
                              nb_units=combined_building["user"].nb_units,
                              nb_occ=combined_building["user"].nb_occ,
                              ev_capacity=combined_building["user"].ev_capacity or [0],
                              ice_carprofile=combined_building["user"].ice_carprofile,
                              heatload=combined_building["envelope"].heatload,
                              bivalent=combined_building["envelope"].bivalent,
                              heatlimit=combined_building["envelope"].heatlimit,
                            #   coolingload=combined_building["envelope"].coolingload, #TODO: Check why not saved
                            #   dhwpower=combined_building["envelope"].dhwpower, #TODO: Check why not saved
                              path=os.path.join(data.resultPath, 'demands'),
                              individual_car_profiles=combined_building["user"].individual_car_profiles)

            profile_store.save_heating_profile(heat=combined_building["user"].heat,
                                    cooling=combined_building["user"].cooling,
                                    name=combined_building["unique_name"],
                                    path=os.path.join(data.resultPath, 'demands'))

        # Mark both buildings for removal
        buildings_to_remove.append(main_idx)
        buildings_to_remove.append(secondary_idx)

        # Add new combined building to the list
        buildings_to_add.append(combined_building)

    # Remove both main and secondary buildings (in reverse order to maintain indices)
    for idx in sorted(buildings_to_remove, reverse=True):
        del data.district[idx]

    # Add all new combined buildings to the district
    for combined_building in buildings_to_add:
        data.district.append(combined_building)

    # Rebuild building_dict completely for ALL buildings
    # After removing/adding buildings, indices have shifted
    data.building_dict = {}
    for idx, building in enumerate(data.district):
        if "original_bldg_id" in building["buildingFeatures"]:
            original_id = building["buildingFeatures"]["original_bldg_id"]
            data.building_dict[original_id] = idx


def split_mixed_buildings(data):
    """
    Splits mixed-use buildings into main and secondary building parts.
    """
    bldgs = data.design_building_data

    buildings_to_process = []
    buildings_to_skip = []

    for idx, building in enumerate(data.district):
        if is_mixed_building(building["buildingFeatures"]["building"]):
            seed = building_seed(data.random_seed, building["buildingFeatures"], "geometry")
            building_random = rd if seed is None else rd.Random(seed)
            # This building needs to be split - we'll handle it separately
            buildings_to_skip.append(idx)

            # Split the building type
            building_types = building["buildingFeatures"]["building"].split("+")
            main_type = building_types[0]
            secondary_type = building_types[1]

            total_area = building["buildingFeatures"]["area"]

            # Calculate number of floors for the main building type
            main_building_long = bldgs["buildings_long"][bldgs["buildings_short"].index(main_type)]

            # Calculate floors based on main building type
            if main_building_long == "single_family_house":
                one_floor_area = building_random.randint(*one_floor_area_range(main_building_long))
                total_floors = max(2, round(total_area / one_floor_area))
            elif main_building_long == "terraced_house":
                one_floor_area = building_random.randint(*one_floor_area_range(main_building_long))
                total_floors = max(2, round(total_area / one_floor_area))
            elif main_building_long == "multi_family_house":
                one_floor_area = building_random.randint(*one_floor_area_range(main_building_long))
                total_floors = max(2, round(total_area / one_floor_area))
                if total_floors > 8: total_floors = 8
            elif main_building_long == "apartment_block":
                one_floor_area = building_random.randint(*one_floor_area_range(main_building_long))
                total_floors = max(3, round(total_area / one_floor_area))
            else:
                # Generate a NonResidential building and get number of floors
                retrofit_level = bldgs["retrofit_long_non_residential"][bldgs["retrofit_short_non_residential"].index(building["buildingFeatures"]["retrofit"])]
                construction_type = bldgs["construction_type_long"][bldgs["construction_type_short"].index(building["buildingFeatures"]["construction_type"])]

                temp_building = NonResidential(
                    usage=main_type,
                    name="NonResidentialBuilding",
                    year_of_construction=building["buildingFeatures"]["year"],
                    net_leased_area=building["buildingFeatures"]["area"],          # Total net leased area of the building, or of the building part if it is a mixed-use building.
                    total_building_area=(                                          # Total net leased area of building
                        building["buildingFeatures"]["area"] if data.total_building_area is None
                        else data.total_building_area),
                    construction_type=construction_type,
                    retrofit_level=retrofit_level,
                    number_of_floors=None
                    )
                total_floors = max(2,int(temp_building.get_number_of_floors())) # If building is split it needs at least two floors
                del temp_building

            # Recalculate one_floor_area based on total area and total floors to ensure consistency
            one_floor_area = total_area / total_floors

            # Allocate 1 floor to secondary, rest to main (main must have at least 1)
            secondary_floors = 1
            main_floors = total_floors - secondary_floors

            # Calculate areas based on floors
            secondary_area = one_floor_area * secondary_floors
            main_area = total_area - secondary_area

            # Create main building
            main_building = {}
            main_row = building["buildingFeatures"].copy()
            main_row["building"] = main_type
            main_row["area"] = main_area
            main_row["is_mixed_part"] = True
            main_row["mixed_parent_id"] = building["buildingFeatures"]["original_bldg_id"]
            main_row["mixed_role"] = "main"
            main_row["fixed_floors"] = main_floors

            main_building["buildingFeatures"] = main_row
            main_building["unique_name"] = f"{data.scenario_name}_{idx}_{main_type}_Main"
            buildings_to_process.append(main_building)

            # Create secondary building
            secondary_building = {}
            secondary_row = building["buildingFeatures"].copy()
            secondary_row["building"] = secondary_type
            secondary_row["area"] = secondary_area
            secondary_row["is_mixed_part"] = True
            secondary_row["mixed_parent_id"] = building["buildingFeatures"]["original_bldg_id"]
            secondary_row["mixed_role"] = "secondary"
            secondary_row["fixed_floors"] = secondary_floors

            secondary_building["buildingFeatures"] = secondary_row
            secondary_building["unique_name"] = f"{data.scenario_name}_{idx}_{secondary_type}_Secondary"
            buildings_to_process.append(secondary_building)

            print(f"Split mixed building {building['buildingFeatures']['original_bldg_id']}: "
                  f"{building['buildingFeatures']['building']} (Total: {total_area:.0f} m², {total_floors} floors) -> "
                  f"{main_type} ({main_area:.0f} m², {main_floors} floors) + "
                  f"{secondary_type} ({secondary_area:.0f} m², {secondary_floors} floor)")

    # Replace district with processed buildings
    new_district = []
    for idx, building in enumerate(data.district):
        if idx not in buildings_to_skip:
            new_district.append(building)
    new_district.extend(buildings_to_process)
    data.district = new_district

    # Rebuild building_dict
    data.building_dict = {}
    for idx, building in enumerate(data.district):
        if "original_bldg_id" in building["buildingFeatures"]:
            original_id = building["buildingFeatures"]["original_bldg_id"]
            # Only map the main building for mixed types, or all regular buildings
            if building["buildingFeatures"].get("mixed_role") == "main" or not building["buildingFeatures"].get("is_mixed_part", False):
                data.building_dict[original_id] = idx
