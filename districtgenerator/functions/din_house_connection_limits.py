"""
Per-building electrical house-connection limits.

Sources:
- Residential buildings: DIN 18015-1 (residential service entrance dimensioning).
  Curve A (with electric DHW: heat pump, electric heater) and curve B (without
  electric DHW: gas/oil/biomass boiler, heat grid).
- Non-residential buildings (NRB): AMEV "EltAnlagen" 2025 Tab. 1 (specific
  1/4-h electrical load in W/m^2 NRF) for matched building types; engineering
  assumptions from planning practice for types without an AMEV BWZK match.

The two methods are dispatched per building based on the type string in
``building["buildingFeatures"]["building"]``:

* Residential (SFH, MFH) -> DIN 18015-1 lookup (W per dwelling unit).
* Non-residential (OB, SC, GS, RE) -> AMEV table (W/m^2 NRF).

The DIN curve is selected via ``buildingFeatures["heater"]``: heat pumps
("HP") and electric heaters ("EH") use curve A (with_ww), all others curve B
(no_ww).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np


RESIDENTIAL_TYPES = {"SFH", "MFH"}

# Heater types where DHW is produced electrically -> DIN 18015-1 curve A.
_ELECTRIC_DHW_HEATERS = {"HP", "EH"}


def _decimal_to_float(s: Any) -> float:
    if s is None:
        return float("nan")
    if isinstance(s, (int, float)):
        return float(s)
    st = str(s).strip()
    if st == "":
        return float("nan")
    if st.count(",") == 1 and st.count(".") >= 1:
        st = st.replace(".", "").replace(",", ".")
    else:
        st = st.replace(",", ".")
    try:
        return float(st)
    except Exception:
        return float("nan")


def _features(building: Any):
    if isinstance(building, dict):
        return building.get("buildingFeatures", {})
    return {}


def _feature_get(building: Any, key: str, default=None):
    bf = _features(building)

    if hasattr(bf, "get"):
        val = bf.get(key, default)
        if val is not None:
            return val

    if isinstance(building, dict) and hasattr(building, "get"):
        val = building.get(key, default)
        if val is not None:
            return val

    return default


def _building_type(building: Any) -> str:
    bt = _feature_get(building, "building", "")
    if bt is None:
        return ""
    return str(bt).strip().split("+")[0].upper()


def _heater(building: Any) -> str:
    h = _feature_get(building, "heater", "")
    if h is None:
        return ""
    return str(h).strip()


def _we_from_demands(building: Any) -> int:
    if isinstance(building, dict):
        user = building.get("user")
        if user is not None and getattr(user, "nb_flats", None) is not None:
            return int(getattr(user, "nb_flats"))

    for k in ("we", "nb_flats", "wohneinheiten"):
        val = _feature_get(building, k, None)
        if val is not None:
            return int(val)

    raise KeyError("Number of dwelling units not found: expected building['user'].nb_flats.")


def _area_m2(building: Any) -> float:
    if isinstance(building, dict):
        bf = building.get("buildingFeatures", {})

        if hasattr(bf, "get"):
            val = bf.get("area")
            if val is not None:
                return float(val)

        val = building.get("area")
        if val is not None:
            return float(val)

    raise KeyError(
        f"Net floor area 'buildingFeatures.area' missing for non-residential building. "
        f"building={building}"
    )
def _heater(building: Any) -> str:
    if isinstance(building, dict):
        bf = building.get("buildingFeatures")
        if isinstance(bf, dict) and bf.get("heater") is not None:
            return str(bf.get("heater"))
        if building.get("heater") is not None:
            return str(building.get("heater"))
    return ""


def _din_case(building: Any) -> str:
    """DIN 18015-1 curve: with_ww (electric DHW) or no_ww (non-electric DHW)."""
    heater = _heater(building).upper()
    return "with_ww" if heater in _ELECTRIC_DHW_HEATERS else "no_ww"


def is_residential(building: Any) -> bool:
    return _building_type(building) in RESIDENTIAL_TYPES


# --------------------------------------------------------------------------- #
# DIN 18015-1 (residential)
# --------------------------------------------------------------------------- #
def read_din_table(path: Path | str) -> Dict[int, Dict[str, float]]:
    """
    Expected header:
      we;din_ha_kW_with_ww;din_strom_A_with_ww;din_fuse_A_with_ww;
      din_ha_kW_no_ww;din_strom_A_no_ww;din_fuse_A_no_ww
    """
    path = Path(path)
    rows = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = "\t" if ("\t" in sample and sample.count("\t") >= sample.count(";")) else ";"
        reader = csv.DictReader(f, delimiter=delimiter)

        for r in reader:
            we_val = _decimal_to_float(r.get("we"))
            if np.isnan(we_val):
                continue
            we = int(we_val)
            rows.append({
                "we": we,
                "din_fuse_A_with_ww": _decimal_to_float(r.get("din_fuse_A_with_ww")),
                "din_ha_kW_with_ww": _decimal_to_float(r.get("din_ha_kW_with_ww")),
                "din_fuse_A_no_ww": _decimal_to_float(r.get("din_fuse_A_no_ww")),
                "din_ha_kW_no_ww": _decimal_to_float(r.get("din_ha_kW_no_ww")),
            })

    table: Dict[int, Dict[str, float]] = {row["we"]: row for row in rows}
    if not table:
        raise ValueError("DIN table parsed empty (delimiter/header wrong?).")
    return table


def din_lookup(table: Dict[int, Dict[str, float]], we: int) -> Tuple[Dict[str, float], int, str]:
    keys = sorted(table.keys())
    if we <= keys[0]:
        return table[keys[0]], keys[0], "clamp_low"
    for k in keys:
        if k >= we:
            return table[k], k, "ceil"
    return table[keys[-1]], keys[-1], "clamp_high"


def _we_from_demands(building: Any) -> int:
    if isinstance(building, dict):
        user = building.get("user")
        if user is not None and getattr(user, "nb_flats", None) is not None:
            return int(getattr(user, "nb_flats"))
        bf = building.get("buildingFeatures")
        if isinstance(bf, dict):
            for k in ("we", "nb_flats", "wohneinheiten"):
                if bf.get(k) is not None:
                    return int(bf.get(k))
    raise KeyError("Number of dwelling units not found: expected building['user'].nb_flats.")


# --------------------------------------------------------------------------- #
# AMEV (non-residential)
# --------------------------------------------------------------------------- #
def read_amev_table(path: Path | str) -> Dict[str, Dict[str, Any]]:
    """
    Expected header:
      building_short;building_long;bwzk;p_spec_W_per_m2;coincidence_factor;source
    """
    path = Path(path)
    table: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for r in reader:
            short = (r.get("building_short") or "").strip().upper()
            if not short:
                continue
            table[short] = {
                "building_long": (r.get("building_long") or "").strip(),
                "bwzk": (r.get("bwzk") or "").strip(),
                "p_spec_W_per_m2": _decimal_to_float(r.get("p_spec_W_per_m2")),
                "coincidence_factor": _decimal_to_float(r.get("coincidence_factor")),
                "source": (r.get("source") or "").strip(),
            }
    if not table:
        raise ValueError("AMEV table parsed empty.")
    return table


def _area_m2(building: Any) -> float:
    if isinstance(building, dict):
        bf = building.get("buildingFeatures")
        if isinstance(bf, dict) and bf.get("area") is not None:
            return float(bf["area"])
    raise KeyError("Net floor area 'buildingFeatures.area' missing for non-residential building.")


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
def apply_house_connection_limits(
    data: Any,
    enabled: bool,
    din_csv_path: Path | str,
    amev_csv_path: Optional[Path | str] = None,
    write_back_to_buildings: bool = True,
) -> Dict[int, float]:
    """
    Compute and store per-building house-connection limits [W].

    Writes:
      data.site['enable_buildingMax_W']         = enabled
      data.site['buildingMax_W_per_building']   = {n: W}
      data.site['house_connection_meta']        = {n: dict with method, source, ...}

    Each building is classified as residential or non-residential via its
    'buildingFeatures.building' code. Residential -> DIN 18015-1, NRB -> AMEV.
    """
    if not hasattr(data, "site") or data.site is None:
        raise AttributeError("data.site missing.")

    if not enabled:
        data.site["enable_buildingMax_W"] = False
        data.site.pop("buildingMax_W_per_building", None)
        data.site.pop("house_connection_meta", None)
        return {}

    din_table = read_din_table(din_csv_path)
    amev_table = read_amev_table(amev_csv_path) if amev_csv_path is not None else {}

    limits_W: Dict[int, float] = {}
    meta: Dict[int, Dict[str, Any]] = {}

    for n, b in enumerate(getattr(data, "district", []) or []):
        bt = _building_type(b)

        if bt in RESIDENTIAL_TYPES:
            we = _we_from_demands(b)
            case = _din_case(b)
            row, used_we, method = din_lookup(din_table, we)
            ha_kW = float(row[f"din_ha_kW_{case}"])
            fuse_A = float(row[f"din_fuse_A_{case}"])
            limits_W[n] = ha_kW * 1000.0
            meta[n] = {
                "category": "residential",
                "method": "DIN_18015_1",
                "din_case": case,
                "din_we_input": we,
                "din_we_used": int(used_we),
                "din_lookup_method": method,
                "din_house_connection_kW": ha_kW,
                "din_fuse_A": fuse_A,
            }
            if write_back_to_buildings and isinstance(b, dict):
                b.setdefault("buildingFeatures", {})
                b["buildingFeatures"].update({
                    "din_case": case,
                    "din_we_used": int(used_we),
                    "din_lookup_method": method,
                    "din_house_connection_kW": float(ha_kW),
                    "din_fuse_A": float(fuse_A),
                })
        else:
            if bt not in amev_table:
                raise KeyError(
                    f"Non-residential building type {bt!r} not found in AMEV table. "
                    f"Add a row to amev_nrb_anschlussleistung.csv or extend the mapping."
                )
            row = amev_table[bt]
            area = _area_m2(b)
            p_spec = float(row["p_spec_W_per_m2"])
            ha_W = area * p_spec
            limits_W[n] = ha_W
            meta[n] = {
                "category": "non_residential",
                "method": "AMEV_EltAnlagen_2025",
                "bwzk": row["bwzk"],
                "p_spec_W_per_m2": p_spec,
                "coincidence_factor_amev": float(row["coincidence_factor"]),
                "area_m2": area,
                "house_connection_kW": ha_W / 1000.0,
                "source": row["source"],
            }
            if write_back_to_buildings and isinstance(b, dict):
                b.setdefault("buildingFeatures", {})
                b["buildingFeatures"].update({
                    "amev_bwzk": row["bwzk"],
                    "amev_p_spec_W_per_m2": p_spec,
                    "house_connection_kW": ha_W / 1000.0,
                })

    data.site["enable_buildingMax_W"] = True
    data.site["buildingMax_W_per_building"] = limits_W
    data.site["house_connection_meta"] = meta
    return limits_W


def apply_din_house_connection_limits(
    data: Any,
    enabled: bool,
    din_csv_path: Path | str,
    write_back_to_buildings: bool = True,
) -> Dict[int, float]:
    """Legacy alias; raises on non-residential buildings (no AMEV table given)."""
    return apply_house_connection_limits(
        data=data,
        enabled=enabled,
        din_csv_path=din_csv_path,
        amev_csv_path=None,
        write_back_to_buildings=write_back_to_buildings,
    )