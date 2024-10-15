# -*- coding: utf-8 -*-

"""
This file is the fifth example to generate the demand profiles of the buildings.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e1.0_generate_first_district.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

from districtgenerator.classes import datahandler

class Test_examples(object):
    """Unit Tests for the DistrictGenerator"""

    def test_e1_initialize_datahandle(self):
        """Tests the executability of example 1"""
        from examples import e1_initialize_datahandler as e1

        data = e1.example1_initialize_datahandler()

        #assert prj.name == "ArchetypeExample"

    def test_e2_generate_environment(self):
        """Tests the executability of example 2"""
        from examples import e2_generate_environment as e2

        data = e2.example2_generate_environment()

    def test_e3_initialize_buildings(self):
        """Tests the executability of example 3"""
        from examples import e3_initialize_buildings as e3

        data = e3.example3_initialize_buildings()

    def test_e4_generate_buildings(self):
        """Tests the executability of example 4"""
        from examples import e4_generate_buildings as e4

        data = e4.example4_generate_buildings()

    def test_e5_generate_demands(self):
        """Tests the executability of example 5"""
        from examples import e5_generate_demands as e5

        data = e5.example5_generate_demands()