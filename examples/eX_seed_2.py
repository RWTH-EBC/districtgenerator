# -*- coding: utf-8 -*-

"""
In this example we compare all of our profiles to see, which ones depend on statistics and therefore
can be influenced by the seed number.
"""

from classes import *
import matplotlib.pyplot as plt
import random as rd
import os


def example_seed_2():

    # Do you know the method "seed" from the module random?
    # The method "seed" can customize the start number of the random number generator.
    # It is used, to get the same random number multiple times.
    # For our district generator, we can use this funktion, to generate the same profiles multiple times.


    # For reference, we first generate a district with a seed(2). Then we generate a district twice with a seed (1)
    # After that we compare the demands of our users. For input we use the "example.csv".

    # set the time horizon, that should bee seen in the plots
    th = 288 # for a time resolution of 900 seconds, 288 equals three days

    # test with seed (2)
    rd.seed(2)
    # Generate district data
    data = Datahandler()
    data.generateDistrictComplete(
        scenario_name='example',
        calcUserProfiles=True,
        saveUserProfiles=True,)

    srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fig = plt.figure(figsize=(10,16))
    fig.add_subplot(421)
    plt.plot(data.district[0]["user"].elec[0:th],'g')
    fig.add_subplot(422)
    plt.plot(data.district[1]["user"].elec[0:th],'g')
    fig.add_subplot(423)
    plt.plot(data.district[0]["user"].heat[0:th],'r')
    fig.add_subplot(424)
    plt.plot(data.district[1]["user"].heat[0:th],'r')
    fig.add_subplot(425)
    plt.plot(data.district[0]["user"].dhw[0:th],'r')
    fig.add_subplot(426)
    plt.plot(data.district[1]["user"].dhw[0:th],'r')
    fig.add_subplot(427)
    plt.plot(data.district[0]["user"].gains[0:th],'r')
    fig.add_subplot(428)
    plt.plot(data.district[1]["user"].gains[0:th],'r')
    plt.savefig(srcPath+ "/results/plots/reference_seed1", bbox_inches="tight")
    plt.show()

    # Now we use the seed method. In this example we use the 1.

    # test with seed -> see the differences between two plots
    for i in range(2):
        rd.seed(1)

        # Generate district data
        data = Datahandler()
        data.generateDistrictComplete(
            scenario_name='example',
            calcUserProfiles=True,
            saveUserProfiles=True,)

        srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fig = plt.figure(figsize=(10,16))
        fig.add_subplot(421)
        plt.plot(data.district[0]["user"].elec[0:th], 'g')
        fig.add_subplot(422)
        plt.plot(data.district[1]["user"].elec[0:th], 'g')
        fig.add_subplot(423)
        plt.plot(data.district[0]["user"].heat[0:th], 'r')
        fig.add_subplot(424)
        plt.plot(data.district[1]["user"].heat[0:th], 'r')
        fig.add_subplot(425)
        plt.plot(data.district[0]["user"].dhw[0:th], 'r')
        fig.add_subplot(426)
        plt.plot(data.district[1]["user"].dhw[0:th], 'r')
        fig.add_subplot(427)
        plt.plot(data.district[0]["user"].gains[0:th], 'r')
        fig.add_subplot(428)
        plt.plot(data.district[1]["user"].gains[0:th], 'r')
        plt.savefig(srcPath + "/results/plots/seed2_"+ str(i), bbox_inches="tight")
        plt.show()


    print("Let's have a look on the plots. What do you see?")


    # Now we can compare the resulting plots. If they do not open automatically, you find them in '/results'.
    # You see user 0 on the left and user 1 on the right.
    # From top to bottom you see profiles for electricity demand, heating demand, heat demand for domestic hot water and
    # heat gains.
    # While the first one with a different seed should show different results to the other two with the same seed,
    # these look exactly the same.

    return


if __name__ == '__main__':
    example_seed_2()