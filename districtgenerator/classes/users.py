# -*- coding: utf-8 -*-
import json
import statistics
import os, math
import random as rd
import numpy as np
import pandas as pd
import openpyxl
from .profils import Profiles
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
        self.generate_number_occupants(area)
        self.generate_annual_el_consumption()
        self.generate_lighting_index(area)
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
            if area <= 4 * 100:
                self.nb_flats = 4
            elif area > 4 * 100:
                self.nb_flats = rd.randint((area // 100) - 1, (area // 100) + 1)
        elif self.building == "AB":
            self.nb_flats = 8


    def generate_number_occupants(self,area):
        """
        Generate number of occupants for different building types.

        Parameters
        ----------
        random_nb : random number in [0,1).

        Returns
        -------
        None.
        """

        if self.building == "SFH":
            # choose random number of occupants (1-5) for single family houses  (assumption)
            probabilities = (0.245114, 0.402323, 0.154148, 0.148869, 0.049623) # Probabilities of having 1, 2, 3, 4 or 5 occupants in a single-family house, assuming a maximum of 5 occupants. Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html and https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            # loop over all flats of current single family house
            for k in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one occupant
                # the random number decides how many occupants are chosen (1-5)
                while j <= 5 :
                    if random_nb < sum(probabilities[:j]) :
                        self.nb_occ.append(j)  # minimum is 1 occupant
                        break
                    j += 1

        elif self.building == "TH":
            # choose random number of occupants (1-5) for terraced houses  (assumption)
            probabilities = (0.236817, 0.400092, 0.157261, 0.154371, 0.051457) # Probabilities of having 1, 2, 3, 4 or 5 occupants in a terraced house, assuming a maximum of 4 occupants. Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html and https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            # loop over all flats of current terraced house
            for k in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one occupant
                # the random number decides how many occupants are chosen (1-5)
                while j <= 5 :
                    if random_nb < sum(probabilities[:j]) :
                        self.nb_occ.append(j)  # minimum is 1 occupant
                        break
                    j += 1

        elif self.building == "MFH":
            # choose random number of occupants (1-5) for each flat in the multi family house  (assumption)
            probabilities = (0.490622, 0.307419, 0.101949, 0.074417, 0.024805) # Probabilities of having 1, 2, 3, 4 or 5 occupants in a flat, assuming a maximum of 4 occupants. Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html and https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            # loop over all flats of current multi family house
            for k in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one occupant
                # the random number decides how many occupants are chosen (1-5)
                while j <= 5 :
                    if random_nb < sum(probabilities[:j]) :
                        self.nb_occ.append(j)  # minimum is 1 occupant
                        break
                    j += 1

        elif self.building == "AB":
            # choose random number of occupants (1-5) for each flat in the apartment block  (assumption)
            probabilities = (0.490622, 0.307419, 0.101949, 0.074417, 0.024805) # Probabilities of having 1, 2, 3, 4 or 5 occupants in a flat, assuming a maximum of 4 occupants. Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html and https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            # loop over all flats of current apartment block
            for k in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one occupant
                # the random number decides how many occupants are chosen (1-5)
                while j <= 5 :
                    if random_nb < sum(probabilities[:j]) :
                        self.nb_occ.append(j)  # minimum is 1 occupant
                        break
                    j += 1


    def generate_annual_el_consumption(self):
        """
        Generate annual electricity consumption
        in dependency of the building type and the number of occupants.

        Parameters
        ----------
        consumption_range : range of the annual consumption of electricity in kWh, not including electricity used for heating, dhw and cooling

        Returns
        -------
        None.
        """
        if self.building in {"SFH","TH","MFH","AB"}:
        # source: https://www.stromspiegel.de/fileadmin/ssi/stromspiegel/Downloads/StromspiegelFlyer_2023_Web.pdf
        # method: https://www.stromspiegel.de/ueber-uns-partner/methodik-des-stromspiegels/
        # Depending on the number of occupants in the household, there is a range of annual electricity demand with the corresponding probabilities
            consumption_range = {"SFH" : {1 : [1100,1400,1800,2200,2600,3400,4500,4800],
                                             2 : [1700,2000,2500,2800,3100,3500,4300,4600],
                                             3 : [2200,2500,3000,3500,3900,4400,5200,5500],
                                             4 : [2500,2800,3500,3900,4300,5000,6000,6300],
                                             5 : [2900,3200,4000,4500,5200,6000,7600,7900]},
                                    "MFH" : {1 : [600,800,1000,1300,1500,1700,2100,2300],
                                             2 : [1200,1400,1700,2000,2300,2500,3000,3200],
                                             3 : [1500,1700,2100,2500,2900,3300,3800,4000],
                                             4 : [1600,1800,2300,2600,3000,3600,4400,4600],
                                             5 : [1300,1500,2100,2700,3400,4100,5500,5700]}}

            probabilities = [0.143, 0.143, 0.143, 0.142, 0.143, 0.143, 0.143]

            self.annual_el_demand = np.zeros(self.nb_flats)
            for j in range(self.nb_flats):
                if self.building == "SFH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand[j] = rd.randint(consumption_range["SFH"][self.nb_occ[j]][i - 1], consumption_range["SFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "TH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand[j] = rd.randint(consumption_range["SFH"][self.nb_occ[j]][i - 1],consumption_range["SFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "MFH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand[j] = rd.randint(consumption_range["MFH"][self.nb_occ[j]][i - 1], consumption_range["MFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "AB":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand[j] = rd.randint(consumption_range["MFH"][self.nb_occ[j]][i - 1], consumption_range["MFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
    def generate_lighting_index(self, area):
        """
        Choose a random lighting index between 0 and 99 for the residential buildings.
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
        if self.building in {"SFH","TH","MFH","AB"}:
            src_path = os.path.dirname(richardsonpy.__file__)
            path_app = os.path.join(src_path, 'inputs', 'Appliances.csv')
            path_light = os.path.join(src_path, 'inputs', 'LightBulbs.csv')

            for j in range(self.nb_flats):

                # annual demand of the electric appliances (annual demand minus lighting)
                # source: https://www.umweltbundesamt.de/daten/private-haushalte-konsum/wohnen/energieverbrauch-privater-haushalte#stromverbrauch-mit-einem-anteil-von-rund-einem-funftel
                # share of the electricity demand for lighting of the total electricity demand without heating, dhw and cooling for 2022: 7.9 / 81.8 = 9.6%
                appliancesDemand = 0.904 * self.annual_el_demand[j]

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

    def calcProfiles(self, site, holidays, time_resolution, time_horizon, building, path, initial_day=1):
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
        if self.building in {"SFH", "TH", "MFH", "AB"}:

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
                temp_obj = Profiles(number_occupants=self.nb_occ[j], number_occupants_building=sum(self.nb_occ),
                                    initial_day=initial_day, nb_days=nb_days, time_resolution=time_resolution,
                                    building=self.building)
                self.dhw = self.dhw + temp_obj.generate_dhw_profile(building=building, holidays=holidays)
                # Occupancy profile in a flat
                self.occ = self.occ + temp_obj.generate_occupancy_profiles_residential()
                self.elec = self.elec + temp_obj.generate_el_profile_residential(holidays=holidays,
                                                                                 irradiance=irradiation,
                                                                                 el_wrapper=self.el_wrapper[j],
                                                                                 annual_demand=self.annual_el_demand[j])
                self.gains = self.gains + temp_obj.generate_gain_profile_residential()
            # currently only one car per building possible
            self.car = self.car + temp_obj.generate_EV_profile(self.occ)

        # ------ Webtool: import of existing time series to save computing time ------ #
        # self.occ = np.loadtxt(path + '/occ_' + unique_name + '.csv', delimiter=',')
        # self.car = np.loadtxt(path + '/car_' + unique_name + '.csv', delimiter=',')
        # self.elec = np.loadtxt(path + '/elec_' + unique_name + '.csv', delimiter=',')
        # self.gains = np.loadtxt(path + '/gains_' + unique_name + '.csv', delimiter=',')

    def calcHeatingProfile(self, site, envelope, night_setback, holidays, time_resolution):
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

        dt = time_resolution / (60 * 60)
        # calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s)
        if night_setback == 1:
            (Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc_night_setback(envelope, site["T_e"], holidays, dt,
                                                                         self.building)
        elif night_setback == 0:
            (Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc(envelope, site["T_e"], holidays, dt, self.building)
        # heating and cooling loads for the current time step in Watt
        self.heat = Q_H
        self.cooling = Q_C
        self.annual_heat_demand = np.sum(Q_H)
        self.annual_cooling_demand = np.sum(Q_C)

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

        data_dict = {
            'elec': (self.elec, "Electricity demand in W"),
            'dhw': (self.dhw, "Drinking hot water in W"),
            'occ': (self.occ, "Occupancy of persons"),
            'gains': (self.gains, "Internal gains in W"),
            'car': (self.car, "Electricity demand of EV in W")
        }

        excel_file = os.path.join(path, unique_name + '.xlsx')

        with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
            for sheet_name, (data, header) in data_dict.items():
                df = pd.DataFrame(data)
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)


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

        excel_file = os.path.join(path, unique_name + '.xlsx')
        with pd.ExcelWriter(excel_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            cooling_df = pd.DataFrame(self.cooling)
            heating_df = pd.DataFrame(self.heat)
            cooling_df.to_excel(writer, sheet_name='cooling', index=False, header=False)
            heating_df.to_excel(writer, sheet_name='heating', index=False, header=False)

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

        excel_file = os.path.join(path, unique_name + '.xlsx')
        workbook = openpyxl.load_workbook(excel_file, data_only=True)
        def load_sheet_to_numpy(workbook, sheet_name):
            sheet = workbook[sheet_name]
            data = []
            for row in sheet.iter_rows(values_only=True):
                data.append(row[0])
            return np.array(data)

        self.elec = load_sheet_to_numpy(workbook, 'elec')
        self.dhw = load_sheet_to_numpy(workbook, 'dhw')
        self.occ = load_sheet_to_numpy(workbook, 'occ')
        self.gains = load_sheet_to_numpy(workbook, 'gains')
        self.car = load_sheet_to_numpy(workbook, 'car')

        workbook.close()

if __name__ == '__main__':

    test = Users(building="SFH",
                 area=1000)

    test.calcProfiles()
