import os
import csv
import numpy as np
import matplotlib.pyplot as plt

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


def _load_single_results_file_to_dict(csv_file_path):
    """
    Lädt eine einzelne Results-CSV in ein strukturiertes Dict:
    - scalar
    - by_device
    - by_year
    - by_year_device
    - unit
    """
    results = {}

    def empty_bucket():
        return {
            "scalar": {},
            "by_device": {},
            "by_year": {},
            "by_year_device": {},
            "unit": {},
        }

    with open(csv_file_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            scenario = row.get("scenario", "")
            category = row.get("category", "")
            metric = row.get("metric", "")
            device = row.get("device") or None
            year_raw = row.get("year")
            year = int(float(year_raw)) if year_raw not in (None, "") else None
            value = _parse_value(row.get("value"))
            unit = row.get("unit") or ""

            scen = results.setdefault(scenario, {})
            cat = scen.setdefault(category, empty_bucket())

            if metric and metric not in cat["unit"]:
                cat["unit"][metric] = unit

            if year is None and device is None:
                cat["scalar"][metric] = value
            elif year is None and device is not None:
                cat["by_device"].setdefault(metric, {})[device] = value
            elif year is not None and device is None:
                cat["by_year"].setdefault(metric, {})[year] = value
            else:
                cat["by_year_device"].setdefault(metric, {}).setdefault(year, {})[device] = value

    return results


def load_four_compare_results_to_dict(
    scenario_name,
    compare_short1,
    compare_short2,
    base_dir=None,
):
    """
    Lädt 4 Dateien:
    - f"{scenario_name}_{compare_short1}_network_results.csv"
    - f"{scenario_name}_{compare_short1}_results.csv"
    - f"{scenario_name}_{compare_short2}_network_results.csv"
    - f"{scenario_name}_{compare_short2}_results.csv"

    Rückgabe:
    {
      "scenario": <scenario_name>,
      "compare_short1": {
        "network": <parsed dict>,
        "single": <parsed dict>,
        "paths": {...}
      },
      "compare_short2": {
        "network": <parsed dict>,
        "single": <parsed dict>,
        "paths": {...}
      }
    }
    """
    if base_dir is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        base_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"Result directory not found: {base_dir}")

    p1_net = os.path.join(base_dir, f"{scenario_name}_{compare_short1}_network_results.csv")
    p1_single = os.path.join(base_dir, f"{scenario_name}_{compare_short1}_results.csv")
    p2_net = os.path.join(base_dir, f"{scenario_name}_{compare_short2}_network_results.csv")
    p2_single = os.path.join(base_dir, f"{scenario_name}_{compare_short2}_results.csv")

    missing = [p for p in [p1_net, p1_single, p2_net, p2_single] if not os.path.isfile(p)]
    if missing:
        raise FileNotFoundError("Missing result files:\n" + "\n".join(missing))

    data_1_network = _load_single_results_file_to_dict(p1_net)
    data_1_single = _load_single_results_file_to_dict(p1_single)
    data_2_network = _load_single_results_file_to_dict(p2_net)
    data_2_single = _load_single_results_file_to_dict(p2_single)

    return {
        "scenario": scenario_name,
        "compare_short1": {
            "network": data_1_network,
            "single": data_1_single,
            "paths": {"network": p1_net, "single": p1_single},
        },
        "compare_short2": {
            "network": data_2_network,
            "single": data_2_single,
            "paths": {"network": p2_net, "single": p2_single},
        },
    }
