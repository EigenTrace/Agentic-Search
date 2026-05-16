import { useState } from 'react';
import SearchBar from './components/SearchBar.jsx';
import StatusFeed from './components/StatusFeed.jsx';
import ResultsTable from './components/ResultsTable.jsx';
import SourcePanel from './components/SourcePanel.jsx';
import SchemaEditor from './components/SchemaEditor.jsx';
import CostDashboard from './components/CostDashboard.jsx';
import QuerySuggestions from './components/QuerySuggestions.jsx';
import { useSearch } from './hooks/useSearch.js';

export default function App() {
  const { state, startSearch, selectCell, clearCell, refine, reset } = useSearch();
  const [showSchemaEditor, setShowSchemaEditor] = useState(false);

  const isIdle = state.status === 'idle';
  const isSearching = state.status === 'searching';
  const renderedEntities = state.entities.length > 0 ? state.entities : state.partialEntities;
  const showTable = state.schema && (renderedEntities.length > 0 || state.status !== 'idle');

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-white/5 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <button onClick={reset} className="flex items-center gap-2 group">
            <span className="text-accent text-xl">◆</span>
            <span className="font-mono text-sm tracking-wide text-white/80 group-hover:text-white">
              agentic-search
            </span>
          </button>
          {!isIdle && (
            <SearchBar
              compact
              disabled={isSearching}
              onSubmit={startSearch}
            />
          )}
        </div>
      </header>

      <main className="flex-1 px-6 py-8">
        <div className="max-w-7xl mx-auto space-y-6">
          {isIdle && (
            <div className="flex flex-col items-center justify-center min-h-[55vh] gap-6">
              <div className="text-center">
                <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight">
                  Discover anything,
                  <span className="text-accent"> structured.</span>
                </h1>
                <p className="text-white/50 mt-3 max-w-lg mx-auto">
                  An agentic search engine that turns a topic query into a structured table — every cell sourced and confidence-scored.
                </p>
              </div>
              <SearchBar onSubmit={startSearch} disabled={isSearching} />
            </div>
          )}

          {!isIdle && state.pipelineStatus && (
            <StatusFeed status={state.pipelineStatus} />
          )}

          {state.error && (
            <div className="border border-red-500/40 bg-red-500/10 rounded-lg p-4 text-sm text-red-200">
              <strong>Error:</strong> {state.error}
            </div>
          )}

          {showTable && (
            <ResultsTable
              schema={state.schema}
              entities={renderedEntities}
              isPartial={isSearching}
              onCellClick={selectCell}
              onEditSchema={() => setShowSchemaEditor(true)}
              query={state.query}
            />
          )}

          {state.status === 'done' && state.suggestedFollowups?.length > 0 && (
            <QuerySuggestions
              suggestions={state.suggestedFollowups}
              onPick={startSearch}
            />
          )}
        </div>
      </main>

      <footer className="border-t border-white/5 px-6 py-3 text-center text-xs text-white/30 font-mono">
        Sources: Brave Search · Anthropic Claude · agentic-search
      </footer>

      <SourcePanel selection={state.selectedCell} onClose={clearCell} />
      {showSchemaEditor && state.schema && (
        <SchemaEditor
          schema={state.schema}
          onClose={() => setShowSchemaEditor(false)}
          onApply={async (payload) => {
            setShowSchemaEditor(false);
            await refine(payload);
          }}
        />
      )}
      <CostDashboard cost={state.cost} />
    </div>
  );
}
