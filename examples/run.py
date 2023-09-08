# -*- coding: utf-8 -*-

import os, sys, json
import numpy as np

from classes import *


# Generate district data
data = Datahandler()
data.generateDistrictComplete(calcUserProfiles=True, saveUserProfiles=True, saveGenProfiles=True)

if True:
    # EHDO
    data.optimizationWithEHDO()

#data.plot(timeStamp=True, show=True)

if True:
    # KPIs
    data.designDevicesComplete(saveGenerationProfiles=True)
    data.clusterProfiles()
    data.optimizationClusters()
    data.calulateKPIs()

test = 1
