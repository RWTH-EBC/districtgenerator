import matplotlib.pyplot as plt
import numpy as np
import os
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
import re

plt.rcParams.update({
    'font.size': 21,           # Base font size
    'axes.titlesize': 23,      # Title font
    'axes.labelsize': 21,      # X and Y axis labels
    'xtick.labelsize': 19,     # X tick labels
    'ytick.labelsize': 19,     # Y tick labels
    'legend.fontsize': 17.5,   # Legend
    'figure.titlesize': 23     # Figure title
})


def _sanitize_name(value):
    """Sanitize a string to be used as a filename."""
    value = str(value)
    value = value.strip().replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9_\-.]", "", value)
    return value


def get_plot_base_path(data, subfolder=None):
    """Get the base path for saving plots, organized by scenario and business model."""
    scenario = _sanitize_name(data.scenario_name)
    bm = _sanitize_name(data.ecoData.get("business_model", "unknown_bm"))

    path = os.path.join(data.resultPath, "plots", scenario, f"bm_{bm}")
    if subfolder is not None:
        path = os.path.join(path, subfolder)

    os.makedirs(path, exist_ok=True)
    return path


def build_plot_data(data, year):
    """
    Build the plotData dictionary for a specific year.

    Parameters
    ----------
    data : Datahandler
        The data object containing resultsOptimization.
    year : int
        The support year to extract data for.

    Returns
    -------
    dict
        plotData dictionary with year-specific optimization results.
    """
    if year not in data.resultsOptimization:
        raise KeyError(
            f"Year {year} not found in data.resultsOptimization. "
            f"Available years: {list(data.resultsOptimization.keys())}"
        )

    plotData = {}
    plotData["year"] = year
    plotData["business_model"] = data.ecoData.get("business_model", "unknown_bm")
    plotData["num_clusters"] = data.time["clusterNumber"]
    plotData["num_buildings"] = len(data.district)
    plotData["time_steps"] = int(data.time["clusterLength"] / data.time["timeResolution"])
    plotData["time"] = range(plotData["time_steps"])
    plotData["resultsOptimization"] = data.resultsOptimization[year]
    return plotData


def _apply_figure_title(fig, title, plotData):
    """Apply a standardized title including business model and year."""
    bm = plotData.get("business_model", "unknown_bm")
    year = plotData.get("year", "unknown_year")
    fig.suptitle(f"{title} – BM {bm} – Jahr {year}")
    fig.tight_layout(rect=[0, 0, 1, 0.95])


def _collect_figures(result):
    """Normalize plot function return values to list of (key, fig) tuples."""
    if isinstance(result, list):
        return result
    return [(None, result)]


def _save_plot_pages(data, years, plot_func, subfolder, filename_pattern):
    """
    Save plots for all years into multi-page PDFs.

    Parameters
    ----------
    data : Datahandler
        The data object.
    years : list
        List of support years to plot.
    plot_func : callable
        The plotting function to call.
    subfolder : str
        Subfolder within the plot base path.
    filename_pattern : str or callable
        Filename or function returning filename from key.
    """
    path = get_plot_base_path(data, subfolder=subfolder)
    pdf_handles = {}

    try:
        for year in years:
            plotData = build_plot_data(data, year)
            figures = _collect_figures(plot_func(plotData, data))

            for key, fig in figures:
                filename = filename_pattern(key) if callable(filename_pattern) else filename_pattern
                if filename not in pdf_handles:
                    pdf_handles[filename] = PdfPages(os.path.join(path, filename))
                pdf_handles[filename].savefig(fig, bbox_inches="tight")
                plt.close(fig)
    finally:
        for pdf in pdf_handles.values():
            pdf.close()


