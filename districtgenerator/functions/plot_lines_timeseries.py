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
) -> Dict[str, Any]:
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

        prod = sum(_parse_value(r.get(dev)) for dev in production_devices if dev in available_columns)
        dem = sum(_parse_value(r.get(dev)) for dev in demand_devices if dev in available_columns)
        imp = _parse_value(r.get(import_column)) if import_column in available_columns else 0.0
        exp = _parse_value(r.get(export_column)) if export_column in available_columns else 0.0

        grouped[(y, d)].append(
            {
                "timestep": t,
                "stromproduktion_kw": prod,
                "strombedarf_kw": dem,
                "strombezug_kw": imp,
                "stromeinspeisung_kw": exp,
            }
        )

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

        ax.set_title(f"Jahr {support_year+2025} - Cluster {cluster}")
        ax.set_ylabel("kW")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right")

    axes[-1][0].set_xlabel("Timestep")

    fig.suptitle(
        titel or f"Power Timeseries - {scenario_name} - Jahr {support_year+2025}",
        y=0.995,
    )
    fig.tight_layout()

    out_path = os.path.join(
        result_dir,
        f"{scenario_name}_power_timeseries_year_{support_year+2025}_clusters_{num_clusters}.pdf",
    )
    fig.savefig(out_path, dpi=300, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return out_path


if __name__ == "__main__":
    scenario_name = "mixed1"
    base_dir = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results"
    result_dir = r"D:\cwu-tja\districtgenerator\plots"
    cluster=4
    year=10
    year_header= year+2025

    out = plot_power_timeseries_by_year_and_clusters(
        scenario_name=scenario_name,
        support_year=year,
        num_clusters=cluster,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
    )
    print(out)