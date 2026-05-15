from districtgenerator.classes import *
from pathlib import Path
import traceback


def run_scenario(scenario_label: str, config: str, overwrite_values: dict, scenario_file: str, calcUserProfiles: bool, saveUserProfiles: bool, gen_cars: bool):

    config_env = get_config_name(config)
    config_name = config_env.split(".")[-1]

    data = Datahandler(scenario_name=scenario_file, env_path=config_env, overwrite_values=overwrite_values)
    data.generateDistrictComplete(calcUserProfiles=calcUserProfiles, saveUserProfiles=saveUserProfiles, gen_cars=gen_cars)
    data.optimizationClusters()
    data.calculateKPIs()
    data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    rename_certificate(scenario_name=scenario_label, scenario_file=scenario_file, config_name=config_name, result_path=data.resultPath)


def write_error_report(result_path, scenario_name: str, scenario_file: str, config_name: str, error: Exception):
    error_folder = Path(result_path) / "test_scenarios"
    error_folder.mkdir(parents=True, exist_ok=True)

    error_path = error_folder / f"Quartiersenergieausweis_{scenario_name}_{config_name}.txt"
    error_text = "\n".join([
        f"Scenario: {scenario_name}",
        f"Scenario file: {scenario_file}",
        f"Config: {config_name}",
        f"Error type: {type(error).__name__}",
        f"Error message: {error}",
        "",
        "Traceback:",
        traceback.format_exc(),
    ])
    error_path.write_text(error_text, encoding="utf-8")


def get_config_name(config: str) -> str:
    config = config.strip()

    if ".env.CONFIG" not in config:
        return f".env.CONFIG.{config}"

    return config

def prepare_shared_demands(settings: dict, scenario_file: str):
    """
    Generate and save one shared set of demand profiles before the scenario runs.

    This keeps the later scenarios from using the first scenario as the profile
    generator and ensures car profiles are available on disk before any scenario
    decides whether to load them.
    """

    first_scenario = next(iter(settings.values()))
    data = Datahandler(
        scenario_name=scenario_file,
        env_path=get_config_name(first_scenario["config"]),
        overwrite_values=first_scenario["overwrite_values"],
    )
    data.generateEnvironment()
    data.initializeBuildings()
    data.generateBuildings()
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True, gen_cars=True)


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


def run_multiple_scenarios(settings:dict, scenario_file: str, load_demands: bool = False):
    if not load_demands:
        print("Generating shared demand profiles for all scenarios...")
        prepare_shared_demands(settings, scenario_file)

    for scenario in settings.values():
        scenario_name = scenario["name"]
        config = scenario["config"]
        overwrite_values = scenario["overwrite_values"]
        gen_cars = scenario["gen_cars"]

        # Demands are already generated once in prepare_shared_demands().
        # Every scenario now loads the shared files and decides independently
        # whether the car profiles should be used.
        calc_profiles = False
        save_profiles = False
        
        config_name = get_config_name(config).split(".")[-1]

        try:
            run_scenario(
                scenario_label=scenario_name,
                config=config,
                overwrite_values=overwrite_values,
                scenario_file=scenario_file,
                gen_cars=gen_cars,
                calcUserProfiles=calc_profiles,
                saveUserProfiles=save_profiles
            )
        except Exception as error:
            print(f"Scenario '{scenario_name}' failed: {error}")
            write_error_report(
                result_path=Path("results"),
                scenario_name=scenario_name,
                scenario_file=scenario_file,
                config_name=config_name,
                error=error,
            )


# Define scenario configurations -
# overwrite_values specify the columns to be overwritten, and 
# configs specify the different configs for which to run this specific setup (e.g., different price settings)
scenario_definitions = {
    "scenario_EFH_BOI": {
        "overwrite_values": {"heater": "BOI"},
        "gen_cars": False,
        "configs": ["LOWGASPRICE", "Normal", "HIGHGASPRICE"]
    },
    "scenario_EFH_BBOI": {
        "overwrite_values": {"heater": "BBOI"},
        "gen_cars": False,
        "configs": ["LOWBIOMASSPRICE", "Normal", "HIGHBIOMASSPRICE"]
    },
    "scenario_EFH_HP": {
        "overwrite_values": {"heater": "HP"},
        "gen_cars": False,
        "configs": ["LOWELECTRICITYPRICE", "Normal", "HIGHELECTRICITYPRICE", "TRAFOLIMIT"]
    },
    "scenario_EFH_HP_PV": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9},
        "gen_cars": False,
        "configs": ["LOWELECTRICITYPRICE", "Normal", "HIGHELECTRICITYPRICE", "TRAFOLIMIT"]
    },
    "scenario_EFH_HP_PV_BAT": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9, "f_BAT": 0.5},
        "gen_cars": False,
        "configs": ["LOWELECTRICITYPRICE", "Normal", "HIGHELECTRICITYPRICE", "TRAFOLIMIT"]
    },
    "scenario_EFH_HP_STC": {
        "overwrite_values": {"heater": "HP", "f_STC": 0.6},
        "gen_cars": False,
        "configs": ["LOWELECTRICITYPRICE", "Normal", "HIGHELECTRICITYPRICE", "TRAFOLIMIT"]
    },
    "scenario_EFH_HP_PV_EV_on_demand": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9, "ev_charging": "on_demand"},
        "gen_cars": True,
        "configs": ["NORMAL", "TRAFOLIMIT"]
    },
    "scenario_EFH_HP_PV_EV_intelligent": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9, "ev_charging": "intelligent"},
        "gen_cars": True,
        "configs": ["NORMAL", "TRAFOLIMIT"]
    },
    "scenario_EFH_HP_PV_EV_bi_directional": {
        "overwrite_values": {"heater": "HP", "f_PV1": 0.9, "ev_charging": "bi_directional"},
        "gen_cars": True,
        "configs": ["NORMAL", "TRAFOLIMIT"]
    },
    "scenario_EFH_HP_EV_on_demand": {
        "overwrite_values": {"heater": "HP", "ev_charging": "on_demand"},
        "gen_cars": True,
        "configs": ["NORMAL", "TRAFOLIMIT"]
    },
    "scenario_EFH_HP_EV_bi_directional": {
        "overwrite_values": {"heater": "HP", "ev_charging": "bi_directional"},
        "gen_cars": True,
        "configs": ["NORMAL", "TRAFOLIMIT"]
    }
}

# Build scenario_settings from definitions
scenario_settings = {}
scenario_id = 1
for scenario_name, scenario_config in scenario_definitions.items():
    overwrite_values = scenario_config["overwrite_values"]
    configs = scenario_config["configs"]
    gen_cars = scenario_config["gen_cars"]
    
    for config in configs:
        scenario_key = f"scenario{scenario_id}"
        scenario_settings[scenario_key] = {
            "name": scenario_name,
            "gen_cars": gen_cars,
            "config": config,
            "overwrite_values": overwrite_values,
        }
        scenario_id += 1


if __name__ == "__main__":
    run_multiple_scenarios(scenario_settings, scenario_file="base_EFH_EV", load_demands=True)