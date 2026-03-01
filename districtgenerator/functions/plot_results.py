import matplotlib.pyplot as plt
import os
import numpy as np
import csv
import re


import csv

def _parse_value(v):
    if v is None or v == "":
        return None
    try:
        i = int(v)
        if str(i) == v:
            return i
    except Exception:
        pass
    try:
        return float(v)
    except Exception:
        return v

def load_results_to_dict(csv_file_path):
    results = {}

    def empty_bucket():
        return {
            "scalar": {},
            "by_device": {},
            "by_year": {},
            "by_year_device": {},
            "unit": {}
        }

    with open(csv_file_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            scenario = row.get("scenario", "")
            category = row.get("category", "")
            metric = row.get("metric", "")
            device = row.get("device") or None
            year_raw = row.get("year")
            year = int(year_raw) if year_raw not in (None, "") else None
            value = _parse_value(row.get("value"))
            unit = row.get("unit") or ""

            scen = results.setdefault(scenario, {})
            cat = scen.setdefault(category, empty_bucket())

            # save unit pro metric 
            if metric and metric not in cat["unit"]:
                cat["unit"][metric] = unit

            # je nach Dimension einsortieren
            if year is None and device is None:
                cat["scalar"][metric] = value
            elif year is None and device is not None:
                cat["by_device"].setdefault(metric, {})[device] = value
            elif year is not None and device is None:
                cat["by_year"].setdefault(metric, {})[year] = value
            else:
                cat["by_year_device"].setdefault(metric, {}).setdefault(year, {})[device] = value

    return results


def plot_device_capacities_from_short_csv(scenario_name=None, base_dir=None, result_dir=None, show=True):
    """
    Load short CSV results and plot device capacities (x=device, y=capacity).

    Supported filename patterns:
    - <scenario>_network_results_short.csv
    - <scenario>_results_short.csv

    Parameters
    ----------
    scenario_name : str | list[str] | None
        Scenario name(s) without suffix. If None, all matching files in base_dir are loaded.
    base_dir : str | None
        Directory containing result CSV files.
    result_dir : str | None
        Output directory for plot files.
    show : bool
        If True, show plot window; otherwise only save file.

    Returns
    -------
    dict
        Loaded capacities: {scenario: {device: capacity}}
    """
    if base_dir is None:
        # Build default results directory relative to this file
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    # Collect candidate CSV files
    files_to_load = []

    if scenario_name is None:
        # Load all short result files found in base_dir
        for fn in os.listdir(base_dir):
            if fn.endswith("_network_results_short.csv") or fn.endswith("_results_short.csv"):
                files_to_load.append(os.path.join(base_dir, fn))
    else:
        # Load explicit scenario(s), preferring *_network_results_short.csv
        scenario_names = [scenario_name] if isinstance(scenario_name, str) else list(scenario_name)
        for sc in scenario_names:
            c1 = os.path.join(base_dir, f"{sc}_network_results_short.csv")
            c2 = os.path.join(base_dir, f"{sc}_results_short.csv")
            if os.path.isfile(c1):
                files_to_load.append(c1)
            elif os.path.isfile(c2):
                files_to_load.append(c2)

    if not files_to_load:
        raise FileNotFoundError(
            f"No matching short CSV found in '{base_dir}' "
            f"(expected: *_network_results_short.csv or *_results_short.csv)."
        )

    capacities_by_scenario = {}

    # Parse all selected files
    for csv_path in files_to_load:
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)

        if not rows:
            continue

        # Read scenario name from CSV; fallback to filename if missing
        scenario = rows[0].get("scenario", "").strip()
        if not scenario:
            base = os.path.basename(csv_path)
            scenario = base.replace("_network_results_short.csv", "").replace("_results_short.csv", "")

        capacities = {}
        for row in rows:
            # Only keep device capacity rows
            if row.get("category") == "device" and row.get("metric") == "capacity":
                dev = (row.get("device") or "").strip()
                raw = row.get("value")
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    continue
                if dev:
                    capacities[dev] = val

        if capacities:
            capacities_by_scenario[scenario] = capacities

    if not capacities_by_scenario:
        print("No device capacities found in selected short CSV files.")
        return {}

    # Plot first scenario (single district/scenario view)
    scenario_for_plot = sorted(capacities_by_scenario.keys())[0]
    caps = capacities_by_scenario[scenario_for_plot]

    preferred_order = [
        "HP", "CHP", "TES", "PV", "STC", "WT", "EB", "BOI", "BBOI", "GHP", "CC", "AC",
        "WAT", "BCHP", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "CTES", "BAT", "GS"
    ]
    devices = [d for d in preferred_order if d in caps] + sorted([d for d in caps if d not in preferred_order])

    x = np.arange(len(devices))
    y = [caps[d] for d in devices]

    # Optional display labels
    label_map = {
        "HP": "WP",
        "CHP": "BHKW",
        "TES": "therm. storage",
        "STC": "ST",
        "WT": "WKA",
        "EB": "EK",
    }
    xtick_labels = [label_map.get(d, d) for d in devices]

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    plt.figure(figsize=(12, 6))
    plt.bar(x, y, color="#DD402D")
    plt.xticks(x, xtick_labels)
    plt.ylabel("Installed capacity")
    plt.xlabel("Devices")
    plt.title(f"Device capacities - {scenario_for_plot}")
    plt.grid(axis="y", alpha=0.4)
    plt.tight_layout()

    plot_path = os.path.join(plots_dir, f"device_capacities_{scenario_for_plot}_from_short_csv.png")
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return capacities_by_scenario


