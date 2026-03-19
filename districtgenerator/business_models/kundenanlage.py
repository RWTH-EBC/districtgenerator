# -*- coding: utf-8 -*-
"""
Kundenanlage Business Model (BM 2.4)

A single operator owns and operates the buildings PV systems, the energy hub,
the district heating network AND the local electricity grid incl. transformer.

Key difference vs Mieterstrom (BM 2.3):
  The operator owns the internal grid -> no network usage charges apply.
  Consequences:
    1. PV behind-the-meter revenue = full p_ms (no network fee deduction)
    2. Reststrom spread = p_ms - p_ret_op (no fee deduction)

Grid constraint difference vs all other BMs:
  The operator connects to the MEDIUM-VOLTAGE grid and owns the MV/LV
  transformer. The DIN/Kerber sizing determines which transformer the
  operator must purchase. This is NOT an external DSO constraint but an
  investment decision whose cost flows into p_min.

Additional cost vs all other BMs:
  Annualised investment + O&M of electricity grid (cables + transformer)
  are added to c_tot and flow into p_min.
  Cable length estimated from heat network pipeline (same street routing).
  Transformer cost scales with the DIN-derived kVA size.

p_min = (c_tot - rev_pv_btm - rev_pv_export - rev_reststrom) / Q_heat
  where c_tot = TAC_EH + c_pv_ann + c_elgrid_ann

p_max: read from ecoData["p_max"] (set manually after reference run).
"""

import math
from pathlib import Path
from typing import Optional

from .base import BusinessModelBase
from districtgenerator.functions.din_house_connection_limits import (
    apply_din_house_connection_limits,
)
from districtgenerator.functions.trafo_sizing import (
    trafo_limit_from_house_connection_limits,
    DIN_TRAFO_STEPS_KVA,
)


