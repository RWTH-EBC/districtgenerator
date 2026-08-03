# -*- coding: utf-8 -*-
"""
plots_central.py

Vier zentrale BM-Vergleichsplots aus den summary_*.pkl:

  C1  Technologie-Mix der zentralen EH je BM mit n_connected/n_total
      fuer Szenario A und B (Annotation am Balken).
  C2  NPV-Vergleich Quartier - Szenario B (NPV_BM vs NPV_ref + Differenz),
      sortiert nach BM (nicht nach Differenz).
  C3  NPV pro Haus - Szenario A, sortiert nach Haus-ID. Ausgeschlossene
      Haeuser bleiben sichtbar (grau, "nicht im Netz"). Ein Plot pro BM.
  C4  Aggregierte Kostenzusammensetzung pro BM/Referenz, klar getrennt nach
      Faktoren: Waermenetz, Stromnetz (Kabel), Trafo, Zentrale EH-Erzeuger,
      Energiekosten, Dezentrale PV (nur wenn Betreiber-Eigentum:
      GGV/Kundenanlage und nur fuer angeschlossene Haeuser).

Datenquellen ausschliesslich aus summary.pkl (keine Neuberechnung):
  - capacities.central / capacities.decentral
  - kpis.bm_breakdown.bm_breakdown.scenario_a / scenario_b
      .connected, .excluded, .building_details
  - kpis.bm_breakdown.bm_breakdown.{c_elgrid_ann, trafo_ann_from_milp,
                                    pv_cost_ann_total}
  - device_costs.central / device_costs.decentral
  - heat_grid.cost.{annualized_capex_eur, annual_om_eur}
  - kpis.yearly.operationCosts
"""

import os
import csv
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.backends.backend_pdf import PdfPages


# =====================================================================
# Konstanten
# =====================================================================

_STORAGE_DEVS = ("TES", "CTES", "BAT", "H2S", "GS")
_AREA_DEVS    = ("PV", "STC")

# BMs, in denen dezentrale PV im Eigentum des Betreibers liegt
_PV_OPERATOR_BMS = {"waermecontracting_ggv", "waermecontracting_kundenanlage"}

# Reihenfolge fuer Kostenstapel (Plot C4)
_COST_ORDER = [
    "Zentral: Waermeerzeuger",
    "Zentral: Stromerzeuger",
    "Zentral: Speicher",
    "Waermenetz",
    "Stromnetz: Kabel",
    "Stromnetz: Trafo",
    "Energiekosten",
    "Dezentrale PV (Betreiber)",
]

_COST_COLORS = {
    "Zentral: Waermeerzeuger":   "#C62828",  # rot - Waerme
    "Zentral: Stromerzeuger":    "#1565C0",  # blau - Strom
    "Zentral: Speicher":         "#6A1B9A",  # lila - Speicher
    "Waermenetz":                "#8E24AA",  # magenta
    "Stromnetz: Kabel":          "#EC407A",  # pink
    "Stromnetz: Trafo":          "#AD1457",  # dunkelpink
    "Energiekosten":             "#FFA726",  # orange
    "Dezentrale PV (Betreiber)": "#FDD835",  # gelb
}

# Geraete-Klassifizierung
_HEAT_GEN_DEVS  = ("BOI", "BBOI", "WBOI", "HP", "GHP", "EB",
                   "CHP", "BCHP", "WCHP", "FC", "STC")
_POWER_GEN_DEVS = ("PV", "WT", "WAT", "ELYZ")
# _STORAGE_DEVS bereits oben definiert

# Tech-Farben fuer C1
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
    "BAT":  "#5E35B2", "H2S":  "#9575CD", "GS":   "#7E57C2",
}

BM_PRETTY = {
    "waermecontracting":              "Contracting",
    "waermecontracting_ggv":          "GGV",
    "waermecontracting_kundenanlage": "Kundenanlage",
    "waermegenossenschaft":           "Genossenschaft",
}


# =====================================================================
# Helpers
# =====================================================================

def _kstatic(s):  return (s.get("kpis") or {}).get("static") or {}
def _kyearly(s):  return (s.get("kpis") or {}).get("yearly") or {}

def _kbm(s):
    bd = (s.get("kpis") or {}).get("bm_breakdown") or {}
    return bd.get("bm_breakdown") or {}

def _capacities(s): return s.get("capacities") or {}

def _heat_grid_cost_annual(s) -> float:
    cost = (s.get("heat_grid") or {}).get("cost") or {}
    return float((cost.get("annualized_capex_eur") or 0)
                 + (cost.get("annual_om_eur") or 0))

def _yearly_mean(s, key: str) -> float:
    d = _kyearly(s).get(key) or {}
    vals = []
    for v in d.values():
        if isinstance(v, dict):
            v = v.get("total_co2", 0)
        if v is not None:
            vals.append(float(v))
    return float(np.mean(vals)) if vals else 0.0

def _smart_unit_eur(values) -> Tuple[float, str]:
    m = max(abs(v) for v in values if v is not None) if values else 0.0
    if m >= 1_000_000: return 1e-6, "Mio. EUR"
    if m >= 10_000:    return 1e-3, "kEUR"
    return 1.0, "EUR"

def _bm_label(sub_key: str) -> str:
    if "__" in sub_key:
        bm, flag = sub_key.split("__", 1)
    else:
        bm, flag = sub_key, ""
    pretty = BM_PRETTY.get(bm, bm.replace("_", " ").title())
    return f"{pretty} ({flag})" if flag else pretty


def _scenario_dict(run: Dict[str, Any], flag: str) -> Dict[str, Any]:
    """scenario_a oder scenario_b aus bm_breakdown."""
    s = run["summary"]
    bd = _kbm(s)
    return bd.get(f"scenario_{flag.lower()}") or {}


def _connected_count(run: Dict[str, Any], flag: str) -> Tuple[int, int]:
    """
    Liefert (n_connected, n_total) fuer das gegebene Szenario.
    Faellt zurueck auf building_details, falls connected/excluded fehlen.
    """
    sc = _scenario_dict(run, flag)
    connected = sc.get("connected") or sc.get("connected_buildings") or []
    excluded  = sc.get("excluded") or []
    if connected or excluded:
        return len(connected), len(connected) + len(excluded)
    # Fallback: building_details
    bd = sc.get("building_details") or {}
    return len(bd), len(bd)


