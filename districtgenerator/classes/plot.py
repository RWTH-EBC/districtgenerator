import matplotlib.pyplot as plt
import numpy as np
import os

def el_buildings(plotData, data):

    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_map = {
        "Grid": "grey",
        "PV": "yellow",
        "CHP": "green",
        "FC": "purple",
        "BAT discharge": "blue",
        "EV discharge": "cyan",
        "Demand": "red",
        "EV charge": "orange",
        "HP": "magenta",
        "EH": "brown",
        "BAT charge": "lightblue",
        "Feed-in": "black"
    }

    for n in range(num_buildings):

        fig, axes = plt.subplots(num_clusters, 1, figsize=(12, 4 * num_clusters), sharex=True)

        if num_clusters == 1:
            axes = [axes]

        # these two lists will collect _all_ the non‐zero
        # handles & labels from _all_ clusters:
        all_handles = []
        all_labels  = []

        for c in range(num_clusters):
            ax = axes[c]

            # positive (sources/generation)
            buy = np.array(plotData["resultsOptimization"][c][n]["res_load"])

            PV_power = safe_array(plotData, c, n, "PV", "P_el", time_steps)
            CHP = safe_array(plotData, c, n, "CHP", "P_el", time_steps)
            FC = safe_array(plotData, c, n, "FC", "P_el", time_steps)
            dch_BAT = safe_array(plotData, c, n, "BAT", "dch", time_steps)
            dch_EV = safe_array(plotData, c, n, "EV", "dch", time_steps)

            # negative (demands/sinks)
            feed = np.array(plotData["resultsOptimization"][c][n]["res_inj"])
            demand = np.array(plotData["resultsOptimization"][c][n]["Demand"]["P_el"])

            ch_EV = safe_array(plotData, c, n, "EV", "ch", time_steps)
            HP = safe_array(plotData, c, n, "HP", "P_el", time_steps)
            EH = safe_array(plotData, c, n, "EH", "P_el", time_steps)
            ch_BAT = safe_array(plotData, c, n, "BAT", "ch", time_steps)

            # SOURCES
            sources = [buy, PV_power, CHP, FC, dch_BAT, dch_EV]
            source_labels = ["Grid", "PV", "CHP", "FC", "BAT discharge", "EV discharge"]
            source_colors = [color_map[label] for label in source_labels]

            # SINKS
            sinks = [demand, ch_EV, HP, EH, ch_BAT, feed]
            sink_labels = ["Demand", "EV charge", "HP", "EH", "BAT charge", "Feed-in"]
            sink_colors = [color_map[label] for label in sink_labels]

            # plot everything (even the all‐zero ones) for stacking consistency
            src_pc = ax.stackplot(time, sources, colors=source_colors, alpha=0.8)
            snk_pc = ax.stackplot(time, [-s for s in sinks], colors=sink_colors, alpha=0.8)

            # pick out just the non‐zero ones _in this cluster_
            src_handles = []
            src_labels = []
            for arr, pc, lbl in zip(sources, src_pc, source_labels):
                if np.any(arr > 0):
                    src_handles.append(pc)
                    src_labels.append(lbl)

            snk_handles = []
            snk_labels = []
            for arr, pc, lbl in zip(sinks, snk_pc, sink_labels):
                if np.any(arr > 0):
                    snk_handles.append(pc)
                    snk_labels.append(lbl)

            # now merge into the _global_ lists, deduping by label
            for h, l in zip(src_handles + snk_handles,
                            src_labels + snk_labels):
                if l not in all_labels:
                    all_handles.append(h)
                    all_labels.append(l)

            ax.set_ylabel('Electrical Power [W]')
            ax.set_title(f'Building {n} – Cluster {c} Electrical Power Balance')
            ax.grid(True)

        if all_handles:
            axes[0].legend(all_handles, all_labels,
                           loc='upper right', ncol=2)

        axes[-1].set_xlabel('Time steps [h]')
        plt.tight_layout()

        path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'buildings')
        os.makedirs(path, exist_ok=True)
        fig.savefig(os.path.join(path, f"el_building_{n}.png"), dpi=300)

