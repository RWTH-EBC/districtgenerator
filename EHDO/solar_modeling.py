# -*- coding: utf-8 -*-
"""

EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool

Developed by:   E.ON Energy Research Center, 
                Institute for Energy Efficient Buildings and Indoor Climate, 
                RWTH Aachen University, 
                Germany
               
Contact:        Marco Wirtz 
                marco.wirtz@eonerc.rwth-aachen.de
                
Solar modeling script developed by Rafal Broda (E.ON ERC EBC, RWTH Aachen University, 2021).                

"""

import os
import math
import numpy as np
import pandas as pd
import csv

def load_epw(weather_file):
    # Import energy plus weather file
    header = {}
    with open(os.path.join(weather_file), newline="", errors="ignore") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=",", quotechar='"')
        for row in csvreader:
            if row[0].isdigit():
                break
            else:
                header[row[0]]=row[1:]

    timezone = float(header["LOCATION"][7])
    altitude = float(header["LOCATION"][8])

    param = {}

    file = open(os.path.join(weather_file), "rb")
    T_air, GHI, DHI, wind_speed = np.loadtxt(file, delimiter=",", skiprows=8, usecols=[6,13,15,21], unpack=True)

    param["T_air"] = T_air
    param["wind_speed"] = wind_speed
    param["direct_horiz_irrad"] = GHI - DHI
    param["diffuse_horiz_irrad"] = DHI
    param["global_irrad"] = GHI

    data = pd.DataFrame(param)

    return timezone, altitude, data

def load_dwd(weather_file):
    # Import dwd weather file
    param = {}

    T_air = []
    wind_speed = []
    direct_horizontal_irrad = []
    diffuse_horizontal_irrad = []

    with open(os.path.join(weather_file), "r") as weather_file:
        file = weather_file.readlines()
        for line in range(34,len(file)):
            cleaned_list = [val for val in file[line].split(" ") if val != ""]
            T_air.append(float(cleaned_list[5]))
            wind_speed.append(float(cleaned_list[8]))
            direct_horizontal_irrad.append(float(cleaned_list[12]))
            diffuse_horizontal_irrad.append(float(cleaned_list[13]))

    param["T_air"] = np.array(T_air)
    param["wind_speed"] = np.array(wind_speed)
    param["direct_horiz_irrad"] = np.array(direct_horizontal_irrad)
    param["diffuse_horiz_irrad"] = np.array(diffuse_horizontal_irrad)
    param["global_irrad"] = param["direct_horiz_irrad"] + param["diffuse_horiz_irrad"]

    data = pd.DataFrame(param)

    return data

