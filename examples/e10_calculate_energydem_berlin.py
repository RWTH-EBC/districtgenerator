# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import pandas as pd
import os
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import warnings

srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plots_dir = os.path.join(srcPath, 'districtgenerator', 'results', 'plots')
os.makedirs(plots_dir, exist_ok=True)

def example10_comparison_heat_demands():
    warnings.filterwarnings("ignore", category=FutureWarning)

    scenario_name = "251028_export"
    heat_demands_QG = pd.DataFrame()

    # Read in significant data from the xlsx file of the wkb (heated area, number of floors, heat demand kWh/a)
    WKB_data = read_wkb_data(scenario_name= scenario_name) #!-> pd.DataFrame

    n_runs = 1
    for run in range(n_runs): 
        print(f"\n--- Run {run+1}/{n_runs} ---")
    # Initialize District
        data = Datahandler(scenario_name = scenario_name, heat_map_berlin = True)
        data.initializeBuildings()
        data.generateEnvironment()
        data.generateBuildings()
    
        if run == -1:
            data.generateDemands(calcUserProfiles=False, saveUserProfiles=False)
        else:
            data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)
    
        # Calculate for each building the total heat demand (kWh/a). Get also floor area, number floors for comparison, Repeat this step 10 Times to get 10 different profiles.
        heat_demands_QG = get_total_heat_demand(data=data, run_number= run, old_df = heat_demands_QG) #!-> pd.DataFrame

    print(heat_demands_QG.head())  # Display the first few rows of the DataFrame

    # put all the data into a combined dataframe for analysis (heatmap and other plots or etc.)
    create_combined_df(scenario_name=scenario_name, heat_demands_QG=heat_demands_QG, WKB_data=WKB_data)
    return data


def get_total_heat_demand(data, run_number, old_df) -> pd.DataFrame:
    """
    Calculate the total heat demand for each buildings in the district.
    If old_df is provided, add new columns to existing DataFrame.

    Parameters
    ----------
    data : Datahandler
        The Datahandler instance containing the district data.
    run_number : int
        The run number for column naming.
    old_df : pd.DataFrame
        Existing DataFrame to append new columns to.

    Returns
    -------
    pd.DataFrame
        DataFrame with building_id as index and heat demands as columns.
    """
    relevant_demands = ["heat", "dhw"]  # Erweitert um weitere demands
    
    # Liste für die Daten
    building_data = []

    for index, building in enumerate(data.district):
        # Dictionary für diese Zeile mit allen relevanten Daten
        row_data = {
            "building_id": index,
            "building_type": building["buildingFeatures"]["building"],
            "area_m2_QG": building["buildingFeatures"]["area"]
        }
        
        teaser_building = data.prj.buildings[index]
        row_data[f"run_{run_number}_floors_QG"] = teaser_building.number_of_floors

        # Heat demands berechnen
        total_demand = 0
        for demand in relevant_demands:
            try:
                values = getattr(building["user"], demand, None)
                if values is not None:
                    # For each demand a separate column
                    single_demand = sum(values) / 1000  # Convert Wh to kWh/a
                    row_data[f"run_{run_number}_total_{demand}_single_kWh_a"] = single_demand
                    total_demand += single_demand
                else:
                    row_data[f"run_{run_number}_total_{demand}_single_kWh_a"] = 0.0
            except AttributeError:
                row_data[f"run_{run_number}_total_{demand}_single_kWh_a"] = 0.0

        row_data[f"run_{run_number}_total_heat_kWh_a"] = total_demand
        building_data.append(row_data)
    
    # DataFrame erstellen
    current_df = pd.DataFrame(building_data)
    current_df.set_index("building_id", inplace=True)
    
    # Falls old_df leer ist oder nicht existiert
    if old_df is None or old_df.empty:
        return current_df
    
    # Merge mit existing DataFrame (nur die neuen Demand-Spalten)
    demand_columns = [col for col in current_df.columns if f"run_{run_number}" in col]
    combined_df = old_df.join(current_df[demand_columns], how='outer')
    
    return combined_df


def read_wkb_data(scenario_name) -> pd.DataFrame:
    """
    Read the WKB data from an CSV data file and filter for specific building usage types.
    Now reads ALL columns from the CSV file for comprehensive analysis.

    Parameters
    ----------
    scenario_name : str
        The name of the scenario to read data for.
    usage_types : list or None
        List of usage types to include. Default: ['Wohnhaus']
        If None, no filtering by usage type is applied.
    
    Returns
    -------
    pd.DataFrame
        DataFrame with all available columns from the Excel file.
    """
    
    filename = f"{scenario_name}_wkb.csv"
    file_path = os.path.join(srcPath, 'districtgenerator', 'data', 'scenarios', filename)
    
    try:
        print(f"Reading CSV file: {file_path}")
        # Read ALL columns from the CSV file (no usecols parameter)
        wkb_df = pd.read_csv(file_path, sep=";")

        print(f"Found {len(wkb_df.columns)} columns in CSV file")
        
        # Reset index to use row numbers as building_id
        wkb_df.reset_index(drop=True, inplace=True)
        wkb_df.index.name = 'building_id'
        
        print(f"\nFinal DataFrame info:")
        print(f"- Shape: {wkb_df.shape}")
        print(f"- Columns: {list(wkb_df.columns)}")
        print(f"- Index name: {wkb_df.index.name}")
        
        # Show first few rows
        print(f"\nFirst 5 rows:")
        print(wkb_df.head())
        
        return wkb_df
    except FileNotFoundError:
        print(f"Error: File {file_path} not found!")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return pd.DataFrame()


def create_combined_df(scenario_name, heat_demands_QG, WKB_data) -> pd.DataFrame:
    """
    Combine heat demands and WKB data for analysis. And save it to a CSV file.
    
    Parameters
    ----------
    heat_demands_QG : pd.DataFrame
        DataFrame containing heat demands.
    WKB_data : pd.DataFrame
        DataFrame containing WKB data.

    Returns
    -------
    pd.DataFrame
        Combined DataFrame for analysis.
    """
    
    # Combine the two DataFrames on the index (building_id)
    combined_data = heat_demands_QG.join(WKB_data, how='outer')
    
    # Display the first few rows of the combined DataFrame
    print(combined_data.head())

    # Save the combined DataFrame to a CSV file
    file_path = os.path.join(srcPath, 'districtgenerator', 'results', f"processed_data_{scenario_name}.csv")

    combined_data.to_csv(file_path, encoding='utf-8')

    return combined_data