def th_buildings(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_map = {
        "Heat Pump": "blue",
        "Boiler": "red",
        "Electric Heater": "orange",
        "Solar Thermal": "yellow",
        "CHP": "green",
        "Fuel Cell": "purple",
        "TES discharge": "black",
        "TES charge": "brown",
        "Heating Demand": "darkred",
        "DHW Demand": "darkorange",
        "Heat Grid": "pink"
    }

    for n in range(num_buildings):

        fig, axes = plt.subplots(num_clusters, 1, figsize=(12, 4 * num_clusters), sharex=True)

        if num_clusters == 1:
            axes = [axes]

        # these two lists will collect _all_ the non‐zero
        # handles & labels from _all_ clusters:
        all_handles = []
        all_labels  = []

        for c in range(num_clusters):
            ax = axes[c]

            # positive (sources/generation)
            HP = safe_array(plotData, c, n, "HP", "Q_th", time_steps)
            BOI = safe_array(plotData, c, n, "BOI", "Q_th", time_steps)
            EH = safe_array(plotData, c, n, "EH", "Q_th", time_steps)
            STC = safe_array(plotData, c, n, "STC", "Q_th", time_steps)
            CHP = safe_array(plotData, c, n, "CHP", "Q_th", time_steps)
            FC = safe_array(plotData, c, n, "FC", "Q_th", time_steps)
            dch_TES = safe_array(plotData, c, n, "TES", "dch", time_steps)
            heat_grid = safe_array(plotData, c, n, "heat_grid", "Q_th", time_steps)

            # negative (demands/sinks)
            ch_TES = safe_array(plotData, c, n, "TES", "ch", time_steps)

            dhw = np.array(plotData["resultsOptimization"][c][n]["DHW"]["Q_th"])
            heating = np.array(plotData["resultsOptimization"][c][n]["Heating"]["Q_th"])

            # Build sources
            sources = [HP, BOI, EH, STC, CHP, FC, dch_TES, heat_grid]
            source_labels = [
                "Heat Pump", "Boiler", "Electric Heater", "Solar Thermal",
                "CHP", "Fuel Cell", "TES discharge", "Heat Grid"
            ]
            source_colors = [color_map[label] for label in source_labels]

            # ---- Build sinks ----
            sinks = [ch_TES, heating, dhw]
            sink_labels = ["TES charge", "Heating Demand", "DHW Demand"]
            sink_colors = [color_map[label] for label in sink_labels]

            # plot everything (even the all‐zero ones) for stacking consistency
            src_pc = ax.stackplot(time, sources, colors=source_colors, alpha=0.8)
            snk_pc = ax.stackplot(time, [-s for s in sinks], colors=sink_colors, alpha=0.8)

            # pick out just the non‐zero ones _in this cluster_
            src_handles = []
            src_labels = []
            for arr, pc, lbl in zip(sources, src_pc, source_labels):
                if np.any(arr > 0):
                    src_handles.append(pc)
                    src_labels.append(lbl)

            snk_handles = []
            snk_labels = []
            for arr, pc, lbl in zip(sinks, snk_pc, sink_labels):
                if np.any(arr > 0):
                    snk_handles.append(pc)
                    snk_labels.append(lbl)

            # now merge into the _global_ lists, deduping by label
            for h, l in zip(src_handles + snk_handles,
                            src_labels + snk_labels):
                if l not in all_labels:
                    all_handles.append(h)
                    all_labels.append(l)

            ax.set_ylabel('Thermal Power [W]')
            ax.set_title(f'Building {n} – Cluster {c} Thermal Power Balance')
            ax.grid(True)

        if all_handles:
            axes[0].legend(all_handles, all_labels,
                           loc='upper right', ncol=2)

        axes[-1].set_xlabel('Time steps [h]')
        plt.tight_layout()

        path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'buildings')
        os.makedirs(path, exist_ok=True)
        fig.savefig(os.path.join(path, f"th_building_{n}.png"), dpi=300)