def el_buildings(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "From grid", "From EH", "PV decentral", "CHP", "FC", "BAT discharge", "EV discharge",
        "Demand", "EV charge", "HP", "EH", "BAT charge", "To grid"
    ]

    palette = sns.color_palette("tab20", n_colors=len(color_labels))
    color_map = {label: palette[i] for i, label in enumerate(color_labels)}

    figures = []

    # Pre-calculate total_res_load for all clusters (performance optimization)
    # This avoids recalculating the same sum for each building
    total_res_load_per_cluster = {}
    for c in range(num_clusters):
        total_res_load = np.zeros(time_steps)
        for n_temp in range(num_buildings):
            total_res_load += np.array(plotData["resultsOptimization"][c][n_temp]["res_load"]) / 1000
        total_res_load_per_cluster[c] = total_res_load

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

            # Get res_load (total residual load: from grid AND/OR from EH)
            res_load_total = np.array(plotData["resultsOptimization"][c][n]["res_load"]) / 1000

            # Decentral generation at building level
            PV_power = safe_array(plotData, c, n, "PV", "P_el", time_steps) / 1000
            CHP = safe_array(plotData, c, n, "CHP", "P_el", time_steps) / 1000
            FC = safe_array(plotData, c, n, "FC", "P_el", time_steps) / 1000
            dch_BAT = safe_array(plotData, c, n, "BAT", "dch", time_steps) / 1000
            dch_EV = safe_array(plotData, c, n, "EV", "dch", time_steps) / 1000

            # ===== SPLIT residual load using direct eh_to_buildings result =====

            # Direct EH supply to all buildings in this cluster
            eh_to_buildings_total = np.array(
                plotData["resultsOptimization"][c].get("eh_to_buildings", np.zeros(time_steps))
            ) / 1000

            # Total residual load of all buildings in this cluster
            total_res_load = total_res_load_per_cluster[c]

            # EH supply cannot exceed total residual load
            eh_to_buildings_total = np.minimum(eh_to_buildings_total, total_res_load)

            # Allocate EH supply proportionally to this building
            building_share = np.divide(
                res_load_total,
                total_res_load,
                out=np.zeros_like(res_load_total),
                where=total_res_load > 1e-9
            )

            eh_to_building = building_share * eh_to_buildings_total

            # Remaining residual load is interpreted as direct grid supply
            grid_to_building = np.maximum(0, res_load_total - eh_to_building)

            # ===== END SPLIT =====

            # negative (demands/sinks)
            feed = np.array(plotData["resultsOptimization"][c][n]["res_inj"]) / 1000
            demand = np.array(plotData["resultsOptimization"][c][n]["Elec_dem"]["P_el"]) / 1000

            ch_EV = safe_array(plotData, c, n, "EV", "ch", time_steps) / 1000
            HP = safe_array(plotData, c, n, "HP", "P_el", time_steps) / 1000
            EH = safe_array(plotData, c, n, "EH", "P_el", time_steps) / 1000
            ch_BAT = safe_array(plotData, c, n, "BAT", "ch", time_steps) / 1000

            # SOURCES (electricity supply to building)
            sources = [grid_to_building, eh_to_building, PV_power, CHP, FC, dch_BAT, dch_EV]
            source_labels = ["From grid", "From EH", "PV decentral", "CHP", "FC", "BAT discharge", "EV discharge"]
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

            # Add a legend centered above each subplot
            if src_handles or snk_handles:
                handles = src_handles + snk_handles
                labels = src_labels + snk_labels
                ax.legend(
                    handles,
                    labels,
                    loc='lower center',
                    ncol=7,
                    columnspacing=0.45,
                    handletextpad=0.15,
                    bbox_to_anchor=(0.5, 1),  # moves legend above each axes
                    frameon=False
                )

        for ax in axes:
            ax.set_xlabel("Time (hours)")
            ax.tick_params(labelbottom=True)
        plt.tight_layout()
        plt.subplots_adjust(top=0.96) # reserve space at the top for the legend

        _apply_figure_title(fig, f"Electrical building balance {n}", plotData)
        figures.append((f"building_{n}", fig))

    return figures


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

    figures = []

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

            dhw = np.array(plotData["resultsOptimization"][c][n]["DHW_dem"]["Q_th"]) / 1000
            heating = np.array(plotData["resultsOptimization"][c][n]["Heating_dem"]["Q_th"]) / 1000

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

            # Add a legend centered above each subplot
            if src_handles or snk_handles:
                handles = src_handles + snk_handles
                labels = src_labels + snk_labels
                ax.legend(
                    handles,
                    labels,
                    loc='lower center',
                    ncol=5,
                    columnspacing=0.45,
                    handletextpad=0.15,
                    bbox_to_anchor=(0.5, 1),  # moves legend above each axes
                    frameon=False
                )

        for ax in axes:
            ax.set_xlabel("Time (hours)")
            ax.tick_params(labelbottom=True)
        plt.tight_layout()
        plt.subplots_adjust(top=0.96) # reserve space at the top for the legend

        _apply_figure_title(fig, f"Thermal building balance {n}", plotData)
        figures.append((f"building_{n}", fig))

    return figures


