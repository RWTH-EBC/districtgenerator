# -*- coding: utf-8 -*-
"""
run_plots_focused.py

Fokussierter Plot-Runner fuer BM-Summary-PKLs.

Erzeugt nur die besprochenen Auswertungen:

P0  Trafo-/Stromnetz-Diagnose als CSV
P1  Technologiemix zentraler Energiehub: Erzeuger und Speicher in EINEM Plot
    mit zwei y-Achsen (links kW/kWp, rechts kWh)
P2  Szenario B / Anschlusszwang: Quartiers-NPV Ref vs. BM, p_min/p_max_B
    und Betreiber-NPV bei p_max_B
P3  Szenario A: NPV-Tabelle je Haus und BM (PDF + CSV)
P4  Szenario A: Anzahl anschliessbarer Haeuser, p_max_A und Betreiber-NPV

Keine Optimierung. Keine Rechenlaeufe. Nur summary_*.pkl lesen.

Aufruf:
    python run_plots_focused.py

Oder in Python:
    from run_plots_focused import run
    run(scenario_variant="A01")
"""

from __future__ import annotations

import csv
import glob
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D


# =====================================================================
# Pfade anpassen
# =====================================================================

RESULT_ROOT = r"C:\Users\rha-csa\PycharmProjects\districtgenerator\districtgenerator\results"
RESULTS_SUBFOLDER = "bm_results"
PLOTS_SUBFOLDER = "bm_plots"

# Zum lokalen Test kann man RESULT_ROOT auch direkt auf einen Ordner mit
# summary_*.pkl setzen und results_subfolder="", scenario_variant="" nutzen.


# =====================================================================
# Farben / Konstanten
# =====================================================================

STORAGE_DEVS = ("TES", "CTES", "BAT", "H2S", "GS")
AREA_DEVS = ("PV", "STC")

GEN_DEVS = (
    "BOI", "BBOI", "WBOI", "HP", "GHP", "EB",
    "CHP", "BCHP", "WCHP", "FC", "PV", "STC", "WT", "WAT", "ELYZ",
)

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
    "waermecontracting": "Contracting",
    "waermecontracting_ggv": "GGV",
    "waermecontracting_kundenanlage": "Kundenanlage",
    "waermegenossenschaft": "Genossenschaft",
    "ref_boi": "Referenz BOI",
    "ref_wp": "Referenz WP",
}


# =====================================================================
# Laden / Gruppieren
# =====================================================================

def _load_pkl(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        return pickle.load(f)


def _parse_summary_name(filename: str) -> Dict[str, Optional[str]]:
    """
    Erlaubte Namen:
      summary_<scenario>_<ref_boi|ref_wp>.pkl
      summary_<scenario>_bm_<ref_boi|ref_wp>_<bm>_<A|B>.pkl
      summary_<scenario>_<ref_boi|ref_wp>_<bm>_<A|B>.pkl

    Robust: sucht einfach die Tokenfolge ref_boi/ref_wp.
    """
    stem = os.path.basename(filename).replace(".pkl", "")
    if not stem.startswith("summary_"):
        return {}
    stem = stem[len("summary_"):]
    parts = stem.split("_")

    # Position von ref_boi/ref_wp finden
    ref_i = None
    for i, p in enumerate(parts[:-1]):
        if p == "ref" and parts[i + 1] in ("boi", "wp"):
            ref_i = i
            break
    if ref_i is None:
        return {}

    ref_key = "_".join(parts[ref_i:ref_i + 2])

    # BM-Run: endet auf A/B
    if parts[-1] in ("A", "B"):
        flag = parts[-1]
        bm = "_".join(parts[ref_i + 2:-1])
        scenario_tokens = parts[:ref_i]
        # optionales Hilfstoken "bm" aus dem Szenarionamen entfernen
        if scenario_tokens and scenario_tokens[-1] == "bm":
            scenario_tokens = scenario_tokens[:-1]
        return {
            "scenario_name": "_".join(scenario_tokens),
            "reference_key": ref_key,
            "business_model": bm,
            "scenario_flag": flag,
            "kind": "bm",
        }

    # Referenz-Run
    scenario_tokens = parts[:ref_i]
    if scenario_tokens and scenario_tokens[-1] == "ref":
        scenario_tokens = scenario_tokens[:-1]
    return {
        "scenario_name": "_".join(scenario_tokens),
        "reference_key": ref_key,
        "business_model": ref_key,
        "scenario_flag": None,
        "kind": "reference",
    }


def load_runs(results_dir: str) -> Dict[str, Dict[str, Any]]:
    files = sorted(glob.glob(os.path.join(results_dir, "summary_*.pkl")))
    out: Dict[str, Dict[str, Any]] = {}
    if not files:
        print(f"[run_plots_focused] Keine summary_*.pkl in {results_dir}")
        return out

    for fp in files:
        info = _parse_summary_name(fp)
        if not info:
            print(f"[WARN] Dateiname nicht erkannt: {os.path.basename(fp)}")
            continue
        if info["kind"] == "reference":
            key = info["reference_key"]
        else:
            key = f"{info['reference_key']}__{info['business_model']}__{info['scenario_flag']}"
        out[key] = {
            "summary": _load_pkl(fp),
            "info": info,
            "summary_path": fp,
        }
    print(f"[run_plots_focused] Geladen: {len(out)} summary-runs")
    return out


def group_by_reference(runs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for key, run in runs.items():
        info = run["info"]
        ref = info["reference_key"]
        grouped.setdefault(ref, {"reference": None, "bms": {}})
        if info["kind"] == "reference":
            grouped[ref]["reference"] = run
        else:
            sub = f"{info['business_model']}__{info['scenario_flag']}"
            grouped[ref]["bms"][sub] = run
    return grouped


# =====================================================================
# Zugriffshilfen
# =====================================================================

def _kpis(s: Dict[str, Any]) -> Dict[str, Any]:
    return s.get("kpis") or {}


def _bm_breakdown(s: Dict[str, Any]) -> Dict[str, Any]:
    bd = (_kpis(s).get("bm_breakdown") or {})
    return bd.get("bm_breakdown") or {}


def _yearly(s: Dict[str, Any]) -> Dict[str, Any]:
    return _kpis(s).get("yearly") or {}


def _static(s: Dict[str, Any]) -> Dict[str, Any]:
    return _kpis(s).get("static") or {}


def _capacities(s: Dict[str, Any]) -> Dict[str, Any]:
    return s.get("capacities") or {}


def _central_raw(s: Dict[str, Any]) -> Dict[str, Any]:
    return (_capacities(s).get("central_raw") or {})


def _device_costs(s: Dict[str, Any]) -> Dict[str, Any]:
    # In den Summary-Dateien liegt device_costs unter kpis.device_costs.
    return _kpis(s).get("device_costs") or s.get("device_costs") or {}


def _label(sub_key: str, run: Optional[Dict[str, Any]] = None) -> str:
    if run is not None and run["info"].get("kind") == "reference":
        return BM_PRETTY.get(run["info"].get("reference_key"), run["info"].get("reference_key"))
    if "__" in sub_key:
        bm, flag = sub_key.split("__", 1)
    else:
        bm, flag = sub_key, ""
    base = BM_PRETTY.get(bm, bm.replace("_", " ").title())
    return f"{base} ({flag})" if flag else base


def _smart_unit_eur(values: List[float]) -> Tuple[float, str]:
    vals = [abs(float(v)) for v in values if v is not None and np.isfinite(float(v))]
    m = max(vals) if vals else 0.0
    if m >= 1_000_000:
        return 1e-6, "Mio. EUR"
    if m >= 10_000:
        return 1e-3, "kEUR"
    return 1.0, "EUR"


def _pvaf(summary: Dict[str, Any]) -> float:
    md = summary.get("metadata") or {}
    eco = summary.get("eco") or {}
    eco_static = eco.get("static") if isinstance(eco, dict) else {}
    n = int(md.get("observation_time") or (eco_static or {}).get("observation_time") or 20)
    i = float((eco_static or {}).get("interest_rate") or 0.05)
    q = 1.0 + i
    if abs(i) < 1e-12:
        return float(n)
    # Konvention wie BusinessModelBase._present_value_factor: Jahre 0..n-1
    return (1.0 - (1.0 / q) ** n) / (1.0 - 1.0 / q)


def _fmt_num(v: Any, digits: int = 2) -> str:
    if v is None:
        return ""
    try:
        if not np.isfinite(float(v)):
            return ""
        return f"{float(v):.{digits}f}"
    except Exception:
        return str(v)


def _scenario_block(run: Dict[str, Any], flag: str) -> Dict[str, Any]:
    bd = _bm_breakdown(run["summary"])
    return bd.get(f"scenario_{flag.lower()}") or {}


def _building_details(run: Dict[str, Any], flag: str) -> Dict[Any, Dict[str, Any]]:
    return _scenario_block(run, flag).get("building_details") or {}


def _natural_key(x: Any) -> List[Any]:
    s = str(x)
    out: List[Any] = []
    buf = ""
    for ch in s:
        if ch.isdigit():
            buf += ch
        else:
            if buf:
                out.append(int(buf)); buf = ""
            out.append(ch.lower())
    if buf:
        out.append(int(buf))
    return out


def _aggregate_npv(run: Dict[str, Any], flag: str) -> Dict[str, Optional[float]]:
    """Summe ueber Gebaeude; Fallback auf aggregierte Felder."""
    sc = _scenario_block(run, flag)
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
        npv_bm += float(a)
        npv_ref += float(r)
        n += 1
    if n > 0:
        return {"npv_bm": npv_bm, "npv_ref": npv_ref, "diff": npv_bm - npv_ref}

    a = sc.get("sum_npv_wn_at_price")
    r = sc.get("sum_npv_ref")
    if a is None or r is None:
        return {"npv_bm": None, "npv_ref": None, "diff": None}
    return {"npv_bm": float(a), "npv_ref": float(r), "diff": float(a) - float(r)}


def _connected_info(run: Dict[str, Any], flag: str) -> Tuple[int, int, List[Any], List[Any]]:
    sc = _scenario_block(run, flag)
    connected = sc.get("connected") or sc.get("connected_buildings") or []
    excluded = sc.get("excluded") or []
    details = sc.get("building_details") or {}
    if not connected and not excluded and details:
        # Wenn keine explizite Liste gespeichert ist: alle Details als betrachtete Gebaeude.
        connected = list(details.keys())
    total = len(set(list(connected) + list(excluded))) if (connected or excluded) else len(details)
    return len(connected), total, list(connected), list(excluded)


def _price_info(run: Dict[str, Any], flag: str) -> Dict[str, Optional[float]]:
    s = run["summary"]
    bd = _bm_breakdown(s)
    sc = _scenario_block(run, flag)
    p_min = bd.get("p_min") or _static(s).get("p_min")
    if flag.upper() == "A":
        p_max = sc.get("p_max")
        if p_max is None:
            p_max = bd.get("p_max_a")
    else:
        p_max = sc.get("p_max")
        if p_max is None:
            p_max = bd.get("p_max_b")
        if p_max is None:
            p_max = bd.get("p_max") or _static(s).get("p_max")
    return {"p_min": float(p_min) if p_min is not None else None,
            "p_max": float(p_max) if p_max is not None else None}


def _operator_npv_at_price(run: Dict[str, Any], flag: str, p_eval: Optional[float]) -> Optional[float]:
    """
    Betreiber-NPV bei Preis p_eval.

    Grundlage: p_min ist der Preis, bei dem Betreiber-NPV = 0.
      NPV_operator(p_eval) = (p_eval - p_min) * Barwert_Waermemenge

    Fuer A wird die Barwert-Waermemenge aus den verbundenen building_details
    approximiert, falls keine spezifische BW-Menge vorhanden ist.
    """
    if p_eval is None:
        return None
    s = run["summary"]
    bd = _bm_breakdown(s)
    p_min = bd.get("p_min") or _static(s).get("p_min")
    if p_min is None:
        return None
    p_min = float(p_min)

    bw_heat = None
    # Szenario B: in den Breakdowns meist direkt vorhanden.
    if flag.upper() == "B":
        bw_heat = bd.get("bw_heat_total")

    # Szenario A: wenn p_max_A auf angeschlossene Haeuser bezogen ist,
    # besser deren Jahreswaermebedarf * PVAF verwenden.
    if bw_heat is None or flag.upper() == "A":
        details = _building_details(run, flag)
        connected = set(_scenario_block(run, flag).get("connected") or _scenario_block(run, flag).get("connected_buildings") or details.keys())
        heat_kwh = 0.0
        for bid, det in details.items():
            if bid not in connected and str(bid) not in {str(x) for x in connected}:
                continue
            if isinstance(det, dict) and det.get("heat_kWh") is not None:
                heat_kwh += float(det.get("heat_kWh") or 0.0)
        if heat_kwh > 0:
            bw_heat = heat_kwh * _pvaf(s)

    if bw_heat is None:
        bw_heat = bd.get("bw_heat_total")
    if bw_heat is None:
        return None
    return (float(p_eval) - p_min) * float(bw_heat)


# =====================================================================
# P0 - Trafo Diagnose
# =====================================================================

def write_trafo_diagnostics(grouped: Dict[str, Dict[str, Any]], out_dir: str, ref_key: str) -> None:
    rows = []
    group = grouped[ref_key]
    all_runs = []
    if group.get("reference"):
        all_runs.append((ref_key, group["reference"]))
    all_runs += list((group.get("bms") or {}).items())

    for key, run in all_runs:
        s = run["summary"]
        bd = _bm_breakdown(s)
        cr = _central_raw(s)
        info = run["info"]
        c_elgrid = bd.get("c_elgrid_ann")
        trafo_bd = bd.get("trafo_ann_from_milp")
        chosen = cr.get("trafo_chosen_kVA")
        ann = cr.get("trafo_ann_cost_eur_per_a")
        inv = cr.get("trafo_inv_eur")
        status = ""
        if info.get("business_model") == "waermecontracting_kundenanlage":
            if not chosen or float(chosen or 0.0) <= 0.0:
                status = "WARNUNG: Kundenanlage ohne gewaehlten Trafo"
            elif not ann or float(ann or 0.0) <= 0.0:
                status = "WARNUNG: Trafo-kVA vorhanden, aber Annuitaet 0"
            else:
                status = "Trafo-Ergebnis vorhanden"
        rows.append({
            "run": _label(key, run),
            "business_model": info.get("business_model"),
            "scenario_flag": info.get("scenario_flag") or "",
            "c_elgrid_ann_EUR_a": c_elgrid,
            "trafo_ann_from_milp_EUR_a": trafo_bd,
            "central_raw_trafo_chosen_kVA": chosen,
            "central_raw_trafo_inv_EUR": inv,
            "central_raw_trafo_ann_EUR_a": ann,
            "trafo_sizing_summary_in_summary": "ja" if bd.get("trafo_sizing_summary") is not None else "nein",
            "status": status,
        })

    path = os.path.join(out_dir, "P0_trafo_diagnose.csv")
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        cols = list(rows[0].keys()) if rows else []
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    print(f"  Saved: {path}")


# =====================================================================
# P1 - Technologie-Mix mit zwei y-Achsen
# =====================================================================

def _capacity_records(group: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = []
    if group.get("reference"):
        records.append((group["reference"]["info"]["reference_key"], group["reference"]))
    records += list((group.get("bms") or {}).items())

    out = []
    for key, run in records:
        s = run["summary"]
        central = (_capacities(s).get("central") or {})
        rec = {"key": key, "label": _label(key, run), "gen": {}, "storage": {}, "area": {}}
        for dev, dd in central.items():
            if not isinstance(dd, dict):
                continue
            if dev in STORAGE_DEVS:
                v = dd.get("cap_kWh")
                if v and float(v) > 0:
                    rec["storage"][dev] = float(v)
            elif dev in AREA_DEVS:
                # Wenn kWp/kW_peak vorhanden ist: auf der Erzeugerachse zeigen.
                v = dd.get("cap_kW") or dd.get("cap_kW_peak")
                if v and float(v) > 0:
                    rec["gen"][dev] = float(v)
                # m2 separat in CSV, nicht in den twin-axis Plot mischen.
                m2 = dd.get("cap_m2")
                if m2 and float(m2) > 0:
                    rec["area"][dev] = float(m2)
            else:
                v = dd.get("cap_kW")
                if v and float(v) > 0:
                    rec["gen"][dev] = float(v)
        out.append(rec)
    return out


def plot_tech_mix(grouped: Dict[str, Dict[str, Any]], out_dir: str, ref_key: str) -> None:
    rows = _capacity_records(grouped[ref_key])
    if not rows:
        return

    gen_devs = []
    sto_devs = []
    for r in rows:
        for d in r["gen"]:
            if d not in gen_devs:
                gen_devs.append(d)
        for d in r["storage"]:
            if d not in sto_devs:
                sto_devs.append(d)

    # CSV
    csv_path = os.path.join(out_dir, "P1_tech_mix_erzeuger_speicher.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        cols = ["run", "typ", "geraet", "wert", "einheit"]
        w = csv.writer(f); w.writerow(cols)
        for r in rows:
            for d, v in r["gen"].items():
                unit = "kWp" if d in ("PV", "STC") else "kW"
                w.writerow([r["label"], "Erzeuger", d, f"{v:.6g}", unit])
            for d, v in r["storage"].items():
                w.writerow([r["label"], "Speicher", d, f"{v:.6g}", "kWh"])
            for d, v in r["area"].items():
                w.writerow([r["label"], "Flaeche_nicht_im_Plot", d, f"{v:.6g}", "m2"])
    print(f"  Saved: {csv_path}")

    if not gen_devs and not sto_devs:
        print(f"  [P1 {ref_key}] keine zentralen Kapazitaeten gefunden")
        return

    labels = [r["label"] for r in rows]
    x = np.arange(len(rows))
    width = 0.34
    x_gen = x - width / 2
    x_sto = x + width / 2

    fig, ax_g = plt.subplots(figsize=(max(10, 1.5 * len(rows)), 6.4))
    ax_s = ax_g.twinx()

    bottom_g = np.zeros(len(rows))
    for d in gen_devs:
        vals = np.array([r["gen"].get(d, 0.0) for r in rows])
        if not np.any(vals > 0):
            continue
        ax_g.bar(x_gen, vals, width, bottom=bottom_g,
                 color=TECH_COLORS.get(d, "#9E9E9E"), edgecolor="white", linewidth=0.4,
                 label=d)
        bottom_g += vals

    bottom_s = np.zeros(len(rows))
    for d in sto_devs:
        vals = np.array([r["storage"].get(d, 0.0) for r in rows])
        if not np.any(vals > 0):
            continue
        ax_s.bar(x_sto, vals, width, bottom=bottom_s,
                 color=TECH_COLORS.get(d, "#9E9E9E"), edgecolor="white", linewidth=0.4,
                 label=f"{d} Speicher")
        bottom_s += vals

    for i, v in enumerate(bottom_g):
        if v > 0:
            ax_g.text(x_gen[i], v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8, color="#1565C0")
    for i, v in enumerate(bottom_s):
        if v > 0:
            ax_s.text(x_sto[i], v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8, color="#AD1457")

    ax_g.set_xticks(x)
    ax_g.set_xticklabels(labels, rotation=18, ha="right")
    ax_g.set_ylabel("Erzeugerleistung [kW / kWp]", color="#1565C0")
    ax_s.set_ylabel("Speicherkapazitaet [kWh]", color="#AD1457")
    ax_g.tick_params(axis="y", labelcolor="#1565C0")
    ax_s.tick_params(axis="y", labelcolor="#AD1457")
    ax_g.grid(axis="y", alpha=0.25)
    ax_g.set_title(f"Technologiemix zentraler Energiehub - Erzeuger und Speicher ({ref_key})", fontweight="bold")
    ax_g.spines["top"].set_visible(False)
    ax_s.spines["top"].set_visible(False)

    h1, l1 = ax_g.get_legend_handles_labels()
    h2, l2 = ax_s.get_legend_handles_labels()
    ax_g.legend(h1 + h2, l1 + l2, loc="upper left", bbox_to_anchor=(0, -0.18),
                ncol=min(4, max(1, len(l1 + l2))), fontsize=9,
                framealpha=0.9, edgecolor="#D0D0D0")
    fig.tight_layout()
    path = os.path.join(out_dir, "P1_tech_mix_erzeuger_speicher.pdf")
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# =====================================================================
# P2 - Szenario B: Quartiers-NPV + Preislogik
# =====================================================================

def plot_scenario_B(grouped: Dict[str, Dict[str, Any]], out_dir: str, ref_key: str) -> None:
    rows = []
    for sub_key, run in (grouped[ref_key].get("bms") or {}).items():
        if run["info"].get("scenario_flag") != "B":
            continue
        npv = _aggregate_npv(run, "B")
        pi = _price_info(run, "B")
        p_min = pi["p_min"]
        p_max = pi["p_max"]
        op_npv = _operator_npv_at_price(run, "B", p_max)
        feasible = (p_min is not None and p_max is not None and p_min <= p_max)
        n_conn, n_total, _, _ = _connected_info(run, "B")
        rows.append({
            "run": _label(sub_key, run),
            "bm": run["info"].get("business_model"),
            "n_connected": n_conn,
            "n_total": n_total,
            "npv_ref": npv["npv_ref"],
            "npv_bm": npv["npv_bm"],
            "npv_diff": npv["diff"],
            "p_min": p_min,
            "p_max_B": p_max,
            "operator_npv_at_pmax_B": op_npv,
            "wirtschaftlich": feasible,
        })

    if not rows:
        print(f"  [P2 {ref_key}] keine B-Runs")
        return

    # CSV
    csv_path = os.path.join(out_dir, "P2_szenario_B_quartier_npv_preis.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        cols = [
            "run", "n_connected", "n_total", "NPV_ref_EUR", "NPV_BM_EUR", "Diff_EUR",
            "p_min_ct_per_kWh", "p_max_B_ct_per_kWh", "operator_NPV_at_pmax_B_EUR", "wirtschaftlich",
        ]
        w = csv.writer(f); w.writerow(cols)
        for r in rows:
            w.writerow([
                r["run"], r["n_connected"], r["n_total"],
                _fmt_num(r["npv_ref"]), _fmt_num(r["npv_bm"]), _fmt_num(r["npv_diff"]),
                _fmt_num(r["p_min"] * 100 if r["p_min"] is not None else None, 4),
                _fmt_num(r["p_max_B"] * 100 if r["p_max_B"] is not None else None, 4),
                _fmt_num(r["operator_npv_at_pmax_B"]),
                "ja" if r["wirtschaftlich"] else "nicht wirtschaftlich",
            ])
    print(f"  Saved: {csv_path}")

    vals = [v for r in rows for v in (r["npv_ref"], r["npv_bm"], r["npv_diff"], r["operator_npv_at_pmax_B"]) if v is not None]
    factor, unit = _smart_unit_eur(vals if vals else [0.0])

    labels = [r["run"] for r in rows]
    x = np.arange(len(rows))
    wbar = 0.26

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(max(10, 1.6 * len(rows)), 8.6), gridspec_kw={"height_ratios": [1.2, 1]})

    ref_vals = np.array([(r["npv_ref"] or 0.0) * factor for r in rows])
    bm_vals = np.array([(r["npv_bm"] or 0.0) * factor for r in rows])
    diff_vals = np.array([(r["npv_diff"] or 0.0) * factor for r in rows])
    ax1.bar(x - wbar, ref_vals, wbar, color="#607D8B", edgecolor="white", label="Σ NPV_ref")
    ax1.bar(x, bm_vals, wbar, color="#1565C0", edgecolor="white", label="Σ NPV_BM")
    diff_cols = ["#2E7D32" if (r["npv_diff"] or 0) >= 0 else "#C62828" for r in rows]
    ax1.bar(x + wbar, diff_vals, wbar, color=diff_cols, edgecolor="white", label="Δ BM-ref")
    ax1.axhline(0, color="black", lw=0.7)
    ax1.set_ylabel(f"NPV [{unit}]")
    ax1.set_title(f"Szenario B: Gesamtquartier-NPV und Preislogik ({ref_key})", fontweight="bold")
    ax1.grid(axis="y", alpha=0.25)
    ax1.legend(ncol=3, loc="upper left")
    ax1.set_xticks(x); ax1.set_xticklabels(labels, rotation=12, ha="right")

    for i, r in enumerate(rows):
        if r["npv_diff"] is not None:
            v = diff_vals[i]
            ax1.text(x[i] + wbar, v, f"{v:+,.2f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=8)

    p_min_ct = np.array([(r["p_min"] * 100) if r["p_min"] is not None else np.nan for r in rows])
    p_max_ct = np.array([(r["p_max_B"] * 100) if r["p_max_B"] is not None else np.nan for r in rows])
    op_vals = np.array([(r["operator_npv_at_pmax_B"] or 0.0) * factor for r in rows])
    y = np.arange(len(rows))
    for i, r in enumerate(rows):
        if np.isfinite(p_min_ct[i]) and np.isfinite(p_max_ct[i]):
            lo = min(p_min_ct[i], p_max_ct[i]); hi = max(p_min_ct[i], p_max_ct[i])
            col = "#2E7D32" if r["wirtschaftlich"] else "#C62828"
            ax2.plot([lo, hi], [i, i], color=col, lw=5, alpha=0.65)
            ax2.scatter([p_min_ct[i]], [i], color="#1B5E20", s=55, zorder=3)
            ax2.scatter([p_max_ct[i]], [i], color="#B71C1C", s=55, zorder=3)
            txt = f"Betreiber-NPV @p_max: {op_vals[i]:+,.2f} {unit}"
            if not r["wirtschaftlich"]:
                txt = "nicht wirtschaftlich | " + txt
            ax2.text(hi + 0.3, i, txt, va="center", ha="left", fontsize=9, color=col)
        else:
            ax2.text(0, i, "p_min/p_max fehlt", va="center", ha="left", fontsize=9, color="#616161")

    ax2.set_yticks(y); ax2.set_yticklabels(labels)
    ax2.invert_yaxis()
    ax2.set_xlabel("Waermepreis [ct/kWh]  |  gruen: p_min, rot: p_max_B")
    ax2.grid(axis="x", alpha=0.25)
    ax2.spines["top"].set_visible(False); ax2.spines["right"].set_visible(False)
    ax2.legend(handles=[
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#1B5E20", markersize=8, label="p_min"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#B71C1C", markersize=8, label="p_max_B"),
    ], loc="lower right")

    plt.tight_layout()
    path = os.path.join(out_dir, "P2_szenario_B_quartier_npv_preis.pdf")
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# =====================================================================
# P3 - Szenario A Haus-Tabelle
# =====================================================================

def _a_table_rows(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    sc = _scenario_block(run, "A")
    details = sc.get("building_details") or {}
    connected = set(str(x) for x in (sc.get("connected") or sc.get("connected_buildings") or []))
    excluded = set(str(x) for x in (sc.get("excluded") or []))
    out = []
    for bid, det in details.items():
        if not isinstance(det, dict):
            continue
        npv_ref = det.get("npv_ref")
        npv_bm = det.get("npv_wn_at_price")
        diff = None if npv_ref is None or npv_bm is None else float(npv_bm) - float(npv_ref)
        bid_s = str(bid)
        status = "angeschlossen" if (not connected or bid_s in connected) and bid_s not in excluded else "ausgeschlossen"
        out.append({
            "building": bid,
            "heat_kWh": det.get("heat_kWh"),
            "NPV_ref": npv_ref,
            "NPV_BM": npv_bm,
            "Diff": diff,
            "p_max_i": det.get("p_max"),
            "economic": det.get("economic_at_price", det.get("economic_for_building")),
            "status": status,
        })
    out.sort(key=lambda r: _natural_key(r["building"]))
    return out


def export_scenario_A_tables(grouped: Dict[str, Dict[str, Any]], out_dir: str, ref_key: str) -> None:
    bms = grouped[ref_key].get("bms") or {}
    a_runs = [(k, r) for k, r in bms.items() if r["info"].get("scenario_flag") == "A"]
    if not a_runs:
        print(f"  [P3 {ref_key}] keine A-Runs")
        return

    csv_path = os.path.join(out_dir, "P3_szenario_A_haus_npv_tabelle.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run", "building", "status", "heat_MWh_a", "NPV_ref_EUR", "NPV_BM_EUR", "Diff_EUR", "p_max_i_ct_per_kWh", "wirtschaftlich"])
        for key, run in a_runs:
            for r in _a_table_rows(run):
                w.writerow([
                    _label(key, run), r["building"], r["status"],
                    _fmt_num((r["heat_kWh"] or 0) / 1000.0 if r["heat_kWh"] is not None else None),
                    _fmt_num(r["NPV_ref"]), _fmt_num(r["NPV_BM"]), _fmt_num(r["Diff"]),
                    _fmt_num(r["p_max_i"] * 100 if r["p_max_i"] is not None else None, 4),
                    "ja" if r["economic"] is True else "nein" if r["economic"] is False else "",
                ])
    print(f"  Saved: {csv_path}")

    pdf_path = os.path.join(out_dir, "P3_szenario_A_haus_npv_tabelle.pdf")
    with PdfPages(pdf_path) as pdf:
        for key, run in a_runs:
            rows = _a_table_rows(run)
            label = _label(key, run)
            sc = _scenario_block(run, "A")
            reason = sc.get("reason") or ""
            vals = [v for r in rows for v in (r["NPV_ref"], r["NPV_BM"], r["Diff"]) if v is not None]
            factor, unit = _smart_unit_eur(vals if vals else [0.0])

            table = []
            for r in rows:
                table.append([
                    str(r["building"]),
                    r["status"],
                    f"{(r['heat_kWh'] or 0)/1000.0:,.2f}" if r["heat_kWh"] is not None else "-",
                    f"{float(r['NPV_ref'])*factor:,.2f}" if r["NPV_ref"] is not None else "-",
                    f"{float(r['NPV_BM'])*factor:,.2f}" if r["NPV_BM"] is not None else "-",
                    f"{float(r['Diff'])*factor:+,.2f}" if r["Diff"] is not None else "-",
                    f"{float(r['p_max_i'])*100:,.2f}" if r["p_max_i"] is not None else "-",
                    "ja" if r["economic"] is True else "nein" if r["economic"] is False else "-",
                ])

            headers = ["Haus", "Status", "Waerme\n[MWh/a]", f"NPV_ref\n[{unit}]", f"NPV_BM\n[{unit}]", f"Diff\n[{unit}]", "p_max,i\n[ct/kWh]", "wirtsch."]
            fig_h = max(4.5, 0.35 * (len(table) + 1) + 1.5)
            fig, ax = plt.subplots(figsize=(12.5, fig_h))
            ax.axis("off")
            title = f"Szenario A: NPV-Tabelle je Haus - {label}"
            if reason:
                title += f"\nHinweis: {reason}"
            ax.set_title(title, fontweight="bold", fontsize=12, pad=10)
            tbl = ax.table(cellText=table, colLabels=headers, cellLoc="center", loc="center")
            tbl.auto_set_font_size(False); tbl.set_fontsize(8.5); tbl.scale(1.0, 1.28)
            for j in range(len(headers)):
                c = tbl[0, j]; c.set_facecolor("#37474F"); c.set_text_props(color="white", fontweight="bold")
            for i, r in enumerate(rows):
                # Status und Diff markieren
                if r["status"] == "ausgeschlossen":
                    for j in range(len(headers)):
                        tbl[i + 1, j].set_facecolor("#EEEEEE")
                else:
                    d = r["Diff"]
                    if d is not None:
                        tbl[i + 1, 5].set_facecolor("#C8E6C9" if d >= 0 else "#FFCDD2")
                    if r["economic"] is True:
                        tbl[i + 1, 7].set_facecolor("#C8E6C9")
                    elif r["economic"] is False:
                        tbl[i + 1, 7].set_facecolor("#FFCDD2")
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    print(f"  Saved: {pdf_path}")


# =====================================================================
# P4 - Szenario A Anschluss + Betreiber-NPV
# =====================================================================

def plot_scenario_A_summary(grouped: Dict[str, Dict[str, Any]], out_dir: str, ref_key: str) -> None:
    rows = []
    for sub_key, run in (grouped[ref_key].get("bms") or {}).items():
        if run["info"].get("scenario_flag") != "A":
            continue
        sc = _scenario_block(run, "A")
        pinfo = _price_info(run, "A")
        p_min = pinfo["p_min"]
        p_max = pinfo["p_max"]
        n_conn, n_total, connected, excluded = _connected_info(run, "A")
        op_npv = _operator_npv_at_price(run, "A", p_max)
        feasible = (p_min is not None and p_max is not None and p_min <= p_max)
        rows.append({
            "run": _label(sub_key, run),
            "n_connected": n_conn,
            "n_total": n_total,
            "n_excluded": max(n_total - n_conn, len(excluded)),
            "p_min": p_min,
            "p_max_A": p_max,
            "operator_npv_at_pmax_A": op_npv,
            "wirtschaftlich": feasible,
            "enabled": sc.get("enabled"),
            "reason": sc.get("reason") or "",
            "excluded_list": ",".join(str(x) for x in excluded),
        })

    if not rows:
        print(f"  [P4 {ref_key}] keine A-Runs")
        return

    csv_path = os.path.join(out_dir, "P4_szenario_A_anschluss_preis_betreiber_npv.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        cols = ["run", "n_connected", "n_total", "n_excluded", "p_min_ct_per_kWh", "p_max_A_ct_per_kWh", "operator_NPV_at_pmax_A_EUR", "wirtschaftlich", "A_enabled", "reason", "excluded"]
        w = csv.writer(f); w.writerow(cols)
        for r in rows:
            w.writerow([
                r["run"], r["n_connected"], r["n_total"], r["n_excluded"],
                _fmt_num(r["p_min"] * 100 if r["p_min"] is not None else None, 4),
                _fmt_num(r["p_max_A"] * 100 if r["p_max_A"] is not None else None, 4),
                _fmt_num(r["operator_npv_at_pmax_A"]),
                "ja" if r["wirtschaftlich"] else "nicht wirtschaftlich",
                r["enabled"], r["reason"], r["excluded_list"],
            ])
    print(f"  Saved: {csv_path}")

    vals = [r["operator_npv_at_pmax_A"] for r in rows if r["operator_npv_at_pmax_A"] is not None]
    factor, unit = _smart_unit_eur(vals if vals else [0.0])
    labels = [r["run"] for r in rows]
    x = np.arange(len(rows))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(max(10, 1.5 * len(rows)), 8.2), gridspec_kw={"height_ratios": [1, 1]})

    conn = np.array([r["n_connected"] for r in rows])
    excl = np.array([max(0, r["n_total"] - r["n_connected"]) for r in rows])
    ax1.bar(x, conn, color="#2E7D32", edgecolor="white", label="anschliessbar / angeschlossen")
    ax1.bar(x, excl, bottom=conn, color="#BDBDBD", edgecolor="white", label="nicht angeschlossen")
    for i, r in enumerate(rows):
        ax1.text(i, r["n_total"] + 0.2, f"{r['n_connected']}/{r['n_total']}", ha="center", va="bottom", fontweight="bold")
        if r["reason"]:
            ax1.text(i, 0, "A deaktiviert", ha="center", va="bottom", fontsize=8, color="#C62828", rotation=90)
    ax1.set_ylabel("Anzahl Haeuser")
    ax1.set_xticks(x); ax1.set_xticklabels(labels, rotation=12, ha="right")
    ax1.set_title(f"Szenario A: Anschlussauswahl und Betreiberbewertung ({ref_key})", fontweight="bold")
    ax1.grid(axis="y", alpha=0.25)
    ax1.legend(loc="upper right")

    # Preis-Korridor und Betreiber-NPV
    y = np.arange(len(rows))
    for i, r in enumerate(rows):
        pmin = r["p_min"] * 100 if r["p_min"] is not None else None
        pmax = r["p_max_A"] * 100 if r["p_max_A"] is not None else None
        op = r["operator_npv_at_pmax_A"] * factor if r["operator_npv_at_pmax_A"] is not None else None
        if pmin is not None and pmax is not None:
            lo = min(pmin, pmax); hi = max(pmin, pmax)
            col = "#2E7D32" if r["wirtschaftlich"] else "#C62828"
            ax2.plot([lo, hi], [i, i], color=col, lw=5, alpha=0.65)
            ax2.scatter([pmin], [i], color="#1B5E20", s=50, zorder=3)
            ax2.scatter([pmax], [i], color="#B71C1C", s=50, zorder=3)
            txt = f"Betreiber-NPV: {op:+,.2f} {unit}" if op is not None else "Betreiber-NPV fehlt"
            if not r["wirtschaftlich"]:
                txt = "nicht wirtschaftlich | " + txt
            ax2.text(hi + 0.3, i, txt, va="center", ha="left", fontsize=9, color=col)
        else:
            msg = "p_max_A fehlt"
            if r["reason"]:
                msg += f" ({r['reason']})"
            ax2.text(0, i, msg, va="center", ha="left", fontsize=9, color="#616161")
    ax2.set_yticks(y); ax2.set_yticklabels(labels)
    ax2.invert_yaxis()
    ax2.set_xlabel("Waermepreis [ct/kWh]  |  gruen: p_min, rot: p_max_A")
    ax2.grid(axis="x", alpha=0.25)
    ax2.spines["top"].set_visible(False); ax2.spines["right"].set_visible(False)

    plt.tight_layout()
    path = os.path.join(out_dir, "P4_szenario_A_anschluss_preis_betreiber_npv.pdf")
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# =====================================================================
# Orchestrator
# =====================================================================

def _make_results_dir(result_root: str, results_subfolder: str, scenario_variant: str) -> str:
    parts = [p for p in [result_root, results_subfolder, scenario_variant] if p]
    return os.path.join(*parts)


def _make_plots_dir(result_root: str, plots_subfolder: str, scenario_variant: str) -> str:
    parts = [p for p in [result_root, plots_subfolder, scenario_variant] if p]
    return os.path.join(*parts)


def run(
    scenario_variant: str = "A01",
    result_root: str = RESULT_ROOT,
    results_subfolder: str = RESULTS_SUBFOLDER,
    plots_subfolder: str = PLOTS_SUBFOLDER,
) -> None:
    results_dir = _make_results_dir(result_root, results_subfolder, scenario_variant)
    plots_dir = _make_plots_dir(result_root, plots_subfolder, scenario_variant)

    print("#" * 70)
    print(f"RUN FOCUSED PLOTS: {scenario_variant}")
    print(f"results_dir: {results_dir}")
    print(f"plots_dir:   {plots_dir}")
    print("#" * 70)

    runs = load_runs(results_dir)
    if not runs:
        return
    grouped = group_by_reference(runs)

    for ref_key, group in grouped.items():
        out_dir = os.path.join(plots_dir, ref_key, "focused")
        os.makedirs(out_dir, exist_ok=True)
        print(f"\n--- {ref_key} -> {out_dir} ---")
        write_trafo_diagnostics(grouped, out_dir, ref_key)
        plot_tech_mix(grouped, out_dir, ref_key)
        plot_scenario_B(grouped, out_dir, ref_key)
        export_scenario_A_tables(grouped, out_dir, ref_key)
        plot_scenario_A_summary(grouped, out_dir, ref_key)

    print("\nDONE")


if __name__ == "__main__":
    SCENARIO_VARIANT = "A01"
    run(scenario_variant=SCENARIO_VARIANT)
