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

Evaluation Methods:
  Option 1: LCOH with Electricity-Credit Method (avoided-cost)
            p_min = (C_tot - credit_avoided - credit_pv_feedin) / Q_heat
  Option 2: Exergy-based allocation (not yet implemented)
  Option 3: NPV comparison with reference case
            NPV_coop >= NPV_ref => economically favorable

p_max: read from ecoData['p_max'] (set manually after the reference run).
npv_ref: read from ecoData['npv_ref'] (set manually after the reference run).
"""

from .base import BusinessModelBase


class CooperativeBM(BusinessModelBase):

    # ------------------------------------------------------------------
    # modify_params -- called before the optimiser runs
    # ------------------------------------------------------------------

    def get_price_el_revenue_by_year(self) -> dict:
        return {y: 0.0 for y in self.interpolation_points}

    # ------------------------------------------------------------------
    # calculate_kpis -- called after the optimiser has finished
    # ------------------------------------------------------------------

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        Calculate KPIs based on the selected evaluation method.

        The method is controlled by ecoData['cooperative_evaluation_method']:
          - 'lcoh' or 'avoided_cost' (default): Option 1, LCOH with electricity credit
          - 'npv': Option 3, NPV comparison with reference case

        For Option 1 (LCOH):
          p_min = (C_tot - credit_avoided - credit_pv_feedin) / Q_heat  [EUR/kWh]
          p_max = read from ecoData['p_max'] (set after the reference run)

        For Option 3 (NPV):
          NPV_coop = NPV of cooperative system
          NPV_ref = read from ecoData['npv_ref'] (set after the reference run)
          economically_favorable = NPV_coop >= NPV_ref
        """
        eval_method = self.ecoData.get('cooperative_evaluation_method', 'lcoh')

        if eval_method in ['npv', 'NPV']:
            self._calculate_kpis_npv(kpis, data, result)
        else:
            # Default: LCOH / avoided-cost method (Option 1)
            self._calculate_kpis_lcoh(kpis, data, result)

    # ------------------------------------------------------------------
    # Option 1: LCOH with Electricity-Credit Method
    # ------------------------------------------------------------------

    def _calculate_kpis_lcoh(self, kpis, data, result: dict) -> None:
        """
        Original LCOH calculation using avoided-cost / electricity-credit method.
        """
        support_years = sorted(result['rev_local_el_by_year'].keys())
        weights = self._support_year_weights(support_years)

        # --- Avoided-cost prices [EUR/kWh] ---
        share_energy = self.ecoData['share_el_energy']
        share_grid = self.ecoData['share_el_grid']
        p_retail_avg = self._weighted_avg_price('price_supply_el', support_years, weights)      # TODO Rawad: Hier nochmal ein Durchschnitt

        p_avoided_eh = p_retail_avg * share_energy
        p_avoided_pv = p_retail_avg * (share_energy + share_grid)

        ann_eh_to_cons_MWh = self._calc_eh_to_buildings(data, result)

        pv_flows = self._calc_pv_flows(data, result)
        E_pv_btm_MWh = pv_flows["E_pv_btm_MWh"]
        E_pv_export_MWh = pv_flows["E_pv_export_MWh"]

        # --- Avoided-cost credit [EUR/a] ---
        credit_avoided = (
                ann_eh_to_cons_MWh * p_avoided_eh * 1000
                + E_pv_btm_MWh * p_avoided_pv * 1000                # TODO Rawad: Falls BTM bedeutet, dass PV-Strom ausschließlich im jeweiligen Gebäude  selbst verbraucht wird (kein Austausch mit anderen Gebäuden oder dem Energy Hub), ist diese Bewertung korrekt. Bei gemeinsamer Nutzung oder Weiterleitung über das Netz müssten Netzentgelte usw. berücksichtigt werden.
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
        kpis.evaluation_method = 'lcoh'

    # ------------------------------------------------------------------
    # Option 3: NPV Comparison with Reference Case
    # ------------------------------------------------------------------

    def _calculate_kpis_npv(self, kpis, data, result: dict) -> None:
        """
        NPV-based evaluation (Option 3 from MA Clemens).

        Compares NPV_coop with NPV_ref from ecoData.
        Cooperative is favorable if NPV_coop >= NPV_ref.
        """
        support_years = sorted(result['rev_local_el_by_year'].keys())
        weights = self._support_year_weights(support_years)

        n_obs = int(self.ecoData["observation_time"])
        i = self.ecoData["interest_rate"]
        q = 1 + i

        # --- Annual costs ---
        tac = result['tac']
        c_pv_ann = self._calc_decentral_pv_annual_cost(kpis)

        # --- Electricity credits ---
        share_energy = self.ecoData['share_el_energy']
        share_grid = self.ecoData['share_el_grid']
        p_retail_avg = self._weighted_avg_price('price_supply_el', support_years, weights)

        p_avoided_eh = p_retail_avg * share_energy
        p_avoided_pv = p_retail_avg * (share_energy + share_grid)

        ann_eh_to_cons_MWh = self._calc_eh_to_buildings(data, result)

        pv_flows = self._calc_pv_flows(data, result)
        E_pv_btm_MWh = pv_flows["E_pv_btm_MWh"]
        E_pv_export_MWh = pv_flows["E_pv_export_MWh"]

        credit_avoided = (
                ann_eh_to_cons_MWh * p_avoided_eh * 1000
                + E_pv_btm_MWh * p_avoided_pv * 1000
        )

        p_feedin_avg = self._weighted_avg_price('revenue_feed_in_el', support_years, weights)
        credit_pv_feedin = E_pv_export_MWh * p_feedin_avg * 1000

        # TODO Rawad: Die Berücksichtigung von credit_avoided ist in der LCOH-Methode
        # als Bewertungsansatz sinnvoll. Für die NPV-Berechnung ist das jedoch falsch,
        # da vermiedene Kosten keine realen Cashflows darstellen. Streng genommen sollte
        # ein NPV nur auf tatsächlichen Zahlungsströmen basieren. oder verstehe ich etwas falsch?
        # --- NPV calculation ---
        annual_net_cost = tac + c_pv_ann - credit_avoided - credit_pv_feedin

        if i != 0:
            pv_factor = (1 - (1 / q) ** n_obs) / i
        else:
            pv_factor = n_obs

        npv_coop = -annual_net_cost * pv_factor

        # --- Compare with reference ---
        npv_ref = self.ecoData.get('npv_ref', None)

        if npv_ref is not None:
            economically_favorable = npv_coop >= npv_ref
            npv_difference = npv_coop - npv_ref
        else:
            economically_favorable = None
            npv_difference = None

        # --- p_min for comparison ---
        Q_heat = self._Q_heat_delivered(data)
        p_min_lcoh = (tac + c_pv_ann - credit_avoided - credit_pv_feedin) / Q_heat if Q_heat > 0 else None

        # --- Store results ---
        kpis.npv_coop = npv_coop
        kpis.npv_ref = npv_ref
        kpis.npv_difference = npv_difference
        kpis.economically_favorable = economically_favorable

        kpis.p_min = p_min_lcoh
        kpis.p_max = self.ecoData.get('p_max', None)

        kpis.annual_net_cost = annual_net_cost
        kpis.tac = tac
        kpis.c_pv_ann = c_pv_ann
        kpis.credit_avoided = credit_avoided
        kpis.credit_pv_feedin = credit_pv_feedin

        kpis.pv_flows_cooperative = pv_flows
        kpis.eh_to_buildings_MWh = ann_eh_to_cons_MWh
        kpis.evaluation_method = 'npv'