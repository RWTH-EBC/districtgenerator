# -*- coding: utf-8 -*-
"""
Wärmecontracting mit Kundenanlage Business Model (BM 4)

Ownership
---------
- Energy hub: operator
- District heating network: operator
- Decentralized PV: operator
- Internal electricity grid incl. transformer: operator
- Public electricity grid: DSO

Electricity logic
-----------------
- A single operator supplies all tenant electricity at the uniform tariff
  p_ms = alpha * p_retail_cons.
- Building-level PV, energy-hub electricity and residual public-grid imports
  are part of one integrated operator-side electricity business.
- Electricity distribution within the district takes place via the internal grid.
- Surplus electricity is exported to the public grid and remunerated via
  the feed-in tariff.

Bewertungslogik (PDF)
---------------------
- Kundenanlage ist fachlich all-or-none: kein gebäudespezifischer Ausschluss.
- Es wird nur Szenario B (Anschlusszwang) bewertet.
- p_min ergibt sich aus dem Barwert der Betreiberkosten (TAC + dezentrale PV
  + internes Stromnetz) geteilt durch den Barwert des Wärmeabsatzes.
- p_max wird auf Quartiersebene über die Indifferenzbedingung
  Σ NPV_WN(p_max) = Σ NPV_Ref ermittelt.
- Diagnose pro Gebäude: ``economic_for_building`` zeigt Quersubventionierung.

References
----------
[1] Kerber, G. (2011). Aufnahmefaehigkeit von Niederspannungsverteilnetzen
    fuer die Einspeisung aus Photovoltaikkleinanlagen. Dissertation,
    TU Muenchen. https://mediatum.ub.tum.de/998003
[2] AMEV. EltAnlagen 2025 - Planung, Bau und Betrieb von elektrischen Anlagen
    in oeffentlichen Gebaeuden, Empfehlung Nr. 177, BMWSB, Berlin.
[3] Stute, J., Klobasa, M. (2024). How do dynamic electricity tariffs and
    different grid charge designs interact? Energy Policy 189, 114062.
    https://doi.org/10.1016/j.enpol.2024.114062
[4] KWW - Kompetenzzentrum Kommunale Waermewende. (2025).
    KWW-Technikkatalog Waermeplanung. Excel-Tabelle und Begleitdokument,
    Version Dezember 2025. Deutsche Energie-Agentur GmbH (dena), Halle (Saale).
[5] DIN 18015-1. Elektrische Anlagen in Wohngebaeuden - Teil 1:
    Planungsgrundlagen. DIN Deutsches Institut fuer Normung.
[6] DIN 42508. Transformatoren - Standard-Bemessungsleistungen fuer
    Verteiltransformatoren.
"""

from pathlib import Path
from typing import Dict, Optional
import numpy as np

from districtgenerator.business_models.Basis import BusinessModelBase
from districtgenerator.functions.din_house_connection_limits import (
    apply_din_house_connection_limits,
)
from districtgenerator.functions.trafo_sizing import (
    trafo_limit_from_house_connection_limits,
    DIN_TRAFO_STEPS_KVA,
)


