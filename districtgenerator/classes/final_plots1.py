import matplotlib.pyplot as plt
import numpy as np
import os
import seaborn as sns

plt.rcParams.update({
    'font.size': 16,           # Base font size
    'axes.titlesize': 18,      # Title font
    'axes.labelsize': 16,      # X and Y axis labels
    'xtick.labelsize': 14,     # X tick labels
    'ytick.labelsize': 14,     # Y tick labels
    'legend.fontsize': 14,     # Legend
    'figure.titlesize': 18     # Figure title
})

def el_buildings(plotData, data):

    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "From grid", "PV", "CHP", "FC", "BAT discharge", "EV discharge",
        "Demand", "EV charge", "HP", "EH", "BAT charge", "To grid"
    ]

    palette = sns.color_palette("tab20", n_colors=len(color_labels))
    color_map = {label: palette[i] for i, label in enumerate(color_labels)}


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
            buy = np.array(plotData["resultsOptimization"][c][n]["res_load"]) / 1000

            PV_power = safe_array(plotData, c, n, "PV", "P_el", time_steps) / 1000
            CHP = safe_array(plotData, c, n, "CHP", "P_el", time_steps) / 1000
            FC = safe_array(plotData, c, n, "FC", "P_el", time_steps) / 1000
            dch_BAT = safe_array(plotData, c, n, "BAT", "dch", time_steps) / 1000
            dch_EV = safe_array(plotData, c, n, "EV", "dch", time_steps) / 1000

            # negative (demands/sinks)
            feed = np.array(plotData["resultsOptimization"][c][n]["res_inj"]) / 1000
            demand = np.array(plotData["resultsOptimization"][c][n]["Demand"]["P_el"]) / 1000

            ch_EV = safe_array(plotData, c, n, "EV", "ch", time_steps) / 1000
            HP = safe_array(plotData, c, n, "HP", "P_el", time_steps) / 1000
            EH = safe_array(plotData, c, n, "EH", "P_el", time_steps) / 1000
            ch_BAT = safe_array(plotData, c, n, "BAT", "ch", time_steps) / 1000

            # SOURCES
            sources = [buy, PV_power, CHP, FC, dch_BAT, dch_EV]
            source_labels = ["From grid", "PV", "CHP", "FC", "BAT discharge", "EV discharge"]
            source_colors = [color_map[label] for label in source_labels]

            # SINKS
            sinks = [demand, ch_EV, HP, EH, ch_BAT, feed]
            sink_labels = ["Demand", "EV charge", "HP", "EH", "BAT charge", "To grid"]
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

            ax.set_ylabel('Electrical Power (kW)')
            ax.grid(True)

        if all_handles:
            for ax in axes:
                ax.legend(all_handles, all_labels, loc='upper right', ncol=2)

        for ax in axes:
            ax.set_xlabel("Time (hours)")
            ax.tick_params(labelbottom=True)
        plt.tight_layout()

        path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'buildings')
        os.makedirs(path, exist_ok=True)
#        fig.savefig(os.path.join(path, f"el_building_{n}.png"), dpi=300)
        fig.savefig(os.path.join(path, f"el_building_{n}.pdf"))

def th_buildings(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "Heat Pump", "Boiler", "Electric Heater", "Solar Thermal",
        "CHP", "Fuel Cell", "TES discharge", "TES charge",
        "Heating Demand", "DHW Demand", "Heat Grid"
    ]

    palette = sns.color_palette("tab20", n_colors=len(color_labels))
    color_map = {label: palette[i] for i, label in enumerate(color_labels)}

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
            HP = safe_array(plotData, c, n, "HP", "Q_th", time_steps) / 1000
            BOI = safe_array(plotData, c, n, "BOI", "Q_th", time_steps) / 1000
            EH = safe_array(plotData, c, n, "EH", "Q_th", time_steps) / 1000
            STC = safe_array(plotData, c, n, "STC", "Q_th", time_steps) / 1000
            CHP = safe_array(plotData, c, n, "CHP", "Q_th", time_steps) / 1000
            FC = safe_array(plotData, c, n, "FC", "Q_th", time_steps) / 1000
            dch_TES = safe_array(plotData, c, n, "TES", "dch", time_steps) / 1000
            heat_grid = safe_array(plotData, c, n, "heat_grid", "Q_th", time_steps) / 1000

            # negative (demands/sinks)
            ch_TES = safe_array(plotData, c, n, "TES", "ch", time_steps) / 1000

            dhw = np.array(plotData["resultsOptimization"][c][n]["DHW"]["Q_th"]) / 1000
            heating = np.array(plotData["resultsOptimization"][c][n]["Heating"]["Q_th"]) / 1000

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

            ax.set_ylabel('Thermal Power (kW)')
            ax.grid(True)

        if all_handles:
            for ax in axes:
                ax.legend(all_handles, all_labels, loc='upper right', ncol=2)

        for ax in axes:
            ax.set_xlabel("Time (hours)")
            ax.tick_params(labelbottom=True)
        plt.tight_layout()

        path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'buildings')
        os.makedirs(path, exist_ok=True)
#        fig.savefig(os.path.join(path, f"th_building_{n}.png"), dpi=300)
        fig.savefig(os.path.join(path, f"th_building_{n}.pdf"))

def el_all_buildings(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "From grid", "PV", "CHP", "FC", "BAT discharge", "EV discharge",
        "Demand", "EV charge", "HP", "EH", "BAT charge", "To grid"
    ]

    palette = sns.color_palette("tab20", n_colors=len(color_labels))
    color_map = {label: palette[i] for i, label in enumerate(color_labels)}

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
            buy = np.array(plotData["resultsOptimization"][c][n]["res_load"]) / 1000  # no safe_array: always present

            PV_power = safe_array(plotData, c, n, "PV", "P_el", time_steps) / 1000
            CHP = safe_array(plotData, c, n, "CHP", "P_el", time_steps) / 1000
            FC = safe_array(plotData, c, n, "FC", "P_el", time_steps) / 1000
            dch_BAT = safe_array(plotData, c, n, "BAT", "dch", time_steps) / 1000
            dch_EV = safe_array(plotData, c, n, "EV", "dch", time_steps) / 1000

            feed = np.array(plotData["resultsOptimization"][c][n]["res_inj"])  / 1000 # always present
            demand = np.array(plotData["resultsOptimization"][c][n]["Demand"]["P_el"]) / 1000 # always present

            ch_EV = safe_array(plotData, c, n, "EV", "ch", time_steps) / 1000
            HP = safe_array(plotData, c, n, "HP", "P_el", time_steps) / 1000
            EH = safe_array(plotData, c, n, "EH", "P_el", time_steps) / 1000
            ch_BAT = safe_array(plotData, c, n, "BAT", "ch", time_steps) / 1000


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
        source_labels = ["From grid", "PV", "CHP", "FC", "BAT discharge", "EV discharge"]
        source_colors = [color_map[label] for label in source_labels]

        # ---- Build sinks ----
        sinks = [total_demand, total_ch_EV, total_HP, total_EH, total_ch_BAT, total_feed]
        sink_labels = ["Demand", "EV charge", "HP", "EH", "BAT charge", "To grid"]
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

        ax.set_ylabel('Electrical Power (kW)')
        ax.grid(True)

    if all_handles:
        for ax in axes:
            ax.legend(all_handles, all_labels, loc='upper right', ncol=2)

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'buildings')
    os.makedirs(path, exist_ok=True)
#    fig.savefig(os.path.join(path, f"el_all_buildings.png"), dpi=300)
    fig.savefig(os.path.join(path, f"el_all_buildings.pdf"))

