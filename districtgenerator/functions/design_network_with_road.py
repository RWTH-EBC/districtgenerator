import copy

import networkx as nx
from networkx.algorithms.approximation import steiner_tree
import gurobipy as gp
import matplotlib.pyplot as plt
import matplotlib.patches as patches

import os
import datetime
import numpy as np
import math
import json
from collections import defaultdict, deque

# check whether point is in the points_list
def point_in_list(point, points_list, tol=1e-6):
    """
    check if point is in points_list
    if not, add it to points_list

    Parameters
    ----------
    point: tuple
        coordinates of point
    points_list: list
        list of coordinates
    tol: float, optional
        tolerance

    Returns
    -------
    bool
        True: if point is in points_list
    """
    return any(np.allclose(point, p, atol=tol) for p in points_list)

def closest_point_on_segment(P, A, B):
    """
    Find a point on the line AB, which is closest to point P.

    Parameters
    ----------
    P: tuple
        coordinate of the point
    A: tuple
        coordinate of the start point of the line AB
    B: tuple
        coordinate of the end point of the line AB

    Returns
    -------
    tuple(closest)
        coordinates of the closest point of P on the line AB
    """
    A = np.array(A)
    B = np.array(B)
    P = np.array(P)
    AB = B - A
    if np.allclose(AB, 0):
        return A  # 道路起止点重合
    t = np.dot(P - A, AB) / np.dot(AB, AB)
    t = np.clip(t, 0, 1)
    closest = A + t * AB
    return tuple(closest)

def euclidean(p1, p2):
    """
    To calculate the Euclidean distance between two points p1 and p2.

    Parameters
    ----------
    p1: tuple
        coordinate of the point p1
    p2: tuple
        coordinate of the point p2

    Returns
    -------
    the Euclidean distance between two points p1 and p2: float
    """
    return math.hypot(p1[0]-p2[0], p1[1]-p2[1])

def merge_close_point(pt, existing_points, tol=0.1):
    """
    If pt is within tol distance of any point in existing_points, return that existing point;
    otherwise, return pt itself.

    Parameters
    ----------
    pt: tuple
        coordinate of the point pt
    existing_points: list
        list of coordinates of all existing points
    tol: float, optional
        tolerance

    Returns
    -------
    ep: tuple
        coordinate of the point existing point (if pt in existing_points)
    pt: tuple
        coordinate of the point pt (if pt not in existing_points)
    """
    for ep in existing_points:
        if np.linalg.norm(np.array(pt) - np.array(ep)) < tol:
            return ep  # Replace with existing point
    return pt

def is_on_line(p, a, b, tol=1e-6):
    """
    check if p is on the line between a and b

    Parameters
    ----------
    p: tuple
        coordinate of p
    a: tuple
        coordinate of line start point a
    b: tuple
        coordinate of line end point b
    tol: float, optional
        tolerance

    Returns
    -------
    bool
        True: p is on the line between a and b
        False: p is not on the line between a and b
    """
    cross = (p[1]-a[1])*(b[0]-a[0]) - (p[0]-a[0])*(b[1]-a[1])
    if abs(cross) > tol:
        return False
    dot = (p[0]-a[0])*(b[0]-a[0]) + (p[1]-a[1])*(b[1]-a[1])
    if dot < 0:
        return False
    sq_len = (b[0]-a[0])**2 + (b[1]-a[1])**2
    if dot > sq_len:
        return False
    return True

def project_on_line(p, a, b):
    """
    Calculate the distance between a point on a line segment and the starting point of the line segment.

    Parameters
    ----------
    p: tuple
        coordinate of p
    a: tuple
        coordinate of line start point a
    b: tuple
        coordinate of line end point b

    Returns
    -------
    float
        the distance between a point on a line segment and the starting point of the line segment
    """
    dx, dy = b[0]-a[0], b[1]-a[1]
    if dx == 0 and dy == 0:
        return 0
    return ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / (dx*dx + dy*dy)

def get_unique_filename(base_path):
    if not os.path.exists(base_path):
        return base_path
    base, ext = os.path.splitext(base_path)
    counter = 1
    while True:
        new_path = f"{base}({counter}){ext}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1

