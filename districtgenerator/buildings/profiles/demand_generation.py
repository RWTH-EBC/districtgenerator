"""
Generation of the demand profiles of all buildings, sequentially, in threads or in processes.
"""
import multiprocessing as mp
import os
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

from districtgenerator.buildings import thermal
from districtgenerator.buildings.typology import mixed_use
from districtgenerator.storage import profile_store
from districtgenerator.utilities.randomness import seeded_demand_worker


def demand_context(data):
    """
    Picklable subset of the Datahandler state needed by a demand worker.

    Parameters
    ----------
    data : Datahandler
        Datahandler of the district.

    Returns
    -------
    dict
        Site, calendar, time and device data, result path and random settings.
    """
    return {"site": data.site,
            "calendar": data.calendar,
            "time": data.time,
            "decentral_device_data": data.decentral_device_data,
            "resultPath": data.resultPath,
            "initial_day": data.initial_day,
            "random_seed": data.random_seed,
            "flat_parallelization": data.flat_parallelization,
            "flat_max_workers": data.flat_max_workers,
            "design_building_data": data.design_building_data}


@seeded_demand_worker
def run_demand_worker(context, building, calcUserProfiles, saveUserProfiles, gen_cars=True):
    """
    Generate or load all demand profiles of one building.

    Used in threads and in worker processes. All required data is passed via
    `context`, which keeps the pickled payload small and avoids pickling the
    whole Datahandler.

    Parameters
    ----------
    context : dict
        Picklable subset of Datahandler state (site, calendar, time,
        decentral_device_data, resultPath, initial_day, design_building_data).
    building : dict
        Single building entry from self.district.
    calcUserProfiles : bool
    saveUserProfiles : bool
    gen_cars : bool

    Returns
    -------
    dict
        Result payload merged back into self.district in the main process.
    """
    warnings.filterwarnings("ignore", category=FutureWarning)
    print(f'starting {building["unique_name"]}')

    site = context["site"]
    calendar = context["calendar"]
    time_cfg = context["time"]
    decentral_device_data = context["decentral_device_data"]
    resultPath = context["resultPath"]
    initial_day = context["initial_day"]
    demands_path = os.path.join(resultPath, 'demands')

    if calcUserProfiles:
        building["user"].calcProfiles(site=site,
                                       holidays=calendar["holidays"],
                                       time_resolution=time_cfg["timeResolution"],
                                       time_horizon=time_cfg["dataLength"],
                                       building_devices_data=decentral_device_data,
                                       building=building,
                                       path=demands_path,
                                       initial_day=initial_day,
                                       gen_cars=gen_cars,
                                       parallelization=context.get("flat_parallelization", "none"),
                                       max_workers=context.get("flat_max_workers", 4))

        if saveUserProfiles:
            profile_store.save_profiles(name=building["unique_name"],
                                   elec=building["user"].elec,
                                   dhw=building["user"].dhw,
                                   dhw_minutely=building["user"].dhw_minutely,
                                   occ=building["user"].occ,
                                   gains=building["user"].gains,
                                   EV_carcharging_ondemand=building["user"].EV_carcharging_ondemand,
                                   EV_carprofile=building["user"].EV_carprofile,
                                   nb_units=building["user"].nb_units,
                                   nb_occ=building["user"].nb_occ,
                                   ev_capacity=building["user"].ev_capacity or [0],
                                   ice_carprofile=building["user"].ice_carprofile,
                                   heatload=building["envelope"].heatload,
                                   bivalent=building["envelope"].bivalent,
                                   heatlimit=building["envelope"].heatlimit,
                                   path=demands_path,
                                   time_cfg=time_cfg,
                                   individual_car_profiles=building["user"].individual_car_profiles)
    else:
        (building["user"].elec, building["user"].dhw, building["user"].dhw_minutely,
         building["user"].occ, building["user"].gains,
         building["user"].EV_carcharging_ondemand, building["user"].EV_carprofile,
         building["user"].ice_carprofile, building["user"].nb_flats, building["user"].nb_main_rooms,
         building["user"].nb_occ, building["user"].ev_capacity, building["envelope"].heatload,
         building["envelope"].bivalent, building["envelope"].heatlimit,
         building["user"].individual_car_profiles) = profile_store.load_profiles(
            building["unique_name"], demands_path, time_cfg, gen_cars=gen_cars)
        print("Load demands of building " + building["unique_name"])

    thermal.prepare_simulation(building["envelope"], building.get("thermal_model"), site, building["user"].gains)

    night_setback = building["buildingFeatures"]["night_setback"]
    is_cooled = building["buildingFeatures"]["cooling"]

    if calcUserProfiles:
        building["user"].calcHeatingProfile(site=site,
                                             envelope=building["envelope"],
                                             thermal_model=building["thermal_model"],
                                             night_setback=night_setback,
                                             is_cooled=is_cooled,
                                             calendar=calendar,
                                             time_resolution=time_cfg["timeResolution"],
                                             initial_day=initial_day)

        if saveUserProfiles:
            profile_store.save_heating_profile(heat=building["user"].heat,
                                          cooling=building["user"].cooling,
                                          name=building["unique_name"],
                                          path=demands_path)
    else:
        heat, cooling = profile_store.load_heating_profiles(name=building["unique_name"], path=demands_path)
        building["user"].heat = heat
        building["user"].cooling = cooling

    return {
        "unique_name": building["unique_name"],
        "elec": building["user"].elec,
        "dhw": building["user"].dhw,
        "dhw_minutely": building["user"].dhw_minutely,
        "cooling": building["user"].cooling,
        "heating": building["user"].heat,
        "occ": building["user"].occ,
        "EV_carcharging_ondemand": building["user"].EV_carcharging_ondemand,
        "EV_carprofile": building["user"].EV_carprofile,
        "ev_capacity": getattr(building["user"], "ev_capacity", None),
        "ice_carprofile": building["user"].ice_carprofile,
        "gains": building["user"].gains,
        "nb_units": building["user"].nb_units,
        "nb_occ": building["user"].nb_occ,
        "individual_car_profiles": getattr(building["user"], "individual_car_profiles", []),
        "envelope": building["envelope"],
        "night_setback": building["buildingFeatures"]["night_setback"],
    }


