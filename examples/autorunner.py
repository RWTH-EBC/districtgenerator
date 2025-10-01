import os
import sys
import subprocess
import json

# Set the directory containing the example scripts
examples_dir = os.path.abspath(os.path.dirname(__file__))

filePath = r"U:\Team-UES-Studis\rha-jpa\Jaspar_Paulus\01_DistrictGenerator\00_Python\DistrictGenerator\districtgenerator\data\heat_grid.json"
far_values = [0.03671063, 0.40077227, 0.1396338, 0.32502226, 0.45687946, 0.5413473]     # make sure the number of FAR values matches the number of scripts!
# For District-Type A-I, the values are [0.03671063, 0.40077227, 0.1396338, 0.32502226, 0.45687946, 0.5413473, 2.82823929, 1.44160314, 1.45025525]

# Loop through each script and execute them sequentially
for letter, far in zip("ABCDEF", far_values):
    script = f"e8_scenario_evaluation_{letter}.py"   # make sure the script name matches your actual script names!
    script_path = os.path.join(examples_dir, script)
    print(f"\nStarte {script_path} mit FAR_Wert {far} ...")

    # Set new FAR values in heat_grid.json (important for the optimization of heat grids)
    with open(filePath, "r", encoding="utf-8") as json_file:
        heat_grid_data = json.load(json_file)
    heat_grid_data["FAR"]["value"] = far
    with open(filePath, "w", encoding="utf-8") as json_file:
        json.dump(heat_grid_data, json_file, ensure_ascii=False, indent=4)

    # Check if the FAR value was set correctly
    with open(filePath, "r", encoding="utf-8") as json_file:
        check_data = json.load(json_file)
    print(f"Aktuell gesetzter FAR_Wert: {check_data['FAR']['value']}")

    try:
        subprocess.run([sys.executable, script_path], check=True, cwd=examples_dir)
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei {script}: {e}")
    else:
        print(f"Fertig mit {script}")