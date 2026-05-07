
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional
import math

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

DISTRICT_LABELS = {
    "residential2": "Wohnquartier 1",
    "residential0": "Wohnquartier 2",
    "residential3": "Wohnquartier 3",
    "mixed1": "Mischquartier",
    "ghd6": "Gewerbequartier",
}

def _get_district_label(district_name: str) -> str:
    """Gibt das Label für einen District zurück."""
    return DISTRICT_LABELS.get(district_name, district_name)



def load_heat_demand_csv(
    district_name: str,
    csv_path: str | Path,
) -> Dict[str, Dict[int, Dict[int, Dict[int, float]]]]:
    """
    Lädt eine CSV-Datei mit Spalten:
    Support_Year;Cluster;Timestep;Heat_Demand_kW;...

    Rückgabeformat:
    heat_demand_dict[district_name][year][cluster][ts] = Heat_Demand_kW
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {csv_path}")

    df = pd.read_csv(csv_path, sep=";")

    required_cols = {"Support_Year", "Cluster", "Timestep", "Heat_Demand_kW"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Fehlende Spalten in {csv_path}: {sorted(missing)}")

    heat_demand_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    for _, row in df.iterrows():
        year = int(row["Support_Year"])
        cluster = int(row["Cluster"])
        ts = int(row["Timestep"])
        value = float(row["Heat_Demand_kW"])
        heat_demand_dict[district_name][year][cluster][ts] = value

    return heat_demand_dict


def load_power_demand_csv(
    district_name: str,
    csv_path: str | Path,
) -> Dict[str, Dict[int, Dict[int, Dict[int, float]]]]:
    """
    Lädt eine CSV-Datei mit Spalten:
    Support_Year;Cluster;Timestep;Power_Demand_kW;...

    Rückgabeformat:
    power_demand_dict[district_name][year][cluster][ts] = Power_Demand_kW
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {csv_path}")

    df = pd.read_csv(csv_path, sep=";")

    required_cols = {"Support_Year", "Cluster", "Timestep", "Power_Demand_kW"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Fehlende Spalten in {csv_path}: {sorted(missing)}")

    power_demand_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    for _, row in df.iterrows():
        year = int(row["Support_Year"])
        cluster = int(row["Cluster"])
        ts = int(row["Timestep"])
        value = float(row["Power_Demand_kW"])
        power_demand_dict[district_name][year][cluster][ts] = value

    return power_demand_dict

def _set_week_hour_axis(ax, x_values: List[int]) -> None:
    """
    X-Achse für eine Cluster-Woche:
    - 6h-Ticks
    - Tagesname am 00:00-Tick
    """
    if not x_values:
        return

    x_min = min(x_values)
    x_max = max(x_values)
    rel_max = x_max - x_min

    tick_rel = list(range(0, rel_max + 1, 6))
    tick_pos = [x_min + r for r in tick_rel]

    day_names = ["Tag 1", "Tag 2", "Tag 3", "Tag 4", "Tag 5", "Tag 6", "Tag 7"]
    labels = []
    for r in tick_rel:
        day_idx = r // 24
        hour = r % 24
        day_label = day_names[day_idx] if day_idx < 7 else f"Tag {day_idx + 1}"

        if hour == 0:
            labels.append(f"{day_label}\n00:00")
        else:
            labels.append(f"{hour:02d}:00")

    ax.set_xticks(tick_pos)
    ax.set_xticklabels(labels)
    ax.set_xlim(x_min, x_max)

    # Tagesgrenzen visuell markieren
    for r in range(0, rel_max + 1, 24):
        ax.axvline(x=x_min + r, color="grey", linewidth=0.8, alpha=0.25)



def plot_summed_heat_demand_three_districts(
    district_names: List[str],
    analyzed_year: int,
    csv_dir: str | Path,
    save_path: str | Path,
    cluster_ids: Optional[List[int]] = None,
    scenario: Optional[str] = None,
    y_max: Optional[float] = None,
    y_step: Optional[float] = None,
) -> Dict[int, Dict[int, float]]:
    """
    district_names: Liste mit genau 3 District-Namen.
    analyzed_year: zu analysierendes Support_Year.
    csv_dir: Verzeichnis, in dem die CSV-Dateien liegen. Dateinamen:
             {district_name}_demand_heat_timeseries.csv
    save_path: Zielpfad für die Abbildung.
    cluster_ids: Optional. Liste der Cluster, die geplottet werden sollen.
                 Wenn None, werden alle Cluster geplottet.

    Rückgabe:
    summed[cluster][ts] = Summe(Heat_Demand_kW) über alle 3 Districts.
    """
    if len(district_names) != 3:
        raise ValueError("district_names muss genau 3 Einträge enthalten.")

    csv_dir = Path(csv_dir)
    if not csv_dir.exists():
        raise FileNotFoundError(f"CSV-Verzeichnis nicht gefunden: {csv_dir}")

    merged = {}
    for d in district_names:
        csv_path = csv_dir / f"{d}_demand_heat_timeseries.csv"
        dct = load_heat_demand_csv(d, csv_path)
        merged[d] = dct[d]

    all_clusters = set()
    for d in district_names:
        if analyzed_year in merged[d]:
            all_clusters.update(merged[d][analyzed_year].keys())

    if not all_clusters:
        raise ValueError(f"Für Jahr {analyzed_year} wurden in den drei Dateien keine Daten gefunden.")

    if cluster_ids is None:
        clusters_sorted = sorted(all_clusters)
    else:
        missing = [c for c in cluster_ids if c not in all_clusters]
        if missing:
            raise ValueError(f"Folgende Cluster wurden für Jahr {analyzed_year} nicht gefunden: {missing}")
        clusters_sorted = list(cluster_ids)

    n = len(clusters_sorted)
    fig, axes = plt.subplots(nrows=n, ncols=1, figsize=(14, max(3 * n, 4)), sharex=False)
    if n == 1:
        axes = [axes]

    summed = defaultdict(lambda: defaultdict(float))

    for i, cluster_id in enumerate(clusters_sorted):
        cluster_ts_set = set()
        for d in district_names:
            ts_map = merged[d].get(analyzed_year, {}).get(cluster_id, {})
            cluster_ts_set.update(ts_map.keys())

        if not cluster_ts_set:
            continue

        sorted_timesteps = sorted(cluster_ts_set)
        ax = axes[i]

        for d in district_names:
            y = [
                merged[d].get(analyzed_year, {}).get(cluster_id, {}).get(ts, 0.0)
                for ts in sorted_timesteps
            ]
            label = _get_district_label(d)
            ax.plot(sorted_timesteps, y, linewidth=1.2, label=label)


        for ts in sorted_timesteps:
            summed[cluster_id][ts] = sum(
                merged[d].get(analyzed_year, {}).get(cluster_id, {}).get(ts, 0.0)
                for d in district_names
            )

        ax.set_title(f"{scenario}-Szenario")
        ax.set_ylabel("Wärmeverbrauch in kW")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize="small")
        _set_week_hour_axis(ax, sorted_timesteps)
        if y_max is not None:
            ax.set_ylim(bottom=0, top=y_max)
        if y_step is not None:
            ax.yaxis.set_major_locator(plt.MultipleLocator(y_step))


    axes[-1].set_xlabel("Zeit in Stunden")
    fig.tight_layout()

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    return {c: dict(ts_map) for c, ts_map in summed.items()}


