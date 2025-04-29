import numpy as np
import math
import scipy.optimize as opt
import cmath
import matplotlib.pyplot as plt

def heating_network(data):

    heat_grid_data = data.heat_grid_data
    timeData = data.time
    dt = timeData["timeResolution"] / timeData["dataResolution"]

    # LOAD DEMANDS
    for b in range(len(data.district)):
        if b == 0:
            heating = data.district[b]["user"].heat / 1000  # kW
            cooling = data.district[b]["user"].cooling / 1000  # kW
            dhw = data.district[b]["user"].dhw / 1000  # kW
            generationSTC = data.district[b]["generationSTC"] / 1000  # kW

        else:
            heating += data.district[b]["user"].heat / 1000  # kW
            cooling += data.district[b]["user"].cooling / 1000  # kW
            dhw += data.district[b]["user"].dhw / 1000  # kW
            generationSTC += data.district[b]["generationSTC"] / 1000  # kW


    heat_grid_data["net_heating_demand"] = heating + dhw - generationSTC  # kW
    heat_grid_data["net_cooling_demand"] = cooling  # kW
    heat_grid_data["net_sum_heating_demand"] = sum(heat_grid_data["net_heating_demand"]) * dt  # kWh/year
    heat_grid_data["net_sum_cooling_demand"] = sum(heat_grid_data["net_cooling_demand"]) * dt  # kWh/year

#    plot(data)
    data = calc_costs(data)
    data = calc_annual_investment(data)
    data = calculate_soil_temperature(data, dt)
    data = calculate_thermal_losses(data)


    return data