def plot_device_capacities_four_bars_from_csv(
    scenario_name,
    compare_short1,
    compare_short2,
    compare_item1=None,
    compare_item2=None,
    base_dir=None,
    result_dir=None,
    show=True,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    show_percent_box=False,
):
    """
    Plot device capacities with 4 bars per device:
    - compare_short1 network
    - compare_short1 single
    - compare_short2 network
    - compare_short2 single
    """
    data = load_four_compare_results_to_dict(
        scenario_name=scenario_name,
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        base_dir=base_dir,
    )

    def _to_set(x):
        if x is None:
            return None
        if isinstance(x, str):
            return {x}
        return set(x)

    def _extract_caps(parsed_dict):
        # Struktur aus _load_single_results_file_to_dict:
        # {scenario: {category: {"by_device": {"capacity": {device: value}}}}}
        if not parsed_dict:
            return {}
        scen_key = scenario_name if scenario_name in parsed_dict else next(iter(parsed_dict.keys()))
        scen = parsed_dict.get(scen_key, {})
        dev_cat = scen.get("device", {})
        return dev_cat.get("by_device", {}).get("capacity", {}) or {}

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    d1_net = _extract_caps(data["compare_short1"]["network"])
    d1_single = _extract_caps(data["compare_short1"]["single"])
    d2_net = _extract_caps(data["compare_short2"]["network"])
    d2_single = _extract_caps(data["compare_short2"]["single"])

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
    }

    all_devices = set(d1_net) | set(d1_single) | set(d2_net) | set(d2_single)

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
    width = 0.18

    y1n = np.array([float(d1_net.get(d, 0.0) or 0.0) for d in devices], dtype=float)
    y1s = np.array([float(d1_single.get(d, 0.0) or 0.0) for d in devices], dtype=float)
    y2n = np.array([float(d2_net.get(d, 0.0) or 0.0) for d in devices], dtype=float)
    y2s = np.array([float(d2_single.get(d, 0.0) or 0.0) for d in devices], dtype=float)

    xtick_labels = [label_map.get(d, d) for d in devices]

    plt.figure(figsize=(10, 4.8))
    b1 = plt.bar(x - 1.5 * width, y1n, width=width, color="#D40000", label=f"{compare_item1 or compare_short1} (verbundweise)")
    b2 = plt.bar(x - 0.5 * width, y1s, width=width, color="#55585C", label=f"{compare_item1 or compare_short1} (quartiersweise)")
    b3 = plt.bar(x + 0.5 * width, y2n, width=width, color="#F08A84", label=f"{compare_item2 or compare_short2} (verbundweise)") 
    b4 = plt.bar(x + 1.5 * width, y2s, width=width, color="#B9BABC", label=f"{compare_item2 or compare_short2} (quartiersweise)")

    ymax = max(np.max(y1n), np.max(y1s), np.max(y2n), np.max(y2s), 1.0)

    if show_percent_box:
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.06

        # Prozentbox über den jeweiligen network-Balken relativ zu single desselben compare-Setups
        for i in range(len(devices)):
            # compare 1
            if y1s[i] == 0:
                txt1 = "n/a" if y1n[i] == 0 else "+∞"
            else:
                txt1 = _fmt_pct((y1n[i] - y1s[i]) / y1s[i] * 100.0)
            plt.text(
                x[i] - 1.5 * width,
                y1n[i] + y_offset,
                txt1,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#D40000", edgecolor="#D40000", linewidth=1.0),
                zorder=5,
            )

            # compare 2
            if y2s[i] == 0:
                txt2 = "n/a" if y2n[i] == 0 else "+∞"
            else:
                txt2 = _fmt_pct((y2n[i] - y2s[i]) / y2s[i] * 100.0)
            plt.text(
                x[i] + 0.5 * width,
                y2n[i] + y_offset,
                txt2,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#F08A84", edgecolor="#F08A84", linewidth=1.0),
                zorder=5,
            )

    plt.xticks(x, xtick_labels, fontsize=11)
    plt.ylabel("Anlagenleistung in kW")
    #plt.title(titel)
    plt.grid(axis="y", alpha=0.35)
    plt.legend(ncol=2)
    plt.tight_layout()

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    plot_name = f"{titel}.pdf" if titel else f"device_capacities_4bars_{scenario_name}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario": scenario_name,
        "compare_short1": {"network": dict(d1_net), "single": dict(d1_single)},
        "compare_short2": {"network": dict(d2_net), "single": dict(d2_single)},
        "plot_path": plot_path,
        "paths": {
            "compare_short1": data["compare_short1"]["paths"],
            "compare_short2": data["compare_short2"]["paths"],
        },
    }