def analyse_data(scenario_name, combined_data= None):
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
    if combined_data is None:
        # If no combined data is provided, read it from the CSV file
        file_path = os.path.join(srcPath, 'districtgenerator', 'results', f"processed_data_{scenario_name}.csv")
        combined_data = pd.read_csv(file_path, encoding='utf-8', index_col=0)

    print(combined_data.columns)  # Display the first few rows of the DataFrame
    # Find all heat demand columns from QG simulation runs
    heat_demand_columns = [col for col in combined_data.columns if 'total_heat_single_kWh_a' in col and 'run_' in col]

    # First add columns for mean simulated heat demand and std
    combined_data['mean_total_heat_kWh_a_QG'] = combined_data[heat_demand_columns].mean(axis=1)
    if len (heat_demand_columns) > 1:
        combined_data['std_total_heat_kWh_a_QG'] = combined_data[heat_demand_columns].std(axis=1)
        combined_data['cv_total_heat_QG'] = combined_data['std_total_heat_kWh_a_QG'] / combined_data['mean_total_heat_kWh_a_QG']
    
    # Calculate differences between WKB and QG data
    combined_data['difference_heat_kWh_a_QG'] = combined_data['mean_total_heat_kWh_a_QG'] - combined_data['waermebedarf_sim_kw']
    combined_data['difference_heat_percent_QG'] = (combined_data['difference_heat_kWh_a_QG'] / combined_data['waermebedarf_sim_kw']) * 100

    # Add here specific analysis and visualizations
    categorical_columns = ['gebaeudetype_einfach', 'baujahr_spectrum', 'iwu_class', 'sanierungszust_sim']
    # create_box_plots_category(combined_data=combined_data, scenario_name=scenario_name, columns=categorical_columns)
    # create_simulation_variance_boxplots(combined_data=combined_data, scenario_name=scenario_name, columns=categorical_columns)
    # create_floors_deviation_boxplots(combined_data=combined_data, scenario_name=scenario_name)
    # create_boxplots_difference_bedarf_verbrauch_category(combined_data, categorical_columns)
    # plot_faceted_crosstab_heat_error_stats(combined_data, category1='gebaeudetype_einfach', category2='baujahr_spectrum', facet_category='sanierungszust_sim')
    # plot_faceted_crosstab_bedarf_verbrauch_heatmap(combined_data, category1='gebaeudetype_einfach', category2='baujahr_spectrum', facet_category='sanierungszust_sim')
    plot_boxplots_by_buildingtype_and_age(combined_data, saniert=False, scenario_name="WKB_export")
    plot_boxplots_by_buildingtype_and_age(combined_data, saniert=True, scenario_name="WKB_export")

    return combined_data


