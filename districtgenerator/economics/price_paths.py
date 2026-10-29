"""
Price and CO2 paths over the observation period.
"""


def calculate_eco_data_per_simulated_year(eco_data):
    """
    Effective prices and CO2 factors for each simulated year of the observation period.

    The observation period is divided into segments that start at the interpolation points.
    Prices of a segment are discounted to an effective yearly value with the interest rate.
    CO2 factors are averaged without discounting.

    Parameters
    ----------
    eco_data : dict
        Economic data of the Datahandler with yearly price paths.

    Returns
    -------
    dict
        Effective economic data per simulated year.
    """
    ecoData = eco_data
    simulated_years = eco_data["interpolation_points"]
    observation_time = eco_data["observation_time"]

    # select the relevant subset of ecoData for optimization
    single_value_keys = ['num_interpolation_points','interpolation_points', 'observation_time','interest_rate', 'optimization_focus']
    ecoData = {k: v for k, v in eco_data.copy().items() if k not in single_value_keys}

    # All keys that have co2 in name are undiscounted
    undiscounted_keys = set()
    co2_keys = set([k for k in ecoData.keys() if 'co2' in k.lower()])
    undiscounted_keys.update(co2_keys)

    # Identify the years that belong to each interpolation segment
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

        if q!=1:
            denom = sum(1/(q**idx) for idx in range(n))
        elif q==1:
            denom = n

        for key in ecoData.keys():
            subset_values = [ecoData[key][i] for i in relevant_years if i < len(ecoData[key])]

            # Calculate present value (PV) of the subset values
            if key in undiscounted_keys:
                pv = sum(subset_values)  # No discounting for these keys
                effective_price = pv / n  # For undiscounted values, the effective value is just the average over the years in the segment
            else:
                pv = sum(val / (q ** idx) for idx, val in enumerate(subset_values))
                effective_price = pv/denom

            all_sim_ecoData[year][key] = effective_price

        # Add the values in single_value_keys to each year's ecoData
        for key in single_value_keys:
            all_sim_ecoData[year][key] = eco_data[key]

    return all_sim_ecoData
