# -*- coding: utf-8 -*-
"""
plots_extra.py

  E1  Kostenaufschluesselung pro BM
  E2  CO2-Aufschluesselung nach Quelle pro BM
  E3  Technologie-Mix (Erzeuger kW + Speicher kWh in einer Grafik)
  E4  Hub-Bilanzen pro Cluster, ueber alle simulierten Jahre
      (eine PDF-Seite pro Jahr, Cluster untereinander)
  E5  Distrikt-Bilanz pro Cluster, ueber alle Jahre
  E6  NPV-Vergleichstabelle pro Haus (CSV + PNG) je BM
"""

import os
import csv
import pickle
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


# ═══════════════════════════════════════════════════════════════
# Schriftgroessen analog plots_balances.py (etwas dezenter fuer A4)
# ═══════════════════════════════════════════════════════════════

PLOT_RC = {
    "font.size":        12,
    "axes.titlesize":   12,
    "axes.labelsize":   12,
    "xtick.labelsize":  10,
    "ytick.labelsize":  10,
    "legend.fontsize":  9,
    "figure.titlesize": 13,
}


def _apply_rc():
    plt.rcParams.update(PLOT_RC)


# ═══════════════════════════════════════════════════════════════
# Farben
# ═══════════════════════════════════════════════════════════════

CO2_COLORS = {
    "Strom (Netz)":   "#FFC107",
    "Erdgas":         "#FB8C00",
    "Biomasse":       "#7CB342",
    "Heizoel":        "#5D4037",
    "Wasserstoff":    "#26C6DA",
    "Abwaerme/Waste": "#9E9E9E",
    "Fernwaerme":     "#E53935",
}

COST_COLORS = {
    "Erzeuger zentral":    "#1565C0",
    "Erzeuger dezentral":  "#42A5F5",
    "Energiekosten":       "#FFA726",
    "Waermenetz":          "#8E24AA",
    "Stromnetz (Kabel)":   "#EC407A",
    "Trafo":               "#AD1457",
    "PV-Kosten":           "#FDD835",
}

TECH_COLORS = {
    "BOI":  "#FF7043", "BBOI": "#FFAB91", "WBOI": "#BF360C",
    "CHP":  "#5D4037", "BCHP": "#8D6E63", "WCHP": "#3E2723",
    "HP":   "#1E88E5", "GHP":  "#5E92F3",
    "EB":   "#FDD835",
    "FC":   "#26A69A",
    "STC":  "#FFA726",
    "PV":   "#FBC02D", "WT":   "#43A047", "WAT":  "#0277BD",
    "ELYZ": "#7B1FA2",
    "TES":  "#E91E63", "CTES": "#F06292",
    "BAT":  "#5E35B2", "H2S":  "#9575CD", "GS":  "#7E57C2",
}

POWER_DEVS = ("PV", "WT", "WAT", "HP", "GHP", "EB", "CC", "CHP", "BCHP",
              "WCHP", "ELYZ", "FC", "STC", "BOI", "BBOI", "WBOI", "AC")
STORAGE_DEVS = ("TES", "CTES", "BAT", "H2S", "GS")
_HEAT_SOURCES = ("STC", "HP", "GHP", "CHP", "BCHP", "WCHP",
                 "BOI", "BBOI", "WBOI", "EB", "FC")


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _load_pkl(p):
    with open(p, "rb") as f:
        return pickle.load(f)

def _kstatic(s):  return (s.get("kpis") or {}).get("static") or {}
def _kyearly(s):  return (s.get("kpis") or {}).get("yearly") or {}

def _kbm(s):
    bd = (s.get("kpis") or {}).get("bm_breakdown") or {}
    return bd.get("bm_breakdown") or {}

def _all_years(s) -> List:
    yrs = (s.get("kpis") or {}).get("simulated_years") or []
    return sorted(yrs)

def _pretty(sub_key: str) -> str:
    if "__" in sub_key:
        bm, flag = sub_key.split("__", 1)
    else:
        bm, flag = sub_key, ""
    pretty = {
        "waermecontracting":              "Contracting",
        "waermecontracting_ggv":          "GGV",
        "waermecontracting_kundenanlage": "Kundenanlage",
        "waermegenossenschaft":           "Genossenschaft",
    }.get(bm, bm)
    return f"{pretty} ({flag})" if flag else pretty


def _yearly_sum(s, key: str) -> float:
    """Summe ueber alle simulierten Jahre."""
    yr = _kyearly(s)
    d = yr.get(key) or {}
    total = 0.0
    for v in d.values():
        if isinstance(v, dict):
            v = v.get("total_co2", 0)
        if v is not None:
            total += float(v)
    return total


def _yearly_mean(s, key: str) -> float:
    """Mittelwert ueber alle simulierten Jahre — fuer annualisierte Werte."""
    yr = _kyearly(s)
    d = yr.get(key) or {}
    vals = []
    for v in d.values():
        if isinstance(v, dict):
            v = v.get("total_co2", 0)
        if v is not None:
            vals.append(float(v))
    return float(np.mean(vals)) if vals else 0.0


def _heat_grid_cost_annual(s):
    cost = (s.get("heat_grid") or {}).get("cost") or {}
    return float((cost.get("annualized_capex_eur") or 0)
                 + (cost.get("annual_om_eur") or 0))


def _smart_unit_eur(values):
    m = max(abs(v) for v in values if v is not None) if values else 0.0
    if m >= 1_000_000: return 1e-6, "Mio. EUR"
    if m >= 10_000:    return 1e-3, "kEUR"
    return 1.0, "EUR"


def _legend_compact(ax, **kw):
    leg = ax.legend(framealpha=0.85, edgecolor="#CFCFCF",
                    handlelength=1.4, handletextpad=0.5,
                    borderpad=0.4, labelspacing=0.3, **kw)
    if leg: leg.get_frame().set_linewidth(0.4)
    return leg


def _ax_compact_legend(ax, n_items: int, loc="upper right"):
    if n_items == 0: return
    ncol = min(n_items, 4) if n_items > 4 else n_items
    leg = ax.legend(loc=loc, ncol=ncol,
                    framealpha=0.75, edgecolor="#CFCFCF",
                    handlelength=1.2, handletextpad=0.4,
                    borderpad=0.3, labelspacing=0.25,
                    columnspacing=0.8, fontsize=8)
    if leg: leg.get_frame().set_linewidth(0.3)


def _stack_keys(cl_data, prefix, keys):
    out = {}
    for k in keys:
        full = f"{prefix}_{k}"
        if full in cl_data:
            arr = np.asarray(cl_data[full], dtype=float)
            if np.any(np.abs(arr) > 1e-6):
                out[k] = arr
    return out


# ═══════════════════════════════════════════════════════════════
# E1 — KOSTEN (annualisierte Mittelwerte ueber alle Jahre)
# ═══════════════════════════════════════════════════════════════

def plot_cost_breakdown(grouped, save_path, reference_key) -> None:
    """
    Stacked bars (annualisiert) — aufgeschluesselt auf Geraete-Ebene:

    Zentral (aus device_costs.central):
       Erzeuger zentral pro Geraet (BOI, CHP, HP, ...)
       Speicher zentral (TES, BAT)

    Dezentral (aus device_costs.decentral, summiert ueber alle Gebaeude):
       PV (dec), STC (dec), HP (dec), BOI (dec), TES (dec), BAT (dec), ...
       T-Reduktionsmassnahmen (T_reduction_measures)

    Plus:
       Energiekosten (operationCosts, Mittel ueber Jahre)
       Waermenetz (heat_grid.cost annual)
       Stromnetz Kabel + Trafo (Kundenanlage)
       PV-Kosten zentral (GGV/KA bm_breakdown.pv_cost_ann_total)
    """
    _apply_rc()
    bms = grouped[reference_key]["bms"]
    if not bms: return

    # ---- Daten je BM einsammeln ----
    rows = []
    all_central_devs  = []
    all_decentral_devs = []

    for sub_key, run in bms.items():
        s = run["summary"]
        st = _kstatic(s); bd = _kbm(s)
        bm = run["info"]["business_model"]
        dev_costs = (s.get("device_costs") or {})
        dec_per_bldg = dev_costs.get("decentral") or {}
        cen_per_dev  = dev_costs.get("central") or {}

        # Zentrale Geraete (pro Geraetetyp ein Eintrag)
        cen = {}
        for dev, info in cen_per_dev.items():
            if not isinstance(info, dict): continue
            v = float(info.get("subsidized_annual_cost") or 0)
            if v > 0 and dev != "Heat_Grid":   # Heat_Grid separat als "Waermenetz"
                cen[dev] = v
                if dev not in all_central_devs:
                    all_central_devs.append(dev)

        # Dezentrale Geraete (ueber Gebaeude summiert)
        dec = {}
        for bidx, bldg_devs in dec_per_bldg.items():
            if not isinstance(bldg_devs, dict): continue
            for dev, info in bldg_devs.items():
                if not isinstance(info, dict): continue
                v = float(info.get("subsidized_annual_cost") or 0)
                if v > 0:
                    dec[dev] = dec.get(dev, 0.0) + v
                    if dev not in all_decentral_devs:
                        all_decentral_devs.append(dev)

        op_costs = _yearly_mean(s, "operationCosts")
        hg_cost  = _heat_grid_cost_annual(s)
        pv_cost  = float(bd.get("pv_cost_ann_total") or 0)

        c_kabel = 0.0; c_trafo = 0.0
        if bm == "waermecontracting_kundenanlage":
            c_kabel = float(bd.get("c_elgrid_ann") or 0)
            c_trafo = float(bd.get("trafo_ann_from_milp") or 0)

        rows.append({
            "label":     _pretty(sub_key),
            "central":   cen,
            "decentral": dec,
            "op_costs":  op_costs,
            "hg_cost":   hg_cost,
            "pv_cost":   pv_cost,
            "c_kabel":   c_kabel,
            "c_trafo":   c_trafo,
        })

    # ---- Skala bestimmen ----
    totals = []
    for r in rows:
        t = (sum(r["central"].values()) + sum(r["decentral"].values())
             + r["op_costs"] + r["hg_cost"] + r["pv_cost"]
             + r["c_kabel"] + r["c_trafo"])
        totals.append(t)
    factor, unit = _smart_unit_eur(totals)

    # ---- Plot ----
    fig, ax = plt.subplots(figsize=(max(11, 1.7 * len(rows) + 2), 7))
    x = np.arange(len(rows))
    bottom = np.zeros(len(rows))

    # 1) zentrale Geraete (gestapelt, je nach Geraet)
    for dev in all_central_devs:
        vals = np.array([r["central"].get(dev, 0) * factor for r in rows])
        if not np.any(vals > 0): continue
        ax.bar(x, vals, 0.55, bottom=bottom,
               color=TECH_COLORS.get(dev, "#9E9E9E"),
               label=f"{dev} (zentral)", edgecolor="white", linewidth=0.4)
        bottom += vals

    # 2) dezentrale Geraete (gestapelt, andere Schraffur fuer Unterscheidung)
    for dev in all_decentral_devs:
        vals = np.array([r["decentral"].get(dev, 0) * factor for r in rows])
        if not np.any(vals > 0): continue
        # einheitliche Farbe + dezenter Hatch fuer dezentral
        col = TECH_COLORS.get(dev, "#90A4AE")
        ax.bar(x, vals, 0.55, bottom=bottom,
               color=col, hatch="//", alpha=0.85,
               label=f"{dev} (dezentral)", edgecolor="white", linewidth=0.4)
        bottom += vals

    # 3) Energiekosten
    vals = np.array([r["op_costs"] * factor for r in rows])
    if np.any(vals > 0):
        ax.bar(x, vals, 0.55, bottom=bottom,
               color=COST_COLORS["Energiekosten"],
               label="Energiekosten", edgecolor="white", linewidth=0.4)
        bottom += vals

    # 4) Waermenetz
    vals = np.array([r["hg_cost"] * factor for r in rows])
    if np.any(vals > 0):
        ax.bar(x, vals, 0.55, bottom=bottom,
               color=COST_COLORS["Waermenetz"],
               label="Waermenetz", edgecolor="white", linewidth=0.4)
        bottom += vals

    # 5) Stromnetz Kabel
    vals = np.array([r["c_kabel"] * factor for r in rows])
    if np.any(vals > 0):
        ax.bar(x, vals, 0.55, bottom=bottom,
               color=COST_COLORS["Stromnetz (Kabel)"],
               label="Stromnetz (Kabel)", edgecolor="white", linewidth=0.4)
        bottom += vals

    # 6) Trafo
    vals = np.array([r["c_trafo"] * factor for r in rows])
    if np.any(vals > 0):
        ax.bar(x, vals, 0.55, bottom=bottom,
               color=COST_COLORS["Trafo"],
               label="Trafo", edgecolor="white", linewidth=0.4)
        bottom += vals

    # 7) PV-Kosten BM-spezifisch
    vals = np.array([r["pv_cost"] * factor for r in rows])
    if np.any(vals > 0):
        ax.bar(x, vals, 0.55, bottom=bottom,
               color=COST_COLORS["PV-Kosten"],
               label="PV (GGV/KA)", edgecolor="white", linewidth=0.4)
        bottom += vals

    # Total ueber jedem Bar
    for i, t in enumerate(bottom):
        if t > 0:
            ax.text(i, t, f"{t:,.1f} {unit}", ha="center", va="bottom",
                    fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([r["label"] for r in rows], rotation=15, ha="right")
    ax.set_ylabel(f"{unit}/a")
    ax.set_title(f"Kostenaufschluesselung pro BM – Referenz {reference_key}",
                 fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)

    leg = ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                    ncol=1, framealpha=0.9, edgecolor="#CFCFCF",
                    handlelength=1.6, handletextpad=0.5,
                    borderpad=0.4, labelspacing=0.3, fontsize=9)
    if leg: leg.get_frame().set_linewidth(0.4)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight"); plt.close()
    print(f"  Saved: {save_path}")


# ═══════════════════════════════════════════════════════════════
# E2 — CO2 (Summe ueber alle simulierten Jahre)
# ═══════════════════════════════════════════════════════════════

def plot_co2_breakdown(grouped, save_path, reference_key) -> None:
    """
    static co2-Werte sind kumulativ ueber alle Jahre;
    yearly co2emissions[year] gibt Jahreswerte. Hier nutzen wir die yearly
    Aufschluesselung NICHT (kein Quellen-Split pro Jahr) -> static-Werte sind
    bereits die Summe aller simulierten Jahre. Daher ist das pro-Jahr-Mittel
    = total / n_years.
    """
    _apply_rc()
    bms = grouped[reference_key]["bms"]
    if not bms: return

    KEYS = [
        ("total_co2_dem_grid",      "Strom (Netz)"),
        ("total_co2_gas",           "Erdgas"),
        ("total_co2_biom",          "Biomasse"),
        ("total_co2_oil",           "Heizoel"),
        ("total_co2_hydrogen",      "Wasserstoff"),
        ("total_co2_waste",         "Abwaerme/Waste"),
        ("total_co2_district_heat", "Fernwaerme"),
    ]

    rows = []
    for sub_key, run in bms.items():
        s = run["summary"]
        st = _kstatic(s)
        n_y = max(len(_all_years(s)), 1)
        rec = {"label": _pretty(sub_key), "n_years": n_y}
        for k, lab in KEYS:
            v = st.get(k, 0)
            # Mittelwert pro Jahr in Tonnen
            rec[lab] = (float(v) / 1000.0 / n_y) if v else 0.0
        rec["total"] = sum(rec[lab] for _, lab in KEYS)
        rows.append(rec)

    fig, ax = plt.subplots(figsize=(max(9, 1.6 * len(rows)), 6.5))
    x = np.arange(len(rows))
    bottom = np.zeros(len(rows))
    for _, lab in KEYS:
        vals = np.array([r[lab] for r in rows])
        if not np.any(vals > 0): continue
        ax.bar(x, vals, 0.55, bottom=bottom,
               color=CO2_COLORS.get(lab, "#9E9E9E"),
               label=lab, edgecolor="white", linewidth=0.4)
        bottom += vals
    for i, t in enumerate(bottom):
        ax.text(i, t, f"{t:,.2f} t/a", ha="center", va="bottom",
                fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([r["label"] for r in rows], rotation=15, ha="right")
    ax.set_ylabel("CO₂ [t/a]  (Mittel ueber simulierte Jahre)")
    ax.set_title(f"CO₂-Emissionen nach Quelle pro BM – Referenz {reference_key}",
                 fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    _legend_compact(ax, loc="upper right", ncol=1)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight"); plt.close()
    print(f"  Saved: {save_path}")


# ═══════════════════════════════════════════════════════════════
# E3 — TECH-MIX (eine Grafik mit Twin-Y-Achse)
# ═══════════════════════════════════════════════════════════════

def plot_technology_mix_combined(grouped, save_path, reference_key) -> None:
    _apply_rc()
    bms = grouped[reference_key]["bms"]
    if not bms: return

    rows = []
    devs_p, devs_s = [], []
    for sub_key, run in bms.items():
        central = ((run["summary"].get("capacities") or {}).get("central") or {})
        rec_p, rec_s = {}, {}
        for dev, dd in central.items():
            if not isinstance(dd, dict): continue
            if dev in STORAGE_DEVS:
                v = dd.get("cap_kWh", 0)
                if v and v > 0: rec_s[dev] = float(v)
            elif dev in POWER_DEVS:
                v = dd.get("cap_kW", 0)
                if v and v > 0: rec_p[dev] = float(v)
        for d in rec_p:
            if d not in devs_p: devs_p.append(d)
        for d in rec_s:
            if d not in devs_s: devs_s.append(d)
        rows.append({"label": _pretty(sub_key),
                     "power": rec_p, "storage": rec_s})

    fig, ax_p = plt.subplots(figsize=(max(11, 1.9 * len(rows) + 2), 6.5))
    ax_s = ax_p.twinx()

    n = len(rows)
    width = 0.36
    x = np.arange(n)
    x_p = x - width / 2 - 0.02
    x_s = x + width / 2 + 0.02

    bottom = np.zeros(n)
    for d in devs_p:
        vals = np.array([r["power"].get(d, 0) for r in rows])
        ax_p.bar(x_p, vals, width, bottom=bottom,
                 color=TECH_COLORS.get(d, "#9E9E9E"),
                 edgecolor="white", linewidth=0.4, label=d)
        bottom += vals
    for i, t in enumerate(bottom):
        if t > 0:
            ax_p.text(x_p[i], t, f"{t:,.1f} kW", ha="center", va="bottom",
                      fontweight="bold", color="#1565C0", fontsize=8)

    bottom = np.zeros(n)
    for d in devs_s:
        vals = np.array([r["storage"].get(d, 0) for r in rows])
        ax_s.bar(x_s, vals, width, bottom=bottom,
                 color=TECH_COLORS.get(d, "#E91E63"),
                 edgecolor="white", linewidth=0.4,
                 label=f"{d} (Speicher)")
        bottom += vals
    for i, t in enumerate(bottom):
        if t > 0:
            ax_s.text(x_s[i], t, f"{t:,.1f} kWh", ha="center", va="bottom",
                      fontweight="bold", color="#AD1457", fontsize=8)

    ax_p.set_xticks(x)
    ax_p.set_xticklabels([r["label"] for r in rows], rotation=15, ha="right")
    ax_p.set_ylabel("Erzeuger-Kapazitaet [kW]", color="#1565C0")
    ax_p.tick_params(axis="y", labelcolor="#1565C0")
    ax_s.set_ylabel("Speicher-Kapazitaet [kWh]", color="#AD1457")
    ax_s.tick_params(axis="y", labelcolor="#AD1457")

    ax_p.set_title(f"Technologie-Mix (Erzeuger | Speicher) – "
                   f"Referenz {reference_key}", fontweight="bold")
    ax_p.grid(axis="y", alpha=0.3)
    ax_p.spines["top"].set_visible(False)
    ax_s.spines["top"].set_visible(False)

    h1, l1 = ax_p.get_legend_handles_labels()
    h2, l2 = ax_s.get_legend_handles_labels()
    leg = ax_p.legend(h1 + h2, l1 + l2, loc="upper right",
                      ncol=2, framealpha=0.85, edgecolor="#CFCFCF",
                      handlelength=1.4, handletextpad=0.5,
                      borderpad=0.4, labelspacing=0.3)
    if leg: leg.get_frame().set_linewidth(0.4)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight"); plt.close()
    print(f"  Saved: {save_path}")


# ═══════════════════════════════════════════════════════════════
# E4 — HUB-BILANZEN (eine PDF-Seite pro Jahr; Cluster untereinander)
# ═══════════════════════════════════════════════════════════════

def _draw_thermal_page(eh, dt, clusters, weights, year, bm_label):
    n = len(clusters)
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.8 * n), squeeze=False,
                              sharex=False)

    # Sammelt eindeutige Handle/Label-Paare ueber alle Cluster
    seen_labels = {}

    def _add(ax, *args, **kw):
        label = kw.pop("label", None)
        h = ax.fill_between(*args, **kw)
        if label and label not in seen_labels:
            seen_labels[label] = h
        return h

    for idx, cl in enumerate(clusters):
        ax = axes[idx][0]
        cl_data = eh[cl] or {}
        sources = _stack_keys(cl_data, "heat", _HEAT_SOURCES)
        n_t = len(next(iter(sources.values()))) if sources else 0
        cl_dt = dt.get(cl) or {}
        tes_dch = np.asarray(cl_data.get("eh_dch_TES", np.zeros(n_t)),
                              dtype=float)
        tes_ch  = np.asarray(cl_data.get("eh_ch_TES",  np.zeros(n_t)),
                              dtype=float)
        if n_t == 0:
            n_t = max(tes_dch.size, tes_ch.size)
        if n_t == 0:
            ax.set_visible(False); continue
        x = np.arange(n_t)

        bottom = np.zeros(n_t)
        for d, v in sources.items():
            _add(ax, x, bottom, bottom + v,
                 color=TECH_COLORS.get(d, "#9E9E9E"),
                 alpha=0.85, linewidth=0, label=d)
            bottom += v
        if tes_dch.size == n_t and np.any(tes_dch > 0):
            _add(ax, x, bottom, bottom + tes_dch,
                 color="#F8BBD0", alpha=0.9, linewidth=0,
                 label="TES discharge")
            bottom += tes_dch

        dem_h = np.asarray(cl_dt.get("total_heat_demand", np.zeros(n_t)),
                            dtype=float)
        dem_w = np.asarray(cl_dt.get("total_dhw_demand",  np.zeros(n_t)),
                            dtype=float)
        top = np.zeros(n_t)
        if np.any(dem_h > 0):
            _add(ax, x, top, top - dem_h,
                 color="#9E9E9E", alpha=0.4, linewidth=0,
                 label="Heating demand")
            top -= dem_h
        if np.any(dem_w > 0):
            _add(ax, x, top, top - dem_w,
                 color="#BDBDBD", alpha=0.5, linewidth=0,
                 label="DHW demand")
            top -= dem_w
        if tes_ch.size == n_t and np.any(tes_ch > 0):
            _add(ax, x, top, top - tes_ch,
                 color="#CE93D8", alpha=0.65, linewidth=0,
                 label="TES charge")
            top -= tes_ch

        ax.axhline(0, color="black", lw=0.5)
        w_factor = int(round(weights.get(cl, 1)))
        ax.set_title(f"Cluster {cl}  (×{w_factor} Wochen)",
                     fontweight="bold", loc="left")
        ax.set_ylabel("Thermal Power (kW)")
        ax.grid(axis="y", alpha=0.3)
        if idx == n - 1:
            ax.set_xlabel("Time (hours)")

    # Eine Legende oben fuer die ganze Figur — vollstaendig
    if seen_labels:
        handles = list(seen_labels.values())
        labels  = list(seen_labels.keys())
        fig.legend(handles, labels, loc="upper center",
                   bbox_to_anchor=(0.5, 0.985),
                   ncol=min(len(labels), 6), fontsize=9,
                   framealpha=0.85, edgecolor="#CFCFCF",
                   handlelength=1.4, handletextpad=0.5,
                   borderpad=0.4, labelspacing=0.3, columnspacing=1.0)

    fig.suptitle(f"Thermal energy hub balance – BM {bm_label} – Jahr {year}",
                 fontweight="bold", y=1.02)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    return fig


def _draw_electrical_page(eh, clusters, weights, year, bm_label):
    EL_GEN = ("PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC", "from_grid")
    EL_INT = ("HP", "GHP", "EB", "CC", "ELYZ")

    n = len(clusters)
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.8 * n), squeeze=False,
                              sharex=False)

    seen_labels = {}

    def _add(ax, *args, **kw):
        label = kw.pop("label", None)
        h = ax.fill_between(*args, **kw)
        if label and label not in seen_labels:
            seen_labels[label] = h
        return h

    for idx, cl in enumerate(clusters):
        ax = axes[idx][0]
        cl_data = eh[cl] or {}

        gen    = _stack_keys(cl_data, "power", EL_GEN)
        intern = _stack_keys(cl_data, "power", EL_INT)
        eh_to_b = np.asarray(cl_data.get("eh_to_buildings", np.zeros(0)),
                              dtype=float)
        to_grid = np.asarray(cl_data.get("power_to_grid", np.zeros(0)),
                              dtype=float)

        ref_arr = (next(iter(gen.values())) if gen
                   else next(iter(intern.values())) if intern
                   else eh_to_b if eh_to_b.size else to_grid)
        n_t = ref_arr.size if hasattr(ref_arr, "size") else 0
        if n_t == 0:
            ax.set_visible(False); continue
        x = np.arange(n_t)

        bottom = np.zeros(n_t)
        for d, v in gen.items():
            _add(ax, x, bottom, bottom + v,
                 color=TECH_COLORS.get(d, "#90A4AE"),
                 alpha=0.85, linewidth=0, label=d)
            bottom += v

        top = np.zeros(n_t)
        for d, v in intern.items():
            _add(ax, x, top, top - v,
                 color=TECH_COLORS.get(d, "#455A64"),
                 alpha=0.7, linewidth=0, label=f"{d} (intern)")
            top -= v
        if eh_to_b.size == n_t and np.any(eh_to_b > 0):
            _add(ax, x, top, top - eh_to_b, color="#37474F",
                 alpha=0.55, linewidth=0, label="EH → Gebaeude")
            top -= eh_to_b
        if to_grid.size == n_t and np.any(to_grid > 0):
            _add(ax, x, top, top - to_grid, color="#FB8C00",
                 alpha=0.7, linewidth=0, label="Export")
            top -= to_grid

        ax.axhline(0, color="black", lw=0.5)
        w_factor = int(round(weights.get(cl, 1)))
        ax.set_title(f"Cluster {cl}  (×{w_factor} Wochen)",
                     fontweight="bold", loc="left")
        ax.set_ylabel("Electrical Power (kW)")
        ax.grid(axis="y", alpha=0.3)
        if idx == n - 1:
            ax.set_xlabel("Time (hours)")

    if seen_labels:
        handles = list(seen_labels.values())
        labels  = list(seen_labels.keys())
        fig.legend(handles, labels, loc="upper center",
                   bbox_to_anchor=(0.5, 0.985),
                   ncol=min(len(labels), 6), fontsize=9,
                   framealpha=0.85, edgecolor="#CFCFCF",
                   handlelength=1.4, handletextpad=0.5,
                   borderpad=0.4, labelspacing=0.3, columnspacing=1.0)

    fig.suptitle(f"Electrical energy hub balance – BM {bm_label} – Jahr {year}",
                 fontweight="bold", y=1.02)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    return fig


def plot_hub_balance_per_cluster(run, save_path_thermal, save_path_electrical,
                                  bm_label) -> None:
    _apply_rc()
    if not run.get("timeseries_path"):
        print(f"  [E4 {bm_label}] timeseries-pkl fehlt"); return

    ts = _load_pkl(run["timeseries_path"])
    eh_all = ts.get("energy_hub") or {}
    dt_all = ts.get("district_totals") or {}
    if not eh_all: return
    weights = (run["summary"].get("metadata") or {}).get("clusterWeights") or {}

    years = sorted(eh_all.keys())
    if not years: return

    # THERMISCH — multipage PDF
    os.makedirs(os.path.dirname(save_path_thermal), exist_ok=True)
    with PdfPages(save_path_thermal) as pdf:
        for y in years:
            eh = eh_all[y] or {}
            dt = (dt_all.get(y) or {})
            clusters = sorted(eh.keys())
            if not clusters: continue
            fig = _draw_thermal_page(eh, dt, clusters, weights, y, bm_label)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    print(f"  Saved: {save_path_thermal}  ({len(years)} Jahre)")

    # ELEKTRISCH — multipage PDF
    os.makedirs(os.path.dirname(save_path_electrical), exist_ok=True)
    with PdfPages(save_path_electrical) as pdf:
        for y in years:
            eh = eh_all[y] or {}
            clusters = sorted(eh.keys())
            if not clusters: continue
            fig = _draw_electrical_page(eh, clusters, weights, y, bm_label)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    print(f"  Saved: {save_path_electrical}  ({len(years)} Jahre)")


# ═══════════════════════════════════════════════════════════════
# E5 — DISTRIKT-BILANZ (multipage PDF: 1 Seite pro Jahr)
# ═══════════════════════════════════════════════════════════════

def _draw_district_page(eh, clusters, weights, year, bm_label):
    n = len(clusters)
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.6 * n), squeeze=False,
                              sharex=False)
    for idx, cl in enumerate(clusters):
        ax = axes[idx][0]
        cl_data = eh[cl] or {}
        el_imp = np.asarray(cl_data.get("P_dem_gcp",
                            cl_data.get("P_dem_total", np.zeros(0))),
                            dtype=float)
        el_exp = np.asarray(cl_data.get("P_inj_gcp",
                            cl_data.get("P_inj_total", np.zeros(0))),
                            dtype=float)
        gas    = np.asarray(cl_data.get("P_gas_total", np.zeros(0)),
                            dtype=float)

        n_t = max(el_imp.size, el_exp.size, gas.size)
        if n_t == 0:
            ax.set_visible(False); continue
        def _pad(a, n):
            if a.size == n: return a
            if a.size == 0: return np.zeros(n)
            return a
        el_imp = _pad(el_imp, n_t); el_exp = _pad(el_exp, n_t); gas = _pad(gas, n_t)
        x = np.arange(n_t)

        ax.fill_between(x, 0, el_imp, color="#1E88E5", alpha=0.75, linewidth=0,
                         label="El. Import" if idx == 0 else None)
        ax.fill_between(x, el_imp, el_imp + gas, color="#90CAF9", alpha=0.75,
                         linewidth=0, label="Gas Import" if idx == 0 else None)
        ax.fill_between(x, 0, -el_exp, color="#FB8C00", alpha=0.75, linewidth=0,
                         label="El. Export" if idx == 0 else None)

        ax.axhline(0, color="black", lw=0.5)
        w_factor = int(round(weights.get(cl, 1)))
        ax.set_title(f"Cluster {cl}  (×{w_factor} Wochen)",
                     fontweight="bold", loc="left")
        ax.set_ylabel("Power (kW)")
        ax.grid(axis="y", alpha=0.3)
        if idx == n - 1:
            ax.set_xlabel("Time (hours)")
        if idx == 0:
            _ax_compact_legend(ax, 3)

    fig.suptitle(f"District balance – BM {bm_label} – Jahr {year}",
                 fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def plot_district_balance_per_cluster(run, save_path, bm_label) -> None:
    _apply_rc()
    if not run.get("timeseries_path"):
        print(f"  [E5 {bm_label}] timeseries-pkl fehlt"); return

    ts = _load_pkl(run["timeseries_path"])
    eh_all = ts.get("energy_hub") or {}
    if not eh_all: return
    weights = (run["summary"].get("metadata") or {}).get("clusterWeights") or {}
    years = sorted(eh_all.keys())
    if not years: return

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with PdfPages(save_path) as pdf:
        for y in years:
            eh = eh_all[y] or {}
            clusters = sorted(eh.keys())
            if not clusters: continue
            fig = _draw_district_page(eh, clusters, weights, y, bm_label)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    print(f"  Saved: {save_path}  ({len(years)} Jahre)")


# ═══════════════════════════════════════════════════════════════
# E6 — NPV-VERGLEICHSTABELLE PRO HAUS (CSV + PNG)
# ═══════════════════════════════════════════════════════════════

def _extract_building_npv_table(run) -> List[Dict[str, Any]]:
    """
    Pro Haus: heat_kWh, npv_ref, npv_strom_wn, npv_wn_at_price,
              p_max_i, economic_at_price, npv_diff = npv_wn_at_price - npv_ref.
    Quelle: bm_breakdown.scenario_<flag>.building_details.
    """
    s = run["summary"]
    bd = (s.get("kpis") or {}).get("bm_breakdown") or {}
    bd_sub = bd.get("bm_breakdown") or {}
    if not bd_sub:
        return []
    flag = run["info"]["scenario_flag"] or bd_sub.get("scenario") or "B"
    scen = bd_sub.get(f"scenario_{flag.lower()}") or bd_sub.get("scenario_b") or {}
    details = scen.get("building_details") or {}

    rows = []
    for bid, det in details.items():
        if not isinstance(det, dict): continue
        npv_ref = det.get("npv_ref")
        npv_at  = det.get("npv_wn_at_price")
        diff = (npv_at - npv_ref) if (npv_ref is not None and npv_at is not None) else None
        rows.append({
            "Gebaeude":        bid,
            "Heat_kWh":        det.get("heat_kWh"),
            "NPV_ref":         npv_ref,
            "NPV_strom_WN":    det.get("npv_strom_wn"),
            "NPV_BM_at_price": npv_at,
            "NPV_BM-NPV_ref":  diff,
            "p_max_i":         det.get("p_max"),
            "wirtschaftlich":  det.get("economic_at_price"),
        })
    # nach Diff sortieren, beste Vorteile zuerst
    rows.sort(key=lambda r: (r["NPV_BM-NPV_ref"] is None,
                              -(r["NPV_BM-NPV_ref"] or 0)))
    return rows


def _format_eur(v, factor, unit):
    if v is None: return "—"
    return f"{v * factor:,.2f} {unit}"


def export_npv_table_per_bm(run, save_path_csv, save_path_png, bm_label) -> None:
    """
    Kompakte NPV-Tabelle pro Haus: Gebaeude | Heat [MWh/a] | NPV_ref |
    NPV_BM | Diff | wirtsch.

    EUR-Einheit automatisch (€ / k€ / Mio €).
    """
    _apply_rc()
    rows = _extract_building_npv_table(run)
    if not rows:
        print(f"  [E6 {bm_label}] keine NPV-Daten"); return

    # ---------- CSV ----------
    cols = ["Gebaeude", "Heat_MWh_a", "NPV_ref_EUR",
            "NPV_BM_EUR", "Diff_BM_minus_Ref_EUR", "wirtschaftlich"]
    os.makedirs(os.path.dirname(save_path_csv), exist_ok=True)
    with open(save_path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            heat_mwh = (r["Heat_kWh"] / 1000.0) if r["Heat_kWh"] is not None else None
            w.writerow([
                r["Gebaeude"],
                f"{heat_mwh:.2f}" if heat_mwh is not None else "",
                f"{r['NPV_ref']:.2f}"         if r["NPV_ref"]         is not None else "",
                f"{r['NPV_BM_at_price']:.2f}" if r["NPV_BM_at_price"] is not None else "",
                f"{r['NPV_BM-NPV_ref']:.2f}"  if r["NPV_BM-NPV_ref"]  is not None else "",
                ("ja" if r["wirtschaftlich"] is True
                 else "nein" if r["wirtschaftlich"] is False else ""),
            ])
    print(f"  Saved: {save_path_csv}")

    # ---------- PNG-Tabelle ----------
    eur_vals = []
    for r in rows:
        for k in ("NPV_ref", "NPV_BM_at_price", "NPV_BM-NPV_ref"):
            if r.get(k) is not None:
                eur_vals.append(r[k])
    factor, unit = _smart_unit_eur(eur_vals)

    table_data = []
    for r in rows:
        heat_mwh = (r["Heat_kWh"] / 1000.0) if r["Heat_kWh"] is not None else None
        table_data.append([
            str(r["Gebaeude"]),
            f"{heat_mwh:,.2f}" if heat_mwh is not None else "—",
            f"{r['NPV_ref']         * factor:,.2f}" if r["NPV_ref"]         is not None else "—",
            f"{r['NPV_BM_at_price'] * factor:,.2f}" if r["NPV_BM_at_price"] is not None else "—",
            f"{r['NPV_BM-NPV_ref']  * factor:,.2f}" if r["NPV_BM-NPV_ref"]  is not None else "—",
            ("✓" if r["wirtschaftlich"] is True
             else "✗" if r["wirtschaftlich"] is False else "—"),
        ])

    headers = [
        "Gebaeude",
        "Heizung [MWh/a]",
        f"NPV_ref [{unit}]",
        f"NPV_BM [{unit}]",
        f"Diff [{unit}]",
        "wirtsch.",
    ]

    n_rows = len(rows)
    fig, ax = plt.subplots(figsize=(10, 0.6 + 0.36 * (n_rows + 1)))
    ax.axis("off")

    tbl = ax.table(cellText=table_data, colLabels=headers,
                    cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.0, 1.35)

    # Header dunkel + weiss
    for j in range(len(headers)):
        c = tbl[0, j]
        c.set_facecolor("#37474F")
        c.set_text_props(color="white", fontweight="bold")

    # Diff-Spalte einfaerben (Spalte 4) + wirtsch. Spalte (5)
    for i, r in enumerate(rows):
        d = r["NPV_BM-NPV_ref"]
        c_diff = tbl[i + 1, 4]
        c_econ = tbl[i + 1, 5]
        if d is None:
            c_diff.set_facecolor("#EEEEEE")
        elif d >= 0:
            c_diff.set_facecolor("#C8E6C9")
        else:
            c_diff.set_facecolor("#FFCDD2")
        if r["wirtschaftlich"] is True:
            c_econ.set_facecolor("#C8E6C9")
        elif r["wirtschaftlich"] is False:
            c_econ.set_facecolor("#FFCDD2")

    # Zebra fuer die anderen Spalten
    for i in range(n_rows):
        if i % 2 == 1:
            for j in (0, 1, 2, 3):
                tbl[i + 1, j].set_facecolor("#F5F5F5")

    fig.suptitle(f"NPV-Vergleich pro Haus – BM {bm_label}",
                 fontweight="bold")
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path_png), exist_ok=True)
    plt.savefig(save_path_png, dpi=200, bbox_inches="tight"); plt.close()
    print(f"  Saved: {save_path_png}")



