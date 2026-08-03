"""
Transformer sizing and cost data for district-level low-voltage grids.

Provides three core functions:

A) ``trafo_lower_bound_from_house_connections``:
   Lower bound on the transformer rating from per-building DIN/AMEV
   house-connection limits. Used as a hard minimum-size constraint by both
   the variable-MILP mode and the legacy pre-sizing mode.

B) ``trafo_cost_eur``:
   Stute & Klobasa (2024) DIN 42508 transformer investment data, piecewise
   linear interpolation, linear extrapolation outside the tabulated range.

C) ``trafo_limit_from_house_connection_limits``:
   Legacy pre-sizing mode (single chosen size) for backwards compatibility.

Coincidence-factor logic:
  - Pure-residential district -> Kerber [1] coincidence factor on the sum of
    DIN house-connection limits.
  - Mixed district (residential + NRB, or NRB-only) -> two-stage AMEV [2]
    aggregation: per-group coincidence factor + a site-wide coincidence
    factor of 0.8 (median of the AMEV-recommended 0.7-0.9 range,
    "EltAnlagen" 2025 Sec. 1.3.2).

References
----------
[1] Kerber, G. (2011). Aufnahmefaehigkeit von Niederspannungsverteilnetzen
    fuer die Einspeisung aus Photovoltaikkleinanlagen. Dissertation,
    TU Muenchen. https://mediatum.ub.tum.de/998003
[2] AMEV. EltAnlagen 2025 - Planung, Bau und Betrieb von elektrischen Anlagen
    in oeffentlichen Gebaeuden, Empfehlung Nr. 177, BMWSB, Berlin.
[3] Stute, J., Klobasa, M. (2024). How do dynamic electricity tariffs and
    different grid charge designs interact? Energy Policy 189, 114062.
    https://doi.org/10.1016/j.enpol.2024.114062
"""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict, Optional
import math
import numpy as np


# DIN 42508 standard transformer steps [kVA]
DIN_TRAFO_STEPS_KVA = [100, 160, 250, 400, 630, 800, 1000, 1250]


# --------------------------------------------------------------------------- #
# Stute & Klobasa (2024) Tab. 6 - transformer investment [EUR]
# --------------------------------------------------------------------------- #
# Steps outside the tabulated range are linearly extrapolated using the slope
# of the nearest tabulated segment. Substation overhead (45 000 EUR, constant
# in the source) is intentionally not added here; it appears separately in
# the customer-installation business-model investment if relevant.
_STUTE_KLOBASA_2024 = {
    250: 19_000.0,
    400: 21_000.0,
    630: 24_000.0,
    800: 30_000.0,
}


def trafo_cost_eur(kva: float, cost_table: Optional[Dict[float, float]] = None) -> float:
    table = {float(k): float(v) for k, v in (cost_table or _STUTE_KLOBASA_2024).items()}
    s = float(kva)
    keys = sorted(table.keys())
    if s <= keys[0]:
        s1, s2 = keys[0], keys[1]
        slope = (table[s2] - table[s1]) / (s2 - s1)
        return max(table[s1] + slope * (s - s1), 0.0)
    if s >= keys[-1]:
        s1, s2 = keys[-2], keys[-1]
        slope = (table[s2] - table[s1]) / (s2 - s1)
        return table[s2] + slope * (s - s2)
    for i in range(len(keys) - 1):
        s1, s2 = keys[i], keys[i + 1]
        if s1 <= s <= s2:
            slope = (table[s2] - table[s1]) / (s2 - s1)
            return table[s1] + slope * (s - s1)
    return table[keys[-1]]


def trafo_cost_table(steps=DIN_TRAFO_STEPS_KVA) -> Dict[float, float]:
    """Return {kVA: EUR} for the given list of DIN 42508 steps."""
    return {float(s): trafo_cost_eur(s) for s in steps}


# --------------------------------------------------------------------------- #
# Coincidence factors
# --------------------------------------------------------------------------- #
def coincidence_factor_kerber(n_we: float, g: float = 0.07) -> float:
    """
    Kerber coincidence factor for residential loads:
        c(n) = g + (1 - g) * n^(-3/4)
    with default g = 0.07 (residential).
    """
    n = max(float(n_we), 1.0)
    return float(g + (1.0 - g) * n ** (-0.75))


