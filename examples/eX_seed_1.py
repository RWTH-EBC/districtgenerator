# -*- coding: utf-8 -*-

"""
Do you know the seed method? This example will show you, what it is good for and how to use it.
"""

from classes import *
import matplotlib.pyplot as plt
import random as rd
import os


def example_seed_1():

    # Do you know the method "seed" from the module random?
    # The method "seed" can customize the start number of the random number generator.
    # It is used, to get the same random number multiple times.
    # For our district generator, we can use this funktion, to generate the same profiles multiple times.

    # This example shows you, what the seed method does and how you can use it.
    # We look at the electricity profiles.
    # For reference, we first generate a district twice without using the seed method. Then we compare the electricity
    # demands of our user. For input we use the "example.csv".

    # test without seed -> see the differences between two plots
    for i in range(2):

        # Generate district data
        data = Datahandler()
        data.generateDistrictComplete(
            scenario_name='example',
            calcUserProfiles=True,
            saveUserProfiles=True,)

        srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fig = plt.figure()
        fig.add_subplot(211)
        plt.plot(data.district[0]["user"].elec[0:1000],'g')
        fig.add_subplot(212)
        plt.plot(data.district[1]["user"].elec[0:1000],'g')
        plt.savefig(srcPath+ "/results/plots/elec_test" + str(i))
        plt.show()

    # Now we use the seed method. The method needs an integer. In this example we use the 1.
    # You can choose any seed number. Every time you use this seed number, you will get the same profiles.
    # If you used all the same input parameters of course.

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
        fig = plt.figure()
        fig.add_subplot(211)
        plt.plot(data.district[0]["user"].elec[0:1000],'g')
        fig.add_subplot(212)
        plt.plot(data.district[1]["user"].elec[0:1000],'g')
        plt.savefig(srcPath+"/results/plots/elec_seed_test" + str(i))
        plt.show()


    print("Let's have a look on the plots. What do you see?")

    # Now we can compare the resulting plots. If they do not open automatically, you find them in '/results'.
    # While the two first ones should show different results (without the seed), the third and fourth,
    # for which we used the seed method, show exactly the same profiles.
    # You can try different seed numbers. Try 12, or even 435987639.

    return


if __name__ == '__main__':
    example_seed_1()