# 'def _read_device_capacities_from_result_csv(csv_path):
#     """
#     Read the 'Device-capacity' section from a semicolon-separated result CSV.
#     Returns dict: {device_name: capacity_kW}.
#     """
#     capacities = {}
#     in_device_section = False

#     with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
#         reader = csv.reader(f, delimiter=";")
#         for row in reader:
#             if not row:
#                 continue

#             key = (row[0] or "").strip()
#             val = (row[1] or "").strip() if len(row) > 1 else ""

#             # Section start
#             if key == "Device-capacity":
#                 in_device_section = True
#                 continue

#             # Stop when next section starts
#             if in_device_section and (
#                 key == ""
#                 or key.endswith(":")
#                 or key in {
#                     "Heat_generation_by_year",
#                     "Heat_profile_energy_kwh_by_year",
#                     "Grid_flows",
#                     "Areas PV and STC",
#                     "volumes of thermal storages",
#                     "Co2_parameter",
#                     "Cost_parameter",
#                 }
#             ):
#                 if key != "":
#                     break
#                 continue

#             if not in_device_section:
#                 continue

#             # Keep only pure device keys (e.g. HP, CHP, TES, PV, STC, WT, EB, ...)
#             # Exclude derived keys like HP_inv, HP_om_cost, ...
#             if "_" in key:
#                 continue
#             if not re.fullmatch(r"[A-Z0-9]+", key):
#                 continue

#             try:
#                 cap = float(val)
#             except (TypeError, ValueError):
#                 continue

#             if np.isfinite(cap) and cap > 0:
#                 capacities[key] = cap

#     return capacities'


# def plot_device_capacities_from_csv(scenario_name, base_dir=None, result_dir=None, show=True):
#     """
#     Plot device capacities from one or multiple scenario result CSVs:
#     <scenario_name>_results.csv

#     Parameters
#     ----------
#     scenario_name : str | list[str]
#         Scenario name(s), without '_results.csv' suffix.
#     base_dir : str, optional
#         Directory of optimization results.
#         Default: ...\\districtgenerator\\Main-tja\\optimization_results
#     result_dir : str, optional
#         Directory where plots folder is created. Default: current directory.
#     show : bool, optional
#         Whether to display the plot.

#     Returns
#     -------
#     None
#     """
#     scenario_names = [scenario_name] if isinstance(scenario_name, str) else list(scenario_name)
#     if not scenario_names:
#         raise ValueError("scenario_name must not be empty.")

#     if base_dir is None:
#         project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
#         base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

#     capacities_by_scenario = {}
#     all_devices = set()

#     for sc in scenario_names:
#         csv_path = os.path.join(base_dir, f"{sc}_network_results.csv")
#         if not os.path.isfile(csv_path):
#             raise FileNotFoundError(f"CSV not found: {csv_path}")

