"""
Deprecated package kept for compatibility.

``from districtgenerator.classes import Datahandler`` keeps working. New code
imports from ``districtgenerator`` and its workflow packages instead.
"""
from districtgenerator.utilities import compat as _compat

_compat.install()

from districtgenerator.datahandler import Datahandler
from districtgenerator.buildings.thermal.model_5r1c.envelope import Envelope as Envelope_5R1C
from districtgenerator.buildings.thermal.model_7r2c.envelope import Envelope as Envelope_7R2C
from districtgenerator.buildings.thermal.model_four_elements.envelope import Envelope as Envelope_FourElements
from districtgenerator.environment.solar import Sun
from districtgenerator.buildings.profiles.users import Users
from districtgenerator.buildings.profiles.profiles import Profiles
from districtgenerator.buildings.typology.non_residential import NonResidential
from districtgenerator.buildings.profiles.lighting import LightingModelConfiguration
from districtgenerator.buildings.profiles.non_residential_electricity import ElectricityProfile
