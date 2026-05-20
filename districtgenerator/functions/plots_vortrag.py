import os
import numpy as np
import matplotlib.pyplot as plt
import csv
from districtgenerator.functions.plot_results_compare import _load_single_results_file_to_dict
from matplotlib.path import Path
from matplotlib.patches import PathPatch
import matplotlib.ticker as mticker
from collections import defaultdict


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
    fontsize=None,
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
                    total_by_year[year] = total_by_year.get(year, 0.0) + value*5

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

    # Positionen so berechnen, dass "single" immer links und "network" immer rechts steht
    x = np.zeros(len(bars), dtype=float)
    for i in range(0, len(bars), 2):
        pair_idx = i // 2
        left = pair_idx * 3.0
        right = left + 0.95
        # zwei Balken pro Paar: ordne links/rechts abhängig von variant
        if bars[i]["variant"] == "single":
            x[i] = left
            if i + 1 < len(bars):
                x[i + 1] = right
        else:
            x[i] = right
            if i + 1 < len(bars):
                x[i + 1] = left
    y = np.array([b["value"] for b in bars], dtype=float)

    fig_w_mm = 245
    fig_h_mm = 150
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
                fontsize=fontsize,
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
    ax.set_xticklabels(pair_labels, fontsize=fontsize)

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

    ax.set_ylabel("Treibhausgasemissionen in t CO₂-eq", fontsize=fontsize)
    ax.tick_params(axis="y", labelsize=fontsize)
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    # Tausenderpunkt (z.B. 1.234 statt 1,234)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", "."))
    )

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
        fontsize=fontsize,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else "co2_sum_multi_bars.png"
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




