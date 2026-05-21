from matplotlib import gridspec
import matplotlib.pyplot as plt
import os
import numpy as np
import csv
import argparse
from pathlib import Path
import pandas as pd
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
    show=False,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    show_percent_box=False,
    plot_tes_only=False,
    compare_item1=None,  
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot capacities side-by-side for:
    - <scenario>_network_results.csv  -> "compare_item1"
    - <scenario>_results.csv          -> "compare_item2"

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
                single_candidate = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
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
        "EB": "Elektrischer\nKessel",
        "BOI": "Erdgas-\nkessel",
        "BBOI": "Biomasse-\nkessel",
    }

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    out = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

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
        plt.bar(x - width/2, y_network, width=width, color="#D40000", label=compare_item1 or "compare_item1")
        plt.bar(x + width/2, y_single, width=width, color="#55585C", label=compare_item2 or "Mit Verbundpreis")

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
    show=False,
    titel=None,
    base_calendar_year=2025,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot stacked heat generation by year (oVP vs VP) from:
    - <scenario>_network_results.csv  -> compare_short1
    - <scenario>_results.csv          -> compare_short2

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
            if fn.endswith(f"_{compare_short1}_results.csv"):
                sc = fn.replace(f"_{compare_short1}_results.csv", "")
                if os.path.isfile(os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")):
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
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

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

        # x-Achse: pro Jahr 2 Balken (compare_short1, compare_short2)
        x = np.arange(len(years) * 2)
        xticklabels = []
        for y in years:
            xticklabels.append(f"{base_calendar_year + y}\n{compare_short1 or 'oVP'}")
            xticklabels.append(f"{base_calendar_year + y}\n{compare_short2 or 'VP'}")

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
    show=False,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot yearly electricity import (MWh) as paired bars (Verbund vs compare_item2).

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
            if fn.endswith(f"_{compare_short1}_results.csv"):
                sc = fn.replace(f"_{compare_short1}_results.csv", "")
                if os.path.isfile(os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")):
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
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")
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
            labels.extend([f"{cal_y}\n{compare_short1 or 'oVP'}", f"{cal_y}\n{compare_short2 or 'VP'}"])

            vb_main.append(vb.get(y, {}).get("from_el_main_grid_total", 0.0))
            vb_net.append(vb.get(y, {}).get("from_network_total", 0.0))

            ez_main.append(ez.get(y, {}).get("from_el_main_grid_total", 0.0))
            ez_net.append(ez.get(y, {}).get("from_network_total", 0.0))

        vals_vb_main = np.array(vb_main, dtype=float)
        vals_vb_net = np.array(vb_net, dtype=float)
        vals_ez_main = np.array(ez_main, dtype=float)
        vals_ez_net = np.array(ez_net, dtype=float)

        # Interleave: [compare_short1(y1), compare_short2(y1), compare_short1(y2), compare_short2(y2), ...]
        y_main = np.empty(len(x), dtype=float)
        y_net = np.empty(len(x), dtype=float)
        y_main[0::2] = vals_vb_main
        y_main[1::2] = vals_ez_main
        y_net[0::2] = vals_vb_net
        y_net[1::2] = vals_ez_net

        plt.figure(figsize=(8, 4))
        width = 0.5

        # Hauptnetz-Balken
        colors_main = ["#E43D30" if i % 2 == 0 else "#B9BABC" for i in range(len(x))]
        plt.bar(x, y_main, width=width, color=colors_main)

        # Verbundnetz gestapelt
        colors_net = ["#8C1D17" if i % 2 == 0 else "#8A8B8D" for i in range(len(x))]
        plt.bar(x, y_net, width=width, bottom=y_main, color=colors_net)


        if show_percent_box:
            # Genug Platz oberhalb der Balken für Linie + Box
            y_total = y_main + y_net
            ymax = max(float(np.max(y_total)) if len(y_total) else 0.0, 1.0)
            plt.ylim(0, ymax * 1.30)
            def _draw_pct_box(x_pos, main_val, net_val):
                total = main_val + net_val
                if total <= 0:
                    return

                pct_net = (net_val / total) * 100.0
                if pct_net <= 0:
                    return

                pct_txt = f"{pct_net:.0f}%".replace(".", ",")

                # Linie vom Balkenende nach oben
                line_y0 = total
                line_y1 = total + 0.05 * ymax

                # Box oberhalb der Linie
                box_y = line_y1 + 0.015 * ymax

                plt.plot(
                    [x_pos, x_pos],
                    [line_y0, line_y1],
                    color="#7A7A7A",
                    linewidth=1.0,
                    zorder=6,
                    clip_on=False,
                )


                plt.text(
                    x_pos,
                    box_y,
                    pct_txt,
                    ha="center",
                    va="bottom",
                    color="black",
                    fontsize=9,
                    fontweight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        facecolor="#FFFFFF",
                        edgecolor="#B9BABC",
                        linewidth=1.0,
                    ),
                    zorder=7,
                    clip_on=False,
                )

            for i in range(len(years)):
                # linker Balken: compare_short1
                _draw_pct_box(x[2 * i], vals_vb_main[i], vals_vb_net[i])
                # rechter Balken: compare_short2
                _draw_pct_box(x[2 * i + 1], vals_ez_main[i], vals_ez_net[i])


        plt.xticks(x, labels)
        plt.ylabel("Energie in MWh")
        plt.title(titel or sc)
        plt.grid(axis="y", alpha=0.4)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)

        handles, legend_labels = [], []
        if np.any(vals_vb_main > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#E43D30"))
            legend_labels.append(f"{compare_item1 or 'Ohne Verbundpreis'} Strombezug aus dem Hauptnetz")
        if np.any(vals_ez_main > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#B9BABC"))
            legend_labels.append(f"{compare_item2 or 'Mit Verbundpreis'} Strombezug aus dem Hauptnetz")
        if np.any(vals_vb_net > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8C1D17"))
            legend_labels.append(f"{compare_item1 or 'Ohne Verbundpreis'} Strombezug aus dem Verbundnetz")
        if np.any(vals_ez_net > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8A8B8D"))
            legend_labels.append(f"{compare_item2 or 'Mit Verbundpreis'} Strombezug aus dem Verbundnetz")

        if handles:
            plt.legend(
                handles,
                legend_labels,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.16),
                ncol=2,
                frameon=False,
            )

        plt.tight_layout(rect=[0, 0.02, 1, 1])

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

def plot_power_export_by_year_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_short1=None,
    compare_short2=None,
    fontsize=None,
):
    """
    Plot yearly electricity import (MWh) as paired bars (Verbund vs Mit Verbundpreis).

    Metrics (category='yearly_totals'):
    - to_el_main_grid_total  -> Stromeinspeisung in das Hauptnetz
    - to_network_total       -> Stromeinspeisung in das Verbundnetz
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
                if metric not in ("to_el_main_grid_total", "to_network_total"):
                    continue
                try:
                    y = int(float(row.get("year")))
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue
                out.setdefault(y, {"to_el_main_grid_total": 0.0, "to_network_total": 0.0})
                out[y][metric] = v
        return out

    if scenario_name is None:
        scenario_names = []
        for fn in os.listdir(base_dir):
            if fn.endswith(f"_{compare_short1}_results.csv"):
                sc = fn.replace(f"_{compare_short1}_results.csv", "")
                if os.path.isfile(os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")):
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
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")
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
            #labels.extend([f"{cal_y}\n{compare_short1 or 'oV'}", f"{cal_y}\n{compare_short2 or 'VP'}"])
            labels.extend([f"{cal_y}", f"{cal_y}"])

            vb_main.append(vb.get(y, {}).get("to_el_main_grid_total", 0.0))
            vb_net.append(vb.get(y, {}).get("to_network_total", 0.0))

            ez_main.append(ez.get(y, {}).get("to_el_main_grid_total", 0.0))
            ez_net.append(ez.get(y, {}).get("to_network_total", 0.0))

        vals_vb_main = np.array(vb_main, dtype=float)
        vals_vb_net = np.array(vb_net, dtype=float)
        vals_ez_main = np.array(ez_main, dtype=float)
        vals_ez_net = np.array(ez_net, dtype=float)

        # Interleave: [compare_short1(y1), compare_short2(y1), compare_short1(y2), compare_short2(y2), ...]
        y_main = np.empty(len(x), dtype=float)
        y_net = np.empty(len(x), dtype=float)
        y_main[0::2] = vals_vb_main
        y_main[1::2] = vals_ez_main
        y_net[0::2] = vals_vb_net
        y_net[1::2] = vals_ez_net

        plt.figure(figsize=(8, 4))
        width = 0.5

        # Hauptnetz-Balken
        colors_main = ["#E43D30" if i % 2 == 0 else "#B9BABC" for i in range(len(x))]
        plt.bar(x, y_main, width=width, color=colors_main)

        # Verbundnetz gestapelt
        colors_net = ["#8C1D17" if i % 2 == 0 else "#8A8B8D" for i in range(len(x))]
        plt.bar(x, y_net, width=width, bottom=y_main, color=colors_net)


        if show_percent_box:
            def _draw_pct_box(x_pos, main_val, net_val):
                total = main_val + net_val
                if total <= 0:
                    return

                pct_net = (net_val / total) * 100.0
                if pct_net <= 0:
                    return

                pct_txt = f"{pct_net:.0f}%".replace(".", ",")
                y_pos = main_val + net_val / 2.0
                va = "center"

                # Bei kleinem Segment: Box oberhalb platzieren
                if net_val < 0.08 * max(total, 1.0):
                    y_pos = main_val + net_val + 0.03 * max(total, 1.0)
                    va = "bottom"

                plt.text(
                    x_pos,
                    y_pos,
                    pct_txt,
                    ha="center",
                    va=va,
                    color="black",
                    fontsize=fontsize-1,
                    fontweight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        facecolor="#FFFFFF",
                        edgecolor="#B9BABC",
                        linewidth=1.0,
                    ),
                    zorder=7,
                    clip_on=False,
                )

            for i in range(len(years)):
                # links: Verbund
                _draw_pct_box(
                    x[2 * i],
                    vals_vb_main[i],   # to_el_main_grid_total
                    vals_vb_net[i],    # to_network_total
                )
                # rechts: Einzeln
                _draw_pct_box(
                    x[2 * i + 1],
                    vals_ez_main[i],   # to_el_main_grid_total
                    vals_ez_net[i],    # to_network_total
                )

        plt.xticks(x, labels, fontsize=fontsize+1)
        plt.ylabel("Energie in MWh", fontsize=fontsize+1)
        #plt.title(titel or sc)
        plt.grid(axis="y", alpha=0.4)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)

        handles, legend_labels = [], []
        if np.any(vals_vb_main > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#E43D30"))
            legend_labels.append(f"Stromeinspeisung in das Hauptnetz {compare_item1 or 'Ohne Verbundpreis'}")
        if np.any(vals_ez_main > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#B9BABC"))
            legend_labels.append(f"Stromeinspeisung in das Hauptnetz {compare_item2 or 'Mit Verbundpreis'}")
        if np.any(vals_vb_net > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8C1D17"))
            legend_labels.append(f"Stromeinspeisung in das Verbundnetz {compare_item1 or 'Ohne Verbundpreis'}")
        if np.any(vals_ez_net > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8A8B8D"))
            legend_labels.append(f"Stromeinspeisung in das Verbundnetz {compare_item2 or 'Mit Verbundpreis'}")

        if handles:
            plt.legend(
                handles,
                legend_labels,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.1),
                ncol=2,
                frameon=False,
                fontsize=fontsize
            )

        plt.tight_layout(rect=[0, 0, 1, 1])

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
    show=False,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None, 
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot yearly LCOE as paired bars (Verbund vs Mit Verbundpreis).

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
            if fn.endswith(f"_{compare_short1}_results.csv"):
                sc = fn[: -len(f"_{compare_short1}_results.csv")]
                if os.path.isfile(os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")):
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
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")
        if not (os.path.isfile(network_path) and os.path.isfile(single_path)):
            print(f"Skip '{sc}': pair not complete.")
            continue

        vb = _read_lcoe_year(network_path)  # Verbund
        ez = _read_lcoe_year(single_path)   # Mit Verbundpreis

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
        plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label=f"{compare_item1 or 'Ohne Verbundpreis'}")
        plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label=f"{compare_item2 or 'Mit Verbundpreis'}")

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
                    fontsize=fontsize,
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
    show=False,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot yearly CO2 emissions as paired bars (Verbund vs Mit Verbundpreis).

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
            if fn.endswith(f"_{compare_short1}_results.csv"):
                sc = fn[: -len(f"_{compare_short1}_results.csv")]
                if os.path.isfile(os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")):
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
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")
        if not (os.path.isfile(network_path) and os.path.isfile(single_path)):
            print(f"Skip '{sc}': pair not complete.")
            continue

        vb = _read_co2_year(network_path)  # Verbund
        ez = _read_co2_year(single_path)   # Mit Verbundpreis

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
        plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label=f"{compare_item1 or 'Ohne Verbundpreis'}")
        plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label=f"{compare_item2 or 'Mit Verbundpreis'}")

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
                    fontsize=fontsize,
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
    show=False,
    titel=None,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot TAC-Summe (3 Quartiere) für Verbund vs. Einzeloptimierung.

    Erwartet:
    - scenario_names: Liste/Tuple mit genau 3 Szenario-Namen
    - Dateien je Szenario:
      - <scenario>_network_results.csv  (Verbund)
      - <scenario>_results.csv          (Mit Verbundpreis)

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
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

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
    labels = [f"{compare_item1 or 'Ohne Verbundpreis'}", f"{compare_item2 or 'Mit Verbundpreis'}"]
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
            fontsize=fontsize,
            bbox=dict(
                boxstyle="square,pad=0.35",
                facecolor="#D40000",
                edgecolor="#D40000",
                linewidth=1.2,
            ),
            zorder=5,
        )

    plt.xticks(x, labels)
    plt.ylabel("TAC-Summe in € pro Jahr")
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


def plot_tes_volume_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot TES-Volumen (device='TES', metric='vol_liter') als Balkenvergleich:
    - Verbund  (<scenario>_network_results.csv)
    - Mit Verbundpreis  (<scenario>_results.csv)

    CSV-Werte sind in Liter; geplottet wird in m³.
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_tes_volume_m3(csv_path):
        liters_sum = 0.0
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if str(row.get("metric", "")).strip() != "vol_liter":
                    continue
                if str(row.get("device", "")).strip() != "TES":
                    continue

                v = _parse_value(row.get("value"))
                try:
                    liters_sum += float(v)
                except Exception:
                    continue
        return liters_sum / 1000.0  # Liter -> m³

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    if scenario_name is None:
        scenario_names = []
        for fn in os.listdir(base_dir):
            if fn.endswith(f"_{compare_short1}_results.csv"):
                sc = fn[: -len(f"_{compare_short1}_results.csv")]
                if os.path.isfile(os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")):
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
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not (os.path.isfile(network_path) and os.path.isfile(single_path)):
            print(f"Skip '{sc}': pair not complete.")
            continue

        vb_m3 = _read_tes_volume_m3(network_path)
        ez_m3 = _read_tes_volume_m3(single_path)

        x = np.arange(2)
        y = [vb_m3, ez_m3]
        labels = [f"{compare_item1 or 'Ohne Verbundpreis'}", f"{compare_item2 or 'Mit Verbundpreis'}"]
        colors = ["#D40000", "#55585C"]

        plt.figure(figsize=(6.5, 4.2))
        bars = plt.bar(x, y, color=colors, width=0.55)

        if show_percent_box:
            ymax = max(max(y), 1.0)
            plt.ylim(0, ymax * 1.30)
            y_offset = ymax * 0.06
            if ez_m3 == 0:
                txt = "n/a" if vb_m3 == 0 else "+∞"
            else:
                txt = _fmt_pct((vb_m3 - ez_m3) / ez_m3 * 100.0)

            plt.text(
                bars[0].get_x() + bars[0].get_width() / 2,
                vb_m3 + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=11,
                bbox=dict(
                    boxstyle="square,pad=0.3",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.1,
                ),
                zorder=5,
            )

        plt.xticks(x, labels)
        plt.ylabel("Volumen thermischer Speicher [m³]")
        plt.title(titel or f"TES-Volumen im Szenario '{sc}'")
        plt.grid(axis="y", alpha=0.35)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)
        plt.tight_layout()

        plot_name = f"tes_volume_{sc}.png" if not titel else f"{titel}.png"
        plot_path = os.path.join(plots_dir, plot_name)
        plt.savefig(plot_path, dpi=150)
        print(f"Plot saved: {plot_path}")

        if show:
            plt.show()
        else:
            plt.close()

        out[sc] = {"network_m3": vb_m3, "single_m3": ez_m3, "plot_path": plot_path}

    if not out:
        print("No plots created.")
    return out


def plot_co2_sum_from_three_scenarios(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot CO2-Summe (3 Quartiere) für Verbund vs. Einzeloptimierung.

    Erwartet:
    - scenario_names: Liste/Tuple mit genau 3 Szenario-Namen
    - Dateien je Szenario:
      - <scenario>_network_results.csv  (Verbund)
      - <scenario>_results.csv          (Mit Verbundpreis)

    CSV-Filter:
    - category == "optimization"
    - metric   == "co2_distr"
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_co2(csv_path):
        co2_sum = 0.0
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "co2_distr":
                    continue
                v = _parse_value(row.get("value"))
                try:
                    co2_sum += float(v)
                except Exception:
                    continue
        return co2_sum

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    total_vb = 0.0
    total_ez = 0.0
    details = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path):
            raise FileNotFoundError(f"Missing file: {network_path}")
        if not os.path.isfile(single_path):
            raise FileNotFoundError(f"Missing file: {single_path}")

        vb = _read_co2(network_path)
        ez = _read_co2(single_path)

        total_vb += vb
        total_ez += ez
        details[sc] = {"network": vb, "single": ez}

    x = np.arange(2)
    y = [total_vb, total_ez]
    labels = [f"{compare_item1 or 'Ohne Verbundpreis'}", f"{compare_item2 or 'Mit Verbundpreis'}"]
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
            fontsize=fontsize,
            bbox=dict(
                boxstyle="square,pad=0.35",
                facecolor="#D40000",
                edgecolor="#D40000",
                linewidth=1.2,
            ),
            zorder=5,
        )

    plt.xticks(x, labels)
    plt.ylabel("CO₂-Emissionen in t")
    plt.title(titel or "CO₂-Summe der drei Quartiere: Verbund vs. Einzeloptimierung")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.tight_layout()

    plot_name = "co2_sum_three_quarters.png" if not titel else f"{titel}.png"
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



def plot_lcoe_sum_from_three_scenarios(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    power_demand=None,
):
    """
    Plot LCOE je Jahr für Verbund vs. Einzeloptimierung (Summen über 3 Quartiere).

    LCOE(year) = TAC_sum / (Heat_sum(year) + Power_sum(year))

    CSV-Filter:
    - TAC:   category == "optimization", metric == "tac_distr"
    - Heat:  category == "yearly_totals", metric == "total_heat_supply_by_year"
    - Power: category == "yearly_totals", metric == "total_power_supply_by_year"
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_tac_and_yearly_heat_supply(csv_path):
        yearly_heat_supply = {}  # {year: heat}
        yearly_tac = {}     # {year: tac}  

        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                cat = str(row.get("category", "")).strip()
                metric = str(row.get("metric", "")).strip()

                # TAC
                if cat == "optimization" and metric == "tac_per_distr_year":
                    y_raw = row.get("year")
                    if y_raw in (None, ""):
                        continue
                    try:
                        y = int(float(y_raw))
                    except Exception:
                        continue

                    v = _parse_value(row.get("value"))
                    try:
                        val = float(v)
                    except Exception:
                        continue
                    yearly_tac[y] = yearly_tac.get(y, 0.0) + val

                # Yearly heat/power production
                if cat == "yearly_totals" and metric == "total_heat_supply_by_year":
                    y_raw = row.get("year")
                    if y_raw in (None, ""):
                        continue
                    try:
                        y = int(float(y_raw))
                    except Exception:
                        continue

                    v = _parse_value(row.get("value"))
                    try:
                        val = float(v)
                    except Exception:
                        continue

                    yearly_heat_supply[y] = yearly_heat_supply.get(y, 0.0) + val

        return yearly_tac, yearly_heat_supply

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    total_tac_vb = {}
    total_tac_ez = {}
    supply_vb = {}
    supply_ez = {}

    for sc in scenario_names:
        print(f"scenario: {sc}")
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path):
            raise FileNotFoundError(f"Missing file: {network_path}")
        if not os.path.isfile(single_path):
            raise FileNotFoundError(f"Missing file: {single_path}")

        y_tac_vb, ys_vb = _read_tac_and_yearly_heat_supply(network_path)
        y_tac_ez, ys_ez = _read_tac_and_yearly_heat_supply(single_path)

        for y, v in y_tac_vb.items():

            total_tac_vb[y] = total_tac_vb.get(y, 0.0) + v
        for y, v in y_tac_ez.items():
            total_tac_ez[y] = total_tac_ez.get(y, 0.0) + v

        for y, v in ys_vb.items():
            supply_vb[y] = supply_vb.get(y, 0.0) + v + power_demand[sc]
            print(f"DEBUG: {sc} Year {y}: Heat supply = {v:.2f}, Power demand = {power_demand[sc]:.2f}, Total supply = {supply_vb[y]:.2f}")
        for y, v in ys_ez.items():
            supply_ez[y] = supply_ez.get(y, 0.0) + v + power_demand[sc]

    # Print total_tac_vb[y] and supply_vb[y] for debugging
    for y in sorted(total_tac_vb.keys()):
        print(f"Year {y}: total_tac_vb = {total_tac_vb[y]:.2f}, supply_vb = {supply_vb.get(y, 0.0):.2f}")
    for y in sorted(total_tac_ez.keys()):
        print(f"Year {y}: total_tac_ez = {total_tac_ez[y]:.2f}, supply_ez = {supply_ez.get(y, 0.0):.2f}")

    years = sorted(set(supply_vb.keys()) | set(supply_ez.keys()))
    if not years:
        raise ValueError("Keine yearly_totals-Daten für Wärme/Strom gefunden.")

    lcoe_vb = []
    lcoe_ez = []
    for y in years:
        den_vb = supply_vb.get(y, 0.0)
        den_ez = supply_ez.get(y, 0.0)
        lcoe_vb.append((total_tac_vb.get(y, 0.0) / den_vb) if den_vb > 0 else 0.0)
        lcoe_ez.append((total_tac_ez.get(y, 0.0) / den_ez) if den_ez > 0 else 0.0)

    x = np.arange(len(years))
    width = 0.35
    labels = [str(base_calendar_year + y) for y in years]

    plt.figure(figsize=(8, 4.8))
    plt.bar(x - width / 2, lcoe_vb, width=width, color="#D40000", label=f"{compare_item1 or 'Ohne Verbundpreis'}")
    plt.bar(x + width / 2, lcoe_ez, width=width, color="#55585C", label=f"{compare_item2 or 'Mit Verbundpreis'}")

    if show_percent_box:
        ymax = max(max(lcoe_vb) if lcoe_vb else 0, max(lcoe_ez) if lcoe_ez else 0, 1.0)
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.07

        for i, (vb_val, ez_val) in enumerate(zip(lcoe_vb, lcoe_ez)):
            if ez_val == 0:
                txt = "n/a" if vb_val == 0 else "+∞"
            else:
                txt = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

            plt.text(
                x[i] - width / 2,
                vb_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=fontsize,
                bbox=dict(
                    boxstyle="square,pad=0.3",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.1,
                ),
            )

    plt.xticks(x, labels)
    plt.ylabel("Energiegestehungskosten in €/MWh")
    #plt.title(titel or "LCOE (Summe aus 3 Quartieren): Verbund vs. Einzeloptimierung")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.legend()
    plt.tight_layout()

    plot_name = "lcoe_sum_three_quarters_by_year.png" if not titel else f"{titel}.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario_names": list(scenario_names),
        "tac_network_sum": total_tac_vb,
        "tac_single_sum": total_tac_ez,
        "supply_network_sum_by_year": supply_vb,
        "supply_single_sum_by_year": supply_ez,
        "lcoe_network_by_year": dict(zip(years, lcoe_vb)),
        "lcoe_single_by_year": dict(zip(years, lcoe_ez)),
        "plot_path": plot_path,
    }



def plot_tac_by_year_sum_from_three_scenarios(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot jährliche Gesamtkosten (TAC) je Jahr, summiert über 3 Quartiere:
    Verbund vs. Einzeloptimierung.

    CSV-Filter:
    - category == "optimization"
    - metric   == "tac_per_distr_year"
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_tac_by_year(csv_path):
        out = {}  # {year: tac}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "tac_per_distr_year":
                    continue

                y_raw = row.get("year")
                if y_raw in (None, ""):
                    continue
                try:
                    y = int(float(y_raw))
                except Exception:
                    continue

                v = _parse_value(row.get("value"))
                try:
                    out[y] = out.get(y, 0.0) + float(v)
                except Exception:
                    continue
        return out

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    tac_vb_sum = {}  # year -> sum over 3 scenarios
    tac_ez_sum = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path):
            raise FileNotFoundError(f"Missing file: {network_path}")
        if not os.path.isfile(single_path):
            raise FileNotFoundError(f"Missing file: {single_path}")

        vb = _read_tac_by_year(network_path)
        ez = _read_tac_by_year(single_path)

        for y, val in vb.items():
            tac_vb_sum[y] = tac_vb_sum.get(y, 0.0) + val
        for y, val in ez.items():
            tac_ez_sum[y] = tac_ez_sum.get(y, 0.0) + val

    years = sorted(set(tac_vb_sum.keys()) | set(tac_ez_sum.keys()))
    if not years:
        raise ValueError("Keine Daten für metric='tac_per_distr_year' gefunden.")

    y_vb = [tac_vb_sum.get(y, 0.0) for y in years]
    y_ez = [tac_ez_sum.get(y, 0.0) for y in years]

    x = np.arange(len(years))
    width = 0.35
    labels = [str(base_calendar_year + y) for y in years]

    plt.figure(figsize=(8, 4.8))
    plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label=compare_item1 or "Ohne Verbundpreis")
    plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label=compare_item2 or "Mit Verbundpreis")

    if show_percent_box:
        ymax = max(max(y_vb) if y_vb else 0, max(y_ez) if y_ez else 0, 1.0)
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.07

        for i, (vb_val, ez_val) in enumerate(zip(y_vb, y_ez)):
            if ez_val == 0:
                txt = "n/a" if vb_val == 0 else "+∞"
            else:
                txt = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

            plt.text(
                x[i] - width / 2,
                vb_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=11,
                bbox=dict(
                    boxstyle="square,pad=0.3",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.1,
                ),
            )

    plt.xticks(x, labels)
    plt.ylabel("Annuitäten in €/a")
    plt.title(titel or "Annuitäten (Summe aus 3 Quartieren)")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.legend()
    plt.tight_layout()

    plot_name = "tac_by_year_sum_three_quarters.png" if not titel else f"{titel}.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario_names": list(scenario_names),
        "network_tac_by_year": dict(zip(years, y_vb)),
        "single_tac_by_year": dict(zip(years, y_ez)),
        "plot_path": plot_path,
    }



