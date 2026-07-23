import matplotlib.pyplot as plt
import matplotlib.patches as patches
import random as pyrandom
import os
import json
import numpy as np
from math import ceil
import shapely
from matplotlib.backends.backend_pdf import PdfPages
from districtgenerator.functions.typdistrict_preprocess import params, district_type, reseed_params
from districtgenerator.functions.typdistrict import (
    run_typdistrict_layout,
    place_adaptive_rectangle,
    select_random_buildings,
)

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

def grz_status(run_results):
    """
    Compare generated GRZ with the typdistrict GRZ range.
    """
    generated_grz = run_results["generated_grz"]
    tolerance = 0.10
    min_grz = params["grund_flaechenzahl"]["min"] * (1 - tolerance)
    max_grz = params["grund_flaechenzahl"]["max"] * (1 + tolerance)

    if generated_grz < min_grz:
        return "too_low"
    if generated_grz > max_grz:
        return "too_high"
    return "valid"

def fill_missing_f_buildings_on_existing_roads(
        placed_buildings,
        road_lines_scaled,
        num_buildings,
        building_width,
        house_connection):
    """
    Add missing type-F row buildings along existing horizontal roads only.

    This keeps the Zeilenbebauung morphology intact and avoids the generic
    fallback that extends short new road branches.
    """
    if len(placed_buildings) >= num_buildings:
        return

    horizontal_roads = [
        road for road in road_lines_scaled
        if road.coords[0][1] == road.coords[1][1] and road.coords[0][1] != 0
    ]
    pyrandom.shuffle(horizontal_roads)
    buffered_roads = [line.buffer(house_connection - 0.1) for line in road_lines_scaled]

    for road in horizontal_roads:
        if len(placed_buildings) >= num_buildings:
            break
        for side in ["left", "right"]:
            if len(placed_buildings) >= num_buildings:
                break
            road_parallel = road.parallel_offset(
                house_connection + building_width / 2,
                side,
                resolution=16,
                mitre_limit=5.0,
            )
            step = building_width + 0.1
            max_distance = max(road.length - house_connection - building_width / 2, 0)
            distances = [
                house_connection + building_width / 2 + i * step
                for i in range(int(max_distance // step) + 1)
            ]
            pyrandom.shuffle(distances)

            for distance in distances:
                if len(placed_buildings) >= num_buildings:
                    break
                point = road_parallel.interpolate(distance)
                new_building = shapely.box(
                    point.x - building_width / 2,
                    point.y - building_width / 2,
                    point.x + building_width / 2,
                    point.y + building_width / 2,
                )
                if any(new_building.intersects(building) for building in placed_buildings):
                    continue
                if any(new_building.intersects(road_buffer) for road_buffer in buffered_roads):
                    continue
                placed_buildings.append(new_building)

def validate_final_layout(buildings, road_lines_scaled, num_buildings, run_results):
    """
    Fail fast if a generated district is incomplete, has buildings on roads,
    or does not satisfy the typdistrict GRZ range.
    """
    if len(buildings) != num_buildings:
        raise RuntimeError(
            f"Generated district is incomplete: {len(buildings)} / {num_buildings} buildings. "
            "This seed/layout must be regenerated with different geometry parameters or another seed."
        )

    road_buffers = [road.buffer(0.5) for road in road_lines_scaled]
    bad_buildings = [
        index
        for index, building in enumerate(buildings)
        if any(building.intersects(road_buffer) for road_buffer in road_buffers)
    ]
    if bad_buildings:
        raise RuntimeError(
            "Generated district has building footprints on road centerlines. "
            f"Invalid building indices: {bad_buildings}"
        )

    status = grz_status(run_results)
    if status != "valid":
        generated_grz = run_results["generated_grz"]
        min_grz = params["grund_flaechenzahl"]["min"]
        max_grz = params["grund_flaechenzahl"]["max"]
        accepted_min_grz = min_grz * 0.90
        accepted_max_grz = max_grz * 1.10
        raise RuntimeError(
            f"Generated GRZ is {status}: {generated_grz:.3f} outside "
            f"accepted range [{accepted_min_grz:.3f}, {accepted_max_grz:.3f}] "
            f"(input range [{min_grz:.3f}, {max_grz:.3f}])."
        )

def scenario_generation(
        num_buildings_override=None,
        retry_depth=0,
        max_seed_retries=50,
        type_i_soft_delete_retry=False):
    """
    Obtain buildings and roads layouts based on the input building type and number of buildings.

    Returns
    -------
    None
    """
    seed = int(params["random_seed"])
    pyrandom.seed(seed)
    np.random.seed(seed)
    # %% STEP ONE: set parameters for the model
    if num_buildings_override is None:
        num_buildings = int(input("\nEnter the number of buildings: "))
    else:
        num_buildings = int(num_buildings_override)
    building_density = params["gebaeude_pro_ha"]["value"]  # buildings per hectare
    # building_density = 5
    building_density_min = params["gebaeude_pro_ha"]["min"]  # buildings per hectare
    building_density_max = params["gebaeude_pro_ha"]["max"]  # buildings per hectare
    width_length_ratio_mean = params["seitenverhaeltnis"]["mean_value"]
    house_connection = params["HA-Leitungen"]["value"]  # Length of house connection lines in m
    distance_between_buildings_min = params["abstand_hausanschluesse"]["min"]  # meters

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
        delete_ratio = 0.4 if type_i_soft_delete_retry else 0.6

    def retry_seed_after_layout_error(error):
        if retry_depth >= max_seed_retries:
            raise RuntimeError(
                f"Could not generate a valid district after {max_seed_retries + 1} seed attempts. "
                f"Last attempted seed: {params['random_seed']}."
            ) from error

        failed_seed = int(params["random_seed"])
        next_seed = failed_seed + 1
        print(f"Seed {failed_seed} rejected: {error}")
        print(f"Trying next seed: {next_seed}")
        reseed_params(next_seed)
        return scenario_generation(
            num_buildings_override=num_buildings,
            retry_depth=retry_depth + 1,
            max_seed_retries=max_seed_retries,
            type_i_soft_delete_retry=False,
        )

    # %% STEP TWO: Repeat running the model until getting a conforming district layout
    # run the model for the first time
    try:
        road_lines_scaled, placed_buildings, transformer_pos, run_results, get_bigger_density = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio))
    except ValueError as error:
        return retry_seed_after_layout_error(error)

    # Limit the maximum number of attempts to avoid model dead loops.
    max_attempts = 30
    attempts = 0

    # If there is too much empty space in the district layout,
    # adjust the road deletion_ratio and building_density, and rerun the model code.
    while get_bigger_density == True and len(placed_buildings) == num_buildings and attempts < max_attempts:
        if district_type not in ["E", "F", "H"]:
            delete_ratio += 0.02
        rate = pyrandom.uniform(0, 1)
        building_density += rate
        building_density = min(building_density, building_density_max)
        attempts += 1
        road_lines_scaled, placed_buildings, transformer_pos, run_results, get_bigger_density = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio))

    # If the number of buildings generated is less than the required number,
    # adjust the road deletion_ratio and building_density, and rerun the model code.
    while len(placed_buildings) < num_buildings and attempts < max_attempts:
        delete_ratio = max(delete_ratio - 0.02, 0)
        rate = pyrandom.uniform(0, 1)
        building_density -= rate
        building_density = max(building_density_min, building_density)
        attempts += 1
        road_lines_scaled, placed_buildings, transformer_pos, run_results, get_bigger_density = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio))

    # Validate the generated ground space index (GRZ). If the generated
    # morphology is outside the typdistrict GRZ range, adjust the density and
    # rerun. This keeps GRZ as a validation-guided target instead of forcing it
    # directly into the geometry.
    grz_attempts = 0
    max_grz_attempts = 30
    while (len(placed_buildings) >= num_buildings and grz_status(run_results) != "valid"
           and attempts < max_attempts and grz_attempts < max_grz_attempts):
        status = grz_status(run_results)
        generated_grz = max(run_results["generated_grz"], 1e-6)

        if status == "too_low":
            min_grz = params["grund_flaechenzahl"]["min"]
            density_factor = min(max(min_grz / generated_grz, 1.10), 2.0)
            building_density = min(building_density * density_factor, building_density_max)
            if district_type not in ["E", "F", "H"]:
                delete_ratio += 0.01
        else:
            max_grz = params["grund_flaechenzahl"]["max"]
            density_factor = max(min(max_grz / generated_grz, 0.90), 0.5)
            building_density = max(building_density * density_factor, building_density_min)
            delete_ratio = max(delete_ratio - 0.01, 0)

        attempts += 1
        grz_attempts += 1
        road_lines_scaled, placed_buildings, transformer_pos, run_results, get_bigger_density = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio))

    # parameter switch_g turns to 1 for district type G
    if len(placed_buildings) < num_buildings and district_type == 'G':
        road_lines_scaled, placed_buildings, transformer_pos, run_results, _ = (
            run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio, switch_g=1))

    # The final check to ensure that the number of buildings meets the requirements.
    if len(placed_buildings) < num_buildings and district_type == "F":
        fill_missing_f_buildings_on_existing_roads(
            placed_buildings=placed_buildings,
            road_lines_scaled=road_lines_scaled,
            num_buildings=num_buildings,
            building_width=run_results["building_width"],
            house_connection=house_connection,
        )

    if len(placed_buildings) < num_buildings and district_type != "F":
        num_missing_building = num_buildings - len(placed_buildings)
        building_width = run_results["building_width"]
        building_ground_area = run_results["building_ground_area"]
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
            pyrandom.shuffle(top_edge_points)

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
                        # Try adaptive rectangular footprints with fixed area.
                        new_building = place_adaptive_rectangle(
                            p, road, building_ground_area, placed_buildings,
                            road_lines_scaled, house_connection, 0.0)
                        if new_building is not None:
                            placed_buildings.append(new_building)

        if direction == "right":
            # Get the coordinates of all rightmost road nodes that need to be extended
            max_x = max(pt[0] for pt in all_points)
            right_edge_points = [pt for pt in all_points if pt[0] == max_x]
            pyrandom.shuffle(right_edge_points)

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
                        # Try adaptive rectangular footprints with fixed area.
                        new_building = place_adaptive_rectangle(
                            p, road, building_ground_area, placed_buildings,
                            road_lines_scaled, house_connection, 0.0)
                        if new_building is not None:
                            placed_buildings.append(new_building)

    if district_type == "F":
        buildings = placed_buildings[:num_buildings]
    else:
        buildings = select_random_buildings(placed_buildings, num_buildings)

    def retry_or_raise(error):
        if district_type == "I" and not type_i_soft_delete_retry:
            failed_seed = int(params["random_seed"])
            print(f"Seed {failed_seed} rejected with normal type-I delete_ratio path: {error}")
            print(f"Retrying seed {failed_seed} with type-I delete_ratio 0.4")
            reseed_params(failed_seed)
            return scenario_generation(
                num_buildings_override=num_buildings,
                retry_depth=retry_depth,
                max_seed_retries=max_seed_retries,
                type_i_soft_delete_retry=True,
            )

        if retry_depth >= max_seed_retries:
            raise RuntimeError(
                f"Could not generate a valid district after {max_seed_retries + 1} seed attempts. "
                f"Last attempted seed: {params['random_seed']}."
            ) from error

        failed_seed = int(params["random_seed"])
        next_seed = failed_seed + 1
        print(f"Seed {failed_seed} rejected: {error}")
        print(f"Trying next seed: {next_seed}")
        reseed_params(next_seed)
        return scenario_generation(
            num_buildings_override=num_buildings,
            retry_depth=retry_depth + 1,
            max_seed_retries=max_seed_retries,
            type_i_soft_delete_retry=False,
        )

    try:
        validate_final_layout(buildings, road_lines_scaled, num_buildings, run_results)
    except RuntimeError as error:
        return retry_or_raise(error)

    # %% STEP THREE: add the building attributes

    # 1 Assign building type

    # Create a list of length num_buildings with the main use category of each building:
    # Residential       -> SFH or MFH
    # Mixed             -> SFH/MFH + non-residential use, e.g. MFH+OB
    # NonResidential    -> only non-residential use, e.g. OB
    use_shares = {
        "NonResidential": float(params["share_non_residential"]),
        "Mixed": float(params["share_mixed_use"]),
        "Residential": float(params["share_residential"])
    }
    if sum(use_shares.values()) > 1.5:
        use_shares = {
            use_category: share / 100.0
            for use_category, share in use_shares.items()
        }

    # Draw the main use of each building from the OSM-based probabilities.
    # Over many seeds, the average follows the OSM shares. Individual 30-building
    # districts remain varied instead of being forced into identical rounded counts.
    use_categories = list(use_shares.keys())
    use_weights = list(use_shares.values())
    building_use_categories = pyrandom.choices(
        use_categories,
        weights=use_weights,
        k=num_buildings
    )

    osm_nrb_type_percentages = params.get("osm_nrb_type_percentages", {})

    # These building types should occur at most once in the whole district.
    hospital_added = False
    university_added = False

    def get_available_non_residential_type_pool(allow_education=True):
        """
        Build a weighted pool of possible non-residential building types.

        If allow_education=False, SC, UNI, HOSPITAL, and SPORT are excluded.
        This is used for mixed-use buildings, because mixed-use buildings should not contain
        schools, universities, hospitals, or sports halls.
        """
        available_type_pool = []
        target_weights = {
            building_type_option: float(weight)
            for building_type_option, weight in osm_nrb_type_percentages.items()
            if float(weight) > 0
        }

        for building_type_option, weight in sorted(target_weights.items()):

            # Mixed-use buildings are not allowed to contain schools,
            # universities, or hospitals.
            if not allow_education and building_type_option in ["SC", "UNI", "HOSPITAL", "SPORT"]:
                continue

            # Hospital and university should each occur at most once in the whole district.
            if building_type_option == "HOSPITAL" and hospital_added:
                continue

            if building_type_option == "UNI" and university_added:
                continue

            if weight <= 0:
                continue

            available_type_pool.append((building_type_option, weight))

        return available_type_pool

    def select_non_residential_type_stochastically(
            current_building,
            already_assigned_buildings,
            allow_education=True
    ):
        """
        Select one non-residential building type from the OSM probabilities.

        Hospital and university stay capped at one per generated district.
        """
        nonlocal hospital_added, university_added

        available_type_pool = get_available_non_residential_type_pool(
            allow_education=allow_education
        )

        # Safety fallback.
        if not available_type_pool:
            return "OB"

        candidate_types, candidate_weights = zip(*available_type_pool)
        selected_type = pyrandom.choices(
            list(candidate_types),
            weights=list(candidate_weights),
            k=1
        )[0]

        if selected_type == "HOSPITAL":
            hospital_added = True
        elif selected_type == "UNI":
            university_added = True

        return selected_type

    type_color = {
        "SFH": "#A6CEE3",
        "TH": "#8DD3C7",
        "MFH": "#56B4E9",
        "SC": "#1F78B4",
        "UNI": "#6A3D9A",
        "OB": "#33A02C",
        "HOSPITAL": "#E31A1C",
        "CULTURE": "#CAB2D6",
        "SPORT": "#FDBF6F",
        "RETAIL": "#FF7F00",
        "GS": "#B15928",
        "RE": "#FB9A99",
        "WORKSHOP": "#B2DF8A"
    }

    type_label = {
        "SC": "School",
        "UNI": "University",
        "OB": "Office",
        "HOSPITAL": "Hospital",
        "CULTURE": "Culture",
        "SPORT": "Sport",
        "RETAIL": "Retail Store",
        "GS": "Grocery Store",
        "RE": "Restaurant",
        "WORKSHOP": "Workshop",
        "SFH": "SFH",
        "TH": "TH",
        "MFH": "MFH",
        "Residential_SFH": "SFH",
        "Residential_TH": "TH",
        "Residential_MFH": "MFH"
    }

    def touches_other_building(current_building, all_buildings, tolerance=0.5):
        """
        Return True if a building footprint touches or nearly touches another footprint.

        A small visual/geometric tolerance is used because generated footprints
        can have tiny construction gaps even when the intended urban form is a
        wall-to-wall attached building.
        """
        current_polygon = current_building["polygon"]
        for other_building in all_buildings:
            if other_building is current_building:
                continue
            if current_polygon.distance(other_building["polygon"]) <= tolerance:
                return True
        return False

    def assign_residential_typology_from_source_shares():
        """
        Assign EFH/MFH source typology to pure residential buildings.

        Mixed-use buildings are handled separately as MFH + non-residential
        ground-floor use, so they are not part of this EFH/MFH share assignment.
        """
        residential_part_buildings = [
            bld for bld in buildings_info
            if bld["use_category"] == "Residential"
        ]
        if not residential_part_buildings:
            return

        typology_shares = params.get("residential_typology_shares", {})
        efh_share = float(typology_shares.get("EFH", 0))
        mfh_share = float(typology_shares.get("MFH", 0))
        if efh_share + mfh_share > 1.5:
            efh_share /= 100.0
            mfh_share /= 100.0

        total_share = efh_share + mfh_share
        if total_share <= 0:
            efh_share = 1.0
            mfh_share = 0.0
            total_share = 1.0

        efh_share /= total_share
        mfh_share /= total_share

        typology_pool = (
            ["EFH"] * int(round(len(residential_part_buildings) * efh_share))
            + ["MFH"] * int(round(len(residential_part_buildings) * mfh_share))
        )
        while len(typology_pool) < len(residential_part_buildings):
            typology_pool.append("EFH" if efh_share >= mfh_share else "MFH")
        typology_pool = typology_pool[:len(residential_part_buildings)]
        pyrandom.shuffle(typology_pool)

        for bld, source_typology in zip(residential_part_buildings, typology_pool):
            bld["source_residential_typology"] = source_typology

    def floor_limits_for_building(residential_base_type, bld):
        """
        Return typology-specific floor limits.

        EFH-derived SFH/TH are intentionally capped. MFH floors are not
        forced to be at least 3; they only need enough floors to exceed the
        EFH floor-area limit. Pure non-residential restaurants, grocery
        stores, retail stores, and workshops additionally receive usable-area
        limits. Mixed-use non-residential parts are not limited here because
        they are represented as one floor during profile generation.
        """
        max_nof = float(params["max_anzahl_vollgeschosse"])
        max_efh_gfa = 216.0
        pure_non_residential_area_ranges = {
            "RE": (80.0, 350.0),
            "GS": (150.0, 1500.0),
            "RETAIL": (80.0, 1000.0),
            "WORKSHOP": (120.0, 2000.0),
        }
        pure_non_residential_min_areas = {
            "OB": 100.0,
            "SC": 300.0,
            "UNI": 500.0,
            "HOSPITAL": 350.0,
            "CULTURE": 120.0,
            "SPORT": 250.0,
        }

        if residential_base_type == "SFH":
            return 1.0, 2.5
        if residential_base_type == "TH":
            return 1.0, 2.5
        if residential_base_type == "MFH":
            min_floor_by_area = np.ceil(((max_efh_gfa + 1e-6) / bld["polygon"].area) * 2) / 2
            if bld["use_category"] == "Mixed":
                min_floor_by_area = max(3.0, min_floor_by_area)
            return max(1.0, min_floor_by_area), max(1.0, max_nof)

        if (
                bld["use_category"] == "NonResidential"
                and residential_base_type in pure_non_residential_area_ranges
        ):
            min_area, max_area = pure_non_residential_area_ranges[residential_base_type]
            min_floor_by_area = np.ceil((min_area / bld["polygon"].area) * 2) / 2
            max_floor_by_area = np.floor((max_area / bld["polygon"].area) * 2) / 2
            return max(1.0, min_floor_by_area), min(max(1.0, max_nof), max_floor_by_area)

        if (
                bld["use_category"] == "NonResidential"
                and residential_base_type in pure_non_residential_min_areas
        ):
            min_area = pure_non_residential_min_areas[residential_base_type]
            min_floor_by_area = np.ceil((min_area / bld["polygon"].area) * 2) / 2
            return max(1.0, min_floor_by_area), max(1.0, max_nof)

        return 1.0, max(1.0, max_nof)

    def assign_typology_specific_floors_to_gfz_target():
        """
        Assign plausible floors by typology and adjust floors until the
        generated GFZ lies inside the typdistrict GFZ range.

        The adjustment is distributed within typology groups so one MFH or
        non-residential building cannot absorb nearly the whole GFZ correction.
        """
        max_efh_gfa = 216.0
        floor_spread_limit = 2.0

        for bld in buildings_info:
            if bld["use_category"] == "Mixed":
                residential_base_type = "MFH"
            elif bld.get("source_residential_typology") == "EFH":
                residential_base_type = "SFH"
                if touches_other_building(bld, buildings_info):
                    residential_base_type = "TH"
            elif bld["use_category"] == "Residential":
                residential_base_type = "MFH"
            else:
                residential_base_type = bld["non_residential_type"]

            min_floor, max_floor = floor_limits_for_building(residential_base_type, bld)

            # EFH-derived SFH/TH must remain small. If the footprint is too
            # large even with the minimum floor count, the seed is inconsistent
            # with the required EFH/MFH share and must be rejected.
            if residential_base_type in {"SFH", "TH"}:
                max_floor_by_area = np.floor((max_efh_gfa / bld["polygon"].area) * 2) / 2
                max_floor = min(max_floor, max_floor_by_area)
                if max_floor < min_floor:
                    raise RuntimeError(
                        f"{residential_base_type} footprint is too large for <= {max_efh_gfa:.0f} m2 "
                        f"total floor area: footprint={bld['polygon'].area:.1f} m2."
                    )
            elif max_floor < min_floor:
                raise RuntimeError(
                    f"{residential_base_type} footprint cannot satisfy the floor-area rule: "
                    f"footprint={bld['polygon'].area:.1f} m2, "
                    f"floor range=[{min_floor:.1f}, {max_floor:.1f}]."
                )

            bld["residential_base_type"] = residential_base_type
            bld["_min_number_of_floors"] = min_floor
            bld["_max_number_of_floors"] = max_floor

            small_variation_max_floor = min(max_floor, min_floor + 1.0)
            floor_options = np.arange(min_floor, small_variation_max_floor + 0.25, 0.5)
            bld["number_of_floors"] = float(pyrandom.choice(list(floor_options)))

        district_area_m2 = run_results["area"] * 10000
        min_gfz = float(params["geschoss_flaechenzahl"]["min"])
        max_gfz = float(params["geschoss_flaechenzahl"]["max"])
        gfz_tolerance = 0.10
        min_floor_area = min_gfz * (1 - gfz_tolerance) * district_area_m2
        max_floor_area = max_gfz * (1 + gfz_tolerance) * district_area_m2

        adjustable_buildings = buildings_info[:]

        def floor_group_key(bld):
            if bld["residential_base_type"] in {"SFH", "TH", "MFH"}:
                return bld["residential_base_type"]
            return "NonResidential"

        def group_floor_bounds():
            bounds = {}
            for item in adjustable_buildings:
                key = floor_group_key(item)
                floors = item["number_of_floors"]
                if key not in bounds:
                    bounds[key] = [floors, floors]
                else:
                    bounds[key][0] = min(bounds[key][0], floors)
                    bounds[key][1] = max(bounds[key][1], floors)
            return bounds

        for _ in range(10000):
            current_floor_area = sum(
                bld["polygon"].area * bld["number_of_floors"]
                for bld in buildings_info
            )
            if min_floor_area <= current_floor_area <= max_floor_area:
                break

            if current_floor_area < min_floor_area:
                bounds = group_floor_bounds()
                candidates = [
                    bld for bld in adjustable_buildings
                    if bld["number_of_floors"] + 0.5 <= bld["_max_number_of_floors"]
                    and bld["number_of_floors"] + 0.5 <= (
                        bounds[floor_group_key(bld)][0] + floor_spread_limit
                    )
                ]
                direction = 1
                target_boundary = min_floor_area
                candidate_key = lambda candidate: (
                    candidate["number_of_floors"],
                    abs(
                        target_boundary - (
                            current_floor_area + 0.5 * candidate["polygon"].area
                        )
                    )
                )
            else:
                bounds = group_floor_bounds()
                candidates = [
                    bld for bld in adjustable_buildings
                    if bld["number_of_floors"] - 0.5 >= bld["_min_number_of_floors"]
                    and bld["number_of_floors"] - 0.5 >= (
                        bounds[floor_group_key(bld)][1] - floor_spread_limit
                    )
                ]
                direction = -1
                target_boundary = max_floor_area
                candidate_key = lambda candidate: (
                    -candidate["number_of_floors"],
                    abs(
                        target_boundary - (
                            current_floor_area - 0.5 * candidate["polygon"].area
                        )
                    )
                )

            if not candidates:
                break

            best = min(candidates, key=candidate_key)
            best["number_of_floors"] += direction * 0.5

        for bld in buildings_info:
            nof = bld["number_of_floors"]
            building_area = int(nof * bld["polygon"].area)
            bld["calculated_building_area"] = building_area
            bld.pop("_min_number_of_floors", None)
            bld.pop("_max_number_of_floors", None)

    def validate_residential_typology_shares():
        """
        Check that generated EFH/MFH shares stay close to the source shares.

        The check is applied to pure residential buildings only. Mixed-use
        buildings are intentionally represented as MFH + non-residential use.
        """
        residential_part_buildings = [
            bld for bld in buildings_info
            if bld["use_category"] == "Residential"
        ]
        if not residential_part_buildings:
            return

        typology_shares = params.get("residential_typology_shares", {})
        efh_target = float(typology_shares.get("EFH", 0.0))
        mfh_target = float(typology_shares.get("MFH", 0.0))
        if efh_target + mfh_target > 1.5:
            efh_target /= 100.0
            mfh_target /= 100.0

        target_sum = efh_target + mfh_target
        if target_sum <= 0:
            return

        efh_target /= target_sum
        mfh_target /= target_sum

        efh_count = sum(
            1 for bld in residential_part_buildings
            if bld["residential_base_type"] in {"SFH", "TH"}
        )
        mfh_count = sum(
            1 for bld in residential_part_buildings
            if bld["residential_base_type"] == "MFH"
        )
        total_count = len(residential_part_buildings)
        efh_share = efh_count / total_count
        mfh_share = mfh_count / total_count
        tolerance = 0.10

        if abs(efh_share - efh_target) > tolerance or abs(mfh_share - mfh_target) > tolerance:
            raise RuntimeError(
                "Generated EFH/MFH shares are outside the accepted 10 percentage point tolerance: "
                f"EFH={efh_share:.3f} target={efh_target:.3f}, "
                f"MFH={mfh_share:.3f} target={mfh_target:.3f}."
            )

    def get_legend_label(legend_type):
        """
        Convert internal legend_type into a readable legend label.
        """
        if legend_type.startswith("Mixed_"):
            parts = legend_type.split("_")
            residential_part = parts[1]
            non_residential_part = parts[2]

            return (
                f"{residential_part} + "
                f"{type_label.get(non_residential_part, non_residential_part)}"
            )

        return type_label.get(legend_type, legend_type)

    # For each main building position from optimization:
    # Use a shuffled assignment order so that the spatial distribution is not biased
    # by the original geometry/list order.
    assignment_order = list(range(len(buildings)))
    pyrandom.shuffle(assignment_order)

    buildings_info = [None] * len(buildings)

    for i in assignment_order:
        bld = buildings[i]
        use_category = building_use_categories[i]

        building_entry = {
            "id": i,
            "use_category": use_category,
            "non_residential_type": None,
            "type": use_category,
            "polygon": bld,
            "color": type_color["SFH"],
            "edge_color": "gray",
            "line_width": 0.5
        }

        already_assigned_buildings = [
            existing_building
            for existing_building in buildings_info
            if existing_building is not None
        ]

        if use_category == "Residential":
            non_residential_type = None
            plot_color_type = "SFH"

        elif use_category == "Mixed":
            non_residential_type = select_non_residential_type_stochastically(
                current_building=building_entry,
                already_assigned_buildings=already_assigned_buildings,
                allow_education=False
            )
            plot_color_type = "MFH"
            building_entry["edge_color"] = type_color[non_residential_type]
            building_entry["line_width"] = 2.5


        else:  # NonResidential
            non_residential_type = select_non_residential_type_stochastically(
                current_building=building_entry,
                already_assigned_buildings=already_assigned_buildings,
                allow_education=True
            )

            plot_color_type = non_residential_type

        building_entry["non_residential_type"] = non_residential_type
        building_entry["color"] = type_color[plot_color_type]
        buildings_info[i] = building_entry

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
    pyrandom.shuffle(retro_list)
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

    # Ensure that the total number of age entries matches the number of buildings.
    difference = n_total - sum(counts)

    if difference > 0:
        # Add missing entries to the categories with the highest probabilities.
        sorted_indices = np.argsort(age_percents)[::-1]
        for i in range(difference):
            counts[sorted_indices[i % len(counts)]] += 1

    elif difference < 0:
        # Remove extra entries from categories with the highest counts.
        for _ in range(abs(difference)):
            max_index = int(np.argmax(counts))
            counts[max_index] -= 1

    age_list = []
    for cat, count in zip(age_categories, counts):
        age_list.extend([cat] * count)
    pyrandom.shuffle(age_list)
    for i, bld in enumerate(buildings_info):
        bld["age_bracket"] = age_list[i]
        start, end = age_brackets[bld["age_bracket"]]
        bld["construction_year"] = pyrandom.randint(start, end)

    # 4 Get the center position of the buildings
    for bld in buildings_info:
        # get the center position of the building
        polygon = bld['polygon']
        center = polygon.centroid
        bld['center'] = (center.x, center.y)

    assign_residential_typology_from_source_shares()

    # 5 Calculate the total floor area
    try:
        assign_typology_specific_floors_to_gfz_target()
        validate_residential_typology_shares()
    except RuntimeError as error:
        return retry_or_raise(error)

    for bld in buildings_info:
        residential_base_type = bld["residential_base_type"]

        if bld["use_category"] == "Residential":
            bld["color"] = type_color[residential_base_type]
            bld["edge_color"] = "gray"
            bld["line_width"] = 0.5

        elif bld["use_category"] == "Mixed":
            bld["color"] = type_color[residential_base_type]
            bld["edge_color"] = type_color[bld["non_residential_type"]]
            bld["line_width"] = 2.5

        else:  # NonResidential
            bld["color"] = type_color[bld["non_residential_type"]]
            bld["edge_color"] = "gray"
            bld["line_width"] = 0.5

        # Create final building code for CSV/JSON and legend.
        if bld["use_category"] == "Residential":
            bld["building_code"] = residential_base_type
            bld["legend_type"] = f"Residential_{residential_base_type}"

        elif bld["use_category"] == "Mixed":
            bld["building_code"] = f"{residential_base_type}+{bld['non_residential_type']}"
            bld["legend_type"] = f"Mixed_{residential_base_type}_{bld['non_residential_type']}"

        else:  # NonResidential
            bld["building_code"] = bld["non_residential_type"]
            bld["legend_type"] = bld["non_residential_type"]

    total_floor_area = sum(bld["calculated_building_area"] for bld in buildings_info)
    total_footprint_area = sum(bld["polygon"].area for bld in buildings_info)
    district_area_m2 = run_results["area"] * 10000
    generated_gfz = total_floor_area / district_area_m2 if district_area_m2 > 0 else 0
    generated_average_floors = (
        total_floor_area / total_footprint_area
        if total_footprint_area > 0
        else 0
    )
    run_results.update({
        "generated_gfz": generated_gfz,
        "generated_average_floors": generated_average_floors
    })
    min_gfz = float(params["geschoss_flaechenzahl"]["min"])
    max_gfz = float(params["geschoss_flaechenzahl"]["max"])
    accepted_min_gfz = min_gfz * 0.90
    accepted_max_gfz = max_gfz * 1.10
    if generated_gfz < accepted_min_gfz or generated_gfz > accepted_max_gfz:
        return retry_or_raise(
            RuntimeError(
                f"Generated GFZ is outside the accepted range: {generated_gfz:.3f} "
                f"not in [{accepted_min_gfz:.3f}, {accepted_max_gfz:.3f}] "
                f"(input range [{min_gfz:.3f}, {max_gfz:.3f}])."
            )
        )

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
    current_dir = os.path.dirname(__file__)
    save_dir = os.path.join(current_dir, '..', 'data', 'scenarios')
    plt.ion()  # enable interactive plotting
    pdf_path = os.path.join(
        save_dir,
        f"district_layout_steps_{district_type}_seed_{seed}_buildings_{num_buildings}.pdf"
    )
    pdf = PdfPages(pdf_path)

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.axis('off')
    ax.set_aspect('equal')

    # determine full bounds first (prevents rescaling later) ----
    for line in road_lines_scaled:
        x, y = line.xy
        ax.plot(x, y, alpha=0)

    for bld in buildings_info:
        poly = bld['polygon']
        x, y = poly.exterior.xy
        ax.fill(x, y, alpha=0)

    ax.relim()
    ax.autoscale_view()

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()

    # clear the invisible objects
    ax.clear()
    ax.axis('off')
    ax.set_aspect('equal')

    # remove outer margins
    ax.margins(0)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

    step = 0

    # STEP 1 — roads
    for line in road_lines_scaled:
        x, y = line.xy

        # road asphalt
        ax.plot(
            x, y,
            color='black',
            linewidth=7,
            solid_capstyle='round',
            zorder=1
        )

        # dashed center line
        ax.plot(
            x, y,
            color='white',
            linewidth=1,
            linestyle=(0, (6, 6)),  # dashed pattern
            solid_capstyle='round',
            zorder=2
        )

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0)
    step += 1

    # STEP 2 — building placement (black boxes)
    for bld in buildings_info:
        poly = bld['polygon']
        x, y = poly.exterior.xy
        ax.fill(x, y, facecolor='white', edgecolor='black', linewidth=1)

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0)
    step += 1

    # STEP 3 — final buildings
    for bld in buildings_info:
        poly = bld['polygon']
        color = bld['color']
        hatch = hatch_patterns[bld["retrofit_level"]]

        x, y = poly.exterior.xy
        edge_color = bld["edge_color"]
        line_width = bld["line_width"]

        ax.fill(
            x, y,
            facecolor=color,
            edgecolor=edge_color,
            linewidth=line_width,
            hatch=hatch
        )

        centroid = poly.centroid
        ax.text(
            centroid.x,
            centroid.y,
            str(bld['construction_year']),
            fontsize=14,
            fontweight='bold',
            color='black',
            ha='center',
            va='center'
        )

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0)
    step += 1

    # STEP 4 — transformer
    if transformer_pos is not None:
        ax.plot(transformer_pos[0], transformer_pos[1], 'ro', markersize=8)

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0)
    step += 1

    # STEP 5 — legend
    transformer_handle = plt.Line2D([], [], marker='o', color='red',
                                    linestyle='None', markersize=10,
                                    label='Energy Hub')

    building_types = {}
    for bld in buildings_info:
        legend_type = bld["legend_type"]
        if legend_type not in building_types:
            building_types[legend_type] = {
                "facecolor": bld["color"],
                "edgecolor": bld["edge_color"],
                "linewidth": bld["line_width"],
            }

    def legend_sort_key(legend_type):
        if legend_type == "Residential_MFH":
            return (0, legend_type)

        if legend_type == "Residential_SFH":
            return (1, legend_type)

        if legend_type.startswith("Mixed_"):
            return (2, legend_type)

        return (3, legend_type)

    ordered_legend_types = sorted(building_types.keys(), key=legend_sort_key)

    type_handles = []

    for typ in ordered_legend_types:
        style = building_types[typ]

        type_handles.append(
            patches.Patch(
                facecolor=style["facecolor"],
                edgecolor=style["edgecolor"],
                linewidth=style["linewidth"],
                label=get_legend_label(typ)
            )
        )

    retrofit_handles = [
        patches.Patch(facecolor="white", edgecolor="black",
                      hatch=hatch_patterns[level], label=level)
        for level in hatch_patterns
    ]

    all_handles = [transformer_handle] + type_handles + retrofit_handles

    ax.legend(handles=all_handles,
              loc="upper left",
              bbox_to_anchor=(1.02, 1),
              fontsize=21)

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    pdf.savefig(fig, bbox_inches='tight', pad_inches=0)
    step += 1

    # 6 Save the plot and json-file

    # create the folder if it doesn't exist
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    plot_filename_png = os.path.join(
        save_dir,
        f"district_layout_{district_type}_seed_{seed}_buildings_{len(buildings)}.png"
    )
    plot_filename_svg = os.path.join(
        save_dir,
        f"district_layout_{district_type}_seed_{seed}_buildings_{len(buildings)}.svg"
    )

    plt.savefig(plot_filename_png, dpi=300, bbox_inches='tight', pad_inches=0)
    plt.savefig(plot_filename_svg, format="svg", bbox_inches='tight', pad_inches=0)
    pdf.close()

    plt.show()
    print(f"The number of generated buildings is {len(buildings)}.")
    print(f"The number of model attempts is {attempts+1}.")

    # STEP FIVE: OUTPUT -> Save Results to JSON and CSV
    # Build a new list with only the keys we want to store.
    buildings_info_json = []
    for bld in buildings_info:
        buildings_info_json.append({
            "id": bld["id"],
            "use_category": bld["use_category"],
            "non_residential_type": bld["non_residential_type"],
            "building_code": bld["building_code"],
            "position": bld["center"],
            "calculated_building_area": bld["calculated_building_area"],
            "number_of_floors": bld["number_of_floors"],
            "construction_year": bld["construction_year"],
            "retrofit_level": bld["retrofit_level"]
        })

    # Save parameters
    params_filename = os.path.join(save_dir,
                                   f"district_{district_type}_seed_{seed}_buildings_{len(buildings)}.json")
    # params_filename = get_unique_filename(params_filename)

    with open(params_filename, 'w') as f:
        json.dump({
            "metadata": {
                "settlement_type": district_type,
                "random_seed": seed,
                "target_number_of_buildings": num_buildings
            },
            "parameters": run_results,
            "values": {
                "numb_buildings": len(buildings),
                "buildings_info": buildings_info_json,
                "lines_info": lines_info,
                "energy_hub": {"position": transformer_pos}
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
            building_val = bld.get("building_code", "")

            year_val = bld.get("construction_year") if bld.get("construction_year") is not None else ""
            retrofit_val = retrofit_mapping.get(bld.get("retrofit_level", ""), "")
            construction_type_val = "2"     # 0 = Leichtbau, 1 = Mittelbau, 2 = Massivbau
            night_setback_val = "0"         # 0 = keine Nachtabsenkung, 1 = mit Nachtabsenkung
            area_val = int(round(bld.get("calculated_building_area", 0)))
            number_of_floors_val = bld.get("number_of_floors") if bld.get("construction_year") is not None else 1.0
            heater_val = "heat_grid"        # ausgewählter Wärmeerzeuger
            cooling_val = "0"               # 0/1, Whether there is a need for cooling?
            ev_val = "0"                    # Zwischen 0 und 1; Anteil der Elektroautos am Gesamtfahrzeugbestand im Gebäude
            f_TES_val = "15"                # Größe des Pufferspeichers in Liter pro kW Heizleistung der Wärmeerzeugungsanlage
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

    return {
        "district_type": district_type,
        "seed": seed,
        "num_buildings": len(buildings),
        "target_num_buildings": num_buildings,
        "csv_filename": csv_filename,
        "json_filename": params_filename,
    }