def plot_summed_power_demand_three_districts(
    district_names: List[str],
    analyzed_year: int,
    csv_dir: str | Path,
    save_path: str | Path,
    cluster_ids: Optional[List[int]] = None,
    scenario: Optional[str] = None,
    y_max: Optional[float] = None,
    y_step: Optional[float] = None,
) -> Dict[int, Dict[int, float]]:
    """
    district_names: Liste mit genau 3 District-Namen.
    analyzed_year: zu analysierendes Support_Year.
    csv_dir: Verzeichnis, in dem die CSV-Dateien liegen. Dateinamen:
             {district_name}_demand_power_timeseries.csv
    save_path: Zielpfad für die Abbildung.
    cluster_ids: Optional. Liste der Cluster, die geplottet werden sollen.
                 Wenn None, werden alle Cluster geplottet.

    Rückgabe:
    summed[cluster][ts] = Summe(Power_Demand_kW) über alle 3 Districts.
    """
    if len(district_names) != 3:
        raise ValueError("district_names muss genau 3 Einträge enthalten.")

    csv_dir = Path(csv_dir)
    if not csv_dir.exists():
        raise FileNotFoundError(f"CSV-Verzeichnis nicht gefunden: {csv_dir}")

    merged = {}
    for d in district_names:
        csv_path = csv_dir / f"{d}_demand_power_timeseries.csv"
        dct = load_power_demand_csv(d, csv_path)
        merged[d] = dct[d]

    all_clusters = set()
    for d in district_names:
        if analyzed_year in merged[d]:
            all_clusters.update(merged[d][analyzed_year].keys())

    if not all_clusters:
        raise ValueError(f"Für Jahr {analyzed_year} wurden in den drei Dateien keine Daten gefunden.")

    if cluster_ids is None:
        clusters_sorted = sorted(all_clusters)
    else:
        missing = [c for c in cluster_ids if c not in all_clusters]
        if missing:
            raise ValueError(f"Folgende Cluster wurden für Jahr {analyzed_year} nicht gefunden: {missing}")
        clusters_sorted = list(cluster_ids)

    n = len(clusters_sorted)
    fig, axes = plt.subplots(nrows=n, ncols=1, figsize=(14, max(3 * n, 4)), sharex=False)
    if n == 1:
        axes = [axes]

    summed = defaultdict(lambda: defaultdict(float))

    for i, cluster_id in enumerate(clusters_sorted):
        cluster_ts_set = set()
        for d in district_names:
            ts_map = merged[d].get(analyzed_year, {}).get(cluster_id, {})
            cluster_ts_set.update(ts_map.keys())

        if not cluster_ts_set:
            continue

        sorted_timesteps = sorted(cluster_ts_set)
        ax = axes[i]

        for d in district_names:
            y = [
                merged[d].get(analyzed_year, {}).get(cluster_id, {}).get(ts, 0.0)
                for ts in sorted_timesteps
            ]
            label = _get_district_label(d)
            ax.plot(sorted_timesteps, y, linewidth=1.2, label=label)

        for ts in sorted_timesteps:
            summed[cluster_id][ts] = sum(
                merged[d].get(analyzed_year, {}).get(cluster_id, {}).get(ts, 0.0)
                for d in district_names
            )

        ax.set_title(f"{scenario}-Szenario")
        ax.set_ylabel("Strombedarf in kW")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize="small")
        _set_week_hour_axis(ax, sorted_timesteps)

        # Y-Achse konfigurieren
        if y_max is not None:
            ax.set_ylim(bottom=0, top=y_max)
        if y_step is not None:
            ax.yaxis.set_major_locator(plt.MultipleLocator(y_step))


    axes[-1].set_xlabel("Zeit in Stunden")
    fig.tight_layout()

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    return {c: dict(ts_map) for c, ts_map in summed.items()}