def getGeometry(initialTime, timeDiscretization, timesteps, timeZone=1,
                location=(50.76, 6.07), altitude=0):
    """
    This function computes hour angle, declination, zenith angle of the sun
    and solar azimuth angle for a given location and time.

    The implemented equations can be found in:
    Duffie, Beckman - Solar Engineering of Thermal Processes, 2013 (4th ed.)

    Function copied from sun.py script, developed by author Thomas Schuetz
    https://github.com/RWTH-EBC/BuildingOPT/blob/master/sun.py

    Parameters
    ----------
    initialTime : integer
        Time passed since January 1st, 00:00:00 in seconds
    timeDiscretization : integer
        Time between two consecutive timesteps in seconds
    timesteps : integer
        Number of investigated / requested timesteps
    timeZone : integer, optional
        Shift between the location"s time and GMT in hours. CET would be 1.
    location : tuple, optional
        (latitude, longitude) of the simulated system"s position. Standard
        values (50.76, 6.07) represent Aachen, Germany.
    altitude : float, optional
        The locations altitude in meters

    Returns
    -------
    omega : array_like
        Hour angle. The angular displacement of the sun east or west of the
        local meridian due to rotation of the earth on its axis at 15 degrees
        per hour; morning negative, afternoon positive
    delta : array_like
        Declination. The angular position of the sun at solar noon (i.e., when
        the sun is on the local meridian) with respect to the plane of the
        equator, north positive; −23.45 <= delta <= 23.45
    thetaZ : array_like
        Zenith angle. The angle between the vertical and the line to the sun,
        that is, the angle of incidence of beam radiation on a horizontal
        surface; 0 <= thetaZ <= 90
    """
    # Define pi
    pi = math.pi

    # Notice:
    # All inputs and outputs are given/expected in degrees. For the
    # computation, radians are required. Angles are converted from degrees to
    # radians via np.radians(angle). The resulting radian value is noted with
    # an R-suffix. Converting radian values to degrees is done via
    # np.rad2deg(angleR).
    # This conversion can also be done by multiplying/dividing with 180°/pi

    # Split location into latitude (phi) and longitude (lambda).
    (latitude, longitude) = location

    # Create time array
    time = ((np.linspace(0, timesteps-1, num=timesteps)) * timeDiscretization
            + initialTime)

    # Determine the day"s number and standard time (neglect daylight saving)
    numberDay = time / (3600 * 24)
    standardTime = time / 3600 - np.floor(numberDay) * 24

    # Equation 1.4.2, page 9
    B = 360 / 365.26 * numberDay
    BR = np.radians(B)
    # Compute abbreviations for E and extraterrestrial irradiation (Gon)
    cosB  = np.cos(BR)
    sinB  = np.sin(BR)
    cos2B = np.cos(2 * BR)
    sin2B = np.sin(2 * BR)

    # Convert local time into solar time
    # Equation 1.5.3, page 11
    E = 229.2 / 60 * (0.000075 +
                      0.001868 * cosB -
                      0.032077 * sinB -
                      0.014615 * cos2B -
                      0.040890 * sin2B)

    # Compute standard meridian
    # Footnote 5 of chapter 1. Can be found on page 11.
    lambdaStandard = timeZone * 15

    # Compute solar time
    # Equation 1.5.2, page 11 (conversion to hours instead of minutes)
    solarTime = (standardTime + 4 * (longitude - lambdaStandard) / 60 + E) - 0.5

    # Hour angle
    # The angular displacement of the sun east or west of the local meridian
    # due to rotation of the earth on its axis at 15 degrees per hour; morning
    # negative, afternoon positive
    # Confirm page 13
    omega = 360 / 24 * (solarTime - 12)
    # Ensure: -180 <= omega <= 180
    omega[omega < -180] = omega[omega < -180] + 360
    omega[omega >  180] = omega[omega >  180] - 360
    omegaR = np.radians(omega)

    # Declination
    # The angular position of the sun at solar noon (i.e., when the sun is on
    # the local meridian) with respect to the plane of the equator, north
    # positive; −23.45 <= delta <= 23.45
    # Equation 1.6.1a, page 13
    delta = 23.45 * np.sin((284 + numberDay) / 365 * 2 * pi)
    deltaR = np.radians(delta)

    # Zenith angle
    # The angle between the vertical and the line to the sun, that is, the
    # angle of incidence of beam radiation on a horizontal surface;
    # 0 <= thetaZ <= 90. If thetaZ > 90, the sun is below the horizon.
    # Equation 1.6.5 on page 15

    # Introduce abbreviations to improve readability
    latitudeR = math.radians(latitude)
    cosPhi    = math.cos(latitudeR)
    sinPhi    = math.sin(latitudeR)
    cosDelta  = np.cos(deltaR)
    sinDelta  = np.sin(deltaR)
    cosOmega  = np.cos(omegaR)
    cosThetaZ = np.maximum(0, cosPhi * cosDelta * cosOmega + sinDelta * sinPhi)
    thetaZR   = np.arccos(cosThetaZ)
    thetaZ    = np.rad2deg(thetaZR)

    # Compute airmass
    # Footnote 3 on page 10
    airmass = (math.exp(-0.0001184 * altitude) /
              (cosThetaZ + 0.5057 * np.power(96.08 - thetaZ, -1.634)))

    # Compute extraterrestrial irradiance (Gon)
    # Extraterrestrial radiation incident on the plane normal to the radiation
    # on the nth day of the year.
    # Solar constant. Page 6
    Gsc = 1367 # W/m2
    # Equation 1.4.1b
    Gon = Gsc * (1.000110 +
                 0.034221 * cosB +
                 0.001280 * sinB +
                 0.000719 * cos2B +
                 0.000077 * sin2B)

    # Return results
    return (omega, delta, thetaZ, airmass, Gon)