def plot_storage_capacities_four_bars_from_csv(
    scenario_name,
    compare_short1,
    compare_short2,
    compare_item1=None,
    compare_item2=None,
    base_dir=None,
    result_dir=None,
    show=True,
    include_devices=None,
    exclude_devices=None,
    titel=None,
    show_percent_box=False,
):
    """
    Plot device capacities with 4 bars per device:
    - compare_short1 network
    - compare_short1 single
    - compare_short2 network
    - compare_short2 single
    """
    data = load_four_compare_results_to_dict(
        scenario_name=scenario_name,
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        base_dir=base_dir,
    )

    def _to_set(x):
        if x is None:
            return None
        if isinstance(x, str):
            return {x}
        return set(x)

    def _extract_caps(parsed_dict):
        # Struktur aus _load_single_results_file_to_dict:
        # {scenario: {category: {"by_device": {"capacity": {device: value}}}}}
        if not parsed_dict:
            return {}
        scen_key = scenario_name if scenario_name in parsed_dict else next(iter(parsed_dict.keys()))
        scen = parsed_dict.get(scen_key, {})
        dev_cat = scen.get("device", {})
        return dev_cat.get("by_device", {}).get("capacity", {}) or {}

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    d1_net = _extract_caps(data["compare_short1"]["network"])
    d1_single = _extract_caps(data["compare_short1"]["single"])
    d2_net = _extract_caps(data["compare_short2"]["network"])
    d2_single = _extract_caps(data["compare_short2"]["single"])

    include_set = _to_set(include_devices)
    exclude_set = _to_set(exclude_devices) or set()

    preferred_order = [
        "TES", "BAT"
    ]

    label_map = {
        "TES": "therm. Speicher",
        "BAT": "Batterie",
    }

    all_devices = set(d1_net) | set(d1_single) | set(d2_net) | set(d2_single)

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
    width = 0.18

    y1n = np.array([float(d1_net.get(d, 0.0) or 0.0) for d in devices], dtype=float)
    y1s = np.array([float(d1_single.get(d, 0.0) or 0.0) for d in devices], dtype=float)
    y2n = np.array([float(d2_net.get(d, 0.0) or 0.0) for d in devices], dtype=float)
    y2s = np.array([float(d2_single.get(d, 0.0) or 0.0) for d in devices], dtype=float)

    xtick_labels = [label_map.get(d, d) for d in devices]

    plt.figure(figsize=(10, 4.8))
    b1 = plt.bar(x - 1.5 * width, y1n, width=width, color="#D40000", label=f"{compare_item1 or compare_short1} (verbundweise)")
    b2 = plt.bar(x - 0.5 * width, y1s, width=width, color="#55585C", label=f"{compare_item1 or compare_short1} (quartiersweise)")
    b3 = plt.bar(x + 0.5 * width, y2n, width=width, color="#F08A84", label=f"{compare_item2 or compare_short2} (verbundweise)") 
    b4 = plt.bar(x + 1.5 * width, y2s, width=width, color="#B9BABC", label=f"{compare_item2 or compare_short2} (quartiersweise)")

    ymax = max(np.max(y1n), np.max(y1s), np.max(y2n), np.max(y2s), 1.0)

    if show_percent_box:
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.06

        # Prozentbox über den jeweiligen network-Balken relativ zu single desselben compare-Setups
        for i in range(len(devices)):
            # compare 1
            if y1s[i] == 0:
                txt1 = "n/a" if y1n[i] == 0 else f"+{y1n[i]:.0f} kWh"
            else:
                txt1 = _fmt_pct((y1n[i] - y1s[i]) / y1s[i] * 100.0)
            plt.text(
                x[i] - 1.5 * width,
                y1n[i] + y_offset,
                txt1,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#D40000", edgecolor="#D40000", linewidth=1.0),
                zorder=5,
            )

            # compare 2
            if y2s[i] == 0:
                txt2 = "n/a" if y2n[i] == 0 else "+∞"
            else:
                txt2 = _fmt_pct((y2n[i] - y2s[i]) / y2s[i] * 100.0)
            plt.text(
                x[i] + 0.5 * width,
                y2n[i] + y_offset,
                txt2,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#F08A84", edgecolor="#F08A84", linewidth=1.0),
                zorder=5,
            )

    plt.xticks(x, xtick_labels, fontsize=11)
    plt.ylabel("Speicherkapazität in kWh")
    #plt.title(titel)
    plt.grid(axis="y", alpha=0.35)
    plt.legend(ncol=2)
    plt.tight_layout()

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    plot_name = f"{titel}.pdf" if titel else f"storage_capacities_4bars_{scenario_name}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario": scenario_name,
        "compare_short1": {"network": dict(d1_net), "single": dict(d1_single)},
        "compare_short2": {"network": dict(d2_net), "single": dict(d2_single)},
        "plot_path": plot_path,
        "paths": {
            "compare_short1": data["compare_short1"]["paths"],
            "compare_short2": data["compare_short2"]["paths"],
        },
    }


