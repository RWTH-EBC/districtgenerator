# -*- coding: utf-8 -*-
#With this class I test how dictionaries work
def test_network():
    tel={'lisa': 5572, 'anna':4421, 'eva': 1234}
    print(tel)

    telbig = {'lisa': {'number': 5572, 'age': 29}, 'anna': {'number': 4421, 'age': 34}, 'eva': {'number': 1234, 'age': 40}}

    smalltel_network=test_run_otim(telbig)
    return smalltel_network


def test_run_otim(telbig):
    smalltel = telbig[list(telbig.keys())[0]]
    print(f"Lisas Data: {smalltel}")
    return smalltel    

def test_add_Vars():
    data1 = {'scenarioname': 'District1'}
    data2 = {'scenarioname': 'District2'}
    dataCon= {}
    dataCon["Districts"] = [data1, data2]

    all_devs = ['BOI', 'HP', 'PV', 'Bat']

    capCon = {}
    for data in dataCon["Districts"]:
        cap = {}
        for device in all_devs:
            cap[device] = 10
        capCon[data["scenarioname"]] = cap
    return dataCon, capCon

def testlist():
    data1 = {'scenarioname': 'District1'}
    data2 = {'scenarioname': 'District2'}
    dataCon= {}
    dataCon["Districts"] = [data1, data2]
    all_devs_Con = {}
    for data in dataCon["Districts"]:
        all_devs = [f"PV_{data["scenarioname"]}", f"CHP_{data["scenarioname"]}"]
        all_devs_Con[data["scenarioname"]] = all_devs
    return all_devs_Con

def test_cluster_setup_devices():
    all_devs = ['BOI', 'HP', 'PV', 'Bat']
    cap = {}
    for device in all_devs:
        cap[device] = 10
    return cap

def test_run_optim():
    data1 = {'scenarioname': 'District1'}
    data2 = {'scenarioname': 'District2'}
    dataCon= {}
    dataCon["Districts"] = [data1, data2]

    capCon = {}
    for data in dataCon["Districts"]:
        capCon[data["scenarioname"]] = test_cluster_setup_devices()
    return dataCon, capCon


if __name__ == '__main__':
    # smalltel_main=test_network()
    # print(f"smalltel_network: {smalltel_main}")

    # dataCon, capCon=test_add_Vars()
    # print(f"dataCon is: {dataCon}")
    # print(f"capCon is: {capCon}")

    # all_devs_Con_main=testlist()
    # print(f"all_devs_main is: {all_devs_Con_main}")

    dataCon_main, capCon_main=test_run_optim()
    print(f"dataCon_main is: {dataCon_main}")
    print(f"capCon_main is: {capCon_main}")
