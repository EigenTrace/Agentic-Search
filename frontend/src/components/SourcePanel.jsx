import { useEffect } from 'react';

export default function SourcePanel({ selection, onClose }) {
  useEffect(() => {
    if (!selection) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selection, onClose]);

  if (!selection) return null;
  const { entity, column, cell } = selection;
  const sources = cell.sources || [];
  const conflicts = cell.conflicts || [];

  return (
    <>
      <div
        onClick={onClose}
        className="fixed inset-0 bg-black/40 z-30 animate-fade-in"
      />
      <aside className="fixed right-0 top-0 bottom-0 w-full sm:w-[460px] z-40 bg-bg-panel border-l border-white/10 animate-slide-in overflow-y-auto">
        <div className="p-5 border-b border-white/10 flex items-start justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-white/40 font-mono">
              {entity.entity_name} · {column}
            </div>
            <h3 className="text-lg font-mono mt-1 break-words">
              <span className={`confidence-dot ${cell.confidence || 'low'}`} />
              {cell.value || '—'}
            </h3>
            <div className="text-xs text-white/40 uppercase mt-1 tracking-wider">
              confidence: <span className="text-white/70">{cell.confidence}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-white/40 hover:text-white text-lg px-2 -mt-1"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="p-5 space-y-4">
          <h4 className="text-xs uppercase tracking-wider text-white/40">
            Sources ({sources.length})
          </h4>
          {sources.length === 0 && (
            <p className="text-white/40 text-sm">No sources recorded for this cell.</p>
          )}
          {sources.map((s, i) => (
            <div key={i} className="border border-white/10 rounded-md p-3 bg-bg-subtle">
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-accent text-sm break-words hover:underline"
              >
                {s.page_title || s.url}
              </a>
              <div className="text-xs text-white/30 mt-1 break-all font-mono">{s.url}</div>
              {s.quote_snippet && (
                <blockquote className="mt-2 text-sm text-white/70 border-l-2 border-accent/40 pl-3">
                  <mark className="hl">{s.quote_snippet}</mark>
                </blockquote>
              )}
              <div className="text-[10px] text-white/30 mt-2 font-mono">
                scraped {s.scraped_at}
              </div>
            </div>
          ))}

          {conflicts.length > 0 && (
            <div className="border border-conf-medium/40 rounded-md p-3 bg-conf-medium/5">
              <h4 className="text-xs uppercase tracking-wider text-conf-medium mb-2">
                ⚠ Conflicting values from other sources
              </h4>
              <ul className="space-y-1 text-sm text-white/80">
                {conflicts.map((c, i) => (
                  <li key={i} className="font-mono">• {c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
