from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import numpy as np


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


def read_din_table(path: Path | str) -> Dict[int, Dict[str, float]]:
    """
    Erwartete Header:
      we;din_fuse_A_with_ww;din_ha_kW_with_ww;din_fuse_A_no_ww;din_ha_kW_no_ww
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
            rows.append(
                {
                    "we": we,
                    "din_fuse_A_with_ww": _decimal_to_float(r.get("din_fuse_A_with_ww")),
                    "din_ha_kW_with_ww": _decimal_to_float(r.get("din_ha_kW_with_ww")),
                    "din_fuse_A_no_ww": _decimal_to_float(r.get("din_fuse_A_no_ww")),
                    "din_ha_kW_no_ww": _decimal_to_float(r.get("din_ha_kW_no_ww")),
                }
            )

    table: Dict[int, Dict[str, float]] = {row["we"]: row for row in rows}
    if not table:
        raise ValueError("DIN table parsed empty (delimiter/header falsch?).")
    return table


def din_lookup(table: Dict[int, Dict[str, float]], we: int) -> Tuple[Dict[str, float], int, str]:
    keys = sorted(table.keys())
    if we <= keys[0]:
        return table[keys[0]], keys[0], "clamp_low"
    for k in keys:
        if k >= we:
            return table[k], k, "ceil"
    return table[keys[-1]], keys[-1], "clamp_high"


def _heater(building: Any) -> str:
    if isinstance(building, dict):
        bf = building.get("buildingFeatures")
        if isinstance(bf, dict) and bf.get("heater") is not None:
            return str(bf.get("heater"))
        if building.get("heater") is not None:
            return str(building.get("heater"))
    return ""


def _din_case(building: Any) -> str:
    """
    Determine DIN 18015-1 curve based on whether DHW is produced electrically.

    Curve A (with_ww):  Households with electric DHW production.
                        Applies to heat pumps and direct electric heaters,
                        where the full electrical load for space heating AND
                        domestic hot water must be transmitted through the
                        house connection.

    Curve B (no_ww):    Households WITHOUT electric DHW production.
                        Applies to gas/oil/biomass boilers and heat grids,
                        where DHW is produced by the fuel/heat source and
                        the electrical house connection only carries
                        lighting, appliances, etc.
    """
    # Heater types where DHW is produced electrically
    _ELECTRIC_DHW = {"HP", "EH"}

    heater = _heater(building).upper()
    if heater in _ELECTRIC_DHW:
        return "with_ww"    # electric DHW → Kurve A (higher limit)
    else:
        return "no_ww"      # non-electric DHW → Kurve B (lower limit)


def _we_from_demands(building: Any) -> int:
    # WE aus den Demands (Users-Objekt)
    if isinstance(building, dict):
        user = building.get("user")
        if user is not None and getattr(user, "nb_flats", None) is not None:
            return int(getattr(user, "nb_flats"))
        # Fallback, falls du WE irgendwo in buildingFeatures speicherst:
        bf = building.get("buildingFeatures")
        if isinstance(bf, dict):
            for k in ("we", "nb_flats", "wohneinheiten"):
                if bf.get(k) is not None:
                    return int(bf.get(k))
    raise KeyError("WE nicht gefunden: erwartet building['user'].nb_flats (Demands).")


def apply_din_house_connection_limits(
    data: Any,
    enabled: bool,
    din_csv_path: Path | str,
    write_back_to_buildings: bool = True,
) -> Dict[int, float]:
    """
    Vor der Optimierung aufrufen.
    Schreibt:
      data.site['enable_buildingMax_W'] = enabled
      data.site['buildingMax_W_per_building'] = {n: W}
    """
    if not hasattr(data, "site") or data.site is None:
        raise AttributeError("data.site fehlt.")

    if not enabled:
        data.site["enable_buildingMax_W"] = False
        data.site.pop("buildingMax_W_per_building", None)
        return {}

    din_table = read_din_table(din_csv_path)

    limits_W: Dict[int, float] = {}
    for n, b in enumerate(getattr(data, "district", [])):
        we = _we_from_demands(b)
        case = _din_case(b)

        row, used_we, method = din_lookup(din_table, we)
        if case == "with_ww":
            ha_kW = float(row["din_ha_kW_with_ww"])
            fuse_A = float(row["din_fuse_A_with_ww"])
        else:
            ha_kW = float(row["din_ha_kW_no_ww"])
            fuse_A = float(row["din_fuse_A_no_ww"])

        limits_W[n] = ha_kW * 1000.0

        if write_back_to_buildings and isinstance(b, dict):
            b.setdefault("buildingFeatures", {})
            b["buildingFeatures"]["din_case"] = case
            b["buildingFeatures"]["din_we_used"] = int(used_we)
            b["buildingFeatures"]["din_lookup_method"] = method
            b["buildingFeatures"]["din_house_connection_kW"] = float(ha_kW)
            b["buildingFeatures"]["din_fuse_A"] = float(fuse_A)

    data.site["enable_buildingMax_W"] = True
    data.site["buildingMax_W_per_building"] = limits_W
    return limits_W