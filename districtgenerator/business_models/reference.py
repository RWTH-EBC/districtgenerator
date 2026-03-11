# -*- coding: utf-8 -*-
"""
Reference Case: Decentral Heating (BM 0)

Each building has an individual gas boiler. Heat is met locally,
electricity is fully supplied by the public grid at retail prices.

No local electricity exchange -> price_el_revenue = 0.

Calculates p_max as the LCOH of the decentralised gas boiler system,
i.e. the maximum heat price consumers are willing to pay.
This value must be written manually into ecoData["p_max"] in the
.env config for use by all subsequent BM runs on the same district.
"""

from .base import BusinessModelBase


class ReferenceBM(BusinessModelBase):

    def modify_params(self, param: dict) -> None:
        """No local electricity revenue."""
        param["price_el_revenue"] = {y: 0.0 for y in self.interpolation_points}

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        p_max = weighted-average LCOH (Orientierung)
        p_min = None

        Individual LCOH per building are already in:
        - kpis.lcoh_year_building[year][n]
        - Excel sheet "LCOH"
        """
        kpis.p_max = self._calc_p_max_from_lcoh(kpis, data)
        kpis.p_min = None

    def _calc_p_max_from_lcoh(self, kpis, data) -> float:
        """Weighted-average LCOH for all BOI buildings."""
        support_years = list(self.interpolation_points)
        year_weights = self._support_year_weights(support_years)

        total_cost_weighted = 0.0
        total_heat_weighted = 0.0

        for year in support_years:
            year_weight = year_weights[year]
            for n in range(len(data.district)):
                heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
                if heater != "BOI":
                    continue

                lcoh_ct = kpis.lcoh_year_building.get(year, {}).get(n, 0.0)
                if lcoh_ct <= 0:
                    continue

                Q_n = self._Q_building_kwh(data, n)
                total_cost_weighted += (lcoh_ct / 100) * Q_n * year_weight
                total_heat_weighted += Q_n * year_weight

        return total_cost_weighted / total_heat_weighted if total_heat_weighted > 0 else None