def calc_costs(data):
    """
    Calculates pipe dimensions and specific annualized costs for a district heating and cooling network

    Methodology:
    - Based on empirical formulas derived from statistical analysis of Danish district heating networks
      as described in Luis Sánchez-García et al. (2023), "Understanding effective width for district heating."
    - Pipe lengths and diameters are estimated using fitting formulas dependent on building density.

    Source:
    - Luis Sánchez-García et al. (2023), "Understanding effective width for district heating," Energy journal.
    """

    # Todo (put this in the json file)
    FAR = 1.17  # Floor area ratio (German: Geschossflächenzahl); Source:  EST 8b Dettmar, J.,et al., 2020. Energetische Stadtraumtypen

    # Calculate Total Building Floor Area
    total_area = 0
    for building in data.district:
        total_area += building["buildingFeatures"].area

    # Calculate Land Area (AL) in hectares
    AL = total_area / FAR / 10000 # ha

    number_of_buildings = len(data.district)

    # G represents the inequality of building distribution.
    # G = 0 assumes perfectly even distribution of buildings.
    # (Based on "Understanding effective width for district heating", Sánchez-García et al., 2023.)
    G = 0

    # Estimate Required Pipe Length per hectare
    l_dist_perha = 213 / (1 + 2.5 * np.exp(-0.34 * number_of_buildings)) - 25 - 40 * G # Distribution pipes [m/ha]
    l_serv_perha = 163 / (1 + 3.9 * np.exp(-0.34 * number_of_buildings)) - 11 - 30 * G # Service pipes [m/ha]

    # Total Required Pipe Lengths
    data.heat_grid_data["length_dist"] = l_dist_perha * AL   # [m]
    data.heat_grid_data["length_serv"] = l_serv_perha * AL   # [m]

    # --- Heating network
    # Calculate linear Heat Densities
    linear_heat_density_dist = data.heat_grid_data["net_sum_heating_demand"]/data.heat_grid_data["length_dist"]/1000/1000*3600 # GJ/(m*a)
    linear_heat_density_serv = data.heat_grid_data["net_sum_heating_demand"]/data.heat_grid_data["length_serv"]/1000/1000*3600 # GJ/(m*a)

    # Calculate required Nominal Diameters (DN)
    DN_heating_dist = 21.255 * np.log(linear_heat_density_dist) + 48.064
    DN_heating_serv = 19.983 * np.exp(0.021 * linear_heat_density_serv)

    # Select Next Larger Available Pipe Size ---
    larger_DN_dist = data.pipe_data[data.pipe_data["Nominal diameter (DN)"] >= DN_heating_dist]
    chosen_row_dist = larger_DN_dist.loc[larger_DN_dist["Nominal diameter (DN)"].idxmin()]
    data.heat_grid_data["DN_heating_dist"] = chosen_row_dist["Nominal diameter (DN)"]
    data.heat_grid_data["da_heating_dist"] = chosen_row_dist["Outer diameter (pipe) (mm)"]
    data.heat_grid_data["di_heating_dist"] = chosen_row_dist["Outer diameter (pipe) (mm)"] - 2 * chosen_row_dist["Thickness (pipe) (mm)"]
    data.heat_grid_data["Da_heating_dist"] = chosen_row_dist["Outer diameter (case) (mm)"]  # outer diameter of the pipe including insulation

    larger_DN_serv = data.pipe_data[data.pipe_data["Nominal diameter (DN)"] >= DN_heating_serv]
    chosen_row_serv = larger_DN_serv.loc[larger_DN_serv["Nominal diameter (DN)"].idxmin()]
    data.heat_grid_data["DN_heating_serv"] = chosen_row_serv["Nominal diameter (DN)"]
    data.heat_grid_data["da_heating_serv"] = chosen_row_serv["Outer diameter (pipe) (mm)"]
    data.heat_grid_data["di_heating_serv"] = chosen_row_serv["Outer diameter (pipe) (mm)"] - 2 * chosen_row_dist["Thickness (pipe) (mm)"]
    data.heat_grid_data["Da_heating_serv"] = chosen_row_serv["Outer diameter (case) (mm)"]  # outer diameter of the pipe including insulation

    # Heating Network Installation Cost
    C_heating_network = (323.579 + 4.267 * data.heat_grid_data["DN_heating_dist"]) * data.heat_grid_data["length_dist"] + (323.579 + 4.267 * data.heat_grid_data["DN_heating_serv"]) * \
                        data.heat_grid_data["length_serv"]  # €


    # --- Cooling network
    # Calculate linear Heat Densities
    linear_cool_density_dist = data.heat_grid_data["net_sum_cooling_demand"] / data.heat_grid_data["length_dist"] / 1000 / 1000 * 3600  # GJ/(m*a)
    linear_cool_density_serv = data.heat_grid_data["net_sum_cooling_demand"] / data.heat_grid_data["length_serv"] / 1000 / 1000 * 3600  # GJ/(m*a)
    if linear_cool_density_dist > 0:
        # Calculate required Nominal Diameters (DN)
        DN_cooling_dist = 21.255 * np.log(linear_cool_density_dist) + 48.064
        DN_cooling_serv = 19.983 * np.exp(0.021 * linear_cool_density_serv)

        # Select Next Larger Available Pipe Size ---
        larger_DN_dist = data.pipe_data[data.pipe_data["Nominal diameter (DN)"] >= DN_cooling_dist]
        chosen_row_dist = larger_DN_dist.loc[larger_DN_dist["Nominal diameter (DN)"].idxmin()]
        data.heat_grid_data["DN_cooling_dist"] = chosen_row_dist["Nominal diameter (DN)"]
        data.heat_grid_data["da_cooling_dist"] = chosen_row_dist["Outer diameter (pipe) (mm)"]
        data.heat_grid_data["di_cooling_dist"] = chosen_row_dist["Outer diameter (pipe) (mm)"] - 2 * chosen_row_dist["Thickness (pipe) (mm)"]
        data.heat_grid_data["Da_cooling_dist"] = chosen_row_dist["Outer diameter (case) (mm)"]  # outer diameter of the pipe including insulation

        larger_DN_serv = data.pipe_data[data.pipe_data["Nominal diameter (DN)"] >= DN_cooling_serv]
        chosen_row_serv = larger_DN_serv.loc[larger_DN_serv["Nominal diameter (DN)"].idxmin()]
        data.heat_grid_data["DN_cooling_serv"] = chosen_row_serv["Nominal diameter (DN)"]
        data.heat_grid_data["da_cooling_serv"] = chosen_row_serv["Outer diameter (pipe) (mm)"]
        data.heat_grid_data["di_cooling_serv"] = chosen_row_serv["Outer diameter (pipe) (mm)"] - 2 * chosen_row_dist["Thickness (pipe) (mm)"]
        data.heat_grid_data["Da_cooling_serv"] = chosen_row_serv["Outer diameter (case) (mm)"]  # outer diameter of the pipe including insulation

        # Cooling Network Installation Cost
        C_cooling_network = (323.579 + 4.267 * data.heat_grid_data["DN_cooling_dist"]) * data.heat_grid_data["length_dist"] + (323.579 + 4.267 * data.heat_grid_data["DN_cooling_serv"]) * \
                        data.heat_grid_data["length_serv"]  # €

    else:
        # No cooling network needed
        data.heat_grid_data["DN_cooling_dist"] = 0 # m
        data.heat_grid_data["DN_cooling_serv"] = 0 # m
        C_cooling_network = 0 # €

    # Substation Costs
    C_substations = 0
    for building in data.district:
        substation_capacity = max(building["envelope"].heatload/1000 + building["dhwpower"]/1000, max(building["user"].cooling)/1000)  #kW
        substation_costs = substation_capacity * data.heat_grid_data["C_subst"]["value"]
        C_substations += substation_costs

    # Total Network Costs
    data.heat_grid_data["costs"] = C_heating_network + C_cooling_network + C_substations # €

    return data

