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

if __name__ == '__main__':
    smalltel_main=test_network()
    print(f"smalltel_network: {smalltel_main}")