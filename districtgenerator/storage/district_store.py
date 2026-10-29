"""
Saving and loading of the generated district as a pickle file.
"""
import pickle


def save_district(data):
    """
    Save district dict as pickle file.

    Returns
    -------
    None.
    """

    with open(data.resultPath + "/" + data.scenario_name + ".p", 'wb') as fp:
        pickle.dump(data.district, fp, protocol=pickle.HIGHEST_PROTOCOL)


def load_district(data, scenario_name='example'):
    """
    Load district dict from pickle file.

    Parameters
    ----------
    scenario_name : string, optional
        Name of district file to be read. The default is 'example'.

    Returns
    -------
    None.
    """

    data.scenario_name = scenario_name

    with open(data.resultPath + "/" + data.scenario_name + ".p", 'rb') as fp:
        data.district = pickle.load(fp)
