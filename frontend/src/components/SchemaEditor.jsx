import { useEffect, useState } from 'react';

export default function SchemaEditor({ schema, onClose, onApply }) {
  const [columns, setColumns] = useState(schema?.columns || []);
  const [descriptions, setDescriptions] = useState(schema?.column_descriptions || {});
  const [newCol, setNewCol] = useState('');

  useEffect(() => {
    setColumns(schema?.columns || []);
    setDescriptions(schema?.column_descriptions || {});
  }, [schema]);

  const removeCol = (c) => {
    if (c === 'name') return; // name is required
    setColumns(columns.filter((x) => x !== c));
  };

  const addCol = () => {
    const v = newCol.trim();
    if (!v || columns.includes(v)) return;
    setColumns([...columns, v]);
    setDescriptions({ ...descriptions, [v]: '' });
    setNewCol('');
  };

  const move = (idx, delta) => {
    const next = [...columns];
    const target = idx + delta;
    if (target < 0 || target >= next.length) return;
    [next[idx], next[target]] = [next[target], next[idx]];
    setColumns(next);
  };

  return (
    <>
      <div onClick={onClose} className="fixed inset-0 bg-black/50 z-30" />
      <div className="fixed inset-0 z-40 flex items-center justify-center p-4 pointer-events-none">
        <div className="bg-bg-panel border border-white/10 rounded-lg w-full max-w-xl pointer-events-auto animate-slide-in">
          <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
            <h3 className="text-sm font-medium">Edit columns</h3>
            <button onClick={onClose} className="text-white/40 hover:text-white">✕</button>
          </div>
          <div className="p-5 space-y-3 max-h-[60vh] overflow-y-auto">
            {columns.map((c, idx) => (
              <div key={c} className="flex items-center gap-2 bg-bg-subtle border border-white/10 rounded px-3 py-2">
                <span className="font-mono text-sm flex-1">{c}</span>
                <input
                  value={descriptions[c] || ''}
                  onChange={(e) => setDescriptions({ ...descriptions, [c]: e.target.value })}
                  placeholder="description (optional)"
                  className="flex-1 bg-bg border border-white/5 rounded px-2 py-1 text-xs text-white/70"
                />
                <button onClick={() => move(idx, -1)} disabled={idx === 0} className="text-white/40 hover:text-white disabled:opacity-20">↑</button>
                <button onClick={() => move(idx, 1)} disabled={idx === columns.length - 1} className="text-white/40 hover:text-white disabled:opacity-20">↓</button>
                <button
                  onClick={() => removeCol(c)}
                  disabled={c === 'name'}
                  className="text-conf-medium hover:text-conf-medium/80 disabled:opacity-20 px-1"
                  title={c === 'name' ? 'name is required' : 'remove'}
                >
                  ✕
                </button>
              </div>
            ))}
            <div className="flex items-center gap-2 pt-2">
              <input
                value={newCol}
                onChange={(e) => setNewCol(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addCol()}
                placeholder="new column name"
                className="flex-1 bg-bg-subtle border border-white/10 rounded px-3 py-2 text-sm font-mono"
              />
              <button
                onClick={addCol}
                disabled={!newCol.trim()}
                className="bg-accent/80 hover:bg-accent text-white px-3 py-2 rounded text-sm disabled:opacity-40"
              >
                Add
              </button>
            </div>
          </div>
          <div className="px-5 py-4 border-t border-white/10 flex justify-end gap-2">
            <button onClick={onClose} className="text-sm text-white/60 hover:text-white px-3 py-2">
              Cancel
            </button>
            <button
              onClick={() => onApply({ columns, columnDescriptions: descriptions })}
              className="bg-accent hover:bg-accent/90 text-white text-sm px-4 py-2 rounded"
            >
              Re-analyze
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
