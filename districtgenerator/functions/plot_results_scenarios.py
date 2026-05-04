import os
import numpy as np
import matplotlib.pyplot as plt
import csv
from districtgenerator.functions.plot_results_compare import _load_single_results_file_to_dict
from matplotlib.path import Path
from matplotlib.patches import PathPatch


def load_multi_compare_results_to_dict(
    scenario_name,
    short_files=None,
    base_dir=None,
    variants=("network", "single"),
    bar_count=None,
):
    """
    Lädt eine beliebige Anzahl Ergebnisdateien für ein Szenario.
    Dateimuster:
      - network: <scenario>_<compare_short>_network_results.csv
      - single:  <scenario>_<compare_short>_results.csv
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    if isinstance(short_files, str):
        short_files = [short_files]
    short_files = list(short_files or [])
    if not short_files:
        raise ValueError("short_files darf nicht leer sein.")

    series = []
    for short in short_files:
        for v in variants:
            if v == "network":
                p = os.path.join(base_dir, f"{scenario_name}_{short}_network_results.csv")
            elif v == "single":
                p = os.path.join(base_dir, f"{scenario_name}_{short}_results.csv")
            else:
                raise ValueError(f"Unbekannte variant: {v}")

            if not os.path.isfile(p):
                raise FileNotFoundError(f"Missing result file: {p}")

            series.append({
                "short_file": short,
                "variant": v,
                "path": p,
                "data": _load_single_results_file_to_dict(p),
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(series):
            raise ValueError(f"bar_count={bar_count} ist größer als verfügbare Reihen ({len(series)}).")
        series = series[:bar_count]

    return {
        "scenario": scenario_name,
        "base_dir": base_dir,
        "series": series,
    }


def plot_device_capacities_multi_bars_from_csv(
    scenario_name,
    compare_short1=None,   # kompatibel
    compare_short2=None,   # kompatibel
    compare_item1=None,    # kompatibel
    compare_item2=None,    # kompatibel
    short_files=None,
    compare_shorts=None,   # neu: Liste beliebiger compare_shorts
    compare_items=None,    # neu: Liste Labels pro compare_short
    bar_count=None,        # neu: Anzahl Balken (gesamt)
    variants=("network", "single"),
    base_dir=None,
    result_dir=None,
    show=True,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    show_percent_box=False,
    storgae_devices=None,
    fontsize1=8,
    fontsize2=8,
):
    """
    Device-Capacity-Plot mit beliebig vielen Balken je Device.
    """
    # Fallback-Kompatibilität mit altem 2er-Interface
    if compare_shorts is None:
        compare_shorts = [c for c in [compare_short1, compare_short2] if c]

    if not compare_shorts:
        raise ValueError("Bitte compare_shorts oder compare_short1/2 angeben.")


    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/2 angeben.")

    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(short_files) != len(compare_shorts):
        raise ValueError("short_files und compare_shorts müssen gleich lang sein.")

    data = load_multi_compare_results_to_dict(
        scenario_name=scenario_name,
        short_files=short_files,
        base_dir=base_dir,
        variants=variants,
        bar_count=bar_count,
    )
    series = data["series"]

    label_by_short = {}
    if compare_items:
        for s, lbl in zip(short_files, compare_items):
            label_by_short[s] = lbl
    if compare_short1 and compare_item1:
        label_by_short[compare_short1] = compare_item1
    if compare_short2 and compare_item2:
        label_by_short[compare_short2] = compare_item2


    def _to_set(x):
        if x is None:
            return None
        if isinstance(x, str):
            return {x}
        return set(x)

    def _extract_caps(parsed_dict):
        if not parsed_dict:
            return {}
        scen_key = scenario_name if scenario_name in parsed_dict else next(iter(parsed_dict.keys()))
        scen = parsed_dict.get(scen_key, {})
        dev_cat = scen.get("device", {})
        return dev_cat.get("by_device", {}).get("capacity", {}) or {}

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    include_set = _to_set(include_devices)
    exclude_set = _to_set(exclude_devices) or set()

    preferred_order = [
        "HP", "CHP", "PV", "STC", "WT", "EB", "BOI", "BBOI", "GHP", "CC", "AC",
        "WAT", "BCHP", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "CTES", "BAT", "GS"
    ]
    label_map = {
        "HP": "Wärmepumpe", "CHP": "BHKW", "BCHP": "BBHKW", "STC": "Solarthermie",
        "WT": "Windkraft", "EB": "Elektrischer\nKessel", "BOI": "Erdgas-\nkessel",
        "BBOI": "Biomasse-\nkessel", "PV": "PV-Anlage",
    }

    # Werte je Reihe extrahieren
    cap_series = []
    for s in series:
        caps = _extract_caps(s["data"])
        cap_series.append({
            "short_file": s["short_file"],
            "compare_short": compare_shorts[short_files.index(s["short_file"])],
            "variant": s["variant"],
            "label": f"{label_by_short.get(s['short_file'], s['short_file'])} "
                     f"({'verbundweise' if s['variant']=='network' else 'quartiersweise'})",
            "caps": caps,
        })

    all_devices = set()
    for cs in cap_series:
        all_devices |= set(cs["caps"].keys())

    if include_set is not None:
        selected = [d for d in preferred_order if d in include_set and d in all_devices]
        selected += sorted([d for d in include_set if d in all_devices and d not in preferred_order])
    else:
        selected = [d for d in preferred_order if d in all_devices]
        selected += sorted([d for d in all_devices if d not in preferred_order])

    devices = [d for d in selected if d not in exclude_set]
    if not devices:
        raise ValueError("No devices left after include/exclude filtering.")

    x = np.arange(len(devices))
    n = len(cap_series)
    width = min(0.8 / max(n, 1), 0.22)

    values = []
    for cs in cap_series:
        y = np.array([float(cs["caps"].get(d, 0.0) or 0.0) for d in devices], dtype=float)
        values.append(y)

    colors = [
        "#721D13", "#242525", "#AC2B1C", "#4E4F50",
        "#DD402D" , "#757679", "#EB8C81", "#D8D8D9",
        "#F1B3AB", "#C4C5C6", "#7f7f7f", "#bcbd22"
    ]
    
    plt.figure(figsize=(8.27, 11.69))
    bars_by_series = []
    for i, cs in enumerate(cap_series):
        offset = (i - (n - 1) / 2) * width
        b = plt.bar(
            x + offset,
            values[i],
            width=width,
            color=colors[i % len(colors)],
            label=cs["label"],
        )
        bars_by_series.append(b)

    ymax = max([np.max(v) for v in values] + [1.0])

    # Prozentbox: nur falls network/single-Paar je compare_short vorhanden
    if show_percent_box:
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.06

        idx_map = {}  # short -> {"network": idx, "single": idx}
        for i, cs in enumerate(cap_series):
            idx_map.setdefault(cs["compare_short"], {})[cs["variant"]] = i

        for short, m in idx_map.items():
            if "network" not in m or "single" not in m:
                continue
            i_net, i_sin = m["network"], m["single"]
            y_net, y_sin = values[i_net], values[i_sin]
            x_net = x + (i_net - (n - 1) / 2) * width

            for k in range(len(devices)):
                if y_sin[k] == 0:
                    txt = "n/a" if y_net[k] == 0 else f"+ {y_net[k]:.0f} kWh"
                else:
                    txt = _fmt_pct((y_net[k] - y_sin[k]) / y_sin[k] * 100.0)

                plt.text(
                    x_net[k],
                    y_net[k] + y_offset,
                    txt,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=fontsize2,
                    bbox=dict(
                        boxstyle="square,pad=0.2",
                        facecolor=colors[i_net % len(colors)],
                        edgecolor=colors[i_net % len(colors)],
                        linewidth=1.0,
                    ),
                    zorder=5,
                )

    plt.xticks(x, [label_map.get(d, d) for d in devices], fontsize=fontsize1)
    if storgae_devices:
        plt.ylabel("Speicherkapazität in kWh")
    else:
        plt.ylabel("Anlagenleistung in kW")
    plt.grid(axis="y", alpha=0.35)
    plt.legend(ncol=2)
    plt.tight_layout()

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    plot_name = f"{titel}.pdf" if titel else f"device_capacities_multibars_{scenario_name}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario": scenario_name,
        "devices": devices,
        "series": [
            {
                "compare_short": cs["compare_short"],
                "variant": cs["variant"],
                "label": cs["label"],
                "values_by_device": dict(zip(devices, values[i])),
            }
            for i, cs in enumerate(cap_series)
        ],
        "plot_path": plot_path,
        "paths": [s["path"] for s in series],
    }

def plot_device_capacities_multi_bars_from_csv_with_TES(
    scenario_name,
    compare_short1=None,
    compare_short2=None,
    compare_item1=None,
    compare_item2=None,
    compare_shorts=None,
    short_files=None,
    compare_items=None,
    bar_count=None,
    variants=("network", "single"),
    base_dir=None,
    result_dir=None,
    show=True,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    show_percent_box=False,
    fontsize1=8,
    fontsize2=8,
):
    """
    Device-Capacity-Plot mit beliebig vielen Balken je Device.
    """
    if compare_shorts is None:
        compare_shorts = [c for c in [compare_short1, compare_short2] if c]

    if not compare_shorts:
        raise ValueError("Bitte compare_shorts oder compare_short1/2 angeben.")

    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/2 angeben.")

    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(short_files) != len(compare_shorts):
        raise ValueError("short_files und compare_shorts müssen gleich lang sein.")

    data = load_multi_compare_results_to_dict(
        scenario_name=scenario_name,
        short_files=short_files,
        base_dir=base_dir,
        variants=variants,
        bar_count=bar_count,
    )
    series = data["series"]

    label_by_short = {}
    if compare_items:
        for s, lbl in zip(short_files, compare_items):
            label_by_short[s] = lbl
    if compare_short1 and compare_item1:
        label_by_short[compare_short1] = compare_item1
    if compare_short2 and compare_item2:
        label_by_short[compare_short2] = compare_item2

    def _to_set(x):
        if x is None:
            return None
        if isinstance(x, str):
            return {x}
        return set(x)

    def _extract_caps(parsed_dict):
        if not parsed_dict:
            return {}
        scen_key = scenario_name if scenario_name in parsed_dict else next(iter(parsed_dict.keys()))
        scen = parsed_dict.get(scen_key, {})
        dev_cat = scen.get("device", {})
        return dev_cat.get("by_device", {}).get("capacity", {}) or {}

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    include_set = _to_set(include_devices)
    exclude_set = _to_set(exclude_devices) or set()

    preferred_order = [
        "HP", "CHP", "PV", "STC", "WT", "EB", "BOI", "BBOI", "GHP", "CC", "AC",
        "WAT", "BCHP", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "CTES", "BAT", "GS"
    ]
    label_map = {
        "HP": "Wärmepumpe",
        "CHP": "BHKW",
        "BCHP": "BBHKW",
        "STC": "Solarthermie",
        "WT": "Windkraft",
        "EB": "Elektrischer\nKessel",
        "BOI": "Erdgas-\nkessel",
        "BBOI": "Biomasse-\nkessel",
        "PV": "PV-Anlage",
        "TES": "Thermischer Speicher",
        "BAT": "Batterie",
    }

    # Werte je Reihe extrahieren
    cap_series = []
    for s in series:
        caps = _extract_caps(s["data"])
        cap_series.append({
            "short_file": s["short_file"],
            "compare_short": compare_shorts[short_files.index(s["short_file"])],
            "variant": s["variant"],
            "label": f"{label_by_short.get(s['short_file'], s['short_file'])} "
                     f"({'verbundweise' if s['variant']=='network' else 'quartiersweise'})",
            "caps": caps,
        })

    all_devices = set()
    for cs in cap_series:
        all_devices |= set(cs["caps"].keys())

    if include_set is not None:
        selected = [d for d in preferred_order if d in include_set and d in all_devices]
        selected += sorted([d for d in include_set if d in all_devices and d not in preferred_order])
    else:
        selected = [d for d in preferred_order if d in all_devices]
        selected += sorted([d for d in all_devices if d not in preferred_order])

    devices = [d for d in selected if d not in exclude_set]
    if not devices:
        raise ValueError("No devices left after include/exclude filtering.")

    x = np.arange(len(devices))
    n = len(cap_series)
    width = min(0.8 / max(n, 1), 0.22)

    storage_devices = {"TES", "BAT"}
    has_storage = any(d in storage_devices for d in devices)

    values = []
    for cs in cap_series:
        y = np.array([float(cs["caps"].get(d, 0.0) or 0.0) for d in devices], dtype=float)
        values.append(y)

    colors = [
        "#721D13", "#242525", "#AC2B1C", "#4E4F50",
        "#DD402D" , "#757679", "#EB8C81", "#D8D8D9",
        "#F1B3AB", "#C4C5C6", "#7f7f7f", "#bcbd22"
    ]
    fig_w_mm = 155
    fig_h_mm = 120
    fig, ax1 = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))


    ax2 = ax1.twinx() if has_storage else None

    for i, cs in enumerate(cap_series):
        offset = (i - (n - 1) / 2) * width

        y_left = np.array(
            [values[i][k] if devices[k] not in storage_devices else 0.0 for k in range(len(devices))],
            dtype=float
        )
        ax1.bar(
            x + offset,
            y_left,
            width=width,
            color=colors[i % len(colors)],
            label=cs["label"],
        )

        if ax2 is not None:
            y_right = np.array(
                [values[i][k] if devices[k] in storage_devices else 0.0 for k in range(len(devices))],
                dtype=float
            )
            ax2.bar(
                x + offset,
                y_right,
                width=width,
                color=colors[i % len(colors)],
                label="_nolegend_",
            )

    left_ymax = max(
        [np.max([values[i][k] for k in range(len(devices)) if devices[k] not in storage_devices] or [0.0])
         for i in range(n)] + [1.0]
    )
    right_ymax = max(
        [np.max([values[i][k] for k in range(len(devices)) if devices[k] in storage_devices] or [0.0])
         for i in range(n)] + [1.0]
    )

    ax1.set_ylim(0, left_ymax * 1.35 if left_ymax > 0 else 1.0)
    ax1.set_ylabel("Anlagenleistung in kW")

    if ax2 is not None:
        ax2.set_ylim(0, right_ymax * 1.35 if right_ymax > 0 else 1.0)
        ax2.set_ylabel("Speicherkapazität in kWh")
        ax2.tick_params(axis="y")

    if show_percent_box:
        y_offset_left = left_ymax * 0.06
        y_offset_right = right_ymax * 0.06 if ax2 is not None else left_ymax * 0.06

        idx_map = {}
        for i, cs in enumerate(cap_series):
            idx_map.setdefault(cs["compare_short"], {})[cs["variant"]] = i

        for short, m in idx_map.items():
            if "network" not in m or "single" not in m:
                continue

            i_net, i_sin = m["network"], m["single"]
            y_net, y_sin = values[i_net], values[i_sin]
            x_net = x + (i_net - (n - 1) / 2) * width

            for k, dev in enumerate(devices):
                if y_sin[k] == 0:
                    txt = "n/a" if y_net[k] == 0 else f"+ {y_net[k]:.0f} kWh"
                else:
                    txt = _fmt_pct((y_net[k] - y_sin[k]) / y_sin[k] * 100.0)

                target_ax = ax2 if (ax2 is not None and dev in storage_devices) else ax1
                y_offset = y_offset_right if (ax2 is not None and dev in storage_devices) else y_offset_left

                target_ax.text(
                    x_net[k],
                    y_net[k] + y_offset,
                    txt,
                    ha="center",
                    va="bottom",
                    color="white",
                    fontsize=fontsize2,
                    bbox=dict(
                        boxstyle="square,pad=0.2",
                        facecolor=colors[i_net % len(colors)],
                        edgecolor=colors[i_net % len(colors)],
                        linewidth=1.0,
                    ),
                    zorder=5,
                )

    ax1.set_xticks(x)
    ax1.set_xticklabels([label_map.get(d, d) for d in devices], fontsize=fontsize1)
    ax1.grid(axis="y", alpha=0.35)

    if ax2 is None:
        handles, labels = ax1.get_legend_handles_labels()
    else:
        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        handles, labels = h1 + h2, l1 + l2

    ax1.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        ncol=2,                 # immer 2 Einträge pro Zeile
        frameon=False,
        fontsize=fontsize1,
        handlelength=1.4,
        columnspacing=0.8,
        labelspacing=0.4,
        borderaxespad=0.2,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.34)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    plot_name = f"{titel}.pdf" if titel else f"device_capacities_multibars_{scenario_name}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300, bbox_inches="tight", pad_inches=0.08)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "scenario": scenario_name,
        "devices": devices,
        "series": [
            {
                "compare_short": cs["compare_short"],
                "variant": cs["variant"],
                "label": cs["label"],
                "values_by_device": dict(zip(devices, values[i])),
            }
            for i, cs in enumerate(cap_series)
        ],
        "plot_path": plot_path,
        "paths": [s["path"] for s in series],
    }





def plot_power_import_single_year_multi_bars_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,          # <- Dateikürzel zum Laden
    compare_shorts=None,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=None,
    target_year=2030,
    bar_count=None,
    variants=("network", "single"),
):
    if scenario_name is None:
        raise ValueError("scenario_name muss gesetzt sein.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    # Backward-Compatibility
    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")

    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

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

    rel_year = target_year - base_calendar_year

    # Wichtig: Laden über short_files
    bars = []
    for short_file, scen_label in zip(short_files, compare_shorts):
        for variant in variants:
            if variant == "network":
                p = os.path.join(base_dir, f"{scenario_name}_{short_file}_network_results.csv")
            elif variant == "single":
                p = os.path.join(base_dir, f"{scenario_name}_{short_file}_results.csv")
            else:
                raise ValueError(f"Unbekannte variant: {variant}")

            if not os.path.isfile(p):
                raise FileNotFoundError(f"Missing result file: {p}")

            yearly = _read_yearly_import(p)
            y_key = rel_year if rel_year in yearly else (target_year if target_year in yearly else None)
            if y_key is None:
                raise ValueError(
                    f"Jahr {target_year} nicht in Datei gefunden: {p} "
                    f"(gesucht als {rel_year} bzw. {target_year})."
                )

            main_val = float(yearly[y_key].get("from_el_main_grid_total", 0.0))
            net_val = float(yearly[y_key].get("from_network_total", 0.0))

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "main": main_val,
                "net": net_val,
                "total": main_val + net_val,
                "path": p,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y_main = np.array([b["main"] for b in bars], dtype=float)
    y_net = np.array([b["net"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58
    ax.bar(x, y_main, width=width, color="#B9BABC", label="Stromeinspeisung in das Hauptnetz")
    ax.bar(x, y_net, width=width, bottom=y_main, color="#8A8B8D", label="Stromeinspeisung in das Verbundnetz")

    # Prozentboxen wieder aktivieren
    if show_percent_box:
        totals = y_main + y_net
        ymax = max(float(np.max(totals)) if len(totals) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)

        for i in range(len(bars)):
            total = float(totals[i])
            if total <= 0:
                continue

            pct_net = (float(y_net[i]) / total) * 100.0
            txt = f"{pct_net:.0f}%".replace(".", ",")

            line_y0 = total
            line_y1 = total + 0.05 * ymax
            box_y = line_y1 + 0.012 * ymax

            ax.plot(
                [x[i], x[i]],
                [line_y0, line_y1],
                color="#7A7A7A",
                linewidth=0.9,
                zorder=6,
                clip_on=False,
            )
            ax.text(
                x[i],
                box_y,
                txt,
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
                color="black",
                bbox=dict(
                    boxstyle="round,pad=0.22",
                    facecolor="white",
                    edgecolor="#B9BABC",
                    linewidth=0.9,
                ),
                zorder=7,
                clip_on=False,
            )

    # x-Ticks nur für Balkenpaare (Mittelpunkte)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=8)

    ax.set_xlim(x.min() - width, x.max() + width)

    ax.set_ylabel("Energie in MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)


    # Farben nach Optimierungsart
    color_main_vw = "#E43D30"  # hellrot (VW Hauptnetz)
    color_net_vw = "#8C1D17"    # dunkelrot (VW Verbundnetz)
    color_main_qw = "#B9BABC"   # QW Hauptnetz (wie vorher)
    color_net_qw = "#8A8B8D"   # QW Verbundnetz (wie vorher)

    # Zeichne Balken paarweise, mit unterschiedlicher Farbgebung für VW vs QW
    for i, b in enumerate(bars):
        if b["variant"] == "network":  # VW = linke Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_vw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_vw, label="_nolegend_")
        else:  # QW = rechte Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_qw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_qw, label="_nolegend_")

    # Legende mit vier Einträgen (VW links, QW rechts)
    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_main_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_main_qw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_qw),
    ]
    labels = [
        "Strombezug aus dem Hauptnetz VW",
        "Strombezug aus dem Verbundnetz VW",
        "Strombezug aus dem Hauptnetz QW",
        "Strombezug aus dem Verbundnetz QW",
    ]
    ax.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=2,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)



    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else f"power_import_single_year_multibars_{scenario_name}_{target_year}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"scenario": scenario_name, "target_year": target_year, "bars": bars, "plot_path": plot_path}


def plot_power_export_single_year_multi_bars_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,          # <- Dateikürzel zum Laden
    compare_shorts=None,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=None,
    target_year=2030,
    bar_count=None,
    variants=("network", "single"),
):
    if scenario_name is None:
        raise ValueError("scenario_name muss gesetzt sein.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    # Backward-Compatibility
    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")

    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

    def _read_yearly_export(csv_path):
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

    rel_year = target_year - base_calendar_year

    # Wichtig: Laden über short_files
    bars = []
    for short_file, scen_label in zip(short_files, compare_shorts):
        for variant in variants:
            if variant == "network":
                p = os.path.join(base_dir, f"{scenario_name}_{short_file}_network_results.csv")
            elif variant == "single":
                p = os.path.join(base_dir, f"{scenario_name}_{short_file}_results.csv")
            else:
                raise ValueError(f"Unbekannte variant: {variant}")

            if not os.path.isfile(p):
                raise FileNotFoundError(f"Missing result file: {p}")

            yearly = _read_yearly_export(p)
            y_key = rel_year if rel_year in yearly else (target_year if target_year in yearly else None)
            if y_key is None:
                raise ValueError(
                    f"Jahr {target_year} nicht in Datei gefunden: {p} "
                    f"(gesucht als {rel_year} bzw. {target_year})."
                )

            main_val = float(yearly[y_key].get("to_el_main_grid_total", 0.0))
            net_val = float(yearly[y_key].get("to_network_total", 0.0))

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "main": main_val,
                "net": net_val,
                "total": main_val + net_val,
                "path": p,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y_main = np.array([b["main"] for b in bars], dtype=float)
    y_net = np.array([b["net"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58
    ax.bar(x, y_main, width=width, color="#B9BABC", label="Stromeinspeisung in das Hauptnetz")
    ax.bar(x, y_net, width=width, bottom=y_main, color="#8A8B8D", label="Stromeinspeisung in das Verbundnetz")

    # Prozentboxen wieder aktivieren
    if show_percent_box:
        totals = y_main + y_net
        ymax = max(float(np.max(totals)) if len(totals) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)

        for i in range(len(bars)):
            total = float(totals[i])
            if total <= 0:
                continue

            pct_net = (float(y_net[i]) / total) * 100.0
            txt = f"{pct_net:.0f}%".replace(".", ",")

            line_y0 = total
            line_y1 = total + 0.05 * ymax
            box_y = line_y1 + 0.012 * ymax

            ax.plot(
                [x[i], x[i]],
                [line_y0, line_y1],
                color="#7A7A7A",
                linewidth=0.9,
                zorder=6,
                clip_on=False,
            )
            ax.text(
                x[i],
                box_y,
                txt,
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
                color="black",
                bbox=dict(
                    boxstyle="round,pad=0.22",
                    facecolor="white",
                    edgecolor="#B9BABC",
                    linewidth=0.9,
                ),
                zorder=7,
                clip_on=False,
            )


    # x-Ticks nur für Balkenpaare (Mittelpunkte)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=8)

    ax.set_xlim(x.min() - width, x.max() + width)

    ax.set_ylabel("Energie in MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    # Farben nach Optimierungsart
    color_main_vw = "#E43D30"  # hellrot (VW Hauptnetz)
    color_net_vw = "#8C1D17"    # dunkelrot (VW Verbundnetz)
    color_main_qw = "#B9BABC"   # QW Hauptnetz (wie vorher)
    color_net_qw = "#8A8B8D"   # QW Verbundnetz (wie vorher)

    # Zeichne Balken paarweise, mit unterschiedlicher Farbgebung für VW vs QW
    for i, b in enumerate(bars):
        if b["variant"] == "network":  # VW = linke Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_vw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_vw, label="_nolegend_")
        else:  # QW = rechte Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_qw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_qw, label="_nolegend_")

    # Legende mit vier Einträgen (VW links, QW rechts)
    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_main_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_main_qw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_qw),
    ]
    labels = [
        "Stromeinspeisung in das Hauptnetz VW",
        "Stromeinspeisung in das Verbundnetz VW",
        "Stromeinspeisung in das Hauptnetz QW",
        "Stromeinspeisung in das Verbundnetz QW",
    ]
    
    ax.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=2,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else f"power_export_single_year_multibars_{scenario_name}_{target_year}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"scenario": scenario_name, "target_year": target_year, "bars": bars, "plot_path": plot_path}



def plot_co2_single_year_multi_bars_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,          # zum Laden der Dateien
    compare_shorts=None,       # Untere x-Achsen-Beschriftung je Szenario
    target_year=2030,
    bar_count=None,
    variants=("network", "single"),
):
    """
    Plot CO2-Emissionen für genau ein Jahr mit beliebig vielen Balken.
    Pro Szenario werden zwei Balken dargestellt:
      - network -> compare_short1 / "VW"
      - single  -> compare_short2 / "QW"

    CSV-Filter:
    - category == "optimization"
    - metric   == "co2_sum_distr_year"
    """
    if scenario_name is None:
        raise ValueError("scenario_name muss gesetzt sein.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")

    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

    def _read_co2_year(csv_path):
        out = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "co2_sum_distr_year":
                    continue
                try:
                    y = int(float(row.get("year")))
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue
                out[y] = out.get(y, 0.0) + v
        return out

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    rel_year = target_year - base_calendar_year

    bars = []
    for short_file, scen_label in zip(short_files, compare_shorts):
        for variant in variants:
            if variant == "network":
                p = os.path.join(base_dir, f"{scenario_name}_{short_file}_network_results.csv")
            elif variant == "single":
                p = os.path.join(base_dir, f"{scenario_name}_{short_file}_results.csv")
            else:
                raise ValueError(f"Unbekannte variant: {variant}")

            if not os.path.isfile(p):
                raise FileNotFoundError(f"Missing result file: {p}")

            yearly = _read_co2_year(p)
            y_key = rel_year if rel_year in yearly else (target_year if target_year in yearly else None)
            if y_key is None:
                raise ValueError(
                    f"Jahr {target_year} nicht in Datei gefunden: {p} "
                    f"(gesucht als {rel_year} bzw. {target_year})."
                )

            variant_label = "VW" if variant == "network" else "QW"
            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": variant_label,
                "value": float(yearly[y_key]),
                "path": p,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y = np.array([b["value"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58

    colors = ["#D40000" if b["variant"] == "network" else "#55585C" for b in bars]
    labels_for_legend = [
        compare_item1 or "Ohne Verbundpreis",
        compare_item2 or "Mit Verbundpreis",
    ]

    # Balken einzeln zeichnen, damit Farbe je Variante stabil bleibt
    for i, b in enumerate(bars):
        ax.bar(
            x[i],
            y[i],
            width=width,
            color=("#D40000" if b["variant"] == "network" else "#55585C"),
            label="_nolegend_",
        )

    if show_percent_box:
        ymax = max(float(np.max(y)) if len(y) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)
        y_offset = ymax * 0.06

        # Prozentbox nur über network-Balken, relativ zum jeweiligen QW-Balken
        for i in range(0, len(bars), 2):
            if i + 1 >= len(bars):
                break
            vb_val = bars[i]["value"]
            ez_val = bars[i + 1]["value"]
            if ez_val == 0:
                txt = "n/a" if vb_val == 0 else "+∞"
            else:
                txt = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

            ax.text(
                x[i],
                vb_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=8,
                bbox=dict(
                    boxstyle="square,pad=0.25",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.0,
                ),
                zorder=5,
            )

    # obere Ebene: VW / QW
    top_labels = [b["variant_label"] for b in bars]


    # x-Ticks nur für Balkenpaare (Mittelpunkte)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=8)

    ax.set_xlim(x.min() - width, x.max() + width)


    ax.set_ylabel("Treibhausgasemissionen in tCO₂e/a")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    # Legende nur 2 Einträge
    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#D40000"),
        plt.Rectangle((0, 0), 1, 1, fc="#55585C"),
    ]
    ax.legend(
        handles,
        labels_for_legend,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=2,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else f"co2_single_year_multibars_{scenario_name}_{target_year}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "scenario": scenario_name,
        "target_year": target_year,
        "bars": bars,
        "plot_path": plot_path,
    }

def plot_lcoe_single_year_multi_bars_from_csv(
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,
    compare_shorts=None,
    compare_items=None,
    target_year=2030,
    bar_count=None,
    variants=("network", "single"),
):
    if scenario_name is None:
        raise ValueError("scenario_name muss gesetzt sein.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")

    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(short_files) != len(compare_shorts):
        raise ValueError("short_files und compare_shorts müssen gleich lang sein.")

    label_by_short = {}
    if compare_items:
        for s, lbl in zip(short_files, compare_items):
            label_by_short[s] = lbl
    if compare_short1 and compare_item1:
        label_by_short[compare_short1] = compare_item1
    if compare_short2 and compare_item2:
        label_by_short[compare_short2] = compare_item2

    def _safe_parse_value(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if not s:
            return None
        s = s.replace(" ", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    def _read_lcoe_year(csv_path):
        out = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "LCOE_year":
                    continue

                try:
                    y = int(float(row.get("year")))
                except (TypeError, ValueError):
                    continue

                v = _safe_parse_value(row.get("value"))
                if v is None:
                    continue

                out[y] = v
        return out

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    rel_year = target_year - base_calendar_year

    bars = []
    for short_file, scen_label in zip(short_files, compare_shorts):
        for variant in variants:
            if variant == "network":
                p = os.path.join(base_dir, f"{scenario_name}_{short_file}_network_results.csv")
            elif variant == "single":
                p = os.path.join(base_dir, f"{scenario_name}_{short_file}_results.csv")
            else:
                raise ValueError(f"Unbekannte variant: {variant}")

            if not os.path.isfile(p):
                raise FileNotFoundError(f"Missing result file: {p}")

            yearly = _read_lcoe_year(p)
            y_key = rel_year if rel_year in yearly else (target_year if target_year in yearly else None)
            if y_key is None:
                raise ValueError(
                    f"Jahr {target_year} nicht in Datei gefunden: {p} "
                    f"(gesucht als {rel_year} bzw. {target_year})."
                )

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "value": float(yearly[y_key]),
                "path": p,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y = np.array([b["value"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58

    for i, b in enumerate(bars):
        ax.bar(
            x[i],
            y[i],
            width=width,
            color=("#D40000" if b["variant"] == "network" else "#55585C"),
            label="_nolegend_",
        )

    if show_percent_box:
        ymax = max(float(np.max(y)) if len(y) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)
        y_offset = ymax * 0.06

        for i in range(0, len(bars), 2):
            if i + 1 >= len(bars):
                break
            vb_val = bars[i]["value"]
            ez_val = bars[i + 1]["value"]

            if ez_val == 0:
                txt = "n/a" if vb_val == 0 else "+∞"
            else:
                txt = _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

            ax.text(
                x[i],
                vb_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=8,
                bbox=dict(
                    boxstyle="square,pad=0.25",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.0,
                ),
                zorder=5,
            )


    # x-Ticks nur für Balkenpaare (Mittelpunkte)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=8)

    ax.set_xlim(x.min() - width, x.max() + width)


    ax.set_ylabel("Energiegestehungskosten in €/MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#D40000"),
        plt.Rectangle((0, 0), 1, 1, fc="#55585C"),
    ]
    ax.legend(
        handles,
        [compare_item1 or "VW", compare_item2 or "QW"],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=2,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else f"lcoe_single_year_multibars_{scenario_name}_{target_year}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "scenario": scenario_name,
        "target_year": target_year,
        "bars": bars,
        "plot_path": plot_path,
    }

def plot_co2_sum_all_years_multi_bars_from_csv(
    scenario_names=None,
    scenario_names_by_item=None,   # neu: pro compare_item eigene 3er-Szenarien
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,
    compare_shorts=None,
    compare_items=None,
    bar_count=None,
    variants=("network", "single"),
):
    """
    Summiert CO2-Emissionen aus genau 3 Quartieren und plottet beliebig viele Balken.

    scenario_names:
      - entweder 3 Szenarien für alle compare_items
      - oder None, wenn scenario_names_by_item genutzt wird

    scenario_names_by_item:
      - Liste von 3er-Listen, z.B.
        [
          ["S1_Q1", "S1_Q2", "S1_Q3"],
          ["S2_Q1", "S2_Q2", "S2_Q3"],
        ]
      - ein Eintrag pro short_file / compare_item
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")
    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(short_files) != len(compare_shorts):
        raise ValueError("short_files und compare_shorts müssen gleich lang sein.")

    if compare_items is None:
        compare_items = [compare_short1, compare_short2]
    compare_items = [x for x in compare_items if x is not None]

    label_by_short = {}
    if compare_items:
        for s, lbl in zip(short_files, compare_items):
            label_by_short[s] = lbl
    if compare_short1 and compare_item1:
        label_by_short[compare_short1] = compare_item1
    if compare_short2 and compare_item2:
        label_by_short[compare_short2] = compare_item2

    def _read_co2_sum(csv_path):
        co2_by_year = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "co2_sum_distr_year":
                    continue
                try:
                    y = int(float(row.get("year")))
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue

                co2_by_year[y] = co2_by_year.get(y, 0.0) + v
        return co2_by_year

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    # scenario_names normalisieren:
    # - flat 3er-Liste => für alle gleich
    # - Liste von 3er-Listen => pro short_file einzeln
    if scenario_names_by_item is None:
        if scenario_names is None or len(scenario_names) != 3:
            raise ValueError("scenario_names muss genau 3 Einträge haben oder scenario_names_by_item muss gesetzt sein.")
        scenario_names_by_item = [list(scenario_names) for _ in short_files]
    else:
        if len(scenario_names_by_item) != len(short_files):
            raise ValueError("scenario_names_by_item muss genauso lang sein wie short_files.")
        for triplet in scenario_names_by_item:
            if not isinstance(triplet, (list, tuple)) or len(triplet) != 3:
                raise ValueError("Jeder Eintrag in scenario_names_by_item muss genau 3 Szenarien enthalten.")

    bars = []
    for short_file, scen_label, scen_triplet in zip(short_files, compare_shorts, scenario_names_by_item):
        for variant in variants:
            total = 0.0
            paths = []
            total_by_year = {}

            for sc in scen_triplet:
                if variant == "network":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")

                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")

                yearly = _read_co2_sum(p)
                paths.append(p)

                for year, value in yearly.items():
                    total_by_year[year] = total_by_year.get(year, 0.0) + value

            # falls weiterhin ein einzelner Wert pro Balken gebraucht wird:
            total = sum(total_by_year.values())
            #print(f"Total CO2 für {scen_label} ({variant}): {total:.2f} tCO₂e über alle Jahre (Details: {total_by_year})")

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "value": total,
                "paths": paths,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y = np.array([b["value"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58

    for i, b in enumerate(bars):
        ax.bar(
            x[i],
            y[i],
            width=width,
            color=("#D40000" if b["variant"] == "network" else "#55585C"),
            label="_nolegend_",
        )

    if show_percent_box:
        ymax = max(float(np.max(y)) if len(y) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)
        y_offset = ymax * 0.06

        for i in range(0, len(bars), 2):
            if i + 1 >= len(bars):
                break

            vb_val = bars[i]["value"]
            ez_val = bars[i + 1]["value"]
            txt = "n/a" if ez_val == 0 and vb_val == 0 else "+∞" if ez_val == 0 else _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

            ax.text(
                x[i],
                vb_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=8,
                bbox=dict(
                    boxstyle="square,pad=0.25",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.0,
                ),
                zorder=5,
            )

    # x-Ticks nur für Balkenpaare (Mittelpunkte)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=8)

    ax.set_xlim(x.min() - width, x.max() + width)

    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    # for xc, lbl in zip(pair_centers, pair_labels):
    #     ax.text(
    #         xc,
    #         -0.10,
    #         lbl,
    #         transform=ax.get_xaxis_transform(),
    #         ha="center",
    #         va="top",
    #         fontsize=8,
    #     )

    ax.set_ylabel("Treibhausgasemissionen in tCO₂e")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#D40000"),
        plt.Rectangle((0, 0), 1, 1, fc="#55585C"),
    ]
    ax.legend(
        handles,
        [compare_item1, compare_item2],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=2,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else "co2_sum_multi_bars.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "bars": bars,
        "plot_path": plot_path,
    }

def plot_lcoe_sum_from_three_scenarios_multi_compare(
    scenario_names_by_item,
    short_files=None,
    compare_item1=None,
    compare_item2=None,
    compare_shorts=None,
    compare_items=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    target_year=2030,
    show_percent_box=False,
    power_demand=None,
    bar_count=None,

):
    """
    Berechnet LCOE für mehrere Verbünde aus je 3 Quartieren.
    
    short_files: Dateikürzel zum Laden (z.B. ["ref", "gas", "elec"])
    compare_shorts: Labels auf x-Achse (z.B. ["Basis", "Gas", "Strom"])
    compare_items: Labels für Legende (z.B. ["Verbund", "Quartier"])
    scenario_names_by_item: pro short_file eine Liste von 3 Quartier-Szenarien
    """
    if not isinstance(scenario_names_by_item, (list, tuple)) or not scenario_names_by_item:
        raise ValueError("scenario_names_by_item muss eine nicht-leere Liste von 3er-Listen sein.")

    if short_files is None:
        raise ValueError("short_files muss gesetzt sein.")
    short_files = list(short_files)

    if len(scenario_names_by_item) != len(short_files):
        raise ValueError("scenario_names_by_item muss genauso lang sein wie short_files.")

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

    if compare_items is None:
        compare_items = ["Verbund", "Quartier"]
    compare_items = list(compare_items)

    for triplet in scenario_names_by_item:
        if not isinstance(triplet, (list, tuple)) or len(triplet) != 3:
            raise ValueError("Jeder Eintrag in scenario_names_by_item muss genau 3 Szenario-Namen enthalten.")

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    def _safe_parse_value(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if not s:
            return None
        s = s.replace(" ", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    def _read_tac_and_supply(csv_path):
        tac_by_year = {}
        supply_by_year = {}

        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                cat = str(row.get("category", "")).strip()
                metric = str(row.get("metric", "")).strip()

                y_raw = row.get("year")
                if y_raw in (None, ""):
                    continue
                try:
                    y = int(float(y_raw))
                except Exception:
                    continue

                v = _safe_parse_value(row.get("value"))
                if v is None:
                    continue

                if cat == "optimization" and metric == "tac_per_distr_year":
                    tac_by_year[y] = tac_by_year.get(y, 0.0) + float(v)

                if cat == "yearly_totals" and metric == "total_heat_supply_by_year":
                    supply_by_year[y] = supply_by_year.get(y, 0.0) + float(v)

        return tac_by_year, supply_by_year

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    rel_year = target_year - base_calendar_year

    lcoe_network = []
    lcoe_single = []
    details = {}


    # Wichtig: Laden über short_files
    for short_file, scen_label, triplet in zip(short_files, compare_shorts, scenario_names_by_item):
        tac_network_sum = {}
        tac_single_sum = {}
        sup_network_sum = {}
        sup_single_sum = {}

        for sc in triplet:
            network_path = os.path.join(base_dir, f"{sc}_{short_file}_network_results.csv")
            single_path = os.path.join(base_dir, f"{sc}_{short_file}_results.csv")

            if not os.path.isfile(network_path):
                raise FileNotFoundError(f"Missing file: {network_path}")
            if not os.path.isfile(single_path):
                raise FileNotFoundError(f"Missing file: {single_path}")

            tac_net, sup_net = _read_tac_and_supply(network_path)
            tac_sin, sup_sin = _read_tac_and_supply(single_path)

            for y, val in tac_net.items():
                tac_network_sum[y] = tac_network_sum.get(y, 0.0) + val
            for y, val in tac_sin.items():
                tac_single_sum[y] = tac_single_sum.get(y, 0.0) + val

            for y, val in sup_net.items():
                sup_network_sum[y] = sup_network_sum.get(y, 0.0) + val + power_demand[sc]
            for y, val in sup_sin.items():
                sup_single_sum[y] = sup_single_sum.get(y, 0.0) + val + power_demand[sc]

        y_key = rel_year if rel_year in sup_network_sum or rel_year in sup_single_sum else target_year
        if y_key not in tac_network_sum and y_key not in tac_single_sum:
            raise ValueError(f"Jahr {target_year} nicht in den Daten für '{scen_label}' gefunden.")

        den_net = sup_network_sum.get(y_key, 0.0)
        den_sin = sup_single_sum.get(y_key, 0.0)
        num_net = tac_network_sum.get(y_key, 0.0)
        num_sin = tac_single_sum.get(y_key, 0.0)

        lcoe_net_val = num_net / den_net if den_net > 0 else 0.0
        lcoe_sin_val = num_sin / den_sin if den_sin > 0 else 0.0

        lcoe_network.append(lcoe_net_val)
        lcoe_single.append(lcoe_sin_val)

        details[scen_label] = {
            "network": {"tac": num_net, "supply": den_net, "lcoe": lcoe_net_val},
            "single": {"tac": num_sin, "supply": den_sin, "lcoe": lcoe_sin_val},
        }

    
    x = np.arange(len(compare_shorts))

    width = 0.35

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.35
    ax.bar(x - width / 2, lcoe_network, width=width, color="#D40000", label=compare_item1)
    ax.bar(x + width / 2, lcoe_single, width=width, color="#55585C", label=compare_item2)

    if show_percent_box:
        ymax = max(max(lcoe_network) if lcoe_network else 0, max(lcoe_single) if lcoe_single else 0, 1.0)
        ax.set_ylim(0, ymax * 1.35)
        y_offset = ymax * 0.07

        for i, (net_val, sin_val) in enumerate(zip(lcoe_network, lcoe_single)):
            if sin_val == 0:
                txt = "n/a" if net_val == 0 else "+∞"
            else:
                txt = _fmt_pct((net_val - sin_val) / sin_val * 100.0)

            ax.text(
                x[i] - width / 2,
                net_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=10,
                bbox=dict(
                    boxstyle="square,pad=0.3",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.1,
                ),
                zorder=5,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(compare_shorts)
    ax.set_ylabel("Energiegestehungskosten in €/MWh")
    #ax.set_title(titel or f"LCOE im Jahr {target_year}")
    ax.grid(axis="y", alpha=0.4)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#D40000"),
        plt.Rectangle((0, 0), 1, 1, fc="#55585C"),
    ]

    ax.legend(
        handles,
        [compare_item1 or "VW", compare_item2 or "QW"],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=2,
        frameon=False,
        fontsize=10,
    )

    fig.tight_layout()

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_path = os.path.join(plots_dir, f"{titel}.pdf" if titel else f"lcoe_sum_multi_compare_{target_year}.pdf")
    fig.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "plot_path": plot_path,
        "details": details,
        "lcoe_network": dict(zip(compare_shorts, lcoe_network)),
        "lcoe_single": dict(zip(compare_shorts, lcoe_single)),
    }


def plot_power_import_single_year_multi_bars_from_csv_per_pair(
    scenario_name=None,
    scenario_names_per_pair=None,   # neu: Liste mit scenario_name für jedes Paar (len == len(short_files))
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,          # <- Dateikürzel zum Laden
    compare_shorts=None,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=None,
    target_year=2030,
    bar_count=None,
    variants=("network", "single"),
):
    """
    Wie plot_power_import_single_year_multi_bars_from_csv, aber ermöglicht pro Balkenpaar
    ein eigenes Quartier (scenario_name) über `scenario_names_per_pair` zu setzen.
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    # Backward-Compatibility
    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")
    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

    if scenario_names_per_pair is not None:
        if isinstance(scenario_names_per_pair, str):
            scenario_names_per_pair = [scenario_names_per_pair]
        scenario_names_per_pair = list(scenario_names_per_pair)
        if len(scenario_names_per_pair) != len(short_files):
            raise ValueError("scenario_names_per_pair muss dieselbe Länge wie short_files haben.")
    else:
        # fallback: alle Paare nutzen `scenario_name`
        if scenario_name is None:
            raise ValueError("Entweder scenario_name oder scenario_names_per_pair muss gesetzt sein.")
        scenario_names_per_pair = [scenario_name for _ in short_files]

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

    rel_year = target_year - base_calendar_year

    # Wichtig: Laden über short_files; pro Paar eigenes scenario_name verwenden
    bars = []
    for idx, (short_file, scen_label) in enumerate(zip(short_files, compare_shorts)):
        scen_for_pair = scenario_names_per_pair[idx]
        for variant in variants:
            if variant == "network":
                p = os.path.join(base_dir, f"{scen_for_pair}_{short_file}_network_results.csv")
            elif variant == "single":
                p = os.path.join(base_dir, f"{scen_for_pair}_{short_file}_results.csv")
            else:
                raise ValueError(f"Unbekannte variant: {variant}")

            if not os.path.isfile(p):
                raise FileNotFoundError(f"Missing result file: {p}")

            yearly = _read_yearly_import(p)
            y_key = rel_year if rel_year in yearly else (target_year if target_year in yearly else None)
            if y_key is None:
                raise ValueError(
                    f"Jahr {target_year} nicht in Datei gefunden: {p} "
                    f"(gesucht als {rel_year} bzw. {target_year})."
                )

            main_val = float(yearly[y_key].get("from_el_main_grid_total", 0.0))
            net_val = float(yearly[y_key].get("from_network_total", 0.0))

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "main": main_val,
                "net": net_val,
                "total": main_val + net_val,
                "path": p,
                "scenario_used": scen_for_pair,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y_main = np.array([b["main"] for b in bars], dtype=float)
    y_net = np.array([b["net"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58

    # Farben nach Optimierungsart
    color_main_vw = "#E43D30"  # hellrot (VW Hauptnetz)
    color_net_vw = "#8C1D17"    # dunkelrot (VW Verbundnetz)
    color_main_qw = "#B9BABC"   # QW Hauptnetz (wie vorher)
    color_net_qw = "#8A8B8D"    # QW Verbundnetz (wie vorher)

    # Zeichne Balken paarweise, mit unterschiedlicher Farbgebung für VW vs QW
    for i, b in enumerate(bars):
        if b["variant"] == "network":  # VW = linke Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_vw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_vw, label="_nolegend_")
        else:  # QW = rechte Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_qw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_qw, label="_nolegend_")

    # Prozentboxen wieder aktivieren
    if show_percent_box:
        totals = y_main + y_net
        ymax = max(float(np.max(totals)) if len(totals) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)

        for i in range(len(bars)):
            total = float(totals[i])
            if total <= 0:
                continue

            pct_net = (float(y_net[i]) / total) * 100.0
            txt = f"{pct_net:.0f}%".replace(".", ",")

            line_y0 = total
            line_y1 = total + 0.05 * ymax
            box_y = line_y1 + 0.012 * ymax

            ax.plot(
                [x[i], x[i]],
                [line_y0, line_y1],
                color="#7A7A7A",
                linewidth=0.9,
                zorder=6,
                clip_on=False,
            )
            ax.text(
                x[i],
                box_y,
                txt,
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
                color="black",
                bbox=dict(
                    boxstyle="round,pad=0.22",
                    facecolor="white",
                    edgecolor=(color_main_vw if bars[i]["variant"] == "network" else color_main_qw),
                    linewidth=0.9,
                ),
                zorder=7,
                clip_on=False,
            )

    # x-Ticks nur für Balkenpaare (Mittelpunkte)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=8)
    ax.set_xlim(x.min() - width, x.max() + width)

    ax.set_ylabel("Energie in MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    # Legende mit vier Einträgen (VW links, QW rechts)
    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_main_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_main_qw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_qw),
    ]
    labels = [
        "Strombezug aus dem Hauptnetz VW",
        "Strombezug aus dem Verbundnetz VW",
        "Strombezug aus dem Hauptnetz QW",
        "Strombezug aus dem Verbundnetz QW",
    ]
    ax.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=2,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else f"power_import_single_year_multibars_perpair_{target_year}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"scenario_names_per_pair": scenario_names_per_pair, "target_year": target_year, "bars": bars, "plot_path": plot_path}

def plot_power_export_single_year_multi_bars_from_csv_per_pair(
    scenario_name=None,
    scenario_names_per_pair=None,   # neu: Liste mit scenario_name für jedes Paar (len == len(short_files))
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,          # <- Dateikürzel zum Laden
    compare_shorts=None,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=None,
    target_year=2030,
    bar_count=None,
    variants=("network", "single"),
    label_left=None,
    label_right=None,
):
    """
    Wie plot_power_export_single_year_multi_bars_from_csv, aber ermöglicht pro Balkenpaar
    ein eigenes Quartier (scenario_name) über `scenario_names_per_pair` zu setzen.
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    # Backward-Compatibility
    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")
    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

    if scenario_names_per_pair is not None:
        if isinstance(scenario_names_per_pair, str):
            scenario_names_per_pair = [scenario_names_per_pair]
        scenario_names_per_pair = list(scenario_names_per_pair)
        if len(scenario_names_per_pair) != len(short_files):
            raise ValueError("scenario_names_per_pair muss dieselbe Länge wie short_files haben.")
    else:
        # fallback: alle Paare nutzen `scenario_name`
        if scenario_name is None:
            raise ValueError("Entweder scenario_name oder scenario_names_per_pair muss gesetzt sein.")
        scenario_names_per_pair = [scenario_name for _ in short_files]

    def _read_yearly_export(csv_path):
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

    rel_year = target_year - base_calendar_year

    # Wichtig: Laden über short_files; pro Paar eigenes scenario_name verwenden
    bars = []
    for idx, (short_file, scen_label) in enumerate(zip(short_files, compare_shorts)):
        scen_for_pair = scenario_names_per_pair[idx]
        for variant in variants:
            if variant == "network":
                p = os.path.join(base_dir, f"{scen_for_pair}_{short_file}_network_results.csv")
            elif variant == "single":
                p = os.path.join(base_dir, f"{scen_for_pair}_{short_file}_results.csv")
            else:
                raise ValueError(f"Unbekannte variant: {variant}")

            if not os.path.isfile(p):
                raise FileNotFoundError(f"Missing result file: {p}")

            yearly = _read_yearly_export(p)
            y_key = rel_year if rel_year in yearly else (target_year if target_year in yearly else None)
            if y_key is None:
                raise ValueError(
                    f"Jahr {target_year} nicht in Datei gefunden: {p} "
                    f"(gesucht als {rel_year} bzw. {target_year})."
                )

            main_val = float(yearly[y_key].get("to_el_main_grid_total", 0.0))
            net_val = float(yearly[y_key].get("to_network_total", 0.0))

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "main": main_val,
                "net": net_val,
                "total": main_val + net_val,
                "path": p,
                "scenario_used": scen_for_pair,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y_main = np.array([b["main"] for b in bars], dtype=float)
    y_net = np.array([b["net"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58

    # Farben nach Optimierungsart
    color_main_vw = "#E43D30"  # hellrot (VW Hauptnetz)
    color_net_vw = "#8C1D17"    # dunkelrot (VW Verbundnetz)
    color_main_qw = "#B9BABC"   # QW Hauptnetz (wie vorher)
    color_net_qw = "#8A8B8D"    # QW Verbundnetz (wie vorher)

    # Zeichne Balken paarweise, mit unterschiedlicher Farbgebung für VW vs QW
    for i, b in enumerate(bars):
        if b["variant"] == "network":  # VW = linke Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_vw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_vw, label="_nolegend_")
        else:  # QW = rechte Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_qw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_qw, label="_nolegend_")

    # Prozentboxen wieder aktivieren
    if show_percent_box:
        totals = y_main + y_net
        ymax = max(float(np.max(totals)) if len(totals) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)

        for i in range(len(bars)):
            total = float(totals[i])
            if total <= 0:
                continue

            pct_net = (float(y_net[i]) / total) * 100.0
            txt = f"{pct_net:.0f}%".replace(".", ",")

            line_y0 = total
            line_y1 = total + 0.05 * ymax
            box_y = line_y1 + 0.012 * ymax

            ax.plot(
                [x[i], x[i]],
                [line_y0, line_y1],
                color="#7A7A7A",
                linewidth=0.9,
                zorder=6,
                clip_on=False,
            )
            ax.text(
                x[i],
                box_y,
                txt,
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
                color="black",
                bbox=dict(
                    boxstyle="round,pad=0.22",
                    facecolor="white",
                    edgecolor=(color_main_vw if bars[i]["variant"] == "network" else color_main_qw),
                    linewidth=0.9,
                ),
                zorder=7,
                clip_on=False,
            )

    # x-Ticks nur für Balkenpaare (Mittelpunkte)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=8)
     # Neue: vertikale gestrichelte Linien zwischen Paaren, wenn sich das scenario ändert
    if label_left or label_right:
        # Abstand zwischen Paarzentren (Fallback)
        if len(pair_centers) > 1:
            center_delta = pair_centers[1] - pair_centers[0]
        else:
            center_delta = (x.max() - x.min()) if len(x) > 1 else width * 2.0
        x_offset = center_delta * 0.20

        # y-Position der Labels INSIDE des Plots (in Daten-Koordinaten)
        totals = y_main + y_net
        ymax_data = max(float(np.max(totals)) if len(totals) else 0.0, 1.0)
        label_y = ymax_data * 1.26

        for j in range(len(pair_centers) - 1):
            scen_left = scenario_names_per_pair[j]
            scen_right = scenario_names_per_pair[j + 1]
            if scen_left != scen_right:
                line_x = 0.5 * (pair_centers[j] + pair_centers[j + 1])
                ax.axvline(line_x, color="#7A7A7A", linestyle="--", linewidth=0.9, zorder=4, clip_on=False)

                if label_left:
                    ax.text(
                        line_x - x_offset,
                        label_y,
                        label_left,
                        ha="right",
                        va="top",
                        fontsize=8,
                        bbox=dict(facecolor="white", edgecolor="none", pad=0.2),
                        zorder=6,
                    )
                if label_right:
                    ax.text(
                        line_x + x_offset,
                        label_y,
                        label_right,
                        ha="left",
                        va="top",
                        fontsize=8,
                        bbox=dict(facecolor="white", edgecolor="none", pad=0.2),
                        zorder=6,
                    )
    ax.set_xlim(x.min() - width, x.max() + width)

    ax.set_ylabel("Energie in MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    # Legende mit vier Einträgen (VW links, QW rechts)
    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_main_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_main_qw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_qw),
    ]
    labels = [
        "Stromeinspeisung in das Hauptnetz VW",
        "Stromeinspeisung in das Verbundnetz VW",
        "Stromeinspeisung in das Hauptnetz QW",
        "Stromeinspeisung in das Verbundnetz QW",
    ]
    ax.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=2,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else f"power_export_single_year_multibars_{scenario_names_per_pair[0]}_{scenario_names_per_pair[2]}_{target_year}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"scenario_names_per_pair": scenario_names_per_pair, "target_year": target_year, "bars": bars, "plot_path": plot_path}



def plot_power_import_single_year_multi_bars_from_csv_per_pair(
    scenario_name=None,
    scenario_names_per_pair=None,      # alt: 1 Szenario je compare_short
    scenario_names_per_compare=None,   # neu: je compare_short 1 oder 2 Szenarien
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,
    compare_shorts=None,
    compare_items=None,
    target_year=2030,
    bar_count=None,
    variants=("network", "single"),
    label_left=None,
    label_right=None,
):
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")
    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

    # -------- Szenario-Setup je compare_short --------
    # Ziel: pro compare_short 1 oder 2 Szenarien zulassen
    scenarios_by_compare = []

    if scenario_names_per_compare is not None:
        if len(scenario_names_per_compare) != len(short_files):
            raise ValueError("scenario_names_per_compare muss dieselbe Länge wie short_files haben.")
        for entry in scenario_names_per_compare:
            if isinstance(entry, str):
                scenarios_by_compare.append([entry])
            elif isinstance(entry, (list, tuple)) and len(entry) in (1, 2):
                scenarios_by_compare.append(list(entry))
            else:
                raise ValueError("Jeder Eintrag in scenario_names_per_compare muss str oder Liste/Tuple mit 1-2 Einträgen sein.")
    else:
        # Fallback auf altes Verhalten
        if scenario_names_per_pair is not None:
            if isinstance(scenario_names_per_pair, str):
                scenario_names_per_pair = [scenario_names_per_pair]
            scenario_names_per_pair = list(scenario_names_per_pair)
            if len(scenario_names_per_pair) != len(short_files):
                raise ValueError("scenario_names_per_pair muss dieselbe Länge wie short_files haben.")
            scenarios_by_compare = [[s] for s in scenario_names_per_pair]
        else:
            if scenario_name is None:
                raise ValueError("Entweder scenario_name oder scenario_names_per_pair oder scenario_names_per_compare muss gesetzt sein.")
            scenarios_by_compare = [[scenario_name] for _ in short_files]

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

    rel_year = target_year - base_calendar_year

    bars = []
    # group_meta speichert je compare_short die x-Positionen für zentrierte xticks
    group_meta = []

    # spacing
    width = 0.35
    inner_step = 0.35
    scenario_gap = 0.55
    group_step = 2.8

    for g_idx, (short_file, scen_label, scen_list) in enumerate(zip(short_files, compare_shorts, scenarios_by_compare)):
        group_x = []
        base_x = g_idx * group_step
        x_cursor = base_x

        for s_idx, scen_for_group in enumerate(scen_list):
            for v_idx, variant in enumerate(variants):
                if variant == "network":
                    p = os.path.join(base_dir, f"{scen_for_group}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{scen_for_group}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")

                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")

                yearly = _read_yearly_import(p)
                y_key = rel_year if rel_year in yearly else (target_year if target_year in yearly else None)
                if y_key is None:
                    raise ValueError(f"Jahr {target_year} nicht in Datei gefunden: {p}")

                main_val = float(yearly[y_key].get("from_el_main_grid_total", 0.0))
                net_val = float(yearly[y_key].get("from_network_total", 0.0))

                bx = x_cursor + v_idx * inner_step
                group_x.append(bx)

                bars.append({
                    "group_idx": g_idx,
                    "x": bx,
                    "short_file": short_file,
                    "compare_short": scen_label,
                    "scenario_used": scen_for_group,
                    "scenario_slot": s_idx,  # 0 oder 1
                    "variant": variant,
                    "main": main_val,
                    "net": net_val,
                    "total": main_val + net_val,
                    "path": p,
                })

            # nach einem Szenario zum nächsten Szenario im gleichen compare_short
            x_cursor = x_cursor + (len(variants) - 1) * inner_step + scenario_gap

        group_meta.append({
            "label": scen_label,
            "x_min": min(group_x),
            "x_max": max(group_x),
            "x_center": 0.5 * (min(group_x) + max(group_x)),
            "scenarios": scen_list,
        })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([b["x"] for b in bars], dtype=float)
    y_main = np.array([b["main"] for b in bars], dtype=float)
    y_net = np.array([b["net"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))

    color_main_vw = "#E43D30"
    color_net_vw = "#8C1D17"
    color_main_qw = "#B9BABC"
    color_net_qw = "#8A8B8D"

    for i, b in enumerate(bars):
        if b["variant"] == "network":
            ax.bar(x[i], y_main[i], width=width, color=color_main_vw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_vw, label="_nolegend_")
        else:
            ax.bar(x[i], y_main[i], width=width, color=color_main_qw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_qw, label="_nolegend_")
    
    # Prozentboxen wieder aktivieren
    if show_percent_box:
        totals = y_main + y_net
        ymax = max(float(np.max(totals)) if len(totals) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)

        for i in range(len(bars)):
            total = float(totals[i])
            if total <= 0:
                continue

            pct_net = (float(y_net[i]) / total) * 100.0
            txt = f"{pct_net:.0f}%".replace(".", ",")

            line_y0 = total
            line_y1 = total + 0.05 * ymax
            box_y = line_y1 + 0.012 * ymax

            ax.plot(
                [x[i], x[i]],
                [line_y0, line_y1],
                color="#7A7A7A",
                linewidth=0.9,
                zorder=6,
                clip_on=False,
            )
            ax.text(
                x[i],
                box_y,
                txt,
                ha="center",
                va="bottom",
                fontsize=7,
                fontweight="bold",
                color="black",
                bbox=dict(
                    boxstyle="round,pad=0.22",
                    facecolor="white",
                    edgecolor=(color_main_vw if bars[i]["variant"] == "network" else color_main_qw),
                    linewidth=0.9,
                ),
                zorder=7,
                clip_on=False,
            )

    
    # x-Achse: zweistufige Beschriftung
    # 1. Ebene: unter jedem Balkenpaar (network+single) steht das dargestellte Quartier
    # 2. Ebene: unter je 4 Balken (eine compare_short-Gruppe) eine geschwungene Klammer + compare_short-Label

    # Mapping für Szenarionamen -> Anzeige
    scenario_name_map = {
        "residential2": "Wohn 1",
        "residential0": "Wohn 2",
        "residential3": "Wohn 3",
        "ghd6": "Gewerbe",
    }


    # 1) Berechne Zentren pro Balkenpaar (group_idx, scenario_slot)
    pair_centers = []
    pair_labels = []
    # gruppiere bars nach (group_idx, scenario_slot)
    from collections import defaultdict
    pair_xs = defaultdict(list)
    pair_scn = {}
    for b in bars:
        key = (b["group_idx"], b["scenario_slot"])
        pair_xs[key].append(b["x"])
        pair_scn[key] = b["scenario_used"]

    # sortiere nach group_idx then scenario_slot
    keys_sorted = sorted(pair_xs.keys(), key=lambda t: (t[0], t[1]))
    for k in keys_sorted:
        xs = pair_xs[k]
        center = float(np.mean(xs))
        pair_centers.append(center)
        scen = pair_scn.get(k, "")
        pair_labels.append(scenario_name_map.get(scen, scen))

    # Zeichne erste Ebene (Szenario-Bezeichnungen unter jedem Balkenpaar)
    for xc, lbl in zip(pair_centers, pair_labels):
        ax.text(
            xc,
            -0.06,
            lbl,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=8,
        )

    # 2) Zeichne geschwungene/vereinfachte Klammer und compare_short-Label pro Gruppe (vier Balken)
    # Gruppen-Metadaten in group_meta enthalten x_min,x_max,x_center
    # Klammer in Axes-Koordinaten zeichnen (transform=ax.transAxes)
    # y-Positionen in Achsen-Koordinaten (unterhalb x-Achse)
    brace_y_ax = -0.085   # Klammer oberer Punkt (axes coords)
    brace_h_ax = 0.035    # Tiefe der Klammer (axes coords)
    label_y_ax = -0.125   # compare_short-Label (axes coords)

    for gm, comp_short in zip(group_meta, compare_shorts):
        x0 = gm["x_min"]
        x1 = gm["x_max"]
        # convert data x to axes coords
        x0_disp, _ = ax.transData.transform((x0, 0.0))
        x1_disp, _ = ax.transData.transform((x1, 0.0))
        inv = ax.transAxes.inverted()
        x0_ax, _ = inv.transform((x0_disp, 0.0))
        x1_ax, _ = inv.transform((x1_disp, 0.0))

        # einfache geschwungene Klammer als bezier-Path in axes coords
        mx = 0.5 * (x0_ax + x1_ax)
        left = x0_ax
        right = x1_ax
        top = brace_y_ax
        mid = top - brace_h_ax * 0.6
        bot = top - brace_h_ax

        verts = [
            (left, top),
            (left + (mx - left) * 0.25, mid),
            (mx, bot),
            (right - (right - mx) * 0.25, mid),
            (right, top),
        ]
        codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.LINETO]
        path = Path(verts, codes)
        patch = PathPatch(path, transform=ax.transAxes, fc="none", ec="#7A7A7A", lw=0.9, linestyle="--", zorder=4)
        ax.add_patch(patch)

        # compare_short-Label zentriert unter der Klammer
        ax.text(
            0.5 * (x0_ax + x1_ax),
            label_y_ax,
            str(comp_short),
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=9,
        )

    # Passe unteren Rand an, damit beide Ebenen sichtbar sind
    fig.subplots_adjust(bottom=0.30)

    # Begrenze x-Achse erneut
    if len(x):
        ax.set_xlim(np.min(x) - width, np.max(x) + width)
    
    # Entferne die numerischen Tick-Labels auf der x-Achse
    ax.set_xticks([])

    ax.set_ylabel("Energie in MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_main_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_main_qw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_qw),
    ]
    labels = [
        "Strombezug aus dem Hauptnetz VW",
        "Strombezug aus dem Verbundnetz VW",
        "Strombezug aus dem Hauptnetz QW",
        "Strombezug aus dem Verbundnetz QW",
    ]
    ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False, fontsize=8)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else f"power_import_single_year_multibars_perpair_{target_year}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "target_year": target_year,
        "bars": bars,
        "plot_path": plot_path,
        "scenario_names_per_compare": scenario_names_per_compare,
    }

def plot_tac_sum_all_years_multi_bars_from_csv(
    scenario_names=None,
    scenario_names_by_item=None,   # neu: pro compare_item eigene 3er-Szenarien
    scenario_name=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    show_percent_box=False,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,
    compare_shorts=None,
    compare_items=None,
    bar_count=None,
    variants=("network", "single"),
):
    """
    Verwendet TAC aus genau 3 Quartieren und plottet beliebig viele Balken.

    scenario_names:
      - entweder 3 Szenarien für alle compare_items
      - oder None, wenn scenario_names_by_item genutzt wird

    scenario_names_by_item:
      - Liste von 3er-Listen, z.B.
        [
          ["S1_Q1", "S1_Q2", "S1_Q3"],
          ["S2_Q1", "S2_Q2", "S2_Q3"],
        ]
      - ein Eintrag pro short_file / compare_item
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    if short_files is None:
        short_files = [c for c in [compare_short1, compare_short2] if c]
    if not short_files:
        raise ValueError("Bitte short_files oder compare_short1/compare_short2 angeben.")
    short_files = list(short_files)

    if compare_shorts is None:
        compare_shorts = short_files.copy()
    compare_shorts = list(compare_shorts)

    if len(short_files) != len(compare_shorts):
        raise ValueError("short_files und compare_shorts müssen gleich lang sein.")

    if compare_items is None:
        compare_items = [compare_short1, compare_short2]
    compare_items = [x for x in compare_items if x is not None]

    label_by_short = {}
    if compare_items:
        for s, lbl in zip(short_files, compare_items):
            label_by_short[s] = lbl
    if compare_short1 and compare_item1:
        label_by_short[compare_short1] = compare_item1
    if compare_short2 and compare_item2:
        label_by_short[compare_short2] = compare_item2

    def _read_tac_sum(csv_path):
        tac_distr = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "optimization":
                    continue
                if row.get("metric") != "tac_distr":
                    continue
                try:
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue

                tac_distr = tac_distr.get(v, 0.0) + v
        return tac_distr

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    # scenario_names normalisieren:
    # - flat 3er-Liste => für alle gleich
    # - Liste von 3er-Listen => pro short_file einzeln
    if scenario_names_by_item is None:
        if scenario_names is None or len(scenario_names) != 3:
            raise ValueError("scenario_names muss genau 3 Einträge haben oder scenario_names_by_item muss gesetzt sein.")
        scenario_names_by_item = [list(scenario_names) for _ in short_files]
    else:
        if len(scenario_names_by_item) != len(short_files):
            raise ValueError("scenario_names_by_item muss genauso lang sein wie short_files.")
        for triplet in scenario_names_by_item:
            if not isinstance(triplet, (list, tuple)) or len(triplet) != 3:
                raise ValueError("Jeder Eintrag in scenario_names_by_item muss genau 3 Szenarien enthalten.")

    bars = []
    for short_file, scen_label, scen_triplet in zip(short_files, compare_shorts, scenario_names_by_item):
        for variant in variants:
            total = 0.0
            paths = []
            total_by_year = {}

            for sc in scen_triplet:
                if variant == "network":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")

                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")

                tac_distr = _read_tac_sum(p)
                paths.append(p)


            # falls weiterhin ein einzelner Wert pro Balken gebraucht wird:
            total = sum(tac_distr.values())
            #print(f"Total CO2 für {scen_label} ({variant}): {total:.2f} tCO₂e über alle Jahre (Details: {total_by_year})")

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "value": total,
                "paths": paths,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y = np.array([b["value"] for b in bars], dtype=float)

    fig_w_mm, fig_h_mm = 155, 100
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58

    for i, b in enumerate(bars):
        ax.bar(
            x[i],
            y[i],
            width=width,
            color=("#D40000" if b["variant"] == "network" else "#55585C"),
            label="_nolegend_",
        )

    if show_percent_box:
        ymax = max(float(np.max(y)) if len(y) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)
        y_offset = ymax * 0.06

        for i in range(0, len(bars), 2):
            if i + 1 >= len(bars):
                break

            vb_val = bars[i]["value"]
            ez_val = bars[i + 1]["value"]
            txt = "n/a" if ez_val == 0 and vb_val == 0 else "+∞" if ez_val == 0 else _fmt_pct((vb_val - ez_val) / ez_val * 100.0)

            ax.text(
                x[i],
                vb_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=8,
                bbox=dict(
                    boxstyle="square,pad=0.25",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.0,
                ),
                zorder=5,
            )

    # x-Ticks nur für Balkenpaare (Mittelpunkte)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=8)

    ax.set_xlim(x.min() - width, x.max() + width)

    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    # for xc, lbl in zip(pair_centers, pair_labels):
    #     ax.text(
    #         xc,
    #         -0.10,
    #         lbl,
    #         transform=ax.get_xaxis_transform(),
    #         ha="center",
    #         va="top",
    #         fontsize=8,
    #     )

    ax.set_ylabel("Treibhausgasemissionen in tCO₂e")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#D40000"),
        plt.Rectangle((0, 0), 1, 1, fc="#55585C"),
    ]
    ax.legend(
        handles,
        [compare_item1, compare_item2],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=2,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else "co2_sum_multi_bars.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "bars": bars,
        "plot_path": plot_path,
    }



def main():
    scenario_name = "residential2"
    scenario_names = ["residential2", "mixed1", "ghd6"]
    #short_files = ["Basis", "Bat", "PV"] 

    # pro Balkenpaar eigenes Szenario
    scenario_names_per_pair = ["mixed1", "mixed1", "residential0"]   
    scenario_names_per_compare = [
    ("residential2", "ghd6"),
    ("residential2", "residential0"),
    ("residential2", "residential3"),
]
    short_files = ["Basis","WM","Wohn"]

    #compare_shorts = ["Basis", "Batterie", "Solarausbau"]
    compare_shorts = ["Basis","Wohnmisch","Wohn"]
    #compare_shorts = ["B-VW", "B-QW","W-VW","W-QW", "B-VW","B-QW", "P-VW","P-QW", "WN-VW","WN-QW"]
    compare_items = ["Basis-Szenario", "Wohnmisch-Szenario", "Wohn-Szenario"]
    #compare_items = ["Basis-Szenario", "Batterie-Szenario", "Solarausbau-Szenario"]
    compare_item1 = "verbundweise"
    compare_item2 = "quartiersweise"
    base_dir=r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results"
    result_dir=r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results"
    target_year = 2035
    bar_count = 6

    scenario_names_by_item = [
        ["residential2", "mixed1", "ghd6"],
        ["residential2", "mixed1", "residential0"],
        ["residential2", "residential0", "residential3"],
    ]

    power_demand={}
    power_demand["ghd6"] = 2276.0
    power_demand["residential2"] = 335.7
    power_demand["mixed1"] = 405.6
    power_demand["residential0"] = 269.4
    power_demand["residential3"] = 634.2

    plot_tac_sum_all_years_multi_bars_from_csv(
        scenario_names_by_item=scenario_names_by_item,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        titel="tac_sum_years_districts",
        short_files=short_files,
        compare_shorts=compare_shorts,
        bar_count=6,
        variants=("network", "single"),
        show_percent_box=True,
        compare_item1 = compare_item1,
        compare_item2 = compare_item2,
    )

    plot_co2_sum_all_years_multi_bars_from_csv(
        scenario_names_by_item=scenario_names_by_item,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        titel="co2_sum_years_districts",
        short_files=short_files,
        compare_shorts=compare_shorts,
        bar_count=6,
        variants=("network", "single"),
        show_percent_box=True,
        compare_item1 = compare_item1,
        compare_item2 = compare_item2,
    )


    plot_power_import_single_year_multi_bars_from_csv_per_pair(
    scenario_names_per_compare=scenario_names_per_compare,   # neu: je compare_short 1 oder 2 Szenarien
    base_dir=base_dir,
    result_dir=result_dir,
    show=True,
    show_percent_box=True,
    compare_item1=compare_item1,
    compare_item2=compare_item2,
    short_files=short_files,          # <- Dateikürzel zum Laden
    compare_shorts=compare_shorts,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=compare_items,
    target_year=target_year,
    bar_count=bar_count*2,
    variants=("network", "single"),
    # label_left="Mischquartier",
    # label_right="Wohnquartier 2",
    )

    plot_power_export_single_year_multi_bars_from_csv_per_pair(
    scenario_names_per_pair=scenario_names_per_pair,   # neu: Liste mit scenario_name für jedes Paar (len == len(short_files))
    base_dir=base_dir,
    result_dir=result_dir,
    show=True,
    show_percent_box=True,
    compare_item1=compare_item1,
    compare_item2=compare_item2,
    short_files=short_files,          # <- Dateikürzel zum Laden
    compare_shorts=compare_shorts,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=compare_items,
    target_year=target_year,
    bar_count=bar_count,
    variants=("network", "single"),
    label_left="Mischquartier",
    label_right="Wohnquartier 2",
    )



    # plot_lcoe_sum_from_three_scenarios_multi_compare(
    #     scenario_names_by_item=scenario_names_by_item,
    #     compare_item1=compare_item1,
    #     compare_item2=compare_item2,
    #     short_files=short_files,
    #     compare_shorts=compare_shorts,
    #     compare_items=compare_items,
    #     base_dir=base_dir,
    #     result_dir=result_dir,
    #     show=True,
    #     titel=None,
    #     base_calendar_year=2025,
    #     target_year=2035,
    #     show_percent_box=True,
    #     power_demand=power_demand,
    #     bar_count=6,
    # )



    # plot_device_capacities_multi_bars_from_csv(
    #     scenario_name=scenario_name,
    #     compare_shorts=compare_shorts,
    #     compare_items=compare_items,
    #     short_files=short_files,
    #     bar_count=8,  # explizit 8 Balken
    #     variants=("network", "single"),
    #     base_dir=r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results",
    #     result_dir=r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results",
    #     show=True,
    #     include_devices=None,
    #     exclude_devices=["HP", "BBOI", "EB"],
    #     titel=f"device_capacities_8bars_{scenario_name}",
    #     show_percent_box=True,
    # )

    plot_device_capacities_multi_bars_from_csv_with_TES(
        scenario_name=scenario_name,
        compare_shorts=compare_shorts,
        compare_items=compare_items,
        short_files=short_files,
        bar_count=bar_count,  
        variants=("network", "single"),
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        include_devices=None,
        exclude_devices=["BBOI"],
        titel=f"device_capacities_{scenario_name}",
        show_percent_box=True,
        fontsize1=9,
        fontsize2=7,
    )

    # plot_power_import_single_year_multi_bars_from_csv(
    #     scenario_name=scenario_name,
    #     base_dir=base_dir,
    #     result_dir=result_dir,
    #     show=True,
    #     titel=f"power_import_{target_year}_{scenario_name}",
    #     base_calendar_year=2025,
    #     show_percent_box=True,
    #     short_files=short_files,
    #     compare_shorts=compare_shorts,
    #     compare_items=compare_items,
    #     target_year=target_year,
    #     bar_count=bar_count,
    #     variants=("network", "single"),
    # )


    # plot_power_export_single_year_multi_bars_from_csv(
    #     scenario_name=scenario_name,
    #     base_dir=base_dir,
    #     result_dir=result_dir,
    #     show=True,
    #     titel=f"power_export_{target_year}_{scenario_name}",
    #     base_calendar_year=2025,
    #     short_files=short_files,
    #     show_percent_box=True,
    #     compare_shorts=compare_shorts,
    #     compare_items=compare_items,
    #     target_year=target_year,
    #     bar_count=bar_count,
    #     variants=("network", "single"),

    # )


    # plot_co2_single_year_multi_bars_from_csv(
    #     scenario_name=scenario_name,
    #     base_dir=base_dir,
    #     result_dir=result_dir,
    #     show=True,
    #     titel=f"co2_{target_year}_{scenario_name}",
    #     base_calendar_year=2025,
    #     show_percent_box=True,
    #     compare_item1=compare_item1,
    #     compare_item2=compare_item2,
    #     short_files=short_files,
    #     compare_shorts=compare_shorts,
    #     target_year=target_year,
    #     bar_count=bar_count,
    #     variants=("network", "single"),
    # )

    # plot_lcoe_single_year_multi_bars_from_csv(
    #     scenario_name=scenario_name,
    #     base_dir=base_dir,
    #     result_dir=result_dir,
    #     show=True,
    #     base_calendar_year=2025,
    #     show_percent_box=True,
    #     compare_item1="verbundweise",
    #     compare_item2="quartiersweise",
    #     titel=f"lcoe_{target_year}_{scenario_name}",
    #     short_files=short_files,
    #     compare_shorts=compare_shorts,
    #     target_year=target_year,
    #     bar_count=bar_count,
    #     variants=("network", "single"),
    # )




if __name__ == "__main__":
    main()