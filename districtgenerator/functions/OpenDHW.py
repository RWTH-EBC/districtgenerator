# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import math
import statistics
import random
import scipy
from scipy.stats import beta
import matplotlib.dates as mdates

"""
This is the script that stores all function of the DHWcalc package.
It is not meant to be executed on its own, but rather a toolbox for building
small scripts. Examples are given in OpenDHW/Examples.

OpenDHW is mostly built on Pandas, a good introduction is given here:
https://pandas.pydata.org/pandas-docs/stable/user_guide/10min.html
https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html

OpenDHW_Utilities stores a few other functions that do not generate DHW 
Timeseries directly, like the StorageLoad Function.
"""

# RWTH colours
rwth_blue = "#00549F"
rwth_red = "#CC071E"
# sns.set_style("white")
sns.set_context("paper")

# --- Constants ---
rho = 980 / 1000  # kg/L for Water (at 60°C? at 10°C its = 1)
cp = 4180  # J/kgK


def import_from_dhwcalc(s_step, daylight_saving, categories,
                        mean_drawoff_vol_per_day=200, max_flowrate=1200):
    """
    DHWcalc yields Volume Flow TimeSeries (in Liters per hour).

    :param  s_step:                     int:    resolution of file in seconds
    :param  categories:                 int:    either '1' or '4'
    :param  mean_drawoff_vol_per_day:   int:    daily water demand in Liters
    :param  daylight_saving:            Bool:   apply daylight saving or not
    :param  max_flowrate:               int:    maximum water flowrate in L/h

    :return timeseries_df:              df:     dataframe that holds the data
    """

    if daylight_saving:
        ds_string = 'ds'
    else:
        ds_string = 'nods'

    # --- DHWcalc result files, saved in the OpenDHW Package
    dhw_file = "{vol}L_{s_step}min_{cats}cat_sf_{ds}_max{max_flow}.txt".format(
        vol=mean_drawoff_vol_per_day,
        s_step=int(s_step / 60),
        cats=categories,
        ds=ds_string,
        max_flow=max_flowrate,
    )

    dhw_profile = Path.cwd().parent / "DHWcalc_Files" / dhw_file

    assert dhw_profile.exists(), 'No DHWcalc File for the selected ' \
                                 'parameters: {}'.format(dhw_file)

    # Flowrate in Liter per Hour in each Step
    water_LperH = [int(word.strip('\n')) for word in
                   open(dhw_profile).readlines()]  # L/h each step

    date_range = pd.date_range(start='2019-01-01', end='2020-01-01',
                               freq=str(s_step) + 'S')
    date_range = date_range[:-1]

    # make dataframe
    timeseries_df = pd.DataFrame(water_LperH, index=date_range, columns=[
        'Water_LperH'])

    timeseries_df['Water_L'] = timeseries_df['Water_LperH'] / 3600 * s_step
    timeseries_df['method'] = 'DHWcalc'
    timeseries_df['mean_drawoff_vol_per_day'] = mean_drawoff_vol_per_day
    timeseries_df['categories'] = categories
    timeseries_df['initial_day'] = 0
    timeseries_df['weekend_weekday_factor'] = 1.2
    timeseries_df['sdtdev_drawoff_vol_per_day'] = mean_drawoff_vol_per_day / 4

    if categories == 1:
        mean_vol_per_drawoff = 8  # constant DHWcalc 1 category
        timeseries_df['mean_vol_per_drawoff'] = 8

        mean_drawoff_flow_rate_LperH = mean_vol_per_drawoff * 3600 / s_step
        timeseries_df[
            'mean_drawoff_flow_rate_LperH'] = mean_drawoff_flow_rate_LperH

        sdt_dev_drawoff_flow_rate = mean_drawoff_flow_rate_LperH / 4  # in L/h
        timeseries_df[
            'sdtdev_drawoff_flow_rate_LperH'] = sdt_dev_drawoff_flow_rate

        mean_no_drawoffs_per_day \
            = mean_drawoff_vol_per_day / mean_vol_per_drawoff
        timeseries_df['mean_no_drawoffs_per_day'] = mean_no_drawoffs_per_day

    return timeseries_df


def generate_dhw_profile(s_step, categories, mean_drawoff_vol_per_day, occupancy, holidays, building_type,  weekend_weekday_factor, initial_day=0):
    """
    Generates a DHW profile. The generation is split up in different
    functions and generally follows the methodology described in the DHWcalc
    paper from Uni Kassel.

    1)  Load some data for the drawoff categories (cats_df).
    2)  Generate a yearly probability profile
    3)  Generate Drawoffs and distribute them randomly into the probability
        profile p_norm_integral.
    4)  Add some additionally stats to the dataframe.

    :param s_step:                      int:    timestep width in seconds.
    :param categories:                  int:    1 or 4 (see DHWcalc)
    :param weekend_weekday_factor:      int:    taken from DHWcalc
    :param mean_drawoff_vol_per_day:    int:    function of number of people in
                                                the house of floor area.
    :param initial_day:                 int:    0:Mon - 1:Tues ... 6:Sun
    :return: timeseries_df              df:     dataframe with all timeseries
    """

    mean_drawoff_vol_per_day *= occupancy

    # --- holds statistic info about the drawoffs
    cats_df = get_data_drawoff_categories(
        s_step=s_step,
        categories=categories,
        mean_drawoff_vol_per_day=mean_drawoff_vol_per_day,
        building_type=building_type
    )

    # --- deterministic function
    timeseries_df = generate_yearly_probability_profile(
        s_step=s_step,
        weekend_weekday_factor=weekend_weekday_factor,
        holidays=holidays,
        initial_day=0,
        building_type=building_type
    )

    # --- empty drawoffs list, will be filled afterwards
    timeseries_df['Water_LperH'] = [0] * int(365 * 24 * 3600 / s_step)

    # --- for each category, generate and distribute drawoffs.
    for i in range(len(cats_df)):
        timeseries_df = generate_and_distribute_drawoffs(
            timeseries_df=timeseries_df,
            cats_series=cats_df.iloc[i],
        )

    # --- add some additional stats
    timeseries_df['Water_L'] = timeseries_df['Water_LperH'] / 3600 * s_step
    timeseries_df['method'] = 'OpenDHW'
    timeseries_df['categories'] = categories
    timeseries_df['initial_day'] = initial_day
    timeseries_df['weekend_weekday_factor'] = weekend_weekday_factor
    timeseries_df['mean_drawoff_vol_per_day'] = mean_drawoff_vol_per_day

    return timeseries_df