def generate_demands(data, calcUserProfiles=True, saveUserProfiles=True, max_workers=8, gen_cars=True):
    """
    Generate demand profiles for all buildings.

    Parameters
    ----------
    calcUserProfiles : bool, optional
        Whether user profiles should be calculated.
    saveUserProfiles : bool, optional
        Whether generated user profiles should be saved.
    max_workers : int, optional
        Maximum number of parallel workers.
    gen_cars : bool, optional
        Whether car profiles should be generated.
    use_multiprocessing : str
        ProcessPoolExecutor or ThreadPoolExecutor is used.
    """

    data.buildings_total = len(data.district)
    data.buildings_completed = 0
    data.save_progress()
    results = []

    # ------------------------------------------------------------------
    # Select parallelization method
    # ------------------------------------------------------------------
    # The same worker and context are used in threads and in processes
    context = demand_context(data)
    if data.parallelization == "multiprocessing":
        # "spawn" is required on Windows and safest cross-platform
        mp_ctx = mp.get_context("spawn")
        executor = ProcessPoolExecutor(max_workers=max_workers, mp_context=mp_ctx)
        parallelization_method = "multiprocessing"
    elif data.parallelization == "threading":
        executor = ThreadPoolExecutor(max_workers=max_workers)
        parallelization_method = "threading"
    else:
        raise ValueError(f"Unknown parallelization '{data.parallelization}'. Options: 'multiprocessing', 'threading'")
    worker_function = lambda ex, building: ex.submit(run_demand_worker, context, building, calcUserProfiles,
                                                     saveUserProfiles, gen_cars)

    # ------------------------------------------------------------------
    # Execute workers
    # ------------------------------------------------------------------
    with executor as ex:
        future_map = {worker_function(ex, building): building["unique_name"] for building in data.district}
        for fut in as_completed(future_map):
            unique_name = future_map[fut]
            result = fut.result()

            data.buildings_completed += 1
            results.append(result)
            data.save_progress()

            print(f"building "f"{data.buildings_completed}/"f"{data.buildings_total} calculated "
                f"({data.buildings_completed / data.buildings_total * 100:.1f}%): "f"{unique_name}")

    # ------------------------------------------------------------------
    # Write results back to district
    # ------------------------------------------------------------------
    for result in results:
        building = next(b for b in data.district if b["unique_name"] == result["unique_name"])

        building["user"].elec = result["elec"]
        building["user"].dhw = result["dhw"]
        building["user"].dhw_minutely = result.get("dhw_minutely")
        building["user"].cooling = result["cooling"]
        building["user"].heat = result["heating"]
        building["user"].occ = result["occ"]
        building["user"].EV_carcharging_ondemand = (result["EV_carcharging_ondemand"])
        building["user"].EV_carprofile = result["EV_carprofile"]
        building["user"].ev_capacity = result.get("ev_capacity")
        building["user"].ice_carprofile = result["ice_carprofile"]
        building["user"].gains = result["gains"]
        building["user"].nb_units = result["nb_units"]
        building["user"].nb_occ = result["nb_occ"]
        building["user"].individual_car_profiles = result.get("individual_car_profiles", [],)
        building["envelope"] = result["envelope"]
        building_features = building["buildingFeatures"].copy()
        building_features["night_setback"] = result["night_setback"]
        building["buildingFeatures"] = building_features

    data.save_progress()
    print(f"Finished generating demands with "f"{parallelization_method}!")
    # Combine demand profiles for mixed-use buildings
    mixed_use.combine_mixed_building_demands(data, saveUserProfiles)
