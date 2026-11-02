"""
Price and CO2 paths over the observation period.
"""


def calculate_eco_data_per_simulated_year(eco_data):
    """Calculate representative energy prices and CO2 factors for simulated years.

    The optimization does not simulate every year of the analysis period.
    Instead, each selected year represents a group of consecutive years.
    This function replaces the annual values in each group with one value
    that the optimization can use for that representative year.

    For example, an analysis period of 10 years with selected years ``[0, 5]``
    has two groups: year 0 represents years 0–4, and year 5 represents years
    5–9. These numbers count from the start of the analysis, not calendar years.

    Parameters
    ----------
    eco_data : dict
        Economic data containing ``observation_time``, ``interpolation_points``,
        ``interest_rate`` and ``num_interpolation_points``.

    Returns
    -------
    dict of int to dict
        One economic-data dictionary per representative year.
    """
    ecoData = eco_data
    simulated_years = eco_data["interpolation_points"]
    observation_time = eco_data["observation_time"]

    # Separate analysis settings from the annual price and emission-factor lists.
    single_value_keys = ['num_interpolation_points','interpolation_points', 'observation_time','interest_rate', 'optimization_focus']
    ecoData = {k: v for k, v in eco_data.copy().items() if k not in single_value_keys}

    # Emission factors use ordinary averages; monetary values use discount weights.
    undiscounted_keys = set()
    co2_keys = set([k for k in ecoData.keys() if 'co2' in k.lower()])
    undiscounted_keys.update(co2_keys)

    # Assign each year to the preceding representative year, e.g. 0: [0, 1], 2: [2, 3].
    year_segments = {k: [] for k in simulated_years}


    for i in range(observation_time): # 0,1,...,observation_time-1
        for j in range(len(simulated_years)):
            if simulated_years[j] == simulated_years[-1]:
                if i >= simulated_years[j]:
                    year_segments[simulated_years[j]].append(i)
                    break
            if simulated_years[j] <= i < simulated_years[j+1]:
                year_segments[simulated_years[j]].append(i)
                break

    all_sim_ecoData = {}

    interest_factor = eco_data['interest_rate']
    q = 1 + interest_factor
    if q < 1:
        print(f"Warning: interest factor q < 1 (q={q}). If not wanted check ecoData interest rate.")

    for year in simulated_years:
        relevant_years = year_segments[year]
        all_sim_ecoData[year] = {}  # Initialize dictionary for this year

        n = len(relevant_years)

        # Sum the discount weights so a constant annual price stays unchanged.
        if q!=1:
            denom = sum(1/(q**idx) for idx in range(n))
        elif q==1:
            denom = n

        for key in ecoData.keys():
            subset_values = [ecoData[key][i] for i in relevant_years if i < len(ecoData[key])]

            # Combine only the annual values belonging to this representative year.
            if key in undiscounted_keys:
                pv = sum(subset_values)  # CO2 emissions are not discounted.
                effective_price = pv / n  # Average emission factor over the group.
            else:
                # idx starts at zero within this group, rather than the analysis year.
                pv = sum(val / (q ** idx) for idx, val in enumerate(subset_values))
                effective_price = pv/denom  # Constant price with the same discounted cost.

            all_sim_ecoData[year][key] = effective_price

        # Retain the analysis settings alongside the representative prices and factors.
        for key in single_value_keys:
            all_sim_ecoData[year][key] = eco_data[key]

    return all_sim_ecoData