def orient_network(G, plant):
    """
    Orient an undirected graph starting from a plant node
    It cannot be used if a ring structure exist in the network.

    Parameters
    ----------
    G : networkx.Graph
        Undirected graph
    plant : int
        index of the plant node (normally 0 for the energy hub)

    Returns
    -------
    directed_dict : dict
        Adjacency dictionary with directed edges (parent → child)
    """
    # Pre-create an empty child list for each node
    # Keys are node IDs, values are lists of child node IDs (empty if no children)
    directed_dict = {G.nodes[n]["id"]: [] for n in G.nodes()}

    # Record visited nodes to avoid revisiting them
    # Ensures each node is only captured once as a child (avoids cycles)
    visited = set()

    # Initialize the BFS queue starting from the plant node
    queue = deque([plant])
    visited.add(plant)

    # Perform BFS traversal
    while queue:
        current = queue.popleft()  # Get the first element in the queue (FIFO)
        current_id = G.nodes[current]["id"]  # Current node ID

        # Iterate through all neighbors of the current node (undirected edges)
        for neighbor in G.neighbors(current):
            neighbor_id = G.nodes[neighbor]["id"]  # Neighbor node ID
            if neighbor not in visited:
                # Direct the edge from current → neighbor
                directed_dict[current_id].append(neighbor_id)
                # Mark neighbor as visited
                visited.add(neighbor)
                # Add neighbor to the queue for further traversal
                queue.append(neighbor)
    return directed_dict

