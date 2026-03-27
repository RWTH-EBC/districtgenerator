# -*- coding: utf-8 -*-
"""
Mieterstrom-Contracting Business Model (BM 2.3) - CORRECTED VERSION

A single operator (e.g. landlord or housing company) owns and operates
the buildings' PV systems, the energy hub, and the district heating
network. The local electricity grid is NOT owned.

CASH FLOW STRUCTURE (Operator perspective):
============================================

COSTS (outflows):
-----------------
1. EH capital + O&M                    → in TAC ✓
2. Heat network capital + O&M          → in TAC ✓
3. Decentral PV capital + O&M          → NOT in TAC, add in postprocessing
4. Electricity purchase EH             → in TAC (price_supply_el_eh)
5. Reststrom purchase                  → NOT in TAC! Add in postprocessing
6. Gas, biomass, etc.                  → in TAC ✓

REVENUES (inflows):
-------------------
1. EH → Mieter (electricity)           → in TAC (rev_local_el at p_ms_net)
2. PV btm → Mieter                     → NOT in TAC, add in postprocessing
3. PV → Grid (export)                  → NOT in TAC, add in postprocessing
4. Reststrom → Mieter                  → NOT in TAC, add in postprocessing
5. Heat → Mieter                       → This IS p_min (what we're solving for)

KEY INSIGHT:
============
The TAC from the dimensioning optimizer does NOT include Reststrom costs!
The dimensioning only optimizes the Energy Hub perspective.
Reststrom (electricity bought from public grid for buildings) must be
added explicitly in postprocessing.

ELECTRICITY PRICING:
====================
- p_ms = α × p_retail                  (Mieterstrom price to tenants)
- p_ms_net = p_ms - grid_fees - levies - VAT  (Net revenue for EH delivery via DSO grid)

IMPORTANT DISTINCTION:
======================
- EH → Mieter: Uses public DSO grid → Operator gets p_ms_net (grid fees deducted)
- Reststrom → Mieter: Operator buys at p_purchase (incl. all fees) and sells at p_ms
  The purchase price ALREADY INCLUDES grid fees, so operator gets FULL p_ms!

RESTSTROM MARGIN:
=================
margin = p_ms - p_purchase_eh
       = α × p_retail - p_eh
       > 0 (positive margin for operator!)

p_min: minimum cost-covering heat selling price (NPV = 0).
p_max: read from ecoData["p_max"] (set manually after the reference run).
"""

from .base import BusinessModelBase


class MieterstromBM(BusinessModelBase):

    # ------------------------------------------------------------------
    # modify_params -- called before the optimiser runs
    # ------------------------------------------------------------------

    def get_price_el_revenue_by_year(self) -> dict:
        """
        Net Mieterstrom revenue for EH -> consumers.
        Public-grid charges are deducted because delivery uses DSO grid.

        p_ms_net = α × p_retail - grid_fees - levies - VAT

        NOTE: This is only for EH delivery, NOT for Reststrom!
        """
        alpha = self.ecoData["alpha"]
        share_grid = self.ecoData["share_el_grid"]
        share_levies = self.ecoData["share_el_levies"]
        share_vat = self.ecoData["share_el_vat"]

        return {
            year: (
                    alpha * self.all_sim_ecoData[year]["price_supply_el"]
                    - share_grid * self.all_sim_ecoData[year]["price_supply_el"]
                    - share_levies * self.all_sim_ecoData[year]["price_supply_el"]
                    - share_vat * self.all_sim_ecoData[year]["price_supply_el"]
            )
            for year in self.interpolation_points
        }

    def get_price_reststrom_purchase_by_year(self) -> dict:
        """
        Reststrom purchase price per year [EUR/kWh].

        Mieterstrom: Operator buys Reststrom at EH price (bulk purchase
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
        Calculate p_min for Mieterstrom business model.

        Formula:
            p_min = (TAC + c_pv_ann + c_reststrom - rev_pv_btm - rev_pv_export - rev_reststrom) / Q_heat

        Where:
            TAC = Total Annual Cost from dimensioning optimizer, includes:
                  - EH capital + O&M
                  - Heat network costs
                  - EH energy procurement (electricity, gas, etc.)
                  - MINUS: rev_local_el (EH → Mieter at p_ms_net)
                  NOTE: TAC does NOT include Reststrom costs!

            c_pv_ann = Annualized cost of decentral PV systems

            c_reststrom = Cost of purchasing Reststrom from public grid
                        = E_reststrom × p_purchase_eh
                        The purchase price already includes all grid fees!

            rev_pv_btm = Revenue from PV self-consumption
                       = E_pv_btm × p_ms (FULL price, no grid fees - behind meter)

            rev_pv_export = Revenue from PV grid export
                          = E_pv_export × p_feed_in

            rev_reststrom = Revenue from selling Reststrom to tenants
                          = E_reststrom × p_ms (FULL Mieterstrom price!)

                          IMPORTANT: Operator gets FULL p_ms, not p_ms_net!
                          The grid fees are already included in the purchase price,
                          so there's no double-charging. The operator simply
                          buys at p_purchase and sells at p_ms.

        Net Reststrom margin = rev_reststrom - c_reststrom
                             = E_reststrom × (p_ms - p_purchase_eh)
                             > 0 (positive margin!)
        """
        support_years = sorted(result['rev_local_el_by_year'].keys())
        weights = self._support_year_weights(support_years)
        n_obs = int(self.ecoData["observation_time"])

        alpha = self.ecoData["alpha"]

        # --- PV electricity flows [MWh/a] ---
        pv_flows = self._calc_pv_flows(data, result)
        E_pv_btm_MWh = pv_flows["E_pv_btm_MWh"]
        E_pv_export_MWh = pv_flows["E_pv_export_MWh"]

        # --- Average prices [EUR/kWh] ---
        p_retail_avg = self._weighted_avg_price('price_supply_el', support_years, weights)
        p_ms = alpha * p_retail_avg  # Mieterstrom price (what tenant pays)
        p_feedin_avg = self._weighted_avg_price('revenue_feed_in_el', support_years, weights)

        # --- Revenue from PV self-consumption [EUR/a] ---
        # Tenant pays p_ms for every kWh consumed from building PV
        # No grid fees because electricity stays behind the meter!
        rev_pv_btm = E_pv_btm_MWh * p_ms * 1000  # MWh × EUR/kWh × 1000 kWh/MWh

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
        # The operator buys at p_purchase (which includes grid fees for that level)
        # and sells at p_ms. No additional grid fees are deducted!
        rev_reststrom = ann_reststrom_MWh * p_ms * 1000

        # --- Decentral PV annual cost [EUR/a] ---
        c_pv_ann = self._calc_decentral_pv_annual_cost(kpis)

        # --- Total annual cost for heat price calculation ---
        c_tot = (
                result["tac"]  # EH + network + EH energy costs - EH electricity revenue
                + c_pv_ann  # Add: decentral PV costs (not in TAC)
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
        kpis.mieterstrom_breakdown = {
            'tac': result["tac"],
            'c_pv_ann': c_pv_ann,
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
        }

        # Legacy attributes for backward compatibility
        kpis.c_reststrom_mietstrom = c_reststrom
        kpis.rev_reststrom_mietstrom = rev_reststrom
        kpis.pv_flows_mietstrom = pv_flows
        kpis.reststrom_MWh = ann_reststrom_MWh
        kpis.rev_pv_btm_mietstrom = rev_pv_btm
        kpis.rev_pv_export_mietstrom = rev_pv_export