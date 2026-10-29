"""Technologies, building and central energy systems, heat grid and wind turbines."""


def __getattr__(name):
    # Lazy access keeps old imports such as ``from districtgenerator.classes.system import BES`` working
    if name == "BES":
        from districtgenerator.energy_systems.building_energy_system import BES
        return BES
    if name == "CES":
        from districtgenerator.energy_systems.central_energy_system import CES
        return CES
    raise AttributeError(f"module 'districtgenerator.energy_systems' has no attribute '{name}'")
