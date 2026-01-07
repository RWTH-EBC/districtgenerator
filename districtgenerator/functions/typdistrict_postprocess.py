import matplotlib.pyplot as plt
import matplotlib.patches as patches
from random import uniform, random, shuffle, randint, sample
import os
import json
import numpy as np
from math import ceil
import shapely
from districtgenerator.functions.typdistrict_preprocess import params, district_type
from districtgenerator.functions.typdistrict import run_typdistrict_layout

'''
use function scenario_generation to generate the district layout
and save the parameters and plot in districtgenerator/data/scenarios
'''

def get_unique_filename(base_path):
    '''
    Generates a unique filename by appending an incremental number if the file already exists
    '''
    if not os.path.exists(base_path):
        return base_path
    base, ext = os.path.splitext(base_path)
    counter = 1
    while True:
        new_path = f"{base}({counter}){ext}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1

def convert_to_serializable(obj):
    '''
    Converts NumPy data types and arrays into standard Python types for JSON serialization
    '''
    if isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj

def scenario_generation():
    """
    Obtain buildings and roads layouts based on the input building type and number of buildings.

    Returns
    -------
    None
    """
    # %% STEP ONE: set parameters for the model
    num_buildings = int(input("\nEnter the number of buildings: "))
    add_waste_heat = input("\nDo you want to add a waste heat source? (y/n): ").lower() == 'y'
    if add_waste_heat:
        waste_heat_type = input("Enter the type of the waste heat source ('paper', 'data_center'): ")
        distance_to_district = float(input("Enter the distance to the district (in m): "))
    building_density = params["gebaeude_pro_ha"]["value"]  # buildings per hectare
    # building_density = 5
    building_density_min = params["gebaeude_pro_ha"]["min"]  # buildings per hectare
    building_density_max = params["gebaeude_pro_ha"]["max"]  # buildings per hectare
    width_length_ratio_mean = params["seitenverhaeltnis"]["mean_value"]
    house_connection = params["HA-Leitungen"]["value"]  # Length of house connection lines in m
    distance_between_buildings_min = params["abstand_hausanschluesse"]["min"]  # meters

    wohneinheiten = params["wohneinheiten"]["value"]

    if district_type == "A":
        delete_ratio = 0.5
    elif district_type == "B":
        delete_ratio = 0.4
    elif district_type == "C":
        delete_ratio = 0.4
    elif district_type == "D":
        delete_ratio = 0.4
    elif district_type == "E":
        delete_ratio = 0
    elif district_type == "F":
        delete_ratio = 0
    elif district_type == "G":
        delete_ratio = 0.6
    elif district_type == "H":
        delete_ratio = 0
    elif district_type == "I":
        delete_ratio = 0.6

    # %% STEP TWO: Repeat running the model until getting a conforming district layout
    # run the model for the first time
    road_lines_scaled, placed_buildings, transformer_pos, run_results, get_bigger_density = (
        run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio))

    # Limit the maximum number of attempts to avoid model dead loops.
    max_attempts = 30
    attempts = 0

    # If there is too much empty space in the district layout,
    # adjust the road deletion_ratio and building_density, and rerun the model code.
    while get_bigger_density == True and len(placed_buildings) == num_buildings and attempts < max_attempts:
        if district_type not in ["E", "F", "H"]:
            delete_ratio += 0.02
        rate = uniform(0, 1)
        building_density += rate
        building_density = min(building_density, building_density_max * 2)
        attempts += 1
        road_lines_scaled, placed_buildings, transformer_pos, run_results, get_bigger_density = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio))

    # If the number of buildings generated is less than the required number,
    # adjust the road deletion_ratio and building_density, and rerun the model code.
    while len(placed_buildings) < num_buildings and attempts < max_attempts:
        delete_ratio = max(delete_ratio - 0.02, 0)
        rate = uniform(0, 1)
        building_density -= rate
        building_density = max(building_density_min, building_density)
        attempts += 1
        road_lines_scaled, placed_buildings, transformer_pos, run_results, get_bigger_density = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio))

    # When a sufficient number of buildings cannot be generated even though the number of attempts exceeds the set upper
    # limit, the layout is performed in a preset manner.
    # parameter switch_i turns to 1 for district type I
    if len(placed_buildings) < num_buildings and district_type == 'I':
        road_lines_scaled, placed_buildings, transformer_pos, run_results, _ = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio, switch_i=1))
    # parameter switch_g turns to 1 for district type G
    if len(placed_buildings) < num_buildings and district_type == 'G':
        road_lines_scaled, placed_buildings, transformer_pos, run_results, _ = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio, switch_g=1))

    # The final check to ensure that the number of buildings meets the requirements.
    if len(placed_buildings) < num_buildings:
        num_missing_building = num_buildings - len(placed_buildings)
        building_width = run_results["building_width"]
        distance_between_bl = max(building_width, distance_between_buildings_min)
        if run_results["width_length_ratio"] >= width_length_ratio_mean:
            # If the width to length ratio of the generated area is greater than average,
            # extend the road and add buildings above the existing area.
            direction = "up"
            num_add_roads = run_results["num_column_roads"]
        else:
            # If the width to length ratio of the generated area is smaller than average,
            # extend the road and add buildings on the right side of the existing area.
            direction = "right"
            num_add_roads = run_results["num_row_roads"]

        # Increase the redundancy margin for building quantities to prevent insufficient structures from being generated in the end.
        num_bl_total = num_missing_building + (num_add_roads - 1) * 2
        bl_per_road_side = ceil(num_bl_total/num_add_roads/2)
        # Calculation of the length of the road to be extended
        road_length = house_connection + bl_per_road_side * building_width

        # Get coordinates of all road nodes
        all_points = [pt for line in road_lines_scaled for pt in (line.coords[0], line.coords[1])]

        if direction == "up":
            # Get the coordinates of all the top road nodes that need to be extended
            max_y = max(pt[1] for pt in all_points)
            top_edge_points = [pt for pt in all_points if pt[1] == max_y]
            shuffle(top_edge_points)

            for pt in top_edge_points:
                if len(placed_buildings) >= num_buildings:
                    break
                # extend the vertical road
                end_point = (pt[0], pt[1]+road_length)
                road = shapely.LineString([pt, end_point])
                road_lines_scaled.append(road)

                # place buildings along the extended road
                for side in ["left", "right"]:
                    # get the parallel line (The center point of the building is on this line)
                    road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16,
                                                         mitre_limit=5.0)
                    # Get a list of the distances from the center of all buildings to the start of the road.
                    distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in
                                 range(bl_per_road_side)]
                    # Get the coordinates of all building center points
                    points = [road_parallel.interpolate(d) for d in distances]
                    for p in points:
                        # Draw the building square
                        new_building = shapely.box(p.x - building_width / 2, p.y - building_width / 2,
                                                   p.x + building_width / 2, p.y + building_width / 2)
                        buffered_roads = [line.buffer(house_connection - 0.1) for line in road_lines_scaled]
                        # Detect whether the building overlaps with existing roads and buildings
                        if not any(new_building.intersects(b) for b in placed_buildings):
                            if not any(new_building.intersects(r) for r in buffered_roads):
                                placed_buildings.append(new_building)

        if direction == "right":
            # Get the coordinates of all rightmost road nodes that need to be extended
            max_x = max(pt[0] for pt in all_points)
            right_edge_points = [pt for pt in all_points if pt[0] == max_x]
            shuffle(right_edge_points)

            for pt in right_edge_points:
                if len(placed_buildings) >= num_buildings:
                    break
                # extend the horizontal road
                end_point = (pt[0]+road_length, pt[1])
                road = shapely.LineString([pt, end_point])
                road_lines_scaled.append(road)

                # place buildings along the extended road
                for side in ["left", "right"]:
                    # get the parallel line (The center point of the building is on this line)
                    road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16,
                                                         mitre_limit=5.0)
                    # Get a list of the distances from the center of all buildings to the start of the road.
                    distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in
                                 range(bl_per_road_side)]
                    # Get the coordinates of all building center points
                    points = [road_parallel.interpolate(d) for d in distances]
                    for p in points:
                        # Draw the building square
                        new_building = shapely.box(p.x - building_width / 2, p.y - building_width / 2,
                                                   p.x + building_width / 2, p.y + building_width / 2)
                        buffered_roads = [line.buffer(house_connection - 0.1) for line in road_lines_scaled]
                        # Detect whether the building overlaps with existing roads and buildings
                        if not any(new_building.intersects(b) for b in placed_buildings):
                            if not any(new_building.intersects(r) for r in buffered_roads):
                                placed_buildings.append(new_building)

    buildings = []
    if len(placed_buildings) - num_buildings <= 0:
        buildings = placed_buildings
    else:
        # If the number of buildings generated exceeds the required number, some buildings are randomly deleted
        num_remove = len(placed_buildings) - num_buildings
        remove_indices = set(sample(range(len(placed_buildings)), num_remove))
        for i in range(len(placed_buildings)):
            if i not in remove_indices:
                buildings.append(placed_buildings[i])

    ### Integrate Waste Heat Source ###
    if add_waste_heat:
        bounds = run_results["district_bounds"]
        xmin, xmax = bounds["xmin"], bounds["xmax"]
        ymin, ymax = bounds["ymin"], bounds["ymax"]

        # Randomly select one side of the rectangle
        side = np.random.choice(["left", "right", "bottom", "top"])

        if side == "left":
            base_point = (xmin, uniform(ymin, ymax))
            outward_angle = np.pi
        elif side == "right":
            base_point = (xmax, uniform(ymin, ymax))
            outward_angle = 0.0
        elif side == "bottom":
            base_point = (uniform(xmin, xmax), ymin)
            outward_angle = -np.pi / 2
        else:  # "top"
            base_point = (uniform(xmin, xmax), ymax)
            outward_angle = np.pi / 2

        waste_pos = (
            base_point[0] + distance_to_district * np.cos(outward_angle),
            base_point[1] + distance_to_district * np.sin(outward_angle)
        )



        print(f"Waste-Heat {distance_to_district} m vom District-Rand ({side}), Pos: {waste_pos}")


    # %% STEP THREE: add the building attributes

    # 1 Assign building type

    # The proportion of non-residential buildings is determined in accordance with the article
    # <Siedlungsentwicklung und Infrastrukturfolgekosten - Bilanzierung und Strategieentwicklung>
    # https://www.ireus.uni-stuttgart.de/forschung/publikationen/Siedentop_etal_2006.pdf
    if district_type == "A":
        non_residential_ratio = {"H": 0.0351, "V": 0.0175, "S": 0.0044}
    elif district_type == "B":
        non_residential_ratio = {"H": 0.0741, "V": 0.0357, "S": 0.0089}
    elif district_type == "C":
        non_residential_ratio = {"H": 0.0444, "V": 0.0222, "S": 0.0056}
    elif district_type == "D":
        non_residential_ratio = {"H": 0.0296, "V": 0.0148, "S": 0.0037}
    elif district_type == "E":
        non_residential_ratio = {"H": 0.0593, "V": 0.0296, "S": 0.0074}
    elif district_type == "F":
        non_residential_ratio = {"H": 0.0684, "V": 0.0342, "S": 0.0085}
    elif district_type == "G":
        non_residential_ratio = {"H": 0.0333, "V": 0.0167, "S": 0.0042}
    elif district_type == "H":
        non_residential_ratio = {"H": 0.0769, "V": 0.0385, "S": 0.0096}
    elif district_type == "I":
        non_residential_ratio = {"H": 0.0606, "V": 0.0303, "S": 0.0076}

    # Create a list of length num_buildings, listing the corresponding number of building types.
    building_type = []

    num_school = round(non_residential_ratio[params["haeufigkeit_schule"]] * num_buildings)
    building_type.extend(["School"] * num_school)

    num_office = round(non_residential_ratio[params["haeufigkeit_buero"]] * num_buildings)
    building_type.extend(["Office"] * num_office)

    num_supermarket = round(non_residential_ratio[params["haeufigkeit_einzelhandel"]] * num_buildings)
    building_type.extend(["Supermarket"] * num_supermarket)

    num_restaurant = round(non_residential_ratio[params["haeufigkeit_gaststaette"]] * num_buildings)
    building_type.extend(["Restaurant"] * num_restaurant)

    num_craft_shop = round(non_residential_ratio[params["haeufigkeit_handwerk"]] * num_buildings)
    building_type.extend(["Craft Shop"] * num_craft_shop)

    num_agricultural_business = round(non_residential_ratio[params["haeufigkeit_landwirtschaft"]] * num_buildings)
    building_type.extend(["Agricultural Business"] * num_agricultural_business)

    num_residential = num_buildings - num_school - num_office - num_supermarket - num_restaurant - num_craft_shop - num_agricultural_business
    building_type.extend(["Residential"] * num_residential)

    shuffle(building_type)

    type_color = {
        "School": "orange",
        "Office": "lightgreen",
        "Supermarket": "gold",
        "Restaurant": "tomato",
        "Craft Shop": "plum",
        "Agricultural Business": "yellowgreen",
        "Residential": "lightblue"
    }

    # For each main building position from optimization:
    buildings_info = []
    for i, bld in enumerate(buildings):
        # Decide on the building type and drawing style.
        b_type = building_type[i]
        buildings_info.append({
            "id": i,
            "type": b_type,
            "polygon": bld,
            "color": type_color[b_type]
        })

    # 2 Assign Retrofitting Levels
    # In this step, we determine the retrofit level for each building based on statistacal datas.
    # We first extract the retrofit percentages for "unsaniert" (Unrenovated), "teilsaniert"
    # (Partially Renovated), and "vollsaniert" (Fully Renovated). Then, using the total number of
    # buildings (n_total), we calculate how many buildings should fall into each category.
    p_unr = float(params["sanierung"]["unsaniert"])/100         # %
    p_pre = float(params["sanierung"]["teilsaniert"])/100       # %
    p_fre = float(params["sanierung"]["vollsaniert"])/100       # %
    n_total = len(buildings_info)
    n_uns = int(round(n_total * p_unr))
    n_teil = int(round(n_total * p_pre))
    n_voll = n_total - n_uns - n_teil
    retro_list = (["Unrenovated"] * n_uns +
                  ["Partially Renovated"] * n_teil +
                  ["Fully Renovated"] * n_voll)
    shuffle(retro_list)
    for i, bld in enumerate(buildings_info):
        bld["retrofit_level"] = retro_list[i]

    # Define hatch patterns for retrofitting levels.
    hatch_patterns = {
        "Unrenovated": "///",
        "Partially Renovated": "xxx",
        "Fully Renovated": "++"
    }

    # 3 Assign Building Ages and Construction Years
    # In this step, we assign each building an age bracket and then select a single construction year
    # within that bracket based on statistical datas.
    age_brackets = {
        "vor_1919": (1900, 1918),
        "1919_1949": (1919, 1949),
        "1950_1959": (1950, 1959),
        "1960_1969": (1960, 1969),
        "1970_1979": (1970, 1979),
        "1980_1989": (1980, 1989),
        "1990_1999": (1990, 1999),
        "2000_2005": (2000, 2005),
        "2006_2009": (2006, 2009),
        "2010_2019": (2010, 2019)
    }

    age_categories = [
        "vor_1919", "1919_1949", "1950_1959", "1960_1969",
        "1970_1979", "1980_1989", "1990_1999", "2000_2005",
        "2006_2009", "2010_2019"
    ]

    age_percents = [
        float(params["gebaeudealter"]["vor_1919"]),
        float(params["gebaeudealter"]["1919_1949"]),
        float(params["gebaeudealter"]["1950_1959"]),
        float(params["gebaeudealter"]["1960_1969"]),
        float(params["gebaeudealter"]["1970_1979"]),
        float(params["gebaeudealter"]["1980_1989"]),
        float(params["gebaeudealter"]["1990_1999"]),
        float(params["gebaeudealter"]["2000_2005"]),
        float(params["gebaeudealter"]["2006_2009"]),
        float(params["gebaeudealter"]["2010_2019"])
    ]

    sum_age = sum(age_percents)
    age_percents = [p / sum_age for p in age_percents]
    counts = [int(round(n_total * p)) for p in age_percents]
    age_list = []
    for cat, count in zip(age_categories, counts):
        age_list.extend([cat] * count)
    shuffle(age_list)
    for i, bld in enumerate(buildings_info):
        if i < len(age_list):
            bld["age_bracket"] = age_list[i]
        else:
            bld["age_bracket"] = "Unknown"
        # Now, inline pick a random construction year within the assigned bracket.
        if bld["age_bracket"] in age_brackets:
            start, end = age_brackets[bld["age_bracket"]]
            bld["construction_year"] = randint(start, end)
        else:
            bld["construction_year"] = None

    # 4 Get the center position of the buildings
    for bld in buildings_info:
        # get the center position of the building
        polygon = bld['polygon']
        center = polygon.centroid
        bld['center'] = (center.x, center.y)

    # 5 Calculate the total floor area
    # Retrieve the quartile values for the number of full floors.
    nof_q0 = params["anzahl_vollgeschosse_0"]
    nof_q25 = params["anzahl_vollgeschosse_25"]
    nof_q50 = params["anzahl_vollgeschosse_50"]
    nof_q75 = params["anzahl_vollgeschosse_75"]
    nof_q100 = params["anzahl_vollgeschosse_100"]

    for bld in buildings_info:
        # Generate a random value in [0,1].
        r = random()

        # Interpolate 'nof' based on which quartile range 'r' falls into.
        if r < 0.25:
            # between 0% and 25%
            nof = nof_q0 + (nof_q25 - nof_q0) * (r / 0.25)
        elif r < 0.50:
            # between 25% and 50%
            nof = nof_q25 + (nof_q50 - nof_q25) * ((r - 0.25) / 0.25)
        elif r < 0.75:
            # between 50% and 75%
            nof = nof_q50 + (nof_q75 - nof_q50) * ((r - 0.50) / 0.25)
        else:
            # between 75% and 100%
            nof = nof_q75 + (nof_q100 - nof_q75) * ((r - 0.75) / 0.25)

        # Round 'nof' to the nearest 0.5 (so the result is an integer or a half-integer)
        nof = round(nof * 2) / 2

        # Compute and save the total floor area for this building.
        building_area = int(nof * run_results["building_ground_area"])
        bld["calculated_building_area"] = building_area
        bld["number_of_floors"] = nof

    # define the road information
    lines_info = []
    for j in range(len(road_lines_scaled)):
        lines_info.append({
            "id": j,
            "start": [road_lines_scaled[j].coords[0][0], road_lines_scaled[j].coords[0][1]],
            "end": [road_lines_scaled[j].coords[1][0], road_lines_scaled[j].coords[1][1]],
            "length": road_lines_scaled[j].length
        })

    # %% STEP FOUR: Plot Buildings and Infrastructure
    fig, ax = plt.subplots(figsize=(12, 8))

    # 1 plot the roads
    for line in road_lines_scaled:
        x, y = line.xy
        ax.plot(x, y, color='blue', linewidth=1)

    # 2 plot the buildings
    for bld in buildings_info:
        poly = bld['polygon']
        color = bld['color']
        hatch = hatch_patterns[bld["retrofit_level"]]

        x, y = poly.exterior.xy
        ax.fill(x, y, facecolor=color, edgecolor='gray', linewidth=0.5, hatch=hatch)

        centroid = poly.centroid
        ax.text(
            centroid.x,
            centroid.y,
            str(bld['construction_year']),
            fontsize=7,
            fontweight='bold',
            color='black',
            ha='center',
            va='center'
        )

    # 3 plot the transformer
    if transformer_pos is not None:
        ax.plot(transformer_pos[0], transformer_pos[1], 'ro', markersize=8)
        ax.text(transformer_pos[0], transformer_pos[1] + 1, '', color='red', fontsize=10, ha='center')

    if add_waste_heat:
        ax.plot(waste_pos[0], waste_pos[1], 'gs', markersize=12, label='Abwärmequelle')
        ax.text(waste_pos[0], waste_pos[1] + 2, waste_heat_type, fontsize=10, ha='center')

    # 4 Create Custom Legend
    # 4.1 Infrastructure(Transformer) legend.
    transformer_handle = plt.Line2D([], [], marker='o', color='red', linestyle='None',
                                    markersize=10, label='Transformer Station')
    waste_heat_handle = plt.Line2D([], [], marker='s', color='green', linestyle='None',
                                   markersize=12, label='Waste Heat Source')

    infra_handles = [transformer_handle, waste_heat_handle]

    # 4.2 Building type legend.
    building_types = {}
    for bld in buildings_info:
        if bld["type"] not in building_types:
            building_types[bld["type"]] = bld["color"]
        type_handles = [patches.Patch(facecolor=color, edgecolor="black", label=typ) for typ, color in building_types.items()]

    # 4.3 Retrofit level legend (using hatch patterns).
    retrofit_handles = [patches.Patch(facecolor="white", edgecolor="black", hatch=hatch_patterns[level], label=level) for level in hatch_patterns]

    all_handles = infra_handles + type_handles + retrofit_handles
    ax.legend(handles=all_handles, loc="upper left", bbox_to_anchor=(1.05, 1), fontsize=17)

    # 5 Adjust image coordinates and format
    ax.set_xlabel("Width (meters)", fontsize=20)
    ax.set_ylabel("Length (meters)", fontsize=20)
    ax.tick_params(axis='both', which='major', labelsize=20)
    ax.set_aspect('equal', adjustable='box')
    ax.set_title("District layout "+district_type, fontsize=20)
    ax.grid(True, linestyle='--', linewidth=0.3)
    plt.tight_layout()



    # 6 Save the plot and json-file
    current_dir = os.path.dirname(__file__)
    save_dir = os.path.join(current_dir, '..', 'data', 'scenarios')
    # create the folder if it doesn't exist
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    plot_filename_png = os.path.join(
        save_dir,
        f"district_layout_{district_type}_buildings_{len(buildings)}.png"
    )
    plot_filename_svg = os.path.join(
        save_dir,
        f"district_layout_{district_type}_buildings_{len(buildings)}.svg"
    )

    plt.savefig(plot_filename_png, dpi=300)
    plt.savefig(plot_filename_svg, format="svg")

    plt.show()
    print(f"The number of generated buildings is {len(buildings)}.")
    print(f"The number of model attempts is {attempts+1}.")

    # STEP FIVE: OUTPUT -> Save Results to JSON and CSV
    # Build a new list with only the keys we want to store.
    buildings_info_json = []
    for bld in buildings_info:
        buildings_info_json.append({
            "id": bld["id"],
            "type": bld["type"],
            "position": bld["center"],
            "calculated_building_area": bld["calculated_building_area"],
            "number_of_floors": bld["number_of_floors"],
            "construction_year": bld["construction_year"],
            "retrofit_level": bld["retrofit_level"]})

    if add_waste_heat:
        waste_heat_json = []
        waste_heat_json.append({
            "type": waste_heat_type,
            "position": waste_pos})

    # Save parameters
    params_filename = os.path.join(save_dir,
                                   f"district_{district_type}_buildings_{len(buildings)}.json")
    # params_filename = get_unique_filename(params_filename)
    params_filename_wh = os.path.join(save_dir,
                                   f"wh_source.json")

    with open(params_filename_wh, "w") as f:
        json.dump(waste_heat_json, f, indent=4, default=convert_to_serializable)

    with open(params_filename, 'w') as f:
        json.dump({"parameters": run_results,
                   "values": {
                       "numb_buildings": len(buildings),
                       "buildings_info": buildings_info_json,
                       "lines_info": lines_info,
                       "transformer_station": {"position": transformer_pos}
                   }}, f, indent=4, default=convert_to_serializable)

    # Save Results as CSV
    import csv
    csv_header = [
        "id", "position", "building", "year", "retrofit", "construction_type", "night_setback",
        "area", "number_of_floors",
        "heater", "cooling", "EV", "f_TES", "f_BAT", "f_PV1", "f_PV2", "f_STC", "gamma_PV", "ev_charging"
    ]
    csv_filename = params_filename.replace('.json', '.csv')
    with open(csv_filename, "w", newline="") as csvfile:
        writer = csv.writer(csvfile, delimiter=";")
        writer.writerow(csv_header)
        # Define mapping for retrofit levels: Unrenovated->0, Partially Renovated->1, Fully Renovated->2
        retrofit_mapping = {
            "Unrenovated": "0",
            "Partially Renovated": "1",
            "Fully Renovated": "2"
        }

        for bld in buildings_info_json:
            id_val = bld.get("id", "")
            position_val = bld.get("position", (0, 0))
            if bld.get("type", "").lower() == "residential":
                # Check the building's area
                area_val = bld.get("calculated_building_area", 0)
                if area_val < 200:
                    building_val = "SFH"
                else:
                    building_val = "MFH"
            elif bld.get("type", "").lower() == "restaurant":
                building_val = "RE"
            elif bld.get("type", "").lower() == "office":
                building_val = "OB"
            elif bld.get("type", "").lower() == "school":
                building_val = "SC"
            elif bld.get("type", "").lower() == "supermarket":
                building_val = "GS"
            else: # Craft Shops and Agricultural Business are replaced with residential buildings, since it is hard to generate demand profiles for these buildings
                area_val = bld.get("calculated_building_area", 0)
                if area_val < 200:
                    building_val = "SFH"
                else:
                    building_val = "MFH"

            year_val = bld.get("construction_year") if bld.get("construction_year") is not None else ""
            retrofit_val = retrofit_mapping.get(bld.get("retrofit_level", ""), "")
            construction_type_val = "2"     # 0 = Leichtbau, 1 = Mittelbau, 2 = Massivbau
            night_setback_val = "0"         # 0 = keine Nachtabsenkung, 1 = mit Nachtabsenkung
            area_val = int(round(bld.get("calculated_building_area", 0)))
            number_of_floors_val = bld.get("number_of_floors") if bld.get("construction_year") is not None else 1.0
            heater_val = "heat_grid"        # ausgewählter Wärmeerzeuger
            cooling_val = "0"               # 0/1, Whether there is a need for cooling?
            ev_val = "0"                    # Zwischen 0 und 1; Anteil der Elektroautos am Gesamtfahrzeugbestand im Gebäude
            f_TES_val = "35"                # Größe des Pufferspeichers in Liter pro kW Heizleistung der Wärmeerzeugungsanlage
            f_BAT_val = "0"                 # Größe des Batteriespeichers in abhängigkeit der Leistung der PV-Anlage in Wh/W_PV
            f_PV1_val = "0.4"               # Zwischen 0 und 1; Anteil der Dachfläche, die mit Photovoltaic ausgestattet ist (Informationen zu Dachflächen sind den Typgebäuden nach Tabula zu entnehmen)
            f_PV2_val = "0"                 # ??? Zwischen 0 und 1; Anteil der Dachfläche, die mit Photovoltaic ausgestattet ist (Informationen zu Dachflächen sind den Typgebäuden nach Tabula zu entnehmen)
            f_STC_val = "0"                 # Zwischen 0 und 1; Anteil der Dachfläche, die mit Solarthermie ausgestattet ist (Informationen zu Dachflächen sind den Typgebäuden nach Tabula zu entnehmen)
            gamma_PV_val = "0"              # Azimut = Himmelsausrichtung der PV-Anlage, Ausrichtung nach Süden: 0°
            ev_charging_val = "on_demand"   # Ladeverhalten des Elektroautos (bi-direktional: Be- und Entladung, Nutzung als Stromspeicher, on-demand: Beladung nach Bedarf, intelligent: optimierte Beladung)
            writer.writerow([
                id_val, position_val, building_val, year_val, retrofit_val, construction_type_val,
                night_setback_val, area_val, number_of_floors_val,
                heater_val, cooling_val, ev_val,
                f_TES_val, f_BAT_val, f_PV1_val, f_PV2_val, f_STC_val,
                gamma_PV_val, ev_charging_val
            ])
