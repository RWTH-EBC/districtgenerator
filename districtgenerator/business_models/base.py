# -*- coding: utf-8 -*-
"""
Abstract base class for all business models.

Each subclass implements get_price_el_revenue_by_year (sets price_el_revenue
before the optimizer) and calculate_kpis (computes p_min / p_max from results).
Optionally, configure_grid_constraints can be overridden for BMs that
own the local electricity grid (Kundenanlage).

Subclasses are looked up by ecoData["business_model"] via BM_REGISTRY.

=====================================================
In load_params_central_devices.py:
    dem["power"] = elec + EV - PV + pump

The PV split used in _calc_pv_flows() is:
    demand = elec + EV
    btm = min(PV, demand)
    export = PV - btm

This is consistent because:
    dem["power"] = demand - PV + pump
                 = (btm + residual) - (btm + export) + pump
                 = residual - export + pump

where residual = demand - btm = electricity demand after on-site PV self-consumption
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import numpy as np
import copy

from districtgenerator.functions.din_house_connection_limits import (
    apply_din_house_connection_limits,
)
from districtgenerator.functions.trafo_sizing import (
    trafo_limit_from_house_connection_limits,
    DIN_TRAFO_STEPS_KVA,
)


class BusinessModelBase(ABC):
    """
    Abstract base class for business models.
    """

    def __init__(self, ecoData: dict, all_sim_ecoData: dict, interpolation_points: list):
        self.ecoData = ecoData
        self.all_sim_ecoData = all_sim_ecoData
        self.interpolation_points = interpolation_points

    # ------------------------------------------------------------------
    # Grid constraint configuration (DIN house-connection + trafo sizing)
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
        Apply DIN house-connection limits and optionally size the transformer.

        Called *before* the optimiser runs (after modify_params).

        The method implements an auto-sizing cascade:

        1. **House-connection limits** (DIN 18015-1):
           Always applied if din_csv_path is given. Sets per-building power
           caps in data.site["buildingMax_W_per_building"].

        2. **Transformer limit** – cascade logic:
           a) If data.site["auto_size_trafo"] is True (or not set, default):
              → Kerber/DIN sizing is executed → overwrites trafoMax_W
              → enable_trafoMax_W = True
           b) If data.site["auto_size_trafo"] is False:
              → Manual values from config are kept (trafoMax_W, enable_trafoMax_W)
              → No Kerber sizing is performed

        This allows users to either rely on the DIN-based estimate (no DSO
        data needed) or override with a known value from the DSO.

        Default behaviour (Contracting / Cooperative / Mieterstrom):
          Both house-connection limits and trafoMax_W are set as *external
          constraints* of the DSO-owned grid (hard caps in the optimiser).

        Parameters
        ----------
        data : Datahandler
            Full data object. Must have data.district and data.site populated.
        din_csv_path : str or Path, optional
            Path to the DIN 18015-1 lookup CSV. If None, all limits disabled.
        cosphi, safety_factor, g : float
            Parameters for trafo sizing (see trafo_sizing.py).
        trafo_steps : list[float]
            Available DIN 42508 transformer sizes [kVA].
        out_dir : Path, optional
            Directory for writing the sizing summary JSON.

        Returns
        -------
        dict
            Trafo sizing summary (empty dict if no sizing was performed).
        """
        summary = {}

        if din_csv_path is None:
            data.site["enable_buildingMax_W"] = False
            return summary

        # ── Step 1: Per-building house-connection limits ──────────────
        apply_din_house_connection_limits(
            data=data,
            enabled=True,
            din_csv_path=din_csv_path,
            write_back_to_buildings=True,
        )
        data.site["enable_buildingMax_W"] = True

        # ── Step 2: Transformer sizing (cascade) ─────────────────────
        auto_size = data.site.get("auto_size_trafo", True)

        if auto_size:
            # Kerber/DIN sizing → overwrites config values
            summary = trafo_limit_from_house_connection_limits(
                data=data,
                cosphi=cosphi,
                safety_factor=safety_factor,
                g=g,
                steps=trafo_steps,
                out_dir=out_dir,
                write_json=(out_dir is not None),
            )
            # For DSO-owned grids: enforce as hard external constraint
            data.site["enable_trafoMax_W"] = True

            # Warn if sizing exceeds largest available NS trafo
            if summary["chosen_transformer_kVA"] >= max(trafo_steps):
                print(
                    f"INFO: DIN-based transformer size "
                    f"({summary['required_kVA']:.0f} kVA required) reaches "
                    f"the largest LV step ({max(trafo_steps)} kVA)."
                )
        else:
            # Manual mode: keep trafoMax_W and enable_trafoMax_W from config
            pass

        return summary

    # ------------------------------------------------------------------
    # Helpers shared by all subclasses
    # ------------------------------------------------------------------

    def _support_year_weights(self, support_years: list) -> dict:
        """
        Calculate weights for multi-year NPV calculation.

        Each support year represents an interval until the next support year
        (or end of observation period for the last year).

        """
        n_obs = int(self.ecoData["observation_time"])
        sorted_years = sorted(support_years)
        return {
            y: (sorted_years[i + 1] - y if i < len(sorted_years) - 1 else n_obs - y)
            for i, y in enumerate(sorted_years)
        }

    def _weighted_avg_price(self, price_key: str, support_years: list, weights: dict) -> float:
        """Time-weighted average of a price across all support years [EUR/kWh]."""
        n_obs = int(self.ecoData["observation_time"])
        return sum(
            self.all_sim_ecoData[y][price_key] * weights[y]
            for y in support_years
        ) / n_obs

    def _Q_building_kwh(self, data, n: int) -> float:
        """Annual useful heat demand of a single building [kWh/a]."""
        dt = float(data.time["timeResolution"])
        heat = np.array(data.district[n]["user"].heat, dtype=float)
        dhw = np.array(data.district[n]["user"].dhw, dtype=float)
        return float(np.sum(heat + dhw) * dt / 3600.0 / 1000.0)  # W * s / 3600 / 1000 = kWh

    def _Q_heat_delivered(self, data) -> float:
        """
        Annual useful heat demand of all HEAT_GRID buildings [kWh/a].

        Corresponds to H_del: heat at the consumer side,
        net of network losses. Same calculation as Q_total_eh in
        calculateLCOH_EH (KPIs.py).
        """
        dt = float(data.time["timeResolution"])
        Q = 0.0
        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue
            heat = np.array(data.district[n]["user"].heat, dtype=float)
            dhw = np.array(data.district[n]["user"].dhw, dtype=float)
            Q += float(np.sum(heat + dhw) * dt / 3600.0 / 1000.0)  # W * s / 3600 / 1000 = kWh
        return Q

    def _calc_decentral_pv_annual_cost(self, kpis) -> float:
        """
        Total annualised cost of all decentral PV systems [EUR/a].

        Taken from the already-computed decentral device costs on the kpis
        object. Used by cooperative and mieterstrom BMs which include
        decentral PV costs in their total system cost calculation.
        """
        total = 0.0
        for n, devs in kpis.decentral_individual_devices_annualized_cost.items():
            if "PV" in devs:
                total += devs["PV"]["subsidized_annual_cost"]
        return total

    # ------------------------------------------------------------------
    # Electricity flow calculations
    # ------------------------------------------------------------------

    def _calc_pv_flows(self, data, result: dict) -> dict:
        """
        Decentral PV electricity flows based on the actual optimiser results [MWh/a].

        For each support year, cluster, building, and time step:
            pv_btm(t)    = min(PV_actual(t), Elec_dem_actual(t))
            pv_export(t) = PV_actual(t) - pv_btm(t)

        Uses:
            data.resultsOptimization[year][cluster][n]["PV"]["P_el"]
            data.resultsOptimization[year][cluster][n]["Elec_dem"]["P_el"]

        Clusters are weighted with data.clusterWeights,
        and years are weighted with the support-year weights over the
        observation period.

        Returns:
            dict: E_pv_total_MWh, E_pv_btm_MWh, E_pv_export_MWh
        """
        support_years = sorted(result.get("rev_local_el_by_year", {}).keys())
        if not support_years:
            return {
                "E_pv_total_MWh": 0.0,
                "E_pv_btm_MWh": 0.0,
                "E_pv_export_MWh": 0.0,
            }

        year_weights = self._support_year_weights(support_years)
        n_obs = int(self.ecoData["observation_time"])

        dt = float(data.time["timeResolution"])  # [s]
        factor_W_to_MWh = dt / 3600.0 / 1e6  # W -> MWh per time step

        clusters = list(getattr(data, "clusters", range(data.time["clusterNumber"])))
        cluster_weights = data.clusterWeights

        E_pv_total_MWh_by_year = {}
        E_pv_btm_MWh_by_year = {}

        for year in support_years:
            E_pv_total_MWh_year = 0.0
            E_pv_btm_MWh_year = 0.0

            for c in range(len(clusters)):
                cw = float(cluster_weights[clusters[c]])
                cluster_result = data.resultsOptimization[year][c]

                for n in range(len(data.district)):
                    building_result = cluster_result[n]

                    pv_profile = np.array(building_result["PV"]["P_el"], dtype=float)
                    demand_profile = np.array(building_result["Elec_dem"]["P_el"], dtype=float)

                    T = min(len(pv_profile), len(demand_profile))
                    pv_profile = np.clip(pv_profile[:T], 0.0, None)
                    demand_profile = np.clip(demand_profile[:T], 0.0, None)

                    pv_btm = np.minimum(pv_profile, demand_profile)

                    E_pv_total_MWh_year += cw * float(np.sum(pv_profile)) * factor_W_to_MWh
                    E_pv_btm_MWh_year += cw * float(np.sum(pv_btm)) * factor_W_to_MWh

            E_pv_total_MWh_by_year[year] = E_pv_total_MWh_year
            E_pv_btm_MWh_by_year[year] = E_pv_btm_MWh_year

        E_pv_total_MWh = sum(
            E_pv_total_MWh_by_year[y] * year_weights[y] for y in support_years
        ) / n_obs

        E_pv_btm_MWh = sum(
            E_pv_btm_MWh_by_year[y] * year_weights[y] for y in support_years
        ) / n_obs

        E_pv_export_MWh = E_pv_total_MWh - E_pv_btm_MWh

        return {
            "E_pv_total_MWh": E_pv_total_MWh,
            "E_pv_btm_MWh": E_pv_btm_MWh,
            "E_pv_export_MWh": E_pv_export_MWh,
        }

    def _annualized_yearly_value(self, result: dict, key: str) -> float:
        """Year-weighted annual average of a per-support-year optimizer result."""
        yearly = result.get(key, {})
        support_years = sorted(yearly.keys())
        if not support_years:
            return 0.0

        weights = self._support_year_weights(support_years)
        n_obs = int(self.ecoData["observation_time"])
        return sum(yearly[y] * weights[y] for y in support_years) / n_obs

    def _calc_reststrom(self, data, result: dict) -> float:
        """
        Annual residual electricity demand of the buildings [MWh/a].

        This is the share of building demand that is not covered by local
        supply, e.g. PV or electricity provided by the energy hub, and
        therefore has to be imported from the public grid.

        In the business-model post-processing, this value is used as a proxy
        for the externally procured residual electricity volume.
        """
        return self._annualized_yearly_value(result, "from_el_grid_buildings_by_year")

    def _calc_eh_to_buildings(self, data, result: dict) -> float:
        """
        Annual electricity supplied from the energy hub to the buildings [MWh/a].

        Corresponds to p_loc_to_cons in the optimiser.
        """
        return self._annualized_yearly_value(result, "to_local_el_total_by_year")

    # ------------------------------------------------------------------
    # Interface every subclass must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def get_price_el_revenue_by_year(self) -> dict:
        """
        Return year-specific local electricity revenue:
        {support_year: price_el_revenue_in_EUR_per_kWh}
        """
        pass

    def apply_operational_ecoData(self, sim_ecoData: dict, year) -> dict:
        """
        Return a copy of sim_ecoData enriched with BM-specific operational values
        needed by opti_central.
        """
        eco = copy.deepcopy(sim_ecoData)
        eco["price_el_revenue"] = self.get_price_el_revenue_by_year().get(year, 0.0)
        return eco

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        Compute p_min and p_max after the optimiser has finished.

        Writes kpis.p_min (cost-covering heat price [EUR/kWh]) and
        kpis.p_max (maximum acceptable price from reference run).
        The result dict contains the optimizer outputs including "tac",
        per-year revenues and energy flows.

        IMPORTANT for subclasses:
        ========================
        p_min = C_tot / Q_heat

        where C_tot = TAC + (additional costs) - (additional revenues)

        TAC already includes:
        - EH capital costs + O&M
        - heat grid costs
        - energy procurement costs (EH + buildings)
        - MINUS: rev_local_el (EH -> consumer revenues)
        - MINUS: rev_feed_in_el (EH -> grid feed-in revenues)

        Depending on the business model, the following must be added in the
        post-processing:
        - Mieterstrom / Kundenanlage: +c_pv_ann, -rev_pv_btm, -rev_pv_export, -rev_reststrom
        - Kundenanlage additionally: +c_elgrid_ann
        - Cooperative: +c_pv_ann, -credit_avoided, -credit_pv_feedin
        """
        pass