Configuration
=============

.. automodule:: districtgenerator.config

All modeling assumptions have default values in :mod:`districtgenerator.config.settings`. A configuration file
overrides them for a scenario:

.. code-block:: python

   from districtgenerator import Datahandler

   data = Datahandler(scenario_name="example_decentral", env_path=".env.CONFIG.EXAMPLE")

A relative ``env_path`` is looked up in ``districtgenerator/data/config``, an absolute path is used as given.
Use ``.env.CONFIG.EXAMPLE`` as a reference and save own assumptions in a new file, e.g. ``.env.CONFIG.MYDISTRICT``.
Only the parameters that differ from the defaults have to be set in the file.

The name of a variable in the ``.env`` file is the field name of the configuration classes below, written in capital
letters:

- Fields of :class:`~districtgenerator.config.settings.DecentralDeviceConfig` start with ``D_``, fields of
  :class:`~districtgenerator.config.settings.CentralDeviceConfig` with ``C_``, e.g. ``C_PV__FEASIBLE=True``.
- Parameters of a group are separated by a double underscore and collected in a dictionary,
  e.g. ``SOLVER_OPTIONS__TIME_LIMIT=600`` or ``COLORS__PRIMARY_COLOR=#368427``.
- Fixed data such as the file format of the TRY weather data, the cooling load zones and the soil properties are
  class constants and cannot be changed in the ``.env`` file.

The configuration classes are combined in :class:`~districtgenerator.config.settings.GlobalConfig`, which
:func:`~districtgenerator.config.settings.load_global_config` creates from a ``.env`` file.

districtgenerator.config.settings
---------------------------------

.. automodule:: districtgenerator.config.settings
   :members:
   :undoc-members:
   :show-inheritance:
