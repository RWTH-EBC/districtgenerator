# -*- coding: utf-8 -*-
"""
plots_loads.py — Lastprofil- und Auslastungsanalyse zentraler Erzeuger.

Liest timeseries_*.pkl und erzeugt:
  G1 — Wärme-Lastprofil ueber Cluster gestapelt (pro BM)
  G2 — Geordnete Jahresdauerlinie pro Erzeuger (pro BM und BM-Vergleich)
  G3 — Auslastungs-KPIs (Vollbenutzungsstunden / Betriebsstunden / mittl. Teillast)
  G4 — Strom-Bilanz ueber Cluster (pro BM)

Cluster -> Jahres-Rekonstruktion:
  Aus metadata.clusterWeights (dict cluster_id -> Anzahl repraesentierter
  Wochen) wird jeder Cluster mit seinem Gewicht in die geordnete Jahres-
  dauerlinie eingebracht (Zeitschritte werden gemaess Gewicht repliziert).
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt


# ---------------------------------------------------------------
# Farben & Reihenfolge der Erzeuger (Stack-Reihenfolge)
# ---------------------------------------------------------------
HEAT_DEVS = ("BOI", "BBOI", "WBOI",  # Brennstoffkessel (Spitzen-/Mittellast)
             "CHP", "BCHP", "WCHP",  # KWK
             "HP", "GHP",            # Waermepumpen
             "EB",                   # Elektroheizer
             "FC",                   # Brennstoffzelle
             "STC")                  # Solarthermie

EL_SOURCES = ("PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC", "from_grid")
EL_SINKS = ("HP", "EB", "CC", "ELYZ", "to_grid")

DEV_COLORS = {
    "BOI":  "#FF7043",  "BBOI": "#FFAB91", "WBOI": "#BF360C",
    "CHP":  "#5D4037",  "BCHP": "#8D6E63", "WCHP": "#3E2723",
    "HP":   "#1E88E5",  "GHP":  "#5E92F3",
    "EB":   "#FDD835",
    "FC":   "#26A69A",
    "STC":  "#FFA726",
    "PV":   "#FBC02D",  "WT":   "#43A047", "WAT":  "#0277BD",
    "ELYZ": "#7B1FA2",
    "from_grid": "#90A4AE", "to_grid": "#455A64",
}


# ═══════════════════════════════════════════════════════════════
# 1) HILFSFUNKTIONEN
# ═══════════════════════════════════════════════════════════════

def _load_timeseries(ts_path: str) -> Dict[str, Any]:
    import pickle
    with open(ts_path, "rb") as f:
        return pickle.load(f)


def _cluster_weights(summary: Dict[str, Any]) -> Dict[int, float]:
    md = summary.get("metadata") or {}
    raw = md.get("clusterWeights") or {}
    return {int(k): float(v) for k, v in raw.items()}


def _years(ts: Dict[str, Any]) -> List:
    return sorted((ts.get("energy_hub") or {}).keys())


def _eh_field_present(ts: Dict[str, Any], year, key: str) -> bool:
    eh = (ts.get("energy_hub") or {}).get(year) or {}
    for cl in eh.values():
        if key in cl:
            return True
    return False


def _stack_clusters(ts: Dict[str, Any], year, key: str) -> Optional[np.ndarray]:
    """Haengt alle Cluster fuer key zu einer langen Reihe aneinander.
    Returns None wenn key fehlt."""
    eh = (ts.get("energy_hub") or {}).get(year) or {}
    if not eh:
        return None
    clusters = sorted(eh.keys())
    out = []
    for cl in clusters:
        arr = eh[cl].get(key)
        if arr is None:
            return None
        out.append(np.asarray(arr, dtype=float))
    return np.concatenate(out) if out else None


def _district_total(ts: Dict[str, Any], year, key: str) -> Optional[np.ndarray]:
    dt = (ts.get("district_totals") or {}).get(year) or {}
    if not dt:
        return None
    clusters = sorted(dt.keys())
    out = []
    for cl in clusters:
        arr = dt[cl].get(key)
        if arr is None:
            return None
        out.append(np.asarray(arr, dtype=float))
    return np.concatenate(out) if out else None


def _weighted_year_series(ts: Dict[str, Any],
                           weights: Dict[int, float],
                           year, key: str) -> Optional[np.ndarray]:
    """
    Rekonstruiert eine 8760h-Reihe aus Cluster-Reihen unter Verwendung der
    clusterWeights. Cluster i wird w_i mal repliziert hintereinander.
    Liefert eine Reihe der Laenge sum(w_i) * time_steps_per_cluster.
    """
    eh = (ts.get("energy_hub") or {}).get(year) or {}
    if not eh or not weights:
        return None
    parts = []
    for cl in sorted(eh.keys()):
        arr = eh[cl].get(key)
        if arr is None:
            continue
        w = int(round(weights.get(cl, 1)))
        if w <= 0:
            continue
        parts.append(np.tile(np.asarray(arr, dtype=float), w))
    return np.concatenate(parts) if parts else None


def _central_capacity(summary: Dict[str, Any], dev: str) -> Optional[float]:
    cap = ((summary.get("capacities") or {}).get("central") or {}).get(dev)
    if not isinstance(cap, dict):
        return None
    # Bei thermischen Geraeten ist cap_kW relevant
    return cap.get("cap_kW")


# ═══════════════════════════════════════════════════════════════
# 2) G1 — WAERME-LASTPROFIL UEBER CLUSTER (gestapelt)
# ═══════════════════════════════════════════════════════════════

def plot_heat_profile_clusters(run: Dict[str, Any],
                                save_path: str,
                                bm_label: str) -> None:
    """
    Stack der zentralen Waermeerzeuger ueber alle Cluster aneinandergehaengt.
    Ueber dem Stack: Gesamt-Waermebedarf (heat + dhw).
    """
    summary = run["summary"]
    ts = _load_timeseries(run["timeseries_path"])
    years = _years(ts)
    if not years:
        print(f"  [G1 {bm_label}] keine timeseries-Daten")
        return
    y = years[0]

    # Erzeuger
    devs_present = []
    series = {}
    for dev in HEAT_DEVS:
        s = _stack_clusters(ts, y, f"heat_{dev}")
        if s is not None and np.any(s > 1e-3):
            series[dev] = s
            devs_present.append(dev)

    if not devs_present:
        print(f"  [G1 {bm_label}] keine zentralen Waermeerzeuger gefunden")
        return

    # Bedarf
    heat_dem = _district_total(ts, y, "total_heat_demand")
    dhw_dem  = _district_total(ts, y, "total_dhw_demand")
    total_dem = None
    if heat_dem is not None:
        total_dem = heat_dem + (dhw_dem if dhw_dem is not None else 0)

    # Cluster-Grenzen
    md = ts.get("metadata") or {}
    tspc = int(md.get("time_steps_per_cluster") or 0)
    n_cl = int(md.get("num_clusters") or 0)
    n_total = next(iter(series.values())).size

    fig, ax = plt.subplots(figsize=(14, 5.5))
    x = np.arange(n_total)
    bottom = np.zeros(n_total)
    for dev in devs_present:
        v = series[dev]
        ax.fill_between(x, bottom, bottom + v, label=dev,
                        color=DEV_COLORS.get(dev, "#9E9E9E"),
                        alpha=0.85, linewidth=0)
        bottom = bottom + v

    if total_dem is not None and total_dem.size == n_total:
        ax.plot(x, total_dem, color="black", lw=1.0, ls="--",
                label="Gesamtbedarf (Heiz + WW)")

    if tspc > 0 and n_cl > 1:
        for i in range(1, n_cl):
            ax.axvline(i * tspc, color="white", lw=1.5, alpha=0.7)

    ax.set_xlim(0, n_total)
    ax.set_xlabel("Stunde (Cluster aneinandergehaengt)")
    ax.set_ylabel("Waermeleistung [kW]")
    ax.set_title(f"Waerme-Lastprofil ueber Cluster — {bm_label}",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8, ncol=min(len(devs_present) + 1, 6))
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# ═══════════════════════════════════════════════════════════════
# 3) G2 — JAHRES-DAUERLINIE (LDC)
# ═══════════════════════════════════════════════════════════════

def _ldc(series: np.ndarray) -> np.ndarray:
    """Geordnete Dauerlinie: absteigend sortiert."""
    return np.sort(series)[::-1]


def plot_ldc_per_bm(run: Dict[str, Any],
                     save_path: str,
                     bm_label: str) -> None:
    """
    Jahresdauerlinie aller zentralen Waermeerzeuger fuer einen BM.
    Mit horizontalen Linien fuer die installierte Kapazitaet jedes Geraets.
    """
    summary = run["summary"]
    ts = _load_timeseries(run["timeseries_path"])
    years = _years(ts)
    if not years:
        return
    y = years[0]

    weights = _cluster_weights(summary)

    devs_present = []
    ldc_data = {}
    caps = {}
    for dev in HEAT_DEVS:
        ser = _weighted_year_series(ts, weights, y, f"heat_{dev}")
        if ser is None or not np.any(ser > 1e-3):
            continue
        devs_present.append(dev)
        ldc_data[dev] = _ldc(ser)
        caps[dev] = _central_capacity(summary, dev)

    if not devs_present:
        print(f"  [G2 {bm_label}] keine Erzeuger")
        return

    fig, ax = plt.subplots(figsize=(11, 5.5))
    n_h = len(next(iter(ldc_data.values())))
    x = np.arange(n_h)

    for dev in devs_present:
        ax.plot(x, ldc_data[dev], color=DEV_COLORS.get(dev, "#9E9E9E"),
                lw=2.0, label=dev)
        cap = caps.get(dev)
        if cap is not None and cap > 0:
            ax.axhline(cap, color=DEV_COLORS.get(dev, "#9E9E9E"),
                       lw=0.8, ls=":", alpha=0.7)

    ax.set_xlim(0, n_h)
    ax.set_xlabel("Stunden im Jahr (absteigend sortiert)")
    ax.set_ylabel("Waermeleistung [kW]")
    ax.set_title(f"Jahresdauerlinie zentrale Erzeuger — {bm_label}",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


def plot_ldc_compare_bms(group: Dict[str, Any],
                          save_path: str,
                          reference_key: str) -> None:
    """
    Pro Geraet ein Subplot, BMs als verschiedene Linien.
    Erlaubt Vergleich: Wie unterscheidet sich die BOI-Last zwischen BMs?
    """
    bms = group.get("bms") or {}
    if not bms:
        return

    # Welche Geraete tauchen mindestens in einem BM auf?
    devs_seen = set()
    runs_data = {}  # sub_key -> {dev: ldc_array, cap_dict}
    for sub_key, run in bms.items():
        if not run.get("timeseries_path"):
            continue
        ts = _load_timeseries(run["timeseries_path"])
        years = _years(ts)
        if not years:
            continue
        y = years[0]
        weights = _cluster_weights(run["summary"])

        per_dev = {}
        per_cap = {}
        for dev in HEAT_DEVS:
            ser = _weighted_year_series(ts, weights, y, f"heat_{dev}")
            if ser is None or not np.any(ser > 1e-3):
                continue
            per_dev[dev] = _ldc(ser)
            per_cap[dev] = _central_capacity(run["summary"], dev)
            devs_seen.add(dev)
        runs_data[sub_key] = {"ldc": per_dev, "cap": per_cap}

    if not devs_seen:
        print(f"  [G2-cmp {reference_key}] keine Geraete")
        return

    devs_list = [d for d in HEAT_DEVS if d in devs_seen]
    n = len(devs_list)
    ncols = min(3, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.5 * ncols, 4.0 * nrows),
                              squeeze=False)

    # BM-Farben
    bm_keys = list(runs_data.keys())
    cmap = plt.get_cmap("tab10")
    bm_color = {k: cmap(i % 10) for i, k in enumerate(bm_keys)}

    for idx, dev in enumerate(devs_list):
        r, c = divmod(idx, ncols)
        ax = axes[r][c]
        ax.set_title(f"{dev}", fontsize=11, fontweight="bold")
        ax.set_xlabel("Stunden")
        ax.set_ylabel("Leistung [kW]")
        ax.grid(alpha=0.3)

        for sub_key in bm_keys:
            ldc = runs_data[sub_key]["ldc"].get(dev)
            cap = runs_data[sub_key]["cap"].get(dev)
            if ldc is None:
                continue
            ax.plot(np.arange(ldc.size), ldc, color=bm_color[sub_key],
                    lw=1.6, label=_pretty_label(sub_key))
            if cap is not None and cap > 0:
                ax.axhline(cap, color=bm_color[sub_key], lw=0.6, ls=":",
                           alpha=0.6)

        ax.legend(fontsize=8, loc="upper right")

    # leere Subplots ausblenden
    for idx in range(n, nrows * ncols):
        r, c = divmod(idx, ncols)
        axes[r][c].axis("off")

    fig.suptitle(f"Jahresdauerlinien-Vergleich BMs — {reference_key}",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# ═══════════════════════════════════════════════════════════════
# 4) G3 — AUSLASTUNGS-KPIs
# ═══════════════════════════════════════════════════════════════

def _utilization_kpis(series_year: np.ndarray, cap_kW: Optional[float]
                       ) -> Dict[str, float]:
    """
    series_year : Reihe ueber 8760h (gewichtet rekonstruiert)
    cap_kW      : installierte Kapazitaet
    """
    out = {"flh": np.nan, "op_h": np.nan, "mean_partload_pct": np.nan,
           "peak_share_pct": np.nan}
    if series_year is None or series_year.size == 0:
        return out

    energy_kWh = float(series_year.sum())  # dt = 1h angenommen
    if cap_kW and cap_kW > 0:
        out["flh"] = energy_kWh / cap_kW
        threshold = 0.01 * cap_kW
        running = series_year[series_year > threshold]
        out["op_h"] = float(running.size)
        if running.size > 0:
            out["mean_partload_pct"] = float(running.mean() / cap_kW * 100.0)
        # Anteil an Stunden mit > 80% cap (Spitzenlast-Indikator)
        out["peak_share_pct"] = float((series_year > 0.8 * cap_kW).sum()
                                       / series_year.size * 100.0)
    return out


def compute_utilization_table(group: Dict[str, Any]
                               ) -> List[Dict[str, Any]]:
    """
    Gibt eine flache Liste fuer Plot/Print: pro (BM, Geraet) eine Zeile mit
    flh, op_h, mean_partload_pct, peak_share_pct.
    """
    bms = group.get("bms") or {}
    rows = []
    for sub_key, run in bms.items():
        if not run.get("timeseries_path"):
            continue
        ts = _load_timeseries(run["timeseries_path"])
        years = _years(ts)
        if not years:
            continue
        y = years[0]
        weights = _cluster_weights(run["summary"])

        for dev in HEAT_DEVS:
            ser = _weighted_year_series(ts, weights, y, f"heat_{dev}")
            if ser is None or not np.any(ser > 1e-3):
                continue
            cap = _central_capacity(run["summary"], dev)
            kpi = _utilization_kpis(ser, cap)
            rows.append({
                "bm_key": sub_key,
                "bm_label": _pretty_label(sub_key),
                "device": dev,
                "cap_kW": cap,
                **kpi,
            })
    return rows


def plot_utilization_kpis(group: Dict[str, Any],
                           save_path: str,
                           reference_key: str) -> None:
    """
    3x1 Subplots: Vollbenutzungsstunden, Betriebsstunden, mittl. Teillast.
    Gruppierte Bars: x-Achse = Geraet, Farben = BMs.
    """
    rows = compute_utilization_table(group)
    if not rows:
        print(f"  [G3 {reference_key}] keine Auslastungsdaten")
        return

    bm_keys = sorted(set(r["bm_key"] for r in rows))
    devs = [d for d in HEAT_DEVS if any(r["device"] == d for r in rows)]

    cmap = plt.get_cmap("tab10")
    bm_color = {k: cmap(i % 10) for i, k in enumerate(bm_keys)}

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), squeeze=False)

    metrics = [
        ("flh",               "Vollbenutzungsstunden [h/a]"),
        ("op_h",              "Betriebsstunden [h/a]"),
        ("mean_partload_pct", "Mittlere Teillast bei Betrieb [%]"),
    ]

    width = 0.8 / max(len(bm_keys), 1)
    for ax_idx, (key, ylabel) in enumerate(metrics):
        ax = axes[0][ax_idx]
        x = np.arange(len(devs))
        for i, bm_key in enumerate(bm_keys):
            vals = []
            for d in devs:
                match = [r for r in rows
                         if r["bm_key"] == bm_key and r["device"] == d]
                vals.append(match[0][key] if match else np.nan)
            offset = (i - (len(bm_keys) - 1) / 2) * width
            ax.bar(x + offset, vals, width, color=bm_color[bm_key],
                   label=_pretty_label(bm_key) if ax_idx == 0 else None,
                   edgecolor="white", linewidth=0.5)

        ax.set_xticks(x)
        ax.set_xticklabels(devs, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.grid(axis="y", alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Referenzlinien fuer Vollbenutzungsstunden
        if key == "flh":
            ax.axhline(1000, color="#C62828", lw=0.8, ls=":", alpha=0.7)
            ax.axhline(4000, color="#2E7D32", lw=0.8, ls=":", alpha=0.7)
            ax.text(len(devs) - 0.5, 1000, " Spitzenlast", fontsize=8,
                    color="#C62828", va="bottom")
            ax.text(len(devs) - 0.5, 4000, " Grundlast", fontsize=8,
                    color="#2E7D32", va="bottom")

    fig.legend(loc="upper center", bbox_to_anchor=(0.5, 1.02),
               ncol=len(bm_keys), fontsize=9, frameon=False)
    fig.suptitle(f"Auslastung zentraler Erzeuger — {reference_key}",
                 fontsize=13, fontweight="bold", y=1.06)
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


def export_utilization_csv(group: Dict[str, Any],
                            save_path: str) -> None:
    """Tabelle der Auslastungs-KPIs als CSV."""
    rows = compute_utilization_table(group)
    if not rows:
        return
    import csv
    cols = ["bm_label", "device", "cap_kW", "flh", "op_h",
            "mean_partload_pct", "peak_share_pct"]
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  Saved: {save_path}")


# ═══════════════════════════════════════════════════════════════
# 5) G4 — STROM-BILANZ UEBER CLUSTER
# ═══════════════════════════════════════════════════════════════

def plot_el_balance_clusters(run: Dict[str, Any],
                              save_path: str,
                              bm_label: str) -> None:
    """
    Strom-Bilanz: Quellen positiv (gestapelt), Senken negativ (gestapelt).
    PV / from_grid / CHP oben, HP / EB / to_grid unten.
    """
    summary = run["summary"]
    ts = _load_timeseries(run["timeseries_path"])
    years = _years(ts)
    if not years:
        return
    y = years[0]

    sources = {}
    for dev in EL_SOURCES:
        s = _stack_clusters(ts, y, f"power_{dev}")
        if s is not None and np.any(np.abs(s) > 1e-3):
            sources[dev] = s

    sinks = {}
    for dev in EL_SINKS:
        s = _stack_clusters(ts, y, f"power_{dev}")
        if s is not None and np.any(np.abs(s) > 1e-3):
            sinks[dev] = s
    # Gebaeude-Strombedarf zusaetzlich als Senke (district_totals)
    bldg_dem = _district_total(ts, y, "total_demand")
    if bldg_dem is not None and np.any(bldg_dem > 1e-3):
        sinks["buildings"] = bldg_dem

    if not sources and not sinks:
        print(f"  [G4 {bm_label}] keine Stromreihen")
        return

    if "buildings" not in DEV_COLORS:
        DEV_COLORS["buildings"] = "#37474F"

    md = ts.get("metadata") or {}
    tspc = int(md.get("time_steps_per_cluster") or 0)
    n_cl = int(md.get("num_clusters") or 0)
    n_total = (next(iter(sources.values())) if sources
               else next(iter(sinks.values()))).size
    x = np.arange(n_total)

    fig, ax = plt.subplots(figsize=(14, 5.5))

    # Quellen (positiv)
    bottom = np.zeros(n_total)
    for dev, v in sources.items():
        ax.fill_between(x, bottom, bottom + v, label=dev,
                        color=DEV_COLORS.get(dev, "#9E9E9E"),
                        alpha=0.85, linewidth=0)
        bottom = bottom + v

    # Senken (negativ)
    top = np.zeros(n_total)
    for dev, v in sinks.items():
        ax.fill_between(x, top, top - v, label=dev,
                        color=DEV_COLORS.get(dev, "#9E9E9E"),
                        alpha=0.55, linewidth=0)
        top = top - v

    ax.axhline(0, color="black", lw=0.6)

    if tspc > 0 and n_cl > 1:
        for i in range(1, n_cl):
            ax.axvline(i * tspc, color="white", lw=1.5, alpha=0.7)

    ax.set_xlim(0, n_total)
    ax.set_xlabel("Stunde (Cluster aneinandergehaengt)")
    ax.set_ylabel("Elektrische Leistung [kW]   (oben Quellen / unten Senken)")
    ax.set_title(f"Strom-Bilanz ueber Cluster — {bm_label}",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8, ncol=4)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {save_path}")


# ═══════════════════════════════════════════════════════════════
# 6) Helper
# ═══════════════════════════════════════════════════════════════

def _pretty_label(sub_key: str) -> str:
    if "__" in sub_key:
        bm, flag = sub_key.split("__", 1)
    else:
        bm, flag = sub_key, ""
    pretty = {
        "waermecontracting":             "Contracting",
        "waermecontracting_ggv":         "GGV",
        "waermecontracting_kundenanlage":"Kundenanlage",
        "waermegenossenschaft":          "Genossenschaft",
    }.get(bm, bm)
    return f"{pretty} ({flag})" if flag else pretty


# ═══════════════════════════════════════════════════════════════
# 7) ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def run_load_plots(grouped: Dict[str, Dict[str, Any]],
                    base_save_dir: str) -> None:
    """
    Erzeugt G2 (LDC) und G3 (Utilization-KPIs) je Referenz/BM.
    G1 (Heatprofile pro Cluster) und G4 (El-Bilanz) werden nicht mehr erzeugt;
    deren Inhalt steckt in plots_extra E4 (Cluster-Hub-Bilanzen).
    """
    for ref_key, group in grouped.items():
        bms = group.get("bms") or {}
        if not bms:
            continue

        ref_dir = os.path.join(base_save_dir, ref_key, "loads")
        os.makedirs(ref_dir, exist_ok=True)

        # Pro BM: nur G2a (LDC pro BM)
        for sub_key, run in bms.items():
            if not run.get("timeseries_path"):
                print(f"  [{ref_key}/{sub_key}] timeseries-pkl fehlt")
                continue
            label = _pretty_label(sub_key)
            tag = sub_key.replace("__", "_")
            plot_ldc_per_bm(
                run,
                os.path.join(ref_dir, f"G2a_ldc_per_bm_{tag}.pdf"),
                label)

        # BM-Vergleich
        plot_ldc_compare_bms(group,
            os.path.join(ref_dir, f"G2b_ldc_compare_BMs.pdf"),
            ref_key)
        plot_utilization_kpis(group,
            os.path.join(ref_dir, f"G3_utilization_kpis.pdf"),
            ref_key)
        export_utilization_csv(group,
            os.path.join(ref_dir, f"G3_utilization_kpis.csv"))