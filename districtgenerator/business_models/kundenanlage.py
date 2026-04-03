# -*- coding: utf-8 -*-
"""
Kundenanlage Business Model (BM 2.4)

A single operator owns and operates the buildings' PV systems, the energy hub,
the district heating network AND the local electricity grid incl. transformer.

KEY DIFFERENCE vs Mieterstrom (BM 2.3):
=======================================
The operator owns the internal grid -> NO network usage charges apply for
any internal electricity delivery!

Consequences:
1. PV btm revenue = p_ms (same as Mieterstrom, no grid fees anyway)
2. EH → Mieter revenue = p_ms - VAT only (no grid fees, operator owns grid!)
3. Reststrom margin = p_ms - p_purchase (same as Mieterstrom)
4. Additional cost: Local grid infrastructure (cables + transformer)

CASH FLOW STRUCTURE (Operator perspective):
============================================

COSTS (outflows):
-----------------
1. EH capital + O&M                    → in TAC ✓
2. Heat network capital + O&M          → in TAC ✓
3. Decentral PV capital + O&M          → NOT in TAC, add in postprocessing
4. Local electricity grid + trafo      → NOT in TAC, add in postprocessing
5. Electricity purchase EH             → in TAC (price_supply_el_eh)
6. Reststrom purchase                  → NOT in TAC! Add in postprocessing
7. Gas, biomass, etc.                  → in TAC ✓

REVENUES (inflows):
-------------------
1. EH → Mieter (electricity)           → in TAC (rev_local_el at p_ms - VAT only!)
2. PV btm → Mieter                     → NOT in TAC, add in postprocessing
3. PV → Grid (export)                  → NOT in TAC, add in postprocessing
4. Reststrom → Mieter                  → NOT in TAC, add in postprocessing
5. Heat → Mieter                       → This IS p_min (what we're solving for)

ELECTRICITY PRICING:
====================
- p_ms = α × p_retail                  (Mieterstrom price to tenants)
- p_ms_net = p_ms - VAT only!          (No grid fees because operator owns grid)

RESTSTROM:
==========
- Operator buys at p_purchase_eh (includes all fees for that voltage level)
- Operator sells at p_ms (full Mieterstrom price)
- Margin = p_ms - p_purchase_eh > 0 (positive!)

p_min: minimum cost-covering heat selling price (NPV = 0).
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
           However, trafoMax_W is NOT set as a hard optimiser constraint                # TODO Rawad: Ich sehe hier zwei mögliche Lösungen: Entweder die Trafogröße wird nach der Optimierung basierend auf der tatsächlichen Spitzenlast bestimmt, oder – die bevorzugte Methode – die Trafogröße wird direkt in die Auslegungsoptimierung als variabel integriert. Für beide Ansätze wird jedoch ein kVA-spezifischer Preis für Transformatoren benötigt, anstatt eines fixen Preises. Daher müsste hierfür eine andere Quelle als der Technikkatalog gefunden werden.
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
        data.site["enable_buildingMax_W"] = True

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
    # modify_params -- called before the optimiser runs
    # ------------------------------------------------------------------

    def get_price_el_revenue_by_year(self) -> dict:
        """
        Full tenant tariff for local delivery in Kundenanlage.
        Only VAT deducted because operator owns the local grid.

        p_ms_net = α × p_retail - VAT

        (No grid fees or levies because no DSO grid is used internally)

        NOTE: This is for EH → Mieter delivery via internal grid.
        """
        alpha = self.ecoData["alpha"]
        share_vat = self.ecoData["share_el_vat"]

        return {
            year: (
                    alpha * self.all_sim_ecoData[year]["price_supply_el"]
                    - share_vat * self.all_sim_ecoData[year]["price_supply_el"]
            )
            for year in self.interpolation_points
        }

    def get_price_reststrom_purchase_by_year(self) -> dict:
        """
        Reststrom purchase price per year [EUR/kWh].

        Kundenanlage: Operator buys Reststrom at EH price (bulk purchase
        from higher voltage level). This price already includes all
        applicable grid fees and levies for that voltage level.
        """
        return {
            year: self.all_sim_ecoData[year]["price_supply_el_eh"]
            for year in self.interpolation_points
        }

    # ------------------------------------------------------------------
    # calculate_kpis -- called after the optimiser has finished
    # ------------------------------------------------------------------

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        Calculate p_min for Kundenanlage business model.

        Formula:
            p_min = (TAC + c_pv_ann + c_elgrid_ann + c_reststrom
                     - rev_pv_btm - rev_pv_export - rev_reststrom) / Q_heat

        Where:
            TAC = Total Annual Cost from dimensioning optimizer, includes:
                  - EH capital + O&M
                  - Heat network costs
                  - EH energy procurement (electricity, gas, etc.)
                  - MINUS: rev_local_el (EH → Mieter at p_ms - VAT)
                  NOTE: TAC does NOT include Reststrom costs!

            c_pv_ann = Annualized cost of decentral PV systems

            c_elgrid_ann = Annualized cost of local electricity grid
                         = cables + transformer (sized per DIN)

            c_reststrom = Cost of purchasing Reststrom from public grid
                        = E_reststrom × p_purchase_eh
                        The purchase price already includes all grid fees!

            rev_pv_btm = Revenue from PV self-consumption
                       = E_pv_btm × p_ms (full Mieterstrom price)

            rev_pv_export = Revenue from PV grid export
                          = E_pv_export × p_feed_in

            rev_reststrom = Revenue from selling Reststrom to tenants
                          = E_reststrom × p_ms (FULL Mieterstrom price!)

                          IMPORTANT: Same as Mieterstrom - operator gets full p_ms!
                          The grid fees are already in the purchase price.

        Net Reststrom margin = rev_reststrom - c_reststrom
                             = E_reststrom × (p_ms - p_purchase_eh)
                             > 0 (positive margin!)
        """
        support_years = sorted(result["rev_local_el_by_year"].keys())
        weights = self._support_year_weights(support_years)
        n_obs = int(self.ecoData["observation_time"])

        alpha = self.ecoData["alpha"]

        # --- PV electricity flows [MWh/a] ---
        pv_flows = self._calc_pv_flows(data, result)
        E_pv_btm_MWh = pv_flows["E_pv_btm_MWh"]
        E_pv_export_MWh = pv_flows["E_pv_export_MWh"]

        # --- Average prices [EUR/kWh] ---
        p_retail_avg = self._weighted_avg_price("price_supply_el", support_years, weights)
        p_ms = alpha * p_retail_avg  # Mieterstrom price (what tenant pays)
        p_feedin_avg = self._weighted_avg_price("revenue_feed_in_el", support_years, weights)

        # --- Revenue from PV self-consumption [EUR/a] ---
        # Tenant pays p_ms for every kWh consumed from building PV
        # Same as Mieterstrom - no grid fees behind the meter anyway
        rev_pv_btm = E_pv_btm_MWh * p_ms * 1000

        # --- Revenue from PV grid export [EUR/a] ---
        rev_pv_export = E_pv_export_MWh * p_feedin_avg * 1000

        # --- Reststrom: Purchase cost AND Sale revenue [EUR/a] ---
        ann_reststrom_MWh = self._calc_reststrom(data, result)

        # Purchase price: Operator buys at EH price (includes all fees for that level)
        price_purchase_by_year = self.get_price_reststrom_purchase_by_year()
        p_purchase_avg = sum(
            price_purchase_by_year[y] * weights[y] for y in support_years
        ) / n_obs

        # Reststrom costs (purchase) - NOT in TAC, must add here!
        c_reststrom = ann_reststrom_MWh * p_purchase_avg * 1000

        # Reststrom revenue (sale to tenants at FULL p_ms!)
        # Same logic as Mieterstrom: operator buys at p_purchase, sells at p_ms
        rev_reststrom = ann_reststrom_MWh * p_ms * 1000

        # --- Additional annual costs [EUR/a] ---
        c_pv_ann = self._calc_decentral_pv_annual_cost(kpis)
        c_elgrid_ann = self._calc_elgrid_annual_cost(data)

        # --- Total annual cost for heat price calculation ---
        c_tot = (
                result["tac"]  # EH + network + EH energy costs - EH electricity revenue
                + c_pv_ann  # Add: decentral PV costs
                + c_elgrid_ann  # Add: local electricity grid costs
                + c_reststrom  # Add: Reststrom purchase costs (NOT in TAC!)
                - rev_pv_btm  # Subtract: PV self-consumption revenue
                - rev_pv_export  # Subtract: PV export revenue
                - rev_reststrom  # Subtract: Reststrom sale revenue (at full p_ms!)
        )

        # --- Heat delivered to consumers [kWh/a] ---
        Q_heat = self._Q_heat_delivered(data)

        # --- Calculate p_min ---
        kpis.p_min = c_tot / Q_heat if Q_heat > 0 else None
        kpis.p_max = self.ecoData.get("p_max", None)

        # --- Store diagnostic values for transparency ---
        kpis.kundenanlage_breakdown = {
            'tac': result["tac"],
            'c_pv_ann': c_pv_ann,
            'c_elgrid_ann': c_elgrid_ann,
            'c_reststrom': c_reststrom,
            'rev_pv_btm': rev_pv_btm,
            'rev_pv_export': rev_pv_export,
            'rev_reststrom': rev_reststrom,
            'reststrom_margin': rev_reststrom - c_reststrom,
            'c_tot': c_tot,
            'Q_heat_kWh': Q_heat,
            'E_pv_btm_MWh': E_pv_btm_MWh,
            'E_pv_export_MWh': E_pv_export_MWh,
            'E_reststrom_MWh': ann_reststrom_MWh,
            'p_ms_EUR_kWh': p_ms,
            'p_purchase_EUR_kWh': p_purchase_avg,
            'p_feedin_EUR_kWh': p_feedin_avg,
            'alpha': alpha,
            'trafo_kVA': data.site.get("kundenanlage_trafo_kVA", None),
        }

        # Legacy attributes for backward compatibility
        kpis.c_pv_ann = c_pv_ann
        kpis.c_elgrid_ann = c_elgrid_ann
        kpis.c_reststrom_kundenanlage = c_reststrom
        kpis.kundenanlage_trafo_kVA = data.site.get("kundenanlage_trafo_kVA", None)
        kpis.pv_flows_kundenanlage = pv_flows
        kpis.reststrom_MWh = ann_reststrom_MWh
        kpis.rev_pv_btm_kundenanlage = rev_pv_btm
        kpis.rev_pv_export_kundenanlage = rev_pv_export
        kpis.rev_reststrom_kundenanlage = rev_reststrom
        kpis.rev_local_el = result.get("rev_local_el", None)
        kpis.rev_feed_in_el = result.get("rev_feed_in_el", None)
        kpis.rev_local_el_by_year = result.get("rev_local_el_by_year", {})
        kpis.rev_feed_in_el_by_year = result.get("rev_feed_in_el_by_year", {})

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

        Cable length = sum of heat network pipe segments (same streets).  #todo Rawad: hier die Straßenlänge nutzen
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
        trafo_kVA_base = cfg.get("trafo_kVA_base", 630.0)  # kVA reference          #todo Rawad: woher kommt die 630 kVA. Ich habe nichts dazu im TEchnikkatalog gefunden. Wir sollen eine andere Quelle für €/kVA finden

        chosen_kVA = data.site.get("kundenanlage_trafo_kVA", trafo_kVA_base)
        scale = chosen_kVA / trafo_kVA_base

        ann_factor_trafo = self._annuity_factor(cfg["life_trafo"])
        ann_trafo = (inv_trafo_base * scale * ann_factor_trafo
                     + om_trafo_base * scale)

        return ann_cable + ann_trafo