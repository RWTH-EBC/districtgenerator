# -*- coding: utf-8 -*-

"""
This script generates district layouts based on the selected settlement type and
the target number of buildings.

It can be used in three modes:
1. Generate one district interactively.
2. Generate a batch of districts automatically.
3. Generate Paper_3: 10 valid districts per type A-F, H, I, with 30 buildings each.

Typical settlement types include:
A   "german": "Streusiedlungen",
    "english": "Scattered settlements"
B   "german": "Dörfliche Bebauung",
    "english": "Rural village development"
C   "german": "Wohnbebauung niedriger Dichte",
    "english": "Low-density residential development"
D   "german": "Wohnbebauung mittlerer Dichte",
    "english": "Medium-density residential development"
E   "german": "Reihenhausbebauung",
    "english": "Row housing development"
F   "german": "Zeilenbebauung mittlerer Dichte",
    "english": "Row development with medium density"
G   "german": "Zeilenbebauung hoher Dichte und Hochhäuser",
    "english": "Row development of high density and high-rise buildings"
H   "german": "Blockbebauung",
    "english": "Block development"
I   "german": "Innenstadt",
    "english": "City center"

The parameters of the settlement types and their sources are listed in:
districtgenerator/data/typdistrict_parameters.xlsx
"""

import subprocess
import sys
import re
import os
from datetime import datetime


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def generate_one_district(output_subdirectory=None):
    """
    Generate one district interactively.

    The inputs are requested by the imported generation functions:
    - typdistrict_preprocess.py requests the random seed and settlement type.
    - typdistrict_postprocess.py requests the number of buildings.

    The generated output files are saved in:
    districtgenerator/data/scenarios

    Output files:
    1. Image file:
       Shows the generated road layout, building positions, transformer station,
       and assigned building attributes.

    2. JSON file:
       Stores the generated district geometry, building attributes, road information,
       transformer position, sampled parameters, and metadata such as settlement type
       and random seed. This file can be used for subsequent network or pipeline
       optimization.

    3. CSV file:
       Stores the building information in a format used for initializing the
       data handler in subsequent analyses.

    The random seed is included in the output file names to distinguish different
    stochastic realizations and to allow reproducible regeneration of the same district.
    """

    from districtgenerator.functions.typdistrict_postprocess import scenario_generation

    result = scenario_generation(output_subdirectory=output_subdirectory)
    if result:
        print(
            f"Generated valid district: type {result['district_type']}, "
            f"seed {result['seed']}, buildings {result['num_buildings']}, "
            f"layout {result.get('f_layout_variant') or 'standard'}"
        )


