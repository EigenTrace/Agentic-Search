const STAGES = [
  { id: 'planning', label: 'Plan' },
  { id: 'searching', label: 'Search' },
  { id: 'scraping', label: 'Scrape' },
  { id: 'extracting', label: 'Extract' },
  { id: 'resolving', label: 'Merge' },
  { id: 'gap_filling', label: 'Fill Gaps' },
  { id: 'done', label: 'Done' },
];

export default function StatusFeed({ status }) {
  if (!status) return null;
  const currentIdx = STAGES.findIndex((s) => s.id === status.stage);

  return (
    <div className="border border-white/10 rounded-lg bg-bg-panel px-4 py-3">
      <div className="flex items-center gap-2 overflow-x-auto">
        {STAGES.map((stage, i) => {
          const isActive = i === currentIdx;
          const isDone = currentIdx > i || status.stage === 'done';
          return (
            <div key={stage.id} className="flex items-center gap-2 shrink-0">
              <div className="flex items-center gap-2">
                <span
                  className={[
                    'w-2 h-2 rounded-full transition',
                    isDone ? 'bg-conf-high' :
                      isActive ? 'bg-accent animate-pulse-soft' :
                      'bg-white/15',
                  ].join(' ')}
                />
                <span
                  className={[
                    'text-xs uppercase tracking-wider',
                    isActive ? 'text-white' : isDone ? 'text-white/60' : 'text-white/30',
                  ].join(' ')}
                >
                  {stage.label}
                </span>
              </div>
              {i < STAGES.length - 1 && (
                <span className="w-6 h-px bg-white/10" />
              )}
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between mt-3">
        <p className="text-xs text-white/55 font-mono">{status.message}</p>
        {typeof status.progress === 'number' && (
          <div className="w-40 h-1 bg-white/10 rounded-full overflow-hidden ml-3 shrink-0">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${Math.max(2, Math.min(100, status.progress * 100))}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
