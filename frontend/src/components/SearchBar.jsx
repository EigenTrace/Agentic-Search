import { useState } from 'react';

const EXAMPLES = [
  'AI startups in healthcare',
  'top pizza places in Brooklyn',
  'open source database tools',
];

export default function SearchBar({ onSubmit, disabled, compact }) {
  const [value, setValue] = useState('');

  const submit = (e) => {
    e?.preventDefault();
    if (!value.trim() || disabled) return;
    onSubmit(value);
  };

  if (compact) {
    return (
      <form onSubmit={submit} className="flex gap-2 w-full max-w-2xl">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Ask a topic query..."
          disabled={disabled}
          className="flex-1 bg-bg-panel border border-white/10 rounded-md px-4 py-2 text-sm font-sans focus:outline-none focus:border-accent/60 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="bg-accent hover:bg-accent/90 text-white px-4 py-2 rounded-md text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          Search
        </button>
      </form>
    );
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <form onSubmit={submit} className="relative">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="What do you want to discover?"
          disabled={disabled}
          autoFocus
          className="w-full bg-bg-panel border border-white/10 rounded-xl px-6 py-5 text-lg font-sans placeholder:text-white/30 focus:outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/30 disabled:opacity-50 transition"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="absolute right-3 top-1/2 -translate-y-1/2 bg-accent hover:bg-accent/90 text-white px-5 py-2.5 rounded-lg text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          Search →
        </button>
      </form>
      <div className="flex flex-wrap gap-2 mt-4 justify-center">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => { setValue(ex); onSubmit(ex); }}
            disabled={disabled}
            className="text-xs px-3 py-1.5 rounded-full border border-white/10 text-white/60 hover:text-white hover:border-white/30 transition disabled:opacity-40"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}