class WaermecontractingKundenanlageBM(BusinessModelBase):

    # ==================================================================
    # GRID CONSTRAINTS
    # ==================================================================

    def configure_grid_constraints(
        self,
        data,
        din_csv_path: Optional[str | Path] = None,
        amev_csv_path: Optional[str | Path] = None,
        cosphi: float = 0.95,
        safety_factor: float = 1.10,
        g: float = 0.07,
        trafo_steps=DIN_TRAFO_STEPS_KVA,
        out_dir: Optional[Path] = None,
    ) -> dict:
        """
        Customer installation: the operator owns the transformer and pays for
        it. The transformer rating is selected endogenously in the design MILP
        (Stute & Klobasa 2024 cost) when ``trafo_sizing_mode == 'variable'``;
        falls back to the legacy DIN/Kerber pre-sizing otherwise.

        ``trafoMax_W`` is NOT enforced as an external DSO cap (the customer
        installation is behind the meter); it is only used internally for
        cost accounting.
        """
        from districtgenerator.functions.din_house_connection_limits import (
            apply_house_connection_limits,
        )
        from districtgenerator.functions.trafo_sizing import (
            trafo_lower_bound_from_house_connections,
        )

        if din_csv_path is None:
            data.site["enable_buildingMax_W"] = False
            data.site["enable_trafoMax_W"] = False
            return {}

        apply_house_connection_limits(
            data=data, enabled=True,
            din_csv_path=din_csv_path,
            amev_csv_path=amev_csv_path,
            write_back_to_buildings=True,
        )
        data.site["enable_buildingMax_W"] = True

        # Lower-bound size from the house-connection limits is mandatory.
        bound = trafo_lower_bound_from_house_connections(
            data=data, cosphi=cosphi, safety_factor=safety_factor,
            g_residential=g, steps=trafo_steps,
        )
        data.site["trafo_min_kVA"] = bound["min_din_step_kVA"]
        data.site["trafo_steps_kVA"] = list(trafo_steps)
        data.site["trafo_cosphi"] = cosphi
        data.site["trafo_sizing_summary"] = bound

        # Behind-the-meter installation: no external DSO cap is enforced.
        data.site["enable_trafoMax_W"] = False

        # Operator pays for the transformer -> include investment in the MILP.
        data.site["trafo_invest_endogenous"] = True

        mode = str(data.site.get("trafo_sizing_mode", "variable")).lower()
        if mode == "din_kerber":
            # Legacy pre-sizing: pin to the smallest sufficient DIN step.
            chosen_kVA = bound["min_din_step_kVA"]
            data.site["trafo_chosen_kVA"] = chosen_kVA
            data.site["kundenanlage_trafo_kVA"] = chosen_kVA  # legacy alias
            return {**bound, "chosen_transformer_kVA": chosen_kVA}

        # mode == "variable": MILP picks the rating; nothing else to do here.
        # The legacy alias is kept as a safe default in case extraction fails.
        data.site["kundenanlage_trafo_kVA"] = bound["min_din_step_kVA"]
        return bound

    # ==================================================================
    # OPERATIONAL PRICE (für die Optimierung)
    # ==================================================================

    def get_price_el_revenue_by_year(self) -> dict:
        """
        Local electricity sales by the operator in the customer-installation model.
        Internal-grid distribution avoids public network charges. Only VAT is deducted.
        """
        alpha = float(self.ecoData["alpha"])
        share_vat = float(self.ecoData["share_el_vat"])

        return {
            year: (
                alpha * self.all_sim_ecoData[year]["price_supply_el"]
                - share_vat * self.all_sim_ecoData[year]["price_supply_el"]
            )
            for year in self.interpolation_points
        }

    # ==================================================================
    # KPI BERECHNUNG
    # ==================================================================

    def calculate_kpis(self, kpis, data, result: dict) -> None:
        """
        Calculate KPIs for the customer-installation business model.

        Berechnet:
        - p_min: kostendeckender Wärmepreis (Betreibersicht).
          Barwerte aller Betreiberkosten (TAC + dezentrale PV + internes
          Stromnetz) durch Barwert des Wärmeabsatzes.
        - p_max: Indifferenz-Wärmepreis auf Quartiersebene gegen die Referenz.
        - Diagnose pro Gebäude (ohne Ausschluss).

        Kundenanlage ist all-or-none — kein Szenario A.
        """
        support_years = list(self.interpolation_points)
        if not support_years:
            kpis.p_min = None
            kpis.p_max = None
            return

        # Diagnostic only: TAC is no longer the heat-price numerator.
        legacy_tac_total = float(result.get("tac", 0.0) or 0.0)

        heat_cost = self._operator_heat_cost_lcoh_like(
            kpis=kpis,
            data=data,
            support_years=support_years,
        )
        heat_total = heat_cost["heat_total_kWh"]
        heat_by_building = self._heat_delivered_by_building(data)
        bw_heat_total = heat_cost["bw_heat_total"]
        bw_operator_heat_cost = heat_cost["bw_heat_cost"]

        # ----------------------------------------------------------------
        # Betreiberseitige Zusatzkosten: dezentrale PV (gehört Betreiber)
        # ----------------------------------------------------------------
        # Harte Prüfung: ohne dezentrale Kostendaten ist p_min systematisch
        # zu niedrig. Lieber crashen als still falsche Ergebnisse liefern.
        dev_costs_all = self._require_decentral_costs(kpis)

        pv_cost_ann_total = 0.0
        for n, n_costs in dev_costs_all.items():
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue
            if "PV" in n_costs:
                pv_cost_ann_total += float(n_costs["PV"].get("subsidized_annual_cost", 0.0))

        # ----------------------------------------------------------------
        # Internes Stromnetz: Kabel immer postprocessing.
        # Trafo-Investition nur wenn der MILP sie nicht bereits enthält
        # (Schutz gegen Doppelzählung bei variable trafo sizing).
        # ----------------------------------------------------------------
        trafo_ann_from_milp = float(result.get("trafo_ann_cost_eur_per_a", 0.0) or 0.0)
        c_elgrid_ann_post = self._elgrid_annual_cost(
            data=data,
            include_trafo=(trafo_ann_from_milp <= 0.0),
        )
        # If the transformer annuity was selected inside the MILP, it is not
        # part of the LCOH-like heat-cost reconstruction. Add it explicitly.
        c_elgrid_ann = c_elgrid_ann_post + trafo_ann_from_milp
        bw_elgrid = self._bw_constant_annual(c_elgrid_ann)
        bw_pv_cost_total = self._bw_constant_annual(pv_cost_ann_total)

        # Alle Terme sind Barwerte [EUR] -> konsistent addierbar.
        bw_operator_heat_cost_incl_pv_grid = (
            bw_operator_heat_cost
            + bw_pv_cost_total
            + bw_elgrid
        )
        p_min = bw_operator_heat_cost_incl_pv_grid / bw_heat_total if bw_heat_total > 0 else None

        # ----------------------------------------------------------------
        # Endkundenseite (NPV)
        # ----------------------------------------------------------------
        npv_ref_by_building = self.ecoData.get("npv_ref_by_building", {})

        npv_strom_wn_by_building = self._npv_strom_wn_by_building(
            data=data,
            result=result,
        )
        npv_wn_at_p_min_by_building = self._npv_wn_by_building_at_price(
            heat_by_building=heat_by_building,
            npv_strom_wn_by_building=npv_strom_wn_by_building,
            heat_price=p_min,
        )

        scenario_b = self._scenario_b(
            heat_by_building=heat_by_building,
            npv_ref_by_building=npv_ref_by_building,
            npv_strom_wn_by_building=npv_strom_wn_by_building,
            npv_wn_at_price_by_building=npv_wn_at_p_min_by_building,
        )

        p_max = scenario_b["p_max"]

        # ----------------------------------------------------------------
        # KPI-Felder setzen
        # ----------------------------------------------------------------
        kpis.p_min = p_min
        kpis.p_max = p_max
        kpis.business_model = self.ecoData.get("business_model")

        kpis.kundenanlage_breakdown = {
            "business_model": self.ecoData.get("business_model"),
            "model_scope": "all_or_none",
            "allows_building_exclusion": False,

            "legacy_tac_total_diagnostic": legacy_tac_total,
            "cost_basis": heat_cost["method"],
            "operator_heat_cost_by_year": heat_cost["annual_heat_cost_by_year"],
            "operator_heat_cost_details_by_year": heat_cost["year_details"],
            "bw_operator_heat_cost": bw_operator_heat_cost,
            "pv_cost_ann_total": pv_cost_ann_total,
            "bw_pv_cost_total": bw_pv_cost_total,
            "c_elgrid_ann_postprocessing": c_elgrid_ann_post,
            "c_elgrid_ann": c_elgrid_ann,
            "bw_elgrid": bw_elgrid,
            "trafo_ann_from_milp": trafo_ann_from_milp,
            "bw_operator_heat_cost_incl_pv_grid": bw_operator_heat_cost_incl_pv_grid,
            "heat_total_kWh": heat_total,
            "bw_heat_total": bw_heat_total,
            "p_min": p_min,
            "p_max": p_max,
            "p_max_a": None,
            "p_max_b": scenario_b["p_max"],
            "alpha": float(self.ecoData.get("alpha", 0.9)),
            "scenario": "B",
            "npv_strom_wn_by_building": npv_strom_wn_by_building,
            "npv_wn_at_p_min_by_building": npv_wn_at_p_min_by_building,

            # Stub-Block, damit die Workflow-Logik ein eindeutiges Signal sieht.
            "scenario_a": {
                "enabled": False,
                "reason": "Kundenanlage is evaluated as all-or-none; "
                          "no building-level exclusion is allowed.",
                "connected": list(heat_by_building.keys()),
                "excluded": [],
                "needs_iteration": False,
                "p_max": None,
                "p_max_by_building": {},
                "building_details": scenario_b.get("building_details", {}),
            },
            "scenario_b": scenario_b,
        }

        # Einheitlicher Zugriffspunkt für die Workflow-Logik.
        kpis.bm_breakdown = kpis.kundenanlage_breakdown

    # ==================================================================
    # NPV ENDKUNDENSEITE
    # ==================================================================

    def _npv_strom_wn_by_building(self, data, result: dict, kpis=None) -> Dict[int, float]:
        """
        Building-level electricity-side NPV in the WN case.

        Customer-installation-specific assumption:
        - tenants buy their full electricity demand from the operator at the
          uniform internal tariff p_ms = alpha * p_retail_cons
        - no separate tenant-side allocation by source is performed
        - end-customer electricity NPV therefore consists only of the payment
          for total building electricity demand at p_ms
        """
        support_years = list(self.interpolation_points)
        alpha = float(self.ecoData.get("alpha", 0.9))
        dt = float(data.time["timeResolution"])

        clusters = list(getattr(data, "clusters", range(data.time["clusterNumber"])))
        cluster_weights = data.clusterWeights

        npv_by_building = {}

        for n in range(len(data.district)):
            heater = data.district[n]["buildingFeatures"].get("heater", "").upper()
            if heater != "HEAT_GRID":
                continue

            cost_by_year = {}
            for year in support_years:
                p_ms = alpha * float(self.all_sim_ecoData[year]["price_supply_el"])
                cost = 0.0

                for c in range(len(clusters)):
                    cw = float(cluster_weights[clusters[c]])
                    res = data.resultsOptimization[year][c][n]

                    demand = np.array(res.get("Elec_dem", {}).get("P_el", [0]), dtype=float)
                    demand_kwh = demand.sum() * dt / 3600.0 / 1000.0
                    cost += cw * demand_kwh * p_ms

                cost_by_year[year] = cost

            bw_cost = self._bw_by_support_year(cost_by_year)
            npv_by_building[n] = -bw_cost

        return npv_by_building

    def _npv_wn_by_building_at_price(
        self,
        heat_by_building: Dict[int, float],
        npv_strom_wn_by_building: Dict[int, float],
        heat_price: Optional[float],
    ) -> Dict[int, float]:
        """
        Total end-customer NPV in the WN case for a given heat price.

        NPV_wn,i(p) = - heat_i * p * PVAF + npv_strom_wn_i
        """
        if heat_price is None:
            return {}

        pvaf = self._present_value_factor()
        npv_by_building = {}

        for n, heat_kwh in heat_by_building.items():
            npv_heat = -heat_kwh * heat_price * pvaf
            npv_strom = npv_strom_wn_by_building.get(n, 0.0)
            npv_by_building[n] = npv_heat + npv_strom

        return npv_by_building

    # ==================================================================
    # SZENARIO B (Anschlusszwang, Quartiersaggregat)
    # ==================================================================

    def _scenario_b(
        self,
        heat_by_building,
        npv_ref_by_building,
        npv_strom_wn_by_building,
        npv_wn_at_price_by_building,
    ) -> dict:
        """
        Szenario B: Anschlusszwang für alle Gebäude.

        Feasibility-Bedingung (PDF):
            Σ NPV_WN(p_min) >= Σ NPV_Ref
        Quartier-p_max:
            Σ NPV_WN(p_max) = Σ NPV_Ref

        Zusätzlich: gebäudespezifischer NPV-Vergleich als Diagnose —
        zeigt welche Gebäude beim Quartiersausgleich profitieren
        und welche quersubventioniert werden. Kein Ausschluss.
        """
        if not npv_ref_by_building:
            return {
                "sum_npv_wn_at_price": 0.0,
                "sum_npv_ref": 0.0,
                "sum_npv_strom_wn": 0.0,
                "heat_total_kWh": 0.0,
                "p_max": None,
                "connected_buildings": list(heat_by_building.keys()),
                "building_details": {},
                "quartier_feasible": None,
            }

        sum_npv_ref = 0.0
        sum_npv_wn_at_price = 0.0
        sum_npv_strom_wn = 0.0
        heat_total = 0.0
        building_details = {}

        for n, heat_kwh in heat_by_building.items():
            npv_ref_n = npv_ref_by_building.get(n, 0.0)
            npv_wn_n = npv_wn_at_price_by_building.get(n, 0.0)
            npv_strom_n = npv_strom_wn_by_building.get(n, 0.0)

            sum_npv_ref += npv_ref_n
            sum_npv_wn_at_price += npv_wn_n
            sum_npv_strom_wn += npv_strom_n
            heat_total += heat_kwh

            building_details[n] = {
                "heat_kWh": heat_kwh,
                "npv_ref": npv_ref_n,
                "npv_wn_at_price": npv_wn_n,
                "npv_strom_wn": npv_strom_n,
                "economic_for_building": npv_wn_n >= npv_ref_n,
            }

        p_max = self._p_max_from_npvs(
            heat_kwh=heat_total,
            npv_ref=sum_npv_ref,
            npv_wn_other=sum_npv_strom_wn,
        ) if heat_total > 0 else None

        return {
            "sum_npv_wn_at_price": sum_npv_wn_at_price,
            "sum_npv_ref": sum_npv_ref,
            "sum_npv_strom_wn": sum_npv_strom_wn,
            "heat_total_kWh": heat_total,
            "p_max": p_max,
            "connected_buildings": list(heat_by_building.keys()),
            "building_details": building_details,
            "quartier_feasible": sum_npv_wn_at_price >= sum_npv_ref,
        }

    # ==================================================================
    # INTERNES STROMNETZ (Kabel + Trafo, jährlich)
    # ==================================================================

    def _cable_length(self, data) -> float:
        length = data.el_grid_data.get("length", None)
        if length is None:
            print("WARNING KundenanlageBM: 'length' nicht in data.el_grid_data gesetzt → E-Netz-Kosten = 0")
            return 0.0
        return float(length)

    def _elgrid_annual_cost(self, data, include_trafo: bool = True) -> float:
        """
        Annualized internal electricity-grid cost [EUR/a].

        Cable cost: per-meter investment + O&M from el_grid_data.
        Transformer investment: piecewise-linear Stute & Klobasa (2024).
        Transformer O&M: KWW Technikkatalog fixed cost per unit [EUR/(Stk.*a)],
        using ``el_grid_data['om_trafo']``. Default in config.py is the typical
        value 1,600 EUR/(Stk.*a); low/high source values are 800/2,400.

        Parameters
        ----------
        include_trafo : bool
            False, wenn der MILP die Trafo-Investition bereits enthält
            (Schutz gegen Doppelzählung).
        """
        from districtgenerator.functions.trafo_sizing import trafo_cost_eur

        cfg = data.el_grid_data

        cable_length_m = self._cable_length(data)
        ann_factor_cable = self._annuity_factor(cfg["life_cable"])
        ann_cable = (
            cfg["inv_cable_per_m"] * cable_length_m * ann_factor_cable
            + cfg["om_cable_per_m"] * cable_length_m
        )

        if not include_trafo:
            return ann_cable

        count_by_step_raw = data.site.get("trafo_count_by_step", {}) or {}
        count_by_step = {float(k): int(v) for k, v in count_by_step_raw.items() if int(v) > 0}

        if count_by_step:
            inv_trafo = sum(trafo_cost_eur(kva) * n for kva, n in count_by_step.items())
            n_transformers = sum(count_by_step.values())
        else:
            # Legacy fallback: one transformer with the chosen total rating.
            chosen_kVA = float(data.site.get("trafo_chosen_kVA", data.site.get("kundenanlage_trafo_kVA", 630.0)))
            inv_trafo = trafo_cost_eur(chosen_kVA)
            n_transformers = 1 if chosen_kVA > 0 else 0

        ann_factor_trafo = self._annuity_factor(cfg["life_trafo"])
        om_trafo = float(cfg.get("om_trafo", 1600.0)) * n_transformers
        ann_trafo = inv_trafo * ann_factor_trafo + om_trafo

        return ann_cable + ann_trafo