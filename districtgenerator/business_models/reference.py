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

    def get_price_el_revenue_by_year(self) -> dict:
        """No local electricity revenue in the reference case."""
        return {y: 0.0 for y in self.interpolation_points}

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

    #todo Rawad: Es scheint, dass hier für p_max ein durchschnittlicher Wert über alle Gebäude verwendet wird.
    # Das ist problematisch, da dadurch einzelne Gebäude benachteiligt werden könnten.
    # Stattdessen sollte p_max gebäudespezifisch bestimmt werden, sodass für jedes Gebäude ein eigener Wert berücksichtigt wird.
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
          NPV = -Annual_Heat_Costs * pv_factor

        Annual heat costs include (consistent with LCOH calculation):
          - Fixed costs: Annualized CAPEX + O&M for heating devices (BOI, TES)
          - Variable costs: Fuel (gas) for heating

        NOTE: Household electricity is NOT included - this is a heat cost comparison.
        The NPV should be consistent with p_max (LCOH) calculation.

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
        # Only include heat-related devices for BOI buildings
        heat_devices = {"BOI", "TES", "STC"}             #todo: kein STC bitte, damit wir am ende die Szenarien gut vergleichen können
        annual_fixed_costs = 0.0

        for n, devs in kpis.decentral_individual_devices_annualized_cost.items():
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "BOI":
                continue
            for dev, info in devs.items():
                if dev in heat_devices:
                    annual_fixed_costs += float(info.get("subsidized_annual_cost", 0.0))

        # --- Variable costs (fuel only, NO household electricity) ---
        dt = float(data.time["timeResolution"])
        variable_costs_per_year = {}

        for year in support_years:
            eco = data.all_sim_ecoData[year]
            price_gas = eco["price_supply_gas"]

            fuel_cost = 0.0

            clusters = list(kpis.inputData["clusters"])
            cweights = kpis.inputData["clusterWeights"]

            for c in range(len(clusters)):
                cw = float(cweights[clusters[c]])
                cluster_results = kpis.inputData["resultsOptimization"][year][c]

                for n in range(len(data.district)):
                    heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
                    if heater != "BOI":
                        continue

                    res = cluster_results[n]
                    T = len(res.get("res_load", []))

                    # Gas consumption for BOI (only fuel cost, no electricity)
                    if "BOI" in res:
                        Q = np.array(res["BOI"].get("Q_th", [0] * T))
                        eta = data.decentral_device_data["BOI"]["eta_th"]
                        fuel = Q.sum() / eta * dt / 3600 / 1000  # kWh
                        fuel_cost += cw * fuel * price_gas

            variable_costs_per_year[year] = fuel_cost

        # TODO rawad: Die aktuellen variablen Kosten werden zunächst über die Jahre gemittelt und erst danach diskontiert.
        # Das ist jedoch keine exakte NPV-Berechnung.
        # Fachlich korrekter wäre es, die jährlichen Kosten direkt zu diskontieren und anschließend zu summieren
        # (Discounting vor Aggregation statt danach)
        avg_variable_costs = sum(
            variable_costs_per_year[y] * year_weights[y]
            for y in support_years
        ) / n_obs

        # --- Total annual heat costs ---
        annual_cost_ref = annual_fixed_costs + avg_variable_costs

        # --- Calculate NPV ---
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