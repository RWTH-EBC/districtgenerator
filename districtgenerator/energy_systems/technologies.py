"""
Technology models of energy conversion devices and supply rules of buildings.
"""
import math
from numbers import Real

import numpy as np

HEATING_CONCEPTS = ("HP", "GHP", "BHP", "H2HP", "OHP", "BOI", "BBOI", "OBOI", "H2BOI", "EH", "CHP", "FC")


def get_heating_candidates(heater):
    """Return candidate concepts for opt/list inputs, or None for a manual heater."""
    specification = str(heater).strip()
    if specification.lower() == "opt":
        return HEATING_CONCEPTS
    is_list = ("," in specification or specification.startswith("[")
               or specification.lower().startswith("opt:"))
    if not is_list:
        return None
    if specification.lower().startswith("opt:"):
        specification = specification[4:].strip()
    if specification.startswith("["):
        if not specification.endswith("]"):
            raise ValueError("Heating candidate list must end with ']'.")
        specification = specification[1:-1]
    candidates = tuple(dict.fromkeys(token.strip().upper() for token in specification.split(",")))
    invalid = set(candidates) - set(HEATING_CONCEPTS)
    if invalid:
        raise ValueError(f"Invalid heating candidates {sorted(invalid)}; choose from {HEATING_CONCEPTS}.")
    return candidates


def get_cooling_supply(building_features):
    """
    Missing/empty cooler values preserve the default: network
    cooling with heater='heat_grid', otherwise a local CC. Return None
    when active cooling is disabled.
    """
    cooler = building_features.get("cooler")
    if cooler is None or cooler == "" or (isinstance(cooler, Real) and math.isnan(cooler)):
        cooler = "cooling_grid" if building_features["heater"] == "heat_grid" else "CC"
    if cooler not in ("CC", "cooling_grid"):
        raise ValueError(f"Invalid cooler {cooler!r}; choose 'CC' or 'cooling_grid'.")
    return cooler if building_features["cooling"] else None


def compression_chiller_cop(ambient_temperature, grade):
    """Air-to-water CC model"""
    return grade * (273.15 + 5) / np.maximum(np.asarray(ambient_temperature) - 5, 0.1)