def create_box_plots_category(combined_data, scenario_name, columns):
    """
    Create boxplots for relative error across different categorical columns in one figure.
    
    Parameters
    ----------
    combined_data : pd.DataFrame
        The combined DataFrame containing the analysis data.
    scenario_name : str
        The name of the scenario for file naming.
    columns : list
        List of categorical columns to create boxplots for.
    """
    
    # Ensure the target column exists
    if 'difference_heat_percent_QG' not in combined_data.columns:
        print("Error: 'difference_heat_percent_QG' column not found in data!")
        return
    
    # Filter out infinite and NaN values
    clean_data = combined_data.dropna(subset=['difference_heat_percent_QG'])
    clean_data = clean_data[np.isfinite(clean_data['difference_heat_percent_QG'])]
    
    # Filter out columns that don't exist in data
    available_columns = [col for col in columns if col in clean_data.columns]
    if not available_columns:
        print("Warning: None of the specified columns found in data!")
        return
    
    print(f"Creating combined boxplot figure for {len(available_columns)} categorical variables...")
    
    # Calculate subplot layout
    n_plots = len(available_columns)
    n_cols = min(2, n_plots)  # Maximum 2 columns
    n_rows = (n_plots + n_cols - 1) // n_cols  # Calculate needed rows
    
    # Create figure with subplots
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 12))
    
    # Handle case where we have only one subplot
    if n_plots == 1:
        axes = [axes]
    elif n_rows == 1:
        axes = axes.flatten() if n_plots > 1 else [axes]
    else:
        axes = axes.flatten()
    
    # Create boxplots for each specified column
    for i, column in enumerate(available_columns):
        ax = axes[i]
        print(f"Creating boxplot for: {column}")
        create_single_boxplot_in_ax(combined_data=clean_data, column_name=column, ax=ax)

    # Hide empty subplots if any
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    
    # Adjust layout
    fig.suptitle(f"Abweichung der ermittelten Bedarfe (QG) mit dem Wärmeverbauch", fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    # Save the combined plot
    os.makedirs(plots_dir, exist_ok=True)
    
    filename = f"boxplots_combined_relative_error_{scenario_name}.png"
    file_path = os.path.join(plots_dir, filename)
    
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    print(f"Combined boxplot saved to: {file_path}")
    
    # Show the plot
    # plt.show()
    
    plt.close(fig)  # Close figure to free memory
    print("Combined boxplot figure created successfully!")
    
    return None


def create_single_boxplot_in_ax(combined_data, column_name, ax):
    """
    Create a single boxplot in a given axis showing relative error by categories.
    """
    
    # Get categories
    categories = combined_data[column_name].dropna().unique()
    categories = sorted(categories)
    
    if len(categories) > 1:
        # Prepare data for boxplot
        category_data = []
        category_labels = []
        category_stats = []
        
        # Add overall data
        overall_data = combined_data['difference_heat_percent_QG'].values
        category_data.append(overall_data)
        
        overall_mean = np.mean(overall_data)
        overall_std = np.std(overall_data)
        category_labels.append('Overall')
        category_stats.append({'mean': overall_mean, 'std': overall_std, 'count': len(combined_data)})
        
        # Add category-specific data
        for category in categories:
            category_subset = combined_data[combined_data[column_name] == category]['difference_heat_percent_QG']
            if len(category_subset) > 0:
                cat_data = category_subset.values
                category_data.append(cat_data)
                
                cat_mean = np.mean(cat_data)
                cat_std = np.std(cat_data)
                cat_count = len(cat_data)
                
                category_labels.append(str(category))
                category_stats.append({'mean': cat_mean, 'std': cat_std, 'count': cat_count})
        
        # Create boxplot
        bp = ax.boxplot(category_data, 
                       labels=category_labels,
                       patch_artist=True,
                       medianprops=dict(color='red', linewidth=2), showmeans=True)
        if column_name != 'iwu_class':
            # Color boxes
            colors = ['lightblue'] + [plt.cm.Set3(i/len(categories)) for i in range(len(categories))]
            for i, (patch, color) in enumerate(zip(bp['boxes'], colors)):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)
                if i == 0:
                    patch.set_edgecolor('black')
                    patch.set_linewidth(2)
            
            
            # Calculate position for text boxes (all at same height)
            all_data_flat = np.concatenate(category_data)
            data_min = np.min(all_data_flat)
            data_max = np.max(all_data_flat)
            data_range = data_max - data_min
            
            # Set consistent height for ALL text boxes
            text_y = data_max + 0.15 * data_range  # Same height for all boxes
            
            # Add statistics as floating text boxes (all at same height)
            for i, stats in enumerate(category_stats):
                x_pos = i + 1
                
                stats_text = f"n={stats['count']}\nμ={stats['mean']:.1f}%\nσ={stats['std']:.1f}%"
                
                # Add floating text box at consistent height
                ax.text(x_pos, text_y, stats_text, 
                    horizontalalignment='center',
                    verticalalignment='center',
                    fontsize=8,
                    bbox=dict(boxstyle='round,pad=0.4', 
                                facecolor='lightyellow', 
                                edgecolor='darkgray',
                                linewidth=1,
                                alpha=0.95))
        
            # Adjust y-axis limits to accommodate text boxes
            ax.set_ylim(data_min - 0.05 * data_range, 
                    data_max + 0.35 * data_range)  # Slightly less space since no staggering
        
        ax.set_title(f'{column_name}', fontsize=12, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
        ax.set_ylabel('Relative Error (%)', fontsize=10)
        ax.tick_params(axis='x', rotation=0, labelsize=9)
        ax.grid(True, alpha=0.3)
        
       
    else:
        # Single category case (similar adjustments)
        overall_data = combined_data['difference_heat_percent_QG'].values
        overall_mean = np.mean(overall_data)
        overall_std = np.std(overall_data)
        overall_count = len(combined_data)
        
        bp = ax.boxplot([overall_data], 
                       labels=['Overall'],
                       patch_artist=True,
                       boxprops=dict(facecolor='lightblue', alpha=0.7),
                       medianprops=dict(color='red', linewidth=2), showmeans=True)
        
        ax.scatter(1, overall_mean, marker='D', color='blue', s=50, zorder=5)
        
        # Position text box
        data_min = np.min(overall_data)
        data_max = np.max(overall_data)
        data_range = data_max - data_min
        text_y = data_max + 0.15 * data_range  # Same calculation as multi-category
        
        stats_text = f"n={overall_count}\nμ={overall_mean:.1f}%\nσ={overall_std:.1f}%"
        
        ax.text(1, text_y, stats_text, 
               horizontalalignment='center',
               verticalalignment='center',
               fontsize=9,
               bbox=dict(boxstyle='round,pad=0.4', 
                        facecolor='lightyellow', 
                        edgecolor='darkgray',
                        alpha=0.95))
        
        ax.set_ylim(data_min - 0.05 * data_range, 
                   data_max + 0.35 * data_range)
        
        ax.set_title(f'{column_name}: {categories[0]}', fontsize=12, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
        ax.set_ylabel('Relative Error (%)', fontsize=10)
        ax.grid(True, alpha=0.3)


def create_simulation_variance_boxplots(combined_data, scenario_name, columns):
    """
    Create boxplots showing the percentage deviation of individual simulation results 
    from the mean of all simulations for each building, categorized by specified columns.
    
    Parameters
    ----------
    combined_data : pd.DataFrame
        The combined DataFrame containing the analysis data.
    scenario_name : str
        The name of the scenario for file naming.
    columns : list
        List of categorical columns to create boxplots for.
    """
    
    # Find all heat demand columns from QG simulation runs
    heat_demand_columns = [col for col in combined_data.columns if 'total_heat_kWh_a' in col and 'run_' in col]
    
    if len(heat_demand_columns) < 2:
        print("Error: Need at least 2 simulation runs to calculate variance!")
        return
    
    print(f"Found {len(heat_demand_columns)} simulation runs for variance analysis")
    
    # Calculate percentage deviations for each run from the mean
    deviation_data = []
    
    for index, row in combined_data.iterrows():
        # Get simulation values for this building
        sim_values = [row[col] for col in heat_demand_columns if not pd.isna(row[col])]
        
        if len(sim_values) >= 2:
            mean_value = np.mean(sim_values)
            
            # Calculate percentage deviation for each simulation
            for i, sim_value in enumerate(sim_values):
                if mean_value != 0:  # Avoid division by zero
                    percentage_dev = ((sim_value - mean_value) / mean_value) * 100
                    
                    # Create row for this deviation
                    dev_row = {
                        'building_id': index,
                        'simulation_run': i,
                        'percentage_deviation': percentage_dev,
                        'absolute_deviation': abs(percentage_dev)
                    }
                    
                    # Add categorical columns
                    for col in columns:
                        if col in combined_data.columns:
                            dev_row[col] = row[col]
                    
                    deviation_data.append(dev_row)
    
    # Create DataFrame with deviation data
    deviation_df = pd.DataFrame(deviation_data)
    
    if deviation_df.empty:
        print("Error: No valid deviation data could be calculated!")
        return
    
    print(f"Calculated deviations for {len(deviation_df)} data points")
    
    # Filter out infinite and NaN values
    clean_data = deviation_df.dropna(subset=['percentage_deviation'])
    clean_data = clean_data[np.isfinite(clean_data['percentage_deviation'])]
    
    # Filter out columns that don't exist in data
    available_columns = [col for col in columns if col in clean_data.columns]
    if not available_columns:
        print("Warning: None of the specified columns found in data!")
        return
    
    print(f"Creating simulation variance boxplot figure for {len(available_columns)} categorical variables...")
    
    # Calculate subplot layout
    n_plots = len(available_columns)
    n_cols = min(2, n_plots)
    n_rows = (n_plots + n_cols - 1) // n_cols
    
    # Create figure with subplots
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 12))
    
    # Handle case where we have only one subplot
    if n_plots == 1:
        axes = [axes]
    elif n_rows == 1:
        axes = axes.flatten() if n_plots > 1 else [axes]
    else:
        axes = axes.flatten()
    
    # Create boxplots for each specified column
    for i, column in enumerate(available_columns):
        ax = axes[i]
        print(f"Creating variance boxplot for: {column}")
        create_single_variance_boxplot_in_ax(clean_data, column, ax)
    
    # Hide empty subplots if any
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    
    # Adjust layout
    fig.suptitle(f"Streung der durch den QG simulierten Bedarfe", 
                fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    # Save the combined plot
    os.makedirs(plots_dir, exist_ok=True)
    
    filename = f"boxplots_simulation_variance_{scenario_name}.png"
    file_path = os.path.join(plots_dir, filename)
    
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    print(f"Simulation variance boxplot saved to: {file_path}")
    
    # Show the plot
    # plt.show()
    
    plt.close(fig)
    print("Simulation variance boxplot figure created successfully!")
    
    return deviation_df


def create_single_variance_boxplot_in_ax(deviation_data, column_name, ax):
    """
    Create a single boxplot showing percentage deviation from simulation mean by categories.
    
    Parameters
    ----------
    deviation_data : pd.DataFrame
        DataFrame containing deviation data for each simulation.
    column_name : str
        The categorical column to analyze.
    ax : matplotlib.axes.Axes
        The axis to plot on.
    """
    
    # Get categories
    categories = deviation_data[column_name].dropna().unique()
    categories = sorted(categories)
    
    if len(categories) > 1:
        # Prepare data for boxplot by categories
        category_data = []
        category_labels = []
        category_stats = []
        
        # Add overall data as first box
        overall_data = deviation_data['percentage_deviation'].values
        category_data.append(overall_data)
        
        overall_mean = np.mean(np.abs(overall_data))  # Mean absolute deviation
        overall_std = np.std(overall_data)
        category_labels.append('Overall')
        category_stats.append({
            'mean_abs': overall_mean, 
            'std': overall_std, 
            'count': len(overall_data)
        })
        
        # Add category-specific data
        for category in categories:
            category_subset = deviation_data[deviation_data[column_name] == category]['percentage_deviation']
            if len(category_subset) > 0:
                cat_data = category_subset.values
                category_data.append(cat_data)
                
                cat_mean_abs = np.mean(np.abs(cat_data))  # Mean absolute deviation
                cat_std = np.std(cat_data)
                cat_count = len(cat_data)
                
                category_labels.append(str(category))
                category_stats.append({
                    'mean_abs': cat_mean_abs, 
                    'std': cat_std, 
                    'count': cat_count
                })
        
        # Create boxplot
        bp = ax.boxplot(category_data, 
                       labels=category_labels,
                       patch_artist=True,
                       medianprops=dict(color='red', linewidth=2), showmeans=True)
        
        # Color each box differently
        colors = ['lightcoral'] + [plt.cm.Set2(i/len(categories)) for i in range(len(categories))]
        for i, (patch, color) in enumerate(zip(bp['boxes'], colors)):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
            if i == 0:  # Overall box
                patch.set_edgecolor('black')
                patch.set_linewidth(2)
        
        # Add mean markers
        for i, stats in enumerate(category_stats):
            x_pos = i + 1
        
        
        # Calculate position for text boxes
        all_data_flat = np.concatenate(category_data)
        data_min = np.min(all_data_flat)
        data_max = np.max(all_data_flat)
        data_range = data_max - data_min
        if column_name != 'iwu_class':
            # Set consistent height for ALL text boxes
            text_y = data_max + 0.15 * data_range
            
            # Add statistics as floating text boxes
            for i, stats in enumerate(category_stats):
                x_pos = i + 1
                
                stats_text = f"n={stats['count']}\n|μ|={stats['mean_abs']:.1f}%\nσ={stats['std']:.1f}%"
                
                ax.text(x_pos, text_y, stats_text, 
                    horizontalalignment='center',
                    verticalalignment='center',
                    fontsize=8,
                    bbox=dict(boxstyle='round,pad=0.4', 
                                facecolor='lightgreen', 
                                edgecolor='darkgreen',
                                linewidth=1,
                                alpha=0.95))
            
            # Adjust y-axis limits
            ax.set_ylim(data_min - 0.05 * data_range, 
                    data_max + 0.35 * data_range)
        
        ax.set_title(f'{column_name}', fontsize=12, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
        ax.set_ylabel('Deviation from Mean (%)', fontsize=10)
        ax.tick_params(axis='x', rotation=0, labelsize=9)
        ax.grid(True, alpha=0.3)
        
        # Add horizontal line at y=0 for reference
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
        
            
    else:
        # Single category case
        overall_data = deviation_data['percentage_deviation'].values
        overall_mean_abs = np.mean(np.abs(overall_data))
        overall_std = np.std(overall_data)
        overall_count = len(overall_data)
        
        bp = ax.boxplot([overall_data], 
                       labels=['Overall'],
                       patch_artist=True,
                       boxprops=dict(facecolor='lightcoral', alpha=0.7),
                       medianprops=dict(color='red', linewidth=2), showmeans=True)
        
        # Position text box
        data_min = np.min(overall_data)
        data_max = np.max(overall_data)
        data_range = data_max - data_min
        text_y = data_max + 0.15 * data_range
        
        stats_text = f"n={overall_count}\n|μ|={overall_mean_abs:.1f}%\nσ={overall_std:.1f}%"
        
        ax.text(1, text_y, stats_text, 
               horizontalalignment='center',
               verticalalignment='center',
               fontsize=9,
               bbox=dict(boxstyle='round,pad=0.4', 
                        facecolor='lightgreen', 
                        edgecolor='darkgreen',
                        alpha=0.95))
        
        ax.set_ylim(data_min - 0.05 * data_range, 
                   data_max + 0.35 * data_range)
        
        ax.set_title(f'{column_name}: {categories[0]}', fontsize=12, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
        ax.set_ylabel('Deviation from Mean (%)', fontsize=10)
        ax.grid(True, alpha=0.3)


def create_floors_deviation_boxplots(combined_data, scenario_name):
    """
    Create boxplots showing relative heat error by floor deviation categories,
    with separate subplots for each number of floors in the original dataset.
    
    Parameters
    ----------
    combined_data : pd.DataFrame
        The combined DataFrame containing the analysis data.
    scenario_name : str
        The name of the scenario for file naming.
    """
    
    # Check if required columns exist
    required_columns = ['anz_etagen', 'difference_heat_percent_QG']
    floors_qg_columns = [col for col in combined_data.columns if 'floors_QG' in col]
    
    if not floors_qg_columns:
        print("Error: No simulated floors columns found (run_*_floors_QG)!")
        return
    
    missing_cols = [col for col in required_columns if col not in combined_data.columns]
    if missing_cols:
        print(f"Error: Required columns not found: {missing_cols}")
        return
    
    print(f"Found {len(floors_qg_columns)} simulated floors columns: {floors_qg_columns}")
    
    # Filter out NaN values
    clean_data = combined_data.dropna(subset=['anz_etagen', 'difference_heat_percent_QG'])
    clean_data = clean_data[np.isfinite(clean_data['difference_heat_percent_QG'])]
    
    # Get unique floor numbers from original data
    unique_floors = sorted(clean_data['anz_etagen'].dropna().unique())
    print(f"Unique floor numbers in original data: {unique_floors}")
    
    if len(unique_floors) == 0:
        print("Error: No valid floor data found!")
        return
    
    # Calculate subplot layout
    n_plots = len(unique_floors)
    n_cols = min(3, n_plots)  # Maximum 3 columns
    n_rows = (n_plots + n_cols - 1) // n_cols
    
    # Create figure with subplots
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 12))
    
    # Handle case where we have only one subplot
    if n_plots == 1:
        axes = [axes]
    elif n_rows == 1:
        axes = axes.flatten() if n_plots > 1 else [axes]
    else:
        axes = axes.flatten()
    
    # Process each floor number
    for i, original_floor_count in enumerate(unique_floors):
        ax = axes[i]
        print(f"Creating boxplot for buildings with {original_floor_count} floors...")
        
        # Filter data for this floor count
        floor_subset = clean_data[clean_data['anz_etagen'] == original_floor_count]
        
        if len(floor_subset) == 0:
            ax.text(0.5, 0.5, f'No data\nfor {original_floor_count} floors', 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f'{original_floor_count} Floors (n=0)', fontsize=12, fontweight='bold')
            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
            continue
        
        create_single_floor_error_by_deviation_boxplot(floor_subset, original_floor_count, floors_qg_columns, ax)
    
    # Hide empty subplots if any
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    
    # Adjust layout
    fig.suptitle(f"Wärmebedarfs Abweichung abhängig von der Simulierten Etagenzahl", 
                fontsize=16, fontweight='bold')
    
    # Better spacing
    plt.subplots_adjust(
        top=0.92,       # More space for main title
        bottom=0.1,     # Space for x-labels
        left=0.08,      # Left margin
        right=0.95,     # Right margin
        hspace=0.4,     # Vertical spacing
        wspace=0.3      # Horizontal spacing
    )
    
    # Save the combined plot
    os.makedirs(plots_dir, exist_ok=True)
    
    filename = f"boxplots_heat_error_by_floor_deviation_{scenario_name}.png"
    file_path = os.path.join(plots_dir, filename)
    
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    print(f"Heat error by floor deviation boxplot saved to: {file_path}")
    
    # Show the plot
    # plt.show()
    
    plt.close(fig)
    print("Heat error by floor deviation boxplot figure created successfully!")
    
    return None


def create_single_floor_error_by_deviation_boxplot(floor_subset, original_floors, floors_qg_columns, ax):
    """
    Create a single boxplot showing heat demand error grouped by floor deviation categories.
    
    Parameters
    ----------
    floor_subset : pd.DataFrame
        Subset of data for buildings with specific floor count.
    original_floors : int
        The original number of floors from WKB data.
    floors_qg_columns : list
        List of columns containing simulated floor counts.
    ax : matplotlib.axes.Axes
        The axis to plot on.
    """
    
    # Collect data for all simulation runs
    all_error_data = []
    
    # Process each simulation run
    for col in floors_qg_columns:
        # Get buildings where both simulated floors and heat error are available
        valid_data = floor_subset.dropna(subset=[col, 'difference_heat_percent_QG'])
        
        if len(valid_data) == 0:
            continue
        
        # Calculate floor deviations for this run
        floor_deviations = valid_data[col] - original_floors
        heat_errors = valid_data['difference_heat_percent_QG']
        
        # Add to collection
        for deviation, error in zip(floor_deviations, heat_errors):
            all_error_data.append({
                'floor_deviation': int(deviation),
                'heat_error': error
            })
    
    if not all_error_data:
        ax.text(0.5, 0.5, f'No valid data\nfor {original_floors} floors', 
               ha='center', va='center', transform=ax.transAxes)
        ax.set_title(f'{original_floors} Floors (n=0)', fontsize=12, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
        return
    
    # Convert to DataFrame for easier processing
    error_df = pd.DataFrame(all_error_data)
    
    # Get unique deviations and sort them
    unique_deviations = sorted(error_df['floor_deviation'].unique())
    print(f"  Floor deviations found: {unique_deviations}")
    
    if len(unique_deviations) == 0:
        ax.text(0.5, 0.5, f'No deviation data\nfor {original_floors} floors', 
               ha='center', va='center', transform=ax.transAxes)
        ax.set_title(f'{original_floors} Floors (n=0)', fontsize=12, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
        return
    
    # Prepare data for boxplot
    boxplot_data = []
    boxplot_labels = []
    category_stats = []
    
    for deviation in unique_deviations:
        # Get heat errors for this deviation
        deviation_errors = error_df[error_df['floor_deviation'] == deviation]['heat_error']
        
        if len(deviation_errors) > 0:
            boxplot_data.append(deviation_errors.values)
            boxplot_labels.append(f'{deviation:+d}')  # Format: +1, -1, +0
            
            # Calculate statistics
            mean_error = np.mean(deviation_errors)
            std_error = np.std(deviation_errors)
            count = len(deviation_errors)
            
            category_stats.append({
                'deviation': deviation,
                'mean': mean_error,
                'std': std_error,
                'count': count
            })
    
    if not boxplot_data:
        ax.text(0.5, 0.5, f'No boxplot data\nfor {original_floors} floors', 
               ha='center', va='center', transform=ax.transAxes)
        ax.set_title(f'{original_floors} Floors (n=0)', fontsize=12, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
        return
    
    # Create boxplot
    bp = ax.boxplot(boxplot_data, 
                   labels=boxplot_labels,
                   patch_artist=True,
                   medianprops=dict(color='red', linewidth=2),
                   showmeans=True)
    
    # Color boxes based on deviation (red for negative, green for zero, blue for positive)
    
    for i, (patch, stats) in enumerate(zip(bp['boxes'], category_stats)):
        deviation = stats['deviation']
        if deviation < 0:
            color = 'lightcoral'  # Red for underestimation
        elif deviation == 0:
            color = 'lightgreen'  # Green for perfect match
        else:
            color = 'lightblue'   # Blue for overestimation
        
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
        
        # Highlight perfect match (deviation = 0)
        if deviation == 0:
            patch.set_edgecolor('darkgreen')
            patch.set_linewidth(3)
    
    # Calculate position for text boxes
    if boxplot_data:
        all_data_flat = np.concatenate(boxplot_data)
        data_min = np.min(all_data_flat)
        data_max = np.max(all_data_flat)
        data_range = data_max - data_min
        
        # Spezialbehandlung für den Fall, dass data_range = 0 (nur ein Datenpunkt oder alle Werte gleich)
        if data_range == 0:
            # Verwende einen festen Bereich um den Wert
            fallback_range = max(10, abs(data_max) * 0.2)  # Mindestens 10 oder 20% des Werts
            data_min = data_max - fallback_range / 2
            data_max = data_max + fallback_range / 2
            data_range = fallback_range
        
        # Position text boxes
        text_y = data_max + 0.15 * data_range
        
        # Add statistics as floating text boxes
        for i, stats in enumerate(category_stats):
            x_pos = i + 1
            
            stats_text = f"n={stats['count']}\nμ={stats['mean']:.1f}%\nσ={stats['std']:.1f}%"
            
            # Color text box based on deviation
            if stats['deviation'] < 0:
                box_color = 'mistyrose'
            elif stats['deviation'] == 0:
                box_color = 'honeydew'
            else:
                box_color = 'lightcyan'
            
            ax.text(x_pos, text_y, stats_text, 
                   horizontalalignment='center',
                   verticalalignment='center',
                   fontsize=8,
                   bbox=dict(boxstyle='round,pad=0.3', 
                            facecolor=box_color, 
                            edgecolor='gray',
                            linewidth=1,
                            alpha=0.9))
        
        # Adjust y-axis limits
        ax.set_ylim(data_min - 0.1 * data_range, 
                   data_max + 0.4 * data_range)
    
    # Add horizontal line at y=0 (no heat error)
    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
    
    # Formatting
    total_buildings = len(floor_subset)
    total_data_points = sum(stats['count'] for stats in category_stats)
    
    ax.set_title(f'{original_floors} Floors\n(n={total_buildings} buildings, {total_data_points} data points)', 
                fontsize=12, fontweight='bold')
    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
    ax.set_xlabel('Floor Deviation (Simulated - WKB)', fontsize=10)
    ax.set_ylabel('Heat Demand Error (%)', fontsize=10)
    ax.tick_params(axis='x', labelsize=9)
    ax.tick_params(axis='y', labelsize=9)
    ax.grid(True, alpha=0.3)
    
    # Print summary statistics
    print(f"    {original_floors} floors: {len(unique_deviations)} deviation categories, {total_data_points} total data points")
    for stats in category_stats:
        print(f"      Deviation {stats['deviation']:+d}: n={stats['count']}, μ={stats['mean']:.1f}%, σ={stats['std']:.1f}%")
    
    return None


def create_boxplots_difference_bedarf_verbrauch_category(combined_data, categories, scenario_name=None):
    """
    Create paired boxplots for the relative deviation between simulated heat demand and actual consumption
    (blue), and for difference_heat_percent_QG (green), for all specified categorical columns in one figure.

    Parameters
    ----------
    combined_data : pd.DataFrame
        The combined DataFrame containing the analysis data.
    categories : list
        List of categorical columns to group by.
    scenario_name : str or None
        Optional scenario name for file naming.
    """
    # Check required columns
    if 'waermebedarf_sim_kw' not in combined_data.columns or 'waermeverbrauch_kw/a' not in combined_data.columns:
        print("Error: Required columns 'waermebedarf_sim_kw' or 'waermeverbrauch_kw/a' not found!")
        return
    if 'difference_heat_percent_QG' not in combined_data.columns:
        print("Error: Required column 'difference_heat_percent_QG' not found!")
        return

    # Calculate relative deviation
    combined_data['relative_deviation_bedarf_verbrauch'] = (
        (combined_data['waermebedarf_sim_kw'] - combined_data['waermeverbrauch_kw/a']) / combined_data['waermeverbrauch_kw/a']
    ) * 100

    # Filter out NaN and infinite values
    clean_data = combined_data.dropna(subset=['relative_deviation_bedarf_verbrauch', 'difference_heat_percent_QG'])
    clean_data = clean_data[np.isfinite(clean_data['relative_deviation_bedarf_verbrauch'])]
    clean_data = clean_data[np.isfinite(clean_data['difference_heat_percent_QG'])]

    # Filter out columns that don't exist in data
    available_columns = [col for col in categories if col in clean_data.columns]
    if not available_columns:
        print("Warning: None of the specified columns found in data!")
        return

    print(f"Creating paired boxplot figure for {len(available_columns)} categorical variables (Bedarf vs Verbrauch & QG)...")

    # Calculate subplot layout
    n_plots = len(available_columns)
    n_cols = min(2, n_plots)
    n_rows = (n_plots + n_cols - 1) // n_cols

    # Create figure with subplots
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 12))

    # Handle case where we have only one subplot
    if n_plots == 1:
        axes = [axes]
    elif n_rows == 1:
        axes = axes.flatten() if n_plots > 1 else [axes]
    else:
        axes = axes.flatten()

    # Create paired boxplots for each specified column
    for i, column in enumerate(available_columns):
        ax = axes[i]
        print(f"Creating paired boxplot for: {column}")

        # Get categories
        cats = clean_data[column].dropna().unique()
        cats = sorted(cats)

        # Prepare data for boxplots
        labels = []
        bedarf_data = []
        qg_data = []

        # Overall data
        bedarf_overall = clean_data['relative_deviation_bedarf_verbrauch'].values
        qg_overall = clean_data['difference_heat_percent_QG'].values
        bedarf_data.append(bedarf_overall)
        qg_data.append(qg_overall)
        labels.append('Overall')

        # Category-specific data
        for cat in cats:
            bedarf_cat = clean_data[clean_data[column] == cat]['relative_deviation_bedarf_verbrauch'].values
            qg_cat = clean_data[clean_data[column] == cat]['difference_heat_percent_QG'].values
            if len(bedarf_cat) > 0 and len(qg_cat) > 0:
                bedarf_data.append(bedarf_cat)
                qg_data.append(qg_cat)
                labels.append(str(cat))

        # Positions for paired boxplots
        positions_bedarf = np.arange(1, len(labels) + 1) - 0.15
        positions_qg = np.arange(1, len(labels) + 1) + 0.15

        # Boxplot: Bedarf (blau)
        bp1 = ax.boxplot(bedarf_data, positions=positions_bedarf, widths=0.25,
                         patch_artist=True, medianprops=dict(color='red', linewidth=2), showmeans=True)
        for patch in bp1['boxes']:
            patch.set_facecolor('lightblue')
            patch.set_alpha(0.7)
            patch.set_edgecolor('black')
            patch.set_linewidth(2)

        # Boxplot: QG (grün)
        bp2 = ax.boxplot(qg_data, positions=positions_qg, widths=0.25,
                         patch_artist=True, medianprops=dict(color='darkgreen', linewidth=2), showmeans=True)
        for patch in bp2['boxes']:
            patch.set_facecolor('lightgreen')
            patch.set_alpha(0.7)
            patch.set_edgecolor('darkgreen')
            patch.set_linewidth(2)

        # X-Achse und Labels
        ax.set_xticks(np.arange(1, len(labels) + 1))
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=9)

        # Y-Achse und Titel
        all_data_flat = np.concatenate(bedarf_data + qg_data)
        data_min = np.min(all_data_flat)
        data_max = np.max(all_data_flat)
        data_range = data_max - data_min
        ax.set_ylim(data_min - 0.05 * data_range, data_max + 0.35 * data_range)
        ax.set_title(f'{column}', fontsize=14, fontweight='bold')
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7, linewidth=1)
        ax.set_ylabel('Relativer Fehler (%)', fontsize=10)
        ax.grid(True, alpha=0.3)

        # Legende
        ax.plot([], [], color='lightblue', label='Fehler WKB')
        ax.plot([], [], color='lightgreen', label='Fehler QG')
        ax.legend(loc='upper right', fontsize=9)

    # Hide empty subplots if any
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    # Adjust layout
    fig.suptitle("Abweichung der simulierten Bedarfe vom Verbrauch", 
                fontsize=16, fontweight='bold')
    plt.tight_layout()

    # Save the combined plot
    os.makedirs(plots_dir, exist_ok=True)
    filename = f"boxplots_combined_bedarf_verbrauch_vs_qg_{scenario_name or 'plot'}.png"
    file_path = os.path.join(plots_dir, filename)
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    print(f"Combined paired boxplot saved to: {file_path}")

    # plt.show()
    plt.close(fig)


