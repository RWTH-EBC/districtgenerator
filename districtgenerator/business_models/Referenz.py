# -*- coding: utf-8 -*-
"""
Referenzfall — dezentrale Wärmeversorgung

Zwei Varianten, gesteuert über ecoData["reference_case"]:

  "boi"   : Konservativer Referenzfall
            Gas-Kessel + dezentrale PV
            Repräsentiert heutigen Gebäudebestand
            → hoher NPV_Ref (geringe Investitionskosten)

  "hp_pv" : Progressiver Referenzfall
            Wärmepumpe + dezentrale PV
            Repräsentiert beste dezentrale Alternative
            → niedrigerer NPV_Ref (höhere Investitionskosten)

Bewertungsprinzip:
- Nur echte Zahlungsströme (Systempreis — keine Trennung Wärme/Strom)
- NPV_Ref,i je Gebäude = vollständiger Barwert aller Kosten und Erlöse
- Summe NPV_Ref = Σ NPV_Ref,i (für BM-Vergleich auf Quartiersebene)
- Kein p_max im Referenzlauf — nur Bereitstellung von npv_ref_by_building

Gespeicherte Größen für BM-Injection:
- kpis.npv_ref_by_building  : {n: float} — pro Gebäude
- kpis.npv_ref              : float      — Summe über alle Gebäude
- kpis.reference_case       : str        — "boi" oder "hp_pv"
"""

from typing import Dict, Optional
import numpy as np

from .Basis import BusinessModelBase


