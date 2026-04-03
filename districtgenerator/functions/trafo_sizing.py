# districtgenerator/functions/trafo_sizing.py
"""
Transformer sizing for district-level low-voltage grids.

Estimates the required MV/LV transformer capacity based on:
  1. Per-building house-connection limits (DIN 18015-1)
  2. Kerber coincidence factor to aggregate non-coincident peaks
  3. Selection of the smallest standard DIN 42508 transformer step

The methodology follows Kerber [1] and the pylovo tool [2].

References
----------
[1] G. Kerber, "Aufnahmefähigkeit von Niederspannungsverteilnetzen für
    die Einspeisung aus Photovoltaikkleinanlagen", TU München, 2011.
[2] Reveron Baecker et al., "Generation of low-voltage synthetic grid
    data for energy system modeling with the pylovo tool",
    Sust. Energy Grids Netw. 41 (2025) 101617.                                                 #todo Rawad: nutzt du das noch im code?
"""
from __future__ import annotations

from pathlib import Path
import json
from math import sqrt

DIN_TRAFO_STEPS_KVA = [100, 160, 250, 400, 630, 800, 1000, 1250]  #todo Rawad: sind diese dann aus DIN 42508?


def coincidence_factor_kerber(n_we: float, g: float = 0.07) -> float:
    """
    Kerber coincidence factor (Gleichzeitigkeitsfaktor) for residential loads.

    Based on the Rusck equation calibrated by Kerber [1] with exponent -3/4:

        c(n) = g + (1 - g) * n^(-3/4)

    This form is more accurate than the Konstantelos variant (exponent -1/2)
    for networks with more than ~20 households, which is the typical case
    at the transformer/district level. See [2] Eq. (4) and Fig. 8.

    Parameters
    ----------
    n_we : float
        Number of residential units (Wohneinheiten).
    g : float
        Asymptotic coincidence factor for n -> inf.
        Default 0.07 for residential loads (Kerber).
        Other typical values: g=0.5 commercial, g=0.6 public.

    Returns
    -------
    float
        Coincidence factor in range [g, 1.0].
    """
    n = max(float(n_we), 1.0)
    return float(g + (1.0 - g) * n ** (-0.75))


def choose_trafo_kva(required_kva: float, steps=DIN_TRAFO_STEPS_KVA) -> float:
    """Select the smallest DIN 42508 transformer step >= required_kva."""
    req = float(required_kva)
    for s in steps:
        if float(s) >= req:
            return float(s)
    return float(steps[-1])


def trafo_limit_from_house_connection_limits(
    data,
    cosphi: float = 0.95,
    safety_factor: float = 1.10,
    g: float = 0.07,
    steps=DIN_TRAFO_STEPS_KVA,
    out_dir: Path | None = None,
    write_json: bool = True,
) -> dict:
    """
    Size the district MV/LV transformer from per-building DIN limits.

    Must be called AFTER apply_din_house_connection_limits(), which populates
    data.site["buildingMax_W_per_building"].

    Procedure:
      1. Sum all non-coincident house-connection limits  [kW]
      2. Count total Wohneinheiten (WE) across the district         #todo Rawad: d. h. das ist nur für Wohngebäude anwendbar? was machst du mit den NWG?
      3. Apply Kerber coincidence factor: Pc = c(WE) * P_sum
      4. Convert to apparent power with cosphi and safety factor
      5. Select smallest DIN 42508 transformer step >= required kVA
      6. Store results in data.site

    Parameters
    ----------
    data : Datahandler
        Must have data.site["buildingMax_W_per_building"] populated.
    cosphi : float
        Power factor (default 0.95).
    safety_factor : float
        Safety margin on required kVA (default 1.10 = 10 %).
    g : float
        Kerber g-factor (default 0.07 for residential).
    steps : list[float]
        Available DIN 42508 transformer sizes [kVA].
    out_dir : Path, optional
        Directory for writing the sizing summary JSON.
    write_json : bool
        Whether to write JSON output.

    Returns
    -------
    dict
        Sizing summary with all intermediate values.

    Raises
    ------
    KeyError
        If buildingMax_W_per_building is not found in data.site.
    """
    per_bldg = (getattr(data, "site", {}) or {}).get("buildingMax_W_per_building", None)
    if not per_bldg:
        data.site["enable_trafoMax_W"] = False
        data.site.pop("trafoMax_W", None)
        data.site.pop("trafo_sizing_summary", None)
        raise KeyError(
            "No buildingMax_W_per_building found. "
            "Call apply_din_house_connection_limits first."
        )

    # Sum of non-coincident house connections [kW]
    din_sum_kW = sum(float(w) for w in per_bldg.values()) / 1000.0

    # Total Wohneinheiten across the district
    we_sum = 0
    for b in getattr(data, "district", []) or []:
        bf = b.get("buildingFeatures", {}) if isinstance(b, dict) else {}
        if bf.get("din_we_used") is not None:
            we_sum += int(bf["din_we_used"])
        else:
            user = b.get("user", None) if isinstance(b, dict) else None
            we_sum += int(getattr(user, "nb_flats", 1) or 1)

    c = coincidence_factor_kerber(we_sum, g=g)
    Pc_kW = c * din_sum_kW

    required_kVA = (Pc_kW / max(cosphi, 1e-6)) * safety_factor
    chosen_kVA = choose_trafo_kva(required_kVA, steps=steps)

    # Active power limit [W]
    trafoMax_W = chosen_kVA * 1000.0 * cosphi

    summary = {
        "din_sum_house_connections_kW_noncoincident": din_sum_kW,
        "we_sum": we_sum,
        "coincidence_factor": c,
        "din_estimated_coincident_peak_kW": Pc_kW,
        "cosphi": cosphi,
        "safety_factor": safety_factor,
        "required_kVA": required_kVA,
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
            json.dumps(summary, indent=2), encoding="utf-8"
        )

    return summary