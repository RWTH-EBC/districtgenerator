# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import pandas as pd
import os
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import warnings

SRCPATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plots_dir = os.path.join(SRCPATH, 'districtgenerator', 'results', 'plots')
os.makedirs(plots_dir, exist_ok=True)
excel_file_name_ending = "results.xlsx"

def example10_comparison_heat_demands(scenario_name):
    warnings.filterwarnings("ignore", category=FutureWarning)

    heat_demands_QG = pd.DataFrame()

    # The original scenario is split into multiple batched csv files
    scenario_folder = os.path.join(SRCPATH, 'districtgenerator', 'data', 'scenarios')
    pattern = f"{scenario_name}_dg_*.csv"

    all_former_files = [file_path for file_path in Path(scenario_folder).glob(pattern)]

    # delete all former batched scenario files to start fresh
    for file_path in all_former_files:
        os.remove(file_path)

    # Initialize District to generate all necessary batched scenario files and map them to districtgenerator format
    data = Datahandler(scenario_name = scenario_name, heat_map_berlin = True)
    
    # Get building model type for later use
    building_model = data.design_building_data.get("thermal_model_type")

    del data # Delete instance to free memory
    
    # These are the batched scenario files created from the WKB data
    all_batched_scenarios = [file_path.stem for file_path in Path(scenario_folder).glob(pattern)]
    print(f"Found {len(all_batched_scenarios)} batched scenario files for processing.")

    # Number of runs to perform for each building
    n_runs = 10
    for run in range(n_runs): 
        print(f"\n--- Run {run+1}/{n_runs} ---")

        for batch_name in all_batched_scenarios:
            print(f"Processing scenario batch file: {batch_name}")
            data = Datahandler(scenario_name = batch_name, heat_map_berlin = False) # No mapping needed here anymore
        
            data.initializeBuildings()
            data.generateEnvironment()
            data.generateBuildings()
            data.generateDemands(calcUserProfiles=True, saveUserProfiles=False, gen_cars=False)

            # Save results to Excel file
            data_frames = load_results_excel(scenario_name=scenario_name, building_model=building_model)
            data_frames = add_demands_to_df(data=data, data_frames=data_frames, run_number=run)
            save_excel(scenario_name=scenario_name, data_frames=data_frames, building_model=building_model)
            del data  # Delete instance to free memory
    
    print("\nSimulation runs completed and results saved to Excel.")

def load_results_excel(scenario_name, building_model="5R1C"):
    """
        Loads the results Excel file for the given scenario name.
        The Excel file is expected to be located in the 'results' directory
        The Excel contains three sheets: 'space_heating', 'dhw', 'total_heat'
    """
    path = os.path.join(SRCPATH, 'districtgenerator', 'results', f"{scenario_name}_{building_model}_{excel_file_name_ending}")
    sheets = ['space_heating', 'dhw', 'total_heat']

    try:
        data_frames = pd.read_excel(path, sheet_name=sheets, index_col=0)
        return data_frames
    except FileNotFoundError:
        print(f"No excel file found here:{path}. Generate empty dataframes to start filling them.")
        data_frames = {sheet: pd.DataFrame() for sheet in sheets}
        for sheet in sheets:
            data_frames[sheet].index.name = 'building_id'
        return data_frames
    
def add_demands_to_df(data, data_frames, run_number):
    """
    Reads out the data Object and adds the heat demands to the dataframes.
    """
    # If the column run_{run_number} does not exist yet, create it  
    for sheet_name in data_frames.keys():
        column_name = f"run_{run_number}"
        if column_name not in data_frames[sheet_name].columns:
            data_frames[sheet_name][column_name] = pd.NA

    # Attributes to translate from dataframe columns to data object attributes
    translation = {
        "space_heating": ["heat"],
        "dhw": ["dhw"],
        "total_heat": ["heat", "dhw"]
    }

    try:
        time_res = data.time["timeResolution"] / 3600.0
    except KeyError:
        time_res = 1.0  # Default to hourly if not specified

    for building in data.district:
        building_id = building["buildingFeatures"]["id"]

        # Get for the building heat, dhw and total heat demand
        building_data = {}
        for sheet_name, demands in translation.items():
            dem = 0
            for d in demands:
                values = getattr(building["user"], d, None)
                if values is not None:
                    dem += sum(values) * time_res / 1000  # Convert W to kWh/a
            building_data[sheet_name] = dem

        # Add data to the respective dataframes
        for sheet_name, demand_value in building_data.items():
            # If the building_id does not exist yet, create a new row
            if building_id not in data_frames[sheet_name].index:
                data_frames[sheet_name].loc[building_id] = pd.NA
            # Add the demand value to the correct column and the correct row
            data_frames[sheet_name].at[building_id, f"run_{run_number}"] = demand_value

    # Sort the dataframes by building_id
    for sheet_name in data_frames.keys():
        data_frames[sheet_name].sort_index(inplace=True)

    return data_frames

