const TAG = {
  High: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  Moderate: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  Medium: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  Low: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
};

export default function SidePanel({ region }) {
  return (
    <aside className="flex flex-col gap-4">
      <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
        <h3 className="text-sm font-semibold text-cyan-300 mb-3">Metadata</h3>
        <dl className="text-sm space-y-2">
          <Row k="Data source" v={region.dataSource} />
          <Row k="Region" v={region.name} />
          <Row k="Before" v={region.beforeDate.replace('\n', ' · ')} />
          <Row k="After" v={region.afterDate.replace('\n', ' · ')} />
        </dl>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
        <h3 className="text-sm font-semibold text-cyan-300 mb-3">Estimated Impact</h3>
        <div className="grid grid-cols-2 gap-3">
          {[[region.impactStats.metricLabel, region.impactStats.metricValue], [region.impactStats.secondaryLabel, region.impactStats.secondaryValue]].map(([k, v], i) => (
            <div key={k} className={`rounded-lg bg-slate-900 border border-slate-800 p-3 ${i === 0 ? 'col-span-2' : ''}`}>
              <div className="text-xs text-slate-400">{k}</div>
              <div className="text-xl font-bold text-cyan-300">{v}</div>
            </div>
          ))}
        </div>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 flex items-center justify-between">
        <span className="text-sm text-slate-400">Confidence</span>
        <span className={`text-xs px-3 py-1 rounded-full border ${TAG[region.confidence]}`}>{region.confidence}</span>
      </section>
    </aside>
  );
}

const Row = ({ k, v }) => (
  <div className="flex justify-between gap-2"><dt className="text-slate-400">{k}</dt><dd className="text-right">{v}</dd></div>
);
