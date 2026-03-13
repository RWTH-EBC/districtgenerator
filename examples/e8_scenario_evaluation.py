# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import warnings



def example8_scenario_evaluation():
    warnings.filterwarnings("ignore", category=FutureWarning)

    # Initialize District
    data = Datahandler(scenario_name = "district_A_buildings_20", env_path=".env.CONFIG.EXAMPLE")

    # We directly generate a complete district.
    # This includes the use of the EHDO tool to obtain an optimized energy central for neighborhoods.
    # EHDO is a tool for planning and designing complex energy systems.
    # Its key feature is the coupling of different sectors (e.g., electricity, heating, cooling).
    # In the early planning phases of energy supply concepts for neighborhoods,
    # the tool provides an initial assessment of the optimal system configuration, sizing,
    # and economic efficiency.
    # As input, EHDO requires data on energy demands and location (weather),
    # which are provided directly from the output of the district generator.
    # Additional information about the technologies to be considered for the dimensioning
    # of the energy central and the economic parameters are read from additional
    # .csv and .json data sources.

    topology_option = data.heat_grid_data["topology_option"]
    data.generateEnvironment()
    # "A": "Papierindustrie", "B": "Baustoff", "C": "Rechenzentrum", "D": "Kläranlage", "E": "cold store"
    #data.generate_waste_heat_source(waste_heat_source="B", distance=800)
    data.generate_waste_heat_source(waste_heat_source="Papierindustrie", distance=100)








    import json
    import matplotlib.pyplot as plt
    import os
    path = data.resultPath
    scenario_name = data.scenario_name
    json_path = os.path.join(path, "wasteheat", f"{scenario_name}.json")
    json_path = "hallo"
#    wh_type = data.waste_heat_data['type']
#    wh_size = data.waste_heat_data['size']


    # JSON laden
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            json_data = json.load(f)

        # heating_demand_density = json_data.get("heating_demand_density", None)
        heating_demand_density = None  # Entfernen für Test!

        # Figure EINMAL erstellen (OBEN!)
        fig, ax = plt.subplots(figsize=(10, 6))  # ← Breit von Anfang an!

        # zentral / dezentral (auf ax plotten)
        TAC_central = json_data.get("zentral_ohne_abwaerme", {}).get("TAC", None)
        TAC_decentral = json_data.get("dezentral", {}).get("TAC", None)

        if TAC_decentral is not None:
            ax.axhline(TAC_decentral, linestyle="-", color="green", label="dezentrale Versorgung")
        if TAC_central is not None:
            ax.axhline(TAC_central, linestyle="-", color="orange", label="zentrale Versorgung")

        # Farben
        price_colors = {"0": "red", "0.02": "blue"}

        # Plots
        for wh_price in ["0", "0.02"]:
            key = f"{wh_type}_{wh_size}_{wh_price}"
            if key in json_data:
                distances = []
                TAC_values = []
                for d, values in json_data[key]["Entfernung"].items():
                    distances.append(float(d))
                    TAC_values.append(values["TAC"])
                if distances:
                    distances, TAC_values = zip(*sorted(zip(distances, TAC_values)))
                    ax.scatter(distances, TAC_values, color=price_colors[wh_price],
                               s=80, label=f"{wh_type} ({wh_size} kW) – {wh_price} €/kWh")

        # Labels & Title AUF AX
        ax.set_xlabel("Entfernung zum Quartier [m]", fontsize=11)
        ax.set_ylabel("TAC [€/Jahr]", fontsize=11)
        ax.set_title(f"TAC für {wh_type} in Abhängigkeit der Entfernung und Abwärmepreise",
                     fontsize=12, pad=20)

        ax.grid(True, alpha=0.3)

        # LEGENDE KLEIN & außen
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=9,
                  frameon=True, framealpha=0.95, handlelength=1.5)

        # Text-Box
        if heating_demand_density is not None:
            ax.text(0.02, 0.95, f"Wärmebedarfsdichte: {heating_demand_density:.2f} kWh/m²",
                    transform=ax.transAxes, fontsize=10, verticalalignment='top',
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

        # ← FIX: ALLES SICHTBAR
        plt.tight_layout(pad=2.0)

        plt.savefig("TAC_plot.pdf", bbox_inches='tight', dpi=300, facecolor='white')
        plt.show()

    data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=True, topology_option = topology_option)

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calculateKPIs()

    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    #data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")
    return data



if __name__ == '__main__':
    data = example8_scenario_evaluation()





