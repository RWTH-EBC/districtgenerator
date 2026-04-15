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


def plot_device_capacities_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    show_percent_box=False,
    plot_tes_only=False,  
):
    """
    Plot capacities side-by-side for:
    - <scenario>_network_results.csv  -> "Verbund"
    - <scenario>_results.csv          -> "Einzeln"

    Returns
    -------
    dict
        {scenario: {"network": {device: cap}, "single": {device: cap}}}
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _to_set(x):
        if x is None:
            return None
        if isinstance(x, str):
            return {x}
        return set(x)

    def _read_caps(csv_path):
        caps = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") == "device" and row.get("metric") == "capacity":
                    dev = (row.get("device") or "").strip()
                    try:
                        val = float(row.get("value"))
                    except (TypeError, ValueError):
                        continue
                    if dev:
                        caps[dev] = val
        return caps

    def _fmt_pct(p):
        # integernah -> ohne Nachkommastelle, sonst 1 Nachkommastelle (mit deutschem Komma)
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    include_set = _to_set(include_devices)
    exclude_set = _to_set(exclude_devices) or set()

    if scenario_name is None:
        scenario_names = []
        for fn in os.listdir(base_dir):
            if fn.endswith("_network_results.csv"):
                sc = fn.replace("_network_results.csv", "")
                single_candidate = os.path.join(base_dir, f"{sc}_results.csv")
                if os.path.isfile(single_candidate):
                    scenario_names.append(sc)
        scenario_names = sorted(set(scenario_names))
    else:
        scenario_names = [scenario_name] if isinstance(scenario_name, str) else list(scenario_name)

    if not scenario_names:
        raise FileNotFoundError("No scenario pairs found (*_network_results.csv + *_results.csv).")

    preferred_order = [
        "HP", "CHP", "TES", "PV", "STC", "WT", "EB", "BOI", "BBOI", "GHP", "CC", "AC",
        "WAT", "BCHP", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "CTES", "BAT", "GS"
    ]

    label_map = {
        "HP": "Wärmepumpe",
        "CHP": "BHKW",
        "BCHP": "BBHKW",
        "TES": "therm. Speicher",
        "STC": "Solarthermie",
        "WT": "Windkraft",
        "EB": "Elektrischer\nBoiler",
        "BOI": "Erdgaskessel",
    }

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    out = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")

        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            print(f"Skip '{sc}': pair not complete.")
            continue

        caps_network = _read_caps(network_path)
        caps_single = _read_caps(single_path)

        all_devices = set(caps_network.keys()) | set(caps_single.keys())

        if include_set is not None:
            selected = [d for d in preferred_order if d in include_set and d in all_devices]
            selected += sorted([d for d in include_set if d in all_devices and d not in preferred_order])
        else:
            selected = [d for d in preferred_order if d in all_devices]
            selected += sorted([d for d in all_devices if d not in preferred_order])

        devices = [d for d in selected if d not in exclude_set]
        if not devices:
            print(f"Skip '{sc}': no devices left after filtering.")
            continue

        x = np.arange(len(devices))
        width = 0.32

        y_network = [caps_network.get(d, 0.0) for d in devices]
        y_single = [caps_single.get(d, 0.0) for d in devices]
        xtick_labels = [label_map.get(d, d) for d in devices]

        plt.figure(figsize=(8, 4))
        plt.bar(x - width/2, y_network, width=width, color="#D40000", label="Verbund")
        plt.bar(x + width/2, y_single, width=width, color="#55585C", label="Einzeln")

        ymax = max(max(y_network) if y_network else 0, max(y_single) if y_single else 0, 1.0)
        if show_percent_box:
            plt.ylim(0, ymax * 1.35)
            y_offset = ymax * 0.08

            for i, (yn, ys) in enumerate(zip(y_network, y_single)):
                if ys == 0:
                    text = "n/a" if yn == 0 else "+∞"
                else:
                    pct = (yn - ys) / ys * 100.0
                    text = _fmt_pct(pct)

                plt.text(
                    x[i] - width/2,
                    yn + y_offset,
                    text,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=16,
                    bbox=dict(
                        boxstyle="square,pad=0.45",
                        facecolor="#D40000",
                        edgecolor="#D40000",
                        linewidth=1.5,
                    ),
                    zorder=5,
                )

        plt.xticks(x, xtick_labels, fontsize=14)
        if plot_tes_only:
            plt.ylabel("Speicherkapazität in kWh", fontsize=14)
            plt.title(titel or f"Speicherauslegung im Szenario '{sc}'", fontsize=16)
        else:
            plt.ylabel("Anlagenleistung in kW", fontsize=14)
        plt.xlabel("")
        plt.title(titel or f"Anlagenleistungen im Szenario '{sc}'", fontsize=16)
        plt.grid(axis="y", alpha=0.4)
        plt.legend()
        plt.tight_layout()

        plot_path = os.path.join(plots_dir, titel + ".png") if titel else os.path.join(plots_dir, f"device_capacities_compare_{sc}.png")
        plt.savefig(plot_path, dpi=150)
        print(f"Plot saved: {plot_path}")

        if show:
            plt.show()
        else:
            plt.close()

        out[sc] = {"network": caps_network, "single": caps_single}

    if not out:
        print("No paired plots created.")
    return out

def plot_heat_generation_by_year_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
):
    """
    Plot stacked heat generation by year (VB vs EZ) from:
    - <scenario>_network_results.csv  -> VB
    - <scenario>_results.csv          -> EZ

    Uses:
    - category == 'heat_by_year'
    - metric   == 'heat_gen'
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_heat_by_year(csv_path):
        by_year = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "heat_profile_energy_by_year" or row.get("metric") != "heat_profile_energy_kwh":
                    continue
                dev = (row.get("device") or "").strip()
                year_raw = row.get("year")
                try:
                    year = int(float(year_raw))
                    val = float(row.get("value"))
                except (TypeError, ValueError):
                    continue
                if not dev:
                    continue
                by_year.setdefault(year, {})[dev] = val
        return by_year

    if scenario_name is None:
        scenario_names = []
        for fn in os.listdir(base_dir):
            if fn.endswith("_network_results.csv"):
                sc = fn.replace("_network_results.csv", "")
                if os.path.isfile(os.path.join(base_dir, f"{sc}_results.csv")):
                    scenario_names.append(sc)
        scenario_names = sorted(set(scenario_names))
    else:
        scenario_names = [scenario_name] if isinstance(scenario_name, str) else list(scenario_name)

    if not scenario_names:
        raise FileNotFoundError("No scenario pairs found (*_network_results.csv + *_results.csv).")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    label_map = {
        "STC": "Solarthermie",
        "HP": "Wärmepumpe",
        "BCHP": "BBHKW",
        "CHP": "BHKW",
        "TES": "therm. Speicher",
        "EB": "Elektrischer Boiler",
        "BOI": "Erdgaskessel",
    }

    fixed_colors = {
        "STC": "#E43D30",  # rot
        "HP": "#9FA1A4",   # grau
        "BCHP": "#2F3133", # dunkelgrau/schwarz
    }

    out = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")

        if not (os.path.isfile(network_path) and os.path.isfile(single_path)):
            print(f"Skip '{sc}': pair not complete.")
            continue

        heat_network = _read_heat_by_year(network_path)  # {year: {device: value}}
        heat_single = _read_heat_by_year(single_path)

        years = sorted(set(heat_network.keys()) | set(heat_single.keys()))
        if not years:
            print(f"Skip '{sc}': no heat_by_year/heat_gen data found.")
            continue

        devices = sorted(
            set(d for y in years for d in heat_network.get(y, {}).keys()) |
            set(d for y in years for d in heat_single.get(y, {}).keys())
        )

        # Nur Geräte behalten, die wirklich genutzt werden (mind. ein Wert != 0)
        used_devices = []
        for dev in devices:
            total = 0.0
            for y in years:
                total += float(heat_network.get(y, {}).get(dev, 0.0) or 0.0)
                total += float(heat_single.get(y, {}).get(dev, 0.0) or 0.0)
            if abs(total) > 1e-9:
                used_devices.append(dev)

        if not used_devices:
            print(f"Skip '{sc}': all heat_gen values are 0.")
            continue

        # x-Achse: pro Jahr 2 Balken (VB, EZ)
        x = np.arange(len(years) * 2)
        xticklabels = []
        for y in years:
            xticklabels.append(f"{base_calendar_year + y}\nVB")
            xticklabels.append(f"{base_calendar_year + y}\nEZ")

        plt.figure(figsize=(8, 4))
        bottoms = np.zeros(len(x), dtype=float)

        # Fallback-Farben für weitere Devices
        cmap = plt.get_cmap("tab20")
        color_i = 0

        for dev in used_devices:
            vals = []
            for y in years:
                # kWh -> MWh
                vals.append((heat_network.get(y, {}).get(dev, 0.0) or 0.0) / 1000.0)
                vals.append((heat_single.get(y, {}).get(dev, 0.0) or 0.0) / 1000.0)

            if dev in fixed_colors:
                color = fixed_colors[dev]
            else:
                color = cmap(color_i % 20)
                color_i += 1

            plt.bar(
                x,
                vals,
                bottom=bottoms,
                width=0.82,
                color=color,
                label=label_map.get(dev, dev),
            )
            bottoms += np.array(vals, dtype=float)

        plt.xticks(x, xticklabels)
        plt.ylabel("Wärmeerzeugung in MWh")
        plt.xlabel("")
        plt.title(titel or sc, pad=12)
        plt.grid(axis="y", alpha=0.4)

        # Keine 10er-Potenz-Darstellung auf der y-Achse
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)

        # Legende oberhalb der Balken (außerhalb der Achse)
        plt.legend(
            ncol=min(4, len(used_devices)),
            loc="upper center",
            bbox_to_anchor=(0.5, -0.16),
            frameon=False,
            handlelength=1.0,
            handletextpad=0.4,
            columnspacing=1.2,
        )

        # Oben Platz für Legende + Titel lassen
        plt.tight_layout(rect=[0, 0.08, 1, 1])

        plot_path = os.path.join(plots_dir, f"heat_generation_by_year_compare_{sc}.png")
        plt.savefig(plot_path, dpi=150)
        print(f"Plot saved: {plot_path}")

        if show:
            plt.show()
        else:
            plt.close()

        out[sc] = {"network": heat_network, "single": heat_single}

    if not out:
        print("No plots created.")
    return out