if __name__ == "__main__":
    # Beispielaufrufe
    district_names = ["mixed1", "residential2", "ghd6"]
    #district_names = ["residential0", "residential2", "residential3"]
    #district_names = ["residential0", "residential2", "mixed1"]
    scenario = "Basis"
    #scenario = "Wohn"
    #scenario = "Wohnmisch"
    analyzed_year = 10
    csv_dir = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results"
    cluster_ids = [0,1,2,3]
    #cluster_ids = [2]
    cluster_amount = len(cluster_ids)
    y_max = None


    # Heat Demand Plot
    save_path_heat = f"D:\\cwu-tja\\districtgenerator\\Main-tja\\optimization_results\\plots\\summed_heat_demand_{scenario}_{cluster_amount}_Cluster.pdf"
    plot_summed_heat_demand_three_districts(
        district_names=district_names,
        analyzed_year=analyzed_year,
        csv_dir=csv_dir,
        save_path=save_path_heat,
        cluster_ids=cluster_ids,
        scenario=scenario,
        y_max=y_max
    )

    # Power Demand Plot
    save_path_power = f"D:\\cwu-tja\\districtgenerator\\Main-tja\\optimization_results\\plots\\summed_power_demand_{scenario}_{cluster_amount}_Cluster.pdf"
    plot_summed_power_demand_three_districts(
        district_names=district_names,
        analyzed_year=analyzed_year,
        csv_dir=csv_dir,
        save_path=save_path_power,
        cluster_ids=cluster_ids,
        scenario=scenario,
        y_max=y_max
    )

