# -*- coding: utf-8 -*-
"""
Collective Ownership Model / Energiegenossenschaft (BM 2.2)

The energy hub and district heating network are owned collectively by the
heat consumers (e.g. as a cooperative). The local electricity grid is NOT owned.

Locally generated electricity is valued at the avoided-cost price -- the
energy-only component of the retail price. Network charges continue to apply
since the public grid is still used for delivery. No internal monetary
transactions between the cooperative and its members are assumed.

Since avoided cost is a post-processing concept and not a cash flow within
the optimiser, price_el_revenue is set to zero for the optimisation.

p_min: LCOH of the cooperative system using the avoided-cost method.
p_max: read from ecoData['p_max'] (set manually after the reference run).

Todo: Add a different allocation method (Option 3) total system comparison
"""

from .base import BusinessModelBase


class CooperativeBM(BusinessModelBase):

    # ------------------------------------------------------------------
    # modify_params -- called before the optimiser runs
    # ------------------------------------------------------------------

    def modify_params(self, param: dict) -> None:
        """
        No monetary local electricity revenue in the optimiser.
        The avoided-cost credit is applied in post-processing only.
        """
        param['price_el_revenue'] = {y: 0.0 for y in self.interpolation_points}

    # ------------------------------------------------------------------
    # calculate_kpis -- called after the optimiser has finished
    # ------------------------------------------------------------------

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        p_min = (C_tot - credit_avoided - credit_pv_feedin) / Q_heat  [EUR/kWh]
        p_max = read from ecoData['p_max'] (set after the reference run)

        Cost allocation (avoided-cost / electricity-credit method):
          C_tot            = TAC_EH + annualised decentral PV costs
          credit_avoided   = avoided retail cost for locally used electricity
                             (EH->buildings at p_avoided_eh, PV btm at p_avoided_pv)
          credit_pv_feedin = feed-in revenue for surplus decentral PV export

        IMPORTANT: Cooperative uses price_el_revenue=0 in the optimizer, so
        TAC does NOT include any electricity revenues. The avoided-cost credits
        are calculated in post-processing and subtracted here.

        This is different from Contracting/Mieterstrom/Kundenanlage where
        price_el_revenue>0 and TAC already includes electricity revenues.
        """
        support_years = sorted(result['rev_local_el_by_year'].keys())
        weights = self._support_year_weights(support_years)

        # --- Avoided-cost prices [EUR/kWh] ---
        share_energy = self.ecoData['share_el_energy']
        share_grid = self.ecoData['share_el_grid']
        p_retail_avg = self._weighted_avg_price('price_supply_el', support_years, weights)

        p_avoided_eh = p_retail_avg * share_energy  # EH->buildings: energy only
        p_avoided_pv = p_retail_avg * (share_energy + share_grid)  # PV btm: energy + grid

        ann_eh_to_cons_MWh = self._calc_eh_to_buildings(data, result)

        pv_flows = self._calc_pv_flows(data, result)
        E_pv_btm_MWh = pv_flows["E_pv_btm_MWh"]
        E_pv_export_MWh = pv_flows["E_pv_export_MWh"]

        # --- Avoided-cost credit [EUR/a] ---
        # MWh * EUR/kWh * 1000 kWh/MWh = EUR/a
        credit_avoided = (
                ann_eh_to_cons_MWh * p_avoided_eh * 1000
                + E_pv_btm_MWh * p_avoided_pv * 1000
        )

        # --- Decentral PV feed-in credit [EUR/a] ---
        p_feedin_avg = self._weighted_avg_price('revenue_feed_in_el', support_years, weights)
        credit_pv_feedin = E_pv_export_MWh * p_feedin_avg * 1000

        # --- Total system cost [EUR/a] ---
        c_pv_ann = self._calc_decentral_pv_annual_cost(kpis)
        c_tot = result['tac'] + c_pv_ann

        Q_heat = self._Q_heat_delivered(data)

        kpis.p_min = (c_tot - credit_avoided - credit_pv_feedin) / Q_heat if Q_heat > 0 else None
        kpis.p_max = self.ecoData.get('p_max', None)

        kpis.pv_flows_cooperative = pv_flows
        kpis.eh_to_buildings_MWh = ann_eh_to_cons_MWh