def plot_co2_by_year_four_bars_from_csv(
    scenario_name,
    compare_short1,
    compare_short2,
    compare_item1=None,
    compare_item2=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
):
    """
    Plot yearly CO2 emissions with 4 bars per year:
    - compare_short1 network
    - compare_short1 single
    - compare_short2 network
    - compare_short2 single

    Verwendet:
    - category == 'optimization'
    - metric   == 'co2_sum_distr_year'
    """
    data = load_four_compare_results_to_dict(
        scenario_name=scenario_name,
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        base_dir=base_dir,
    )

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    def _extract_co2_year(parsed_dict):
        # Struktur:
        # {scenario: {category: {"by_year": {"co2_sum_distr_year": {year: value}}}}}
        if not parsed_dict:
            return {}
        scen_key = scenario_name if scenario_name in parsed_dict else next(iter(parsed_dict.keys()))
        scen = parsed_dict.get(scen_key, {})
        opt = scen.get("optimization", {})
        by_year = opt.get("by_year", {}).get("co2_sum_distr_year", {}) or {}

        out = {}
        for y, v in by_year.items():
            try:
                out[int(y)] = float(v)
            except Exception:
                continue
        return out

    y1_net = _extract_co2_year(data["compare_short1"]["network"])
    y1_single = _extract_co2_year(data["compare_short1"]["single"])
    y2_net = _extract_co2_year(data["compare_short2"]["network"])
    y2_single = _extract_co2_year(data["compare_short2"]["single"])

    years = sorted(set(y1_net) | set(y1_single) | set(y2_net) | set(y2_single))
    if not years:
        raise ValueError("No optimization/co2_sum_distr_year data found in the four input files.")

    x = np.arange(len(years))
    width = 0.18

    vals_1n = np.array([y1_net.get(y, 0.0) for y in years], dtype=float)
    vals_1s = np.array([y1_single.get(y, 0.0) for y in years], dtype=float)
    vals_2n = np.array([y2_net.get(y, 0.0) for y in years], dtype=float)
    vals_2s = np.array([y2_single.get(y, 0.0) for y in years], dtype=float)

    labels = [str(base_calendar_year + y) for y in years]

    plt.figure(figsize=(9, 4.8))
    plt.bar(x - 1.5 * width, vals_1n, width=width, color="#D40000", label=f"{compare_item1 or compare_short1} (verbundweise)")
    plt.bar(x - 0.5 * width, vals_1s, width=width, color="#55585C", label=f"{compare_item1 or compare_short1} (quartiersweise)")
    plt.bar(x + 0.5 * width, vals_2n, width=width, color="#F08A84", label=f"{compare_item2 or compare_short2} (verbundweise)")
    plt.bar(x + 1.5 * width, vals_2s, width=width, color="#B9BABC", label=f"{compare_item2 or compare_short2} (quartiersweise)")

    ymax = max(np.max(vals_1n), np.max(vals_1s), np.max(vals_2n), np.max(vals_2s), 1.0)

    if show_percent_box:
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.06

        for i in range(len(years)):
            # compare 1: network relativ zu single
            if vals_1s[i] == 0:
                txt1 = "n/a" if vals_1n[i] == 0 else "+∞"
            else:
                txt1 = _fmt_pct((vals_1n[i] - vals_1s[i]) / vals_1s[i] * 100.0)

            plt.text(
                x[i] - 1.5 * width,
                vals_1n[i] + y_offset,
                txt1,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#D40000", edgecolor="#D40000", linewidth=1.0),
                zorder=5,
            )

            # compare 2: network relativ zu single
            if vals_2s[i] == 0:
                txt2 = "n/a" if vals_2n[i] == 0 else "+∞"
            else:
                txt2 = _fmt_pct((vals_2n[i] - vals_2s[i]) / vals_2s[i] * 100.0)

            plt.text(
                x[i] + 0.5 * width,
                vals_2n[i] + y_offset,
                txt2,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#F08A84", edgecolor="#F08A84", linewidth=1.0),
                zorder=5,
            )

    plt.xticks(x, labels)
    plt.ylabel("CO₂-Emissionen in t/a")
    plt.grid(axis="y", alpha=0.35)
    plt.legend(ncol=2)
    plt.tight_layout()

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    plot_name = f"{titel}.pdf" if titel else f"co2_by_year_4bars_{scenario_name}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario": scenario_name,
        "years": years,
        "compare_short1": {"network": y1_net, "single": y1_single},
        "compare_short2": {"network": y2_net, "single": y2_single},
        "plot_path": plot_path,
        "paths": {
            "compare_short1": data["compare_short1"]["paths"],
            "compare_short2": data["compare_short2"]["paths"],
        },
    }



def plot_lcoe_by_year_four_bars_from_csv(
    scenario_name,
    compare_short1,
    compare_short2,
    compare_item1=None,
    compare_item2=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
):
    """
    Plot yearly LCOE with 4 bars per year:
    - compare_short1 network
    - compare_short1 single
    - compare_short2 network
    - compare_short2 single

    Verwendet:
    - category == 'optimization'
    - metric   == 'LCOE_year'
    """
    data = load_four_compare_results_to_dict(
        scenario_name=scenario_name,
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        base_dir=base_dir,
    )

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    def _extract_lcoe_year(parsed_dict):
        if not parsed_dict:
            return {}
        scen_key = scenario_name if scenario_name in parsed_dict else next(iter(parsed_dict.keys()))
        scen = parsed_dict.get(scen_key, {})
        opt = scen.get("optimization", {})
        by_year = opt.get("by_year", {}).get("LCOE_year", {}) or {}

        out = {}
        for y, v in by_year.items():
            try:
                out[int(y)] = float(v)
            except Exception:
                continue
        return out

    y1_net = _extract_lcoe_year(data["compare_short1"]["network"])
    y1_single = _extract_lcoe_year(data["compare_short1"]["single"])
    y2_net = _extract_lcoe_year(data["compare_short2"]["network"])
    y2_single = _extract_lcoe_year(data["compare_short2"]["single"])

    years = sorted(set(y1_net) | set(y1_single) | set(y2_net) | set(y2_single))
    if not years:
        raise ValueError("No optimization/LCOE_year data found in the four input files.")

    x = np.arange(len(years))
    width = 0.18

    vals_1n = np.array([y1_net.get(y, 0.0) for y in years], dtype=float)
    vals_1s = np.array([y1_single.get(y, 0.0) for y in years], dtype=float)
    vals_2n = np.array([y2_net.get(y, 0.0) for y in years], dtype=float)
    vals_2s = np.array([y2_single.get(y, 0.0) for y in years], dtype=float)

    labels = [str(base_calendar_year + y) for y in years]

    plt.figure(figsize=(9, 4.8))
    plt.bar(x - 1.5 * width, vals_1n, width=width, color="#D40000", label=f"{compare_item1 or compare_short1} (verbundweise)")
    plt.bar(x - 0.5 * width, vals_1s, width=width, color="#55585C", label=f"{compare_item1 or compare_short1} (quartiersweise)")
    plt.bar(x + 0.5 * width, vals_2n, width=width, color="#F08A84", label=f"{compare_item2 or compare_short2} (verbundweise)")
    plt.bar(x + 1.5 * width, vals_2s, width=width, color="#B9BABC", label=f"{compare_item2 or compare_short2} (quartiersweise)")

    ymax = max(np.max(vals_1n), np.max(vals_1s), np.max(vals_2n), np.max(vals_2s), 1.0)

    if show_percent_box:
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.06

        for i in range(len(years)):
            # compare 1: network relativ zu single
            if vals_1s[i] == 0:
                txt1 = "n/a" if vals_1n[i] == 0 else "+∞"
            else:
                txt1 = _fmt_pct((vals_1n[i] - vals_1s[i]) / vals_1s[i] * 100.0)

            plt.text(
                x[i] - 1.5 * width,
                vals_1n[i] + y_offset,
                txt1,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#D40000", edgecolor="#D40000", linewidth=1.0),
                zorder=5,
            )

            # compare 2: network relativ zu single
            if vals_2s[i] == 0:
                txt2 = "n/a" if vals_2n[i] == 0 else "+∞"
            else:
                txt2 = _fmt_pct((vals_2n[i] - vals_2s[i]) / vals_2s[i] * 100.0)

            plt.text(
                x[i] + 0.5 * width,
                vals_2n[i] + y_offset,
                txt2,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#F08A84", edgecolor="#F08A84", linewidth=1.0),
                zorder=5,
            )

    plt.xticks(x, labels)
    plt.ylabel("Energiegestehungskosten in €/MWh")
    plt.grid(axis="y", alpha=0.35)
    plt.legend(ncol=2)
    plt.tight_layout()

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    plot_name = f"{titel}.pdf" if titel else f"lcoe_by_year_4bars_{scenario_name}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario": scenario_name,
        "years": years,
        "compare_short1": {"network": y1_net, "single": y1_single},
        "compare_short2": {"network": y2_net, "single": y2_single},
        "plot_path": plot_path,
        "paths": {
            "compare_short1": data["compare_short1"]["paths"],
            "compare_short2": data["compare_short2"]["paths"],
        },
    }