def getIncidenceAngle(beta, gamma, phi, omega, delta):
    """
    Compute the incidence angle on a tilted surface.

    All inputs/outputs are supposed to be in degrees!

    Function copied from sun.py script, developed by author Thomas Schuetz
    https://github.com/RWTH-EBC/BuildingOPT/blob/master/sun.py

    Parameters
    ----------
    beta : float
        Slope, the angle (in degree) between the plane of the surface in
        question and the horizontal. 0 <= beta <= 180. If beta > 90, the
        surface faces downwards.
    gamma : float
        Surface azimuth angle. The deviation of the projection on a horizontal
        plane of the normal to the surface from the local meridian, with zero
        due south, east negative, and west positive.
        -180 <= gamma <= 180
    phi : float
        Latitude. North is positve, south negative. -90 <= phi <= 90
    omega : array_like
        Hour angle. The angular displacement of the sun east or west of the
        local meridian due to rotation of the earth on its axis at 15 degrees
        per hour; morning negative, afternoon positive
    delta : array_like
        Declination. The angular position of the sun at solar noon (i.e., when
        the sun is on the local meridian) with respect to the plane of the
        equator, north positive; −23.45 <= delta <= 23.45
    """
    # Compute incidence angle of beam radiation
    # Transform to radian
    betaR  = math.radians(beta)
    phiR   = math.radians(phi)
    gammaR = math.radians(gamma)
    deltaR = np.radians(delta)
    omegaR = np.radians(omega)

    # Introduce required abbreviations
    sinBeta  = math.sin(betaR)
    cosBeta  = math.cos(betaR)
    sinDelta = np.sin(deltaR)
    cosDelta = np.cos(deltaR)
    sinPhi   = math.sin(phiR)
    cosPhi   = math.cos(phiR)
    sinGamma = math.sin(gammaR)
    cosGamma = math.cos(gammaR)
    sinOmega = np.sin(omegaR)
    cosOmega = np.cos(omegaR)

    # Equation 1.6.2, page 14
    cosTheta = np.maximum(sinDelta * sinPhi * cosBeta -
                          sinDelta * cosPhi * sinBeta * cosGamma +
                          cosDelta * cosPhi * cosBeta * cosOmega +
                          cosDelta * sinPhi * sinBeta * cosGamma * cosOmega +
                          cosDelta * sinBeta * sinGamma * sinOmega, 0)

    thetaR = np.arccos(cosTheta)
    theta  = np.rad2deg(thetaR)

    # Return incidence angle
    return (cosTheta, theta)

