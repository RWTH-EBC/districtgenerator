# -*- coding: utf-8 -*-
"""
Contracting Business Model / Quartiersbetreiber (BM 2.1)

A single operator invests in and operates the energy hub, storage, and
district heating network. The local electricity grid is NOT owned.

Electricity generated in the district is sold locally to consumers at a
fraction alpha of the consumer retail price. Since the public grid is used
for delivery, network charges, levies, and VAT must be deducted -- only
the net revenue remains for the operator:

    price_el_local_net = alpha * p_ret_cons - p_grid - p_levies - p_vat

p_min: minimum cost-covering heat selling price (NPV = 0).
p_max: read from ecoData["p_max"] (set manually after the reference run).
"""

from .base import BusinessModelBase


class ContractingBM(BusinessModelBase):

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
        p_min = TAC / Q_heat  [EUR/kWh]
        p_max = read from ecoData["p_max"] (set after the reference run)

        TAC from the optimizer already includes all revenues:
          TAC = (capital + om + heat_grid + energy_costs - revenues)
          where revenues = rev_local_el + rev_feed_in_el + rev_feed_in_gas

        The optimizer calculated energy_costs as:
          energy_costs = supply_costs - rev_feed_in_el - rev_local_el

        Therefore TAC is already NET (revenues deducted). No additional
        revenue subtraction is needed in post-processing.

        Since Contracting BM does NOT own decentral PV systems, no additional
        costs need to be added to TAC.
        """

        Q_heat = self._Q_heat_delivered(data)

        kpis.p_min = result["tac"] / Q_heat if Q_heat > 0 else None
        kpis.p_max = self.ecoData.get("p_max", None)
