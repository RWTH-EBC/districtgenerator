# -*- coding: utf-8 -*-

import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import sys
import os


class DemandPlots:
    """
    Class to generate plots of energy consumption and generation.
    """

    def __init__(self):
        """
        Constructor of DemandPlots class.
        Load economical and ecological data to compute costs and CO2 emissions.

        Returns
        -------
        None.
        """

        self.srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.resultPath = os.path.join(self.srcPath, 'results')

    def preparePlots(self, data):
        """
        Collect data to create plots.

        Parameters
        ----------
        data: object
            datahandler-object.

        Returns
        -------
        None.
        """

        # %% read in energy consumption and generation data

        # length of all energy consumption and generation profiles
        self.l = len(data.district[0]['user'].elec)

        # initialize arrays for profiles of the hole district
        self.y = {}
        # electricity demand of domestic appliances and lighting [kW]
        self.y['elec'] = np.zeros(self.l)
        # heat demand by domestic hot water consumption [kW]
        self.y['dhw'] = np.zeros(self.l)
        # cooling demand for space cooling [kW]
        self.y['cooling'] = np.zeros(self.l)
        # heat demand for space heating [kW]
        self.y['heating'] = np.zeros(self.l)

        # electricity demand of electric vehicles [kW]
        #self.y['car'] = np.zeros(self.l)
        # electricity generation of photovoltaic systems [kW]
        #self.y['pv'] = np.zeros(self.l)
        # heat generation of solar thermal collectors [kW]
        #self.y['stc'] = np.zeros(self.l)
        # electricity generation of wind turbines [kW]
        #self.y['wt'] = np.zeros(self.l)

        # loop over buildings to sum upp energy consumptions and generations for the hole district
        for b in range(len(data.district)):
            self.y['elec'] += data.district[b]['user'].elec / 1000
            self.y['dhw'] += data.district[b]['user'].dhw / 1000
            self.y['cooling'] += data.district[b]['user'].cooling / 1000
            self.y['heating'] += data.district[b]['user'].heat / 1000
            #self.y['car'] += data.district[b]['user'].car / 1000
            #self.y['pv'] += data.district[b]['user']['generationPV'] / 1000
            #self.y['stc'] += data.district[b]['user']['generationSTC'] / 1000

        # add renewable generation of central devices
        #self.y['pv'] += data.centralDevices['renewableGeneration']['centralPV'] / 1000
        #self.y['stc'] += data.centralDevices['renewableGeneration']['centralSTC'] / 1000
        #self.y['wt'] = data.centralDevices['renewableGeneration']['centralWT'] / 1000

        # compute electricity demand by domestic appliances, lighting and electric vehicles [W]
        #self.y['electricityDemand'] = self.y['elec'] + self.y['car']
        # compute heat demand by space heating and domestic hot water [W]
        #self.y['heatDemand'] = self.y['heating'] + self.y['dhw']

        # factor to convert power [kW] for one timestep to energy [kWh] for one timestep
        self.factor = data.time['timeResolution'] / 3600
        # time array for x-axis [h]
        self.time = data.time["timeResolution"] / 3600 \
                    * np.arange((365 * 24 * 60 * 60 / data.time["timeResolution"]))

        # labels of y-axis
        self.labels = {}
        self.labels['time'] = 'Time [h]'
        self.labels['elec'] = 'Electricity demand [kW]'
        self.labels['dhw'] = 'DHW demand [kW]'
        self.labels['cooling'] = 'Space cooling demand [kW]'
        self.labels['heating'] = 'Space heating demand [kW]'
        #self.labels['car'] = 'Electricity demand EV [kW]'
        #self.labels['pv'] = 'Power generation PV [kW]'
        #self.labels['stc'] = 'Heat generation STC [kW]'
        #self.labels['electricityDemand'] = 'Electricity demand [kW]'
        #self.labels['heatDemand'] = 'Heat demand [kW]'
        #self.labels['wt'] = 'Power generation WT [kW]'

        # plot titles
        self.titles = {}
        self.titles['elec'] = 'Electricity demand for domestic appliances and lighting'
        self.titles['dhw'] = 'Domestic hot water (DHW) demand of district'
        self.titles['cooling'] = 'Space cooling demand of district'
        self.titles['heating'] = 'Space heating demand of district'
        #self.titles['car'] = 'Electricity demand of electric vehicles (EV)'
        #self.titles['pv'] = 'Power generation of photovoltaic (PV) systems'
        #self.titles['stc'] = 'Heat generation of solar thermal collectors (STC)'
        #self.titles['electricityDemand'] = 'Electricity demand of district'
        #self.titles['heatDemand'] = 'Heat demand of district'
        #self.titles['wt'] = 'Power generation of wind turbines (WT)'

        # definition of default stepwise plots
        self.plots = ['elec', 'dhw', 'cooling', 'heating']  # 'pv', 'stc', 'heatDemand', 'wt']


        # %% monthly plots (bar plots)

        # days per month and cumulated days of months
        daysInMonhs = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
        cumutaltedDays = np.zeros(12)
        for i in range(len(cumutaltedDays)):
            if i == 0:
                cumutaltedDays[i] = daysInMonhs[i]
            else:
                cumutaltedDays[i] = cumutaltedDays[i-1] + daysInMonhs[i]

        # array with last time step of each month
        monthlyDataSteps = cumutaltedDays * 24 * 3600 / data.time['timeResolution']

        # create monthly data for bar plots
        self.y['elecMonthly'] = []
        self.y['dhwMonthly'] = []
        self.y['coolingMonthly'] = []
        self.y['heatingMonthly'] = []
        #self.y['carMonthly'] = []
        #self.y['pvMonthly'] = []
        #self.y['stcMonthly'] = []
        #self.y['electricityDemandMonthly'] = []
        #self.y['heatDemandMonthly'] = []
        #self.y['wtMonthly'] = []
        for m in range(len(cumutaltedDays)):
            if m == 0:
                # first month starts with time step zero
                start = 0
            else:
                # all the other months starts one time step after the last time step of the previous month
                start = int(monthlyDataSteps[m - 1]) + 1
            end = int(monthlyDataSteps[m]) + 1
            # convert power [W] to energy per month [kWh] by multiplication with factor
            self.y['elecMonthly'].append(np.sum(self.y['elec'][start:end] * self.factor))
            self.y['dhwMonthly'].append(np.sum(self.y['dhw'][start:end] * self.factor))
            self.y['coolingMonthly'].append(np.sum(self.y['cooling'][start:end] * self.factor))
            self.y['heatingMonthly'].append(np.sum(self.y['heating'][start:end] * self.factor))
            #self.y['carMonthly'].append(np.sum(self.y['car'][start:end] * self.factor))
            #self.y['pvMonthly'].append(np.sum(self.y['pv'][start:end] * self.factor))
            #self.y['stcMonthly'].append(np.sum(self.y['stc'][start:end] * self.factor))
            #self.y['electricityDemandMonthly'].append(np.sum(self.y['electricityDemand'][start:end] * self.factor))
            #self.y['heatDemandMonthly'].append(np.sum(self.y['heatDemand'][start:end] * self.factor))
            #self.y['wtMonthly'].append(np.sum(self.y['wt'][start:end] * self.factor))

        # months as categories for x-axis
        self.months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
                       'November', 'December']

        # labels of y-axis
        self.labels['elecMonthly'] = 'Electricity demand [kWh]'
        self.labels['dhwMonthly'] = 'DHW demand [kWh]'
        self.labels['coolingMonthly'] = 'Space cooling demand  [kWh]'
        self.labels['heatingMonthly'] = 'Space heating demand [kWh]'
        #self.labels['carMonthly'] = 'Electricity demand of EV [kWh]'
        #self.labels['pvMonthly'] = 'Power generation of PV systems [kWh]'
        #self.labels['stcMonthly'] = 'Heat generation of STC [kWh]'
        #self.labels['electricityDemandMonthly'] = 'Electricity demand [kWh]'
        #self.labels['heatDemandMonthly'] = 'Heat demand [kWh]'
        #self.labels['wtMonthly'] = 'Power generation of WT [kWh]'

        # plot titles
        self.titles['elecMonthly'] = 'Monthly electricity demand for domestic appliances and lighting'
        self.titles['dhwMonthly'] = 'Monthly domestic hot water (DHW) demand of district'
        self.titles['coolingMonthly'] = 'Monthly space cooling demand of district'
        self.titles['heatingMonthly'] = 'Monthly space heating demand of district'
        #self.titles['carMonthly'] = 'Monthly electricity demand of electric vehicles (EV)'
        #self.titles['pvMonthly'] = 'Monthly power generation of photovoltaic (PV) systems'
        #self.titles['stcMonthly'] = 'Monthly heat generation of solar thermal collectors (STC)'
        #self.titles['electricityDemandMonthly'] = 'Monthly electricity demand of district'
        #self.titles['heatDemandMonthly'] = 'Monthly heat demand of district'
        #self.titles['wtMonthly'] = 'Monthly power generation of wind turbines (WT)'

        # definition of default monthly plots
        self.plotsMonthly = \
            ['elec', 'dhw', 'cooling', 'heating']  #, 'car',  'pv', 'stc', 'electricityDemand', 'heatDemand', 'wt']

        # define colors for plot types
        blue = '#00549F'
        red = '#CC071E'
        green = '#57AB27'
        self.color = {}
        self.color['standard'] = blue
        self.color['elec'] = green
        self.color['dhw'] = red
        self.color['gains'] = red
        self.color['occ'] = blue
        self.color['car'] = green
        self.color['heating'] = red
        self.color['pv'] = green
        self.color['stc'] = red
        self.color['electricityDemand'] = green
        self.color['heatDemand'] = red
        self.color['standard'] = blue
        self.color['wt'] = green

    def defaultPlots(self, plotResolution='monthly', initialTime=0, timeHorizon=31536000, savePlots=True,
                     timeStamp=False, show=False):
        """
        Create of a selection of default plots.

        Parameters
        ----------
        plotResolution : string, optional
            Defines the plot resolution. The default is 'monthly'.
        initialTime : integer, optional
            Start of the plot in seconds from the beginning of the year. The default is 0.
        timeHorizon : integer, optional
            Length of the time horizon that is plotted in seconds. The default is 31536000 (what equals one year).
        savePlots : boolean, optional
            Decision if plots are saved under results/plots/. The default is True.
        timeStamp : boolean, optional
            Decision if saved plots get a unique name by adding a time stamp. The default is False.
        show : boolean, optional
            Option to show the plot directly. The default is False.

        Returns
        -------
        None.
        """

        if plotResolution == 'stepwise':
            plots = self.plots
        elif plotResolution == 'monthly':
            plots = self.plotsMonthly

        for plotType in plots:
            self.onePlot(plotType, plotResolution=plotResolution, initialTime=initialTime, timeHorizon=timeHorizon,
                         savePlots=savePlots, timeStamp=timeStamp, show=show)

    def onePlot(self, plotType, plotResolution='monthly', initialTime=0, timeHorizon=31536000, label=None, title=None,
                color=None, savePlots=True, timeStamp=False, show=False):
        """
        Create a single plot.

        Parameters
        ----------
        plotType : string
            Type of the plot.
            Options are
            ['elec', 'dhw', 'gains', 'car', 'heating', 'pv', 'stc', 'electricityDemand', 'heatDemand', 'wt'].
        plotResolution : string, optional
            Defines the plot resolution.
            Options are ['monthly', 'stepwise']. The default is 'monthly'.
        initialTime : integer, optional
            Start of the plot in seconds from the beginning of the year. The default is 0.
        timeHorizon : integer, optional
            Length of the time horizon that is plotted in seconds. The default is 31536000 (what equals one year).
        label : string, optional
            Custom y-axis label. Otherwise, a default label is used.
        title : string, optional
            Custom plot title. Otherwise, a default title is used.
        color : string, optional
            Custom plot color. Otherwise, a default color is used.
        savePlots : boolean, optional
            Decision if plots are saved under results/plots/. The default is True.
        timeStamp : boolean, optional
            Decision if saved plots get a unique name by adding a time stamp. The default is False.
        show : boolean, optional
            Option to show the plot directly. The default is False.

        Returns
        -------
        None.
        """

        # transform time data in seconds to data in hours
        initialTime_h = initialTime / 3600
        timeHorizon_h = timeHorizon / 3600

        # check validity of input
        if (initialTime < 0) or (timeHorizon < 0):
            sys.exit('No negative values for initial time and time horizon allowed!')
        if (plotType not in self.plots) and (plotType not in self.plotsMonthly):
            sys.exit('Selected plot type is invalid!')
        if plotResolution != 'stepwise' and plotResolution != 'monthly':
            sys.exit('Selected plot resolution is invalid!')
        # the initial time is shorter than one year
        initialTime_h = initialTime_h % 8760
        # just one year of data is available
        timeResolution = self.time[1] - self.time[0]
        if (initialTime_h + timeHorizon_h) > (self.time[-1] + timeResolution):
            timeHorizon_max = ((self.time[-1] + timeResolution) - initialTime_h) * 3600
            sys.exit('Selected initial time and time horizon are not compatible!\n'
                     'For selected initial time the maximal time horizon is ' + str(timeHorizon_max))

        if plotResolution == 'stepwise':

            # calculate index of first data step
            for t in range(len(self.time)):
                if self.time[t] == initialTime_h:
                    start_index = t
                    break
                elif self.time[t] > initialTime_h:
                    start_index = t -1
                    break
            # calculate index of last data step
            for t in range(len(self.time)):
                if self.time[t] + timeResolution >= (initialTime_h + timeHorizon_h):
                    end_index = t
                    break
            if end_index == None:
                sys.exit("Error with initial time and time horizon.")

            # slice of x and y values
            x = self.time[start_index:end_index + 1]
            y = self.y[plotType][start_index:end_index + 1]

            # determine if standard title, label and color are used
            if label == None:
                label = self.labels[plotType]
            if title == None:
                title = self.titles[plotType]
            if color == None:
                try:
                    color = self.color[plotType]
                except:
                    color = self.color['standard']

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.set_title(title, fontsize=15)
            ax.set_xlabel(self.labels['time'], fontsize=14)
            ax.set_ylabel(label, fontsize=14)
            plt.xticks(fontsize=14)
            plt.yticks(fontsize=14)

            plt.plot(x, y, color=color)

            # optional saving of the plot
            if savePlots:
                if timeStamp:
                    _now = datetime.now()
                    strDate = _now.strftime("%Y%m%d")
                    strTime = _now.strftime("%H%M%S")
                    stamp = '_D' + strDate + 'T' + strTime
                else:
                    stamp = ''
                plt.savefig(os.path.join(self.resultPath, 'plots') +  plotType + '_' + plotResolution + stamp,
                            dpi=300, bbox_inches="tight")

            if show:
                plt.show()

        elif plotResolution == 'monthly':

            # determine if standard title, label and color are used
            if label == None:
                label = self.labels[plotType + 'Monthly']
            if title == None:
                title = self.titles[plotType + 'Monthly']
            if color == None:
                try:
                    color = self.color[plotType]
                except:
                    color = self.color['standard']

            # reading data
            categories = self.months
            y = self.y[plotType + 'Monthly']

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.set_title(title, fontsize=12)
            ax.set_ylabel(label, fontsize=12)
            # plt.xlabel("Months")
            plt.xticks(rotation=45, fontsize=12)
            plt.yticks(fontsize=12)

            ax.bar(categories, y, width=0.9, edgecolor="white", linewidth=0.7, color=color)

            fig.subplots_adjust(bottom=0.2)

            # optional saving of the plot
            if savePlots:
                if timeStamp:
                    _now = datetime.now()
                    strDate = _now.strftime("%Y%m%d")
                    strTime = _now.strftime("%H%M%S")
                    stamp = '_D' + strDate + 'T' + strTime
                else:
                    stamp = ''
                plt.savefig(os.path.join(self.resultPath, 'plots') + plotType + '_' + plotResolution + stamp,
                            dpi=300, bbox_inches="tight")
            if show:
                plt.show()

        elif plotResolution == 'weekly':

            pass