def el_all_buildings(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    # ----- Fixed color map -----
    color_map = {
        "Grid": "grey",
        "PV": "yellow",
        "CHP": "green",
        "FC": "purple",
        "BAT discharge": "blue",
        "EV discharge": "cyan",
        "Demand": "red",
        "EV charge": "orange",
        "HP": "magenta",
        "EH": "brown",
        "BAT charge": "lightblue",
        "Feed-in": "black"
    }

    fig, axes = plt.subplots(num_clusters, 1, figsize=(12, 4 * num_clusters), sharex=True)

    if num_clusters == 1:
        axes = [axes]

    # these two lists will collect _all_ the non‐zero
    # handles & labels from _all_ clusters:
    all_handles = []
    all_labels  = []

    for c in range(num_clusters):
        ax = axes[c]

        # Initialize totals for all sources and sinks
        total_buy = np.zeros(time_steps)
        total_PV = np.zeros(time_steps)
        total_CHP = np.zeros(time_steps)
        total_FC = np.zeros(time_steps)
        total_dch_BAT = np.zeros(time_steps)
        total_dch_EV = np.zeros(time_steps)

        total_demand = np.zeros(time_steps)
        total_ch_EV = np.zeros(time_steps)
        total_HP = np.zeros(time_steps)
        total_EH = np.zeros(time_steps)
        total_ch_BAT = np.zeros(time_steps)
        total_feed = np.zeros(time_steps)

        # --- Sum over all buildings ---
        for n in range(num_buildings):
            buy = np.array(plotData["resultsOptimization"][c][n]["res_load"])  # no safe_array: always present

            PV_power = safe_array(plotData, c, n, "PV", "P_el", time_steps)
            CHP = safe_array(plotData, c, n, "CHP", "P_el", time_steps)
            FC = safe_array(plotData, c, n, "FC", "P_el", time_steps)
            dch_BAT = safe_array(plotData, c, n, "BAT", "dch", time_steps)
            dch_EV = safe_array(plotData, c, n, "EV", "dch", time_steps)

            feed = np.array(plotData["resultsOptimization"][c][n]["res_inj"])  # always present
            demand = np.array(plotData["resultsOptimization"][c][n]["Demand"]["P_el"])  # always present

            ch_EV = safe_array(plotData, c, n, "EV", "ch", time_steps)
            HP = safe_array(plotData, c, n, "HP", "P_el", time_steps)
            EH = safe_array(plotData, c, n, "EH", "P_el", time_steps)
            ch_BAT = safe_array(plotData, c, n, "BAT", "ch", time_steps)


        # --- Sum for all buildings ---
            total_buy += buy
            total_PV += PV_power
            total_CHP += CHP
            total_FC += FC
            total_dch_BAT += dch_BAT
            total_dch_EV += dch_EV

            total_demand += demand
            total_ch_EV += ch_EV
            total_HP += HP
            total_EH += EH
            total_ch_BAT += ch_BAT
            total_feed += feed

        # ---- Build sources ----
        sources = [total_buy, total_PV, total_CHP, total_FC, total_dch_BAT, total_dch_EV]
        source_labels = ["Grid", "PV", "CHP", "FC", "BAT discharge", "EV discharge"]
        source_colors = [color_map[label] for label in source_labels]

        # ---- Build sinks ----
        sinks = [total_demand, total_ch_EV, total_HP, total_EH, total_ch_BAT, total_feed]
        sink_labels = ["Demand", "EV charge", "HP", "EH", "BAT charge", "Feed-in"]
        sink_colors = [color_map[label] for label in sink_labels]

        # plot everything (even the all‐zero ones) for stacking consistency
        src_pc = ax.stackplot(time, sources, colors=source_colors, alpha=0.8)
        snk_pc = ax.stackplot(time, [-s for s in sinks], colors=sink_colors, alpha=0.8)

        # pick out just the non‐zero ones _in this cluster_
        src_handles = []
        src_labels = []
        for arr, pc, lbl in zip(sources, src_pc, source_labels):
            if np.any(arr > 0):
                src_handles.append(pc)
                src_labels.append(lbl)

        snk_handles = []
        snk_labels = []
        for arr, pc, lbl in zip(sinks, snk_pc, sink_labels):
            if np.any(arr > 0):
                snk_handles.append(pc)
                snk_labels.append(lbl)

        # now merge into the _global_ lists, deduping by label
        for h, l in zip(src_handles + snk_handles,
                        src_labels + snk_labels):
            if l not in all_labels:
                all_handles.append(h)
                all_labels.append(l)

        ax.set_ylabel('Electrical Power [W]')
        ax.set_title(f'Cluster {c} - Total Electrical Power Balance (All Buildings)')
        ax.grid(True)

    if all_handles:
        axes[0].legend(all_handles, all_labels,
                       loc='upper right', ncol=2)

    axes[-1].set_xlabel('Time steps [h]')
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'buildings')
    os.makedirs(path, exist_ok=True)
    fig.savefig(os.path.join(path, f"el_all_buildings.png"), dpi=300)