def plot_co2_by_year_sum_from_three_scenarios(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Plot jährliche CO2-Emissionen je Jahr, summiert über 3 Quartiere:
    Verbund vs. Einzeloptimierung.

    CSV-Filter:
    - category == "optimization"
    - metric   == "co2_sum_distr_year"
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_co2_by_year(csv_path):
        out = {}  # {year: co2}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "co2_sum_distr_year":
                    continue

                y_raw = row.get("year")
                if y_raw in (None, ""):
                    continue
                try:
                    y = int(float(y_raw))
                except Exception:
                    continue

                v = _parse_value(row.get("value"))
                try:
                    out[y] = out.get(y, 0.0) + float(v)
                except Exception:
                    continue
        return out

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    co2_vb_sum = {}
    co2_ez_sum = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path):
            raise FileNotFoundError(f"Missing file: {network_path}")
        if not os.path.isfile(single_path):
            raise FileNotFoundError(f"Missing file: {single_path}")

        vb = _read_co2_by_year(network_path)
        ez = _read_co2_by_year(single_path)

        for y, val in vb.items():
            co2_vb_sum[y] = co2_vb_sum.get(y, 0.0) + val
        for y, val in ez.items():
            co2_ez_sum[y] = co2_ez_sum.get(y, 0.0) + val

    years = sorted(set(co2_vb_sum.keys()) | set(co2_ez_sum.keys()))
    if not years:
        raise ValueError("Keine Daten für metric='co2_sum_distr_year' gefunden.")

    y_vb = [co2_vb_sum.get(y, 0.0) for y in years]
    y_ez = [co2_ez_sum.get(y, 0.0) for y in years]

    x = np.arange(len(years))
    width = 0.35
    labels = [str(base_calendar_year + y) for y in years]

    plt.figure(figsize=(8, 4.8))
    plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label=compare_item1 or "Ohne Verbundpreis")
    plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label=compare_item2 or "Mit Verbundpreis")

    if show_percent_box:
        ymax = max(max(y_vb) if y_vb else 0, max(y_ez) if y_ez else 0, 1.0)
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.07

        for i, (vb_val, ez_val) in enumerate(zip(y_vb, y_ez)):
            if ez_val == 0:
                txt = "n/a" if vb_val == 0 else "+∞"
            else:
                txt = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

            plt.text(
                x[i] - width / 2,
                vb_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=fontsize,
                bbox=dict(
                    boxstyle="square,pad=0.3",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.1,
                ),
            )

    plt.xticks(x, labels)
    plt.ylabel("Jährliche CO₂-Emissionen in t/a")
    plt.title(titel or "Jährliche CO₂-Emissionen (Summe aus 3 Quartieren)")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.legend()
    plt.tight_layout()

    plot_name = "co2_by_year_sum_three_quarters.png" if not titel else f"{titel}.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario_names": list(scenario_names),
        "network_co2_by_year": dict(zip(years, y_vb)),
        "single_co2_by_year": dict(zip(years, y_ez)),
        "plot_path": plot_path,
    }