def getTotalRadiationTiltedSurface(theta, thetaZ,
                                   beamRadiation, diffuseRadiation,
                                   airmass, extraterrestrialIrradiance,
                                   beta, albedo):
    """
    Compute the total radiation on a tilted surface.

    Function copied from sun.py script, developed by author Thomas Schuetz
    https://github.com/RWTH-EBC/BuildingOPT/blob/master/sun.py

    Parameters
    ----------
    theta : array_like
        Incidence angle.
    thetaZ : array_like
        Zenith angle. The angle between the vertical and the line to the sun,
        that is, the angle of incidence of beam radiation on a horizontal
        surface; 0 <= thetaZ <= 90
    beamRadiation : array_like
        The solar radiation received from the sun without having been
        scattered by the atmosphere (also often named direct radiation)
    diffuseRadiation : array_like
        The solar radiation received from the sun after its direction has been
        changed by scattering by the atmosphere.
    airmass : array_like
        The ratio of the mass of atmosphere through which beam radiation
        passes to the mass it would pass through if the sun were at the zenith.
        Thus at sea level ``m=1`` when the sun is at the zenith and ``m=2``
        for a zenith angle ``thetaZ=60`` degrees.
    extraterrestrialIrradiance : array_like
        Extraterrestrial radiation incident on the plane normal to the
        radiation on the nth day of the year.
    beta : float
        Slope, the angle (in degree) between the plane of the surface in
        question and the horizontal. 0 <= beta <= 180. If beta > 90, the
        surface faces downwards.
    albedo : float
        Ground reflectance. 0 <= albedo <= 1
    """
    # Model coefficients
    # Table 6, in Perez et al - 1990 - Modeling daylight availability and
    # irradiance components from direct and global irradiance.
    # Solar Energy, Vol. 44, No. 5, pp. 271-289
    # Values with increased accuracy can be found in the EnergyPlus
    # engineering reference (Table 22, Fij Factors as a Function of Sky
    # Clearness Range, page 147)

    fCoefficients = np.array(
      [[-0.0083117, 0.5877285, -0.0620636, -0.0596012,  0.0721249, -0.0220216],
       [0.1299457,  0.6825954, -0.1513752, -0.0189325,  0.065965,  -0.0288748],
       [0.3296958,  0.4868735, -0.2210958,  0.055414,  -0.0639588, -0.0260542],
       [0.5682053,  0.1874525, -0.295129,   0.1088631, -0.1519229, -0.0139754],
       [0.873028,  -0.3920403, -0.3616149,  0.2255647, -0.4620442,  0.0012448],
       [1.1326077, -1.2367284, -0.4118494,  0.2877813, -0.8230357,  0.0558651],
       [1.0601591, -1.5999137, -0.3589221,  0.2642124, -1.127234,   0.1310694],
       [0.677747,  -0.3272588, -0.2504286,  0.1561313, -1.3765031,  0.2506212]
      ])

    # Compute a and b (page 281, below equation 9)
    thetaR  = np.radians(theta)
    thetaZR = np.radians(thetaZ)
    cosThetaZ = np.cos(thetaZR)
    cosTheta  = np.cos(thetaR)
    a = np.maximum(0, cosTheta)
    b = np.maximum(0.087, cosThetaZ)

    # Compute epsilon (the sky"s clearness)
    # Introduce variables and compute third power of thetaZR
    kappa = 1.041
    thetaZRTo3 = np.power(thetaZR, 3)

    # Compute normal incidence direct irradiance
    I = beamRadiation / b
    # Prevent division by zero
    temp = np.zeros_like(theta) # All inputs should have this length!
    temp[diffuseRadiation > 0] = (1.0 * I[diffuseRadiation > 0] /
                                  diffuseRadiation[diffuseRadiation > 0])
    # equation 1 on p. 273 in Perez et al - 1990
    epsilon = (1 + temp + kappa * thetaZRTo3) / (1 + kappa * thetaZRTo3)

    # Determine clear sky category
    # table 1 on page 273 in Perez et al - 1990
    # Note: As this value is used to get data from fCoefficients, the
    # implemented categories range from 0 to 7 instead from 1 to 8
    epsilonCategory = np.zeros_like(epsilon, dtype=int)
    epsilonCategory[(epsilon >= 1.065) & (epsilon < 1.23)] = 1
    epsilonCategory[(epsilon >= 1.230) & (epsilon < 1.50)] = 2
    epsilonCategory[(epsilon >= 1.500) & (epsilon < 1.95)] = 3
    epsilonCategory[(epsilon >= 1.950) & (epsilon < 2.80)] = 4
    epsilonCategory[(epsilon >= 2.800) & (epsilon < 4.50)] = 5
    epsilonCategory[(epsilon >= 4.500) & (epsilon < 6.20)] = 6
    epsilonCategory[epsilon >= 6.200] = 7

    # Compute Delta (the sky"s brightness)
    # equation 2 on page 273 in Perez et al - 1990
    Delta = diffuseRadiation * airmass / extraterrestrialIrradiance

    # Compute F1 (circumsolar brightening coefficient) and F2 (horizon
    # brightening coefficient)
    # Below table 6 on page 282 in Perez et al - 1990
    # According to Duffie and Beckman (4th edition, page 94, equation 2.16.12),
    # F1 is supposed to be greater or equal to 0
    F1 = np.maximum(fCoefficients[epsilonCategory,0] +
                    fCoefficients[epsilonCategory,1] * Delta +
                    fCoefficients[epsilonCategory,2] * thetaZR,
                    0)

    F2 = (fCoefficients[epsilonCategory,3] +
          fCoefficients[epsilonCategory,4] * Delta +
          fCoefficients[epsilonCategory,5] * thetaZR)

    # Compute diffuse radiation on tilted surface
    # Equation 9 on page 281 in Perez et al - 1990
    betaR   = math.radians(beta)
    cosBeta = math.cos(betaR)
    sinBeta = math.sin(betaR)
    diffuseRadTiltSurface = diffuseRadiation * ((1 - F1) * (1 + cosBeta) / 2 +
                                                F1 * a / b + F2 * sinBeta)

    # Compute the influence of beam radiation and reflected radiation
    # Equation 2.15.1 in Duffie and Beckman (4th edition, page 89)
    # Compute direct radiation on tilted surface
    # Equation 1.8.1 in Duffie and Beckman (4th edition, page 24)
    # We divide by b instead of cosThetaZ to prevent division by 0
    # Direct radiation on a tilted surface is always positive, therefore use
    # ``a`` insted of cosTheta
    directRadTiltSurface = beamRadiation * a / b

    # Compute reflected total radiation
    # Equation 2.15.1 in Duffie and Beckman (4th edition, page 89)
    # Notice: We changed the proposed nomenclature. rhoG is written as albedo.
    # Total solar radiation is computed as sum of beam and diffuse radiation.
    # See page 10 in Duffie and Beckman (4th edition)
    totalSolarRad = beamRadiation + diffuseRadiation
    reflectedRadTiltSurface = totalSolarRad * albedo * (1 - cosBeta) / 2

    totalRadTiltSurface = (diffuseRadTiltSurface +
                           directRadTiltSurface +
                           reflectedRadTiltSurface)

    # Return total radiation on a tilted surface
    return totalRadTiltSurface, directRadTiltSurface, diffuseRadTiltSurface, reflectedRadTiltSurface