def calc_pv_and_stc_profile(sun, time, site, devices, area_roof, beta=35, gamma=0, usageFactorPV1=0.4, usageFactorPV2=0,
                        usageFactorSTC=0.2):
    """
    Computation of power profiles for photovoltaic (PV) collectors and solar thermal collectors (STC).

    Parameters
    ----------
    time : dictionary
        Time information from the Datahandler class.
    site : dictionary
        Site information from the Datahandler class.
    area_roof : float
        Area of the building's roof.
        The unit is [m²].
    devicesType : string, optional
        Possible options are "central" and "decentral". The default entry is "decentral".
    beta : list, optional
        Slope, the angle (in degree) between the plane of the surface of the photovoltaic collectors (PV) / solar
        thermal collectors (STCs) and the horizontal. 0 <= beta <= 180. If beta > 90, the surface faces downwards.
        Just one entry is reasonable. The default entry is 35. The unit is [°].
    gamma : list, optional
        Surface azimuth angle of roof side 1. The deviation of the projection on a horizontal plane of the normal
        to the surface of the PV collectors / STCs from the local meridian, with zero due south, east negative, and
        west positive. -180 <= gamma <= 180. Just one entry is reasonable. The default entry is 0. The unit is [°].
        gamma for roof side 2 is being calculated (while calling the function "getSolarGains" for side 2) as opposite
        to side 1.
    usageFactorPV1/usageFactorPV2 : float, optional
        Ratio between area of all PV collectors on side 1/side 2 of the roof and the roof surface area.
        The default is 0.4 for side 1 and 0 for side 2.
    usageFactorSTC : float, optional
        Ratio between area of all STCs and the surface of the roof. The default is 0.2.

    Returns
    -------
    generation_PV : array_like
        Power profiles of PV collectors. With given weather data as input the unit is [W].
    generation_STC : array_like
        Power profiles of STCs. With given weather data as input the unit is [W].
    """

    # Input validation
    if usageFactorPV1 + usageFactorPV2 > 1:
        raise ValueError(
            f"The sum of usageFactorPV1 ({usageFactorPV1}) and usageFactorPV2 ({usageFactorPV2}) "
            f"is {usageFactorPV1 + usageFactorPV2:.2f}, which exceeds 1. "
            f"Please ensure their sum does not exceed 1."
        )

    # get solar irradiance on PV plant surface
    # Side 1 of the roof (=main side, which is defined by gamma_PV in the input file ("scenario"))
    SunRad1 = sun.getSolarGains(initialTime=0,
                                 timeDiscretization=time["timeResolution"],
                                 timeSteps=time["timeSteps"],
                                 timeZone=site["timeZone"],
                                 location=site["location"],
                                 altitude=site["altitude"],
                                 beta=beta,
                                 gamma=gamma,
                                 beamRadiation=site["SunDirect"],
                                 diffuseRadiation=site["SunDiffuse"],
                                 albedo=site["albedo"])
    # Side 2 of the roof (opposite = 180° to side 1)
    SunRad2 = sun.getSolarGains(initialTime=0,
                                 timeDiscretization=time["timeResolution"],
                                 timeSteps=time["timeSteps"],
                                 timeZone=site["timeZone"],
                                 location=site["location"],
                                 altitude=site["altitude"],
                                 beta=beta,
                                 gamma=(((np.array(gamma) + 360) % 360) - 180).tolist(),  # calculating gamma for
                                 # roof side 2 so that side 2 is opposite to side 1, with respect to the definition
                                 # of gamma (0° = south, 90° = east, 180° = north, -90° = west)
                                 beamRadiation=site["SunDirect"],
                                 diffuseRadiation=site["SunDiffuse"],
                                 albedo=site["albedo"])

    # profile of the ambient temperature
    temperatureProfile = site["T_e"]

    # compute overall correction factor for PV efficiency
    kappa_corr = np.sum([devices["PV"]["kappa_inverter"], devices["PV"]["kappa_wiring"],
                         devices["PV"]["kappa_connections"], devices["PV"]["kappa_soiling"],
                         devices["PV"]["kappa_shading"], devices["PV"]["kappa_mismatch"],
                         devices["PV"]["kappa_NPR"], devices["PV"]["kappa_av"],
                         devices["PV"]["kappa_LID"]
                         ])

    # calculate time variant PV efficiency
    eta_PV1 = np.zeros(time["timeSteps"])
    eta_PV2 = np.zeros(time["timeSteps"])
    for t in range(time["timeSteps"]):
        # source of formula:
        # 'Temperature Dependent Photovoltaic (PV) Efficiency and Its Effect on PV Production in the World
        #  – A Review' , page 313, formula 5
        # by Dubey, Swapnil; Sarvaiya, Jatin Narotam; Seshadri, Bharath - 2013
        # Side 1 of the roof (main side defined by gamma_PV in the input file)
        eta_PV1[t] = devices["PV"]["eta_el_ref"] * \
                     (
                             1 - devices["PV"]["gamma"] * \
                             (
                                     temperatureProfile[t] - devices["PV"]["t_cell_ref"]
                                     + (devices["PV"]["t_cell_noct"] - temperatureProfile[t])
                                     * (SunRad1[0][t] / devices["PV"]["G_noct"])
                             )
                     )
        # Side 2 of the roof (opposite = 180° to side 1)
        eta_PV2[t] = devices["PV"]["eta_el_ref"] * \
                     (
                             1 - devices["PV"]["gamma"] * \
                             (
                                     temperatureProfile[t] - devices["PV"]["t_cell_ref"]
                                     + (devices["PV"]["t_cell_noct"] - temperatureProfile[t])
                                     * (SunRad2[0][t] / devices["PV"]["G_noct"])
                             )
                     )

    # calculate PV power
    generation_PV = np.zeros(time["timeSteps"])
    for t in range(time["timeSteps"]):
        generation_PV[t] = (area_roof) * (1 - kappa_corr) * (
                eta_PV1[t] * SunRad1[0][t] * usageFactorPV1 + eta_PV2[t] * SunRad2[0][t] * usageFactorPV2)

    # efficiency of solar thermal collectors (STC)
    temp_diff = np.zeros_like(temperatureProfile)
    for t in range(time["timeSteps"]):
        temp_diff[t] = devices["STC"]["T_flow"] - temperatureProfile[t]

    eta_STC = np.zeros_like(SunRad1[0])
    eta_STC[SunRad1[0] > 0] = (devices["STC"]["zero_loss"]
                               - devices["STC"]["first_order"] * temp_diff[SunRad1[0] > 0] / SunRad1[0][
                                   SunRad1[0] > 0]
                               - devices["STC"]["second_order"] * temp_diff[SunRad1[0] > 0] ** 2
                               / SunRad1[0][SunRad1[0] > 0])
    eta_STC[eta_STC <= 0.01] = 0

    # calculate STC power
    generation_STC = np.zeros(time["timeSteps"])
    for t in range(time["timeSteps"]):
        generation_STC[t] = SunRad1[0][t] * eta_STC[t] * usageFactorSTC * area_roof

    return generation_PV, generation_STC


