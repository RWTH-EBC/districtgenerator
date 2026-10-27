"""Once-only investment grants; BEW calculations are research screening, not approval.

Investment and grant both occur at t=0. Monetary inputs are EUR without recoverable VAT.
Replacement investments and terminal residual values always retain their gross basis.
"""
import math

import pyomo.environ as pyo


def capital_recovery_factor(interest_rate, years):
    i, n = float(interest_rate), float(years)
    if not math.isfinite(i) or i <= -1 or not math.isfinite(n) or n <= 0:
        raise ValueError("Interest must exceed -1 and the assessment horizon must be positive.")
    return 1.0 / n if abs(i) < 1e-12 else i / (1.0 - (1.0 + i) ** (-n))


def once_only_annuity(gross_investment, lifecycle_factor, grant, eco):
    """Keep gross replacement/residual costs and deduct one initial grant at t=0."""
    return gross_investment * lifecycle_factor - grant * capital_recovery_factor(
        eco["interest_rate"], eco["observation_time"])


# BEW guideline 4.2: eligible heat generators, thermal storage and heat-network
# infrastructure. Fossil generators, CHP, pure electricity/cooling assets are excluded.
BEW_HEAT_DEVICES = ("HP", "WaterHP", "STC", "TES", "BBOI")
# Heat-share accounting is separate from investment eligibility. BCHP is
# assumed to use biomass meeting the BEW fuel/sustainability requirements.
BEW_RENEWABLE_HEAT_DEVICES = ("HP", "WaterHP", "STC", "BBOI", "BCHP")


def bew_heat_mix_conditions(heat, recovered=0.0, absorption_heat=0.0, renewable_shortfall=0.0, gas_excess=0.0):
    """Generation-based share before storage; non-credited heat supplies AC first.

    Building heat-pump output is not an additional network heat source. Counting
    it would count network heat twice and could disguise fossil regeneration.
    Ambient pipe gains are outside this indicator. Only cooling return matched
    to simultaneous building HP heat extraction is passed as recovered heat.
    It is credited as waste heat by research assumption, not verified BEW eligibility.
    R and U are credited and non-credited producer heat; Qac is chiller input.
    Remaining producer heat is H = R + U - Qac. The share is
    (min(R, H) + recovered) / (H + recovered). For nonnegative H and recovered,
    the 75-percent test is equivalent to R + recovered >= .75*(H + recovered).
    A separate H >= 0 check prevents allocating more heat to AC than produced.
    No extra variables/binaries are needed. Storage charge,
    discharge and losses are not added/subtracted in this generation proxy.
    This is not an exact share of heat delivered at the network boundary.

    Allocation is an energy-accounting assumption over the assessment period
    (operation cluster / design support year), not timestep-resolved routing.
    To evaluate the gas limit consistently, cooling takes BOI/GHP heat first,
    then other non-credited heat, then renewable heat. A separate combined
    gas/CHP 25-percent limit is redundant: gas/CHP heat is a subset of U,
    and the 75-percent condition already implies U - Qac <= .25*(H + recovered).
    """
    remaining_heat = sum(heat.values()) - absorption_heat
    total = remaining_heat + recovered
    renewable = sum(value for d, value in heat.items() if d in BEW_RENEWABLE_HEAT_DEVICES)
    combustion = heat.get("BOI", 0.0) + heat.get("GHP", 0.0)
    return (renewable + recovered + renewable_shortfall >= .75 * total,
            combustion - absorption_heat <= .10 * total + gas_excess,
            pyo.inequality(0.0, remaining_heat))


