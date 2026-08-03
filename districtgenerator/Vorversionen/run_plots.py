# -*- coding: utf-8 -*-
"""
run_plots.py — Generiert BM-Vergleichsplots aus den gespeicherten pkl-Dateien.

Workflow:
  1. Reference und alle BMs wurden bereits per e8_2.run_reference_and_all_bms()
     ausgefuehrt und liegen als summary_*.pkl / timeseries_*.pkl im
     <RESULT_ROOT>/<RESULTS_SUBFOLDER>/<scenario_variant> Ordner.
  2. Diese Datei laedt die summary-pkls, gruppiert sie pro Referenzfall
     (ref_boi / ref_wp) und erzeugt die Bewertungs-Plots.

Pflichten dieser Datei:
- KEINE Optimierung. Nur Plotgenerierung aus pkl.
- KEINE Redundanzen: Wir nutzen die bereits in den pkl-Dateien gespeicherten
  KPIs (p_min, p_max, npv_coop, npv_ref, npv_difference, lcoh,
  bm_breakdown, capacities, eco) sowie die Heat-Grid-Metriken.
- Plots gegen die existierenden plots_bm_comparison-Funktionen (Adapter
  Summary -> Pseudo-Datahandler) und neue, pkl-native Bewertungslogik-Plots.

Aufruf:
    python run_plots.py
oder programmatisch:
    from run_plots import run
    run(scenario_variant="H01")
"""

import os
import re
import glob
import pickle
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ----------------------------------------------------------------------
# Pfade — identisch zu e8_2.py
# ----------------------------------------------------------------------
RESULT_ROOT = r"C:\Users\rha-csa\PycharmProjects\districtgenerator\districtgenerator\results"
RESULTS_SUBFOLDER = "bm_results"
PLOTS_SUBFOLDER = "bm_plots"

# Lastprofil-Modul (G1-G4)
try:
    from plots_loads import run_load_plots
    _HAS_LOAD_PLOTS = True
except ImportError as _e:
    print(f"[run_plots] plots_loads nicht verfuegbar: {_e}")
    _HAS_LOAD_PLOTS = False

# Zentrale Plots (C1-C4)
try:
    from plots_central import run_central_plots
    _HAS_CENTRAL_PLOTS = True
except ImportError as _e:
    print(f"[run_plots] plots_central nicht verfuegbar: {_e}")
    _HAS_CENTRAL_PLOTS = False


# ══════════════════════════════════════════════════════════════════════
# 1) LADEN UND GRUPPIEREN
# ══════════════════════════════════════════════════════════════════════