def plot_power_import_by_year_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
):
    """
    Plot yearly electricity import (MWh) as paired bars (Verbund vs Einzeln).

    Metrics (category='yearly_totals'):
    - from_el_main_grid_total  -> Strombezug aus dem Hauptnetz
    - from_network_total       -> Strombezug aus dem Verbundnetz
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_yearly_import(csv_path):
        out = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "yearly_totals":
                    continue
                metric = row.get("metric")
                if metric not in ("from_el_main_grid_total", "from_network_total"):
                    continue
                try:
                    y = int(float(row.get("year")))
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue
                out.setdefault(y, {"from_el_main_grid_total": 0.0, "from_network_total": 0.0})
                out[y][metric] = v
        return out

    if scenario_name is None:
        scenario_names = []
        for fn in os.listdir(base_dir):
            if fn.endswith("_network_results.csv"):
                sc = fn.replace("_network_results.csv", "")
                if os.path.isfile(os.path.join(base_dir, f"{sc}_results.csv")):
                    scenario_names.append(sc)
        scenario_names = sorted(set(scenario_names))
    else:
        scenario_names = [scenario_name] if isinstance(scenario_name, str) else list(scenario_name)

    if not scenario_names:
        raise FileNotFoundError("No scenario pairs found (*_network_results.csv + *_results.csv).")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    out = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")
        if not (os.path.isfile(network_path) and os.path.isfile(single_path)):
            print(f"Skip '{sc}': pair not complete.")
            continue

        vb = _read_yearly_import(network_path)
        ez = _read_yearly_import(single_path)

        years = sorted(set(vb.keys()) | set(ez.keys()))
        if not years:
            print(f"Skip '{sc}': no yearly_totals import data found.")
            continue

        x = np.arange(len(years) * 2)
        labels = []
        vb_main, vb_net, ez_main, ez_net = [], [], [], []

        for y in years:
            cal_y = base_calendar_year + y
            labels.extend([f"{cal_y}\nVB", f"{cal_y}\nEZ"])

            vb_main.append(vb.get(y, {}).get("from_el_main_grid_total", 0.0))
            vb_net.append(vb.get(y, {}).get("from_network_total", 0.0))

            ez_main.append(ez.get(y, {}).get("from_el_main_grid_total", 0.0))
            ez_net.append(ez.get(y, {}).get("from_network_total", 0.0))

        vals_vb_main = np.array(vb_main, dtype=float)
        vals_vb_net = np.array(vb_net, dtype=float)
        vals_ez_main = np.array(ez_main, dtype=float)
        vals_ez_net = np.array(ez_net, dtype=float)

        # Interleave: [VB(y1), EZ(y1), VB(y2), EZ(y2), ...]
        y_main = np.empty(len(x), dtype=float)
        y_net = np.empty(len(x), dtype=float)
        y_main[0::2] = vals_vb_main
        y_main[1::2] = vals_ez_main
        y_net[0::2] = vals_vb_net
        y_net[1::2] = vals_ez_net

        plt.figure(figsize=(8, 5))
        width = 0.5

        # Hauptnetz-Balken
        colors_main = ["#E43D30" if i % 2 == 0 else "#B9BABC" for i in range(len(x))]
        plt.bar(x, y_main, width=width, color=colors_main)

        # Verbundnetz gestapelt
        colors_net = ["#8C1D17" if i % 2 == 0 else "#8A8B8D" for i in range(len(x))]
        plt.bar(x, y_net, width=width, bottom=y_main, color=colors_net)


        plt.xticks(x, labels)
        plt.ylabel("Energie in MWh")
        plt.title(titel or sc)
        plt.grid(axis="y", alpha=0.4)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)

        handles, legend_labels = [], []
        if np.any(vals_vb_main > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#E43D30"))
            legend_labels.append("Verbund Strombezug aus dem Hauptnetz")
        if np.any(vals_ez_main > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#B9BABC"))
            legend_labels.append("Einzeln Strombezug aus dem Hauptnetz")
        if np.any(vals_vb_net > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8C1D17"))
            legend_labels.append("Verbund Strombezug aus dem Verbundnetz")
        if np.any(vals_ez_net > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8A8B8D"))
            legend_labels.append("Einzeln Strombezug aus dem Verbundnetz")

        if handles:
            plt.legend(
                handles,
                legend_labels,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.14),
                ncol=2,
                frameon=False,
            )

        plt.tight_layout(rect=[0, 0.08, 1, 1])

        plot_path = os.path.join(plots_dir, titel + ".png")
        plt.savefig(plot_path, dpi=150)
        print(f"Plot saved: {plot_path}")

        if show:
            plt.show()
        else:
            plt.close()

        out[sc] = {"network": vb, "single": ez}

    if not out:
        print("No plots created.")
    return out


def plot_lcoe_by_year_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False, 
):
    """
    Plot yearly LCOE as paired bars (Verbund vs Einzeln).

    Uses rows with:
    - category == 'optimization'
    - metric   == 'LCOE_year'
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_lcoe_year(csv_path):
        out = {}  # {year: lcoe_value}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "LCOE_year":
                    continue

                year_raw = row.get("year")
                if year_raw in (None, ""):
                    continue

                try:
                    y = int(year_raw)
                except Exception:
                    continue

                v = _parse_value(row.get("value"))
                try:
                    out[y] = float(v)
                except Exception:
                    continue
        return out

    def _fmt_pct(p):  # NEU
        # integernah -> ohne Nachkommastelle, sonst 1 Nachkommastelle (mit deutschem Komma)
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    if scenario_name is None:
        scenario_names = []
        for fn in os.listdir(base_dir):
            if fn.endswith("_network_results.csv"):
                sc = fn[: -len("_network_results.csv")]
                if os.path.isfile(os.path.join(base_dir, f"{sc}_results.csv")):
                    scenario_names.append(sc)
        scenario_names = sorted(set(scenario_names))
    else:
        scenario_names = [scenario_name] if isinstance(scenario_name, str) else list(scenario_name)

    if not scenario_names:
        raise FileNotFoundError("No scenario pairs found (*_network_results.csv + *_results.csv).")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    out = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")
        if not (os.path.isfile(network_path) and os.path.isfile(single_path)):
            print(f"Skip '{sc}': pair not complete.")
            continue

        vb = _read_lcoe_year(network_path)  # Verbund
        ez = _read_lcoe_year(single_path)   # Einzeln

        years = sorted(set(vb.keys()) | set(ez.keys()))
        if not years:
            print(f"Skip '{sc}': no optimization/LCOE_year data found.")
            continue

        x = np.arange(len(years))
        width = 0.35

        y_vb = [vb.get(y, 0.0) for y in years]
        y_ez = [ez.get(y, 0.0) for y in years]

        labels = [str(base_calendar_year + y) for y in years]

        def _fmt_pct(p):  
            if abs(p - round(p)) < 0.05:
                s = f"{p:+.0f}%"
            else:
                s = f"{p:+.1f}%"
            return s.replace(".", ",")

        plt.figure(figsize=(8, 4))
        plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label="Verbund")
        plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label="Einzeln")

        if show_percent_box:  # NEU
            ymax = max(max(y_vb) if y_vb else 0, max(y_ez) if y_ez else 0, 1.0)
            plt.ylim(0, ymax * 1.35)
            y_offset = ymax * 0.08

            for i, (vb_val, ez_val) in enumerate(zip(y_vb, y_ez)):
                if ez_val == 0:
                    text = "n/a" if vb_val == 0 else "+∞"
                else:
                    text = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

                plt.text(
                    x[i] - width / 2,     # über Verbund-Balken
                    vb_val + y_offset,
                    text,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=12,
                    bbox=dict(
                        boxstyle="square,pad=0.35",
                        facecolor="#D40000",
                        edgecolor="#D40000",
                        linewidth=1.2,
                    ),
                    zorder=5,
                )

        plt.xticks(x, labels)
        plt.ylabel("Energiegestehungskosten in €/MWh")
        plt.xlabel("")
        plt.title(titel or f"Energiegestehungskosten im Szenario '{sc}'")
        plt.grid(axis="y", alpha=0.4)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)
        plt.legend()
        plt.tight_layout()

        plot_path = os.path.join(
            plots_dir,
            f"lcoe_by_year_compare_{sc}.png" if not titel else f"{titel}.png"
        )
        plt.savefig(plot_path, dpi=150)
        print(f"Plot saved: {plot_path}")

        if show:
            plt.show()
        else:
            plt.close()

        out[sc] = {"network": vb, "single": ez}

    if not out:
        print("No plots created.")
    return out


