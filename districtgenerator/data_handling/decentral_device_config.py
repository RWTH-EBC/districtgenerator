from pydantic_settings import BaseSettings, SettingsConfigDict

class DecentralDeviceConfig(BaseSettings):
    # HP parameters
    HP_grade: float = 0.4
    HP_life_time: int = 18
    HP_inv_var: int = 1000
    HP_cost_om: float = 0.05

    # EH parameters
    EH_eta_th: float = 1.0

    # BOI parameters
    BOI_eta_th: float = 0.97
    BOI_life_time: int = 20
    BOI_inv_var: int = 130
    BOI_cost_om: float = 0.05

    # CHP parameters
    CHP_eta_th: float = 0.62
    CHP_eta_el: float = 0.30
    CHP_life_time: int = 15
    CHP_inv_var: int = 3500
    CHP_cost_om: float = 0.05

    # FC parameters
    FC_eta_th: float = 0.53
    FC_eta_el: float = 0.39

    # PV parameters
    PV_area_real: float = 1.6
    PV_eta_el_ref: float = 0.199
    PV_t_cell_ref: int = 25
    PV_G_ref: int = 1000
    PV_t_cell_noct: int = 44
    PV_t_air_noct: int = 20
    PV_G_noct: int = 800
    PV_gamma: float = 0.003
    PV_eta_inv: float = 0.96
    PV_eta_opt: float = 0.9
    PV_P_nominal: float = 220.0
    PV_life_time: int = 25
    PV_inv_var: int = 340
    PV_cost_om: float = 0.05

    # STC parameters
    STC_T_flow: int = 50
    STC_zero_loss: float = 0.786
    STC_first_order: float = 0.003345
    STC_second_order: float = 0.0000142
    STC_life_time: int = 20
    STC_inv_var: int = 400
    STC_cost_om: float = 0.05

    # TES parameters
    TES_soc_min: float = 0.0
    TES_soc_max: float = 1.0
    TES_eta_standby: float = 0.97
    TES_eta_ch: float = 1.0
    TES_coeff_ch: float = 10000.0
    TES_init: float = 0.5
    TES_T_diff_max: int = 35
    TES_life_time: int = 15
    TES_inv_var: int = 20
    TES_cost_om: float = 0.05

    # BAT parameters
    BAT_soc_min: float = 0.0
    BAT_soc_max: float = 0.95
    BAT_eta_standby: float = 0.97
    BAT_eta_ch: float = 0.97
    BAT_coeff_ch: float = 0.8
    BAT_init: float = 0.2
    BAT_life_time: int = 15
    BAT_inv_var: int = 850
    BAT_cost_om: float = 0.05

    # EV parameters
    EV_soc_min: float = 0.05
    EV_soc_max: float = 0.95
    EV_eta_standby: float = 1.0
    EV_eta_ch: float = 0.97
    EV_coeff_ch: float = 1.2
    EV_init: float = 0.2
    EV_life_time: int = 20
    EV_inv_var: int = 700
    EV_cost_om: float = 0.05

    # Investment data parameters
    inv_data_observation_time: int = 20
    inv_data_interest_rate: float = 0.05
    
    model_config = SettingsConfigDict(
        env_file= ".decentraldeviceconfig",
        extra="forbid" 
    )