def th_all_buildings(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "Heat Pump", "Boiler", "Electric Heater", "Solar Thermal",
        "CHP", "Fuel Cell", "TES discharge", "TES charge",
        "Heating Demand", "DHW Demand", "Heat Grid"
    ]

    palette = sns.color_palette("tab20", n_colors=len(color_labels))
    color_map = {label: palette[i] for i, label in enumerate(color_labels)}

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

            total_HP += safe_array(plotData, c, n, "HP", "Q_th", time_steps) / 1000
            total_BOI += safe_array(plotData, c, n, "BOI", "Q_th", time_steps) / 1000
            total_EH += safe_array(plotData, c, n, "EH", "Q_th", time_steps) / 1000
            total_STC += safe_array(plotData, c, n, "STC", "Q_th", time_steps) / 1000
            total_CHP += safe_array(plotData, c, n, "CHP", "Q_th", time_steps) / 1000
            total_FC += safe_array(plotData, c, n, "FC", "Q_th", time_steps) / 1000
            total_dch_TES += safe_array(plotData, c, n, "TES", "dch", time_steps) / 1000
            total_heat_grid += safe_array(plotData, c, n, "heat_grid", "Q_th", time_steps) / 1000

            total_ch_TES += safe_array(plotData, c, n, "TES", "ch", time_steps) / 1000

            total_heating += np.array(plotData["resultsOptimization"][c][n]["Heating"]["Q_th"]) / 1000  # always exists
            total_dhw += np.array(plotData["resultsOptimization"][c][n]["DHW"]["Q_th"]) / 1000  # always exists

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

        ax.set_ylabel('Thermal Power (kW)')
        ax.grid(True)

    if all_handles:
        for ax in axes:
            ax.legend(all_handles, all_labels, loc='upper right', ncol=2)

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'buildings')
    os.makedirs(path, exist_ok=True)
#    fig.savefig(os.path.join(path, f"th_all_buildings.png"), dpi=300)
    fig.savefig(os.path.join(path, f"th_all_buildings.pdf"))

def el_energy_hub(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC", "from_grid",
        "BAT discharge", "HP", "EH", "CC", "ELYZ", "BAT charge", "to_grid"
    ]

    palette = sns.color_palette("tab20", n_colors=len(color_labels))
    color_map = {label: palette[i] for i, label in enumerate(color_labels)}

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

        PV = safe_array(plotData, c, "eh_power", "PV", None, time_steps) / 1000
        WT = safe_array(plotData, c, "eh_power", "WT", None, time_steps) / 1000
        WAT = safe_array(plotData, c, "eh_power", "WAT", None, time_steps) / 1000
        CHP = safe_array(plotData, c, "eh_power", "CHP", None, time_steps) / 1000
        BCHP = safe_array(plotData, c, "eh_power", "BCHP", None, time_steps) / 1000
        WCHP = safe_array(plotData, c, "eh_power", "WCHP", None, time_steps) / 1000
        FC = safe_array(plotData, c, "eh_power", "FC", None, time_steps) / 1000
        from_grid = safe_array(plotData, c, "eh_power", "from_grid", None, time_steps) / 1000
        dch_BAT = safe_array(plotData, c, "eh_dch", "BAT", None, time_steps) / 1000

        sources = [
            PV, WT, WAT, CHP, BCHP, WCHP,
            FC, from_grid, dch_BAT
        ]
        source_labels = ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP",
                         "FC", "from_grid", "BAT discharge"]
        source_colors = [color_map[label] for label in source_labels]

        # ---- SINKS ----
        HP = safe_array(plotData, c, "eh_power", "HP", None, time_steps) / 1000
        EH = safe_array(plotData, c, "eh_power", "EB",None, time_steps) / 1000
        CC = safe_array(plotData, c, "eh_power", "CC", None, time_steps) / 1000
        ELYZ = safe_array(plotData, c, "eh_power", "ELYZ", None, time_steps) / 1000
        ch_BAT = safe_array(plotData, c, "eh_ch", "BAT", None, time_steps) / 1000
        to_grid = safe_array(plotData, c, "eh_power", "to_grid", None, time_steps) / 1000

        sinks = [HP, EH, CC, ELYZ, ch_BAT, to_grid]
        sink_labels = ["HP", "EH", "CC", "ELYZ", "BAT charge", "to_grid"]
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

        ax.set_ylabel('Electrical Power (kW)')
        ax.grid(True)

    if all_handles:
        for ax in axes:
            ax.legend(all_handles, all_labels, loc='upper right', ncol=2)

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'energy_hub')
    os.makedirs(path, exist_ok=True)
#    fig.savefig(os.path.join(path, f"el_energy_hub.png"), dpi=300)
    fig.savefig(os.path.join(path, f"el_energy_hub.pdf"))

