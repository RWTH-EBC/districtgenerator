# -*- coding: utf-8 -*-

import os, math
import random as rd
import numpy as np
from classes.profils import Profiles
import richardsonpy
import richardsonpy.classes.stochastic_el_load_wrapper as wrap
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
import districtgenerator.functions.heating_profile_5R1C as heating


class Users:
    """
    Building Users class describing the number of occupants and their configs.

    Parameters
    ----------
    building : string
        Building type according to TABULA database.
    area : integer
        Total floor area of the building [m²].

    Attributes
    ----------
    building : string
        Building type according to TABULA database.
    nb_flats : integer
        Number of flats in building.
    annual_el_demand : array-like
        Annual electricity consumption in dependency of the building type and the number of occupants.
    lighting_index : integer
        This index defines the lighting configuration of the household.
    el_wrapper : object
        This objects holds information about the lighting and appliance configuration.
    nc_occ : list
        List with the number of occupants for each flat of the current building.
    occ : array-like
        Occupancy profile for each flat of the current building.
    dhw : array-like
        Drinking hot water profile for each building.
    elec : array-like
        Electrical demand for each building.
    gains : array-like
        Internal gains for each building.
    heat : array-like
        Heat demand for each building.
    """

    def __init__(self, building, area):
        """
        Constructor of Users class.

        Returns
        -------
        None.
        """

        self.building = building
        self.nb_flats = None
        self.annual_el_demand = None
        self.annual_heat_demand = None
        self.annual_dhw_demand = None
        self.annual_cooling_demand = None
        self.lighting_index = []
        self.el_wrapper = []
        self.nb_occ = []
        self.occ = None
        self.dhw = None
        self.elec = None
        self.gains = None
        self.heat = None
        self.cooling = None

        self.generate_number_flats(area)
        self.generate_number_occupants()
        self.generate_annual_el_consumption()
        self.generate_lighting_index()
        self.create_el_wrapper()

    def generate_number_flats(self, area):
        """
        Generate number of flats for different of building types.
        Possible building types are:
            - single family house (SFH)
            - terraced house (TH)
            - multifamily house (MFH)
            - apartment block (AP)

        Parameters
        ----------
        area : integer
            Floor area of different building types.

        Returns
        -------
        None.
        """

        if self.building == "SFH":
            self.nb_flats = 1
        elif self.building == "TH":
            self.nb_flats = 1
        elif self.building == "MFH":
            if area <= 6 * 100:
                self.nb_flats = 6
            elif area > 6 * 100:
                self.nb_flats = 8
        elif self.building == "AB":
            self.nb_flats = 8


    def generate_number_occupants(self):
        """
        Generate number of occupants for different of building types.

        Parameters
        ----------
        random_nb : random number in [0,1).

        Returns
        -------
        None.
        """

        if self.building == "SFH":
            # choose random number of occupants (2-5) for single family houses (assumption)

            # loop over all flats of current building
            for j in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one (additional) occupant
                # the random number decides how many occupants are chosen (2-5)
                while j <= 4:
                    if random_nb < j / 4:
                        self.nb_occ.append(1 + j)  # minimum is 2 occupants
                        break
                    j += 1

        if self.building == "TH":
            # choose random number of occupants (2-5) for terraced houses (assumption)

            # loop over all flats of current building
            for j in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one (additional) occupant
                # the random number decides how many occupants are chosen (2-5)
                while j <= 4:
                    if random_nb < j / 4:
                        self.nb_occ.append(1 + j)  # minimum is 2 occupants
                        break
                    j += 1

        if self.building == "MFH":
            # choose random number of occupants (1-4) for each flat in the multifamily house (assumption)

            # loop over all flats of current building
            for j in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                k = 1
                # the random number decides how many occupants are chosen (1-4)
                while k <= 4:
                    if random_nb < k / 4:
                        self.nb_occ.append(k)
                        break
                    k += 1

        if self.building == "AB":
            # choose random number of occupants (1-4) for each flat in the apartment block  (assumption)

            # loop over all flats of current building
            for j in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                k = 1
                # the random number decides how many occupants are chosen (1-4)
                while k <= 4:
                    if random_nb < k / 4:
                        self.nb_occ.append(k)
                        break
                    k += 1

    def generate_annual_el_consumption(self):
        """
        Generate annual electricity consumption
        in dependency of the building type and the number of occupants.

        Parameters
        ----------
        standard_consumption : standard annual consumption in kWh (assumption).

        Returns
        -------
        None.
        """

        # source: https://www.stromspiegel.de/stromverbrauch-verstehen/stromverbrauch-im-haushalt/#c120951
        # method: https://www.stromspiegel.de/ueber-uns-partner/methodik-des-stromspiegels/
        standard_consumption = {"SFH": {1: 2400,
                                        2: 3000,
                                        3: 3600,
                                        4: 4000,
                                        5: 5000},
                                "MFH": {1: 1400,
                                        2: 2000,
                                        3: 2600,
                                        4: 2900,
                                        5: 3000}}

        self.annual_el_demand = np.zeros(self.nb_flats)
        # assumption: standard deviation 10% of mean value
        for j in range(self.nb_flats):
            if self.building == "SFH":
                annual_el_demand_temp = standard_consumption["SFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(annual_el_demand_temp, annual_el_demand_temp * 0.10)
            if self.building == "TH":
                annual_el_demand_temp = standard_consumption["SFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(annual_el_demand_temp, annual_el_demand_temp * 0.10)
            if self.building == "MFH":
                annual_el_demand_temp = standard_consumption["MFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(annual_el_demand_temp, annual_el_demand_temp * 0.10)
            if self.building == "AB":
                annual_el_demand_temp = standard_consumption["MFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(annual_el_demand_temp, annual_el_demand_temp * 0.10)

    def generate_lighting_index(self):
        """
        Choose a random lighting index between 0 and 99.
        This index defines the lighting configuration of the household.
        There are 100 predefined lighting configurations.

        Assumptions: - All lighting configurations have the same probability.
                     - No differences between SFH, TH, MFH and AB.

        Parameters
        ----------
        random_nb : random number in [0,1).

        Returns
        -------
        None.
        """

        for j in range(self.nb_flats):
            random_nb = rd.random()
            self.lighting_index.append(int(random_nb * 100))

    def create_el_wrapper(self):
        """
        Create a wrapper-object
        holding information about the lighting and appliance configuration.

        Parameters
        ----------
        annual_demand : integer
            Annual electricity demand in kWh.
        light_config : integer
            This index defines the lighting configuration of the household.
            There are 100 predefined lighting configurations.

        Returns
        -------
        None.
        """

        src_path = os.path.dirname(richardsonpy.__file__)
        path_app = os.path.join(src_path, 'inputs', 'Appliances.csv')
        path_light = os.path.join(src_path, 'inputs', 'LightBulbs.csv')

        for j in range(self.nb_flats):

            # annual demand of the electric appliances (annual demand minus lighting)
            # source: https://www.umweltbundesamt.de/daten/private-haushalte-konsum/wohnen/energieverbrauch-privater-haushalte#stromverbrauch-mit-einem-anteil-von-rund-einem-funftel
            # values from diagram for 2018 without heating, dhw and cooling: 8,1 / 81,1 = 10,0%
            appliancesDemand = 0.9 * self.annual_el_demand[j]

            # Create and save appliances object
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
            self.el_wrapper.append(wrap.ElectricityProfile(appliances, lights))

    def calcProfiles(self, site, time_resolution, time_horizon, building, path, initial_day=1):
        """
        Calculate profiles for every flat and summarize them for the whole building

        Parameters
        ----------
        site: dict
            Site data, e.g. weather.
        time_resolution : integer
            Resolution of time steps of output array in seconds.
        time_horizon : integer
            Time horizon for which a stochastic profile is generated.
        initial_day : integer, optional
            Day of the week with which the generation starts.
            1-7 for monday-sunday. The default is 1.

        Returns
        -------
        None.
        """

        irradiation = site["SunTotal"]
        T_e = site["T_e"]

        time_day = 24 * 60 * 60
        nb_days = int(time_horizon/time_day)
        #if building["unique_name"]

        self.occ = np.zeros(int(time_horizon / time_resolution))
        self.dhw = np.zeros(int(time_horizon / time_resolution))
        self.elec = np.zeros(int(time_horizon / time_resolution))
        self.gains = np.zeros(int(time_horizon / time_resolution))
        self.car = np.zeros(int(time_horizon / time_resolution))
        if building['buildingFeatures']['building'] == "AB":
            unique_name = "MFH_" + str(building["user"].nb_flats) + "_" + str(building['buildingFeatures']['id'])
        elif building['buildingFeatures']['building'] == "TH":
            unique_name = "SFH_" + str(building["user"].nb_flats) + "_" + str(building['buildingFeatures']['id'])
        else:
            unique_name = building['unique_name']
        for j in range(self.nb_flats):
            temp_obj = Profiles(self.nb_occ[j], initial_day, nb_days, time_resolution)
            self.dhw = self.dhw + temp_obj.generate_dhw_profile(building=building)
            self.occ = self.occ + temp_obj.generate_occupancy_profiles()
            self.elec = self.elec + temp_obj.generate_el_profile(irradiance=irradiation,
                                                                 el_wrapper=self.el_wrapper[j],
                                                                 annual_demand=self.annual_el_demand[j])
            self.gains = self.gains + temp_obj.generate_gain_profile()
        # currently only one car per building possible
        self.car = self.car + temp_obj.generate_EV_profile(self.occ)

        # ------ Webtool: import of existing time series to save computing time ------ #
        #self.occ = np.loadtxt(path + '/occ_' + unique_name + '.csv', delimiter=',')
        #self.car = np.loadtxt(path + '/car_' + unique_name + '.csv', delimiter=',')
        #self.elec = np.loadtxt(path + '/elec_' + unique_name + '.csv', delimiter=',')
        #self.gains = np.loadtxt(path + '/gains_' + unique_name + '.csv', delimiter=',')

    def calcHeatingProfile(self, site, envelope, time_resolution):
        """
        Calculate heat demand for each building.

        Parameters
        ----------
        site: dict
            Site data, e.g. weather.
        envelope: object
            Containing all physical data of the envelope.
        time_resolution : integer
            Resolution of time steps of output array in seconds.
        Q_HC : float
            Heating (positive) or cooling (negative) load for the current time
            step in Watt.

        Returns
        -------
        None.
        """

        dt = time_resolution/(60*60)
        # calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s)
        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope, envelope.T_set_min, site["T_e"], dt)
        #(Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc(envelope, site["T_e"], dt)
        # heating  load for the current time step in Watt
        self.heat = np.zeros(len(Q_HC))
        for t in range(len(Q_HC)):
            self.heat[t] = max(0, Q_HC[t])
        self.annual_heat_demand = np.sum(self.heat)

        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope, envelope.T_set_max, site["T_e"], dt)
        self.cooling = np.zeros(len(Q_HC))
        for t in range(len(Q_HC)):
            self.cooling[t] = min(0, Q_HC[t]) * (-1)
        self.annual_cooling_demand = np.sum(self.cooling)

    def saveProfiles(self, unique_name, path):
        """
        Save profiles to csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """

        np.savetxt(path + '/elec_' + unique_name + '.csv', self.elec, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/dhw_' + unique_name + '.csv', self.dhw, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/occ_' + unique_name + '.csv', self.occ, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/gains_' + unique_name + '.csv', self.gains, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/car_' + unique_name + '.csv', self.car, fmt='%1.2f', delimiter=',')

        '''
        fields = [name + "_" + str(id), str(sum(self.nb_occ))]
        with open(path + '/_nb_occupants.csv','a') as f :
            writer = csv.writer(f)
            writer.writerow(fields)
        '''

    def saveHeatingProfile(self, unique_name, path):
        """
        Save heating demand to csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """

        np.savetxt(path + '/cooling_' + unique_name + '.csv', self.cooling, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/heating_' + unique_name + '.csv', self.heat, fmt='%1.2f', delimiter=',')

    def loadProfiles(self, unique_name, path):
        """
        Load profiles from csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """

        self.elec = np.loadtxt(path + '/elec_' + unique_name + '.csv', delimiter=',')
        self.dhw = np.loadtxt(path + '/dhw_' + unique_name + '.csv', delimiter=',')
        self.occ = np.loadtxt(path + '/occ_' + unique_name + '.csv', delimiter=',')
        self.gains = np.loadtxt(path + '/gains_' + unique_name + '.csv', delimiter=',')
        self.car = np.loadtxt(path + '/car_' + unique_name + '.csv', delimiter=',')


if __name__ == '__main__':

    test = Users(building="SFH",
                 area=1000)

    test.calcProfiles()