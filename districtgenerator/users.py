import os, math
import random as rd
import numpy as np
import pandas as pd
import openpyxl
from classes.profils import Profiles
import richardsonpy
import richardsonpy.classes.stochastic_el_load_wrapper as wrap
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
import functions.heating_profile_5R1C as heating



class Users():
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


    def generate_number_flats(self ,area):
        '''
        Generate number of flats for different of building types.
        Possible building types are:
            - single family house (SFH)
            - terraced house (TH)
            - multifamily house (MFH)
            - apartment block (AB)

        Assumes the average area of a flat is 100 square meters in MFH and AB.

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

        data_dict = {
            'elec': (self.elec, "Electricity demand in W"),
            'dhw': (self.dhw, "Drinking hot water in W"),
            'occ': (self.occ, "Occupancy of persons"),
            'gains': (self.gains, "Internal gains in W"),
            'car': (self.car, "Electricity demand of EV in W")
        }
        if not os.path.exists(path):
            os.makedirs(path)
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

