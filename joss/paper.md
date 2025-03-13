---
title: 'Districtgenerator: Generating building-specific load profiles for residential districts.'
tags:
  - Python
  - District
  - Building
  - Load profile generation
authors:
  - name: Sarah Henn
    orcid: 0000-0002-3423-7511
    affiliation: 1
  - name: Joel David Schölzel
    orcid: 0009-0000-5053-3161
    affiliation: 1
  - name: Tobias Beckhölter
    affiliation: 1
  - name: Carla Wüller
    affiliation: 1 
  - name: Dirk Müller
    orcid: 0000-0002-6106-6607
    affiliation: 1
affiliations:
 - name: Institute for Energy Efficient Buildings and Indoor Climate, RWTH Aachen University
   index: 1
date: 13 July 2024
bibliography: paper.bib
---

# Summary

The `Districtgenerator` enables an automated generation of time-resolved load profiles for residential districts. 
The profiles generated for each building within the district are the demands for electricity, space heating demand, domestic hot water, and the occupancy profiles. 
Additionally, a heating load calculation is carried out for each building.
The `Districtgenerator` is conceptualized using a minimum amount of input data. 
Thus, the tool is valuable for researchers and planners to obtain information  needed, for example, for the energy system or energy management system design in an early planning phase of a district.

# Statement of need

An essential part of facing global warming is to reduce the carbon footprint of the building sector, especially with a growing world population and a trend of urbanization in mind [@IEA_2021].
The `Districtgenerator` offers knowledge, shows synergy potentials and supports scalability regarding building and district solutions.  

* **Knowledge** of the energy demands is fundamental for the proper design and operation of any energy system.
With the integration of distributed energy resources (DER), district energy systems and building energy systems get more complex.
The energy supply of highly variable generators and user-dependent consumption need to be aligned. 
Thus, detailed time-resolved profiles of energy demand and generation are required for a successful and future-oriented energy system design and operation. 

* **Synergy** potentials between buildings of different usage structures can be exploited through joint concepts.
While joint heating concepts, such as local heating networks, have been the focus of research for a long time, joint electricity concepts have only recently emerged.
For example, the European Union proposed and introduced the concept of energy communities [@REDII_2018; @IEMD_2019].
According to the Renewable Energy Directive [@REDII_2018], a district can also form an energy community where energy is shared or traded Peer-to-Peer.
By this, district concepts can lead to financial benefits for consumers and prosumers. Moreover, its expected that self-consumption increases, 
peaks are evened out and the superordinate grid might be decongested. [@bose_reinforcement_2021]

* **Scalability** is a key issue for a resource-efficient transformation of the energy system, especially as numerous existing districts will have to be retrofitted and newly equipped in the next few years [@IEA_2021].
The `Districtgenerator` enables its users to easily gain information about districts in order to identify promising concepts and conduct comparative evaluations.
By using representative building types, data for representative districts is created. 
Thus, the data applies to a wide range of residential districts and can be included in guidelines or representative examples.

Also existing tools facilitate during the strategic and preliminary planning phases the identification of measures that 
support the detailed planning and subsequent implementation of sustainable and sector-coupling energy systems in neighborhoods.
However, the models and calculation methods of the time series are often not transparent. For stakeholders such as 
investors, urban planner, property owners or municipalities with limited resources, the complexity of these tools can be a barrier. Their user-friendliness 
is low, leading to potentially time-intensive applications. Furthermore, utilizing them may require specialized 
knowledge in energy planning, modeling, and data analysis, thus restricting access for less experienced users. [@schoelzel_districtgenerator_2024]

# Functional principle 

The minimum input data required is the number of buildings  and basic information about each building, namely the building type, year of construction, retrofit level, and net floor area.
The district size is freely choosable and the number of buildings to compute is not limited by the program. 
The default file format for the building information is .csv because of its compatibility and ease of use.
Optionally, the site of the district, the time resolution of the profiles and the test reference year (TRY) for weather data 
[@dwd_2023, @bbsr_2020}] can be modified. 
There are 16 choosable sites, which refer to the representative locations of the German climate zones. 
For every site, the user is able to select between warm, cold and normal TRYs. 
Moreover, TRYs are available for 2015 and 2045, reflecting either current or future weather conditions.

\setkeys{Gin}{width=.9\linewidth}
![Usage of external tools and data sources to generate occupancy and demand profiles with the Districtgenerator.](Schema_QG.pdf)

The district generator integrates multiple open-source tools and databases. 
Figure 1 visualizes the dependencies of external tools and data with internal functions.
The geometry and material properties of the buildings are determined based on the \href{https://github.com/RWTH-EBC/TEASER}{TEASER} python package [@remmen_teaser_2018] with data from the \href{https://webtool.building-typology.eu}{TABULA WebTool} [@loga_deutsche_2015]. 
As the \href{https://webtool.building-typology.eu}{TABULA WebTool} defines archetypal building properties for type, age class and retrofit level, the districts generated by the `Districtgenerator` are composed of representative buildings, making them ideal for representative analyses or scalability studies.
The @din_en_12831 contributes standard design temperatures for the selectable sites.
Based on this standard, a heating load calculation is performed. 
For the determination of the standard load for domestic hot water demand, the method of the unit dwelling [@din_4708] is used.
A number of residents is randomly, but within defined limits, attributed to each dwelling and serves as input data for the \href{https://github.com/RWTH-EBC/richardsonpy}{richardsonpy} tool [@richardson_domestic_2010] to calculate the time-resolved occupancy profiles.
Furthermore, the Stromspiegel [@co2online_stromspiegel_2022] provides statistical data on annual electricity consumption in German households.
Annual consumption is stochastically assigned to each building, upon which the time-resolved electricity profile is created using the stochastic profile generator \href{https://github.com/RWTH-EBC/richardsonpy}{richardsonpy} again.
The electricity and occupancy profiles serve as input for a time-resolved internal gain calculation. 
Additionally, the occupancy profiles are needed for domestic hot water profile generation, for which functions from the \href{https://github.com/RWTH-EBC/pyCity}{pyCity} tool [@schiefelbein_automated_2019] are utilized. 
Finally, the static building data, as well as the time-resolved weather and internal gain data, are included in the space heating profile generation.
These are computed by means of a 5R1C-substitution model according to @din_en_iso_13790, using the simplified hourly method.

All profiles generated can be saved in a customizable format, with .csv files output by default.
The `Districtgenerator` provides various plot functions. 
The plots visualize the profiles and can show monthly energy consumption or stepwise data for user-defined periods of the year.
For easy handling, a \href{https://districtgenerator.eonerc.rwth-aachen.de/de/}{web-based} graphical user interface is created.

# Further development

There are further expansion stages of the `Districtgenerator` planned.
Future versions will include technologies that can be assigned to the buildings or central devices providing energy for the whole district. 
Based on that, firstly, the user will be given access to renewable energy generation data, like photovoltaic generation and solar thermal heat generation, and to further demands, like electric vehicle charging demand.
Secondly, a module for operation optimization will be added, with which the energy system under observation can be simulated and evaluated.
Moreover, the open-source webtool \href{https://github.com/RWTH-EBC/EHDO}{EHDO} will be integrated to provide
optimization-based designing of energy hubs consisting of complex multi-energy systems [@wirtz_ehdo_2020].

# Acknowledgements

We gratefully acknowledge the financial support by Federal Ministry for Economic Affairs and Climate Action (BMWK), promotional reference 03EWB003B.


# References

