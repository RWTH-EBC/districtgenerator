# -*- coding: utf-8 -*-
"""
Abstract base class for all business models.

NPV-based helper functions for business-model postprocessing.

Notation:
- bw_*  : present-value helper terms / discounted partial cash flows


Principles:
1. Only real cash flows are used (no avoided-cost logic as primary method).
2. Discounting is applied year by year with the correct support-year mapping.
3. End-customer decisions are based on total NPV comparisons against the reference case.
4. The offered heat price enters the end-customer NPV only through the heat payment
   term q_heat * p * PVAF; operator-side system costs are reflected indirectly via price setting.
"""


from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np
import copy

from districtgenerator.functions.din_house_connection_limits import (
    apply_din_house_connection_limits,
)
from districtgenerator.functions.trafo_sizing import (
    trafo_limit_from_house_connection_limits,
    DIN_TRAFO_STEPS_KVA,
)


class BusinessModelBase(ABC):
    """
    Abstract base class for business models with NPV-based calculations.
    """

    def __init__(self, ecoData: dict, all_sim_ecoData: dict, interpolation_points: list):
        self.ecoData = ecoData
        self.all_sim_ecoData = all_sim_ecoData
        self.interpolation_points = interpolation_points
        self._discount_factors_cache = None

    # ==================================================================
    # CACHE HELPERS
    # ==================================================================

    def _cache_key(self, name: str, *parts) -> tuple:
        """
        Stable key for data-level BM postprocessing cache.

        The cache is valid only for one fixed optimization result.
        It must be cleared before/after every new optimization run.
        """
        return (name, tuple(parts))

    def _get_bm_cache(self, data) -> dict:
        cache = getattr(data, "_bm_postprocessing_cache", None)
        if cache is None:
            cache = {}
            setattr(data, "_bm_postprocessing_cache", cache)
        return cache

    def _clear_bm_cache(self, data) -> None:
        if hasattr(data, "_bm_postprocessing_cache"):
            delattr(data, "_bm_postprocessing_cache")

    def _require_decentral_costs(self, kpis):
        """
        Return decentralized annualized device costs or fail loudly.

        Required before BM postprocessing whenever decentralized BOI/HP/PV
        investment costs enter NPV or p_min calculations.
        """
        costs = getattr(kpis, "decentral_individual_devices_annualized_cost", None)

        if costs is None:
            raise RuntimeError(
                "BusinessModelBase: decentral_individual_devices_annualized_cost "
                "is missing. KPIs.calc_annual_cost_total() must run before "
                "calculateBMKPIs()."
            )

        if not isinstance(costs, dict):
            raise RuntimeError(
                "BusinessModelBase: decentral_individual_devices_annualized_cost "
                f"has invalid type {type(costs).__name__}; expected dict."
            )

        if not costs:
            raise RuntimeError(
                "BusinessModelBase: decentral_individual_devices_annualized_cost "
                "is empty. KPIs.calc_annual_cost_total() must run before "
                "calculateBMKPIs(), or no decentralized devices were costed."
            )

        return costs

    # ==================================================================
    # DISKONTIERUNG UND BARWERTBERECHNUNG
    # ==================================================================

    def _interest_rate(self) -> float:
        return float(self.ecoData["interest_rate"])

    def _observation_time(self) -> int:
        return int(self.ecoData["observation_time"])

    def _discount_factor(self, year: int) -> float:
        """DF(t) = 1 / (1 + i)^t"""
        q = 1.0 + self._interest_rate()
        return 1.0 / (q ** year)

    def _discount_factors(self) -> Dict[int, float]:
        if self._discount_factors_cache is None:
            n_obs = self._observation_time()
            self._discount_factors_cache = {
                0: 1.0,
                **{t: self._discount_factor(t) for t in range(1, n_obs + 1)}
            }
        return self._discount_factors_cache

    def _present_value_factor(self) -> float:
        """
        PVAF über Jahre 0..n-1 — konsistent mit MILP-Diskontierung
        in opti_dimensioning_central_devices (year=0 hat DF=1).

        Verwendung: TAC * PVAF, Energieflüsse, PV-Erlöse, alles was im
        MILP bereits diskontiert wurde.
        """
        i = self._interest_rate()
        n = self._observation_time()
        if i == 0:
            return float(n)
        q = 1.0 + i
        return (1.0 - (1.0 / q) ** n) / (1.0 - 1.0 / q)

    def _present_value_factor_vdi(self) -> float:
        """
        PVAF über Jahre 1..n — konsistent zu VDI 2067 Annuitäten
        aus KPIs.calc_annual_cost_device.

        Verwendung: dezentrale Geräte-Annuitäten (subsidized_annual_cost).
        """
        i = self._interest_rate()
        n = self._observation_time()
        if i == 0:
            return float(n)
        q = 1.0 + i
        return (1.0 - (1.0 / q) ** n) / i

    def _annuity_factor(self, life_time: float) -> float:
        """VDI-2067-Annuitätenfaktor mit Ersatzinvestitionen und Restwert."""
        import math

        n_obs = float(self._observation_time())
        life = float(life_time)

        if n_obs <= 0.0:
            raise ValueError(f"observation_time must be positive, got {n_obs!r}")
        if life <= 0.0:
            raise ValueError(f"life_time must be positive, got {life_time!r}")

        i = float(self._interest_rate())
        q = 1.0 + i

        if abs(i) < 1e-12:
            crf = 1.0 / n_obs
        else:
            crf = (q ** n_obs * i) / (q ** n_obs - 1.0)

        n_replacements = int(math.floor(n_obs / life))

        invest_replacements = sum(
            q ** (-j * life)
            for j in range(1, n_replacements + 1)
        )

        if abs(i) < 1e-12:
            res_value = ((n_replacements + 1) * life - n_obs) / life
        else:
            res_value = (
                    ((n_replacements + 1) * life - n_obs)
                    / life
                    * q ** (-n_obs)
            )

        return (1.0 + invest_replacements - res_value) * crf

    # ==================================================================
    # JAHRESSPEZIFISCHE BARWERTBERECHNUNG
    # ==================================================================

    def _year_interval_map(self, support_years: List[int]) -> Dict[int, List[int]]:
        """Mapping: Stützjahr → Liste der repräsentierten Jahre."""
        n_obs = self._observation_time()
        sorted_years = sorted(support_years)
        mapping = {}
        for i, sy in enumerate(sorted_years):
            if i < len(sorted_years) - 1:
                end_year = sorted_years[i + 1]
            else:
                end_year = n_obs + 1
            mapping[sy] = list(range(sy, end_year))
        return mapping

    def _bw_by_support_year(self, values_by_support_year: Dict[int, float]) -> float:
        """
        Discounted present value of support-year specific annual values.

        Jedes Stützjahr wird für alle repräsentierten Jahre
        einzeln mit dem korrekten DF diskontiert.
        """
        if not values_by_support_year:
            return 0.0
        support_years = sorted(values_by_support_year.keys())
        year_mapping = self._year_interval_map(support_years)
        discount_factors = self._discount_factors()

        bw = 0.0
        for sy in support_years:
            value = values_by_support_year[sy]
            for year in year_mapping[sy]:
                if year in discount_factors:
                    bw += value * discount_factors[year]
        return bw

    def _bw_constant_annual(self, annual_value: float) -> float:
        """
        Barwert eines konstanten Jahres-Cashflows über Jahre 0..n-1.
        Für TAC und Operator-Cashflows (MILP-Konvention).
        """
        return annual_value * self._present_value_factor()

    def _bw_constant_annual_vdi(self, annual_value: float) -> float:
        """
        Barwert einer VDI-2067-Annuität über Jahre 1..n.
        Für dezentrale Geräte-Annuitäten aus KPIs.
        """
        return annual_value * self._present_value_factor_vdi()

    # ==================================================================
    # WÄRMELIEFERUNG
    # ==================================================================

    def _heat_demand_building(self, data, n: int) -> float:
        """Annual useful heat demand of one building [kWh/a]."""
        dt = float(data.time["timeResolution"])
        heat = np.array(data.district[n]["user"].heat, dtype=float)
        dhw = np.array(data.district[n]["user"].dhw, dtype=float)
        return float(np.sum(heat + dhw) * dt / 3600.0 / 1000.0)

    def _heat_delivered_total(self, data) -> float:
        """Annual useful heat delivered to all HEAT_GRID buildings [kWh/a]."""
        cache = self._get_bm_cache(data)
        key = self._cache_key("heat_delivered_total")
        if key in cache:
            return cache[key]

        dt = float(data.time["timeResolution"])
        q = 0.0
        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue
            heat = np.array(data.district[n]["user"].heat, dtype=float)
            dhw = np.array(data.district[n]["user"].dhw, dtype=float)
            q += float(np.sum(heat + dhw) * dt / 3600.0 / 1000.0)

        cache[key] = q
        return q

    def _heat_delivered_by_building(self, data) -> Dict[int, float]:
        """Annual useful heat delivered per HEAT_GRID building [kWh/a]."""
        cache = self._get_bm_cache(data)
        key = self._cache_key("heat_delivered_by_building")
        if key in cache:
            return cache[key]

        dt = float(data.time["timeResolution"])
        q_by_building = {}
        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue
            heat = np.array(data.district[n]["user"].heat, dtype=float)
            dhw = np.array(data.district[n]["user"].dhw, dtype=float)
            q_by_building[n] = float(np.sum(heat + dhw) * dt / 3600.0 / 1000.0)

        cache[key] = q_by_building
        return q_by_building

    # ==================================================================
    # PV-STROMFLÜSSE (für Strom-NPV Berechnung)
    # ==================================================================

    def _pv_flows_by_building_year(self, data, result: dict) -> Dict[int, Dict[int, dict]]:
        """PV electricity flows per building and support year [MWh/a]."""
        support_years = sorted(result.get("rev_feed_in_el_by_year", {}).keys())
        if not support_years:
            support_years = list(self.interpolation_points)

        cache = self._get_bm_cache(data)
        key = self._cache_key("pv_flows_by_building_year", tuple(support_years))
        if key in cache:
            return cache[key]

        dt = float(data.time["timeResolution"])
        factor = dt / 3600.0 / 1e6

        clusters = list(getattr(data, "clusters", range(data.time["clusterNumber"])))
        cluster_weights = data.clusterWeights

        flows = {}
        for year in support_years:
            flows[year] = {}
            for n in range(len(data.district)):
                E_total = 0.0
                E_btm = 0.0

                for c in range(len(clusters)):
                    cw = float(cluster_weights[clusters[c]])
                    res = data.resultsOptimization[year][c][n]

                    pv_el = np.array(res.get("PV", {}).get("P_el", [0]), dtype=float)
                    demand = np.array(res.get("Elec_dem", {}).get("P_el", [0]), dtype=float)

                    T = min(len(pv_el), len(demand))
                    if T == 0:
                        continue
                    pv_el = np.clip(pv_el[:T], 0, None)
                    demand = np.clip(demand[:T], 0, None)

                    btm = np.minimum(pv_el, demand)
                    E_total += cw * pv_el.sum() * factor
                    E_btm += cw * btm.sum() * factor

                flows[year][n] = {
                    "E_pv_total_MWh": E_total,
                    "E_pv_btm_MWh": E_btm,
                    "E_pv_export_MWh": E_total - E_btm,
                }

        cache[key] = flows
        return flows

    def _pv_flows_by_year(self, data, result: dict) -> Dict[int, dict]:
        """Aggregated decentralized PV flows per support year [MWh/a]."""
        by_building = self._pv_flows_by_building_year(data, result)

        flows_by_year = {}

        for year, building_data in by_building.items():
            e_total = 0.0
            e_btm = 0.0
            e_export = 0.0

            for n, flows in building_data.items():
                e_total += flows.get("E_pv_total_MWh", 0.0)
                e_btm += flows.get("E_pv_btm_MWh", 0.0)
                e_export += flows.get("E_pv_export_MWh", 0.0)

            flows_by_year[year] = {
                "E_pv_total_MWh": e_total,
                "E_pv_btm_MWh": e_btm,
                "E_pv_export_MWh": e_export,
            }

        return flows_by_year

    # ==================================================================
    # STROM-NPV BERECHNUNG (nur echte Zahlungsströme!)
    # ==================================================================

    def _bw_pv_feed_in_by_building(
        self,
        data,
        pv_flows_by_building_year: Dict[int, Dict[int, dict]],
    ) -> Dict[int, float]:
        """
        Present value of PV feed-in revenues per building [EUR].

        Only HEAT_GRID buildings are included.
        Feed-in tariff is taken from the building-side price (revenue_feed_in_el),
        since decentralized PV belongs to the end customer in all BMs that use this method.
        """
        support_years = sorted(pv_flows_by_building_year.keys())
        if not support_years:
            return {}

        cache = self._get_bm_cache(data)
        key = self._cache_key("bw_pv_feed_in_by_building", tuple(support_years))
        if key in cache:
            return cache[key]

        bw_by_building = {}
        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue

            revenue_by_year = {}
            for year in support_years:
                flows = pv_flows_by_building_year[year].get(n, {})
                E_export = flows.get("E_pv_export_MWh", 0.0)
                p_feedin = self.all_sim_ecoData[year]["revenue_feed_in_el"]
                revenue_by_year[year] = E_export * p_feedin * 1000.0

            bw_by_building[n] = self._bw_by_support_year(revenue_by_year)

        cache[key] = bw_by_building
        return bw_by_building

    def _bw_pv_local_cost_by_building(
        self,
        data,
        pv_flows_by_building_year: Dict[int, Dict[int, dict]],
        alpha: float,
    ) -> Dict[int, float]:
        """
        Present value of end-customer payments for directly consumed building PV [EUR].

        The payment is valued at p_ms = alpha * p_retail for the behind-the-meter
        PV share E_pv_btm_MWh.
        """
        support_years = sorted(pv_flows_by_building_year.keys())
        if not support_years:
            return {}

        alpha = float(alpha)
        cache = self._get_bm_cache(data)
        key = self._cache_key("bw_pv_local_cost_by_building", tuple(support_years), alpha)
        if key in cache:
            return cache[key]

        bw_by_building = {}
        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue

            cost_by_year = {}
            for year in support_years:
                p_retail = self.all_sim_ecoData[year]["price_supply_el"]
                flows = pv_flows_by_building_year.get(year, {}).get(n, {})
                e_pv_btm_mwh = flows.get("E_pv_btm_MWh", 0.0)
                cost_by_year[year] = e_pv_btm_mwh * alpha * p_retail * 1000.0

            bw_by_building[n] = self._bw_by_support_year(cost_by_year)

        cache[key] = bw_by_building
        return bw_by_building

    def _bw_pv_operator_revenue_by_building(self,data,pv_flows_by_building_year: Dict[int, Dict[int, dict]],alpha: float, ) -> Dict[int, float]:

        support_years = sorted(pv_flows_by_building_year.keys())
        if not support_years:
            return {}

        alpha = float(alpha)
        bw_by_building = {}

        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue

            rev_by_year = {}
            for year in support_years:
                p_retail = float(self.all_sim_ecoData[year]["price_supply_el"])
                p_eh = float(self.all_sim_ecoData[year].get(
                    "price_supply_el_eh", p_retail))
                p_feedin = float(self.all_sim_ecoData[year]["revenue_feed_in_el"])

                flows = pv_flows_by_building_year.get(year, {}).get(n, {})
                e_btm = flows.get("E_pv_btm_MWh", 0.0)
                e_exp = flows.get("E_pv_export_MWh", 0.0)

                rev_by_year[year] = (
                        e_btm * (alpha * p_retail - p_eh) * 1000.0
                        + e_exp * p_feedin * 1000.0
                )

            bw_by_building[n] = self._bw_by_support_year(rev_by_year)

        return bw_by_building

    def _bw_pv_operator_correction_kundenanlage(
            self,
            data,
            pv_flows_by_building_year: Dict[int, Dict[int, dict]],
    ) -> Dict[int, float] | float:
        """
        Kundenanlage-spezifische TAC-Korrektur und Einspeiseerlös für Operator-PV.

        Mieterstrom-Zahlung wird separat über _npv_strom_wn_by_building
        eingerechnet (Verbrauch = Σ Elec_dem * alpha * p_retail).
        Hier: nur Einspeise-Erlös + TAC-Korrektur:

            Cashflow_y = E_export_y * p_feedin_y - E_btm_y * p_supply_eh_y
        """
        support_years = sorted(pv_flows_by_building_year.keys())
        if not support_years:
            return 0.0

        rev_by_year = {}
        for year in support_years:
            p_eh = float(self.all_sim_ecoData[year].get(
                "price_supply_el_eh",
                self.all_sim_ecoData[year]["price_supply_el"]))
            p_feedin = float(self.all_sim_ecoData[year]["revenue_feed_in_el"])
            total = 0.0
            for n, flows in pv_flows_by_building_year[year].items():
                heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
                if heater != "HEAT_GRID":
                    continue
                total += (
                        flows.get("E_pv_btm_MWh", 0.0) * p_eh * 1000.0
                        - flows.get("E_pv_export_MWh", 0.0) * p_feedin * 1000.0
                )
            rev_by_year[year] = total

        return self._bw_by_support_year(rev_by_year)

    def _bw_grid_tac_correction_residual(self, data, support_years) -> float:
        """
        Approximative TAC-Korrektur für BMs ohne Operator-Stromgeschäft
        (Contracting BM2, GGV, Genossenschaft).

        Das MILP enthält residualen Haushaltsstrombezug in supply_costs_el
        über dem["power"], obwohl Endkunden diesen Strom selbst beziehen.

        Bewertet wird mit price_supply_el_eh, weil genau dieser Preis im TAC
        für supply_costs_el verwendet wird.

        Kein HEAT_GRID-Filter, weil dem["power"] aktuell Strom aller Gebäude
        umfasst.
        """
        dt = float(data.time["timeResolution"])
        clusters = list(getattr(data, "clusters", range(data.time["clusterNumber"])))
        cluster_weights = data.clusterWeights

        cost_by_year = {}

        for year in support_years:
            p_eh = float(
                self.all_sim_ecoData[year].get(
                    "price_supply_el_eh",
                    self.all_sim_ecoData[year]["price_supply_el"],
                )
            )

            total = 0.0

            for n in range(len(data.district)):
                for c in range(len(clusters)):
                    cw = float(cluster_weights[clusters[c]])
                    res = data.resultsOptimization[year][c][n]

                    res_load = np.array(res.get("res_load", [0.0]), dtype=float)
                    grid_kwh = (
                        np.maximum(res_load, 0.0).sum()
                        * dt / 3600.0 / 1000.0
                    )

                    total += cw * grid_kwh * p_eh

            cost_by_year[year] = total

        return self._bw_by_support_year(cost_by_year)

    def _bw_grid_cost_by_building(
        self,
        data,
        result: dict,
        support_years: Optional[List[int]] = None,
    ) -> Dict[int, float]:
        """
        Present value of grid electricity procurement costs per connected building.

        Real cash flow: grid import × retail electricity price
        """
        if support_years is None:
            support_years = list(self.interpolation_points)
        support_years = list(support_years)

        cache = self._get_bm_cache(data)
        key = self._cache_key("bw_grid_cost_by_building", tuple(support_years))
        if key in cache:
            return cache[key]

        dt = float(data.time["timeResolution"])
        clusters = list(getattr(data, "clusters", range(data.time["clusterNumber"])))
        cluster_weights = data.clusterWeights

        bw_by_building = {}
        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue

            cost_by_year = {}
            for year in support_years:
                p_retail = self.all_sim_ecoData[year]["price_supply_el"]
                cost = 0.0

                for c in range(len(clusters)):
                    cw = float(cluster_weights[clusters[c]])
                    res = data.resultsOptimization[year][c][n]

                    res_load = np.array(res.get("res_load", [0]), dtype=float)
                    grid_kwh = np.maximum(res_load, 0.0).sum() * dt / 3600.0 / 1000.0
                    cost += cw * grid_kwh * p_retail

                cost_by_year[year] = cost

            bw_by_building[n] = self._bw_by_support_year(cost_by_year)

        cache[key] = bw_by_building
        return bw_by_building

    def _bw_internal_el_payment_by_building(
        self,
        data,
        support_years: List[int],
        price_by_year: Dict[int, float],
    ) -> Dict[int, float]:
        """
        Present value of end-customer electricity payments for total building demand [EUR].

        This is used when the customer pays a uniform internal tariff for the full
        electricity demand, independent of source allocation.
        """
        support_years = list(support_years)
        price_key = tuple((int(y), float(price_by_year.get(y, 0.0))) for y in support_years)

        cache = self._get_bm_cache(data)
        key = self._cache_key("bw_internal_el_payment_by_building", tuple(support_years), price_key)
        if key in cache:
            return cache[key]

        dt = float(data.time["timeResolution"])
        clusters = list(getattr(data, "clusters", range(data.time["clusterNumber"])))
        cluster_weights = data.clusterWeights

        bw_by_building = {}
        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue

            cost_by_year = {}
            for year in support_years:
                p_el = float(price_by_year.get(year, 0.0))
                cost = 0.0

                for c in range(len(clusters)):
                    cw = float(cluster_weights[clusters[c]])
                    res = data.resultsOptimization[year][c][n]

                    demand = np.array(res.get("Elec_dem", {}).get("P_el", [0]), dtype=float)
                    demand_kwh = demand.sum() * dt / 3600.0 / 1000.0
                    cost += cw * demand_kwh * p_el

                cost_by_year[year] = cost

            bw_by_building[n] = self._bw_by_support_year(cost_by_year)

        cache[key] = bw_by_building
        return bw_by_building

    # ==================================================================
    # p_max BERECHNUNG
    # ==================================================================

    def _p_max_from_npvs(
            self,
            heat_kwh: float,
            npv_ref: float,
            npv_wn_other: float = 0.0
    ) -> Optional[float]:
        """
        Maximum acceptable heat price for one building from total NPV equality.

        End-customer view:
            NPV_wn(p) = - heat_kwh * p * PVAF + npv_wn_other

        Indifference condition:
            NPV_wn(p_max) = NPV_ref

        Therefore:
            p_max = (npv_wn_other - npv_ref) / (heat_kwh * PVAF)
        """
        if heat_kwh <= 0:
            return None

        pvaf = self._present_value_factor()
        p_max = (npv_wn_other - npv_ref) / (heat_kwh * pvaf)

        # Negative p_max means: even at zero heat price the WN case is
        # worse than the reference case. Do not mask this as p_max = 0.
        if p_max < 0.0:
            return None

        return p_max

    def _p_max_building(
            self,
            heat_kwh: float,
            npv_ref: float,
            npv_wn_other: float = 0.0
    ) -> Optional[float]:
        """Alias for `_p_max_from_npvs`."""
        return self._p_max_from_npvs(
            heat_kwh=heat_kwh,
            npv_ref=npv_ref,
            npv_wn_other=npv_wn_other,
        )

    # ------------------------------------------------------------------
    # Legacy wrappers (temporary compatibility during refactoring)
    # ------------------------------------------------------------------

    def _calc_p_max_building(
            self,
            q_heat_kwh: float,
            npv_ref: float,
            bw_stromvorteil: float = 0.0
    ) -> Optional[float]:
        """
        Legacy wrapper.

        `bw_stromvorteil` is interpreted as the already-discounted non-heat part
        of the end-customer NPV in the WN case.
        """
        return self._p_max_from_npvs(
            heat_kwh=q_heat_kwh,
            npv_ref=npv_ref,
            npv_wn_other=bw_stromvorteil,
        )

    # ==================================================================
    # GRID CONSTRAINTS
    # ==================================================================

    def configure_grid_constraints(
            self, data,
            din_csv_path=None, amev_csv_path=None,
            cosphi: Optional[float] = None,
            safety_factor: Optional[float] = None,
            g: Optional[float] = None,
            trafo_steps=DIN_TRAFO_STEPS_KVA,
            out_dir=None,
    ) -> dict:

        """
        Apply per-building house-connection limits and (optionally) pre-size
        the transformer. Supports residential (DIN 18015-1) and non-residential
        (AMEV EltAnlagen 2025) buildings.

        The transformer-sizing behaviour is controlled by
        ``data.site["trafo_sizing_mode"]``:
          - "variable"   : do NOT pre-size; the design MILP picks the kVA step
                           endogenously, using the lower bound from the
                           house-connection limits as a minimum-size constraint.
          - "din_kerber" : pre-size to the smallest DIN 42508 step satisfying
                           the lower bound (legacy behaviour).
          - "manual"     : do not auto-size at all; leave ``trafoMax_W``
                           unchanged.
        """
        from districtgenerator.functions.din_house_connection_limits import (
            apply_house_connection_limits,
        )
        from districtgenerator.functions.trafo_sizing import (
            trafo_lower_bound_from_house_connections,
        )

        summary: dict = {}
        if din_csv_path is None:
            data.site["enable_buildingMax_W"] = False
            return summary

        eco = self.ecoData
        if cosphi is None:
            cosphi = float(eco.get("trafo_cosphi", 0.95))
        if safety_factor is None:
            safety_factor = float(eco.get("trafo_safety_factor", 1.10))
        if g is None:
            g = float(eco.get("kerber_g_residential", 0.07))
        site_coinc = float(eco.get("amev_site_coincidence", 0.8))

        apply_house_connection_limits(
            data=data, enabled=True,
            din_csv_path=din_csv_path,
            amev_csv_path=amev_csv_path,
            write_back_to_buildings=True,
        )
        data.site["enable_buildingMax_W"] = True

        mode = str(data.site.get("trafo_sizing_mode", "variable")).lower()

        if mode == "manual":
            return summary

        if mode == "din_kerber":
            summary = trafo_limit_from_house_connection_limits(
                data=data, cosphi=cosphi, safety_factor=safety_factor,
                g=g, steps=trafo_steps,
                out_dir=out_dir, write_json=(out_dir is not None),
            )
            data.site["enable_trafoMax_W"] = True
            return summary

        # mode == "variable": for the default (non-customer-installation)
        # business model, the transformer is owned and dimensioned by the
        # DSO. We use the SAME DIN/Kerber/AMEV lower bound as the
        # customer-installation case, but FIX the transformer rating to
        # ``min_din_step_kVA`` (no endogenous sizing optimisation) and
        # enforce ``grid_limit_el <= trafoMax_W`` as a hard physical cap.
        # The DSO transformer investment does NOT enter the objective:
        # it is paid by the DSO and recovered via grid fees, which are
        # implicit in the residential electricity price.
        bound = trafo_lower_bound_from_house_connections(
            data=data, cosphi=cosphi, safety_factor=safety_factor,
            g_residential=g, site_coincidence=site_coinc, steps=trafo_steps,
        )
        chosen_kVA = bound["min_din_step_kVA"]
        trafoMax_W = chosen_kVA * 1000.0 * cosphi

        data.site["trafo_min_kVA"] = chosen_kVA
        data.site["trafo_steps_kVA"] = list(trafo_steps)
        data.site["trafo_cosphi"] = cosphi
        data.site["trafo_chosen_kVA"] = chosen_kVA
        data.site["trafoMax_W"] = trafoMax_W
        data.site["enable_trafoMax_W"] = True
        # DSO pays the trafo, not the district -> investment NOT endogenous.
        data.site["trafo_invest_endogenous"] = False
        data.site["trafo_sizing_summary"] = {
            **bound,
            "chosen_transformer_kVA": chosen_kVA,
            "trafoMax_W_for_optimization": trafoMax_W,
            "owner": "DSO",
        }
        return data.site["trafo_sizing_summary"]

    # ==================================================================
    # LEGACY METHODS (Abwärtskompatibilität)
    # ==================================================================

    def _support_year_weights(self, support_years: list) -> dict:
        n_obs = self._observation_time()
        sorted_years = sorted(support_years)
        return {
            y: (sorted_years[i + 1] - y if i < len(sorted_years) - 1 else n_obs - y)
            for i, y in enumerate(sorted_years)
        }


    def _get_interest_rate(self) -> float:
        """Legacy wrapper for renamed helper."""
        return self._interest_rate()

    def _get_observation_time(self) -> int:
        """Legacy wrapper for renamed helper."""
        return self._observation_time()

    def _get_discount_factors(self) -> Dict[int, float]:
        """Legacy wrapper for renamed helper."""
        return self._discount_factors()

    def _get_year_interval_mapping(self, support_years: List[int]) -> Dict[int, List[int]]:
        """Legacy wrapper for renamed helper."""
        return self._year_interval_map(support_years)

    def _bw_annual_values_by_support_year(self, values_by_support_year: Dict[int, float]) -> float:
        """Legacy wrapper for renamed helper."""
        return self._bw_by_support_year(values_by_support_year)

    def _bw_constant_annual_value(self, annual_value: float) -> float:
        """Legacy wrapper for renamed helper."""
        return self._bw_constant_annual(annual_value)

    def _Q_building_kwh(self, data, n: int) -> float:
        """Legacy wrapper for renamed helper."""
        return self._heat_demand_building(data, n)

    def _Q_heat_delivered(self, data) -> float:
        """Legacy wrapper for renamed helper."""
        return self._heat_delivered_total(data)

    def _Q_heat_delivered_by_building(self, data) -> Dict[int, float]:
        """Legacy wrapper for renamed helper."""
        return self._heat_delivered_by_building(data)

    def _calc_pv_flows_by_year(self, data, result: dict) -> Dict[int, dict]:
        """Legacy wrapper for renamed helper."""
        return self._pv_flows_by_year(data, result)

    def _calc_pv_flows_by_building_year(self, data, result: dict) -> Dict[int, Dict[int, dict]]:
        """Legacy wrapper for renamed helper."""
        return self._pv_flows_by_building_year(data, result)

    def _calc_bw_pv_stromvorteil_by_building(
            self,
            data,
            pv_flows_by_building_year: Dict[int, Dict[int, dict]]
    ) -> Dict[int, float]:
        """Legacy wrapper for renamed helper."""
        return self._bw_pv_feed_in_by_building(data, pv_flows_by_building_year)

    def _calc_bw_netzbezug_by_building(
            self,
            data,
            result: dict
    ) -> Dict[int, float]:
        """Legacy wrapper for renamed helper."""
        return self._bw_grid_cost_by_building(data, result)


    # ==================================================================
    # INTERFACE
    # ==================================================================

    @abstractmethod
    def get_price_el_revenue_by_year(self) -> dict:
        """Return year-specific local electricity revenue."""
        pass

    def apply_operational_ecoData(self, sim_ecoData: dict, year) -> dict:
        """Enrich sim_ecoData with BM-specific operational values."""
        eco = copy.deepcopy(sim_ecoData)
        eco["price_el_revenue"] = self.get_price_el_revenue_by_year().get(year, 0.0)
        return eco

    @abstractmethod
    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """Compute p_min and p_max after optimization."""
        pass