const API_BASE = import.meta.env.VITE_API_BASE || '';

export function streamSearch(query, { onStatus, onSchema, onPartial, onResult, onError }) {
  const url = `${API_BASE}/api/search?q=${encodeURIComponent(query)}`;
  const eventSource = new EventSource(url);
  let finished = false;

  const safe = (cb, raw) => {
    try {
      cb && cb(JSON.parse(raw));
    } catch (e) {
      console.error('SSE parse failed', e, raw);
    }
  };

  eventSource.addEventListener('status', (e) => safe(onStatus, e.data));
  eventSource.addEventListener('schema', (e) => safe(onSchema, e.data));
  eventSource.addEventListener('partial', (e) => safe(onPartial, e.data));
  eventSource.addEventListener('result', (e) => {
    finished = true;
    safe(onResult, e.data);
    eventSource.close();
  });
  eventSource.addEventListener('error', (e) => {
    if (finished) return; // server closed the stream after success
    if (e.data) {
      safe(onError, e.data);
    } else {
      onError && onError({ message: 'Connection lost' });
    }
    eventSource.close();
  });

  return () => {
    finished = true;
    eventSource.close();
  };
}

export async function refineSchema({ query, columns, columnDescriptions, entityType }) {
  const resp = await fetch(`${API_BASE}/api/search/refine`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      columns,
      column_descriptions: columnDescriptions,
      entity_type: entityType,
    }),
  });
  if (!resp.ok) throw new Error(`Refine failed: ${resp.status}`);
  return resp.json();
}
