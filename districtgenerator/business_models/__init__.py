# -*- coding: utf-8 -*-

from .reference    import ReferenceBM
from .contracting  import ContractingBM
from .cooperative  import CooperativeBM
from .mietstrom  import MieterstromBM
from .kundenanlage import KundenanlageBM

BM_REGISTRY = {
    "reference":    ReferenceBM,
    "contracting":  ContractingBM,
    "cooperative":  CooperativeBM,
    "mieterstrom":  MieterstromBM,
    "kundenanlage": KundenanlageBM,
}

__all__ = [
    "BM_REGISTRY",
    "ReferenceBM",
    "ContractingBM",
    "CooperativeBM",
    "MieterstromBM",
    "KundenanlageBM",
]