def calculate_thermal_losses(data):
    """

    Calculate thermal losses in heating grid and cooling grid, which are
    assumed to be consisting of separate pre-insulated pipes (single pipes).
    Thermal loss calculation is based on DIN EN 13941 pair of single pipes.
    The interaction between the pipes is accounted for using the multipole
    method, which models the heat loss as a superposition of symmetrical
    and antisymmetrical cases.

    """

    #%% Losses in the heating network

    # get heating network parameters
    T_hot_heating_network = data.heat_grid_data["T_hot_heating_network"]["value"]
    T_cold_heating_network = data.heat_grid_data["T_cold_heating_network"]["value"]

    D_heating_network = data.heat_grid_data["D_heating_network"]["value"] # Distance between the centerlines of the supply and return pipelines

    k_soil = data.heat_grid_data["k_soil"]["value"]  # W/(m*K),
    k_is =data.heat_grid_data["k_PUF"]["value"]   # W/(m*K)
    Z_c =  data.heat_grid_data["grid_depth"]["value"] + 0.069 * k_soil
    b = np.log((1+(2*Z_c/D_heating_network)**2)**0.5)

    Ts_heating_network = (T_hot_heating_network + T_cold_heating_network) / 2
    Ta_heating_network = (T_hot_heating_network - T_cold_heating_network) / 2

    # Losses in the distribution pipes

    a_dist = np.log(4 * Z_c / (data.heat_grid_data["Da_heating_dist"]/1000))
    beta_dist =  k_soil / k_is * np.log((data.heat_grid_data["Da_heating_dist"]) / data.heat_grid_data["da_heating_dist"])

    ks_heating_network_dist = (a_dist + beta_dist + b)**-1
    ka_heating_network_dist = (a_dist + beta_dist - b)**-1

    qs_heating_network_dist = (Ts_heating_network- data.heat_grid_data["T_soil"]) * 2 * np.pi * k_soil * ks_heating_network_dist  # W/m
    qa_heating_network_dist = (Ta_heating_network) * 2 * np.pi * k_soil * ka_heating_network_dist          # W/m

    losses_hotpipe_heating_network_dist = (qs_heating_network_dist + qa_heating_network_dist) * data.heat_grid_data["length_dist"]
    losses_coldpipe_heating_network_dist = (qs_heating_network_dist - qa_heating_network_dist) * data.heat_grid_data["length_dist"]
    losses_heating_network_dist = (losses_hotpipe_heating_network_dist + losses_coldpipe_heating_network_dist) / 1000  # kW

    # Losses in the service pipes

    a_serv = np.log(4 * Z_c / (data.heat_grid_data["Da_heating_serv"]/1000))
    beta_serv =  k_soil / k_is * np.log((data.heat_grid_data["Da_heating_serv"]) / data.heat_grid_data["da_heating_serv"])

    ks_heating_network_serv = (a_serv + beta_serv + b)**-1
    ka_heating_network_serv = (a_serv + beta_serv - b)**-1

    qs_heating_network_serv = (Ts_heating_network- data.heat_grid_data["T_soil"]) * 2 * np.pi * k_soil * ks_heating_network_serv  # W/m
    qa_heating_network_serv = (Ta_heating_network) * 2 * np.pi * k_soil * ka_heating_network_serv          # W/m

    losses_hotpipe_heating_network_serv = (qs_heating_network_serv + qa_heating_network_serv) * data.heat_grid_data["length_serv"]
    losses_coldpipe_heating_network_serv = (qs_heating_network_serv - qa_heating_network_serv) * data.heat_grid_data["length_serv"]
    losses_heating_network_serv = (losses_hotpipe_heating_network_serv + losses_coldpipe_heating_network_serv) / 1000  # kW

    # Losses in the substations
    losses_substations_heating = data.heat_grid_data["h_loss_subst"]["value"]/100 * data.heat_grid_data["net_heating_demand"]

    # total losses in the heating network
    data.heat_grid_data["total_losses_heating_network"] = losses_heating_network_dist + losses_heating_network_serv + losses_substations_heating # kW

    #%% Losses in the cooling network

    # get cooling network parameters (if a network exists)
    if data.heat_grid_data["net_sum_cooling_demand"] > 0:
        T_hot_cooling_network = data.heat_grid_data["T_hot_cooling_network"]["value"]
        T_cold_cooling_network = data.heat_grid_data["T_cold_cooling_network"]["value"]

        D_cooling_network = data.heat_grid_data["D_cooling_network"]["value"] # distance between hot and cold pipe

        Z_c =  data.heat_grid_data["grid_depth"]["value"] + 0.069 * k_soil
        b = np.log((1+(2*Z_c/D_cooling_network)**2)**0.5)

        Ts_cooling_network = (T_hot_cooling_network + T_cold_cooling_network) / 2
        Ta_cooling_network = (T_hot_cooling_network - T_cold_cooling_network) / 2

        a_dist = np.log(4 * Z_c / (data.heat_grid_data["Da_cooling_dist"]/1000))
        beta_dist =  k_soil / k_is * np.log((data.heat_grid_data["Da_cooling_dist"]) / data.heat_grid_data["da_cooling_dist"])

        ks_cooling_network_dist = (a_dist + beta_dist + b)**-1
        ka_cooling_network_dist = (a_dist + beta_dist - b)**-1

        qs_cooling_network_dist = (Ts_cooling_network- data.heat_grid_data["T_soil"]) * 2 * np.pi * k_soil * ks_cooling_network_dist  # W/m
        qa_cooling_network_dist = (Ta_cooling_network) * 2 * np.pi * k_soil * ka_cooling_network_dist          # W/m

        losses_hotpipe_cooling_network_dist = (qs_cooling_network_dist + qa_cooling_network_dist) * data.heat_grid_data["length_dist"]
        losses_coldpipe_cooling_network_dist = (qs_cooling_network_dist - qa_cooling_network_dist) * data.heat_grid_data["length_dist"]
        losses_cooling_network_dist = (losses_hotpipe_cooling_network_dist + losses_coldpipe_cooling_network_dist) / 1000  # kW

        # Losses in the service pipes

        a_serv = np.log(4 * Z_c / (data.heat_grid_data["Da_cooling_serv"]/1000))
        beta_serv = k_soil / k_is * np.log((data.heat_grid_data["Da_cooling_serv"]) / data.heat_grid_data["da_cooling_serv"])

        ks_cooling_network_serv = (a_serv + beta_serv + b) ** -1
        ka_cooling_network_serv = (a_serv + beta_serv - b) ** -1

        qs_cooling_network_serv = (Ts_cooling_network - data.heat_grid_data["T_soil"]) * 2 * np.pi * k_soil * ks_cooling_network_serv  # W/m
        qa_cooling_network_serv = (Ta_cooling_network) * 2 * np.pi * k_soil * ka_cooling_network_serv  # W/m

        losses_hotpipe_cooling_network_serv = (qs_cooling_network_serv + qa_cooling_network_serv) * data.heat_grid_data["length_serv"]
        losses_coldpipe_cooling_network_serv = (qs_cooling_network_serv - qa_cooling_network_serv) * data.heat_grid_data["length_serv"]
        losses_cooling_network_serv = (losses_hotpipe_cooling_network_serv + losses_coldpipe_cooling_network_serv) / 1000  # kW

        # Losses in the substations
        losses_substations_cooling = data.heat_grid_data["h_loss_subst"]["value"] / 100 * data.heat_grid_data["net_cooling_demand"]

    else:
        losses_cooling_network_dist = np.zeros(len(data.heat_grid_data["T_soil"]))
        losses_cooling_network_serv = np.zeros(len(data.heat_grid_data["T_soil"]))
        losses_substations_cooling = np.zeros(len(data.heat_grid_data["T_soil"]))

    data.heat_grid_data["total_losses_cooling_network"] = losses_cooling_network_dist + losses_cooling_network_serv + losses_substations_cooling # kW

    return data

