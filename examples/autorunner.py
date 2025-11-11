import os
import sys
import subprocess
import json

# Set the directory containing the example scripts
examples_dir = os.path.abspath(os.path.dirname(__file__))

filePath = r"U:\Team-UES-Studis\rha-jpa\Jaspar_Paulus\Rawad_Hiwi\01_DistrictGenerator\00_Python\DistrictGenerator\districtgenerator\data\site_data.json"
area_values = [24.52695551, 17.16061845, 3.223488545, 2.592437824, 1.254160115, 4.518725758]     # make sure the number of area values matches the number of scripts!
# For District-Type A-F, the values are [24.52695551, 17.16061845, 3.223488545, 2.592437824, 1.254160115, 4.518725758]

# Loop through each script and execute them sequentially
for letter, area in zip("ABCDEF", area_values):
    script = f"e8_scenario_evaluation_{letter}.py"   # make sure the script name matches your actual script names!
    script_path = os.path.join(examples_dir, script)
    print(f"\nStarte {script_path} mit {area} ha Distriktgröße...")

    # Set new FAR values in heat_grid.json (important for the optimization of heat grids)
    with open(filePath, "r", encoding="utf-8") as json_file:
        district_data = json.load(json_file)
    district_data[4]["value"] = area
    with open(filePath, "w", encoding="utf-8") as json_file:
        json.dump(district_data, json_file, ensure_ascii=False, indent=4)

    # Check if the FAR value was set correctly
    with open(filePath, "r", encoding="utf-8") as json_file:
        check_data = json.load(json_file)
    print(f"Aktuell gesetzte Distriktgröße: {check_data[4]['value']}")

    try:
        subprocess.run([sys.executable, script_path], check=True, cwd=examples_dir)
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei {script}: {e}")
    else:
        print(f"Fertig mit {script}")

    script_HP = f"e8_scenario_evaluation_{letter}_HP.py"  # make sure the script name matches your actual script names!
    script_HP_path = os.path.join(examples_dir, script_HP)
    print(f"\nStarte {script_HP_path} mit {area} ha Distriktgröße...")

    try:
        subprocess.run([sys.executable, script_HP_path], check=True, cwd=examples_dir)
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei {script_HP}: {e}")
    else:
        print(f"Fertig mit {script_HP}")