def save_excel(scenario_name, data_frames, building_model="5R1C"):
    """
    Saves the dataframes to an Excel file with multiple sheets.
    """
    path = os.path.join(SRCPATH, 'districtgenerator', 'results', f"{scenario_name}_{building_model}_{excel_file_name_ending}")
    with pd.ExcelWriter(path) as writer:
        for sheet_name, df in data_frames.items():
            df.to_excel(writer, sheet_name=sheet_name)
    print(f"Data saved to Excel file: {path}")

def read_wkb_data(scenario_name) -> pd.DataFrame:
    """
    Read the WKB data from an CSV data file.
    Now reads ALL columns from the CSV file for comprehensive analysis.

    Parameters
    ----------
    scenario_name : str
        The name of the scenario to read data for.
    Returns
    -------
    pd.DataFrame
        DataFrame with all available columns from the Excel file.
    """
    
    filename = f"{scenario_name}_wkb.csv"
    file_path = os.path.join(SRCPATH, 'districtgenerator', 'data', 'scenarios', filename)
    
    try:
        print(f"Reading CSV file: {file_path}")

        # Read ALL columns from the CSV file. Index column is 'id' (same as saved in the excel file)
        wkb_df = pd.read_csv(file_path, sep=";", index_col='id')
        print(f"Found {len(wkb_df.columns)} columns in CSV file")
        print(f"DataFrame info:")
        print(f"- Shape: {wkb_df.shape}")
        print(f"- Columns: {list(wkb_df.columns)}")        
        return wkb_df

    except FileNotFoundError:
        print(f"Error: File {file_path} not found!")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return pd.DataFrame()

def analyse_data(scenario_name, building_model = "5R1C"):
    """
    Analyse the combined data for insights.
    
    Parameters
    ----------
    scenario_name : str
        The name of the scenario.
    combined_data : pd.DataFrame
        The combined DataFrame containing heat demands and WKB data.
    
    Returns
    -------
    None
    """    
    # Switch between simulated and measured data to define against which we compare
    simulated_col = 'heat_demand_simulated'
    measured_col = 'energy_consumption_sh'
    relevant_col = measured_col

    ###########################################################
    # Load data
    ###########################################################

    # Choose against which demand data to compare: space_heating, dhw, total_heat
    demand_sheet = 'total_heat'
    data_frames = load_results_excel(scenario_name, building_model=building_model)
    data_frame = data_frames[demand_sheet]
    # WKB data
    WKB_data = read_wkb_data(scenario_name)

    ###########################################################
    # Combine data
    ###########################################################

    combined_data = data_frame.join(WKB_data, how='outer')

    # Save the data in an excel file for manual inspection if needed
    output_path = os.path.join(SRCPATH, 'districtgenerator', 'results', f"processed_data_{scenario_name}.xlsx")
    with pd.ExcelWriter(output_path) as writer:
        combined_data.to_excel(writer, sheet_name='combined_data')

    print(combined_data.columns)  # Display the columns of the DataFrame

    ###########################################################
    # Prepare data for analysis
    ###########################################################

    # For each building, calculate mean and std of simulated heat demand across all runs
    all_demand_cols = [col for col in combined_data.columns if 'run_' in col]
    combined_data['mean_QG'] = combined_data[all_demand_cols].mean(axis=1)

    if len(all_demand_cols) > 1:
        combined_data['std_QG'] = combined_data[all_demand_cols].std(axis=1)
        combined_data['cv_QG'] = combined_data['std_QG'] / combined_data['mean_QG']

    # Calculate the difference between simulated and WKB data
    combined_data["difference_heat_kWh_a_QG"] = combined_data['mean_QG'] - combined_data[relevant_col]
    combined_data["difference_heat_percent_QG"] = (combined_data['difference_heat_kWh_a_QG'] / combined_data[relevant_col]) * 100
    
    # Add here specific analysis and visualizations
    plot_boxplots_gmh_mfh_by_age(combined_data, saniert=False, scenario_name=scenario_name)
    plot_boxplots_gmh_mfh_by_age(combined_data, saniert=True, scenario_name=scenario_name)