def calculate_soil_temperature(data, dt):

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

    if data.heat_grid_data["asphaltlayer"]["value"] == 0:  # no asphalt layer, only soil
        alpha_s = 0.9                                                           #---,       soil surface absorptance Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        epsilon_s = 0.9                                                         #---,       soil surface emissivity. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        f = 0.7                                                                 #---,       soil surface evaporation rate. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        k_soil = data.heat_grid_data["k_soil"]["value"]                              # W/(m*K),  soil heat conductivity
        k = k_soil
        c_soil = 2.4e6                                                          # J/(m^3*K),soil volumetric heat capacity. Source: Table 1.1 Wessolek, G. (2022). Parametrisierung thermischer Bodeneigenschaften: Endbericht
        delta_s = (2 * (k_soil / c_soil * 3600 * 24) / omega) ** 0.5            # m,  surface damping depth. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020
        delta_soil = delta_s
    else:  # with asphalt layer at surface
        alpha_s = 0.93                                                          #---,        asphalt surface absorptance. Source: VDI Wärmeatlas
        epsilon_s = 0.93                                                        #---,        asphalt surface emissivity. Source: VDI Wärmeatlas
        f =  0.3                                                                #---,        asphalt surface evaporation rate. Source: http://dx.doi.org/10.1016/j.renene.2015.06.020 (assumed like the dry soil)
        k_asph = 0.76                                                           # W/(m*K),   asphalt heat conductivity. Source: VDI Wärmeatlas
        k_soil = data.heat_grid_data["k_soil"]["value"]                              # W/(m*K),  soil heat conductivity
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
    d = data.heat_grid_data["d_asph"]["value"]    # m asphalt layer thickness
    t = data.heat_grid_data["grid_depth"]["value"] # m installation depth beneath surface
    omega = 2 * np.pi / 365 / 24
    time = np.arange(dt, 8760 + dt, dt)  # time array in hours

    if data.heat_grid_data["asphaltlayer"]["value"] == 0:  # no asphalt
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
    # This function fits a cosine model to a given dataset using
    # a least-squares optimization approach.
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


