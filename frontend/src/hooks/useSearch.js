import { useCallback, useEffect, useReducer, useRef } from 'react';
import { refineSchema, streamSearch } from '../api.js';

const STORAGE_KEY = 'agentic-search:lastResult';

const initialState = {
  status: 'idle', // idle | searching | done | error
  query: '',
  schema: null,
  entities: [],
  partialEntities: [],
  suggestedFollowups: [],
  cost: null,
  pipelineStatus: null,
  selectedCell: null,
  error: null,
};

// Subset of state worth persisting: skip transient UI state.
const PERSISTED_KEYS = ['status', 'query', 'schema', 'entities', 'suggestedFollowups', 'cost'];

function loadPersisted() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (!saved || saved.status !== 'done') return null;
    return saved;
  } catch {
    return null;
  }
}

function savePersisted(state) {
  try {
    if (state.status !== 'done') return;
    const slim = {};
    for (const k of PERSISTED_KEYS) slim[k] = state[k];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slim));
  } catch {
    // ignore quota errors
  }
}

function clearPersisted() {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
}

function hydrateInitial() {
  const saved = loadPersisted();
  if (!saved) return initialState;
  return {
    ...initialState,
    status: 'done',
    query: saved.query || '',
    schema: saved.schema || null,
    entities: saved.entities || [],
    suggestedFollowups: saved.suggestedFollowups || [],
    cost: saved.cost || null,
  };
}

function reducer(state, action) {
  switch (action.type) {
    case 'START':
      return {
        ...initialState,
        status: 'searching',
        query: action.query,
        pipelineStatus: { stage: 'planning', message: 'Starting...', progress: 0 },
      };
    case 'STATUS':
      return { ...state, pipelineStatus: action.payload };
    case 'SCHEMA':
      return { ...state, schema: action.payload };
    case 'PARTIAL':
      return { ...state, partialEntities: action.payload.entities || [] };
    case 'RESULT':
      return {
        ...state,
        status: 'done',
        entities: action.payload.entities || [],
        suggestedFollowups: action.payload.suggested_followups || [],
        cost: action.payload.cost || null,
        schema: action.payload.schema || state.schema,
        pipelineStatus: { stage: 'done', message: 'Done', progress: 1 },
      };
    case 'ERROR':
      return { ...state, status: 'error', error: action.payload?.message || 'Unknown error' };
    case 'SELECT_CELL':
      return { ...state, selectedCell: action.payload };
    case 'CLEAR_CELL':
      return { ...state, selectedCell: null };
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

export function useSearch() {
  const [state, dispatch] = useReducer(reducer, undefined, hydrateInitial);
  const cleanupRef = useRef(null);

  useEffect(() => {
    if (state.status === 'done') savePersisted(state);
  }, [state]);

  const startSearch = useCallback((query) => {
    if (!query?.trim()) return;
    if (cleanupRef.current) cleanupRef.current();
    dispatch({ type: 'START', query: query.trim() });
    cleanupRef.current = streamSearch(query.trim(), {
      onStatus: (p) => dispatch({ type: 'STATUS', payload: p }),
      onSchema: (p) => dispatch({ type: 'SCHEMA', payload: p }),
      onPartial: (p) => dispatch({ type: 'PARTIAL', payload: p }),
      onResult: (p) => dispatch({ type: 'RESULT', payload: p }),
      onError: (p) => dispatch({ type: 'ERROR', payload: p }),
    });
  }, []);

  const selectCell = useCallback((cell) => dispatch({ type: 'SELECT_CELL', payload: cell }), []);
  const clearCell = useCallback(() => dispatch({ type: 'CLEAR_CELL' }), []);
  const reset = useCallback(() => {
    clearPersisted();
    if (cleanupRef.current) cleanupRef.current();
    dispatch({ type: 'RESET' });
  }, []);

  const refine = useCallback(async ({ columns, columnDescriptions }) => {
    if (!state.query) return;
    dispatch({ type: 'STATUS', payload: { stage: 'refining', message: 'Re-extracting with new schema...', progress: 0.3 } });
    try {
      const result = await refineSchema({
        query: state.query,
        columns,
        columnDescriptions,
        entityType: state.schema?.entity_type,
      });
      dispatch({ type: 'RESULT', payload: result });
    } catch (e) {
      dispatch({ type: 'ERROR', payload: { message: e.message } });
    }
  }, [state.query, state.schema]);

  useEffect(() => () => {
    if (cleanupRef.current) cleanupRef.current();
  }, []);

  return { state, startSearch, selectCell, clearCell, refine, reset };
}