def calc_global_tilted_irrad(direct_solar, diffuse_solar, azim, elev, latitude, longitude, timezone, altitude=0):
    """
    Calculate the total radiation on a tilted surface.

    Function copied from sun.py script, developed by author Thomas Schuetz
    https://github.com/RWTH-EBC/BuildingOPT/blob/master/sun.py

    Parameters
    ---------
    ghi : array_like
        Global horizontal irradiance
    dhi : array_like
        Diffuse horizontal irradiance
    azim : float
        Azimuth of the surface in degree; 0 if south
    elev : float
        Tilt angle of the surface in degree
    latitude : float
        latitude (phi) of location
    longitude : float
        longitude (lambda) of location
    timezone : int
        Shift between the location"s time and GMT in hours. CET would be 1.
    altitude : float, optional
        height of location above sea level
    """

    # Calculate geometric relations
    location = (latitude, longitude)
    geometry = getGeometry(3600, 3600, 8760, timezone, location, altitude)
    (omega, delta, thetaZ, airmass, Gon) = geometry

    theta = getIncidenceAngle(elev, azim, location[0], omega, delta)
    theta = theta[1] # cosTheta is not required

    totalRadTiltSurface, directRadTiltSurface, diffuseRadSkyTiltSurface, reflectedRadTiltSurface = getTotalRadiationTiltedSurface(theta, thetaZ, direct_solar, diffuse_solar, airmass, Gon, elev, 0.2)

    # Calculate radiation on tilted surface
    return totalRadTiltSurface, directRadTiltSurface, diffuseRadSkyTiltSurface+reflectedRadTiltSurface, theta

def ashrae_iam(theta, b0):
    r"""
    Determine the incidence angle modifier using the ASHRAE transmission
    model.

    The ASHRAE (American Society of Heating, Refrigeration, and Air
    Conditioning Engineers) transmission model is developed in
    [1], and in [2]. The model has been used in software such as PVSyst [3].

    Parameters
    ----------
    theta : numeric
        The angle of incidence (AOI) between the module normal vector and the
        sun-beam vector in degrees. Angles of nan will result in nan.

    b0 : float
        A parameter to adjust the incidence angle modifier as a function of
        angle of incidence. Typical values for PV systems are on the order of 0.05 [3].
        For thermal systems, this parameter is fitted using IAM (50°) datapoint from
        collector specification and corresponding function for IAM.

    Returns
    -------
    iam : numeric
        The incident angle modifier (IAM). Returns zero for all abs(aoi) >= 90
        and for all ``iam`` values that would be less than 0.

    Notes
    -----
    The incidence angle modifier is calculated as

    .. math::

        IAM = 1 - b0 (cos(theta) - 1)

    As AOI approaches 90 degrees, the model yields negative values for IAM;
    negative IAM values are set to zero in this implementation.

    References
    ----------
    .. [1] Souka A.F., Safwat H.H., "Determination of the optimum
       orientations for the double exposure flat-plate collector and its
       reflections". Solar Energy vol .10, pp 170-174. 1966.

    .. [2] ASHRAE standard 93-77

    .. [3] PVsyst Contextual Help.
       https://files.pvsyst.com/help/index.html?iam_loss.htm [Accessed on
       30- Aug- 2021]

    """

    iam = 1 - b0 * (1 / np.cos(np.radians(theta)) - 1)
    theta_gte_90 = np.full_like(theta, False, dtype="bool")
    np.greater_equal(np.abs(theta), 90, where=~np.isnan(theta), out=theta_gte_90)
    iam = np.where(theta_gte_90, 0, iam)
    iam = np.maximum(0, iam)

    if isinstance(theta, pd.Series):
        iam = pd.Series(iam, index=theta.index)

    return iam