"""

import matplotlib.pyplot as plt
fig, ax1 = plt.subplots(1, figsize=(7, 4))
par = {'mathtext.default': 'regular'}
plt.rcParams.update(par)
plt.bar(0, 434, 0.4, color=[(87/256, 171/256, 30/256)], alpha=1)#,  edgecolor = "black")
plt.bar(1, 287, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.8)#, edgecolor = "black")
plt.bar(2, 197, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.6)#, edgecolor = "black")
#plt.bar(3, 512, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.4)#, edgecolor = "black")

#plt.legend(bbox_to_anchor=(0, 1), loc='upper left', borderaxespad=0.3)
#plt.title('Electricity exchange at the GCP')
plt.ylim([0, 700])                                                                  ###
plt.ylabel('Emission [t/a]')                                                          ###
plt.xlabel('Scenarios')
plt.xticks(np.arange(3), ["1", "2", "3"])
plt.savefig("Emissions_hp_ratio", dpi=1200)                                         ###
plt.show()

import numpy as np
import matplotlib.pyplot as plt
fig, ax1 = plt.subplots(1, figsize=(7, 4))
par = {'mathtext.default': 'regular'}
plt.rcParams.update(par)
plt.bar(0, 643, 0.4, color=[(87/256, 171/256, 30/256)], alpha=1)#,  edgecolor = "black")
plt.bar(1, 379, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.8)#, edgecolor = "black")
plt.bar(2, 287, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.6)#, edgecolor = "black")
#plt.bar(3, 457, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.4)#, edgecolor = "black")

#plt.legend(bbox_to_anchor=(0, 1), loc='upper left', borderaxespad=0.3)
#plt.title('Electricity exchange at the GCP')
plt.ylim([0, 700])                                                                  ###
plt.ylabel('Spitzenlast [kW]')                                                          ###
plt.xlabel('Scenarios')
plt.xticks(np.arange(3), ["1", "2", "3"])
plt.savefig("Peakload_hp_ratio", dpi=1200)                                         ###
plt.show()

import numpy as np
import matplotlib.pyplot as plt
fig, ax1 = plt.subplots(1, figsize=(7, 4))
par = {'mathtext.default': 'regular'}
plt.rcParams.update(par)
plt.bar(0, 18.3, 0.4, color=[(87/256, 171/256, 30/256)], alpha=1)#,  edgecolor = "black")
plt.bar(1, 27.5, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.8)#, edgecolor = "black")
plt.bar(2, 39.7, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.6)#, edgecolor = "black")
plt.bar(3, 27.6, 0.4, color=[(87/256, 171/256, 30/256)], alpha=0.4)#, edgecolor = "black")

#plt.legend(bbox_to_anchor=(0, 1), loc='upper left', borderaxespad=0.3)
#plt.title('Electricity exchange at the GCP')
plt.ylim([0, 100])                                                                  ###
plt.ylabel('Autarkie [%]')                                                          ###
plt.xlabel('Szenario')
plt.xticks(np.arange(4), ["1", "2", "3", "4"])
plt.savefig("Autarky_hp_ratio", dpi=1200)                                         ###
plt.show()

"""