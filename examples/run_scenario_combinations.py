from districtgenerator.classes import *
from pathlib import Path


def run_scenario(scenario_label: str, config: str, overwrite_values: dict, scenario_file: str, calcUserProfiles: bool, saveUserProfiles: bool):

    config_name = config.split()[-1]

    if ".env.CONFIG" not in config:
        config = f".env.CONFIG.{config_name}"

    data = Datahandler(scenario_name=scenario_file, env_path=config, overwrite_values=overwrite_values)
    data.generateDistrictComplete(calcUserProfiles=calcUserProfiles, saveUserProfiles=saveUserProfiles)
    data.optimizationClusters()
    data.calculateKPIs()
    data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    rename_certificate(scenario_name=scenario_label, scenario_file=scenario_file, config_name=config_name, result_path=data.resultPath)


def rename_certificate(scenario_name: str, scenario_file: str, config_name: str, result_path):
    old_name = f"Quartiersenergieausweis_{scenario_file}.pdf"
    new_name = f"Quartiersenergieausweis_{scenario_name}_{config_name}.pdf"
    old_path = Path(result_path) / old_name
    new_folder = Path(result_path) / "test_scenarios"
    new_path = new_folder / new_name

    if not old_path.exists():
        raise FileNotFoundError(f"Certificate file not found: {old_path}")
    
    # Ensure folder exists
    new_folder.mkdir(parents=True, exist_ok=True)

    # Remove existing file if it exists
    if new_path.exists():
        new_path.unlink()

    old_path.rename(new_path)


def run_multiple_scenarios(settings:dict, scenario_file: str):
    first_scenario = True
    for scenario in settings.values():
        scenario_name = scenario["name"]
        config = scenario["config"]
        overwrite_values = scenario["overwrite_values"]
        
        # Only calculate and save user profiles for the first scenario
        calc_profiles = first_scenario
        save_profiles = first_scenario
        
        run_scenario(
            scenario_label=scenario_name,
            config=config,
            overwrite_values=overwrite_values,
            scenario_file=scenario_file,
            calcUserProfiles=calc_profiles,
            saveUserProfiles=save_profiles
        )
        
        first_scenario = False


# Define scenario configurations -
# overwrite_values specify the columns to be overwritten, and 
# configs specify the different configs for which to run this specific setup (e.g., different price settings)
scenario_definitions = {
    "scenario_EFH_BOI": {
        "overwrite_values": {"heater": "BOI"},
        "configs": ["LOWGASPRICE", "HIGHGASPRICE"]
    },
    "scenario_EFH_BBOI": {
        "overwrite_values": {"heater": "BBOI"},
        "configs": ["LOWBIOMASSPRICE", "HIGHBIOMASSPRICE"]
    },
    "scenario_EFH_HP": {
        "overwrite_values": {"heater": "HP"},
        "configs": ["LOWELECTRICITYPRICE", "HIGHELECTRICITYPRICE"]
    },
    "scenario_EFH_HP_PV": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9},
        "configs": ["LOWELECTRICITYPRICE", "HIGHELECTRICITYPRICE"]
    },
    "scenario_EFH_HP_PV_BAT": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9, "f_BAT": 0.5},
        "configs": ["LOWELECTRICITYPRICE", "HIGHELECTRICITYPRICE"]
    },
    "scenario_EFH_HP_STC": {
        "overwrite_values": {"heater": "HP", "f_STC": 0.6},
        "configs": ["LOWELECTRICITYPRICE", "HIGHELECTRICITYPRICE"]
    },
    "scenario_EFH_HP_PV_EV_on_demand": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9, "f_EV": 0.9, "ev_charging": "on_demand"},
        "configs": ["NORMAL"]
    },
    "scenario_EFH_HP_PV_EV_intelligent": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9, "f_EV": 0.9, "ev_charging": "intelligent"},
        "configs": ["NORMAL"]
    },
    "scenario_EFH_HP_PV_EV_bi_directional": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9, "f_EV": 0.9, "ev_charging": "bi_directional"},
        "configs": ["NORMAL"]
    }# ,
    # "scenario_EFH_HP_EV_bi_directional": {
    #     "overwrite_values": {"heater": "HP", "f_EV": 0.9, "ev_charging": "bi_directional"},
    #     "configs": ["TRAFOLIMIT"]
    # },
    # "scenario_EFH_HP_EV_on_demand": {
    #     "overwrite_values": {"heater": "HP", "f_EV": 0.9, "ev_charging": "on_demand"},
    #     "configs": ["TRAFOLIMIT"]
    # }
}

# Build scenario_settings from definitions
scenario_settings = {}
scenario_id = 1
for scenario_name, scenario_config in scenario_definitions.items():
    overwrite_values = scenario_config["overwrite_values"]
    configs = scenario_config["configs"]
    
    for config in configs:
        scenario_key = f"scenario{scenario_id}"
        scenario_settings[scenario_key] = {
            "name": scenario_name,
            "config": config,
            "overwrite_values": overwrite_values,
        }
        scenario_id += 1


if __name__ == "__main__":
    run_multiple_scenarios(scenario_settings, scenario_file="base_EFH") 