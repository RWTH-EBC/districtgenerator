# -*- coding: utf-8 -*-

"""
This script generates district layouts based on the selected settlement type and
the target number of buildings.

It can be used in two modes:
1. Generate one district interactively.
2. Generate a batch of districts automatically.

Typical settlement types include:
A   "german": "Wohnplätze und Streusiedlungen",
    "english": "Residential places and scattered settlements"
B   "german": "Dörfer mit überwiegend Gehöften",
    "english": "Villages with mainly homesteads"
C   "german": "Ein- und Zweifamilienhaussiedlung niedriger Dichte",
    "english": "Single and two-family house settlements of low density"
D   "german": "Bausiedlung hoher Dichte und Dorfkern",
    "english": "Settlements with high density and village core"
E   "german": "Reihenhausbebauung",
    "english": "Row housing development"
F   "german": "Zeilenbebauung mittlerer Dichte",
    "english": "Row development with medium density"
G   "german": "Zeilenbebauung hoher Dichte und Hochhäuser",
    "english": "Row development of high density and high-rise buildings"
H   "german": "Blockbebauung",
    "english": "Block development"
I   "german": "Mittelalterliche Altstadt",
    "english": "Medieval old town"

The parameters of the settlement types and their sources are listed in:
districtgenerator/data/typdistrict_parameters.xlsx
"""

import subprocess
import sys


def generate_one_district():
    """
    Generate one district interactively.

    The inputs are requested by the imported generation functions:
    - typdistrict_preprocess.py requests the random seed and settlement type.
    - typdistrict_postprocess_paper2.py requests the number of buildings.

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

    from districtgenerator.functions.typdistrict_postprocess_paper2 import scenario_generation

    scenario_generation()


def generate_batch():
    """
    Generate a batch of districts automatically.

    Current batch setting:
    - Settlement types: A--I
    - Number of districts per settlement type: 20
    - Number of buildings per district: 30
    - Random seeds: 1--20 for each settlement type

    This means that 20 stochastic realizations are generated for each settlement type.
    Since the seed is fixed for each realization, the same district can be reproduced
    later by using the same settlement type, number of buildings, and random seed.
    """

    settlement_types = list("ABCDEFGHI")
    number_of_districts_per_type = 20
    number_of_buildings = 30

    for district_type in settlement_types:
        for seed in range(1, number_of_districts_per_type + 1):
            print(
                f"\nGenerating settlement type {district_type}, "
                f"seed {seed}, buildings {number_of_buildings}"
            )

            # The called script expects three inputs in this order:
            # 1. random seed
            # 2. settlement type
            # 3. number of buildings
            user_inputs = f"{seed}\n{district_type}\n{number_of_buildings}\n"

            subprocess.run(
                [sys.executable, __file__, "--single"],
                input=user_inputs,
                text=True,
                check=True
            )

    print("\nFinished generating all batch districts.")


def main():
    """
    Choose between interactive single-district generation and automatic batch generation.

    Use mode 1 if you want to generate one district manually.
    Use mode 2 if you want to generate 20 districts with 30 buildings for each
    settlement type A--I.
    """

    # Internal mode used by generate_batch().
    # It prevents the menu from appearing for every automatically generated district.
    if len(sys.argv) > 1 and sys.argv[1] == "--single":
        generate_one_district()
        return

    print("\nSelect generation mode:")
    print("1: Generate one district")
    print("2: Generate batch: 20 districts per settlement type, 30 buildings each")

    mode = input("\nEnter mode 1 or 2: ").strip()

    if mode == "1":
        generate_one_district()

    elif mode == "2":
        generate_batch()

    else:
        print("Invalid mode. Please enter 1 or 2.")


if __name__ == "__main__":
    main()