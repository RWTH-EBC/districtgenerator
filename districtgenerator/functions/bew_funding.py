"""BEW Modules 2 and 4.

Module 2 investment and its one initial grant occur at t=0; Module 4 pays annually.

Rates and conditions: BAFA BEW guidance, sections 4.5.2--4.5.4:
https://www.bafa.de/SharedDocs/Downloads/DE/Energie/bew_merkblatt_20251216.pdf
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
OPERATING_FUNDING_YEARS = 10


def policy_heat_mix_conditions(total, renewable, absorption, recovered, target):
    """Heat balance, retaining the policy-specific source credits."""
    remaining = total - absorption
    return (renewable + recovered >= target * (remaining + recovered),
            pyo.inequality(0.0, remaining))


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
    """Unrounded cluster energies for the annual check, using the AC allocation."""
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
    # Only roundoff is tolerated at the acceptance-band boundaries.
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


# Module 4: all energy quantities below are kWh, money is EUR, and time is hours.
# Source-specific annual performance is the linear research approximation.
# The heating balance is before storage, as in Module 2; no discharge is paid twice.

def _minimum(block, name, a, b, upper_a, upper_b):
    """Exact priority min(a,b); no binary when either side is absent or fixed."""
    if upper_a <= 0 or upper_b <= 0:
        return 0.0
    if pyo.is_fixed(a) and pyo.is_fixed(b):
        return min(float(pyo.value(a)), float(pyo.value(b)))
    if not all(math.isfinite(v) and v >= 0 for v in (upper_a, upper_b)):
        raise ValueError("Exact BEW priorities require finite technology capacity limits.")
    part = pyo.Block(concrete=True)
    block.add_component(name, part)
    part.amount = pyo.Var(bounds=(0, min(upper_a, upper_b)))
    part.side = pyo.Var(domain=pyo.Binary)
    part.constraints = pyo.ConstraintList()
    part.constraints.add(part.amount <= a)
    part.constraints.add(part.amount <= b)
    part.constraints.add(part.amount >= a - upper_a * (1 - part.side))
    part.constraints.add(part.amount >= b - upper_b * part.side)
    return part.amount


def _positive_cost(block, name, cost, lower, upper):
    """A negative net electricity bill gives a zero, never a negative, grant cap."""
    if lower >= 0:
        return cost
    if upper <= 0:
        return 0.0
    part = pyo.Block(concrete=True)
    block.add_component(name, part)
    part.value = pyo.Var(bounds=(0, upper))
    part.positive = pyo.Var(domain=pyo.Binary)
    part.constraints = pyo.ConstraintList()
    part.constraints.add(part.value >= cost)
    part.constraints.add(part.value <= cost - lower * (1 - part.positive))
    part.constraints.add(part.value <= upper * part.positive)
    return part.value


def add_operating_funding(model, data, *, param=None, devs=None, year=None, cluster=None, eco=None):
    """M4:
    No components are created with BEW off or after the ten-year support period.
    Direct hub PV/WT/WAT/BCHP supplies heating HPs before other hub consumers.
    Battery and other unqualified generation get no operating credit. At the hub
    connection, building PV is grid electricity.
    AC receives non-credited heat first, then HP, WaterHP, STC, BBOI and BCHP;
    the priority is on assessment-period heat, with no storage-origin tracking.
    Only existing HP O&M and allocated grid expenditure enter the HP OPEX cap;
    unmodelled auxiliary or direct-source expenses are not invented.
    """
    if not getattr(data, "funding_config", {}).get("enabled", False):
        return
    design = param is not None
    years = [int(y) for y in model.support_years if 0 <= int(y) < OPERATING_FUNDING_YEARS] if design else [int(year)]
    if not design and not 0 <= int(year) < OPERATING_FUNDING_YEARS:
        return
    if not years:
        return
    from districtgenerator.functions.hub_electricity_prices import operation_prices
    dt = data.time["timeResolution"] / 3600.0
    capacities = (getattr(data, "centralDevices", {}) or {}).get("capacities") or {}
    def active(d):
        return bool(devs.get(d, {}).get("feasible", False)) if design else float(capacities.get(d, {}).get("cap", 0)) > 0
    hp = [d for d in ("HP", "WaterHP") if active(d)]
    solar = active("STC")
    if not hp and not solar:
        return
    producers = [d for d in (model.heat_devs if design else model.eh_ecs_heat) if d not in ("AC", "to_grid")]
    periods = [(y, int(c), int(t)) for y in years for c in (model.clusters if design else [cluster])
               for t in (model.time_steps if design else model.t)]
    def power(d, p):
        return model.power[d, *p] if design else getattr(model, "eh_power_" + d)[p[2]] / 1000.0
    def heat(d, p):
        return model.heat[d, *p] if design else getattr(model, "eh_heat_" + d)[p[2]] / 1000.0
    def cop(d, p):
        values = devs[d]["COP"] if design else capacities["devs"][d]["COP"]
        value = float(values[p[0]][p[1]][p[2]])
        if not math.isfinite(value) or value < 1:
            raise ValueError("M4 heating COP must be finite and at least one.")
        return value
    def capacity_bound(d):
        if not active(d):
            return 0.0
        if not design:
            return float(capacities[d]["cap"])
        v = devs[d]
        bounds = [float(v[k]) for k in ("max_cap",) if v.get(k) is not None]
        if d in ("PV", "STC") and v.get("max_area") is not None:
            bounds.append(float(v["max_area"]) * float(v.get("G_stc", 1)) * float(v["eta"]))
        finite = [x for x in bounds if math.isfinite(x) and x >= 0]
        if not finite:
            raise ValueError("M4 priorities need a finite maximum capacity for " + d)
        return min(finite)
    def heat_bound(d):
        limit = capacity_bound(d)
        if d == "HP" and limit:
            source = devs[d] if design else capacities.get("devs", {}).get(d, {})
            profile = source.get("available_capacity_factor")
            if profile is not None:
                limit *= max([1.0] + [float(profile[p[1]][p[2]]) for p in periods])
        if d == "AC" and limit:
            source = devs[d] if design else data.central_device_data.get(d, {})
            limit *= max(1.0, 1.0 / float(source.get("eta_th", 1.0)))
        if d in ("CHP", "BCHP", "WCHP", "FC") and limit:
            v = devs[d] if design else data.central_device_data[d]
            limit *= float(v["eta_th"]) / float(v["eta_el"])
        return limit
    def factor(p):
        return dt * (float(param["cluster_weights"][p[1]]) if design else 1.0)
    def price(p):
        if design:
            if "price_supply_el_eh_profile" in param:
                return float(param["price_supply_el_eh_profile"][p[0]][p[1]][p[2]])
            return float(param["price_supply_el_eh"][p[0]])
        return float(operation_prices(eco, cluster, len(model.t))[p[2]])
    renewables = [d for d in ("PV", "WT", "WAT", "BCHP") if active(d)]
    others = [d for d in ("CHP", "WCHP", "FC") if active(d)]
    ac_active = active("AC")
    m4 = pyo.Block(concrete=True)
    model.operating_funding = m4
    m4.flow = pyo.Block(periods)
    frames = {}
    for p in periods:
        flow = m4.flow[p]
        flow.electricity = pyo.Var(hp, ("grid", "direct", "unfunded"), domain=pyo.NonNegativeReals)
        flow.constraints = pyo.ConstraintList()
        demand = sum(power(d, p) for d in hp)
        renewable = sum(power(d, p) for d in renewables)
        if renewables and hp:
            bound_hp = sum(heat_bound(d) / cop(d, p) for d in hp)
            direct = _minimum(flow, "hp_first", renewable, demand,
                              sum(capacity_bound(d) for d in renewables), bound_hp)
        else:
            direct = 0.0
        battery = 0.0
        if active("BAT"):
            if design:
                bound = capacity_bound("BAT") / dt
                battery = _positive_cost(flow, "battery_discharge", -model.ch["BAT", *p], -bound, bound)
            else:
                battery = model.eh_dch_BAT[p[2]] / 1000.0
        for d in hp:
            flow.constraints.add(sum(flow.electricity[d, s] for s in ("grid", "direct", "unfunded")) == power(d, p))
        if hp:
            flow.constraints.add(sum(flow.electricity[d, "direct"] for d in hp) == direct)
            flow.constraints.add(sum(flow.electricity[d, "grid"] for d in hp) <= power("from_grid", p))
            flow.constraints.add(sum(flow.electricity[d, "unfunded"] for d in hp) <= battery + sum(power(d, p) for d in others))
        if ac_active:
            flow.cooling_electricity = pyo.Var(hp, ("grid", "direct", "unfunded"), domain=pyo.NonNegativeReals)
            for d in hp:
                for s in ("grid", "direct", "unfunded"):
                    flow.constraints.add(flow.cooling_electricity[d, s] <= flow.electricity[d, s])
            if solar:
                flow.solar_to_ac = pyo.Var(domain=pyo.NonNegativeReals)
                flow.constraints.add(flow.solar_to_ac <= heat("STC", p))
        frames[p] = flow
    m4.annual = pyo.Block(years)
    summaries = {}
    for y in years:
        annual = m4.annual[y]
        ps = [p for p in periods if p[0] == y]
        annual.constraints = pyo.ConstraintList()
        if ac_active:
            remaining = sum(heat("AC", p) * factor(p) for p in ps)
            ac_upper = heat_bound("AC") * sum(factor(p) for p in ps)
            noncredited = [d for d in producers if d not in BEW_RENEWABLE_HEAT_DEVICES]
            order = [("noncredited", noncredited)] + [(d, [d]) for d in ("HP", "WaterHP", "STC", "BBOI", "BCHP") if active(d)]
            for name, sources in order:
                available = sum(heat(d, p) * factor(p) for d in sources for p in ps)
                upper = sum(heat_bound(d) for d in sources) * sum(factor(p) for p in ps)
                taken = _minimum(annual, "ac_from_" + name, available, remaining, upper, ac_upper)
                remaining -= taken
                if name in hp:
                    annual.constraints.add(sum(cop(name, p) * sum(frames[p].cooling_electricity[name, s] for s in ("grid", "direct", "unfunded")) * factor(p) for p in ps) == taken)
                elif name == "STC" and solar:
                    annual.constraints.add(sum(frames[p].solar_to_ac * factor(p) for p in ps) == taken)
            annual.constraints.add((0.0, remaining, 0.0))
        device_terms = {}
        for d in hp:
            terms = {}
            for s in ("grid", "direct", "unfunded"):
                eligible_e = {p: frames[p].electricity[d, s] - (frames[p].cooling_electricity[d, s] if ac_active else 0.0) for p in ps}
                terms[s + "_electricity_kwh"] = sum(eligible_e[p] * factor(p) for p in ps)
                terms[s + "_heat_kwh"] = sum(cop(d, p) * eligible_e[p] * factor(p) for p in ps)
                if s == "grid":
                    terms["grid_cost_eur"] = sum(eligible_e[p] * price(p) * factor(p) for p in ps)
            terms["om_cost_eur"] = model.c_om[d] if design else float(capacities[d].get("om_cost", 0.0))
            device_terms[d] = terms
        solar_heat = sum((heat("STC", p) - (frames[p].solar_to_ac if ac_active else 0.0)) * factor(p) for p in ps) if solar else 0.0
        raw = {d: {"grid": .004 * v["grid_heat_kwh"] + .1275 * v["grid_electricity_kwh"],
                   "direct": .006 * v["direct_heat_kwh"] + .060 * v["direct_electricity_kwh"]} for d, v in device_terms.items()}
        if design:
            annual.grant = pyo.Var(hp, ("grid", "direct"), domain=pyo.NonNegativeReals)
            for d, terms in device_terms.items():
                e_upper = sum(heat_bound(d) / cop(d, p) * factor(p) for p in ps)
                q_upper = heat_bound(d) * sum(factor(p) for p in ps)
                cost_lower = sum(min(0.0, price(p)) * heat_bound(d) / cop(d, p) * factor(p) for p in ps)
                cost_upper = sum(max(0.0, price(p)) * heat_bound(d) / cop(d, p) * factor(p) for p in ps)
                payable_cost = _positive_cost(annual, "positive_grid_cost_" + d, terms["grid_cost_eur"], cost_lower, cost_upper)
                for s in ("grid", "direct"):
                    annual.constraints.add(annual.grant[d, s] <= raw[d][s])
                annual.constraints.add(annual.grant[d, "grid"] <= .092 * (terms["grid_heat_kwh"] - terms["grid_electricity_kwh"]))
                annual.constraints.add(annual.grant[d, "direct"] <= .03 * terms["direct_heat_kwh"])
                annual.constraints.add(annual.grant[d, "grid"] <= .90 * payable_cost)
                annual.constraints.add(sum(annual.grant[d, s] for s in ("grid", "direct")) <= payable_cost + terms["om_cost_eur"])
                if min(cop(d, p) for p in ps) < 2.5:
                    gate = pyo.Var(domain=pyo.Binary)
                    annual.add_component("jaz_eligible_" + d, gate)
                    q = sum(terms[s + "_heat_kwh"] for s in ("grid", "direct", "unfunded"))
                    e = sum(terms[s + "_electricity_kwh"] for s in ("grid", "direct", "unfunded"))
                    annual.constraints.add(q >= 2.5 * e - 2.5 * e_upper * (1 - gate))
                    annual.constraints.add(sum(annual.grant[d, s] for s in ("grid", "direct")) <= (.004 * q_upper + .1275 * e_upper + .03 * q_upper) * gate)
            annual.credit = pyo.Expression(expr=sum(annual.grant[d, s] for d in hp for s in ("grid", "direct")) + .01 * solar_heat)
        else:
            # The annual settlement applies all caps to weighted cluster totals later.
            annual.credit = pyo.Expression(expr=sum(raw[d][s] for d in hp for s in ("grid", "direct")) + .01 * solar_heat)
        summaries[y] = {"devices": device_terms, "solar_heat_kwh": solar_heat,
                        "provisional_grant_eur": sum(raw[d][s] for d in hp for s in ("grid", "direct")) + .01 * solar_heat,
                        "model_credit_eur": annual.credit}
    m4._summaries = summaries
    if design:
        points = sorted(int(y) for y in model.support_years)
        i, horizon = float(param["interest_rate"]), int(param["observation_time"])
        npv = 0.0
        for y in years:
            end = min(OPERATING_FUNDING_YEARS, horizon, next((v for v in points if v > y), horizon))
            npv += m4.annual[y].credit * sum((1 + i) ** (-(k + 1)) for k in range(y, end))
        m4.annual_credit = pyo.Expression(expr=npv * capital_recovery_factor(i, horizon))
    else:
        m4.credit = pyo.Expression(expr=m4.annual[int(year)].credit)


def operating_funding_results(model):
    """Unrounded quantities; no independent report files are generated."""
    if not hasattr(model, "operating_funding"):
        return {}
    return {y: {"devices": {d: {k: float(pyo.value(v)) for k, v in terms.items()} for d, terms in summary["devices"].items()},
                "solar_heat_kwh": float(pyo.value(summary["solar_heat_kwh"])),
                "provisional_grant_eur": float(pyo.value(summary["provisional_grant_eur"])),
                "model_credit_eur": float(pyo.value(summary["model_credit_eur"]))}
            for y, summary in model.operating_funding._summaries.items()}


def annual_operating_payment(cluster_results, weights):
    """Annual M4 settlement with per-HP JAZ, rate, 90%-electricity and OPEX caps."""
    devices, solar, provisional = {}, 0.0, 0.0
    for c, result in cluster_results.items():
        v = result.get("operating_funding", {})
        w = float(weights[c])
        solar += w * v.get("solar_heat_kwh", 0.0)
        provisional += w * v.get("provisional_grant_eur", 0.0)
        for d, terms in v.get("devices", {}).items():
            dest = devices.setdefault(d, {})
            for key, value in terms.items():
                # Fixed annual O&M is not multiplied by cluster occurrence weights.
                if key == "om_cost_eur":
                    dest[key] = float(value)
                else:
                    dest[key] = dest.get(key, 0.0) + w * float(value)
    paid = {}
    for d, v in devices.items():
        q = sum(v[s + "_heat_kwh"] for s in ("grid", "direct", "unfunded"))
        e = sum(v[s + "_electricity_kwh"] for s in ("grid", "direct", "unfunded"))
        jaz = q / e if e > 1e-9 else None
        raw_g = max(0.0, .004 * v["grid_heat_kwh"] + .1275 * v["grid_electricity_kwh"])
        raw_r = max(0.0, .006 * v["direct_heat_kwh"] + .060 * v["direct_electricity_kwh"])
        g = min(raw_g, .092 * max(0.0, v["grid_heat_kwh"] - v["grid_electricity_kwh"]), .90 * max(0.0, v["grid_cost_eur"]))
        r = min(raw_r, .03 * max(0.0, v["direct_heat_kwh"]))
        limits = []
        if g < raw_g - 1e-7:
            rate_cap = .092 * max(0.0, v["grid_heat_kwh"] - v["grid_electricity_kwh"])
            cost_cap = .90 * max(0.0, v["grid_cost_eur"])
            if rate_cap <= cost_cap + 1e-7:
                limits.append("9.2 ct/kWh source heat")
            if cost_cap <= rate_cap + 1e-7:
                limits.append("90% grid electricity costs")
        if r < raw_r - 1e-7:
            limits.append("direct renewable rate")
        total = g + r
        opex = max(0.0, v["grid_cost_eur"]) + max(0.0, v["om_cost_eur"])
        if total > opex:
            scale = opex / total
            g, r, total = g * scale, r * scale, opex
            limits.append("modelled operating costs")
        if jaz is None or jaz < 2.5 - 1e-9:
            g = r = total = 0.0
            if jaz is not None:
                limits.append("annual JAZ below 2.5")
        grid_jaz = v["grid_heat_kwh"] / v["grid_electricity_kwh"] if v["grid_electricity_kwh"] > 1e-9 else None
        direct_jaz = v["direct_heat_kwh"] / v["direct_electricity_kwh"] if v["direct_electricity_kwh"] > 1e-9 else None
        paid[d] = dict(v, annual_jaz=jaz, grid_jaz=grid_jaz, direct_jaz=direct_jaz, provisional_grant_eur=raw_g + raw_r,
                       grid_grant_eur=g, direct_grant_eur=r, paid_grant_eur=total, binding_caps=limits)
    final = sum(v["paid_grant_eur"] for v in paid.values()) + .01 * max(0.0, solar)
    return dict(devices=paid, solar_heat_kwh=solar, solar_grant_eur=.01 * max(0.0, solar),
                provisional_grant_eur=provisional, paid_grant_eur=final,
                correction_eur=provisional - final)


def settle_operating_funding(data, year):
    """Replace provisional cluster credits once; never rerun dispatch for settlement."""
    results = data.resultsOptimization[year]
    if not all(v is not None for v in results.values()):
        return None
    final = annual_operating_payment(results, data.clusterWeights)
    for c, result in results.items():
        v = result.get("operating_funding")
        if v is None:
            continue
        payment = .01 * max(0.0, v["solar_heat_kwh"])
        for d, terms in v["devices"].items():
            raw = .004 * terms["grid_heat_kwh"] + .1275 * terms["grid_electricity_kwh"] + .006 * terms["direct_heat_kwh"] + .060 * terms["direct_electricity_kwh"]
            annual_raw = final["devices"][d]["provisional_grant_eur"]
            payment += raw * final["devices"][d]["paid_grant_eur"] / annual_raw if annual_raw > 0 else 0.0
        # Restore the previous settlement first, allowing safe repeated KPI evaluation.
        result["Cost_total"] -= v.get("annual_settlement_correction_eur", 0.0)
        correction = v["provisional_grant_eur"] - payment
        result["Cost_total"] += correction
        v.update(paid_grant_eur=payment, annual_settlement_correction_eur=correction)
    return final


def design_operating_payments(model, param):
    """Settle actual dispatch even when the selected objective is CO2, not costs."""
    summaries = operating_funding_results(model)
    payments = {y: annual_operating_payment({0: {"operating_funding": v}}, {0: 1.0})
                for y, v in summaries.items()}
    points = sorted(int(y) for y in model.support_years)
    i, horizon = float(param["interest_rate"]), int(param["observation_time"])
    npv = 0.0
    for y, payment in payments.items():
        end = min(OPERATING_FUNDING_YEARS, horizon, next((v for v in points if v > y), horizon))
        npv += payment["paid_grant_eur"] * sum((1 + i) ** (-(k + 1)) for k in range(y, end))
    return payments, npv * capital_recovery_factor(i, horizon)
