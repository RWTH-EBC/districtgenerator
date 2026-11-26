"""districtgenerator: energy profile generation and optimization of districts."""
import logging

from districtgenerator.utilities.log import set_progress, setup_logging

__version__ = '1.0.1'

__all__ = ["Datahandler", "setup_logging", "set_progress"]

# As a library, the districtgenerator does not print anything unless logging is set up by the application
# or with setup_logging()
logging.getLogger(__name__).addHandler(logging.NullHandler())


def __getattr__(name):
    # Lazy import keeps light submodule imports, for example in worker processes, fast
    if name == "Datahandler":
        from districtgenerator.datahandler import Datahandler
        return Datahandler
    raise AttributeError(f"module 'districtgenerator' has no attribute '{name}'")