def th_all_buildings(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_map = {
        "Heat Pump": "blue",
        "Boiler": "red",
        "Electric Heater": "orange",
        "Solar Thermal": "yellow",
        "CHP": "green",
        "Fuel Cell": "purple",
        "TES discharge": "black",
        "TES charge": "brown",
        "Heating Demand": "darkred",
        "DHW Demand": "darkorange",
        "Heat Grid": "pink"
    }

    fig, axes = plt.subplots(num_clusters, 1, figsize=(12, 4 * num_clusters), sharex=True)

    if num_clusters == 1:
        axes = [axes]

    # these two lists will collect _all_ the non‐zero
    # handles & labels from _all_ clusters:
    all_handles = []
    all_labels  = []

    for c in range(num_clusters):
        ax = axes[c]

        # ---- Initialize totals ----
        total_HP = np.zeros(time_steps)
        total_BOI = np.zeros(time_steps)
        total_EH = np.zeros(time_steps)
        total_STC = np.zeros(time_steps)
        total_CHP = np.zeros(time_steps)
        total_FC = np.zeros(time_steps)
        total_dch_TES = np.zeros(time_steps)
        total_heat_grid = np.zeros(time_steps)

        total_ch_TES = np.zeros(time_steps)
        total_heating = np.zeros(time_steps)
        total_dhw = np.zeros(time_steps)

        # ---- Sum over all buildings ----
        for n in range(num_buildings):

            total_HP += safe_array(plotData, c, n, "HP", "Q_th", time_steps)
            total_BOI += safe_array(plotData, c, n, "BOI", "Q_th", time_steps)
            total_EH += safe_array(plotData, c, n, "EH", "Q_th", time_steps)
            total_STC += safe_array(plotData, c, n, "STC", "Q_th", time_steps)
            total_CHP += safe_array(plotData, c, n, "CHP", "Q_th", time_steps)
            total_FC += safe_array(plotData, c, n, "FC", "Q_th", time_steps)
            total_dch_TES += safe_array(plotData, c, n, "TES", "dch", time_steps)
            total_heat_grid += safe_array(plotData, c, n, "heat_grid", "Q_th", time_steps)

            total_ch_TES += safe_array(plotData, c, n, "TES", "ch", time_steps)

            total_heating += np.array(plotData["resultsOptimization"][c][n]["Heating"]["Q_th"])  # always exists
            total_dhw += np.array(plotData["resultsOptimization"][c][n]["DHW"]["Q_th"])  # always exists

        # ---- Build sources ----
        sources = [total_HP, total_BOI, total_EH, total_STC,
                   total_CHP, total_FC, total_dch_TES, total_heat_grid]

        source_labels = ["Heat Pump", "Boiler", "Electric Heater", "Solar Thermal",
                         "CHP", "Fuel Cell", "TES discharge", "Heat Grid"]

        source_colors = [color_map[label] for label in source_labels]

        # ---- Build sinks ----
        sinks = [total_ch_TES, total_heating, total_dhw]
        sink_labels = ["TES charge", "Heating Demand", "DHW Demand"]
        sink_colors = [color_map[label] for label in sink_labels]

        # plot everything (even the all‐zero ones) for stacking consistency
        src_pc = ax.stackplot(time, sources, colors=source_colors, alpha=0.8)
        snk_pc = ax.stackplot(time, [-s for s in sinks], colors=sink_colors, alpha=0.8)

        # pick out just the non‐zero ones _in this cluster_
        src_handles = []
        src_labels = []
        for arr, pc, lbl in zip(sources, src_pc, source_labels):
            if np.any(arr > 0):
                src_handles.append(pc)
                src_labels.append(lbl)

        snk_handles = []
        snk_labels = []
        for arr, pc, lbl in zip(sinks, snk_pc, sink_labels):
            if np.any(arr > 0):
                snk_handles.append(pc)
                snk_labels.append(lbl)

        # now merge into the _global_ lists, deduping by label
        for h, l in zip(src_handles + snk_handles,
                        src_labels + snk_labels):
            if l not in all_labels:
                all_handles.append(h)
                all_labels.append(l)

        ax.set_ylabel('Thermal Power [W]')
        ax.set_title(f'Cluster {c} - Total Thermal Power Balance (All Buildings)')
        ax.grid(True)

    if all_handles:
        axes[0].legend(all_handles, all_labels,
                       loc='upper right', ncol=2)

    axes[-1].set_xlabel('Time steps [h]')
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'buildings')
    os.makedirs(path, exist_ok=True)
    fig.savefig(os.path.join(path, f"th_all_buildings.png"), dpi=300)

