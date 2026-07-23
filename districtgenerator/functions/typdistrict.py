import networkx as nx
import shapely
from shapely.affinity import scale
from shapely.ops import unary_union
from random import shuffle, uniform, choice, sample
from math import sqrt, ceil, floor, atan2
import numpy as np
from districtgenerator.functions.typdistrict_preprocess import params, random_with_mean

def compute_inner_rectangle(district_type, num_buildings, building_density, width_length_ratio, building_width, house_connection):
    """
    Since the area calculated from building density represents the total area of the district,
    road layout requires the enclosed area formed by the outermost roads,
    a function is needed to estimate the enclosed road area from the total district area.
    For Type E districts, roads are assumed to have buildings on both sides (left and right).
    For Type F districts, the enclosed road area is assumed to be equal to the total district area.
    For all other district types, roads are assumed to be present on all four sides (top, bottom, left, and right).

    Parameters
    ----------
    district_type: string
    num_buildings: int
    building_density: float
    width_length_ratio: float
    building_width: float
    house_connection:float
        the distance between the building and the road

    Returns
    -------
    A_inner: float
        Converted road inner perimeter area
    """
    # external expansion per side (m)
    e = building_width + house_connection   # adjust if your geometry interprets e differently

    # target total area in m2
    A_tot = num_buildings / building_density * 10000.0

    if district_type == 'E':
        a = width_length_ratio
        b = 2.0 * e
        c = 0 - A_tot
    else:
        a = width_length_ratio
        b = 2.0 * e * (1.0 + width_length_ratio)
        c = 4.0 * e * e - A_tot

    disc = b*b - 4.0*a*c
    if disc < 0:
        raise ValueError(f"No real solution: discriminant < 0 (disc={disc}). Try relaxing parameters.")

    L_pos = (-b + sqrt(disc)) / (2.0 * a)
    L_neg = (-b - sqrt(disc)) / (2.0 * a)

    # choose positive physically meaningful root
    L = max(L_pos, L_neg)
    if L <= 0:
        raise ValueError(f"No positive solution for L (roots: {L_pos}, {L_neg}).")

    W = width_length_ratio * L
    A_inner = L * W

    return A_inner

def road_angle(road):
    """
    Return the orientation angle of a road segment in radians.
    """
    (x0, y0), (x1, y1) = road.coords[0], road.coords[-1]
    return atan2(y1 - y0, x1 - x0)

def building_rectangle(center, ground_area, aspect_ratio, angle):
    """
    Create a rectangular building footprint with fixed area.

    The rectangle length is aligned with angle. The aspect ratio is length/depth.
    """
    length = sqrt(ground_area * aspect_ratio)
    depth = sqrt(ground_area / aspect_ratio)
    rect = shapely.box(
        center.x - length / 2,
        center.y - depth / 2,
        center.x + length / 2,
        center.y + depth / 2,
    )
    return shapely.affinity.rotate(rect, angle, origin="center", use_radians=True)

def sample_irregular_road_distances(road_length, count, edge_clearance, spacing_min, spacing_max):
    """
    Generate slightly irregular positions along a road segment.

    This is used for type A so buildings form a scattered settlement.
    """
    if count <= 0:
        return []

    lower = edge_clearance
    upper = road_length - edge_clearance
    if upper <= lower:
        return [road_length / 2.0]

    base_gap = (upper - lower) / (count + 1)
    jitter = min(max(spacing_max - spacing_min, 0.0) / 2.0, base_gap * 0.35)
    distances = [
        lower + (i + 1) * base_gap + uniform(-jitter, jitter)
        for i in range(count)
    ]
    return sorted(max(lower, min(distance, upper)) for distance in distances)

def offset_line_for_side(road, offset_distance, side):
    """Return a usable road-parallel line for one road side."""
    offset_line = road.parallel_offset(offset_distance, side, resolution=16, mitre_limit=5.0)
    if offset_line.geom_type == "MultiLineString":
        offset_line = max(offset_line.geoms, key=lambda geom: geom.length)
    return offset_line

def choose_type_a_road_sides():
    """
    Choose which side(s) of a type-A road receive buildings.

    Type A represents scattered settlements, so most road segments should not
    be mirrored symmetrically on both sides.
    """
    value = uniform(0, 1)
    if value < 0.4:
        return ["left"]
    if value < 0.8:
        return ["right"]
    return ["left", "right"]

def road_side_for_point(road, point):
    """
    Return the side of the road on which a point lies.
    """
    (x0, y0), (x1, y1) = road.coords[0], road.coords[-1]
    cross_product = (x1 - x0) * (point.y - y0) - (y1 - y0) * (point.x - x0)
    return "left" if cross_product > 0 else "right"

def offset_center_for_rectangle(road, point, offset_distance):
    """
    Recompute the building center at the required distance from the road.

    The incoming point is used only to preserve its road-side and longitudinal
    position.
    """
    side = road_side_for_point(road, point)
    distance_along_road = road.project(point)
    offset_line = road.parallel_offset(offset_distance, side, resolution=16, mitre_limit=5.0)

    if offset_line.geom_type == "MultiLineString":
        offset_line = max(offset_line.geoms, key=lambda geom: geom.length)

    return offset_line.interpolate(distance_along_road)

def place_adaptive_rectangle(center, road, building_ground_area, placed_buildings,
                             road_lines_scaled, house_connection, clearance):
    """
    Place a rectangular footprint by trying several aspect ratios and orientations.

    The footprint area stays fixed. The aspect-ratio order is shuffled for each
    building so the first collision-free candidate does not always have the same
    shape.
    """
    road_clearance_margin = 0.2
    buffered_roads = [
        line.buffer(house_connection + road_clearance_margin)
        for line in road_lines_scaled
    ]
    base_angle = road_angle(road)
    aspect_ratios = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
    shuffle(aspect_ratios)
    angle_options = (base_angle, base_angle + np.pi / 2)

    for angle in angle_options:
        for aspect_ratio in aspect_ratios:
            length = sqrt(building_ground_area * aspect_ratio)
            depth = sqrt(building_ground_area / aspect_ratio)
            perpendicular_size = depth if angle == base_angle else length
            adapted_center = offset_center_for_rectangle(
                road,
                center,
                house_connection + road_clearance_margin + perpendicular_size / 2,
            )
            candidate = building_rectangle(adapted_center, building_ground_area, aspect_ratio, angle)
            if any(candidate.intersects(b.buffer(clearance)) for b in placed_buildings):
                continue
            if any(candidate.intersects(r) for r in buffered_roads):
                continue
            return candidate

    return None