def plot_device_capacities_three_subplots_from_csv(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    subplot_titles=None,
    show_percent_box=False,
    plot_tes_only=False,
    fontsize=None,
    compare_item1=None,
    compare_item2=None,
):
    """
    Erstellt eine gemeinsame Abbildung mit 3 Subplots (1x3),
    jeweils wie plot_device_capacities_from_csv für ein Szenario.
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

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
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    include_set = _to_set(include_devices)
    exclude_set = _to_set(exclude_devices) or set()

    preferred_order = [
        "HP", "CHP", "TES", "PV", "STC", "WT", "EB", "BOI", "BBOI", "GHP", "CC", "AC",
        "WAT", "BCHP", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "CTES", "BAT", "GS"
    ]

    label_map = {
        "HP": "Wärmepumpe",
        "CHP": "BHKW",
        "BCHP": "BBHKW",
        "TES": "thermischer Speicher",
        "STC": "Solarthermie",
        "WT": "Windkraft",
        "EB": "Elektrischer\nKessel",
        "BOI": "Erdgas-\nkessel",
        "BBOI": "Biomasse-\nkessel",
        "PV": "PV-Anlage",
    }

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    if subplot_titles is None:
        subplot_titles = list(scenario_names)
    if len(subplot_titles) != 3:
        raise ValueError("subplot_titles muss genau 3 Einträge enthalten.")

    fig = plt.figure(figsize=(12, 7.5))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])   # oben links
    ax2 = fig.add_subplot(gs[0, 1])   # oben rechts
    ax3 = fig.add_subplot(gs[1, :])   # unten über beide Spalten
    axes = [ax1, ax2, ax3]
    out = {}

    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")


        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            ax.axis("off")
            ax.text(0.5, 0.5, f"Fehlende Dateien\n{sc}", ha="center", va="center")
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
            ax.axis("off")
            ax.text(0.5, 0.5, f"Keine Geräte nach Filter\n{sc}", ha="center", va="center")
            continue

        x = np.arange(len(devices))
        width = 0.32

        y_network = [caps_network.get(d, 0.0) for d in devices]
        y_single = [caps_single.get(d, 0.0) for d in devices]
        xtick_labels = [label_map.get(d, d) for d in devices]

        ax.bar(x - width / 2, y_network, width=width, color="#D40000", label=compare_item1 or "Ohne Verbundpreis")
        ax.bar(x + width / 2, y_single, width=width, color="#55585C", label=compare_item2 or "Mit Verbundpreis")

        ymax = max(max(y_network) if y_network else 0, max(y_single) if y_single else 0, 1.0)
        if show_percent_box:
            ax.set_ylim(0, ymax * 1.35)
            y_offset = ymax * 0.08

            for i, (yn, ys) in enumerate(zip(y_network, y_single)):
                if ys == 0:
                    text = "n/a" if yn == 0 else f"+{yn:.1f} kW" if not plot_tes_only else f"+{yn:.1f} kWh"
                else:
                    text = _fmt_pct((yn - ys) / ys * 100.0)

                ax.text(
                    x[i] - width / 2,
                    yn + y_offset,
                    text,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=fontsize,
                    bbox=dict(
                        boxstyle="square,pad=0.35",
                        facecolor="#D40000",
                        edgecolor="#D40000",
                        linewidth=1.2,
                    ),
                    zorder=5,
                )

        ax.set_xticks(x)
        ax.set_xticklabels(xtick_labels, fontsize=fontsize)
        ax.set_title(sub_titel, fontsize=fontsize)
        ax.grid(axis="y", alpha=0.4)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

        # statt ax.legend(...) -> Handles nur einmal einsammeln
        if shared_handles is None:
            shared_handles, shared_labels = ax.get_legend_handles_labels()

        if plot_tes_only:
            ax.set_ylabel("Speicherkapazität in kWh", fontsize=fontsize)
        else:
            ax.set_ylabel("Anlagenleistung in kW", fontsize=fontsize)

        out[sc] = {"network": caps_network, "single": caps_single}

    # gemeinsame Legende für alle Subplots
    if shared_handles and shared_labels:
        fig.legend(
            shared_handles,
            shared_labels,
            loc="lower center",
            ncol=2,
            frameon=False,
            bbox_to_anchor=(0.5, 0.01),
            fontsize=fontsize,
        )

    fig.tight_layout(rect=[0, 0.06, 1, 1])

    plot_name = f"{titel}.png" if titel else "device_capacities_three_subplots.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out



def plot_lcoe_three_subplots_from_csv(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    subplot_titles=None,
    base_calendar_year=2025,
    show_percent_box=False,
    fontsize=None,
    compare_item1=None,
    compare_item2=None,
):
    """
    Erstellt eine gemeinsame Abbildung mit 3 Subplots für LCOE (2 oben, 1 unten),
    jeweils wie plot_lcoe_by_year_from_csv für ein Szenario.
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_lcoe_year(csv_path):
        out = {}  # {year: lcoe}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "LCOE_year":
                    continue
                y_raw = row.get("year")
                if y_raw in (None, ""):
                    continue
                try:
                    y = int(float(y_raw))
                    v = float(_parse_value(row.get("value")))
                except Exception:
                    continue
                out[y] = v
        return out

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    if subplot_titles is None:
        subplot_titles = list(scenario_names)
    if len(subplot_titles) != 3:
        raise ValueError("subplot_titles muss genau 3 Einträge enthalten.")

    fig = plt.figure(figsize=(12, 7.5))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    axes = [ax1, ax2, ax3]

    out = {}
    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            ax.axis("off")
            ax.text(0.5, 0.5, f"Fehlende Dateien\n{sc}", ha="center", va="center")
            continue

        vb = _read_lcoe_year(network_path)
        ez = _read_lcoe_year(single_path)

        years = sorted(set(vb.keys()) | set(ez.keys()))
        if not years:
            ax.axis("off")
            ax.text(0.5, 0.5, f"Keine LCOE-Daten\n{sc}", ha="center", va="center")
            continue

        x = np.arange(len(years))
        width = 0.35

        y_vb = [vb.get(y, 0.0) for y in years]
        y_ez = [ez.get(y, 0.0) for y in years]
        labels = [str(base_calendar_year + y) for y in years]

        ax.bar(x - width / 2, y_vb, width=width, color="#D40000", label=compare_item1 or "Ohne Verbundpreis")
        ax.bar(x + width / 2, y_ez, width=width, color="#55585C", label=compare_item2 or "Mit Verbundpreis")

        if show_percent_box:
            ymax = max(max(y_vb) if y_vb else 0, max(y_ez) if y_ez else 0, 1.0)
            ax.set_ylim(0, ymax * 1.35)
            y_offset = ymax * 0.08

            for i, (vb_val, ez_val) in enumerate(zip(y_vb, y_ez)):
                if ez_val == 0:
                    text = "n/a" if vb_val == 0 else "+∞"
                else:
                    text = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

                ax.text(
                    x[i] - width / 2,
                    vb_val + y_offset,
                    text,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=fontsize,
                    bbox=dict(
                        boxstyle="square,pad=0.35",
                        facecolor="#D40000",
                        edgecolor="#D40000",
                        linewidth=1.2,
                    ),
                    zorder=5,
                )

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=fontsize)
        ax.set_title(sub_titel, fontsize=fontsize + 1)
        ax.set_ylabel("Energiegestehungskosten in €/MWh", fontsize=fontsize)
        ax.grid(axis="y", alpha=0.4)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

        if shared_handles is None:
            shared_handles, shared_labels = ax.get_legend_handles_labels()

        out[sc] = {"network": vb, "single": ez}

    if shared_handles and shared_labels:
        fig.legend(
            shared_handles,
            shared_labels,
            loc="lower center",
            ncol=2,
            frameon=False,
            bbox_to_anchor=(0.5, 0.01),
        )

    fig.tight_layout(rect=[0, 0.06, 1, 1])

    plot_name = f"{titel}.png" if titel else "lcoe_three_subplots.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out