def bew_5g_recovered_heat_profile(data, typedays, horizon):
    """Match recovery to simultaneous building HP extraction, then select medoids.

    Both raw profiles are kW on the cold-network side. Recovery serves heating
    first; excess cooling return and possible delayed use through storage get
    no credit. Taking the minimum before aggregation prevents crediting heat
    returned during a cooling-only timestep against demand at another time.
    """
    import numpy as np

    profiles = []
    for key in ("net_heat_rejection_5g", "net_heat_extraction_5g"):
        if key not in data.heat_grid_data:
            raise ValueError(f"BEW 5G heat-mix constraints require source profile '{key}'.")
        values = np.asarray(data.heat_grid_data[key], dtype=float)
        if values.ndim != 1 or not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"Invalid BEW 5G source profile '{key}'.")
        profiles.append(values)
    if profiles[0].shape != profiles[1].shape:
        raise ValueError("BEW 5G cooling return and heating extraction profiles must have equal lengths.")
    profile = np.minimum(profiles[0], profiles[1])
    periods = []
    for day in typedays:
        start = int(day) * horizon
        period = profile[start:start + horizon]
        if day != int(day) or day < 0 or len(period) != horizon:
            raise ValueError("BEW 5G recovery/heating profiles do not cover the selected medoid.")
        periods.append(period)
    return np.asarray(periods)


def _operation_funding_heat_terms(model, data, cluster):
    """Existing producer/AC sums and coincident 5G recovery, in summed W."""
    heat = {d: sum(getattr(model, f"eh_heat_{d}")[t] for t in model.t)
            for d in model.eh_ecs_heat if d not in ("AC", "to_grid")}
    recovered = 0.0
    if data.heat_grid_data.get("heatgrid_generation") == "5G":
        meta = data.centralDevices["capacities"]["cluster_meta"]
        rejection = bew_5g_recovered_heat_profile(data, meta["typedays"], int(meta["clusterLength"]))
        # Operation uses W; physical network profiles are kW.
        recovered = sum(rejection[cluster, int(t)] * 1000 for t in model.t)
    absorption_heat = sum(model.eh_heat_AC[t] for t in model.t)
    return heat, recovered, absorption_heat


def add_operation_funding_heat_mix(model, data, cluster, soft=False):
    """Cluster limits; the annual-triggered fallback uses soft limits in kWh."""
    if not getattr(data, "funding_config", {}).get("enabled", False):
        return
    heat, recovered, absorption_heat = _operation_funding_heat_terms(model, data, cluster)
    shortfall = excess = 0.0
    if soft:
        # W * timestep hours / 1000 = kWh; both violations have equal energy weight.
        scale = data.time["timeResolution"] / 3600.0 / 1000.0
        heat = {d: value * scale for d, value in heat.items()}
        recovered *= scale
        absorption_heat *= scale
        model.funding_shortfall = pyo.Var(["renewable", "gas"], domain=pyo.NonNegativeReals)
        shortfall = model.funding_shortfall["renewable"]
        excess = model.funding_shortfall["gas"]
        model.funding_violation = pyo.Expression(expr=shortfall + excess)
        model.funding_total_heat = pyo.Expression(expr=sum(heat.values()) - absorption_heat + recovered)
    model.funding_heat_mix = pyo.ConstraintList()
    for condition in bew_heat_mix_conditions(heat, recovered, absorption_heat, shortfall, excess):
        model.funding_heat_mix.add(condition)


def operation_funding_heat_totals(model, data, cluster):
    """Unrounded cluster energies for the annual check, using the agreed AC allocation."""
    heat, recovered, absorption_heat = _operation_funding_heat_terms(model, data, cluster)
    heat = {d: float(pyo.value(value)) for d, value in heat.items()}
    absorption_heat = float(pyo.value(absorption_heat))
    recovered = float(pyo.value(recovered))
    remaining = sum(heat.values()) - absorption_heat
    if remaining < -1e-6 * max(1.0, sum(heat.values())):
        raise ValueError("Absorption cooling exceeds producer heat in the funding heat balance.")
    remaining = max(remaining, 0.0)
    renewable = sum(value for d, value in heat.items() if d in BEW_RENEWABLE_HEAT_DEVICES)
    scale = data.time["timeResolution"] / 3600.0 / 1000.0
    result = {
        "total_heat_kwh": (remaining + recovered) * scale,
        "eligible_heat_kwh": (min(max(renewable, 0.0), remaining) + recovered) * scale,
        "gas_heat_kwh": max(heat.get("BOI", 0.0) + heat.get("GHP", 0.0) - absorption_heat, 0.0) * scale,
    }
    if hasattr(model, "funding_minimum_violation_kwh"):
        result["minimum_violation_kwh"] = model.funding_minimum_violation_kwh
        result["remaining_violation_kwh"] = float(pyo.value(model.funding_violation))
    return result