def th_energy_hub(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "STC", "HP", "EH", "CHP", "BOI", "GHP", "BCHP", "BBOI",
        "WCHP", "WBOI", "FC", "TES discharge", "AC", "TES charge",
        "Heating Demand", "DHW Demand", "Network Losses"
    ]

    palette = sns.color_palette("tab20", n_colors=len(color_labels))
    color_map = {label: palette[i] for i, label in enumerate(color_labels)}

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
        STC = safe_array(plotData, c, "eh_heat", "STC", None, time_steps) / 1000
        HP = safe_array(plotData, c, "eh_heat", "HP", None, time_steps) / 1000
        EH = safe_array(plotData, c, "eh_heat", "EB", None, time_steps) / 1000
        CHP = safe_array(plotData, c, "eh_heat", "CHP", None, time_steps) / 1000
        BOI = safe_array(plotData, c, "eh_heat", "BOI", None, time_steps) / 1000
        GHP = safe_array(plotData, c, "eh_heat", "GHP", None, time_steps) / 1000
        BCHP = safe_array(plotData, c, "eh_heat", "BCHP", None, time_steps) / 1000
        BBOI = safe_array(plotData, c, "eh_heat", "BBOI", None, time_steps) / 1000
        WCHP = safe_array(plotData, c, "eh_heat", "WCHP", None, time_steps) / 1000
        WBOI = safe_array(plotData, c, "eh_heat", "WBOI", None, time_steps) / 1000
        FC = safe_array(plotData, c, "eh_heat", "FC", None, time_steps) / 1000
        dch_TES = safe_array(plotData, c, "eh_dch", "TES", None, time_steps) / 1000

        sources = [
            STC, HP, EH, CHP, BOI, GHP,
            BCHP, BBOI, WCHP, WBOI, FC, dch_TES
        ]
        source_labels = ["STC", "HP", "EH", "CHP", "BOI", "GHP",
                         "BCHP", "BBOI", "WCHP", "WBOI", "FC", "TES discharge"]
        source_colors = [color_map[label] for label in source_labels]

        # ---- SINKS ----
        AC = safe_array(plotData, c, "eh_heat", "AC", None, time_steps) / 1000
        ch_TES = safe_array(plotData, c, "eh_ch", "TES", None, time_steps) / 1000
        # Demand
        total_heating = np.zeros(time_steps)
        total_dhw = np.zeros(time_steps)
        for n in range(num_buildings):
            total_heating += np.array(plotData["resultsOptimization"][c][n]["Heating"]["Q_th"]) / 1000
            total_dhw += np.array(plotData["resultsOptimization"][c][n]["DHW"]["Q_th"]) / 1000
        # NETWORK LOSSES
        if "total_losses_heating_network_cluster" in data.heat_grid_data:
            losses = np.array(data.heat_grid_data["total_losses_heating_network_cluster"][c])
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

        ax.set_ylabel('Thermal Power (kW)')
        ax.grid(True)

    if all_handles:
        for ax in axes:
            ax.legend(all_handles, all_labels, loc='lower left', ncol=2)

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'energy_hub')
    os.makedirs(path, exist_ok=True)
#    fig.savefig(os.path.join(path, f"th_energy_hub.png"), dpi=300)
    fig.savefig(os.path.join(path, f"th_energy_hub.pdf"))


def district(plotData, data):
    num_clusters = plotData["num_clusters"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "El. Import", "Gas Import", "El. Export"
    ]

    palette = sns.color_palette("tab20", n_colors=len(color_labels))
    color_map = {label: palette[i] for i, label in enumerate(color_labels)}

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
        P_dem_gcp = np.array(plotData["resultsOptimization"][c]["P_dem_gcp"]) / 1000  # Grid import
        P_gas_total = np.array(plotData["resultsOptimization"][c]["P_gas_total"]) / 1000  # Gas import

        sources = [P_dem_gcp, P_gas_total]
        source_labels = ["El. Import", "Gas Import"]
        source_colors = [color_map[label] for label in source_labels]

        # ---- SINKS ----
        P_inj_gcp = np.array(plotData["resultsOptimization"][c]["P_inj_gcp"]) / 1000  # Grid feed-in

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

        ax.set_ylabel('Power (kW)')
        ax.grid(True)

    if all_handles:
        for ax in axes:
            ax.legend(all_handles, all_labels, loc='upper right', ncol=2)

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()

    path = os.path.join(data.resultPath, 'plots', data.scenario_name, 'district')
    os.makedirs(path, exist_ok=True)
#    fig.savefig(os.path.join(path, f"district.png"), dpi=300)
    fig.savefig(os.path.join(path, f"district.pdf"))

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