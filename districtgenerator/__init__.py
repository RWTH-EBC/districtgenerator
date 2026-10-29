"""districtgenerator: energy profile generation and optimization of districts."""
__version__ = '0.1.2'

__all__ = ["Datahandler"]


def __getattr__(name):
    # Lazy import keeps light submodule imports, for example in worker processes, fast
    if name == "Datahandler":
        from districtgenerator.datahandler import Datahandler
        return Datahandler
    raise AttributeError(f"module 'districtgenerator' has no attribute '{name}'")