# ═══════════════════════════════════════════════════════════════
# E1b — AGGREGIERTE KOSTEN (fokussierter oekonomischer Block)
# ═══════════════════════════════════════════════════════════════

_COST_AGG_ORDER = [
    "Zentrale Erzeugungsanlagen",
    "Waermenetz",
    "Stromnetz",
    "Trafo",
    "Energiekosten",
    "Dezentrale PV",
    "Dezentrale Ref-Anlagen",
    "Dezentral BM (pruefen)",
]

_COST_AGG_COLORS = {
    "Zentrale Erzeugungsanlagen": "#4C78A8",
    "Waermenetz":                 "#9C755F",
    "Stromnetz":                  "#B279A2",
    "Trafo":                      "#D37295",
    "Energiekosten":              "#F58518",
    "Dezentrale PV":              "#E5C100",
    "Dezentrale Ref-Anlagen":     "#72B7B2",
    "Dezentral BM (pruefen)":     "#E45756",
}


def _is_reference_run(run: Dict[str, Any]) -> bool:
    return (run.get("info") or {}).get("kind") == "reference"


def _pretty_run_label(run_key: str, run: Dict[str, Any]) -> str:
    info = run.get("info") or {}
    if info.get("kind") == "reference":
        ref = info.get("reference_key") or run_key
        return "Referenz BOI" if ref == "ref_boi" else "Referenz WP" if ref == "ref_wp" else ref
    return _pretty(run_key)


def _annual_cost_from_device_info(info: Any) -> float:
    if not isinstance(info, dict):
        return 0.0
    for key in ("subsidized_annual_cost", "annual_cost", "annualized_cost"):
        v = info.get(key)
        if v is not None:
            return float(v or 0.0)
    return 0.0


