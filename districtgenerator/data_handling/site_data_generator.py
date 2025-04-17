from typing import Any, Dict, List
from districtgenerator.data_handling.config import LocationConfig

class SiteDataGenerator:
    def __init__(self, location_config: LocationConfig):
        self.location = location_config

    def generate_site_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "timeZone",
                "value": self.location.timeZone,
                "unit": "h",
                "description": "Time zone offset from GMT (e.g. CET is 1)."
            },
            {
                "name": "albedo",
                "value": self.location.albedo,
                "unit": "",
                "description": "Ground reflectance (0 = 0%, 1 = 100%)."
            },
            {
                "name": "TRYYear",
                "value": self.location.TRYYear,
                "unit": "",
                "description": "Test reference year (e.g. TRY2015 or TRY2045)."
            },
            {
                "name": "TRYType",
                "value": self.location.TRYType,
                "unit": "",
                "description": "Test reference condition (e.g. Jahr, Somm, Wint)."
            },
            {
                "name": "zip",
                "value": self.location.zip,
                "unit": "",
                "description": "Zip code of the location."
            }
        ]
