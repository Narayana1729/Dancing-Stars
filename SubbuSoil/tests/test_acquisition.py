from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.acquisition import AcquiredObservation, AcquisitionRequest, AccessMode
from app.schemas.discovery import AOIInfo, DiscoveryResponse, Observation, TrackGroup
from app.services.acquisition import (
    AcquisitionError,
    _verify,
    open_sme2_grids,
    select_observations,
)

client = TestClient(app)
LOCAL_H5 = next(Path(__file__).resolve().parents[2].joinpath("data").glob("*SME2*.h5"), None)


def _obs(track_key, day, cov=1.0):
    t = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(days=day)
    gid = f"G_{track_key}_{day:03d}"
    return Observation(
        granule_id=gid, start_time=t, stop_time=t, flight_direction="ASCENDING",
        track=1, frame=1, cycle=day // 12, orbit=None, track_key=track_key, crid="P05023",
        https_url=f"https://x/{gid}.h5", s3_url=None, size_bytes=1, aoi_coverage=cov,
        footprint={"type": "Polygon", "coordinates": []},
    )


def _discovery():
    a = [_obs("A_156_011", d) for d in (0, 12, 24, 36, 48)]
    d = [_obs("D_077_079", d, 0.9) for d in (6, 18)]
    single = [_obs("A_084_011", 3, 1.0)]
    obs = a + d + single
    tracks = [
        TrackGroup(track_key="A_084_011", flight_direction="A", track=84, frame=11,
                   n_observations=1, mean_aoi_coverage=1.0, granule_ids=[o.granule_id for o in single]),
        TrackGroup(track_key="A_156_011", flight_direction="A", track=156, frame=11,
                   n_observations=5, mean_aoi_coverage=1.0, granule_ids=[o.granule_id for o in a]),
        TrackGroup(track_key="D_077_079", flight_direction="D", track=77, frame=79,
                   n_observations=2, mean_aoi_coverage=0.9, granule_ids=[o.granule_id for o in d]),
    ]
    aoi = AOIInfo(wkt="", bounds=[0, 0, 1, 1], area_km2=1)
    return DiscoveryResponse(aoi=aoi, start_date="2026-08-01", end_date="2026-10-01",
                             n_observations=len(obs), observations=obs, tracks=tracks)


def _req(**kw):
    return AcquisitionRequest(bbox=[78, 18, 79, 19], **kw)


def test_default_picks_best_track_with_two_obs_first_last():
    key, picked = select_observations(_discovery(), _req())
    assert key == "A_156_011"  # skips the single-observation track
    assert [o.granule_id[-3:] for o in picked] == ["000", "048"]


def test_strategies():
    _, latest = select_observations(_discovery(), _req(strategy="latest", max_observations=3))
    assert [o.granule_id[-3:] for o in latest] == ["024", "036", "048"]
    _, spread = select_observations(_discovery(), _req(max_observations=3))
    assert [o.granule_id[-3:] for o in spread] == ["000", "024", "048"]
    _, d = select_observations(_discovery(), _req(track_key="D_077_079"))
    assert {o.track_key for o in d} == {"D_077_079"}


def test_explicit_granules_must_share_track():
    with pytest.raises(AcquisitionError, match="several tracks"):
        select_observations(_discovery(), _req(granule_ids=["G_A_156_011_000", "G_D_077_079_006"]))
    with pytest.raises(AcquisitionError, match="not found"):
        select_observations(_discovery(), _req(granule_ids=["nope", "G_A_156_011_000"]))
    key, picked = select_observations(_discovery(), _req(granule_ids=["G_A_156_011_036", "G_A_156_011_000"]))
    assert [o.granule_id[-3:] for o in picked] == ["000", "036"]  # sorted by time


def test_unknown_track_rejected():
    with pytest.raises(AcquisitionError):
        select_observations(_discovery(), _req(track_key="A_084_011"))  # only 1 obs


@pytest.mark.skipif(LOCAL_H5 is None, reason="no local SME2 file in ../data")
def test_open_and_verify_local_file():
    with open_sme2_grids(str(LOCAL_H5)) as ds:
        assert {"soilMoisture", "soilMoistureUncertainty", "retrievalQualityFlag"} <= set(ds.data_vars)
        assert ds.soilMoisture.shape == (ds.sizes["yCoordinates"], ds.sizes["xCoordinates"])
    item = AcquiredObservation(
        granule_id=LOCAL_H5.stem, start_time=datetime.now(timezone.utc), track_key="A_156_011",
        aoi_coverage=1, https_url="", mode=AccessMode.DOWNLOAD, local_path=str(LOCAL_H5),
    )
    item = _verify(item)
    assert item.verified, item.error
    assert item.epsg == 6933


@pytest.mark.live
def test_live_acquire_stream():
    r = client.post("/api/v1/acquisition/acquire", json={
        "bbox": [78.86, 18.27, 79.36, 18.77], "start_date": "2026-08-01", "end_date": "2026-11-11",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_observations"] == 2 and body["days_spanned"] > 0
    assert all(o["verified"] for o in body["observations"]), body["observations"]
    assert len({o["track_key"] for o in body["observations"]}) == 1