def plot_co2_three_subplots_from_csv(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    subplot_titles=None,
    base_calendar_year=2025,
    show_percent_box=False,
    fontsize=None,
    compare_item1=None,
    compare_item2=None,
):
    """
    Erstellt eine gemeinsame Abbildung mit 3 Subplots für CO2-Emissionen
    (2 oben, 1 unten), jeweils wie plot_co2_by_year_from_csv für ein Szenario.
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_co2_year(csv_path):
        out = {}  # {year: co2}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "co2_sum_distr_year":
                    continue

                y_raw = row.get("year")
                if y_raw in (None, ""):
                    continue

                try:
                    y = int(float(y_raw))
                    v = float(_parse_value(row.get("value")))
                except Exception:
                    continue

                out[y] = v
        return out

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    if subplot_titles is None:
        subplot_titles = list(scenario_names)
    if len(subplot_titles) != 3:
        raise ValueError("subplot_titles muss genau 3 Einträge enthalten.")

    fig = plt.figure(figsize=(12, 7.5))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    axes = [ax1, ax2, ax3]

    out = {}
    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            ax.axis("off")
            ax.text(0.5, 0.5, f"Fehlende Dateien\n{sc}", ha="center", va="center")
            continue

        vb = _read_co2_year(network_path)
        ez = _read_co2_year(single_path)

        years = sorted(set(vb.keys()) | set(ez.keys()))
        if not years:
            ax.axis("off")
            ax.text(0.5, 0.5, f"Keine CO2-Daten\n{sc}", ha="center", va="center")
            continue

        x = np.arange(len(years))
        width = 0.35

        y_vb = [vb.get(y, 0.0) for y in years]
        y_ez = [ez.get(y, 0.0) for y in years]
        labels = [str(base_calendar_year + y) for y in years]

        ax.bar(x - width / 2, y_vb, width=width, color="#D40000", label=compare_item1 or "Ohne Verbundpreis")
        ax.bar(x + width / 2, y_ez, width=width, color="#55585C", label=compare_item2 or "Mit Verbundpreis")

        if show_percent_box:
            ymax = max(max(y_vb) if y_vb else 0, max(y_ez) if y_ez else 0, 1.0)
            ax.set_ylim(0, ymax * 1.35)
            y_offset = ymax * 0.08

            for i, (vb_val, ez_val) in enumerate(zip(y_vb, y_ez)):
                if ez_val == 0:
                    text = "n/a" if vb_val == 0 else "+∞"
                else:
                    text = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

                ax.text(
                    x[i] - width / 2,
                    vb_val + y_offset,
                    text,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=fontsize-1,
                    bbox=dict(
                        boxstyle="square,pad=0.35",
                        facecolor="#D40000",
                        edgecolor="#D40000",
                        linewidth=1.2,
                    ),
                    zorder=5,
                )

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=fontsize)
        ax.set_title(sub_titel, fontsize=fontsize + 1)
        ax.set_ylabel("THG-Emissionen in t CO₂-eq/a", fontsize=fontsize)
        ax.grid(axis="y", alpha=0.4)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

        if shared_handles is None:
            shared_handles, shared_labels = ax.get_legend_handles_labels()

        out[sc] = {"network": vb, "single": ez}

    if shared_handles and shared_labels:
        fig.legend(
            shared_handles,
            shared_labels,
            loc="lower center",
            ncol=2,
            frameon=False,
            bbox_to_anchor=(0.5, 0.01),
            fontsize=fontsize+1,
        )

    fig.tight_layout(rect=[0, 0.06, 1, 1])

    plot_name = f"{titel}.png" if titel else "co2_three_subplots.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out


def plot_power_import_three_subplots_from_csv(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    subplot_titles=None,
    base_calendar_year=2025,
    show_percent_box=False,
    fontsize=None,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Erstellt eine gemeinsame Abbildung mit 3 Subplots für Strombezug
    (2 oben, 1 unten), jeweils wie plot_power_import_by_year_from_csv für ein Szenario.
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

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

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    if subplot_titles is None:
        subplot_titles = list(scenario_names)
    if len(subplot_titles) != 3:
        raise ValueError("subplot_titles muss genau 3 Einträge enthalten.")
    
    #     fig_w_mm = 155
    # fig_h_mm = 120
    # fig, ax1 = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))

    fig = plt.figure(figsize=(12, 7.5))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    axes = [ax1, ax2, ax3]

    out = {}
    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            ax.axis("off")
            ax.text(0.5, 0.5, f"Fehlende Dateien\n{sc}", ha="center", va="center")
            continue

        vb = _read_yearly_import(network_path)
        ez = _read_yearly_import(single_path)

        years = sorted(set(vb.keys()) | set(ez.keys()))
        if not years:
            ax.axis("off")
            ax.text(0.5, 0.5, f"Keine Import-Daten\n{sc}", ha="center", va="center")
            continue

        x = np.arange(len(years) * 2)
        labels = []
        vb_main, vb_net, ez_main, ez_net = [], [], [], []

        for y in years:
            cal_y = base_calendar_year + y
            labels.extend([f"{cal_y}\n{compare_short1 or 'oVP'}", f"{cal_y}\n{compare_short2 or 'VP'}"])

            vb_main.append(vb.get(y, {}).get("from_el_main_grid_total", 0.0))
            vb_net.append(vb.get(y, {}).get("from_network_total", 0.0))
            ez_main.append(ez.get(y, {}).get("from_el_main_grid_total", 0.0))
            ez_net.append(ez.get(y, {}).get("from_network_total", 0.0))

        vals_vb_main = np.array(vb_main, dtype=float)
        vals_vb_net = np.array(vb_net, dtype=float)
        vals_ez_main = np.array(ez_main, dtype=float)
        vals_ez_net = np.array(ez_net, dtype=float)

        y_main = np.empty(len(x), dtype=float)
        y_net = np.empty(len(x), dtype=float)
        y_main[0::2] = vals_vb_main
        y_main[1::2] = vals_ez_main
        y_net[0::2] = vals_vb_net
        y_net[1::2] = vals_ez_net

        width = 0.5
        colors_main = ["#E43D30" if i % 2 == 0 else "#B9BABC" for i in range(len(x))]
        colors_net = ["#8C1D17" if i % 2 == 0 else "#8A8B8D" for i in range(len(x))]

        ax.bar(x, y_main, width=width, color=colors_main)
        ax.bar(x, y_net, width=width, bottom=y_main, color=colors_net)

        if show_percent_box:
            y_total = y_main + y_net
            ymax = max(float(np.max(y_total)) if len(y_total) else 0.0, 1.0)
            ax.set_ylim(0, ymax * 1.30)

            def _draw_pct_box(x_pos, main_val, net_val):
                total = main_val + net_val
                if total <= 0:
                    return
                pct_net = (net_val / total) * 100.0
                if pct_net <= 0:
                    return

                pct_txt = f"{pct_net:.0f}%".replace(".", ",")
                line_y0 = total
                line_y1 = total + 0.05 * ymax
                box_y = line_y1 + 0.015 * ymax

                ax.plot(
                    [x_pos, x_pos],
                    [line_y0, line_y1],
                    color="#7A7A7A",
                    linewidth=1.0,
                    zorder=6,
                    clip_on=False,
                )

                ax.text(
                    x_pos,
                    box_y,
                    pct_txt,
                    ha="center",
                    va="bottom",
                    color="black",
                    fontsize=max(9, fontsize - 2),
                    fontweight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        facecolor="#FFFFFF",
                        edgecolor="#B9BABC",
                        linewidth=1.0,
                    ),
                    zorder=7,
                    clip_on=False,
                )

            for i in range(len(years)):
                _draw_pct_box(x[2 * i], vals_vb_main[i], vals_vb_net[i])
                _draw_pct_box(x[2 * i + 1], vals_ez_main[i], vals_ez_net[i])

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=max(9, fontsize - 1))
        ax.set_title(sub_titel, fontsize=fontsize + 1)
        ax.set_ylabel("Energie in MWh", fontsize=fontsize)
        ax.grid(axis="y", alpha=0.4)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

        if shared_handles is None:
            handles, legend_labels = [], []
            if np.any(vals_vb_main > 0):
                handles.append(plt.Rectangle((0, 0), 1, 1, fc="#E43D30"))
                legend_labels.append(f"{compare_item1 or 'Ohne Verbundpreis'} Strombezug aus dem Hauptnetz")
            if np.any(vals_ez_main > 0):
                handles.append(plt.Rectangle((0, 0), 1, 1, fc="#B9BABC"))
                legend_labels.append(f"{compare_item2 or 'Mit Verbundpreis'} Strombezug aus dem Hauptnetz")
            if np.any(vals_vb_net > 0):
                handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8C1D17"))
                legend_labels.append(f"{compare_item1 or 'Ohne Verbundpreis'} Strombezug aus dem Verbundnetz")
            if np.any(vals_ez_net > 0):
                handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8A8B8D"))
                legend_labels.append(f"{compare_item2 or 'Mit Verbundpreis'} Strombezug aus dem Verbundnetz")

            if handles:
                shared_handles, shared_labels = handles, legend_labels

        out[sc] = {"network": vb, "single": ez}

    if shared_handles and shared_labels:
        fig.legend(
            shared_handles,
            shared_labels,
            loc="lower center",
            ncol=2,
            frameon=False,
            bbox_to_anchor=(0.5, 0.02),   # sicher innerhalb der Figure
            fontsize=max(9, fontsize),
        )

    # Kein tight_layout hier, stattdessen fixer Rand unten für die Legende
    fig.subplots_adjust(        
        left=0.10,    # vorher größer
        right=0.99,   # vorher kleiner
        bottom=0.22,
        top=0.92,
        hspace=0.35,
        wspace=0.18,  # etwas enger zwischen links/rechts oben
        )

    plot_name = f"{titel}.png" if titel else "power_import_three_subplots.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)  # <-- ohne bbox_inches="tight"
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out




def plot_power_import_two_subplots_from_csv(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    subplot_titles=None,
    base_calendar_year=2025,
    show_percent_box=False,
    fontsize=None,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Erstellt eine gemeinsame Abbildung mit 2 Subplots für Strombezug
    (2 oben, 1 unten), jeweils wie plot_power_import_by_year_from_csv für ein Szenario.
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 2:
        raise ValueError("scenario_names muss genau 2 Szenario-Namen enthalten.")

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

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    if subplot_titles is None:
        subplot_titles = list(scenario_names)
    if len(subplot_titles) != 2:
        raise ValueError("subplot_titles muss genau 2 Einträge enthalten.")
    
    #     fig_w_mm = 155
    # fig_h_mm = 120
    # fig, ax1 = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))

    fig = plt.figure(figsize=(12, 7.5))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, :])
    #ax3 = fig.add_subplot(gs[1, :])
    axes = [ax1, ax2]

    out = {}
    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            ax.axis("off")
            ax.text(0.5, 0.5, f"Fehlende Dateien\n{sc}", ha="center", va="center")
            continue

        vb = _read_yearly_import(network_path)
        ez = _read_yearly_import(single_path)
        print(f"Debug power import: {sc} - VB from_el_main_grid_total: {vb[15]['from_el_main_grid_total']}, EZ from_el_main_grid_total: {ez[15]['from_el_main_grid_total']}")

        years = sorted(set(vb.keys()) | set(ez.keys()))
        if not years:
            ax.axis("off")
            ax.text(0.5, 0.5, f"Keine Import-Daten\n{sc}", ha="center", va="center")
            continue

        x = np.arange(len(years) * 2)
        labels = []
        vb_main, vb_net, ez_main, ez_net = [], [], [], []

        for y in years:
            # Ohne VW undQW unter jedem Jahr
            cal_y = base_calendar_year + y
            # labels.extend([f"{cal_y}\n{compare_short1 or 'oVP'}", f"{cal_y}\n{compare_short2 or 'VP'}"])
            labels.extend([f"{cal_y}", f"{cal_y}"])

            vb_main.append(vb.get(y, {}).get("from_el_main_grid_total", 0.0))
            vb_net.append(vb.get(y, {}).get("from_network_total", 0.0))
            ez_main.append(ez.get(y, {}).get("from_el_main_grid_total", 0.0))
            ez_net.append(ez.get(y, {}).get("from_network_total", 0.0))

        vals_vb_main = np.array(vb_main, dtype=float)
        vals_vb_net = np.array(vb_net, dtype=float)
        vals_ez_main = np.array(ez_main, dtype=float)
        vals_ez_net = np.array(ez_net, dtype=float)

        y_main = np.empty(len(x), dtype=float)
        y_net = np.empty(len(x), dtype=float)
        y_main[0::2] = vals_vb_main
        y_main[1::2] = vals_ez_main
        y_net[0::2] = vals_vb_net
        y_net[1::2] = vals_ez_net

        width = 0.5
        colors_main = ["#E43D30" if i % 2 == 0 else "#B9BABC" for i in range(len(x))]
        colors_net = ["#8C1D17" if i % 2 == 0 else "#8A8B8D" for i in range(len(x))]

        ax.bar(x, y_main, width=width, color=colors_main)
        ax.bar(x, y_net, width=width, bottom=y_main, color=colors_net)

        if show_percent_box:
            y_total = y_main + y_net
            ymax = max(float(np.max(y_total)) if len(y_total) else 0.0, 1.0)
            ax.set_ylim(0, ymax * 1.30)

            def _draw_pct_box(x_pos, main_val, net_val):
                total = main_val + net_val
                if total <= 0:
                    return
                pct_net = (net_val / total) * 100.0
                if pct_net <= 0:
                    return

                pct_txt = f"{pct_net:.0f}%".replace(".", ",")
                line_y0 = total
                line_y1 = total + 0.05 * ymax
                box_y = line_y1 + 0.015 * ymax

                ax.plot(
                    [x_pos, x_pos],
                    [line_y0, line_y1],
                    color="#7A7A7A",
                    linewidth=1.0,
                    zorder=6,
                    clip_on=False,
                )

                ax.text(
                    x_pos,
                    box_y,
                    pct_txt,
                    ha="center",
                    va="bottom",
                    color="black",
                    fontsize=max(9, fontsize - 2),
                    fontweight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        facecolor="#FFFFFF",
                        edgecolor="#B9BABC",
                        linewidth=1.0,
                    ),
                    zorder=7,
                    clip_on=False,
                )

            for i in range(len(years)):
                _draw_pct_box(x[2 * i], vals_vb_main[i], vals_vb_net[i])
                _draw_pct_box(x[2 * i + 1], vals_ez_main[i], vals_ez_net[i])

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=max(9, fontsize - 1))
        ax.set_title(sub_titel, fontsize=fontsize + 1)
        ax.set_ylabel("Energie in MWh", fontsize=fontsize)
        ax.grid(axis="y", alpha=0.4)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

        if shared_handles is None:
            handles, legend_labels = [], []
            if np.any(vals_vb_main > 0):
                handles.append(plt.Rectangle((0, 0), 1, 1, fc="#E43D30"))
                legend_labels.append(f"Strombezug aus dem Hauptnetz {compare_item1 or 'Ohne Verbundpreis'}")
            if np.any(vals_ez_main > 0):
                handles.append(plt.Rectangle((0, 0), 1, 1, fc="#B9BABC"))
                legend_labels.append(f"Strombezug aus dem Hauptnetz {compare_item2 or 'Mit Verbundpreis'}")
            if np.any(vals_vb_net > 0):
                handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8C1D17"))
                legend_labels.append(f"Strombezug aus dem Verbundnetz {compare_item1 or 'Ohne Verbundpreis'}")
            if np.any(vals_ez_net > 0):
                handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8A8B8D"))
                legend_labels.append(f"Strombezug aus dem Verbundnetz {compare_item2 or 'Mit Verbundpreis'}")

            if handles:
                shared_handles, shared_labels = handles, legend_labels

        out[sc] = {"network": vb, "single": ez}

    if shared_handles and shared_labels:
        fig.legend(
            shared_handles,
            shared_labels,
            loc="lower center",
            ncol=2,
            frameon=False,
            bbox_to_anchor=(0.5, 0.02),   # sicher innerhalb der Figure
            fontsize=max(9, fontsize),
        )

    # Kein tight_layout hier, stattdessen fixer Rand unten für die Legende
    fig.subplots_adjust(        
        left=0.10,    # vorher größer
        right=0.99,   # vorher kleiner
        bottom=0.18,
        top=0.92,
        hspace=0.35,
        wspace=0.18,  # etwas enger zwischen links/rechts oben
        )

    plot_name = f"{titel}.png" if titel else "power_import_two_subplots.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)  # <-- ohne bbox_inches="tight"
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out

def plot_tac_three_subplots_from_csv(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    subplot_titles=None,
    base_calendar_year=2025,
    show_percent_box=False,
    fontsize=None,
    compare_item1=None,
    compare_item2=None,
):
    """
    Erstellt eine gemeinsame Abbildung mit 3 Subplots für tac-Emissionen
    (2 oben, 1 unten), jeweils wie plot_tac_by_year_from_csv für ein Szenario.
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_tac_year(csv_path):
        out = {}  # {year: tac}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "tac_per_distr_year":
                    continue

                y_raw = row.get("year")
                if y_raw in (None, ""):
                    continue

                try:
                    y = int(float(y_raw))
                    v = float(_parse_value(row.get("value")))
                except Exception:
                    continue

                out[y] = v
        return out

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    if subplot_titles is None:
        subplot_titles = list(scenario_names)
    if len(subplot_titles) != 3:
        raise ValueError("subplot_titles muss genau 3 Einträge enthalten.")

    fig = plt.figure(figsize=(12, 7.5))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    axes = [ax1, ax2, ax3]

    out = {}
    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            ax.axis("off")
            ax.text(0.5, 0.5, f"Fehlende Dateien\n{sc}", ha="center", va="center")
            continue

        vb = _read_tac_year(network_path)
        ez = _read_tac_year(single_path)

        years = sorted(set(vb.keys()) | set(ez.keys()))
        if not years:
            ax.axis("off")
            ax.text(0.5, 0.5, f"Keine tac-Daten\n{sc}", ha="center", va="center")
            continue

        x = np.arange(len(years))
        width = 0.35

        y_vb = [vb.get(y, 0.0) for y in years]
        y_ez = [ez.get(y, 0.0) for y in years]
        labels = [str(base_calendar_year + y) for y in years]

        ax.bar(x - width / 2, y_vb, width=width, color="#D40000", label=compare_item1 or "Ohne Verbundpreis")
        ax.bar(x + width / 2, y_ez, width=width, color="#55585C", label=compare_item2 or "Mit Verbundpreis")

        if show_percent_box:
            ymax = max(max(y_vb) if y_vb else 0, max(y_ez) if y_ez else 0, 1.0)
            ax.set_ylim(0, ymax * 1.35)
            y_offset = ymax * 0.08

            for i, (vb_val, ez_val) in enumerate(zip(y_vb, y_ez)):
                if ez_val == 0:
                    text = "n/a" if vb_val == 0 else "+∞"
                else:
                    text = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

                ax.text(
                    x[i] - width / 2,
                    vb_val + y_offset,
                    text,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=fontsize,
                    bbox=dict(
                        boxstyle="square,pad=0.35",
                        facecolor="#D40000",
                        edgecolor="#D40000",
                        linewidth=1.2,
                    ),
                    zorder=5,
                )

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=fontsize)
        ax.set_title(sub_titel, fontsize=fontsize)
        ax.set_ylabel("Annuitäten in €/a", fontsize=fontsize)
        ax.grid(axis="y", alpha=0.4)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

        if shared_handles is None:
            shared_handles, shared_labels = ax.get_legend_handles_labels()

        out[sc] = {"network": vb, "single": ez}

    if shared_handles and shared_labels:
        fig.legend(
            shared_handles,
            shared_labels,
            loc="lower center",
            ncol=2,
            frameon=False,
            bbox_to_anchor=(0.5, 0.01),
            fontsize=fontsize+1,
        )

    fig.tight_layout(rect=[0, 0.06, 1, 1])

    plot_name = f"{titel}.png" if titel else "tac_three_subplots.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out

