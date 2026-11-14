const STYLE = {
  empty: 'border-slate-700 text-slate-300',
  error: 'border-rose-500/50 bg-rose-500/10 text-rose-200',
  loading: 'border-cyan-500/40 text-cyan-200',
};

/** Accessible loading / error / empty message. kind: 'empty' | 'error' | 'loading'. */
export default function StatusMessage({ kind = 'empty', title, message }) {
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={`rounded-xl border p-6 text-center ${STYLE[kind]}`}>
      <p className="font-semibold">{title}</p>
      {message && <p className="mt-1 text-sm opacity-80">{message}</p>}
    </div>
  );
}