def select_random_buildings(placed_buildings, num_buildings):
    """
    Keep the requested number of buildings by randomly removing excess candidates.
    """
    if len(placed_buildings) <= num_buildings:
        return placed_buildings

    num_remove = len(placed_buildings) - num_buildings
    remove_indices = set(sample(range(len(placed_buildings)), num_remove))
    return [
        building
        for index, building in enumerate(placed_buildings)
        if index not in remove_indices
    ]

def cleanup_unused_road_tails(road_lines, buildings, transformer_pos, house_connection, building_width):
    """
    Remove empty redundant roads and shorten empty dead-end road tails.

    A road is considered useful if it serves at least one building or is needed
    to connect building-serving roads.
    """
    if not road_lines:
        return road_lines

    building_access_distance = house_connection + 0.5
    road_tail_margin = house_connection + building_width / 2
    transformer_point = shapely.Point(transformer_pos)

    def endpoint_key(point):
        return round(point[0], 6), round(point[1], 6)

    def road_endpoint_keys(road):
        return endpoint_key(road.coords[0]), endpoint_key(road.coords[-1])

    def road_has_building(road):
        return any(
            building.distance(road) <= building_access_distance
            for building in buildings
        )

    def build_endpoint_graph(roads):
        graph = nx.Graph()
        for index, road in enumerate(roads):
            start_key, end_key = road_endpoint_keys(road)
            graph.add_edge(start_key, end_key, index=index)
        return graph

    def hub_node(graph):
        if graph.number_of_nodes() == 0:
            return None
        node_distances = [
            (shapely.Point(node).distance(transformer_point), node)
            for node in graph.nodes
        ]
        distance, node = min(node_distances, key=lambda item: item[0])
        if distance > 1e-4:
            return None
        return node

    def served_network_connected(roads):
        graph = build_endpoint_graph(roads)
        if graph.number_of_nodes() == 0:
            return False

        anchor = hub_node(graph)
        if anchor is None:
            return False

        served_nodes = set()
        for road in roads:
            if road_has_building(road):
                served_nodes.update(road_endpoint_keys(road))

        if not served_nodes:
            return True

        return all(
            node in graph and nx.has_path(graph, anchor, node)
            for node in served_nodes
        )

    cleaned_roads = list(road_lines)

    # First delete empty roads if building-serving roads remain connected to
    # the hub. Repeat because one deletion can make another road redundant.
    changed = True
    while changed:
        changed = False

        for index, road in enumerate(cleaned_roads):
            if road_has_building(road):
                continue

            trial_roads = cleaned_roads[:index] + cleaned_roads[index + 1:]
            if not trial_roads:
                continue

            if served_network_connected(trial_roads):
                cleaned_roads = trial_roads
                changed = True
                break

    # Then shorten empty dead-end tails behind the last served building.
    graph = build_endpoint_graph(cleaned_roads)
    shortened_roads = []

    for road_index, road in enumerate(cleaned_roads):
        start_key, end_key = road_endpoint_keys(road)
        start_degree = graph.degree[start_key]
        end_degree = graph.degree[end_key]

        if not ((start_degree == 1) ^ (end_degree == 1)):
            shortened_roads.append(road)
            continue

        nearby_buildings = [
            building for building in buildings
            if building.distance(road) <= building_access_distance
        ]
        if not nearby_buildings:
            shortened_roads.append(road)
            continue

        projections = [
            road.project(building.centroid)
            for building in nearby_buildings
        ]

        shortened_road = None
        if start_degree > 1 and end_degree == 1:
            keep_until = min(max(projections) + road_tail_margin, road.length)
            if keep_until < road.length - road_tail_margin:
                shortened_road = shapely.LineString([
                    road.coords[0],
                    road.interpolate(keep_until).coords[0],
                ])
        elif end_degree > 1 and start_degree == 1:
            keep_from = max(min(projections) - road_tail_margin, 0)
            if keep_from > road_tail_margin:
                shortened_road = shapely.LineString([
                    road.interpolate(keep_from).coords[0],
                    road.coords[-1],
                ])

        if shortened_road is None:
            shortened_roads.append(road)
            continue

        trial_roads = cleaned_roads[:road_index] + [shortened_road] + cleaned_roads[road_index + 1:]
        if served_network_connected(trial_roads):
            shortened_roads.append(shortened_road)
        else:
            shortened_roads.append(road)

    return shortened_roads

def choose_energy_hub_position(road_lines, buildings=None):
    """
    Choose the energy hub position.

    The selected road node has the highest road degree. If several nodes have
    the same degree, the node closest to the final district geometry center is
    used.
    """
    graph = nx.Graph()

    def endpoint_key(point):
        return round(point[0], 6), round(point[1], 6)

    for road in road_lines:
        start_key = endpoint_key(road.coords[0])
        end_key = endpoint_key(road.coords[-1])
        graph.add_edge(start_key, end_key)

    if graph.number_of_nodes() == 0:
        return (0, 0), 0

    degrees = dict(graph.degree())
    max_degree = max(degrees.values())
    hub_candidates = [
        node for node, degree in degrees.items()
        if degree == max_degree
    ]

    center_geometries = list(road_lines)
    if buildings:
        center_geometries.extend(buildings)

    xmin, ymin, xmax, ymax = unary_union(center_geometries).bounds
    center_x = (xmin + xmax) / 2
    center_y = (ymin + ymax) / 2

    hub_node = min(
        hub_candidates,
        key=lambda node: (
            (node[0] - center_x) ** 2 + (node[1] - center_y) ** 2,
            node[1],
            node[0],
        ),
    )

    return hub_node, max_degree

def get_edges_in_quadrant(graph, quadrant, mid_x, mid_y):
    """
    The area is divided into four sections (upper left, upper right, lower left, lower right)
    to ensure that road removal is more evenly distributed across the entire area.

    Parameters
    ----------
    graph: networkx.Graph
    quadrant: string
        'ul', 'ur', 'll', 'lr'
    mid_x: int
    mid_y: int

    Returns
    -------
    edges: list
        list of edges in certain quadrant
    """
    edges = []
    for u,v in graph.edges():
        x1, y1 = graph.nodes[u]['pos']
        x2, y2 = graph.nodes[v]['pos']
        if quadrant == 'ul' and x1 <= mid_x and y1 >= mid_y and x2 <= mid_x and y2 > mid_y:
            edges.append((u, v))
        elif quadrant == 'ur' and x1 >= mid_x and y1 >= mid_y and x2 > mid_x and y2 > mid_y:
            edges.append((u, v))
        elif quadrant == 'll' and x1 <= mid_x and y1 <= mid_y and x2 <= mid_x and y2 <= mid_y:
            edges.append((u, v))
        elif quadrant == 'lr' and x1 >= mid_x and y1 <= mid_y and x2 > mid_x and y2 <= mid_y:
            edges.append((u, v))
    return edges