def plot_co2_by_year_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
):
    """
    Plot yearly CO2 emissions as paired bars (Verbund vs Einzeln).

    Uses rows with:
    - category == 'optimization'
    - metric   == 'co2_sum_distr_year'
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_co2_year(csv_path):
        out = {}  # {year: co2_value}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "co2_sum_distr_year":
                    continue

                year_raw = row.get("year")
                if year_raw in (None, ""):
                    continue

                try:
                    y = int(year_raw)
                except Exception:
                    continue

                v = _parse_value(row.get("value"))
                try:
                    out[y] = float(v)
                except Exception:
                    continue
        return out

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    if scenario_name is None:
        scenario_names = []
        for fn in os.listdir(base_dir):
            if fn.endswith("_network_results.csv"):
                sc = fn[: -len("_network_results.csv")]
                if os.path.isfile(os.path.join(base_dir, f"{sc}_results.csv")):
                    scenario_names.append(sc)
        scenario_names = sorted(set(scenario_names))
    else:
        scenario_names = [scenario_name] if isinstance(scenario_name, str) else list(scenario_name)

    if not scenario_names:
        raise FileNotFoundError("No scenario pairs found (*_network_results.csv + *_results.csv).")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    out = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")
        if not (os.path.isfile(network_path) and os.path.isfile(single_path)):
            print(f"Skip '{sc}': pair not complete.")
            continue

        vb = _read_co2_year(network_path)  # Verbund
        ez = _read_co2_year(single_path)   # Einzeln

        years = sorted(set(vb.keys()) | set(ez.keys()))
        if not years:
            print(f"Skip '{sc}': no optimization/co2_sum_distr_year data found.")
            continue

        x = np.arange(len(years))
        width = 0.35

        y_vb = [vb.get(y, 0.0) for y in years]
        y_ez = [ez.get(y, 0.0) for y in years]
        labels = [str(base_calendar_year + y) for y in years]

        plt.figure(figsize=(8, 4))
        plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label="Verbund")
        plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label="Einzeln")

        if show_percent_box:
            ymax = max(max(y_vb) if y_vb else 0, max(y_ez) if y_ez else 0, 1.0)
            plt.ylim(0, ymax * 1.35)
            y_offset = ymax * 0.08

            for i, (vb_val, ez_val) in enumerate(zip(y_vb, y_ez)):
                if ez_val == 0:
                    text = "n/a" if vb_val == 0 else "+∞"
                else:
                    # Prozentuale Abweichung des hell-roten Balkens relativ zum grauen Balken
                    text = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

                plt.text(
                    x[i] - width / 2,
                    vb_val + y_offset,
                    text,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=12,
                    bbox=dict(
                        boxstyle="square,pad=0.35",
                        facecolor="#D40000",
                        edgecolor="#D40000",
                        linewidth=1.2,
                    ),
                    zorder=5,
                )

        plt.xticks(x, labels)
        plt.ylabel("CO₂-Emissionen in t/a")
        plt.xlabel("")
        plt.title(titel or f"CO₂-Emissionen im Szenario '{sc}'")
        plt.grid(axis="y", alpha=0.4)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)
        plt.legend()
        plt.tight_layout()

        plot_name = f"co2_by_year_compare_{sc}.png" if not titel else f"{titel}.png"
        plot_path = os.path.join(plots_dir, plot_name)
        plt.savefig(plot_path, dpi=150)
        print(f"Plot saved: {plot_path}")

        if show:
            plt.show()
        else:
            plt.close()

        out[sc] = {"network": vb, "single": ez}

    if not out:
        print("No plots created.")
    return out


def plot_tac_sum_from_three_scenarios(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    show_percent_box=False,
):
    """
    Plot TAC-Summe (3 Quartiere) für Verbund vs. Einzeloptimierung.

    Erwartet:
    - scenario_names: Liste/Tuple mit genau 3 Szenario-Namen
    - Dateien je Szenario:
      - <scenario>_network_results.csv  (Verbund)
      - <scenario>_results.csv          (Einzeln)

    CSV-Filter:
    - category == "optimization"
    - metric   == "tac_distr"
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_tac(csv_path):
        tac_sum = 0.0
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "tac_distr":
                    continue
                v = _parse_value(row.get("value"))
                try:
                    tac_sum += float(v)
                except Exception:
                    continue
        return tac_sum

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    total_vb = 0.0
    total_ez = 0.0
    details = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")

        if not os.path.isfile(network_path):
            raise FileNotFoundError(f"Missing file: {network_path}")
        if not os.path.isfile(single_path):
            raise FileNotFoundError(f"Missing file: {single_path}")

        vb = _read_tac(network_path)
        ez = _read_tac(single_path)

        total_vb += vb
        total_ez += ez
        details[sc] = {"network": vb, "single": ez}

    x = np.arange(2)
    y = [total_vb, total_ez]
    labels = ["Verbund", "Einzeln"]
    colors = ["#D40000", "#55585C"]

    plt.figure(figsize=(7, 4.5))
    bars = plt.bar(x, y, color=colors, width=0.55)

    if show_percent_box:
        ymax = max(max(y), 1.0)
        plt.ylim(0, ymax * 1.30)
        y_offset = ymax * 0.06

        if total_ez == 0:
            text = "n/a" if total_vb == 0 else "+∞"
        else:
            text = _fmt_pct((total_vb - total_ez) / total_ez * 100.0)

        plt.text(
            bars[0].get_x() + bars[0].get_width() / 2,
            total_vb + y_offset,
            text,
            ha="center",
            va="bottom",
            color="white",
            fontsize=12,
            bbox=dict(
                boxstyle="square,pad=0.35",
                facecolor="#D40000",
                edgecolor="#D40000",
                linewidth=1.2,
            ),
            zorder=5,
        )

    plt.xticks(x, labels)
    plt.ylabel("TAC-Summe [€]")
    plt.title(titel or "TAC-Summe der drei Quartiere: Verbund vs. Einzeloptimierung")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.tight_layout()

    plot_name = "tac_sum_three_quarters.png" if not titel else f"{titel}.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario_names": list(scenario_names),
        "network_sum": total_vb,
        "single_sum": total_ez,
        "details": details,
        "plot_path": plot_path,
    }