def plot_tac_sum_all_years_multi_bars_from_csv(
    scenario_names=None,
    scenario_names_by_item=None,   # neu: pro compare_item eigene 3er-Szenarien
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
    fontsize=None,
):
    """
    Summiert TAC (metric "tac_distr") aus genau 3 Quartieren und plottet beliebig viele Balken.

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

    def _read_tac_value(csv_path):
        total = 0.0
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
                total += v
        return total

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

            for sc in scen_triplet:
                if variant == "network":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")

                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")

                val = _read_tac_value(p)
                paths.append(p)
                total += val

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "value": total/1000,  # in Tausend €
                "paths": paths,
            })
            # print Debug-Info for total per compare_short
            print(f"Total TAC for {scen_label} ({short_file}): {total/1000:.2f} Tausend €")

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]



    # Positionen so berechnen, dass "single" immer links und "network" immer rechts steht
    x = np.zeros(len(bars), dtype=float)
    for i in range(0, len(bars), 2):
        pair_idx = i // 2
        left = pair_idx * 3.0
        right = left + 0.95
        # zwei Balken pro Paar: ordne links/rechts abhängig von variant
        if bars[i]["variant"] == "single":
            x[i] = left
            if i + 1 < len(bars):
                x[i + 1] = right
        else:
            x[i] = right
            if i + 1 < len(bars):
                x[i + 1] = left
    y = np.array([b["value"] for b in bars], dtype=float)

    fig_w_mm = 245
    fig_h_mm = 150
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
                fontsize=fontsize,
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
    ax.set_xticklabels(pair_labels, fontsize=fontsize)

    ax.set_xlim(x.min() - width, x.max() + width)

    ax.set_ylabel("Annuitäten der Verbünde in Tausend €/a", fontsize=fontsize)
    ax.tick_params(axis="y", labelsize=fontsize)
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    # Tausenderpunkt (z.B. 1.234 statt 1,234)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", "."))
    )

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#55585C" ),
        plt.Rectangle((0, 0), 1, 1, fc="#D40000"),
    ]
    ax.legend(
        handles,
        [compare_item2, compare_item1],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=2,
        frameon=False,
        fontsize=fontsize,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else "tac_sum_multi_bars.png"
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


def plot_device_capacities_multi_bars_from_csv_with_TES_per_pair(
    scenario_name=None,
    scenario_names_per_pair=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,
    compare_shorts=None,
    compare_items=None,
    include_devices=None,
    exclude_devices=None,
    show_percent_box=False,
    fontsize1=None,
    fontsize2=None,
    label_left=None,
    label_middle=None,
    label_right=None,
    variants=("network", "single"),
):
    """
    Per-pair Variante von plot_device_capacities_multi_bars_from_csv_with_TES,
    nutzt die gleiche Farbpalette und das enge Balkenlayout wie die TES-Version,
    lädt aber pro compare_short ein eigenes scenario_name aus scenario_names_per_pair.
    compare_shorts erscheinen nur in der Legende (nicht unter den Balken).
    """

    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

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

    if scenario_names_per_pair is None:
        if scenario_name is None:
            raise ValueError("Entweder scenario_name oder scenario_names_per_pair muss gesetzt sein.")
        scenario_names_per_pair = [scenario_name for _ in short_files]
    else:
        if isinstance(scenario_names_per_pair, str):
            scenario_names_per_pair = [scenario_names_per_pair]
        scenario_names_per_pair = list(scenario_names_per_pair)
        if len(scenario_names_per_pair) != len(short_files):
            raise ValueError("scenario_names_per_pair muss dieselbe Länge wie short_files haben.")

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
        scen_key = next(iter(parsed_dict.keys()))
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
        "WAT", "BCHP", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "CTES", "BAT", "TES", "GS"
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

    # Daten laden: pro compare_short ein eigenes scenario_name
    group_caps = []
    all_devices = set()

    for short_file, scen_label, scen_name in zip(short_files, compare_shorts, scenario_names_per_pair):
        pair_caps = {}
        for variant in variants:
            if variant == "single":
                p = os.path.join(base_dir, f"{scen_name}_{short_file}_results.csv")
            elif variant == "network":
                p = os.path.join(base_dir, f"{scen_name}_{short_file}_network_results.csv")
            else:
                raise ValueError(f"Unbekannte variant: {variant}")

            if not os.path.isfile(p):
                raise FileNotFoundError(f"Missing result file: {p}")

            pair_caps[variant] = _extract_caps(_load_single_results_file_to_dict(p))
            all_devices |= set(pair_caps[variant].keys())

        group_caps.append({
            "short_file": short_file,
            "compare_short": scen_label,
            "scenario_name": scen_name,
            "caps": pair_caps,
        })

    # Geräteauswahl und Sortierung nach preferred_order (wie TES-Version)
    if include_set is not None:
        selected = [d for d in preferred_order if d in include_set and d in all_devices]
        selected += sorted([d for d in include_set if d in all_devices and d not in preferred_order])
    else:
        selected = [d for d in preferred_order if d in all_devices]
        selected += sorted([d for d in all_devices if d not in preferred_order])

    devices = [d for d in selected if d not in exclude_set]
    if not devices:
        raise ValueError("No devices left after include/exclude filtering.")

    storage_devices = {"TES", "BAT"}
    has_storage = any(d in storage_devices for d in devices)

    # Farbpalette wie in plot_device_capacities_multi_bars_from_csv_with_TES
    colors = [
        "#721D13", "#242525", "#AC2B1C", "#4E4F50",
        "#DD402D" , "#757679", "#EC7568", "#9B9B9B",
        "#F3A69C", "#A6A8A9", "#7f7f7f", "#bcbd22"
    ]

    # Layout: enge Balken wie TES-Version
    width = 0.22
    device_step = 0.78
    group_gap = 0.6
    group_step = len(devices) * device_step + group_gap

    bars = []
    for g_idx, g in enumerate(group_caps):
        base_x = g_idx * group_step
        for d_idx, dev in enumerate(devices):
            center = base_x + d_idx * device_step
            for v_idx, variant in enumerate(variants):
                val = float(g["caps"].get(variant, {}).get(dev, 0.0) or 0.0)
                x = center + (-width / 2 if variant == "single" else width / 2)
                bars.append({
                    "group_idx": g_idx,
                    "device": dev,
                    "variant": variant,
                    "value": val,
                    "x": x,
                    "center": center,
                    "compare_short": g["compare_short"],
                    "scenario_name": g["scenario_name"],
                })

    # Y-Achsenlimits berechnen
    values_left = [b["value"] for b in bars if b["device"] not in storage_devices]
    values_right = [b["value"] for b in bars if b["device"] in storage_devices]
    left_ymax = max(values_left) if values_left else 1.0
    right_ymax = max(values_right) if values_right else 1.0

    fig_w_mm = 245
    fig_h_mm = 150
    fig, ax1 = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    ax2 = ax1.twinx() if has_storage else None

    # Balken zeichnen (Palette benutzen)
    for b in bars:
        color = "#D40000" if b["variant"] == "network" else "#55585C"
        target_ax = ax2 if (ax2 is not None and b["device"] in storage_devices) else ax1
        target_ax.bar(
            b["x"],
            b["value"],
            width=width,
            color=color,
            label="_nolegend_",
            zorder=3,
        )


    # Prozentboxen wie gehabt (optional)
    if show_percent_box:
        ymax = max(left_ymax, right_ymax, 1.0)
        ax1.set_ylim(0, left_ymax * 1.35 if left_ymax > 0 else 1.0)
        if ax2 is not None:
            ax2.set_ylim(0, right_ymax * 1.35 if right_ymax > 0 else 1.0)

        y_offset = max(left_ymax, right_ymax) * 0.035
        from collections import defaultdict
        pair_map = defaultdict(dict)
        for b in bars:
            pair_map[(b["group_idx"], b["device"])][b["variant"]] = b

        for (g_idx, dev), m in pair_map.items():
            if "network" not in m or "single" not in m:
                continue
            b_net = m["network"]
            b_sin = m["single"]
            if b_sin["value"] == 0:
                txt = "n/a" if b_net["value"] == 0 else f"+ {b_net['value']:.0f}"
            else:
                txt = _fmt_pct((b_net["value"] - b_sin["value"]) / b_sin["value"] * 100.0)
            target_ax = ax2 if (ax2 is not None and dev in storage_devices) else ax1
            target_ax.text(
                b_net["x"],
                b_net["value"] + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=fontsize2,
                bbox=dict(
                    boxstyle="square,pad=0.2",
                    facecolor="#D40000",   # alle Prozentboxen jetzt einheitlich rot
                    edgecolor="#D40000",
                    linewidth=1.0,
                ),
                zorder=5,
            )

    # X-Achse: compare_shorts anzeigen (identische, aufeinanderfolgende Labels zusammenfassen)
    centers = []
    labels = []
    for g_idx, g in enumerate(group_caps):
        base_x = g_idx * group_step
        center = base_x + 0.5 * (len(devices) - 1) * device_step
        centers.append(center)
        labels.append(str(g["compare_short"]))

    # Zusammenfassen gleicher, aufeinanderfolgender Labels (z.B. "Solarausbau-Szenario" -> nur ein Label)
    merged_centers = []
    merged_labels = []
    i = 0
    n = len(labels)
    while i < n:
        lbl = labels[i]
        j = i + 1
        sum_center = centers[i]
        count = 1
        while j < n and labels[j] == lbl:
            sum_center += centers[j]
            count += 1
            j += 1
        merged_centers.append(sum_center / count)
        merged_labels.append(lbl)
        i = j

    ax1.set_xticks(merged_centers)
    ax1.set_xticklabels(merged_labels, fontsize=fontsize1)
    ax1.tick_params(axis="x", which="both", labelbottom=True, length=0)

    #ax1.set_xlabel("Szenarien", fontsize=fontsize1)


    #ax1.set_xlabel("Szenarien", fontsize=fontsize1)  # x-Achsenbeschriftung hinzugefügt
#


    # Mit x-Achsenbeschriftung
    # ax1.set_xticks(device_centers)
    # ax1.set_xticklabels(device_labels, fontsize=fontsize1, rotation=90)
    
    # Ohne x-Achsenbeschriftung 
    # ax1.set_xticks(device_centers)
    # ax1.set_xticklabels([""] * len(device_centers))
    # ax1.tick_params(axis="x", which="both", labelbottom=False, length=0)

    

    # Trennklammern wie bei per_pair-Funktion, aber OHNE Text-Label unter den Klammern
    brace_y_ax = -0.10
    brace_h_ax = 0.035

    change_count = 0
    for g_idx, g in enumerate(group_caps):
        base_x = g_idx * group_step
        x0 = base_x
        x1 = base_x + (len(devices) - 1) * device_step

        x0_disp, _ = ax1.transData.transform((x0, 0.0))
        x1_disp, _ = ax1.transData.transform((x1, 0.0))
        inv = ax1.transAxes.inverted()
        x0_ax, _ = inv.transform((x0_disp, 0.0))
        x1_ax, _ = inv.transform((x1_disp, 0.0))

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
        patch = PathPatch(
            Path(verts, codes),
            transform=ax1.transAxes,
            fc="none",
            ec="#7A7A7A",
            lw=0.9,
            linestyle="--",
            zorder=4,
        )
        ax1.add_patch(patch)

        # Trennlinie zwischen verschiedenen Szenarien (falls nötig)
        if g_idx < len(group_caps) - 1:
            next_base = (g_idx + 1) * group_step
            next_scn = group_caps[g_idx + 1]["scenario_name"]
            if next_scn != g["scenario_name"]:
                change_count += 1
                sep_x = 0.5 * (x1 + next_base)
                ax1.axvline(sep_x, color="#7A7A7A", linestyle="--", linewidth=0.9, zorder=4, clip_on=False)
                
                if change_count == 1:
                    # Erster Wechsel: label_left und label_middle
                    if label_left:
                        ax1.text(
                            0.60,
                            1.02,
                            label_left,
                            transform=ax1.get_xaxis_transform(),
                            ha="right",
                            va="bottom",
                            fontsize=fontsize1,
                            bbox=dict(facecolor="white", edgecolor="none", pad=0.2),
                        )
                    if label_middle:
                        ax1.text(
                            sep_x + 0.02 * group_step,
                            1.02,
                            label_middle,
                            transform=ax1.get_xaxis_transform(),
                            ha="left",
                            va="bottom",
                            fontsize=fontsize1,
                            bbox=dict(facecolor="white", edgecolor="none", pad=0.2),
                        )
                else:
                    # Weitere Wechsel: nur label_right
                    if label_right:
                        ax1.text(
                            sep_x + 0.05 * group_step,
                            1.02,
                            label_right,
                            transform=ax1.get_xaxis_transform(),
                            ha="left",
                            va="bottom",
                            fontsize=fontsize1,
                            bbox=dict(facecolor="white", edgecolor="none", pad=0.2),
                        )

    ax1.set_ylabel("PV-Anlagenleistung in kW", fontsize=fontsize1)
    ax1.tick_params(axis="y", labelsize=fontsize1)
    ax1.grid(axis="y", alpha=0.35)

    # Achsen-Formatierung wie TES-Version
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", "."),)
    )
    if ax2 is not None:
        ax2.set_ylabel("Speicherkapazität in kWh", fontsize=fontsize1)
        ax2.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", "."))
        )

    ax1.tick_params(axis="y", labelsize=fontsize1)
    if ax2 is not None:
        ax2.tick_params(axis="y", labelsize=fontsize1)

    # Legende: Farbe -> compare_item1 / compare_item2
    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#55585C"),
        plt.Rectangle((0, 0), 1, 1, fc="#D40000"),
    ]
    ax1.legend(
        handles,
        [compare_item2, compare_item1],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=2,
        frameon=False,
        fontsize=fontsize1,
    )


    fig.tight_layout()
    fig.subplots_adjust(bottom=0.15)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else "device_capacities_pv.png"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300, bbox_inches="tight", pad_inches=0.08)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "devices": devices,
        "bars": bars,
        "plot_path": plot_path,
        "scenario_names_per_pair": scenario_names_per_pair,
    }



def plot_tac_per_demand_sum_all_years_multi_bars_from_csv(
    scenario_names=None,
    scenario_names_by_item=None,
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
    power_demand=None,
    fontsize=None,
):
    """
    Spezifische jährliche Gesamtkosten (€/MWh) über compare_items:
      value = sum(mean(tac_district je scenario)) / sum(mean(total_heat_supply_by_year je scenario) + power_demand[scenario])

    - Pro compare_item (Zeile in scenario_names_by_item) werden 3 scenario_names erwartet.
    - Pro scenario wird aus network/single-Datei gelesen.
    """
    if power_demand is None or not isinstance(power_demand, dict):
        raise ValueError("power_demand muss als Dictionary gesetzt sein.")

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

    if scenario_names_by_item is None:
        if scenario_names is None or len(scenario_names) != 3:
            raise ValueError(
                "scenario_names muss genau 3 Einträge haben oder scenario_names_by_item muss gesetzt sein."
            )
        scenario_names_by_item = [list(scenario_names) for _ in short_files]
    else:
        if len(scenario_names_by_item) != len(short_files):
            raise ValueError("scenario_names_by_item muss genauso lang sein wie short_files.")
        for triplet in scenario_names_by_item:
            if not isinstance(triplet, (list, tuple)) or len(triplet) != 3:
                raise ValueError("Jeder Eintrag in scenario_names_by_item muss genau 3 Szenarien enthalten.")

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

    def _read_tac_and_supply_means(csv_path):
        tac_vals = []
        supply_by_year = {}

        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                cat = str(row.get("category", "")).strip()
                metric = str(row.get("metric", "")).strip()
                val = _safe_parse_value(row.get("value"))
                if val is None:
                    continue

                if cat == "optimization" and metric == "tac_distr":
                    tac_vals.append(float(val))

                if cat == "yearly_totals" and metric == "total_heat_supply_by_year":
                    try:
                        year = int(float(row.get("year", 0)))
                        supply_by_year[year] = float(val)
                    except (TypeError, ValueError):
                        continue

        if not tac_vals:
            raise ValueError(
                f"Keine Werte gefunden für category='optimization' & metric='tac_distr' in Datei: {csv_path}"
            )
        if not supply_by_year:
            raise ValueError(
                f"Keine Werte gefunden für category='yearly_totals' & metric='total_heat_supply_by_year' in Datei: {csv_path}"
            )

        # TAC: SUMME
        tac_sum = float(np.sum(tac_vals))

        # Wärme: gewichteter Mittelwert
        # Jahre 0, 5, 10, 15: Faktor 5
        # Jahr 20: Faktor 1
        weighted_sum = 0.0
        for year in [0, 5, 10, 15]:
            if year in supply_by_year:
                weighted_sum += supply_by_year[year] * 5.0
        if 20 in supply_by_year:
            weighted_sum += supply_by_year[20] * 1.0

        supply_mean = weighted_sum / 21.0

        return tac_sum, supply_mean

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    bars = []
    for short_file, scen_label, scen_triplet in zip(short_files, compare_shorts, scenario_names_by_item):
        for variant in variants:
            tac_total = 0.0
            demand_total = 0.0
            paths = []

            for sc in scen_triplet:
                if sc not in power_demand:
                    raise KeyError(f"power_demand enthält keinen Eintrag für scenario_name='{sc}'.")

                if variant == "network":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")

                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")

                tac_sum, supply_mean = _read_tac_and_supply_means(p)
                tac_total += tac_sum
                pd = float(power_demand[sc])

                demand_total += (supply_mean + pd)
                paths.append(p)

            value = tac_total / demand_total if demand_total > 0 else 0.0

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "QW" if variant == "single" else "VW",
                "value": value,
                "tac_total": tac_total,
                "demand_total": demand_total,
                "paths": paths,
            })

            print(
                f"[DEBUG] {scen_label} | {variant}: "
                f"sum(TAC)={tac_total:.3f}, sum(mean Supply+Power)={demand_total:.3f}, "
                f"spezifisch={value:.6f} €/MWh"
            )

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]



    # Positionen so berechnen, dass "single" immer links und "network" immer rechts steht
    x = np.zeros(len(bars), dtype=float)
    for i in range(0, len(bars), 2):
        pair_idx = i // 2
        left = pair_idx * 3.0
        right = left + 0.95
        # zwei Balken pro Paar: ordne links/rechts abhängig von variant
        if bars[i]["variant"] == "single":
            x[i] = left
            if i + 1 < len(bars):
                x[i + 1] = right
        else:
            x[i] = right
            if i + 1 < len(bars):
                x[i + 1] = left
    y = np.array([b["value"] for b in bars], dtype=float)


    fig_w_mm = 245
    fig_h_mm = 150
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58

    for i, b in enumerate(bars):
        ax.bar(
            x[i],
            y[i],
            width=width,
            #color=("#D40000" if b["variant"] == "network" else "#55585C"),
            color=("#55585C" if b["variant"] == "single" else "#D40000"),
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
                fontsize=fontsize,
                bbox=dict(
                    boxstyle="square,pad=0.25",
                    facecolor="#D40000",
                    edgecolor="#D40000",
                    linewidth=1.0,
                ),
                zorder=5,
            )

    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=fontsize)
    ax.set_xlim(x.min() - width, x.max() + width)

    ax.set_ylabel("Spez. jährliche Gesamtkosten in €/MWh", fontsize=fontsize)
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", "."))
    )

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
        fontsize=fontsize,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else "tac_per_demand_multi_bars.png"
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



def plot_power_import_all_years_multi_bars_from_csv_per_pair(
    scenario_name=None,
    scenario_names_per_pair=None,      # alt: 1 Szenario je compare_short
    scenario_names_per_compare=None,   # neu: je compare_short 1-3 Szenarien
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
    label_left=None,
    label_right=None,
    fontsize=None,
):
    """
    Wie plot_power_import_single_year_multi_bars_from_csv_per_pair aber summiert
    über alle Jahre (alle in der Datei vorhandenen Jahre) die beiden Metriken
    from_el_main_grid_total und from_network_total. Zusätzlich unterstützt
    scenario_names_per_compare wie die single-year per-pair Funktion, d.h.
    pro compare_short können 1..3 scenario_names angegeben werden.
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

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

    # -------- Szenario-Setup je compare_short --------
    # Ziel: pro compare_short 1..3 Szenarien zulassen (scenario_names_per_compare)
    scenarios_by_compare = []

    if scenario_names_per_compare is not None:
        if len(scenario_names_per_compare) != len(short_files):
            raise ValueError("scenario_names_per_compare muss dieselbe Länge wie short_files haben.")
        for entry in scenario_names_per_compare:
            if isinstance(entry, str):
                scenarios_by_compare.append([entry])
            elif isinstance(entry, (list, tuple)) and 1 <= len(entry) <= 3:
                scenarios_by_compare.append(list(entry))
            else:
                raise ValueError("Jeder Eintrag in scenario_names_per_compare muss str oder Liste/Tuple mit 1-3 Einträgen sein.")
    else:
        # Fallback auf altes Verhalten / scenario_names_per_pair
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

    def _read_yearly_import_weighted(csv_path):
        """
        Summiert from_el_main_grid_total und from_network_total mit Gewichtung:
        - Jahre 1-4: Wert * 5
        - Jahr 5: Wert * 1
        """
        yearly_data = {}  # year -> {"from_el_main_grid_total": val, "from_network_total": val}
        
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "yearly_totals":
                    continue
                metric = row.get("metric")
                if metric not in ("from_el_main_grid_total", "from_network_total"):
                    continue
                
                try:
                    year = int(row.get("year", 0))
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue
                
                if year not in yearly_data:
                    yearly_data[year] = {}
                yearly_data[year][metric] = v
        
        # Berechne gewichtete Summe
        main_total = 0.0
        net_total = 0.0
        
        for year in sorted(yearly_data.keys()):
            weight = 5 if year <= 19 else 1  # Jahre 1-4: Faktor 5, Jahr 5+: Faktor 1
            
            main_val = yearly_data[year].get("from_el_main_grid_total", 0.0)
            net_val = yearly_data[year].get("from_network_total", 0.0)
            
            main_total += main_val * weight
            net_total += net_val * weight
        
        return main_total, net_total



    # Bars erzeugen — pro compare_short können mehrere Szenarien (Slots) gezeichnet werden
    bars = []
    group_meta = []

    # spacing / layout (ähnlich wie single-year per-pair)
    width = 0.35
    inner_step = 0.35
    scenario_gap = 0.55
    group_step = 2.8

    for g_idx, (short_file, scen_label, scen_list) in enumerate(zip(short_files, compare_shorts, scenarios_by_compare)):
        group_x = []
        base_x = g_idx * group_step
        x_cursor = base_x

        for s_idx, scen_for_group in enumerate(scen_list):
            group_bars = []
            for variant in variants:
                if variant == "network":
                    p = os.path.join(base_dir, f"{scen_for_group}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{scen_for_group}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")

                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")

                main_sum, net_sum = _read_yearly_import_weighted(p)

                group_bars.append({
                    "group_idx": g_idx,
                    "x": 0,  # wird später gesetzt
                    "short_file": short_file,
                    "compare_short": scen_label,
                    "scenario_used": scen_for_group,
                    "scenario_slot": s_idx,
                    "variant": variant,
                    "main": main_sum/1000.0,
                    "net": net_sum/1000.0,
                    "total": (main_sum + net_sum)/1000.0,
                    "path": p,
                })

            # Ordne die Balken um: single links (erste Pos), network rechts (zweite Pos)
            ordered = []
            for v in ("single", "network"):
                for b in group_bars:
                    if b["variant"] == v:
                        ordered.append(b)

            # Aktualisiere x-Positionen für ordered bars
            for idx, b in enumerate(ordered):
                b["x"] = x_cursor + idx * inner_step
                group_x.append(b["x"])
                bars.append(b)

            x_cursor = x_cursor + (len(variants) - 1) * inner_step + scenario_gap


        if group_x:
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

    if not bars:
        raise ValueError("Keine Balken erstellt (keine Daten).")

    x = np.array([b["x"] for b in bars], dtype=float)
    y_main = np.array([b["main"] for b in bars], dtype=float)
    y_net = np.array([b["net"] for b in bars], dtype=float)

    #fig_w_mm, fig_h_mm = 155, 100
    fig_w_mm = 160
    fig_h_mm = 130
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

    # Prozentboxen (optional)
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
            ax.plot([x[i], x[i]], [line_y0, line_y1], color="#7A7A7A", linewidth=0.9, zorder=6, clip_on=False)
            ax.text(
                x[i],
                box_y,
                txt,
                ha="center",
                va="bottom",
                fontsize=fontsize-2,
                fontweight="bold",
                color="black",
                bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor=(color_main_vw if bars[i]["variant"] == "network" else color_main_qw), linewidth=0.9),
                zorder=7,
                clip_on=False,
            )

    # 1) Zentren pro Balkenpaar (group_idx, scenario_slot)
    pair_xs = defaultdict(list)
    pair_scn = {}
    for b in bars:
        key = (b["group_idx"], b["scenario_slot"])
        pair_xs[key].append(b["x"])
        pair_scn[key] = b["scenario_used"]

    keys_sorted = sorted(pair_xs.keys(), key=lambda t: (t[0], t[1]))
    pair_centers = []
    pair_labels = []

    # Mapping für Szenarionamen -> Anzeige (aus single-year per-pair)
    scenario_name_map = {
        "residential2": "Wohn 1",
        "residential0": "Wohn 2",
        "residential3": "Wohn 3",
        "ghd6": "Gewerbe",
        "mixed1": "Misch",
    }

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
            fontsize=fontsize,
        )

    # 2) Zeichne Klammer und compare_short-Label pro Gruppe (axes coords)
    brace_y_ax = -0.085
    brace_h_ax = 0.035
    label_y_ax = -0.125

    for gm, comp_short in zip(group_meta, compare_shorts):
        x0 = gm["x_min"]
        x1 = gm["x_max"]
        x0_disp, _ = ax.transData.transform((x0, 0.0))
        x1_disp, _ = ax.transData.transform((x1, 0.0))
        inv = ax.transAxes.inverted()
        x0_ax, _ = inv.transform((x0_disp, 0.0))
        x1_ax, _ = inv.transform((x1_disp, 0.0))

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

        ax.text(
            0.5 * (x0_ax + x1_ax),
            label_y_ax,
            str(comp_short),
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=fontsize,
        )

    fig.subplots_adjust(bottom=0.10)

    if len(x):
        ax.set_xlim(np.min(x) - width, np.max(x) + width)

    ax.set_xticks([])
    ax.set_ylabel("Strombezug in GWh", fontsize=fontsize)
    ax.tick_params(axis="y", labelsize=fontsize)
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", ".")))

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
    #ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False, fontsize=fontsize)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.1)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else f"power_import_all_years_multibars_percompare.png"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"scenario_names_per_compare": scenario_names_per_compare or scenario_names_per_pair or [scenario_name], "bars": bars, "plot_path": plot_path}


