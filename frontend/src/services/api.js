// API client interface connecting frontend to NISAR backend services.
const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function request(path, options) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const getHealth = () => request('/health');
export const getDomainStatus = (domain) => request(`/api/v1/${domain}/status`);
export const analyze = (domain, payload) =>
  request(`/api/v1/${domain}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

// Multi-Temporal Forest Visualization APIs
export const getForestLayers = () => request('/api/v1/forests/layers');
export const getForestBoundaries = () => request('/api/v1/forests/boundaries');
export const getForestTemporalMetrics = () => request('/api/v1/forests/temporal-metrics');
export const inspectForestPixel = (lon, lat) =>
  request(`/api/v1/forests/pixel-inspect?lon=${encodeURIComponent(lon)}&lat=${encodeURIComponent(lat)}`);
export const getLayerImageUrl = (layerId, aoiClip = 'none') =>
  `${BASE}/api/v1/forests/layers/${layerId}?aoi_clip=${encodeURIComponent(aoiClip)}`;
