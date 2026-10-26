"""Prepare electricity tariffs for the energy hub and decentralised 5G heat pumps.

The historical SMARD Germany/Luxembourg prices for 2025 supply ONLY the pattern
of cheap and expensive hours, including the absolute size of their fluctuations
in EUR2023/kWh. Future annual levels come from the configured PRICE_SUPPLY_EL_EH
series.

To separate the historical pattern from its price level, the module converts
the 2025 prices to EUR2023/kWh and subtracts their full-year mean. The resulting
hourly deviations have a mean of zero. For each economic support-year segment,
the configured annual prices of its represented years are discount-weighted to
obtain one effective reference level. Dynamic prices equal that level plus the
historical hourly deviations; static prices equal that level at every timestep.

This preserves the historical absolute fluctuation pattern as a scenario, not
as a forecast of actual future hourly prices. Within each year, only the
wholesale component varies over time. The hub and decentralised 5G heat pumps
share this purchase tariff. Dynamic hub exports receive the same wholesale
profile around REVENUE_FEED_IN_EL_EH, without subsidies or marketing fees.
Static hub exports use that reference level without hourly deviations.

CET means Central European Time, UTC+01:00. The included file has already been
converted from market clock time to fixed CET: summer hours are also expressed
in UTC+01:00, without switching to Central European Summer Time (UTC+02:00).
This provides a continuous hourly axis without daylight-saving clock gaps or
repeated clock labels, for mapping prices onto the TRY model time axis.
"""

from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / "data" / "electricity_prices" / "smard_de_lu_2025_cet.csv"


