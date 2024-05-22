# created May 2024 
# by Felix Rehmann 

import os
import json
from teaser.logic.buildingobjects.thermalzone import ThermalZone
from teaser.logic.buildingobjects.useconditions import UseConditions as UseCond


class NonResidential(object):
    """Base class for each non-residential archetype.

    This is the base class for all non-residential archetype buildings according to data NWG.
    The setup is similiar to TEASER, considering that there are no information about layers and 
    details about material available. The class provides the necessary information for the districtgenerator. 

    These are:
        - prj.data.material_bind -> No data available for non-residential Archetypes
        - prj.data.element_bind - -> No data available for non-residential Archetypes
        - prj.buildings[self.id].volume 
        - prj.buildings[self.id].outer_area
        - prj.buildings[self.id].window_area -> has to be caculated, as it is not present in data NWG.

    Teasers uses typical layers and material for the build envrionment according to MASEA ( https://www.masea-ensan.de/ ). 
    Currently, the gathering and combinatory selection of this is not feasible. 

    Several parameters are are obligatory: name, year_of_construction, net_leased_area, type.
    
    Other parameters are optional, and are implemented to provide further options for configuration. 

    In accordance with TEASER it is assumed, that each building has four orientations of outer walls and windows (north,
    east, south and west), two orientations for rooftops (south and north), 
    with tilt of 35 degree and one orientation for ground floors and one door (default orientation is west).

    In TEASER it is assumed,  thath the surface is the product of the given net_leased_area and specific estimation factors. These
    estimation factors where build by dividing the given 'surface area' by the 'reference floor area' in TABULA. The same approach is followed here. 
    The factors are given in: 
        - 

    Obliagotry Parameters
    ----------

    name : str
        Individual name
    year_of_construction : int
        Year of first construction
    net_leased_area : float [m2]
        Total net leased area of building. This is area is NOT the footprint
        of a building
    usage: str 
        Type of the building, according to Data NWG. Options are: "oag", "rnt", "hlc", "sdc", "clt", "spf", "hbr", "pwo", "trd", "tud", "trs", "gs1", "gs2"
    
        
    Optional Parameters
    ------------- 

    street_name : string
        Name of the street the building is located at. (optional)
    city : string
        Name of the city the building is located at. (optional)
    longitude : float [degree]
        Longitude of building location.
    latitude : float [degree]
        Latitude of building location.

    Attributes
    ----------
    central_ahu : instance of BuildingAHU
        Teaser Instance of BuildingAHU if a central AHU is embedded into the
        building (currently mostly needed for AixLib simulation).
    number_of_floors : int
        number of floors above ground (default: None)
    height_of_floors : float [m]
        Average height of the floors (default: None)
    internal_id : float
        Random id for the distinction between different buildings.
    year_of_retrofit : int
        Year of last retrofit.
    type_of_building : string
        Type of a Building (e.g. Building (unspecified), Office etc.).
    building_id : None
        ID of building, can be set by the user to keep track of a building
        even outside of TEASER, e.g. in a simulation or in post-processing.
        This is not the same as internal_id, as internal_id is e.g. not
        exported to Modelica models!
   
        

    thermal_zones : list
        List with instances of ThermalZone(), that are located in this building.
    outer_area : dict [degree: m2]
        Dictionary with orientation as key and sum of outer wall areas of
        that direction as value.
    window_area : dict [degree: m2]
        Dictionary with orientation as key and sum of window areas of
        that direction as value.
    bldg_height : float [m]
        Total building height.
    volume : float [m3]
        Total volume of all thermal zones.
    sum_heat_load : float [W]
        Total heating load of all thermal zones.
    sum_cooling_load : float [W]
        Total heating load of all thermal zones. (currently not supported)
    number_of_elements_calc : int
        Number of elements that are used for thermal zone calculation in this
        building.

        1. OneElement
        2. TwoElement
        3. ThreeElement
        4. FourElement

    merge_windows_calc : boolean
        True for merging the windows into the outer wall's RC-combination,
        False for separate resistance for window, default is False
    used_library_calc : str
        'AixLib' for https://github.com/RWTH-EBC/AixLib
        'IBPSA' for https://github.com/ibpsa/modelica
    library_attr : Annex() or AixLib() instance
        Classes with specific functions and attributes for building models in
        IBPSA and AixLib. Python classes can be found in calculation package.

        self.volume = volume
        

    """

    def __init__(
        self,
        name,
        year_of_construction,
        net_leased_area,
        usage,  
        number_of_floors,
        height_of_floors,
        construction_type = "Tabula", 
    ):
        self.name = name 
        self.year_of_construction = year_of_construction
        self.net_leased_area = float(net_leased_area)
        self.usage = usage 
        self.height = None
        self.number_of_floors=float(number_of_floors)
        self.height_of_floors=float(height_of_floors)

        # To-Do: Check zone factors
        self.zone_area_factors = {"SingleDwelling": [1, "Living"]} 

        # Validate construction_type
        valid_construction_types = ["Light", "Medium", "Heavy", "Tabula"]
        if construction_type and construction_type not in valid_construction_types:
            raise ValueError(f"Invalid construction_type '{construction_type}'. Must be one of {valid_construction_types}.")
        
        # check Orientation 
        


        self.volume = self.calculate_volume()
        self.parameters = self.load_building_data()
        self.facade_estimation_factors = self.load_surface_estimation_factors()

        self.street_name = ""
        self.city = ""
        self.longitude = 6.05
        self.latitude = 50.79

        self._thermal_zones = []
        self._outer_area = {}
        self._window_area = {}

        self.outer_wall_names = {
            "Exterior Facade North": [90.0, 0.0],
            "Exterior Facade East": [90.0, 90.0],
            "Exterior Facade South": [90.0, 180.0],
            "Exterior Facade West": [90.0, 270.0],
        }
        # [tilt, orientation]

        self.roof_names = {"Rooftop": [0, -1]}  # [0, -1]

        self.ground_floor_names = {"Ground Floor": [0, -2]}  # [0, -2]

        self.window_names = {
            "Window Facade North": [90.0, 0.0],
            "Window Facade East": [90.0, 90.0],
            "Window Facade South": [90.0, 180.0],
            "Window Facade West": [90.0, 270.0],
        }
        # no information about the door, inner walls, or ceiling in the archetype
        # Hence No self.door_names, self.inner_wall_names, self.ceiling_names are given
        # 

        self.fill_outer_area_dict()
        self.fill_window_area_dict()

    def _check_year_of_construction(self):
        """Assigns the bldg age group according to year of construction"""

        for key in self.facade_estimation_factors:
            if (
                self.year_of_construction in range(key[0], key[1])
                or self.year_of_construction == key[1]
            ):
                self.building_age_group = (key[0], key[1])

        if self.building_age_group is None:
            raise RuntimeError(
                "Year of construction not supported for this archetype" "building"
            )

    def generate_archetype(self):
        """
        Generates an archetype building.

        Adaption of TEASER archetype generation for IWU Non-Residential Building Typology. 
        There is currently no ThermalZone() or BuildingPart() implemented in the Non-Residential Building.

        """

        self.thermal_zones = None
        self._check_year_of_construction(self.year_of_construction)
        # help area for the correct building area setting while using typeBldgs
        type_bldg_area = self.net_leased_area
        self.net_leased_area = 0.0

        for key, value in self.zone_area_factors.items():
            zone = ThermalZone(parent=self)
            zone.name = key
            zone.area = type_bldg_area * value[0]
            use_cond = UseCond(parent=zone)
            use_cond.load_use_conditions(zone_usage=value[1])
            zone.use_conditions = use_cond

            zone.use_conditions.with_ahu = False
        if self.facade_estimation_factors[self.building_age_group]["ow1"] != 0:
            for key, value in self._outer_wall_names_1.items():
                for zone in self.thermal_zones:
                    outer_wall = OuterWall(zone)
                    outer_wall.load_type_element(
                        year=self.year_of_construction,
                        construction=self._construction_type_1,
                        data_class=self.parent.data,
                    )
                    outer_wall.name = key
                    outer_wall.tilt = value[0]
                    outer_wall.orientation = value[1]
                    outer_wall.area = (
                        self.facade_estimation_factors[self.building_age_group]["ow1"]
                        * zone.area
                    ) / len(self._outer_wall_names_1)
        
        if self.facade_estimation_factors[self.building_age_group]["win1"] != 0:
            for key, value in self.window_names_1.items():
                for zone in self.thermal_zones:
                    window = Window(zone)
                    window.load_type_element(
                        self.year_of_construction,
                        construction=self._construction_type_1,
                        data_class=self.parent.data,
                    )
                    window.name = key
                    window.tilt = value[0]
                    window.orientation = value[1]
                    window.area = (
                        self.facade_estimation_factors[self.building_age_group]["win1"]
                        * zone.area
                    ) / len(self.window_names_1)
        
        if self.facade_estimation_factors[self.building_age_group]["gf1"] != 0:
            for key, value in self.ground_floor_names_1.items():

                for zone in self.thermal_zones:
                    gf = GroundFloor(zone)
                    gf.load_type_element(
                        year=self.year_of_construction,
                        construction=self._construction_type_1,
                        data_class=self.parent.data,
                    )
                    gf.name = key
                    gf.tilt = value[0]
                    gf.orientation = value[1]
                    gf.area = (
                        self.facade_estimation_factors[self.building_age_group]["gf1"]
                        * zone.area
                    ) / len(self.ground_floor_names_1)
        
        
        if self.facade_estimation_factors[self.building_age_group]["rt1"] != 0:
            for key, value in self.roof_names_1.items():

                for zone in self.thermal_zones:
                    rt = Rooftop(zone)
                    rt.load_type_element(
                        year=self.year_of_construction,
                        construction=self._construction_type_1,
                        data_class=self.parent.data,
                    )
                    rt.name = key
                    rt.tilt = value[0]
                    rt.orientation = value[1]
                    rt.area = (
                        self.facade_estimation_factors[self.building_age_group]["rt1"]
                        * zone.area

        

    def calculate_volume(self):
        self.volume = self.net_leased_area * self.number_of_floors * self.height_of_floors

    def load_surface_estimation_factors(self):
        """
        Load surface estimation factors data from a JSON file
        # rt - rooftop
        # ow - outer wall 
        # gf - ground floor
        # win - window 
       
        Returns
        -------
        dict
            Dictionary with the surface estimation factors:
            {
                'rt1': 0.625,
                'ow1': 0.77604,
                'gf1': 0.625,
                'win1': 0.18854
                }
        """
        DATA_DIR_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        DATA_PATH = os.path.join(DATA_DIR_PATH, 'data', 'non_residential_envelope', 'suface_estimation_factors.json')
        with open(DATA_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
    
        # Validate if the archetype exists in the data
        if self.usage not in data:
            raise ValueError(f"Archetype '{self.usage}' not found in the data.")
    
        # Get the building age groups for the specified archetype
        age_groups = data[self.usage]["building_age_group"]
        
        # Validate if the year_of_construction falls within any age group
        for age_range, parameters in age_groups.items():
            start_year, end_year = map(int, age_range.split(' - '))
            if start_year <= self.year_of_construction <= end_year:
                return parameters

    
    def load_building_data(self):
        """
        Load building data from a JSON file

        Parameters
        ----------
        file_path : str
            Path to the JSON file

        Returns
        -------
        dict
            Dictionary with the building data
        """
        DATA_DIR_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        DATA_PATH = os.path.join(DATA_DIR_PATH, 'data', 'non_residential_envelope', 'non_residential_envelope.json')
        with open(DATA_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
    
        # Validate if the archetype exists in the data
        if self.usage not in data:
            raise ValueError(f"Archetype '{self.usage}' not found in the data.")
    
        # Get the building age groups for the specified archetype
        age_groups = data[self.usage]["building_age_group"]
        
        # Validate if the year_of_construction falls within any age group
        for age_range, parameters in age_groups.items():
            start_year, end_year = map(int, age_range.split(' - '))
            if start_year <= self.year_of_construction <= end_year:
                return parameters

          # If no matching age group is found
        raise ValueError(f"Year of construction '{self.year_of_construction}' not found in any age group for archetype '{self.bldg_type}'.")
    
    def set_outer_wall_area(self, new_area, orientation):
        """Outer area wall setter

        sets the outer wall area of all walls of one direction and weights
        them according to zone size. This function covers OuterWalls,
        Rooftops, GroundFloors.

        Parameters
        ----------
        new_area : float
            new_area of all outer walls of one orientation
        orientation : float
            orientation of the obtained walls
        """

        for zone in self.thermal_zones:
            for wall in zone.outer_walls:
                if wall.orientation == orientation:
                    wall.area = ((new_area / self.net_leased_area) * zone.area) / sum(
                        count.orientation == orientation for count in zone.outer_walls
                    )

            for roof in zone.rooftops:
                if roof.orientation == orientation:
                    roof.area = ((new_area / self.net_leased_area) * zone.area) / sum(
                        count.orientation == orientation for count in zone.rooftops
                    )

            for ground in zone.ground_floors:
                if ground.orientation == orientation:
                    ground.area = ((new_area / self.net_leased_area) * zone.area) / sum(
                        count.orientation == orientation for count in zone.ground_floors
                    )

            for door in zone.doors:
                if door.orientation == orientation:
                    door.area = ((new_area / self.net_leased_area) * zone.area) / sum(
                        count.orientation == orientation for count in zone.doors
                    )

    def set_window_area(self, new_area, orientation):
        """Window area setter

        sets the window area of all windows of one direction and weights
        them according to zone size

        Parameters
        ----------
        new_area : float
            new_area of all window of one orientation
        orientation : float
            orientation of the obtained windows
        """

        for zone in self.thermal_zones:
            for win in zone.windows:
                if win.orientation == orientation:
                    win.area = ((new_area / self.net_leased_area) * zone.area) / sum(
                        count.orientation == orientation for count in zone.windows
                    )

    def get_outer_wall_area(self, orientation):
        """Get aggregated wall area of one orientation

        Returns the area of all outer walls of one direction. This function
        covers OuterWalls, GroundFloors and Rooftops.

        Parameters
        ----------
        orientation : float
            orientation of the obtained wall
        Returns
        -------
        sum_area : float
            area of all walls of one direction
        """

        sum_area = 0.0
        for zone_count in self.thermal_zones:
            for wall_count in zone_count.outer_walls:
                if (
                    wall_count.orientation == orientation
                    and wall_count.area is not None
                ):
                    sum_area += wall_count.area
            for roof_count in zone_count.rooftops:
                if (
                    roof_count.orientation == orientation
                    and roof_count.area is not None
                ):
                    sum_area += roof_count.area
            for ground_count in zone_count.ground_floors:
                if (
                    ground_count.orientation == orientation
                    and ground_count.area is not None
                ):
                    sum_area += ground_count.area
        return sum_area

    def get_window_area(self, orientation):
        """Get aggregated window area of one orientation

        returns the area of all windows of one direction

        Parameters
        ----------
        orientation : float
            orientation of the obtained windows
        Returns
        -------
        sum_area : float
            area of all windows of one direction
        """

        sum_area = 0.0
        for zone_count in self.thermal_zones:
            for win_count in zone_count.windows:
                if win_count.orientation == orientation and win_count.area is not None:
                    sum_area += win_count.area
        return sum_area


    def fill_outer_area_dict(self):
        """Fills the attribute outer_area

        Fills the dictionary outer_area with the sum of outer wall area
        corresponding to the orientations of the building. This function
        covers OuterWalls, GroundFloors and Rooftops.

        """
        self.outer_area = {}
        for zone_count in self.thermal_zones:
            for wall_count in zone_count.outer_walls:
                self.outer_area[wall_count.orientation] = None
            for roof in zone_count.rooftops:
                self.outer_area[roof.orientation] = None
            for ground in zone_count.ground_floors:
                self.outer_area[ground.orientation] = None

        for key in self.outer_area:
            self.outer_area[key] = self.get_outer_wall_area(key)

    def fill_window_area_dict(self):
        """Fills the attribute

        Fills the dictionary window_area with the sum of window area
        corresponding to the orientations of the building.

        """
        self.window_area = {}
        for zone_count in self.thermal_zones:
            for win_count in zone_count.windows:
                self.window_area[win_count.orientation] = None

        for key in self.window_area:
            self.window_area[key] = self.get_window_area(key)
    
    @property
    def thermal_zones(self):
        return self._thermal_zones

    @thermal_zones.setter
    def thermal_zones(self, value):
        if value is None:
            self._thermal_zones = []

    @property
    def outer_area(self):
        return self._outer_area

    @outer_area.setter
    def outer_area(self, value):
        self._outer_area = value

    def set_outer_wall_area(self, new_area, orientation):
        """Set the outer wall area for a specific orientation."""
        self.outer_area[orientation] = new_area

    def set_window_area(self, new_area, orientation):
        """Set the window area for a specific orientation."""
        self.window_area[orientation] = new_area

    def get_outer_wall_area(self, orientation):
        """Get the outer wall area for a specific orientation."""
        return self.outer_area.get(orientation, 0.0)

    def get_window_area(self, orientation):
        """Get the window area for a specific orientation."""
        return self.window_area.get(orientation, 0.0)

    def fill_outer_area_dict(self):
        """Fill the outer_area dictionary with initial values."""
        for orientation in [0.0, 90.0, 180.0, 270.0, -1, -2]:
            self.outer_area[orientation] = self.calculate_estimated_area(orientation, "outer_wall")

    def fill_window_area_dict(self):
        """Fill the window_area dictionary with initial values."""
        for orientation in [0.0, 90.0, 180.0, 270.0]:
            self.window_area[orientation] = self.calculate_estimated_area(orientation, "window")

    def calculate_estimated_area(self, orientation, area_type):
        """Calculate an estimated area based on orientation and type."""
        factor = self.facade_estimation_factors.get(f"{area_type[0:3]}1", 1)
        return self.net_leased_area * factor / len(self.outer_wall_names if area_type == "outer_wall" else self.window_names)

    @property
    def thermal_zones(self):
        return self._thermal_zones

    @thermal_zones.setter
    def thermal_zones(self, value):
        if value is None:
            self._thermal_zones = []

    @property
    def outer_area(self):
        return self._outer_area

    @outer_area.setter
    def outer_area(self, value):
        self._outer_area = value

    @property
    def window_area(self):
        return self._window_area

    @window_area.setter
    def window_area(self, value):
        self._window_area = value