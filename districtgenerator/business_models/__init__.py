# -*- coding: utf-8 -*-

from .Referenz    import ReferenzBM
from .Waermecontracting  import WaermecontractingBM
from .Waermegenossenschaft  import WaermegenossenschaftBM
from .WaermecontractingGGV  import WaermecontractingGGVBM
from .WaermecontractingKundenanlage import WaermecontractingKundenanlageBM

BM_REGISTRY = {
    "ref_boi":                        ReferenzBM,
    "ref_wp":                         ReferenzBM,  # gleiche Klasse, anderer Config-Key
    "waermecontracting":              WaermecontractingBM,
    "waermecontracting_ggv":          WaermecontractingGGVBM,
    "waermecontracting_kundenanlage": WaermecontractingKundenanlageBM,
    "waermegenossenschaft":           WaermegenossenschaftBM,

}

__all__ = [
    "BM_REGISTRY",
    "ReferenzBM",
    "WaermecontractingBM",
    "WaermecontractingGGVBM",
    "WaermecontractingKundenanlageBM",
    "WaermegenossenschaftBM",
]