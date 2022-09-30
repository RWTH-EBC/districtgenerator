# -*- coding: utf-8 -*-


"""
The third example will show you how easy you can create some plots.
"""


# Import classes of the districtgenerator to be able to use the district generator.
from classes import *


def example_fist_plots():

    # In this example we use the "timeHorizon" of 604800 seconds which equals one week as we set them as preparation for
    # the second example. As district, we use the "example.csv" file by setting "scenario_name" to "example".
    # To be able to compare different settings, we use the demand profiles, we generated in our first example.
    # Therefor we set clacUserProfiles=False and saveUserProfiles=False.

    # Generate district with energy profiles
    data = Datahandler()
    data.generateDistrictComplete(scenario_name='example', calcUserProfiles=False, saveUserProfiles=False)

    # Now we can easily create some plots for the hole district.
    # default values are: (mode='default', initialTime=0, timeHorizon=31536000,
    # savePlots=True, timeStamp=False, show=False)
    # We set the parameter "timeStamp" to "True". So the file
    # names of the saved pictures get a unique name and do not overwrite existing pictures in the same folder.
    # The mode specifies, which value should be plotted.
    # We can choose between 'elec', 'dhw', 'gains', 'occ', 'heating', 'heatDemand' or 'default'.
    # With 'default', all plots are generated.

    # For our first plots we use the "default" mode.
    # As initialTime=0 and timeHorizon=31536000 are the default values, the plot will have a monthly resolution.

    # Generate all Plots
    data.plot(timeStamp=True, show=True)

    # We change this up, by setting the timeHorizon=604800 seconds (one week) now.
    # As mode we choose "elec" and "heating" to get the electricity and the heating demand profile of the district.

    # Generate weekly Plots (first week of the year = winter)
    data.plot(mode="elec", timeStamp=True, show=True, timeHorizon=604800)
    data.plot(mode="heating", timeStamp=True, show=True, timeHorizon=604800)

    # You can also change the value of "initialTime" to 86400 seconds (one day) or 604800 seconds (one week).
    # When you run the example again, you get result starting with the second day of the year
    # or for the second week of the year.

    # We will change "initialTime" to 15724800. (26 weeks or half a year)

    # Generate weekly Plots (mid week of the year = summer)
    data.plot(mode="elec", timeStamp=True, show=True, initialTime= 15724800, timeHorizon=604800)
    data.plot(mode="heating", timeStamp=True, show=True, initialTime= 15724800, timeHorizon=604800)

    # We can see, that the electricity demand varies for a day, but not so much over the year, the heating demand
    # shows main differences in summer or winter.

    # Now open the "time_data.json" file in the "data/" directory of the districtgenerator (e.g. with a text editor).
    # Change the "dataResolution" from 900 (the default value) to 3600 seconds (one hour) and save the file. Then run
    # this example again and compare the new and old plots. The resolution of our single plots should be different.
    # Note that you have to change calcUserProfiles to True, because you use a different resolution.

    # You can find all the plots in the "result/plots/" directory of the districtgenerator. You should see that the
    # filenames end with "D" for the current date followed by six digits for year, month and day and "T" for current the
    # time with again six digits for hour, minutes and seconds.

    # Go on! Start exploring. You are now able to change resolutions, time horizon and time slot. And having example2 in
    # mind, you can create and compare different districts with each other.

    return data


if __name__ == '__main__':
    data = example_fist_plots()

    print("\nFinished to create your first plots in example three? Wonderful!")