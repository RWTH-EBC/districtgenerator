"""
Residential buildings based on the TABULA German building typology, created with TEASER.
"""
from teaser.project import Project


def one_floor_area_range(building_type):
    """
    Floor area ranges for different residential building types based on the TABULA German Building Typology

    Returns
    -------
    tuple
        A tuple containing the minimum and maximum floor area for one floor of the given building type.
    """
    if building_type == "single_family_house":
        return (62, 115) # Source: TABULA German Building Typology
    elif building_type == "terraced_house":
        return (50, 73) # Source: TABULA German Building Typology
    elif building_type == "multi_family_house":
        return (102, 971) # Source: TABULA German Building Typology
    elif building_type == "apartment_block":
        return (350, 540) # Source: TABULA German Building Typology
    else: raise ValueError(f"Unknown building type for residential floor area estimation according to TABULA: {building_type}")


def add_residential_building(prj, building, building_type, bldgs, building_random):
    """
    Add a residential building to the TEASER project.

    The number of floors is estimated from the floor area of the building and a random
    floor area per storey from the TABULA typology. The storey height depends on the
    year of construction.

    Parameters
    ----------
    prj : teaser.project.Project
        TEASER project of the district.
    building : dict
        Building of the district. Its ``buildingFeatures`` get the TEASER building id.
    building_type : str
        TABULA building type, for example ``"single_family_house"``.
    bldgs : dict
        Design building data of the Datahandler.
    building_random : random.Random or module
        Random source for the floor area per storey.

    Returns
    -------
    str
        TEASER construction data of the retrofit level.
    """
    retrofit_level = bldgs["retrofit_long"][bldgs["retrofit_short"].index(building["buildingFeatures"]["retrofit"])]
    if retrofit_level == "tabula_retrofit":
        construction_data = 'tabula_de_retrofit'
    elif retrofit_level == "tabula_adv_retrofit":
        construction_data = 'tabula_de_adv_retrofit'
    else:
        # tabula standard
        construction_data = 'tabula_de_standard'

    # Determining the number of floors in a building based on its type.
    # The method estimates the number of floors by:
    # - Assigning a range of possible floor areas per level based on building type.
    # - Randomly selecting a value within the assigned range using the TABULA German Building Typology.
    # - Calculating the total number of floors by dividing the building’s total floor area
    #   by the selected single-floor area.

    # Check if floors are already fixed those are used (from mixed building splitting)
    if "fixed_floors" in building["buildingFeatures"]:
        number_of_floors = building["buildingFeatures"]["fixed_floors"]
    elif building_type == "single_family_house":
        one_floor_area = building_random.randint(*one_floor_area_range(building_type))
        # Calculate the number of floors, rounding to the nearest integer and ensuring at least 1
        number_of_floors = max(1, round(building["buildingFeatures"]["area"] / one_floor_area))

    elif building_type == "terraced_house":
        one_floor_area = building_random.randint(*one_floor_area_range(building_type))  # Source: TABULA German Building Typology
        # Calculate the number of floors, rounding to the nearest integer and ensuring at least 1
        number_of_floors = max(1, round(building["buildingFeatures"]["area"] / one_floor_area))

    elif building_type == "multi_family_house":
        # Generate a valid one-floor area and number of floors in one step
        one_floor_area = building_random.randint(*one_floor_area_range(building_type)) # Source: TABULA German Building Typology
        # Calculate the number of floors, rounding to the nearest integer and ensuring at least 2
        number_of_floors = max(2, round(building["buildingFeatures"]["area"] / one_floor_area))
        # Cap the number of floors to a maximum of 8
        if number_of_floors > 8:
            number_of_floors = 8

    elif building_type == "apartment_block":
        one_floor_area = building_random.randint(*one_floor_area_range(building_type))  # Source: TABULA German Building Typology
        # Calculate the number of floors, rounding to the nearest integer and ensuring at least 3
        number_of_floors = max(3, round(building["buildingFeatures"]["area"] / one_floor_area))

    # Determining the typical floor height based on the building's construction year.
    # Older buildings (constructed before 1960) generally have higher ceilings, while newer buildings
    # (built from 1960 onwards) tend to have lower ceilings.
    # Source: https://www.wohnung.com/ratgeber/418/alt-und-neubau-deckenhoehe

    if building["buildingFeatures"]["year"] < 1960:
        height_of_floors = 3.3  # m
    elif building["buildingFeatures"]["year"] >= 1960:
        height_of_floors = 2.5  # m

    # add buildings to TEASER project
    prj.add_residential(name="ResidentialBuildingTabula",
                        geometry_data="tabula_de_" + building_type,
                        construction_data=construction_data,
                        year_of_construction=building["buildingFeatures"]["year"],
                        number_of_floors=number_of_floors,
                        height_of_floors=height_of_floors,
                        net_leased_area=building["buildingFeatures"]["area"])

    if building["buildingFeatures"].get("is_mixed_part", False):
        if isinstance(prj, Project):
            mixed_res_part = prj.buildings[-1]
            for r in mixed_res_part.thermal_zones[0].ground_floors:
                # Ensure no ground area for the residential part.
                r.area = 1e-9 # Set to a very small value to avoid division by zero errors in Envelope calculations


    building["buildingFeatures"] = building["buildingFeatures"].copy() # What is the purpose of creating the copy and then overwriting the old version
    building["buildingFeatures"]["id_teaser"] = len(prj.buildings) - 1

    return construction_data
