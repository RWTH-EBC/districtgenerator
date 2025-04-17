from typing import Any, Dict, List
from districtgenerator.data_handling.config import TimeConfig

class TimeDataGenerator:
    def __init__(self, time_config: TimeConfig):
        self.time_config = time_config
            
    def generate_time_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "timeResolution",
                "value": self.time_config.timeResolution,
                "unit": "sec",
                "description": ("Required time resolution. For example, 3600 refers to an hourly resolution "
                                "and 900 to a 15min resolution.")
            },
            {
                "name": "clusterLength",
                "value": self.time_config.clusterLength,
                "unit": "sec",
                "description": ("Length of cluster. For example, 604800 refers to one week and 86400 to one day.")
            },
            {
                "name": "clusterNumber",
                "value": self.time_config.clusterNumber,
                "unit": "-",
                "description": "Number of clusters"
            },
            {
                "name": "dataResolution",
                "value": self.time_config.dataResolution,
                "unit": "sec",
                "description": "Time resolution of input data."
            },
            {
                "name": "dataLength",
                "value": self.time_config.dataLength,
                "unit": "sec",
                "description": "Length of input data."
            },
            {
                "name": "holidays2015",
                "value": self.time_config.holidays2015,
                "unit": "",
                "description": "Julian day number of the holidays in NRW in 2015."
            },
            {
                "name": "holidays2045",
                "value": self.time_config.holidays2045,
                "unit": "",
                "description": "Julian day number of the holidays in NRW in 2045."
            },
            {
                "name": "initial_day_2015",
                "value": self.time_config.initial_day_2015,
                "unit": "",
                "description": "Thursday"
            },
            {
                "name": "initial_day_2045",
                "value": self.time_config.initial_day_2045,
                "unit": "",
                "description": "Saturday"
            }
        ]
    
