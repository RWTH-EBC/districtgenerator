import os
import csv
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt


def _parse_value(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except Exception:
        try:
            return float(str(v).replace(",", "."))
        except Exception:
            return 0.0


def _to_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except Exception:
        return default


def _resolve_dirs(base_dir: Optional[str], result_dir: Optional[str]) -> Tuple[str, str]:
    if base_dir is None:
        base_dir = os.getcwd()
    if result_dir is None:
        result_dir = base_dir

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"base_dir nicht gefunden: {base_dir}")

    os.makedirs(result_dir, exist_ok=True)
    return base_dir, result_dir


def load_power_timeseries_from_csv(
    scenario_name: str,
    base_dir: Optional[str] = None,
    result_dir: Optional[str] = None,
    production_devices: Optional[List[str]] = None,
    demand_devices: Optional[List[str]] = None,
    import_column: str = "from_grid",
    export_column: str = "to_grid",
    base_demand_column: str = "Power_Demand_kW",  # neu
) -> Dict[str, Any]:
    """
    Lädt <scenario_name>_devices_power_timeseries.csv aus base_dir und aggregiert:
    - Stromproduktion
    - Strombedarf (technische Verbraucher)
    - Strombezug
    - Stromeinspeisung
    """
    base_dir, result_dir = _resolve_dirs(base_dir, result_dir)

    csv_file_path = os.path.join(base_dir, f"{scenario_name}_devices_power_timeseries.csv")
    if not os.path.isfile(csv_file_path):
        raise FileNotFoundError(f"CSV nicht gefunden: {csv_file_path}")

    if production_devices is None:
        production_devices = ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC"]
    if demand_devices is None:
        demand_devices = ["HP", "EB", "CC", "ELYZ"]

    rows = []
    available_columns = set()

    with open(csv_file_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(row)
            available_columns.update(row.keys())

    rows.sort(
        key=lambda r: (
            _to_int(r.get("Support_Year")),
            _to_int(r.get("Cluster")),
            _to_int(r.get("Timestep")),
        )
    )

    grouped = defaultdict(list)

    for r in rows:
        y = _to_int(r.get("Support_Year"))
        d = _to_int(r.get("Cluster"))
        t = _to_int(r.get("Timestep"))

        row_data = {
            "timestep": t,
            "stromproduktion_kw": 0.0,
            "stromeinspeisung_kw": 0.0,
            "strombezug_kw": 0.0,
            "BASE_DEM": _parse_value(r.get("Power_Demand_kW")) if "Power_Demand_kW" in available_columns else 0.0,  # neu
        }

        prod_devices = ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC"]
        row_data["stromproduktion_kw"] = sum(
            _parse_value(r.get(dev)) for dev in prod_devices if dev in available_columns
        )

        if "to_grid" in available_columns:
            row_data["stromeinspeisung_kw"] = _parse_value(r.get("to_grid"))
        if "from_grid" in available_columns:
            row_data["strombezug_kw"] = _parse_value(r.get("from_grid"))

        for dev in demand_devices:
            row_data[dev] = _parse_value(r.get(dev)) if dev in available_columns else 0.0

        grouped[(y, d)].append(row_data)

    return {
        "scenario_name": scenario_name,
        "csv_file": csv_file_path,
        "base_dir": base_dir,
        "result_dir": result_dir,
        "available_columns": sorted(available_columns),
        "production_devices_used": [d for d in production_devices if d in available_columns],
        "demand_devices_used": [d for d in demand_devices if d in available_columns],
        "grouped_series": dict(grouped),
    }

DEVICE_LABELS_DE = {
    "HP": "Wärmepumpe",
    "CHP": "BHKW",
    "BCHP": "BBHKW",
    "TES": "therm. Speicher",
    "STC": "Solarthermie",
    "WT": "Windkraft",
    "EB": "Elektrischer Kessel",
    "BOI": "Erdgas-\nkessel",
    "BBOI": "Biomasse-\nkessel",
    "BASE_DEM": "Grundstrombedarf",  # neu
}

# Nur Rot-/Grau-Palette
RIGHT_BAR_COLORS = {
    "HP": "#CA4949",
    "EB": "#D40000",
    # "CC": "#8A8D91",
    # "ELYZ": "#B30000",
    # "CHP": "#9CA0A6",
    # "BCHP": "#8F0000",
    # "TES": "#B0B5BB",
    # "STC": "#A40000",
    # "WT": "#C2C7CD",
    # "BOI": "#C00000",
    # "BBOI": "#D3D7DC",
    "BASE_DEM": "#8C1D17",
}

LEFT_PROD_COLORS = [
    "#8A8B8D",
    "#0B0B0C",
    "#2F3337",
    "#E53935",
    "#C62828",
    "#EF5350",
    "#FF6F61",
]

def _device_label(dev: str) -> str:
    return DEVICE_LABELS_DE.get(dev, dev)

def plot_power_timeseries_by_year_and_clusters(
    scenario_name: str,
    support_year: int,
    num_clusters: int = 1,
    base_dir: Optional[str] = None,
    result_dir: Optional[str] = None,
    show: bool = True,
    titel: Optional[str] = None,
):
    data = load_power_timeseries_from_csv(
        scenario_name=scenario_name,
        base_dir=base_dir,
        result_dir=result_dir,
    )

    base_dir, result_dir = _resolve_dirs(data["base_dir"], data["result_dir"])

    # Alle verfügbaren Cluster für das Jahr sammeln
    clusters = sorted(
        d for (y, d) in data["grouped_series"].keys() if y == support_year
    )

    if not clusters:
        raise ValueError(f"Kein Datensatz für Support_Year={support_year} gefunden.")

    clusters = clusters[:num_clusters]

    fig, axes = plt.subplots(
        len(clusters),
        1,
        figsize=(14, 4 * len(clusters)),
        sharex=True,
        squeeze=False,
    )

    for idx, cluster in enumerate(clusters):
        ax = axes[idx][0]
        series = data["grouped_series"].get((support_year, cluster), [])
        series = sorted(series, key=lambda x: x["timestep"])

        x = [row["timestep"] for row in series]
        y_prod = [row["stromproduktion_kw"] for row in series]
        y_dem = [row["strombedarf_kw"] for row in series]
        y_imp = [row["strombezug_kw"] for row in series]
        y_exp = [row["stromeinspeisung_kw"] for row in series]

        ax.plot(x, y_prod, label="Stromproduktion", linewidth=1.8)
        ax.plot(x, y_dem, label="Strombedarf", linewidth=1.8)
        ax.plot(x, y_imp, label="Strombezug", linewidth=1.8)
        ax.plot(x, y_exp, label="Stromeinspeisung", linewidth=1.8)

        ax.set_title(f"Jahr {support_year} - Cluster {cluster}")
        ax.set_ylabel("kW")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right")

    axes[-1][0].set_xlabel("Timestep")

    fig.suptitle(
        titel or f"Power Timeseries - {scenario_name} - Jahr {support_year}",
        y=0.995,
    )
    fig.tight_layout()

    out_path = os.path.join(
        result_dir,
        f"{scenario_name}_power_timeseries_year_{support_year}_clusters_{num_clusters}.png",
    )
    fig.savefig(out_path, dpi=300, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return out_path

def plot_power_stacked_normalized_by_day(
    scenario_name: str,
    support_year: int,
    cluster: int,
    base_dir: Optional[str] = None,
    result_dir: Optional[str] = None,
    show: bool = True,
    titel: Optional[str] = None,
):
    """
    Plottet 14 gestapelte Säulen:
    - 7 Säulen: Strombezug (unten) + Stromproduktion (oben), normiert
    - 7 Säulen: Strombedarf (unten) + Stromeinspeisung (oben), normiert
    
    Jede Säule = 1 Tag (24 aufeinander folgende Timesteps).
    Normierung: auf die Summe der beiden Größen pro Tag = 100%.
    
    Parameters
    ----------
    scenario_name : str
        Name des Szenarios (für CSV-Datei)
    support_year : int
        Gewähltes Support_Year
    cluster : int
        Gewähltes Cluster (Woche mit stündlicher Auflösung = 7*24 = 168 Timesteps)
    base_dir : Optional[str]
        Verzeichnis, in dem die CSV geladen wird
    result_dir : Optional[str]
        Verzeichnis, in dem die PNG gespeichert wird
    show : bool
        Ob das Diagramm angezeigt werden soll
    titel : Optional[str]
        Benutzerdefinierter Titel
    """
    data = load_power_timeseries_from_csv(
        scenario_name=scenario_name,
        base_dir=base_dir,
        result_dir=result_dir,
    )

    base_dir, result_dir = _resolve_dirs(data["base_dir"], data["result_dir"])

    series = data["grouped_series"].get((support_year, cluster), [])
    if not series:
        raise ValueError(
            f"Keine Daten für Support_Year={support_year}, Cluster={cluster}"
        )

    series = sorted(series, key=lambda x: x["timestep"])

    # Aggregieren in 7 Tage à 24 Timesteps
    days_data = []
    for day in range(7):
        start_idx = day * 24
        end_idx = start_idx + 24
        day_series = series[start_idx:end_idx]

        if len(day_series) < 24:
            day_series.extend(
                [
                    {
                        "timestep": -1,
                        "stromproduktion_kw": 0.0,
                        "strombedarf_kw": 0.0,
                        "strombezug_kw": 0.0,
                        "stromeinspeisung_kw": 0.0,
                    }
                ]
                * (24 - len(day_series))
            )

        # Gruppe 1: Strombezug + Stromproduktion
        prod_sum = sum(row["stromproduktion_kw"] for row in day_series)
        imp_sum = sum(row["strombezug_kw"] for row in day_series)
        total_1 = prod_sum + imp_sum

        if total_1 > 1e-6:
            prod_pct = 100.0 * prod_sum / total_1
            imp_pct = 100.0 * imp_sum / total_1
        else:
            prod_pct = 0.0
            imp_pct = 0.0

        # Gruppe 2: Strombedarf + Stromeinspeisung
        dem_sum = sum(row["strombedarf_kw"] for row in day_series)
        exp_sum = sum(row["stromeinspeisung_kw"] for row in day_series)
        total_2 = dem_sum + exp_sum

        if total_2 > 1e-6:
            dem_pct = 100.0 * dem_sum / total_2
            exp_pct = 100.0 * exp_sum / total_2
        else:
            dem_pct = 0.0
            exp_pct = 0.0

        days_data.append(
            {
                "day": day + 1,
                # Gruppe 1
                "prod_sum": prod_sum,
                "imp_sum": imp_sum,
                "total_1": total_1,
                "prod_pct": prod_pct,
                "imp_pct": imp_pct,
                # Gruppe 2
                "dem_sum": dem_sum,
                "exp_sum": exp_sum,
                "total_2": total_2,
                "dem_pct": dem_pct,
                "exp_pct": exp_pct,
            }
        )

    # Plot mit 2 Y-Achsen nebeneinander (14 Säulen total)
    fig, ax = plt.subplots(figsize=(14, 6))

    days = [d["day"] for d in days_data]
    
    # Gruppe 1: Bezug + Produktion
    imp_pcts_1 = [d["imp_pct"] for d in days_data]
    prod_pcts_1 = [d["prod_pct"] for d in days_data]
    
    # Gruppe 2: Bedarf + Einspeisung
    dem_pcts_2 = [d["dem_pct"] for d in days_data]
    exp_pcts_2 = [d["exp_pct"] for d in days_data]

    # X-Positionen: 14 Säulen mit Abstand
    x_pos_1 = [i * 2 for i in range(len(days))]      # 0, 2, 4, ...
    x_pos_2 = [i * 2 + 0.8 for i in range(len(days))] # 0.8, 2.8, 4.8, ...
    
    width = 0.8

    # Gruppe 1: Strombezug (blau) + Stromproduktion (orange)
    bars1_imp = ax.bar(x_pos_1, imp_pcts_1, width, label="Strombezug", color="#1f77b4")
    bars1_prod = ax.bar(x_pos_1, prod_pcts_1, width, bottom=imp_pcts_1, 
                        label="Stromproduktion", color="#ff7f0e")

    # Gruppe 2: Strombedarf (grün) + Stromeinspeisung (rot)
    bars2_dem = ax.bar(x_pos_2, dem_pcts_2, width, label="Strombedarf", color="#2ca02c")
    bars2_exp = ax.bar(x_pos_2, exp_pcts_2, width, bottom=dem_pcts_2,
                       label="Stromeinspeisung", color="#d62728")

    # Prozentangaben auf Säulen (Gruppe 1)
    for i, (imp_pct, prod_pct) in enumerate(zip(imp_pcts_1, prod_pcts_1)):
        if imp_pct > 3:
            ax.text(x_pos_1[i], imp_pct / 2, f"{imp_pct:.0f}%", 
                   ha="center", va="center", fontsize=10, color="white", weight="bold")
        if prod_pct > 3:
            ax.text(x_pos_1[i], imp_pct + prod_pct / 2, f"{prod_pct:.0f}%",
                   ha="center", va="center", fontsize=10, color="white", weight="bold")

    # Prozentangaben auf Säulen (Gruppe 2)
    for i, (dem_pct, exp_pct) in enumerate(zip(dem_pcts_2, exp_pcts_2)):
        if dem_pct > 3:
            ax.text(x_pos_2[i], dem_pct / 2, f"{dem_pct:.0f}%",
                   ha="center", va="center", fontsize=10, color="white", weight="bold")
        if exp_pct > 3:
            ax.text(x_pos_2[i], dem_pct + exp_pct / 2, f"{exp_pct:.0f}%",
                   ha="center", va="center", fontsize=10, color="white", weight="bold")

    #ax.set_xlabel("Tag der Woche", fontsize=11)
    ax.set_ylabel("Prozentualer Anteil (%)", fontsize=11)
    ax.set_title(
        titel
        or f"Normierte Stromflüsse - {scenario_name} - Jahr {support_year}, Cluster {cluster}",
        fontsize=12,
        weight="bold"
    )
    
    # X-Achsen-Labels
    all_x_pos = sorted(x_pos_1 + x_pos_2)
    ax.set_xticks(x_pos_1)
    ax.set_xticklabels([f"Tag {d}" for d in days])
    
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right", fontsize=10, ncol=2)
    ax.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()

    out_path = os.path.join(
        result_dir,
        f"{scenario_name}_power_stacked_normalized_extended_year_{support_year}_cluster_{cluster}.png",
    )
    fig.savefig(out_path, dpi=300, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return out_path



def plot_power_stacked_normalized_by_day_demand_breakdown(
    scenario_name: str,
    support_year: int,
    cluster: int,
    base_dir: Optional[str] = None,
    result_dir: Optional[str] = None,
    show: bool = True,
    titel: Optional[str] = None,
    demand_devices: Optional[List[str]] = None,
    production_devices: Optional[List[str]] = None,
):
    if demand_devices is None:
        demand_devices = ["HP", "EB", "CC", "ELYZ"]
    if production_devices is None:
        production_devices = ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC"]

    base_dir, result_dir = _resolve_dirs(base_dir, result_dir)
    csv_file_path = os.path.join(base_dir, f"{scenario_name}_devices_power_timeseries.csv")
    if not os.path.isfile(csv_file_path):
        raise FileNotFoundError(f"CSV nicht gefunden: {csv_file_path}")

    rows, available_columns = [], set()
    with open(csv_file_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(row)
            available_columns.update(row.keys())

    rows.sort(key=lambda r: (_to_int(r.get("Support_Year")), _to_int(r.get("Cluster")), _to_int(r.get("Timestep"))))
    grouped = defaultdict(list)

    for r in rows:
        y = _to_int(r.get("Support_Year"))
        d = _to_int(r.get("Cluster"))
        t = _to_int(r.get("Timestep"))

        from_main = _parse_value(r.get("from_main_grid")) if "from_main_grid" in available_columns else 0.0
        from_net = _parse_value(r.get("from_network")) if "from_network" in available_columns else 0.0
        if "from_main_grid" not in available_columns and "from_network" not in available_columns and "from_grid" in available_columns:
            from_main = _parse_value(r.get("from_grid"))

        to_main = _parse_value(r.get("to_main_grid")) if "to_main_grid" in available_columns else 0.0
        to_net = _parse_value(r.get("to_network")) if "to_network" in available_columns else 0.0
        if "to_main_grid" not in available_columns and "to_network" not in available_columns and "to_grid" in available_columns:
            to_main = _parse_value(r.get("to_grid"))

        row_data = {
            "timestep": t,
            "from_main_grid_kw": from_main,
            "from_network_kw": from_net,
            "to_main_grid_kw": to_main,
            "to_network_kw": to_net,
            "BASE_DEM": _parse_value(r.get("Power_Demand_kW")) if "Power_Demand_kW" in available_columns else 0.0,
        }

        for pdev in production_devices:
            row_data[pdev] = _parse_value(r.get(pdev)) if pdev in available_columns else 0.0
        for ddev in demand_devices:
            row_data[ddev] = _parse_value(r.get(ddev)) if ddev in available_columns else 0.0

        grouped[(y, d)].append(row_data)

    series = sorted(grouped.get((support_year, cluster), []), key=lambda x: x["timestep"])
    if not series:
        raise ValueError(f"Keine Daten für Support_Year={support_year}, Cluster={cluster}")

    tol = 1e-9
    used_prod_devices = [dev for dev in production_devices if sum(r.get(dev, 0.0) for r in series) > tol]
    right_demand_parts = list(demand_devices) + ["BASE_DEM"]
    used_demand_devices = [dev for dev in right_demand_parts if sum(r.get(dev, 0.0) for r in series) > tol]

    days_data = []
    for day in range(7):
        day_series = series[day * 24: day * 24 + 24]
        if len(day_series) < 24:
            day_series.extend([{
                "timestep": -1,
                "from_main_grid_kw": 0.0, "from_network_kw": 0.0,
                "to_main_grid_kw": 0.0, "to_network_kw": 0.0,
                **{dev: 0.0 for dev in used_prod_devices},
                **{dev: 0.0 for dev in used_demand_devices},
            }] * (24 - len(day_series)))

        imp_main_sum = sum(r["from_main_grid_kw"] for r in day_series)
        imp_net_sum = sum(r["from_network_kw"] for r in day_series)
        prod_sums = {dev: sum(r.get(dev, 0.0) for r in day_series) for dev in used_prod_devices}
        total_1 = imp_main_sum + imp_net_sum + sum(prod_sums.values())

        imp_main_pct = 100.0 * imp_main_sum / total_1 if total_1 > tol else 0.0
        imp_net_pct = 100.0 * imp_net_sum / total_1 if total_1 > tol else 0.0
        prod_pcts = {dev: (100.0 * v / total_1 if total_1 > tol else 0.0) for dev, v in prod_sums.items()}

        dem_sums = {dev: sum(r.get(dev, 0.0) for r in day_series) for dev in used_demand_devices}
        exp_main_sum = sum(r["to_main_grid_kw"] for r in day_series)
        exp_net_sum = sum(r["to_network_kw"] for r in day_series)
        total_2 = sum(dem_sums.values()) + exp_main_sum + exp_net_sum

        dem_pcts = {dev: (100.0 * v / total_2 if total_2 > tol else 0.0) for dev, v in dem_sums.items()}
        exp_main_pct = 100.0 * exp_main_sum / total_2 if total_2 > tol else 0.0
        exp_net_pct = 100.0 * exp_net_sum / total_2 if total_2 > tol else 0.0

        days_data.append({
            "day": day + 1,
            "imp_main_pct": imp_main_pct,
            "imp_net_pct": imp_net_pct,
            "prod_device_pcts": prod_pcts,
            "dem_device_pcts": dem_pcts,
            "exp_main_pct": exp_main_pct,
            "exp_net_pct": exp_net_pct,
        })

    fig, ax = plt.subplots(figsize=(15, 6))
    days = [d["day"] for d in days_data]
    x_pos_1 = [i * 2 for i in range(len(days))]
    x_pos_2 = [i * 2 + 0.8 for i in range(len(days))]
    width = 0.8

    imp_main_pcts = [d["imp_main_pct"] for d in days_data]
    imp_net_pcts = [d["imp_net_pct"] for d in days_data]
    has_imp_main = sum(imp_main_pcts) > tol
    has_imp_net = sum(imp_net_pcts) > tol

    h_imp_main = ax.bar(x_pos_1, imp_main_pcts, width, label="Strombezug Hauptnetz" if has_imp_main else "_nolegend_", color="#38393B" )
    h_imp_net = ax.bar(x_pos_1, imp_net_pcts, width, bottom=imp_main_pcts, label="Strombezug Verbundnetz" if has_imp_net else "_nolegend_", color="#55585C")

    bottom_left = [a + b for a, b in zip(imp_main_pcts, imp_net_pcts)]
    prod_palette = ["#ff7f0e", "#fdae6b", "#fd8d3c", "#e6550d", "#fdd0a2", "#f16913", "#d94801"]
    left_prod_handles = []
    for i_dev, dev in enumerate(used_prod_devices):
        vals = [d["prod_device_pcts"][dev] for d in days_data]
        if sum(vals) <= tol:
            continue
        h = ax.bar(x_pos_1, vals, width, bottom=bottom_left, label=f"Stromproduktion {_device_label(dev)}-Anlage", color=LEFT_PROD_COLORS[i_dev % len(LEFT_PROD_COLORS)])
        left_prod_handles.append(h)
        for i, p in enumerate(vals):
            if p > 3:
                ax.text(x_pos_1[i], bottom_left[i] + p / 2, f"{p:.0f}%", ha="center", va="center", fontsize=10, color="white", weight="bold")
        bottom_left = [b + p for b, p in zip(bottom_left, vals)]

    for i in range(len(days)):
        if imp_main_pcts[i] > 3:
            ax.text(x_pos_1[i], imp_main_pcts[i] / 2, f"{imp_main_pcts[i]:.0f}%", ha="center", va="center", fontsize=10, color="white", weight="bold")
        if imp_net_pcts[i] > 3:
            ax.text(x_pos_1[i], imp_main_pcts[i] + imp_net_pcts[i] / 2, f"{imp_net_pcts[i]:.0f}%", ha="center", va="center", fontsize=10, color="white", weight="bold")

    fallback_colors = ["#6B6E73", "#8A8D91", "#9CA0A6", "#B0B5BB", "#C2C7CD", "#A40000", "#C00000"]
    used_fallback = 0
    device_color = {}
    for dev in used_demand_devices:
        if dev in RIGHT_BAR_COLORS:
            device_color[dev] = RIGHT_BAR_COLORS[dev]
        else:
            device_color[dev] = fallback_colors[used_fallback % len(fallback_colors)]
            used_fallback += 1
    exp_main_color, exp_net_color = "#4d4d4d", "#A40000"

    bottom = [0.0] * len(days)
    right_handles = []
    for dev in used_demand_devices:
        vals = [d["dem_device_pcts"][dev] for d in days_data]
        if sum(vals) <= tol:
            continue
        label = "Grundstrombedarf" if dev == "BASE_DEM" else f"Strombedarf {_device_label(dev)}"
        h = ax.bar(x_pos_2, vals, width, bottom=bottom, label=label, color=device_color[dev])
        right_handles.append(h)
        for i, p in enumerate(vals):
            if p > 3:
                ax.text(x_pos_2[i], bottom[i] + p / 2, f"{p:.0f}%", ha="center", va="center", fontsize=10, color="white", weight="bold")
        bottom = [b + p for b, p in zip(bottom, vals)]

    exp_main_pcts = [d["exp_main_pct"] for d in days_data]
    exp_net_pcts = [d["exp_net_pct"] for d in days_data]
    has_exp_main = sum(exp_main_pcts) > tol
    has_exp_net = sum(exp_net_pcts) > tol

    h_exp_main = None
    h_exp_net = None
    if has_exp_main:
        h_exp_main = ax.bar(x_pos_2, exp_main_pcts, width, bottom=bottom, label="Stromeinspeisung Hauptnetz", color=exp_main_color)
        for i, p in enumerate(exp_main_pcts):
            if p > 3:
                ax.text(x_pos_2[i], bottom[i] + p / 2, f"{p:.0f}%", ha="center", va="center", fontsize=10, color="white", weight="bold")
        bottom = [b + p for b, p in zip(bottom, exp_main_pcts)]

    if has_exp_net:
        h_exp_net = ax.bar(x_pos_2, exp_net_pcts, width, bottom=bottom, label="Stromeinspeisung Verbundnetz", color=exp_net_color)
        for i, p in enumerate(exp_net_pcts):
            if p > 3:
                ax.text(x_pos_2[i], bottom[i] + p / 2, f"{p:.0f}%", ha="center", va="center", fontsize=10, color="white", weight="bold")

    #ax.set_xlabel("Tag der Woche")
    ax.set_ylabel("Prozentualer Anteil (%)")
    day_centers = [(x1 + x2) / 2 for x1, x2 in zip(x_pos_1, x_pos_2)]
    ax.set_xticks(day_centers)
    # ax.set_xticks(x_pos_1)
    ax.set_xticklabels([f"Tag {d}" for d in days])
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_title(titel or f"Stromflüsse mit Demand-Breakdown - {scenario_name} - Jahr {support_year}, Cluster {cluster}")

    handles = []
    if has_imp_main:
        handles.append(h_imp_main)
    if has_imp_net:
        handles.append(h_imp_net)
    handles.extend(left_prod_handles)
    handles.extend(right_handles)
    if h_exp_main is not None:
        handles.append(h_exp_main)
    if h_exp_net is not None:
        handles.append(h_exp_net)

    labels = [h.get_label() for h in handles]
    ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.18),
              ncol=min(4, max(1, len(labels))), fontsize=10, frameon=False)

    fig.tight_layout(rect=[0, 0.08, 1, 1])

    out_path = os.path.join(
        result_dir,
        f"{scenario_name}_power_stacked_demand_breakdown_year_{support_year}_cluster_{cluster}.png",
    )
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return out_path

if __name__ == "__main__":
    base_dir = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results"
    result_dir = r"D:\cwu-tja\districtgenerator\plots"
    # scenario_name = "mixed1"
    # scenario_titel_name = "Mischquartier"
    # scenario_name = "residential2"
    # scenario_titel_name = "Wohnquartier"
    scenario_name = "residential0"
    scenario_titel_name = "Wohnquartier 1"
    # scenario_name = "ghd6"
    # scenario_titel_name = "Gewerbequartier"
    year=0
    year_header= year+2025
    #cluster=3

    #out = plot_power_timeseries_by_year_and_clusters(scenario_name=scenario_name, support_year=year,num_clusters=cluster,base_dir=base_dir,result_dir=result_dir,show=True,)
    for cluster in range(0,4):
        out3=plot_power_stacked_normalized_by_day_demand_breakdown(scenario_name=scenario_name,support_year=year,cluster=cluster,titel=f"Stromflüsse im {scenario_titel_name} im Jahr {year_header} mit dem Cluster {cluster}",
            base_dir=base_dir,result_dir=result_dir,show=True,)
        #print(out)
        print(out3)