def get_data_drawoff_categories(s_step, categories, mean_drawoff_vol_per_day, building_type):
    """
    Get some data for each drawoff category. If only one category is chosen,
    a simplified datafarme is returned.

    :param s_step:                      int:    seconds in a timestep. f.e 900
    :param categories: int: 1 or 4, 1: short laod (washing hands, etc.), 2: medium load (dish-washer, etc.), 3: bath, 4:shower (see DHWcalc)
    :param mean_drawoff_vol_per_day:    int:    volume per day used in house
    :return: cats_df:                   df:     Categores Data
    """
    if building_type in {"SFH", "TH", "MFH", "AB"}:

        if categories == 4:
            cats_data_60 = {'mean_flow_rate_per_drawoff_LperH': [60, 360, 840, 480],
                            'drawoff_duration_min': [1, 1, 10, 5],
                            'portion': [0.14, 0.36, 0.1, 0.4],
                            'stddev_flow_rate_per_drawoff_LperH': [120, 120, 12, 24],
                            'min_flow_rate_per_drawoff_LperH': [1, 1, 1, 1]
                            }

            cats_df = pd.DataFrame(data=cats_data_60)
            # sort by duration distributes long drawoff types first.
            cats_df.sort_values(by=['drawoff_duration_min'], ascending=False,
                                inplace=True)

        elif categories == 1:
            cats_data_60 = {'mean_flow_rate_per_drawoff_LperH': [480],
                            'drawoff_duration_min': [1],
                            'portion': [1],
                            'stddev_flow_rate_per_drawoff_LperH': [120],
                            'min_flow_rate_per_drawoff_LperH': [6]
                            }

            cats_df = pd.DataFrame(data=cats_data_60)
        else:
            raise Exception('unkown number of categories')

    # if DHWcalc uses 4 categories with a timestep other than 60s,
    # the drawoffs data has to be altered.
    if s_step != 60:
        cats_df['drawoff_duration_min_old'] = cats_df['drawoff_duration_min']

        cats_df['drawoff_duration_min'] = int(s_step / 60)

        cats_df['conversion_factor'] = cats_df['drawoff_duration_min'] / \
                                       cats_df['drawoff_duration_min_old']

        cats_df['mean_flow_rate_per_drawoff_LperH'] \
            = cats_df['mean_flow_rate_per_drawoff_LperH'] / cats_df[
            'conversion_factor']
        cats_df['stddev_flow_rate_per_drawoff_LperH'] = \
            cats_df['stddev_flow_rate_per_drawoff_LperH'] / cats_df[
                'conversion_factor']

    # add more data to the category dataframe.
    cats_df['mean_vol_per_drawoff'] = \
        cats_df['mean_flow_rate_per_drawoff_LperH'] \
        / 60 * cats_df['drawoff_duration_min']

    cats_df['mean_vol_per_day'] = mean_drawoff_vol_per_day * cats_df['portion']

    cats_df['mean_vol_per_year'] = cats_df['mean_vol_per_day'] * 365

    cats_df['mean_no_drawoffs_per_day'] = \
        cats_df['mean_vol_per_day'] / cats_df['mean_vol_per_drawoff']

    cats_df['mean_no_drawoffs_per_year'] = \
        cats_df['mean_no_drawoffs_per_day'] * 365

    # add max flow rate: Max(1200, highest category mean flow rate)
    cats_df['max_flow_rate_per_drawoff_LperH'] \
        = max(cats_df['mean_flow_rate_per_drawoff_LperH'].max(), 1200)

    return cats_df


def generate_daily_probability_step_function(mode, s_step, save_fig=False,
                                             test_concentrated_ps=False):
    """
    Generates probabilities for a day with 6 periods. Corresponds to the mode
    "step function for weekdays and weekends" in DHWcalc and uses the same
    standard values. Each Day starts at 0:00. Steps in hours. Sum of steps
    has to be 24. Sum of probabilities has to be 1.

    :param test_concentrated_ps:    bool:   different probabilities,
                                            very concentrated in the morning
    :param mode:                    string: weekday or weekend day
    :param s_step:                  int:    seconds within a timestep
    :param save_fig:                Bool:   plot the probability distribution
    :return: p_day                  list:   distribution for one day.
    """

    # todo: add profiles for non-residential buildings, no more heavy periods
    #  in the morning and evening? different for every industry type? more
    #  during the night?

    if s_step <= 1800:
        if mode == 'weekday':
            steps_and_ps = [(6.5, 0.01), (1, 0.5), (4.5, 0.06), (1, 0.16),
                            (5, 0.06), (4, 0.2), (2, 0.01)]

        elif mode == 'weekend':
            steps_and_ps = [(7, 0.02), (2, 0.475), (6, 0.071), (2, 0.237),
                            (3, 0.036), (3, 0.143), (1, 0.018)]

        else:
            raise Exception('Unknown Mode. Please Choose "Weekday" or '
                            '"Weekend".')
    else:
        # no more half-hourly steps
        if mode == 'weekday':
            steps_and_ps = [(7, 0.01), (1, 0.5), (4, 0.06), (1, 0.16),
                            (5, 0.06), (4, 0.2), (2, 0.01)]

        elif mode == 'weekend':
            steps_and_ps = [(7, 0.02), (2, 0.475), (6, 0.071), (2, 0.237),
                            (3, 0.036), (3, 0.143), (1, 0.018)]

        else:
            raise Exception('Unknown Mode. Please Choose "Weekday" or '
                            '"Weekend".')

    if test_concentrated_ps:
        # just as a test, if p is very concentrated, only 2 hours in the morning
        steps_and_ps = [(7, 0), (2, 1), (15, 0)]

    steps = [tup[0] for tup in steps_and_ps]
    ps = [tup[1] for tup in steps_and_ps]

    assert sum(steps) == 24
    assert sum(ps) == 1

    p_day = []

    for tup in steps_and_ps:
        p_lst = [tup[1] for _ in range(int(tup[0] * 3600 / s_step))]
        p_day.extend(p_lst)

    # check if length of daily intervals fits into the stepwidth.
    assert len(p_day) == 24 * 3600 / s_step

    if save_fig:
        fig, ax = plt.subplots()
        plt.plot(p_day)
        plt.show()
        dir_output = Path.cwd() / "plots"
        dir_output.mkdir(exist_ok=True)
        fname = "Daily_Probability_Profile_{}S_{}".format(s_step, mode)
        fig.savefig(dir_output / (fname + '.pdf'))
        fig.savefig(dir_output / (fname + '.svg'))
        fig.savefig(dir_output / (fname + '.png'))

    return p_day


def generate_yearly_probability_profile(s_step, weekend_weekday_factor,building_type, holidays,
                                        initial_day=0):
    """
    generate a summed yearly probability profile. The whole function is
    deterministic. The same inputs always produce the same outputs.

    1)  Probabilities for weekdays and weekend-days are loaded (p_we, p_wd).
    2)  Probability of weekend-days is increased relative to weekdays (shift).
    3)  Based on an initial day, the yearly probability distribution (p_final)
        is generated. The seasonal influence is modelled by a sine-function.
    4)  p_final is normalized and integrated. The sum over the year is thus
        equal to 1 (p_norm_integral).

    :param s_step:                  int:    seconds in a timestep
    :param weekend_weekday_factor:  float:  shift probabilities towards weekend
    :param initial_day:             int:    Mon: 0 ... Sun: 6
    :return: timeseries_df:         df:     df that holds the yearly profile
    """

    # load daily probabilities (deterministic)
    p_we = generate_daily_probability_step_function(
        mode='weekend',
        s_step=s_step
    )

    p_wd = generate_daily_probability_step_function(
        mode='weekday',
        s_step=s_step
    )

    # shift towards weekend (deterministic)
    p_wd_weighted, p_we_weighted, av_p_week_weighted = shift_weekend_weekday(
        p_weekday=p_wd,
        p_weekend=p_we,
        factor=weekend_weekday_factor
    )

    # yearly curve (deterministic)
    p_final = generate_yearly_probabilities(
        initial_day=initial_day,
        p_weekend=p_we_weighted,
        p_weekday=p_wd_weighted,
        s_step=s_step
    )

    # sum and normalize to range between 0 and 1.
    p_norm_integral = normalize_and_sum_list(lst=p_final)

    # make timeseries dataframe and append the final list
    date_range = pd.date_range(start='2019-01-01', end='2020-01-01',
                               freq=str(s_step) + 's')
    date_range = date_range[:-1]

    timeseries_df = pd.DataFrame(index=date_range,
                                 data={'p_norm_integral': p_norm_integral})

    return timeseries_df