# AMEV "EltAnlagen" 2025 Sec. 1.3.2: site-wide factor 0.7-0.9 for liegenschaft
# with multiple building groups; we use the median 0.8.
SITE_COINCIDENCE_FACTOR_AMEV = 1


def choose_single_trafo_step_kva(required_kva: float, steps=DIN_TRAFO_STEPS_KVA) -> float:
    """Smallest available single-transformer step >= required_kva.

    If required_kva exceeds the largest available single-transformer step,
    the largest step is returned. Parallelization is handled separately.
    """
    req = float(required_kva)
    steps_sorted = sorted(float(s) for s in steps)
    for s in steps_sorted:
        if s >= req:
            return float(s)
    return float(steps_sorted[-1])


def choose_trafo_kva(required_kva: float, steps=DIN_TRAFO_STEPS_KVA) -> float:
    """Backward-compatible alias for choosing one single-transformer step."""
    return choose_single_trafo_step_kva(required_kva, steps=steps)


# --------------------------------------------------------------------------- #
# Lower-bound transformer rating from house-connection limits
# --------------------------------------------------------------------------- #
def trafo_lower_bound_from_house_connections(
    data: Any,
    cosphi: float = 0.95,
    safety_factor: float = 1.0,
    g_residential: float = 0.07,
    site_coincidence: float = SITE_COINCIDENCE_FACTOR_AMEV,
    steps=DIN_TRAFO_STEPS_KVA,
) -> Dict[str, Any]:
    """
    Compute the minimum DIN 42508 transformer step required to physically
    cover all house connections.

    Logic:
      - Pure residential -> Kerber on (sum DIN HA, sum WE).
      - Else (mixed or NRB-only) -> per-group coincident peak (Kerber for the
        residential block, AMEV factor per NRB BWZK group), summed and
        multiplied by a site-wide coincidence factor.

    Requires ``apply_house_connection_limits`` to have been called first
    (populates ``data.site['buildingMax_W_per_building']`` and
    ``data.site['house_connection_meta']``).
    """
    site = getattr(data, "site", {}) or {}
    per_bldg = site.get("buildingMax_W_per_building")
    meta = site.get("house_connection_meta")
    if not per_bldg or not meta:
        raise KeyError(
            "Per-building house-connection limits not found. "
            "Call apply_house_connection_limits first."
        )

    residential_kW = 0.0
    residential_we = 0
    nrb_groups: Dict[str, Dict[str, float]] = {}

    for n, b in enumerate(getattr(data, "district", []) or []):
        info = meta.get(n, {})
        kW_b = float(per_bldg[n]) / 1000.0
        cat = info.get("category")

        if cat == "residential":
            residential_kW += kW_b
            we = info.get("din_we_used") or 1
            residential_we += int(we)
        elif cat == "non_residential":
            bwzk = str(info.get("bwzk", "")) or "NRB"
            cf = float(info.get("coincidence_factor_amev", 1.0))
            grp = nrb_groups.setdefault(bwzk, {"kW": 0.0, "cf": cf})
            grp["kW"] += kW_b
            grp["cf"] = cf
        else:
            grp = nrb_groups.setdefault("UNKNOWN", {"kW": 0.0, "cf": 1.0})
            grp["kW"] += kW_b

    has_residential = residential_kW > 0.0
    has_nrb = len(nrb_groups) > 0

    if has_residential and not has_nrb:
        c_res = coincidence_factor_kerber(residential_we, g=g_residential)
        Pc_kW = c_res * residential_kW
        aggregation = "kerber_residential"
        details: Dict[str, Any] = {
            "residential_sum_kW": residential_kW,
            "residential_we": residential_we,
            "kerber_coincidence": c_res,
        }
    else:
        Pc_res_kW = 0.0
        if has_residential:
            c_res = coincidence_factor_kerber(residential_we, g=g_residential)
            Pc_res_kW = c_res * residential_kW

        nrb_block_kW = 0.0
        nrb_breakdown: Dict[str, Dict[str, float]] = {}
        for bwzk, grp in nrb_groups.items():
            grp_peak_kW = grp["cf"] * grp["kW"]
            nrb_block_kW += grp_peak_kW
            nrb_breakdown[bwzk] = {
                "sum_kW": grp["kW"],
                "coincidence_factor": grp["cf"],
                "coincident_peak_kW": grp_peak_kW,
            }

        Pc_kW = site_coincidence * (Pc_res_kW + nrb_block_kW)
        aggregation = "amev_mixed"
        details = {
            "residential_sum_kW": residential_kW,
            "residential_we": residential_we,
            "residential_coincident_peak_kW": Pc_res_kW,
            "nrb_breakdown": nrb_breakdown,
            "site_coincidence_factor": site_coincidence,
        }

        # Profile-based validation: ensure trafo covers actual quarter-level peak.
        # AMEV / Kerber give a normbased pre-sizing; the operational MILP needs
        # a trafo that physically supports the simulated load profile.
        quarter_peak_kW = 0.0
        elec_total = None
        for b in getattr(data, "district", []) or []:
            elec = np.array(b["user"].elec, dtype=float)
            ev = np.array(b["user"].EV_carcharging_ondemand, dtype=float)
            load = elec + ev
            elec_total = load if elec_total is None else elec_total + load
        if elec_total is not None:
            quarter_peak_kW = float(np.max(elec_total)) / 1000.0

        if quarter_peak_kW > Pc_kW:
            print(f"[TRAFO] AMEV pre-size {Pc_kW:.1f} kW < operational peak "
                  f"{quarter_peak_kW:.1f} kW → using profile peak.")
            Pc_kW = quarter_peak_kW
            details["profile_quarter_peak_kW"] = quarter_peak_kW
            details["pre_size_method"] = "profile_overrides_amev"
        else:
            details["profile_quarter_peak_kW"] = quarter_peak_kW
            details["pre_size_method"] = "amev"

    required_kVA = (Pc_kW / max(cosphi, 1e-6)) * safety_factor

    steps_sorted = sorted(float(s) for s in steps)
    max_single_kVA = steps_sorted[-1]

    if required_kVA <= max_single_kVA:
        n_trafos = 1
        single_step_kVA = choose_single_trafo_step_kva(required_kVA, steps=steps_sorted)
    else:
        n_trafos = int(math.ceil(required_kVA / max_single_kVA))
        single_step_kVA = max_single_kVA

    min_step_kVA = n_trafos * single_step_kVA

    return {
        "aggregation": aggregation,
        "cosphi": cosphi,
        "safety_factor": safety_factor,
        "coincident_peak_kW": Pc_kW,
        "required_kVA": required_kVA,
        "min_din_step_kVA": min_step_kVA,
        "single_transformer_kVA": single_step_kVA,
        "n_parallel_transformers": n_trafos,
        "installed_transformer_kVA": min_step_kVA,
        "parallel_transformers_used": n_trafos > 1,
        "details": details,
    }


