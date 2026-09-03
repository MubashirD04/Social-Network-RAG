// This is the sole interactive graph renderer for the app — the PyVis output
// served from GET /graph/{id}/visualisation is a separate, static HTML export
// (e.g. for viewing a graph outside the SPA, or from a non-browser MCP
// client) and is not meant to be embedded here.
import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { UploadCloud, Network, Search, FolderOpen, X } from 'lucide-react';
import './App.css';

const COLORS = {
  chat: '#FF6B6B',
  person: '#4ECDC4',
  topic: '#FFD93D',
  message: '#A0D2EB',
  bg: '#0f1115'
};

const API_BASE_URL = ''; // Proxied via Vite in dev, same origin in prod

// Node IDs are prefixed by type on the backend (social_graph_builder.py):
// person -> `p_{sender}`, message -> `m_{message_id}`. Topic and chat nodes
// use their raw string as-is. Build/parse IDs through these helpers rather
// than inline template literals so the convention lives in one place.
const nodeId = {
  message: (messageId) => `m_${messageId}`,
};

function App() {
  const [analysisId, setAnalysisId] = useState(null);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [query, setQuery] = useState('');
  const [queryResults, setQueryResults] = useState([]);
  const [queryLoading, setQueryLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  // Set when a message node is selected, so the whole reply thread it
  // belongs to (root + every nested reply) can be highlighted instead of
  // just the one flat edge to its immediate parent.
  const [highlightThreadRoot, setHighlightThreadRoot] = useState(null);

  // Maps message node id -> thread_root, so link color/width can tell
  // whether a link belongs to the highlighted thread even before
  // react-force-graph resolves link.source/target into full node objects.
  const messageThreadById = useMemo(() => {
    const map = {};
    graphData.nodes.forEach(n => {
      if (n.thread_root) map[n.id] = n.thread_root;
    });
    return map;
  }, [graphData]);

  const fgRef = useRef();
  const fileInputRef = useRef();
  const [windowSize, setWindowSize] = useState({ width: window.innerWidth, height: window.innerHeight });

  useEffect(() => {
    const handleResize = () => setWindowSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleFileUpload = async (file) => {
    if (!file) return;
    
    const validExtensions = ['.txt', '.json', '.zip'];
    if (!validExtensions.some(ext => file.name.toLowerCase().endsWith(ext))) {
      alert("Invalid file format. Please upload a .txt, .json, or .zip file.");
      return;
    }

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE_URL}/analyse`, {
        method: 'POST',
        body: formData
      });
      
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Analysis failed' }));
        throw new Error(err.detail || 'Analysis failed');
      }
      
      const data = await res.json();
      setAnalysisId(data.id);
      
      const graphRes = await fetch(`${API_BASE_URL}/graph/${data.id}/data`);
      const graphDataRaw = await graphRes.json();
      
      const formattedData = {
        nodes: graphDataRaw.nodes.map(n => ({
          ...n,
          id: String(n.id),
          val: n.type === 'person' ? (parseFloat(n.size) || 20) : 5
        })),
        links: graphDataRaw.edges.map(e => ({
          source: String(e.source),
          target: String(e.target)
        }))
      };
      
      setGraphData(formattedData);
    } catch (err) {
      alert("Upload Error:\n\n" + err.message);
    } finally {
      setLoading(false);
    }
  };

  const onDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const executeSearch = async () => {
    if (!analysisId || !query.trim()) return;
    setQueryLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/graph/${analysisId}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), top_k: 8 })
      });
      
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      setQueryResults(data.results || []);
    } catch (err) {
      alert("Search failed: " + err.message);
    } finally {
      setQueryLoading(false);
    }
  };

  const handleNodeClick = useCallback(node => {
    if (!fgRef.current || !node) return;
    fgRef.current.centerAt(node.x, node.y, 1000);
    fgRef.current.zoom(3, 1000);
    setSelectedNode(node);
    setHighlightThreadRoot(node.type === 'message' ? node.thread_root : null);
  }, []);

  const handleResultClick = (result) => {
    const node = graphData.nodes.find(n => n.id === nodeId.message(result.message_id));
    if (node && fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 1000);
      fgRef.current.zoom(3, 1000);
      setSelectedNode({ ...node, type: 'message', text: result.content, timestamp: result.timestamp });
      setHighlightThreadRoot(node.thread_root ?? null);
    }
  };

  const resetApp = () => {
    setAnalysisId(null);
    setGraphData({ nodes: [], links: [] });
    setSelectedNode(null);
    setHighlightThreadRoot(null);
    setQuery('');
    setQueryResults([]);
    setDragActive(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="app-container">
      {!analysisId && (
        <div 
          className={`drop-zone ${dragActive ? 'drag-active' : ''}`}
          onDragEnter={onDrag}
          onDragLeave={onDrag}
          onDragOver={onDrag}
          onDrop={onDrop}
          onClick={() => !loading && fileInputRef.current.click()}
        >
          <div className="drop-content">
            {loading ? (
              <div className="loading-state">
                <div className="spinner"></div>
                <p>Analyzing Chat Data...</p>
              </div>
            ) : (
              <>
                <UploadCloud className="icon-large" />
                <h1>Drop Chat File Here</h1>
                <p>Upload WhatsApp (.txt), Telegram (.json), or Slack (.zip) exports</p>
                <div className="test-files-hint">
                  Or click here to browse test data
                </div>
              </>
            )}
          </div>
          <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            onChange={(e) => handleFileUpload(e.target.files[0])}
            accept=".txt,.json,.zip"
          />
        </div>
      )}

      {analysisId && (
        <>
          <ForceGraph2D
            key={analysisId}
            ref={fgRef}
            width={windowSize.width}
            height={windowSize.height}
            graphData={graphData}
            backgroundColor={COLORS.bg}
            nodeId="id"
            nodeRelSize={6}
            nodeAutoColorBy="type"
            nodeCanvasObject={(node, ctx, globalScale) => {
              const label = node.label || node.id;
              const fontSize = 12/globalScale;
              ctx.font = `${fontSize}px Sans-Serif`;

              // Message nodes shrink with reply depth, so a nested thread
              // reads visually as narrowing rather than a flat chain of
              // identically-sized dots.
              const depth = node.reply_depth || 0;
              const radius = node.type === 'message' ? Math.max(2.5, 5 - depth * 0.6) : 5;

              const inHighlightedThread = highlightThreadRoot && node.thread_root === highlightThreadRoot;
              const isDimmed = highlightThreadRoot && !inHighlightedThread;

              ctx.globalAlpha = isDimmed ? 0.15 : 1;

              ctx.fillStyle = COLORS[node.type] || '#fff';
              ctx.beginPath();
              ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
              ctx.fill();

              if (inHighlightedThread) {
                ctx.strokeStyle = '#FFD93D';
                ctx.lineWidth = 1.5 / globalScale;
                ctx.stroke();
              }

              if (!isDimmed) {
                const textWidth = ctx.measureText(label).width;
                const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2); // some padding

                ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
                ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y - bckgDimensions[1] / 2 - 8, bckgDimensions[0], bckgDimensions[1]);

                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = '#000';
                ctx.fillText(label, node.x, node.y - 8);
              }

              ctx.globalAlpha = 1;
            }}
            onNodeClick={handleNodeClick}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkColor={(link) => {
              if (!highlightThreadRoot) return 'rgba(255,255,255,0.2)';
              const sourceRoot = typeof link.source === 'object' ? link.source.thread_root : messageThreadById[link.source];
              const targetRoot = typeof link.target === 'object' ? link.target.thread_root : messageThreadById[link.target];
              const inThread = sourceRoot === highlightThreadRoot || targetRoot === highlightThreadRoot;
              return inThread ? '#FFD93D' : 'rgba(255,255,255,0.04)';
            }}
            linkWidth={(link) => {
              if (!highlightThreadRoot) return 1;
              const sourceRoot = typeof link.source === 'object' ? link.source.thread_root : messageThreadById[link.source];
              const targetRoot = typeof link.target === 'object' ? link.target.thread_root : messageThreadById[link.target];
              return (sourceRoot === highlightThreadRoot || targetRoot === highlightThreadRoot) ? 2 : 0.5;
            }}
          />

          <div className="top-bar glass-panel overlay-panel">
            <div className="branding">
              <Network size={20} /> Social RAG
            </div>
            <div className="search-container">
              <Search className="search-icon" size={18} onClick={executeSearch} />
              <input 
                type="text" 
                id="rag-search" 
                placeholder="Ask a question about the chat..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && executeSearch()}
              />
              {queryLoading && <div className="search-spinner"></div>}
            </div>
            <button className="icon-btn" title="Reset" onClick={resetApp}>
              <FolderOpen size={20} />
            </button>
          </div>

          {selectedNode && (
            <div className="details-sidebar glass-panel overlay-panel">
              <div className="panel-header">
                <h2>{selectedNode.label || selectedNode.id}</h2>
                <button className="close-btn" onClick={() => { setSelectedNode(null); setHighlightThreadRoot(null); }}><X size={20} /></button>
              </div>
              <div className="badge-container">
                {selectedNode.type === 'person' ? (
                  <>
                    {selectedNode.is_influencer && <span className="badge influencer">INFLUENCER</span>}
                    {selectedNode.is_info_broker && <span className="badge broker">BROKER</span>}
                  </>
                ) : (
                  <span className="badge" style={{background: COLORS[selectedNode.type] || '#888', color: '#000'}}>
                    {(selectedNode.type || 'UNKNOWN').toUpperCase()}
                  </span>
                )}
              </div>
              
              {selectedNode.type === 'person' ? (
                <div className="metrics-grid">
                  <div className="metric-box"><div className="metric-value">{selectedNode.message_count || 0}</div><div className="metric-label">Messages</div></div>
                  <div className="metric-box"><div className="metric-value">{selectedNode.replies_received || 0}</div><div className="metric-label">Replies</div></div>
                  <div className="metric-box"><div className="metric-value">{selectedNode.pagerank?.toFixed(3) || 0}</div><div className="metric-label">Influence</div></div>
                  <div className="metric-box"><div className="metric-value">Group {selectedNode.community ?? '?'}</div><div className="metric-label">Community</div></div>
                </div>
              ) : (
                <div className="node-content">
                  {selectedNode.type === 'message' && (
                    <>
                      <p>{selectedNode.text || ''}</p>
                      <p style={{marginTop:'10px', color: 'var(--text-muted)', fontSize:'0.8rem'}}>
                        {new Date(selectedNode.timestamp).toLocaleString()}
                      </p>
                      {typeof selectedNode.reply_depth === 'number' && (
                        <p style={{marginTop:'10px', color: 'var(--text-muted)', fontSize:'0.8rem'}}>
                          {selectedNode.reply_depth === 0
                            ? `Thread root · ${selectedNode.thread_size} message${selectedNode.thread_size === 1 ? '' : 's'} in this thread`
                            : `Reply depth ${selectedNode.reply_depth} of ${selectedNode.thread_size}-message thread`}
                          <br />Full thread highlighted on the graph.
                        </p>
                      )}
                    </>
                  )}
                  {selectedNode.type === 'topic' && <p>Conversations about <strong>{selectedNode.label}</strong>.</p>}
                </div>
              )}
            </div>
          )}

          {queryResults.length > 0 && (
            <div className="results-panel glass-panel overlay-panel">
              <div className="panel-header">
                <h3>Search Results</h3>
                <button className="close-btn" onClick={() => setQueryResults([])}><X size={20} /></button>
              </div>
              <div className="results-list">
                {queryResults.map((result, idx) => (
                  <div key={idx} className="result-item" onClick={() => handleResultClick(result)}>
                    <div className="result-meta">
                      <span className="result-sender">{result.sender}</span>
                      <span>Match: {(result.score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="result-text">{result.content}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="legend-panel glass-panel overlay-panel">
            <h4>Legend</h4>
            <div className="legend-item"><span className="dot person-dot"></span> Person</div>
            <div className="legend-item"><span className="dot topic-dot" style={{borderRadius: '2px', transform: 'rotate(45deg)'}}></span> Topic</div>
            <div className="legend-item"><span className="dot message-dot"></span> Message</div>
            <div className="legend-item" style={{marginTop: '8px', fontSize: '0.75rem', color: 'var(--text-muted)'}}>
              Click a message to highlight its full reply thread
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default App;