def shift_weekend_weekday(p_weekday, p_weekend, factor=1.2):
    """
    Shifts the probabilities between the weekday list and the weekend list by a
    defined factor. If the factor is bigger than 1, the probability on the
    weekend is increased. If its smaller than 1, the probability on the
    weekend is decreased.

    :param p_weekday:   list:   probabilities for 1 day of the week [0...1]
    :param p_weekend:   list:   probabilities for 1 day of the weekend [0...1]
    :param factor:      float:  factor to shift the probabilities between
                                weekdays and weekend-days
    :return:
    """

    p_wd_factor = 1 / (5 / 7 + factor * 2 / 7)
    p_we_factor = 1 / (1 / factor * 5 / 7 + 2 / 7)

    assert p_wd_factor * 5 / 7 + p_we_factor * 2 / 7 == 1

    p_wd_weighted = [p * p_we_factor for p in p_weekday]
    p_we_weighted = [p * p_we_factor for p in p_weekend]

    av_p_wd_weighted = statistics.mean(p_wd_weighted)
    av_p_we_weighted = statistics.mean(p_we_weighted)

    av_p_week_weighted = av_p_wd_weighted * 5 / 7 + av_p_we_weighted * 2 / 7

    return p_wd_weighted, p_we_weighted, av_p_week_weighted


def generate_yearly_probabilities(initial_day, p_weekend, p_weekday,
                                  s_step, plot_p_yearly=False):
    """
    Takes the probabilities of a weekday and a weekendday and generates a
    list of yearly probabilities by adding a seasonal probability factor.
    The seasonal factor is a sine-function, like in DHWcalc.

    :param initial_day:     int:    0: Mon, 1: Tue, 2: Wed, 3: Thur, 4: Fri,
                                    5 : Sat, 6 : Sun
    :param p_weekend:       list:   probabilities of a weekend day
    :param p_weekday:       list:   probabilities of a weekday
    :param s_step:          int:    seconds within a timestep
    :param plot_p_yearly:   bool:   plot the yearly probabilities

    :return: p_final:       list:   probabilities of a full year
    """

    p_final = []
    timesteps_day = int(24 * 3600 / s_step)

    for day in range(365):

        # Is the current day on a weekend?
        if (day + initial_day) % 7 >= 5:
            p_day = p_weekend
        else:
            p_day = p_weekday

        # Compute seasonal factor
        arg = math.pi * (2 / 365 * day - 1 / 4)
        probability_season = 1 + 0.1 * np.cos(arg)

        for step in range(timesteps_day):
            probability = p_day[step] * probability_season
            p_final.append(probability)

    if plot_p_yearly:
        fig, ax = plt.subplots()
        plt.plot(p_final)
        plt.show()
        dir_output = Path.cwd() / "plots"
        dir_output.mkdir(exist_ok=True)
        fname = "Yearly_Probability_Profile_{}initalday_{}S".format(
            initial_day, s_step)
        fig.savefig(dir_output / (fname + '.pdf'))
        fig.savefig(dir_output / (fname + '.svg'))
        fig.savefig(dir_output / (fname + '.png'))

    return p_final


def normalize_and_sum_list(lst, save_fig=False):
    """
    takes a list and normalizes it based on the sum of all list elements.
    then generates a new list based on the current sum of each list entry.

    :param lst:                 list:   input list
    :param save_fig:            bool:   plot the output list
    :return: lst_norm_integral: list    output list
    """

    sum_lst = sum(lst)
    lst_norm = [float(i) / sum_lst for i in lst]

    current_sum = 0
    lst_norm_integral = []

    for entry in lst_norm:
        current_sum += entry
        lst_norm_integral.append(current_sum)

    if save_fig:
        fig, ax = plt.subplots()
        plt.plot(lst_norm_integral)
        plt.show()
        dir_output = Path.cwd() / "plots"
        dir_output.mkdir(exist_ok=True)
        fname = "Normed_and_summed_probability_profile"
        fig.savefig(dir_output / (fname + '.pdf'))
        fig.savefig(dir_output / (fname + '.svg'))
        fig.savefig(dir_output / (fname + '.png'))

    return lst_norm_integral


def generate_and_distribute_drawoffs(timeseries_df, cats_series):
    """
    generate and distribute drawoffs

    :param      timeseries_df:          df:     holds the timeseries
    :param      cats_series:            series: constants for a category
    """

    # --- compute how many timesteps the drawoff occupies. some take more than 1
    s_step = int(timeseries_df.index.freqstr[:-1])
    drawoff_duration = cats_series['drawoff_duration_min'] * 60
    drawoff_steps = int(drawoff_duration / s_step)

    # --- generate drawoffs until V_max is reached ---
    V_curr = 0
    V_max = cats_series['mean_vol_per_year']
    drawoffs = []  # L/h

    while V_curr <= V_max:
        drawoff = generate_single_drawoff_inside_boundaries(cats_series, s_step)
        drawoffs.append(drawoff)

        drawoff_L = drawoff / 3600 * s_step * drawoff_steps
        V_curr += drawoff_L

    # --- generate a probability for each drawoff ---
    p_norm_integral = list(timeseries_df['p_norm_integral'])
    min_rand = min(p_norm_integral)
    max_rand = max(p_norm_integral)
    p_drawoffs = [random.uniform(min_rand, max_rand) for _ in range(
        len(drawoffs))]

    # --- sort both lists for the distribution algorithm ---
    p_drawoffs.sort()
    p_norm_integral.sort()

    # --- distribute drawoffs ---
    water_LperH_cat = [0] * int(365 * 24 * 3600 / s_step)
    water_LperH = list(timeseries_df['Water_LperH'])
    max_flow_rate = cats_series['max_flow_rate_per_drawoff_LperH']

    # counter for the drawoffs
    drawoff_count = 0

    # loop p_norm_integral and place drawoffs:
    for time_step, p_current_sum in enumerate(p_norm_integral):

        # dont place drawoff if timestep has already reached the max flowrate
        if water_LperH[time_step] >= max_flow_rate:
            continue

        # if all drawoffs are palced, break the loop.
        if drawoff_count >= len(drawoffs):
            break

        # if the looping of p_norm_integral results in surpassing the
        # probability of the chosen drawoff, that drawoff might be placed at
        # that timestep!
        while p_drawoffs[drawoff_count] < p_current_sum:

            # if the drawoff event occupies more than one timestep,
            # a list (drawoffs_time_step_delta) is placed, rather than a
            # single number.
            drawoff = drawoffs[drawoff_count]
            drawoffs_time_step_delta = [drawoff] * drawoff_steps

            # boolean, to count the drawoff events, but not the timesteps
            # occupied by all drawoffs. this is needed when the drawoff
            # event occupies more than one timestep.
            drawoff_occured = True

            for i in range(drawoff_steps):

                # if the added drawoff surpasses the max flowrate in any of
                # the possible timesteps it would occupy, it should not occur!
                if water_LperH[time_step + i] + \
                        drawoffs_time_step_delta[i] > max_flow_rate:
                    drawoff_occured = False
                    break

            if drawoff_occured:
                for i in range(drawoff_steps):
                    # if the added drawoff would not surpass the max
                    # flowrate, add it to both return lists! for the
                    # category, and for the whole list.
                    water_LperH[time_step + i] \
                        += drawoffs_time_step_delta[i]
                    water_LperH_cat[time_step + i] \
                        += drawoffs_time_step_delta[i]

                drawoff_count += 1

            else:
                break  # break the while loop.

            if drawoff_count >= len(drawoffs):
                break

    # update the sum of all categories
    timeseries_df['Water_LperH'] = water_LperH

    # write the drawoff list for the current category to the df
    cat_id = int(cats_series['mean_flow_rate_per_drawoff_LperH'])
    timeseries_df['Water_LperH_cat{}'.format(cat_id)] = water_LperH_cat

    # compute the amount of water for the category
    timeseries_df['Water_L_cat{}'.format(cat_id)] = \
        timeseries_df['Water_LperH_cat{}'.format(cat_id)] * s_step / 3600

    return timeseries_df


