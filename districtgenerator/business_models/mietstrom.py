# -*- coding: utf-8 -*-
"""
Mieterstrom-Contracting Business Model (BM 2.3)

A single operator (e.g. landlord or housing company) owns and operates
the buildings PV systems, the energy hub, and the district heating
network. The local electricity grid is NOT owned.

Electricity flows and their revenue treatment:

1. EH -> Mieter (via public grid):
   Sold at p_ms = alpha * p_ret_cons, but network charges apply because
   the public grid is used for delivery. The NET revenue seen by the
   optimizer is: p_ms_net = p_ms - grid_fees - levies - VAT.

2. PV -> Mieter btm (behind the meter, same building):
   Sold at p_ms, NO network charges (no public grid used).
   This is NOT in the optimizer (PV btm is a demand reduction).
   The additional revenue (grid fee savings) is added in post-processing.

3. PV -> Grid (export):
   Remunerated at feed-in tariff. Handled via building-level feed-in.

4. Reststrom (Grid -> Mieter, via operator):
   Operator buys at p_ret_op, sells at p_ms. The spread (p_ms - p_ret_op)
   is captured in the optimizer through price_el_revenue for local delivery
   vs. price_supply_el for grid import.

TODO: Decentral PV size is currently fixed from buildingFeatures.

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
        Public-grid charges are deducted.
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

    # ------------------------------------------------------------------
    # calculate_kpis -- called after the optimiser has finished
    # ------------------------------------------------------------------

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        p_min = (TAC + c_pv - rev_pv_btm_bonus - rev_pv_export) / Q_heat

        TAC from the optimizer includes EH electricity revenues at the NET
        price (p_ms minus grid fees). This correctly reflects that EH->Mieter
        delivery uses the public grid.

        However, TAC does NOT include:
          1. Decentral PV investment + O&M costs (not in central optimization)
          2. PV btm revenue bonus: PV btm is sold at full p_ms (no grid fees),
             but the optimizer valued the demand reduction at the NET price.
             The difference (grid fee savings on PV btm) must be credited.
          3. PV export revenue: feed-in tariff for PV surplus exported to grid.

        The PV btm "bonus" is the grid-fee portion that PV btm avoids:
          rev_pv_btm_bonus = E_pv_btm * (share_grid + share_levies + share_vat) * p_ret

        This represents the additional value of PV btm over EH-delivered
        electricity: the operator saves the network charges on every kWh
        that is consumed directly behind the meter.
        """
        support_years = sorted(result['rev_local_el_by_year'].keys())
        weights = self._support_year_weights(support_years)

        # --- PV flows ---
        pv_flows = self._calc_pv_flows(data, result)
        E_pv_btm_MWh = pv_flows["E_pv_btm_MWh"]
        E_pv_export_MWh = pv_flows["E_pv_export_MWh"]

        # --- PV btm bonus: grid fee savings [EUR/a] ---
        # PV btm avoids grid fees that EH->Mieter delivery would incur.
        share_grid = self.ecoData["share_el_grid"]
        share_levies = self.ecoData["share_el_levies"]
        share_vat = self.ecoData["share_el_vat"]
        share_fees_total = share_grid + share_levies + share_vat

        p_retail_avg = self._weighted_avg_price('price_supply_el', support_years, weights)
        rev_pv_btm_bonus = E_pv_btm_MWh * share_fees_total * p_retail_avg * 1000  # MWh * EUR/kWh * 1000 kWh/MWh

        # --- PV export revenue [EUR/a] ---
        p_feedin_avg = self._weighted_avg_price('revenue_feed_in_el', support_years, weights)
        rev_pv_export = E_pv_export_MWh * p_feedin_avg * 1000  # MWh * EUR/kWh * 1000

        # --- Total cost ---
        c_pv_ann = self._calc_decentral_pv_annual_cost(kpis)
        c_tot = result["tac"] + c_pv_ann - rev_pv_btm_bonus - rev_pv_export
        Q_heat = self._Q_heat_delivered(data)

        kpis.p_min = c_tot / Q_heat if Q_heat > 0 else None
        kpis.p_max = self.ecoData.get("p_max", None)

        # Store diagnostic values
        ann_reststrom_MWh = self._calc_reststrom(data, result)

        kpis.pv_flows_mietstrom = pv_flows
        kpis.reststrom_MWh = ann_reststrom_MWh
        kpis.rev_pv_btm_bonus = rev_pv_btm_bonus
        kpis.rev_pv_export_mietstrom = rev_pv_export