#         caps = _read_device_capacities_from_result_csv(csv_path)
#         capacities_by_scenario[sc] = caps
#         all_devices.update(caps.keys())

#     if not all_devices:
#         print("No installed devices with finite capacity > 0 found in CSV file(s).")
#         return

#     preferred_order = [
#         "HP", "CHP", "TES", "PV", "STC", "WT", "EB", "BOI", "BBOI", "GHP", "CC", "AC",
#         "WAT", "BCHP", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "CTES", "BAT", "GS"
#     ]
#     devices = [d for d in preferred_order if d in all_devices if d!="TES"]
#     devices += sorted([d for d in all_devices if d not in preferred_order])

#     label_map = {
#         "HP": "WP",
#         "CHP": "BHKW",
#         "TES": "therm. Speicher",
#         "PV": "PV",
#         "STC": "ST",
#         "WT": "WKA",
#         "EB": "EK",
#         "BCHP": "BBHKW",
#     }
#     xtick_labels = [label_map.get(d, d) for d in devices]

#     plots_dir = os.path.join(result_dir or ".", "plots")
#     os.makedirs(plots_dir, exist_ok=True)

#     n_devices = len(devices)
#     n_series = len(scenario_names)
#     x = np.arange(n_devices)
#     width = min(0.8 / max(n_series, 1), 0.35)

#     plt.figure(figsize=(12, 6))
#     for idx, sc in enumerate(scenario_names):
#         offset = (idx - (n_series - 1) / 2) * width
#         y_values = [capacities_by_scenario[sc].get(dev, 0.0) for dev in devices]
#         plt.bar(x + offset, y_values, width=width, label=sc, color='#DD402D' if idx == 0 else 'grey')

#     plt.ylabel("Anlagenleistung in kW")
#     plt.xticks(x, xtick_labels)
#     plt.grid(axis="y", alpha=0.4)
#     plt.legend(
#         loc="upper center",
#         bbox_to_anchor=(0.5, -0.15),
#         ncol=max(1, min(4, n_series)),
#         frameon=False,
#     )
#     plt.tight_layout(rect=[0, 0.08, 1, 1])

#     if len(scenario_names) == 1:
#         filename = f"device_capacities_{scenario_names[0]}_from_csv.png"
#     else:
#         filename = "device_capacities_compare_from_csv.png"

#     plot_path = os.path.join(plots_dir, filename)
#     plt.savefig(plot_path, dpi=150)
#     print(f"Device capacities plot saved to {plot_path}")

#     if show:
#         plt.show()
#     else:
#         plt.close()

#     return None

# def plot_device_capacities(result_dictCon, result_dir=None, show=True):
#     """
#     Plots grouped device capacities for all districts.
#     For each device, one bar per district is shown side-by-side.
    
#     Parameters
#     ----------
#     result_dictCon : dict
#         Result dictionary for all districts from network optimization.
#     result_dir : str, optional
#         Directory where plots will be saved. Default is current directory.
#     show : bool, optional
#         Whether to display the plot. Default is True.
    
#     Returns
#     -------
#     None
#     """
#     if result_dictCon is None:
#         raise ValueError("result_dictCon is required")
    
#     plots_dir = os.path.join(result_dir or ".", "plots")
#     os.makedirs(plots_dir, exist_ok=True)

#     # Keep district entries only (skip aggregate entries like "network")
#     district_names = [
#         name for name, values in result_dictCon.items()
#         if isinstance(values, dict) and name != "network"
#     ]
#     if not district_names:
#         print("No district results found in result_dictCon.")
#         return

#     # Collect capacities by district and device
#     capacities_by_district = {}
#     all_devices = set()
#     for district_name in district_names:
#         district_result = result_dictCon[district_name]
#         capacities_by_district[district_name] = {}
#         for key, value in district_result.items():
#             if isinstance(value, dict) and "cap" in value:
#                 cap = value.get("cap", 0)
#                 if isinstance(cap, (int, float)) and np.isfinite(cap) and cap > 0:
#                     capacities_by_district[district_name][key] = cap
#                     all_devices.add(key)

#     if not all_devices:
#         print("No installed devices with finite capacity > 0 found.")
#         return