def generate_single_drawoff_inside_boundaries(cats_series, s_step):
    """
    From the data of one category, generate a drawoff inside the defined
    boundaries, similar to DHWcalc.

    :param cats_series: df:     pandas series that holds the drawoff data
    :param s_step:      int:    seconds in a timestep
    :return: drawoff:   int:    drawoff eevnt in L/h
    """

    # --- get mean and stddev from series ---
    mu = cats_series['mean_flow_rate_per_drawoff_LperH']  # in L/h
    sig = cats_series['stddev_flow_rate_per_drawoff_LperH']  # in L/h

    # --- generate drawoff
    drawoff = random.gauss(mu, sig)

    # --- get min and max allowed flowrate
    max_drawoff_flow_rate = cats_series['max_flow_rate_per_drawoff_LperH']
    min_drawoff_flow_rate = cats_series['min_flow_rate_per_drawoff_LperH']

    # --- set boundaries for drawoff
    low_lim = max(float(mu - 2 * sig), min_drawoff_flow_rate)
    up_lim = min(float(mu + 2 * sig), max_drawoff_flow_rate)

    # --- if drawoff is outside boundaries, generate it again until its inside.
    while drawoff < low_lim or drawoff > up_lim:
        drawoff = random.gauss(mu, sig)

    # --- DHWcalc uses a fixed flow rate step width rather than floats.
    if s_step == 60:
        flow_rate_step = 6
    else:
        flow_rate_step = 1
    drawoff = flow_rate_step * round(drawoff / flow_rate_step)

    return drawoff  # in L/h


def compute_heat(timeseries_df, temp_dT=35):
    """
    Add heat columns to the timeseries

    :param timeseries_df:   df:     Pandas Dataframe with all the timeseries
    :param temp_dT:         int:    temperature difference between freshwater
                                    and average DHW outlet temperature. F.e.
                                    35°C.

    :return: timeseries_df: df:     Dataframe with added 'Heat' Column
    """

    timeseries_df['Heat_W'] = \
        timeseries_df['Water_LperH'] / 3600 * rho * cp * temp_dT
    timeseries_df['Heat_kW'] = timeseries_df['Heat_W'] / 1000

    s_step = int(timeseries_df.index.freqstr[:-1])
    timeseries_df['Heat_J'] = timeseries_df['Heat_W'] * s_step
    timeseries_df['Heat_kWh'] = timeseries_df['Heat_J'] / (3600 * 1000)

    return timeseries_df


def draw_lineplot(timeseries_df, plot_var='water', start_plot='2019-02-01',
                  end_plot='2019-02-05', save_fig=False):
    """
    Plots the timeseries for a given timedelta in a year.

    :param timeseries_df:   df:     Dataframe that holds the timeseries.
    :param plot_var:        str:    choose to plot Water or Heat series.
    :param start_plot:      str:    start date of the plot. F.e. 2019-01-01
    :param end_plot:        str:    end date of the plot. F.e. 2019-01-07
    :param save_fig:        bool:   decide to save plots as pdf
    """

    fig, ax1 = plt.subplots()
    fig.tight_layout()

    if plot_var == 'water':
        # make subset of dataframe for plotting
        plot_df = timeseries_df[['Water_LperH', 'mean_drawoff_vol_per_day']]

        ax1 = sns.lineplot(ax=ax1, data=plot_df[start_plot:end_plot],
                           linewidth=1.0, palette=[rwth_blue, rwth_red])

        ax1.legend(loc="upper left")

        title_str = make_title_str(timeseries_df=timeseries_df)
        ax1.set_title(title_str)

    if plot_var == 'heat':
        # make subset of dataframe for plotting
        plot_df = timeseries_df[['Heat_W']]

        ax1 = sns.lineplot(ax=ax1, data=plot_df[start_plot:end_plot],
                           linewidth=1.0, palette=[rwth_red])

        ax1.legend(loc="upper left")

        # compute some stats for figure title.
        # todo: add to make_title_str function for Heat plots.
        max_water_flow = timeseries_df['Water_LperH'].max()  # in L/h
        s_step = timeseries_df.index.freqstr
        method = timeseries_df['method'][0]

        plt.title('Heat Time-series from {}, timestep = {}\n'
                  'with a Peak of {:.1f} L/h'.format(method, s_step,
                                                     max_water_flow))

    # set the x axis ticks
    # https://matplotlib.org/3.1.1/gallery/ticks_and_spines/date_concise_formatter.html
    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax1.xaxis.set_major_locator(locator)
    ax1.xaxis.set_major_formatter(formatter)

    plt.show()

    if save_fig:
        method = timeseries_df['method'][0]
        s_step = get_s_step(timeseries_df)
        vol_per_day = timeseries_df['mean_drawoff_vol_per_day'][0]
        cats = timeseries_df['categories'][0]

        dir_output = Path.cwd() / "plots"
        dir_output.mkdir(exist_ok=True)

        fname = "Lineplot_{}_{}S_{}LperDay_{}cats".format(
            method, s_step, vol_per_day, cats)
        fig.savefig(dir_output / (fname + '.pdf'))
        fig.savefig(dir_output / (fname + '.svg'))
        fig.savefig(dir_output / (fname + '.png'))


def draw_histplot(timeseries_df, extra_kde=False, save_fig=False):
    """
    Takes a DHW profile and plots a histogram with some stats in the title

    :param save_fig:        bool:   save the figure
    :param timeseries_df:   df:     Dataframe that holds the water timeseries
    :param extra_kde:       bool:   plot a detailed kde plot behind the main
                                    histogram.
    """

    # get non-zero values of the profile
    drawoffs_df = get_drawoffs(timeseries_df=timeseries_df, remove_cats=False)

    cats = timeseries_df['categories'][0]
    if cats == 1:
        drawoffs_df = drawoffs_df['Water_LperH']

    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()

    # https://seaborn.pydata.org/generated/seaborn.histplot.html
    sns.histplot(data=drawoffs_df, ax=ax2, stat='count', kde=True,
                 kde_kws={'bw_adjust': 1})

    if extra_kde:
        # https://seaborn.pydata.org/generated/seaborn.kdeplot.html
        sns.kdeplot(data=drawoffs_df, ax=ax1, alpha=.05, bw_adjust=0.05,
                    legend=False, color='r')

    # title
    title_str = make_title_str(timeseries_df=timeseries_df)
    ax1.set_title(title_str)

    plt.show()

    if save_fig:
        method = timeseries_df['method'][0]
        s_step = get_s_step(timeseries_df)
        vol_per_day = timeseries_df['mean_drawoff_vol_per_day'][0]
        cats = timeseries_df['categories'][0]

        dir_output = Path.cwd() / "plots"
        dir_output.mkdir(exist_ok=True)

        fname = "Histplot_{}_{}S_{}LperDay_{}cats".format(
            method, s_step, vol_per_day, cats)
        fig.savefig(dir_output / (fname + '.pdf'))
        fig.savefig(dir_output / (fname + '.svg'))
        fig.savefig(dir_output / (fname + '.png'))


