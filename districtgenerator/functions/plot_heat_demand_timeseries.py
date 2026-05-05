# ...existing code...
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List
import math

import pandas as pd
import matplotlib.pyplot as plt


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


def plot_summed_heat_demand_three_districts(
    district_names: List[str],
    analyzed_year: int,
    csv_dir: str | Path,
    save_path: str | Path,
) -> Dict[int, Dict[int, float]]:
    """
    district_names: Liste mit genau 3 District-Namen.
    analyzed_year: zu analysierendes Support_Year.
    csv_dir: Verzeichnis, in dem die CSV-Dateien liegen. Dateinamen:
             {district_name}_demand_heat_timeseries.csv
    save_path: Zielpfad für die Abbildung.

    Rückgabe:
    summed[cluster][ts] = Summe(Heat_Demand_kW) über alle 3 Districts.
    """
    if len(district_names) != 3:
        raise ValueError("district_names muss genau 3 Einträge enthalten.")

    csv_dir = Path(csv_dir)
    if not csv_dir.exists():
        raise FileNotFoundError(f"CSV-Verzeichnis nicht gefunden: {csv_dir}")

    # 1) Laden
    merged = {}
    for d in district_names:
        csv_path = csv_dir / f"{d}_demand_heat_timeseries.csv"
        dct = load_heat_demand_csv(d, csv_path)
        merged[d] = dct[d]

    # Ermitteln aller Cluster (aus allen Districts für das analysierte Jahr)
    all_clusters = set()
    for d in district_names:
        if analyzed_year in merged[d]:
            all_clusters.update(merged[d][analyzed_year].keys())
    if not all_clusters:
        raise ValueError(f"Für Jahr {analyzed_year} wurden in den drei Dateien keine Daten gefunden.")

    clusters_sorted = sorted(all_clusters)
    n = len(clusters_sorted)

    fig, axes = plt.subplots(nrows=n, ncols=1, figsize=(14, max(3 * n, 4)), sharex=False)
    if n == 1:
        axes = [axes]

    # Für Rückgabe der Summen
    summed = defaultdict(lambda: defaultdict(float))  # summed[cluster][ts]

    for i, cluster in enumerate(clusters_sorted):
        # alle Timesteps für diesen Cluster aus allen Districts sammeln
        cluster_ts_set = set()
        for d in district_names:
            ts_map = merged[d].get(analyzed_year, {}).get(cluster, {})
            cluster_ts_set.update(ts_map.keys())
        if not cluster_ts_set:
            continue
        sorted_timesteps = sorted(cluster_ts_set)

        ax = axes[i]
        # pro District plotten
        for d in district_names:
            y = [merged[d].get(analyzed_year, {}).get(cluster, {}).get(ts, 0.0) for ts in sorted_timesteps]
            ax.plot(sorted_timesteps, y, linewidth=1.2, label=d)

        # Summenlinie berechnen und zeichnen
        summed_y = []
        for ts in sorted_timesteps:
            s = sum(merged[d].get(analyzed_year, {}).get(cluster, {}).get(ts, 0.0) for d in district_names)
            summed[cluster][ts] = s
            summed_y.append(s)
        ax.plot(sorted_timesteps, summed_y, color="k", linewidth=2.0, linestyle="--", label="Summe")

        ax.set_title(f"Cluster {cluster}")
        ax.set_ylabel("Wärmeverbrauch in kW")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize="small")

    axes[-1].set_xlabel("Timestep")
    #fig.suptitle(f"Heat_Demand_kW je District und Summe ({', '.join(district_names)}) - Jahr {analyzed_year}", y=1.02)
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
) -> Dict[int, Dict[int, float]]:
    """
    district_names: Liste mit genau 3 District-Namen.
    analyzed_year: zu analysierendes Support_Year.
    csv_dir: Verzeichnis, in dem die CSV-Dateien liegen. Dateinamen:
             {district_name}_demand_power_timeseries.csv
    save_path: Zielpfad für die Abbildung.

    Rückgabe:
    summed[cluster][ts] = Summe(Power_Demand_kW) über alle 3 Districts.
    """
    if len(district_names) != 3:
        raise ValueError("district_names muss genau 3 Einträge enthalten.")

    csv_dir = Path(csv_dir)
    if not csv_dir.exists():
        raise FileNotFoundError(f"CSV-Verzeichnis nicht gefunden: {csv_dir}")

    # 1) Laden
    merged = {}
    for d in district_names:
        csv_path = csv_dir / f"{d}_demand_power_timeseries.csv"
        dct = load_power_demand_csv(d, csv_path)
        merged[d] = dct[d]

    # Ermitteln aller Cluster (aus allen Districts für das analysierte Jahr)
    all_clusters = set()
    for d in district_names:
        if analyzed_year in merged[d]:
            all_clusters.update(merged[d][analyzed_year].keys())
    if not all_clusters:
        raise ValueError(f"Für Jahr {analyzed_year} wurden in den drei Dateien keine Daten gefunden.")

    clusters_sorted = sorted(all_clusters)
    n = len(clusters_sorted)

    fig, axes = plt.subplots(nrows=n, ncols=1, figsize=(14, max(3 * n, 4)), sharex=False)
    if n == 1:
        axes = [axes]

    # Für Rückgabe der Summen
    summed = defaultdict(lambda: defaultdict(float))  # summed[cluster][ts]

    for i, cluster in enumerate(clusters_sorted):
        # alle Timesteps für diesen Cluster aus allen Districts sammeln
        cluster_ts_set = set()
        for d in district_names:
            ts_map = merged[d].get(analyzed_year, {}).get(cluster, {})
            cluster_ts_set.update(ts_map.keys())
        if not cluster_ts_set:
            continue
        sorted_timesteps = sorted(cluster_ts_set)

        ax = axes[i]
        # pro District plotten
        for d in district_names:
            y = [merged[d].get(analyzed_year, {}).get(cluster, {}).get(ts, 0.0) for ts in sorted_timesteps]
            ax.plot(sorted_timesteps, y, linewidth=1.2, label=d)

        # Summenlinie berechnen und zeichnen
        summed_y = []
        for ts in sorted_timesteps:
            s = sum(merged[d].get(analyzed_year, {}).get(cluster, {}).get(ts, 0.0) for d in district_names)
            summed[cluster][ts] = s
            summed_y.append(s)
        ax.plot(sorted_timesteps, summed_y, color="k", linewidth=2.0, linestyle="--", label="Summe")

        ax.set_title(f"Cluster {cluster}")
        ax.set_ylabel("Strombedarf in kW")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize="small")

    axes[-1].set_xlabel("Timestep")
    #fig.suptitle(f"Power_Demand_kW je District und Summe ({', '.join(district_names)}) - Jahr {analyzed_year}", y=1.02)
    fig.tight_layout()

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    return {c: dict(ts_map) for c, ts_map in summed.items()}


if __name__ == "__main__":
    # Beispielaufrufe
    #district_names = ["mixed1", "residential2", "ghd6"]
    #district_names = ["residential0", "residential2", "residential3"]
    district_names = ["residential0", "residential2", "mixed1"]
    #scenario = "Basis"
    #scenario = "Wohn"
    scenario = "Wohnmisch"
    analyzed_year = 10
    csv_dir = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results"

    # Heat Demand Plot
    save_path_heat = f"D:\\cwu-tja\\districtgenerator\\Main-tja\\optimization_results\\plots\\summed_heat_demand_{scenario}.pdf"
    plot_summed_heat_demand_three_districts(
        district_names=district_names,
        analyzed_year=analyzed_year,
        csv_dir=csv_dir,
        save_path=save_path_heat,
    )

    # Power Demand Plot
    save_path_power = f"D:\\cwu-tja\\districtgenerator\\Main-tja\\optimization_results\\plots\\summed_power_demand_{scenario}.pdf"
    plot_summed_power_demand_three_districts(
        district_names=district_names,
        analyzed_year=analyzed_year,
        csv_dir=csv_dir,
        save_path=save_path_power,
    )