def plot_power_export_all_years_multi_bars_from_csv_per_pair(
    scenario_name=None,
    scenario_names_per_pair=None,
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
    label_left=None,
    label_right=None,
    fontsize=None,
):
    """
    Wie plot_power_export_single_year_multi_bars_from_csv_per_pair, aber summiert
    "to_el_main_grid_total" und "to_network_total" über ALLE Jahre in der Datei
    statt nur ein einzelnes Jahr auszuwählen.
    
    Pro compare_short kann über scenario_names_per_pair ein eigenes Quartier gesetzt werden.
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

    def _read_yearly_export_weighted(csv_path):
        """
        Summiert to_el_main_grid_total und to_network_total mit Gewichtung:
        - Jahre 1-4: Wert * 5
        - Jahr 5: Wert * 1
        """
        yearly_data = {}  # year -> {"to_el_main_grid_total": val, "to_network_total": val}
        
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "yearly_totals":
                    continue
                metric = row.get("metric")
                if metric not in ("to_el_main_grid_total", "to_network_total"):
                    continue
                
                try:
                    year = int(row.get("year", 0))
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue
                
                if year not in yearly_data:
                    yearly_data[year] = {}
                yearly_data[year][metric] = v
        
        # Berechne gewichtete Summe
        main_total = 0.0
        net_total = 0.0
        
        for year in sorted(yearly_data.keys()):
            weight = 5 if year <= 19 else 1  # Jahre 1-4: Faktor 5, Jahr 5+: Faktor 1
            
            main_val = yearly_data[year].get("to_el_main_grid_total", 0.0)
            net_val = yearly_data[year].get("to_network_total", 0.0)
            print(f"[DEBUG] Year {year}: main={main_val}, net={net_val}, weight={weight}")
            
            main_total += main_val * weight
            net_total += net_val * weight
        
        return main_total, net_total

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

            main_val, net_val = _read_yearly_export_weighted(p)

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

    #fig_w_mm, fig_h_mm = 155, 100
    fig_w_mm = 245
    fig_h_mm = 150
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58


    # Farben nach Optimierungsart
    color_main_vw = "#E43D30"  # hellrot (VW Hauptnetz)
    color_net_vw = "#8C1D17"    # dunkelrot (VW Verbundnetz)
    color_main_qw = "#B9BABC"   # QW Hauptnetz
    color_net_qw = "#8A8B8D"    # QW Verbundnetz

    # Zeichne Balken paarweise, mit unterschiedlicher Farbgebung für VW vs QW
    for i, b in enumerate(bars):
        if b["variant"] == "network":  # VW = linke Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_vw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_vw, label="_nolegend_")
        else:  # QW = rechte Balken im Paar
            ax.bar(x[i], y_main[i], width=width, color=color_main_qw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_qw, label="_nolegend_")

    # Prozentboxen
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
                fontsize=fontsize,
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
    ax.set_xticklabels(pair_labels, fontsize=fontsize)

    # Trennlinien zwischen verschiedenen Szenarien
    if label_left or label_right:
        if len(pair_centers) > 1:
            center_delta = pair_centers[1] - pair_centers[0]
        else:
            center_delta = (x.max() - x.min()) if len(x) > 1 else width * 2.0
        x_offset = center_delta * 0.20

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
                        fontsize=fontsize,
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
                        fontsize=fontsize,
                        bbox=dict(facecolor="white", edgecolor="none", pad=0.2),
                        zorder=6,
                    )

    ax.set_xlim(x.min() - width, x.max() + width)
    ax.set_ylabel("Energie in MWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    # Tausenderpunkt
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", "."))
    )

    # Legende
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
        fontsize=fontsize,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else f"power_export_all_years_multibars_{scenario_names_per_pair[0]}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"scenario_names_per_pair": scenario_names_per_pair, "bars": bars, "plot_path": plot_path}

def plot_tes_capacity_sum_from_three_scenarios_multi_compare(
    scenario_names_per_compare=None,   # Liste von 3er-Listen, je compare_short
    scenario_names_by_item=None,       # Alias
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,
    compare_shorts=None,
    compare_items=None,
    bar_count=None,
    variants=("network", "single"),
    show_percent_box=False,
    fontsize1=8,
    fontsize2=8,
):
    """
    Summiert die TES-Kapazität aus genau 3 Szenarien je compare_short
    und stellt die Summen für verbundweise (network) und quartiersweise (single)
    als Balkenpaar dar.

    Erwartung:
      scenario_names_per_compare = [
          ["scenario_a1", "scenario_a2", "scenario_a3"],
          ["scenario_b1", "scenario_b2", "scenario_b3"],
          ...
      ]
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

    # Alias unterstützen
    if scenario_names_per_compare is None:
        scenario_names_per_compare = scenario_names_by_item

    if scenario_names_per_compare is None:
        raise ValueError("scenario_names_per_compare muss gesetzt sein.")

    if len(scenario_names_per_compare) != len(short_files):
        raise ValueError("scenario_names_per_compare muss dieselbe Länge wie short_files haben.")

    for triplet in scenario_names_per_compare:
        if not isinstance(triplet, (list, tuple)) or len(triplet) != 3:
            raise ValueError("Jeder Eintrag in scenario_names_per_compare muss genau 3 Szenarien enthalten.")

    def _extract_tes_capacity(parsed_dict, scenario_name):
        if not parsed_dict:
            return 0.0
        scen_key = scenario_name if scenario_name in parsed_dict else next(iter(parsed_dict.keys()))
        scen = parsed_dict.get(scen_key, {})
        dev_cat = scen.get("device", {})
        caps = dev_cat.get("by_device", {}).get("capacity", {}) or {}
        return float(caps.get("TES", 0.0) or 0.0)

    bars = []
    for short_file, scen_label, triplet in zip(short_files, compare_shorts, scenario_names_per_compare):
        for variant in variants:
            total_tes = 0.0
            paths = []

            for sc in triplet:
                if variant == "network":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{sc}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")

                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")

                parsed = _load_single_results_file_to_dict(p)
                total_tes += _extract_tes_capacity(parsed, sc)
                paths.append(p)
            print(f"[DEBUG] {scen_label} - {variant}: total TES={total_tes:.2f} kWh from scenarios {triplet}")

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "value": total_tes,
                "paths": paths,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    if not bars:
        raise ValueError("Keine Balken erstellt.")

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y = np.array([b["value"] for b in bars], dtype=float)

    fig_w_mm = 245
    fig_h_mm = 150
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58

    color_net = "#D40000"
    color_sin = "#55585C"

    for i, b in enumerate(bars):
        ax.bar(
            x[i],
            y[i],
            width=width,
            color=(color_net if b["variant"] == "network" else color_sin),
            label="_nolegend_",
        )

    if show_percent_box:
        ymax = max(float(np.max(y)) if len(y) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)
        y_offset = ymax * 0.06

        for i in range(0, len(bars), 2):
            if i + 1 >= len(bars):
                break

            net_val = bars[i]["value"]
            sin_val = bars[i + 1]["value"]

            if sin_val == 0:
                txt = "n/a" if net_val == 0 else "+∞"
            else:
                txt = f"{((net_val - sin_val) / sin_val * 100.0):+.0f}%".replace(".", ",")

            ax.text(
                x[i],
                net_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=fontsize2,
                bbox=dict(
                    boxstyle="square,pad=0.25",
                    facecolor=color_net,
                    edgecolor=color_net,
                    linewidth=1.0,
                ),
                zorder=5,
            )

    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=fontsize1)
    ax.set_xlim(x.min() - width, x.max() + width)

    ax.set_ylabel("Thermische Speicherkapazitäten in kWh")
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", "."))
    )

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_net),
        plt.Rectangle((0, 0), 1, 1, fc=color_sin),
    ]
    ax.legend(
        handles,
        [compare_item1 or "verbundweise", compare_item2 or "quartiersweise"],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=2,
        frameon=False,
        fontsize=fontsize1,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.pdf" if titel else "tes_capacity_sum_multi_compare.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {
        "bars": bars,
        "plot_path": plot_path,
    }

def plot_power_import_sum_from_rows_multi_bars_from_csv_per_compare(
    scenario_names_per_compare=None,
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
    label_left=None,
    label_right=None,
    fontsize=None,
):
    """
    Summiert pro Zeile in scenario_names_per_compare alle Szenarien:
    - from_el_main_grid_total
    - from_network_total

    Ergebnis: ein Balkenpaar je compare_short und je Zeile in scenario_names_per_compare.
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

    if scenario_names_per_compare is None:
        raise ValueError("scenario_names_per_compare muss gesetzt sein.")
    if len(scenario_names_per_compare) != len(short_files):
        raise ValueError("scenario_names_per_compare muss dieselbe Länge wie short_files haben.")

    for row in scenario_names_per_compare:
        if not isinstance(row, (list, tuple)) or len(row) < 1:
            raise ValueError("Jede Zeile in scenario_names_per_compare muss 1..n Szenarien enthalten.")

    def _read_yearly_import_weighted(csv_path):
        yearly_data = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "yearly_totals":
                    continue
                metric = row.get("metric")
                if metric not in ("from_el_main_grid_total", "from_network_total"):
                    continue
                try:
                    year = int(float(row.get("year", 0)))
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue
                yearly_data.setdefault(year, {})[metric] = v

        main_total = 0.0
        net_total = 0.0
        for year in sorted(yearly_data.keys()):
            weight = 5 if year <= 19 else 1
            main_total += yearly_data[year].get("from_el_main_grid_total", 0.0) * weight
            net_total += yearly_data[year].get("from_network_total", 0.0) * weight

        return main_total, net_total

    bars = []
    for g_idx, (short_file, comp_short, scen_row) in enumerate(zip(short_files, compare_shorts, scenario_names_per_compare)):
        # sammle gruppenweise und ordne dann so, dass links 'single' und rechts 'network' steht
        group_bars = []
        for variant in variants:
            main_total = 0.0
            net_total = 0.0
            paths = []
            for scen in scen_row:
                if variant == "network":
                    p = os.path.join(base_dir, f"{scen}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{scen}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")
                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")
                m, n = _read_yearly_import_weighted(p)
                main_total += m
                net_total += n
                paths.append(p)

            group_bars.append({
                "group_idx": g_idx,
                "compare_short": comp_short,
                "variant": variant,
                "value_main": main_total / 1000.0,
                "value_net": net_total / 1000.0,
                "value_total": (main_total + net_total) / 1000.0,
                "paths": paths,
            })

        # gewünschte Reihenfolge: 'single' links, 'network' rechts; Rest anhängen
        ordered = []
        for v in ("single", "network"):
            for b in group_bars:
                if b["variant"] == v:
                    ordered.append(b)
        for b in group_bars:
            if b not in ordered:
                ordered.append(b)

        bars.extend(ordered)

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y_main = np.array([b["value_main"] for b in bars], dtype=float)
    y_net = np.array([b["value_net"] for b in bars], dtype=float)

    fig_w_mm = 245
    fig_h_mm = 150
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.58


    color_main_vw = "#D40000"
    color_net_vw = "#DD847D"
    color_main_qw = "#55585C" 
    color_net_qw = "#B9BABC"

    for i, b in enumerate(bars):
        if b["variant"] == "network":
            ax.bar(x[i], y_main[i], width=width, color=color_main_vw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_vw, label="_nolegend_")
        else:
            ax.bar(x[i], y_main[i], width=width, color=color_main_qw, label="_nolegend_")
            ax.bar(x[i], y_net[i], width=width, bottom=y_main[i], color=color_net_qw, label="_nolegend_")
    # Prozentboxen (optional)
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
            ax.plot([x[i], x[i]], [line_y0, line_y1], color="#7A7A7A", linewidth=0.9, zorder=6, clip_on=False)
            ax.text(
                x[i],
                box_y,
                txt,
                ha="center",
                va="bottom",
                fontsize=fontsize-2,
                fontweight="bold",
                color="black",
                bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor=(color_main_vw if bars[i]["variant"] == "network" else color_main_qw), linewidth=0.9),
                zorder=7,
                clip_on=False,
            )



    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        center = 0.5 * (x[i] + x[i + 1]) if i + 1 < len(bars) else x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=fontsize)
    ax.set_xlim(x.min() - width, x.max() + width)
    ax.set_ylabel("Strombezug in GWh", fontsize=fontsize)
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", ".")))

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_main_qw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_qw),
        plt.Rectangle((0, 0), 1, 1, fc=color_main_vw),
        plt.Rectangle((0, 0), 1, 1, fc=color_net_vw),
    ]
    labels = [
        "Hauptnetz quartiersweise",
        "Verbundnetz quartiersweise",
        "Hauptnetz verbundweise",
        "Verbundnetz verbundweise",

    ]
    ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False, fontsize=fontsize)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.2)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else "power_import_sum_from_rows_multi_bars.png"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"bars": bars, "plot_path": plot_path}


def plot_import_main_grid_sum_all_years_multi_bars_from_csv(
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
    fontsize=None,
):
    """
    Summiert Strombezug aus dem Hauptnetz und plottet beliebig viele Balken.

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
                if row.get("category") != "yearly_totals":
                    continue
                if row.get("metric") != "from_el_main_grid_total":
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
                    total_by_year[year] = total_by_year.get(year, 0.0) + value*5

            # falls weiterhin ein einzelner Wert pro Balken gebraucht wird:
            total = sum(total_by_year.values())
            #print(f"Total CO2 für {scen_label} ({variant}): {total:.2f} tCO₂e über alle Jahre (Details: {total_by_year})")

            bars.append({
                "short_file": short_file,
                "compare_short": scen_label,
                "variant": variant,
                "variant_label": "VW" if variant == "network" else "QW",
                "value": total/1000.0,  # from MWh to GWh
                "paths": paths,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    # Positionen so berechnen, dass "single" immer links und "network" immer rechts steht
    x = np.zeros(len(bars), dtype=float)
    for i in range(0, len(bars), 2):
        pair_idx = i // 2
        left = pair_idx * 3.0
        right = left + 0.95
        # zwei Balken pro Paar: ordne links/rechts abhängig von variant
        if bars[i]["variant"] == "single":
            x[i] = left
            if i + 1 < len(bars):
                x[i + 1] = right
        else:
            x[i] = right
            if i + 1 < len(bars):
                x[i + 1] = left
    y = np.array([b["value"] for b in bars], dtype=float)

    fig_w_mm = 245
    fig_h_mm = 150
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
                fontsize=fontsize,
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
    ax.set_xticklabels(pair_labels, fontsize=fontsize)

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

    ax.set_ylabel("Strombezug aus dem Hauptnetz in GWh", fontsize=fontsize)
    ax.tick_params(axis="y", labelsize=fontsize)
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    # Tausenderpunkt (z.B. 1.234 statt 1,234)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", "."))
    )

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc="#55585C"),
        plt.Rectangle((0, 0), 1, 1, fc="#D40000"),
    ]
    ax.legend(
        handles,
        [compare_item2, compare_item1],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=2,
        frameon=False,
        fontsize=fontsize,
    )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else "co2_sum_multi_bars.png"
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