def el_energy_hub(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_map = {
        "PV": "yellow",
        "WT": "green",
        "WAT": "cyan",
        "CHP": "orange",
        "BCHP": "brown",
        "WCHP": "olive",
        "FC": "purple",
        "from_grid": "grey",
        "BAT discharge": "blue",
        "HP": "magenta",
        "EB": "orange",
        "CC": "red",
        "ELYZ": "pink",
        "BAT charge": "lightblue",
        "to_grid": "black"
    }

    fig, axes = plt.subplots(num_clusters, 1, figsize=(12, 4 * num_clusters), sharex=True)

    if num_clusters == 1:
        axes = [axes]

    # these two lists will collect _all_ the non‐zero
    # handles & labels from _all_ clusters:
    all_handles = []
    all_labels  = []

    for c in range(num_clusters):
        ax = axes[c]

        # ---- SOURCES ----

        PV = safe_array(plotData, c, "eh_power", "PV", None, time_steps)
        WT = safe_array(plotData, c, "eh_power", "WT", None, time_steps)
        WAT = safe_array(plotData, c, "eh_power", "WAT", None, time_steps)
        CHP = safe_array(plotData, c, "eh_power", "CHP", None, time_steps)
        BCHP = safe_array(plotData, c, "eh_power", "BCHP", None, time_steps)
        WCHP = safe_array(plotData, c, "eh_power", "WCHP", None, time_steps)
        FC = safe_array(plotData, c, "eh_power", "FC", None, time_steps)
        from_grid = safe_array(plotData, c, "eh_power", "from_grid", None, time_steps)
        dch_BAT = safe_array(plotData, c, "eh_dch", "BAT", None, time_steps)

        sources = [
            PV, WT, WAT, CHP, BCHP, WCHP,
            FC, from_grid, dch_BAT
        ]
        source_labels = ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP",
                         "FC", "from_grid", "BAT discharge"]
        source_colors = [color_map[label] for label in source_labels]

        # ---- SINKS ----
        HP = safe_array(plotData, c, "eh_power", "HP", None, time_steps)
        EB = safe_array(plotData, c, "eh_power", "EB",None, time_steps)
        CC = safe_array(plotData, c, "eh_power", "CC", None, time_steps)
        ELYZ = safe_array(plotData, c, "eh_power", "ELYZ", None, time_steps)
        ch_BAT = safe_array(plotData, c, "eh_ch", "BAT", None, time_steps)
        to_grid = safe_array(plotData, c, "eh_power", "to_grid", None, time_steps)

        sinks = [HP, EB, CC, ELYZ, ch_BAT, to_grid]
        sink_labels = ["HP", "EB", "CC", "ELYZ", "BAT charge", "to_grid"]
        sink_colors = [color_map[label] for label in sink_labels]

        # plot everything (even the all‐zero ones) for stacking consistency
        src_pc = ax.stackplot(time, sources, colors=source_colors, alpha=0.8)
        snk_pc = ax.stackplot(time, [-s for s in sinks], colors=sink_colors, alpha=0.8)

        # pick out just the non‐zero ones _in this cluster_
        src_handles = []
        src_labels = []
        for arr, pc, lbl in zip(sources, src_pc, source_labels):
            if np.any(arr > 0):
                src_handles.append(pc)
                src_labels.append(lbl)

        snk_handles = []
        snk_labels = []
        for arr, pc, lbl in zip(sinks, snk_pc, sink_labels):
            if np.any(arr > 0):
                snk_handles.append(pc)
                snk_labels.append(lbl)

        # now merge into the _global_ lists, deduping by label
        for h, l in zip(src_handles + snk_handles,
                        src_labels + snk_labels):
            if l not in all_labels:
                all_handles.append(h)
                all_labels.append(l)

        ax.set_ylabel('Electrical Power [W]')
        ax.set_title(f'Cluster {c} - Energy Hub Electrical Power Balance')
        ax.grid(True)

    if all_handles:
        axes[0].legend(all_handles, all_labels,
                       loc='upper right', ncol=2)

    axes[-1].set_xlabel('Time steps [h]')
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'energy_hub')
    os.makedirs(path, exist_ok=True)
    fig.savefig(os.path.join(path, f"el_energy_hub.png"), dpi=300)

