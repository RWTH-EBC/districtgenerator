from typing import Any, Dict, List
from districtgenerator.data_handling.config import BuildingConfig

class BuildingDataGenerator:
    def __init__(self, building_config: BuildingConfig):
        self.building = building_config
        
    def generate_building_data(self) -> List[Dict[str, Any]]:
        buildings_out = []
        for idx, b in enumerate(self.building.buildings):
            building = {
                "id": idx,
                "gmlId": b.get("id"),
                "building": b.get("building_type"),
                "year": b.get("construction_year"),
                "construction_type": b.get("construction_type"),
                "night_setback": int(b.get("night_setback", self.building.night_setback)),
                "retrofit": b.get("retrofit", 0),
                "area": b.get("area"),
                "number_of_floors": b.get("number_of_floors"),
                "elec": b.get("elec"),
                "height": b.get("height"),
                "heater": b.get("heater_type"),
                "PV": int(b.get("PV", self.building.PV)),
                "STC": int(b.get("STC", self.building.STC)),
                "EV": int(b.get("EV", self.building.EV)),
                "BAT": int(b.get("BAT", self.building.BAT)),
                "f_TES": b.get("f_TES", self.building.storage.get("f_TES")),
                "f_BAT": b.get("f_BAT", self.building.storage.get("f_BAT")),
                "f_EV": b.get("f_EV", self.building.storage.get("f_EV")),
                "f_PV": b.get("f_PV", self.building.storage.get("f_PV")),
                "f_STC": b.get("f_STC", self.building.storage.get("f_STC")),
                "gamma_PV": b.get("gamma_PV", 0),
                "ev_charging": b.get("ev_charging", self.building.charging_modes[0])
            }
            buildings_out.append(building)
        return buildings_out
