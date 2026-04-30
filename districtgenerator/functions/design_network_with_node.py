import networkx as nx
import gurobipy as gp
import matplotlib.pyplot as plt

import os
import datetime
import numpy as np
import json
import math
from collections import defaultdict, deque

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

def run_pipeline_node(district_type, buildings_info, transformer_info):
    """
    Ignore road restrictions and connect all building nodes and energy center nodes via the shortest path.
    using Minimum Spanning Tree(MST) algorithm

    Parameters
    ----------
    district_type: string
    buildings_info: list
        list of building informations, each building is a dictionary with following keys:
            "id", "type", "position", "calculated_building_area",
            "number_of_floors", "construction_year", "retrofit_level"
    transformer_info: dictionary
        only one key: "position"

    Returns
    -------
    None
    """
    # %% STEP ONE: get the complete weighted graph
    weighted_graph = nx.Graph()

    # get the coordinate of the transformer(energy hub)
    transformer = tuple(transformer_info["position"])
    # add transformer node to the graph, set the role attribute as "EH"
    weighted_graph.add_node(0, pos=transformer, role="EH")

    # get the coordinates of all building nodes
    heat_network_points = []
    for i, building in enumerate(buildings_info):
        pos = tuple(building["position"])
        heat_network_points.append(pos)
        weighted_graph.add_node(i+1, pos=pos, role="bldg", bldg_id=building["id"])

    # get a list of all the nodes in the graph
    all_points = [transformer] + heat_network_points
    # connect the nodes with edges and generate a complete graph
    for i in range(len(all_points)):
        for j in range(i + 1, len(all_points)):
            x1, y1 = all_points[i]
            x2, y2 = all_points[j]
            distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
            weighted_graph.add_edge(i, j, weight=distance)

    # %% STEP TWO: FIND NETWORK WITH MINIMUM TOTAL PIPE LENGTH (MINIMUM SPANNING TREE)
    # find network with minimal length (= MST = minimal spanning tree)
    """What is a MST:
    Connects all nodes with the minimum total edge weight (pipe length).
    Avoids cycles and redundant connections.
    Ensures the shortest total length of pipes necessary to connect all nodes."""
    network = nx.minimum_spanning_tree(weighted_graph)

    # Calculate and print total network length
    # network_length = sum(edge_lengths[edge_dict[e]] for e in network.edges)
    # print("Pipe connections calculated. Total network length: " + str(network_length) + " m.")

    # get node positions
    pos = nx.get_node_attributes(network, "pos")

    # %% STEP THREE: PLOT NETWORK
    # Set image size and resolution
    plt.figure(figsize=(12, 8), dpi=300)

    # Plot Network
    # plot the edges
    nx.draw_networkx_edges(network, pos, alpha=0.5, edge_color='blue', width=3)
    # plot the nodes
    nx.draw_networkx_nodes(network, pos=pos, nodelist=pos.keys(), node_color="green", node_size=150)
    nx.draw_networkx_labels(network, pos=pos, labels={i: i for i in pos.keys()}, font_size=8, font_color="white")

#    plt.grid(True)              # Enable grid lines on the plot for better readability
    plt.axis("equal")           # Ensure equal scaling on both axes (1 unit on x = 1 unit on y)
    plt.gca().set_axis_on()     # Make sure the plot axes are visible

    # Save figure
    # define the save path for the output file
    current_dir = os.path.dirname(__file__)
    save_dir = os.path.join(current_dir, '..', 'data', 'scenarios')
    # create the folder if it doesn't exist
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    plot_filename_png = os.path.join(save_dir,f"pipeline_layout_node_{district_type}_buildings_{len(buildings_info)}.png")
    plot_filename_svg = os.path.join(save_dir,f"pipeline_layout_node_{district_type}_buildings_{len(buildings_info)}.svg")
    plt.savefig(plot_filename_png, dpi=300)
    plt.savefig(plot_filename_svg, format="svg")

#    plt.show()

    # %% STEP FOUR: OUTPUT
    # Assign unique identifiers to all nodes and count the role attributes separately.
    counters = {"bldg": 1, "node": 1, "EH": 1}

    for n in network.nodes:
        role = network.nodes[n].get("role", "node")  # default value for unassigned role attribute: "node"
        # Assign unique identifiers to all nodes
        if role == "bldg":
            network.nodes[n]["id"] = f"bldg{str(network.nodes[n]['bldg_id'])}"
            counters["bldg"] += 1
        elif role == "EH":
            network.nodes[n]["id"] = f"EH{counters['EH']}"
            counters["EH"] += 1
        else:
            network.nodes[n]["id"] = f"node{counters['node']}"
            counters["node"] += 1

    json_filename = f"topology_node_{district_type}_buildings_{len(buildings_info)}.json"
    # json_filename = get_unique_filename(json_filename)
    json_path = os.path.join(save_dir, json_filename)

    # Orient an undirected graph starting from a plant node
    directed_dict = orient_network(network, 0)

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