def get_edges_in_rows(graph, m):
    """
    The area is divided into three sections (up, middel, down)
    to ensure that road removal is more evenly distributed across the entire area.

    Parameters
    ----------
    graph: networkx.Graph
    m: rows of the grid

    Returns
    -------
    edges_up, edges_middel, edges_down: list
        list of edges in certain section
    """
    edges_up = []
    edges_middel = []
    edges_down = []
    bound1 = max(floor(m/3), 1)
    bound2 = floor(m/3*2)
    for u,v in graph.edges():
        x1, y1 = graph.nodes[u]['pos']
        x2, y2 = graph.nodes[v]['pos']
        if y1 <= bound1 and y2 <= bound1:
            edges_down.append((u, v))
        elif y1 <= bound2 and y2 <= bound2:
            edges_middel.append((u, v))
        else:
            edges_up.append((u, v))
    return edges_up, edges_middel, edges_down

def delete_edges(graph, edges, delete_ratio):
    """
    Removing portions of the grid network serves to disrupt the artificial uniformity,
    thereby enhancing the realism and spatial variety of the simulated district.
    A delete_ratio can be specified to determine the proportion of roads to be removed from the initial grid layout.

    Parameters
    ----------
    graph: networkx.Graph
    edges: list
    delete_ratio: float

    Returns
    -------
    None
    """
    if delete_ratio > 0:
        shuffle(edges)
        target_deleted_num = int(len(edges) * delete_ratio)
        deleted_num = 0
        for e in edges:
            graph.remove_edge(*e)
            # After the removal of roads, the connectivity of the remaining road network is verified.
            # If the network becomes disconnected, the deletion is reverted.
            if not nx.is_connected(graph):
                graph.add_edge(*e)
            else:
                deleted_num += 1
            if deleted_num >= target_deleted_num:
                break

def run_typdistrict_layout(district_type, num_buildings, building_density, delete_ratio, switch_g=0):
    """
    generate the district layout

    Parameters
    ----------
    district_type: string
    num_buildings: int
    building_density: float
    delete_ratio: float
    switch_g=0
        When the number of generated buildings is not sufficient after 30 attempts,
        switch_g turns 1 and the layout of type G is fixed.

    Returns
    -------
    road_lines_scaled: list
        list of LineStrings (roads)
    buildings: list
        list of shapely Polygons (building-squares)
    transformer_pos: tuple
        coordinate of the transformer (Energy hub)
    run_results: dictionary
        includes all paraeters of the district
    get_bigger_density: bool
        True: If there are too many empty space, then get bigger density for the district and rerun the model.
    """
    # %% STEP ONE: get the parameters
    # Sample inside the GRZ range only as an initial footprint sizing guide.
    # The final generated GRZ is calculated from the generated geometry and
    # validated against the input range in postprocessing.
    initial_grz_for_geometry = uniform(
        params["grund_flaechenzahl"]["min"],
        params["grund_flaechenzahl"]["max"],
    )
    building_ground_area = initial_grz_for_geometry * 10000 / building_density  # in square meters
    building_width = sqrt(building_ground_area)  # meters
    distance_between_buildings_min = params["abstand_hausanschluesse"]["min"]  # meters
    distance_between_buildings_max = params["abstand_hausanschluesse"]["max"]  # meters
    house_connection = params["HA-Leitungen"]["value"]  # Length of house connection lines in m
    house_connection_min = params["HA-Leitungen"]["min"]
    house_connection_max = params["HA-Leitungen"]["max"]
    if district_type == "I":
        min_line_length = params["laenge_netzstrahlabschnitte"]["min"]  # meters
    else:
        min_line_length = params["laenge_netzstrahlabschnitte"]["min"] / 2  # meters

    max_line_length = params["laenge_netzstrahlabschnitte"]["max"]  # meters
    width_length_ratio = params["seitenverhaeltnis"]["value"]

    get_bigger_density = False

    # Define the area
    if district_type in ['A', 'B', 'C', 'D', 'E', 'G', 'H']:
        area_density = compute_inner_rectangle(district_type, num_buildings, building_density, width_length_ratio, building_width, house_connection)
    else:           # district F and I
        area_density = num_buildings / building_density * 10000  # square meters

    area = area_density

    length = sqrt(area / width_length_ratio)  # meters
    width = area / length  # meters

    # %% STEP TWO: generate the initial grid layout
    """
    To initiate the road layout, a grid-based graph is constructed. 
    The parameters m (number of rows), n (number of columns) and delete_ratio are determined according to the specific characteristics of each region.
    To calculate m and n, first we can calculate spacing, which means the width(x) and length(y) of a block.
    block_ratio means the ratio between the length(y) and width(x) of the block.
    The block_ratio and delete_ratio is for every district different.
    """
    if district_type == "A":
        block_ratio = 1.5
    elif district_type == "B":
        block_ratio = 2
    elif district_type == "C":
        block_ratio = 1.5
    elif district_type == "D":
        block_ratio = 1
    elif district_type == "E":
        block_ratio = 1.8
    elif district_type == "F":
        block_ratio = 1.2
    elif district_type == "G":
        block_ratio = 1
    elif district_type == "H":
        block_ratio = 1.2
    elif district_type == "I":
        block_ratio = 1.8

    if district_type in ['A', 'B']:
        max_line_length = max_line_length / 1.8

    # Randomly obtain the length(spacing_y) and width(spacing_y) of blocks for each area type.
    if district_type == 'E':
        spacing_x = (house_connection + building_width) * 2 + 20  # meters
        spacing_y = spacing_x * block_ratio  # meters
    elif district_type == 'F':
        # make sure that it can contain at least one group of three buildings in each row
        length_group = 2 * house_connection + 3 * building_width  # meters
        spacing_x_value = uniform(min_line_length / block_ratio, max_line_length / block_ratio)  # meters
        spacing_x = max(spacing_x_value, length_group)  # meters
        spacing_y = spacing_x * block_ratio  # meters
    else:
        spacing_x = uniform(min_line_length / block_ratio, max_line_length / block_ratio)  # meters
        spacing_y = spacing_x * block_ratio  # meters

    # calculate the number of rows and columns of the gird
    m_min = ceil(length / max_line_length) + 1
    m_max = max(floor(length / min_line_length) + 1, 2)
    m_value = floor(length / spacing_y) + 1
    m = np.clip(m_value, m_min, m_max)

    n_min = ceil(width / max_line_length) + 1
    n_max = max(floor(width / min_line_length) + 1, 2)
    n_value = floor(width / spacing_x) + 1
    n = np.clip(n_value, n_min, n_max)