def draw_detailed_histplot(timeseries_df):
    """
    https://towardsdatascience.com/advanced-histogram-using-python-bceae288e715
    plot to further analyse timeseries with 1 drawoff category.
    """
    cats = timeseries_df['categories'][0]
    method = timeseries_df['method'][0]

    if cats == 1 and method == 'DHWcalc':

        # create bin values
        mean = timeseries_df['mean_drawoff_flow_rate_LperH'][0]
        sdtdev = timeseries_df['sdtdev_drawoff_flow_rate_LperH'][0]
        non_zero_min = timeseries_df[timeseries_df['Water_LperH'] > 0][
            'Water_LperH'].min()  # smallest entry that is not 0.

        bin_values = [non_zero_min,
                      mean - 2 * sdtdev,
                      mean - sdtdev,
                      mean,
                      mean + sdtdev,
                      mean + 2 * sdtdev,
                      timeseries_df['Water_LperH'].max()]
        bin_values = list(set(bin_values))  # remove double entries
        bin_values.sort()  # bins have to be sorted

        # get non-zero values of the profile
        drawoffs = timeseries_df[timeseries_df['Water_LperH'] != 0][
            'Water_LperH']

        # Plot the Histogram from the random data
        fig, (ax) = plt.subplots()

        # counts: count of data ponts for each bin/column in the histogram
        # bins: bin edge/range values
        # patches: list of Patch objects. each Patch object contains a
        # Rectangle object. e.g. Rectangle(xy=(-2.51953, 0), width=0.501013,
        # height=3, angle=0)
        counts, bins, patches = ax.hist(drawoffs, bins=bin_values,
                                        edgecolor='black')

        # Set the ticks to be at the edges of the bins.
        ax.set_xticks(bins.round(2))

        # Set the graph title and axes titles
        plt.ylabel('Count')
        plt.xlabel('Flowrate L/h')

        # Calculate bar centre to display the count of data points and %
        bin_x_centers = 0.5 * np.diff(bins) + bins[:-1]
        bin_y_centers = ax.get_yticks()[1] * 0.25

        # Display the the count of data points and % for each bar in histogram
        for i in range(len(bins) - 1):
            bin_label = "{0:,}".format(counts[i]) + "  ({0:.2f}%)".format(
                (counts[i] / counts.sum()) * 100)
            plt.text(bin_x_centers[i], bin_y_centers, bin_label, rotation=90,
                     rotation_mode='anchor')

        # Display the graph
        plt.show()

    else:
        print('detailed histplot is only meant to analyse DHWcalc timeseries '
              'with one drawoff category.')


def add_additional_runs(timeseries_df, total_runs=5, dir_output=None):
    """
    method to add more runs to a timeseries dataframe with the same input
    parameters as the original timeseries.

    :param timeseries_df:
    :param total_runs:
    :param dir_output:
    :return:
    """
    added_runs = total_runs - 1

    s_step = int(timeseries_df.index.freqstr[:-1])
    mean_drawoff_vol_per_day = timeseries_df['mean_drawoff_vol_per_day'][0]
    weekend_weekday_factor = timeseries_df['weekend_weekday_factor'][0]
    initial_day = timeseries_df['initial_day'][0]
    method = timeseries_df['method'][0]
    categories = timeseries_df['categories'][0]

    if method == 'OpenDHW':

        for run in range(added_runs):
            extra_timeseries_df = generate_dhw_profile(
                s_step=s_step,
                categories=categories,
                weekend_weekday_factor=weekend_weekday_factor,
                mean_drawoff_vol_per_day=mean_drawoff_vol_per_day,
                initial_day=initial_day
            )

            additional_profile = extra_timeseries_df['Water_LperH']
            timeseries_df['Water_LperH_' + str(run)] = additional_profile

    elif method == 'DHWcalc':

        raise Exception('adding multiple plots for DWHcalc is not so useful, '
                        'as DHWcalc does not work with a random seed!')

    if dir_output is not None:
        # set a name for the file
        save_name = "{}_{}runs_{}L_{}min.csv".format(
            method, total_runs, mean_drawoff_vol_per_day, int(s_step / 60))

        # make a directory. if it already exists, no problem, just use it
        dir_output.mkdir(exist_ok=True)

        # save the dataframe in the folder as a csv with the chosen name
        timeseries_df.to_csv(dir_output / save_name)

    return timeseries_df


def get_drawoffs(timeseries_df, remove_cats=True):
    """
    get sorted drawoff events from a timeseries Dataframe.
    """

    # only columns that contain 'Water_LperH'
    cols_bool_str = timeseries_df.columns.str.contains('Water_LperH')
    water_LperH_df = timeseries_df.loc[:, cols_bool_str]

    if remove_cats:
        # not columns that contain 'cat'
        cols_bool_str2 = water_LperH_df.columns.str.contains('cat')
        cols_bool_str2 = [not i for i in cols_bool_str2]
        water_LperH_df = water_LperH_df.loc[:, cols_bool_str2]

    drawoffs_df = water_LperH_df.reset_index(drop=True)

    for col_name in drawoffs_df.columns:
        #  From each column, get only values != 0.
        drawoffs_series = water_LperH_df[water_LperH_df[col_name] != 0][
            col_name]
        drawoffs_lst = list(drawoffs_series)

        #  fill zero-values with NaN's
        empty_cells_len = len(timeseries_df) - len(drawoffs_lst)
        empty_cells_lst = [np.nan] * empty_cells_len
        drawoffs_lst.extend(empty_cells_lst)
        drawoffs_lst.sort()

        # append to the drawoff dataframe
        drawoffs_df[col_name] = drawoffs_lst

    # Drop rows that have only NaN's as values
    drawoffs_df = drawoffs_df.dropna(how='all')

    return drawoffs_df


def plot_multiple_runs(timeseries_df, plot_demands_overlay=True,
                       start_plot='2019-02-01', end_plot='2019-02-02',
                       plot_hist=True, plot_kde=True):
    """
    This function should only be used when the 'add_additional_runs' function
    has been used before.

    :param timeseries_df:           df:     dataframe with timesieries
    :param plot_demands_overlay:    bool:   plot lineplot
    :param start_plot:              str:    start date
    :param end_plot:                str:    end date
    :param plot_hist:               bool:   plot histogram
    :param plot_kde:                bool:   plot kde plot
    """

    drawoffs_df = get_drawoffs(timeseries_df=timeseries_df)

    if plot_demands_overlay:
        fig, ax1 = plt.subplots()
        fig.tight_layout()

        # only columns that contain 'Water_LperH'
        cols_bool_str = timeseries_df.columns.str.contains('Water_LperH')
        water_LperH_df = timeseries_df.loc[:, cols_bool_str]

        # not columns that contrain 'cats'
        cols_bool_str2 = water_LperH_df.columns.str.contains('cat')
        cols_bool_str2 = [not i for i in cols_bool_str2]
        water_LperH_df = water_LperH_df.loc[:, cols_bool_str2]

        ax1 = sns.lineplot(ax=ax1, data=water_LperH_df[start_plot:end_plot],
                           linewidth=0.5, legend=False)

        # set beautiful x axis ticks for datetime
        # https://matplotlib.org/3.1.1/gallery/ticks_and_spines/date_concise_formatter.html
        locator = mdates.AutoDateLocator()
        formatter = mdates.ConciseDateFormatter(locator)
        ax1.xaxis.set_major_locator(locator)
        ax1.xaxis.set_major_formatter(formatter)

        plt.show()

    if plot_hist:
        sns.histplot(data=drawoffs_df, kde=False, element="step", fill=False,
                     stat='count', line_kws={'alpha': 0.8, 'linewidth': 0.9})

        title_str = make_title_str(timeseries_df)
        plt.title(title_str)

        plt.show()

    if plot_kde:
        sns.kdeplot(data=drawoffs_df, bw_adjust=0.1, alpha=0.5, fill=False,
                    linewidth=0.5, legend=True)

        title_str = make_title_str(timeseries_df)
        plt.title(title_str)

        plt.show()


