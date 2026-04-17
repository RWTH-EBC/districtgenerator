import os
import csv
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple


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
    # gleiche Idee wie in plot_results.py: base_dir für Input, result_dir für Output
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

    series = {
        "support_year": [],
        "cluster": [],
        "timestep": [],
        "stromproduktion_kw": [],
        "strombedarf_kw": [],
        "strombezug_kw": [],
        "stromeinspeisung_kw": [],
    }

    grouped = defaultdict(list)

    for r in rows:
        y = _to_int(r.get("Support_Year"))
        d = _to_int(r.get("Cluster"))
        t = _to_int(r.get("Timestep"))

        prod = sum(_parse_value(r.get(dev)) for dev in production_devices if dev in available_columns)
        dem = sum(_parse_value(r.get(dev)) for dev in demand_devices if dev in available_columns)
        imp = _parse_value(r.get(import_column)) if import_column in available_columns else 0.0
        exp = _parse_value(r.get(export_column)) if export_column in available_columns else 0.0

        series["support_year"].append(y)
        series["cluster"].append(d)
        series["timestep"].append(t)
        series["stromproduktion_kw"].append(prod)
        series["strombedarf_kw"].append(dem)
        series["strombezug_kw"].append(imp)
        series["stromeinspeisung_kw"].append(exp)

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
        "series": series,
        "grouped_series": dict(grouped),
    }


def save_power_timeseries_summary_csv(
    data: Dict[str, Any],
    scenario_name: Optional[str] = None,
    result_dir: Optional[str] = None,
) -> str:
    """Speichert eine aggregierte CSV in result_dir."""
    if scenario_name is None:
        scenario_name = data.get("scenario_name", "scenario")

    if result_dir is None:
        result_dir = data.get("result_dir") or data.get("base_dir") or os.getcwd()
    os.makedirs(result_dir, exist_ok=True)

    out_path = os.path.join(result_dir, f"{scenario_name}_power_timeseries_summary.csv")

    s = data["series"]
    with open(out_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            [
                "Support_Year",
                "Cluster",
                "Timestep",
                "Stromproduktion_kW",
                "Strombedarf_kW",
                "Strombezug_kW",
                "Stromeinspeisung_kW",
            ]
        )
        for i in range(len(s["timestep"])):
            writer.writerow(
                [
                    s["support_year"][i],
                    s["cluster"][i],
                    s["timestep"][i],
                    round(s["stromproduktion_kw"][i], 3),
                    round(s["strombedarf_kw"][i], 3),
                    round(s["strombezug_kw"][i], 3),
                    round(s["stromeinspeisung_kw"][i], 3),
                ]
            )

    return out_path


if __name__ == "__main__":

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    base_dir = os.path.join(project_root, "Main-tja", "optimization_results")
    # Beispielaufruf:
    data = load_power_timeseries_from_csv("mixed1", base_dir=base_dir)
    out = save_power_timeseries_summary_csv(data)
    print(out)
    pass