# --------------------------------------------------------------------------- #
# Legacy pre-sizing mode
# --------------------------------------------------------------------------- #
def trafo_limit_from_house_connection_limits(
    data: Any,
    cosphi: float = 0.95,
    safety_factor: float = 1.10,
    g: float = 0.07,
    steps=DIN_TRAFO_STEPS_KVA,
    out_dir: Optional[Path] = None,
    write_json: bool = True,
) -> Dict[str, Any]:
    """
    Pre-sizes the transformer to the minimum DIN step that satisfies the
    house-connection lower bound. Sets ``trafoMax_W`` in ``data.site``.

    The MILP-variable mode (opti_central) instead reads only the lower bound
    and chooses any DIN step >= min_din_step_kVA endogenously.
    """
    bound = trafo_lower_bound_from_house_connections(
        data=data, cosphi=cosphi, safety_factor=safety_factor,
        g_residential=g, steps=steps,
    )
    chosen_kVA = bound["min_din_step_kVA"]
    trafoMax_W = chosen_kVA * 1000.0 * cosphi

    summary = {
        **bound,
        "chosen_transformer_kVA": chosen_kVA,
        "trafoMax_W_for_optimization": trafoMax_W,
    }

    data.site["enable_trafoMax_W"] = True
    data.site["trafoMax_W"] = trafoMax_W
    data.site["trafo_sizing_summary"] = summary

    if write_json and out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "trafo_limit_from_house_connections.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )

    return summary