import uni
# Shoud create simulations for non-residential buildings
# Write a test, that all functions run through without errors
# Check if the results exist and are not zero

class TestNonResidential(unittest.TestCase):
    def test_non_residential(self):
        # Test all functions in the non_residential module
        pass


if __name__ == '__main__':
    unittest.main()

    # Save a file to scenarios folder
    # Create for each building type a simulation 
    # Test if it ran trough without errors and teh results are not zero

    test_data = { 
        id : [0 , 1 ,2 ,3 ,4 ,5 ,6 ,7 ,8 ,9 }
    }