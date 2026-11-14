import { useState } from 'react';
import { domainsData } from './mock/mockDomains.js';
import StatusMessage from './components/StatusMessage.jsx';
import { useBackendHealth } from './hooks/useBackendHealth.js';
import BeforeAfterSlider from './components/BeforeAfterSlider.jsx';
import SidePanel from './components/SidePanel.jsx';
import ForestDisturbanceMap from './components/ForestDisturbanceMap.jsx';
import ForestAnalysisPanel from './components/ForestAnalysisPanel.jsx';

export default function App() {
  const [domainKey, setDomainKey] = useState('forests');
  const [regionKey, setRegionKey] = useState(0);
  const [viewMode, setViewMode] = useState('layer_explorer'); // 'layer_explorer' | 'slider'

  const health = useBackendHealth();
  const domain = domainsData[domainKey];
  const region = domain?.regions?.[regionKey];

  const changeDomain = (k) => {
    setDomainKey(k);
    setRegionKey(0); // reset region for the new domain
  };

  const isSimilipalAuthentic = domainKey === 'forests' && region?.id === 'similipal_india';

  return (
    <div className="min-h-screen bg-[#060810] text-slate-100">
      <header className="flex flex-wrap items-center justify-between gap-3 px-4 md:px-8 py-3 border-b border-slate-800 bg-[#05070fcc] backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🛰️</span>
          <div>
            <h1 className="text-lg md:text-xl font-bold text-cyan-300">Dancing with the SARs</h1>
            <p className="text-xs text-slate-400">Team Dancing Stars · NISAR Multi-Temporal Analysis</p>
          </div>
        </div>
        <nav className="flex flex-wrap gap-2">
          {Object.entries(domainsData).map(([k, d]) => (
            <button
              key={k}
              onClick={() => changeDomain(k)}
              className={`px-4 py-2 rounded-lg text-sm border transition ${
                k === domainKey
                  ? 'bg-gradient-to-br from-cyan-600 to-indigo-500 border-transparent text-white shadow-[0_0_18px_#22d3ee55]'
                  : 'border-slate-700 hover:border-cyan-400 text-slate-300'
              }`}
            >
              {d.title}
            </button>
          ))}
        </nav>
      </header>

      <main className="p-4 md:px-8 space-y-4 max-w-[1720px] mx-auto">
        {/* Status / Data Origin Banner */}
        <div
          role="note"
          className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3.5 py-2 text-xs ${
            isSimilipalAuthentic
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
              : 'border-amber-500/40 bg-amber-500/10 text-amber-200'
          }`}
        >
          <span>
            {isSimilipalAuthentic
              ? '✅ Authentic NISAR L2 GCOV Data: Operational multi-temporal SAR radiometric analytics and 9-layer forest disturbance visualization.'
              : 'Demo data: the images and statistics shown are illustrative placeholders, not results computed by this platform.'}
          </span>
          <span aria-live="polite" className="font-mono">
            Backend:{' '}
            {health === 'loading'
              ? 'checking…'
              : health === 'ok'
              ? 'connected (v1 operational)'
              : 'not reachable'}
          </span>
        </div>

        {/* Region & View Mode Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-semibold uppercase">Study Region:</span>
            <select
              value={regionKey}
              onChange={(e) => setRegionKey(+e.target.value)}
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-400 text-white"
            >
              {domain.regions.map((r, i) => (
                <option key={r.id} value={i}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>

          {/* View Mode Switcher for Authentic NISAR Region */}
          {isSimilipalAuthentic && (
            <div className="flex items-center rounded-lg border border-slate-700 bg-slate-900/90 p-1 text-xs">
              <button
                onClick={() => setViewMode('layer_explorer')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition ${
                  viewMode === 'layer_explorer'
                    ? 'bg-cyan-600 text-white font-semibold shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>🗺️</span>
                <span>Multi-Temporal Layer Explorer</span>
              </button>
              <button
                onClick={() => setViewMode('slider')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition ${
                  viewMode === 'slider'
                    ? 'bg-cyan-600 text-white font-semibold shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>🔀</span>
                <span>Before/After Comparison Slider</span>
              </button>
            </div>
          )}
        </div>

        {!region ? (
          <StatusMessage kind="empty" title="No regions available" message="There is no data for this category yet." />
        ) : isSimilipalAuthentic && viewMode === 'layer_explorer' ? (
          /* Multi-Temporal Layer Explorer View */
          <div className="grid gap-4 lg:grid-cols-[1fr_360px] xl:grid-cols-[1fr_400px]">
            <ForestDisturbanceMap />
            <ForestAnalysisPanel />
          </div>
        ) : (
          /* Before / After Slider View (Preserved) */
          <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
            <BeforeAfterSlider
              key={`${domainKey}-${regionKey}`}
              beforeImg={region.beforeImg}
              afterImg={region.afterImg}
              beforeDate={region.beforeDate}
              afterDate={region.afterDate}
              locationLabel={region.locationLabel}
            />
            <SidePanel region={region} />
          </div>
        )}
      </main>
    </div>
  );
}
