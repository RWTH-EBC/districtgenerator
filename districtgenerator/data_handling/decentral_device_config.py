from pydantic_settings import BaseSettings, SettingsConfigDict


class DecentralDeviceConfig(BaseSettings):
    """Configuration for decentralized devices in a district energy system.

    This class defines the default parameters for various decentralized devices such as
    heat pumps (HP), electric heaters (EH), gas boilers (BOI),
    combined heat and power plants (CHP), fuel cells (FC), photovoltaics (PV),
    solar thermal collectors (STC), thermal energy storage (TES),
    battery storage (BAT), and electric vehicles (EV).

    Each device has parameters such as efficiency, lifetime, investment costs,
    and operational characteristics.
    """

    # CC Parameters (Air-to-Water Compression Chiller)
    CC_grade: float = 0.4      # Quality grade. Ratio of the achieved coefficient of performance to the Carnot coefficient of performance.
    CC_life_time: int = 20     # Maximum life time in years.
    CC_inv_var: float = 700    # Variable investment costs in €/kW.
    CC_cost_om: float = 0.02   # Operation and maintenance costs as a fraction of investment costs in 1/year.

    # HP parameters (Air Source Heat Pump)
    HP_grade: float = 0.4      # Quality grade. Ratio of the achieved coefficient of performance to the Carnot coefficient of performance.
    HP_life_time: int = 20     # Maximum life time in years.
    HP_inv_var: float = 1950   # Variable investment costs in €/kWth.
    HP_cost_om: float = 0.02   # Operation and maintenance costs as a fraction of investment costs in 1/year.

    # EH parameters (Electric Heater)
    # Definition: Electric heating device for bivalent operation in combination with the heat pump.
    EH_eta_th: float = 1.0     # Thermal efficiency.
    EH_life_time: int = 25     # Maximum life time in years.
    EH_inv_var: float = 620    # Variable investment costs in €/kW.
    EH_cost_om: float = 0.0096 # Operation and maintenance costs as a fraction of investment costs in 1/year.

    # BOI parameters (Gas Boiler)
    BOI_eta_th: float = 0.99   # Thermal efficiency.
    BOI_life_time: int = 20    # Maximum life time in years.
    BOI_inv_var: float = 420   # Variable investment costs in €/kW.
    BOI_cost_om: float = 0.031 # Operation and maintenance costs as a fraction of investment costs in 1/year.

    # BBOI parameters (Biomass Boiler)
    BBOI_eta_th: float = 0.90    # Thermal efficiency.
    BBOI_life_time: int = 20     # Maximum life time in years.
    BBOI_inv_var: float = 2200   # Variable investment costs in €/kW
    BBOI_cost_om: float = 0.0095 # Operation and maintenance costs as a fraction of investment costs in 1/year.
    
    # OBOI parameters (Oil Boiler)
    OBOI_eta_th: float = 0.92    # Thermal efficiency.
    OBOI_life_time: int = 20     # Maximum life time in years.
    OBOI_inv_var: float = 779    # Variable investment costs in €/kW.
    OBOI_cost_om: float = 0.036  # Operation and maintenance costs as a fraction of investment costs in 1/year.

    # H2BOI parameters (Hydrogen Boiler)
    H2BOI_eta_th: float = 0.994  # Thermal efficiency.
    H2BOI_life_time: int = 20    # Maximum life time in years.
    H2BOI_inv_var: float = 390   # Variable investment costs in €/kW.
    H2BOI_cost_om: float = 0.03  # Operation and maintenance costs as a fraction of investment costs in 1/year.

    # CHP parameters (Combined Heat and Power)
    # Definition: Gas based combined heat and power plant.
    CHP_eta_th: float = 0.62    # Thermal efficiency.
    CHP_eta_el: float = 0.30    # Electrical efficiency.
    CHP_life_time: int = 15     # Maximum life time in years.
    CHP_inv_var: float = 3500   # Variable investment costs in €/kW.
    CHP_cost_om: float = 0.05   # Operation and maintenance costs as a fraction of total investment costs (percentage).

    # DH parameters (District Heating Connection)
    DH_eta_th: float = 1.0      # Thermal efficiency.
    DH_life_time: int = 30      # Maximum life time in years.
    DH_inv_var: float = 60.93   # Variable investment costs in €/kW.
    DH_cap_fee: float = 0.0     # Capacity fee in €/kW/year.

    # FC parameters (Fuel Cell)
    # Definition: Gas based fuel cell.
    FC_eta_th: float = 0.53     # Thermal efficiency.
    FC_eta_el: float = 0.39     # Electrical efficiency.
    FC_life_time: int = 20      # Maximum life time in years.
    FC_inv_var: float = 390     # Variable investment costs in €/kW.
    FC_cost_om: float = 0.03    # Operation and maintenance costs as a fraction of total investment costs (percentage).

    # PV parameters (Photovoltaics)
    PV_area_real: float = 1.6       # Module area in squaremeters.
    PV_eta_el_ref: float = 0.199    # Electrical efficiency under reference conditions.
    PV_t_cell_ref: int = 25         # Reference cell temperature in degree Celsius.
    PV_G_ref: int = 1000            # Reference solar irradiance in Watt per squaremeter.
    PV_t_cell_noct: int = 44        # Cell temperature under normal operating cell temperature (NOCT) conditions in degree Celsius.
    PV_t_air_noct: int = 20         # Ambient air temperature under normal operating cell temperature (NOCT) conditions in degree Celsius.
    PV_G_noct: int = 800            # Irradiance under normal operating cell temperature (NOCT) conditions in Watt per squaremeter.
    PV_gamma: float = 0.003         # Temperature coefficient of power loss in Percent per Kelvin.
    PV_eta_inv: float = 0.96        # Inverter efficiency.
    PV_eta_opt: float = 0.9         # Optical efficiency.
    PV_P_nominal: float = 220.0     # Reference power per squaremeter, used for Battery sizing, in Watt per squaremeter.
    PV_life_time: int = 25          # Maximum life time in years.
    PV_inv_var: int = 250           # Variable investment costs in €/m^2.
    PV_cost_om: float = 0.015       # Operation and maintenance costs as a fraction of investment costs in 1/year.
    PV_kappa_inverter: float = 0.02 # Correction factor for inverter losses
    PV_kappa_wiring: float = 0.015    # Correction factor for wiring losses
    PV_kappa_connections: float = 0.005   # Correction factor for all losses in connectors
    PV_kappa_soiling: float = 0.02        # Correction factor for losses due to soiling
    PV_kappa_shading: float = 0.03        # Correction factor for losses due to shading
    PV_kappa_mismatch: float = 0.02      # Correction factor for mismatch losses (production deviations between modules)
    PV_kappa_NPR: float = 0.01            # Correction factor for name plate rating losses (deviation of the power rating from the actual power)
    PV_kappa_av: float = 0.025             # Correction factor for losses to to non-availability of the system (e.g. maintenance, redispatch, etc.)
    PV_kappa_LID: float = 0.015            # Correction factor for mismatch losses (production deviations between modules)



    # STC parameters (Solar Thermal Collector)
    STC_T_flow: int = 50                    # Flow temperature in degree Celsius.
    STC_zero_loss: float = 0.786            # Optical efficiency (zero loss collector efficiency).
    STC_first_order: float = 0.003345       # First order loss coefficient (linear thermal losses) in Watt per squaremeter per Kelvin.
    STC_second_order: float = 0.0000142     # Second order loss coefficient (quadratic thermal losses) in Watt per squaremeter per Kelvin square.
    STC_life_time: int = 20                 # Maximum life time in years.
    STC_inv_var: int = 400                  # Variable investment costs in €/m^2.
    STC_cost_om: float = 0.05               # Operation and maintenance costs as a fraction of total investment costs (percentage).

    # TES parameters (Thermal Energy Storage)
    TES_soc_min: float = 0.0            # Minimum state of charge.
    TES_soc_max: float = 1.0            # Maximum state of charge.
    TES_eta_standby: float = 0.97       # Standby hourly efficiency (accounts for self-discharge).
    TES_eta_ch: float = 1.0             # Charging and discharging efficiency.
    TES_coeff_ch: float = 10000.0       # Charging and discharging coefficient in Watt per Watthour.
    TES_init: float = 0.5               # Initial state of charge.
    TES_T_diff_max: int = 35            # Maximum temperature difference in degree Celsius.
    TES_life_time: int = 20             # Maximum life time in years.
    TES_inv_var: float = 11             # Variable investment costs in €/liter.
    TES_cost_om: float = 0.013          # Operation and maintenance costs as a fraction of investment costs in 1/year.

    # BAT parameters (Battery Storage)
    BAT_soc_min: float = 0.0        # Minimum state of charge.
    BAT_soc_max: float = 0.95       # Maximum state of charge.
    BAT_eta_standby: float = 0.97   # Standby hourly efficiency (accounts for self-discharge).
    BAT_eta_ch: float = 0.97        # Charging and discharging efficiency.
    BAT_coeff_ch: float = 0.8       # Charging and discharging coefficient in Watt per Watthour.
    BAT_init: float = 0.5           # Initial state of charge.
    BAT_life_time: int = 15         # Maximum life time in years.
    BAT_inv_var: float = 850        # Variable investment costs in €/kWh.
    BAT_cost_om: float = 0.05       # Operation and maintenance costs as a fraction of total investment costs (percentage).

    # EV parameters (Electric Vehicle)
    EV_soc_min: float = 0.05        # Minimum state of charge.
    EV_soc_max: float = 0.95        # Maximum state of charge.
    EV_eta_standby: float = 1.0     # Standby hourly efficiency (accounts for self-discharge).
    EV_eta_ch: float = 0.97         # Charging and discharging efficiency.
    EV_coeff_ch: float = 0.15       # Charging and discharging coefficient in Watt per Watthour.
    EV_init: float = 0.9            # Initial state of charge.
    EV_life_time: int = 20          # Maximum life time in years.
    EV_inv_var: float = 0           # Variable investment costs in €/kWh.
    EV_cost_om: float = 0.0         # Operation and maintenance costs as a fraction of total investment costs (percentage).

    # Investment data parameters
    inv_data_observation_time: int = 20     # Observation time in years.
    inv_data_interest_rate: float = 0.05    # Interest rate.

    model_config = SettingsConfigDict(
        env_prefix="D_",
        env_file=".decentraldeviceconfig",
        extra="allow"
    )