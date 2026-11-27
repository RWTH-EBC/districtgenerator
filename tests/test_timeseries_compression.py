import numpy as np
import pandas as pd

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


def test_write_path_is_always_compressed(tmp_path):
    assert _ts_write_path(str(tmp_path), "0_MFH").endswith(TS_SUFFIX)
