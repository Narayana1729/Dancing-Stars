import json

import numpy as np
import pytest
import xarray as xr

from app.services import results as R
from app.services.analysis import analyse_run
from app.services.change import ChangeParams, pair_indices
from tests.test_analysis import make_stack

RUN = "multi00000001"


def three_dates():
    """make_stack() has two dates; add a third, later date (copy of the second)."""
    s = make_stack()
    extra = s.isel(time=[1]).copy(deep=True).assign_coords(
        time=np.array(["2026-11-01T00:09:48"], "datetime64[ns]"),
        granule_id=("time", ["G3"]),
    )
    return xr.concat([s, extra], dim="time")


@pytest.fixture
def multi_root(tmp_path, monkeypatch):
    settings = type("S", (), {"data_dir": tmp_path})()
    monkeypatch.setattr("app.services.analysis.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.results.get_settings", lambda: settings)
    run = tmp_path / "processed" / RUN
    run.mkdir(parents=True)
    three_dates().to_netcdf(run / "stack.nc", engine="h5netcdf")
    dates = ["2026-08-12T00:09:48+00:00", "2026-10-11T00:09:48+00:00", "2026-11-01T00:09:48+00:00"]
    manifest = {"request": {"wkt": "POLYGON((0 0,1 0,1 1,0 0))"}, "result": {
        "track_key": "A_156_011", "n_observations": 3,
        "aoi": {"wkt": "", "bounds": [0, 0, 1, 1], "area_km2": 1.0},
        "n_common_valid_pixels": 1, "observations": [{"start_time": d} for d in dates]}}
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_pair_modes_over_three_dates():
    assert pair_indices(3, "first_last") == [(0, 2)]
    assert pair_indices(3, "consecutive") == [(0, 1), (1, 2)]
    assert len(pair_indices(3, "all")) == 3


def test_consecutive_pairs_are_analysed_in_date_order(multi_root):
    out = analyse_run(RUN, ChangeParams(pairs="consecutive"))
    spans = [(p["stats"]["t1"][:10], p["stats"]["t2"][:10]) for p in out["pairs"]]
    assert spans == [("2026-08-12", "2026-10-11"), ("2026-10-11", "2026-11-01")]
    assert all(p["stats"]["n_compared"] > 0 for p in out["pairs"])


def test_each_pair_is_stored_separately(multi_root):
    analyse_run(RUN, ChangeParams(pairs="consecutive"))
    pairs = R.run_detail(RUN)["result"]["pairs"]
    assert len(pairs) == 2 and len(set(pairs)) == 2
    history = R.history(RUN)["series"]
    assert [h["time"][:10] for h in history] == ["2026-08-12", "2026-10-11", "2026-11-01"]
