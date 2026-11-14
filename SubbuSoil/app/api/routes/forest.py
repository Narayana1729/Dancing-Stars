import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.config import get_settings
from app.services import forest_analysis as F

router = APIRouter(prefix="/forest", tags=["forest (GCOV)"])


def _run_dir(run_id: str):
    if not all(c.isalnum() or c in "-_" for c in run_id) or len(run_id) > 80:
        raise HTTPException(status_code=404, detail="invalid run id")
    run = get_settings().data_dir / "forest" / "runs" / run_id
    if not (run / "report.json").exists():
        raise HTTPException(status_code=404, detail=f"forest run {run_id} not found")
    return run


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@router.get("/runs")
def list_runs():
    root = get_settings().data_dir / "forest" / "runs"
    if not root.exists():
        return {"runs": []}
    runs = []
    for d in sorted(root.iterdir()):
        if (d / "report.json").exists():
            rep = _read_json(d / "report.json")
            runs.append({"run_id": d.name, "track_key": rep["track_key"], "n_dates": rep["n_dates"],
                         "has_change": (d / "forest_change" / "summary.json").exists()})
    return {"runs": runs}


@router.get("/runs/{run_id}")
def run_detail(run_id: str):
    """Preparation report, change summary, validation and the plain-language explanation."""
    run = _run_dir(run_id)
    summary = _read_json(run / "forest_change" / "summary.json")
    validation = _read_json(run / "forest_change" / "validation.json")
    out = {"run_id": run_id, "report": _read_json(run / "report.json"), "summary": summary,
           "validation": validation, "layers": list(F.FOREST_LAYERS)}
    if summary:
        out["explanation"] = F.forest_explanation(summary, validation)
    return out


@router.get("/runs/{run_id}/regions")
def regions(run_id: str):
    run = _run_dir(run_id)
    path = run / "forest_change" / "disturbances.geojson"
    if not path.exists():
        raise HTTPException(status_code=404, detail="run forest change first")
    return _read_json(path)


@router.get("/runs/{run_id}/layers/{layer}/overlay")
def layer_overlay(run_id: str, layer: str):
    _run_dir(run_id)
    if layer not in F.FOREST_LAYERS:
        raise HTTPException(status_code=404, detail="unknown layer")
    return F.forest_overlay_bounds(run_id, layer)


@router.get("/runs/{run_id}/layers/{layer}.png", responses={200: {"content": {"image/png": {}}}})
def layer_png(run_id: str, layer: str):
    _run_dir(run_id)
    if layer not in F.FOREST_LAYERS:
        raise HTTPException(status_code=404, detail="unknown layer")
    return Response(content=F.forest_layer_png(run_id, layer), media_type="image/png")


@router.post("/runs/{run_id}/change")
def run_change(run_id: str):
    """Steps 9 and 10 for a prepared run (about 1 minute: reads the WorldCover tile)."""
    _run_dir(run_id)
    return F.analyse_forest(run_id)


@router.post("/runs/{run_id}/validate")
def run_validate(run_id: str):
    """Step 11: check candidate patches against Sentinel-2 NDVI (about 3 minutes)."""
    _run_dir(run_id)
    try:
        return F.validate_disturbances(run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=409, detail=str(e))