# %% COP model for ammonia-heat pumps
# Heat pump COP, part 2: Generalized COP estimation of heat pump processes
# DOI: 10.18462/iir.gl.2018.1386
# Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes.
def calc_COP(data, clusterHorizon, devs, device, temperatures):

    # get temperature parameters
    t_c_in = temperatures[0]
    dt_c = temperatures[1]
    t_h_in = temperatures[2]
    dt_h = temperatures[3]

    # device parameters
    dt_pp_cond = devs[device]["dT_pinch_cond"]  # pinch point temperature difference in the condenser
    dt_pp_evap = devs[device]["dT_pinch_evap"]  # pinch point temperature difference in the evaporator

    eta_is = devs[device]["eta_compr"]  # isentropic compression efficiency
    f_Q = devs[device]["heatloss_compr"]  # heat loss rate during compression

    # Entropic mean temperautures (or Logarithmic mean temperatures)
    t_h_s = dt_h / np.log((t_h_in + dt_h) / t_h_in)
    t_c_s = dt_c / np.log(t_c_in / (t_c_in - dt_c))

    # Prevent numeric issues
    for d in range(data.time["clusterNumber"]):
        for t in range(clusterHorizon):
            if t_h_s[d][t] == t_c_s[d][t]:
                t_h_s[d][t] += 1e-5

    # Lorentz-COP
    COP_Lor = t_h_s / (t_h_s - t_c_s)

    # linear model equations; Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes.
    dt_r_H = 0.2 * (t_h_in + dt_h - (
                t_c_in - dt_c) + (dt_pp_cond + dt_pp_evap)) + 0.2 * dt_h + 0.016  # mean entropic heat difference in condenser deducting dt_pp and assuming an ammonia heat pump
    w_is = 0.0014 * (t_h_in + dt_h - (
                t_c_in - dt_c) + (dt_pp_cond + dt_pp_evap)) - 0.0015 * dt_h + 0.039  # ratio of isentropic expansion work to isentropic compression work and assuming an ammonia heat pump

    # help values
    num = 1 + (dt_r_H + dt_pp_cond) / t_h_s
    denom = 1 + (dt_r_H + 0.5 * dt_c + (dt_pp_cond + dt_pp_evap)) / (t_h_s - t_c_s)

    # COP
    COP = COP_Lor * num / denom * eta_is * (1 - w_is) + 1 - eta_is - f_Q

    if device == "CC":
        COP = COP - 1  # consider COP definition for compression chillers (COP_CC = Q_0/P_el = (Q - P_el)/P_el = COP_HP - 1)

    # limit COP's
    COP_max = devs[device]["COP_max"]
    for d in range(data.time["clusterNumber"]):
        for t in range(clusterHorizon):
            if COP[d, t] > COP_max or COP[d, t] < 0:
                COP[d, t] = COP_max

    return COP
