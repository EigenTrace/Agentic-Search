import { useState } from 'react';

export default function CostDashboard({ cost }) {
  const [open, setOpen] = useState(false);
  if (!cost) return null;
  const time = cost.wall_clock_seconds?.toFixed?.(1) ?? '0';
  const dollars = (cost.estimated_cost_usd ?? 0).toFixed(3);

  return (
    <div className="fixed bottom-4 right-4 z-20">
      {open ? (
        <div className="bg-bg-panel border border-white/10 rounded-lg p-4 w-64 text-xs font-mono shadow-xl animate-slide-in">
          <div className="flex justify-between items-center mb-3">
            <span className="uppercase tracking-wider text-white/40">Cost</span>
            <button onClick={() => setOpen(false)} className="text-white/40 hover:text-white">✕</button>
          </div>
          <Row label="Wall clock" value={`${time}s`} />
          <Row label="Estimated cost" value={`$${dollars}`} />
          <Row label="Search API calls" value={cost.total_search_api_calls} />
          <Row label="Pages scraped" value={cost.total_pages_scraped} />
          <Row label="LLM calls" value={cost.total_llm_calls} />
          <Row label="Input tokens" value={cost.total_input_tokens?.toLocaleString?.()} />
          <Row label="Output tokens" value={cost.total_output_tokens?.toLocaleString?.()} />
        </div>
      ) : (
        <button
          onClick={() => setOpen(true)}
          className="bg-bg-panel border border-white/10 rounded-full px-4 py-2 text-xs font-mono text-white/70 hover:text-white hover:border-white/30"
        >
          ⏱ {time}s · ${dollars}
        </button>
      )}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-white/50">{label}</span>
      <span className="text-white/90">{value}</span>
    </div>
  );
}