def plot_multiple_timeseries(timeseries_lst, col_part='Water_LperH',
                             plot_demands_overlay=True,
                             start_plot='2019-02-01', end_plot='2019-02-02',
                             plot_hist=True, plot_kde=True):
    """
    plots multiple timeseries given in a list. better than "plot multiple runs?"

    :param timeseries_lst:          list:   list with timeseries dataframes
    :param col_part:                str:    string that matches colum names
                                            which should be plotted
    :param plot_demands_overlay:    bool:   plot lineplot of all dfs
    :param start_plot:              str:    start of lineplot
    :param end_plot:                str:    end of lineplot
    :param plot_hist:               bool:   plot histogram
    :param plot_kde:                bool:   plot kde plot
    :return:
    """

    # get the index column of one timeseries and use it to make a plot df.
    plot_index = timeseries_lst[0].index
    plot_df = pd.DataFrame(index=plot_index)

    for i, df in enumerate(timeseries_lst):
        # get colum names
        cols_LperH = [name for name in list(df.columns) if col_part in name]

        # the timeseries_df should only have 1 column that matches the
        # desired string. more are not implemented yet
        assert len(cols_LperH) <= 1

        # fill the plot dataframe with the matching column
        plot_df[i] = df[cols_LperH]

    drawoffs_df = get_drawoffs(timeseries_df=plot_df)

    if plot_demands_overlay:
        fig, ax1 = plt.subplots()
        fig.tight_layout()

        ax1 = sns.lineplot(ax=ax1, data=plot_df[start_plot:end_plot],
                           linewidth=0.5, legend=True)

        # set beautiful x axis ticks for datetime
        # https://matplotlib.org/3.1.1/gallery/ticks_and_spines/date_concise_formatter.html
        locator = mdates.AutoDateLocator()
        formatter = mdates.ConciseDateFormatter(locator)
        ax1.xaxis.set_major_locator(locator)
        ax1.xaxis.set_major_formatter(formatter)

        plt.show()

    if plot_hist:
        sns.histplot(data=drawoffs_df, kde=True, element="step", fill=False,
                     stat='count', line_kws={'alpha': 0.8, 'linewidth': 0.9})
        plt.show()

    if plot_kde:
        sns.kdeplot(data=drawoffs_df, bw_adjust=0.1, alpha=0.5, fill=False,
                    linewidth=0.5, legend=True)
        plt.show()


def compare_generators(timeseries_df_1, timeseries_df_2,
                       start_plot='2019-03-01', end_plot='2019-03-08',
                       plot_date_slice=True, plot_distribution=True,
                       plot_detailed_distribution=True, save_fig=False):
    """
    Compares two timeseries by plotting them next to each other with the same
    x and y axis limits.

    :param timeseries_df_1:             df:     first timeseries dataframe
    :param timeseries_df_2:             df:     second timeseries dataframe
    :param start_plot:                  str:    date, f.e. 2019-03-01
    :param end_plot:                    str:    date, f.e. 2019-03-08
    :param plot_date_slice:             bool:   plot lineplots
    :param plot_distribution:           bool:   plot histplots
    :param plot_detailed_distribution:  bool:    plot detailed histplots
    :param save_fig:                    bool:   save the plot
    """

    cats_1 = timeseries_df_1['categories'][0]
    cats_2 = timeseries_df_2['categories'][0]
    if cats_1 or cats_2 == 1:
        print("detailed distribution is designed to compare timeseries with "
              "one drawoff category")
        plot_detailed_distribution = False

    # compute Stats for the title
    drawoffs_1 = timeseries_df_1[timeseries_df_1['Water_LperH'] != 0][
        'Water_LperH']

    drawoffs_2 = timeseries_df_2[timeseries_df_2['Water_LperH'] != 0][
        'Water_LperH']

    if plot_date_slice:

        # make dataframe for plotting with seaborn
        plot_df_1 = timeseries_df_1[['Water_LperH', 'mean_drawoff_vol_per_day']]
        plot_df_2 = timeseries_df_2[['Water_LperH', 'mean_drawoff_vol_per_day']]

        fig, (ax1, ax2) = plt.subplots(2, 1)
        fig.tight_layout()

        # First Subplot
        ax1 = sns.lineplot(ax=ax1, data=plot_df_1[start_plot:end_plot],
                           linewidth=1.0, palette=[rwth_blue, rwth_red])

        title_str_1 = make_title_str(timeseries_df=timeseries_df_1)
        ax1.set_title(title_str_1)

        ax1.legend(loc="upper left")

        # Second Subplot
        ax2 = sns.lineplot(ax=ax2, data=plot_df_2[start_plot:end_plot],
                           linewidth=1.0, palette=[rwth_blue, rwth_red])

        title_str_2 = make_title_str(timeseries_df=timeseries_df_2)
        ax2.set_title(title_str_2)

        ax2.legend(loc="upper left")

        # --- set both aes to the same y limit ---
        ymin1, ymax1 = ax1.get_ylim()
        ymin2, ymax2 = ax2.get_ylim()

        ymax_set = max(ymax1, ymax2)

        ax1.set_ylim(ymin1, ymax_set)
        ax2.set_ylim(ymin2, ymax_set)

        # --- beautiful x-ticks ---
        locator = mdates.AutoDateLocator()
        formatter = mdates.ConciseDateFormatter(locator)
        ax1.xaxis.set_major_locator(locator)
        ax1.xaxis.set_major_formatter(formatter)
        ax2.xaxis.set_major_locator(locator)
        ax2.xaxis.set_major_formatter(formatter)

        plt.show()

        if save_fig:
            dir_output = Path.cwd() / "plots"
            dir_output.mkdir(exist_ok=True)

            fname = "Timeseries_Comparison_Lineplot"
            fig.savefig(dir_output / (fname + '.pdf'))
            fig.savefig(dir_output / (fname + '.svg'))
            fig.savefig(dir_output / (fname + '.png'))

    if plot_distribution:
        # compute Jensen Shannon Distance
        distance = jensen_shannon_distance(q=timeseries_df_1['Water_LperH'],
                                           p=timeseries_df_2['Water_LperH'])

        fig, (ax1, ax2) = plt.subplots(2, 1)
        fig.tight_layout()

        # plot the distribution
        # https://seaborn.pydata.org/generated/seaborn.displot.html
        ax1 = sns.histplot(ax=ax1, data=drawoffs_1, kde=True)
        ax2 = sns.histplot(ax=ax2, data=drawoffs_2, kde=True)

        # --- Set titles and Labels ---
        title_str_1 = make_title_str(timeseries_df=timeseries_df_1)
        title_str_1 = 'Jensen Shannon Distance = {:.4f} \n'.format(distance) \
                      + title_str_1
        ax1.set_title(title_str_1)

        ax1.set_ylabel('Count in a Year')
        ax1.set_xlabel('Flowrate [L/h]')

        title_str_2 = make_title_str(timeseries_df=timeseries_df_2)
        ax2.set_title(title_str_2)

        ax2.set_ylabel('Count in a Year')
        ax2.set_xlabel('Flowrate [L/h]')

        # --- set both axes to the same y limit ---
        ymin1, ymax1 = ax1.get_ylim()
        ymin2, ymax2 = ax2.get_ylim()

        ymax_set = max(ymax1, ymax2)

        ax1.set_ylim(ymin1, ymax_set)
        ax2.set_ylim(ymin2, ymax_set)

        # --- set both axes to the same x limit ---
        xmin1, xmax1 = ax1.get_xlim()
        xmin2, xmax2 = ax2.get_xlim()

        xmax_set = max(xmax1, xmax2)

        ax1.set_xlim(xmin1, xmax_set)
        ax2.set_xlim(xmin2, xmax_set)

        plt.show()

        if save_fig:
            dir_output = Path.cwd() / "plots"
            dir_output.mkdir(exist_ok=True)

            fname = "Timeseries_Comparison_Histplot"
            fig.savefig(dir_output / (fname + '.pdf'))
            fig.savefig(dir_output / (fname + '.svg'))
            fig.savefig(dir_output / (fname + '.png'))

    if plot_detailed_distribution:

        # https://towardsdatascience.com/advanced-histogram-using-python-bceae288e715

        # compute Jensen Shannon Distance
        distance = jensen_shannon_distance(q=timeseries_df_1['Water_LperH'],
                                           p=timeseries_df_2['Water_LperH'])

        fig, axes = plt.subplots(2, 1)
        ax1 = axes[0]
        ax2 = axes[1]
        fig.tight_layout()

        drawoffs_lst = [drawoffs_1, drawoffs_2]

        # create bin values
        mean1 = timeseries_df_1['mean_drawoff_flow_rate_LperH'][0]
        sdtdev1 = timeseries_df_1['sdtdev_drawoff_flow_rate_LperH'][0]
        non_zero_min1 = timeseries_df_1[timeseries_df_1['Water_LperH'] > 0][
            'Water_LperH'].min()  # smallest entry that is not 0.

        bin_values1 = [non_zero_min1,
                       mean1 - 2 * sdtdev1,
                       mean1 - sdtdev1,
                       mean1,
                       mean1 + sdtdev1,
                       mean1 + 2 * sdtdev1,
                       timeseries_df_1['Water_LperH'].max()]
        bin_values1 = list(set(bin_values1))  # remove double entries
        bin_values1.sort()  # bins have to be sorted

        mean2 = timeseries_df_2['mean_drawoff_flow_rate_LperH'][0]
        sdtdev2 = timeseries_df_2['sdtdev_drawoff_flow_rate_LperH'][0]
        non_zero_min2 = timeseries_df_2[timeseries_df_2['Water_LperH'] > 0][
            'Water_LperH'].min()  # smallest entry that is not 0.

        bin_values2 = [non_zero_min2,
                       mean2 - 2 * sdtdev2,
                       mean2 - sdtdev2,
                       mean2,
                       mean2 + sdtdev2,
                       mean2 + 2 * sdtdev2,
                       timeseries_df_2['Water_LperH'].max()]
        bin_values2 = list(set(bin_values2))  # remove double entries
        bin_values2.sort()  # bins have to be sorted

        bin_values_lst = [bin_values1, bin_values2]

        for sub_i, drawoffs_i in enumerate(drawoffs_lst):

            ax = axes[sub_i]

            counts, bins, patches = ax.hist(
                drawoffs_i, bins=bin_values_lst[sub_i], edgecolor='black')

            # Set the ticks to be at the edges of the bins.
            ax.set_xticks(bins.round(2))

            # Calculate bar centre to display the count of data points and %
            bin_x_centers = 0.1 * np.diff(bins) + bins[:-1]
            bin_y_centers = ax.get_yticks()[1] * 0.25

            # Display the the count of data points and % for each bar in hist
            for i in range(len(bins) - 1):
                bin_label = str(int(counts[i])) + "\n{0:.2f}%".format(
                    (counts[i] / counts.sum()) * 100)
                ax.text(bin_x_centers[i], bin_y_centers, bin_label, rotation=0)

        title_str_1 = make_title_str(timeseries_df=timeseries_df_1)
        title_str_1 = 'Jensen Shannon Distance = {:.4f} \n'.format(distance) \
                      + title_str_1
        ax1.set_title(title_str_1)

        ax1.set_ylabel('Count in a Year')

        title_str_2 = make_title_str(timeseries_df=timeseries_df_2)
        ax2.set_title(title_str_2)

        ax2.set_ylabel('Count in a Year')
        ax2.set_xlabel('Flowrate [L/h]')

        # --- set both aes to the same y limit ---
        ymin1, ymax1 = ax1.get_ylim()
        ymin2, ymax2 = ax2.get_ylim()

        ymax_set = max(ymax1, ymax2)

        ax1.set_ylim(ymin1, ymax_set)
        ax2.set_ylim(ymin2, ymax_set)

        plt.show()


