"""
Saving and loading of generated demand profiles as CSV files.

Each building is stored in three files in the demands folder: hourly time series,
minutely DHW time series and static values such as design loads.
"""
import json
import os

import numpy as np
import pandas as pd


def save_profiles(name, elec, dhw, dhw_minutely, occ, gains, EV_carcharging_ondemand,
                           EV_carprofile, ev_capacity, ice_carprofile, nb_units,
                           nb_occ, heatload, bivalent, heatlimit, path, time_cfg,
                           individual_car_profiles=None):
    """
    Save profiles to csv. Used by the Datahandler and by worker processes.

    Parameters
    ----------
    name : string
        Unique building name.
    elec : list
        Hourly electricity demand in W.
    dhw : list
        Hourly domestic hot water demand in W.
    dhw_minutely : list
        Minutely domestic hot water demand in W.
    occ : list
        Hourly occupancy of persons.
    gains : list
        Hourly internal gains in W.
    EV_carcharging_ondemand : list
        Hourly on-demand EV charging profile in W.
    EV_carprofile : list
        Hourly electricity demand of EV in W.
    ev_capacity : list
        Battery capacities of EVs.
    ice_carprofile : list
        Hourly fuel consumption profile of ICE vehicles.
    nb_units : int
        Number of units (flats) in the building.
    nb_occ : list
        Number of occupants in the building.
    heatload : float
        Design heat load in W.
    bivalent : float
        Bivalent heat load in W.
    heatlimit : float
        Heat limit heat load in W.
    path : string
        Results path.
    time_cfg : dict
        Picklable subset of Datahandler.time (timeResolution, dataLength).
    individual_car_profiles : list, optional
        Per-vehicle profile data.

    Returns
    -------
    None.
    """

    os.makedirs(path, exist_ok=True)

    time_resolution = time_cfg["timeResolution"]
    time_horizon = time_cfg["dataLength"]
    num_timesteps = int(time_horizon / time_resolution)

    # timeseries data points
    ts_dict = {
        'timestep': np.arange(num_timesteps) * (time_resolution / 3600),  # Index-Column (hour of the year)
        'elec': elec,
        'dhw': dhw,
        'occ': occ,
        'gains': gains,
        'EV_carprofile': EV_carprofile,
        'EV_carcharging_ondemand': EV_carcharging_ondemand,
        'ice_carprofile': ice_carprofile
    }

    car_info_list = []
    # Prepare individual car profiles for saving
    if individual_car_profiles is not None:
        for i, car in enumerate(individual_car_profiles):
            car_info_list.append({
                "car_id": car.get('car_id'),
                "type": car.get("type"),
                "location": car.get("location"),
                "battery_capacity_wh": car.get("battery_capacity_wh")
            })
            # Create Dataframes for the individual car profiles
            if car['consumption_profile_wh'] is not None:
                ts_dict[f'EV_demand_car_{i}'] = car['consumption_profile_wh']
            if car['on_demand_charging_profile_w'] is not None:
                ts_dict[f'EV_charging_car_{i}'] = car['on_demand_charging_profile_w']
            if car['fuel_profile_l'] is not None:
                ts_dict[f'ICE_fuel_car_{i}'] = car['fuel_profile_l']
            if car['availability_profile'] is not None:
                ts_dict[f'Car_availability_car_{i}'] = car['availability_profile']

    df_ts = pd.DataFrame(ts_dict)
    df_ts.to_csv(
        os.path.join(path, f"{name}_timeseries.csv"),
        sep=';',
        index=False
    )

    # Singular Data points (static)
    static_dict = {
        'nb_units': [nb_units],
        'nb_occ': [json.dumps(list(nb_occ) if isinstance(nb_occ, (list, np.ndarray)) else [nb_occ])],
        'ev_capacity': [
            json.dumps(list(ev_capacity) if isinstance(ev_capacity, (list, np.ndarray)) else [ev_capacity])],
        'heatload': [heatload],
        'bivalent': [bivalent],
        'heatlimit': [heatlimit],
        'car_info': [json.dumps(car_info_list)]
    }

    df_static = pd.DataFrame(static_dict)
    df_static.to_csv(
        os.path.join(path, f"{name}_static.csv"),
        sep=';',
        index=False,
        float_format='%.3f'
    )

    # Minutely timeseries data points (currently only used for domestic hot water demand)
    ts_minutely_dict = {
        'timestep': np.arange(len(dhw_minutely)) * (1 / 60),  # Index-Column (hour of the year)
        'dhw_minutely': dhw_minutely
    }

    df_ts_minutely = pd.DataFrame(ts_minutely_dict)
    df_ts_minutely.to_csv(
        os.path.join(path, f"{name}_timeseries_minutely.csv"),
        sep=';',
        index=False
    )


def save_heating_profile(heat, cooling, name, path):
    """
    Save heating demand to csv. Standalone counterpart of
    Datahandler.saveHeatingProfile, usable inside a worker process.

    Parameters
    ----------
    heat : list
        Hourly heating demand in W.
    cooling : list
        Hourly cooling demand in W.
    name : string
        Unique building name.
    path : string
        Results path.

    Returns
    -------
    None.
    """
    ts_path = os.path.join(path, f"{name}_timeseries.csv")
    if os.path.exists(ts_path):
        df_ts = pd.read_csv(ts_path, sep=';')
    else:
        df_ts = pd.DataFrame()

    df_ts['heating'] = heat
    df_ts['cooling'] = cooling
    df_ts.to_csv(ts_path,
                 index=False,
                 sep=';',
                 float_format='%.3f')


