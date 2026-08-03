# -*- coding: utf-8 -*-
"""
Wärmecontracting im Gemeinschaftlicher Gebäudeversorgung Business Model (BM 3)

Ownership
---------
- Energy hub: operator
- District heating network: operator
- Decentralized PV: operator
- Public electricity grid: DSO

Electricity logic
-----------------
- No local electricity sales from the energy hub to buildings are modeled here.
- Building-level PV electricity is sold to tenants at the Mieterstrom tariff
  p_ms = alpha * p_retail.
- Residual tenant electricity demand is procured individually from the public grid.
- Surplus PV electricity is exported to the public grid and remunerated via
  the feed-in tariff.

Post-processing logic
---------------------
- p_min is the cost-covering offered heat price of the model.
  It is derived from the discounted net system cost of the operator.
- p_max is derived from the end-customer NPV indifference condition
  against the reference case.
- The class provides model-specific NPV quantities and scenario results,
  but it does not make the final feasibility decision of the overall run.
"""

from typing import Dict, Optional
import numpy as np

from districtgenerator.business_models.Basis import BusinessModelBase


class WaermecontractingGGVBM(BusinessModelBase):

    def get_price_el_revenue_by_year(self) -> dict:
        """
        No optimized local electricity revenue of the energy hub is modeled here.

        The Mieterstrom revenue considered in this class originates from
        decentralized building-level PV and is handled in post-processing.
        """
        return {year: 0.0 for year in self.interpolation_points}

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        Calculate model-specific KPIs for the Mieterstrom business model.

        Implemented here:
        - cost-covering heat price p_min from operator-side net system costs
        - maximum acceptable heat price p_max from end-customer NPV equality
        - scenario-specific helper outputs for the run logic

        Not implemented here:
        - final feasibility decision of the overall workflow
        - iterative exclusion / re-run control
        """
        support_years = list(self.interpolation_points)
        if not support_years:
            kpis.p_min = None
            kpis.p_max = None
            return

        # Diagnostic only: TAC is no longer the heat-price numerator.
        legacy_tac_total = float(result.get("tac", 0.0) or 0.0)

        heat_cost = self._operator_heat_cost_lcoh_like(
            kpis=kpis,
            data=data,
            support_years=support_years,
        )
        heat_total = heat_cost["heat_total_kWh"]
        heat_by_building = self._heat_delivered_by_building(data)
        bw_heat_total = heat_cost["bw_heat_total"]
        bw_operator_heat_cost = heat_cost["bw_heat_cost"]

        # Dezentrale PV gehört dem Betreiber und wird zusätzlich zur
        # LCOH-nah rekonstruierten Wärmekostenbasis berücksichtigt.
        # Harte Prüfung — ohne dezentrale Kostendaten ist p_min systematisch
        # zu niedrig. Lieber crashen als still falsche Ergebnisse liefern.
        dev_costs_all = self._require_decentral_costs(kpis)

        pv_cost_ann_total = 0.0
        for n, n_costs in dev_costs_all.items():
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue
            if "PV" in n_costs:
                pv_cost_ann_total += float(n_costs["PV"].get("subsidized_annual_cost", 0.0))

        bw_pv_cost_total = self._bw_constant_annual(pv_cost_ann_total)
        bw_operator_heat_cost_incl_pv = bw_operator_heat_cost + bw_pv_cost_total

        p_min = bw_operator_heat_cost_incl_pv / bw_heat_total if bw_heat_total > 0 else None

        npv_ref_by_building = self.ecoData.get("npv_ref_by_building", {})
        scenario = self.ecoData.get("scenario", "B")

        npv_strom_wn_by_building = self._npv_strom_wn_by_building(
            data=data,
            result=result,
        )
        npv_wn_at_p_min_by_building = self._npv_wn_by_building_at_price(
            heat_by_building=heat_by_building,
            npv_strom_wn_by_building=npv_strom_wn_by_building,
            heat_price=p_min,
        )

        scenario_a = self._scenario_a(
            heat_by_building=heat_by_building,
            npv_ref_by_building=npv_ref_by_building,
            npv_strom_wn_by_building=npv_strom_wn_by_building,
            npv_wn_at_price_by_building=npv_wn_at_p_min_by_building,
        )
        scenario_b = self._scenario_b(
            heat_by_building=heat_by_building,
            npv_ref_by_building=npv_ref_by_building,
            npv_strom_wn_by_building=npv_strom_wn_by_building,
            npv_wn_at_price_by_building=npv_wn_at_p_min_by_building,
        )

        p_max = scenario_a["p_max"] if scenario == "A" else scenario_b["p_max"]

        kpis.p_min = p_min
        kpis.p_max = p_max
        kpis.gemeinschaftliche_gebaeudeversorgung_breakdown = {
            "legacy_tac_total_diagnostic": legacy_tac_total,
            "cost_basis": heat_cost["method"],
            "operator_heat_cost_by_year": heat_cost["annual_heat_cost_by_year"],
            "operator_heat_cost_details_by_year": heat_cost["year_details"],
            "bw_operator_heat_cost": bw_operator_heat_cost,
            "pv_cost_ann_total": pv_cost_ann_total,
            "bw_pv_cost_total": bw_pv_cost_total,
            "bw_operator_heat_cost_incl_pv": bw_operator_heat_cost_incl_pv,
            "heat_total_kWh": heat_total,
            "bw_heat_total": bw_heat_total,
            "p_min": p_min,
            "p_max": p_max,
            "p_max_a": scenario_a["p_max"],
            "p_max_b": scenario_b["p_max"],
            "alpha": self.ecoData.get("alpha", 0.9),
            "scenario": scenario,
            "npv_strom_wn_by_building": npv_strom_wn_by_building,
            "npv_wn_at_p_min_by_building": npv_wn_at_p_min_by_building,
            "scenario_a": scenario_a,
            "scenario_b": scenario_b,
        }

        # WaermecontractingGGV:
        kpis.bm_breakdown = kpis.gemeinschaftliche_gebaeudeversorgung_breakdown

    def _npv_strom_wn_by_building(self, data, result: dict, kpis=None) -> Dict[int, float]:
        """
        Building-level electricity-side NPV in the WN case.

        Mieterstrom-specific assumptions:
        - building-level PV is owned by the operator
        - PV investment costs are reflected in TAC / p_min
        - the tenant has no PV investment; they only pay for electricity consumed
        - tenants buy directly consumed PV electricity at p_ms = alpha * p_retail
        - residual electricity demand is bought by tenants from the public grid
        - no PV investment cost or feed-in revenue is assigned to the tenant side

        Therefore, the tenant-side electricity NPV consists only of electricity
        payments:
        - payment for directly consumed PV electricity at p_ms
        - payment for residual grid electricity at p_retail
        """
        alpha = float(self.ecoData.get("alpha", 0.9))

        pv_flows_by_building_year = self._pv_flows_by_building_year(data, result)
        support_years = sorted(pv_flows_by_building_year.keys())

        bw_pv_local_cost_by_building = self._bw_pv_local_cost_by_building(
            data=data,
            pv_flows_by_building_year=pv_flows_by_building_year,
            alpha=alpha,
        )
        bw_grid_cost_by_building = self._bw_grid_cost_by_building(
            data=data,
            result=result,
            support_years=support_years,
        )

        npv_by_building = {}

        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue

            bw_pv_local_cost = bw_pv_local_cost_by_building.get(n, 0.0)
            bw_grid_cost = bw_grid_cost_by_building.get(n, 0.0)

            npv_by_building[n] = -bw_pv_local_cost - bw_grid_cost

        return npv_by_building
    def _npv_wn_by_building_at_price(
        self,
        heat_by_building: Dict[int, float],
        npv_strom_wn_by_building: Dict[int, float],
        heat_price: Optional[float],
    ) -> Dict[int, float]:
        """
        Total end-customer NPV in the WN case for a given heat price.

        NPV_wn,i(p) = - heat_i * p * PVAF + npv_strom_wn_i
        """
        if heat_price is None:
            return {}

        pvaf = self._present_value_factor()
        npv_by_building = {}

        for n, heat_kwh in heat_by_building.items():
            npv_heat = -heat_kwh * heat_price * pvaf
            npv_strom = npv_strom_wn_by_building.get(n, 0.0)
            npv_by_building[n] = npv_heat + npv_strom

        return npv_by_building

    def _scenario_a(
        self,
        heat_by_building: Dict[int, float],
        npv_ref_by_building: Dict[int, float],
        npv_strom_wn_by_building: Dict[int, float],
        npv_wn_at_price_by_building: Dict[int, float],
    ) -> dict:
        """
        Scenario A: no mandatory connection.

        The class only prepares building-level results.
        The final exclusion, re-run, and feasibility decision are handled outside.
        """
        if not npv_ref_by_building:
            return {
                "connected": list(heat_by_building.keys()),
                "excluded": [],
                "needs_iteration": False,
                "p_max": None,
                "p_max_by_building": {},
                "building_details": {},
            }

        connected = []
        excluded = []
        p_max_by_building = {}
        building_details = {}

        for n, heat_kwh in heat_by_building.items():
            npv_ref = npv_ref_by_building.get(n, 0.0)
            npv_wn_at_price = npv_wn_at_price_by_building.get(n, 0.0)
            npv_strom_wn = npv_strom_wn_by_building.get(n, 0.0)

            p_max_i = self._p_max_from_npvs(
                heat_kwh=heat_kwh,
                npv_ref=npv_ref,
                npv_wn_other=npv_strom_wn,
            )
            p_max_by_building[n] = p_max_i

            is_economic_at_price = (
                    p_max_i is not None
                    and npv_wn_at_price >= npv_ref)
            if is_economic_at_price:
                connected.append(n)
            else:
                excluded.append(n)

            building_details[n] = {
                "heat_kWh": heat_kwh,
                "npv_ref": npv_ref,
                "npv_strom_wn": npv_strom_wn,
                "npv_wn_at_price": npv_wn_at_price,
                "economic_at_price": is_economic_at_price,
                "p_max": p_max_i,
            }

        # PDF Bewertungslogik Szenario A:
        # "Für die verbleibenden Gebäude wird jeweils ein p_max,i berechnet.
        #  p_max = min_i(p_max,i)"
        # -> nur die nicht ausgeschlossenen Gebäude gehen in das min ein.
        valid_p_max = [
            p_max_by_building[n]
            for n in connected
            if p_max_by_building.get(n) is not None
        ]
        p_max = min(valid_p_max) if valid_p_max else None

        return {
            "connected": connected,
            "excluded": excluded,
            "needs_iteration": len(excluded) > 0,
            "p_max": p_max,
            "p_max_by_building": p_max_by_building,
            "building_details": building_details,
        }

    def _scenario_b(
        self,
        heat_by_building: Dict[int, float],
        npv_ref_by_building: Dict[int, float],
        npv_strom_wn_by_building: Dict[int, float],
        npv_wn_at_price_by_building: Dict[int, float],
    ) -> dict:
        """
        Scenario B: mandatory connection.

        The class provides the aggregate NPV quantities needed by the outer run logic.
        """
        if not npv_ref_by_building:
            return {
                "sum_npv_wn_at_price": 0.0,
                "sum_npv_ref": 0.0,
                "p_max": None,
                "connected_buildings": list(heat_by_building.keys()),
            }

        sum_npv_ref = 0.0
        sum_npv_wn_at_price = 0.0
        sum_npv_strom_wn = 0.0
        heat_total = 0.0

        for n, heat_kwh in heat_by_building.items():
            sum_npv_ref += npv_ref_by_building.get(n, 0.0)
            sum_npv_wn_at_price += npv_wn_at_price_by_building.get(n, 0.0)
            sum_npv_strom_wn += npv_strom_wn_by_building.get(n, 0.0)
            heat_total += heat_kwh

        p_max = self._p_max_from_npvs(
            heat_kwh=heat_total,
            npv_ref=sum_npv_ref,
            npv_wn_other=sum_npv_strom_wn,
        ) if heat_total > 0 else None

        return {
            "sum_npv_wn_at_price": sum_npv_wn_at_price,
            "sum_npv_ref": sum_npv_ref,
            "sum_npv_strom_wn": sum_npv_strom_wn,
            "heat_total_kWh": heat_total,
            "p_max": p_max,
            "connected_buildings": list(heat_by_building.keys()),
        }