def _is_pv_operator(bm_name: str) -> bool:
    return bm_name in _PV_OPERATOR_BMS


# =====================================================================
# C1 - TECHNOLOGIE-MIX MIT HAEUSERZAHLEN
# =====================================================================

def plot_central_tech_mix_with_houses(grouped: Dict[str, Dict[str, Any]],
                                       save_path: str,
                                       reference_key: str) -> None:
    """
    Stacked-Bar pro BM-Run (BM x Szenario). Zeigt zentrale Erzeuger-/
    Speicherkapazitaeten. Annotation 'A: c/t' bzw. 'B: c/t' am Balken.
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    # Daten je Run einsammeln
    rows = []
    all_devs: List[str] = []
    for sub_key, run in bms.items():
        s = run["summary"]
        flag = run["info"]["scenario_flag"] or ""
        central = _capacities(s).get("central") or {}
        caps: Dict[str, float] = {}
        for dev, dev_data in central.items():
            if not isinstance(dev_data, dict):
                continue
            if dev in _STORAGE_DEVS:
                v = dev_data.get("cap_kWh", 0)
            elif dev in _AREA_DEVS:
                v = dev_data.get("cap_m2", 0)
            else:
                v = dev_data.get("cap_kW", 0)
            if v and v > 0:
                caps[dev] = float(v)
                if dev not in all_devs:
                    all_devs.append(dev)

        n_c, n_t = _connected_count(run, flag) if flag else (0, 0)
        rows.append({
            "label":   _bm_label(sub_key),
            "bm":      run["info"]["business_model"],
            "flag":    flag,
            "caps":    caps,
            "n_c":     n_c,
            "n_t":     n_t,
        })

    if not rows or not all_devs:
        print(f"  [C1 {reference_key}] keine zentralen Kapazitaeten")
        return

    # sortieren: zuerst nach BM, dann A vor B
    rows.sort(key=lambda r: (r["bm"], r["flag"]))

    labels = [r["label"] for r in rows]
    x = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(max(9, 1.4 * len(rows)), 6.2))
    bottom = np.zeros(len(rows))
    for dev in all_devs:
        vals = np.array([r["caps"].get(dev, 0.0) for r in rows])
        if not np.any(vals > 0):
            continue
        ax.bar(x, vals, 0.62, bottom=bottom, label=dev,
               color=TECH_COLORS.get(dev, "#9E9E9E"),
               edgecolor="white", linewidth=0.5)
        bottom += vals

    # Annotation: Anzahl angeschlossener Haeuser
    pad = 0.025 * (max(bottom) if len(bottom) else 1.0)
    for i, r in enumerate(rows):
        if r["n_t"] > 0:
            txt = f"{r['flag']}: {r['n_c']}/{r['n_t']}"
        else:
            txt = ""
        if txt:
            ax.text(i, bottom[i] + pad, txt, ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color="#263238")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right", fontsize=10)
    ax.set_ylabel("Kapazitaet  [kW / kWh / m²]")
    ax.set_title(f"Zentraler Energiehub - Technologiemix mit angeschlossenen "
                 f"Haeusern ({reference_key})",
                 fontsize=12, fontweight="bold")
    ax.set_ylim(0, max(bottom) * 1.18 if max(bottom) > 0 else 1)
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(title="Geraete", fontsize=9, ncol=min(4, len(all_devs)),
              loc="upper left", bbox_to_anchor=(0.0, -0.18),
              frameon=True, framealpha=0.9, edgecolor="#D0D0D0")

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=220, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# =====================================================================
# C2 - NPV QUARTIER (SZENARIO B)
# =====================================================================

def _npv_aggregate_b(run: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Liefert NPV_BM, NPV_ref und Differenz fuer Szenario B.

    Reihenfolge der Quellen:
      1) building_details (Kundenanlage, Genossenschaft) - aufsummieren
      2) sum_npv_wn_at_price / sum_npv_ref (Contracting, GGV) - direkt
    """
    sc = _scenario_dict(run, "B")

    details = sc.get("building_details") or {}
    npv_bm = 0.0
    npv_ref = 0.0
    n = 0
    for det in details.values():
        if not isinstance(det, dict):
            continue
        a = det.get("npv_wn_at_price")
        r = det.get("npv_ref")
        if a is None or r is None:
            continue
        npv_bm  += float(a)
        npv_ref += float(r)
        n += 1
    if n > 0:
        return {"npv_bm": npv_bm, "npv_ref": npv_ref, "diff": npv_bm - npv_ref}

    # Fallback: aggregierte Summen aus dem BM (Contracting / GGV)
    a = sc.get("sum_npv_wn_at_price")
    r = sc.get("sum_npv_ref")
    if a is None or r is None:
        return {"npv_bm": None, "npv_ref": None, "diff": None}
    return {"npv_bm": float(a), "npv_ref": float(r),
            "diff": float(a) - float(r)}