#     # Deterministic and readable ordering
#     preferred_order = [
#         "HP", "CHP", "TES", "PV", "STC", "WT", "EB", "BOI", "BBOI", "GHP", "CC", "AC",
#         "WAT", "BCHP", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "CTES", "BAT", "GS"
#     ]
#     devices = [dev for dev in preferred_order if dev in all_devices]
#     devices += sorted([dev for dev in all_devices if dev not in preferred_order])

#     label_map = {
#         "HP": "WP",
#         "CHP": "BHKW",
#         "TES": "Speicher",
#         "PV": "PV",
#         "STC": "ST",
#         "WT": "WKA",
#         "EB": "EK",
#     }
#     xtick_labels = [label_map.get(dev, dev) for dev in devices]

#     # Grouped bar chart
#     n_devices = len(devices)
#     n_districts = len(district_names)
#     x = np.arange(n_devices)
#     width = min(0.8 / max(n_districts, 1), 0.35)

#     plt.figure(figsize=(12, 6))
#     for idx, district_name in enumerate(district_names):
#         offset = (idx - (n_districts - 1) / 2) * width
#         y_values = [capacities_by_district[district_name].get(dev, 0) for dev in devices]
#         plt.bar(x + offset, y_values, width=width, label=district_name)

#     plt.ylabel("Capacity (kW)")
#     plt.xticks(x, xtick_labels)
#     plt.grid(axis='y', alpha=0.4)
#     plt.legend(
#     loc="upper center",
#     bbox_to_anchor=(0.5, -0.15),
#     ncol=max(1, min(4, n_districts)),
#     frameon=False
#     )
#     plt.tight_layout(rect=[0, 0.08, 1, 1])

#     filename = "device_capacities_all_districts.png"
#     plot_path = os.path.join(plots_dir, filename)
#     plt.savefig(plot_path, dpi=150)
#     print(f"Device capacities comparison plot saved to {plot_path}")
    
#     if show:
#         plt.show()
#     else:
#         plt.close()
    
#     return None

# def plot_grid_flows(result_dictCon=None,y=None, result_dir=None, show=True):

#     if result_dictCon is None:
#         raise ValueError("result_dict is required")
    
#     plots_dir = os.path.join(result_dir or ".", "plots")
#     os.makedirs(plots_dir, exist_ok=True)


#     for district_name, result_dict in result_dictCon.items():  
        
#         series_from_main_grid_by_year = result_dict.get("from_main_grid_timeseries")
#         series_to_main_grid_by_year = result_dict.get("to_main_grid_timeseries")
#         series_from_network_by_year = result_dict.get("from_network_timeseries")
#         series_to_network_by_year = result_dict.get("to_network_timeseries")
#         series_from_grid_by_year = result_dict.get("from_grid_timeseries")
#         series_to_grid_by_year = result_dict.get("to_grid_timeseries")
        
#         if not series_from_main_grid_by_year:
#             continue 
        
        
#         available_years = sorted(series_from_main_grid_by_year.keys())
#         year = y if y is not None else available_years[0]
#         if year not in series_from_main_grid_by_year:
#             raise ValueError(f"support year {year} not in from_main_grid_timeseries for {district_name}")

#         values_from_main_grid = [value for cluster in series_from_main_grid_by_year[year] for value in cluster]
#         values_to_main_grid = [value for cluster in series_to_main_grid_by_year[year] for value in cluster]
#         values_from_network = [value for cluster in series_from_network_by_year[year] for value in cluster]
#         values_to_network = [value for cluster in series_to_network_by_year[year] for value in cluster]
#         values_from_grid = [value for cluster in series_from_grid_by_year[year] for value in cluster]
#         values_to_grid = [value for cluster in series_to_grid_by_year[year] for value in cluster]
#         x = list(range(len(values_from_main_grid)))

#         title = f"from_and_to_main_grid timeseries"
#         if district_name:
#             title += f" - {district_name}"
#         title += f" (year {year})"