# ----------------------------------------
# Code used for visualizations
# ----------------------------------------

def plot_boxplots_by_buildingtype_and_age(
    combined_data,
    saniert=True,
    value_col='difference_heat_percent_QG',
    gebaeudetyp_col='building_type_simplified',
    baujahr_col='construction_year',
    sanierungs_col='renovation_state_simulated',
    scenario_name=None
):
    """
    Erstellt eine Grafik mit Subplots für jeden Gebäudetyp, die den Fehler für jede Altersklasse zeigen.
    Es wird nach saniert/unsaniert gefiltert. Zeigt immer alle 4 Gebäudetypen und 4 Altersklassen an.

    Parameters
    ----------
    combined_data : pd.DataFrame
        Die kombinierte DataFrame mit allen Daten.
    saniert : bool
        True = nur sanierte Gebäude, False = nur unsanierte.
    value_col : str
        Die Spalte mit dem Fehlerwert.
    gebaeudetyp_col : str
        Die Spalte mit dem Gebäudetyp.
    altersklasse_col : str
        Die Spalte mit der Altersklasse.
    sanierungs_col : str
        Die Spalte mit dem Sanierungszustand.
    scenario_name : str
        Optional für Dateinamen.
    """
    import matplotlib.pyplot as plt
    import os
    import numpy as np


    altersklassen_qg = [
        '1860 - 1918',
        '1919 - 1948',
        '1949 - 1957',
        '1958 - 1968',
        '1969 - 1978',
        '1979 - 1983',
        '1984 - 1994',
        '1995 - 2001',
        '2002 - 2009',
        '2010 - 2015',
        '2016 - 2023',
    ]
    
    bins = [1859, 1918, 1948, 1957, 1968, 1978, 1983, 1994, 2001, 2009, 2015, 2023]
    gemappte_altersklasse_col = "baujahr_mapped"

    df = combined_data.copy()
    df[gemappte_altersklasse_col] = pd.cut(df[baujahr_col],
                                           bins=bins,
                                           labels=altersklassen_qg,
                                           right=True,  # z.B. (1859, 1918] -> '1860 - 1918'
                                           ordered=False)

    # Definiere feste Listen für alle zu zeigenden Kategorien
    alle_gebaeudetypen = ['EFH', 'GMH', 'MFH', 'RH']

    # Filter nach teilsaniert/unsaniert
    filter_value = 'teilsaniert' if saniert else 'unsaniert'
    df = df[df[sanierungs_col] == filter_value]
    df = df.dropna(subset=[gebaeudetyp_col, gemappte_altersklasse_col, value_col])
    df = df[np.isfinite(df[value_col])]

    print(f"Gefilterte Daten für '{filter_value}': {len(df)} Datenpunkte")
    print(f"Verfügbare Gebäudetypen in Daten: {sorted(df[gebaeudetyp_col].unique())}")
    print(f"Verfügbare Altersklassen in Daten: {sorted(df[gemappte_altersklasse_col].unique())}")

    # Subplot-Layout: Feste 2x2 Anordnung für 4 Gebäudetypen
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    axes = axes.flatten()

    # Für jeden der 4 Gebäudetypen einen Subplot erstellen
    for i, gebaeudetyp in enumerate(alle_gebaeudetypen):
        ax = axes[i]
        subset = df[df[gebaeudetyp_col] == gebaeudetyp]
        
        boxplot_data = []
        labels = []
        counts = []
        
        # Daten für jede der 4 Altersklassen sammeln
        for altersklasse in altersklassen_qg:
            vals = subset[subset[gemappte_altersklasse_col] == altersklasse][value_col].values
            if len(vals) > 0:
                boxplot_data.append(vals)
                labels.append(str(altersklasse))
                counts.append(len(vals))
            else:
                # Leere Liste für fehlende Altersklassen hinzufügen
                boxplot_data.append([])
                labels.append(str(altersklasse))
                counts.append(0)
        
        # Prüfen ob überhaupt Daten für diesen Gebäudetyp vorhanden sind
        total_count = sum(counts)
        has_data = any(len(data) > 0 for data in boxplot_data)
        
        if not has_data:
            # Keine Daten für diesen Gebäudetyp
            ax.text(0.5, 0.5, f'Keine Daten\nfür {gebaeudetyp}', 
                   ha='center', va='center', transform=ax.transAxes, fontsize=12)
            ax.set_title(f"{gebaeudetyp}\n(n=0)", 
                        fontsize=12, fontweight='bold', pad=15)
            # Setze Standard Y-Limits auch für leere Plots mit sichtbarem Null-Niveau
            ax.set_ylim(-15, 15)
        else:
            # Boxplot erstellen - nur für nicht-leere Daten
            valid_data = [data for data in boxplot_data if len(data) > 0]
            valid_labels = [labels[j] for j, data in enumerate(boxplot_data) if len(data) > 0]
            valid_positions = [j+1 for j, data in enumerate(boxplot_data) if len(data) > 0]
            
            if valid_data:
                bp = ax.boxplot(valid_data, positions=valid_positions, labels=valid_labels, 
                               patch_artist=True, medianprops=dict(color='red', linewidth=2), 
                               showmeans=True)
                
                # Boxen färben
                for patch in bp['boxes']:
                    patch.set_facecolor('lightcoral')
                    patch.set_alpha(0.7)
                
                # Y-Achsen-Bereich ZUERST berechnen und erweitern
                all_valid_data = np.concatenate(valid_data)
                data_min = np.min(all_valid_data)
                data_max = np.max(all_valid_data)
                data_range = data_max - data_min
                
                # Spezialbehandlung für den Fall, dass data_range = 0 (nur ein Datenpunkt oder alle Werte gleich)
                if data_range == 0:
                    # Verwende einen festen Bereich um den Wert
                    fallback_range = max(10, abs(data_max) * 0.2)  # Mindestens 10 oder 20% des Werts
                    data_min = data_max - fallback_range / 2
                    data_max = data_max + fallback_range / 2
                    data_range = fallback_range
                
                # Y-Achse ERWEITERN um sicherzustellen, dass Null immer sichtbar ist
                extended_min = data_min - 0.05 * data_range
                extended_max = data_max + 0.6 * data_range  # MEHR Platz oben für Textboxen
                
                # Stelle sicher, dass Null immer sichtbar ist
                if extended_min > 0:
                    extended_min = min(extended_min, -5)  # Mindestens bis -5%
                if extended_max < 0:
                    extended_max = max(extended_max, 5)   # Mindestens bis +5%
                
                ax.set_ylim(extended_min, extended_max)
                
                # DANN Textbox-Position berechnen - WEITER oberhalb der Daten
                text_y = data_max + 0.25 * data_range  # Textboxen weiter oben
                
                # Statistiken als Textboxen - nur für vorhandene Daten
                for idx, (pos, vals) in enumerate(zip(valid_positions, valid_data)):
                    mean = np.mean(vals)
                    std = np.std(vals)
                    n = len(vals)
                    stats_text = f"n={n}\nμ={mean:.1f}%\nσ={std:.1f}%"
                    ax.text(pos, text_y, stats_text, ha='center', va='center', fontsize=8,
                            bbox=dict(boxstyle='round,pad=0.2', facecolor='lightyellow', 
                                    edgecolor='gray', alpha=0.9))
            
            # Titel mit Gesamtanzahl
            ax.set_title(f"{gebaeudetyp}\n(n={total_count})", 
                        fontsize=12, fontweight='bold', pad=15)
        
        # Immer alle 4 Altersklassen auf X-Achse anzeigen
        ax.set_xticks(range(1, len(altersklassen_qg) + 1))
        ax.set_xticklabels(altersklassen_qg, rotation=0, fontsize=9)
        # X-Achse Limits erweitern für mehr Platz an den Rändern
        ax.set_xlim(0.5, len(altersklassen_qg) + 0.5)
        ax.set_xlabel('Altersklasse (Baujahr)', fontsize=10, labelpad=8)
        ax.set_ylabel('Relative Abweichung (%)', fontsize=10, labelpad=8)
        # Null-Linie hervorheben für bessere Sichtbarkeit
        ax.axhline(y=0, color='gray', alpha=0.7, linewidth=1)
        #ax.grid(True, alpha=0.3)
        ax.tick_params(axis='y', labelsize=9)
        
        # Markiere fehlende Altersklassen
        for j, (altersklasse, count) in enumerate(zip(altersklassen_qg, counts)):
            if count == 0:
                # Berechne die Y-Position basierend auf vorhandenen Statistik-Textboxen
                if has_data and len(valid_data) > 0:
                    # Verwende dieselbe Y-Position wie die Statistik-Textboxen
                    all_valid_data = np.concatenate(valid_data)
                    data_min_calc = np.min(all_valid_data)
                    data_max_calc = np.max(all_valid_data)
                    data_range_calc = data_max_calc - data_min_calc
                    
                    # Spezialbehandlung für data_range = 0
                    if data_range_calc == 0:
                        fallback_range = max(10, abs(data_max_calc) * 0.2)
                        data_max_calc = data_max_calc + fallback_range / 2
                        data_range_calc = fallback_range
                    
                    # Gleiche Y-Position wie die Statistik-Textboxen
                    text_y_pos = data_max_calc + 0.25 * data_range_calc
                else:
                    # Falls keine Daten vorhanden sind, verwende eine Position weiter oben
                    y_limits = ax.get_ylim()
                    y_range = y_limits[1] - y_limits[0]
                    text_y_pos = y_limits[0] + y_range * 0.75  # Höher positioniert
                
                ax.text(j+1, text_y_pos, 'keine\nDaten', ha='center', va='center', fontsize=8,
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='lightgray', 
                               edgecolor='gray', alpha=0.8))

    # Layout anpassen
    # fig.suptitle(f"Fehler nach Gebäudetyp und Altersklasse ({'Teilsaniert' if saniert else 'Unsaniert'})", fontsize=14, fontweight='bold', y=0.95)
    
    # Präzise Layout-Anpassung
    plt.subplots_adjust(
        top=0.90,       # Platz für Haupttitel
        bottom=0.15,    # Platz für X-Achsen Labels
        left=0.08,      # Linker Rand
        right=0.95,     # Rechter Rand
        hspace=0.4,     # Vertikaler Abstand zwischen Subplots
        wspace=0.25     # Horizontaler Abstand zwischen Subplots
    )
    
    # Speichern
    plots_dir = os.path.join(SRCPATH, 'districtgenerator', 'results', 'plots')
    os.makedirs(plots_dir, exist_ok=True)
    fname = f"boxplots_all_buildingtype_age_{'teilsaniert' if saniert else 'unsaniert'}_{scenario_name or 'plot'}.png"
    file_path = os.path.join(plots_dir, fname)
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    # plt.show()
    plt.close(fig)
    print(f"Kombinierte Boxplot-Grafik gespeichert: {fname}")

