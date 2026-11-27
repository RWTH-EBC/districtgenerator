# -*- coding: utf-8 -*-
"""
Tests of the option FAST_EL_PROFILES (numba-compiled FastElectricityProfile of richardsonpy).

Tests that need numba are skipped without it. Run with: python -m pytest tests/test_fast_el_profiles.py
"""
import logging
import os
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import richardsonpy.classes.fast_el_load_wrapper as fast_wrap
import richardsonpy.classes.stochastic_el_load_wrapper as wrap

from districtgenerator.buildings.profiles import users
from districtgenerator.config.settings import Scenario
from test_results import REFERENCE, demand_profiles, run_example

needs_numba = pytest.mark.skipif(not fast_wrap.FAST_AVAILABLE, reason="numba is not installed")


@pytest.fixture
def users_log(caplog):
    """Capture the records of the users logger (the districtgenerator logger may not propagate to root)."""
    logger = logging.getLogger(users.__name__)
    logger.addHandler(caplog.handler)
    caplog.handler.setLevel(logging.DEBUG)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def test_scenario_default_is_off(monkeypatch):
    monkeypatch.delenv("FAST_EL_PROFILES", raising=False)
    assert Scenario().fast_el_profiles is False


def test_scenario_reads_env(monkeypatch):
    monkeypatch.setenv("FAST_EL_PROFILES", "true")
    assert Scenario().fast_el_profiles is True


def test_profile_class_off_is_original():
    assert users.electricity_profile_class(False) is wrap.ElectricityProfile


@needs_numba
def test_profile_class_on_is_fast():
    assert users.electricity_profile_class(True) is fast_wrap.FastElectricityProfile


def test_profile_class_fallback_warns_once(monkeypatch, users_log):
    monkeypatch.setattr(fast_wrap, "FAST_AVAILABLE", False)
    monkeypatch.setattr(users, "_fast_fallback_logged", False)
    assert users.electricity_profile_class(True) is wrap.ElectricityProfile
    assert users.electricity_profile_class(True) is wrap.ElectricityProfile
    # A record may be captured twice (logger handler and root), so count unique records
    warnings = list({id(r): r for r in users_log.records if r.levelno == logging.WARNING}.values())
    assert len(warnings) == 1
    assert "FAST_EL_PROFILES" in warnings[0].getMessage()


@pytest.mark.parametrize("enabled, available, expected_calls", [
    (False, True, 0),
    (True, False, 0),
    (True, True, 1),
])
def test_warm_up_only_when_used(monkeypatch, enabled, available, expected_calls):
    calls = []
    monkeypatch.setattr(fast_wrap, "FAST_AVAILABLE", available)
    monkeypatch.setattr(fast_wrap, "warm_up", lambda: calls.append(1) or 0.0)
    users.warm_up_fast_el_profiles(enabled)
    assert len(calls) == expected_calls


@pytest.mark.parametrize("fast", [False, pytest.param(True, marks=needs_numba)])
def test_users_creates_wrapper_class(fast):
    user = users.Users(building="MFH", area=600, year_of_construction=1990, retrofit=0, fast_el_profiles=fast)
    expected = fast_wrap.FastElectricityProfile if fast else wrap.ElectricityProfile
    assert user.nb_flats > 1
    assert len(user.el_wrapper) == user.nb_flats
    assert all(type(wrapper) is expected for wrapper in user.el_wrapper)


@needs_numba
def test_e5_fast_reproducible_with_flat_multiprocessing():
    """
    With a random seed, FAST_EL_PROFILES gives the same profiles with and without flat multiprocessing.

    The electricity demand is normalized to the annual demand, so the totals match the reference of the
    original model, while the profiles themselves differ (the fast model is not bit-identical).
    """
    profiles = {}
    for flat_parallelization in ("none", "multiprocessing"):
        overrides = {"FAST_EL_PROFILES": "True", "FLAT_PARALLELIZATION": flat_parallelization,
                     "FLAT_MAX_WORKERS": "2"}
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e5_generate_demands", "example5_generate_demands", result_path, overrides)
        assert data.fast_el_profiles is True
        profiles[flat_parallelization] = demand_profiles(data)

    pd.testing.assert_frame_equal(profiles["none"], profiles["multiprocessing"], check_exact=True)

    reference = pd.read_csv(REFERENCE / "e5_profiles.csv", index_col=0)
    elec_columns = [c for c in reference.columns if c.endswith("_elec")]
    fast = profiles["none"][elec_columns].to_numpy(dtype=float)
    original = reference[elec_columns].to_numpy(dtype=float)
    np.testing.assert_allclose(np.nansum(fast, axis=0), np.nansum(original, axis=0), rtol=0.01)
    assert not np.allclose(fast, original, equal_nan=True)
