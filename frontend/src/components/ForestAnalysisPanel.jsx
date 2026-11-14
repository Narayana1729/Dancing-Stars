import React, { useState, useEffect } from 'react';
import { getForestTemporalMetrics } from '../services/api.js';

export default function ForestAnalysisPanel() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function fetchMetrics() {
      try {
        setLoading(true);
        const data = await getForestTemporalMetrics();
        if (isMounted) {
          setMetrics(data);
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || 'Failed to load temporal metrics.');
          setLoading(false);
        }
      }
    }
    fetchMetrics();
    return () => { isMounted = false; };
  }, []);

  if (loading) {
    return (
      <aside className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-4 text-xs text-slate-400">
        Loading NISAR temporal analytics…
      </aside>
    );
  }

  if (error || !metrics) {
    return (
      <aside className="flex flex-col gap-3 rounded-xl border border-rose-900/50 bg-rose-950/20 p-4 text-xs text-rose-300">
        {error || 'Unable to load temporal metrics.'}
      </aside>
    );
  }

  const { observations, quantitative_changes, disturbance_classification, coverage_and_validity, scientific_uncertainty } = metrics;
  const t1 = disturbance_classification.tier1_instantaneous;
  const t2 = disturbance_classification.tier2_temporally_sustained;
  const t3 = disturbance_classification.tier3_long_term_persistent;
  const rec = disturbance_classification.canopy_recovery;

  return (
    <aside className="flex flex-col gap-4 text-slate-200">
      {/* 1. Multi-Temporal Acquisition Metadata */}
      <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
        <h3 className="text-sm font-semibold text-cyan-300 mb-2 flex items-center justify-between">
          <span>Acquisition Metadata</span>
          <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800/40">
            {observations.temporal_separation_days} Days / {observations.orbital_repeat_cycles} Cycles
          </span>
        </h3>
        <dl className="text-xs space-y-1.5 divide-y divide-slate-800/60">
          <Row k="Baseline (t₀)" v="2026-03-04 23:37 UTC" sub="Orbit 014 · Track 098 · Frame 12" />
          <Row k="Comparison (t₁)" v="2026-04-21 23:37 UTC" sub="Orbit 018 · Track 098 · Frame 12" />
          <Row k="Sensor & Geometry" v="L-band GCOV (1293.5 MHz)" sub="Ascending · Left-Look · 80m Grid" />
          <Row k="Study Region" v="Similipal Tiger Reserve" sub="Odisha, India (UTM Zone 45N)" />
        </dl>
      </section>

      {/* 2. Radiometric Backscatter Dynamics */}
      <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
        <h3 className="text-sm font-semibold text-cyan-300 mb-3">Radiometric Changes</h3>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <MetricBox
            label="Δσ°_HV (Cross-Pol)"
            val={`${quantitative_changes.delta_hv_db.mean} dB`}
            sub={`Median: ${quantitative_changes.delta_hv_db.median} dB`}
            color="text-amber-400"
          />
          <MetricBox
            label="Δσ°_HH (Co-Pol)"
            val={`${quantitative_changes.delta_hh_db.mean} dB`}
            sub={`Median: ${quantitative_changes.delta_hh_db.median} dB`}
            color="text-slate-200"
          />
          <MetricBox
            label="ΔRatio (HV / HH)"
            val={`${quantitative_changes.delta_ratio_db.mean} dB`}
            sub={`Median: ${quantitative_changes.delta_ratio_db.median} dB`}
            color="text-slate-300"
          />
          <MetricBox
            label="RND (Step Index)"
            val={`${quantitative_changes.rnd_hv.mean}`}
            sub="Scale: [-1.0, +1.0]"
            color="text-slate-300"
          />
        </div>
      </section>

      {/* 3. Disturbance Candidate Classification with Strict Scientific Guardrails */}
      <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-cyan-300">Disturbance Classification</h3>
          <span className="text-[10px] uppercase font-bold text-rose-400 bg-rose-950/40 px-2 py-0.5 rounded border border-rose-500/30">
            Tier 1 Candidate
          </span>
        </div>

        {/* Tier 1 Instantaneous Card */}
        <div className="rounded-lg bg-rose-950/20 border border-rose-500/40 p-3 space-y-1.5">
          <div className="flex justify-between items-center text-xs">
            <span className="font-semibold text-rose-300">Tier 1: Instantaneous Disturbance</span>
            <span className="text-[11px] font-mono text-white font-bold">{t1.detected_area_ha} ha ({t1.detected_area_km2} km²)</span>
          </div>
          <p className="text-[11px] text-slate-300 leading-tight">
            Detected: {t1.detected_pixels} pixels across {t1.total_forest_pixels.toLocaleString()} monitored forest pixels ({t1.disturbance_fraction_percent}%). Spatial filter MMU ≥ 1.92 ha applied.
          </p>
          <div className="rounded border border-amber-500/50 bg-amber-950/40 px-2 py-1 text-[10px] text-amber-200 font-medium">
            ⚠ Scientific Guardrail: Instantaneous candidate only. Represents an unvalidated statistical backscatter drop; NOT confirmed deforestation.
          </div>
        </div>

        {/* Multi-Temporal Tiers Status Table */}
        <div className="space-y-1.5 text-[11px]">
          <div className="flex justify-between items-center p-2 rounded bg-slate-900 border border-amber-900/40">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-slate-200">Tier 2: Sustained Anomaly</span>
                <span className="text-[9px] font-mono text-amber-300 bg-amber-950/60 px-1.5 py-0.2 rounded border border-amber-700/40">N ≥ 3</span>
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">{t2.reason}</div>
            </div>
            <span className="text-[9px] font-bold text-amber-300 bg-amber-950/80 px-2 py-0.5 rounded border border-amber-600/40">
              REQUIRES ADDITIONAL OBSERVATIONS
            </span>
          </div>

          <div className="flex justify-between items-center p-2 rounded bg-slate-900 border border-purple-900/40">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-slate-200">Tier 3: Persistent Deforestation</span>
                <span className="text-[9px] font-mono text-purple-300 bg-purple-950/60 px-1.5 py-0.2 rounded border border-purple-700/40">N ≥ 4 · ≥180d</span>
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">{t3.reason}</div>
            </div>
            <span className="text-[9px] font-bold text-purple-300 bg-purple-950/80 px-2 py-0.5 rounded border border-purple-600/40">
              REQUIRES SEASONAL COVERAGE
            </span>
          </div>

          <div className="flex justify-between items-center p-2 rounded bg-slate-900 border border-slate-800">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-slate-200">Canopy Recovery Status</span>
                <span className="text-[9px] font-mono text-slate-400 bg-slate-800 px-1.5 py-0.2 rounded">Post-Event Repeat</span>
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">{rec.reason}</div>
            </div>
            <span className="text-[9px] font-bold text-slate-400 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
              REQUIRES ADDITIONAL OBSERVATIONS
            </span>
          </div>

          <div className="flex justify-between items-center p-2 rounded bg-slate-900 border border-rose-900/30">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-rose-200">Confirmed Deforestation Verdict</span>
                <span className="text-[9px] font-mono text-rose-300 bg-rose-950/60 px-1.5 py-0.2 rounded border border-rose-700/40">In-Situ</span>
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">Cannot be established from SAR backscatter alone without ground truth.</div>
            </div>
            <span className="text-[9px] font-bold text-rose-300 bg-rose-950/80 px-2 py-0.5 rounded border border-rose-600/40">
              REQUIRES INDEPENDENT VERIFICATION
            </span>
          </div>
        </div>
      </section>

      {/* Blocked Capabilities Transparency Card */}
      <section className="rounded-xl border border-rose-900/30 bg-rose-950/10 p-3.5 space-y-2 text-xs">
        <h4 className="text-xs font-semibold text-rose-300 flex items-center justify-between">
          <span>Data-Blocked Capabilities & Safeguards</span>
          <span className="text-[9px] font-mono text-rose-400 bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-700/40">
            Enforced by Policy
          </span>
        </h4>
        <ul className="text-[11px] text-slate-400 space-y-1 list-disc list-inside">
          <li>
            <strong className="text-slate-300">Supervised ML Training:</strong> Blocked (only 43 positive pixels in 1 micro-event; 53,556:1 class imbalance). Prevented by DataSufficiencyError.
          </li>
          <li>
            <strong className="text-slate-300">Seasonal Reference Baseline:</strong> Blocked (requires 8–12 repeat passes across Monsoon, Post-Monsoon, and Dry seasons).
          </li>
          <li>
            <strong className="text-slate-300">Full Sanctuary Core Coverage:</strong> Partially Blocked (Track 098 Frame 012 covers 18.29%; Frame 013 required for southern 81.71%).
          </li>
        </ul>
      </section>

      {/* 4. Coverage & Valid Observation Statistics */}
      <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
        <h3 className="text-sm font-semibold text-cyan-300 mb-2">Temporal Coverage</h3>
        <dl className="text-xs space-y-1.5 divide-y divide-slate-800/60">
          <Row k="Frame Validity" v={`${coverage_and_validity.frame_validity_percent}%`} sub={`${coverage_and_validity.valid_dual_epoch_pixels.toLocaleString()} dual-epoch valid pixels`} />
          <Row k="Reserve Swath Overlap" v={`${coverage_and_validity.reserve_swath_overlap_percent}%`} sub={`${coverage_and_validity.monitored_reserve_forest_area_km2} km² observed in Frame 012`} />
          <Row k="Outside Swath" v={`${(100 - coverage_and_validity.reserve_swath_overlap_percent).toFixed(1)}%`} sub="81.7% of Similipal Core unobserved" />
        </dl>
      </section>

      {/* 5. Scientific Uncertainty & Independent Corroboration */}
      <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 text-xs space-y-2">
        <h3 className="text-sm font-semibold text-cyan-300">Scientific Uncertainty</h3>
        <div className="space-y-1.5 text-[11px] text-slate-400">
          <p>
            <strong className="text-amber-300">Phenological Ambiguity:</strong> {scientific_uncertainty.phenological_moisture_sensitivity.finding}
          </p>
          <p>
            <strong className="text-cyan-300">Optical Corroboration:</strong> {scientific_uncertainty.independent_optical_corroboration.in_swath_overlap_ha} ha candidate cross-sensor event within swath; {scientific_uncertainty.independent_optical_corroboration.outside_swath_unobserved_loss_ha} ha optical anomaly located outside Track 098 swath.
          </p>
          <p className="text-[10px] text-slate-500 italic">
            Optical Caution: Dry-season NDVI &gt; 0.55 indicates green canopy retention, but does not independently establish absence of understory disturbance; 0.43 ha is an anomaly overlap candidate, not confirmed deforestation.
          </p>
        </div>
      </section>
    </aside>
  );
}

const Row = ({ k, v, sub }) => (
  <div className="flex justify-between items-baseline gap-2 pt-1.5">
    <dt className="text-slate-400">{k}</dt>
    <dd className="text-right">
      <div className="font-semibold text-slate-100">{v}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </dd>
  </div>
);

const MetricBox = ({ label, val, sub, color = 'text-white' }) => (
  <div className="rounded-lg bg-slate-900 border border-slate-800/80 p-2.5">
    <div className="text-[10px] text-slate-400">{label}</div>
    <div className={`text-base font-bold font-mono ${color}`}>{val}</div>
    {sub && <div className="text-[9px] text-slate-500 mt-0.5">{sub}</div>}
  </div>
);