if __name__ == "__main__":
    plot_tac_sum_from_three_scenarios(scenario_names=["1rural", "6urban", "4zb"],show=True,show_percent_box=True,titel="TAC Summe 3 Quartiere",
)
    # plot_device_capacities_from_csv(scenario_name="rural", show=True, exclude_devices = ["TES", "STC"], show_percent_box=True, titel="Vergleich der Anlagen-Leistungen im ländlichen Quartier")
    # plot_device_capacities_from_csv(scenario_name="urban", show=True, exclude_devices = ["TES", "STC"], show_percent_box=True, titel="Vergleich der Anlagen-Leistungen im städtischen Quartier")

    # plot_device_capacities_from_csv(scenario_name="rural", show=True, exclude_devices = ["PV", "HP", "BCHP", "BBOI"], show_percent_box=True, titel="Vergleich der Speicherauslegung im ländlichen Quartier", plot_tes_only=True)
    # plot_device_capacities_from_csv(scenario_name="urban", show=True, exclude_devices = ["PV", "HP", "BCHP", "BBOI"], show_percent_box=True, titel="Vergleich der Speicherauslegung im städtischen Quartier", plot_tes_only=True)
    
    # plot_heat_generation_by_year_from_csv("rural", titel="Wärmeproduktion im ländlichen Quartier", show=True)
    # plot_heat_generation_by_year_from_csv("urban", titel="Wärmeproduktion im städtischen Quartier", show=True)
    
    # plot_power_import_by_year_from_csv("1rural", titel="Strombezug im ländlichen Quartier", show=True, show_percent_box=True)
    # plot_power_import_by_year_from_csv("urban", titel="Strombezug im städtischen Quartier", show=True, show_percent_box=True)
    # plot_power_import_by_year_from_csv("4zb", titel="Strombezug im Quartier Zeilenbebauung", show=True, show_percent_box=True)
    
    # plot_lcoe_by_year_from_csv("rural", titel="Energiegestehungskosten im ländlichen Quartier", show=True, show_percent_box=True)
    # plot_lcoe_by_year_from_csv("urban", titel="Energiegestehungskosten im städtischen Quartier", show=True, show_percent_box=True)
    
    # plot_co2_by_year_from_csv("rural",titel="CO₂-Emissionen im ländlichen Quartier",show=True,show_percent_box=True)
    # plot_co2_by_year_from_csv("urban",titel="CO₂-Emissionen im städtischen Quartier",show=True,show_percent_box=True)