def load_reference_deviation(time_resolution):
    """Load the included file, convert once, centre and duration-average."""
    path = DEFAULT_PROFILE
    raw = path.read_bytes()
    frame = pd.read_csv(path)
    expected = pd.date_range("2025-01-01", periods=8760, freq="h")
    stamps = pd.DatetimeIndex(pd.to_datetime(frame["timestamp_cet"], errors="raise"))
    if not stamps.equals(expected):
        raise ValueError("Hub price file must contain all 8760 consecutive fixed-CET hours of 2025.")
    prices = pd.to_numeric(frame["day_ahead_eur2025_mwh"], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(prices).all():
        raise ValueError("Hub price file contains missing or non-finite prices.")
    step = float(time_resolution)
    if not np.isfinite(step) or step <= 0 or not np.isclose(31536000 / step, round(31536000 / step)):
        raise ValueError("Hub tariff time resolution must divide the 8760-hour reference year.")
    # Match the model's common EUR2023 price basis (VPI2023/VPI2025) and EUR/kWh
    # unit; otherwise historical deviations and annual reference prices cannot be added.
    real_prices = prices * (116.7 / 121.9) / 1000.0
    # Match the simulation timestep so each power value receives the price for
    # its own interval, rather than assuming the model always uses hourly steps.
    # Integrating the piecewise-constant source preserves duration-weighted means.
    edges = np.arange(round(31536000 / step) + 1, dtype=float) * step
    integral = np.r_[0.0, np.cumsum(real_prices) * 3600.0]
    resampled = np.diff(np.interp(edges, np.arange(8761) * 3600.0, integral)) / step
    # Keep only within-year fluctuations: the future annual price level comes
    # from the configured reference series, not from the historical 2025 mean.
    # Zero-mean deviations can be added without counting an annual level twice.
    deviation = resampled - resampled.mean()
    metadata = {
        "mode": "dynamic", "reference_year": 2025, "price_basis": "EUR2023/kWh, net",
        "source": "https://www.smard.de/page/home/topic-article/444/218954/hoechste-pv-einspeisung-in-jedem-quartal",
        "profile_file": str(path.resolve()), "profile_sha256": sha256(raw).hexdigest(),
        "source_mean_eur2025_mwh": float(prices.mean()),
        "time_axis": "8760 hours, fixed CET (UTC+01:00), synthetic TRY alignment",
        "transformation": "annual total hub reference price + centred real 2025 wholesale deviation",
        "network_costs": "existing 4000-hour reference, no separate annual peak charge",
        "clustering": "unchanged medoids and weights; no post-clustering price normalisation",
        "scope": "hub/5G purchase tariff; dynamic hub export at pure wholesale; ordinary building tariffs unchanged",
        "export_pricing": "wholesale annual mean + same hourly deviation; no subsidy or marketing fee; negative prices retained",
        "foresight_and_flow_constraints": "unchanged; not a rolling-horizon implementation",
    }
    return deviation, metadata


def effective_profile(annual_prices, years, rate, deviation):
    """Build a full-year price profile for one support-year segment.

    Discount-weight the annual prices at the consecutive year indices in years,
    then add the zero-mean historical deviations. Inputs and output use
    EUR2023/kWh. Example: level 0.20 plus [0, -0.06, 0.06] gives [0.20, 0.14, 0.26].
    """
    years = list(years)
    weights = np.power(1.0 + rate, -np.arange(len(years), dtype=float))
    level = np.dot(np.asarray(annual_prices)[years], weights) / weights.sum()
    # Fixed real deviations are identical in every year under the additive scenario.
    return level + deviation


def select_price_periods(profile, typedays, cluster_horizon):
    """Extract prices for periods already selected by weather clustering.
    """
    profile = np.asarray(profile, dtype=float)
    days = np.asarray(typedays)
    horizon = int(cluster_horizon)
    if horizon <= 0 or not np.isfinite(profile).all() or profile.ndim != 1:
        raise ValueError("Invalid hub price profile or cluster horizon.")
    if not np.equal(days, days.astype(int)).all() or (days < 0).any():
        raise ValueError("Hub price medoid indices must be non-negative integers.")
    if ((days.astype(int) + 1) * horizon > len(profile)).any():
        raise ValueError("Hub price medoid lies outside the reference year.")
    return np.asarray([profile[int(day) * horizon:(int(day) + 1) * horizon] for day in days])


def operation_prices(eco_data, cluster, steps, *, feed_in=False):
    """Return one price per timestep for the selected operating period.

    Static mode repeats the configured price; dynamic mode uses the selected
    period's prices. feed_in=True selects hub sale prices, not purchase prices.
    """
    scalar_key = "revenue_feed_in_el_eh" if feed_in else "price_supply_el_eh"
    profile_key = "revenue_feed_in_el_eh_cluster" if feed_in else "price_supply_el_eh_cluster"
    if eco_data.get("hub_electricity_price_mode", "static") == "static":
        return np.full(steps, eco_data[scalar_key], dtype=float)
    if profile_key not in eco_data:
        raise ValueError("Dynamic hub tariff requires prices mapped to the operation medoids.")
    prices = np.asarray(eco_data[profile_key][cluster], dtype=float)
    if prices.shape != (steps,) or not np.isfinite(prices).all():
        raise ValueError("Dynamic hub price period does not match the operation horizon.")
    return prices


def hub_import_cost(power, prices, dt_hours, watts=False):
    """Sum power x timestep duration x price to obtain electricity costs.

    Power is in kW, or W if watts=True; duration is in hours and prices in
    EUR/kWh. Works with numeric values and linear Pyomo expressions.
    """
    return dt_hours / (1000.0 if watts else 1.0) * sum(p * price for p, price in zip(power, prices))


def design_import_cost(model, param, year, dt_hours):
    """Calculate annual hub import costs for one support year in device sizing.

    Static mode uses annual energy x price. Dynamic mode sums timestep costs
    across representative periods, weighted by their occurrence counts.
    """
    if "price_supply_el_eh_profile" not in param:
        return model.from_el_grid_total[year] * param["price_supply_el_eh"][year]
    return sum(
        param["cluster_weights"][d] * hub_import_cost(
            (model.power["from_grid", year, d, t] for t in model.time_steps),
            param["price_supply_el_eh_profile"][year][d], dt_hours)
        for d in model.clusters)


def design_export_revenue(model, param, year, dt_hours):
    """Return hub export revenue, signed at negative prices, without subsidies/fees."""
    if "revenue_feed_in_el_eh_profile" not in param:
        return model.to_el_grid_total[year] * param["revenue_feed_in_el_eh"][year]
    return sum(
        param["cluster_weights"][d] * hub_import_cost(
            (model.power["to_grid", year, d, t] for t in model.time_steps),
            param["revenue_feed_in_el_eh_profile"][year][d], dt_hours)
        for d in model.clusters)
