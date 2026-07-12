# -*- coding: utf-8 -*-
"""
Example script to compare 5R1C and 7R2C building simulation models.
Runs simulations for both models under identical occupant profiles and internal heat gains.
Generates a clean, uncluttered concatenated timeseries plot for the 4 typical weeks across all building types.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Add the project root to the path so we can run the script from anywhere
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from districtgenerator.classes import Datahandler

def main():
    scenario_name = "example_decentral"
    env_path = ".env.CONFIG.EXAMPLE"
    
    print("Initializing Datahandler for 5R1C simulation...")
    # 1. Run 5R1C simulation
    data = Datahandler(scenario_name=scenario_name, env_path=env_path)
    data.design_building_data["thermal_model_type"] = "5R1C"
    
    data.generateEnvironment()
    data.initializeBuildings()
    data.generateBuildings()
    
    print("Generating demand profiles for 5R1C model...")
    # This generates raw building demand profiles
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)
    
    print("Designing decentral devices...")
    # This calculates PV/STC profiles which are required for clustering inputs
    data.designDecentralDevices(saveGenerationProfiles=False)
    
    # Initialize centralDevices dictionary (required by clustering process when central energy supply is not designed)
    data.centralDevices = {}
    
    print("Running initial clustering...")
    # This clusters building demand and environmental profiles using k-medoids
    data.prepareClusteringInputs()
    
    # Store 5R1C heating loads and gains for all buildings
    bld_data = []
    for b in data.district:
        bld_data.append({
            "name": b["unique_name"],
            "type": b["buildingFeatures"]["building"],
            "heat_5r1c": b["user"].heat.copy() / 1000.0,  # W to kW
            "gains": b["user"].gains.copy() / 1000.0,      # W to kW
            "heat_7r2c": None
        })
    
    # Get typical weeks selected by clustering
    clusters = data.clusters
    print(f"Typical weeks selected by clustering: {clusters}")
    
    # 2. Run 7R2C simulation using the exact same occupant profiles and internal gains
    print("Switching model type to 7R2C...")
    data.design_building_data["thermal_model_type"] = "7R2C"
    
    # Re-generate buildings to create 7R2C envelopes
    data.generateBuildings()
    
    # Now programmatically run 7R2C calculation for each building
    for b in data.district:
        b["thermal_model"] = "7R2C"
        # Calculate 7R2C thermal parameters
        b["envelope"]._VDI6007_params(data.site["SunRad"])
        b["envelope"].calc_theta_eq(data.site, b["user"].gains)
        
        # Calculate space heating profile
        night_setback = b["buildingFeatures"]["night_setback"]
        is_cooled = b["buildingFeatures"]["cooling"]
        b["user"].calcHeatingProfile(
            site=data.site,
            envelope=b["envelope"],
            thermal_model="7R2C",
            night_setback=night_setback,
            is_cooled=is_cooled,
            calendar=data.calendar,
            time_resolution=data.time["timeResolution"],
            initial_day=data.initial_day
        )
    
    # Store 7R2C heating loads for all buildings
    for idx, b in enumerate(data.district):
        bld_data[idx]["heat_7r2c"] = b["user"].heat.copy() / 1000.0  # W to kW
    
    # 3. Extract boundary conditions for the 4 typical weeks
    T_e_annual = data.site["T_e"]
    SunTotal_annual = data.site["SunTotal"]
    
    # 4. Concatenate the 4 typical weeks horizontally
    hours_per_week = 168
    total_hours = hours_per_week * 4
    
    T_e_concat = np.zeros(total_hours)
    solar_concat = np.zeros(total_hours)
    
    for idx, bld in enumerate(bld_data):
        bld["heat_5r1c_concat"] = np.zeros(total_hours)
        bld["heat_7r2c_concat"] = np.zeros(total_hours)
        bld["gains_concat"] = np.zeros(total_hours)
        
    for i, week_idx in enumerate(clusters):
        start_h = week_idx * hours_per_week
        end_h = (week_idx + 1) * hours_per_week
        
        dest_start = i * hours_per_week
        dest_end = (i + 1) * hours_per_week
        
        T_e_concat[dest_start:dest_end] = T_e_annual[start_h:end_h]
        solar_concat[dest_start:dest_end] = SunTotal_annual[start_h:end_h]
        
        for bld in bld_data:
            bld["heat_5r1c_concat"][dest_start:dest_end] = bld["heat_5r1c"][start_h:end_h]
            bld["heat_7r2c_concat"][dest_start:dest_end] = bld["heat_7r2c"][start_h:end_h]
            bld["gains_concat"][dest_start:dest_end] = bld["gains"][start_h:end_h]

    # 5. Generate comparison plots
    print("Generating comparative plots (concatenated 5-subplot stack)...")
    fig, axs = plt.subplots(5, 1, figsize=(16, 20), sharex=True)
    
    # Colors
    color_5r1c = '#1f77b4'       # Blue
    color_7r2c = '#d62728'       # Red
    color_temp = '#2ca02c'       # Green
    color_solar = '#f1c40f'      # Yellow
    color_gains = '#9b59b6'      # Purple
    
    x_hours = np.arange(total_hours)
    
    # Divider configurations
    dividers = [hours_per_week * k for k in range(1, 4)]
    week_midpoints = [hours_per_week * (k + 0.5) for k in range(4)]
    week_labels = [f"Typical Week {k+1}\n(Week {w} of Year)" for k, w in enumerate(clusters)]
    
    # Subplot 0: Boundary Conditions (Weather)
    ax0 = axs[0]
    line_temp = ax0.plot(x_hours, T_e_concat, color=color_temp, linewidth=1.5, label='Ambient Temp.')
    ax0.set_ylabel("Ambient Temp. (°C)", color=color_temp, fontsize=11)
    ax0.tick_params(axis='y', labelcolor=color_temp)
    ax0.grid(True, linestyle=':', alpha=0.6)
    
    ax0_right = ax0.twinx()
    line_solar = ax0_right.plot(x_hours, solar_concat, color=color_solar, linewidth=1.2, linestyle='-.', label='Solar Radiation')
    ax0_right.set_ylabel("Solar Radiation (W/m²)", color=color_solar, fontsize=11)
    ax0_right.tick_params(axis='y', labelcolor=color_solar)
    
    # Combine legend for weather
    lines_weather = line_temp + line_solar
    labels_weather = [l.get_label() for l in lines_weather]
    ax0.legend(lines_weather, labels_weather, loc='upper right', fontsize=9, frameon=True, facecolor='white', framealpha=0.9)
    
    # Subplots 1-4: Building demand comparisons
    for j, bld in enumerate(bld_data):
        ax = axs[j + 1]
        
        # Primary axis: Heating Load (5R1C vs 7R2C)
        line1 = ax.plot(x_hours, bld["heat_5r1c_concat"], color=color_5r1c, linewidth=2.0, label='Heating Load 5R1C')
        line2 = ax.plot(x_hours, bld["heat_7r2c_concat"], color=color_7r2c, linewidth=2.0, linestyle='--', label='Heating Load 7R2C')
        
        ax.set_ylabel("Heating Load (kW)", color='black', fontsize=11)
        ax.tick_params(axis='y', labelcolor='black')
        ax.grid(True, linestyle=':', alpha=0.6)
        
        # Ensure heating load starts at 0 and has a sensible upper bound
        max_load = max(bld["heat_5r1c_concat"].max(), bld["heat_7r2c_concat"].max())
        ax.set_ylim(bottom=0, top=max(1.0, max_load * 1.15))
        
        # Secondary y-axis: Building Internal Gains
        ax_right = ax.twinx()
        line3 = ax_right.plot(x_hours, bld["gains_concat"] * 1000.0, color=color_gains, linewidth=1.2, linestyle=':', label='Internal Gains')
        ax_right.set_ylabel("Internal Gains (W)", color=color_gains, fontsize=11)
        ax_right.tick_params(axis='y', labelcolor=color_gains)
        
        # Combine legend
        lines = line1 + line2 + line3
        labels = [l.get_label() for l in lines]
        ax.legend(lines, labels, loc='upper right', fontsize=9, frameon=True, facecolor='white', framealpha=0.9)
        
        ax.set_title(f"Building: {bld['type']} ({bld['name']})", fontsize=13, fontweight='bold')

    # Add vertical dividers and labels across all subplots
    for ax in axs:
        for div in dividers:
            ax.axvline(x=div, color='#7f8c8d', linestyle='--', linewidth=1.5, alpha=0.8)
            
    # Add week headers above the top plot
    for midpoint, label in zip(week_midpoints, week_labels):
        axs[0].text(midpoint, axs[0].get_ylim()[1] * 1.05, label, 
                    ha='center', va='bottom', fontsize=10, fontweight='bold', color='#2c3e50')
        
    axs[-1].set_xlabel("Cumulative Hours of the 4 Typical Weeks", fontsize=11)
    
    plt.suptitle("Comparative Simulation: 5R1C vs 7R2C Building Models", fontsize=16, fontweight='bold', y=0.99)
    plt.tight_layout()
    
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "model_comparison.png")
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Comparison plot successfully saved to: {output_path}")

if __name__ == "__main__":
    main()
