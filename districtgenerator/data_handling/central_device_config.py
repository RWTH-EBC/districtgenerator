from pydantic_settings import BaseSettings, SettingsConfigDict

class CentralDeviceConfig(BaseSettings):
    # PV parameters
    PV_feasible: bool = True
    PV_eta: float = 0.15
    PV_life_time: int = 25
    PV_inv_var: int = 1000
    PV_cost_om: float = 0.02
    PV_max_area: int = 10000
    PV_min_area: int = 100
    PV_G_stc: int = 1

    # WT parameters
    WT_feasible: bool = True
    WT_inv_var: int = 1500
    WT_life_time: int = 20
    WT_cost_om: float = 0.015
    WT_min_cap: int = 100
    WT_max_cap: int = 3000
    WT_h_coeff: float = 0.2
    WT_hub_h: int = 100
    WT_ref_h: int = 10
    WT_norm_power: float = 0.85

    # WAT parameters
    WAT_feasible: bool = False
    WAT_inv_var: int = 2000
    WAT_life_time: int = 30
    WAT_cost_om: float = 0.01
    WAT_min_cap: int = 50
    WAT_max_cap: int = 2000
    WAT_potential: int = 50000

    # STC parameters
    STC_feasible: bool = False
    STC_eta: float = 0.7
    STC_inv_var: int = 800
    STC_life_time: int = 20
    STC_cost_om: float = 0.02
    STC_max_area: int = 5000
    STC_min_area: int = 10
    STC_G_stc: int = 1

    # CHP parameters
    CHP_feasible: bool = False
    CHP_inv_var: int = 1200
    CHP_eta_el: float = 0.4
    CHP_eta_th: float = 0.5
    CHP_life_time: int = 20
    CHP_cost_om: float = 0.03
    CHP_min_cap: int = 50
    CHP_max_cap: int = 1000

    # BOI parameters
    BOI_feasible: bool = False
    BOI_inv_var: int = 500
    BOI_eta_th: float = 0.9
    BOI_life_time: int = 20
    BOI_cost_om: float = 0.02
    BOI_min_cap: int = 10
    BOI_max_cap: int = 500

    # GHP parameters
    GHP_feasible: bool = False
    GHP_inv_var: int = 1000
    GHP_COP: float = 3.5
    GHP_life_time: int = 20
    GHP_cost_om: float = 0.02
    GHP_min_cap: int = 10
    GHP_max_cap: int = 500

    # HP parameters
    HP_feasible: bool = True
    HP_CCOP_feasible: bool = False
    HP_ASHP_feasible: bool = False
    HP_CSV_feasible: bool = True
    HP_inv_var: int = 800
    HP_life_time: int = 20
    HP_cost_om: float = 0.015
    HP_min_cap: int = 10
    HP_max_cap: int = 500
    HP_ASHP_carnot_eff: float = 0.4
    HP_ASHP_supply_temp: int = 60
    HP_COP_const: int = 4

    # EB parameters
    EB_feasible: bool = True
    EB_inv_var: int = 600
    EB_eta_th: float = 0.99
    EB_life_time: int = 20
    EB_cost_om: float = 0.01
    EB_min_cap: int = 10
    EB_max_cap: int = 300

    # CC parameters
    CC_feasible: bool = True
    CC_inv_var: int = 700
    CC_COP: float = 3.5
    CC_life_time: int = 20
    CC_cost_om: float = 0.02
    CC_min_cap: int = 10
    CC_max_cap: int = 500

    # AC parameters
    AC_feasible: bool = False
    AC_inv_var: int = 1000
    AC_eta_th: float = 0.75
    AC_life_time: int = 20
    AC_cost_om: float = 0.02
    AC_min_cap: int = 10
    AC_max_cap: int = 500

    # BCHP parameters
    BCHP_feasible: bool = False
    BCHP_inv_var: int = 1500
    BCHP_eta_el: float = 0.35
    BCHP_eta_th: float = 0.55
    BCHP_life_time: int = 20
    BCHP_cost_om: float = 0.03
    BCHP_min_cap: int = 50
    BCHP_max_cap: int = 1000

    # BBOI parameters
    BBOI_feasible: bool = False
    BBOI_inv_var: int = 600
    BBOI_eta_th: float = 0.85
    BBOI_life_time: int = 20
    BBOI_cost_om: float = 0.02
    BBOI_min_cap: int = 10
    BBOI_max_cap: int = 500

    # WCHP parameters
    WCHP_feasible: bool = False
    WCHP_inv_var: int = 2000
    WCHP_eta_el: float = 0.3
    WCHP_eta_th: float = 0.6
    WCHP_life_time: int = 20
    WCHP_cost_om: float = 0.03
    WCHP_min_cap: int = 50
    WCHP_max_cap: int = 1000

    # WBOI parameters
    WBOI_feasible: bool = False
    WBOI_inv_var: int = 700
    WBOI_eta_th: float = 0.8
    WBOI_life_time: int = 20
    WBOI_cost_om: float = 0.02
    WBOI_min_cap: int = 10
    WBOI_max_cap: int = 500

    # ELYZ parameters
    ELYZ_feasible: bool = False
    ELYZ_inv_var: int = 1500
    ELYZ_eta_el: float = 0.7
    ELYZ_life_time: int = 20
    ELYZ_cost_om: float = 0.03
    ELYZ_min_cap: int = 50
    ELYZ_max_cap: int = 1000

    # FC parameters
    FC_feasible: bool = False
    FC_inv_var: int = 1800
    FC_eta_el: float = 0.5
    FC_eta_th: float = 0.4
    FC_life_time: int = 20
    FC_cost_om: float = 0.03
    FC_min_cap: int = 50
    FC_max_cap: int = 1000
    FC_enable_heat_diss: bool = True

    # H2S parameters
    H2S_feasible: bool = False
    H2S_inv_var: int = 1200
    H2S_sto_loss: float = 0.0
    H2S_life_time: int = 20
    H2S_cost_om: float = 0.02
    H2S_min_cap: int = 100
    H2S_max_cap: int = 5000

    # SAB parameters
    SAB_feasible: bool = False
    SAB_inv_var: int = 2000
    SAB_eta: float = 0.6
    SAB_life_time: int = 20
    SAB_cost_om: float = 0.03
    SAB_min_cap: int = 50
    SAB_max_cap: int = 1000

    # TES parameters
    TES_feasible: bool = True
    TES_inv_var: int = 1200
    TES_sto_loss: float = 0.01
    TES_life_time: int = 20
    TES_cost_om: float = 0.01
    TES_min_vol: int = 100
    TES_max_vol: int = 5000
    TES_delta_T: int = 30
    TES_soc_init: float = 0.5

    # CTES parameters
    CTES_feasible: bool = False
    CTES_inv_var: int = 1300
    CTES_sto_loss: float = 0.01
    CTES_life_time: int = 20
    CTES_cost_om: float = 0.01
    CTES_min_vol: int = 100
    CTES_max_vol: int = 5000
    CTES_delta_T: int = 30
    CTES_soc_init: float = 0.5

    # BAT parameters
    BAT_feasible: bool = False
    BAT_inv_var: int = 200
    BAT_life_time: int = 15
    BAT_cost_om: float = 0.02
    BAT_min_cap: int = 10
    BAT_max_cap: int = 200
    BAT_sto_loss: float = 0.0
    BAT_soc_init: float = 0.5

    # GS parameters
    GS_feasible: bool = False
    GS_inv_var: int = 150
    GS_life_time: int = 20
    GS_cost_om: float = 0.01
    GS_min_cap: int = 1000
    GS_max_cap: int = 10000
    GS_sto_loss: float = 0.0
    GS_soc_init: float = 0.5

    model_config = SettingsConfigDict(
        env_file= ".centraldeviceconfig",
        extra="forbid" 
    )

