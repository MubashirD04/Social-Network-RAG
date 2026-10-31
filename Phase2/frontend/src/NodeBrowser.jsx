import { useMemo, useState } from 'react';
import { X } from 'lucide-react';

const RESULT_LIMIT = 50;
const TYPE_ORDER = { person: 0, topic: 1, chat: 2, message: 3 };

// A non-spatial route to every node: the graph itself is a canvas that
// keyboards and screen readers can't get into.
function NodeBrowser({ nodes, selectedId, onSelect, onClose }) {
  const [filter, setFilter] = useState('');

  const matches = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return nodes
      .filter(n => (needle
        ? `${n.label || n.id} ${n.text || ''}`.toLowerCase().includes(needle)
        : n.type !== 'message'))
      .sort((a, b) => (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9) || (b.pagerank || 0) - (a.pagerank || 0));
  }, [nodes, filter]);

  return (
    <>
      <div className="panel-header">
        <h3>Browse nodes</h3>
        <button type="button" className="close-btn" aria-label="Close node browser" onClick={onClose}><X size={20} /></button>
      </div>
      <input
        type="search"
        className="node-filter"
        aria-label="Filter people, topics and messages"
        placeholder="Filter people, topics, messages…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <p className="node-count" role="status">
        {matches.length > RESULT_LIMIT ? `Showing ${RESULT_LIMIT} of ${matches.length}` : `${matches.length} found`}
      </p>
      <ul className="node-list">
        {matches.slice(0, RESULT_LIMIT).map(n => (
          <li key={n.id}>
            <button type="button" className="result-item" aria-current={n.id === selectedId} onClick={() => onSelect(n.id)}>
              <span className="result-meta"><span className="result-sender">{n.label || n.id}</span><span>{n.type}</span></span>
              {n.type === 'message' && <span className="result-text">{n.text}</span>}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

export default NodeBrowser;