def run_pipeline_road(district_type, building_width, house_connection, buildings_info, lines_info, transformer_info):
    """
    Consider road constraints, ensuring all main pipelines are laid beneath roads.
    using Steiner Tree algorithm

    Parameters
    ----------
    district_type: string
    building_width: float
    house_connection: float
    buildings_info: list
        list of building informations, each building is a dictionary with following keys:
            "id", "type", "position", "calculated_building_area",
            "number_of_floors", "construction_year", "retrofit_level"
    lines_info: list
        list of lines informations, each line is a dictionary with following keys:
            "id", "start"(tuple, coordinate of the start point),
            "end"(tuple, coordinate of the end point), "length"(float)
    transformer_info: dictionary
        only one key: "position"

    Returns
    -------
    None
    """
    if district_type != "F":
        # Due to the unique nature of Type F, pipeline network layouts will be planned separately.

        # %% STEP ONE: get all the nodes in the graph
        # first get the connection points for all buildings
        connection_points = []

        for building in buildings_info:
            closest_points = []
            distances = []
            for line in lines_info:
                pt = closest_point_on_segment(building["position"], line["start"], line["end"])
                closest_points.append(pt)
                distances.append(np.linalg.norm(np.array(building["position"]) - pt))
            # Select the point with the shortest distance as the connection point
            min_idx = np.argmin(distances)
            raw_point = closest_points[min_idx]

            # Merge points that are “almost overlapping” here.
            merged_point = merge_close_point(raw_point, connection_points, tol=0.1)

            connection_points.append(merged_point)
            building["connection_point"] = merged_point

        # add all the connection points to heat_network_points
        # but note that the same connection point can only be added once
        # (Two buildings across from each other may share the same connection point.)
        heat_network_points = []
        seen = set()
        for pt in connection_points:
            if pt not in seen:
                heat_network_points.append(pt)
                seen.add(pt)

        # get the coordinate of the transformer(energy hub)
        transformer = tuple(transformer_info["position"])

        # add transformer(energy hub) node to heat_network_points
        heat_network_points.insert(0, transformer)
        num_nodes = len(heat_network_points)
        # get the range of nodes that must be linked in the network
        terminal_nodes = range(num_nodes)

        # add road endpoints to heat_network_points
        for line in lines_info:
            start = tuple(line["start"])
            end = tuple(line["end"])
            # Check whether the node is in the list. If it is not, add it.
            if not point_in_list(start, heat_network_points):
                heat_network_points.append(start)
            if not point_in_list(end, heat_network_points):
                heat_network_points.append(end)

        # %% STEP TWO: add all nodes and possible edges to the graph
        # Create networkx-graph
        weighted_graph = nx.Graph()

        # add all nodes to the graph
        for i, point in enumerate(heat_network_points):
            weighted_graph.add_node(i, pos=point)

        # add all edges to the graph
        for line in lines_info:
            start = line["start"]
            end = line["end"]
            # Find all nodes along this line
            nodes_on_road = [i for i, point in enumerate(heat_network_points)
                             if is_on_line(point, start, end)]
            # sort the nodes from start point to end point
            nodes_on_road.sort(key=lambda i: project_on_line(heat_network_points[i], start, end))

            # add edges between adjacent nodes
            for u, v in zip(nodes_on_road[:-1], nodes_on_road[1:]):
                weighted_graph.add_edge(u, v, weight=euclidean(heat_network_points[u], heat_network_points[v]))


        # %% STEP THREE: FIND NETWORK WITH MINIMUM TOTAL PIPE LENGTH (STEINER TREE)
        """What is a steiner tree:
        Connects all terminal nodes with the minimum total edge weight (pipe length).
        Avoids cycles and redundant connections.
        Ensures the shortest total length of pipes necessary to connect all terminal nodes.
        Terminal nodes constitute a subset of all nodes within the graph, including all building access points and energy hub node in this code."""
        network = steiner_tree(weighted_graph, terminal_nodes, weight='weight', method="mehlhorn")

        # %% STEP FOUR: add all building connection pipes to the graph
        # get node positions (only EH and building connection points)
        pos = {}
        for i in range(num_nodes):
            pos[i] = heat_network_points[i]

        # Create a copy of the optimization network (since the optimization network cannot be modified).
        mutable_network = nx.Graph(network)

        i = len(heat_network_points)
        # add building nodes to the mutable-graph
        for building in buildings_info:
            bld = tuple(building["position"])
            mutable_network.add_node(i, pos=bld)
            i += 1

        # Create a mapping from POS -> node_id
        pos_to_node = {}
        for node_id, data in mutable_network.nodes(data=True):
            pos_to_node[tuple(data['pos'])] = node_id

        # Traverse each building and add a building connection edge.
        for building in buildings_info:
            bld_pos = tuple(building["position"])
            conn_pos = tuple(building["connection_point"])

            bld_node = pos_to_node[bld_pos]  # index of the building node
            # Add attribute to facilitate diameter optimization(locate building nodes, add thermal load and flow rate)
            mutable_network.nodes[bld_node]["role"] = "bldg"

            conn_node = pos_to_node[conn_pos]  # index of the connection node
            # Add role attribute
            mutable_network.nodes[conn_node]["role"] = "node"

            # add edge and the weight(length) of the edge to the graph
            dist = ((bld_pos[0] - conn_pos[0]) ** 2 + (bld_pos[1] - conn_pos[1]) ** 2) ** 0.5
            mutable_network.add_edge(bld_node, conn_node, weight=dist, kind="connection")

        transformer_node = pos_to_node[transformer]  # index of the transformer node
        # Add role attribute
        mutable_network.nodes[transformer_node]["role"] = "EH"
        # Assign the role attribute to the remaining nodes that have not yet been assigned one, setting it to “node”.
        for n in mutable_network.nodes:
            if "role" not in mutable_network.nodes[n]:
                mutable_network.nodes[n]["role"] = "node"

        # Assign unique identifiers to all nodes and count the role attributes separately.
        counters = {"bldg": 1, "node": 1, "EH": 1}

        for n in mutable_network.nodes:
            role = mutable_network.nodes[n].get("role", "node")  # default value for unassigned role attribute: "node"
            # Assign unique identifiers to all nodes
            if role == "bldg":
                mutable_network.nodes[n]["id"] = f"bldg{counters['bldg']}"
                counters["bldg"] += 1
            elif role == "EH":
                mutable_network.nodes[n]["id"] = f"EH{counters['EH']}"
                counters["EH"] += 1
            else:
                mutable_network.nodes[n]["id"] = f"node{counters['node']}"
                counters["node"] += 1

        # %% STEP FIVE: Plot Network
        # Set image size and resolution
        plt.figure(figsize=(12, 8), dpi=300)

        # plot the edges
        nx.draw_networkx_edges(network, pos=nx.get_node_attributes(network, "pos"),
                               alpha=0.5, edge_color='blue', width=3)
        nx.draw_networkx_edges(mutable_network, pos=nx.get_node_attributes(mutable_network, "pos"),
                               edgelist=[(u, v) for u, v, d in mutable_network.edges(data=True) if d.get("kind") == "connection"],
                               alpha=0.5, edge_color='blue', width=2)

        # plot the buildings
        for building in buildings_info:
            cx, cy = building["position"]  # coordinate of the center point of the building
            half_w = building_width / 2
            rect = patches.Rectangle(
                (cx - half_w, cy - half_w),  # Lower left corner of the building
                building_width,
                building_width,
                linewidth=1,
                edgecolor='black',
                facecolor='lightgray',
                alpha=0.7
            )
            plt.gca().add_patch(rect)

        # plot the nodes(EH and all connection points)
        nx.draw_networkx_nodes(network, pos=pos, nodelist=pos.keys(), node_color="green", node_size=150)
        nx.draw_networkx_labels(network, pos=pos, labels={i: i for i in pos.keys()}, font_size=8, font_color="white")

        plt.grid(True)
        plt.axis("equal")

        # Save figure
        # define the save path for the output file
        current_dir = os.path.dirname(__file__)
        save_dir = os.path.join(current_dir, '..', 'data', 'scenarios')
        # create the folder if it doesn't exist
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        plot_filename = f"pipeline_layout_road_{district_type}_buildings_{len(buildings_info)}.png"
        # plot_filename = get_unique_filename(plot_filename)
        plot_path = os.path.join(save_dir, plot_filename)
        plt.savefig(plot_path)

        plt.show()

        # %% STEP SIX: Output
        json_filename = f"topology_road_{district_type}_buildings_{len(buildings_info)}.json"
        # json_filename = get_unique_filename(json_filename)
        json_path = os.path.join(save_dir, json_filename)

        # Orient an undirected graph starting from a plant node
        directed_dict = orient_network(mutable_network, transformer_node)

        # Write the identifiers of all nodes, their corresponding coordinates,
        # and the entire network's tree structure into a JSON file.
        json_data = {
            "nodes": {},
            "edges": directed_dict
        }

        for n, attrs in mutable_network.nodes(data=True):
            node_id = attrs["id"]
            json_data["nodes"][node_id] = {
                "role": attrs.get("role", ""),     # Retrieve the node attribute role; if absent, use an empty string.
                "pos": attrs.get("pos", (0, 0))    # Retrieve node coordinates. If none exists, default to (0,0).
            }

        with open(json_path, "w") as f:
            json.dump(json_data, f, indent=4)

    else:
        # Type F

        # classify the horizontal roads and vertical roads
        horizontal_road = []
        for line in lines_info:
            start = line["start"]
            end = line["end"]
            if start[1] == end[1]:
                horizontal_road.append(line)

        # %% STEP ONE: get all the nodes in the graph
        # first get the connection points for all buildings
        # initialize
        connection_points = []
        for b in buildings_info:
            b["connection_point"] = ("unset", "unset")

        # Detect all buildings located near the roads — directly connect them to nearby roads
        for road in horizontal_road:
            y0 = road["start"][1]
            threshold = 50  # Maximum distance from the road for a building to be considered “near”
            # Find buildings located slightly below the road (within threshold)
            buildings_id_left = [b["id"] for b in buildings_info if b["position"][1] < y0 and abs(b["position"][1] - y0) < threshold]
            # Find buildings located slightly above the road (within threshold)
            buildings_id_right = [b["id"] for b in buildings_info if b["position"][1] > y0 and abs(b["position"][1] - y0) < threshold]
            if buildings_id_left or buildings_id_right:
                # All nearby buildings should be connected directly to this road
                buildings_id = buildings_id_left + buildings_id_right
                for id in buildings_id:
                    raw_point = [buildings_info[id]["position"][0], y0]
                    # merge nearly identical connection points
                    merged_point = merge_close_point(raw_point, connection_points, tol=0.1)
                    buildings_info[id]["connection_point"] = merged_point
                    connection_points.append(tuple(merged_point))

        # get the position of the transformer (energy hub)
        transformer = tuple(transformer_info["position"])

        # For buildings that still don’t have a connection point,
        # create one on the side closest to the transformer
        for building in buildings_info:
            if building["connection_point"][0] == "unset":
                if building["position"][1] > transformer[1]:
                    # If the building is above the transformer, connect downward
                    raw_point = [building["position"][0], building["position"][1]-building_width/2-house_connection]
                else:
                    # If the building is below the transformer, connect upward
                    raw_point = [building["position"][0], building["position"][1] + building_width / 2 + house_connection]
                # merge nearly identical connection points
                merged_point = merge_close_point(raw_point, connection_points, tol=0.1)
                building["connection_point"] = merged_point
                connection_points.append(tuple(merged_point))

        # add all the connection points to heat_network_points
        # but note that the same connection point can only be added once
        # (Two buildings across from each other may share the same connection point.)
        seen = set()
        heat_network_points = []
        for p in connection_points:
            if p not in seen:
                seen.add(p)
                heat_network_points.append(p)

        # get the coordinate of the transformer(energy hub)
        heat_network_points.insert(0, transformer)
        num_cp = len(heat_network_points)

        # add building nodes to heat_network_points
        for building in buildings_info:
            bld = tuple(building["position"])
            heat_network_points.append(bld)

        # add all the nodes to the graph
        network = nx.Graph()
        for i, point in enumerate(heat_network_points):
            network.add_node(i, pos=point)

        # Find nodes in the same row (including building connection points and the transformer)
        rows = defaultdict(list)  # row_key -> [(cp_id, pos)]
        for cp_id, pos in enumerate(heat_network_points[:num_cp]):
            # Determine a “row key” by using the y-coordinate of each point
            yk = pos[1]
            rows[yk].append((cp_id, pos))

        # Add nodes that align vertically with the transformer (for vertical connection lines)
        x_col = transformer[0]  # The x-coordinate of the transformer
        col_nodes = []  # Store all column nodes (used for drawing vertical connections)

        i = len(heat_network_points)
        for yk, lst in rows.items():
            # Compute the position of the column connection node for this row
            col_node = tuple([x_col, lst[0][1][1]])

            if col_node[1] != transformer[1]:
                # Skip if the node overlaps with the transformer itself
                lst.append((i, col_node))  # Add the new column node to this row
                col_nodes.append(col_node)
                network.add_node(i, pos=col_node)  # Add it to the network graph
                i += 1
                print("Adding col_node:", i, col_node)

        # %% STEP TWO: add all the edges to the graph
        # Create a mapping from POS -> node_id
        pos_to_node = {}
        for node_id, data in network.nodes(data=True):
            pos_to_node[tuple(data['pos'])] = node_id

        # Traverse each building and add a building connection edge.
        for building in buildings_info:
            bld_pos = tuple(building["position"])
            conn_pos = tuple(building["connection_point"])

            bld_node = pos_to_node[bld_pos]  # index of the building node
            conn_node = pos_to_node[conn_pos]  # index of the connection node

            # add edge and the weight(length) of the edge to the graph
            dist = ((bld_pos[0] - conn_pos[0]) ** 2 + (bld_pos[1] - conn_pos[1]) ** 2) ** 0.5
            network.add_edge(bld_node, conn_node, weight=dist, kind="connection")

        # add all horizontal connection pipes to the graph
        for yk, lst in rows.items():
            # Sort nodes within the same row(y-value) from left to right
            lst.sort(key=lambda x: x[1][0])
            for k in range(len(lst)-1):
                start = tuple(lst[k][1])
                end = tuple(lst[k+1][1])

                start_node = pos_to_node[start]  # index of the start point
                end_node = pos_to_node[end]  # index of the end point

                dist = ((start[0] - end[0]) ** 2 + (start[1] - end[1]) ** 2) ** 0.5
                network.add_edge(start_node, end_node, weight=dist, kind="row")

        # add all vertical connection pipes to the graph
        col_nodes.append(transformer)
        col_nodes.sort(key=lambda x: x[1])
        for k in range(len(col_nodes)-1):
            start = tuple(col_nodes[k])
            end = tuple(col_nodes[k + 1])

            start_node = pos_to_node[start]  # index of the start point
            end_node = pos_to_node[end]  # index of the end point

            dist = ((start[0] - end[0]) ** 2 + (start[1] - end[1]) ** 2) ** 0.5
            network.add_edge(start_node, end_node, weight=dist, kind="column")

        # %% STEP THREE: Plot Network

        # Set image size and resolution
        plt.figure(figsize=(12, 8), dpi=300)

        # plot the edges
        nx.draw_networkx_edges(network, pos=nx.get_node_attributes(network, "pos"),
                               alpha=0.5, edge_color='blue', width=3)

        # plot the buildings
        for building in buildings_info:
            cx, cy = building["position"]  # coordinate of the center point of the building
            half_w = building_width / 2
            rect = patches.Rectangle(
                (cx - half_w, cy - half_w),  # Lower left corner of the building
                building_width,
                building_width,
                linewidth=1,
                edgecolor='black',
                facecolor='lightgray',
                alpha=0.7
            )
            plt.gca().add_patch(rect)

        # plot the nodes(EH and all connection points)
        pos = nx.get_node_attributes(network, "pos")
        subset_nodes = list(network.nodes())[:num_cp]
        nx.draw_networkx_nodes(network, pos=pos, nodelist=subset_nodes, node_color="green", node_size=150)
        nx.draw_networkx_labels(network, pos=pos, labels={n: n for n in subset_nodes}, font_size=8, font_color="white")

        plt.grid(True)
        plt.axis("equal")

        # Save figure
        # define the save path for the output file
        current_dir = os.path.dirname(__file__)
        save_dir = os.path.join(current_dir, '..', 'data', 'scenarios')
        # create the folder if it doesn't exist
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        plot_filename = f"pipeline_layout_road_{district_type}_buildings_{len(buildings_info)}.png"
        # plot_filename = get_unique_filename(plot_filename)
        plot_path = os.path.join(save_dir, plot_filename)
        plt.savefig(plot_path)

        plt.show()

        # %% STEP FOUR: Output
        # Add role attribute
        for building in buildings_info:
            bld_pos = tuple(building["position"])
            bld_node = pos_to_node[bld_pos]  # index of the building node
            network.nodes[bld_node]["role"] = "bldg"  # Add attribute to facilitate diameter optimization

        transformer_node = pos_to_node[transformer]  # index of the EH node
        network.nodes[transformer_node]["role"] = "EH"  # Add attribute to facilitate diameter optimization

        # Assign the role attribute to the remaining nodes that have not yet been assigned one, setting it to “node”.
        for n in network.nodes:
            if "role" not in network.nodes[n]:
                network.nodes[n]["role"] = "node"

        # Assign unique identifiers to all nodes and count the role attributes separately.
        counters = {"bldg": 1, "node": 1, "EH": 1}

        for n in network.nodes:
            role = network.nodes[n].get("role", "node")  # default value for unassigned role attribute: "node"
            # Assign unique identifiers to all nodes
            if role == "bldg":
                network.nodes[n]["id"] = f"bldg{counters['bldg']}"
                counters["bldg"] += 1
            elif role == "EH":
                network.nodes[n]["id"] = f"EH{counters['EH']}"
                counters["EH"] += 1
            else:
                network.nodes[n]["id"] = f"node{counters['node']}"
                counters["node"] += 1

        json_filename = f"topology_road_{district_type}_buildings_{len(buildings_info)}.json"
        # json_filename = get_unique_filename(json_filename)
        json_path = os.path.join(save_dir, json_filename)

        # Orient an undirected graph starting from a plant node
        directed_dict = orient_network(network, transformer_node)

        # Write the identifiers of all nodes, their corresponding coordinates,
        # and the entire network's tree structure into a JSON file.
        json_data = {
            "nodes": {},
            "edges": directed_dict
        }

        for n, attrs in network.nodes(data=True):
            node_id = attrs["id"]
            json_data["nodes"][node_id] = {
                "role": attrs.get("role", ""),  # Retrieve the node attribute role; if absent, use an empty string.
                "pos": attrs.get("pos", (0, 0))  # Retrieve node coordinates. If none exists, default to (0,0).
            }

        with open(json_path, "w") as f:
            json.dump(json_data, f, indent=4)