def plot_tac_sum_from_three_scenarios_four_bars(
    scenario_names,
    compare_short1,
    compare_short2,
    compare_item1=None,
    compare_item2=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    show_percent_box=False,
):
    """
    Plot TAC-Summe für 3 Szenarien mit je 4 Balken:
    - compare_short1 network
    - compare_short1 single
    - compare_short2 network
    - compare_short2 single

    Erwartet:
    - scenario_names: Liste/Tuple mit genau 3 Szenario-Namen
    - Dateien je Szenario:
      - <scenario>_{compare_short1}_network_results.csv
      - <scenario>_{compare_short1}_results.csv
      - <scenario>_{compare_short2}_network_results.csv
      - <scenario>_{compare_short2}_results.csv

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
        """Summiert alle tac_distr-Werte aus einer CSV."""
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

    # Pro Szenario: 4 TAC-Werte laden
    tac_values = {
        "compare_short1_net": [],
        "compare_short1_single": [],
        "compare_short2_net": [],
        "compare_short2_single": [],
    }

    for sc in scenario_names:
        p1_net = os.path.join(base_dir, f"{sc}_{compare_short1}_network_results.csv")
        p1_single = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        p2_net = os.path.join(base_dir, f"{sc}_{compare_short2}_network_results.csv")
        p2_single = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        missing = [p for p in [p1_net, p1_single, p2_net, p2_single] if not os.path.isfile(p)]
        if missing:
            raise FileNotFoundError(f"Missing files for scenario '{sc}':\n" + "\n".join(missing))

        tac_values["compare_short1_net"].append(_read_tac(p1_net))
        tac_values["compare_short1_single"].append(_read_tac(p1_single))
        tac_values["compare_short2_net"].append(_read_tac(p2_net))
        tac_values["compare_short2_single"].append(_read_tac(p2_single))

    # x-Achse: 3 Positionen (pro Szenario), jeweils 4 Balken
    x = np.arange(len(scenario_names))
    width = 0.18

    y1n = np.array(tac_values["compare_short1_net"], dtype=float)
    y1s = np.array(tac_values["compare_short1_single"], dtype=float)
    y2n = np.array(tac_values["compare_short2_net"], dtype=float)
    y2s = np.array(tac_values["compare_short2_single"], dtype=float)

    plt.figure(figsize=(9, 5))
    plt.bar(x - 1.5 * width, y1n, width=width, color="#D40000", label=f"{compare_item1 or compare_short1} (verbundweise)")
    plt.bar(x - 0.5 * width, y1s, width=width, color="#55585C", label=f"{compare_item1 or compare_short1} (quartiersweise)")
    plt.bar(x + 0.5 * width, y2n, width=width, color="#F08A84", label=f"{compare_item2 or compare_short2} (verbundweise)")
    plt.bar(x + 1.5 * width, y2s, width=width, color="#B9BABC", label=f"{compare_item2 or compare_short2} (quartiersweise)")

    ymax = max(np.max(y1n), np.max(y1s), np.max(y2n), np.max(y2s), 1.0)

    if show_percent_box:
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.06

        for i in range(len(scenario_names)):
            # compare_short1: network relativ zu single
            if y1s[i] == 0:
                txt1 = "n/a" if y1n[i] == 0 else "+∞"
            else:
                txt1 = _fmt_pct((y1n[i] - y1s[i]) / y1s[i] * 100.0)

            plt.text(
                x[i] - 1.5 * width,
                y1n[i] + y_offset,
                txt1,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#D40000", edgecolor="#D40000", linewidth=1.0),
                zorder=5,
            )

            # compare_short2: network relativ zu single
            if y2s[i] == 0:
                txt2 = "n/a" if y2n[i] == 0 else "+∞"
            else:
                txt2 = _fmt_pct((y2n[i] - y2s[i]) / y2s[i] * 100.0)

            plt.text(
                x[i] + 0.5 * width,
                y2n[i] + y_offset,
                txt2,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#F08A84", edgecolor="#F08A84", linewidth=1.0),
                zorder=5,
            )

    plt.xticks(x, scenario_names)
    plt.ylabel("TAC-Summe in € pro Jahr")
    plt.title(titel or "TAC-Summe der drei Szenarien (4er-Vergleich)")
    plt.grid(axis="y", alpha=0.35)
    plt.legend(ncol=2, loc="upper left")
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.tight_layout()

    plot_name = f"{titel}.pdf" if titel else "tac_sum_three_scenarios_4bars.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario_names": list(scenario_names),
        "compare_short1_network": dict(zip(scenario_names, y1n)),
        "compare_short1_single": dict(zip(scenario_names, y1s)),
        "compare_short2_network": dict(zip(scenario_names, y2n)),
        "compare_short2_single": dict(zip(scenario_names, y2s)),
        "plot_path": plot_path,
    }

def plot_co2_sum_from_three_scenarios_four_bars(
    scenario_names,
    compare_short1,
    compare_short2,
    compare_item1=None,
    compare_item2=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    show_percent_box=False,
):
    """
    Summiert CO2-Emissionen über alle 3 Szenarien und alle Jahre.

    Ergebnis:
    - compare_short1 network
    - compare_short1 single
    - compare_short2 network
    - compare_short2 single

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

    def _read_co2_sum(csv_path):
        co2_sum = 0.0
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                if str(row.get("category", "")).strip() != "optimization":
                    continue
                if str(row.get("metric", "")).strip() != "co2_distr":
                    continue
                v = _parse_value(row.get("value"))
                try:
                    co2_sum += float(v)
                except Exception:
                    continue
        return co2_sum

    def _fmt_pct(p):
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    total_1_net = 0.0
    total_1_single = 0.0
    total_2_net = 0.0
    total_2_single = 0.0

    for sc in scenario_names:
        p1_net = os.path.join(base_dir, f"{sc}_{compare_short1}_network_results.csv")
        p1_single = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        p2_net = os.path.join(base_dir, f"{sc}_{compare_short2}_network_results.csv")
        p2_single = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        missing = [p for p in [p1_net, p1_single, p2_net, p2_single] if not os.path.isfile(p)]
        if missing:
            raise FileNotFoundError(
                f"Missing files for scenario '{sc}':\n" + "\n".join(missing)
            )

        total_1_net += _read_co2_sum(p1_net)
        total_1_single += _read_co2_sum(p1_single)
        total_2_net += _read_co2_sum(p2_net)
        total_2_single += _read_co2_sum(p2_single)

    x = np.arange(4)
    y = [total_1_net, total_1_single, total_2_net, total_2_single]
    labels = [
        f"{compare_item1 or compare_short1}\n(verbundweise)",
        f"{compare_item1 or compare_short1}\n(quartiersweise)",
        f"{compare_item2 or compare_short2}\n(verbundweise)",
        f"{compare_item2 or compare_short2}\n(quartiersweise)",
    ]
    colors = ["#D40000", "#55585C","#F08A84" , "#B9BABC"]

    plt.figure(figsize=(9, 4.8))
    bars = plt.bar(x, y, color=colors, width=0.55)

    if show_percent_box:
        ymax = max(max(y), 1.0)
        plt.ylim(0, ymax * 1.30)
        y_offset = ymax * 0.06

        if total_1_single == 0:
            txt1 = "n/a" if total_1_net == 0 else "+∞"
        else:
            txt1 = _fmt_pct((total_1_net - total_1_single) / total_1_single * 100.0)

        if total_2_single == 0:
            txt2 = "n/a" if total_2_net == 0 else "+∞"
        else:
            txt2 = _fmt_pct((total_2_net - total_2_single) / total_2_single * 100.0)

        plt.text(
            bars[0].get_x() + bars[0].get_width() / 2,
            total_1_net + y_offset,
            txt1,
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

        plt.text(
            bars[2].get_x() + bars[2].get_width() / 2,
            total_2_net + y_offset,
            txt2,
            ha="center",
            va="bottom",
            color="white",
            fontsize=12,
            bbox=dict(
                boxstyle="square,pad=0.35",
                facecolor="#F08A84",
                edgecolor="#F08A84",
                linewidth=1.2,
            ),
            zorder=5,
        )

    plt.xticks(x, labels)
    plt.ylabel("CO₂-Emissionen in t")
    # plt.title(titel or "CO₂-Summe über 3 Quartiere: 4-Balken-Vergleich")
    plt.grid(axis="y", alpha=0.4)
    plt.ticklabel_format(axis="y", style="plain", useOffset=False)
    plt.tight_layout()

    plot_name = "co2_sum_three_quarters_four_bars.pdf" if not titel else f"{titel}.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario_names": list(scenario_names),
        "compare_short1_network_sum": total_1_net,
        "compare_short1_single_sum": total_1_single,
        "compare_short2_network_sum": total_2_net,
        "compare_short2_single_sum": total_2_single,
        "plot_path": plot_path,
    }




