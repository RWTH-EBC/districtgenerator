from pydantic_settings import BaseSettings, SettingsConfigDict

class CentralDeviceConfig(BaseSettings):
    """Configuration for central devices in a district energy system.

    This class defines the default parameters for various central devices such as
    photovoltaic systems (PV), wind turbines (WT), water turbines (WAT),
    solar thermal collectors (STC), combined heat and power systems (CHP),
    boilers (BOI), heat pumps (HP), electric boilers (EB), chillers (CC),
    and various storage systems like TES, BAT, and GS.

    Each device has parameters such as feasibility, efficiency, lifetime, investment costs,
    and operational characteristics.

    Attributes
    ----------
    Descriptions directly in Class.

    """

    # PV parameters (Photovoltaic System)
    PV_feasible: bool = True        # Should this be considered for the central optimization.
    PV_eta: float = 0.18            # Electrical efficiency between 0 and 1.
    PV_life_time: int = 20          # Maximum life time in years.
    PV_inv_var: int = 1300          # Investment variable in €/kWp.
    PV_cost_om: float = 0.02        # Cost of operation and maintenance as a percentage of investment.
    PV_max_area: int = 50000        # Maximum installation area in square meters.
    PV_min_area: int = 0            # Minimum installation area in square meters.
    PV_G_stc: int = 1               # Global horizontal irradiance under STC in kW/m^2.

    # WT parameters (Wind Turbine)
    WT_feasible: bool = True        # Should this be considered for the central optimization.
    WT_inv_var: int = 900           # Investment variable in €/kW.
    WT_life_time: int = 20          # Maximum life time in years.
    WT_cost_om: float = 0.03        # Cost of operation and maintenance as a percentage of investment.
    WT_min_cap: int = 0             # Minimum capacity in kW.
    WT_max_cap: int = 10000         # Maximum capacity in kW.
    WT_h_coeff: float = 0.14        # Hellmann exponent for wind speed correction.
    WT_hub_h: int = 122             # Hub height of the wind turbine in meters.
    WT_ref_h: int = 10              # Reference height for wind speed data in meters.
    WT_norm_power: float = 0.85     # Normalized power output.

    # WAT parameters (Water Turbine)
    WAT_feasible: bool = False      # Should this be considered for the central optimization.
    WAT_inv_var: int = 1000         # Investment variable in €/kW.
    WAT_life_time: int = 40         # Maximum life time in years.
    WAT_cost_om: float = 0.02       # Cost of operation and maintenance as a percentage of investment.
    WAT_min_cap: int = 0            # Minimum capacity in kW.
    WAT_max_cap: int = 100000       # Maximum capacity in kW.
    WAT_potential: int = 1000       # Maximum available potential in kW.

    # STC parameters (Solar Thermal Collector)
    STC_feasible: bool = False      # Should this be considered for the central optimization.
    STC_eta: float = 0.45           # Thermal efficiency between 0 and 1.
    STC_inv_var: int = 702          # Investment variable in €/m^2.
    STC_life_time: int = 20         # Maximum life time in years.
    STC_cost_om: float = 0.02       # Cost of operation and maintenance as a percentage of investment.
    STC_max_area: int = 10000       # Maximum installation area in square meters.
    STC_min_area: int = 0           # Minimum installation area in square meters.
    STC_G_stc: int = 1              # Global horizontal irradiance under STC in kW/m^2.

    # CHP parameters (Combined Heat and Power) - Mapped from CHPunit
    CHP_feasible: bool = False      # Should this be considered for the central optimization.
    CHP_inv_var: int = 1180         # Investment variable in €/kW.
    CHP_eta_el: float = 0.46        # Electrical efficiency between 0 and 1.
    CHP_eta_th: float = 0.44        # Thermal efficiency between 0 and 1.
    CHP_life_time: int = 15         # Maximum life time in years.
    CHP_cost_om: float = 0.08       # Cost of operation and maintenance as a percentage of investment.
    CHP_min_cap: int = 0            # Minimum capacity in kW.
    CHP_max_cap: int = 100000       # Maximum capacity in kW.

    # BOI parameters (Boiler) - Mapped from GasBoiler
    BOI_feasible: bool = False      # Should this be considered for the central optimization.
    BOI_inv_var: int = 108          # Investment variable in €/kW.
    BOI_eta_th: float = 0.99        # Thermal efficiency between 0 and 1.
    BOI_life_time: int = 25         # Maximum life time in years.
    BOI_cost_om: float = 0.01       # Cost of operation and maintenance as a percentage of investment.
    BOI_min_cap: int = 0            # Minimum capacity in kW.
    BOI_max_cap: int = 100000       # Maximum capacity in kW.

    # GHP parameters (Gas Heat Pump)
    GHP_feasible: bool = False      # Should this be considered for the central optimization.
    GHP_inv_var: int = 1527         # Investment variable in €/kW.
    GHP_COP: float = 2.4            # Coefficient of Performance (COP).
    GHP_life_time: int = 18         # Maximum life time in years.
    GHP_cost_om: float = 0.03       # Cost of operation and maintenance as a percentage of investment.
    GHP_min_cap: int = 0            # Minimum capacity in kW.
    GHP_max_cap: int = 100000       # Maximum capacity in kW.

    # HP parameters (Heat Pump)
    HP_feasible: bool = True        # Should this be considered for the central optimization.
    HP_CCOP_feasible: bool = False  # Should this be considered for the central optimization (constant COP).
    HP_ASHP_feasible: bool = False  # Should this be considered for the central optimization (air source).
    HP_CSV_feasible: bool = True    # Should this be considered for the central optimization (CSV data).
    HP_inv_var: int = 748           # Investment variable in €/kW.
    HP_life_time: int = 25          # Maximum life time in years.
    HP_cost_om: float = 0.03        # Cost of operation and maintenance as a percentage of investment.
    HP_min_cap: int = 0             # Minimum capacity in kW.
    HP_max_cap: int = 100000        # Maximum capacity in kW.
    HP_ASHP_carnot_eff: float = 0.4 # Carnot efficiency of the Air Source Heat Pump between 0 and 1.
    HP_ASHP_supply_temp: int = 60   # Supply temperature of the Air Source Heat Pump in Celsius.
    HP_COP_const: int = 5           # Constant Coefficient of Performance (COP).

    # EB parameters (Electric Boiler)
    EB_feasible: bool = True        # Should this be considered for the central optimization.
    EB_inv_var: int = 463           # Investment variable in €/kW.
    EB_eta_th: float = 1.0          # Thermal efficiency between 0 and 1.
    EB_life_time: int = 25          # Maximum life time in years.
    EB_cost_om: float = 0.01        # Cost of operation and maintenance as a percentage of investment.
    EB_min_cap: int = 0             # Minimum capacity in kW.
    EB_max_cap: int = 100000        # Maximum capacity in kW.

    # CC parameters (Chiller)
    CC_feasible: bool = True        # Should this be considered for the central optimization.
    CC_inv_var: int = 600           # Investment variable in €/kW.
    CC_COP: float = 5.0             # Coefficient of Performance (COP).
    CC_life_time: int = 20          # Maximum life time in years.
    CC_cost_om: float = 0.05        # Cost of operation and maintenance as a percentage of investment.
    CC_min_cap: int = 0             # Minimum capacity in kW.
    CC_max_cap: int = 100000        # Maximum capacity in kW.

    # AC parameters (Absorption Chiller)
    AC_feasible: bool = False       # Should this be considered for the central optimization.
    AC_inv_var: int = 750           # Investment variable in €/kW.
    AC_eta_th: float = 0.6          # Thermal efficiency between 0 and 1.
    AC_life_time: int = 20          # Maximum life time in years.
    AC_cost_om: float = 0.05        # Cost of operation and maintenance as a percentage of investment.
    AC_min_cap: int = 0             # Minimum capacity in kW.
    AC_max_cap: int = 100000        # Maximum capacity in kW.

    # BCHP parameters (Building Combined Heat and Power) - Mapped from BiomassCHP
    BCHP_feasible: bool = False     # Should this be considered for the central optimization.
    BCHP_inv_var: int = 6386        # Investment variable in €/kW.
    BCHP_eta_el: float = 0.13       # Electrical efficiency between 0 and 1.
    BCHP_eta_th: float = 0.77       # Thermal efficiency between 0 and 1.
    BCHP_life_time: int = 28        # Maximum life time in years.
    BCHP_cost_om: float = 0.05      # Cost of operation and maintenance as a percentage of investment.
    BCHP_min_cap: int = 0           # Minimum capacity in kW.
    BCHP_max_cap: int = 100000      # Maximum capacity in kW.

    # BBOI parameters (Biomass Boiler)
    BBOI_feasible: bool = False     # Should this be considered for the central optimization.
    BBOI_inv_var: int = 692         # Investment variable in €/kW.
    BBOI_eta_th: float = 0.9        # Thermal efficiency between 0 and 1.
    BBOI_life_time: int = 28        # Maximum life time in years.
    BBOI_cost_om: float = 0.04      # Cost of operation and maintenance as a percentage of investment.
    BBOI_min_cap: int = 0           # Minimum capacity in kW.
    BBOI_max_cap: int = 100000      # Maximum capacity in kW.

    # WCHP parameters (Water Combined Heat and Power)
    WCHP_feasible: bool = False     # Should this be considered for the central optimization.
    WCHP_inv_var: int = 1200        # Investment variable in €/kW.
    WCHP_eta_el: float = 0.35       # Electrical efficiency between 0 and 1.
    WCHP_eta_th: float = 0.5        # Thermal efficiency between 0 and 1.
    WCHP_life_time: int = 30        # Maximum life time in years.
    WCHP_cost_om: float = 0.08      # Cost of operation and maintenance as a percentage of investment.
    WCHP_min_cap: int = 0           # Minimum capacity in kW.
    WCHP_max_cap: int = 100000      # Maximum capacity in kW.

    # WBOI parameters (Waste Boiler)
    WBOI_feasible: bool = False     # Should this be considered for the central optimization.
    WBOI_inv_var: int = 2788        # Investment variable in €/kW.
    WBOI_eta_th: float = 1.06       # Thermal efficiency between 0 and 1.
    WBOI_life_time: int = 25        # Maximum life time in years.
    WBOI_cost_om: float = 0.04      # Cost of operation and maintenance as a percentage of investment.
    WBOI_min_cap: int = 0           # Minimum capacity in kW.
    WBOI_max_cap: int = 100000      # Maximum capacity in kW.

    # ELYZ parameters (Electrolyzer)
    ELYZ_feasible: bool = False     # Should this be considered for the central optimization.
    ELYZ_inv_var: int = 1200        # Investment variable in €/kW.
    ELYZ_eta_el: float = 0.7        # Electrical efficiency between 0 and 1.
    ELYZ_life_time: int = 20        # Maximum life time in years.
    ELYZ_cost_om: float = 0.08      # Cost of operation and maintenance as a percentage of investment.
    ELYZ_min_cap: int = 0           # Minimum capacity in kW.
    ELYZ_max_cap: int = 100000      # Maximum capacity in kW.

    # FC parameters (Fuel Cell)
    FC_feasible: bool = False       # Should this be considered for the central optimization.
    FC_inv_var: int = 4000          # Investment variable in €/kW.
    FC_eta_el: float = 0.35         # Electrical efficiency between 0 and 1.
    FC_eta_th: float = 0.5          # Thermal efficiency between 0 and 1.
    FC_life_time: int = 20          # Maximum life time in years.
    FC_cost_om: float = 0.08        # Cost of operation and maintenance as a percentage of investment.
    FC_min_cap: int = 0             # Minimum capacity in kW.
    FC_max_cap: int = 100000        # Maximum capacity in kW.
    FC_enable_heat_diss: bool = True # Enable/disable heat dissipation for the fuel cell.

    # H2S parameters (Hydrogen Storage)
    H2S_feasible: bool = False      # Should this be considered for the central optimization.
    H2S_inv_var: int = 150          # Investment variable in €/kWh.
    H2S_sto_loss: float = 0.0       # Storage loss as a fraction.
    H2S_life_time: int = 20         # Maximum life time in years.
    H2S_cost_om: float = 0.01       # Cost of operation and maintenance as a percentage of investment.
    H2S_min_cap: int = 0            # Minimum capacity in kWh.
    H2S_max_cap: int = 100000       # Maximum capacity in kWh.

    # SAB parameters (Sabatier Reactor)
    SAB_feasible: bool = False      # Should this be considered for the central optimization.
    SAB_inv_var: int = 800          # Investment variable in €/kW.
    SAB_eta: float = 0.83           # Round-trip efficiency between 0 and 1.
    SAB_life_time: int = 20         # Maximum life time in years.
    SAB_cost_om: float = 0.08       # Cost of operation and maintenance as a percentage of investment.
    SAB_min_cap: int = 0            # Minimum capacity in kW.
    SAB_max_cap: int = 100000       # Maximum capacity in kW.

    # TES parameters (Thermal Energy Storage)
    TES_feasible: bool = True       # Should this be considered for the central optimization.
    TES_inv_var: int = 297          # Investment variable in €/m^3.
    TES_sto_loss: float = 0.01      # Storage loss per hour as a fraction.
    TES_life_time: int = 45         # Maximum life time in years.
    TES_cost_om: float = 0.01       # Cost of operation and maintenance as a percentage of investment.
    TES_min_vol: int = 0            # Minimum storage volume in cubic meters.
    TES_max_vol: int = 100000       # Maximum storage volume in cubic meters.
    TES_delta_T: int = 55           # Temperature difference between charged and discharged state in Celsius.
    TES_soc_init: float = 0.5       # Initial state of charge between 0 and 1.

    # CTES parameters (Cold Thermal Energy Storage)
    CTES_feasible: bool = False     # Should this be considered for the central optimization.
    CTES_inv_var: int = 297         # Investment variable in €/m^3.
    CTES_sto_loss: float = 0.01     # Storage loss per hour as a fraction.
    CTES_life_time: int = 45        # Maximum life time in years.
    CTES_cost_om: float = 0.01      # Cost of operation and maintenance as a percentage of investment.
    CTES_min_vol: int = 0           # Minimum storage volume in cubic meters.
    CTES_max_vol: int = 100000      # Maximum storage volume in cubic meters.
    CTES_delta_T: int = 55          # Temperature difference between charged and discharged state in Celsius.
    CTES_soc_init: float = 0.5      # Initial state of charge between 0 and 1.

    # BAT parameters (Battery Storage)
    BAT_feasible: bool = False      # Should this be considered for the central optimization.
    BAT_inv_var: int = 970          # Investment variable in €/kWh.
    BAT_life_time: int = 15         # Maximum life time in years.
    BAT_cost_om: float = 0.01       # Cost of operation and maintenance as a percentage of investment.
    BAT_min_cap: int = 0            # Minimum capacity in kWh.
    BAT_max_cap: int = 100000       # Maximum capacity in kWh.
    BAT_sto_loss: float = 0.0       # Storage loss as a fraction.
    BAT_soc_init: float = 0.5       # Initial state of charge between 0 and 1.

    # GS parameters (Gas Storage)
    GS_feasible: bool = False       # Should this be considered for the central optimization.
    GS_inv_var: int = 150           # Investment variable in €/kWh.
    GS_life_time: int = 20          # Maximum life time in years.
    GS_cost_om: float = 0.01        # Cost of operation and maintenance as a percentage of investment.
    GS_min_cap: int = 0             # Minimum capacity in kWh.
    GS_max_cap: int = 100000        # Maximum capacity in kWh.
    GS_sto_loss: float = 0.0        # Storage loss as a fraction.
    GS_soc_init: float = 0.5        # Initial state of charge between 0 and 1.

    model_config = SettingsConfigDict(
        env_file= ".centraldeviceconfig",
        extra="allow"
    )