#    if district_type == 'E':
#        n = floor(width / spacing_x) + 1

    # adjust the layout and randomly delete the roads
    if switch_g == 1 and district_type == 'G':
        # When the number of generated buildings is not sufficient after 30 attempts,
        # switch_g turns 1 and the layout of type G is fixed.
        road_grid = nx.grid_2d_graph(m, n, periodic=False, create_using=None)
        pos = {node: (node[1], node[0]) for node in road_grid.nodes()}
        nx.set_node_attributes(road_grid, pos, "pos")
    else:
        road_grid = nx.grid_2d_graph(m, n, periodic=False, create_using=None)

        # Add diagonal roads in district types G and I.
        # Some cells receive two diagonals, some receive one diagonal, and
        # type I can also have cells without diagonals. This keeps the road
        # morphology irregular.
        if district_type in ("G", "I"):
            for i in range(m-1):
                for j in range(n-1):
                    diagonal_a = ((i, j), (i + 1, j + 1))
                    diagonal_b = ((i, j + 1), (i + 1, j))
                    random_value = uniform(0, 1)

                    if district_type == "G":
                        if random_value < 0.70:
                            road_grid.add_edge(*diagonal_a)
                            road_grid.add_edge(*diagonal_b)
                        elif uniform(0, 1) < 0.50:
                            road_grid.add_edge(*diagonal_a)
                        else:
                            road_grid.add_edge(*diagonal_b)
                    else:
                        if random_value < 0.20:
                            road_grid.add_edge(*diagonal_a)
                            road_grid.add_edge(*diagonal_b)
                        elif random_value < 0.90:
                            if uniform(0, 1) < 0.50:
                                road_grid.add_edge(*diagonal_a)
                            else:
                                road_grid.add_edge(*diagonal_b)

        pos = {node: (node[1], node[0]) for node in road_grid.nodes()}
        nx.set_node_attributes(road_grid, pos, "pos")

        # delete in roads in different sections with a delete_ratio
        if m == 2 and n == 2:
            edges = list(road_grid.edges())
            delete_edges(road_grid, edges, delete_ratio)
        elif n == 2 or m == 4:
            edges_up, edges_middel, edges_down = get_edges_in_rows(road_grid, m)
            delete_edges(road_grid, edges_up, delete_ratio)
            delete_edges(road_grid, edges_middel, delete_ratio)
            delete_edges(road_grid, edges_down, delete_ratio)
        else:
            for quadrant in ['ul', 'ur', 'll', 'lr']:
                edges = get_edges_in_quadrant(road_grid, quadrant, (n-1)//2, (m-1)//2)
                delete_edges(road_grid, edges, delete_ratio)

    # Select the energy hub location.
    # First, choose nodes with the maximum graph degree, i.e. the most connected intersections.
    # If several nodes have the same maximum degree, choose the one closest to the district center.
    degrees = dict(road_grid.degree())
    max_degree = max(degrees.values())

    hub_candidates = [node for node, degree in degrees.items() if degree == max_degree]

    district_center_x = width / 2
    district_center_y = length / 2

    def node_to_position(node):
        """
        Convert a graph node index to the corresponding physical district coordinates.
        NetworkX grid nodes are stored as (row, column).
        """
        row, column = node
        x = column * width / (n - 1)
        y = row * length / (m - 1)
        return x, y

    def hub_selection_key(node):
        """
        Deterministic tie-break:
        1. shortest distance to district center
        2. row index
        3. column index
        """
        x, y = node_to_position(node)
        distance_to_center_squared = (
                (x - district_center_x) ** 2 +
                (y - district_center_y) ** 2
        )
        row, column = node
        return distance_to_center_squared, row, column

    hub_node = min(hub_candidates, key=hub_selection_key)
    transformer_pos = node_to_position(hub_node)

    # %% STEP THREE: Scale the roads to meet the required width-to-length ratio and area
    # Convert edges in Networkx to LineStrings, which can be used in shapely
    road_lines = []
    for u, v in road_grid.edges:
        point_u = road_grid.nodes[u]['pos']
        point_v = road_grid.nodes[v]['pos']
        road_lines.append(shapely.LineString([point_u, point_v]))

    # scale the road layout
    road_lines_scaled = [scale(line, xfact=width/(n-1), yfact=length/(m-1), origin=(0, 0)) for line in road_lines]

    # seperate the roads into vertical, horizontal and diagonal roads
    vertical_road = []
    horizontal_road = []
    diagonal_road = []
    for road in road_lines_scaled:
        if road.coords[0][1] == road.coords[1][1]:
            horizontal_road.append(road)
            block_width = abs(road.coords[0][0] - road.coords[1][0])
        elif road.coords[0][0] == road.coords[1][0]:
            vertical_road.append(road)
            block_length = abs(road.coords[0][1] - road.coords[1][1])
        else:
            diagonal_road.append(road)
            block_width = abs(road.coords[0][0] - road.coords[1][0])
            block_length = abs(road.coords[0][1] - road.coords[1][1])
    # calculate the total length of all vertical / horizontal / diagonal roads (prepare for placing the buildings)
    length_vertical_road = len(vertical_road) * block_length
    length_horizontal_road = len(horizontal_road) * block_width
    length_road = length_vertical_road + length_horizontal_road

    # %% STEP FOUR: Place the buildings along the roads using Shapely (check overlaps)
    placed_buildings = []
    if district_type in ['A', 'B', 'C', 'D', 'H']:
        """
        Generate parallel lines to the roads, 
        sample evenly spaced points along these lines to place buildings, 
        and check for overlaps with existing buildings or roads.
        """
        # Distribute the number of buildings to horizontal and vertical roads according to their lengths
        num_bl_ver_road = ceil(num_buildings * length_vertical_road/length_road)
        num_bl_hor_road = num_buildings - num_bl_ver_road

        # calculate the minimum distance between the centers of two adjacent buildings
        distance_between_bl = max(building_width, distance_between_buildings_min)

        # calculate the number of buildings along each vertical road
        num_bl_per_ver_road_value = ceil(num_bl_ver_road/len(vertical_road))
        num_bl_per_ver_road_max = floor((block_length - 2 * house_connection - building_width + distance_between_bl)/distance_between_bl * 2)
        num_bl_per_ver_road = min(num_bl_per_ver_road_max, num_bl_per_ver_road_value)

        num_ver_point = ceil(num_bl_per_ver_road / 2)   # the number of buildings on each side
        for road in vertical_road:
            road_sides = choose_type_a_road_sides() if district_type == "A" else ["left", "right"]
            for side in road_sides:
                if district_type == "A":
                    points_this_side = num_bl_per_ver_road if len(road_sides) == 1 else num_ver_point
                    distances = sample_irregular_road_distances(
                        block_length,
                        points_this_side,
                        house_connection_max + building_width / 2,
                        distance_between_buildings_min,
                        distance_between_buildings_max
                    )
                elif num_bl_per_ver_road == num_bl_per_ver_road_value:
                    # Buildings can be spaced equidistantly along the road.
                    distance_value = block_length / (num_ver_point + 1)
                    distance_max = max(building_width, distance_between_buildings_max)
                    # The distance between buildings cannot exceed the maximum value.
                    distance = min(distance_value, distance_max)

                    # If there are too many empty space, then get bigger density for the district and rerun the model.
                    ratio = distance_value / distance_max
                    if ratio > 1.2 and get_bigger_density == False:
                        get_bigger_density = True

                    # Get a list of the distances from the center of all buildings to the start of the road.
                    distances = [(i+1)*distance for i in range(num_ver_point)]
                else:
                    # Building spacing is the minimum spacing
                    distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in range(num_ver_point)]
                # Get the coordinates of all building center points
                for distance in distances:
                    if district_type == "A":
                        local_house_connection = uniform(house_connection_min, house_connection_max)
                    else:
                        local_house_connection = house_connection
                    road_parallel = offset_line_for_side(
                        road,
                        local_house_connection + building_width / 2,
                        side
                    )
                    p = road_parallel.interpolate(distance)
                    # Draw the building square
                    new_building = shapely.box(p.x - building_width / 2, p.y - building_width / 2,
                                               p.x + building_width / 2, p.y + building_width / 2)
                    buffered_roads = [line.buffer(local_house_connection - 0.1) for line in road_lines_scaled]
                    # Detect whether the building overlaps with existing roads and buildings
                    if not any(new_building.intersects(b.buffer(distance_between_bl-building_width)) for b in placed_buildings):
                        if not any(new_building.intersects(r) for r in buffered_roads):
                            placed_buildings.append(new_building)

        # same for the horizontal roads
        num_bl_per_hor_road_value = ceil(num_bl_hor_road / len(horizontal_road))
        num_bl_per_hor_road_max = floor(
            (block_width - 2 * house_connection - building_width + distance_between_bl) / distance_between_bl * 2)
        num_bl_per_hor_road = min(num_bl_per_hor_road_max, num_bl_per_hor_road_value)

        num_hor_point = ceil(num_bl_per_hor_road / 2)
        for road in horizontal_road:
            road_sides = choose_type_a_road_sides() if district_type == "A" else ["left", "right"]
            for side in road_sides:
                if district_type == "A":
                    points_this_side = num_bl_per_hor_road if len(road_sides) == 1 else num_hor_point
                    distances = sample_irregular_road_distances(
                        block_width,
                        points_this_side,
                        house_connection_max + building_width / 2,
                        distance_between_buildings_min,
                        distance_between_buildings_max
                    )
                elif num_bl_per_hor_road == num_bl_per_hor_road_value:
                    distance_value = block_length / (num_hor_point + 1)
                    distance_max = max(building_width, distance_between_buildings_max)
                    distance = min(distance_value, distance_max)

                    ratio = distance_value / distance_max
                    if ratio > 1.2 and get_bigger_density == False:
                        get_bigger_density = True

                    distances = [(i + 1) * distance for i in range(num_hor_point)]
                else:
                    distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in
                                 range(num_hor_point)]
                for distance in distances:
                    if district_type == "A":
                        local_house_connection = uniform(house_connection_min, house_connection_max)
                    else:
                        local_house_connection = house_connection
                    road_parallel = offset_line_for_side(
                        road,
                        local_house_connection + building_width / 2,
                        side
                    )
                    p = road_parallel.interpolate(distance)
                    new_building = shapely.box(p.x - building_width / 2, p.y - building_width / 2,
                                               p.x + building_width / 2, p.y + building_width / 2)
                    buffered_roads = [line.buffer(local_house_connection - 0.1) for line in road_lines_scaled]
                    if not any(new_building.intersects(b.buffer(distance_between_bl-building_width)) for b in placed_buildings):
                        if not any(new_building.intersects(r) for r in buffered_roads):
                            placed_buildings.append(new_building)

        buildings = select_random_buildings(placed_buildings, num_buildings)

    elif district_type == "E":
        """
        In the Reihenhausbebauung (row housing) type, the vertical roads serve as the main streets, and buildings are only placed along their sides. 
        The total number of buildings in the district is divided by the number of vertical roads to determine how many buildings should be placed along each road.
        This number is then checked against the maximum possible number of buildings that can be accommodated on each road. 

        In the Reihenhausbebauung (row housing) type, buildings are grouped in sets of 4 to 8, without any gap between all buildings in each group. 
        The distance between two groups is generally between 5 and 20 metres.
        After placement, overlap checks are performed to ensure feasibility.
        """
        # Calculate the number of buildings on each side of each vertical road
        num_bl_per_road_side_value = ceil(num_buildings / len(vertical_road) / 2)
        num_bl_per_road_side_max = floor((block_length - 2 * house_connection)/building_width)
        num_bl_per_road_side = min(num_bl_per_road_side_value, num_bl_per_road_side_max)

        # The distance range between each group (Measurements summarized from actual areas in googlemap)
        distance_group_min = 5  # meters
        distance_group_max = 20  # meters

        # randomly choose the number of buildings in a group and calculate the number of groups per vertical raod
        num_bl_per_group = min(choice(range(4, 9)), num_bl_per_road_side_value)
        num_group_per_rd = ceil(num_bl_per_road_side / num_bl_per_group)

        # calculate the distance between each group
        if num_group_per_rd > 1:
            distance_group = (block_length - num_bl_per_road_side*(building_width+0.1) - 2*house_connection)/(num_group_per_rd-1)  # meters
        else:
            distance_group = block_length - num_bl_per_road_side * (building_width+0.1) - house_connection  # meters
        # If two groups are too close together, increase the number of buildings in a group.
        while distance_group < distance_group_min:
            num_bl_per_group += 1
            num_group_per_rd = ceil(num_bl_per_road_side / num_bl_per_group)
            if num_group_per_rd > 1:
                distance_group = (block_length - num_bl_per_road_side * (building_width+0.1) - 2 * house_connection) / (
                        num_group_per_rd - 1)  # meters
            else:
                distance_group = block_length - num_bl_per_road_side * (building_width+0.1) - house_connection  # meters
        # If two groups are too far apart, reduce the number of buildings in a group.
        while distance_group > distance_group_max:
            num_bl_per_group -= 1
            num_group_per_rd = ceil(num_bl_per_road_side / num_bl_per_group)
            if num_group_per_rd > 1:
                distance_group = (block_length - num_bl_per_road_side * (building_width+0.1) - 2 * house_connection) / (
                        num_group_per_rd - 1)  # meters
            else:
                distance_group = block_length - num_bl_per_road_side * (building_width+0.1) - house_connection  # meters
            if num_bl_per_group <= 4 and distance_group > distance_group_max:
                # If the number of buildings in a group is already small,
                # but the distance between two groups is still far, increase the building density and re-run the model.
                get_bigger_density = True
                break

        # Try to avoid having only one building in a group.
        # If this happens, add it to the end of the previous group.
        add_one_building = False
        if num_bl_per_road_side % num_bl_per_group == 1:
            num_group_per_rd -= 1
            add_one_building = True
            if num_group_per_rd > 1:
                distance_group = (block_length - num_bl_per_road_side * (building_width+0.1) - 2 * house_connection) / (
                        num_group_per_rd - 1)  # meters
            else:
                distance_group = block_length - num_bl_per_road_side * (building_width+0.1) - house_connection  # meters
            if distance_group > distance_group_max:
                get_bigger_density = True

        # calculate the width of a group (to determine the center point of each building more conveniently)
        group_width = num_bl_per_group * (building_width+0.1)

        for road in vertical_road:
            for side in ['left', 'right']:
                building_this_road = []
                # get the parallel line (The center point of the building is on this line)
                road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16, mitre_limit=5.0)
                for j in range(num_group_per_rd):
                    num_points = num_bl_per_group
                    if j == num_group_per_rd-1 and add_one_building:
                        # If there is only one building in the last group,
                        # then merge that building into the penultimate group.
                        num_points += 1
                    # Get a list of the distances from the center of all buildings to the start of the road.
                    distances = [house_connection + (group_width + distance_group) * j + building_width / 2 + (
                            building_width + 0.1) * k for k in range(num_points)]
                    # Get the coordinates of all building center points
                    points = [road_parallel.interpolate(d) for d in distances]
                    for p in points:
                        # Try adaptive rectangular footprints with fixed area.
                        new_building = place_adaptive_rectangle(
                            p, road, building_ground_area, placed_buildings,
                            road_lines_scaled, house_connection, 0.0)
                        if new_building is not None:
                            placed_buildings.append(new_building)
                            building_this_road.append(new_building)
                        if len(building_this_road) == num_bl_per_road_side:
                            break

        # If the number of generated buildings exceeds the target, randomly remove extras.
        buildings = select_random_buildings(placed_buildings, num_buildings)

    elif district_type == "F":
        """
        In the Zeilenbebauung (row development) type, several buildings are placed seamlessly to form a row, positioned perpendicularly between two vertical main roads. 
        First, the average number of buildings to be placed in each block is calculated. 
        Then, the maximum number of buildings that can fit in a single row along the horizontal direction is determined. 
        Based on this, the number of rows that can be accommodated in each block is computed. 
        The block length is then evenly divided according to the number of rows, and a random number of buildings is placed in each row. 
        After placement, overlap checks are performed to ensure validity.
        """
        # set the number of buildings per group
        num_bl_per_group = 3
        group_width = num_bl_per_group * building_width  # meters

        # The distance range between each group (Measurements summarized from actual areas in googlemap)
        distance_group_hor_min = 15  # meters
        distance_group_ver_min = 30  # meters

        # divide the number of buildings evenly to each block
        num_bl_per_block = ceil(num_buildings/((m-1)*(n-1)))
        num_group_per_block = ceil(num_bl_per_block / num_bl_per_group)
        # calculate the maximum number of groups per block vertically and horizontally
        num_group_per_col_max = min(floor((block_length - 2*house_connection + distance_group_ver_min)/
                                          (building_width + distance_group_ver_min)), num_group_per_block)
        num_group_per_row_max = min(floor((block_width - 2*house_connection + distance_group_hor_min)/
                                          (group_width + distance_group_hor_min)), num_group_per_block)

        # determine the distance between each group vertically
        distance_group_ver = max(2.5*building_width, distance_group_ver_min)
        # calculate the number of groups vertically
        num_group_per_col_value = floor((block_length - 2 * house_connection + distance_group_ver) /
                                        (building_width + distance_group_ver))
        num_group_per_col = np.clip(num_group_per_col_value, 1, num_group_per_col_max)
        # calculate the vertical distance between buildings and horizontal roads
        distance_bl_rd_ver = (block_length - num_group_per_col * building_width -(num_group_per_col - 1) * distance_group_ver) / 2
        # If buildings are too far from the road, increase building density and rerun the model.
        if distance_bl_rd_ver > 30 and get_bigger_density == False:
            get_bigger_density = True

        # # calculate the number of groups horizontally
        num_group_per_row_value = ceil(num_group_per_block/num_group_per_col)
        num_group_per_row = np.clip(num_group_per_row_value, 1, num_group_per_row_max)
        # calculate the horizontal distance between two groups
        # If two groups are too far from each other, increase building density and rerun the model.
        if num_group_per_row > 1:
            distance_group_hor = (block_width - num_group_per_row * group_width - 2*house_connection)/(num_group_per_row - 1) - 1
            if distance_group_hor > 30 and get_bigger_density == False:
                get_bigger_density = True
        else:
            distance_group_hor = block_width - group_width - house_connection
            if distance_group_hor > house_connection + 10 and get_bigger_density == False:
                get_bigger_density = True

        # Get all horizontal roads with y not equal to 0
        roads = []
        for road in horizontal_road:
            if road.coords[0][1] != 0:
                roads.append(road)

        # start to place the groups
        for i in range(num_group_per_col):  # for each row in the blocks
            if len(placed_buildings) >= num_buildings:
                break
            for road in roads:
                if len(placed_buildings) >= num_buildings:
                    break
                # get the parallel line (The center point of the building is on this line)
                road_parallel = road.parallel_offset(distance_bl_rd_ver + building_width/2 + (building_width + distance_group_ver)*i,
                                                     "right", resolution=16, mitre_limit=5.0)
                for j in range(num_group_per_row):
                    # Get a list of the distances from the center of all buildings to the start of the road.
                    distances = [house_connection + (group_width + distance_group_hor)*j + building_width/2 + (building_width+0.1)*k for k in range(num_bl_per_group)]
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

        # If the number of buildings generated exceeds the required number, retain only the quantity requested
        buildings = placed_buildings[:num_buildings]

    elif district_type == "G":
        # calculate the minimum distance between the centers of two adjacent buildings
        distance_between_bl = max(building_width, distance_between_buildings_min)

        # calculate the maximum number of buildings along each vertical, horizontal and diagonal road
        num_bl_per_ver_road_max = floor((block_length - 2 * house_connection - building_width + distance_between_bl) / distance_between_bl * 2)
        num_bl_per_hor_road_max = floor((block_width - 2 * house_connection - building_width + distance_between_bl) / distance_between_bl * 2)
        dia_length = sqrt(block_length * block_length + block_width * block_width)
        num_bl_per_dia_road_max = floor((dia_length - 2 * house_connection - building_width + distance_between_bl) / distance_between_bl * 2)

        # calculate the total length of all roads
        length_road += len(diagonal_road) * dia_length
        # Distribute the number of buildings to horizontal, vertical and diagonal roads according to their lengths
        num_bl_per_ver_road_value = ceil(num_buildings * length_vertical_road / length_road)
        num_bl_per_hor_road_value = ceil(num_buildings * length_horizontal_road / length_road)
        num_bl_per_dia_road_value = num_buildings - num_bl_per_ver_road_value - num_bl_per_hor_road_value
        # determine the number of buildings along each road
        num_bl_per_ver_road = min(num_bl_per_ver_road_max, num_bl_per_ver_road_value)
        num_bl_per_hor_road = min(num_bl_per_hor_road_max, num_bl_per_hor_road_value)
        num_bl_per_dia_road = min(num_bl_per_dia_road_max, num_bl_per_dia_road_value)

        # place the buildings first along all diagonal roads
        num_dia_point = ceil(num_bl_per_dia_road / 2)
        for road in diagonal_road:
            for side in ['left', 'right']:
                # get the parallel line (The center point of the building is on this line)
                road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16, mitre_limit=5.0)

                # Calculation of diagonal road inclination
                dx = road.coords[1][0] - road.coords[0][0]
                dy = road.coords[1][1] - road.coords[0][1]
                angle_road = atan2(dy, dx)

                if num_bl_per_dia_road == num_bl_per_dia_road_value:
                    # Buildings can be spaced equidistantly along the road.
                    distance_value = block_length / (num_dia_point + 1)
                    distance_max = max(building_width, distance_between_buildings_max)
                    # The distance between buildings cannot exceed the maximum value.
                    distance = min(distance_value, distance_max)

                    # If there are too many empty space, then get bigger density for the district and rerun the model.
                    ratio = distance_value / distance_max
                    if ratio > 1.2 and get_bigger_density == False:
                        get_bigger_density = True

                    # Get a list of the distances from the center of all buildings to the start of the road.
                    distances = [(i+1)*distance for i in range(num_dia_point)]
                else:
                    # Building spacing is the minimum spacing
                    distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in range(num_dia_point)]
                # Get the coordinates of all building center points
                points = [road_parallel.interpolate(d) for d in distances]
                for p in points:
                    # Draw the building square
                    new_building = shapely.box(p.x - building_width / 2, p.y - building_width / 2,
                                               p.x + building_width / 2, p.y + building_width / 2)
                    # rotate the buildings for diagonal roads
                    new_building_rotated = shapely.affinity.rotate(new_building, angle_road, origin='center',
                                                                   use_radians=True)
                    buffered_roads = [line.buffer(house_connection - 0.1) for line in road_lines_scaled]
                    # Detect whether the building overlaps with existing roads and buildings
                    if not any(new_building_rotated.intersects(b.buffer(distance_between_bl - building_width)) for b in placed_buildings):
                        if not any(new_building_rotated.intersects(r) for r in buffered_roads):
                            placed_buildings.append(new_building_rotated)

        # same for the vertical roads
        num_ver_point = ceil(num_bl_per_ver_road / 2)
        for road in vertical_road:
            for side in ['left', 'right']:
                # get the parallel line (The center point of the building is on this line)
                road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16, mitre_limit=5.0)
                if num_bl_per_ver_road == num_bl_per_ver_road_value:
                    distance_value = block_length / (num_ver_point + 1)
                    distance_max = max(building_width, distance_between_buildings_max)
                    distance = min(distance_value, distance_max)

                    ratio = distance_value / distance_max
                    if ratio > 1.2 and get_bigger_density == False:
                        get_bigger_density = True

                    distances = [(i + 1) * distance for i in range(num_ver_point)]
                else:
                    distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in
                                 range(num_ver_point)]
                points = [road_parallel.interpolate(d) for d in distances]
                for p in points:
                    new_building = shapely.box(p.x - building_width / 2, p.y - building_width / 2,
                                               p.x + building_width / 2, p.y + building_width / 2)
                    buffered_roads = [line.buffer(house_connection - 0.1) for line in road_lines_scaled]
                    if not any(new_building.intersects(b.buffer(distance_between_bl - building_width)) for b in placed_buildings):
                        if not any(new_building.intersects(r) for r in buffered_roads):
                            placed_buildings.append(new_building)

        # same for the horizontal roads
        num_hor_point = ceil(num_bl_per_hor_road / 2)
        for road in horizontal_road:
            for side in ['left', 'right']:
                # get the parallel line (The center point of the building is on this line)
                road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16,
                                                     mitre_limit=5.0)
                if num_bl_per_hor_road == num_bl_per_hor_road_value:
                    distance_value = block_length / (num_hor_point + 1)
                    distance_max = max(building_width, distance_between_buildings_max)
                    distance = min(distance_value, distance_max)

                    ratio = distance_value / distance_max
                    if ratio > 1.2 and get_bigger_density == False:
                        get_bigger_density = True

                    distances = [(i + 1) * distance for i in range(num_hor_point)]
                else:
                    distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in
                                 range(num_hor_point)]
                points = [road_parallel.interpolate(d) for d in distances]
                for p in points:
                    new_building = shapely.box(p.x - building_width / 2, p.y - building_width / 2,
                                               p.x + building_width / 2, p.y + building_width / 2)
                    buffered_roads = [line.buffer(house_connection - 0.1) for line in road_lines_scaled]
                    if not any(new_building.intersects(b.buffer(distance_between_bl - building_width)) for b in
                               placed_buildings):
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

    elif district_type == "I":
        # calculate the minimum distance between the centers of two adjacent buildings
        distance_between_bl = max(building_width, distance_between_buildings_min)

        # calculate the maximum number of buildings along each vertical, horizontal and diagonal road
        num_bl_per_ver_road_max = floor((block_length - 2 * house_connection - building_width + distance_between_bl) / distance_between_bl * 2)
        num_bl_per_hor_road_max = floor(
            (block_width - 2 * house_connection - building_width + distance_between_bl) / distance_between_bl * 2)
        dia_length = sqrt(block_length*block_length + block_width*block_width)
        num_bl_per_dia_road_max = floor((dia_length - 2 * house_connection - building_width + distance_between_bl) / distance_between_bl * 2)
        # num_bl_max = num_bl_per_ver_road_max*len(vertical_road) + num_bl_per_hor_road_max*len(horizontal_road) + num_bl_per_dia_road_max * len(diagonal_road)

        # Since, according to generation experience, region I often fails to generate a sufficient number of buildings,
        # and since, according to daily experience, buildings are often built next to each other in this type of region,
        # the building spacing is taken as a direct minimum here.

        for road in diagonal_road:
            for side in ['left', 'right']:
                # get the parallel line (The center point of the building is on this line)
                road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16, mitre_limit=5.0)

                # Calculation of diagonal road inclination
                dx = road.coords[1][0] - road.coords[0][0]
                dy = road.coords[1][1] - road.coords[0][1]
                angle_road = atan2(dy, dx)

                # Get a list of the distances from the center of all buildings to the start of the road.
                distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in range(num_bl_per_dia_road_max//2)]
                # Get the coordinates of all building center points
                points = [road_parallel.interpolate(d) for d in distances]
                for p in points:
                    # Try adaptive rectangular footprints with fixed area.
                    clearance = max(0.0, distance_between_bl - building_width)
                    new_building = place_adaptive_rectangle(
                        p, road, building_ground_area, placed_buildings,
                        road_lines_scaled, house_connection, clearance)
                    if new_building is not None:
                        placed_buildings.append(new_building)

        # same for the vertical roads
        for road in vertical_road:
            for side in ['left', 'right']:
                road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16, mitre_limit=5.0)
                distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in range(num_bl_per_ver_road_max//2)]
                points = [road_parallel.interpolate(d) for d in distances]
                for p in points:
                    clearance = max(0.0, distance_between_bl - building_width)
                    new_building = place_adaptive_rectangle(
                        p, road, building_ground_area, placed_buildings,
                        road_lines_scaled, house_connection, clearance)
                    if new_building is not None:
                        placed_buildings.append(new_building)

        # same for the horizontal roads
        for road in horizontal_road:
            for side in ['left', 'right']:
                road_parallel = road.parallel_offset(house_connection + building_width / 2, side, resolution=16, mitre_limit=5.0)
                distances = [house_connection + 0.5 * building_width + i * (distance_between_bl + 0.1) for i in range(num_bl_per_hor_road_max//2)]
                points = [road_parallel.interpolate(d) for d in distances]
                for p in points:
                    clearance = max(0.0, distance_between_bl - building_width)
                    new_building = place_adaptive_rectangle(
                        p, road, building_ground_area, placed_buildings,
                        road_lines_scaled, house_connection, clearance)
                    if new_building is not None:
                        placed_buildings.append(new_building)

        buildings = select_random_buildings(placed_buildings, num_buildings)

    # %% STEP FIVE: Save the parameters for this run
    # calculate the actual total area and building density
    if district_type != "F":
        cleanup_house_connection = (
            house_connection_max
            if district_type == "A"
            else house_connection
        )
        road_lines_scaled = cleanup_unused_road_tails(
            road_lines=road_lines_scaled,
            buildings=buildings,
            transformer_pos=transformer_pos,
            house_connection=cleanup_house_connection,
            building_width=building_width,
        )

    transformer_pos, max_degree = choose_energy_hub_position(
        road_lines_scaled,
        buildings=buildings,
    )

    # Combine buildings and roads into a single graph
    all_geoms = list(buildings) + list(road_lines_scaled)

    # Get rectangle boundaries
    all_union = unary_union(all_geoms)

    # Get xmin, ymin, xmax, ymax for the rectangle boundaries
    xmin, ymin, xmax, ymax = all_union.bounds

    # calculate parameters
    area_space = (xmax - xmin) * (ymax - ymin) / 10000  # ha
    area_width = xmax - xmin  # meters
    area_length = ymax - ymin  # meters
    area_building_density = num_buildings / area_space  #number of buildings per ha
    total_building_footprint_area = sum(building.area for building in buildings)
    generated_grz = total_building_footprint_area / (area_space * 10000) if area_space > 0 else 0

    run_results = {
        "district_type": district_type,
        "num_buildings": num_buildings,
        "width": area_width,
        "length": area_length,
        "width_length_ratio": area_width / area_length,
        "area": area_space,
        "building_density": area_building_density,
        "generated_grz": generated_grz,
        "target_grz_min": params["grund_flaechenzahl"]["min"],
        "target_grz_max": params["grund_flaechenzahl"]["max"],
        "initial_grz_for_geometry": initial_grz_for_geometry,
        "target_gfz_min": params["geschoss_flaechenzahl"]["min"],
        "target_gfz_max": params["geschoss_flaechenzahl"]["max"],
        "building_ground_area": building_ground_area,
        "building_width": building_width,
        "house_connection": house_connection,
        "energy_hub_road_degree": max_degree,
        "num_roads": len(road_lines_scaled),
        "num_row_roads": m,
        "num_column_roads": n
    }

    return road_lines_scaled, buildings, transformer_pos, run_results, get_bigger_density