def th_energy_hub(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_map = {
        "STC": "yellow",
        "HP": "blue",
        "EB": "orange",
        "CHP": "green",
        "BOI": "red",
        "GHP": "cyan",
        "BCHP": "brown",
        "BBOI": "pink",
        "WCHP": "olive",
        "WBOI": "purple",
        "FC": "magenta",
        "TES discharge": "black",
        "AC": "lightblue",
        "TES charge": "brown",
        "Heating Demand": "darkred",
        "DHW Demand": "darkorange",
        "Network Losses": "grey"

    }

    fig, axes = plt.subplots(num_clusters, 1, figsize=(12, 4 * num_clusters), sharex=True)

    if num_clusters == 1:
        axes = [axes]

    # these two lists will collect _all_ the non‐zero
    # handles & labels from _all_ clusters:
    all_handles = []
    all_labels  = []

    for c in range(num_clusters):
        ax = axes[c]

        # ---- SOURCES ----
        STC = safe_array(plotData, c, "eh_heat", "STC", None, time_steps)
        HP = safe_array(plotData, c, "eh_heat", "HP", None, time_steps)
        EB = safe_array(plotData, c, "eh_heat", "EB", None, time_steps)
        CHP = safe_array(plotData, c, "eh_heat", "CHP", None, time_steps)
        BOI = safe_array(plotData, c, "eh_heat", "BOI", None, time_steps)
        GHP = safe_array(plotData, c, "eh_heat", "GHP", None, time_steps)
        BCHP = safe_array(plotData, c, "eh_heat", "BCHP", None, time_steps)
        BBOI = safe_array(plotData, c, "eh_heat", "BBOI", None, time_steps)
        WCHP = safe_array(plotData, c, "eh_heat", "WCHP", None, time_steps)
        WBOI = safe_array(plotData, c, "eh_heat", "WBOI", None, time_steps)
        FC = safe_array(plotData, c, "eh_heat", "FC", None, time_steps)
        dch_TES = safe_array(plotData, c, "eh_dch", "TES", None, time_steps)

        sources = [
            STC, HP, EB, CHP, BOI, GHP,
            BCHP, BBOI, WCHP, WBOI, FC, dch_TES
        ]
        source_labels = ["STC", "HP", "EB", "CHP", "BOI", "GHP",
                         "BCHP", "BBOI", "WCHP", "WBOI", "FC", "TES discharge"]
        source_colors = [color_map[label] for label in source_labels]

        # ---- SINKS ----
        AC = safe_array(plotData, c, "eh_heat", "AC", None, time_steps)
        ch_TES = safe_array(plotData, c, "eh_ch", "TES", None, time_steps)
        # Demand
        total_heating = np.zeros(time_steps)
        total_dhw = np.zeros(time_steps)
        for n in range(num_buildings):
            total_heating += np.array(plotData["resultsOptimization"][c][n]["Heating"]["Q_th"])
            total_dhw += np.array(plotData["resultsOptimization"][c][n]["DHW"]["Q_th"])
        # NETWORK LOSSES
        if "total_losses_heating_network_cluster" in data.heat_grid_data:
            losses = np.array(data.heat_grid_data["total_losses_heating_network_cluster"][c]) * 1000
        else:
            losses = np.zeros(time_steps)

        heating_sink = total_heating
        dhw_sink = total_dhw

        sinks = [losses, heating_sink, dhw_sink, AC, ch_TES]
        sink_labels = ["Network Losses", "Heating Demand", "DHW Demand", "AC", "TES charge"]
        sink_colors = [color_map[label] for label in sink_labels]

        # plot everything (even the all‐zero ones) for stacking consistency
        src_pc = ax.stackplot(time, sources, colors=source_colors, alpha=0.8)
        snk_pc = ax.stackplot(time, [-s for s in sinks], colors=sink_colors, alpha=0.8)

        # pick out just the non‐zero ones _in this cluster_
        src_handles = []
        src_labels = []
        for arr, pc, lbl in zip(sources, src_pc, source_labels):
            if np.any(arr > 0):
                src_handles.append(pc)
                src_labels.append(lbl)

        snk_handles = []
        snk_labels = []
        for arr, pc, lbl in zip(sinks, snk_pc, sink_labels):
            if np.any(arr > 0):
                snk_handles.append(pc)
                snk_labels.append(lbl)

        # now merge into the _global_ lists, deduping by label
        for h, l in zip(src_handles + snk_handles,
                        src_labels + snk_labels):
            if l not in all_labels:
                all_handles.append(h)
                all_labels.append(l)

        ax.set_ylabel('Thermal Power [W]')
        ax.set_title(f'Cluster {c} - Energy Hub Thermal Power Balance')
        ax.grid(True)

    if all_handles:
        axes[0].legend(all_handles, all_labels,
                       loc='upper right', ncol=2)

    axes[-1].set_xlabel('Time steps [h]')
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'energy_hub')
    os.makedirs(path, exist_ok=True)
    fig.savefig(os.path.join(path, f"th_energy_hub.png"), dpi=300)

