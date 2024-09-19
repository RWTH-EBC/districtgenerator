# -*- coding: utf-8 -*-
"""
"""

import os, math
import random as rd
import numpy as np
import pandas as pd
from districtgenerator.profils import Profiles
import richardsonpy
import richardsonpy.classes.stochastic_el_load_wrapper as wrap
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
import functions.heating_profile_5R1C as heating

class Users():
    '''
    Building Users class describing the number of occupants and their configs

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



    def __init__(self, building, area):
        """
        Constructor of Users Class
        """

        self.building = building
        self.nb_flats = None
        self.annual_el_demand = None
        self.lighting_index = []
        self.el_wrapper = []
        self.nb_occ = []
        self.occ = None
        self.dhw = None
        self.elec = None
        self.gains = None
        self.heat = None
        self.cool = None

        self.generate_number_flats(area)
        self.generate_number_occupants()
        self.generate_annual_el_consumption()
        self.generate_lighting_index()
        self.create_el_wrapper()


    def generate_number_flats(self,area):
        '''
        Generate number of flats for different of building types.

        Parameters
        ----------
        area : integer
            Floor area of different building types

        '''
        if self.building == "SFH":
            self.nb_flats = 1
        elif self.building == "TH":
            self.nb_flats = 1
        elif self.building == "MFH":
            if area <= 4*100:
                self.nb_flats = 4
            elif area > 4 * 100:
                self.nb_flats = math.floor(area/100)
        elif self.building == "AB":
            if area <= 10*100:
                self.nb_flats = 10
            elif area > 10*100:
                self.nb_flats = math.floor(area/100)

    def generate_number_occupants(self):
        '''
        Generate number of occupants for different of building types.

        Parameters
        ----------
        random_nb : random number in [0,1)

        '''

        if self.building == "SFH":
            # choose random number of occupants (2-5) for single family houses  (assumption)

            # loop over all flats of current multi family house
            for j in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one (additional) occupant
                # the random number decides how many occupants are chosen (2-5)
                while j <= 4 :
                    if random_nb < j / 4 :
                        self.nb_occ.append(1 + j)  # minimum is 2 occupants
                        break
                    j += 1

        if self.building == "TH":
            # choose random number of occupants (2-5) for single family houses  (assumption)

            # loop over all flats of current multi family house
            for j in range(self.nb_flats) :
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one (additional) occupant
                # the random number decides how many occupants are chosen (2-5)
                while j <= 4 :
                    if random_nb < j / 4 :
                        self.nb_occ.append(1 + j)  # minimum is 2 occupants
                        break
                    j += 1

        if self.building == "MFH":
            # choose random number of occupants (1-4) for each flat in the multi family house  (assumption)

            # loop over all flats of current multi family house
            for j in range(self.nb_flats) :
                random_nb = rd.random()  # picking random number in [0,1)
                k = 1
                # the random number decides how many occupants are chosen (1-5)
                while k <= 4 :
                    if random_nb < k / 4 :
                        self.nb_occ.append(k)
                        break
                    k += 1

        if self.building == "AB":
            # choose random number of occupants (1-4) for each flat in the apartment block  (assumption)

            # loop over all flats of current multi family house
            for j in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                k = 1
                # the random number decides how many occupants are chosen (1-5)
                while k <= 4 :
                    if random_nb < k / 4 :
                        self.nb_occ.append(k)
                        break
                    k += 1


    def generate_annual_el_consumption(self):
        '''
        Generate annual elictricity consumption
        in dependency of the building type and the number of occupants

        Parameters
        ----------
        standard_consumption : standard annual consumption in kWh (assumption)
         - dhw demand is not included 

        '''

        # source: https://www.stromspiegel.de/stromverbrauch-verstehen/stromverbrauch-im-haushalt/#c120951
        # method: https://www.stromspiegel.de/ueber-uns-partner/methodik-des-stromspiegels/
        standard_consumption = {"SFH" : {1 : 2300,
                                         2 : 3000,
                                         3 : 3500,
                                         4 : 4000,
                                         5 : 5000},
                                "MFH" : {1 : 1300,
                                         2 : 2000,
                                         3 : 2500,
                                         4 : 2600,
                                         5 : 3000}}

        self.annual_el_demand = np.zeros(self.nb_flats)
        for j in range(self.nb_flats):
            if self.building == "SFH":
                annual_el_demand_temp = standard_consumption["SFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(annual_el_demand_temp,
                                                         annual_el_demand_temp * 0.10)  # assumption: standard deviation 20% of mean value
            if self.building == "TH":
                annual_el_demand_temp = standard_consumption["SFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(annual_el_demand_temp,
                                                         annual_el_demand_temp * 0.10)  # assumption: standard deviation 20% of mean value
            if self.building == "MFH":
                annual_el_demand_temp = standard_consumption["MFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(annual_el_demand_temp,
                                                 annual_el_demand_temp * 0.10)  # assumption: standard deviation 20% of mean value
            if self.building == "AB":
                annual_el_demand_temp = standard_consumption["MFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(annual_el_demand_temp,
                                                 annual_el_demand_temp * 0.10)  # assumption: standard deviation 20% of mean value


    def generate_lighting_index(self):
        '''
        Choose a random lighting index between 0 and 99.
        This index defines the lighting configuration of the houshold.
        There are 100 predifined ligthing configurations.

        Assumption: All light configurations are equally probable. 
        No distinction is made between SHF and MFH.

        Parameters
        ----------
        random_nb : random number in [0,1)
        '''

        for j in range(self.nb_flats):
            random_nb = rd.random()
            self.lighting_index.append(int(random_nb * 100))


    def create_el_wrapper(self) :
        '''
        Creat a wrapper-object
        holding information about the lighting and appliance configuration.

        Parameters
        ----------
        annual_demand : integer
            Annual elictricity demand in kWh.
        light_config : integer
            This index defines the lighting configuration of the houshold.
            There are 100 predifined ligthing configurations.


        '''

        src_path = os.path.dirname(richardsonpy.__file__)
        path_app = os.path.join(src_path,'inputs','Appliances.csv')
        path_light = os.path.join(src_path,'inputs','LightBulbs.csv')


        for j in range(self.nb_flats):

            # annual demand of the elictric appliances (annual demand minus lighting)
            # source: https://www.umweltbundesamt.de/daten/private-haushalte-konsum/wohnen/energieverbrauch-privater-haushalte#stromverbrauch-mit-einem-anteil-von-rund-einem-funftel
            # values from diagram for 2018 without heating, dhw and cooling: 8,1 / 81,1 = 10,0%
            appliancesDemand = 0.9 * self.annual_el_demand[j]

            #  Create and save appliances object
            appliances = \
                app_model.Appliances(path_app,
                                 annual_consumption=appliancesDemand,
                                 randomize_appliances=True,
                                 max_iter=15,
                                 prev_heat_dev=True)

            # Create and save light configuration object
            lights = light_model.load_lighting_profile(filename=path_light,
                                                   index=self.lighting_index[j])

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
        for j in range(self.nb_flats):
            temp_obj = Profiles(self.nb_occ[j],initital_day,nb_days,time_resolution)
            self.occ = self.occ + temp_obj.generate_occupancy_profiles()
            self.dhw = self.dhw + temp_obj.generate_dhw_profile()
            #To-Do: Check how the irridation is modeled here and why it is not illuminance
            self.elec = self.elec + temp_obj.generate_el_profile(irradiance=irradiation,
                                                                 el_wrapper=self.el_wrapper[j],
                                                                 annual_demand=self.annual_el_demand[j])
            self.gains = self.gains + temp_obj.generate_gain_profile()

    def calcHeatingProfile(self,site, envelope, time_resolution) :

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
        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope, envelope.T_set_min, site["T_e"], dt)
        # heating  load for the current time step in Watt
        self.heat = np.zeros(len(Q_HC))
        self.heat = np.maximum(0, Q_HC)

        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope, envelope.T_set_max, site["T_e"], dt)
        # Cooling load for the current time step in Watt
        self.cool = np.zeros(len(Q_HC))
        self.cool = np.minimum(0, Q_HC)
    

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
 
        data = pd.DataFrame({
            'elec': self.elec,
            'dhw': self.dhw,
            'occ': self.occ,
            'gains': self.gains,
            'heat': self.heat,
            'cool': self.cool
        })
        data.to_csv(path + f'/{unique_name}' + '.csv', index=False)


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

        np.savetxt(path + '/heat_' + unique_name + '.csv',self.heat,fmt='%1.2f',delimiter=',')
        if not os.path.exists(path):
            os.makedirs(path)
        file_path = path + f'/{unique_name}'+ '.csv'
        if os.path.exists(file_path):
            data = pd.read_csv(file_path)
            data['heat'] = self.heat
        else:
            data = pd.DataFrame({
                'heat': self.heat
            })
            data.to_csv(file_path, index=False)

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


if __name__ == '__main__':

    test = Users(building="SFH",
                area=1000)

    test.calcProfiles()