def plot_npv_quartier_B(grouped: Dict[str, Dict[str, Any]],
                         save_path: str,
                         reference_key: str) -> None:
    """
    Gruppierte Balken pro BM (Szenario B): NPV_BM vs NPV_ref +
    Differenz als drittes Balkenpaar; sortiert nach BM-Name (alphabetisch).
    """
    bms = grouped[reference_key]["bms"]
    rows = []
    for sub_key, run in bms.items():
        if run["info"].get("scenario_flag") != "B":
            continue
        agg = _npv_aggregate_b(run)
        rows.append({
            "label":  _bm_label(sub_key),
            "bm":     run["info"]["business_model"],
            "npv_bm": agg["npv_bm"],
            "npv_ref":agg["npv_ref"],
            "diff":   agg["diff"],
        })
    if not rows:
        print(f"  [C2 {reference_key}] keine Szenario-B-Runs")
        return

    rows.sort(key=lambda r: r["bm"])

    all_vals = [v for r in rows for v in (r["npv_bm"], r["npv_ref"], r["diff"])
                if v is not None]
    if not all_vals:
        print(f"  [C2 {reference_key}] keine NPV-Daten in building_details")
        return
    factor, unit = _smart_unit_eur(all_vals)

    labels = [r["label"] for r in rows]
    x = np.arange(len(rows))
    w = 0.27

    fig, ax = plt.subplots(figsize=(max(9, 1.6 * len(rows)), 6.2))
    bm_vals  = [(r["npv_bm"]  or 0) * factor for r in rows]
    ref_vals = [(r["npv_ref"] or 0) * factor for r in rows]
    diff_vals = [(r["diff"]    or 0) * factor for r in rows]

    ax.bar(x - w, bm_vals,  w, color="#1565C0", label=r"$NPV_{BM}$",
           edgecolor="white", linewidth=0.4)
    ax.bar(x,     ref_vals, w, color="#607D8B", label=r"$NPV_{ref}$",
           edgecolor="white", linewidth=0.4)
    diff_colors = ["#2E7D32" if (r["diff"] or 0) >= 0 else "#C62828"
                   for r in rows]
    ax.bar(x + w, diff_vals, w, color=diff_colors,
           label=r"$\Delta = NPV_{BM} - NPV_{ref}$",
           edgecolor="white", linewidth=0.4)

    # Werte beschriften (nur Differenz)
    all_plot_vals = bm_vals + ref_vals + diff_vals
    max_abs = max(abs(v) for v in all_plot_vals) or 1.0
    pad = 0.025 * max_abs
    for i, v in enumerate(diff_vals):
        ax.text(x[i] + w, v + (pad if v >= 0 else -pad),
                f"{v:+,.2f} {unit}",
                ha="center", va="bottom" if v >= 0 else "top",
                fontsize=9, fontweight="bold",
                color=diff_colors[i])

    # Y-Limits mit Headroom fuer Labels
    ymin = min(0.0, min(all_plot_vals)) - pad * 4
    ymax = max(all_plot_vals) + pad * 4
    ax.set_ylim(ymin, ymax)

    ax.axhline(0, color="black", lw=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=10)
    ax.set_ylabel(f"NPV  [{unit}]")
    ax.set_title(f"NPV-Vergleich Quartier - Szenario B (Anschlusszwang) - "
                 f"{reference_key}", fontsize=12, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.16),
              ncol=3, frameon=True, framealpha=0.9, edgecolor="#D0D0D0",
              fontsize=10)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=220, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# =====================================================================
# C3 - NPV PRO HAUS (SZENARIO A), SORTIERT NACH HAUS-ID
# =====================================================================

def _natural_id_key(bid: Any):
    """Sortiert Haus-IDs natuerlich (Building_2 vor Building_10)."""
    s = str(bid)
    parts: List = []
    cur = ""
    for c in s:
        if c.isdigit():
            cur += c
        else:
            if cur:
                parts.append(int(cur)); cur = ""
            parts.append(c.lower())
    if cur:
        parts.append(int(cur))
    return parts


