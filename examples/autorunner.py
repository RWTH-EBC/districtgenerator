import os
import sys
import subprocess

# Verzeichnisse festlegen
examples_dir = os.path.abspath(os.path.dirname(__file__))

# Skripte A bis I ausführen
for letter in "ABCDEFGHI":
    script = f"e8_scenario_evaluation_{letter}.py"
    script_path = os.path.join(examples_dir, script)
    print(f"\nStarte {script_path} ...")
    try:
        subprocess.run([sys.executable, script_path], check=True, cwd=examples_dir)
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei {script}: {e}")
    else:
        print(f"Fertig mit {script}")