def plot_three_histplots(timeseries_df_1, timeseries_df_2, timeseries_df_3):
    """
    Compares three timeseries by means of a triple subplot.
    :param timeseries_df_1:     df:   first time series
    :param timeseries_df_2:     df:   second time series
    :param timeseries_df_3:     df:   third time series

    """

    # compute Stats for the title
    drawoffs_1 = timeseries_df_1[timeseries_df_1['Water_LperH'] != 0][
        'Water_LperH']
    drawoffs_2 = timeseries_df_2[timeseries_df_2['Water_LperH'] != 0][
        'Water_LperH']
    drawoffs_3 = timeseries_df_3[timeseries_df_3['Water_LperH'] != 0][
        'Water_LperH']

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1)
    fig.tight_layout()

    # plot the distribution
    # https://seaborn.pydata.org/generated/seaborn.displot.html
    ax1 = sns.histplot(ax=ax1, data=drawoffs_1, kde=True)
    ax2 = sns.histplot(ax=ax2, data=drawoffs_2, kde=True)
    ax3 = sns.histplot(ax=ax3, data=drawoffs_3, kde=True)

    # --- Set titles and Labels ---
    title_str_1 = make_title_str(timeseries_df=timeseries_df_1)
    ax1.set_title(title_str_1)
    ax1.set_ylabel('Count in a Year')
    ax1.set_xlabel('Flowrate [L/h]')

    title_str_2 = make_title_str(timeseries_df=timeseries_df_2)
    ax2.set_title(title_str_2)
    ax2.set_ylabel('Count in a Year')
    ax2.set_xlabel('Flowrate [L/h]')

    title_str_3 = make_title_str(timeseries_df=timeseries_df_3)
    ax3.set_title(title_str_3)
    ax3.set_ylabel('Count in a Year')
    ax3.set_xlabel('Flowrate [L/h]')

    # --- set both axes to the same y limit ---
    ymin1, ymax1 = ax1.get_ylim()
    ymin2, ymax2 = ax2.get_ylim()
    ymin3, ymax3 = ax3.get_ylim()

    ymax_set = max(ymax1, ymax2, ymax3)

    ax1.set_ylim(ymin1, ymax_set)
    ax2.set_ylim(ymin2, ymax_set)
    ax3.set_ylim(ymin3, ymax_set)

    # --- set both axes to the same x limit ---
    xmin1, xmax1 = ax1.get_xlim()
    xmin2, xmax2 = ax2.get_xlim()
    xmin3, xmax3 = ax3.get_xlim()

    xmax_set = max(xmax1, xmax2, xmax3)

    ax1.set_xlim(xmin1, xmax_set)
    ax2.set_xlim(xmin2, xmax_set)
    ax3.set_xlim(xmin3, xmax_set)

    plt.show()


def jensen_shannon_distance(p, q):
    """
    method to compute the Jenson-Shannon Distance between two probability
    distributions. 0 indicates that the two distributions are the same,
    and 1 would indicate that they are nowhere similar.

    From https://medium.com/@sourcedexter/how-to-find-the-similarity-between-two-probability-distributions-using-python-a7546e90a08d
    """

    # convert the vectors into numpy arrays in case that they aren't
    p = np.array(p)
    q = np.array(q)

    # calculate m
    m = (p + q) / 2

    # compute Jensen Shannon Divergence
    divergence = (scipy.stats.entropy(p, m) + scipy.stats.entropy(q, m)) / 2

    # compute the Jensen Shannon Distance
    distance = np.sqrt(divergence)

    return round(distance, 4)


def get_s_step(timeseries_df):
    """
    get the seconds within a timestep from a pandas dataframe. When loading
    Dataframes from a csv, the index loses its 'freq' attribute. This is thus
    just a workaround when loading Timeseries from csv.
    """

    try:
        s_step = int(timeseries_df.index.freqstr[:-1])
        # todo: why doesnt this work for Dataframes loaded from a csv?

    except TypeError:

        steps = len(timeseries_df)
        secs_in_year = 8760 * 60 * 60
        s_step = secs_in_year / steps

        # check if s_step has no decimal points (should not be 60.01 f.e.)
        assert s_step % 1 == 0
        s_step = int(s_step)

    return s_step