def plot_npv_per_house_A(run: Dict[str, Any],
                          save_path: str,
                          bm_label: str) -> None:
    """
    Pro Haus: NPV_BM - NPV_ref (Diff) im Szenario A.
    Reihenfolge: Haus-ID (natuerliche Sortierung).
    Ausgeschlossene Haeuser bleiben in der Liste (grau, "nicht im Netz").
    """
    sc = _scenario_dict(run, "A")
    details = sc.get("building_details") or {}
    excluded = set(sc.get("excluded") or [])
    if not details:
        print(f"  [C3 {bm_label}] keine building_details fuer Szenario A")
        return

    items = []
    for bid, det in details.items():
        if not isinstance(det, dict):
            continue
        npv_at  = det.get("npv_wn_at_price")
        npv_ref = det.get("npv_ref")
        diff = (npv_at - npv_ref) if (npv_at is not None and npv_ref is not None) else None
        is_excluded = bid in excluded or det.get("economic_at_price") is False \
                      and det.get("connected", True) is False
        # Eindeutiger Marker: explizit aus excluded-Liste
        items.append({
            "bid":      bid,
            "diff":     diff,
            "excluded": bid in excluded,
        })
    items.sort(key=lambda r: _natural_id_key(r["bid"]))

    diffs_for_unit = [r["diff"] for r in items if r["diff"] is not None]
    factor, unit = _smart_unit_eur(diffs_for_unit if diffs_for_unit else [0.0])

    fig_h = max(4.6, 0.36 * len(items) + 1.6)
    fig, ax = plt.subplots(figsize=(10.5, fig_h))
    y = np.arange(len(items))

    vals = []
    colors = []
    for r in items:
        if r["excluded"] or r["diff"] is None:
            vals.append(0.0)
            colors.append("#BDBDBD")
        else:
            v = r["diff"] * factor
            vals.append(v)
            colors.append("#2E7D32" if v >= 0 else "#C62828")

    ax.barh(y, vals, color=colors, edgecolor="white", linewidth=0.4,
            alpha=0.88)

    max_abs = max([abs(v) for v in vals] + [1.0])
    pad = 0.018 * max_abs
    for i, r in enumerate(items):
        if r["excluded"]:
            ax.text(pad, i, "nicht Teil des Netzes", va="center", ha="left",
                    fontsize=9, color="#616161", style="italic")
        elif r["diff"] is None:
            ax.text(pad, i, "keine Daten", va="center", ha="left",
                    fontsize=9, color="#9E9E9E", style="italic")
        else:
            v = vals[i]
            ha = "left" if v >= 0 else "right"
            xt = v + pad if v >= 0 else v - pad
            ax.text(xt, i, f"{v:+,.2f} {unit}", va="center", ha=ha,
                    fontsize=9)

    ax.axvline(0, color="black", lw=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels([str(r["bid"]) for r in items], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel(f"NPV_BM − NPV_ref pro Haus  [{unit}]")
    ax.set_title(f"NPV-Vorteil pro Haus - Szenario A - {bm_label}",
                 fontsize=12, fontweight="bold")
    lim = max_abs * 1.22
    ax.set_xlim(-lim, lim)
    ax.grid(axis="x", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    legend_items = [
        Patch(facecolor="#2E7D32", label="Vorteil im BM"),
        Patch(facecolor="#C62828", label="Nachteil im BM"),
        Patch(facecolor="#BDBDBD", label="nicht Teil des Netzes"),
    ]
    ax.legend(handles=legend_items, loc="upper right", fontsize=9,
              framealpha=0.9, edgecolor="#D0D0D0")

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=220, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# =====================================================================
# C4 - AGGREGIERTE KOSTENZUSAMMENSETZUNG
# =====================================================================

def _aggregate_costs(run_key: str, run: Dict[str, Any]) -> Dict[str, Any]:
    s = run["summary"]
    info = run.get("info") or {}
    bm   = info.get("business_model")
    flag = info.get("scenario_flag") or ""
    is_ref = info.get("kind") == "reference"
    bd = _kbm(s)

    dev_costs = s.get("device_costs") or {}
    cen = dev_costs.get("central") or {}

    row = {c: 0.0 for c in _COST_ORDER}

    # Zentrale Geraete: nach Klasse aufteilen.
    heat_grid_from_dev = 0.0
    trafo_from_dev = 0.0
    for dev, info_d in cen.items():
        if not isinstance(info_d, dict):
            continue
        v = float(info_d.get("subsidized_annual_cost") or 0.0)
        if v <= 0:
            continue
        if dev == "Heat_Grid":
            heat_grid_from_dev += v
        elif dev in ("Trafo", "TRAFO"):
            trafo_from_dev += v
        elif dev in _STORAGE_DEVS:
            row["Zentral: Speicher"] += v
        elif dev in _POWER_GEN_DEVS:
            row["Zentral: Stromerzeuger"] += v
        elif dev in _HEAT_GEN_DEVS:
            row["Zentral: Waermeerzeuger"] += v
        else:
            # unbekannt -> bei Waermeerzeugern verbuchen, mit Hinweis
            row["Zentral: Waermeerzeuger"] += v

    # Waermenetz: bevorzugt heat_grid.cost, sonst Heat_Grid aus device_costs
    hg = _heat_grid_cost_annual(s)
    row["Waermenetz"] = hg if hg > 0 else heat_grid_from_dev

    # Stromnetz Kabel + Trafo
    # Kabel kommt nur aus bm_breakdown (Postprocessing in Kundenanlage).
    # Trafo: bevorzugt aus bm_breakdown (trafo_ann_from_milp); falls dort 0,
    # aus device_costs (zentrales Trafo-Device) uebernehmen.
    row["Stromnetz: Kabel"] = float(bd.get("c_elgrid_ann") or 0.0)
    trafo_bd = float(bd.get("trafo_ann_from_milp") or 0.0)
    row["Stromnetz: Trafo"] = trafo_bd if trafo_bd > 0 else trafo_from_dev

    # Energiekosten (Mittel ueber Jahre)
    row["Energiekosten"] = _yearly_mean(s, "operationCosts")

    # Dezentrale PV - nur fuer GGV/Kundenanlage und nur fuer Runs mit
    # angeschlossenen Haeusern. Die BMs filtern pv_cost_ann_total bereits
    # auf connected (siehe WaermecontractingGGV.py / Kundenanlage.py).
    if (not is_ref) and _is_pv_operator(bm) and flag:
        pv_breakdown = float(bd.get("pv_cost_ann_total") or 0.0)
        row["Dezentrale PV (Betreiber)"] = pv_breakdown

    # Label
    if is_ref:
        ref_pretty = {"ref_boi": "Referenz BOI", "ref_wp": "Referenz WP"}
        label = ref_pretty.get(info.get("reference_key"), info.get("reference_key"))
    else:
        label = _bm_label(run_key)

    row["label"] = label
    row["bm"]    = bm
    row["kind"]  = "reference" if is_ref else "bm"
    row["TOTAL"] = sum(row[c] for c in _COST_ORDER)

    # Anzahl angeschlossener Haeuser fuer die "pro Anschluss"-Spalte.
    # Referenz -> alle Haeuser (= n_total). BM -> aus aktivem Szenario.
    n_conn = 0
    if is_ref:
        # Total aus irgendeinem BM-Run schaetzbar; fuer Ref nehmen wir
        # die Gesamtzahl der dezentralen Gebaeude aus capacities.
        dec = _capacities(s).get("decentral") or {}
        if isinstance(dec, dict):
            n_conn = len(dec)
    else:
        n_c, _n_t = _connected_count(run, flag) if flag else (0, 0)
        n_conn = n_c
    row["n_connected"] = int(n_conn)
    row["TOTAL_per_house"] = (row["TOTAL"] / n_conn) if n_conn > 0 else None
    return row


def plot_cost_breakdown_central(grouped: Dict[str, Dict[str, Any]],
                                 save_path: str,
                                 reference_key: str) -> None:
    """
    Stacked horizontal bar: Referenz + alle BMs.
    Kategorien: Zentrale EH-Erzeuger, Waermenetz, Stromnetz (Kabel),
                Trafo, Energiekosten, Dezentrale PV (nur Betreiber-BMs).
    """
    group = grouped.get(reference_key) or {}
    rows: List[Dict[str, Any]] = []

    if group.get("reference"):
        rows.append(_aggregate_costs(reference_key, group["reference"]))
    for sub_key, run in (group.get("bms") or {}).items():
        rows.append(_aggregate_costs(sub_key, run))

    # sortieren: Referenz zuerst, dann nach BM-Name + Szenario
    rows.sort(key=lambda r: (0 if r["kind"] == "reference" else 1,
                              r.get("bm") or "", r["label"]))

    if not rows:
        print(f"  [C4 {reference_key}] keine Kostendaten")
        return

    totals = [r["TOTAL"] for r in rows]
    factor, unit = _smart_unit_eur(totals)

    labels = [r["label"] for r in rows]
    y = np.arange(len(rows))

    fig_h = max(4.8, 0.6 * len(rows) + 1.8)
    fig, ax = plt.subplots(figsize=(11.5, fig_h))

    left = np.zeros(len(rows))
    for cat in _COST_ORDER:
        vals_raw = np.array([float(r[cat]) for r in rows])
        if not np.any(np.abs(vals_raw) > 1e-9):
            continue
        vals = vals_raw * factor
        ax.barh(y, vals, left=left, label=cat,
                color=_COST_COLORS[cat], edgecolor="white", linewidth=0.5)
        left += vals

    # Totals + pro angeschlossenem Haus
    max_total = max(left) if len(left) else 1.0
    pad = 0.018 * max_total
    for i, total in enumerate(left):
        n = rows[i].get("n_connected", 0)
        per_h = rows[i].get("TOTAL_per_house")
        if per_h is not None and n > 0:
            # pro-Haus in passender Skala formatieren
            ph_val = per_h * factor
            txt = (f"{total:,.2f} {unit}/a   |   "
                   f"{ph_val:,.2f} {unit}/(a*Haus)  (n={n})")
        else:
            txt = f"{total:,.2f} {unit}/a"
        ax.text(total + pad, i, txt,
                va="center", ha="left", fontsize=9, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel(f"Annualisierte Kosten  [{unit}/a]")
    ax.set_title(f"Kostenzusammensetzung nach Faktoren - {reference_key}",
                 fontsize=12, fontweight="bold")
    ax.grid(axis="x", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, max_total * 1.85 if max_total > 0 else 1)

    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=True,
              framealpha=0.9, edgecolor="#D0D0D0", fontsize=9,
              title="Faktoren")

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=220, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# =====================================================================
# C5 - TECH-MIX AUFGETEILT NACH ERZEUGER / SPEICHER (Multi-Page-PDF)
# =====================================================================

def _collect_capacities_split(grouped, reference_key):
    """
    Liefert pro Run die zentralen Kapazitaeten getrennt in:
      - Erzeuger (kW: Waerme + Strom; m2 fuer PV/STC)
      - Speicher (kWh)
    """
    bms = grouped[reference_key]["bms"]
    rows = []
    for sub_key, run in bms.items():
        s = run["summary"]
        flag = run["info"]["scenario_flag"] or ""
        central = _capacities(s).get("central") or {}

        gen_caps: Dict[str, float] = {}
        sto_caps: Dict[str, float] = {}
        for dev, dev_data in central.items():
            if not isinstance(dev_data, dict):
                continue
            if dev in _STORAGE_DEVS:
                v = float(dev_data.get("cap_kWh", 0) or 0)
                if v > 0:
                    sto_caps[dev] = v
            elif dev in _AREA_DEVS:
                v = float(dev_data.get("cap_m2", 0) or 0)
                if v > 0:
                    gen_caps[dev] = v
            else:
                v = float(dev_data.get("cap_kW", 0) or 0)
                if v > 0:
                    gen_caps[dev] = v

        n_c, n_t = _connected_count(run, flag) if flag else (0, 0)
        rows.append({
            "label": _bm_label(sub_key),
            "bm":    run["info"]["business_model"],
            "flag":  flag,
            "gen":   gen_caps,
            "sto":   sto_caps,
            "n_c":   n_c, "n_t": n_t,
        })

    rows.sort(key=lambda r: (r["bm"], r["flag"]))
    return rows


def _draw_capacity_page(ax, rows, key: str, title: str, ylabel: str) -> None:
    devs: List[str] = []
    for r in rows:
        for d in r[key].keys():
            if d not in devs:
                devs.append(d)
    if not devs:
        ax.text(0.5, 0.5, "keine Daten", ha="center", va="center",
                transform=ax.transAxes, fontsize=11, color="#9E9E9E")
        ax.axis("off")
        return

    labels = [r["label"] for r in rows]
    x = np.arange(len(rows))

    bottom = np.zeros(len(rows))
    for dev in devs:
        vals = np.array([r[key].get(dev, 0.0) for r in rows])
        if not np.any(vals > 0):
            continue
        ax.bar(x, vals, 0.62, bottom=bottom, label=dev,
               color=TECH_COLORS.get(dev, "#9E9E9E"),
               edgecolor="white", linewidth=0.5)
        bottom += vals

    pad = 0.025 * (max(bottom) if len(bottom) and max(bottom) > 0 else 1.0)
    for i, r in enumerate(rows):
        if r["n_t"] > 0:
            ax.text(i, bottom[i] + pad, f"{r['flag']}: {r['n_c']}/{r['n_t']}",
                    ha="center", va="bottom", fontsize=9, fontweight="bold",
                    color="#263238")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right", fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylim(0, max(bottom) * 1.18 if max(bottom) > 0 else 1)
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(title="Geraete", fontsize=8,
              ncol=min(4, max(1, len(devs))),
              loc="upper left", bbox_to_anchor=(0.0, -0.18),
              frameon=True, framealpha=0.9, edgecolor="#D0D0D0")


def plot_central_tech_mix_split(grouped: Dict[str, Dict[str, Any]],
                                 save_path: str,
                                 reference_key: str) -> None:
    """
    Multi-Page-PDF:
      Seite 1: Erzeuger (kW / m2)
      Seite 2: Speicher (kWh)
    """
    rows = _collect_capacities_split(grouped, reference_key)
    if not rows:
        return
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with PdfPages(save_path) as pdf:
        for kind, key, ylab in [
            ("Erzeuger (kW bzw. m2)", "gen", "Kapazitaet  [kW / m²]"),
            ("Speicher (kWh)",        "sto", "Kapazitaet  [kWh]"),
        ]:
            fig, ax = plt.subplots(figsize=(max(9, 1.4 * len(rows)), 6.4))
            _draw_capacity_page(ax, rows, key,
                                 f"Zentraler Energiehub - {kind} ({reference_key})",
                                 ylab)
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    print(f"  Saved: {save_path}")


# =====================================================================
# C6 - NPV-TABELLE PRO RUN (Multi-Page-PDF pro Referenz)
# =====================================================================

def _npv_rows_for_run(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Pro-Haus-NPV-Eintraege fuer den Run (Szenario A oder B je nach Flag).
    Faellt im B-Fall ohne building_details auf eine einzelne Aggregat-Zeile zurueck.
    """
    s = run["summary"]
    bd_sub = _kbm(s)
    flag = (run["info"].get("scenario_flag") or "B").upper()
    sc = bd_sub.get(f"scenario_{flag.lower()}") or {}

    details = sc.get("building_details") or {}
    excluded = set(sc.get("excluded") or [])

    rows = []
    if details:
        for bid, det in details.items():
            if not isinstance(det, dict):
                continue
            npv_ref = det.get("npv_ref")
            npv_at  = det.get("npv_wn_at_price")
            diff = (npv_at - npv_ref) if (npv_ref is not None and npv_at is not None) else None
            economic = det.get("economic_at_price")
            if economic is None:
                economic = det.get("economic_for_building")
            rows.append({
                "Gebaeude":        bid,
                "Heat_kWh":        det.get("heat_kWh"),
                "NPV_ref":         npv_ref,
                "NPV_BM_at_price": npv_at,
                "Diff":            diff,
                "p_max_i":         det.get("p_max"),
                "wirtschaftlich":  economic,
                "ausgeschlossen":  bid in excluded,
            })
        rows.sort(key=lambda r: _natural_id_key(r["Gebaeude"]))
        return rows

    # Aggregat-Fallback (Contracting / GGV in Szenario B)
    sum_at = sc.get("sum_npv_wn_at_price")
    sum_ref = sc.get("sum_npv_ref")
    heat_total = sc.get("heat_total_kWh")
    if sum_at is None or sum_ref is None:
        return []
    rows.append({
        "Gebaeude":        "Quartier (Aggregat)",
        "Heat_kWh":        heat_total,
        "NPV_ref":         sum_ref,
        "NPV_BM_at_price": sum_at,
        "Diff":            sum_at - sum_ref,
        "p_max_i":         None,
        "wirtschaftlich":  (sum_at >= sum_ref),
        "ausgeschlossen":  False,
    })
    return rows


def _draw_npv_table_page(rows: List[Dict[str, Any]],
                          run: Dict[str, Any],
                          run_label: str):
    """Zeichnet eine PDF-Seite mit der NPV-Tabelle fuer einen Run."""
    if not rows:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.axis("off")
        ax.text(0.5, 0.5, f"{run_label}: keine NPV-Daten",
                ha="center", va="center", fontsize=12, color="#616161")
        return fig

    eur_vals = []
    for r in rows:
        for k in ("NPV_ref", "NPV_BM_at_price", "Diff"):
            if r.get(k) is not None:
                eur_vals.append(r[k])
    factor, unit = _smart_unit_eur(eur_vals if eur_vals else [0.0])

    table = []
    for r in rows:
        heat_mwh = (r["Heat_kWh"] / 1000.0) if r["Heat_kWh"] is not None else None
        pmax_ct = (r["p_max_i"] * 100.0) if r["p_max_i"] is not None else None
        table.append([
            str(r["Gebaeude"]),
            f"{heat_mwh:,.2f}" if heat_mwh is not None else "-",
            f"{r['NPV_ref']         * factor:,.2f}" if r["NPV_ref"]         is not None else "-",
            f"{r['NPV_BM_at_price'] * factor:,.2f}" if r["NPV_BM_at_price"] is not None else "-",
            f"{r['Diff']            * factor:,.2f}" if r["Diff"]            is not None else "-",
            f"{pmax_ct:,.2f}" if pmax_ct is not None else "-",
            ("ja" if r["wirtschaftlich"] is True
             else "nein" if r["wirtschaftlich"] is False else "-"),
        ])

    headers = ["Gebaeude", "Heizung [MWh/a]", f"NPV_ref [{unit}]",
               f"NPV_BM [{unit}]", f"Diff [{unit}]",
               "p_max,i [ct/kWh]", "wirtsch."]

    fig_h = max(2.5, 0.42 * (len(rows) + 1) + 1.0)
    fig, ax = plt.subplots(figsize=(11.5, fig_h))
    ax.axis("off")
    ax.set_title(f"NPV-Vergleich pro Haus - {run_label}",
                 fontweight="bold", fontsize=12, pad=14)

    tbl = ax.table(cellText=table, colLabels=headers,
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(9)
    tbl.scale(1.0, 1.35)

    # Header-Style
    for j in range(len(headers)):
        c = tbl[0, j]
        c.set_facecolor("#37474F")
        c.set_text_props(color="white", fontweight="bold")

    # Zeilen einfaerben (Diff + wirtsch.)
    for i, r in enumerate(rows):
        if r.get("ausgeschlossen"):
            for j in range(len(headers)):
                tbl[i + 1, j].set_facecolor("#EEEEEE")
            tbl[i + 1, 0].set_text_props(color="#616161", style="italic")
            continue
        d = r["Diff"]
        c_diff = tbl[i + 1, 4]
        c_econ = tbl[i + 1, 6]
        if d is None:
            c_diff.set_facecolor("#F5F5F5")
        elif d >= 0:
            c_diff.set_facecolor("#C8E6C9")
        else:
            c_diff.set_facecolor("#FFCDD2")
        if r["wirtschaftlich"] is True:
            c_econ.set_facecolor("#C8E6C9")
        elif r["wirtschaftlich"] is False:
            c_econ.set_facecolor("#FFCDD2")
        if i % 2 == 1:
            for j in (0, 1, 2, 3, 5):
                tbl[i + 1, j].set_facecolor("#F5F5F5")

    return fig


def plot_npv_tables_per_run(grouped: Dict[str, Dict[str, Any]],
                             save_path_pdf: str,
                             save_path_csv: str,
                             reference_key: str) -> None:
    """
    Eine PDF pro Referenzfall, je Run ein Blatt.
    Zusaetzlich CSV mit allen Eintraegen (Run-Spalte ergaenzt).
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    # Reihenfolge: nach BM-Name + Szenario A vor B
    run_keys = sorted(bms.keys(),
                      key=lambda k: (bms[k]["info"]["business_model"],
                                      bms[k]["info"]["scenario_flag"] or ""))

    os.makedirs(os.path.dirname(save_path_pdf), exist_ok=True)
    with PdfPages(save_path_pdf) as pdf:
        for sub_key in run_keys:
            run = bms[sub_key]
            label = _bm_label(sub_key)
            rows = _npv_rows_for_run(run)
            fig = _draw_npv_table_page(rows, run, label)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    print(f"  Saved: {save_path_pdf}")

    # CSV ueber alle Runs
    os.makedirs(os.path.dirname(save_path_csv), exist_ok=True)
    cols = ["Run", "Gebaeude", "Heat_MWh_a", "NPV_ref_EUR",
            "NPV_BM_EUR", "Diff_EUR", "p_max_i_ct_per_kWh",
            "wirtschaftlich", "ausgeschlossen"]
    with open(save_path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols)
        for sub_key in run_keys:
            run = bms[sub_key]; label = _bm_label(sub_key)
            for r in _npv_rows_for_run(run):
                heat_mwh = (r["Heat_kWh"] / 1000.0) if r["Heat_kWh"] is not None else None
                pmax_ct = (r["p_max_i"] * 100.0) if r["p_max_i"] is not None else None
                w.writerow([
                    label, r["Gebaeude"],
                    f"{heat_mwh:.2f}" if heat_mwh is not None else "",
                    f"{r['NPV_ref']:.2f}"          if r["NPV_ref"]         is not None else "",
                    f"{r['NPV_BM_at_price']:.2f}" if r["NPV_BM_at_price"] is not None else "",
                    f"{r['Diff']:.2f}"             if r["Diff"]            is not None else "",
                    f"{pmax_ct:.4f}"               if pmax_ct              is not None else "",
                    "ja" if r["wirtschaftlich"] is True
                       else "nein" if r["wirtschaftlich"] is False else "",
                    "ja" if r.get("ausgeschlossen") else "nein",
                ])
    print(f"  Saved: {save_path_csv}")


# =====================================================================
# C7 - SCHLUSSUEBERSICHT pro Referenz
# =====================================================================

def _summary_row(sub_key: str, run: Dict[str, Any]) -> Dict[str, Any]:
    s = run["summary"]
    bd = _kbm(s)
    flag = run["info"]["scenario_flag"] or ""

    p_min   = bd.get("p_min")
    p_max_a = bd.get("p_max_a")
    p_max_b = bd.get("p_max_b")

    # Anschluss-Info aus dem aktiven Szenario-Block
    sc_a = bd.get("scenario_a") or {}
    sc_b = bd.get("scenario_b") or {}

    # Connected je Szenario
    conn_a = sc_a.get("connected") or sc_a.get("connected_buildings") or []
    excl_a = sc_a.get("excluded") or []
    n_total = len(conn_a) + len(excl_a) if (conn_a or excl_a) else \
              len(sc_a.get("building_details") or {})

    conn_b = sc_b.get("connected_buildings") or sc_b.get("connected") or []
    n_total_b = len(conn_b) or n_total

    # NPV-Aggregat (BM-Sicht: Sum NPV_BM ueber angeschlossene Haeuser)
    def _agg(sc_block):
        details = sc_block.get("building_details") or {}
        if details:
            tot = 0.0; ok = False
            for det in details.values():
                v = det.get("npv_wn_at_price")
                if v is not None:
                    tot += float(v); ok = True
            return tot if ok else None
        # Fallback Aggregat
        v = sc_block.get("sum_npv_wn_at_price")
        return float(v) if v is not None else None

    npv_at_a = _agg(sc_a)
    npv_at_b = _agg(sc_b)

    return {
        "Run":         _bm_label(sub_key),
        "BM":          run["info"]["business_model"],
        "Szenario":    flag,
        "n_connected_A": len(conn_a),
        "n_excluded_A":  len(excl_a),
        "n_total_A":     n_total,
        "n_connected_B": n_total_b,
        "p_min_ct":     (p_min   * 100.0) if p_min   is not None else None,
        "p_max_A_ct":   (p_max_a * 100.0) if p_max_a is not None else None,
        "p_max_B_ct":   (p_max_b * 100.0) if p_max_b is not None else None,
        "NPV_BM_at_pmax_A": npv_at_a,
        "NPV_BM_at_pmax_B": npv_at_b,
        "ausgeschlossene_Gebaeude": ", ".join(str(x) for x in excl_a),
    }


def plot_overview_table(grouped: Dict[str, Dict[str, Any]],
                         save_path_pdf: str,
                         save_path_csv: str,
                         reference_key: str) -> None:
    """
    Schlusstabelle pro Referenz mit:
      Run | n_conn_A | n_total | excluded | p_min | p_max_A | p_max_B
          | NPV_BM(A) | NPV_BM(B)
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    # Pro BM-Name nur einmal: bevorzugt A-Run (enthaelt p_max_a + scenario_a),
    # B-Run als Backup falls kein A vorhanden.
    by_bm: Dict[str, Dict[str, Any]] = {}
    for sub_key, run in bms.items():
        bm = run["info"]["business_model"]
        flag = run["info"]["scenario_flag"] or ""
        if bm not in by_bm or (flag == "A" and by_bm[bm]["info"]["scenario_flag"] != "A"):
            by_bm[bm] = {**run, "_sub_key": sub_key}

    rows = [_summary_row(r["_sub_key"], r) for r in by_bm.values()]
    rows.sort(key=lambda r: r["BM"])
    if not rows:
        return

    # Einheit Geld
    npv_vals = [r[k] for r in rows for k in ("NPV_BM_at_pmax_A", "NPV_BM_at_pmax_B")
                if r.get(k) is not None]
    factor, unit = _smart_unit_eur(npv_vals if npv_vals else [0.0])

    headers = ["BM", "n_conn\nA", "n_total\nA", "excl\nA",
               "p_min\n[ct/kWh]", "p_max,A\n[ct/kWh]", "p_max,B\n[ct/kWh]",
               f"NPV_BM\n@p_max A\n[{unit}]",
               f"NPV_BM\n@p_max B\n[{unit}]",
               "ausgeschl. (A)"]

    table = []
    for r in rows:
        table.append([
            BM_PRETTY.get(r["BM"], r["BM"]),
            str(r["n_connected_A"]),
            str(r["n_total_A"]),
            str(r["n_excluded_A"]),
            f"{r['p_min_ct']:.2f}"   if r["p_min_ct"]   is not None else "-",
            f"{r['p_max_A_ct']:.2f}" if r["p_max_A_ct"] is not None else "-",
            f"{r['p_max_B_ct']:.2f}" if r["p_max_B_ct"] is not None else "-",
            f"{r['NPV_BM_at_pmax_A'] * factor:,.2f}" if r["NPV_BM_at_pmax_A"] is not None else "-",
            f"{r['NPV_BM_at_pmax_B'] * factor:,.2f}" if r["NPV_BM_at_pmax_B"] is not None else "-",
            r["ausgeschlossene_Gebaeude"] or "-",
        ])

    fig_h = max(3.5, 0.55 * (len(rows) + 1) + 1.6)
    fig, ax = plt.subplots(figsize=(15.5, fig_h))
    ax.axis("off")
    ax.set_title(f"Uebersicht BM-Vergleich - {reference_key}",
                 fontweight="bold", fontsize=13, pad=14)

    tbl = ax.table(cellText=table, colLabels=headers,
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(9)
    tbl.scale(1.0, 1.65)

    # Header-Zeile groesser, mehrzeilig
    for j in range(len(headers)):
        c = tbl[0, j]
        c.set_facecolor("#263238")
        c.set_text_props(color="white", fontweight="bold")
        c.set_height(0.18)

    # zebra
    for i in range(len(rows)):
        if i % 2 == 1:
            for j in range(len(headers)):
                tbl[i + 1, j].set_facecolor("#F5F5F5")

    os.makedirs(os.path.dirname(save_path_pdf), exist_ok=True)
    plt.savefig(save_path_pdf, dpi=220, bbox_inches="tight"); plt.close()
    print(f"  Saved: {save_path_pdf}")

    # CSV
    csv_cols = ["BM", "n_connected_A", "n_total_A", "n_excluded_A",
                "p_min_ct_per_kWh", "p_max_A_ct_per_kWh", "p_max_B_ct_per_kWh",
                "NPV_BM_at_pmax_A_EUR", "NPV_BM_at_pmax_B_EUR",
                "ausgeschlossen_A"]
    os.makedirs(os.path.dirname(save_path_csv), exist_ok=True)
    with open(save_path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(csv_cols)
        for r in rows:
            w.writerow([
                BM_PRETTY.get(r["BM"], r["BM"]),
                r["n_connected_A"], r["n_total_A"], r["n_excluded_A"],
                f"{r['p_min_ct']:.4f}"   if r["p_min_ct"]   is not None else "",
                f"{r['p_max_A_ct']:.4f}" if r["p_max_A_ct"] is not None else "",
                f"{r['p_max_B_ct']:.4f}" if r["p_max_B_ct"] is not None else "",
                f"{r['NPV_BM_at_pmax_A']:.2f}" if r["NPV_BM_at_pmax_A"] is not None else "",
                f"{r['NPV_BM_at_pmax_B']:.2f}" if r["NPV_BM_at_pmax_B"] is not None else "",
                r["ausgeschlossene_Gebaeude"],
            ])
    print(f"  Saved: {save_path_csv}")


# =====================================================================
# ORCHESTRATOR
# =====================================================================

def run_central_plots(grouped: Dict[str, Dict[str, Any]],
                       base_save_dir: str) -> None:
    """
    Erzeugt fuer jede Referenz:
      C1  zentraler Tech-Mix mit Haeuserzahlen
      C2  NPV-Vergleich Quartier (Szenario B)
      C3  NPV pro Haus (Szenario A) - ein Plot pro BM
      C4  Kostenzusammensetzung (inkl. EUR/a/Haus)
      C5  Tech-Mix aufgeteilt Erzeuger/Speicher (Multi-Page)
      C6  NPV-Tabellen pro Run (Multi-Page PDF + CSV)
      C7  Schluesselkennzahlen-Uebersicht (PDF + CSV)
    """
    for ref_key, group in grouped.items():
        bms = group.get("bms") or {}
        if not bms:
            continue

        out_dir = os.path.join(base_save_dir, ref_key, "central")
        os.makedirs(out_dir, exist_ok=True)

        plot_central_tech_mix_with_houses(
            grouped, os.path.join(out_dir, "C1_tech_mix_n_houses.pdf"), ref_key)

        plot_npv_quartier_B(
            grouped, os.path.join(out_dir, "C2_npv_quartier_B.pdf"), ref_key)

        # C3 pro BM - nur Szenario-A-Runs
        c3_dir = os.path.join(out_dir, "C3_npv_per_house_A")
        os.makedirs(c3_dir, exist_ok=True)
        for sub_key, run in bms.items():
            if run["info"].get("scenario_flag") != "A":
                continue
            tag = sub_key.replace("__", "_")
            plot_npv_per_house_A(
                run,
                os.path.join(c3_dir, f"C3_npv_per_house_A_{tag}.pdf"),
                _bm_label(sub_key),
            )

        plot_cost_breakdown_central(
            grouped, os.path.join(out_dir, "C4_cost_breakdown.pdf"), ref_key)

        plot_central_tech_mix_split(
            grouped, os.path.join(out_dir, "C5_tech_mix_split.pdf"), ref_key)

        plot_npv_tables_per_run(
            grouped,
            os.path.join(out_dir, "C6_npv_tables_per_run.pdf"),
            os.path.join(out_dir, "C6_npv_tables_per_run.csv"),
            ref_key,
        )

        plot_overview_table(
            grouped,
            os.path.join(out_dir, "C7_overview.pdf"),
            os.path.join(out_dir, "C7_overview.csv"),
            ref_key,
        )