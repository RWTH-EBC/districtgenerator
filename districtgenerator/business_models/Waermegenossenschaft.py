# -*- coding: utf-8 -*-
"""
Reine Wärmegenossenschaft (BM 3)

Inherits all electricity-side helpers from ContractingBM:
- Decentralized PV belongs to cooperative members
- Members bear PV investment costs and benefit from reduced grid procurement
  and feed-in revenues — identical to Contracting electricity logic

Key difference to ContractingBM:
- Heat price = LCOH (discounted TAC / discounted Q_heat) — no profit markup
- No p_max — members are owners, not customers
- Feasibility: NPV_WN(LCOH) >= NPV_Ref

LCOH note:
- LCOH = BW_TAC / BW_Q_heat — consistent with p_min of other BMs
- Different from kpis.lcoh_year_eh (yearly operative diagnostic value in KPIs.py)
"""

from .Waermecontracting import WaermecontractingBM


class WaermegenossenschaftBM(WaermecontractingBM):

    def get_price_el_revenue_by_year(self) -> dict:
        """No local electricity sales by the cooperative."""
        return {year: 0.0 for year in self.interpolation_points}

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        Calculate KPIs for the pure heat cooperative.

        Overrides ContractingBM.calculate_kpis:
        - Uses LCOH instead of p_min
        - No p_max
        - All electricity-side helpers (_npv_strom_wn_by_building,
          _scenario_a, _scenario_b) inherited from ContractingBM
          and now correctly include npv_strom_wn_by_building.
        """
        support_years = list(self.interpolation_points)
        if not support_years:
            kpis.p_min = None
            kpis.p_max = None
            kpis.lcoh = None
            return

        tac_total = float(result["tac"])
        bw_tac_total = self._bw_constant_annual(tac_total)

        heat_total = self._heat_delivered_total(data)
        heat_by_building = self._heat_delivered_by_building(data)
        bw_heat_total = self._bw_constant_annual(heat_total)

        # TAC-Korrektur: residualer Endkunden-Bezug ist im MILP-TAC enthalten, gehört aber dem Endkunden.
        bw_tac_correction_grid = self._bw_grid_tac_correction_residual(
            data=data, support_years=support_years)
        bw_tac_corrected = bw_tac_total - bw_tac_correction_grid

        lcoh = bw_tac_corrected / bw_heat_total if bw_heat_total > 0 else None

        npv_ref_by_building = self.ecoData.get("npv_ref_by_building", {})
        scenario = self.ecoData.get("scenario", "B")

        # Inherited from ContractingBM — PV costs on member side
        # Setzt voraus dass KPIs.py Fixkosten bereits berechnet hat (Standardreihenfolge).
        # Bei Änderung der Aufruforder → PV-Kosten = 0, kein Fehler.
        npv_strom_wn_by_building = self._npv_strom_wn_by_building(
            data=data,
            result=result,
            kpis=kpis,
        )
        npv_wn_at_lcoh_by_building = self._npv_wn_by_building_at_price(
            heat_by_building=heat_by_building,
            npv_strom_wn_by_building=npv_strom_wn_by_building,
            heat_price=lcoh,
        )

        # Inherited _scenario_a/_scenario_b from ContractingBM
        # — now include npv_strom_wn_by_building correctly
        scenario_a = self._scenario_a(
            heat_by_building=heat_by_building,
            npv_ref_by_building=npv_ref_by_building,
            npv_strom_wn_by_building=npv_strom_wn_by_building,
            npv_wn_at_price_by_building=npv_wn_at_lcoh_by_building,
        )
        scenario_b = self._scenario_b(
            heat_by_building=heat_by_building,
            npv_ref_by_building=npv_ref_by_building,
            npv_strom_wn_by_building=npv_strom_wn_by_building,
            npv_wn_at_price_by_building=npv_wn_at_lcoh_by_building,
        )

        # Genossenschaft hat fachlich kein p_max — Mitglieder sind Eigentümer.
        # Die geerbten Szenario-Methoden berechnen Indifferenz-Preise,
        # die hier nicht als p_max interpretiert werden dürfen.
        scenario_a["p_max"] = None
        scenario_a["p_max_by_building"] = {}
        scenario_b["p_max"] = None
        for details in scenario_a.get("building_details", {}).values():
            details["p_max"] = None

        kpis.lcoh = lcoh
        kpis.p_min = lcoh    # Alias — LCOH ist der kostendeckende Preis
        kpis.p_max = None    # Kein p_max — Mitglieder sind Eigentümer

        kpis.genossenschaft_breakdown = {
            "tac_total": tac_total,
            "bw_tac_total": bw_tac_total,
            "heat_total_kWh": heat_total,
            "bw_heat_total": bw_heat_total,
            "bw_tac_correction_grid": bw_tac_correction_grid,
            "bw_tac_corrected": bw_tac_corrected,
            "lcoh": lcoh,
            "p_min": lcoh,
            "p_max": None,
            "scenario": scenario,
            "npv_strom_wn_by_building": npv_strom_wn_by_building,
            "npv_wn_at_lcoh_by_building": npv_wn_at_lcoh_by_building,
            "scenario_a": scenario_a,
            "scenario_b": scenario_b,
        }

        # Waermegenossenschaft:
        kpis.bm_breakdown = kpis.genossenschaft_breakdown