def _load_pkl(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        return pickle.load(f)


def _parse_summary_name(filename: str) -> Dict[str, Optional[str]]:
    """
    Parst summary_<scenario>_<reference_key>_<bm_name>_<A|B>.pkl
    Reference: summary_<scenario>_<reference_key>.pkl

    Returns dict mit keys: scenario_name, reference_key, business_model, scenario_flag, kind
    kind in {"reference", "bm"}
    """
    stem = os.path.basename(filename).replace(".pkl", "")
    if not stem.startswith("summary_"):
        return {}
    stem = stem[len("summary_"):]
    parts = stem.split("_")

    # BM-Run: ... _A oder _B am Ende
    if parts[-1] in ("A", "B"):
        flag = parts[-1]
        # ref_key ist immer "ref_boi" oder "ref_wp" -> 2 tokens
        # scenario_name kann mehrere underscores enthalten
        # Pattern: <scenario>...<ref_X>_<bm...>_<flag>
        # finde "ref_boi" oder "ref_wp"
        for i, p in enumerate(parts[:-1]):
            if p == "ref" and i + 1 < len(parts) and parts[i + 1] in ("boi", "wp"):
                scen = "_".join(parts[:i])
                ref = "_".join(parts[i:i + 2])
                bm = "_".join(parts[i + 2:-1])
                return {
                    "scenario_name": scen,
                    "reference_key": ref,
                    "business_model": bm,
                    "scenario_flag": flag,
                    "kind": "bm",
                }
        return {}

    # Reference-Run: ...<scenario>_ref_boi oder ...<scenario>_ref_wp
    for i, p in enumerate(parts):
        if p == "ref" and i + 1 < len(parts) and parts[i + 1] in ("boi", "wp"):
            scen = "_".join(parts[:i])
            ref = "_".join(parts[i:i + 2])
            return {
                "scenario_name": scen,
                "reference_key": ref,
                "business_model": ref,
                "scenario_flag": None,
                "kind": "reference",
            }
    return {}


def load_all_runs(results_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Laedt alle summary_*.pkl und gibt einen dict zurueck:
        { run_key: { "summary": ..., "info": parsed, "summary_path": ...,
                     "timeseries_path": ..., "topology_path": ... } }

    run_key:
      - reference: "<reference_key>"                   (z.B. "ref_boi")
      - bm:        "<reference_key>__<bm_name>__<flag>" (z.B. "ref_boi__waermecontracting__A")
    """
    out = {}
    pattern = os.path.join(results_dir, "summary_*.pkl")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"[run_plots] Keine summary-Dateien gefunden in {results_dir}")
        return out

    for fp in files:
        info = _parse_summary_name(fp)
        if not info:
            print(f"[run_plots] Konnte Filename nicht parsen: {os.path.basename(fp)}")
            continue

        if info["kind"] == "reference":
            key = info["reference_key"]
        else:
            key = f"{info['reference_key']}__{info['business_model']}__{info['scenario_flag']}"

        # zugehoerige timeseries/topology Pfade ermitteln (gleicher Stem)
        stem = os.path.basename(fp).replace(".pkl", "")[len("summary_"):]
        ts_path = os.path.join(results_dir, f"timeseries_{stem}.pkl")
        topo_path = os.path.join(results_dir, f"topology_{stem}.pkl")

        out[key] = {
            "summary": _load_pkl(fp),
            "info": info,
            "summary_path": fp,
            "timeseries_path": ts_path if os.path.exists(ts_path) else None,
            "topology_path": topo_path if os.path.exists(topo_path) else None,
        }

    print(f"[run_plots] Geladen: {len(out)} runs aus {results_dir}")
    return out


def group_by_reference(runs: Dict[str, Dict[str, Any]]
                       ) -> Dict[str, Dict[str, Any]]:
    """
    Gruppiert Runs nach reference_key.
    Returns:
        { reference_key: { "reference": run, "bms": { "<bm>__<flag>": run, ... } } }
    """
    grouped: Dict[str, Dict[str, Any]] = {}
    for key, run in runs.items():
        info = run["info"]
        ref = info["reference_key"]
        grouped.setdefault(ref, {"reference": None, "bms": {}})
        if info["kind"] == "reference":
            grouped[ref]["reference"] = run
        else:
            sub_key = f"{info['business_model']}__{info['scenario_flag']}"
            grouped[ref]["bms"][sub_key] = run
    return grouped


# ══════════════════════════════════════════════════════════════════════
# 2) KPI-EXTRAKTION AUS SUMMARY (single source of truth)
# ══════════════════════════════════════════════════════════════════════

def _kpi_static(summary: Dict[str, Any]) -> Dict[str, Any]:
    return (summary.get("kpis") or {}).get("static") or {}


def _kpi_yearly(summary: Dict[str, Any]) -> Dict[str, Any]:
    return (summary.get("kpis") or {}).get("yearly") or {}


def _bm_breakdown(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gibt das BM-spezifische breakdown dict zurueck (waermecontracting / ggv /
    kundenanlage / genossenschaft / reference).
    """
    bd = (summary.get("kpis") or {}).get("bm_breakdown") or {}
    # bevorzugt "bm_breakdown" (immer gesetzt), sonst spezifischer Key
    if "bm_breakdown" in bd:
        return bd["bm_breakdown"]
    for k in ("waermecontracting_breakdown",
              "gemeinschaftliche_gebaeudeversorgung_breakdown",
              "kundenanlage_breakdown",
              "genossenschaft_breakdown",
              "reference_breakdown"):
        if k in bd:
            return bd[k]
    return {}


def _capacities(summary: Dict[str, Any]) -> Dict[str, Any]:
    return summary.get("capacities") or {}


def _heat_grid(summary: Dict[str, Any]) -> Dict[str, Any]:
    return summary.get("heat_grid") or {}


def _eco_static(summary: Dict[str, Any]) -> Dict[str, Any]:
    return (summary.get("eco") or {}).get("static") or {}


def _smart_unit_eur(values):
    """Skala anhand des Maximalwerts: € / k€ / Mio €."""
    m = max(abs(v) for v in values if v is not None) if values else 0.0
    if m >= 1_000_000: return 1e-6, "Mio. EUR"
    if m >= 10_000:    return 1e-3, "kEUR"
    return 1.0, "EUR"


def _label(bm_key: str) -> str:
    if "__" in bm_key:
        bm, flag = bm_key.split("__", 1)
    else:
        bm, flag = bm_key, ""
    pretty = {
        "waermecontracting":             "Contracting",
        "waermecontracting_ggv":         "GGV",
        "waermecontracting_kundenanlage":"Kundenanlage",
        "waermegenossenschaft":          "Genossenschaft",
        "ref_boi":                       "Ref BOI",
        "ref_wp":                        "Ref WP",
    }.get(bm, bm.replace("_", " ").title())
    return f"{pretty} ({flag})" if flag else pretty


# ══════════════════════════════════════════════════════════════════════
# 3) BEWERTUNGSLOGIK-PLOTS (KERNPLOTS)
# ══════════════════════════════════════════════════════════════════════

# Gemeinsame Farben
BM_COLORS = {
    "waermecontracting":              "#2196F3",  # Blau
    "waermecontracting_ggv":          "#FF9800",  # Orange
    "waermecontracting_kundenanlage": "#9C27B0",  # Lila
    "waermegenossenschaft":           "#4CAF50",  # Gruen
}


def _bm_color(bm_name: str) -> str:
    return BM_COLORS.get(bm_name, "#607D8B")


def plot_pmin_pmax_corridor(grouped: Dict[str, Dict[str, Any]],
                             save_path: str,
                             reference_key: str) -> None:
    """
    Bewertungslogik-Kernplot: p_min vs p_max Korridor pro BM.

    Pro BM:
      - Balken zeigt Korridor [p_min, p_max] in ct/kWh.
      - Liegt p_min unter p_max -> wirtschaftlich darstellbar (gruen).
      - Liegt p_min ueber p_max -> nicht darstellbar (rot).
      - Genossenschaft: nur p_min (= LCOH), kein p_max (Mitglieder = Eigentuemer).
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        print(f"[pmin_pmax] keine BMs fuer {reference_key}")
        return

    rows = []
    for sub_key, run in bms.items():
        s = run["summary"]
        st = _kpi_static(s)
        bm_name = run["info"]["business_model"]
        rows.append({
            "label": _label(sub_key),
            "bm_name": bm_name,
            "p_min": st.get("p_min"),
            "p_max": st.get("p_max"),
            "feasible": st.get("economically_favorable"),
        })

    fig, ax = plt.subplots(figsize=(max(8, 1.3 * len(rows)), 6))
    x = np.arange(len(rows))

    for i, r in enumerate(rows):
        p_min = r["p_min"]
        p_max = r["p_max"]
        color = _bm_color(r["bm_name"])

        if p_min is not None and p_max is not None:
            lo, hi = sorted([p_min * 100, p_max * 100])
            feasible = p_min <= p_max
            edge = "#2E7D32" if feasible else "#C62828"
            ax.bar(i, hi - lo, bottom=lo, color=color, alpha=0.55,
                   edgecolor=edge, linewidth=2.0,
                   label=r["label"] if i == 0 else None)
            ax.plot([i - 0.3, i + 0.3], [p_min * 100, p_min * 100],
                    color="#1B5E20", lw=2.4)
            ax.plot([i - 0.3, i + 0.3], [p_max * 100, p_max * 100],
                    color="#B71C1C", lw=2.4)
            ax.text(i, max(p_min, p_max) * 100,
                    f"Δ = {(p_max - p_min) * 100:+.2f}",
                    ha="center", va="bottom", fontsize=9, fontweight="bold",
                    color=edge)
        elif p_min is not None and p_max is None:
            # Genossenschaft: nur p_min = LCOH
            ax.bar(i, p_min * 100, color=color, alpha=0.55,
                   edgecolor="#1B5E20", linewidth=2.0)
            ax.plot([i - 0.3, i + 0.3], [p_min * 100, p_min * 100],
                    color="#1B5E20", lw=2.4)
            ax.text(i, p_min * 100, "LCOH", ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color="#1B5E20")

    ax.set_xticks(x)
    ax.set_xticklabels([r["label"] for r in rows], rotation=20, ha="right",
                       fontsize=10)
    ax.set_ylabel(r"Waermepreis [ct/kWh]")
    ax.set_title(f"p_min / p_max Korridor — Referenz: {reference_key}",
                 fontsize=12, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Legende manuell
    from matplotlib.lines import Line2D
    leg = [
        Line2D([0], [0], color="#1B5E20", lw=2.4, label=r"$p_{min}$"),
        Line2D([0], [0], color="#B71C1C", lw=2.4, label=r"$p_{max}$"),
    ]
    ax.legend(handles=leg, loc="upper right", fontsize=10)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


def _aggregate_bm_npv(run: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Aggregiert NPV_BM und NPV_ref aus bm_breakdown.scenario_<>.building_details.
    Verwendet das tatsaechlich aktive Szenario aus bm_breakdown["scenario"].
    """
    s = run["summary"]
    bd = (s.get("kpis") or {}).get("bm_breakdown") or {}
    bd_sub = bd.get("bm_breakdown") or {}
    if not bd_sub:
        return {"npv_bm": None, "npv_ref": None, "diff": None}

    flag = run["info"]["scenario_flag"] or bd_sub.get("scenario") or "B"
    scen = bd_sub.get(f"scenario_{flag.lower()}") or bd_sub.get("scenario_b") or {}
    details = scen.get("building_details") or {}

    npv_bm_total = 0.0
    npv_ref_total = 0.0
    n = 0
    for bid, det in details.items():
        if not isinstance(det, dict):
            continue
        npv_at = det.get("npv_wn_at_price")
        npv_rf = det.get("npv_ref")
        if npv_at is None or npv_rf is None:
            continue
        npv_bm_total += float(npv_at)
        npv_ref_total += float(npv_rf)
        n += 1
    if n == 0:
        return {"npv_bm": None, "npv_ref": None, "diff": None}
    return {
        "npv_bm":  npv_bm_total,
        "npv_ref": npv_ref_total,
        "diff":    npv_bm_total - npv_ref_total,
    }


def plot_npv_difference(grouped: Dict[str, Dict[str, Any]],
                         save_path: str,
                         reference_key: str) -> None:
    """
    NPV-Differenz (NPV_BM - NPV_ref), summiert ueber alle versorgten Gebaeude.
    Aus bm_breakdown.scenario_<>.building_details extrahiert.
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    rows = []
    for sub_key, run in bms.items():
        agg = _aggregate_bm_npv(run)
        rows.append({
            "label":  _label(sub_key),
            "bm_name": run["info"]["business_model"],
            "diff":    agg["diff"],
        })

    diffs = [r["diff"] for r in rows if r["diff"] is not None]
    if not diffs:
        print(f"  [npv_diff] keine NPV-Daten in bm_breakdown")
        return

    factor, unit = _smart_unit_eur(diffs)

    fig, ax = plt.subplots(figsize=(max(8, 1.3 * len(rows)), 6))
    x = np.arange(len(rows))
    for i, r in enumerate(rows):
        if r["diff"] is None: continue
        v = r["diff"] * factor
        color = "#2E7D32" if r["diff"] >= 0 else "#C62828"
        ax.bar(i, v, color=color, alpha=0.85, edgecolor="white")
        ax.text(i, v, f"{v:+,.2f} {unit}", ha="center",
                va="bottom" if v >= 0 else "top",
                fontsize=10, fontweight="bold")

    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([r["label"] for r in rows], rotation=15, ha="right",
                       fontsize=10)
    ax.set_ylabel(f"NPV_BM − NPV_ref  [{unit}]")
    ax.set_title(f"NPV-Differenz vs. Referenz — {reference_key}",
                 fontsize=12, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")



def plot_npv_difference_quartier_B(grouped: Dict[str, Dict[str, Any]],
                                   save_path: str,
                                   reference_key: str) -> None:
    """
    Gesamtquartier-NPV-Differenz nur fuer Kategorie/Szenario B.

    Dargestellt wird pro Business Model:
        Summe_Gebaeude(NPV_BM - NPV_ref)

    Falls fuer ein BM keine building_details gefunden werden, bleibt die Zeile
    sichtbar und wird als "keine Daten" markiert. Dadurch sieht man sofort,
    ob Daten fehlen, statt versehentlich nur einen Balken zu bekommen.
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    rows = []
    for sub_key, run in bms.items():
        if run.get("info", {}).get("scenario_flag") != "B":
            continue
        agg = _aggregate_bm_npv(run)
        rows.append({
            "label": _label(sub_key),
            "bm_name": run["info"]["business_model"],
            "diff": agg["diff"],
            "npv_bm": agg["npv_bm"],
            "npv_ref": agg["npv_ref"],
        })

    if not rows:
        print(f"  [npv_diff_B {reference_key}] keine Kategorie-B-Runs gefunden")
        return

    diffs = [r["diff"] for r in rows if r["diff"] is not None]
    factor, unit = _smart_unit_eur(diffs if diffs else [0.0])

    fig_h = max(4.2, 0.62 * len(rows) + 1.7)
    fig, ax = plt.subplots(figsize=(9.5, fig_h))
    y = np.arange(len(rows))

    vals = []
    colors = []
    for r in rows:
        if r["diff"] is None:
            vals.append(0.0)
            colors.append("#BDBDBD")
        else:
            vals.append(r["diff"] * factor)
            colors.append("#2E7D32" if r["diff"] >= 0 else "#C62828")

    ax.barh(y, vals, color=colors, alpha=0.88, edgecolor="white", linewidth=0.6)

    # Labels: Werte oder klarer Hinweis bei fehlenden Daten
    max_abs = max([abs(v) for v in vals] + [1.0])
    pad = 0.025 * max_abs
    for i, (r, v) in enumerate(zip(rows, vals)):
        if r["diff"] is None:
            ax.text(pad, i, "keine building_details", va="center", ha="left",
                    fontsize=9, color="#616161")
        else:
            ha = "left" if v >= 0 else "right"
            x_txt = v + pad if v >= 0 else v - pad
            ax.text(x_txt, i, f"{v:+,.2f} {unit}", va="center", ha=ha,
                    fontsize=10, fontweight="bold")

    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([r["label"] for r in rows], fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel(f"Summe ueber Gebaeude: NPV_BM - NPV_ref [{unit}]")
    ax.set_title(f"Gesamtquartier-NPV gegenueber Referenz - Kategorie B - {reference_key}",
                 fontsize=12, fontweight="bold")
    ax.grid(axis="x", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    # Symmetrische Achse um 0, damit positive/negative Effekte vergleichbar sind
    lim = max_abs * 1.18
    ax.set_xlim(-lim, lim)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=220, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")

def plot_npv_levels(grouped: Dict[str, Dict[str, Any]],
                     save_path: str,
                     reference_key: str) -> None:
    """
    Absolute NPV-Vergleichswerte: NPV_BM und NPV_ref nebeneinander.
    Erlaubt Einordnung der Differenz in der Groessenordnung.
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    rows = []
    for sub_key, run in bms.items():
        agg = _aggregate_bm_npv(run)
        rows.append({
            "label":   _label(sub_key),
            "bm_name": run["info"]["business_model"],
            "npv_bm":  agg["npv_bm"],
            "npv_ref": agg["npv_ref"],
        })

    all_vals = [v for r in rows for v in (r["npv_bm"], r["npv_ref"])
                if v is not None]
    if not all_vals:
        print(f"  [npv_levels] keine NPV-Daten in bm_breakdown")
        return
    factor, unit = _smart_unit_eur(all_vals)

    fig, ax = plt.subplots(figsize=(max(8, 1.3 * len(rows)), 6))
    x = np.arange(len(rows))
    w = 0.35

    coops = [(r["npv_bm"]  or 0) * factor for r in rows]
    refs  = [(r["npv_ref"] or 0) * factor for r in rows]
    colors = [_bm_color(r["bm_name"]) for r in rows]

    ax.bar(x - w / 2, coops, w, color=colors, alpha=0.9, label=r"$NPV_{BM}$")
    ax.bar(x + w / 2, refs, w, color="#607D8B", alpha=0.7, label=r"$NPV_{ref}$")

    for i, (c, r) in enumerate(zip(coops, refs)):
        if c:
            ax.text(i - w / 2, c, f"{c:,.2f}", ha="center",
                    va="bottom" if c >= 0 else "top", fontsize=8)
        if r:
            ax.text(i + w / 2, r, f"{r:,.2f}", ha="center",
                    va="bottom" if r >= 0 else "top", fontsize=8,
                    color="#37474F")

    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([r["label"] for r in rows], rotation=15, ha="right",
                       fontsize=10)
    ax.set_ylabel(f"NPV [{unit}]")
    ax.set_title(f"NPV-Niveau (BM vs. Referenz) — {reference_key}",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# ══════════════════════════════════════════════════════════════════════
# 4) TECHNISCHE / KONTEXT-PLOTS (Gruppe B)
# ══════════════════════════════════════════════════════════════════════

_STORAGE_DEVS = ("TES", "CTES", "BAT", "H2S", "GS")
_AREA_DEVS = ("PV", "STC")


def plot_technology_mix_central(grouped: Dict[str, Dict[str, Any]],
                                 save_path: str,
                                 reference_key: str) -> None:
    """
    Stacked bar: Zentral installierte Kapazitaeten je BM.
    """
    bms = grouped[reference_key]["bms"]
    runs = [(_label(k), v) for k, v in bms.items()]
    if not runs:
        return

    # alle Devices
    all_dev = []
    cap_per_bm: Dict[str, Dict[str, float]] = {}
    for label, run in runs:
        cap_per_bm[label] = {}
        central = (_capacities(run["summary"]).get("central") or {})
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
                cap_per_bm[label][dev] = float(v)
                if dev not in all_dev:
                    all_dev.append(dev)

    if not all_dev:
        print("  Keine zentralen Kapazitaeten gefunden.")
        return

    # Plot
    from plots_bm_comparison import TECH_COLORS  # bestehende Farbpalette nachnutzen
    labels = [r[0] for r in runs]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(max(9, 1.3 * len(labels)), 6))
    bottom = np.zeros(len(labels))
    for dev in all_dev:
        vals = np.array([cap_per_bm[l].get(dev, 0.0) for l in labels])
        if not np.any(vals > 0):
            continue
        ax.bar(x, vals, 0.6, bottom=bottom, label=dev,
               color=TECH_COLORS.get(dev, "#9E9E9E"),
               edgecolor="white", linewidth=0.4)
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=10)
    ax.set_ylabel("Kapazitaet (kW / kWh / m²)")
    ax.set_title(f"Technologiemix zentral — {reference_key}",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=8, ncol=3, loc="upper right")
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


def plot_heat_supply_shares(grouped: Dict[str, Dict[str, Any]],
                             save_path: str,
                             reference_key: str) -> None:
    """
    Anteile der zentralen Waermequellen am EH-Output je BM (aus summary
    pre-aggregated heat_grid metrics; falls dort nicht vorhanden, aus
    capacities-orientierter Heuristik).

    Praezision: kommt aus den jaehrlichen KPI-Feldern, falls KPIs.heat_*
    bereits aggregiert vorliegen. Fallback: Energietraeger-Anteile aus
    yearly['gas_year'], ['biomass_year'], ['waste_year'], ['hydrogen_year'],
    ['oil_year'], ['districtHeat_year'] + bilanziell el-basiert (HP/EB).
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    rows = []
    for sub_key, run in bms.items():
        s = run["summary"]
        yr = _kpi_yearly(s)
        # Erstes simulated_year nehmen
        years = (s.get("kpis") or {}).get("simulated_years") or []
        if not years:
            continue
        y = years[0]

        # Energietraegerbezug -> grobe Waermebilanz
        gas = (yr.get("gas_year") or {}).get(y, 0)
        biom = (yr.get("biomass_year") or {}).get(y, 0)
        waste = (yr.get("waste_year") or {}).get(y, 0)
        h2 = (yr.get("hydrogen_year") or {}).get(y, 0)
        oil = (yr.get("oil_year") or {}).get(y, 0)
        dh = (yr.get("districtHeat_year") or {}).get(y, 0)

        # El-basiert (HP, EB) -> ueber W_dem_buildings/HP nicht direkt;
        # Naeherung via residual_load nicht moeglich aus summary allein.
        # Wir zeigen den Brennstoffmix als Indikator.
        rows.append({
            "label": _label(sub_key),
            "Gas": gas / 1000.0,
            "Biomasse": biom / 1000.0,
            "Abwaerme": waste / 1000.0,
            "Wasserstoff": h2 / 1000.0,
            "Heizoel": oil / 1000.0,
            "Fernwaerme": dh / 1000.0,
        })

    if not rows:
        print("  Keine yearly-KPIs in summary.")
        return

    cats = ["Gas", "Biomasse", "Abwaerme", "Wasserstoff", "Heizoel", "Fernwaerme"]
    colors = ["#FF9800", "#8BC34A", "#9E9E9E", "#00BCD4", "#795548", "#F44336"]
    labels = [r["label"] for r in rows]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(max(9, 1.3 * len(labels)), 6))
    bottom = np.zeros(len(labels))
    for cat, col in zip(cats, colors):
        vals = np.array([r[cat] for r in rows])
        if not np.any(vals > 0):
            continue
        ax.bar(x, vals, 0.6, bottom=bottom, label=cat, color=col,
               edgecolor="white", linewidth=0.4)
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=10)
    ax.set_ylabel("Brennstoffbezug [MWh/a]")
    ax.set_title(f"Brennstoffmix — {reference_key}",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


def plot_autonomy_co2(grouped: Dict[str, Dict[str, Any]],
                       save_path: str,
                       reference_key: str) -> None:
    """
    Autonomie [%] und CO2-Emissionen [t/a] je BM.
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    rows = []
    for sub_key, run in bms.items():
        s = run["summary"]
        yr = _kpi_yearly(s)
        st = _kpi_static(s)
        years = (s.get("kpis") or {}).get("simulated_years") or []
        if not years:
            continue
        y = years[0]

        aut = (yr.get("energy_autonomy_year") or {}).get(y, 0)
        co2_v = (yr.get("co2emissions") or {}).get(y, 0)
        if isinstance(co2_v, dict):
            co2_v = co2_v.get("total_co2", 0)

        rows.append({
            "label": _label(sub_key),
            "bm_name": run["info"]["business_model"],
            "autonomy_pct": float(aut) * 100.0,
            "co2_t": float(co2_v),
        })

    if not rows:
        return

    fig, ax1 = plt.subplots(figsize=(max(9, 1.3 * len(rows)), 6))
    x = np.arange(len(rows))
    w = 0.35
    colors = [_bm_color(r["bm_name"]) for r in rows]

    ax1.bar(x - w / 2, [r["autonomy_pct"] for r in rows], w,
            color=colors, alpha=0.85, edgecolor="white",
            label="Autonomie")
    ax1.set_ylabel("Autonomie [%]", color="#1976D2")
    ax1.tick_params(axis="y", labelcolor="#1976D2")
    ax1.set_ylim(0, 100)

    ax2 = ax1.twinx()
    ax2.bar(x + w / 2, [r["co2_t"] for r in rows], w,
            color="#D32F2F", alpha=0.7, edgecolor="white",
            label="CO₂")
    ax2.set_ylabel("CO₂ [t/a]", color="#D32F2F")
    ax2.tick_params(axis="y", labelcolor="#D32F2F")

    ax1.set_xticks(x)
    ax1.set_xticklabels([r["label"] for r in rows], rotation=20, ha="right",
                        fontsize=10)
    ax1.set_title(f"Autonomie und CO₂ — {reference_key}",
                  fontsize=12, fontweight="bold")
    ax1.spines["top"].set_visible(False)
    ax2.spines["top"].set_visible(False)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=9)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# ══════════════════════════════════════════════════════════════════════
# 5) RANKING-HEATMAP (Gruppe D)
# ══════════════════════════════════════════════════════════════════════

def plot_ranking_heatmap(grouped: Dict[str, Dict[str, Any]],
                          save_path: str,
                          reference_key: str) -> None:
    """
    Heatmap mit normierten Bewertungen je BM und Kriterium.
    Kriterien: p_min (niedriger besser), p_max-Marge (groesser besser),
               NPV-Diff (groesser besser), CO2 (niedriger besser),
               Autonomie (hoeher besser), LCOH (niedriger besser).
    Werte werden je Kriterium auf [0,1] normiert (1 = bester BM).
    """
    bms = grouped[reference_key]["bms"]
    if not bms:
        return

    rows = []
    for sub_key, run in bms.items():
        s = run["summary"]
        st = _kpi_static(s)
        yr = _kpi_yearly(s)
        years = (s.get("kpis") or {}).get("simulated_years") or []
        y = years[0] if years else None

        p_min = st.get("p_min")
        p_max = st.get("p_max")
        margin = (p_max - p_min) if (p_min is not None and p_max is not None) else None

        co2 = None
        aut = None
        if y is not None:
            co2_v = (yr.get("co2emissions") or {}).get(y, None)
            if isinstance(co2_v, dict):
                co2_v = co2_v.get("total_co2", None)
            co2 = co2_v
            aut = (yr.get("energy_autonomy_year") or {}).get(y, None)

        rows.append({
            "label": _label(sub_key),
            "p_min":  p_min,
            "margin": margin,
            "npv_diff": st.get("npv_difference"),
            "co2":   co2,
            "autonomy": aut,
            "lcoh":  st.get("lcoh"),
        })

    # Kriterien
    crits = [
        ("p_min",    "p_min",   "min"),
        ("margin",   "p_max-p_min", "max"),
        ("npv_diff", "ΔNPV",    "max"),
        ("co2",      "CO₂",     "min"),
        ("autonomy", "Autonomie","max"),
        ("lcoh",     "LCOH",    "min"),
    ]

    n_bm = len(rows)
    n_cr = len(crits)
    M = np.full((n_bm, n_cr), np.nan)

    for j, (key, _, mode) in enumerate(crits):
        col = np.array([r[key] if r[key] is not None else np.nan for r in rows],
                       dtype=float)
        if np.all(np.isnan(col)):
            continue
        lo = np.nanmin(col); hi = np.nanmax(col)
        if hi == lo:
            norm = np.where(np.isnan(col), np.nan, 1.0)
        else:
            norm = (col - lo) / (hi - lo)
            if mode == "min":
                norm = 1.0 - norm
        M[:, j] = norm

    fig, ax = plt.subplots(figsize=(1.3 * n_cr + 3, 0.6 * n_bm + 2))
    im = ax.imshow(M, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(n_cr))
    ax.set_xticklabels([c[1] for c in crits], rotation=15, ha="right",
                       fontsize=10)
    ax.set_yticks(range(n_bm))
    ax.set_yticklabels([r["label"] for r in rows], fontsize=10)

    # Werte schreiben (Originalwerte, nicht normiert)
    for i, r in enumerate(rows):
        for j, (key, _, _) in enumerate(crits):
            v = r[key]
            if v is None:
                txt = "-"
            elif key in ("p_min", "margin", "lcoh"):
                txt = f"{v * 100:.2f} ct"
            elif key == "npv_diff":
                txt = f"{v / 1000:+,.0f} k€"
            elif key == "co2":
                txt = f"{v:.1f} t"
            elif key == "autonomy":
                txt = f"{v * 100:.1f}%"
            else:
                txt = f"{v:.2f}"
            ax.text(j, i, txt, ha="center", va="center",
                    fontsize=8, color="black")

    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("Score (1 = bester BM)", fontsize=9)

    ax.set_title(f"Ranking-Heatmap — {reference_key}",
                 fontsize=12, fontweight="bold")
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# ══════════════════════════════════════════════════════════════════════
# 6) ADAPTER FUER plots_bm_comparison.py (existierende Plots)
# ══════════════════════════════════════════════════════════════════════

def _make_pseudo_datahandler_from_summary(run: Dict[str, Any]) -> SimpleNamespace:
    """
    Baut einen Pseudo-Datahandler, der nur die Felder bereitstellt, die
    plots_bm_comparison erwartet:
      - .KPIs (mit allen relevanten yearly-Dicts und static Attributen)
      - .centralDevices["capacities"]
      - .district (Liste von Gebaeude-Dicts mit "capacities")
      - .ecoData
    """
    s = run["summary"]
    st = _kpi_static(s)
    yr = _kpi_yearly(s)

    # ----- KPIs Pseudo -----
    kpis_attrs = {}
    # static
    for k, v in st.items():
        kpis_attrs[k] = v
    # yearly als dicts
    for k, v in yr.items():
        kpis_attrs[k] = v
    # bm_breakdown durchreichen
    bd_all = (s.get("kpis") or {}).get("bm_breakdown") or {}
    for bd_key, bd_val in bd_all.items():
        kpis_attrs[bd_key] = bd_val

    kpis_pseudo = SimpleNamespace(**kpis_attrs)

    # ----- centralDevices -----
    central = (_capacities(s).get("central") or {})
    central_caps = {}
    for dev, dev_data in central.items():
        if not isinstance(dev_data, dict):
            continue
        # plots_bm_comparison liest "cap" -> Skalar nehmen
        if dev in _STORAGE_DEVS:
            cap_val = dev_data.get("cap_kWh", 0)
        elif dev in _AREA_DEVS:
            cap_val = dev_data.get("cap_m2", 0)
        else:
            cap_val = dev_data.get("cap_kW", 0)
        central_caps[dev] = {"cap": float(cap_val) if cap_val else 0.0}
    centralDevices = {"capacities": central_caps}

    # ----- district (dezentral) -----
    dec = (_capacities(s).get("decentral") or {})
    district_list = []
    if isinstance(dec, dict):
        # dec enthaelt z.B. {building_id: {device: {cap_kW: ...}}}
        for bldg_id, bldg_caps in dec.items():
            caps = {}
            if isinstance(bldg_caps, dict):
                for dev, dev_data in bldg_caps.items():
                    if not isinstance(dev_data, dict):
                        continue
                    if dev in _AREA_DEVS:
                        caps[dev] = {"area": dev_data.get("cap_m2", 0)}
                    else:
                        caps[dev] = {"cap": dev_data.get("cap_kW",
                                          dev_data.get("cap_kWh", 0))}
            district_list.append({"capacities": caps,
                                  "buildingFeatures": {"unique_name": bldg_id}})

    pseudo = SimpleNamespace(
        KPIs=kpis_pseudo,
        centralDevices=centralDevices,
        district=district_list,
        ecoData=_eco_static(s),
        scenario_name=(s.get("metadata") or {}).get("scenario_name"),
        resultPath=os.path.dirname(run["summary_path"]),
    )
    return pseudo


def run_plots_bm_comparison_adapter(grouped: Dict[str, Dict[str, Any]],
                                     save_dir: str,
                                     reference_key: str) -> None:
    """
    Erzeugt die existierenden plots_bm_comparison-Plots ueber Pseudo-Datahandler.
    Verwendet KPIs/Capacities aus summary.pkl — keine Neuberechnung.
    """
    try:
        from plots_bm_comparison import plot_bm_economics
    except ImportError as e:
        print(f"[adapter] plots_bm_comparison nicht verfuegbar: {e}")
        return

    bms = grouped[reference_key]["bms"]
    ref_run = grouped[reference_key].get("reference")

    pseudo_results = {}
    if ref_run is not None:
        pseudo_results["reference"] = _make_pseudo_datahandler_from_summary(ref_run)
    for sub_key, run in bms.items():
        # plots_bm_comparison erwartet flachen Namen -> bm_name + flag
        flat = run["info"]["business_model"]
        if run["info"]["scenario_flag"]:
            flat = f"{flat}_{run['info']['scenario_flag']}"
        pseudo_results[flat] = _make_pseudo_datahandler_from_summary(run)

    out_dir = os.path.join(save_dir, "bm_comparison_legacy")
    os.makedirs(out_dir, exist_ok=True)
    plot_bm_economics(pseudo_results, save_dir=out_dir)


# ══════════════════════════════════════════════════════════════════════
# 7) HAUPT-RUNNER
# ══════════════════════════════════════════════════════════════════════

def run(scenario_variant: str = "H01",
        result_root: str = RESULT_ROOT,
        results_subfolder: str = RESULTS_SUBFOLDER,
        plots_subfolder: str = PLOTS_SUBFOLDER,
        use_legacy_adapter: bool = False,
        do_load_plots: bool = False,
        do_central_plots: bool = True) -> None:
    """
    Vollstaendiger Plot-Lauf fuer ein Szenario-Variant (z.B. 'H01').

    Erzeugt fuer JEDE gefundene Referenz (ref_boi, ref_wp) einen Plot-Satz
    in <result_root>/<plots_subfolder>/<scenario_variant>/<reference_key>/.
    """
    results_dir = os.path.join(result_root, results_subfolder, scenario_variant)
    plots_dir   = os.path.join(result_root, plots_subfolder, scenario_variant)
    print(f"\n{'#' * 60}\n# RUN PLOTS — {scenario_variant}\n{'#' * 60}")
    print(f"  results_dir : {results_dir}")
    print(f"  plots_dir   : {plots_dir}")

    runs = load_all_runs(results_dir)
    if not runs:
        print("  Keine Runs gefunden — Abbruch.")
        return

    grouped = group_by_reference(runs)
    print(f"\nGefundene Referenzen: {list(grouped.keys())}\n")

    for ref_key, group in grouped.items():
        if not group["bms"]:
            print(f"[{ref_key}] keine BMs — uebersprungen.")
            continue

        sub = os.path.join(plots_dir, ref_key)
        os.makedirs(sub, exist_ok=True)
        print(f"\n--- {ref_key}  ({len(group['bms'])} BMs) ---")

        # Bewertungslogik: nur Gesamtquartier-NPV fuer Kategorie B
        plot_npv_difference_quartier_B(
            grouped,
            os.path.join(sub, "02_npv_difference_quartier_B.pdf"),
            ref_key,
        )

        # Legacy-Adapter (existierende plots_bm_comparison)
        if use_legacy_adapter:
            run_plots_bm_comparison_adapter(grouped, sub, ref_key)

    # Lastprofil-Plots G1-G4 (timeseries-basiert), referenzuebergreifend
    if do_load_plots and _HAS_LOAD_PLOTS:
        print("\n--- Lastprofile G1-G4 ---")
        run_load_plots(grouped, plots_dir)

    # Zentrale Plots C1-C4
    if do_central_plots and _HAS_CENTRAL_PLOTS:
        print("\n--- Zentrale Plots C1-C4 ---")
        run_central_plots(grouped, plots_dir)

    print(f"\n{'#' * 60}\n# DONE — Plots in {plots_dir}\n{'#' * 60}")


# ══════════════════════════════════════════════════════════════════════
# 8) STUFE 2 (PLATZHALTER): Bilanzen pro BM aus timeseries.pkl
# ══════════════════════════════════════════════════════════════════════

def run_balances_per_bm(scenario_variant: str = "H01",
                         result_root: str = RESULT_ROOT,
                         results_subfolder: str = RESULTS_SUBFOLDER,
                         plots_subfolder: str = PLOTS_SUBFOLDER) -> None:
    """
    Optionaler zweiter Schritt:
    Erzeugt die EH-/Gebaeude-/Distrikt-Bilanzplots aus plots_balances.py
    pro BM aus den timeseries-pkl. Implementierung folgt sobald
    plots_balances-Adapter feststeht (separates Modul).
    """
    print("[run_balances_per_bm] noch nicht implementiert — Stufe 2.")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    SCENARIO_VARIANT = "H01"
    run(scenario_variant=SCENARIO_VARIANT, use_legacy_adapter=True)