def load_profiles(name, path, time_cfg, gen_cars=True):
    """
    Load profiles from csv. Standalone counterpart of
    Datahandler.loadProfiles, usable inside a worker process.

    Parameters
    ----------
    name : string
        Unique building name.
    path : string
        Results path.
    time_cfg : dict
        Picklable subset of Datahandler.time (timeResolution, dataLength).
    gen_cars : bool, optional
        True to load car profiles, False to return zero profiles.

    Returns
    -------
    tuple
        Same layout as Datahandler.loadProfiles.
    """
    ts_path = os.path.join(path, f"{name}_timeseries.csv")
    static_path = os.path.join(path, f"{name}_static.csv")
    ts_minutely_path = os.path.join(path, f"{name}_timeseries_minutely.csv")

    error_msg = "Before loading profiles, please make sure to generate them first by setting calcUserProfiles to True in the generateDistrictComplete function. If you have already generated the profiles, please check if the files exist in the specified path."

    if not os.path.exists(ts_path): raise FileNotFoundError(f"Timeseries file not found: {ts_path} \n{error_msg}")
    if not os.path.exists(static_path): raise FileNotFoundError(f"Static file not found: {static_path} \n{error_msg}")
    if not os.path.exists(ts_minutely_path): raise FileNotFoundError(f"Minutely timeseries file not found: {ts_minutely_path} \n{error_msg}")

    df_ts = pd.read_csv(ts_path, sep=";")
    df_static = pd.read_csv(static_path, sep=";")
    df_ts_minutely = pd.read_csv(ts_minutely_path, sep=";")

    elec = df_ts['elec'].to_numpy()
    dhw = df_ts['dhw'].to_numpy()
    occ = df_ts['occ'].to_numpy()
    gains = df_ts['gains'].to_numpy()

    dhw_minutely = df_ts_minutely['dhw_minutely'].to_numpy()

    nb_flats = int(df_static['nb_units'].iloc[0])
    nb_main_rooms = nb_flats
    heatload = float(df_static['heatload'].iloc[0])
    bivalent = float(df_static['bivalent'].iloc[0])
    heatlimit = float(df_static['heatlimit'].iloc[0])

    nb_occ = np.array(json.loads(df_static['nb_occ'].iloc[0]))
    ev_capacity = np.array(json.loads(df_static['ev_capacity'].iloc[0]))
    car_info_list = json.loads(df_static['car_info'].iloc[0])

    # Load car profiles
    individual_car_profiles = []
    if gen_cars:  # Only load car profiles if cars are supposed to be generated
        EV_carprofile = df_ts['EV_carprofile'].to_numpy()
        EV_carcharging_ondemand = df_ts['EV_carcharging_ondemand'].to_numpy()
        ice_carprofile = df_ts['ice_carprofile'].to_numpy()

        for i, info in enumerate(car_info_list):
            car_profile = {
                'car_id': info['car_id'],
                'type': info['type'],
                'location': info['location'],
                'battery_capacity_wh': info['battery_capacity_wh'],
                'consumption_profile_wh': df_ts[
                    f'EV_demand_car_{i}'].to_numpy() if f'EV_demand_car_{i}' in df_ts.columns and not df_ts[
                    f'EV_demand_car_{i}'].isnull().all() else None,
                'on_demand_charging_profile_w': df_ts[
                    f'EV_charging_car_{i}'].to_numpy() if f'EV_charging_car_{i}' in df_ts.columns and not df_ts[
                    f'EV_charging_car_{i}'].isnull().all() else None,
                'fuel_profile_l': df_ts[
                    f'ICE_fuel_car_{i}'].to_numpy() if f'ICE_fuel_car_{i}' in df_ts.columns and not df_ts[
                    f'ICE_fuel_car_{i}'].isnull().all() else None,
                'availability_profile': df_ts[
                    f'Car_availability_car_{i}'].to_numpy() if f'Car_availability_car_{i}' in df_ts.columns and not
                df_ts[f'Car_availability_car_{i}'].isnull().all() else None
            }
            individual_car_profiles.append(car_profile)
    else:
        # if no cars are generated, return zero profiles
        length = int(time_cfg["dataLength"] / time_cfg["timeResolution"])
        EV_carprofile = np.zeros(length)
        EV_carcharging_ondemand = np.zeros(length)
        ice_carprofile = np.zeros(length)

    return (elec, dhw, dhw_minutely, occ, gains, EV_carcharging_ondemand, EV_carprofile, ice_carprofile,
            nb_flats, nb_main_rooms, nb_occ, ev_capacity, heatload, bivalent, heatlimit, individual_car_profiles)


def load_heating_profiles(name, path):
    """
    Load heating/cooling profiles from csv. Standalone counterpart of
    Datahandler.loadHeatingProfiles, usable inside a worker process.

    Parameters
    ----------
    name : string
        Unique building name.
    path : string
        Results path.

    Returns
    -------
    tuple of np.ndarray
        (heat, cooling)
    """
    ts_path = os.path.join(path, f"{name}_timeseries.csv")
    df_ts = pd.read_csv(ts_path, sep=";")
    return df_ts['heating'].to_numpy(), df_ts['cooling'].to_numpy()