def generate_batch(settlement_types=None, number_of_new_districts_per_type=None,
                   number_of_buildings=None, output_subdirectory=None):
    """
    Generate a batch of districts automatically.

    Batch behavior:
    - Starts with seed 1 for each selected settlement type.
    - Generates the requested number of valid districts.
    - If a seed cannot generate the requested number of buildings, the
      generation function automatically tries the next seed.
    - Writes every batch to a new subfolder (timestamped unless explicitly named).
      Refuses to use an existing folder, even if it is empty.

    Example:
    If 20 valid districts are requested and seed 2 fails, the outputs may use
    seeds 1, 3, 4, ..., 21.
    """

    if settlement_types is None:
        settlement_types = input(
            "\nEnter settlement type(s), e.g. H or ABCDEFGHI: "
        ).strip().upper()
    settlement_types = list(settlement_types)
    invalid_types = [district_type for district_type in settlement_types if district_type not in list("ABCDEFGHI")]
    if not settlement_types or invalid_types:
        raise ValueError("Please enter only settlement types A-I.")
    if len(set(settlement_types)) != len(settlement_types):
        raise ValueError("Please enter each settlement type only once.")

    if number_of_new_districts_per_type is None:
        number_of_new_districts_per_type = int(
            input("\nEnter number of valid districts to generate per type: ").strip()
        )
    if number_of_buildings is None:
        number_of_buildings = int(
            input("\nEnter number of buildings per district: ").strip()
        )
    if number_of_new_districts_per_type < 1 or number_of_buildings < 1:
        raise ValueError("District and building counts must be positive.")
    type_label = "".join(settlement_types)
    batch_subdirectory = output_subdirectory or (
        f"validation_{type_label}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    if (any(part in {"", ".", ".."} for part in batch_subdirectory.replace("\\", "/").split("/"))
            or os.path.isabs(batch_subdirectory)
            or os.path.splitdrive(batch_subdirectory)[0]):
        raise ValueError("output_subdirectory must be a relative path without traversal.")
    batch_directory = os.path.join(
        PROJECT_ROOT, "districtgenerator", "data", "scenarios", batch_subdirectory
    )
    # Reserve a fresh folder before starting any generation subprocess.
    try:
        os.makedirs(batch_directory, exist_ok=False)
    except FileExistsError:
        raise FileExistsError(
            f"Refusing to overwrite an existing batch folder: {batch_directory}"
        ) from None
    print(
        "\nThis batch will be saved separately in: "
        f"{batch_directory}"
    )
    max_seed_to_try = 500

    for district_type in settlement_types:
        seed = 1
        new_districts_created = 0
        while new_districts_created < number_of_new_districts_per_type:
            if seed > max_seed_to_try:
                raise RuntimeError(
                    f"Could not generate {number_of_new_districts_per_type} new complete "
                    f"districts for type {district_type} after trying seeds up to {max_seed_to_try}."
                )

            print(
                f"\nGenerating settlement type {district_type}, "
                f"seed {seed}, buildings {number_of_buildings}"
            )

            # The called script expects three inputs in this order:
            # 1. random seed
            # 2. settlement type
            # 3. number of buildings
            user_inputs = f"{seed}\n{district_type}\n{number_of_buildings}\n"

            process = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    __file__,
                    "--single",
                    f"--output-subdirectory={batch_subdirectory}",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write(user_inputs)
            process.stdin.close()

            output_lines = []
            for line in process.stdout:
                output_lines.append(line)
                print(line, end="")

            return_code = process.wait()
            completed_stdout = "".join(output_lines)
            if return_code != 0:
                raise subprocess.CalledProcessError(
                    return_code,
                    [sys.executable, "-u", __file__, "--single"],
                    output=completed_stdout,
                )

            successful_seed_match = re.search(
                rf"Generated valid district: type {district_type}, seed (\d+), buildings (\d+),",
                completed_stdout
            )
            if not successful_seed_match:
                raise RuntimeError("Generation ended without confirming a valid district.")
            successful_seed = int(successful_seed_match.group(1))
            if (successful_seed < seed
                    or int(successful_seed_match.group(2)) != number_of_buildings):
                raise RuntimeError("Generated district does not match the requested seed or building count.")

            new_districts_created += 1
            print(
                f"New {district_type} districts created in this batch: "
                f"{new_districts_created} / {number_of_new_districts_per_type}"
            )
            seed = max(seed + 1, successful_seed + 1)

    print("\nFinished generating all batch districts.")


def main():
    """
    Choose between interactive single-district generation and automatic batch generation.

    Use mode 1 if you want to generate one district manually.
    Use mode 2 if you want to generate a batch of valid districts.
    Use mode 3 for the protected Paper_3 batch (80 districts, 30 buildings each).
    """

    # Internal mode used by generate_batch().
    # It prevents the menu from appearing for every automatically generated district.
    if len(sys.argv) > 1 and sys.argv[1] == "--single":
        output_subdirectory = None
        for argument in sys.argv[2:]:
            if argument.startswith("--output-subdirectory="):
                output_subdirectory = argument.split("=", 1)[1]
                break
        generate_one_district(output_subdirectory=output_subdirectory)
        return

    print("\nSelect generation mode:")
    print("1: Generate one district")
    print("2: Generate batch")
    print("3: Generate Paper_3 (types ABCDEFHI, 10 districts per type, 30 buildings)")

    mode = input("\nEnter mode 1, 2 or 3: ").strip()

    if mode == "1":
        generate_one_district()

    elif mode == "2":
        generate_batch()

    elif mode == "3":
        generate_batch(
            settlement_types="ABCDEFHI",
            number_of_new_districts_per_type=10,
            number_of_buildings=30,
            output_subdirectory=os.path.join("Paper_3", "districts"),
        )

    else:
        print("Invalid mode. Please enter 1, 2 or 3.")


if __name__ == "__main__":
    main()
