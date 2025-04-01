from typing import Any, Dict, List
from districtgenerator.data_handling.decentral_device_config import DecentralDeviceConfig

class DecentralDeviceDataGenerator:
    def __init__(self, tech_config: DecentralDeviceConfig):
        self.config = tech_config

        # Mapping of device abbreviations to their meta data.
        self.devices_meta: Dict[str, Dict[str, Any]] = {
            "HP": {
                "device": "heat pump",
                "abbreviation": "HP",
                "description": "Air-to-water heat pump.",
                "specifications": {
                    "grade": {
                        "unit": "-",
                        "description": "Quality grade. Ratio of the achieved coefficient of performance to the Carnot coefficient of performance."
                    },
                    "life_time": {
                        "unit": "years",
                        "description": "Maximum life time."
                    },
                    "inv_var": {
                        "unit": "€/liter",
                        "description": ""
                    },
                    "cost_om": {
                        "unit": "percentage",
                        "description": ""
                    }
                }
            },
            "EH": {
                "device": "electric heater",
                "abbreviation": "EH",
                "description": "Electric heating device for bivalent operation in combination with the heat pump.",
                "specifications": {
                    "eta_th": {
                        "unit": "-",
                        "description": "Thermal efficiency."
                    }
                }
            },
            "BOI": {
                "device": "gas boiler",
                "abbreviation": "BOI",
                "description": "Gas boiler.",
                "specifications": {
                    "eta_th": {
                        "unit": "-",
                        "description": "Thermal efficiency."
                    },
                    "life_time": {
                        "unit": "years",
                        "description": "Maximum life time."
                    },
                    "inv_var": {
                        "unit": "€/kW",
                        "description": ""
                    },
                    "cost_om": {
                        "unit": "percentage",
                        "description": ""
                    }
                }
            },
            "CHP": {
                "device": "combined heat and power plant",
                "abbreviation": "CHP",
                "description": "Gas based combined heat and power plant.",
                "specifications": {
                    "eta_th": {
                        "unit": "-",
                        "description": "Thermal efficiency."
                    },
                    "eta_el": {
                        "unit": "-",
                        "description": "Electrical efficiency."
                    },
                    "life_time": {
                        "unit": "years",
                        "description": "Maximum life time."
                    },
                    "inv_var": {
                        "unit": "€/kW",
                        "description": ""
                    },
                    "cost_om": {
                        "unit": "percentage",
                        "description": ""
                    }
                }
            },
            "FC": {
                "device": "fuel cell",
                "abbreviation": "FC",
                "description": "Gas based fuel cell.",
                "specifications": {
                    "eta_th": {
                        "unit": "-",
                        "description": "Thermal efficiency."
                    },
                    "eta_el": {
                        "unit": "-",
                        "description": "Electrical efficiency."
                    }
                }
            },
            "PV": {
                "device": "photovoltaics",
                "abbreviation": "PV",
                "description": "photovoltaics",
                "specifications": {
                    "area_real": {
                        "unit": "squaremeters",
                        "description": "Module area."
                    },
                    "eta_el_ref": {
                        "unit": "-",
                        "description": "Electrical efficiency under reference conditions."
                    },
                    "t_cell_ref": {
                        "unit": "degree Celsius",
                        "description": "Reference ambient air temperature."
                    },
                    "G_ref": {
                        "unit": "Watt per squaremeter",
                        "description": "Reference solar irradiance."
                    },
                    "t_cell_noct": {
                        "unit": "degree Celsius",
                        "description": "Cell temperature under normal test conditions (NOCT)."
                    },
                    "t_air_noct": {
                        "unit": "degree Celsius",
                        "description": "Ambient air temperature under normal test conditions (NOCT)."
                    },
                    "G_noct": {
                        "unit": "Watt per squaremeter",
                        "description": "Irradiance under normal test conditions (NOCT)."
                    },
                    "gamma": {
                        "unit": "Percent per Kelvin",
                        "description": "loss coefficient"
                    },
                    "eta_inv": {
                        "unit": "-",
                        "description": "Inverter efficiency."
                    },
                    "eta_opt": {
                        "unit": "-",
                        "description": "Optical efficiency."
                    },
                    "P_nominal": {
                        "unit": "Watt per squaremeter",
                        "description": "Reference power per squaremeter. Used for Battery sizing."
                    },
                    "life_time": {
                        "unit": "years",
                        "description": "Maximum life time."
                    },
                    "inv_var": {
                        "unit": "€/m^2",
                        "description": ""
                    },
                    "cost_om": {
                        "unit": "percentage",
                        "description": ""
                    }
                }
            },
            "STC": {
                "device": "solar thermal collector",
                "abbreviation": "STC",
                "description": "solar thermal collector",
                "specifications": {
                    "T_flow": {
                        "unit": "degree celsius",
                        "description": "Flow temperature."
                    },
                    "zero_loss": {
                        "unit": "-",
                        "description": "Optical efficiency."
                    },
                    "first_order": {
                        "unit": "Watt per squaremeter per Kelvin",
                        "description": "First order efficiency. Linear thermal losses."
                    },
                    "second_order": {
                        "unit": "Watt per squaremeter per Kelvin square",
                        "description": "Second order efficiency. Quadratic thermal losses."
                    },
                    "life_time": {
                        "unit": "years",
                        "description": "Maximum life time."
                    },
                    "inv_var": {
                        "unit": "€/m^2",
                        "description": ""
                    },
                    "cost_om": {
                        "unit": "percentage",
                        "description": ""
                    }
                }
            },
            "TES": {
                "device": "thermal energy storage",
                "abbreviation": "TES",
                "description": "thermal energy storage",
                "specifications": {
                    "soc_min": {
                        "unit": "-",
                        "description": "Minimum state of charge."
                    },
                    "soc_max": {
                        "unit": "-",
                        "description": "Maximum state of charge."
                    },
                    "eta_standby": {
                        "unit": "-",
                        "description": "Standby efficiency."
                    },
                    "eta_ch": {
                        "unit": "-",
                        "description": "Charging and discharging efficiency."
                    },
                    "coeff_ch": {
                        "unit": "Watt per Watthour",
                        "description": "Charging and discharging coefficient."
                    },
                    "init": {
                        "unit": "-",
                        "description": "Initial state of charge."
                    },
                    "T_diff_max": {
                        "unit": "degree Celsius",
                        "description": "Maximum temperature difference. At a temperature difference of 35 degree the upper level temperature is 60 degree and the lower level temperature is 25 degree."
                    },
                    "life_time": {
                        "unit": "years",
                        "description": "Maximum life time."
                    },
                    "inv_var": {
                        "unit": "€/liter",
                        "description": ""
                    },
                    "cost_om": {
                        "unit": "percentage",
                        "description": ""
                    }
                }
            },
            "BAT": {
                "device": "battery",
                "abbreviation": "BAT",
                "description": "electrical home storage system",
                "specifications": {
                    "soc_min": {
                        "unit": "-",
                        "description": "Minimum state of charge."
                    },
                    "soc_max": {
                        "unit": "-",
                        "description": "Maximum state of charge."
                    },
                    "eta_standby": {
                        "unit": "-",
                        "description": "Standby efficiency."
                    },
                    "eta_ch": {
                        "unit": "-",
                        "description": "Charging and discharging efficiency."
                    },
                    "coeff_ch": {
                        "unit": "Watt per Watthour",
                        "description": "Charging and discharging coefficient."
                    },
                    "init": {
                        "unit": "-",
                        "description": "Initial state of charge."
                    },
                    "life_time": {
                        "unit": "years",
                        "description": "Maximum life time."
                    },
                    "inv_var": {
                        "unit": "€/kWh",
                        "description": ""
                    },
                    "cost_om": {
                        "unit": "percentage",
                        "description": ""
                    }
                }
            },
            "EV": {
                "device": "electrical vehicle",
                "abbreviation": "EV",
                "description": "electrical car",
                "specifications": {
                    "soc_min": {
                        "unit": "-",
                        "description": "Minimum state of charge."
                    },
                    "soc_max": {
                        "unit": "-",
                        "description": "Maximum state of charge."
                    },
                    "eta_standby": {
                        "unit": "-",
                        "description": "Standby efficiency."
                    },
                    "eta_ch": {
                        "unit": "-",
                        "description": "Charging and discharging efficiency."
                    },
                    "coeff_ch": {
                        "unit": "Watt per Watthour",
                        "description": "Charging and discharging coefficient."
                    },
                    "init": {
                        "unit": "-",
                        "description": "Initial state of charge."
                    },
                    "life_time": {
                        "unit": "years",
                        "description": "Maximum life time."
                    },
                    "inv_var": {
                        "unit": "€/liter",
                        "description": ""
                    },
                    "cost_om": {
                        "unit": "percentage",
                        "description": ""
                    }
                }
            },
            "inv_data": {
                "device": "Investment data",
                "abbreviation": "inv_data",
                "description": "Investment data of decentral devices",
                "specifications": {
                    "observation_time": {
                        "unit": "-",
                        "description": "observation time."
                    },
                    "interest_rate": {
                        "unit": "-",
                        "description": "interest rate."
                    }
                }
            }
        }

    def generate_tech_data(self) -> List[Dict[str, Any]]:
        devices = []

        # Iterate over each device defined in our meta mapping.
        for tech, meta in self.devices_meta.items():
            entry: Dict[str, Any] = {
                "device": meta["device"],
                "abbreviation": meta["abbreviation"],
                "description": meta["description"],
                "specifications": []
            }

            # For each specification, get the corresponding value from the config.
            for spec_name, spec_meta in meta["specifications"].items():
                field_name = f"{tech}_{spec_name}"
                value = getattr(self.config, field_name)
                spec_entry = {
                    "name": spec_name,
                    "value": value,
                    "unit": spec_meta["unit"],
                    "description": spec_meta["description"]
                }
                entry["specifications"].append(spec_entry)

            devices.append(entry)

        return devices