class KundenanlageBM(BusinessModelBase):

    # ------------------------------------------------------------------
    # configure_grid_constraints -- OVERRIDDEN for Kundenanlage
    # ------------------------------------------------------------------

    def configure_grid_constraints(
            self,
            data,
            din_csv_path: Optional[str | Path] = None,
            cosphi: float = 0.95,
            safety_factor: float = 1.10,
            g: float = 0.07,
            trafo_steps=DIN_TRAFO_STEPS_KVA,
            out_dir: Optional[Path] = None,
    ) -> dict:
        """
        Kundenanlage-specific grid constraint configuration.

        Key differences to the base class (DSO-owned grid):

        1. House-connection limits: SAME as base -- physical cable limits
           still apply even when the operator owns the grid.

        2. Transformer sizing: Always performed (auto_size_trafo is ignored).
           The operator MUST know which MV/LV transformer to purchase.
           However, trafoMax_W is NOT set as a hard optimiser constraint
           because the operator can choose a larger transformer if needed.

        3. The chosen kVA is stored in data.site["kundenanlage_trafo_kVA"]
           for cost scaling in _calc_elgrid_annual_cost().
        """
        summary = {}

        if din_csv_path is None:
            data.site["enable_buildingMax_W"] = False
            data.site["enable_trafoMax_W"] = False
            return summary

        # ── Step 1: Per-building house-connection limits (same as base) ──
        apply_din_house_connection_limits(
            data=data,
            enabled=True,
            din_csv_path=din_csv_path,
            write_back_to_buildings=True,
        )
        data.site["enable_buildingMax_W"] = False

        # ── Step 2: Trafo sizing (always, regardless of auto_size_trafo) ─
        summary = trafo_limit_from_house_connection_limits(
            data=data,
            cosphi=cosphi,
            safety_factor=safety_factor,
            g=g,
            steps=trafo_steps,
            out_dir=out_dir,
            write_json=(out_dir is not None),
        )

        # Operator owns the transformer → NOT an external DSO constraint.
        # The trafoMax_W value is stored but not enforced as a hard limit.
        data.site["enable_trafoMax_W"] = False

        # Store chosen trafo for cost calculation
        data.site["kundenanlage_trafo_kVA"] = summary["chosen_transformer_kVA"]

        # Warn if sizing exceeds largest available NS trafo
        if summary["chosen_transformer_kVA"] >= max(trafo_steps):
            print(
                f"WARNING KundenanlageBM: DIN-basierte Trafogröße "
                f"({summary['required_kVA']:.0f} kVA benötigt) übersteigt "
                f"größte NS-Stufe ({max(trafo_steps)} kVA). "
                f"Ein MS-Anschluss mit höherer Spannungsebene sollte "
                f"geprüft werden."
            )

        return summary

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------

    def get_price_el_revenue_by_year(self) -> dict:
        """
        Full tenant tariff for local delivery in Kundenanlage.
        No grid fees deducted because operator owns the local grid.
        """
        alpha = self.ecoData["alpha"]
        share_vat = self.ecoData["share_el_vat"]
        return {  year: (
                    alpha * self.all_sim_ecoData[year]["price_supply_el"]
                    - share_vat * self.all_sim_ecoData[year]["price_supply_el"]
            )
            for year in self.interpolation_points
        }

    # ------------------------------------------------------------------
    # calculate_kpis -- called after the optimiser has finished
    # ------------------------------------------------------------------

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        p_min = (TAC + c_pv_ann + c_elgrid_ann - rev_pv_btm - rev_pv_export) / Q_heat

        Cost structure and system boundary:

        TAC (from the optimizer):
            Includes only costs and revenues of the central energy hub (EH):
            - capital and operating costs of EH components
            - energy procurement costs (electricity, gas, etc.)
            - revenues from local electricity supply from the EH to consumers
              (rev_local_el, valued at p_ms)
            - revenues from EH electricity feed-in to the public grid
              (rev_feed_in_el)

            NOT included: decentralized building PV (neither costs nor revenues).

        Explicitly post-processed terms (not included in the optimizer):

            c_pv_ann:        annualized investment + O&M costs of decentralized PV systems
            c_elgrid_ann:    annualized cost of the local electricity grid
                             (cables + transformer)
            rev_pv_btm:      revenues from PV self-consumption within the building
                             (valued at p_ms)
            rev_pv_export:   revenues from PV feed-in to the public grid
                             (feed-in tariff)

        Symmetry principle:
            Both costs and revenues of decentralized PV are accounted for explicitly.
            This mirrors the structure used in the tenant electricity model (BM 2.3)
            and ensures that the allocation remains transparent and consistent.

        Customer installation specific features:
            - Own local grid -> no grid fees for EH-to-consumer or PV-to-consumer delivery
            - p_ms = alpha * p_ret (full tariff, no deductions)
            - local grid costs (c_elgrid_ann) are included in p_min
        """

        support_years = sorted(result["rev_local_el_by_year"].keys())
        weights = self._support_year_weights(support_years)

        # --- PV flows from decentral building PV ---
        pv_flows = self._calc_pv_flows(data, result)
        E_pv_btm_MWh = pv_flows["E_pv_btm_MWh"]
        E_pv_export_MWh = pv_flows["E_pv_export_MWh"]

        # --- Prices [EUR/kWh] ---
        p_ms_avg = self._weighted_avg_price("price_supply_el", support_years, weights) * self.ecoData["alpha"]
        p_feedin_avg = self._weighted_avg_price("revenue_feed_in_el", support_years, weights)

        # --- Revenues from decentral PV [EUR/a] ---
        rev_pv_btm = E_pv_btm_MWh * p_ms_avg * 1000
        rev_pv_export = E_pv_export_MWh * p_feedin_avg * 1000

        # --- Additional annual costs [EUR/a] ---
        c_pv_ann = self._calc_decentral_pv_annual_cost(kpis)
        c_elgrid_ann = self._calc_elgrid_annual_cost(data)

        c_tot = result["tac"] + c_pv_ann + c_elgrid_ann - rev_pv_btm - rev_pv_export
        Q_heat = self._Q_heat_delivered(data)

        kpis.p_min = c_tot / Q_heat if Q_heat > 0 else None
        kpis.p_max = self.ecoData.get("p_max", None)

        # --- Store diagnostics / transparency ---
        kpis.c_pv_ann = c_pv_ann
        kpis.c_elgrid_ann = c_elgrid_ann
        kpis.kundenanlage_trafo_kVA = data.site.get("kundenanlage_trafo_kVA", None)

        kpis.pv_flows_kundenanlage = pv_flows
        kpis.rev_pv_btm_kundenanlage = rev_pv_btm
        kpis.rev_pv_export_kundenanlage = rev_pv_export

        kpis.rev_local_el = result.get("rev_local_el", None)
        kpis.rev_feed_in_el = result.get("rev_feed_in_el", None)
        kpis.rev_local_el_by_year = result.get("rev_local_el_by_year", {})
        kpis.rev_feed_in_el_by_year = result.get("rev_feed_in_el_by_year", {})

        kpis.reststrom_MWh = self._calc_reststrom(data, result)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _annuity_factor(self, life_time: int) -> float:
        """VDI 2067 annuity factor incl. replacements and residual value."""
        n_obs = int(self.ecoData["observation_time"])
        q = 1.0 + float(self.ecoData["interest_rate"])
        CRF = (q ** n_obs * (q - 1)) / (q ** n_obs - 1)

        n = int(math.floor(n_obs / life_time))
        invest_replacements = sum(q ** (-i * life_time) for i in range(1, n + 1))
        res_value = ((n + 1) * life_time - n_obs) / life_time * (q ** (-n_obs))

        if life_time > n_obs:
            return (1.0 - res_value) * CRF
        return (1.0 + invest_replacements - res_value) * CRF

    def _calc_elgrid_annual_cost(self, data) -> float:
        """
        Annualised total cost of the local electricity grid [EUR/a].

        Cable length = sum of heat network pipe segments (same streets).
        One MV/LV transformer substation per district.

        Transformer cost scales with the DIN-derived kVA size relative
        to a base size (default 630 kVA). This is a simple linear
        scaling; real cost curves are slightly sub-linear.

        Returns
        -------
        float
            Total annualised electricity grid cost [EUR/a].
        """
        cfg = data.el_grid_data

        # Cable
        cable_length_m = sum(pipe["length"] for pipe in data.pipeline.values())
        ann_factor_cable = self._annuity_factor(cfg["life_cable"])
        ann_cable = (cfg["inv_cable_per_m"] * cable_length_m * ann_factor_cable
                     + cfg["om_cable_per_m"] * cable_length_m)

        # Transformer: scale investment with chosen kVA
        inv_trafo_base = cfg["inv_trafo"]  # EUR
        om_trafo_base = cfg["om_trafo"]  # EUR/a
        trafo_kVA_base = cfg.get("trafo_kVA_base", 630.0)  # kVA reference

        chosen_kVA = data.site.get("kundenanlage_trafo_kVA", trafo_kVA_base)
        scale = chosen_kVA / trafo_kVA_base

        ann_factor_trafo = self._annuity_factor(cfg["life_trafo"])
        ann_trafo = (inv_trafo_base * scale * ann_factor_trafo
                     + om_trafo_base * scale)

        return ann_cable + ann_trafo