def make_title_str(timeseries_df):
    """
    creates a title string based on the timeseries dataframe. The title
    string can then be used for a variety of plots.
    """

    # compute additional stats for title
    s_step = get_s_step(timeseries_df)
    yearly_water_demand = timeseries_df['Water_L'].sum()  # in L
    drawoffs = timeseries_df[timeseries_df['Water_LperH'] != 0]['Water_LperH']
    max_water_flow = timeseries_df['Water_LperH'].max()
    method = timeseries_df['method'][0]
    cats = timeseries_df['categories'][0]

    if cats == 1:
        method = "{} ({} cat)".format(method, cats)

        title_str = '{}, ∆t = {}, Yearly Demand = {:.1f} L \n' \
                    'No. Drawoffs = {}, Peak = {:.1f} L/h, ' \
                    'Mean = {:.1f} L/h, SdtDev = {:.1f} L/h'.format(
            method, s_step, yearly_water_demand, len(drawoffs), max_water_flow,
            drawoffs.mean(), drawoffs.std())

    else:  # f.e. four categories

        if 'OpenDHW' in method:

            method = "{} ({} cats)".format(method, cats)

            col_names = list(timeseries_df.columns)
            cols_LperH = [name for name in col_names if 'Water_L_' in name]
            water_LperH_df = timeseries_df[cols_LperH]

            cats_str = ''
            for col in cols_LperH:
                cat_sum = water_LperH_df[col].sum()
                cats_str += '{:.0f} L, '.format(cat_sum)
            cats_str = cats_str[:-2]

            title_str = f'{method}, ∆t = {s_step}, No. Drawoffs =' \
                        f' {len(drawoffs)}, Peak = {max_water_flow:.1f} L/h ' \
                        f'\n Yearly Demand = {yearly_water_demand:.0f} L (=' \
                        f' {cats_str})'

        elif 'DHWcalc' in method:

            method = "{} ({} cats)".format(method, cats)

            title_str = f"{method}, ∆t = {s_step}, No. Drawoffs =" \
                        f" {len(drawoffs)}, Peak = {max_water_flow:.1f} L/h " \
                        f"\n Yearly Demand = {yearly_water_demand:.0f} L"

        else:
            raise Exception("Unkown method, try 'OpenDHW' or 'DHWcalc'.")

    return title_str


def resample_water_series(timeseries_df, s_step_output):
    """
    Before resampling a dataframe, we have to choose which data has to be
    resampled in what way. some columns list constants, some list intensive
    properties (like L/h, kW) and some list extensive properties (Like
    Liters/kWh).
    Constants should stay the same, intensive properties should be averaged
    and extensive properties should be summed up.

    :param timeseries_df:       df:     dataframe that holds the timeseries
    :param s_step_output:       int:    desired output seconds in a timestep
    :return: timeseries_df_re:  df:     resampled dataframe
    """

    s_step_old = get_s_step(timeseries_df)
    conversion_factor = s_step_output / s_step_old

    if conversion_factor != 1:
        # separate constants from variables
        cols_consts = list(timeseries_df.columns[timeseries_df.nunique() <= 1])
        cols_vars = list(timeseries_df.columns[timeseries_df.nunique() > 1])

        # separate flows (intensive) from sums (extensive)
        cols_flows = [i for i in cols_vars if 'Lper' in i]
        cols_sums = [i for i in cols_vars if i not in cols_flows]

        # separate constants that change with the timestep (intensive
        # properties)
        cols_const_flows = [i for i in cols_consts if 'Lper' in i]
        cols_consts = [i for i in cols_consts if i not in cols_const_flows]

        # make new sub-dataframes
        timeseries_df_sum = timeseries_df[cols_sums]
        timeseries_df_flows = timeseries_df[cols_flows]
        timeseries_df_consts = timeseries_df[cols_consts]
        timeseries_df_const_flows = timeseries_df[cols_const_flows]

        # resample them according to their physical properties
        rule = str(s_step_output) + 's'
        timeseries_df_sum_re = timeseries_df_sum.resample(rule=rule).sum()
        timeseries_df_flows_re = timeseries_df_flows.resample(rule=rule).mean()

        # cut the dataframe with the constant variables and update the index
        resampled_index = timeseries_df_sum_re.index
        timeseries_df_consts_cut = timeseries_df_consts[0:len(resampled_index)]
        timeseries_df_consts_re \
            = timeseries_df_consts_cut.set_index(resampled_index)

        # update the constants that change with the timestep (intensive
        # properties) with the conversion factor
        timeseries_df_consts_flows_cut \
            = timeseries_df_const_flows[0:len(resampled_index)]
        timeseries_df_consts_flows_re \
            = timeseries_df_consts_flows_cut.set_index(resampled_index)
        timeseries_df_consts_flows_re \
            = timeseries_df_consts_flows_re / conversion_factor

        timeseries_df_re = pd.concat(
            [timeseries_df_flows_re, timeseries_df_sum_re,
             timeseries_df_consts_re, timeseries_df_consts_flows_re],
            axis=1)

        # add 'resampled' tag to method column
        timeseries_df_re['method'] = timeseries_df['method'].iloc[0] + ' (resampled)'

    else:
        timeseries_df_re = timeseries_df

    return timeseries_df_re


def reduce_no_drawoffs(timeseries_df):
    """
    for some reason, DHWcalc still yields less yearly drawoffs than OpenDHW.
    In case the yearly water demand is higher in an OpenDHW timeseries than
    the expected one, this function removes some randomly selected drawoffs
    events with a small flowrate to reduce the yearly water demand until its
    just under the expected one and simultaneously decreasing the number of
    drawoffs.

    :param timeseries_df:           df: input dataframe
    :return: timeseries_df_cleaned: df  output dataframe
    """

    # get the expected yearly water demand
    expected_yearly_water = timeseries_df['mean_drawoff_vol_per_day'][0] * 365
    actual_yearly_water = timeseries_df['Water_L'].sum()

    if expected_yearly_water < actual_yearly_water:

        # select a cut off flow rate
        max_flow_rate = timeseries_df['Water_LperH'].max()
        min_flow_rate = \
            timeseries_df[timeseries_df['Water_LperH'] != 0].min()[
                'Water_LperH']
        cut_off_flow_rate = max(min_flow_rate * 5, max_flow_rate / 200)

        # shuffle df so random days are selected when iterated over.
        timeseries_df_shuffled = timeseries_df.sample(frac=1).reset_index(
            drop=False)

        # loop over the shuffled timeseries and set some vales to 0.
        for i in timeseries_df_shuffled.index:

            curr_sum = timeseries_df_shuffled['Water_L'].sum()
            if curr_sum <= expected_yearly_water:
                break

            curr_flow_rate = timeseries_df_shuffled.loc[i, 'Water_LperH']
            if curr_flow_rate != 0 and curr_flow_rate < cut_off_flow_rate:
                timeseries_df_shuffled.loc[i, 'Water_L'] = 0
                timeseries_df_shuffled.loc[i, 'Water_LperH'] = 0

        # un-shuffle df
        timeseries_df_shuffled = timeseries_df_shuffled.set_index('index')
        timeseries_df_cleaned = timeseries_df_shuffled.sort_index()

    else:
        timeseries_df_cleaned = timeseries_df
        print('No drawoffs have neen reduced, as expected_yearly_water >= '
              'actual_yearly_water')

    return timeseries_df_cleaned