def pv_system(direct_tilted_irrad, diffuse_tilted_irrad, theta, T_air, wind_speed, module="standard", mounting="freestanding_wind_dep"):
    """
    Calculate PV system output [kW/kWp] using empirical models for cell temperature, losses, and inverter.

    Parameters
    ----------
    global_tilted_irrad : numeric, series
        Total incident irradiance [W/m^2] on module.

    T_air : numeric, series
        Ambient dry bulb temperature [°C].

    wind_speed : numeric, series
        Wind speed in m/s.

    module : string, default: "standard"
        Module type; used for approximation of cell temperature effect on efficiency.
        It can be selected from the following:

        +----------------+---------------+
        | Module         | gamma [%/°C]  |
        +================+===============+
        | standard       | -0.47         |
        +----------------+---------------+
        | premium        | -0.35         |
        +----------------+---------------+
        | thin_film      | -0.20         |
        +----------------+---------------+

        The “standard” option represents typical poly- or mono-crystalline silicon modules.
        The “premium” option is appropriate for modeling high efficiency monocrystalline silicon
        modules that have lower temperature coefficients.
        The thin film option assumes a significantly lower temperature coefficient which is
        representative of most installed thin film modules as of 2013.

        Model and empirical values are taken from [2].


    mounting : string, default: "freestanding_wind_dep"
        Mounting of modules; used for cell temperature approximation.
        It can be selected from the following:

        +--------------------------+---------------+---------------+
        | Mounting                 | :math:`U_{c}` | :math:`U_{v}` |
        +==========================+===============+===============+
        | insulated                | 15.0          | 0.0           |
        +--------------------------+---------------+---------------+
        | semi_integrated          | 20.0          | 0.0           |
        +--------------------------+---------------+---------------+
        | freestanding             | 29.0          | 0.0           |
        +--------------------------+---------------+---------------+
        | freestanding_wind_dep    | 25.0          | 1.2           |
        +--------------------------+---------------+---------------+

        Semi_integrated refers to intermediary cases (integration with air duct below the collectors).
        Temperature model and empirical values are taken from [1].

    Returns
    -------
    power_ac : numeric, series
        Hourly AC power output profile [W/kWp].

    References
    ----------
    .. [1] "PVsyst 7 Help", Files.pvsyst.com, 2021. [Online]. Available:
           https://www.pvsyst.com/help/index.html. [Accessed: 04- Aug- 2021].

    .. [2] A. P. Dobos, "PVWatts Version 5 Manual"
           https://www.nrel.gov/docs/fy14osti/62641.pdf
           (2014).

    """

    MODEL_PARAMETERS = {"temperature":
                          {"insulated": {"u_c": 15.0, "u_v": 0},
                           "semi_integrated": {"u_c": 20, "u_v": 0},
                           "freestanding": {"u_c": 29.0, "u_v": 0},
                           "freestanding_wind_dep": {"u_c": 25.0, "u_v": 1.2}},
                        "module":
                          {"standard": {"gamma": -0.47},
                           "premium":  {"gamma": -0.35},
                           "thin_film": {"gamma": -0.20}}
                       }
    #----------------------#
    # compute cell temperature according to [1]
    eta_m = 0.1
    alpha_absorption = 0.9

    total_loss_factor = MODEL_PARAMETERS["temperature"][mounting]["u_c"] + MODEL_PARAMETERS["temperature"][mounting]["u_v"] * wind_speed
    heat_input = (direct_tilted_irrad + diffuse_tilted_irrad) * alpha_absorption * (1 - eta_m)
    T_difference = heat_input / total_loss_factor
    T_cell = T_air + T_difference

    #----------------------#
    # compute losses according to [2]
    soiling = 2
    shading = 3
    snow = 0
    mismatch = 2
    wiring = 2
    connections = 0.5
    lid = 1.5              # light induced degradation
    nameplate_rating = 1
    age = 0
    availability = 3

    params = [soiling, shading, snow, mismatch, wiring, connections, lid,
              nameplate_rating, age, availability]

    # manually looping over params allows for numpy/pandas to handle any
    # array-like broadcasting that might be necessary
    perf = 1
    for param in params:
        perf *= 1 - param/100

    losses = (1 - perf) * 100.

    # compute incidence angle modifier (IAM)
    b0 = 0.05 # as stated in [1]
    iam = ashrae_iam(theta, b0)

    #----------------------#
    # compute DC output according to [2]
    power_dc = (1 - 0.01 * losses) * (iam * direct_tilted_irrad + diffuse_tilted_irrad) * 0.001 * (1 + MODEL_PARAMETERS["module"][module]["gamma"] * 0.01 * (T_cell - 25.))

    #----------------------#
    # compute AC output (inverter) according to [2]

    eta_inv_nom = 0.96
    eta_inv_ref = 0.9637

    pac0 = eta_inv_nom
    zeta = power_dc

    # arrays to help avoid divide by 0 for scalar and array
    eta = np.zeros_like(power_dc, dtype=float)
    pdc_neq_0 = ~np.equal(power_dc, 0)

    # eta < 0 if zeta < 0.006. power_ac is forced to be >= 0 below.
    eta = eta_inv_nom / eta_inv_ref * (
        -0.0162 * zeta - np.divide(0.0059, zeta, out=eta, where=pdc_neq_0)
        + 0.9858)

    power_ac = eta * power_dc
    power_ac = np.minimum(pac0, power_ac)
    power_ac = np.maximum(0, power_ac)

    power_ac = power_ac * 1000

    return power_ac

