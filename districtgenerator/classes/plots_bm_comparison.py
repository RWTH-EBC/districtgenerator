# -*- coding: utf-8 -*-
"""
plots_bm_comparison.py — Economic comparison plots for business models.

Extended version with:
- Technology mix per BM
- Electrical hub balance (grid import, grid export, export to buildings, self-consumption)
- Autonomy and CO2 per year and BM

Usage:
    from plots_bm_comparison import plot_bm_economics
    plot_bm_economics(results, save_dir="results/plots/bm_comparison")

    where `results` is the dict returned by compare_business_models().
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ══════════════════════════════════════════════════════════════════════
# COLOR SCHEME
# ══════════════════════════════════════════════════════════════════════

BM_COLORS = {
    "contracting": "#2196F3",
    "cooperative": "#4CAF50",
    "mieterstrom": "#FF9800",
    "mietstrom": "#FF9800",  # alias without 'e'
    "kundenanlage": "#9C27B0",
    "reference": "#607D8B",
}

COST_COLORS = {
    "Investment (ann.)": "#1565C0",
    "O&M": "#42A5F5",
    "Energiekosten (netto)": "#EF6C00",
    "PV-Kosten": "#FFC107",
    "E-Netz-Kosten": "#795548",
    "Strom-Erlöse": "#66BB6A",
    "Reststrom-Erlös": "#AED581",
    "PV-btm-Bonus / Credit": "#C8E6C9",
    "PV-Export / Feed-in": "#81C784",
}

# Technology colors for stacked bar charts
TECH_COLORS = {
    # Heat generation
    "HP": "#1976D2",  # Heat Pump - Blue
    "EB": "#2196F3",  # Electric Boiler - Light Blue
    "BOI": "#FF9800",  # Gas Boiler - Orange
    "BBOI": "#8BC34A",  # Biomass Boiler - Green
    "H2BOI": "#00BCD4",  # Hydrogen Boiler - Cyan
    "OBOI": "#795548",  # Oil Boiler - Brown
    "CHP": "#9C27B0",  # CHP - Purple
    "BCHP": "#7B1FA2",  # Biomass CHP - Dark Purple
    "FC": "#00ACC1",  # Fuel Cell - Teal
    "STC": "#FFC107",  # Solar Thermal - Amber
    "DH": "#F44336",  # District Heating - Red
    "GHP": "#3F51B5",  # Ground Heat Pump - Indigo

    # Power generation
    "PV": "#FFEB3B",  # PV - Yellow
    "WT": "#4CAF50",  # Wind Turbine - Green

    # Storage
    "BAT": "#673AB7",  # Battery - Deep Purple
    "TES": "#E91E63",  # Thermal Storage - Pink
    "H2S": "#009688",  # Hydrogen Storage - Teal

    # Grid flows
    "Grid Import": "#D32F2F",  # Red
    "Grid Export": "#388E3C",  # Green
    "To Buildings": "#1976D2",  # Blue
    "Self-Consumption": "#FFA000",  # Amber
    "From Buildings": "#7B1FA2",  # Purple
}


def _get_color(bm_name):
    return BM_COLORS.get(bm_name.lower(), "#607D8B")


def _safe_kpi(kpis, attr, default=0.0):
    """Safely get a KPI attribute, return default if missing or None."""
    if kpis is None:
        return default
    val = getattr(kpis, attr, None)
    return float(val) if val is not None else default


def _safe_cap(cap, key, default=0):
    """Safely get a capacities dict value."""
    if not isinstance(cap, dict):
        return default
    val = cap.get(key, None)
    if isinstance(val, dict):
        return float(val.get("cap", default))
    return float(val) if val is not None else default


def _get_kpis_and_cap(data):
    """Extract KPIs object and capacities dict from a Datahandler."""
    kpis = data.KPIs if hasattr(data, 'KPIs') and data.KPIs is not None else None
    cap = {}
    if hasattr(data, 'centralDevices') and isinstance(data.centralDevices, dict):
        cap = data.centralDevices.get("capacities", {})
        if not isinstance(cap, dict):
            cap = {}
    return kpis, cap


def _get_revenues(kpis, bm_name):
    """
    Extract BM-specific revenue components.
    Handles different attribute names per BM.

    Returns dict with standardized keys (all positive values = revenue).
    """
    rev = {
        "reststrom": 0.0,
        "pv_btm": 0.0,
        "pv_export": 0.0,
        "credit_el": 0.0,  # cooperative: avoided cost credit
    }
    if kpis is None:
        return rev

    # Mieterstrom
    rev["reststrom"] = _safe_kpi(kpis, "rev_reststrom_mietstrom")
    rev["pv_btm"] = max(_safe_kpi(kpis, "rev_pv_btm_bonus"),
                        _safe_kpi(kpis, "rev_pv_btm_kundenanlage"))
    rev["pv_export"] = max(_safe_kpi(kpis, "rev_pv_export_mietstrom"),
                           _safe_kpi(kpis, "rev_pv_export_kundenanlage"))

    # Kundenanlage (if mietstrom attrs are 0)
    if rev["reststrom"] == 0:
        rev["reststrom"] = _safe_kpi(kpis, "rev_reststrom_kundenanlage")

    # Cooperative: credit_avoided + credit_pv_feedin
    rev["credit_el"] = (_safe_kpi(kpis, "credit_avoided") +
                        _safe_kpi(kpis, "credit_pv_feedin"))

    return rev


# ══════════════════════════════════════════════════════════════════════
# PLOT: Technology Mix per BM
# ══════════════════════════════════════════════════════════════════════

def plot_technology_mix(results, save_path=None):
    """
    Stacked bar chart: Installed capacities of central and decentral devices per BM.
    Shows the technology mix for each business model.
    """
    bm_names = list(results.keys())
    if not bm_names:
        return

    # Collect technology capacities for each BM
    tech_data = {}
    all_techs = set()

    for name in bm_names:
        data = results[name]
        tech_data[name] = {}

        # Central devices
        if hasattr(data, 'centralDevices') and isinstance(data.centralDevices, dict):
            cap = data.centralDevices.get("capacities", {})
            if isinstance(cap, dict):
                for dev_name, dev_info in cap.items():
                    if isinstance(dev_info, dict) and "cap" in dev_info:
                        cap_val = dev_info["cap"]
                        if cap_val > 0:
                            tech_data[name][dev_name] = cap_val
                            all_techs.add(dev_name)

        # Decentral devices (aggregated from buildings)
        if hasattr(data, 'district') and isinstance(data.district, list):
            for bldg in data.district:
                if isinstance(bldg, dict) and "capacities" in bldg:
                    bldg_cap = bldg["capacities"]
                    for dev in ["HP", "BOI", "BBOI", "H2BOI", "OBOI", "CHP", "FC", "EH", "PV", "BAT", "TES", "STC"]:
                        if dev in bldg_cap:
                            val = bldg_cap[dev]
                            if isinstance(val, dict):
                                val = val.get("area", val.get("cap", 0))
                            if val > 0:
                                key = f"{dev} (dec)"
                                tech_data[name][key] = tech_data[name].get(key, 0) + val / 1000  # kW to MW
                                all_techs.add(key)

    if not all_techs:
        print("  No technology data found for technology mix plot.")
        return

    # Sort technologies
    tech_order = ["PV", "PV (dec)", "WT", "STC", "STC (dec)",
                  "HP", "HP (dec)", "EB", "BOI", "BOI (dec)",
                  "BBOI", "BBOI (dec)", "CHP", "BCHP", "FC", "FC (dec)",
                  "TES", "TES (dec)", "BAT", "BAT (dec)", "H2S"]
    sorted_techs = [t for t in tech_order if t in all_techs]
    sorted_techs += [t for t in sorted(all_techs) if t not in sorted_techs]

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(bm_names))
    bar_width = 0.6

    bottom = np.zeros(len(bm_names))

    for tech in sorted_techs:
        vals = np.array([tech_data[name].get(tech, 0) for name in bm_names])
        if np.any(vals > 0):
            # Get color (remove "(dec)" suffix for color lookup)
            base_tech = tech.replace(" (dec)", "")
            color = TECH_COLORS.get(base_tech, "#9E9E9E")
            # Lighter shade for decentral
            if "(dec)" in tech:
                import matplotlib.colors as mcolors
                rgb = mcolors.to_rgb(color)
                color = tuple(min(1, c + 0.3) for c in rgb)

            ax.bar(x, vals, bar_width, bottom=bottom, label=tech,
                   color=color, edgecolor="white", linewidth=0.3)
            bottom += vals

    ax.set_ylabel("Kapazität [kW]", fontsize=11)
    ax.set_title("Technologie-Mix pro Geschäftsmodell", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", " ").title() for n in bm_names], fontsize=10)
    ax.legend(fontsize=8, loc="upper right", ncol=3, bbox_to_anchor=(1.0, 1.0))
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════
# PLOT: Electrical Hub Balance per BM
# ══════════════════════════════════════════════════════════════════════

def plot_electrical_hub_balance(results, save_path=None):
    """
    Stacked bar chart: Electrical balance of the energy hub per BM.
    Shows:
    - Grid import (Strombezug aus dem Netz)
    - Grid export (Stromexport ins Netz)
    - Export to buildings (Stromlieferung an Gebäude)
    - Self-consumption (Eigenverbrauch im Hub)
    """
    bm_names = list(results.keys())
    if not bm_names:
        return

    # Collect electrical flows for each BM
    flow_data = {name: {} for name in bm_names}

    for name in bm_names:
        data = results[name]
        kpis = data.KPIs if hasattr(data, 'KPIs') and data.KPIs is not None else None

        if kpis is None:
            continue

        # Get simulation years
        years = list(kpis.W_dem_GCP_year.keys()) if hasattr(kpis, 'W_dem_GCP_year') else []
        if not years:
            continue

        # Use first year for annual values (or average)
        year = years[0]

        # Grid demand (import from grid)
        grid_import = kpis.W_dem_GCP_year.get(year, 0) if hasattr(kpis, 'W_dem_GCP_year') else 0

        # Grid injection (export to grid)
        grid_export = kpis.W_inj_GCP_year.get(year, 0) if hasattr(kpis, 'W_inj_GCP_year') else 0

        # Energy to buildings (from hub)
        to_buildings = kpis.W_dem_buildings_year.get(year, 0) if hasattr(kpis, 'W_dem_buildings_year') else 0

        # Energy from buildings (to hub)
        from_buildings = kpis.W_inj_buildings_year.get(year, 0) if hasattr(kpis, 'W_inj_buildings_year') else 0

        # Self-consumption = generation - export - to_buildings
        # Or estimate from demand cover factor
        dcf = kpis.dcf_year.get(year, 0) if hasattr(kpis, 'dcf_year') else 0
        scf = kpis.scf_year.get(year, 0) if hasattr(kpis, 'scf_year') else 0

        # Calculate self-consumption within district
        self_consumption = min(from_buildings, to_buildings) * dcf if dcf > 0 else 0

        flow_data[name] = {
            "Netzbezug": grid_import / 1000,  # kWh to MWh
            "Netzeinspeisung": grid_export / 1000,
            "Lieferung an Gebäude": to_buildings / 1000,
            "Eigenverbrauch": self_consumption / 1000,
        }

    if not any(flow_data.values()):
        print("  No electrical flow data found for hub balance plot.")
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(bm_names))
    bar_width = 0.35

    # Plot imports (positive) and exports (negative)
    import_keys = ["Netzbezug", "Lieferung an Gebäude"]
    export_keys = ["Netzeinspeisung", "Eigenverbrauch"]

    colors_import = ["#D32F2F", "#1976D2"]
    colors_export = ["#388E3C", "#FFA000"]

    # Imports (left side of grouped bars)
    bottom_pos = np.zeros(len(bm_names))
    for i, key in enumerate(import_keys):
        vals = np.array([flow_data[name].get(key, 0) for name in bm_names])
        ax.bar(x - bar_width / 2, vals, bar_width, bottom=bottom_pos,
               label=key, color=colors_import[i], edgecolor="white", linewidth=0.3)
        bottom_pos += vals

    # Exports (right side - shown as positive for comparison)
    bottom_neg = np.zeros(len(bm_names))
    for i, key in enumerate(export_keys):
        vals = np.array([flow_data[name].get(key, 0) for name in bm_names])
        ax.bar(x + bar_width / 2, vals, bar_width, bottom=bottom_neg,
               label=key, color=colors_export[i], edgecolor="white", linewidth=0.3)
        bottom_neg += vals

    ax.set_ylabel("Energie [MWh/a]", fontsize=11)
    ax.set_title("Elektrische Hub-Bilanz pro Geschäftsmodell", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", " ").title() for n in bm_names], fontsize=10)
    ax.legend(fontsize=9, loc="upper right")
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Add labels for grouped bars
    ax.text(-0.3, ax.get_ylim()[1] * 1.02, "Import ↓", fontsize=9, ha="center", color="#D32F2F")
    ax.text(0.3, ax.get_ylim()[1] * 1.02, "Export ↑", fontsize=9, ha="center", color="#388E3C")

    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════
# PLOT: Autonomy and CO2 per Year and BM
# ══════════════════════════════════════════════════════════════════════

def plot_autonomy_co2(results, save_path=None):
    """
    Combined plot showing:
    - Left axis: Autonomy (%) per BM
    - Right axis: CO2 emissions (t/a) per BM
    """
    bm_names = list(results.keys())
    if not bm_names:
        return

    autonomy_data = {}
    co2_data = {}

    for name in bm_names:
        data = results[name]
        kpis = data.KPIs if hasattr(data, 'KPIs') and data.KPIs is not None else None

        if kpis is None:
            continue

        # Get simulation years
        years = []
        if hasattr(kpis, 'energy_autonomy_year'):
            years = list(kpis.energy_autonomy_year.keys())
        elif hasattr(kpis, 'co2emissions'):
            years = list(kpis.co2emissions.keys())

        if not years:
            continue

        # Use first year
        year = years[0]

        # Autonomy
        if hasattr(kpis, 'energy_autonomy_year'):
            autonomy_data[name] = kpis.energy_autonomy_year.get(year, 0) * 100  # to %

        # CO2 emissions
        if hasattr(kpis, 'co2emissions') and isinstance(kpis.co2emissions.get(year), dict):
            co2_data[name] = kpis.co2emissions[year].get("total_co2", 0)
        elif hasattr(kpis, 'co2emissions'):
            co2_data[name] = kpis.co2emissions.get(year, 0)

    if not autonomy_data and not co2_data:
        print("  No autonomy/CO2 data found.")
        return

    fig, ax1 = plt.subplots(figsize=(11, 6))
    x = np.arange(len(bm_names))
    bar_width = 0.35

    # Autonomy bars (left y-axis)
    autonomy_vals = [autonomy_data.get(name, 0) for name in bm_names]
    colors = [_get_color(name) for name in bm_names]

    bars1 = ax1.bar(x - bar_width / 2, autonomy_vals, bar_width,
                    label="Autonomie", color=colors, alpha=0.8,
                    edgecolor="white", linewidth=0.5)

    ax1.set_ylabel("Autonomie [%]", fontsize=11, color="#1976D2")
    ax1.tick_params(axis='y', labelcolor="#1976D2")
    ax1.set_ylim(0, 100)

    # Add value labels on autonomy bars
    for bar, val in zip(bars1, autonomy_vals):
        if val > 0:
            ax1.text(bar.get_x() + bar.get_width() / 2, val + 2,
                     f"{val:.1f}%", ha="center", va="bottom", fontsize=9, color="#1976D2")

    # CO2 bars (right y-axis)
    ax2 = ax1.twinx()
    co2_vals = [co2_data.get(name, 0) for name in bm_names]

    bars2 = ax2.bar(x + bar_width / 2, co2_vals, bar_width,
                    label="CO₂-Emissionen", color="#D32F2F", alpha=0.7,
                    edgecolor="white", linewidth=0.5)

    ax2.set_ylabel("CO₂-Emissionen [t/a]", fontsize=11, color="#D32F2F")
    ax2.tick_params(axis='y', labelcolor="#D32F2F")

    # Add value labels on CO2 bars
    for bar, val in zip(bars2, co2_vals):
        if val > 0:
            ax2.text(bar.get_x() + bar.get_width() / 2, val + ax2.get_ylim()[1] * 0.02,
                     f"{val:.1f}", ha="center", va="bottom", fontsize=9, color="#D32F2F")

    ax1.set_title("Autonomie und CO₂-Emissionen pro Geschäftsmodell", fontsize=13, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels([n.replace("_", " ").title() for n in bm_names], fontsize=10)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=10, loc="upper right")

    ax1.spines['top'].set_visible(False)
    ax2.spines['top'].set_visible(False)

    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    plt.close()


def plot_co2_breakdown(results, save_path=None):
    """
    Stacked bar chart: CO2 emissions breakdown by source per BM.
    """
    bm_names = list(results.keys())
    if not bm_names:
        return

    co2_sources = ["co2_dem_grid", "co2_gas", "co2_biom", "co2_oil",
                   "co2_hydrogen", "co2_district_heat", "co2_waste"]
    source_labels = {
        "co2_dem_grid": "Strom (Netz)",
        "co2_gas": "Erdgas",
        "co2_biom": "Biomasse",
        "co2_oil": "Heizöl",
        "co2_hydrogen": "Wasserstoff",
        "co2_district_heat": "Fernwärme",
        "co2_waste": "Abwärme",
    }
    source_colors = {
        "co2_dem_grid": "#FFC107",
        "co2_gas": "#FF9800",
        "co2_biom": "#8BC34A",
        "co2_oil": "#795548",
        "co2_hydrogen": "#00BCD4",
        "co2_district_heat": "#F44336",
        "co2_waste": "#9E9E9E",
    }

    co2_data = {name: {} for name in bm_names}

    for name in bm_names:
        data = results[name]
        kpis = data.KPIs if hasattr(data, 'KPIs') and data.KPIs is not None else None

        if kpis is None or not hasattr(kpis, 'co2emissions'):
            continue

        years = list(kpis.co2emissions.keys())
        if not years:
            continue

        year = years[0]
        emissions = kpis.co2emissions.get(year, {})

        if isinstance(emissions, dict):
            for source in co2_sources:
                co2_data[name][source] = emissions.get(source, 0)

    if not any(co2_data.values()):
        print("  No CO2 breakdown data found.")
        return

    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(bm_names))
    bar_width = 0.6

    bottom = np.zeros(len(bm_names))

    for source in co2_sources:
        vals = np.array([co2_data[name].get(source, 0) for name in bm_names])
        if np.any(vals > 0):
            ax.bar(x, vals, bar_width, bottom=bottom,
                   label=source_labels.get(source, source),
                   color=source_colors.get(source, "#9E9E9E"),
                   edgecolor="white", linewidth=0.3)
            bottom += vals

    # Add total labels
    totals = bottom
    for i, total in enumerate(totals):
        if total > 0:
            ax.text(i, total + ax.get_ylim()[1] * 0.02, f"{total:.1f} t",
                    ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_ylabel("CO₂-Emissionen [t/a]", fontsize=11)
    ax.set_title("CO₂-Emissionen nach Quelle pro Geschäftsmodell", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", " ").title() for n in bm_names], fontsize=10)
    ax.legend(fontsize=9, loc="upper right")
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════
# ORIGINAL PLOTS (p_min vs p_max, Cost breakdown, NPV, Alpha sensitivity)
# ══════════════════════════════════════════════════════════════════════

def plot_pmin_pmax(results, save_path=None, exclude_bms=None):
    """Bar chart: p_min vs p_max for each BM.

    Parameters
    ----------
    exclude_bms : list, optional
        List of BM names to exclude (default: ["reference", "cooperative"])
    """
    if exclude_bms is None:
        exclude_bms = ["reference", "cooperative"]

    bm_names = [name for name in results if name.lower() not in [e.lower() for e in exclude_bms]]
    if not bm_names:
        return

    p_mins = []
    p_maxs = []
    colors = []

    for name in bm_names:
        kpis, _ = _get_kpis_and_cap(results[name])
        pm = _safe_kpi(kpis, 'p_min', None)
        px = _safe_kpi(kpis, 'p_max', None)
        p_mins.append(pm * 100 if pm else 0)
        p_maxs.append(px * 100 if px else 0)
        colors.append(_get_color(name))

    x = np.arange(len(bm_names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5.5))

    bars_min = ax.bar(x, p_mins, width,
                      label=r"$p_{min}$ (Mindest-Wärmepreis)",
                      color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)

    # p_max line (use first non-zero value)
    p_max_val = next((v for v in p_maxs if v > 0), 0)
    if p_max_val > 0:
        ax.axhline(y=p_max_val, color="#D32F2F", linestyle="--", linewidth=1.8,
                   label=rf"$p_{{max}}$ = {p_max_val:.2f} ct/kWh (Referenz)")

    # Value labels
    for bar, val in zip(bars_min, p_mins):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, val + 0.3,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    # Feasibility markers + NPV info
    for i, (pmin, pmax) in enumerate(zip(p_mins, p_maxs)):
        if pmin > 0 and pmax > 0:
            marker = "wirtschaftlich" if pmin <= pmax else "nicht wirtsch."
            color = "#2E7D32" if pmin <= pmax else "#C62828"
            ax.text(x[i], pmin + 1.5, marker,
                    ha="center", fontsize=8, color=color, fontweight="bold")

        # Add NPV info below bar if available
        kpis_i, _ = _get_kpis_and_cap(results[bm_names[i]])
        npv_c = _safe_kpi(kpis_i, 'npv_coop', None)
        npv_d = _safe_kpi(kpis_i, 'npv_difference', None)
        if npv_c is not None:
            npv_label = f"NPV: {npv_c / 1000:,.0f}k€"
            if npv_d is not None:
                sign = "+" if npv_d >= 0 else ""
                npv_label += f" (Δ{sign}{npv_d / 1000:,.0f}k)"
            ax.text(x[i], -0.8, npv_label,
                    ha="center", fontsize=7, color="#455A64", style="italic")

    ax.set_ylabel("ct/kWh", fontsize=11)
    ax.set_title("Wirtschaftlichkeitsvergleich der Geschäftsmodelle", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", " ").title() for n in bm_names], fontsize=10)
    ax.legend(fontsize=10, loc="upper right")
    ax.set_ylim(0, max(p_mins + [p_max_val]) * 1.3)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    plt.close()


def plot_cost_breakdown(results, save_path=None):
    """
    Stacked bar chart: cost and revenue components per BM (EUR/a).
    """
    bm_names = [name for name in results if name != "reference"]
    if not bm_names:
        return

    rows = []
    for name in bm_names:
        data = results[name]
        kpis, cap = _get_kpis_and_cap(data)
        rev = _get_revenues(kpis, name)

        tac = _safe_cap(cap, "tac")
        ann_inv = _safe_cap(cap, "total_ann_inv_cost")
        om = _safe_cap(cap, "total_om_cost")

        # Heat grid costs
        hg_ann = 0.0
        hg_om = 0.0
        if hasattr(data, "heat_grid_data") and isinstance(data.heat_grid_data, dict):
            hg_ann = float(data.heat_grid_data.get("ann_costs", 0))
            hg_om = float(data.heat_grid_data.get("om_costs", 0))

        # Energy costs = TAC minus capital minus O&M minus heat grid
        energy_net = tac - (ann_inv + om + hg_ann + hg_om)

        # BM-specific additional costs
        c_pv = _safe_kpi(kpis, "c_pv_ann")
        c_elgrid = _safe_kpi(kpis, "c_elgrid_ann")

        rows.append({
            "Investment (ann.)": ann_inv + hg_ann,
            "O&M": om + hg_om,
            "Energiekosten (netto)": max(energy_net, 0),
            "PV-Kosten": c_pv,
            "E-Netz-Kosten": c_elgrid,
            "Reststrom-Erlös": -rev["reststrom"],
            "PV-btm-Bonus / Credit": -(rev["pv_btm"] + rev["credit_el"]),
            "PV-Export / Feed-in": -rev["pv_export"],
        })

    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(bm_names))
    bar_width = 0.55

    # Stack costs (positive)
    cost_keys = ["Investment (ann.)", "O&M", "Energiekosten (netto)", "PV-Kosten", "E-Netz-Kosten"]
    bottom_pos = np.zeros(len(bm_names))
    for key in cost_keys:
        vals = np.array([row.get(key, 0) for row in rows], dtype=float)
        if np.any(vals > 0):
            ax.bar(x, vals, bar_width, bottom=bottom_pos,
                   label=key, color=COST_COLORS.get(key, "#9E9E9E"),
                   edgecolor="white", linewidth=0.3)
            bottom_pos += np.maximum(vals, 0)

    # Stack revenues (negative)
    rev_keys = ["Reststrom-Erlös", "PV-btm-Bonus / Credit", "PV-Export / Feed-in"]
    bottom_neg = np.zeros(len(bm_names))
    for key in rev_keys:
        vals = np.array([row.get(key, 0) for row in rows], dtype=float)
        if np.any(vals < 0):
            ax.bar(x, vals, bar_width, bottom=bottom_neg,
                   label=key, color=COST_COLORS.get(key, "#A5D6A7"),
                   edgecolor="white", linewidth=0.3)
            bottom_neg += np.minimum(vals, 0)

    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_ylabel("EUR/a", fontsize=11)
    ax.set_title("Kostenaufschlüsselung pro Geschäftsmodell", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", " ").title() for n in bm_names], fontsize=10)
    ax.legend(fontsize=8, loc="upper right", ncol=2)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 1000:,.0f}k"))
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    plt.close()


def plot_npv_comparison(results, save_path=None):
    """
    Bar chart: NPV_coop vs NPV_ref for each BM that has NPV data.
    """
    bm_names = [name for name in results if name != "reference"]
    if not bm_names:
        return

    npv_coops = []
    npv_refs = []
    npv_diffs = []
    valid_names = []
    colors = []

    for name in bm_names:
        kpis, _ = _get_kpis_and_cap(results[name])
        npv_c = _safe_kpi(kpis, 'npv_coop', None)
        npv_r = _safe_kpi(kpis, 'npv_ref', None)
        npv_d = _safe_kpi(kpis, 'npv_difference', None)

        valid_names.append(name)
        npv_coops.append(npv_c / 1000 if npv_c is not None else 0)
        npv_refs.append(npv_r / 1000 if npv_r is not None else 0)
        npv_diffs.append(npv_d if npv_d is not None else None)
        colors.append(_get_color(name))

    if not valid_names:
        return

    x = np.arange(len(valid_names))
    width = 0.3

    fig, ax = plt.subplots(figsize=(11, 6))

    bars_coop = ax.bar(x - width / 2, npv_coops, width,
                       label=r"$NPV_{BM}$",
                       color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
    bars_ref = ax.bar(x + width / 2, npv_refs, width,
                      label=r"$NPV_{ref}$",
                      color="#D32F2F", alpha=0.5, edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars_coop, npv_coops):
        if val != 0:
            ax.text(bar.get_x() + bar.get_width() / 2, val,
                    f"{val:,.0f}k", ha="center", va="bottom", fontsize=9, fontweight="bold")
    for bar, val in zip(bars_ref, npv_refs):
        if val != 0:
            ax.text(bar.get_x() + bar.get_width() / 2, val,
                    f"{val:,.0f}k", ha="center", va="bottom", fontsize=9, color="#D32F2F")

    for i, (name, diff) in enumerate(zip(valid_names, npv_diffs)):
        if diff is not None:
            sign = "+" if diff >= 0 else ""
            color = "#2E7D32" if diff >= 0 else "#C62828"
            label = "vorteilhaft" if diff >= 0 else "nachteilig"
            y_pos = max(npv_coops[i], npv_refs[i])
            ax.annotate(f"Δ = {sign}{diff / 1000:,.0f}k€\n({label})",
                        (x[i], y_pos), textcoords="offset points",
                        xytext=(0, 15), ha="center", fontsize=9,
                        fontweight="bold", color=color)

    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_ylabel("k€ (Barwert)", fontsize=11)
    ax.set_title("NPV-Vergleich der Geschäftsmodelle", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", " ").title() for n in valid_names], fontsize=10)
    ax.legend(fontsize=10, loc="upper right")
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    plt.close()


def plot_alpha_sensitivity(alpha_results, p_max=None, save_path=None, exclude_bms=None):
    """
    Line plot: p_min over alpha for each BM.

    """
    if exclude_bms is None:
        exclude_bms = ["cooperative"]

    fig, ax = plt.subplots(figsize=(10, 6))

    for bm_name, alpha_data in alpha_results.items():
        # Skip excluded BMs
        if bm_name.lower() in [e.lower() for e in exclude_bms]:
            continue

        alphas = sorted(alpha_data.keys())
        valid = [(a, alpha_data[a]["p_min"] * 100)
                 for a in alphas
                 if alpha_data[a].get("p_min") is not None]

        if valid:
            ax.plot([v[0] for v in valid], [v[1] for v in valid], "o-",
                    label=bm_name.replace("_", " ").title(),
                    color=_get_color(bm_name), linewidth=2, markersize=5)

    if p_max is not None:
        ax.axhline(y=p_max * 100, color="#D32F2F", linestyle="--", linewidth=1.8,
                   label=rf"$p_{{max}}$ = {p_max * 100:.2f} ct/kWh")

    ax.set_xlabel(r"$\alpha$ (Anteil des Retail-Strompreises)", fontsize=11)
    ax.set_ylabel(r"$p_{min}$ (ct/kWh)", fontsize=11)
    ax.set_title(r"Sensitivitätsanalyse: $p_{min}(\alpha)$", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0.55, 1.05)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"  Saved: {save_path}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════
# CONVENIENCE: Run all plots
# ══════════════════════════════════════════════════════════════════════

def plot_bm_economics(results, save_dir="results/plots/bm_comparison",
                      alpha_results=None, p_max_ref=None):
    """
    Generate all economic comparison plots.

    Parameters
    ----------
    results : dict
        Output of compare_business_models().
    save_dir : str
        Directory for saving PDFs.
    alpha_results : dict, optional
        If provided, alpha sensitivity plot is generated.
    p_max_ref : float, optional
        p_max from reference in EUR/kWh (for alpha plot).
    """
    os.makedirs(save_dir, exist_ok=True)
    print(f"\nGenerating economic comparison plots in {save_dir}/\n")

    # Original plots (excluding cooperative from p_min plot)
    plot_pmin_pmax(results,
                   save_path=os.path.join(save_dir, "01_pmin_pmax_comparison.pdf"))

    plot_cost_breakdown(results,
                        save_path=os.path.join(save_dir, "02_cost_breakdown.pdf"))

    plot_npv_comparison(results,
                        save_path=os.path.join(save_dir, "03_npv_comparison.pdf"))

    if alpha_results:
        if p_max_ref is None:
            for data in results.values():
                kpis, _ = _get_kpis_and_cap(data)
                pm = _safe_kpi(kpis, 'p_max', None)
                if pm:
                    p_max_ref = pm
                    break

        plot_alpha_sensitivity(alpha_results, p_max=p_max_ref,
                               save_path=os.path.join(save_dir, "04_alpha_sensitivity.pdf"))

    # NEW plots
    plot_technology_mix(results,
                        save_path=os.path.join(save_dir, "05_technology_mix.pdf"))

    plot_electrical_hub_balance(results,
                                save_path=os.path.join(save_dir, "06_electrical_hub_balance.pdf"))

    plot_autonomy_co2(results,
                      save_path=os.path.join(save_dir, "07_autonomy_co2.pdf"))

    plot_co2_breakdown(results,
                       save_path=os.path.join(save_dir, "08_co2_breakdown.pdf"))

    print(f"\nAll plots saved to {save_dir}/")


def plot_alpha_only(alpha_results, p_max_ref, save_path="results/plots/alpha_sensitivity.pdf",
                    exclude_bms=None):
    """
    Generate ONLY the alpha sensitivity plot - no KPIs storage, just the plot.

    This is a lightweight function for running alpha sensitivity analysis
    without storing full KPIs for each alpha value.


    """
    if exclude_bms is None:
        exclude_bms = ["cooperative"]

    print(f"\nGenerating alpha sensitivity plot...")
    plot_alpha_sensitivity(alpha_results, p_max=p_max_ref, save_path=save_path,
                           exclude_bms=exclude_bms)
    print(f"  Saved: {save_path}")