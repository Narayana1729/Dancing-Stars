# Architecture

```
backend/app/
  main.py            app factory, CORS, /health, 501 handler
  api_router.py      /api/v1 router (domains + /data-products)
  config.py          env-based Settings (stdlib only)
  core/              exceptions (NotYetImplemented); database.py, security.py are empty
  shared/
    satellite/       SarProduct, Mission, SceneQuery, SatelliteProvider (ABC)
    raster/          RasterLoader, MetadataExtractor (ABC)
    preprocessing/   Preprocessor, TemporalComparator (ABC)
    geospatial/      BoundingBox (validated), GeoTransformer (ABC)
    analysis.py      ChangeDetector (ABC)
  domains/{forests,wildfires}/
    acquisition processing algorithms models services api
backend/tests/       pytest suite
frontend/src/        App, components, mock/, services/api.js, hooks/
```

| Part | Status |
|---|---|
| FastAPI app, health, CORS, routing, config | Implemented, tested |
| `BoundingBox`, `SceneQuery` validation | Implemented, tested |
| Product-selection policy (`/api/v1/data-products`) | Implemented, tested |
| All ABCs (provider, loader, extractor, preprocessing, detectors) | Interfaces only |
| `/api/v1/{forests,wildfires}/analyze` | Returns 501 by design |
| Domain `acquisition/processing/models/services` packages | Empty placeholders |
| `core/database.py`, `core/security.py`, `shared/utilities`, `shared/visualization`, `backend/app/domains/domain_3` | Empty / unused leftovers |

Frontend mock data is isolated in `frontend/src/mock/mockDomains.js`.