def annual_operation_funding_heat_mix(cluster_results, cluster_weights):
    """Weight energies, not percentages; 72%/12% decide whether fallback is needed."""
    totals = dict(total_heat_kwh=0.0, eligible_heat_kwh=0.0, gas_heat_kwh=0.0)
    for cluster, result in cluster_results.items():
        weight = float(cluster_weights[cluster])
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("Cluster weights must be finite and nonnegative.")
        for key in totals:
            value = float(result["funding_heat_mix"][key])
            if not math.isfinite(value) or value < 0:
                raise ValueError("Funding heat totals must be finite and nonnegative.")
            totals[key] += weight * value
    total = totals["total_heat_kwh"]
    renewable = totals["eligible_heat_kwh"] / total if total > 0 else None
    gas = totals["gas_heat_kwh"] / total if total > 0 else None
    # Only roundoff is tolerated at the agreed acceptance-band boundaries.
    epsilon = 1e-9
    return dict(totals, renewable_share=renewable, gas_share=gas,
                within_acceptance_band=(total == 0 or (renewable >= .72 - epsilon and gas <= .12 + epsilon)),
                meets_targets=(renewable >= .75 - 1e-6 and gas <= .10 + 1e-6) if total > 0 else None)


def prepare_investment_funding(data):
    """Restore costs before the project grant; BEW replaces individual hub/5G grants."""
    grid = data.heat_grid_data
    if "ann_costs" not in grid:
        return
    previous_annuity = grid["ann_costs"]
    grid["ann_costs"] = grid.get("ann_costs_before_network_funding", grid["ann_costs"])
    if "investment_funding" in grid:
        grid["ann_costs"] = grid.get("ann_costs_before_network_funding", grid["ann_costs_unsubsidized"])
        del grid["investment_funding"]
    if "ann_costs_without_HP_5G_unsubsidized" in grid:
        grid["ann_costs_without_HP_5G"] = grid["ann_costs_without_HP_5G_unsubsidized"]
        infrastructure = sum(grid["initial_investment_components"].values())
        grid.setdefault("HP_5G_initial_investment", grid.get("costs_unsubsidized", infrastructure) - infrastructure)
        grid.setdefault("HP_5G_individual_grant", grid.get("costs_unsubsidized", 0) - grid.get("costs", 0))
        grid.setdefault("HP_5G_ann_costs_individual", grid["HP_5G_ann_costs"])
        enabled = getattr(data, "funding_config", {}).get("enabled", False)
        grid["HP_5G_ann_costs"] = (grid["HP_5G_ann_costs_unsubsidized"] if enabled
                                  else grid["HP_5G_ann_costs_individual"])
        grid["ann_costs"] = grid["ann_costs_without_HP_5G_unsubsidized"] + grid["HP_5G_ann_costs"]
        grid["costs"] = infrastructure + grid["HP_5G_initial_investment"] - (0 if enabled else grid["HP_5G_individual_grant"])
    grid["ann_costs_before_network_funding"] = grid["ann_costs"]
    if "network_total_costs" in grid:
        grid["network_total_costs"] += grid["ann_costs"] - previous_annuity
        grid["network_total_costs_before_network_funding"] = grid["network_total_costs"]