def plot_lcoe_sum_from_three_scenarios(
    scenario_names,
    compare_short1,
    compare_short2,
    compare_item1=None,
    compare_item2=None,
    base_dir=None,
    result_dir=None,
    show=True,
    titel=None,
    base_calendar_year=2025,
    show_percent_box=False,
):
    """
    Plot LCOE je Jahr als Summe aus 3 Szenarien mit 4 Balken pro Jahr:
    - compare_short1 network
    - compare_short1 single
    - compare_short2 network
    - compare_short2 single

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

                if cat == "optimization" and metric == "tac_distr":
                    v = _parse_value(row.get("value"))
                    try:
                        tac += float(v)
                    except Exception:
                        pass
                    continue

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
        if abs(p - round(p)) < 0.05:
            s = f"{p:+.0f}%"
        else:
            s = f"{p:+.1f}%"
        return s.replace(".", ",")

    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)

    tac_1_net = 0.0
    tac_1_single = 0.0
    tac_2_net = 0.0
    tac_2_single = 0.0

    supply_1_net = {}
    supply_1_single = {}
    supply_2_net = {}
    supply_2_single = {}

    for sc in scenario_names:
        p1_net = os.path.join(base_dir, f"{sc}_{compare_short1}_network_results.csv")
        p1_single = os.path.join(base_dir, f"{sc}_{compare_short1}_results.csv")
        p2_net = os.path.join(base_dir, f"{sc}_{compare_short2}_network_results.csv")
        p2_single = os.path.join(base_dir, f"{sc}_{compare_short2}_results.csv")

        missing = [p for p in [p1_net, p1_single, p2_net, p2_single] if not os.path.isfile(p)]
        if missing:
            raise FileNotFoundError(f"Missing files for scenario '{sc}':\n" + "\n".join(missing))

        t, ys = _read_tac_and_yearly_supply(p1_net)
        tac_1_net += t
        for y, v in ys.items():
            supply_1_net[y] = supply_1_net.get(y, 0.0) + v

        t, ys = _read_tac_and_yearly_supply(p1_single)
        tac_1_single += t
        for y, v in ys.items():
            supply_1_single[y] = supply_1_single.get(y, 0.0) + v

        t, ys = _read_tac_and_yearly_supply(p2_net)
        tac_2_net += t
        for y, v in ys.items():
            supply_2_net[y] = supply_2_net.get(y, 0.0) + v

        t, ys = _read_tac_and_yearly_supply(p2_single)
        tac_2_single += t
        for y, v in ys.items():
            supply_2_single[y] = supply_2_single.get(y, 0.0) + v

    years = sorted(set(supply_1_net) | set(supply_1_single) | set(supply_2_net) | set(supply_2_single))
    if not years:
        raise ValueError("Keine yearly_totals-Daten für Wärme/Strom gefunden.")

    lcoe_1_net = np.array([(tac_1_net / supply_1_net[y]) if supply_1_net.get(y, 0.0) > 0 else 0.0 for y in years], dtype=float)
    lcoe_1_single = np.array([(tac_1_single / supply_1_single[y]) if supply_1_single.get(y, 0.0) > 0 else 0.0 for y in years], dtype=float)
    lcoe_2_net = np.array([(tac_2_net / supply_2_net[y]) if supply_2_net.get(y, 0.0) > 0 else 0.0 for y in years], dtype=float)
    lcoe_2_single = np.array([(tac_2_single / supply_2_single[y]) if supply_2_single.get(y, 0.0) > 0 else 0.0 for y in years], dtype=float)

    x = np.arange(len(years))
    width = 0.18
    labels = [str(base_calendar_year + y) for y in years]

    plt.figure(figsize=(9, 4.8))
    plt.bar(x - 1.5 * width, lcoe_1_net, width=width, color="#D40000", label=f"{compare_item1 or compare_short1} (verbundweise)")
    plt.bar(x - 0.5 * width, lcoe_1_single, width=width, color="#55585C", label=f"{compare_item1 or compare_short1} (quartiersweise)")
    plt.bar(x + 0.5 * width, lcoe_2_net, width=width, color="#F08A84", label=f"{compare_item2 or compare_short2} (verbundweise)")
    plt.bar(x + 1.5 * width, lcoe_2_single, width=width, color="#B9BABC", label=f"{compare_item2 or compare_short2} (quartiersweise)")

    ymax = max(np.max(lcoe_1_net), np.max(lcoe_1_single), np.max(lcoe_2_net), np.max(lcoe_2_single), 1.0)

    if show_percent_box:
        plt.ylim(0, ymax * 1.35)
        y_offset = ymax * 0.06

        for i in range(len(years)):
            if lcoe_1_single[i] == 0:
                txt1 = "n/a" if lcoe_1_net[i] == 0 else "+∞"
            else:
                txt1 = _fmt_pct((lcoe_1_net[i] - lcoe_1_single[i]) / lcoe_1_single[i] * 100.0)

            if lcoe_2_single[i] == 0:
                txt2 = "n/a" if lcoe_2_net[i] == 0 else "+∞"
            else:
                txt2 = _fmt_pct((lcoe_2_net[i] - lcoe_2_single[i]) / lcoe_2_single[i] * 100.0)

            plt.text(
                x[i] - 1.5 * width,
                lcoe_1_net[i] + y_offset,
                txt1,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#D40000", edgecolor="#D40000", linewidth=1.0),
                zorder=5,
            )
            plt.text(
                x[i] + 0.5 * width,
                lcoe_2_net[i] + y_offset,
                txt2,
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#F08A84", edgecolor="#F08A84", linewidth=1.0),
                zorder=5,
            )

    plt.xticks(x, labels)
    plt.ylabel("Energiegestehungskosten in €/MWh")
    plt.grid(axis="y", alpha=0.35)
    plt.legend(ncol=2)
    plt.tight_layout()

    plot_name = f"{titel}.pdf" if titel else "lcoe_sum_three_scenarios_4bars.pdf"
    plot_path = os.path.join(plots_dir, plot_name)
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved: {plot_path}")

    if show:
        plt.show()
    else:
        plt.close()

    return {
        "scenario_names": list(scenario_names),
        "years": years,
        "lcoe_compare_short1_network_by_year": dict(zip(years, lcoe_1_net)),
        "lcoe_compare_short1_single_by_year": dict(zip(years, lcoe_1_single)),
        "lcoe_compare_short2_network_by_year": dict(zip(years, lcoe_2_net)),
        "lcoe_compare_short2_single_by_year": dict(zip(years, lcoe_2_single)),
        "tac": {
            "compare_short1_network": tac_1_net,
            "compare_short1_single": tac_1_single,
            "compare_short2_network": tac_2_net,
            "compare_short2_single": tac_2_single,
        },
        "plot_path": plot_path,
    }





def main():
    # Beispiel-Konfiguration

    scenario_name3 = "mixed1"   # z. B. "residential2"
    scenario_name1 = "residential2"   # z. B. "residential2"
    scenario_name2 = "ghd6"   # z. B. "residential2"
    #compare_short1 = "Batterie"   # z. B. "without_vp"
    compare_short1 = "PV"   # z. B. "without_vp"
    compare_short2 = "Basis"   # z. B. "with_vp"

    # Optional: lesbare Labels für die Legende
    #compare_item1 = "Batterie-Szenario"
    compare_item1 = "Solarausbau-Szenario"
    compare_item2 = "Basis-Szenario"

    # Optional: Ergebnis- und Plot-Verzeichnisse
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    base_dir = os.path.join(project_root, "Main-tja", "optimization_results")
    result_dir = os.path.join(project_root, "Main-tja", "optimization_results")

    plot_lcoe_sum_from_three_scenarios(
        scenario_names=[scenario_name1, scenario_name2, scenario_name3],
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        compare_item1=compare_item1,
        compare_item2=compare_item2,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        show_percent_box=True,
    )

    plot_co2_sum_from_three_scenarios_four_bars(
        scenario_names=[scenario_name1, scenario_name2, scenario_name3],
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        compare_item1=compare_item1,
        compare_item2=compare_item2,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        show_percent_box=True
    )

    plot_tac_sum_from_three_scenarios_four_bars(
        scenario_names=[scenario_name1, scenario_name2, scenario_name3],
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        compare_item1=compare_item1,
        compare_item2=compare_item2,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        show_percent_box=True)


    plot_device_capacities_four_bars_from_csv(
        scenario_name=scenario_name1,
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        compare_item1=compare_item1,
        compare_item2=compare_item2,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        include_devices=["PV", "EB"],
        # include_devices=["EB", "PV", "BBOI", "HP"],
        exclude_devices=None,
        show_percent_box=True,
    )
    plot_storage_capacities_four_bars_from_csv(
        scenario_name=scenario_name1,
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        compare_item1=compare_item1,
        compare_item2=compare_item2,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        include_devices=["TES", "BAT"],
        exclude_devices=None,
        show_percent_box=True,
    )

    plot_co2_by_year_four_bars_from_csv(
        scenario_name=scenario_name1,
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        compare_item1=compare_item1,
        compare_item2=compare_item2,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        show_percent_box=True,
    )

    plot_lcoe_by_year_four_bars_from_csv(
        scenario_name=scenario_name1,
        compare_short1=compare_short1,
        compare_short2=compare_short2,
        compare_item1=compare_item1,
        compare_item2=compare_item2,
        base_dir=base_dir,
        result_dir=result_dir,
        show=True,
        show_percent_box=True,
    )

if __name__ == "__main__":
    main()