def plot_boxplots_gmh_mfh_by_age(
    combined_data,
    saniert=True,
    value_col='difference_heat_percent_QG',
    gebaeudetyp_col='building_type_simplified',
    baujahr_col='construction_year',
    sanierungs_col='renovation_state_simulated',
    scenario_name=None,
    SRCPATH="." # Annahme: SRCPATH wird benötigt, Standardwert auf "." gesetzt
):
    """
    Erstellt eine Grafik mit Subplots für die Gebäudetypen GMH und MFH, 
    die den Fehler für jede Altersklasse zeigen.
    Es wird nach saniert/unsaniert gefiltert. Zeigt immer alle 11 Altersklassen an.

    Parameters
    ----------
    combined_data : pd.DataFrame
        Die kombinierte DataFrame mit allen Daten.
    saniert : bool
        True = nur sanierte Gebäude, False = nur unsanierte.
    value_col : str
        Die Spalte mit dem Fehlerwert.
    gebaeudetyp_col : str
        Die Spalte mit dem Gebäudetyp.
    baujahr_col : str
        Die Spalte mit dem Baujahr (für Binning).
    sanierungs_col : str
        Die Spalte mit dem Sanierungszustand.
    scenario_name : str
        Optional für Dateinamen.
    SRCPATH : str
        Basispfad zum Speichern der Plots.
    """

    altersklassen_qg = [
        '1860 - 1918',
        '1919 - 1948',
        '1949 - 1957',
        '1958 - 1968',
        '1969 - 1978',
        '1979 - 1983',
        '1984 - 1994',
        '1995 - 2001',
        '2002 - 2009',
        '2010 - 2015',
        '2016 - 2023',
    ]
    
    bins = [1859, 1918, 1948, 1957, 1968, 1978, 1983, 1994, 2001, 2009, 2015, 2023]
    gemappte_altersklasse_col = "baujahr_mapped"

    df = combined_data.copy()
    df[gemappte_altersklasse_col] = pd.cut(df[baujahr_col],
                                          bins=bins,
                                          labels=altersklassen_qg,
                                          right=True,
                                          ordered=False)

    # *** MODIFIKATION: Nur GMH und MFH ***
    alle_gebaeudetypen = ['GMH', 'MFH']

    # Filter nach teilsaniert/unsaniert
    filter_value = 'teilsaniert' if saniert else 'unsaniert'
    df = df[df[sanierungs_col] == filter_value]
    df = df.dropna(subset=[gebaeudetyp_col, gemappte_altersklasse_col, value_col])
    df = df[np.isfinite(df[value_col])]

    print(f"Gefilterte Daten für '{filter_value}': {len(df)} Datenpunkte")
    print(f"Verfügbare Gebäudetypen in Daten: {sorted(df[gebaeudetyp_col].unique())}")
    print(f"Verfügbare Altersklassen in Daten: {sorted(df[gemappte_altersklasse_col].unique())}")

    fig, axes = plt.subplots(2, 1, figsize=(14, 10)) # Breite reduziert, Höhe erhöht
    axes = axes.flatten() # Stellt sicher, dass axes immer iterierbar ist (jetzt Array der Länge 2)

    # Für jeden der 2 Gebäudetypen einen Subplot erstellen
    for i, gebaeudetyp in enumerate(alle_gebaeudetypen):
        ax = axes[i]
        subset = df[df[gebaeudetyp_col] == gebaeudetyp]
        
        boxplot_data = []
        labels = []
        counts = []
        
        # Daten für jede der 11 Altersklassen sammeln
        for altersklasse in altersklassen_qg:
            vals = subset[subset[gemappte_altersklasse_col] == altersklasse][value_col].values
            if len(vals) > 0:
                boxplot_data.append(vals)
                labels.append(str(altersklasse))
                counts.append(len(vals))
            else:
                # Leere Liste für fehlende Altersklassen hinzufügen
                boxplot_data.append([])
                labels.append(str(altersklasse))
                counts.append(0)
        
        # Prüfen ob überhaupt Daten für diesen Gebäudetyp vorhanden sind
        total_count = sum(counts)
        has_data = any(len(data) > 0 for data in boxplot_data)
        
        if not has_data:
            # Keine Daten für diesen Gebäudetyp
            ax.text(0.5, 0.5, f'Keine Daten\nfür {gebaeudetyp}', 
                    ha='center', va='center', transform=ax.transAxes, fontsize=12)
            ax.set_title(f"{gebaeudetyp}\n(n=0)", 
                         fontsize=12, fontweight='bold', pad=15)
            # Setze Standard Y-Limits auch für leere Plots mit sichtbarem Null-Niveau
            ax.set_ylim(-15, 15)
        else:
            # Boxplot erstellen - nur für nicht-leere Daten
            valid_data = [data for data in boxplot_data if len(data) > 0]
            valid_labels = [labels[j] for j, data in enumerate(boxplot_data) if len(data) > 0]
            valid_positions = [j+1 for j, data in enumerate(boxplot_data) if len(data) > 0]
            
            if valid_data:
                bp = ax.boxplot(valid_data, positions=valid_positions, labels=valid_labels, 
                                patch_artist=True, medianprops=dict(color='red', linewidth=2), 
                                showmeans=True)
                
                # Boxen färben
                for patch in bp['boxes']:
                    patch.set_facecolor('lightcoral')
                    patch.set_alpha(0.7)
                
                # Y-Achsen-Bereich ZUERST berechnen und erweitern
                all_valid_data = np.concatenate(valid_data)
                data_min = np.min(all_valid_data)
                data_max = np.max(all_valid_data)
                data_range = data_max - data_min
                
                # Spezialbehandlung für den Fall, dass data_range = 0
                if data_range == 0:
                    fallback_range = max(10, abs(data_max) * 0.2)
                    data_min = data_max - fallback_range / 2
                    data_max = data_max + fallback_range / 2
                    data_range = fallback_range
                
                # Y-Achse ERWEITERN um sicherzustellen, dass Null immer sichtbar ist
                extended_min = data_min - 0.05 * data_range
                extended_max = data_max + 0.6 * data_range # MEHR Platz oben für Textboxen
                
                # Stelle sicher, dass Null immer sichtbar ist
                if extended_min > 0:
                    extended_min = min(extended_min, -5)
                if extended_max < 0:
                    extended_max = max(extended_max, 5)
                
                ax.set_ylim(extended_min, extended_max)
                
                # DANN Textbox-Position berechnen
                text_y = data_max + 0.25 * data_range
                
                # Statistiken als Textboxen
                for idx, (pos, vals) in enumerate(zip(valid_positions, valid_data)):
                    mean = np.mean(vals)
                    std = np.std(vals)
                    n = len(vals)
                    stats_text = f"n={n}\nμ={mean:.1f}%\nσ={std:.1f}%"
                    ax.text(pos, text_y, stats_text, ha='center', va='center', fontsize=8,
                            bbox=dict(boxstyle='round,pad=0.2', facecolor='lightyellow', 
                                      edgecolor='gray', alpha=0.9))
            
            # Titel mit Gesamtanzahl
            ax.set_title(f"{gebaeudetyp}\n(n={total_count})", 
                         fontsize=12, fontweight='bold', pad=15)
        
        # Immer alle Altersklassen auf X-Achse anzeigen
        ax.set_xticks(range(1, len(altersklassen_qg) + 1))
        ax.set_xticklabels(altersklassen_qg, rotation=0, fontsize=9)
        ax.set_xlim(0.5, len(altersklassen_qg) + 0.5)
        ax.set_xlabel('Altersklasse (Baujahr)', fontsize=10, labelpad=8)
        ax.set_ylabel('Relative Abweichung (%)', fontsize=10, labelpad=8)
        ax.axhline(y=0, color='gray', alpha=0.7, linewidth=1)
        ax.tick_params(axis='y', labelsize=9)
        
        # Markiere fehlende Altersklassen
        for j, (altersklasse, count) in enumerate(zip(altersklassen_qg, counts)):
            if count == 0:
                if has_data and len(valid_data) > 0:
                    all_valid_data = np.concatenate(valid_data)
                    data_min_calc = np.min(all_valid_data)
                    data_max_calc = np.max(all_valid_data)
                    data_range_calc = data_max_calc - data_min_calc
                    
                    if data_range_calc == 0:
                        fallback_range = max(10, abs(data_max_calc) * 0.2)
                        data_max_calc = data_max_calc + fallback_range / 2
                        data_range_calc = fallback_range
                    
                    text_y_pos = data_max_calc + 0.25 * data_range_calc
                else:
                    y_limits = ax.get_ylim()
                    y_range = y_limits[1] - y_limits[0]
                    text_y_pos = y_limits[0] + y_range * 0.75
                
                ax.text(j+1, text_y_pos, 'keine\nDaten', ha='center', va='center', fontsize=8,
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='lightgray', 
                                  edgecolor='gray', alpha=0.8))

    # Layout anpassen
    # (Optional) Haupttitel, falls gewünscht
    # fig.suptitle(f"Fehler GMH/MFH nach Altersklasse ({'Teilsaniert' if saniert else 'Unsaniert'})", fontsize=14, fontweight='bold', y=0.95)
    
    # Präzise Layout-Anpassung
    plt.subplots_adjust(
        top=0.92,       # Etwas mehr Platz oben für Titel
        bottom=0.10,    # Etwas weniger Platz unten
        left=0.12,      # Etwas mehr Platz links für Y-Label
        right=0.95,     # Rechter Rand ok
        hspace=0.5,     # Vertikaler Abstand zwischen Subplots
        wspace=0.25     # (Bei 1 Spalte irrelevant, schadet aber nicht)
    )
    
    # Speichern
    # Annahme: SRCPATH ist eine Variable, die den Basispfad enthält
    plots_dir = os.path.join(SRCPATH, 'districtgenerator', 'results', 'plots')
    os.makedirs(plots_dir, exist_ok=True)
    
    # *** MODIFIKATION: Dateiname angepasst ***
    fname = f"boxplots_gmh_mfh_age_{'teilsaniert' if saniert else 'unsaniert'}_{scenario_name or 'plot'}.png"
    
    file_path = os.path.join(plots_dir, fname)
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    # plt.show()
    plt.close(fig)
    print(f"GMH/MFH Boxplot-Grafik gespeichert: {fname}")


if __name__ == '__main__':
    scenario_name = '251028_export'
    # example10_comparison_heat_demands(scenario_name=scenario_name)
    # Analyse the data
    combined_data= analyse_data(scenario_name=scenario_name, building_model="5R1C") # Alternative: "7R2C"