#         plt.figure(figsize=(12, 4))
#         plt.plot(x, values_from_main_grid, label="From Main Grid", color='blue')
#         plt.plot(x, values_to_main_grid, label="To Main Grid", color='orange')
#         plt.plot(x, values_from_network, label="From Network", linestyle='--', color='blue')
#         plt.plot(x, values_to_network, label="To Network", linestyle='--', color='orange')
#         highlight_indices = [
#             i for i, (a, b, c, d) in enumerate(zip(values_from_main_grid, values_from_network, values_to_main_grid, values_to_network))
#             if (a > 0 and c > 0) or (a > 0 and d > 0 ) or (b > 0 and c > 0) or (b > 0 and d > 0)
#         ]
#         for idx in highlight_indices:
#             plt.axvspan(idx - 0.5, idx + 0.5, color="#8a0707c8", alpha=0.4, zorder=0)
#         plt.xlabel("Time step")
#         plt.ylabel("Power from and to main grid (kW)")
#         plt.title(title)
#         plt.legend()
#         plt.tight_layout()

#         if district_name:
#             filename = f"all_grid_flows_{district_name}_y{year}.png"
#         else:
#             filename = f"all_grid_flows_y{year}.png"

#         plot_path = os.path.join(plots_dir, filename)
#         plt.savefig(plot_path, dpi=150)

#         if show:
#             plt.show()
#         else:
#             plt.close()

#         plt.figure(figsize=(12, 4))
#         plt.plot(x, values_from_main_grid, label="From Main Grid", color='blue')
#         plt.plot(x, values_to_main_grid, label="To Main Grid", color='orange')
#         highlight_indices = [
#             i for i, (a, b) in enumerate(zip(values_from_main_grid, values_to_main_grid))
#             if a > 0 and b > 0
#         ]
#         for idx in highlight_indices:
#             plt.axvspan(idx - 0.5, idx + 0.5, color="#f50707", alpha=0.4, zorder=0)
#         plt.xlabel("Time step")
#         plt.ylabel("Power from and to main grid (kW)")
#         plt.title(title)
#         plt.legend()
#         plt.tight_layout()

#         if district_name:
#             filename = f"main_grid_flows_{district_name}_y{year}.png"
#         else:
#             filename = f"main_grid_flows_y{year}.png"

#         plot_path = os.path.join(plots_dir, filename)
#         plt.savefig(plot_path, dpi=150)

#         if show:
#             plt.show()
#         else:
#             plt.close()
        
#         plt.figure(figsize=(12, 4))
#         plt.plot(x, values_from_grid, label="From Grid", color='blue')
#         plt.plot(x, values_to_grid, label="To Grid", color='orange')
#         highlight_indices = [
#             i for i, (a, b) in enumerate(zip(values_from_grid, values_to_grid))
#             if a > 0 and b > 0
#         ]
#         for idx in highlight_indices:
#             plt.axvspan(idx - 0.5, idx + 0.5, color="#f50707", alpha=0.4, zorder=0)
#         plt.xlabel("Time step")
#         plt.ylabel("Power from and to grid (kW)")
#         plt.title(title)
#         plt.legend()
#         plt.tight_layout()

#         if district_name:
#             filename = f"grid_flows_{district_name}_y{year}.png"
#         else:
#             filename = f"grid_flows_y{year}.png"

#         plot_path = os.path.join(plots_dir, filename)
#         plt.savefig(plot_path, dpi=150)

#         if show:
#             plt.show()
#         else:
#             plt.close()
        
#         plt.figure(figsize=(12, 4))
#         plt.plot(x, values_from_network, label="From Network", linestyle='--', color='blue')
#         plt.plot(x, values_to_network, label="To Network", linestyle='--', color='orange')
#         highlight_indices = [
#             i for i, (a, b) in enumerate(zip(values_from_network, values_to_network))
#             if a > 0 and b > 0
#         ]
#         for idx in highlight_indices:
#             plt.axvspan(idx - 0.5, idx + 0.5, color="#f50707", alpha=0.4, zorder=0)
#         plt.xlabel("Time step")
#         plt.ylabel("Power from and to network (kW)")
#         plt.title(title)
#         plt.legend()
#         plt.tight_layout()

#         if district_name:
#             filename = f"network_flows_{district_name}_y{year}.png"
#         else:
#             filename = f"network_flows_y{year}.png"

#         plot_path = os.path.join(plots_dir, filename)
#         plt.savefig(plot_path, dpi=150)

#         if show:
#             plt.show()
#         else:
#             plt.close()


#     return None

# if __name__ == "__main__":
#     plot_device_capacities_from_csv(["rural", "urban"], show=True)