import numpy as np
import pandas as pd
import pytest

from districtgenerator.classes.datahandler import (TS_SUFFIX, TS_SUFFIX_LEGACY, _ts_read_path,
                                                   _ts_write_path, _write_ts)


def _df(n=8760):
    rng = np.random.default_rng(0)
    return pd.DataFrame({"timestep": np.arange(n, dtype=float), "elec": rng.random(n) * 1000,
                         "dhw": rng.random(n) * 500})


def test_write_creates_compressed_file_and_roundtrips(tmp_path):
    df = _df()
    _write_ts(df, tmp_path, "0_MFH")
    path = tmp_path / f"0_MFH{TS_SUFFIX}"
    assert path.exists()
    back = pd.read_csv(_ts_read_path(tmp_path, "0_MFH"), sep=";")
    assert list(back.columns) == list(df.columns)
    np.testing.assert_allclose(back["elec"], df["elec"], atol=5e-4)  # 3 decimals


def test_compressed_file_is_much_smaller(tmp_path):
    df = _df()
    df.to_csv(tmp_path / "plain.csv", sep=";", index=False)  # previous format
    _write_ts(df, tmp_path, "0_MFH")
    assert (tmp_path / f"0_MFH{TS_SUFFIX}").stat().st_size < (tmp_path / "plain.csv").stat().st_size / 3


def test_read_path_falls_back_to_legacy_file(tmp_path):
    _df(10).to_csv(tmp_path / f"0_MFH{TS_SUFFIX_LEGACY}", sep=";", index=False)
    assert _ts_read_path(tmp_path, "0_MFH").endswith(TS_SUFFIX_LEGACY)


def test_read_path_prefers_compressed_file(tmp_path):
    _df(10).to_csv(tmp_path / f"0_MFH{TS_SUFFIX_LEGACY}", sep=";", index=False)
    _df(10).to_csv(tmp_path / f"0_MFH{TS_SUFFIX}", sep=";", index=False, compression="gzip")
    assert _ts_read_path(tmp_path, "0_MFH").endswith(TS_SUFFIX)


def test_write_removes_legacy_file(tmp_path):
    _df(10).to_csv(tmp_path / f"0_MFH{TS_SUFFIX_LEGACY}", sep=";", index=False)
    _write_ts(_df(10), tmp_path, "0_MFH")
    assert not (tmp_path / f"0_MFH{TS_SUFFIX_LEGACY}").exists()
    assert (tmp_path / f"0_MFH{TS_SUFFIX}").exists()


def test_write_path_is_compressed_by_default(tmp_path):
    assert _ts_write_path(str(tmp_path), "0_MFH").endswith(TS_SUFFIX)


def test_savetxt_with_gz_suffix_is_compressed_and_readable(tmp_path):
    # Generation profiles are written with np.savetxt; the .gz suffix alone enables compression
    profile = np.r_[np.zeros(4000), np.linspace(0, 5000, 4760)]
    np.savetxt(tmp_path / "0_MFH_generationPV.csv.gz", profile, delimiter=";", fmt="%.2f")
    np.savetxt(tmp_path / "plain.csv", profile, delimiter=";", fmt="%.2f")
    assert (tmp_path / "0_MFH_generationPV.csv.gz").stat().st_size < (tmp_path / "plain.csv").stat().st_size / 3
    np.testing.assert_allclose(np.loadtxt(tmp_path / "0_MFH_generationPV.csv.gz", delimiter=";"), profile, atol=5e-3)
    np.testing.assert_allclose(pd.read_csv(tmp_path / "0_MFH_generationPV.csv.gz", sep=";", header=None)[0],
                               profile, atol=5e-3)


from districtgenerator.classes.datahandler import _save_generation_profile


def test_write_uncompressed_when_switched_off(tmp_path):
    _write_ts(_df(10), tmp_path, "0_MFH", compress=False)
    assert (tmp_path / f"0_MFH{TS_SUFFIX_LEGACY}").exists()
    assert not (tmp_path / f"0_MFH{TS_SUFFIX}").exists()
    assert _ts_read_path(tmp_path, "0_MFH").endswith(TS_SUFFIX_LEGACY)


def test_uncompressed_write_removes_stale_compressed_file(tmp_path):
    # readers prefer .gz, so an old compressed file must not shadow freshly written plain results
    _write_ts(_df(10), tmp_path, "0_MFH", compress=True)
    _write_ts(_df(10) * 2, tmp_path, "0_MFH", compress=False)
    assert not (tmp_path / f"0_MFH{TS_SUFFIX}").exists()
    back = pd.read_csv(_ts_read_path(tmp_path, "0_MFH"), sep=";")
    assert back["elec"].iloc[0] == pytest.approx(_df(10)["elec"].iloc[0] * 2, abs=1e-3)


@pytest.mark.parametrize("compress, suffix", [(True, ".csv.gz"), (False, ".csv")])
def test_generation_profile_follows_switch(tmp_path, compress, suffix):
    other = ".csv" if compress else ".csv.gz"
    np.savetxt(tmp_path / f"0_MFH_generationPV{other}", np.zeros(5), fmt="%.2f")  # stale file of the other format
    _save_generation_profile(str(tmp_path), "0_MFH", "PV", np.arange(5.0), compress=compress)
    assert (tmp_path / f"0_MFH_generationPV{suffix}").exists()
    assert not (tmp_path / f"0_MFH_generationPV{other}").exists()
    np.testing.assert_allclose(np.loadtxt(tmp_path / f"0_MFH_generationPV{suffix}"), np.arange(5.0))


def test_compress_profiles_flag_default_and_env(monkeypatch):
    from districtgenerator.data_handling.config import flags
    assert flags().compress_profiles is True
    monkeypatch.setenv("COMPRESS_PROFILES", "False")
    assert flags().compress_profiles is False
