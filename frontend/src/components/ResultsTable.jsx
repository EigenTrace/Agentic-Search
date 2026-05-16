import { useMemo, useState } from 'react';

function confidenceClass(c) {
  return c || 'low';
}

function exportJSON(entities, schema, query) {
  const data = { query, schema, entities };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `agentic-search-${query.slice(0,40).replace(/\W+/g, '_')}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function exportCSV(entities, columns, query) {
  const escape = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const rows = [columns.join(',')];
  for (const e of entities) {
    rows.push(columns.map((c) => escape(e.cells?.[c]?.value || '')).join(','));
  }
  const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `agentic-search-${query.slice(0,40).replace(/\W+/g, '_')}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ResultsTable({
  schema, entities, isPartial, onCellClick, query, onEditSchema,
}) {
  const [sortColumn, setSortColumn] = useState(null);
  const [sortDir, setSortDir] = useState('asc');

  const columns = schema?.columns || [];

  const sortedEntities = useMemo(() => {
    if (!sortColumn) return entities;
    const sign = sortDir === 'asc' ? 1 : -1;
    return [...entities].sort((a, b) => {
      const va = (a.cells?.[sortColumn]?.value || '').toLowerCase();
      const vb = (b.cells?.[sortColumn]?.value || '').toLowerCase();
      if (!va && vb) return 1;
      if (va && !vb) return -1;
      return sign * va.localeCompare(vb);
    });
  }, [entities, sortColumn, sortDir]);

  const onHeaderClick = (col) => {
    if (sortColumn === col) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(col);
      setSortDir('asc');
    }
  };

  if (!columns.length) return null;

  return (
    <div className="border border-white/10 rounded-lg bg-bg-panel overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-medium text-white/80">
            Results <span className="text-white/40">({entities.length})</span>
          </h2>
          {isPartial && (
            <span className="text-xs text-accent/90 animate-pulse-soft">
              ● Still searching for more...
            </span>
          )}
          {schema?.entity_type && (
            <span className="text-xs uppercase tracking-wider text-white/40 font-mono">
              {schema.entity_type}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onEditSchema}
            className="text-xs text-white/60 hover:text-white px-2 py-1 rounded border border-white/10 hover:border-white/30"
          >
            Edit columns
          </button>
          <button
            onClick={() => exportJSON(entities, schema, query)}
            className="text-xs text-white/60 hover:text-white px-2 py-1 rounded border border-white/10 hover:border-white/30"
          >
            Export JSON
          </button>
          <button
            onClick={() => exportCSV(entities, columns, query)}
            className="text-xs text-white/60 hover:text-white px-2 py-1 rounded border border-white/10 hover:border-white/30"
          >
            Export CSV
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full font-mono text-sm">
          <thead>
            <tr className="border-b border-white/10 bg-bg-subtle">
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => onHeaderClick(col)}
                  className="text-left px-4 py-3 text-xs uppercase tracking-wider text-white/50 font-medium cursor-pointer hover:text-white whitespace-nowrap"
                  title={schema?.column_descriptions?.[col] || ''}
                >
                  {col}
                  {sortColumn === col && (
                    <span className="ml-1 text-accent">
                      {sortDir === 'asc' ? '↑' : '↓'}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedEntities.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-white/30 text-sm">
                  No entities yet...
                </td>
              </tr>
            )}
            {sortedEntities.map((e, idx) => (
              <tr key={`${e.entity_name}-${idx}`} className="border-b border-white/5 hover:bg-white/[0.015]">
                {columns.map((col) => {
                  const cell = e.cells?.[col];
                  const value = cell?.value || '';
                  const conf = cell?.confidence || 'low';
                  return (
                    <td
                      key={col}
                      onClick={() => cell && onCellClick({ entity: e, column: col, cell })}
                      className={[
                        'px-4 py-3 align-top text-white/85 cell-clickable',
                        !value ? 'text-white/20' : '',
                      ].join(' ')}
                    >
                      {value ? (
                        <span className="inline-flex items-start">
                          <span className={`confidence-dot ${confidenceClass(conf)}`} title={conf} />
                          <span className="break-words max-w-md">{value}</span>
                        </span>
                      ) : (
                        <span>—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-2 border-t border-white/10 flex items-center gap-4 text-xs text-white/40 font-mono">
        <Legend />
      </div>
    </div>
  );
}

function Legend() {
  return (
    <>
      <span><span className="confidence-dot high" />2+ sources</span>
      <span><span className="confidence-dot medium" />1 specific source</span>
      <span><span className="confidence-dot low" />1 vague source</span>
      <span><span className="confidence-dot unverified" />Gap-filled</span>
    </>
  );
}