def district(plotData, data):
    num_clusters = plotData["num_clusters"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_map = {
        "El. Import": "grey",
        "Gas Import": "brown",
        "El. Export": "blue"
    }

    fig, axes = plt.subplots(num_clusters, 1, figsize=(12, 4 * num_clusters), sharex=True)

    if num_clusters == 1:
        axes = [axes]

    # these two lists will collect _all_ the non‐zero
    # handles & labels from _all_ clusters:
    all_handles = []
    all_labels  = []

    for c in range(num_clusters):
        ax = axes[c]

        # ---- SOURCES ----
        # Power and gas drawn from grids
        P_dem_gcp = np.array(plotData["resultsOptimization"][c]["P_dem_gcp"])  # Grid import
        P_gas_total = np.array(plotData["resultsOptimization"][c]["P_gas_total"])  # Gas import

        sources = [P_dem_gcp, P_gas_total]
        source_labels = ["El. Import", "Gas Import"]
        source_colors = [color_map[label] for label in source_labels]

        # ---- SINKS ----
        P_inj_gcp = np.array(plotData["resultsOptimization"][c]["P_inj_gcp"])  # Grid feed-in

        sinks = [P_inj_gcp]
        sink_labels = ["El. Export"]
        sink_colors = [color_map[label] for label in sink_labels]

        # plot everything (even the all‐zero ones) for stacking consistency
        src_pc = ax.stackplot(time, sources, colors=source_colors, alpha=0.8)
        snk_pc = ax.stackplot(time, [-s for s in sinks], colors=sink_colors, alpha=0.8)

        # pick out just the non‐zero ones _in this cluster_
        src_handles = []
        src_labels = []
        for arr, pc, lbl in zip(sources, src_pc, source_labels):
            if np.any(arr > 0):
                src_handles.append(pc)
                src_labels.append(lbl)

        snk_handles = []
        snk_labels = []
        for arr, pc, lbl in zip(sinks, snk_pc, sink_labels):
            if np.any(arr > 0):
                snk_handles.append(pc)
                snk_labels.append(lbl)

        # now merge into the _global_ lists, deduping by label
        for h, l in zip(src_handles + snk_handles,
                        src_labels + snk_labels):
            if l not in all_labels:
                all_handles.append(h)
                all_labels.append(l)

        ax.set_ylabel('Power [W]')
        ax.set_title(f'Cluster {c} - District Electrical & Gas Exchange')
        ax.grid(True)

    if all_handles:
        axes[0].legend(all_handles, all_labels,
                       loc='upper right', ncol=2)

    axes[-1].set_xlabel('Time steps [h]')
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'district')
    os.makedirs(path, exist_ok=True)
    fig.savefig(os.path.join(path, f"district.png"), dpi=300)

def plot_all(data):
    # initialize input data for calculation of KPIs

    plotData = {}

    plotData["num_clusters"] = data.time["clusterNumber"]
    plotData["num_buildings"] = len(data.district)
    plotData["time_steps"] = int(data.time["clusterLength"]/data.time["timeResolution"])
    plotData["time"] = range(plotData["time_steps"])

    plotData["resultsOptimization"] = data.resultsOptimization

    el_buildings(plotData, data)
    th_buildings(plotData, data)
    el_all_buildings(plotData, data)
    th_all_buildings(plotData, data)
    if any(building["buildingFeatures"]["heater"] == "heat_grid" for building in data.district):
        el_energy_hub(plotData, data)
    if any(building["buildingFeatures"]["heater"] == "heat_grid" for building in data.district):
        th_energy_hub(plotData, data)
    district(plotData, data)
#    plt.show()

def safe_array(plotData, c, n_or_key, device, var, time_steps):
    """
    Safely extract an array for a device and variable, or just the device if var is None.
    """
    try:
        if var is not None:
            return np.array(plotData["resultsOptimization"][c][n_or_key][device][var])
        else:
            return np.array(plotData["resultsOptimization"][c][n_or_key][device])
    except KeyError:
        return np.zeros(time_steps)