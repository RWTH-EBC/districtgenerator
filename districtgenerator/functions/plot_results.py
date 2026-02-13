import matplotlib.pyplot as plt
import os

def plot_grid_flows(result_dictCon=None,y=None, result_dir=None, show=True):

    if result_dictCon is None:
        raise ValueError("result_dict is required")
    
    plots_dir = os.path.join(result_dir or ".", "plots")
    os.makedirs(plots_dir, exist_ok=True)


    for district_name, result_dict in result_dictCon.items():  
        
        series_from_main_grid_by_year = result_dict.get("from_main_grid_timeseries")
        series_to_main_grid_by_year = result_dict.get("to_main_grid_timeseries")
        series_from_network_by_year = result_dict.get("from_network_timeseries")
        series_to_network_by_year = result_dict.get("to_network_timeseries")
        series_from_grid_by_year = result_dict.get("from_grid_timeseries")
        series_to_grid_by_year = result_dict.get("to_grid_timeseries")
        
        if not series_from_main_grid_by_year:
            continue 
        
        
        available_years = sorted(series_from_main_grid_by_year.keys())
        year = y if y is not None else available_years[0]
        if year not in series_from_main_grid_by_year:
            raise ValueError(f"support year {year} not in from_main_grid_timeseries for {district_name}")

        values_from_main_grid = [value for cluster in series_from_main_grid_by_year[year] for value in cluster]
        values_to_main_grid = [value for cluster in series_to_main_grid_by_year[year] for value in cluster]
        values_from_network = [value for cluster in series_from_network_by_year[year] for value in cluster]
        values_to_network = [value for cluster in series_to_network_by_year[year] for value in cluster]
        values_from_grid = [value for cluster in series_from_grid_by_year[year] for value in cluster]
        values_to_grid = [value for cluster in series_to_grid_by_year[year] for value in cluster]
        x = list(range(len(values_from_main_grid)))

        title = f"from_and_to_main_grid timeseries"
        if district_name:
            title += f" - {district_name}"
        title += f" (year {year})"

        plt.figure(figsize=(12, 4))
        plt.plot(x, values_from_main_grid, label="From Main Grid", color='blue')
        plt.plot(x, values_to_main_grid, label="To Main Grid", color='orange')
        plt.plot(x, values_from_network, label="From Network", linestyle='--', color='blue')
        plt.plot(x, values_to_network, label="To Network", linestyle='--', color='orange')
        highlight_indices = [
            i for i, (a, b, c, d) in enumerate(zip(values_from_main_grid, values_from_network, values_to_main_grid, values_to_network))
            if (a > 0 and c > 0) or (a > 0 and d > 0 ) or (b > 0 and c > 0) or (b > 0 and d > 0)
        ]
        for idx in highlight_indices:
            plt.axvspan(idx - 0.5, idx + 0.5, color="#f50707", alpha=0.4, zorder=0)
        plt.xlabel("Time step")
        plt.ylabel("Power from and to main grid (kW)")
        plt.title(title)
        plt.legend()
        plt.tight_layout()

        if district_name:
            filename = f"all_grid_flows_{district_name}_y{year}.png"
        else:
            filename = f"all_grid_flows_y{year}.png"

        plot_path = os.path.join(plots_dir, filename)
        plt.savefig(plot_path, dpi=150)

        if show:
            plt.show()
        else:
            plt.close()

        plt.figure(figsize=(12, 4))
        plt.plot(x, values_from_main_grid, label="From Main Grid", color='blue')
        plt.plot(x, values_to_main_grid, label="To Main Grid", color='orange')
        highlight_indices = [
            i for i, (a, b) in enumerate(zip(values_from_main_grid, values_to_main_grid))
            if a > 0 and b > 0
        ]
        for idx in highlight_indices:
            plt.axvspan(idx - 0.5, idx + 0.5, color="#f50707", alpha=0.4, zorder=0)
        plt.xlabel("Time step")
        plt.ylabel("Power from and to main grid (kW)")
        plt.title(title)
        plt.legend()
        plt.tight_layout()

        if district_name:
            filename = f"main_grid_flows_{district_name}_y{year}.png"
        else:
            filename = f"main_grid_flows_y{year}.png"

        plot_path = os.path.join(plots_dir, filename)
        plt.savefig(plot_path, dpi=150)

        if show:
            plt.show()
        else:
            plt.close()
        
        plt.figure(figsize=(12, 4))
        plt.plot(x, values_from_grid, label="From Grid", color='blue')
        plt.plot(x, values_to_grid, label="To Grid", color='orange')
        highlight_indices = [
            i for i, (a, b) in enumerate(zip(values_from_grid, values_to_grid))
            if a > 0 and b > 0
        ]
        for idx in highlight_indices:
            plt.axvspan(idx - 0.5, idx + 0.5, color="#f50707", alpha=0.4, zorder=0)
        plt.xlabel("Time step")
        plt.ylabel("Power from and to grid (kW)")
        plt.title(title)
        plt.legend()
        plt.tight_layout()

        if district_name:
            filename = f"grid_flows_{district_name}_y{year}.png"
        else:
            filename = f"grid_flows_y{year}.png"

        plot_path = os.path.join(plots_dir, filename)
        plt.savefig(plot_path, dpi=150)

        if show:
            plt.show()
        else:
            plt.close()
        
        plt.figure(figsize=(12, 4))
        plt.plot(x, values_from_network, label="From Network", linestyle='--', color='blue')
        plt.plot(x, values_to_network, label="To Network", linestyle='--', color='orange')
        highlight_indices = [
            i for i, (a, b) in enumerate(zip(values_from_network, values_to_network))
            if a > 0 and b > 0
        ]
        for idx in highlight_indices:
            plt.axvspan(idx - 0.5, idx + 0.5, color="#f50707", alpha=0.4, zorder=0)
        plt.xlabel("Time step")
        plt.ylabel("Power from and to network (kW)")
        plt.title(title)
        plt.legend()
        plt.tight_layout()

        if district_name:
            filename = f"network_flows_{district_name}_y{year}.png"
        else:
            filename = f"network_flows_y{year}.png"

        plot_path = os.path.join(plots_dir, filename)
        plt.savefig(plot_path, dpi=150)

        if show:
            plt.show()
        else:
            plt.close()


    return None