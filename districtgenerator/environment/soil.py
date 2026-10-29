"""
Undisturbed soil temperature at the installation depth of thermal networks.
"""
import cmath

import numpy as np
import scipy.optimize as opt


def calculate_soil_temperature(data, dt):
    """
    Calculate the undisturbed soil-temperature profile at network depth.

    Derive an annual harmonic soil-temperature profile from outdoor air
    temperature, wind speed, relative humidity, global solar radiation,
    and sky temperature. The model accounts for either a soil surface or
    an asphalt surface layer and evaluates the temperature at the network
    installation depth.

    Parameters
    ----------
    data : object
        DistrictGenerator data object. Required weather series are read
        from ``data.site``:

        - ``"T_e"``: outdoor air temperature [°C].
        - ``"wind_speed"``: wind speed [m/s].
        - ``"r_humidity"``: relative humidity [%].
        - ``"SunTotal"``: global solar irradiance [W/m²].
        - ``"pressure"``: air pressure [hPa].

        Ground parameters are read from ``data.heat_grid_data``, including
        ``"asphaltlayer"``, ``"k_soil"``, ``"d_asph"``, and
        ``"grid_depth"``.
    dt : float
        Temporal resolution of the input series in hours.

    Returns
    -------
    object
        The same ``data`` object. The calculated soil-temperature time
        series [°C] is stored in
        ``data.heat_grid_data["T_soil"]``.

    """

    # LOAD WEATHER DATA
    weather = {}
    weather["T_air"] = data.site["T_e"]  # Air temperatur °C
    weather["v_wind"] = data.site["wind_speed"]  # Wind Velocity m/s
    weather["r"] =  data.site["r_humidity"] / 100  # relative humidity -
    weather["G"] = data.site["SunTotal"]  # Global radiation W/m^2
    weather["p"] = data.site["pressure"]  # air pressure hPa

    # Calculate the total number of time steps in one year
    num_timesteps = int(365 * (24 / dt))
    # Create an array of times in hours, shifted so that the first time is 1 hour.
    time_in_hours = 1 + np.arange(num_timesteps) * dt
    # Calculate the hour-of-day values
    hours_year = time_in_hours % 24

    # Calculate the dew point temperature (Ts) using the Magnus formula:
    alpha = np.log(weather["r"]) + (17.62 * weather["T_air"] / (243.12 + weather["T_air"]))
    weather["T_dp"] = (243.04 * alpha) / (17.625 - alpha)  # dew point temperatur °C

    # Calculate T_sky based on http://dx.doi.org/10.1016/j.renene.2015.06.020
    weather["T_sky"] = (weather["T_air"] + 273.15) * ((0.711 + 0.0056 * weather["T_dp"] + 0.000073 * weather["T_dp"] ** 2 + 0.013 * np.cos(15 * hours_year)) ** 0.25) - 273.15  # sky temperature °C

    # Cosinus Fit of G, T_air and T_sky: X = mean - amp * cos(omega*t - phase)
    G_mean, G_amp, G_phase = cosFit(weather["G"], dt)
    Tair_mean, Tair_amp, Tair_phase = cosFit(weather["T_air"], dt)
    Tsky_mean, Tsky_amp, Tsky_phase = cosFit(weather["T_sky"], dt)


    # Convective heat transfer at surface W/(m^2*K):
    # Since the forced convection mode is dominant with 7867 h per year (Source: https://doi.org/10.1016/j.solener.2014.07.015),
    # the convective heat transfer can be calculated based on McAdams correlations.
    # Mc Adams correlation is suggested by M. Ouzzane (2014): Analysis of the convective heat exchange effect on the undisturbed ground temperature
    # https://doi.org/10.1016/j.solener.2014.07.015
    weather["alpha_conv"] = np.zeros(len(weather["v_wind"]))
    for t in range(len(weather["v_wind"])):
        if weather["v_wind"][t] <= 4.88:
            weather["alpha_conv"][t] = 5.7 + 3.8 * weather["v_wind"][t]**0.5
        else:
            weather["alpha_conv"][t] = 7.2*weather["v_wind"][t]**0.78
    alpha_conv = np.mean(weather["alpha_conv"])


    # mean relative air humidity
    r = np.mean(weather["r"])

    # get ground parameters
    omega = 2 * np.pi / 365 # angular frequency

    if data.heat_grid_data["asphaltlayer"] == 0:  # no asphalt layer, only soil
        alpha_s = 0.9                                                           #---,       soil surface absorptance Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        epsilon_s = 0.9                                                         #---,       soil surface emissivity. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        f = 0.7                                                                 #---,       soil surface evaporation rate. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        k_soil = data.heat_grid_data["k_soil"]                              # W/(m*K),  soil heat conductivity
        k = k_soil
        c_soil = 2.4e6                                                          # J/(m^3*K),soil volumetric heat capacity. Source: Table 1.1 Wessolek, G. (2022). Parametrisierung thermischer Bodeneigenschaften: Endbericht
        delta_s = (2 * (k_soil / c_soil * 3600 * 24) / omega) ** 0.5            # m,  surface damping depth. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        delta_soil = delta_s
    else:  # with asphalt layer at surface
        alpha_s = 0.93                                                          #---,        asphalt surface absorptance. Source: VDI Wärmeatlas
        epsilon_s = 0.93                                                        #---,        asphalt surface emissivity. Source: VDI Wärmeatlas
        f =  0.3                                                                #---,        asphalt surface evaporation rate. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020 (assumed like the dry soil)
        k_asph = 0.76                                                           # W/(m*K),   asphalt heat conductivity. Source: VDI Wärmeatlas
        k_soil = data.heat_grid_data["k_soil"]                              # W/(m*K),  soil heat conductivity
        k = k_asph
        c_asph = 2100000                                                        # J/(m^3*K), asphalt volumetric heat capacity. Source: VDI Wärmeatlas
        c_soil = 2.4e6                                                          # J/(m^3*K),soil volumetric heat capacity. Source: Table 1.1 Wessolek, G. (2022). Parametrisierung thermischer Bodeneigenschaften: Endbericht
        delta_s = (2 * (k_asph / c_asph * 3600 * 24) / omega) ** 0.5            # m,    surface damping depth (= asphalt). Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        delta_soil = (2 * (k_soil / c_soil * 3600 * 24) / omega) ** 0.5         # m,    soil damping depth. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020

    # Calculate and return time series of soil temperature in grid depth
    # Model by M. Badache (2015): A new modeling approach for improved ground temperature profile determination
    # http://dx.doi.org/10.1016/j.renene.2015.06.020

    # simple correlation for average surface temperature
    Ts_mean = (12.5 + 0.951 * (Tair_mean + 273.15)) - 273.15   # Adjusted to reach 10°C in a depth of 14 m

    # long-wave radiation heat transfer
    alpha_rad = epsilon_s * 5.67e-8 * (Ts_mean + 273.15 + Tsky_mean + 273.15) * ((Ts_mean + 273.15) ** 2 + (Tsky_mean + 273.15) ** 2)

    h_e = alpha_conv * (1 + 103 * 0.0168 * f) + alpha_rad
    h_r = alpha_conv * (1 + 103 * 0.0168 * f * r)

    # Calculating the amplitude of the ground surface temperature and the phase angle difference between the air and the ground surface temperature
    num = (h_r * Tair_amp + alpha_s * cmath.rect(G_amp, Tair_phase - G_phase) + alpha_rad * cmath.rect(Tsky_amp, Tair_phase - Tsky_phase))
    denom = (h_e + k * ((1 + 1j) / delta_s))
    z = num / denom
    Ts_amp = abs(z) # amplitude of the ground surface temperature
    Ts_phase = Tair_phase + cmath.phase(z) # phase angle difference between the air and the ground surface temperature

    # Calculate soil temperature in grid depth
    d = data.heat_grid_data["d_asph"]    # m asphalt layer thickness
    t = data.heat_grid_data["grid_depth"] # m installation depth beneath surface
    omega = 2 * np.pi / 365 / 24
    time = np.arange(dt, 8760 + dt, dt)  # time array in hours

    if data.heat_grid_data["asphaltlayer"] == 0:  # no asphalt
        weather["T_soil"] = Ts_mean - Ts_amp * np.exp(-t / delta_soil) * np.cos(omega * time - Ts_phase - t / delta_soil)
    else:  # with asphalt layaer
        if t > d:  # grid is below asphalt layer
            weather["T_soil"] = Ts_mean - Ts_amp * np.exp(-d / delta_s) * np.exp(-(t - d) / delta_soil) * np.cos(omega * time - Ts_phase - d / delta_s - (t - d) / delta_soil)
        else:  # grid is within asphalt layer
            weather["T_soil"] = Ts_mean - Ts_amp * np.exp(-t / delta_s) * np.cos(omega * time - Ts_phase - t / delta_s)

    # plt.plot(time/24, weather["T_soil"])
    # plt.show()

    # return time series of soil temperature
    data.heat_grid_data["T_soil"] = weather["T_soil"]

    return data


def cosFit(data, dt):
    """
    Fit a one-year cosine function to a time series by least squares.

    Parameters
    ----------
    data : array_like
        One-dimensional time series to fit. Values may represent any
        physical quantity; the fitted mean and amplitude retain the same
        unit as ``data``.
    dt : float
        Temporal spacing between consecutive values in hours.

    Returns
    -------
    mean : float
        Fitted annual mean, in the same unit as ``data``.
    amp : float
        Fitted cosine amplitude, in the same unit as ``data``.
    phase : float
        Fitted phase angle in radians.
    """
    omega = 2 * np.pi / 8760
    time = np.arange(len(data)) * dt

    start_mean = np.mean(data) # initial guess for the mean of the cosine function
    start_amp = np.std(data) * (2 ** 0.5) # initial guess for the amplitude
    start_phase = 0 # The initial guess for the phase shift is set to 0

    func = lambda x: x[0] - x[1] * np.cos(omega * time - x[2]) - data # difference between the model and the actual data for each time point
    # Minimizing the difference (in the least-squares sense)
    # adjust the parameters so that the cosine function best
    # fits the observed data
    mean, amp, phase = opt.leastsq(func, [start_mean, start_amp, start_phase])[0]

    return mean, amp, phase