def plot_power_import_main_grid_all_years_multi_bars_from_csv_per_pair(
    scenario_name=None,
    scenario_names_per_pair=None,
    scenario_names_per_compare=None,
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
    label_left=None,
    label_right=None,
    fontsize=None,
    ):
    """
    Variante von plot_power_import_all_years_multi_bars_from_csv_per_pair,
    zeigt NUR 'from_el_main_grid_total' (Hauptnetz-Bezug) förmlich pro Balken.

    Unterstützt scenario_names_per_compare wie die andere Funktion (pro compare_short 1..3 Szenarien).
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

    if len(compare_shorts) != len(short_files):
        raise ValueError("compare_shorts und short_files müssen gleich lang sein.")

    # Szenario-Setup
    scenarios_by_compare = []
    if scenario_names_per_compare is not None:
        if len(scenario_names_per_compare) != len(short_files):
            raise ValueError("scenario_names_per_compare muss dieselbe Länge wie short_files haben.")
        for entry in scenario_names_per_compare:
            if isinstance(entry, str):
                scenarios_by_compare.append([entry])
            elif isinstance(entry, (list, tuple)) and 1 <= len(entry) <= 3:
                scenarios_by_compare.append(list(entry))
            else:
                raise ValueError("Jeder Eintrag in scenario_names_per_compare muss str oder Liste/Tuple mit 1-3 Einträgen sein.")
    else:
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

    def _read_yearly_main_weighted(csv_path):
        yearly = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if row.get("category") != "yearly_totals":
                    continue
                metric = row.get("metric")
                if metric != "from_el_main_grid_total":
                    continue
                try:
                    year = int(float(row.get("year", 0)))
                    v = float(row.get("value"))
                except (TypeError, ValueError):
                    continue
                yearly[year] = yearly.get(year, 0.0) + v

        total = 0.0
        for year in sorted(yearly.keys()):
            weight = 5 if year <= 19 else 1
            total += yearly[year] * weight
        return total

    def _fmt_pct(p):
        s = f"{p:+.0f}%" if abs(p - round(p)) < 0.05 else f"{p:+.1f}%"
        return s.replace(".", ",")

    bars = []
    group_meta = []
    # layout
    #width = 0.58
    width = 0.35
    inner_step = 0.35
    scenario_gap = 0.55
    group_step = 2.8

    for g_idx, (short_file, scen_label, scen_list) in enumerate(zip(short_files, compare_shorts, scenarios_by_compare)):
        base_x = g_idx * group_step
        x_cursor = base_x
        group_x = []
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

                main_sum = _read_yearly_main_weighted(p)
                # position: single links, network rechts (falls beide vorhanden)
                if len(variants) == 1:
                    bx = x_cursor
                elif variant == "single":
                    bx = x_cursor - inner_step * 0.5
                elif variant == "network":
                    bx = x_cursor + inner_step * 0.5
                else:
                    bx = x_cursor + v_idx * inner_step


                group_x.append(bx)

                bars.append({
                    "group_idx": g_idx,
                    "x": bx,
                    "short_file": short_file,
                    "compare_short": scen_label,
                    "scenario_used": scen_for_group,
                    "scenario_slot": s_idx,
                    "variant": variant,
                    "main": main_sum / 1000.0,  # MWh -> GWh
                    "path": p,
                })

            x_cursor = x_cursor + (len(variants) - 1) * inner_step + scenario_gap

        if group_x:
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

    if not bars:
        raise ValueError("Keine Balken erstellt (keine Daten).")

    x = np.array([b["x"] for b in bars], dtype=float)
    y = np.array([b["main"] for b in bars], dtype=float)


    fig_w_mm = 160
    fig_h_mm = 130
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))

    color_main_vw = "#D40000"
    color_main_qw = "#55585C"


    for i, b in enumerate(bars):
        col = color_main_vw if b["variant"] == "network" else color_main_qw
        ax.bar(x[i], y[i], width=width, color=col, label="_nolegend_")

    # Prozentboxen: relative Änderung network vs single pro Balkenpaar
    if show_percent_box:
        ymax = max(float(np.max(y)) if len(y) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)
        y_offset = ymax * 0.06
        for i in range(0, len(bars), 2):
            if i + 1 >= len(bars):
                break
            net_val = bars[i]["main"]
            sin_val = bars[i + 1]["main"]
            if sin_val == 0:
                txt = "n/a" if net_val == 0 else "+∞"
            else:
                txt = _fmt_pct((net_val - sin_val) / sin_val * 100.0)
            ax.text(
                x[i],
                net_val + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=fontsize,
                bbox=dict(
                    boxstyle="square,pad=0.25",
                    facecolor=color_main_vw,
                    edgecolor=color_main_vw,
                    linewidth=1.0,
                ),
                zorder=5,
            )

    # erste Ebene: Szenarionamen unter jedem Balkenpaar
    pair_xs = defaultdict(list)
    pair_scn = {}
    for b in bars:
        key = (b["group_idx"], b["scenario_slot"])
        pair_xs[key].append(b["x"])
        pair_scn[key] = b["scenario_used"]
    keys_sorted = sorted(pair_xs.keys(), key=lambda t: (t[0], t[1]))
    pair_centers = []
    pair_labels = []
    scenario_name_map = {
        "residential2": "Wohn 1",
        "residential0": "Wohn 2",
        "residential3": "Wohn 3",
        "ghd6": "Gewerbe",
        "mixed1": "Misch",
    }
    for k in keys_sorted:
        xs = pair_xs[k]
        center = float(np.mean(xs))
        pair_centers.append(center)
        scen = pair_scn.get(k, "")
        pair_labels.append(scenario_name_map.get(scen, scen))
    for xc, lbl in zip(pair_centers, pair_labels):
        ax.text(
            xc,
            -0.06,
            lbl,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=fontsize,
        )

    # Klammern und compare_short-Label pro Gruppe
    brace_y_ax = -0.085
    brace_h_ax = 0.035
    label_y_ax = -0.125
    for gm, comp_short in zip(group_meta, compare_shorts):
        x0 = gm["x_min"]
        x1 = gm["x_max"]
        x0_disp, _ = ax.transData.transform((x0, 0.0))
        x1_disp, _ = ax.transData.transform((x1, 0.0))
        inv = ax.transAxes.inverted()
        x0_ax, _ = inv.transform((x0_disp, 0.0))
        x1_ax, _ = inv.transform((x1_disp, 0.0))

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
        patch = PathPatch(Path(verts, codes), transform=ax.transAxes, fc="none", ec="#7A7A7A", lw=0.9, linestyle="--", zorder=4)
        ax.add_patch(patch)

        ax.text(
            0.5 * (x0_ax + x1_ax),
            label_y_ax,
            str(comp_short),
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=fontsize,
        )

    fig.subplots_adjust(bottom=0.30)
    if len(x):
        ax.set_xlim(np.min(x) - width, np.max(x) + width)

    ax.set_xticks([])
    ax.set_ylabel("Strombezug aus dem Hauptnetz in GWh", fontsize=fontsize)
    ax.tick_params(axis="y", labelsize=fontsize)
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, pos: f"{int(round(x)):,}".replace(",", ".")))

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_main_qw),
        plt.Rectangle((0, 0), 1, 1, fc=color_main_vw),
    ]
    labels = [
        "quartiersweise",
        "verbundweise",
    ]
    #ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False, fontsize=fontsize)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.1)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else "power_import_main_grid_all_years_multibars_percompare.png"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"scenario_names_per_compare": scenario_names_per_compare or scenario_names_per_pair or [scenario_name], "bars": bars, "plot_path": plot_path}


def plot_power_import_main_over_network_sum_from_rows_multi_bars_from_csv_per_compare(
    scenario_names_per_compare=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    show_percent_box=True,
    compare_item1=None,
    compare_item2=None,
    compare_short1=None,
    compare_short2=None,
    short_files=None,
    compare_shorts=None,
    compare_items=None,
    bar_count=None,
    variants=("network", "single"),
    label_left=None,
    label_right=None,
    fontsize=None,
    ):
    """
    Für jede Zeile in scenario_names_per_compare werden alle Szenarien aufsummiert.
    Darstellung: gestapelte Balken pro Variante (unten = from_network_total hellrot,
    oben = from_el_main_grid_total dunklerot). Prozentzahl = Anteil von
    from_el_main_grid_total am Gesamt (main+network).
    """
    import os
    import csv
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

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

    if scenario_names_per_compare is None:
        raise ValueError("scenario_names_per_compare muss gesetzt sein.")
    if len(scenario_names_per_compare) != len(short_files):
        raise ValueError("scenario_names_per_compare muss dieselbe Länge wie short_files haben.")

    for row in scenario_names_per_compare:
        if not isinstance(row, (list, tuple)) or len(row) < 1:
            raise ValueError("Jede Zeile in scenario_names_per_compare muss 1..n Szenarien enthalten.")

    def _read_yearly_import_weighted(csv_path):
        yearly = {}
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for r in reader:
                if r.get("category") != "yearly_totals":
                    continue
                metric = r.get("metric")
                if metric not in ("from_el_main_grid_total", "from_network_total"):
                    continue
                try:
                    year = int(float(r.get("year", 0)))
                    v = float(r.get("value"))
                except (TypeError, ValueError):
                    continue
                yearly.setdefault(year, {})[metric] = yearly.get(year, {}).get(metric, 0.0) + v

        main_total = 0.0
        net_total = 0.0
        for year in sorted(yearly.keys()):
            weight = 5 if year <= 19 else 1
            main_total += yearly[year].get("from_el_main_grid_total", 0.0) * weight
            net_total += yearly[year].get("from_network_total", 0.0) * weight
        return main_total, net_total

    bars = []
    for g_idx, (short_file, comp_short, scen_row) in enumerate(zip(short_files, compare_shorts, scenario_names_per_compare)):
        for variant in variants:
            main_total = 0.0
            net_total = 0.0
            paths = []
            for scen in scen_row:
                if variant == "network":
                    p = os.path.join(base_dir, f"{scen}_{short_file}_network_results.csv")
                elif variant == "single":
                    p = os.path.join(base_dir, f"{scen}_{short_file}_results.csv")
                else:
                    raise ValueError(f"Unbekannte variant: {variant}")
                if not os.path.isfile(p):
                    raise FileNotFoundError(f"Missing result file: {p}")
                m, n = _read_yearly_import_weighted(p)
                main_total += m
                net_total += n
                paths.append(p)

            bars.append({
                "group_idx": g_idx,
                "compare_short": comp_short,
                "variant": variant,
                "value_main": main_total / 1000.0,
                "value_net": net_total / 1000.0,
                "value_total": (main_total + net_total) / 1000.0,
                "paths": paths,
            })

    if bar_count is not None:
        if bar_count <= 0:
            raise ValueError("bar_count muss > 0 sein.")
        if bar_count > len(bars):
            raise ValueError(f"bar_count={bar_count} > verfügbare Balken={len(bars)}")
        bars = bars[:bar_count]

    if not bars:
        raise ValueError("Keine Daten für Balken vorhanden.")

    # x-Positionen: Paarweise (single links, network rechts) je Gruppe
    x = np.array([(i // 2) * 3.0 + (i % 2) * 0.95 for i in range(len(bars))], dtype=float)
    y_main = np.array([b["value_main"] for b in bars], dtype=float)
    y_net = np.array([b["value_net"] for b in bars], dtype=float)

    fig_w_mm = 245
    fig_h_mm = 150
    fig, ax = plt.subplots(figsize=(fig_w_mm / 25.4, fig_h_mm / 25.4))
    width = 0.35

    color_bottom = "#E43D30"  # hellrot -> from_network_total (unten)
    color_top = "#8C1D17"     # dunklerot -> from_el_main_grid_total (oben)

    for i in range(len(bars)):
        # bottom = network, top = main
        ax.bar(x[i], y_net[i], width=width, color=color_bottom, label="_nolegend_")
        ax.bar(x[i], y_main[i], width=width, bottom=y_net[i], color=color_top, label="_nolegend_")

    # Prozentzahlen: Anteil von main an (main+net)
    if show_percent_box:
        totals = y_main + y_net
        ymax = max(float(np.max(totals)) if len(totals) else 0.0, 1.0)
        ax.set_ylim(0, ymax * 1.30)
        y_offset = ymax * 0.04
        for i in range(len(bars)):
            main = y_main[i]
            net = y_net[i]
            total = main + net
            if total == 0:
                txt = "n/a"
            else:
                pct = (main / total) * 100.0
                txt = f"{pct:.0f}%".replace(".", ",")
            ax.text(
                x[i],
                total + y_offset,
                txt,
                ha="center",
                va="bottom",
                color="white",
                fontsize=fontsize,
                bbox=dict(boxstyle="round,pad=0.2", facecolor=color_top, edgecolor=color_top),
                zorder=6,
            )

    # xticks: one label per group (compare_short)
    pair_centers = []
    pair_labels = []
    for i in range(0, len(bars), 2):
        if i + 1 < len(bars):
            center = 0.5 * (x[i] + x[i + 1])
        else:
            center = x[i]
        pair_centers.append(center)
        pair_labels.append(str(bars[i]["compare_short"]))

    ax.set_xticks(pair_centers)
    ax.set_xticklabels(pair_labels, fontsize=fontsize)
    if len(x):
        ax.set_xlim(x.min() - width, x.max() + width)
    ax.set_ylabel("Energie in MWh", fontsize=fontsize)
    ax.grid(axis="y", alpha=0.35)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda val, pos: f"{int(round(val)):,}".replace(",", ".")))

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=color_bottom),
        plt.Rectangle((0, 0), 1, 1, fc=color_top),
    ]
    labels = [
        "Strombezug aus dem Verbundnetz (unten)",
        "Strombezug aus dem Hauptnetz (oben)",
    ]
    ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False, fontsize=fontsize)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    plot_name = f"{titel}.png" if titel else "power_import_main_over_network_sum_multibars.png"
    plot_path = os.path.join(plots_dir, plot_name)
    fig.savefig(plot_path, dpi=300)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return {"bars": bars, "plot_path": plot_path}



def main():
    # Allgemeine Einstellungen für die Plots
    compare_item1 = "verbundweise"
    compare_item2 = "quartiersweise"
    base_dir=r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results"
    result_dir=r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results"

    ###############################################################################
    # For plot_co2 and plot_tac_per_demand_sum
    show = False
    short_files = ["Basis", "Bat", "PV"]
    scenario_names_by_item = [
        ["residential2", "mixed1", "ghd6"],
        ["residential2", "mixed1", "ghd6"],
        ["residential2", "mixed1", "ghd6"],
        # ["residential2", "residential0", "residential3"]
    ]
    compare_shorts = ["Basis", "Batterie", "Solarausbau"]
    bar_count = 6
    fontsize = 15

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
        show=show,
        titel="tac_sum_years_districts",
        short_files=short_files,
        compare_shorts=compare_shorts,
        bar_count=bar_count,
        variants=("network", "single"),
        show_percent_box=True,
        compare_item1 = compare_item1,
        compare_item2 = compare_item2,
        fontsize=fontsize,
    )



    #################################################################################
    # For plot_power_import only main_grid_total
    # !! Szenariowechsel
    show = False

    # Für jedes Quartier:
    # scenario_names_per_compare = [
    # ("residential2", "ghd6", "mixed1"),]

    # short_files = ["Basis"] 
    # compare_shorts = ["Basis"]
    # compare_items = ["Basis-Szenario"]

    scenario_names_per_compare = [
    ("residential2", "ghd6", "mixed1"),]

    short_files = ["Bat"] 
    compare_shorts = ["Batterie"]
    compare_items = ["Batterie-Szenario"]

    bar_count = 6
    fontsize = 13
    
    
    plot_power_import_main_grid_all_years_multi_bars_from_csv_per_pair(
    scenario_names_per_compare=scenario_names_per_compare,   # neu: je compare_short 1 oder 2 Szenarien
    base_dir=base_dir, result_dir=result_dir, show=show,
    show_percent_box=True,
    compare_item1=compare_item1, compare_item2=compare_item2,
    short_files=short_files,          # <- Dateikürzel zum Laden
    compare_shorts=compare_shorts,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=compare_items,
    bar_count=bar_count,
    variants=("network", "single"),
    fontsize=fontsize,
    )

    # Für den Verbund

    scenario_names_by_item = [
        ["residential2", "mixed1", "ghd6"],
        ["residential2", "mixed1", "ghd6"],
        ["residential2", "mixed1", "ghd6"],
    ]

    short_files = ["Basis", "Bat", "PV"] 
    compare_shorts = ["Basis", "Batterie", "Solarausbau"]
    compare_items = ["Basis-Szenario", "Batterie-Szenario", "Solarausbau-Szenario"]
    

    plot_import_main_grid_sum_all_years_multi_bars_from_csv(
        scenario_names_by_item=scenario_names_by_item,
        base_dir=base_dir,
        result_dir=result_dir,
        show=show,
        titel="import_sum_years_districts",
        short_files=short_files,
        compare_shorts=compare_shorts,
        bar_count=bar_count,
        variants=("network", "single"),
        show_percent_box=False,
        compare_item1 = compare_item1,
        compare_item2 = compare_item2,
        fontsize=fontsize,
    )


    #################################################################################
    # For plot_power_import from_main_grid_total and from_network_total
    # !! Szenariowechsel
    show = False

    bar_count = 6

    # Für jedes Quartier:
    # scenario_names_per_compare = [
    # ("residential2", "ghd6", "mixed1"),]

    # short_files = ["Basis"] 
    # compare_shorts = ["Basis"]
    # compare_items = ["Basis-Szenario"]

    scenario_names_per_compare = [
    ("residential2", "ghd6", "mixed1"),]

    short_files = ["Bat"] 
    compare_shorts = ["Batterie"]
    compare_items = ["Batterie-Szenario"]
    bar_count = 6
    fontsize = 13

    plot_power_import_all_years_multi_bars_from_csv_per_pair(
    scenario_names_per_compare=scenario_names_per_compare,   # neu: je compare_short 1 oder 2 Szenarien
    base_dir=base_dir, result_dir=result_dir, show=show,
    show_percent_box=False,
    compare_item1=compare_item1, compare_item2=compare_item2,
    short_files=short_files,          # <- Dateikürzel zum Laden
    compare_shorts=compare_shorts,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=compare_items,
    bar_count=bar_count,
    variants=("network", "single"),
    fontsize=fontsize,
    )

    # Für den Verbund

    scenario_names_per_compare = [
    ("residential2", "ghd6", "mixed1"),
    ("residential2", "ghd6","mixed1"),
    ("residential2", "ghd6","mixed1"),
    ]

    short_files = ["Basis", "Bat", "PV"] 
    compare_shorts = ["Basis", "Batterie", "Solarausbau"]
    compare_items = ["Basis-Szenario", "Batterie-Szenario", "Solarausbau-Szenario"]


    # plot_power_import_main_over_network_sum_from_rows_multi_bars_from_csv_per_compare(
    # scenario_names_per_compare=scenario_names_per_compare,   # neu: je compare_short 1 oder 2 Szenarien
    # base_dir=base_dir, result_dir=result_dir, show=show,
    # show_percent_box=True,
    # compare_item1=compare_item1, compare_item2=compare_item2,
    # short_files=short_files,          # <- Dateikürzel zum Laden
    # compare_shorts=compare_shorts,       # <- Labels auf x-Achse (pro Szenario)
    # compare_items=compare_items,
    # bar_count=bar_count,
    # variants=("network", "single"),
    # fontsize=fontsize,
    # )

    plot_power_import_sum_from_rows_multi_bars_from_csv_per_compare(
    scenario_names_per_compare=scenario_names_per_compare,   # neu: je compare_short 1 oder 2 Szenarien
    base_dir=base_dir, result_dir=result_dir, show=show,
    show_percent_box=False,
    compare_item1=compare_item1, compare_item2=compare_item2,
    short_files=short_files,          # <- Dateikürzel zum Laden
    compare_shorts=compare_shorts,       # <- Labels auf x-Achse (pro Szenario)
    compare_items=compare_items,
    bar_count=bar_count,
    variants=("network", "single"),
    fontsize=fontsize,
    )

    #################################################################################
    # Für plot_device_capacities_all_scenarios
    # !! Szenariowechsel
    show = True
    short_files = ["Basis", "Bat", "PV", "PV"]
    compare_shorts = ["Basis", "Batterie", "Solarausbau","Solarausbau"]
    #compare_shorts = ["Basis-Szenario", "Batterie-Szenario", "Solarausbau-Szenario","Solarausbau-Szenario", "Wohn-Szenario"]
    scenario_names_per_pair = ["mixed1", "mixed1", "mixed1","ghd6"]
    label_left="Mischquartier"
    label_middle="Gewerbequartier"
    label_right="Wohnquartier 2"
    fontsize1 = 14
    fontsize2 = 14
    compare_item1 = "verbundweise"
    compare_item2 = "quartiersweise"


    plot_device_capacities_multi_bars_from_csv_with_TES_per_pair(
    short_files=short_files,
    compare_shorts=compare_shorts,
    scenario_names_per_pair=scenario_names_per_pair,
    base_dir=base_dir,
    result_dir=result_dir,
    show=show,
    titel="device_capacities_all_scenarios",
    show_percent_box=True,
    label_left=label_left,
    label_middle=label_middle,
    label_right=label_right,
    exclude_devices=["EB", "BBOI", "HP", "TES","BAT"],
    fontsize1=fontsize1,
    fontsize2=fontsize2,
    compare_item1=compare_item1,
    compare_item2=compare_item2,
    )

    #################################################################################
   
    # Vielleicht verwendet

        # plot_co2_sum_all_years_multi_bars_from_csv(
    #     scenario_names_by_item=scenario_names_by_item,
    #     base_dir=base_dir, result_dir=result_dir,
    #     show=show, titel="co2_sum_years_districts",
    #     short_files=short_files,
    #     compare_shorts=compare_shorts,
    #     bar_count=bar_count,
    #     variants=("network", "single"), show_percent_box=True,
    #     compare_item1 = compare_item1, compare_item2 = compare_item2, fontsize=fontsize
    # )

    # plot_tac_per_demand_sum_all_years_multi_bars_from_csv(
    #     scenario_names_by_item=scenario_names_by_item,
    #     base_dir=base_dir, result_dir=result_dir,
    #     show=show, 
    #     titel="specific_tac_sum_years_districts",
    #     short_files=short_files, compare_shorts=compare_shorts, bar_count=bar_count,
    #     variants=("network", "single"), show_percent_box=True,
    #     compare_item1 = compare_item1, compare_item2 = compare_item2, power_demand=power_demand,
    #     fontsize=fontsize,
    # )
    # plot_power_export_all_years_multi_bars_from_csv_per_pair(
    # scenario_names_per_pair=scenario_names_per_pair,   # neu: Liste mit scenario_name für jedes Paar (len == len(short_files))
    # base_dir=base_dir,
    # result_dir=result_dir,
    # show=True,
    # show_percent_box=True,
    # compare_item1=compare_item1,
    # compare_item2=compare_item2,
    # short_files=short_files,          # <- Dateikürzel zum Laden
    # compare_shorts=compare_shorts,       # <- Labels auf x-Achse (pro Szenario)
    # compare_items=compare_items,
    # bar_count=bar_count,
    # variants=("network", "single"),
    # label_left="Mischquartier",
    # label_middle="Gewerbequartier",
    # label_right="Wohnquartier 2",
    # )

    #plot_tes_capacity_sum_from_three_scenarios_multi_compare(
    # scenario_names_per_compare=scenario_names_per_compare,   # Liste von 3er-Listen, je compare_short
    # scenario_names_by_item=scenario_names_by_item,       # Alias
    # base_dir=base_dir,
    # result_dir=result_dir,
    # show=True,
    # titel=None,
    # compare_item1=compare_item1,
    # compare_item2=compare_item2,
    # short_files=short_files,
    # compare_shorts=compare_shorts,
    # compare_items=compare_items,
    # bar_count=bar_count,
    # variants=("network", "single"),
    # show_percent_box=True,
    # fontsize1=8,
    # fontsize2=8,
    # )



if __name__ == "__main__":
    main()