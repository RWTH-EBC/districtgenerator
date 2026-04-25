import matplotlib.pyplot as plt
import os
import numpy as np
import csv
import matplotlib.gridspec as gridspec

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
    fontsize=14,
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
        "EB": "Elektrischer\nKessel",
        "BOI": "Erdgas-\nkessel",
        "BBOI": "Biomasse-\nkessel",
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
        plt.bar(x - width/2, y_network, width=width, color="#D40000", label="verbundweise")
        plt.bar(x + width/2, y_single, width=width, color="#55585C", label="quartiersweise")

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
                    fontsize=fontsize,
                    bbox=dict(
                        boxstyle="square,pad=0.45",
                        facecolor="#D40000",
                        edgecolor="#D40000",
                        linewidth=1.5,
                    ),
                    zorder=5,
                )

        plt.xticks(x, xtick_labels, fontsize=fontsize)
        if plot_tes_only:
            plt.ylabel("Speicherkapazität in kWh", fontsize=fontsize)
            # plt.title(titel or f"Speicherauslegung im Szenario '{sc}'", fontsize=fontsize)
        else:
            plt.ylabel("Anlagenleistung in kW", fontsize=fontsize)
        plt.xlabel("")
        # plt.title(titel or f"Anlagenleistungen im Szenario '{sc}'", fontsize=fontsize)
        plt.grid(axis="y", alpha=0.4)
        plt.legend()
        plt.tight_layout()

        plot_path = os.path.join(plots_dir, titel + ".pdf") if titel else os.path.join(plots_dir, f"device_capacities_compare_{sc}.pdf")
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
        #plt.title(titel or sc, pad=12)
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

        plot_path = os.path.join(plots_dir, f"heat_generation_by_year_compare_{sc}.pdf")
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

        plt.figure(figsize=(8, 4))
        width = 0.5

        # Hauptnetz-Balken
        colors_main = ["#E43D30" if i % 2 == 0 else "#B9BABC" for i in range(len(x))]
        plt.bar(x, y_main, width=width, color=colors_main)

        # Verbundnetz gestapelt
        colors_net = ["#8C1D17" if i % 2 == 0 else "#8A8B8D" for i in range(len(x))]
        plt.bar(x, y_net, width=width, bottom=y_main, color=colors_net)

        # Anteil aus Verbundnetz im dunkelroten Bereich (nur linker Balken = Verbund)
        for i in range(len(years)):
            main_vb = vals_vb_main[i]
            net_vb = vals_vb_net[i]
            total_vb = main_vb + net_vb
            if total_vb <= 0:
                continue

            pct_net = (net_vb / total_vb) * 100.0
            if pct_net <= 0:
                continue

            pct_txt = f"{pct_net:.0f}%".replace(".", ",")
            x_pos = x[2 * i]                      # linker Balken (VB)
            y_pos = main_vb + net_vb / 2.0        # Mitte des dunkelroten Segments
            va = "center"

            # Wenn Segment sehr klein ist -> Label oberhalb platzieren
            if net_vb < 0.08 * max(total_vb, 1.0):
                y_pos = main_vb + net_vb + 0.03 * max(total_vb, 1.0)
                va = "bottom"

            plt.text(
                x_pos,
                y_pos,
                pct_txt,
                ha="center",
                va=va,
                color="black",
                fontsize=10,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.25",
                    facecolor="#B9BABC",
                    edgecolor="#B9BABC",
                    linewidth=1.0,
                ),
                zorder=7,
                clip_on=False,  # darf über den Balken / Achsenbereich hinausragen
            )
        plt.xticks(x, labels)
        plt.ylabel("Energie in MWh")
        #plt.title(titel or sc)
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
                bbox_to_anchor=(0.5, -0.16),
                ncol=2,
                frameon=False,
            )

        plt.tight_layout(rect=[0, 0.02, 1, 1])

        plot_path = os.path.join(plots_dir, titel + ".pdf")
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
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
):
    """
    Plot yearly electricity import (MWh) as paired bars (Verbund vs Einzeln).

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

            vb_main.append(vb.get(y, {}).get("to_el_main_grid_total", 0.0))
            vb_net.append(vb.get(y, {}).get("to_network_total", 0.0))

            ez_main.append(ez.get(y, {}).get("to_el_main_grid_total", 0.0))
            ez_net.append(ez.get(y, {}).get("to_network_total", 0.0))

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

        plt.figure(figsize=(8, 4))
        width = 0.5

        # Hauptnetz-Balken
        colors_main = ["#E43D30" if i % 2 == 0 else "#B9BABC" for i in range(len(x))]
        plt.bar(x, y_main, width=width, color=colors_main)

        # Verbundnetz gestapelt
        colors_net = ["#8C1D17" if i % 2 == 0 else "#8A8B8D" for i in range(len(x))]
        plt.bar(x, y_net, width=width, bottom=y_main, color=colors_net)

                # Anteil to_network_total / (to_network_total + to_el_main_grid_total)
        # nur linker Balken je Jahr (Verbund), nur wenn > 0 %
        for i in range(len(years)):
            main_vb = vals_vb_main[i]   # to_el_main_grid_total (Verbund)
            net_vb = vals_vb_net[i]     # to_network_total (Verbund)
            total_vb = main_vb + net_vb
            if total_vb <= 0:
                continue

            pct_net = (net_vb / total_vb) * 100.0
            if pct_net <= 0:
                continue

            pct_txt = f"{pct_net:.0f}%".replace(".", ",")
            x_pos = x[2 * i]                 # linker Balken (VB)
            y_pos = main_vb + net_vb / 2.0   # Mitte dunkelrotes Segment
            va = "center"

            # Bei kleinem Segment: Box oberhalb
            if net_vb < 0.08 * max(total_vb, 1.0):
                y_pos = main_vb + net_vb + 0.03 * max(total_vb, 1.0)
                va = "bottom"

            plt.text(
                x_pos,
                y_pos,
                pct_txt,
                ha="center",
                va=va,
                color="black",
                fontsize=10,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.25",
                    facecolor="#B9BABC",
                    edgecolor="#B9BABC",
                    linewidth=1.0,
                ),
                zorder=7,
                clip_on=False,
            )

        plt.xticks(x, labels)
        plt.ylabel("Energie in MWh")
        # plt.title(titel or sc)
        plt.grid(axis="y", alpha=0.4)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)

        handles, legend_labels = [], []
        if np.any(vals_vb_main > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#E43D30"))
            legend_labels.append("Verbund Stromeinspeisung in das Hauptnetz")
        if np.any(vals_ez_main > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#B9BABC"))
            legend_labels.append("Einzeln Stromeinspeisung in das Hauptnetz")
        if np.any(vals_vb_net > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8C1D17"))
            legend_labels.append("Verbund Stromeinspeisung in das Verbundnetz")
        if np.any(vals_ez_net > 0):
            handles.append(plt.Rectangle((0, 0), 1, 1, fc="#8A8B8D"))
            legend_labels.append("Einzeln Stromeinspeisung in das Verbundnetz")

        if handles:
            plt.legend(
                handles,
                legend_labels,
                loc="upper center",
                bbox_to_anchor=(0.4, -0.15),
                ncol=2,
                frameon=False,
            )

        plt.tight_layout(rect=[0, 0, 1, 1])

        plot_path = os.path.join(plots_dir, titel + ".pdf")
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
        plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label="verbundweise")
        plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label="quartiersweise")

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
        # plt.title(titel or f"Energiegestehungskosten im Szenario '{sc}'")
        plt.grid(axis="y", alpha=0.4)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)
        plt.legend()
        plt.tight_layout()

        plot_path = os.path.join(
            plots_dir,
            f"lcoe_by_year_compare_{sc}.pdf" if not titel else f"{titel}.pdf"
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
        plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label="verbundweise")
        plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label="quartiersweise")

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
        # plt.title(titel or f"CO₂-Emissionen im Szenario '{sc}'")
        plt.grid(axis="y", alpha=0.4)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)
        plt.legend()
        plt.tight_layout()

        plot_name = f"co2_by_year_compare_{sc}.pdf" if not titel else f"{titel}.pdf"
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
    labels = ["verbundweise", "quartiersweise"]
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
    plt.ylabel("TAC-Summe in € pro Jahr")
    # plt.title(titel or "TAC-Summe der drei Quartiere: Verbund vs. Einzeloptimierung")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.tight_layout()

    plot_name = "tac_sum_three_quarters.pdf" if not titel else f"{titel}.pdf"
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
    show=True,
    titel=None,
    show_percent_box=False,
):
    """
    Plot TES-Volumen (device='TES', metric='vol_liter') als Balkenvergleich:
    - Verbund  (<scenario>_network_results.csv)
    - Einzeln  (<scenario>_results.csv)

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

        vb_m3 = _read_tes_volume_m3(network_path)
        ez_m3 = _read_tes_volume_m3(single_path)

        x = np.arange(2)
        y = [vb_m3, ez_m3]
        labels = ["verbundweise", "quartiersweise"]
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
        # plt.title(titel or f"TES-Volumen im Szenario '{sc}'")
        plt.grid(axis="y", alpha=0.35)
        plt.ticklabel_format(axis="y", style="plain", useOffset=False)
        plt.tight_layout()

        plot_name = f"tes_volume_{sc}.pdf" if not titel else f"{titel}.pdf"
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
    show=True,
    titel=None,
    show_percent_box=False,
):
    """
    Plot CO2-Summe (3 Quartiere) für Verbund vs. Einzeloptimierung.

    Erwartet:
    - scenario_names: Liste/Tuple mit genau 3 Szenario-Namen
    - Dateien je Szenario:
      - <scenario>_network_results.csv  (Verbund)
      - <scenario>_results.csv          (Einzeln)

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
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")

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
    labels = ["verbundweise", "quartiersweise"]
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
    plt.ylabel("CO₂-Emissionen in t")
    # plt.title(titel or "CO₂-Summe der drei Quartiere: Verbund vs. Einzeloptimierung")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.tight_layout()

    plot_name = "co2_sum_three_quarters.pdf" if not titel else f"{titel}.pdf"
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
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
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

    def _read_tac_and_yearly_supply(csv_path):
        tac = 0.0
        yearly_supply = {}  # {year: heat+power}

        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                cat = str(row.get("category", "")).strip()
                metric = str(row.get("metric", "")).strip()

                # TAC
                if cat == "optimization" and metric == "tac_distr":
                    v = _parse_value(row.get("value"))
                    try:
                        tac += float(v)
                    except Exception:
                        pass
                    continue

                # Yearly heat/power production
                if cat == "yearly_totals" and metric in ("total_heat_supply_by_year", "total_power_supply_by_year"):
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

                    yearly_supply[y] = yearly_supply.get(y, 0.0) + val

        return tac, yearly_supply

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    total_tac_vb = 0.0
    total_tac_ez = 0.0
    supply_vb = {}
    supply_ez = {}

    for sc in scenario_names:
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")

        if not os.path.isfile(network_path):
            raise FileNotFoundError(f"Missing file: {network_path}")
        if not os.path.isfile(single_path):
            raise FileNotFoundError(f"Missing file: {single_path}")

        tac_vb, ys_vb = _read_tac_and_yearly_supply(network_path)
        tac_ez, ys_ez = _read_tac_and_yearly_supply(single_path)

        total_tac_vb += tac_vb
        total_tac_ez += tac_ez

        for y, v in ys_vb.items():
            supply_vb[y] = supply_vb.get(y, 0.0) + v
        for y, v in ys_ez.items():
            supply_ez[y] = supply_ez.get(y, 0.0) + v

    years = sorted(set(supply_vb.keys()) | set(supply_ez.keys()))
    if not years:
        raise ValueError("Keine yearly_totals-Daten für Wärme/Strom gefunden.")

    lcoe_vb = []
    lcoe_ez = []
    for y in years:
        den_vb = supply_vb.get(y, 0.0)
        den_ez = supply_ez.get(y, 0.0)
        lcoe_vb.append((total_tac_vb / den_vb) if den_vb > 0 else 0.0)
        lcoe_ez.append((total_tac_ez / den_ez) if den_ez > 0 else 0.0)

    x = np.arange(len(years))
    width = 0.35
    labels = [str(base_calendar_year + y) for y in years]

    plt.figure(figsize=(8, 4.8))
    plt.bar(x - width / 2, lcoe_vb, width=width, color="#D40000", label="verbundweise")
    plt.bar(x + width / 2, lcoe_ez, width=width, color="#55585C", label="quartiersweise")

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
                fontsize=11,
                bbox=dict(
                    boxstyle="square,pad=0.3",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.1,
                ),
            )

    plt.xticks(x, labels)
    plt.ylabel("Energiegestehungskosten in €/MWh")
    # plt.title(titel or "LCOE (Summe aus 3 Quartieren): Verbund vs. Einzeloptimierung")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.legend()
    plt.tight_layout()

    plot_name = "lcoe_sum_three_quarters_by_year.pdf" if not titel else f"{titel}.pdf"
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
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
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
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")

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
    plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label="verbundweise")
    plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label="quartiersweise")

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
    plt.ylabel("Jährliche Gesamtkosten in €/a")
    # plt.title(titel or "Jährliche Gesamtkosten (Summe aus 3 Quartieren)")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.legend()
    plt.tight_layout()

    plot_name = "tac_by_year_sum_three_quarters.pdf" if not titel else f"{titel}.pdf"
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
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
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
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")

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
    plt.bar(x - width / 2, y_vb, width=width, color="#D40000", label="verbundweise")
    plt.bar(x + width / 2, y_ez, width=width, color="#55585C", label="quartiersweise")

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
    plt.ylabel("Jährliche CO₂-Emissionen in t/a")
    #plt.title(titel or "Jährliche CO₂-Emissionen (Summe aus 3 Quartieren)")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.legend()
    plt.tight_layout()

    plot_name = "co2_by_year_sum_three_quarters.pdf" if not titel else f"{titel}.pdf"
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
    show=True,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    subplot_titles=None,
    show_percent_box=False,
    plot_tes_only=False,
    fontsize=12,

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
        "TES": "therm. Speicher",
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

    fig = plt.figure(figsize=(9, 8))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])   # oben links
    ax2 = fig.add_subplot(gs[0, 1])   # oben rechts
    ax3 = fig.add_subplot(gs[1, :])   # unten über beide Spalten
    axes = [ax1, ax2, ax3]
    out = {}

    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_results.csv")


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
        # if not devices:
        #     ax.axis("off")
        #     ax.text(0.5, 0.5, f"Keine Geräte nach Filter\n{sc}", ha="center", va="center")
        #     continue

        x = np.arange(len(devices))
        width = 0.32

        y_network = [caps_network.get(d, 0.0) for d in devices]
        y_single = [caps_single.get(d, 0.0) for d in devices]
        xtick_labels = [label_map.get(d, d) for d in devices]

        ax.bar(x - width / 2, y_network, width=width, color="#D40000", label="verbundweise")
        ax.bar(x + width / 2, y_single, width=width, color="#55585C", label="quartiersweise")

        ymax = max(max(y_network) if y_network else 0, max(y_single) if y_single else 0, 1.0)
        if show_percent_box:
            ax.set_ylim(0, ymax * 1.35)
            y_offset = ymax * 0.08

            for i, (yn, ys) in enumerate(zip(y_network, y_single)):
                if ys == 0:
                    text = "n/a" if yn == 0 else f"+{yn:.0f} kWh"
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
        ax.set_title(sub_titel, fontsize=fontsize + 1)
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
        )

    fig.tight_layout(rect=[0, 0.06, 1, 1])

    plot_name = f"{titel}.pdf" if titel else "device_capacities_three_subplots.pdf"
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
    compare_short, 
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    subplot_titles=None,
    base_calendar_year=2025,
    show_percent_box=False,
    fontsize=12,
):
    """
    Erstellt eine gemeinsame Abbildung mit 3 Subplots für LCOE (2 oben, 1 unten),
    jeweils wie plot_lcoe_by_year_from_csv für ein Szenario.
    """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")
    if not compare_short:
        raise ValueError("compare_short darf nicht leer sein.")

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

    fig = plt.figure(figsize=(11, 8))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    axes = [ax1, ax2, ax3]

    out = {}
    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short}_results.csv")

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

        ax.bar(x - width / 2, y_vb, width=width, color="#D40000", label="verbundweise")
        ax.bar(x + width / 2, y_ez, width=width, color="#55585C", label="quartiersweise")

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

    plot_name = f"{titel}.pdf" if titel else "lcoe_three_subplots.pdf"
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
    compare_short,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    subplot_titles=None,
    base_calendar_year=2025,
    show_percent_box=False,
    fontsize=12,
):
    """
    Erstellt eine gemeinsame Abbildung mit 3 Subplots für CO2-Emissionen
    (2 oben, 1 unten), jeweils wie plot_co2_by_year_from_csv für ein Szenario.
     """
    if not isinstance(scenario_names, (list, tuple)) or len(scenario_names) != 3:
        raise ValueError("scenario_names muss genau 3 Szenario-Namen enthalten.")
    if not compare_short:
        raise ValueError("compare_short darf nicht leer sein.")

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

    fig = plt.figure(figsize=(11, 8))
    gs = gridspec.GridSpec(2, 2, figure=fig, height_ratios=[1, 1.05], hspace=0.35, wspace=0.25)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    axes = [ax1, ax2, ax3]

    out = {}
    shared_handles = None
    shared_labels = None

    for ax, sc, sub_titel in zip(axes, scenario_names, subplot_titles):
        network_path = os.path.join(base_dir, f"{sc}_{compare_short}_network_results.csv")
        single_path = os.path.join(base_dir, f"{sc}_{compare_short}_results.csv")

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

        ax.bar(x - width / 2, y_vb, width=width, color="#D40000", label="verbundweise")
        ax.bar(x + width / 2, y_ez, width=width, color="#55585C", label="quartiersweise")

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
        ax.set_ylabel("Jährliche CO₂-Emissionen in t/a", fontsize=fontsize)
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

    plot_name = f"{titel}.pdf" if titel else "co2_three_subplots.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return out


if __name__ == "__main__":
    # district1 = "residential2"
    # district2 = "mixed1"
    # district3 = "residential0"
    # name1 = "Wohnquartier 2"
    # name2 = "Mischquartier"
    # name3 = "Wohnquartier 1"
    district1 = "ghd6"
    district2 = "residential2"
    district3 = "mixed1"

    name1 = "Gewerbequartier"
    name2 = "Wohnquartier 1"
    name3 = "Mischquartier"
    fontsize = 11
    compare_short = "Basis"

    # district1 = "1rural"
    # district2 = "4zb"
    # district3 = "6urban"
    # name1 = "ländlichen Quartier"
    # name2 = "vorstädtischen Quartier"
    # name3 = "urbanen Quartier"

    # plot_device_capacities_three_subplots_from_csv(
    #     scenario_names=[district1, district2, district3],
    #     subplot_titles=[name1, name2, name3],
    #     fontsize=fontsize,
    #     show=True,
    #     exclude_devices=["TES", "STC"],
    #     show_percent_box=True,
    #     titel="Vergleich der Anlagen-Leistungen (3 Quartiere)",
    #     plot_tes_only=False
    # )

    # plot_device_capacities_three_subplots_from_csv(
    #     scenario_names=[district1, district2, district3],
    #     subplot_titles=[name1, name2, name3],
    #     fontsize=fontsize,
    #     show=True,
    #     exclude_devices=["PV", "HP", "BCHP", "BBOI", "EB", "TES"],
    #     show_percent_box=True,
    #     titel="Vergleich der Anlagen-Leistungen (3 Quartiere)",
    #     plot_tes_only=True
    # )

    plot_lcoe_three_subplots_from_csv(
        scenario_names=[district1, district2, district3],
        compare_short=compare_short, 
        subplot_titles=[name1, name2, name3],
        fontsize=fontsize,
        show=True,
        show_percent_box=True,
        titel="Energiegestehungskosten (3 Quartiere)"
    )

    plot_co2_three_subplots_from_csv(
    scenario_names=[district1, district2, district3],
    compare_short=compare_short, 
    subplot_titles=[name1, name2, name3],
    fontsize=fontsize,
    show=True,
    show_percent_box=True,
    titel="CO₂-Emissionen (3 Quartiere)"
    )

    
    
    # plot_tac_sum_from_three_scenarios(scenario_names=[district1, district2, district3],show=True,show_percent_box=True,titel="Jährliche Gesamtkosten als Summe der Quartiere und der Jahre")
    # plot_tac_by_year_sum_from_three_scenarios(scenario_names=[district1, district2, district3],show=True,show_percent_box=True,titel="Jährliche Gesamtkosten als Summe der drei Quartiere")
    # plot_co2_sum_from_three_scenarios(scenario_names=[district1, district2, district3],show=True,show_percent_box=True,titel="CO₂-Emissionen als Summe der Quartiere und der Jahre")
    # plot_co2_by_year_sum_from_three_scenarios(scenario_names=[district1, district2, district3],show=True,show_percent_box=True,titel="CO₂-Emissionen als Summe der drei Quartiere")
    # plot_lcoe_sum_from_three_scenarios(scenario_names=[district1, district2, district3],show=True,show_percent_box=True,titel="Energiegestehungskosten als Summe der drei Quartiere")
    # plot_tes_volume_from_csv( scenario_name=district1, show=True, show_percent_box=True,titel="Volumen thermischer Speicher im  " + f"{name1}")
    # plot_tes_volume_from_csv( scenario_name=district2, show=True, show_percent_box=True,titel="Volumen thermischer Speicher im  " + f"{name2}")
    # plot_tes_volume_from_csv( scenario_name=district3, show=True, show_percent_box=True,titel="Volumen thermischer Speicher im  " + f"{name3}")

    # plot_device_capacities_from_csv(scenario_name=district1, fontsize=fontsize, show=True, exclude_devices = ["TES", "STC", "EB"], show_percent_box=True, titel="Vergleich der Anlagen-Leistungen im " + f"{name1}")
    # plot_device_capacities_from_csv(scenario_name=district2, fontsize=fontsize, show=True, exclude_devices = ["TES", "STC", "EB"], show_percent_box=True, titel="Vergleich der Anlagen-Leistungen im " + f"{name2}")
    # plot_device_capacities_from_csv(scenario_name=district3, fontsize=fontsize, show=True, exclude_devices = ["TES", "STC", "EB"], show_percent_box=True, titel="Vergleich der Anlagen-Leistungen im " + f"{name3}")

    # plot_device_capacities_from_csv(scenario_name=district1, show=True, exclude_devices = ["PV", "HP", "BCHP", "BBOI", "EB"], show_percent_box=True, titel="Vergleich der Speicherauslegung im " + f"{name1}", plot_tes_only=True)
    # plot_device_capacities_from_csv(scenario_name=district2, show=True, exclude_devices = ["PV", "HP", "BCHP", "BBOI", "EB"], show_percent_box=True, titel="Vergleich der Speicherauslegung im " + f"{name2}", plot_tes_only=True)
    # plot_device_capacities_from_csv(scenario_name=district3, show=True, exclude_devices = ["PV", "HP", "BCHP", "BBOI", "EB"], show_percent_box=True, titel="Vergleich der Speicherauslegung im " + f"{name3}", plot_tes_only=True)

    # plot_heat_generation_by_year_from_csv(district1, titel="Wärmeproduktion im " + f"{name1}", show=True)
    # plot_heat_generation_by_year_from_csv(district2, titel="Wärmeproduktion im " + f"{name2}", show=True)
    # plot_heat_generation_by_year_from_csv(district3, titel="Wärmeproduktion im " + f"{name3}", show=True)
    
    # plot_power_import_by_year_from_csv(district1, titel="Strombezug im " + f"{name1}", show=True, show_percent_box=True)
    # plot_power_import_by_year_from_csv(district2, titel="Strombezug im " + f"{name2}", show=True, show_percent_box=True)
    # plot_power_import_by_year_from_csv(district3, titel="Strombezug im " + f"{name3}", show=True, show_percent_box=True)

    # plot_power_export_by_year_from_csv(district1, titel="Stromeinspeisung im " + f"{name1}", show=True, show_percent_box=True)
    # plot_power_export_by_year_from_csv(district2, titel="Stromeinspeisung im " + f"{name2}", show=True, show_percent_box=True)
    # plot_power_export_by_year_from_csv(district3, titel="Stromeinspeisung im " + f"{name3}", show=True, show_percent_box=True)

    # plot_lcoe_by_year_from_csv(district1, titel="Energiegestehungskosten im " + f"{name1}", show=True, show_percent_box=True)
    # plot_lcoe_by_year_from_csv(district2, titel="Energiegestehungskosten im " + f"{name2}", show=True, show_percent_box=True)
    # plot_lcoe_by_year_from_csv(district3, titel="Energiegestehungskosten im " + f"{name3}", show=True, show_percent_box=True)

    # plot_co2_by_year_from_csv(district1, titel="CO₂-Emissionen im " + f"{name1}", show=True, show_percent_box=True)
    # plot_co2_by_year_from_csv(district2, titel="CO₂-Emissionen im " + f"{name2}", show=True, show_percent_box=True)
    # plot_co2_by_year_from_csv(district3, titel="CO₂-Emissionen im " + f"{name3}", show=True, show_percent_box=True)