class ReferenzBM(BusinessModelBase):

    def get_price_el_revenue_by_year(self) -> dict:
        """Kein lokaler Stromverkauf im Referenzfall."""
        return {year: 0.0 for year in self.interpolation_points}

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        Berechnet NPV_Ref,i je Gebäude für den gewählten Referenzfall.

        Gespeichert wird:
        - kpis.npv_ref_by_building  {n: float}
        - kpis.npv_ref              float (Summe)
        - kpis.reference_case       str
        - kpis.p_min = None         (kein p_min im Referenzfall)
        - kpis.p_max = None         (kein p_max im Referenzfall)
        """
        reference_case = self.ecoData.get("reference_case", "boi")
        support_years = list(self.interpolation_points)

        if not support_years:
            kpis.p_min = None
            kpis.p_max = None
            kpis.npv_ref = None
            kpis.npv_ref_by_building = {}
            kpis.reference_case = reference_case
            return

        if reference_case == "boi":
            npv_by_building = self._npv_boi(data, kpis, support_years)
        elif reference_case == "hp_pv":
            npv_by_building = self._npv_hp_pv(data, kpis, support_years)
        else:
            raise ValueError(
                f"ReferenceBM: Unbekannter reference_case '{reference_case}'. "
                f"Erlaubt: 'boi', 'hp_pv'."
            )

        npv_ref_total = sum(npv_by_building.values())

        kpis.p_min = None
        kpis.p_max = None
        kpis.npv_ref = npv_ref_total
        kpis.npv_ref_by_building = {n: float(v) for n, v in npv_by_building.items()}
        kpis.reference_case = reference_case

        kpis.reference_breakdown = {
            "reference_case": reference_case,
            "npv_ref_total": npv_ref_total,
            "npv_ref_by_building": kpis.npv_ref_by_building,
        }

    # ==================================================================
    # REFERENZFALL 1: Gas-Kessel + PV (konservativ)
    # ==================================================================

    def _npv_boi(self, data, kpis, support_years: list) -> Dict[int, float]:
        """
        NPV je Gebäude: Gas-Kessel + dezentrale PV.

        Zahlungsströme:
        - Auszahlung: annualisierte Kessel-Investitionskosten
        - Auszahlung: Gas-Brennstoffkosten (Wärmebedarf / eta_boi × p_gas)
        - Auszahlung: Netzbezugskosten Strom (Haushaltsstrom + ggf. WW-Hilfsenergie)
        - Einzahlung: PV-Einspeisevergütung
        - Auszahlung: annualisierte PV-Investitionskosten
        """
        pv_flows = self._pv_flows_by_building_year(data, {})
        bw_feedin = self._bw_pv_feed_in_reference_by_building(data, pv_flows)
        bw_grid = self._bw_grid_cost_reference_by_building(data, support_years)
        dev_costs_all = self._require_decentral_costs(kpis)

        npv_by_building = {}

        for n in range(len(data.district)):
            # BOI-Kosten aus decentral_individual_devices_annualized_cost
            dev_costs = dev_costs_all.get(n, {})

            boi_cost_ann = float(
                dev_costs.get("BOI", {}).get("subsidized_annual_cost", 0.0)
            )
            pv_cost_ann = float(
                dev_costs.get("PV", {}).get("subsidized_annual_cost", 0.0)
            )

            bw_boi = self._bw_constant_annual(boi_cost_ann)
            bw_pv = self._bw_constant_annual(pv_cost_ann)

            # Gaskosten: Wärmebedarf / eta × p_gas
            bw_gas = self._bw_gas_cost_building(data, n, support_years)

            # Netzbezug (Haushaltsstrom ohne WP)
            bw_grid_n = bw_grid.get(n, 0.0)

            # PV Feed-in Erlöse
            bw_feedin_n = bw_feedin.get(n, 0.0)

            npv_by_building[n] = (
                - bw_boi
                - bw_pv
                - bw_gas
                - bw_grid_n
                + bw_feedin_n
            )

        return npv_by_building

    # ==================================================================
    # REFERENZFALL 2: Wärmepumpe + PV (progressiv)
    # ==================================================================

    def _npv_hp_pv(self, data, kpis, support_years: list) -> Dict[int, float]:
        """
        NPV je Gebäude: Wärmepumpe + dezentrale PV.

        Zahlungsströme:
        - Auszahlung: annualisierte WP-Investitionskosten
        - Auszahlung: annualisierte PV-Investitionskosten
        - Auszahlung: Netzbezugskosten Strom (Haushaltsstrom + WP-Strom)
        - Einzahlung: PV-Einspeisevergütung
        """
        pv_flows = self._pv_flows_by_building_year(data, {})
        bw_feedin = self._bw_pv_feed_in_reference_by_building(data, pv_flows)
        bw_grid = self._bw_grid_cost_reference_by_building(data, support_years)
        dev_costs_all = self._require_decentral_costs(kpis)

        npv_by_building = {}

        for n in range(len(data.district)):
            dev_costs = dev_costs_all.get(n, {})

            hp_cost_ann = float(
                dev_costs.get("HP", {}).get("subsidized_annual_cost", 0.0)
            )
            pv_cost_ann = float(
                dev_costs.get("PV", {}).get("subsidized_annual_cost", 0.0)
            )

            bw_hp = self._bw_constant_annual(hp_cost_ann)
            bw_pv = self._bw_constant_annual(pv_cost_ann)

            # Netzbezug enthält bereits WP-Strom (aus Optimierungsergebnis)
            bw_grid_n = bw_grid.get(n, 0.0)

            # PV Feed-in Erlöse
            bw_feedin_n = bw_feedin.get(n, 0.0)

            npv_by_building[n] = (
                - bw_hp
                - bw_pv
                - bw_grid_n
                + bw_feedin_n
            )

        return npv_by_building

    # ==================================================================
    # REFERENZ-STROMHILFSMETHODEN
    # ==================================================================

    def _bw_pv_feed_in_reference_by_building(
        self,
        data,
        pv_flows_by_building_year: Dict[int, Dict[int, dict]],
    ) -> Dict[int, float]:
        """
        Present value of PV feed-in revenues per building [EUR]
        for the decentralized reference case.

        Unlike the BM helper in Basis.py, this method intentionally does
        NOT filter for HEAT_GRID buildings. In the reference case the
        buildings are decentralized BOI/HP buildings.
        """
        support_years = sorted(pv_flows_by_building_year.keys())
        if not support_years:
            return {}

        bw_by_building = {}

        for n in range(len(data.district)):
            revenue_by_year = {}

            for year in support_years:
                flows = pv_flows_by_building_year.get(year, {}).get(n, {})
                e_export_mwh = flows.get("E_pv_export_MWh", 0.0)
                p_feedin = self.all_sim_ecoData[year]["revenue_feed_in_el"]

                revenue_by_year[year] = e_export_mwh * p_feedin * 1000.0

            bw_by_building[n] = self._bw_by_support_year(revenue_by_year)

        return bw_by_building

    def _bw_grid_cost_reference_by_building(
        self,
        data,
        support_years: list,
    ) -> Dict[int, float]:
        """
        Present value of grid electricity procurement costs per building [EUR]
        for the decentralized reference case.

        Unlike the BM helper in Basis.py, this method intentionally does
        NOT filter for HEAT_GRID buildings.
        """
        dt = float(data.time["timeResolution"])
        clusters = list(getattr(data, "clusters", range(data.time["clusterNumber"])))
        cluster_weights = data.clusterWeights

        bw_by_building = {}

        for n in range(len(data.district)):
            cost_by_year = {}

            for year in support_years:
                p_retail = self.all_sim_ecoData[year]["price_supply_el"]
                cost = 0.0

                for c in range(len(clusters)):
                    cw = float(cluster_weights[clusters[c]])
                    res = data.resultsOptimization[year][c][n]

                    res_load = np.array(res.get("res_load", [0.0]), dtype=float)
                    grid_kwh = (
                        np.maximum(res_load, 0.0).sum()
                        * dt / 3600.0 / 1000.0
                    )
                    cost += cw * grid_kwh * p_retail

                cost_by_year[year] = cost

            bw_by_building[n] = self._bw_by_support_year(cost_by_year)

        return bw_by_building

    # ==================================================================
    # HILFSMETHODE: Gaskosten je Gebäude
    # ==================================================================

    def _bw_gas_cost_building(self, data, n: int, support_years: list) -> float:
        """
        Present value of gas cost for one building from optimization results.

        Gas consumption = BOI["Q_th"] / eta_boi
        """
        eta_boi = float(
            data.decentral_device_data.get("BOI", {}).get("eta_th", 0.9)
        )
        dt = float(data.time["timeResolution"])
        clusters = list(getattr(data, "clusters", range(data.time["clusterNumber"])))
        cluster_weights = data.clusterWeights

        cost_by_year = {}

        for year in support_years:
            p_gas = self.all_sim_ecoData[year].get(
                "price_supply_gas_effective",
                self.all_sim_ecoData[year]["price_supply_gas"],)
            cost = 0.0

            for c in range(len(clusters)):
                cw = float(cluster_weights[clusters[c]])
                res = data.resultsOptimization[year][c][n]

                boi_heat = np.array(
                    res.get("BOI", {}).get("Q_th", [0]), dtype=float
                )
                gas_kwh = boi_heat.sum() * dt / 3600.0 / 1000.0 / eta_boi
                cost += cw * gas_kwh * p_gas

            cost_by_year[year] = cost

        return self._bw_by_support_year(cost_by_year)