"""Technologies, building and central energy systems, heat grid and wind turbines."""


def __getattr__(name):
    """
    Resolve package-level energy-system class imports lazily.

    Lazy access allows ``from districtgenerator.energy_systems import BES`` without importing
    the energy-system modules when the package is loaded.

    Parameters
    ----------
    name : str
        Requested public class name: ``"BES"`` or ``"CES"``.

    Returns
    -------
    type
        Building or central energy-system class, imported only when requested.
    """
    if name == "BES":
        from districtgenerator.energy_systems.building_energy_system import BES
        return BES
    if name == "CES":
        from districtgenerator.energy_systems.central_energy_system import CES
        return CES
    raise AttributeError(f"module 'districtgenerator.energy_systems' has no attribute '{name}'")