def el_all_buildings(plotData, data):
    num_clusters = plotData["num_clusters"]
    num_buildings = plotData["num_buildings"]

    time_steps = plotData["time_steps"]
    time = plotData["time"]

    color_labels = [
        "From grid", "From EH", "PV decentral", "CHP", "FC", "BAT discharge", "EV discharge",
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
        total_res_load = np.zeros(time_steps)
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
            res_load = np.array(plotData["resultsOptimization"][c][n]["res_load"]) / 1000

            PV_power = safe_array(plotData, c, n, "PV", "P_el", time_steps) / 1000
            CHP = safe_array(plotData, c, n, "CHP", "P_el", time_steps) / 1000
            FC = safe_array(plotData, c, n, "FC", "P_el", time_steps) / 1000
            dch_BAT = safe_array(plotData, c, n, "BAT", "dch", time_steps) / 1000
            dch_EV = safe_array(plotData, c, n, "EV", "dch", time_steps) / 1000

            feed = np.array(plotData["resultsOptimization"][c][n]["res_inj"])  / 1000 # always present
            demand = np.array(plotData["resultsOptimization"][c][n]["Elec_dem"]["P_el"]) / 1000 # always present

            ch_EV = safe_array(plotData, c, n, "EV", "ch", time_steps) / 1000
            HP = safe_array(plotData, c, n, "HP", "P_el", time_steps) / 1000
            EH = safe_array(plotData, c, n, "EH", "P_el", time_steps) / 1000
            ch_BAT = safe_array(plotData, c, n, "BAT", "ch", time_steps) / 1000

            # Sum for all buildings
            total_res_load += res_load
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

        # ===== SPLIT aggregate residual load using direct eh_to_buildings result =====

        # Direct EH supply to all buildings in this cluster
        total_eh_to_buildings = np.array(
            plotData["resultsOptimization"][c].get("eh_to_buildings", np.zeros(time_steps))
        ) / 1000

        # EH supply cannot exceed total residual building load
        total_eh_to_buildings = np.minimum(total_eh_to_buildings, total_res_load)

        # Remaining residual load is interpreted as direct grid supply
        total_grid_to_buildings = np.maximum(0, total_res_load - total_eh_to_buildings)

        # ===== END SPLIT =====

        # ---- Build sources ----
        sources = [total_grid_to_buildings, total_eh_to_buildings, total_PV, total_CHP, total_FC, total_dch_BAT,
                   total_dch_EV]
        source_labels = ["From grid", "From EH", "PV decentral", "CHP", "FC", "BAT discharge", "EV discharge"]
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
        # Create one legend for the entire figure, placed above all subplots
        fig.legend(
            all_handles,
            all_labels,
            loc='lower center',
            ncol=5,  # adjust columns to fit your labels
            columnspacing=0.45,
            handletextpad=0.15,
            bbox_to_anchor=(0.5, 1),  # 1.05 = just above the top
            frameon=False  # no border (optional)
        )

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()
    plt.subplots_adjust(top=0.96)  # reserve space at the top for the legend

    _apply_figure_title(fig, "Electrical balance all buildings", plotData)
    return fig


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

        # Initialize totals for all sources and sinks
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

        # --- Sum over all buildings ---
        for n in range(num_buildings):
            HP = safe_array(plotData, c, n, "HP", "Q_th",  time_steps) / 1000
            BOI = safe_array(plotData, c, n, "BOI", "Q_th",  time_steps) / 1000
            EH = safe_array(plotData, c, n, "EH", "Q_th",  time_steps) / 1000
            STC = safe_array(plotData, c, n, "STC", "Q_th", time_steps) / 1000
            CHP = safe_array(plotData, c, n, "CHP", "Q_th", time_steps) / 1000
            FC = safe_array(plotData, c, n, "FC", "Q_th", time_steps) / 1000
            dch_TES = safe_array(plotData, c, n, "TES", "dch", time_steps) / 1000
            heat_grid = safe_array(plotData, c, n, "heat_grid", "Q_th", time_steps) / 1000

            ch_TES = safe_array(plotData, c, n, "TES", "ch", time_steps) / 1000
            heating = np.array(plotData["resultsOptimization"][c][n]["Heating_dem"]["Q_th"]) / 1000  # always exists
            dhw = np.array(plotData["resultsOptimization"][c][n]["DHW_dem"]["Q_th"]) / 1000  # always exists

            total_HP += HP
            total_BOI += BOI
            total_EH += EH
            total_STC += STC
            total_CHP += CHP
            total_FC += FC
            total_dch_TES += dch_TES
            total_heat_grid += heat_grid

            total_ch_TES += ch_TES
            total_heating += heating
            total_dhw += dhw

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
        # Create one legend for the entire figure, placed above all subplots
        fig.legend(
            all_handles,
            all_labels,
            loc='lower center',
            ncol=4,  # adjust columns to fit your labels
            columnspacing=0.45,
            handletextpad=0.15,
            bbox_to_anchor=(0.5, 1),  # 1.05 = just above the top
            frameon=False  # no border (optional)
        )

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()
    plt.subplots_adjust(top=0.96)  # reserve space at the top for the legend

    _apply_figure_title(fig, "Thermal balance all buildings", plotData)
    return fig


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
        EH = safe_array(plotData, c, "eh_power", "EB", None, time_steps) / 1000
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
        # Create one legend for the entire figure, placed above all subplots
        fig.legend(
            all_handles,
            all_labels,
            loc='lower center',
            ncol=5,  # adjust columns to fit your labels
            columnspacing=0.45,
            handletextpad=0.15,
            bbox_to_anchor=(0.5, 1),  # 1.05 = just above the top
            frameon=False  # no border (optional)
        )

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()
    plt.subplots_adjust(top=0.96)  # reserve space at the top for the legend

    _apply_figure_title(fig, "Electrical energy hub balance", plotData)
    return fig


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
            total_heating += np.array(plotData["resultsOptimization"][c][n]["Heating_dem"]["Q_th"]) / 1000
            total_dhw += np.array(plotData["resultsOptimization"][c][n]["DHW_dem"]["Q_th"]) / 1000
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
    plt.subplots_adjust(top=0.96)  # reserve space at the top for the legend

    _apply_figure_title(fig, "Thermal energy hub balance", plotData)
    return fig


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
    all_labels = []

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
        # Create one legend for the entire figure, placed above all subplots
        fig.legend(
            all_handles,
            all_labels,
            loc='lower center',
            ncol=5,  # adjust columns to fit your labels
            columnspacing=0.45,
            handletextpad=0.15,
            bbox_to_anchor=(0.5, 1),  # 1.05 = just above the top
            frameon=False  # no border (optional)
        )

    for ax in axes:
        ax.set_xlabel("Time (hours)")
        ax.tick_params(labelbottom=True)
    plt.tight_layout()
    plt.subplots_adjust(top=0.96)  # reserve space at the top for the legend

    _apply_figure_title(fig, "District balance", plotData)
    return fig

def plot_all(data, years=None):
    """
     # initialize input data for calculation of KPIs
    Create multi-page PDFs for all available support years.
    One PDF is generated per plot type. For building-level plots, one PDF per building is generated.

    Parameters
    ----------
    data : Datahandler
        The data object containing resultsOptimization.
    years : list or int, optional
        Support years to plot. If None, uses all interpolation_points.
    """
    if years is None:
        years = list(data.ecoData["interpolation_points"])
    elif isinstance(years, (int, float)):
        years = [years]

    bm = _sanitize_name(data.ecoData.get("business_model", "unknown_bm"))

    _save_plot_pages(data, years, el_buildings, "buildings", lambda key: f"el_{key}_bm_{bm}.pdf")
    _save_plot_pages(data, years, th_buildings, "buildings", lambda key: f"th_{key}_bm_{bm}.pdf")
    _save_plot_pages(data, years, el_all_buildings, "buildings", f"el_all_buildings_bm_{bm}.pdf")
    _save_plot_pages(data, years, th_all_buildings, "buildings", f"th_all_buildings_bm_{bm}.pdf")

    if any(building["buildingFeatures"]["heater"] == "heat_grid" for building in data.district):
        _save_plot_pages(data, years, el_energy_hub, "energy_hub", f"el_energy_hub_bm_{bm}.pdf")
        _save_plot_pages(data, years, th_energy_hub, "energy_hub", f"th_energy_hub_bm_{bm}.pdf")

    _save_plot_pages(data, years, district, "district", f"district_bm_{bm}.pdf")


def plot_single_year(data, year=None):
    """
    Create all plots for one single support year.

    Parameters
    ----------
    data : Datahandler
        The data object containing resultsOptimization.
    year : int, optional
        Support year to plot. If None, uses first interpolation_point.
    """
    if year is None:
        year = data.ecoData["interpolation_points"][0]
    plot_all(data, years=[year])


def safe_array(plotData, c, n_or_key, device, var, time_steps):
    """
    Safely extract an array for a device and variable, or just the device if var is None.
    Returns zeros if the requested entry is missing or malformed.

    Parameters
    ----------
    plotData : dict
        The plotData dictionary containing resultsOptimization.
    c : int
        Cluster index.
    n_or_key : int or str
        Building index or key string (e.g., "eh_power").
    device : str
        Device name (e.g., "PV", "HP", "BAT").
    var : str or None
        Variable name (e.g., "P_el", "Q_th", "ch", "dch"). None for direct device access.
    time_steps : int
        Number of time steps (used to create zero array on failure).

    Returns
    -------
    np.ndarray
        Array of values or zeros if not found.
    """
    try:
        if var is not None:
            arr = np.array(plotData["resultsOptimization"][c][n_or_key][device][var])
        else:
            arr = np.array(plotData["resultsOptimization"][c][n_or_key][device])

        if len(arr) != time_steps:
            return np.zeros(time_steps)
        return arr
    except (KeyError, TypeError, IndexError, ValueError):
        return np.zeros(time_steps)