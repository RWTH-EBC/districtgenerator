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

    Attributes
    ----------
    Descriptions directly in Class.

    """

    # HP parameters (Air Source Heat Pump)
    HP_grade: float = 0.4       # Quality grade. Ratio of the achieved coefficient of performance to the Carnot coefficient of performance between 0 and 1.
    HP_life_time: int = 18      # Maximum life time in years.
    HP_inv_var: int = 1000      # Investment variable in €/liter.
    HP_cost_om: float = 0.05    # Cost of operation and maintenance as a percentage of investment.

    # EH parameters (Electric Heater)
    # Definition: Electric heating device for bivalent operation in combination with the heat pump.
    EH_eta_th: float = 1.0      # Thermal efficiency between 0 and 1.

    # BOI parameters (Gas Boiler)
    BOI_eta_th: float = 0.97    # Thermal efficiency between 0 and 1.
    BOI_life_time: int = 20     # Maximum life time in years.
    BOI_inv_var: int = 130      # Investment variable in €/kW.
    BOI_cost_om: float = 0.05   # Cost of operation and maintenance as a percentage of investment.

    # CHP parameters (Combined Heat and Power)
    # Definition: Gas based combined heat an power plant.
    CHP_eta_th: float = 0.62    # Thermal efficiency between 0 and 1.
    CHP_eta_el: float = 0.30    # Electrical efficiency between 0 and 1.
    CHP_life_time: int = 15     # Maximum life time in years.
    CHP_inv_var: int = 3500     # Investment variable in €/kW.
    CHP_cost_om: float = 0.05   # Cost of operation and maintenance as a percentage of investment.

    # FC parameters (Fuel Cell)
    # Definition: Gas based fuel cell.
    FC_eta_th: float = 0.53     # Thermal efficiency between 0 and 1.
    FC_eta_el: float = 0.39     # Electrical efficiency between 0 and 1

    # PV parameters (Photovoltaics)
    PV_area_real: float = 1.6       # Module area in square meters.
    PV_eta_el_ref: float = 0.199    # Electrical efficiency under reference conditions between 0 and 1.
    PV_t_cell_ref: int = 25         # Reference ambient temperature in degree Celsius.
    PV_G_ref: int = 1000            # Reference solar irradiance in Watt per square meter.
    PV_t_cell_noct: int = 44        # Cell temperature under normal test conditions (NOCT) in degree Celsius.
    PV_t_air_noct: int = 20         # Ambient air temperature under normal test conditions (NOCT) in degree Celsius.
    PV_G_noct: int = 800            # Irradiance under normal test conditions (NOCT) in Watt per square meter.
    PV_gamma: float = 0.003         # Loss coefficient in percent per Kelvin.
    PV_eta_inv: float = 0.96        # Inverter efficiency between 0 and 1.
    PV_eta_opt: float = 0.9         # Optical efficiency between 0 and 1.
    PV_P_nominal: float = 220.0     # Reference power per square meter, used for Battery sizing.
    PV_life_time: int = 25          # Maximum life time in years.
    PV_inv_var: int = 340           # Investment variable in €/m^2.
    PV_cost_om: float = 0.05         # Cost of operation and maintenance as a percentage of investment.

    # STC parameters (Solar Thermal Collector)
    STC_T_flow: int = 50                    # Flow temperature in degree Celsius.
    STC_zero_loss: float = 0.786            # Optical efficiency between 0 and 1.
    STC_first_order: float = 0.003345       # First order efficiency (linear thermal losses) in Watt per square meter per Kelvin.
    STC_second_order: float = 0.0000142     # Second order efficiency (quadratic thermal losses) in Watt per square meter per Kelvin square.
    STC_life_time: int = 20                 # Maximum life time in years.
    STC_inv_var: int = 400                  # Investment variable in €/m^2.
    STC_cost_om: float = 0.05               # Cost of operation and maintenance as a percentage of investment.

    # TES parameters (Thermal Energy Storage)
    TES_soc_min: float = 0.0            # Minimum state of charge between 0 and 1.
    TES_soc_max: float = 1.0            # Maximum state of charge between 0 and 1.
    TES_eta_standby: float = 0.97       # Standby efficiency between 0 and 1.
    TES_eta_ch: float = 1.0             # Charging and discharging efficiency between 0 and 1.
    TES_coeff_ch: float = 10000.0       # Charging and discharging coefficient in Watt per Watthour.
    TES_init: float = 0.5               # Initial state of charge between 0 and 1.
    TES_T_diff_max: int = 35            # Maximum temperature difference in degree Celsius.
    TES_life_time: int = 15             # Maximum life time in years.
    TES_inv_var: int = 20               # Investment variable in €/liter.
    TES_cost_om: float = 0.05           # Cost of operation and maintenance as a percentage of investment.

    # BAT parameters (Battery Storage)
    BAT_soc_min: float = 0.0        # Minimum state of charge between 0 and 1.
    BAT_soc_max: float = 0.95       # Maximum state of charge between 0 and 1.
    BAT_eta_standby: float = 0.97   # Standby efficiency between 0 and 1.
    BAT_eta_ch: float = 0.97        # Charging and discharging efficiency between 0 and 1.
    BAT_coeff_ch: float = 0.8       # Charging and discharging coefficient in Watt per Watthour.
    BAT_init: float = 0.2           # Initial state of charge between 0 and 1.
    BAT_life_time: int = 15         # Maximum life time in years.
    BAT_inv_var: int = 850          # Investment variable in €/kWh.
    BAT_cost_om: float = 0.05       # Cost of operation and maintenance as a percentage of investment.

    # EV parameters (Electric Vehicle)
    EV_soc_min: float = 0.05        # Minimum state of charge between 0 and 1.
    EV_soc_max: float = 0.95        # Maximum state of charge between 0 and 1.
    EV_eta_standby: float = 1.0     # Standby efficiency between 0 and 1.
    EV_eta_ch: float = 0.97         # Charging and discharging efficiency between 0 and 1.
    EV_coeff_ch: float = 1.2        # Charging and discharging coefficient in Watt per Watthour.
    EV_init: float = 0.2            # Initial state of charge between 0 and 1.
    EV_life_time: int = 20          # Maximum life time in years.
    EV_inv_var: int = 700           # Investment variable in €/liter.
    EV_cost_om: float = 0.05        # Cost of operation and maintenance as a percentage of investment.

    # Investment data parameters
    inv_data_observation_time: int = 20     # Observation time in years.
    inv_data_interest_rate: float = 0.05    # Interest rate between 0 and 1.

    model_config = SettingsConfigDict(
        env_file=".decentraldeviceconfig",
        extra="allow"
    )