def collector_system(direct_tilted_irrad, diffuse_tilted_irrad, theta, T_air, collector="flat_plate", T_m=50):
    """
    Calculate collector system output. Model is based on DIN EN 12975-2 [1].

    Parameters
    ----------
    direct_tilted_irrad : numeric, series
        Direct incident irradiance [W/m^2] on collector.

    diffuse_tilted_irrad : numeric, series
        Diffuse incident irradiance [W/m^2] on collector.

    theta : numeric, series
        Angle of incidence [°].

    T_air : numeric, series
        Ambient dry bulb temperature [°C].

    collector : string, default: "flat_plate"
        Collector model parameters.
        It can be selected from the following:

        +-------------------+-------+-------+-------+------+-------+
        | Collector         |  eta0 |  a1   |   a2  |  K_d |   b0  |
        +===================+=======+=======+=======+======+=======+
        | flat_plate        | 0.784 | 3.69  | 0.012 | 0.96 | 0.134 |
        +-------------------+-------+-------+-------+------+-------+
        | evacuated_tube    | 0.559 | 0.656 | 0.004 | 0.96 | 0.02  |
        +-------------------+-------+-------+-------+------+-------+

        Values are taken from [2].
        flat_plate: Vaillant VTK 155/2 V (License Number: 011-7S1937 F)
        evacuated_tube: Vaillant VTK 570/2 (License Number: 011-7S768 R)

    T_m : numeric, default: 50
        Mean collector temperature [°C].
        Calculated as
        T_m = (T_in + T_out)/2

    Returns
    -------
    heat : numeric, series
        Hourly heat flow profile [W/m2].


    References
    ----------
    .. [1] DIN EN 12975-2

    .. [2] "Solar Keymark", 2021 [Online]. Available:
           http://www.solarkeymark.nl/DBF/#. [Accessed: 30- Aug- 2021].

    """

    MODEL_PARAMETERS = {"collector":
                          {"flat_plate": {"eta0": 0.784, "a1": 3.69, "a2": 0.012, "K_d": 0.96, "b0": 0.134},
                           "evacuated_tube": {"eta0": 0.559, "a1": 0.646, "a2": 0.004, "K_d": 0.96, "b0": 0.02}}
                       }

    K_b = ashrae_iam(theta, MODEL_PARAMETERS["collector"][collector]["b0"])
    T_coll = T_m - T_air

    heat = (MODEL_PARAMETERS["collector"][collector]["eta0"] * K_b * direct_tilted_irrad +
            MODEL_PARAMETERS["collector"][collector]["eta0"] * MODEL_PARAMETERS["collector"][collector]["K_d"] * diffuse_tilted_irrad -
            MODEL_PARAMETERS["collector"][collector]["a1"] * T_coll -
            MODEL_PARAMETERS["collector"][collector]["a2"] * T_coll**2)

    heat = np.maximum(0, heat)

    return heat

