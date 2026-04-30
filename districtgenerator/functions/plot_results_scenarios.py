import os
import numpy as np
import matplotlib.pyplot as plt
import csv
from districtgenerator.functions.plot_results_compare import _load_single_results_file_to_dict


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
    ax.bar(x, y_main, width=width, color="#B9BABC", label="Strombezug aus dem Hauptnetz")
    ax.bar(x, y_net, width=width, bottom=y_main, color="#8A8B8D", label="Strombezug aus dem Verbundnetz")

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
    ax.set_xticks(x)
    ax.set_xticklabels([b["variant_label"] for b in bars], fontsize=8)

    pair_centers, pair_labels = [], []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    for xc, lbl in zip(pair_centers, pair_labels):
        ax.text(xc, -0.10, lbl, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=8)

    ax.set_xlim(x.min() - width, x.max() + width)
    ax.set_ylabel("Energie in MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False, fontsize=8)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

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
    ax.set_xticks(x)
    ax.set_xticklabels([b["variant_label"] for b in bars], fontsize=8)

    pair_centers, pair_labels = [], []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    for xc, lbl in zip(pair_centers, pair_labels):
        ax.text(xc, -0.10, lbl, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=8)

    ax.set_xlim(x.min() - width, x.max() + width)
    ax.set_ylabel("Energie in MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False, fontsize=8)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

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
    ax.set_xticks(x)
    ax.set_xticklabels(top_labels, fontsize=8)

    # untere Ebene: Szenarioname zentriert pro Paar
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    for xc, lbl in zip(pair_centers, pair_labels):
        ax.text(
            xc,
            -0.10,
            lbl,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=8,
        )

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

    top_labels = [b["variant_label"] for b in bars]
    ax.set_xticks(x)
    ax.set_xticklabels(top_labels, fontsize=8)

    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    for xc, lbl in zip(pair_centers, pair_labels):
        ax.text(
            xc,
            -0.10,
            lbl,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=8,
        )

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



def main():
    scenario_name = "residential2"
    short_files = ["Basis", "Bat", "PV"]  # 5 Dateien -> 10 Balken
    # 4 Compare-Shorts -> bei variants=("network","single") ergibt das 8 Balken
    compare_shorts = ["Basis", "Batterie", "Solarausbau"]
    #compare_shorts = ["B-VW", "B-QW","W-VW","W-QW", "B-VW","B-QW", "P-VW","P-QW", "WN-VW","WN-QW"]
    #compare_items = ["Basis-Szenario", "Wohnmisch-Szenario", "Batterie-Szenario", "PV-Szenario", "Wohn-Szenario"]
    compare_items = ["Basis-Szenario", "Batterie-Szenario", "Solarausbau-Szenario"]
    base_dir=r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results"
    result_dir=r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results"
    target_year = 2030


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
        bar_count=6,  # explizit 6 Balken
        variants=("network", "single"),
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        include_devices=None,
        exclude_devices=["HP", "BBOI", "EB"],
        titel=f"device_capacities_{scenario_name}",
        show_percent_box=True,
        fontsize1=9,
        fontsize2=8,
    )

    plot_power_import_single_year_multi_bars_from_csv(
        scenario_name=scenario_name,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        titel=f"power_import_{target_year}_{scenario_name}",
        base_calendar_year=2025,
        show_percent_box=True,
        short_files=short_files,
        compare_shorts=compare_shorts,
        compare_items=compare_items,
        target_year=target_year,
        bar_count=6,
        variants=("network", "single"),
    )


    plot_power_export_single_year_multi_bars_from_csv(
        scenario_name=scenario_name,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        titel=f"power_export_{target_year}_{scenario_name}",
        base_calendar_year=2025,
        short_files=short_files,
        show_percent_box=True,
        compare_shorts=compare_shorts,
        compare_items=compare_items,
        target_year=target_year,
        bar_count=6,
        variants=("network", "single"),
    )


    plot_co2_single_year_multi_bars_from_csv(
        scenario_name=scenario_name,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        titel=f"co2_{target_year}_{scenario_name}",
        base_calendar_year=2025,
        show_percent_box=True,
        compare_item1="verbundweise",
        compare_item2="quartiersweise",
        short_files=short_files,
        compare_shorts=compare_shorts,
        target_year=target_year,
        bar_count=6,
        variants=("network", "single"),
    )

    plot_lcoe_single_year_multi_bars_from_csv(
        scenario_name=scenario_name,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        base_calendar_year=2025,
        show_percent_box=True,
        compare_item1="verbundweise",
        compare_item2="quartiersweise",
        titel=f"lcoe_{target_year}_{scenario_name}",
        short_files=short_files,
        compare_shorts=compare_shorts,
        target_year=target_year,
        bar_count=6,
        variants=("network", "single"),
    )

if __name__ == "__main__":
    main()