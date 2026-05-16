export default function QuerySuggestions({ suggestions, onPick }) {
  if (!suggestions?.length) return null;
  return (
    <div className="border border-white/10 rounded-lg bg-bg-panel p-4">
      <div className="text-xs uppercase tracking-wider text-white/40 mb-3">
        Suggested follow-ups
      </div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s, i) => (
          <button
            key={i}
            onClick={() => onPick(s)}
            className="text-sm px-3 py-2 rounded-md border border-white/10 hover:border-accent/60 hover:text-white text-white/70 transition"
          >
            {s} →
          </button>
        ))}
      </div>
    </div>
  );
}
