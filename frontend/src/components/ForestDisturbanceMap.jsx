import React, { useState, useEffect, useRef, useCallback } from 'react';
import { getForestLayers, getForestBoundaries, getLayerImageUrl, inspectForestPixel } from '../services/api.js';

// Exact spatial bounds for Similipal raster grid
const BOUNDS = {
  west: 86.050355,
  south: 21.449910,
  east: 86.650337,
  north: 22.049976,
};

export default function ForestDisturbanceMap() {
  const [layers, setLayers] = useState([]);
  const [activeLayerId, setActiveLayerId] = useState('delta_hv');
  const [aoiClip, setAoiClip] = useState('none');
  const [opacity, setOpacity] = useState(0.9);
  const [showBoundaries, setShowBoundaries] = useState(true);
  const [boundariesData, setBoundariesData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Pan & Zoom state
  const [viewState, setViewState] = useState({
    zoom: 1.0,
    offsetX: 0,
    offsetY: 0,
  });
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0 });

  // Hover coordinate & sampled pixel state
  const [cursorPos, setCursorPos] = useState(null);
  const [inspectedPixel, setInspectedPixel] = useState(null);
  const [inspectLoading, setInspectLoading] = useState(false);

  const canvasRef = useRef(null);
  const imageCacheRef = useRef({});

  // 1. Load layers catalog and vector boundaries on mount
  useEffect(() => {
    let isMounted = true;
    async function init() {
      try {
        setLoading(true);
        setError(null);
        const [layersData, boundsData] = await Promise.all([
          getForestLayers(),
          getForestBoundaries().catch(() => null),
        ]);
        if (isMounted) {
          setLayers(layersData.layers || []);
          setBoundariesData(boundsData);
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || 'Failed to initialize forest visualization.');
          setLoading(false);
        }
      }
    }
    init();
    return () => { isMounted = false; };
  }, []);

  // 2. Preload active raster image
  const [activeImage, setActiveImage] = useState(null);
  useEffect(() => {
    if (!activeLayerId || activeLayerId === 'boundary') return;
    const url = getLayerImageUrl(activeLayerId, aoiClip);
    if (imageCacheRef.current[url]) {
      setActiveImage(imageCacheRef.current[url]);
      return;
    }
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = url;
    img.onload = () => {
      imageCacheRef.current[url] = img;
      setActiveImage(img);
    };
    img.onerror = () => {
      setError(`Failed to load layer imagery for ${activeLayerId}`);
    };
  }, [activeLayerId, aoiClip]);

  // Coordinate projections between WGS84 and Canvas coordinate space
  const projectLonLatToCanvas = useCallback((lon, lat, width, height, vs) => {
    // Normalization to [0, 1] relative to BOUNDS
    const normX = (lon - BOUNDS.west) / (BOUNDS.east - BOUNDS.west);
    const normY = (BOUNDS.north - lat) / (BOUNDS.north - BOUNDS.south);

    // Center and scale with zoom/pan
    const baseW = width * 0.88;
    const baseH = height * 0.88;
    const originX = (width - baseW) / 2 + vs.offsetX;
    const originY = (height - baseH) / 2 + vs.offsetY;

    const x = originX + normX * baseW * vs.zoom;
    const y = originY + normY * baseH * vs.zoom;
    return { x, y };
  }, []);

  const projectCanvasToLonLat = useCallback((x, y, width, height, vs) => {
    const baseW = width * 0.88;
    const baseH = height * 0.88;
    const originX = (width - baseW) / 2 + vs.offsetX;
    const originY = (height - baseH) / 2 + vs.offsetY;

    const normX = (x - originX) / (baseW * vs.zoom);
    const normY = (y - originY) / (baseH * vs.zoom);

    const lon = BOUNDS.west + normX * (BOUNDS.east - BOUNDS.west);
    const lat = BOUNDS.north - normY * (BOUNDS.north - BOUNDS.south);
    return { lon, lat };
  }, []);

  // Draw Canvas
  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    // Clear background
    ctx.fillStyle = '#090d16';
    ctx.fillRect(0, 0, width, height);

    // Draw cartographic background grid
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    const lonStep = 0.1;
    const latStep = 0.1;

    for (let lon = Math.floor(BOUNDS.west * 10) / 10; lon <= BOUNDS.east; lon += lonStep) {
      const p1 = projectLonLatToCanvas(lon, BOUNDS.south, width, height, viewState);
      const p2 = projectLonLatToCanvas(lon, BOUNDS.north, width, height, viewState);
      ctx.beginPath();
      ctx.moveTo(p1.x, 0);
      ctx.lineTo(p1.x, height);
      ctx.stroke();

      ctx.fillStyle = '#475569';
      ctx.font = '10px monospace';
      ctx.fillText(`${lon.toFixed(1)}°E`, p1.x + 4, height - 8);
    }

    for (let lat = Math.floor(BOUNDS.south * 10) / 10; lat <= BOUNDS.north; lat += latStep) {
      const p = projectLonLatToCanvas(BOUNDS.west, lat, width, height, viewState);
      ctx.beginPath();
      ctx.moveTo(0, p.y);
      ctx.lineTo(width, p.y);
      ctx.stroke();

      ctx.fillStyle = '#475569';
      ctx.font = '10px monospace';
      ctx.fillText(`${lat.toFixed(1)}°N`, 8, p.y - 4);
    }

    // Draw active raster layer
    const nw = projectLonLatToCanvas(BOUNDS.west, BOUNDS.north, width, height, viewState);
    const se = projectLonLatToCanvas(BOUNDS.east, BOUNDS.south, width, height, viewState);
    const rasterW = se.x - nw.x;
    const rasterH = se.y - nw.y;

    if (activeImage && activeLayerId !== 'boundary') {
      ctx.save();
      ctx.globalAlpha = opacity;
      ctx.imageSmoothingEnabled = false; // preserve crisp SAR pixels
      ctx.drawImage(activeImage, nw.x, nw.y, rasterW, rasterH);
      ctx.restore();
    }

    // Draw bounding box border of the NISAR swath
    ctx.strokeStyle = '#38bdf844';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(nw.x, nw.y, rasterW, rasterH);

    // Draw Similipal boundaries GeoJSON if enabled
    if (showBoundaries && boundariesData?.features) {
      boundariesData.features.forEach((feature) => {
        const isCore = feature.id === 'similipal_core';
        const color = isCore ? '#f59e0b' : '#10b981';
        const fillColor = isCore ? 'rgba(245, 158, 11, 0.08)' : 'rgba(16, 185, 129, 0.05)';

        ctx.save();
        ctx.strokeStyle = color;
        ctx.fillStyle = fillColor;
        ctx.lineWidth = isCore ? 2 : 1.5;
        if (!isCore) {
          ctx.setLineDash([6, 4]);
        }

        const geomType = feature.geometry.type;
        const coords = feature.geometry.coordinates;

        const drawPolygonRings = (rings) => {
          rings.forEach((ring) => {
            ctx.beginPath();
            ring.forEach(([lon, lat], i) => {
              const pt = projectLonLatToCanvas(lon, lat, width, height, viewState);
              if (i === 0) ctx.moveTo(pt.x, pt.y);
              else ctx.lineTo(pt.x, pt.y);
            });
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
          });
        };

        if (geomType === 'Polygon') {
          drawPolygonRings(coords);
        } else if (geomType === 'MultiPolygon') {
          coords.forEach((poly) => drawPolygonRings(poly));
        }
        ctx.restore();
      });
    }

    // Draw active cursor crosshair and coordinates
    if (cursorPos) {
      ctx.save();
      ctx.strokeStyle = '#38bdf888';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(cursorPos.x, 0);
      ctx.lineTo(cursorPos.x, height);
      ctx.moveTo(0, cursorPos.y);
      ctx.lineTo(width, cursorPos.y);
      ctx.stroke();
      ctx.restore();
    }
  }, [viewState, activeImage, activeLayerId, opacity, showBoundaries, boundariesData, cursorPos, projectLonLatToCanvas]);

  // Keep canvas size responsive
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      canvas.width = canvas.parentElement.clientWidth;
      canvas.height = Math.max(480, Math.min(640, window.innerHeight * 0.65));
      renderCanvas();
    };
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, [renderCanvas]);

  // Redraw when state changes
  useEffect(() => {
    renderCanvas();
  }, [renderCanvas]);

  // Pan interaction handlers
  const handleMouseDown = (e) => {
    isDraggingRef.current = true;
    dragStartRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (isDraggingRef.current) {
      const dx = e.clientX - dragStartRef.current.x;
      const dy = e.clientY - dragStartRef.current.y;
      dragStartRef.current = { x: e.clientX, y: e.clientY };
      setViewState((vs) => ({
        ...vs,
        offsetX: vs.offsetX + dx,
        offsetY: vs.offsetY + dy,
      }));
    } else {
      const { lon, lat } = projectCanvasToLonLat(x, y, canvas.width, canvas.height, viewState);
      const inBbox = lon >= BOUNDS.west && lon <= BOUNDS.east && lat >= BOUNDS.south && lat <= BOUNDS.north;
      setCursorPos({ x, y, lon, lat, inBbox });
    }
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.88;
    setViewState((vs) => ({
      ...vs,
      zoom: Math.min(6.0, Math.max(0.6, vs.zoom * zoomFactor)),
    }));
  };

  // Click on map to inspect pixel values
  const handleClick = async (e) => {
    if (!cursorPos || !cursorPos.inBbox) return;
    try {
      setInspectLoading(true);
      const data = await inspectForestPixel(cursorPos.lon, cursorPos.lat);
      setInspectedPixel(data);
    } catch {
      // silently ignore inspection error
    } finally {
      setInspectLoading(false);
    }
  };

  const resetView = () => {
    setViewState({ zoom: 1.0, offsetX: 0, offsetY: 0 });
  };

  const activeLayerMeta = layers.find((l) => l.id === activeLayerId) || layers[1];

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-[#070b14] p-4 text-slate-200">
      {/* Top Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400">Layer:</span>
          <select
            value={activeLayerId}
            onChange={(e) => setActiveLayerId(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-white focus:border-cyan-400 focus:outline-none"
          >
            {layers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.units})
              </option>
            ))}
          </select>

          <span className="ml-2 text-xs font-semibold uppercase tracking-wider text-slate-400">AOI Mask:</span>
          <select
            value={aoiClip}
            onChange={(e) => setAoiClip(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-300 focus:border-cyan-400 focus:outline-none"
          >
            <option value="none">Full Track 098 Swath</option>
            <option value="sanctuary">Clip: Similipal Sanctuary</option>
            <option value="core">Clip: Similipal Core</option>
            <option value="forest">Clip: Forest Cover (≥30%)</option>
          </select>
        </div>

        {/* View Tools & Toggles */}
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={showBoundaries}
              onChange={(e) => setShowBoundaries(e.target.checked)}
              className="rounded border-slate-700 text-cyan-500 focus:ring-0"
            />
            <span>Reserve Boundaries</span>
          </label>

          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <span>Opacity:</span>
            <input
              type="range"
              min="0.2"
              max="1.0"
              step="0.05"
              value={opacity}
              onChange={(e) => setOpacity(+e.target.value)}
              className="h-1.5 w-16 accent-cyan-400 cursor-pointer"
            />
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => setViewState((vs) => ({ ...vs, zoom: Math.min(6.0, vs.zoom * 1.2) }))}
              title="Zoom In"
              className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs hover:border-cyan-400"
            >
              +
            </button>
            <button
              onClick={() => setViewState((vs) => ({ ...vs, zoom: Math.max(0.6, vs.zoom / 1.2) }))}
              title="Zoom Out"
              className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs hover:border-cyan-400"
            >
              −
            </button>
            <button
              onClick={resetView}
              title="Reset View to Swath"
              className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs hover:border-cyan-400"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      {/* Main Canvas Viewport */}
      <div className="relative w-full overflow-hidden rounded-lg border border-slate-800 bg-[#04070e]">
        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/80 text-sm text-cyan-300">
            Loading NISAR multi-temporal layers…
          </div>
        )}
        {error && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-rose-950/80 p-4 text-center text-sm text-rose-200">
            {error}
          </div>
        )}

        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
          onClick={handleClick}
          className="cursor-crosshair block w-full select-none"
        />

        {/* Dynamic Legend Overlay (Bottom-Left) */}
        <div className="absolute bottom-3 left-3 z-10 rounded-lg border border-slate-800 bg-slate-950/85 p-2.5 backdrop-blur-sm text-xs max-w-xs shadow-lg">
          <div className="font-semibold text-cyan-300 mb-1">{activeLayerMeta?.name}</div>
          <div className="text-[11px] text-slate-400 mb-2">{activeLayerMeta?.description}</div>

          {/* Continuous Legend Ramp */}
          {activeLayerMeta?.type === 'continuous' && (
            <div>
              <div
                className="h-2.5 w-full rounded"
                style={{
                  background:
                    activeLayerMeta.colormap === 'PuOr'
                      ? 'linear-gradient(to right, #e66101, #fdb863, #f7f7f7, #b2abd2, #5e3c99)'
                      : activeLayerMeta.colormap === 'PRGn'
                      ? 'linear-gradient(to right, #7b3294, #c2a5cf, #f7f7f7, #a6dba0, #008837)'
                      : 'linear-gradient(to right, #ca0020, #f4a582, #f7f7f7, #92c5de, #0571b0)',
                }}
              />
              <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                <span>{activeLayerMeta.min_val} {activeLayerMeta.units}</span>
                <span>0</span>
                <span>+{activeLayerMeta.max_val} {activeLayerMeta.units}</span>
              </div>
            </div>
          )}

          {/* Categorical Regimes Key */}
          {activeLayerId === 'physical_regimes' && (
            <div className="space-y-1 text-[10px]">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#e11d48]" />
                <span>1: Volume Scattering Loss (Canopy Drop)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#0284c7]" />
                <span>2: Surface / Moisture Increase</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#7c3aed]" />
                <span>3: Severe Dual-Pol Attenuation</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#059669]" />
                <span>4: Structural Regrowth</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#d97706]" />
                <span>5: Double-Bounce / Inundation</span>
              </div>
            </div>
          )}

          {/* Tier 1 Candidates Key */}
          {activeLayerId === 'tier1_candidates' && (
            <div className="space-y-1 text-[10px]">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#ef4444]" />
                <span className="text-rose-200 font-semibold">Tier 1 Instantaneous Candidate (ΔHV ≤ −2.5 dB)</span>
              </div>
              <p className="text-[9px] text-amber-300/80 italic">Unvalidated candidate anomaly; NOT confirmed deforestation.</p>
            </div>
          )}

          {/* Valid Coverage Key */}
          {activeLayerId === 'valid_coverage' && (
            <div className="space-y-1 text-[10px]">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#10b981]" />
                <span>Both Epochs Valid (2/2)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#f59e0b]" />
                <span>Single Epoch Only (1/2)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-slate-700" />
                <span>Outside Swath (0/2)</span>
              </div>
            </div>
          )}

          {/* Uncertainty Key */}
          {activeLayerId === 'uncertainty_mask' && (
            <div className="space-y-1 text-[10px]">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#f43f5e]" />
                <span className="text-rose-300 font-semibold">Insufficient Evidence / Unobserved</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-transparent border border-slate-600" />
                <span>Sufficient Evidence</span>
              </div>
            </div>
          )}

          {/* Boundary Legenda */}
          {showBoundaries && (
            <div className="border-t border-slate-800 pt-1.5 mt-2 flex items-center justify-between text-[10px] text-slate-400">
              <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 bg-[#10b981] inline-block" /> Sanctuary</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 bg-[#f59e0b] inline-block" /> Core Reserve</span>
            </div>
          )}
        </div>

        {/* Dynamic Scale Bar & Coordinates HUD (Bottom-Right) */}
        <div className="absolute bottom-3 right-3 z-10 flex flex-col items-end gap-1.5 rounded-lg border border-slate-800 bg-slate-950/85 px-3 py-2 backdrop-blur-sm text-xs font-mono">
          <div className="flex items-center gap-2 text-slate-300">
            {cursorPos ? (
              <span>
                {cursorPos.lat.toFixed(4)}°N, {cursorPos.lon.toFixed(4)}°E
              </span>
            ) : (
              <span className="text-slate-500">Hover map to inspect coordinates</span>
            )}
          </div>
          {/* 10 km Scale Bar */}
          <div className="flex items-center gap-1 opacity-80">
            <span className="text-[9px] text-slate-400">0</span>
            <div
              className="h-[2px] bg-cyan-300 relative"
              style={{ width: `${Math.max(20, Math.min(120, 48 * viewState.zoom))}px` }}
            >
              <div className="absolute top-0 left-0 h-1 w-[1px] bg-cyan-300 -translate-y-0.5" />
              <div className="absolute top-0 right-0 h-1 w-[1px] bg-cyan-300 -translate-y-0.5" />
            </div>
            <span className="text-[9px] text-slate-400">10 km</span>
          </div>
        </div>
      </div>

      {/* Interactive Pixel Sample Inspector Card (Triggered on Click) */}
      {inspectedPixel && inspectedPixel.inside_bbox && (
        <div className="rounded-lg border border-cyan-500/40 bg-cyan-950/20 p-3 text-xs">
          <div className="flex items-center justify-between border-b border-cyan-800/40 pb-2 mb-2">
            <div className="font-semibold text-cyan-300">
              Coordinate Inspection: {inspectedPixel.coordinates.latitude}°N, {inspectedPixel.coordinates.longitude}°E (UTM 45N: {inspectedPixel.coordinates.utm_easting}m E, {inspectedPixel.coordinates.utm_northing}m N)
            </div>
            <button
              onClick={() => setInspectedPixel(null)}
              className="text-slate-400 hover:text-white"
            >
              ✕
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div className="bg-slate-900/60 p-2 rounded">
              <span className="text-slate-400 block text-[10px]">Δσ°_HH (Co-Pol)</span>
              <span className="text-sm font-bold text-white">{inspectedPixel.values.delta_hh_db != null ? `${inspectedPixel.values.delta_hh_db} dB` : 'N/A (Outside Swath)'}</span>
            </div>
            <div className="bg-slate-900/60 p-2 rounded">
              <span className="text-slate-400 block text-[10px]">Δσ°_HV (Cross-Pol)</span>
              <span className="text-sm font-bold text-white">{inspectedPixel.values.delta_hv_db != null ? `${inspectedPixel.values.delta_hv_db} dB` : 'N/A (Outside Swath)'}</span>
            </div>
            <div className="bg-slate-900/60 p-2 rounded">
              <span className="text-slate-400 block text-[10px]">ΔRatio (HV/HH)</span>
              <span className="text-sm font-bold text-white">{inspectedPixel.values.delta_ratio_db != null ? `${inspectedPixel.values.delta_ratio_db} dB` : 'N/A (Outside Swath)'}</span>
            </div>
            <div className="bg-slate-900/60 p-2 rounded">
              <span className="text-slate-400 block text-[10px]">Physical Regime</span>
              <span className="text-xs font-semibold text-cyan-200">{inspectedPixel.regime.name}</span>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between text-[11px] text-slate-300 border-t border-slate-800/60 pt-2">
            <span>
              Observation Status: <strong className={inspectedPixel.is_valid_observation ? 'text-emerald-400' : 'text-amber-400'}>{inspectedPixel.valid_observation_count}/2 Valid Acquisitions</strong>
            </span>
            <span>
              Forest Cover: <strong className={inspectedPixel.in_reference_forest ? 'text-emerald-400' : 'text-slate-400'}>{inspectedPixel.in_reference_forest ? 'Reference Canopy (≥30%)' : 'Non-Forest / Unclassified'}</strong>
            </span>
            {inspectedPixel.disturbance_candidate.is_candidate ? (
              <span className="text-rose-300 font-semibold bg-rose-950/40 px-2 py-0.5 rounded border border-rose-500/30">
                ⚠ {inspectedPixel.disturbance_candidate.classification} ({inspectedPixel.disturbance_candidate.caution})
              </span>
            ) : (
              <span className="text-slate-400">Disturbance: Stable / No Candidate Anomaly</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