def solar_yield(latitude, longitude, azimuth, elevation, weather_file,
                pv_module="standard", pv_mounting="freestanding_wind_dep",
                collector="flat_plate", T_m=50):
    """
    Calculate collector and PV system output.

    Parameters
    ----------

    latitude : float
        Latitude of location.

    longitude : float
        Longitude of location.

    azimuth : float
        Azimuth angle of PV or collector module (in degree).
        0 for south; 180 for north; -90 for east; 90 for west.

    elevation : float
        Slope, the angle (in degree) between the plane of the surface in
        question and the horizontal. 0 <= elevation <= 180. If beta > 90, the
        surface faces downwards.

    weather_file : string
        Energy Plus Weather (EPW) file (+ file path).
        Example: "epw_weather_files/DEU_Dusseldorf.104000_IWEC.epw"

    pv_module : string, default: "standard"
        Module type; used for approximation of PV cell temperature effect on efficiency.
        It can be selected from the following:

        +----------------+---------------+
        | Module         | gamma [%/°C]  |
        +================+===============+
        | standard       | -0.47         |
        +----------------+---------------+
        | premium        | -0.35         |
        +----------------+---------------+
        | thin_film      | -0.20         |
        +----------------+---------------+

        The “standard” option represents typical poly- or mono-crystalline silicon modules.
        The “premium” option is appropriate for modeling high efficiency monocrystalline silicon
        modules that have lower temperature coefficients.
        The thin film option assumes a significantly lower temperature coefficient which is
        representative of most installed thin film modules as of 2013.

        Model and empirical values are taken from [2].

    pv_mounting : string, default: "freestanding_wind_dep"
        Mounting of modules; used for cell temperature approximation.
        It can be selected from the following:

        +--------------------------+---------------+---------------+
        | Mounting                 | :math:`U_{c}` | :math:`U_{v}` |
        +==========================+===============+===============+
        | insulated                | 15.0          | 0.0           |
        +--------------------------+---------------+---------------+
        | semi_integrated          | 20.0          | 0.0           |
        +--------------------------+---------------+---------------+
        | freestanding             | 29.0          | 0.0           |
        +--------------------------+---------------+---------------+
        | freestanding_wind_dep    | 25.0          | 1.2           |
        +--------------------------+---------------+---------------+

        Semi_integrated refers to intermediary cases (integration with air duct below the collectors).
        Temperature model and empirical values are taken from [1].

    collector : string, default: "flat_plate"
        Collector model parameters. Model based on [3].
        It can be selected from the following:

        +-------------------+-------+-------+-------+------+-------+
        | Collector         |  eta0 |  a1   |   a2  |  K_d |   b0  |
        +===================+=======+=======+=======+======+=======+
        | flat_plate        | 0.784 | 3.69  | 0.012 | 0.96 | 0.134 |
        +-------------------+-------+-------+-------+------+-------+
        | evacuated_tube    | 0.559 | 0.656 | 0.004 | 0.96 | 0.02  |
        +-------------------+-------+-------+-------+------+-------+

        Values are taken from [2].
        flat_plate: Vaillant VTK 155/2 V (License Number: 011-7S1937 F)
        evacuated_tube: Vaillant VTK 570/2 (License Number: 011-7S768 R)

    T_m : numeric, default: 50
        Mean collector temperature [°C].
        Calculated as
        T_m = (T_in + T_out)/2

    Returns
    -------

    data["pv_power"] : numeric, series
        Hourly AC power output profile [W/kWp] of PV system.

    data["collector_heat"] : numeric, series
        Hourly heat flow profile [W/m2] of collector system.

    References
    ----------
    .. [1] "PVsyst 7 Help", Files.pvsyst.com, 2021. [Online]. Available:
           https://www.pvsyst.com/help/index.html. [Accessed: 04- Aug- 2021].

    .. [2] A. P. Dobos, "PVWatts Version 5 Manual"
           https://www.nrel.gov/docs/fy14osti/62641.pdf
           (2014).

    .. [3] DIN EN 12975-2

    .. [4] "Solar Keymark", 2021 [Online]. Available:
           http://www.solarkeymark.nl/DBF/#. [Accessed: 30- Aug- 2021].

    """

    # get weather data and timezone from epw weather file
    timezone, altitude, data = load_epw(weather_file)

    # compute global, direct, and diffuse irradiance on tilted surface
    global_tilted, direct_tilted, diffuse_tilted, theta = calc_global_tilted_irrad(direct_solar=data["direct_horiz_irrad"],
                                              diffuse_solar=data["diffuse_horiz_irrad"],
                                              azim=azimuth,
                                              elev=elevation,
                                              latitude=latitude,
                                              longitude=longitude,
                                              timezone=timezone,
                                              altitude=altitude
                                              )

    data["global_tilted_irrad"] = global_tilted
    data["direct_tilted_irrad"] = direct_tilted
    data["diffuse_tilted_irrad"] = diffuse_tilted
    data["theta"] = theta # incidence angle

    # compute PV system AC power output
    pv_power = pv_system(direct_tilted_irrad = data["direct_tilted_irrad"],
                        diffuse_tilted_irrad = data["diffuse_tilted_irrad"],
                        theta = data["theta"],
                        T_air = data["T_air"],
                        wind_speed = data["wind_speed"],
                        module=pv_module,
                        mounting=pv_mounting
                        )
    data["pv_power"] = pv_power

    # compute collector heat output
    collector_heat = collector_system(direct_tilted_irrad = data["direct_tilted_irrad"],
                                      diffuse_tilted_irrad = data["diffuse_tilted_irrad"],
                                      theta = data["theta"],
                                      T_air = data["T_air"],
                                      collector = collector,
                                      T_m = T_m
                                      )
    data["collector_heat"] = collector_heat

    return data