def plot_power_import_sum_two_subplots_from_csv(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    titel=None,
    subplot_titles=None,
    show_percent_box=False,
    fontsize=None,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
):
    """
    Erstellt eine gemeinsame Abbildung mit 2 Subplots für den summierten Strombezug
    über alle Jahre.

    Es werden pro Szenario alle Werte mit
    - category == 'yearly_totals'
    - metric in ('from_el_main_grid_total', 'from_network_total')
    über alle Jahre aufsummiert.

    Pro Subplot:
    - compare_short1 / compare_item1
    - compare_short2 / compare_item2
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 2:
        raise ValueError("scenario_names muss genau 2 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _read_import_sums(csv_path):
        total_main = 0.0
        total_net = 0.0

        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "yearly_totals":
                    continue

                metric = row.get("metric")
                if metric not in ("from_el_main_grid_total", "from_network_total"):
                    continue

                v = _parse_value(row.get("value"))
                try:
                    val = float(v)
                except Exception:
                    continue

                if metric == "from_el_main_grid_total":
                    total_main += val
                elif metric == "from_network_total":
                    total_net += val

        return {
            "from_el_main_grid_total": total_main,
            "from_network_total": total_net,
        }

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    if subplot_titles is None:
        subplot_titles = list(scenario_names)
    if len(subplot_titles) != 2:
        raise ValueError("subplot_titles muss genau 2 Einträge enthalten.")

    fig = plt.figure(figsize=(12, 6.5))
    gs = gridspec.GridSpec(2, 1, figure=fig, height_ratios=[1, 1], hspace=0.35)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[1, 0])
    axes = [ax1, ax2]

    out = {}

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            ax.axis("off")
            ax.text(0.5, 0.5, f"Fehlende Dateien\n{sc}", ha="center", va="center")
            continue

        vb = _read_import_sums(network_path)
        ez = _read_import_sums(single_path)


        x = np.arange(2)
        width = 0.5

        main_vals = np.array(
            [
                vb["from_el_main_grid_total"],
                ez["from_el_main_grid_total"],
            ],
            dtype=float,
        )
        net_vals = np.array(
            [
                vb["from_network_total"],
                ez["from_network_total"],
            ],
            dtype=float,
        )

        colors_main = ["#E43D30", "#B9BABC"]
        colors_net = ["#8C1D17", "#8A8B8D"]

        ax.bar(x, main_vals, width=width, color=colors_main)
        ax.bar(x, net_vals, width=width, bottom=main_vals, color=colors_net)

        if show_percent_box:
            total_vals = main_vals + net_vals
            ymax = max(float(np.max(total_vals)) if len(total_vals) else 0.0, 1.0)
            ax.set_ylim(0, ymax * 1.30)

            for i in range(2):
                total = total_vals[i]
                if total <= 0:
                    continue

                pct_net = (net_vals[i] / total) * 100.0
                if pct_net <= 0:
                    continue

                pct_txt = f"{pct_net:.0f}%".replace(".", ",")
                line_y0 = total
                line_y1 = total + 0.05 * ymax
                box_y = line_y1 + 0.015 * ymax

                ax.plot(
                    [x[i], x[i]],
                    [line_y0, line_y1],
                    color="#7A7A7A",
                    linewidth=1.0,
                    zorder=6,
                    clip_on=False,
                )

                ax.text(
                    x[i],
                    box_y,
                    pct_txt,
                    ha="center",
                    va="bottom",
                    color="black",
                    fontsize=max(9, fontsize - 2),
                    fontweight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        facecolor="#FFFFFF",
                        edgecolor="#B9BABC",
                        linewidth=1.0,
                    ),
                    zorder=7,
                    clip_on=False,
                )

        ax.set_xticks(x)
        ax.set_xticklabels(
            [compare_short1 or "oVP", compare_short2 or "VP"],
            fontsize=fontsize,
        )
        ax.set_title(sub_titel, fontsize=fontsize)
        ax.set_ylabel("Energie in MWh", fontsize=fontsize)
        ax.grid(axis="y", alpha=0.4)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

        out[sc] = {"network": vb, "single": ez}

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#E43D30"),
        plt.Rectangle((0, 0), 1, 1, fc="#B9BABC"),
        plt.Rectangle((0, 0), 1, 1, fc="#8C1D17"),
        plt.Rectangle((0, 0), 1, 1, fc="#8A8B8D"),
    ]
    labels = [
        f"{compare_item1 or 'Ohne Verbundpreis'} Strombezug aus dem Hauptnetz",
        f"{compare_item2 or 'Mit Verbundpreis'} Strombezug aus dem Hauptnetz",
        f"{compare_item1 or 'Ohne Verbundpreis'} Strombezug aus dem Verbundnetz",
        f"{compare_item2 or 'Mit Verbundpreis'} Strombezug aus dem Verbundnetz",
    ]
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 0.01),
        fontsize=max(9, fontsize),
    )

    fig.subplots_adjust(left=0.10, right=0.99, bottom=0.18, top=0.92, hspace=0.35)

    plot_name = f"{titel}.png" if titel else "power_import_sum_two_subplots.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out





def plot_device_capacities_three_subplots_stacked_from_csv(
    scenario_names,
    base_dir=None,
    result_dir=None,
    show=False,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    subplot_titles=None,
    show_percent_box=False,
    plot_tes_only=False,
    fontsize=None,
    compare_item1=None,
    compare_item2=None,
):
    """
    Like plot_device_capacities_three_subplots_from_csv but heat generation devices
    ("HP","BCHP","EB","BBOI") are shown as a single grouped xtick whose bars are
    stacked segments (one segment per device) for network vs single.

    Colors: each device gets a dedicated color for the verbundweise (network)
    and a dedicated color for the quartiersweise (single) plot.
    Legend: entries for each device are shown for both compare_item1 and compare_item2.
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")

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

    include_set = _to_set(include_devices)
    exclude_set = _to_set(exclude_devices) or set()

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
        "EB": "Elektrischer\nKessel",
        "BOI": "Erdgas-\nkessel",
        "BBOI": "Biomasse-\nkessel",
        "PV": "PV-Anlage",
    }

    # device-specific color pairs: (network_color, single_color)
    # device_color_pairs = {
    #     # heat generators
    #     "HP":  ('#F47328', '#F49961'),
    #     "EB":  ('#1058B0', '#4B81C4'),
    #     "BBOI":('#5F379B', '#8768B4'),
    #     # other typical devices
    #     "BCHP":("#2F3133", "#7F7F7F"),
    #     "CHP": ("#B23A48", "#E89AA2"),
    #     "TES": ("#C93A3A", "#FFB3B3"),
    #     "PV":  ('#008746', '#6EBB96'),
    #     "STC": ("#E07A5F", "#F7C6B0"),
    #     "WT":  ("#2E8B57", "#7FC08A"),
    #     "BOI": ("#6B5B95", "#A793C9"),
    #     "GHP": ("#3A6EA5", "#8FB7E0"),
    #     "CC":  ("#4B4E6D", "#9AA0B8"),
    #     "AC":  ("#6E6F71", "#BDBFC1"),
    #     "BAT": ("#5F4B8B", "#A88FE1"),
    #     "GS":  ("#2F6F69", "#78BFB7"),
    # }

    device_color_pairs = {
        # heat generators
        "HP":  ("#721D13", "#242525"),
        "EB":  ("#DD402D" , "#757679"),
        "BBOI":('#5F379B', '#8768B4'),
        # other typical devices
        "BCHP":("#2F3133", "#7F7F7F"),
        "CHP": ("#B23A48", "#E89AA2"),
        "TES": ("#C93A3A", "#FFB3B3"),
        "PV":  ("#ED7E72", "#A8A8A8"),
        "STC": ("#E07A5F", "#F7C6B0"),
        "WT":  ("#2E8B57", "#7FC08A"),
        "BOI": ("#6B5B95", "#A793C9"),
        "GHP": ("#3A6EA5", "#8FB7E0"),
        "CC":  ("#4B4E6D", "#9AA0B8"),
        "AC":  ("#6E6F71", "#BDBFC1"),
        "BAT": ("#5F4B8B", "#A88FE1"),
        "GS":  ("#2F6F69", "#78BFB7"),
    }

    '#E53027', '#1058B0', '#F47328', '#5F379B','#9B231E','#BE4198','#008746'
    '#EC635C', '#4B81C4', '#F49961', '#8768B4','#B45955','#CB74F4','#6EBB96'

    # fallback colormap for devices not specified above
    cmap = plt.get_cmap("tab20")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    if subplot_titles is None:
        subplot_titles = list(scenario_names)
    if len(subplot_titles) != 3:
        raise ValueError("subplot_titles muss genau 3 Einträge enthalten.")

    fig = plt.figure(figsize=(12, 7.5))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])   # oben links
    ax2 = fig.add_subplot(gs[0, 1])   # oben rechts
    ax3 = fig.add_subplot(gs[1, :])   # unten über beide Spalten
    axes = [ax1, ax2, ax3]
    out = {}

    # global legend containers (ensure unique entries)
    shared_handles = []
    shared_labels = []
    shared_added = set()

    heat_group = ["HP", "BCHP", "EB", "BBOI"]

    # prepare compare labels fallback
    cmp1_label = compare_item1 or "Ohne Verbundpreis"
    cmp2_label = compare_item2 or "Mit Verbundpreis"

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv") if False else None
        # find files similar to other functions: try compare_short names first, then VW/QW fallback
        # use the same detection as other functions by constructing from provided compare_short1/2 if available
        # but here we assume standard file naming like other functions use:
        network_path = os.path.join(base_dir, f"{sc}_{compare_item1}_results.csv") if compare_item1 and os.path.isfile(os.path.join(base_dir, f"{sc}_{compare_item1}_results.csv")) else os.path.join(base_dir, f"{sc}_VW_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_item2}_results.csv") if compare_item2 and os.path.isfile(os.path.join(base_dir, f"{sc}_{compare_item2}_results.csv")) else os.path.join(base_dir, f"{sc}_QW_results.csv")

        if not os.path.isfile(network_path):
            network_path = os.path.join(base_dir, f"{sc}_VW_results.csv")
        if not os.path.isfile(single_path):
            single_path = os.path.join(base_dir, f"{sc}_QW_results.csv")

        if not os.path.isfile(network_path) or not os.path.isfile(single_path):
            ax.axis("off")
            ax.text(0.5, 0.5, f"Fehlende Dateien\n{sc}", ha="center", va="center")
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
            ax.axis("off")
            ax.text(0.5, 0.5, f"Keine Geräte nach Filter\n{sc}", ha="center", va="center")
            continue

        # Build plotting groups: one group for the heat generators (if any present), plus single-device groups for others
        heat_present = [d for d in heat_group if d in devices]
        other_devices = [d for d in devices if d not in heat_group]

        groups = []
        if heat_present:
            groups.append(("HEAT_GROUP", heat_present))
        for d in other_devices:
            groups.append((d, [d]))

        x = np.arange(len(groups))
        width = 0.32

        fallback_i = 0

        for i, (grp_name, grp_devs) in enumerate(groups):
            bottom_net = 0.0
            bottom_single = 0.0

            if grp_name == "HEAT_GROUP":
                for dev in grp_devs:
                    val_net = caps_network.get(dev, 0.0)
                    val_single = caps_single.get(dev, 0.0)

                    if dev in device_color_pairs:
                        col_net, col_single = device_color_pairs[dev]
                    else:
                        # fallback: pick two distinct colors from cmap
                        col_net = cmap((fallback_i * 2) % 20)
                        col_single = cmap((fallback_i * 2 + 1) % 20)
                        fallback_i += 1

                    ax.bar(
                        x[i] - width / 2,
                        val_net,
                        bottom=bottom_net,
                        width=width,
                        color=col_net,
                    )
                    ax.bar(
                        x[i] + width / 2,
                        val_single,
                        bottom=bottom_single,
                        width=width,
                        color=col_single,
                    )

                    # add legend entries for both compare types, unique across figure
                    lbl = label_map.get(dev, dev)
                    lbl_net = f"{lbl} ({cmp1_label})"
                    lbl_single = f"{lbl} ({cmp2_label})"
                    if lbl_net not in shared_added:
                        shared_handles.append(plt.Rectangle((0, 0), 1, 1, fc=col_net))
                        shared_labels.append(lbl_net)
                        shared_added.add(lbl_net)
                    if lbl_single not in shared_added:
                        shared_handles.append(plt.Rectangle((0, 0), 1, 1, fc=col_single))
                        shared_labels.append(lbl_single)
                        shared_added.add(lbl_single)

                    bottom_net += val_net
                    bottom_single += val_single

                if show_percent_box:
                    ymax = max(bottom_net, bottom_single, 1.0)
                    ax.set_ylim(0, ymax * 1.35)
                    y_offset = ymax * 0.08
                    if bottom_single == 0:
                        text = "n/a" if bottom_net == 0 else "+∞"
                    else:
                        pct = (bottom_net - bottom_single) / bottom_single * 100.0
                        if abs(pct - round(pct)) < 0.05:
                            text = f"{pct:+.0f}%".replace(".", ",")
                        else:
                            text = f"{pct:+.1f}%".replace(".", ",")
                    ax.text(
                        x[i] - width/2,
                        bottom_net + y_offset,
                        text,
                        ha="center",
                        va="bottom",
                        color="black",
                        fontsize=fontsize,
                        bbox=dict(boxstyle="square,pad=0.35", facecolor="white", edgecolor="white", linewidth=1.2),
                        zorder=5,
                    )
                    #"#7A7A7A"

            else:
                dev = grp_devs[0]
                val_net = caps_network.get(dev, 0.0)
                val_single = caps_single.get(dev, 0.0)

                if dev in device_color_pairs:
                    col_net, col_single = device_color_pairs[dev]
                else:
                    col_net = cmap((fallback_i * 2) % 20)
                    col_single = cmap((fallback_i * 2 + 1) % 20)
                    fallback_i += 1

                ax.bar(x[i] - width / 2, val_net, width=width, color=col_net)
                ax.bar(x[i] + width / 2, val_single, width=width, color=col_single)

                if show_percent_box:
                    ymax = max(val_net, val_single, 1.0)
                    ax.set_ylim(0, ymax * 1.35)
                    y_offset = ymax * 0.08
                    if val_single == 0:
                        text = "n/a" if val_net == 0 else "+∞"
                    else:
                        pct = (val_net - val_single) / val_single * 100.0
                        if abs(pct - round(pct)) < 0.05:
                            text = f"{pct:+.0f}%".replace(".", ",")
                        else:
                            text = f"{pct:+.1f}%".replace(".", ",")
                    ax.text(
                        x[i] - width / 2,
                        val_net + y_offset,
                        text,
                        ha="center",
                        va="bottom",
                        color="black",
                        fontsize=fontsize,
                        bbox=dict(boxstyle="square,pad=0.35", facecolor="white", edgecolor="white", linewidth=1.2),
                        zorder=5,
                    )

                # collect legend entries for this device for both comparisons
                lbl = label_map.get(dev, dev)
                lbl_net = f"{lbl} ({cmp1_label})"
                lbl_single = f"{lbl} ({cmp2_label})"
                if lbl_net not in shared_added:
                    shared_handles.append(plt.Rectangle((0, 0), 1, 1, fc=col_net))
                    shared_labels.append(lbl_net)
                    shared_added.add(lbl_net)
                if lbl_single not in shared_added:
                    shared_handles.append(plt.Rectangle((0, 0), 1, 1, fc=col_single))
                    shared_labels.append(lbl_single)
                    shared_added.add(lbl_single)

        # xticks: group labels (use "Wärmeerzeuger" for heat group)
        xtick_labels = []
        for grp_name, grp_devs in groups:
            if grp_name == "HEAT_GROUP":
                xtick_labels.append("Wärmeerzeuger")
            else:
                xtick_labels.append(label_map.get(grp_name, grp_name))

        ax.set_xticks(x)
        ax.set_xticklabels(xtick_labels, fontsize=fontsize)
        ax.set_title(sub_titel, fontsize=fontsize )
        if plot_tes_only:
            ax.set_ylabel("Speicherkapazität in kWh", fontsize=fontsize)
        else:
            ax.set_ylabel("Anlagenleistung in kW", fontsize=fontsize)
        ax.grid(axis="y", alpha=0.4)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

        out[sc] = {"network": caps_network, "single": caps_single}

    # draw global legend (device x compare entries)
    if shared_handles and shared_labels:
        ncol = min(6, max(2, len(shared_labels) // 2))
        fig.legend(
            shared_handles,
            shared_labels,
            loc="lower center",
            ncol=ncol,
            frameon=False,
            bbox_to_anchor=(0.5, -0.02),
            fontsize=max(9, fontsize - 1),
        )

    # ensure space for legend and save without clipping
    fig.subplots_adjust(bottom=0.20)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    plot_name = f"{titel}.png" if titel else "device_capacities_three_subplots_stacked.png"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out






if __name__ == "__main__":
    compare_item1="VW"
    compare_item2="QW"
    compare_short1 = "VW"
    compare_short2 = "QW"

    district2 = "ghd6"
    district1 = "residential2"
    district3 = "mixed1"

    # district2 = "residential0"
    # district1 = "residential2"
    # district3 = "mixed1"

    # district3 = "residential0"
    # district2 = "residential2"
    # district1 = "residential3"

    name2 = "Gewerbequartier"
    name1 = "Wohnquartier 1"
    name3 = "Mischquartier"

    # name2 = "Wohnquartier 2"
    # name1 = "Wohnquartier 1"
    # name3 = "Mischquartier"

    # name3 = "Wohnquartier 2"
    # name2 = "Wohnquartier 1"
    # name1 = "Wohnquartier 3"
    
    
    fontsize = 14

    power_demand={}
    power_demand["ghd6"] = 2276.0
    power_demand["residential2"] = 335.7
    power_demand["mixed1"] = 405.6
    power_demand["residential0"] = 269.4
    power_demand["residential3"] = 634.2

    plot_device_capacities_three_subplots_stacked_from_csv(
        scenario_names=[district1, district2, district3],
        subplot_titles=[name1, name2, name3],
        fontsize=fontsize,
        show=True,
        exclude_devices=["TES", "STC"],
        show_percent_box=True,
        titel="Vergleich der Anlagen-Leistungen (3 Quartiere) gestapelt",
        compare_item1=compare_item1, compare_item2=compare_item2
    )

    plot_co2_three_subplots_from_csv(
    scenario_names=[district1, district2, district3],
    subplot_titles=[name1, name2, name3],
    fontsize=fontsize,
    show=False,
    show_percent_box=True,
    titel="CO₂-Emissionen (3 Quartiere)",
    compare_item1=compare_item1, compare_item2=compare_item2
    )

    plot_tac_three_subplots_from_csv(
    scenario_names=[district1, district2, district3],
    subplot_titles=[name1, name2, name3],
    fontsize=fontsize,
    show=False,
    show_percent_box=True,
    titel="TAC (3 Quartiere)",
    compare_item1=compare_item1, compare_item2=compare_item2
    )

    plot_power_export_by_year_from_csv(district3, titel="Stromeinspeisung im " + f"{name3}", show=False, 
                                       show_percent_box=True, compare_short1=compare_short1, compare_short2=compare_short2,
                                       fontsize=fontsize)





    plot_power_import_two_subplots_from_csv(
        scenario_names=[district1, district2],
        show=False,
        show_percent_box=True,
        subplot_titles=[name1, name2],
        fontsize=fontsize,
        compare_item1=compare_item1, compare_item2=compare_item2,
        compare_short1=compare_short1, compare_short2=compare_short2,
    )

    plot_device_capacities_three_subplots_from_csv(
        scenario_names=[district1, district2, district3],
        subplot_titles=[name1, name2, name3],
        plot_tes_only= True,
        fontsize=fontsize,
        show=False,
        exclude_devices=["HP","EB", "BBOI","PV"],
        show_percent_box=False,
        titel="Vergleich der Speicherkapazitäten (3 Quartiere)",
        compare_item1=compare_item1, compare_item2=compare_item2
    )



    plot_power_import_sum_two_subplots_from_csv(
        scenario_names=[district1, district3],
        show=False,
        show_percent_box=True,
        subplot_titles=[name1, name3],
        fontsize=14,
        compare_item1=compare_item1, compare_item2=compare_item2,
        compare_short1=compare_short1, compare_short2=compare_short2,
    )



    plot_device_capacities_three_subplots_from_csv(
        scenario_names=[district1, district2, district3],
        subplot_titles=[name1, name2, name3],
        fontsize=fontsize,
        show=False,
        exclude_devices=["TES", "STC"],
        show_percent_box=True,
        titel="Vergleich der Anlagen-Leistungen (3 Quartiere)",
        compare_item1=compare_item1, compare_item2=compare_item2
    )


 

    




 

    # plot_lcoe_three_subplots_from_csv(
    #     scenario_names=[district1, district2, district3],
    #     subplot_titles=[name1, name2, name3],
    #     fontsize=fontsize,
    #     show=False,
    #     show_percent_box=True,
    #     titel="Energiegestehungskosten (3 Quartiere)",
    #     compare_item1=compare_item1, compare_item2=compare_item2
    # )

    # plot_power_import_three_subplots_from_csv(
    #     scenario_names=[district1, district2, district3],
    #     show=False,
    #     show_percent_box=True,
    #     subplot_titles=[name1, name2, name3],
    #     fontsize=14,
    #     compare_item1=compare_item1, compare_item2=compare_item2,
    #     compare_short1=compare_short1, compare_short2=compare_short2,
    # )


    # plot_lcoe_sum_from_three_scenarios(
    #     scenario_names=[district1, district2, district3],
    #     show=False,show_percent_box=True,
    #     titel="LCOE als Summe der Quartiere je Jahr", 
    #     compare_item1=compare_item1, compare_item2=compare_item2, 
    #     compare_short1=compare_short1, compare_short2=compare_short2, power_demand=power_demand
    #     )
    
    # plot_power_export_by_year_from_csv(district1, titel="Stromeinspeisung im " + f"{name1}", show=False, show_percent_box=True, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_power_export_by_year_from_csv(district2, titel=" ", show=False, show_percent_box=True, compare_short1=compare_short1, compare_short2=compare_short2)

    

   


    
    # plot_tac_sum_from_three_scenarios(
    #     scenario_names=[district1, district2, district3],show=False,show_percent_box=True,
    #     titel="Jährliche Gesamtkosten als Summe der Quartiere und der Jahre", 
    #     compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2
    # )
    
    # plot_tac_by_year_sum_from_three_scenarios(scenario_names=[district1, district2, district3],show=False,show_percent_box=True,
    # titel="Jährliche Gesamtkosten als Summe der drei Quartiere", 
    # compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    
    # plot_co2_sum_from_three_scenarios(scenario_names=[district1, district2, district3],show=False,show_percent_box=True,
    # titel="CO₂-Emissionen als Summe der Quartiere und der Jahre", 
    # compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    
    #plot_co2_by_year_sum_from_three_scenarios(scenario_names=[district1, district2, district3],show=False,show_percent_box=True,
    # titel="CO₂-Emissionen als Summe der drei Quartiere", compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)

    # plot_tes_volume_from_csv( scenario_name=district1, show=False, show_percent_box=True,
    # titel="Volumen thermischer Speicher im  " + f"{name1}",
    # compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_tes_volume_from_csv( scenario_name=district2, show=False, show_percent_box=True,titel="Volumen thermischer Speicher im  " + f"{name2}", compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_tes_volume_from_csv( scenario_name=district3, show=False, show_percent_box=True,titel="Volumen thermischer Speicher im  " + f"{name3}", compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)

    # plot_device_capacities_from_csv(scenario_name=district1, show=False, exclude_devices = ["TES", "STC", "EB"], show_percent_box=True, titel="Vergleich der Anlagen-Leistungen im " + f"{name1}", compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_device_capacities_from_csv(scenario_name=district2, show=False, exclude_devices = ["TES", "STC", "EB"], show_percent_box=True, titel="Vergleich der Anlagen-Leistungen im " + f"{name2}", compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_device_capacities_from_csv(scenario_name=district3, show=False, exclude_devices = ["TES", "STC", "EB"], show_percent_box=True, titel="Vergleich der Anlagen-Leistungen im " + f"{name3}", compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)

    # plot_device_capacities_from_csv(scenario_name=district1, show=False, exclude_devices = ["PV", "HP", "BCHP", "BBOI", "EB"], show_percent_box=True, titel="Vergleich der Speicherauslegung im " + f"{name1}", plot_tes_only=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_device_capacities_from_csv(scenario_name=district2, show=False, exclude_devices = ["PV", "HP", "BCHP", "BBOI", "EB"], show_percent_box=True, titel="Vergleich der Speicherauslegung im " + f"{name2}", plot_tes_only=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_device_capacities_from_csv(scenario_name=district3, show=False, exclude_devices = ["PV", "HP", "BCHP", "BBOI", "EB"], show_percent_box=True, titel="Vergleich der Speicherauslegung im " + f"{name3}", plot_tes_only=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)

    plot_heat_generation_by_year_from_csv(district1, titel="Wärmeproduktion im " + f"{name1}", show=False, compare_short1=compare_short1, compare_short2=compare_short2)
    plot_heat_generation_by_year_from_csv(district2, titel="Wärmeproduktion im " + f"{name2}", show=False, compare_short1=compare_short1, compare_short2=compare_short2)
    plot_heat_generation_by_year_from_csv(district3, titel="Wärmeproduktion im " + f"{name3}", show=False, compare_short1=compare_short1, compare_short2=compare_short2)

    # plot_power_import_by_year_from_csv(district1, titel="Strombezug im " + f"{name1}", show=False, show_percent_box=True, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_power_import_by_year_from_csv(district2, titel="Strombezug im " + f"{name2}", show=False, show_percent_box=True, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_power_import_by_year_from_csv(district3, titel="Strombezug im " + f"{name3}", show=False, show_percent_box=True, compare_short1=compare_short1, compare_short2=compare_short2)


    # plot_lcoe_by_year_from_csv(district1, titel="Energiegestehungskosten im " + f"{name1}", show=False, show_percent_box=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_lcoe_by_year_from_csv(district2, titel="Energiegestehungskosten im " + f"{name2}", show=False, show_percent_box=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_lcoe_by_year_from_csv(district3, titel="Energiegestehungskosten im " + f"{name3}", show=False, show_percent_box=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)

    # plot_co2_by_year_from_csv(district1, titel="CO₂-Emissionen im " + f"{name1}", show=False, show_percent_box=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_co2_by_year_from_csv(district2, titel="CO₂-Emissionen im " + f"{name2}", show=False, show_percent_box=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)
    # plot_co2_by_year_from_csv(district3, titel="CO₂-Emissionen im " + f"{name3}", show=False, show_percent_box=True, compare_item1=compare_item1, compare_item2=compare_item2, compare_short1=compare_short1, compare_short2=compare_short2)