def plot_faceted_crosstab_heat_error_stats(
    combined_data,
    category1='gebaeudetype_einfach',
    category2='baujahr_spectrum',
    facet_category='sanierungszust_sim',
    value_col='difference_heat_percent_QG',
    scenario_name=None
):
    """
    Create a faceted heatmap for each value of facet_category, showing mean, std, and n for value_col.
    All heatmaps have the same rows/columns and order, even if some cells are empty.
    """
    from matplotlib.colors import LinearSegmentedColormap
    import matplotlib.gridspec as gridspec

    # Filter out NaN and infinite values
    df = combined_data.dropna(subset=[category1, category2, facet_category, value_col])
    df = df[np.isfinite(df[value_col])]

    # Get all possible categories for rows and columns
    all_rows = sorted(combined_data[category1].dropna().unique())
    all_cols = sorted(combined_data[category2].dropna().unique())
    facet_values = sorted(combined_data[facet_category].dropna().unique())
    n_facets = len(facet_values)
    n_cols = min(3, n_facets)
    n_rows = (n_facets + n_cols - 1) // n_cols

    # Custom colormap: -60% rot, 0% grün, +60% rot
    colors = [(1, 0, 0), (0, 1, 0), (1, 0, 0)]  # Red, Green, Red
    cmap = LinearSegmentedColormap.from_list("custom_red_green", colors, N=256)
    vmin, vmax = -60, 60

    # Gridspec für Heatmaps + eine Spalte für die Farbskala
    fig = plt.figure(figsize=(6 * n_cols + 2, 5 * n_rows))
    gs = gridspec.GridSpec(n_rows, n_cols + 1, width_ratios=[1]*n_cols + [0.08], wspace=0.3)

    axes = []
    for idx, facet_val in enumerate(facet_values):
        row = idx // n_cols
        col = idx % n_cols
        ax = fig.add_subplot(gs[row, col])
        axes.append(ax)
        sub_df = df[df[facet_category] == facet_val]
        grouped = sub_df.groupby([category1, category2])[value_col].agg(['mean', 'std', 'count']).reset_index()

        # Pivot and reindex to ensure all categories are present and in same order
        mean_table = grouped.pivot(index=category1, columns=category2, values='mean').reindex(index=all_rows, columns=all_cols)
        std_table = grouped.pivot(index=category1, columns=category2, values='std').reindex(index=all_rows, columns=all_cols)
        count_table = grouped.pivot(index=category1, columns=category2, values='count').reindex(index=all_rows, columns=all_cols)

        im = ax.imshow(mean_table.values, cmap=cmap, aspect='auto', vmin=vmin, vmax=vmax)

        # Annotate each cell
        for i in range(len(all_rows)):
            for j in range(len(all_cols)):
                mean_val = mean_table.iloc[i, j]
                std_val = std_table.iloc[i, j]
                count_val = count_table.iloc[i, j]
                if not np.isnan(mean_val):
                    text = f"µ={mean_val:.1f}%\nσ={std_val:.1f}\nn={int(count_val)}"
                    color = "black" if abs(mean_val) < 30 else "white"
                else:
                    text = ""
                    color = "black"
                ax.text(j, i, text, ha="center", va="center", fontsize=9, color=color)

        ax.set_xticks(np.arange(len(all_cols)))
        ax.set_yticks(np.arange(len(all_rows)))
        ax.set_xticklabels(all_cols, rotation=45, ha='right', fontsize=9)
        ax.set_yticklabels(all_rows, fontsize=9)
        ax.set_xlabel(category2, fontsize=11)
        ax.set_ylabel(category1, fontsize=11)
        ax.set_title(f"{facet_category}: {facet_val}", fontsize=12, fontweight='bold')

    # Remove empty axes
    for idx in range(len(facet_values), n_rows * n_cols):
        fig.delaxes(fig.add_subplot(gs[idx // n_cols, idx % n_cols]))

    # Farbskala ganz rechts
    cbar_ax = fig.add_subplot(gs[:, -1])
    norm = plt.Normalize(vmin=vmin, vmax=vmax)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, cax=cbar_ax)
    cbar.set_label('Mean Error category (%)', fontsize=10)
    cbar.set_ticks([-60, -30, 0, 30, 60])
    cbar.ax.set_yticklabels(['-60', '-30', '0', '30', '60'])

    fig.suptitle(f"Relativer Fehler QG/Wärmeverbrauch-WKB", fontsize=16, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.97])

    filename = f"heat_error_faceted_crosstab_{facet_category}_{scenario_name or 'plot'}.png"
    file_path = os.path.join(plots_dir, filename)
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    print(f"Faceted crosstab heatmap saved to: {file_path}")

    # plt.show()
    plt.close(fig)


def plot_faceted_crosstab_bedarf_verbrauch_heatmap(
    combined_data,
    category1='gebaeudetype_einfach',
    category2='baujahr_spectrum',
    facet_category='sanierungszust_sim',
    scenario_name=None
):
    """
    Faceted heatmap for relative deviation between simulated heat demand and actual consumption.
    """
    from matplotlib.colors import LinearSegmentedColormap
    import matplotlib.gridspec as gridspec

    # Calculate relative deviation
    combined_data['relative_deviation_bedarf_verbrauch'] = (
        (combined_data['waermebedarf_sim_kw'] - combined_data['waermeverbrauch_kw/a']) / combined_data['waermeverbrauch_kw/a']
    ) * 100

    value_col = 'relative_deviation_bedarf_verbrauch'

    # Filter out NaN and infinite values
    df = combined_data.dropna(subset=[category1, category2, facet_category, value_col])
    df = df[np.isfinite(df[value_col])]

    # Get all possible categories for rows and columns
    all_rows = sorted(combined_data[category1].dropna().unique())
    all_cols = sorted(combined_data[category2].dropna().unique())
    facet_values = sorted(combined_data[facet_category].dropna().unique())
    n_facets = len(facet_values)
    n_cols = min(3, n_facets)
    n_rows = (n_facets + n_cols - 1) // n_cols

    # Custom colormap: -60% rot, 0% grün, +60% rot
    colors = [(1, 0, 0), (0, 1, 0), (1, 0, 0)]  # Red, Green, Red
    cmap = LinearSegmentedColormap.from_list("custom_red_green", colors, N=256)
    vmin, vmax = -60, 60

    # Gridspec für Heatmaps + eine Spalte für die Farbskala
    fig = plt.figure(figsize=(6 * n_cols + 2, 5 * n_rows))
    gs = gridspec.GridSpec(n_rows, n_cols + 1, width_ratios=[1]*n_cols + [0.08], wspace=0.3)

    axes = []
    for idx, facet_val in enumerate(facet_values):
        row = idx // n_cols
        col = idx % n_cols
        ax = fig.add_subplot(gs[row, col])
        axes.append(ax)
        sub_df = df[df[facet_category] == facet_val]
        grouped = sub_df.groupby([category1, category2])[value_col].agg(['mean', 'std', 'count']).reset_index()

        # Pivot and reindex to ensure all categories are present and in same order
        mean_table = grouped.pivot(index=category1, columns=category2, values='mean').reindex(index=all_rows, columns=all_cols)
        std_table = grouped.pivot(index=category1, columns=category2, values='std').reindex(index=all_rows, columns=all_cols)
        count_table = grouped.pivot(index=category1, columns=category2, values='count').reindex(index=all_rows, columns=all_cols)

        im = ax.imshow(mean_table.values, cmap=cmap, aspect='auto', vmin=vmin, vmax=vmax)

        # Annotate each cell
        for i in range(len(all_rows)):
            for j in range(len(all_cols)):
                mean_val = mean_table.iloc[i, j]
                std_val = std_table.iloc[i, j]
                count_val = count_table.iloc[i, j]
                if not np.isnan(mean_val):
                    text = f"µ={mean_val:.1f}%\nσ={std_val:.1f}\nn={int(count_val)}"
                    color = "black" if abs(mean_val) < 30 else "white"
                else:
                    text = ""
                    color = "black"
                ax.text(j, i, text, ha="center", va="center", fontsize=9, color=color)

        ax.set_xticks(np.arange(len(all_cols)))
        ax.set_yticks(np.arange(len(all_rows)))
        ax.set_xticklabels(all_cols, rotation=45, ha='right', fontsize=9)
        ax.set_yticklabels(all_rows, fontsize=9)
        ax.set_xlabel(category2, fontsize=10)
        ax.set_ylabel(category1, fontsize=10)
        ax.set_title(f"{facet_category}: {facet_val}", fontsize=12, fontweight='bold')

    # Remove empty axes
    for idx in range(len(facet_values), n_rows * n_cols):
        fig.delaxes(fig.add_subplot(gs[idx // n_cols, idx % n_cols]))

    # Farbskala ganz rechts
    cbar_ax = fig.add_subplot(gs[:, -1])
    norm = plt.Normalize(vmin=vmin, vmax=vmax)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, cax=cbar_ax)
    cbar.set_label('Mean Error (%)', fontsize=10)
    cbar.set_ticks([-60, -30, 0, 30, 60])
    cbar.ax.set_yticklabels(['-60', '-30', '0', '30', '60'])

    fig.suptitle(f"Relativer Fehler Simulationsmodell WKB", fontsize=16, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.97])

    filename = f"heatmap_bedarf_verbrauch_faceted_{facet_category}_{scenario_name or 'plot'}.png"
    file_path = os.path.join(plots_dir, filename)
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    print(f"Faceted Bedarf/Verbrauch heatmap saved to: {file_path}")

    # plt.show()
    plt.close(fig)


def plot_boxplots_by_buildingtype_and_age(
    combined_data,
    saniert=True,
    value_col='difference_heat_percent_QG',
    gebaeudetyp_col='gebaeudetype_einfach',
    altersklasse_col='baujahr_spectrum',
    sanierungs_col='sanierungszust_sim',
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

    # Definiere feste Listen für alle zu zeigenden Kategorien
    alle_gebaeudetypen = ['EFH', 'GMH', 'MFH', 'RH']
    alle_altersklassen = ['1919 - 1948', '1949 - 1978', '1979 - 1990', '1991 - 2000']

    # Filter nach teilsaniert/unsaniert
    filter_value = 'teilsaniert' if saniert else 'unsaniert'
    df = combined_data[combined_data[sanierungs_col] == filter_value]
    df = df.dropna(subset=[gebaeudetyp_col, altersklasse_col, value_col])
    df = df[np.isfinite(df[value_col])]

    print(f"Gefilterte Daten für '{filter_value}': {len(df)} Datenpunkte")
    print(f"Verfügbare Gebäudetypen in Daten: {sorted(df[gebaeudetyp_col].unique())}")
    print(f"Verfügbare Altersklassen in Daten: {sorted(df[altersklasse_col].unique())}")

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
        for altersklasse in alle_altersklassen:
            vals = subset[subset[altersklasse_col] == altersklasse][value_col].values
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
        ax.set_xticks(range(1, len(alle_altersklassen) + 1))
        ax.set_xticklabels(alle_altersklassen, rotation=0, fontsize=9)
        # X-Achse Limits erweitern für mehr Platz an den Rändern
        ax.set_xlim(0.5, len(alle_altersklassen) + 0.5)
        ax.set_xlabel('Altersklasse (Baujahr)', fontsize=10, labelpad=8)
        ax.set_ylabel('Relative Abweichung (%)', fontsize=10, labelpad=8)
        # Null-Linie hervorheben für bessere Sichtbarkeit
        ax.axhline(y=0, color='gray', alpha=0.7, linewidth=1)
        #ax.grid(True, alpha=0.3)
        ax.tick_params(axis='y', labelsize=9)
        
        # Markiere fehlende Altersklassen
        for j, (altersklasse, count) in enumerate(zip(alle_altersklassen, counts)):
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
    plots_dir = os.path.join(srcPath, 'districtgenerator', 'results', 'plots')
    os.makedirs(plots_dir, exist_ok=True)
    fname = f"boxplots_all_buildingtype_age_{'teilsaniert' if saniert else 'unsaniert'}_{scenario_name or 'plot'}.png"
    file_path = os.path.join(plots_dir, fname)
    plt.savefig(file_path, dpi=300, bbox_inches='tight')
    # plt.show()
    plt.close(fig)
    print(f"Kombinierte Boxplot-Grafik gespeichert: {fname}")



if __name__ == '__main__':
    data = example10_comparison_heat_demands()
    # Analyse the data
    # combined_data= analyse_data(scenario_name="WKB_export")
