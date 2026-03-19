# -*- coding: utf-8 -*-
"""
Abstract base class for all business models.

Each subclass implements modify_params (sets price_el_revenue before the
optimizer) and calculate_kpis (computes p_min / p_max from the results).
Optionally, configure_grid_constraints can be overridden for BMs that
own the local electricity grid (Kundenanlage).

Subclasses are looked up by ecoData["business_model"] via BM_REGISTRY.
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
        data.site["enable_buildingMax_W"] = False

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
                    f"INFO: DIN-basierte Trafogröße "
                    f"({summary['required_kVA']:.0f} kVA benötigt) erreicht "
                    f"größte NS-Stufe ({max(trafo_steps)} kVA)."
                )
        else:
            # Manual mode: keep trafoMax_W and enable_trafoMax_W from config
            pass

        return summary

    # ------------------------------------------------------------------
    # Helpers shared by all subclasses
    # ------------------------------------------------------------------

    def _support_year_weights(self, support_years: list) -> dict:

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
    # electricity flow calculations
    # ------------------------------------------------------------------

    def _calc_pv_flows(self, data, result: dict) -> dict:
        """
        Decentral PV electricity flows via timestep-accurate matching [MWh/a].

        For each building and timestep, btm usage is min(PV_gen, demand).
        The remainder is exported. Profiles are full-year (8760h), so
        cluster weights do not apply here.

        Returns dict with E_pv_total_MWh, E_pv_btm_MWh, E_pv_export_MWh.
        """
        support_years = sorted(result.get("rev_local_el_by_year", {}).keys())
        if not support_years:
            return {"E_pv_total_MWh": 0.0, "E_pv_btm_MWh": 0.0, "E_pv_export_MWh": 0.0}

        weights = self._support_year_weights(support_years)
        n_obs = int(self.ecoData["observation_time"])
        dt = float(data.time["timeResolution"])

        # Annual PV flows from full-year profiles
        E_pv_total_Wh = 0.0
        E_pv_btm_Wh = 0.0

        for n in range(len(data.district)):
            pv_profile = np.array(data.district[n]["generationPV"], dtype=float)
            demand_profile = (
                np.array(data.district[n]["user"].elec, dtype=float) +
                np.array(data.district[n]["user"].EV_carcharging_ondemand, dtype=float)
            )

            btm = np.minimum(pv_profile, demand_profile)
            E_pv_total_Wh += float(np.sum(pv_profile)) * dt / 3600.0   # W * s / 3600 = Wh
            E_pv_btm_Wh += float(np.sum(btm)) * dt / 3600.0

        E_pv_total_MWh_annual = E_pv_total_Wh / 1e6
        E_pv_btm_MWh_annual = E_pv_btm_Wh / 1e6

        # Year-weighted average
        E_pv_total_MWh = sum(E_pv_total_MWh_annual * weights[y] for y in support_years) / n_obs
        E_pv_btm_MWh = sum(E_pv_btm_MWh_annual * weights[y] for y in support_years) / n_obs
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
        """Annual grid electricity purchased by buildings [MWh/a]."""
        return self._annualized_yearly_value(result, "from_el_grid_buildings_by_year")

    def _calc_eh_to_buildings(self, data, result: dict) -> float:
        """Annual electricity delivered from Energy Hub to buildings [MWh/a]."""
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
        """