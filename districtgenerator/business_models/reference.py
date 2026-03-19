# -*- coding: utf-8 -*-
"""
Reference Case: Decentral Heating (BM 0)

Each building has an individual gas boiler. Heat is met locally,
electricity is fully supplied by the public grid at retail prices.

No local electricity exchange -> price_el_revenue = 0.

Calculates:
  - p_max: LCOH of the decentralised gas boiler system (max acceptable heat price)
  - npv_ref: NPV of the reference case for Option 3 comparison

These values must be written manually into ecoData for use by all subsequent
BM runs on the same district:
  - ecoData["p_max"] for LCOH-based evaluation (Options 1 & 2)
  - ecoData["npv_ref"] for NPV-based evaluation (Option 3)
"""

from .base import BusinessModelBase
import numpy as np


class ReferenceBM(BusinessModelBase):

    def modify_params(self, param: dict) -> None:
        """No local electricity revenue."""
        param["price_el_revenue"] = {y: 0.0 for y in self.interpolation_points}

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        Calculate reference case KPIs:

        p_max = weighted-average LCOH (for LCOH-based comparison)
        npv_ref = NPV of reference case (for NPV-based comparison)
        p_min = None (not applicable for reference case)

        Individual LCOH per building are already in:
        - kpis.lcoh_year_building[year][n]
        - Excel sheet "LCOH"
        """
        kpis.p_max = self._calc_p_max_from_lcoh(kpis, data)
        kpis.p_min = None

        # Calculate NPV for Option 3 comparison
        kpis.npv_ref = self._calc_npv_reference(kpis, data)

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

    def _calc_npv_reference(self, kpis, data) -> float:
        """
        Calculate the Net Present Value (NPV) of the reference case.

        NPV calculation for decentralized heating system:
          NPV = -Σ (Annual_Costs_t / (1+r)^t) for t = 0 to observation_time

        Annual costs include:
          - Fixed costs: Annualized CAPEX + O&M for decentral devices
          - Variable costs: Fuel (gas) and electricity for heating

        Note: NPV is negative because it represents costs (outflows).
        For comparison: NPV_coop >= NPV_ref means cooperative is better
        (less negative = lower costs).

        Returns
        -------
        float : NPV of reference case [EUR]
        """
        n_obs = int(self.ecoData["observation_time"])
        i = self.ecoData["interest_rate"]
        q = 1 + i

        support_years = list(self.interpolation_points)
        year_weights = self._support_year_weights(support_years)

        # --- Fixed costs (annualized CAPEX + O&M) ---
        # Sum of all decentral device costs for BOI buildings
        annual_fixed_costs = 0.0

        for n, devs in kpis.decentral_individual_devices_annualized_cost.items():
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "BOI":
                continue
            for dev, info in devs.items():
                annual_fixed_costs += float(info.get("subsidized_annual_cost", 0.0))

        # --- Variable costs (fuel, electricity) ---
        # Calculate weighted average operation costs across support years
        # Operation costs include fuel costs for heating

        variable_costs_per_year = {}
        dt = float(data.time["timeResolution"])

        for year in support_years:
            eco = data.all_sim_ecoData[year]
            price_gas = eco["price_supply_gas"]
            price_el = eco["price_supply_el"]

            fuel_cost = 0.0
            el_cost = 0.0

            # Loop over clusters
            clusters = list(kpis.inputData["clusters"])
            cweights = kpis.inputData["clusterWeights"]

            for c in range(len(clusters)):
                cw = float(cweights[clusters[c]])
                cluster_results = kpis.inputData["resultsOptimization"][year][c]

                # Loop over BOI buildings
                for n in range(len(data.district)):
                    heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
                    if heater != "BOI":
                        continue

                    res = cluster_results[n]
                    T = len(res.get("res_load", []))

                    # Gas consumption for BOI
                    if "BOI" in res:
                        Q = np.array(res["BOI"].get("Q_th", [0] * T))
                        eta = data.decentral_device_data["BOI"]["eta_th"]
                        fuel = Q.sum() / eta * dt / 3600 / 1000  # kWh
                        fuel_cost += cw * fuel * price_gas

                    # Electricity for auxiliary equipment (pumps, controls)
                    # This is typically included in res_load
                    grid_load = np.array(res.get("res_load", [0] * T))
                    el_kWh = grid_load.sum() * dt / 3600 / 1000
                    el_cost += cw * el_kWh * price_el

            variable_costs_per_year[year] = fuel_cost + el_cost

        # Calculate weighted average variable costs
        avg_variable_costs = sum(
            variable_costs_per_year[y] * year_weights[y]
            for y in support_years
        ) / n_obs

        # --- Total annual costs ---
        annual_cost_ref = annual_fixed_costs + avg_variable_costs

        # --- Calculate NPV ---
        # Present value factor for annuity: (1 - (1+i)^-n) / i
        if i != 0:
            pv_factor = (1 - (1 / q) ** n_obs) / i
        else:
            pv_factor = n_obs

        # NPV = negative present value of costs
        npv_ref = -annual_cost_ref * pv_factor

        # Store breakdown for transparency
        kpis.npv_ref_breakdown = {
            'annual_fixed_costs': annual_fixed_costs,
            'annual_variable_costs': avg_variable_costs,
            'annual_total_costs': annual_cost_ref,
            'pv_factor': pv_factor,
            'npv': npv_ref
        }

        return npv_ref