def calc_annual_investment(data):
    """
    Calculation of total investment costs including replacements (based on VDI 2067-1, pages 16-17).

    Parameters
    ----------
    dev : dictionary
        technology parameter
    param : dictionary
        economic parameters

    Returns
    -------
    annualized fix and variable investment
    """

    observation_time = data.params_ehdo_model["observation_time"]
    interest_rate = data.params_ehdo_model["interest_rate"]
    q = 1 + data.params_ehdo_model["interest_rate"]

    # Calculate capital recovery factor
    CRF = ((q**observation_time)*interest_rate)/((q**observation_time)-1)

    # Get device life time
    life_time = data.heat_grid_data["life_time"]["value"]

    # Number of required replacements
    n = int(math.floor(observation_time / life_time))

    # Investment for replacements
    invest_replacements = sum((q ** (-i * life_time)) for i in range(1, n+1))

    # Residual value of final replacement
    res_value = ((n+1) * life_time - observation_time) / life_time * (q ** (-observation_time))

    # Calculate annualized investments
    if life_time > observation_time:
        data.heat_grid_data["ann_factor"] = (1 - res_value) * CRF
    else:
        data.heat_grid_data["ann_factor"] = ( 1 + invest_replacements - res_value) * CRF


    data.heat_grid_data["CRF"] = CRF
    data.heat_grid_data["ann_costs"] = data.heat_grid_data["costs"] * data.heat_grid_data["ann_factor"] # €/a
    data.heat_grid_data["om_costs"] = data.heat_grid_data["C_O&M"]["value"] * data.heat_grid_data["net_sum_heating_demand"]/1000 + data.heat_grid_data["C_O&M"]["value"] * data.heat_grid_data["net_sum_cooling_demand"]/1000 # €/a

    return data