def _aggregate_cost_row(run_key: str, run: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregiert Kosten in wenige, interpretierbare Kategorien.

    Dezentral-Logik:
    - PV wird immer separat als "Dezentrale PV" gezeigt.
    - Nicht-PV-Dezentrale Anlagen in der Referenz werden als
      "Dezentrale Ref-Anlagen" gezeigt.
    - Nicht-PV-Dezentrale Anlagen in Business Models werden nicht stillschweigend
      einsortiert, sondern als "Dezentral BM (pruefen)" markiert.
    """
    s = run["summary"]
    bm = (run.get("info") or {}).get("business_model")
    is_ref = _is_reference_run(run)
    bd = _kbm(s)
    dev_costs = s.get("device_costs") or {}
    cen_per_dev = dev_costs.get("central") or {}
    dec_per_bldg = dev_costs.get("decentral") or {}

    row = {"label": _pretty_run_label(run_key, run), "run_key": run_key}
    for cat in _COST_AGG_ORDER:
        row[cat] = 0.0

    # Zentrale Anlagen; Heat_Grid separat als Waermenetz behandeln.
    heat_grid_from_device_costs = 0.0
    for dev, info in cen_per_dev.items():
        v = _annual_cost_from_device_info(info)
        if v <= 0:
            continue
        if dev == "Heat_Grid":
            heat_grid_from_device_costs += v
        else:
            row["Zentrale Erzeugungsanlagen"] += v

    # Waermenetz aus expliziter heat_grid-Struktur; falls dort nichts steht,
    # ersatzweise Heat_Grid aus device_costs verwenden.
    hg = _heat_grid_cost_annual(s)
    row["Waermenetz"] = hg if hg > 0 else heat_grid_from_device_costs

    # Energiekosten: annualisierter/Jahresmittel-Wert aus yearly operationCosts.
    row["Energiekosten"] = _yearly_mean(s, "operationCosts")

    # Geschaeftsmodell-spezifische Stromnetz-/Trafo-/PV-Kosten.
    row["Stromnetz"] = float(bd.get("c_elgrid_ann") or 0.0)
    row["Trafo"] = float(bd.get("trafo_ann_from_milp") or 0.0)
    pv_breakdown = float(bd.get("pv_cost_ann_total") or 0.0)

    # Dezentrale Geraetekosten.
    pv_from_devices = 0.0
    for _bidx, bldg_devs in dec_per_bldg.items():
        if not isinstance(bldg_devs, dict):
            continue
        for dev, info in bldg_devs.items():
            v = _annual_cost_from_device_info(info)
            if v <= 0:
                continue
            if dev == "PV":
                pv_from_devices += v
            elif is_ref:
                row["Dezentrale Ref-Anlagen"] += v
            else:
                row["Dezentral BM (pruefen)"] += v

    # PV kann je nach Summary-Version in device_costs.decentral oder im
    # bm_breakdown stehen. Wir nehmen den groesseren Wert, um Doppelzaehlung
    # zu vermeiden und trotzdem vorhandene PV-Kosten sichtbar zu machen.
    row["Dezentrale PV"] = max(pv_from_devices, pv_breakdown)

    row["TOTAL"] = sum(float(row[c]) for c in _COST_AGG_ORDER)
    row["pv_from_device_costs"] = pv_from_devices
    row["pv_from_bm_breakdown"] = pv_breakdown
    row["bm"] = bm
    row["kind"] = "reference" if is_ref else "bm"
    return row


def plot_cost_breakdown_aggregated(grouped, save_path_pdf: str,
                                   save_path_csv: str,
                                   reference_key: str) -> None:
    """
    Aggregierte annualisierte Kosten fuer Referenz + BMs.

    Ziel: wenige Kategorien, keine Geraete-Legende, klare Kennzeichnung, falls
    in einem Business Model unerwartet dezentrale Nicht-PV-Anlagen auftauchen.
    """
    _apply_rc()
    group = grouped.get(reference_key) or {}
    rows = []

    ref_run = group.get("reference")
    if ref_run is not None:
        rows.append(_aggregate_cost_row(reference_key, ref_run))

    for sub_key, run in (group.get("bms") or {}).items():
        rows.append(_aggregate_cost_row(sub_key, run))

    if not rows:
        print(f"  [E1b {reference_key}] keine Kostendaten")
        return

    totals = [r["TOTAL"] for r in rows]
    factor, unit = _smart_unit_eur(totals)

    # CSV zuerst: damit fehlende/unerwartete Kategorien numerisch pruefbar sind.
    os.makedirs(os.path.dirname(save_path_csv), exist_ok=True)
    with open(save_path_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["label", "run_key", "kind"] + _COST_AGG_ORDER + [
            "TOTAL", "pv_from_device_costs", "pv_from_bm_breakdown"
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  Saved: {save_path_csv}")

    # Plot: horizontal, weil BM-Namen dadurch lesbar bleiben.
    labels = [r["label"] for r in rows]
    y = np.arange(len(rows))
    fig_h = max(4.8, 0.58 * len(rows) + 1.8)
    fig, ax = plt.subplots(figsize=(11.0, fig_h))

    left = np.zeros(len(rows))
    for cat in _COST_AGG_ORDER:
        vals_raw = np.array([float(r[cat]) for r in rows])
        if not np.any(np.abs(vals_raw) > 1e-9):
            continue
        vals = vals_raw * factor
        ax.barh(y, vals, left=left, label=cat,
                color=_COST_AGG_COLORS.get(cat, "#9E9E9E"),
                edgecolor="white", linewidth=0.5)
        left += vals

    # Totals am Balkenende
    max_total = max(abs(v) for v in left) if len(left) else 1.0
    pad = 0.018 * max_total
    for i, total_scaled in enumerate(left):
        ax.text(total_scaled + pad, i, f"{total_scaled:,.2f} {unit}/a",
                va="center", ha="left", fontsize=9, fontweight="bold")

    # Warnhinweis direkt an der Zeile, wenn BM dezentrale Nicht-PV-Anlagen hat.
    for i, r in enumerate(rows):
        if r["Dezentral BM (pruefen)"] > 1e-6:
            ax.text(left[i] + pad, i - 0.25, "Dezentral im BM pruefen",
                    va="center", ha="left", fontsize=8, color="#B71C1C")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel(f"Annualisierte Kosten [{unit}/a]")
    ax.set_title(f"Aggregierte Kostenaufschluesselung - {reference_key}",
                 fontsize=12, fontweight="bold")
    ax.grid(axis="x", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=True,
              framealpha=0.9, edgecolor="#D0D0D0", fontsize=9)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path_pdf), exist_ok=True)
    plt.savefig(save_path_pdf, dpi=220, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path_pdf}")


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def run_extra_plots(grouped, base_save_dir) -> None:
    """
    Fokussierter Extra-Plot-Lauf fuer den aktuellen Arbeitsstand:
    - aggregierte Kostenaufschluesselung
    - NPV-Tabelle pro Gebaeude und BM

    Andere Extra-Plots bleiben im Modul erhalten, werden hier aber bewusst
    nicht automatisch erzeugt.
    """
    for ref_key, group in grouped.items():
        bms = group.get("bms") or {}
        if not bms:
            continue

        ref_dir = os.path.join(base_save_dir, ref_key, "extra")
        os.makedirs(ref_dir, exist_ok=True)

        plot_cost_breakdown_aggregated(
            grouped,
            os.path.join(ref_dir, "E1_cost_breakdown_aggregated.pdf"),
            os.path.join(ref_dir, "E1_cost_breakdown_aggregated.csv"),
            ref_key,
        )

        npv_dir = os.path.join(ref_dir, "npv_per_building")
        os.makedirs(npv_dir, exist_ok=True)

        for sub_key, run in bms.items():
            tag = sub_key.replace("__", "_")
            label = _pretty(sub_key)
            export_npv_table_per_bm(
                run,
                os.path.join(npv_dir, f"E6_npv_table_{tag}.csv"),
                os.path.join(npv_dir, f"E6_npv_table_{tag}.pdf"),
                label,
            )