def add_investment_funding(model, data, param):
    """One initial BEW grant for eligible hub devices, infrastructure and 5G heat pumps.

    This applies the configured rate directly to eligible
    investment. No project-level financial caps are modelled.
    The BEW network-size requirement is assumed fulfilled for these scenarios.
    """
    from districtgenerator.data_handling.config import FundingConfig

    config = FundingConfig(**getattr(data, "funding_config", {}))
    model.investment_grant = pyo.Var(domain=pyo.NonNegativeReals)
    model.annual_investment_grant = pyo.Expression(
        expr=model.investment_grant * capital_recovery_factor(
            param["interest_rate"], param["observation_time"]))
    model._investment_funding = {"enabled": config.enabled}
    if not config.enabled:
        model.investment_grant.fix(0)
        return
    grid = data.heat_grid_data
    is_5g = grid.get("heatgrid_generation") == "5G"
    if grid.get("heatgrid_generation") not in ("4G", "5G"):
        raise ValueError("Investment funding supports 4G and 5G heat networks only.")
    network = grid.get("initial_investment_components")
    if network is None:
        raise ValueError("Investment funding needs the network's initial cost ledger.")
    unknown = set(network) - {"network_pipes", "network_construction", "network_pump", "network_substations", "network_heating"}
    if unknown:
        raise ValueError(f"Unknown eligible cost components: {sorted(unknown)}")
    model.funding_heat_mix = pyo.ConstraintList()
    recovered = 0.0
    if is_5g:
        rejection = bew_5g_recovered_heat_profile(data, param["typedays"], len(model.time_steps))
        recovered = sum(rejection[c, int(t)] * param["cluster_weights"][c]
                        for c in model.clusters for t in model.time_steps)
    for y in model.support_years:
        annual = {d: sum(model.heat[d, y, c, t] * param["cluster_weights"][c]
                         for c in model.clusters for t in model.time_steps)
                  for d in model.heat_devs if d != "AC"}
        absorption_heat = sum(model.heat["AC", y, c, t] * param["cluster_weights"][c]
                              for c in model.clusters for t in model.time_steps)
        for condition in bew_heat_mix_conditions(annual, recovered, absorption_heat):
            model.funding_heat_mix.add(condition)
    fixed_eligible = sum(float(cost) for cost in network.values())
    building_hp = float(grid.get("HP_5G_initial_investment", 0.0)) if is_5g else 0.0
    if any(not math.isfinite(float(cost)) or cost < 0 for cost in network.values()) or not math.isfinite(building_hp) or building_hp < 0:
        raise ValueError("Initial network and heat-pump costs must be finite and nonnegative.")
    fixed_eligible += building_hp
    selected = [d for d in BEW_HEAT_DEVICES if d in model.all_devs]
    eligible = fixed_eligible + sum(model.inv_base[d] for d in selected)
    model.funding_eligible_investment = pyo.Expression(expr=eligible)
    model.funding_constraint = pyo.Constraint(expr=model.investment_grant == config.rate * eligible)


def funding_results(model, data):
    """Allocate the single project grant proportionally for consistent component KPIs."""
    result = dict(model._investment_funding)
    if not result["enabled"]:
        return result
    grid = data.heat_grid_data
    selected = set(BEW_HEAT_DEVICES) | set(grid["initial_investment_components"])
    costs = {d: pyo.value(model.inv_base[d]) for d in model.all_devs}
    costs.update(grid["initial_investment_components"])
    if grid.get("heatgrid_generation") == "5G":
        costs["HP_5G"] = grid.get("HP_5G_initial_investment", 0.0)
        selected.add("HP_5G")
    eligible = {key: value if key in selected else 0.0 for key, value in costs.items()}
    total = sum(eligible.values())
    grant = float(pyo.value(model.investment_grant))
    factor = capital_recovery_factor(data.ecoData["interest_rate"], data.ecoData["observation_time"])
    result.update(grant_eur=grant, eligible_investment_eur=total,
                  annual_grant_eur=grant * factor,
                  components={key: {"initial_investment_eur": value,
                                    "eligible_investment_eur": eligible[key],
                                    "grant_eur": grant * eligible[key] / total if total else 0.0,
                                    "annual_grant_eur": factor * grant * eligible[key] / total if total else 0.0}
                              for key, value in costs.items()})
    return result
