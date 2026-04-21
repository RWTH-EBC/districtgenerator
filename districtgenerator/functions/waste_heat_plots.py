import numpy as np
import matplotlib.pyplot as plt
import os
import json
from districtgenerator.classes import *
"""Python file with functions to plot the results of waste heat integration"""

# plot TAC depending on distance and price
def plot_TAC():
    # load json
    data = Datahandler(scenario_name="district_F_buildings_20", env_path=".env.CONFIG.EXAMPLE")
    path = data.resultPath
    json_path = os.path.join(path, "wasteheat", "district_F_buildings_20.json")
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            json_data = json.load(f)

        # heating_demand_density = json_data.get("heating_demand_density", None)
        heating_demand_density = None


        #fig, ax = plt.subplots(figsize=(10, 6))
        fig, ax = plt.subplots(figsize=(8, 10))

        # central/decentral
        TAC_central = json_data.get("zentral_ohne_abwaerme", {}).get("TAC", None)
        TAC_decentral = json_data.get("dezentral", {}).get("TAC", None)

        if TAC_decentral is not None:
            ax.axhline(TAC_decentral, linestyle="-", color="green", label="dezentrale Versorgung")
        if TAC_central is not None:
            ax.axhline(TAC_central, linestyle="-", color="orange", label="zentrale Versorgung")

        # colours
        price_colors = {"0": "red", "0.02": "blue"}

        # Plots
        for wh_price in ["0", "0.02"]:
            key = f"Baustoff_100_{wh_price}"
            if key in json_data:
                distances = []
                TAC_values = []
                for d, values in json_data[key]["Entfernung"].items():
                    distances.append(float(d))
                    TAC_values.append(values["TAC"])
                if distances:
                    distances, TAC_values = zip(*sorted(zip(distances, TAC_values)))
                    ax.scatter(distances, TAC_values, color=price_colors[wh_price],
                               s=40, label=f"Abwärmepreis: {wh_price} €/kWh")

        # labels and title
        ax.set_xlabel("Entfernung zum Quartier [m]", fontsize=20)
        ax.set_ylabel("TAC [€/Jahr]", fontsize=20)
        ax.set_ylim(0, max(TAC_values) * 1.3)

        #ax.set_ylim(0, None)  # y-axis starts from 0

        # 2. X-Ticks: 100, 500, 1000
        ax.set_xticks([100, 500, 1000])
        ax.set_xticklabels(['100', '500', '1000'])
        ax.tick_params(axis='both', labelsize=11)

        #ax.set_title(f"TAC in Abhängigkeit der Entfernung und Abwärmepreise",
                    # fontsize=12, pad=20)

        ax.grid(True, alpha=0.3)
        ax.margins(x=0.1, y=0.2)

        ax.legend(loc='upper right', bbox_to_anchor=(0.98, 0.25),
                  fontsize=17, ncol=1, frameon=True, framealpha=0.95)


        # add heating demand density
        if heating_demand_density is not None:
            ax.text(0.02, 0.95, f"Wärmebedarfsdichte: {heating_demand_density:.2f} kWh/m²",
                    transform=ax.transAxes, fontsize=10, verticalalignment='top',
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

        plt.tight_layout(pad=2.0)

        plt.savefig("TAC_plot.svg", bbox_inches='tight', dpi=300, facecolor='white')
        plt.show()



# plots fixed and operational costs of central and decentral heat supply in a bar chart
def plot_fixed_operational():
    # load json
    data = Datahandler(scenario_name="district_F_buildings_20", env_path=".env.CONFIG.EXAMPLE")
    path = data.resultPath
    json_path = os.path.join(path, "wasteheat", "district_F_buildings_20.json")

    with open(json_path, "r") as f:
        json_data = json.load(f)

    # extract fixed and operational costs
    categories = ["Zentral ohne Abwärme", "Dezentral"]
    fixed_values = [
        json_data["zentral_ohne_abwaerme"]["fixed"],
        json_data["dezentral"]["fixed"]
    ]
    operational_values = [
        json_data["zentral_ohne_abwaerme"]["operational"],
        json_data["dezentral"]["operational"]
    ]

    heating_density = json_data.get("heating_demand_density", None)

    # create bar chart
    fig, ax = plt.subplots(figsize=(8, 6))

    # bar positions
    x = range(len(categories))

    # stacked bars
    ax.bar(x, fixed_values, width=0.5, color="red", label="Fixed")
    ax.bar(x, operational_values, width=0.5, bottom=fixed_values, color="royalblue", label="Operational")

    # labels and title
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11)
    ax.set_ylabel("Kosten [€/a]", fontsize=11)
    ax.tick_params(axis='y', labelsize=11)
    ax.set_ylim(0, max(fixed_values + operational_values) * 2.1)
    # ax.set_title("TAC-Aufschlüsselung nach Versorgungskonzepten", fontsize=13, pad=15)
    # ax.grid(axis="y", alpha=0.3)

    # legend
    legend_labels = ["jährliche Fixkosten", "variable Kosten"]
    if heating_density is not None:
        legend_labels.append(f"Wärmebedarfsdichte: {heating_density:.2f} kWh/m²")
    ax.legend(legend_labels, loc="upper right", fontsize=14,
              frameon=False, handlelength=1.0)

    # layout
    plt.tight_layout()
    plt.savefig('tac_kosten.pdf', bbox_inches='tight', dpi=300)
    plt.show()


# schematisches Lastprofil für Poster und Abschlussvortrag
def plot_poster():

    t = np.linspace(0, 7*24, 7*24)

    # generate profile
    load = np.ones_like(t)       # constant
#    load = np.zeros_like(t)

#    for day in range(7):          # example of 2-shift profile
#        offset = day * 24

    # monday-friday
#        if day < 5:
#            mask = (t >= (6 + offset)) & (t < (22 + offset))
#            load[mask] = 0.5  # full load


    plt.plot(t, load, linewidth = 10)
    plt.xlabel("$t$ in (h)", fontsize=35)

    plt.ylabel(r'$T$ in (°C)', fontsize = 35)
    #plt.ylabel(r'$\dot{Q}$ in (kW)', fontsize=35)
    plt.xticks([])
    plt.yticks([])

    ax = plt.gca()
    ax.xaxis.set_label_coords(0.5, -0.03)
    #plt.gcf().patch.set_facecolor('#d9d9d9')
    #plt.gca().set_facecolor('#d9d9d9')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_linewidth(10)
    ax.spines['left'].set_linewidth(10)

    plt.grid(False)

    plt.savefig("schematisch.svg", bbox_inches='tight', dpi=300, facecolor='white')
    plt.show()



plot_poster()