def plot(data):

    # Parameters
    # Todo (put these in the json file)
    FAR = 1.17  # Floor area ratio (German: Geschossflächenzahl); Source:  EST 8b Dettmar, J.,et al., 2020. Energetische Stadtraumtypen
    site_coverage_ratio = 0.52

    # Calculate Total Building Floor Area
    total_area = 0
    for building in data.district:
        total_area += building["buildingFeatures"].area

    # Calculate Land Area (AL) in m^2
    AL = total_area / FAR   # m^2

    l_w_ratio = 1.5
    length = np.sqrt(AL/l_w_ratio) * l_w_ratio
    width = np.sqrt(AL/l_w_ratio)
    number_of_buildings = len(data.district)
    minimum_spacing_x = 1.5  # Minimum horizontal spacing in meters
    minimum_spacing_y = 10  # Minimum vertical spacing in meters

    # Calculate building footprint area and side length
    total_building_area = AL * site_coverage_ratio
    average_building_area = total_building_area / number_of_buildings
    building_side_length = np.sqrt(average_building_area)

    # Determine how many buildings per row and column
    buildings_per_row = math.floor((length) / (building_side_length + minimum_spacing_x))
    buildings_per_column = math.floor((width) / (building_side_length + minimum_spacing_y))

    # Check if enough slots
    adjustment_needed = False
    if buildings_per_row * buildings_per_column < number_of_buildings:
        adjustment_needed = True

    # Calculate available length and width for spacing
    available_length = length - (buildings_per_row * building_side_length)
    available_width = width - (buildings_per_column * building_side_length)

    spacing_x = available_length / (buildings_per_row)
    spacing_y = available_width / (buildings_per_column)

    # Generate building positions
    positions = []
    for i in range(buildings_per_column):
        for j in range(buildings_per_row):
            if len(positions) < number_of_buildings:
                x = spacing_x/2 + j * (building_side_length + spacing_x)
                y = spacing_y/2 + i * (building_side_length + spacing_y)
                positions.append((x, y))

    # Plotting
    fig, ax = plt.subplots(figsize=(12, 6))

    # Draw black rectangles to represent horizontal roads between buildings
    for i in range(buildings_per_column + 1):
        y_bottom = -spacing_y/2 + spacing_y * (i) + building_side_length * i
        rect = plt.Rectangle((0, y_bottom), length, spacing_y,
                             edgecolor='black', facecolor='black', alpha=1.0)
        ax.add_patch(rect)
        # Always draw dashed white line for every road
        ax.plot([0, length], [y_bottom + spacing_y / 2, y_bottom + spacing_y / 2],
                color='white', linestyle='--', linewidth=1)
        # Only draw blue and red lines if it's between rows of buildings
        # Draw blue and red lines alternately between rows of buildings
        if 0 < i < buildings_per_column and i % 2 == 1:
            ax.plot([building_side_length/2, length-building_side_length/2], [y_bottom + spacing_y / 2 + spacing_y / 4, y_bottom + spacing_y / 2 + + spacing_y / 4],
                    color='#5DADE2', linestyle='-', linewidth=2)
            ax.plot([building_side_length/2, length-building_side_length/2], [y_bottom + spacing_y / 2  + spacing_y / 3, y_bottom + spacing_y / 2 + spacing_y / 3],
                    color='red', linestyle='-', linewidth=2)

    # Calculate total pipe length (only for roads with colored pipes)
    number_of_piped_roads = (buildings_per_column) / 2  # only every second road
    total_pipe_length = number_of_piped_roads * (length - building_side_length)  # only supply pipes


    # Draw buildings
    for x, y in positions:
        rect = plt.Rectangle((x, y), building_side_length, building_side_length,
                             edgecolor='black', facecolor='gray', alpha=0.7)
        ax.add_patch(rect)

    # District boundary
    ax.set_xlim(0, length)
    ax.set_ylim(0, width)
    ax.set_title(f"District (Area = {AL:.0f} m², Length = {length:.0f} m, Width = {width:.0f} m)\n"
                 f"{len(positions)} Buildings: x-spacing = {spacing_x:.1f} m, y-spacing = {spacing_y:.1f} m\n"
                 f"Total Pipe Length = {total_pipe_length:.0f} m")
    ax.set_xlabel('Meters')
    ax.set_ylabel('Meters')
    plt.gca().set_aspect('equal', adjustable='box')
    plt.grid(False)

    # Print some checks
    print(f"District area: {AL} m^2")
    print(f"Length: {length:.2f} m, Width: {width:.2f} m")
    print(f"Building side length: {building_side_length:.2f} m")
    print(f"Spacing x: {spacing_x:.2f} m, Spacing y: {spacing_y:.2f} m")
    print(f"Adjustment needed: {adjustment_needed}")

    plt.show()

