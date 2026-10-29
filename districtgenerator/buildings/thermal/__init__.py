"""
Thermal building models. Each model pairs an envelope with its simulation.

The model type strings are the values of ``THERMAL_MODEL_TYPE`` in the config.
"""
from districtgenerator.buildings.thermal.model_5r1c import envelope as _envelope_5r1c
from districtgenerator.buildings.thermal.model_5r1c import simulation as _simulation_5r1c
from districtgenerator.buildings.thermal.model_7r2c import envelope as _envelope_7r2c
from districtgenerator.buildings.thermal.model_7r2c import simulation as _simulation_7r2c
from districtgenerator.buildings.thermal.model_four_elements import envelope as _envelope_four_elements
from districtgenerator.buildings.thermal.model_four_elements import simulation as _simulation_four_elements

THERMAL_MODELS = {
    "5R1C": (_envelope_5r1c.Envelope, _simulation_5r1c),
    "7R2C": (_envelope_7r2c.Envelope, _simulation_7r2c),
    "FourElements": (_envelope_four_elements.Envelope, _simulation_four_elements),
}


def _lookup(model_type):
    try:
        return THERMAL_MODELS[model_type]
    except KeyError:
        raise ValueError(f"Unknown thermal_model_type: {model_type}") from None


def get_envelope_class(model_type):
    """Return the envelope class of a thermal model type."""
    return _lookup(model_type)[0]


def get_simulation(model_type):
    """Return the simulation module of a thermal model type, providing calc and calc_night_setback."""
    return _lookup(model_type)[1]


def prepare_simulation(envelope, model_type, site, gains):
    """Compute the model parameters that depend on weather and internal gains, before simulating."""
    _lookup(model_type)
    if model_type == "5R1C":
        envelope.calcNormativeProperties(site["SunRad"], gains)
    else:
        # VDI 6007 models: model parameters, then equivalent outdoor temperature
        envelope._VDI6007_params()
        envelope.calc_theta_eq(site, gains)
