# -*- coding: utf-8 -*-
"""
"""

import os, math
import json 
import random as rd
import numpy as np
import richardsonpy
import richardsonpy.classes.stochastic_el_load_wrapper as wrap
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
from districtgenerator.profils import Profiles , NonResidentialProfiles
import functions.heating_profile_5R1C as heating
import functions.schedule_reader as schedules
import functions.light_demand as light_demand
from districtgenerator.solar import SunIlluminance


class NonResidentialUsers():
    '''
    Building Users class describing the number of occupants and their configs. 


    Parameters
    ----------
    building : object
        buildings objects of TEASER project
    area : integer
        Floor area of different building types
  

    Attributes
    ----------
    building : string
        building type according to TABULA database
    nb_flats : integer
        number of flats in building
    annual_el_demand : array
        annual elictricity consumption in dependency of the building type and the number of occupants
    lighting_index : integer
        This index defines the lighting configuration of the houshold.
    el_wrapper : object
        This objects holdes information about the lighting and appliance configuration.
    nc_occ : list
        list with the number of occupants for each flat of the current building.
    occ : array
        occupancy profile for each flat of the current building.
    dhw :
        drinking hot water profile for each building.
    elec :
        electrical demand for each building.
    gains :
        internal gains for each building.
    heat :
        heat demand for each building.
    '''



    def __init__(self, building_usage, area, file, envelope, site, time):
        """
        Constructor of Users Class
        """

        self.usage = building_usage 
        self.area = area
        self.file = file
        self.envelope = envelope
        self.site = site 
        self.time = time
        #self.nb_flats = None
        self.annual_el_demand = None
        self.nb_occ = []
        self.occ = None
        self.dhw = None
        self.elec = None
        self.gains = None
        self.heat = None
        self.occupancy_schedule = None
        self.appliance_schedule = None
        self.lighntning_schedule = None
        
        # Define the path to the JSON file
        base_path = os.getcwd()
        occupancy_json_path = os.path.join(base_path,  'data', 'occupancy_schedules', 
                                           'average_occupancy.json')
        electricity_json_path = os.path.join(base_path,  'data', 'consumption_data', 
                                             'average_electricity_per_occupants.json')

        # Load the JSON data from the specified path
        self.occupancy_data = self.load_json_data(occupancy_json_path)
        self.electricity_data = self.load_json_data(electricity_json_path)
        


        # self.generate_number_flats(area)
        self.generate_number_occupants()
        self.generate_annual_el_consumption_equipment()
        self.generate_annual_el_consumption_lightning()
        self.generate_schedules()
        # self.generate_lighting_index()
        # self.create_el_wrapper()

    
    def load_json_data(self, json_path):
        with open(json_path, 'r') as file:
            data = json.load(file)
            return data


    def generate_number_occupants(self):
        '''
        Generate number of occupants for different of building types.
        According to the data in  data\occupancy_schedules\average_occupancy.json

        Parameters
        ----------
        random_nb : random number in [0,1)

        '''
        keys = [
            "oag",
            "IWU Research and University Teaching",
            "IWU Health and Care",
            "IWU School, Day Nursery and other Care",
            "IWU Culture and Leisure",
            "IWU Sports Facilities",
            "IWU Hotels, Boarding, Restaurants or Catering",
            "IWU Production, Workshop, Warehouse or Operations",
            "IWU Trade Buildings",
            "IWU Technical and Utility (supply and disposal)",
            "IWU Transport",
            "IWU Generalized (1) Services building, Includes categories (1) to (7) and (9)",
            "IWU Generalized (2) Production buildings and similar, Includes cat. (8), (10), (11)"
        ]



    
        if self.usage in self.occupancy_data:
            occupancy_values = self.occupancy_data[self.usage]
            random_nb = rd.random()  # picking random number in [0,1)
            if random_nb < 1 / 3:
                self.nb_occ.append(self.area/occupancy_values["Gering"])
                self.occupancy = "Gering"
            elif random_nb < 2 / 3:
                self.nb_occ.append(self.area/occupancy_values["Mittel"])
                self.occupancy = "Mittel"
            else:
                self.nb_occ.append(self.area/occupancy_values["Hoch"])
                self.occupancy = "Hoch"
        else:
            print(f"No data available for building type: {self.usage}")

    def generate_schedules(self):
        # get schedules occupancy
        df_schedules, schedule = schedules.get_schedule(self.usage)
        nb_days =  timeDiscretization=self.time["timeResolution"],
                                          timeSteps=self.time["timeSteps"]
        schedules.adjust_schedule(inital_day=0, nb_days=)
        self.occupancy_schedule = df_schedules["OCCUPANCY"]
        self.appliance_schedule = df_schedules["APPLIANCES"]
        #To-Do: Replace with key
        self.lighntning_schedule = df_schedules["LIGHTING"]
        
    def generate_annual_el_consumption_equipment(self, equipment="Mittel"):
        '''
        Generate annual elictricity consumption in dependency of the building type and the average area. 
        
        Attributes
        ---------
        equipment - depending on the class of equipment, the electricity demand is caclulated. 
        Data is described in: data\consumption_data\info.txt
        Possible Values are: "Gering", "Mittel", "Hoch". Default is "Mittel. 
            "Gering": 4.5,
            "Mittel": 6.5,
            "Hoch": 23

        Parameters
        ----------
        standard_consumption : standard annual consumption in kWh (assumption)
         - dhw demand is not included 

        '''
        # For Residential buildings,
        # the Stromspiegel is used
        # In DIBS only electricity used for heating is simulated
        # Several approaches might be used for Non-Residential,
        # such as calculation bases on users, tasks, e.g. 
        # Here the calculation is done, based on the average equipment in the building type 
        # For more information see: 
        # [1] S. Henning and K. Jagnow, “Statistische Untersuchung der Flächen- und Nutzstromanateile von Zonen in Nichtwohngebäuden (Fortführung),” 51/2023, Jul. 2023. [Online]. Available: https://www.bbsr.bund.de/BBSR/DE/veroeffentlichungen/bbsr-online/2023/bbsr-online-51-2023-dl.pdf?__blob=publicationFile&v=3
        # [2] K. Jagnow and S. Henning, “Statistische Untersuchung der Flächen- und Nutzstromanteile von Zonen in Nichtwohngebäuden,” Hochschule	Magdeburg-Stendal, Mar. 2020. [Online]. Available: https://www.h2.de/fileadmin/user_upload/Fachbereiche/Bauwesen/Forschung/Forschungsberichte/Endbericht_SWD-10.08.18.7-18.29.pdf


        
        if self.usage in self.electricity_data:
            electricity_values = self.electricity_data[self.usage]
            try: 
                annual_el_demand_temp = electricity_values[equipment] * self.area 
                self.annual_el_demand = rd.gauss(annual_el_demand_temp,
                                                        annual_el_demand_temp * 0.10)  # assumption: standard deviation 20% of mean value

            except KeyError:
                print(f"No data about annual electrical consumption available for building type: {self.usage}")
            # To Do 
            # Check if randomifaction of electriciy set up works  
        else:
            print(f"No data about annual electrical consumption available available for building type: {self.usage}")

    def generate_annual_el_consumption_lightning(self):
        """
        Creates 
        """
        # Mapping cardinal directions to azimuth angles
        windows = self.envelope.A["window"] # ["window"]
        # Filter out the 'sum' key if present
        windows = {key: value for key, value in windows.items() if key != 'sum'}
        orientations = {
            'north': 0,
            'east': 90,
            'south': 180,
            'west': 270
        }

        beta = [90] * len(windows)  # tilt for all windows
        gamma = [orientations[key] for key in windows.keys()]  # azimuths based on orientation
        Sun = SunIlluminance(filePath=self.envelope.file_path)
        illuminance = Sun.calcIlluminance(initialTime=0, timeDiscretization=self.time["timeResolution"],
                                          timeSteps=self.time["timeSteps"], timeZone=self.site["timeZone"], location=self.site["location"], altitude=self.site["altitude"],
                                          beta=beta, gamma=gamma,
                                          normal_direct_illuminance=self.site["IlluminanceDirect"], 
                                          horizontal_diffuse_illuminance=self.site["IlluminaceDiffuse"])
        print(illuminance, "This is the illuminance")
        # To-Do: 
        # Calculate Energy Demand throuhg lighning
        self.annual_lightning_demand = light_demand.calculate_light_demand(building_type=self.usage, illuminance=illuminance, 
                                                                           occupancy=self.occupancy, area=self.area)
    


    def create_el_wrapper(self) :
        '''
        Smiliar to thec creat a wrapper-object in the Residential configuration, 
        this generates the information about lighning and appliances. 



        Parameters
        ----------
        annual_demand : integer
            Annual elictricity demand in kWh.
        light_config : integer
            This index defines the lighting configuration of the houshold.
            There are 100 predifined ligthing configurations.


        '''

        # Write a function, that returns the respective 
        # Can be deleted 
        src_path = os.path.dirname(richardsonpy.__file__)
        path_app = os.path.join(src_path,'inputs','Appliances.csv')
        path_light = os.path.join(src_path,'inputs','LightBulbs.csv')

        # To-Do: Adjust thte code, so it wraps the lightning
        
        # Full Electricity Demand equals to:
        # User_related_Demand + Central Demand + Diverse Demand 
        #  
        # Source: [1] S. Henning and K. Jagnow, 
        # “Statistische Untersuchung der Flächen- und Nutzstromanateile von Zonen in Nichtwohngebäuden (Fortführung),” 
        # 51/2023, Jul. 2023. [Online]. Available: https://www.bbsr.bund.de/BBSR/DE/veroeffentlichungen/bbsr-online/2023/bbsr-online-51-2023-dl.pdf?__blob=publicationFile&v=3
        # Pages: 80-81
        # To-Do: Find factor for calclulation of annual demand  

        appliancesDemand =  self.annual_el_demand + 0 

        #  Create and save appliances object
        appliances = \
            app_model.Appliances(path_app,
                                annual_consumption=appliancesDemand,
                                randomize_appliances=True,
                                max_iter=15,
                                prev_heat_dev=True)

        # Create and save light configuration object
        lights = light_model.load_lighting_profile(filename=path_light,
                                                index=self.lighting_index)

        #  Create wrapper object
        self.el_wrapper.append(wrap.ElectricityProfile(appliances,lights))


    def calcProfiles(self, site, time_resolution, time_horizon, initital_day=1):
        '''
        Calclulate profiles for every flat and summarize them for the whole building

        Parameters
        ----------
        site: dict
            site data, e.g. weather
        initial_day : integer
            Day of the week with which the generation starts
            1-7 for monday-sunday.
        time_horizon : integer
            Time horizon for which a stochastic profile is generated.
        time_resolution : integer
            resolution of time steps of output array in seconds.
        irradiation: array
            if none is given default weather data (TRY 2015 Potsdam) is used


        '''

        irradiation = site["SunTotal"]
        T_e = site["T_e"]

        time_day = 24 * 60 * 60
        nb_days = int(time_horizon/time_day)

        self.occ = np.zeros(int(time_horizon/time_resolution))
        self.dhw = np.zeros(int(time_horizon/time_resolution))
        self.elec = np.zeros(int(time_horizon/time_resolution))
        self.gains = np.zeros(int(time_horizon/time_resolution))
        
        # To-Do
        # Write a funtion, that get's occupancy data 
        # based on amount of occupants and SIA profiles 
        # Write Function that generates an lighning profile
        # Write DHW function

        temp_obj = NonResidentialProfiles(building_type=self.usage, max_number_occupants=self.nb_occ, area=self.area,
                                          initital_day=initital_day, nb_days=nb_days, time_resolution=time_resolution)
        self.occ = temp_obj.generate_occupancy_profiles()
        self.dhw = temp_obj.generate_dhw_profile()
        # Electircal profile needs to be generated for this 
        # Calculation of user demand + lighning + other 
        self.elec = temp_obj.generate_el_profile(irradiance=irradiation,
                                                 annual_demand=self.annual_el_demand)
        self.gains = temp_obj.generate_gain_profile()
        

    def calcHeatingProfile(self,site,envelope,time_resolution):

        '''
        Calclulate heat demand for each building

        Parameters
        ----------
        site: dict
            site data, e.g. weather
        envelope: object
            containing all physical data of the envelope
        time_resolution : integer
            resolution of time steps of output array in seconds.
        Q_HC : float
            Heating (positive) or cooling (negative) load for the current time
            step in Watt.

        '''


        dt = time_resolution/(60*60)
        # calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s)
        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope,site["T_e"],dt)
        # heating  load for the current time step in Watt
        self.heat = np.zeros(len(Q_HC))
        for t in range(len(Q_HC)):
            self.heat[t] = max(0,Q_HC[t])

    def saveProfiles(self,unique_name,path):
        '''
        Save profiles to csv

        Parameters
        ----------
        unique_name : string
            unique building name
        path : string
            results path
        '''
        if not os.path.exists(path):
            os.makedirs(path)
        np.savetxt(path + '/elec_' + unique_name + '.csv', self.elec, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/dhw_' + unique_name + '.csv', self.dhw, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/occ_' + unique_name + '.csv', self.occ, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/gains_' + unique_name + '.csv', self.gains, fmt='%1.2f', delimiter=',')

        '''
        fields = [name + "_" + str(id), str(sum(self.nb_occ))]
        with open(path + '/_nb_occupants.csv','a') as f :
            writer = csv.writer(f)
            writer.writerow(fields)
        '''

    def saveHeatingProfile(self,unique_name,path) :
        '''
        Save heat demand to csv

        Parameters
        ----------
        unique_name : string
            unique building name
        path : string
            results path
        '''
        print(path)

        np.savetxt(path + '/heat_' + unique_name + '.csv',self.heat,fmt='%1.2f',delimiter=',')

    def loadProfiles(self,unique_name,path):
        '''
        Load profiles from csv

        Parameters
        ----------
        unique_name : string
            unique building name
        path : string
            results path
        '''

        self.elec = np.loadtxt(path + '/elec_' + unique_name + '.csv', delimiter=',')
        self.dhw = np.loadtxt(path + '/dhw_' + unique_name + '.csv', delimiter=',')
        self.occ = np.loadtxt(path + '/occ_' + unique_name + '.csv', delimiter=',')
        self.gains = np.loadtxt(path + '/gains_' + unique_name + '.csv', delimiter=',')


    


class NonResidentialLighting(object):

      def __init__(self, building_usage):
        """
        Constructor of Non Residential Lighning Class. 



        #ToDo: 
        """

        self.usage = building_usage 
        # self.area = area
        # self.nb_flats = None
        self.annual_el_demand = None
        self.lighting_index = []
        self.el_wrapper = []
        self.nb_occ = []
        self.occ = None
        self.dhw = None
        self.elec = None
        self.gains = None
        self.heat = None
    


    


if __name__ == '__main__':

    test = Users(building="SFH",
                area=1000)

    test.calcProfiles()