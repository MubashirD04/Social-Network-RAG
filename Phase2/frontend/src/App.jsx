// This is the sole interactive graph renderer for the app — the PyVis output
// served from GET /graph/{id}/visualisation is a separate, static HTML export
// (e.g. for viewing a graph outside the SPA, or from a non-browser MCP
// client) and is not meant to be embedded here.
import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { UploadCloud, Network, Search, FolderOpen, X, Users, Zap, MessageSquare, ShieldCheck, ChevronDown } from 'lucide-react';
import NetworkBackground from './NetworkBackground';
import CodeExample from './CodeExample';
import './App.css';

const CAPABILITIES = [
  {
    icon: Users,
    title: 'Community Detection',
    desc: 'Greedy modularity clustering surfaces the sub-groups hiding inside a big chat.'
  },
  {
    icon: Zap,
    title: 'Influencers & Brokers',
    desc: 'PageRank and betweenness centrality find who drives the conversation and who bridges cliques.'
  },
  {
    icon: Search,
    title: 'Semantic Search (RAG)',
    desc: 'Ask plain-English questions and get back the messages that actually answer them.'
  },
  {
    icon: MessageSquare,
    title: 'Topic Extraction',
    desc: 'KeyBERT pulls out what people were really talking about, run entirely on-device.'
  },
  {
    icon: Network,
    title: 'Interactive Graph',
    desc: 'Click any person, message, or topic to trace its connections through the whole network.'
  },
  {
    icon: ShieldCheck,
    title: 'Runs Locally',
    desc: 'No external LLM calls for core analysis — your export never leaves the machine to be understood.'
  }
];

const COLORS = {
  chat: '#FF6B6B',
  person: '#4ECDC4',
  topic: '#FFD93D',
  message: '#A0D2EB',
  bg: '#0f1115'
};

// A connection the backend inferred from shared wording between two
// unthreaded messages (_infer_lexical_continuity), not a confirmed reply —
// kept visually distinct (muted, dashed) so it never reads with the same
// certainty as a real thread reply.
const INFERRED_LINK_COLOR_IDLE = 'rgba(160, 180, 200, 0.35)';
const INFERRED_LINK_COLOR_HIGHLIGHT = 'rgba(160, 180, 200, 0.9)';

// Distinct hues cycled by community id so each cluster reads as its own
// color both on person nodes and on the edges between members of that
// cluster. -1 ("no community", e.g. isolated participants) falls back to
// a neutral gray rather than claiming a palette slot.
// Yellow is reserved for topic nodes/highlight strokes (see COLORS.topic and
// the highlight styling below) — it's deliberately left out here so a
// community swatch never reads as "this is a topic".
const COMMUNITY_PALETTE = [
  '#FF6B6B', '#4ECDC4', '#F4A261', '#A78BFA', '#F97316',
  '#22D3EE', '#F472B6', '#84CC16', '#60A5FA', '#FB923C',
  '#34D399', '#E879F9'
];
const NO_COMMUNITY_COLOR = '#6B7280';

const communityColor = (communityId) => {
  if (communityId === undefined || communityId === null || communityId === -1) {
    return NO_COMMUNITY_COLOR;
  }
  return COMMUNITY_PALETTE[communityId % COMMUNITY_PALETTE.length];
};

const API_BASE_URL = ''; // Proxied via Vite in dev, same origin in prod

// Node IDs are prefixed by type on the backend (social_graph_builder.py):
// person -> `p_{sender}`, message -> `m_{message_id}`. Topic and chat nodes
// use their raw string as-is. Build/parse IDs through these helpers rather
// than inline template literals so the convention lives in one place.
const nodeId = {
  message: (messageId) => `m_${messageId}`,
};

const MIN_TOPIC_COUNT = 5;
const MAX_TOPIC_COUNT = 10;

// Shared by the initial upload and by the topic-count control, both of
// which swap a fresh {nodes, edges} payload from the backend into
// react-force-graph's {nodes, links} shape.
const formatGraphData = (graphDataRaw) => ({
  nodes: graphDataRaw.nodes.map(n => ({
    ...n,
    id: String(n.id),
    val: n.type === 'person' ? (parseFloat(n.size) || 20) : 5
  })),
  links: graphDataRaw.edges.map(e => {
    // Backend stores REPLIED_TO as reply -> original (newer message
    // pointing at the one it replies to), which is what the reply
    // thread/stats calculations need server-side. Flip it here so the
    // rendered arrow points forward in conversation order (original
    // -> reply) instead of backward.
    const isReply = e.relationship === 'REPLIED_TO';
    return {
      source: String(isReply ? e.target : e.source),
      target: String(isReply ? e.source : e.target),
      relationship: e.relationship,
      // Two messages that were never in a real reply thread but clearly
      // share content (see _infer_lexical_continuity in
      // social_graph_builder.py) still get a REPLIED_TO edge so thread
      // rendering picks them up, but it's a guess rather than a fact —
      // carried through so it can render visually distinct from a
      // confirmed reply instead of claiming the same certainty.
      inferred: !!e.inferred
    };
  })
});

function App() {
  const [analysisId, setAnalysisId] = useState(null);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [query, setQuery] = useState('');
  const [queryResults, setQueryResults] = useState([]);
  const [queryLoading, setQueryLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [legendOpen, setLegendOpen] = useState(true);
  const [topicCount, setTopicCount] = useState(MIN_TOPIC_COUNT);
  const [topicCountLoading, setTopicCountLoading] = useState(false);
  const [showInferredLinks, setShowInferredLinks] = useState(true);

  // The graph view relies on fixed-position panels that never overflow the
  // viewport, so body scroll stays off there; the landing page is a normal
  // flowing document and needs it back, which the global `overflow: hidden`
  // in index.css otherwise blocks regardless of any container's own
  // overflow rules.
  useEffect(() => {
    document.body.classList.toggle('scrollable', !analysisId);
    return () => document.body.classList.remove('scrollable');
  }, [analysisId]);

  // Maps node id -> node, for community lookups on links before
  // react-force-graph resolves link.source/target into full node objects.
  const nodeById = useMemo(() => {
    const map = {};
    graphData.nodes.forEach(n => { map[n.id] = n; });
    return map;
  }, [graphData]);

  // Inferred connections (_infer_lexical_continuity) never affect influence
  // scores server-side, but they can still visually suggest a relationship
  // that isn't confirmed — this lets a viewer drop them from the picture
  // entirely rather than just dimming them.
  const visibleGraphData = useMemo(() => ({
    nodes: graphData.nodes,
    links: showInferredLinks ? graphData.links : graphData.links.filter(l => !l.inferred)
  }), [graphData, showInferredLinks]);

  // Drives click-to-highlight: every link directly touching the selected
  // node lights up, along with the neighbors on the other end of those
  // links. For a message that's its parent reply-to edge (before) and any
  // direct replies to it (after), plus its SENT/PART_OF/topic edges — one
  // hop out, same as every other node type. Everything else dims.
  const highlightData = useMemo(() => {
    if (!selectedNode) return null;

    const nodeIds = new Set([selectedNode.id]);
    const linkSet = new Set();
    visibleGraphData.links.forEach(l => {
      const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
      const targetId = typeof l.target === 'object' ? l.target.id : l.target;
      if (sourceId === selectedNode.id || targetId === selectedNode.id) {
        linkSet.add(l);
        nodeIds.add(sourceId);
        nodeIds.add(targetId);
      }
    });
    return { nodeIds, linkSet };
  }, [selectedNode, visibleGraphData]);

  // Topics are only meaningful in relation to what was actually said, so a
  // selected topic node needs the messages behind it, not just its own
  // label. MENTIONS_TOPIC edges run message -> topic (see
  // social_graph_builder.py), so we grab every message on the other end.
  const topicMessages = useMemo(() => {
    if (!selectedNode || selectedNode.type !== 'topic') return [];
    return graphData.links
      .filter(l => {
        const targetId = typeof l.target === 'object' ? l.target.id : l.target;
        return l.relationship === 'MENTIONS_TOPIC' && targetId === selectedNode.id;
      })
      .map(l => {
        const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
        return nodeById[sourceId];
      })
      .filter(Boolean)
      // Edge order follows thread/link construction, not chronology, so
      // sort by the message's own timestamp to show the conversation in
      // the order it actually happened.
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  }, [selectedNode, graphData, nodeById]);

  const fgRef = useRef();
  const fileInputRef = useRef();
  const [windowSize, setWindowSize] = useState({ width: window.innerWidth, height: window.innerHeight });

  useEffect(() => {
    const handleResize = () => setWindowSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Push nodes further apart than the library defaults so dense graphs
  // don't collapse into an unreadable clump: stronger mutual repulsion
  // plus longer rest length on links, then reheat so it takes effect.
  useEffect(() => {
    if (!fgRef.current || graphData.nodes.length === 0) return;
    fgRef.current.d3Force('charge').strength(-220).distanceMax(800);
    fgRef.current.d3Force('link').distance(90);
    fgRef.current.d3ReheatSimulation();
  }, [graphData]);

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
      setTopicCount(MIN_TOPIC_COUNT);

      const graphRes = await fetch(`${API_BASE_URL}/graph/${data.id}/data`);
      const graphDataRaw = await graphRes.json();
      setGraphData(formatGraphData(graphDataRaw));
    } catch (err) {
      alert("Upload Error:\n\n" + err.message);
    } finally {
      setLoading(false);
    }
  };

  const updateTopicCount = async (nextCount) => {
    setTopicCount(nextCount);
    if (!analysisId) return;

    setTopicCountLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/graph/${analysisId}/topics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ top_n: nextCount })
      });
      if (!res.ok) throw new Error("Failed to update topic count");
      const graphDataRaw = await res.json();
      setGraphData(formatGraphData(graphDataRaw));
      // The selected topic node may no longer exist post-regeneration.
      setSelectedNode(sel => (sel && sel.type === 'topic') ? null : sel);
    } catch (err) {
      alert("Couldn't update topics: " + err.message);
    } finally {
      setTopicCountLoading(false);
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
  }, []);

  const handleTopicMessageClick = (node) => {
    if (!node || !fgRef.current) return;
    fgRef.current.centerAt(node.x, node.y, 1000);
    fgRef.current.zoom(3, 1000);
    setSelectedNode(node);
  };

  const handleResultClick = (result) => {
    const node = graphData.nodes.find(n => n.id === nodeId.message(result.message_id));
    if (node && fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 1000);
      fgRef.current.zoom(3, 1000);
      setSelectedNode({ ...node, type: 'message', text: result.content, timestamp: result.timestamp });
    }
  };

  const resetApp = () => {
    setAnalysisId(null);
    setGraphData({ nodes: [], links: [] });
    setSelectedNode(null);
    setQuery('');
    setQueryResults([]);
    setDragActive(false);
    setTopicCount(MIN_TOPIC_COUNT);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className={`app-container ${!analysisId ? 'landing-mode' : ''}`}>
      {!analysisId && (
        <div className="landing-page">
          <NetworkBackground />

          <div className="landing-content">
            <header className="landing-hero">
              <div className="brand-mark">
                <Network size={22} />
                <span>Social RAG</span>
              </div>
              <h1>Turn a chat export into a living social graph</h1>
              <p className="landing-subtitle">
                Drop a WhatsApp, Telegram, or Slack export below and see who talks to whom,
                who holds the room, and what they're actually talking about — analyzed
                entirely on your machine.
              </p>
            </header>

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
                    <h2>Drop Chat File Here</h2>
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

            <section className="landing-section">
              <h3 className="landing-section-title">What's possible</h3>
              <div className="capability-grid">
                {CAPABILITIES.map((cap) => (
                  <div className="capability-card" key={cap.title}>
                    <cap.icon className="capability-icon" size={20} />
                    <h4>{cap.title}</h4>
                    <p>{cap.desc}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="landing-section">
              <h3 className="landing-section-title">How it works under the hood</h3>
              <p className="landing-section-lead">
                The drop zone above talks to a plain REST API — the same two calls
                you'd make from your own code:
              </p>
              <CodeExample />
            </section>
          </div>
        </div>
      )}

      {analysisId && (
        <>
          <ForceGraph2D
            key={analysisId}
            ref={fgRef}
            width={windowSize.width}
            height={windowSize.height}
            graphData={visibleGraphData}
            backgroundColor={COLORS.bg}
            nodeId="id"
            nodeRelSize={6}
            d3VelocityDecay={0.25}
            nodeCanvasObject={(node, ctx, globalScale) => {
              const label = node.label || node.id;
              const fontSize = 12/globalScale;
              ctx.font = `${fontSize}px Sans-Serif`;

              // Message nodes shrink with reply depth, so a nested thread
              // reads visually as narrowing rather than a flat chain of
              // identically-sized dots.
              const depth = node.reply_depth || 0;
              const radius = node.type === 'message' ? Math.max(2.5, 5 - depth * 0.6) : 5;

              const isHighlighted = highlightData && highlightData.nodeIds.has(node.id);
              const isDimmed = highlightData && !isHighlighted;

              ctx.globalAlpha = isDimmed ? 0.15 : 1;

              // Person nodes are colored by their detected community so
              // clusters are visually distinct; every other node type keeps
              // its fixed type color.
              ctx.fillStyle = node.type === 'person' ? communityColor(node.community) : (COLORS[node.type] || '#fff');
              ctx.beginPath();
              ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
              ctx.fill();

              if (isHighlighted && node.id !== selectedNode?.id) {
                ctx.strokeStyle = '#FFD93D';
                ctx.lineWidth = 1.5 / globalScale;
                ctx.stroke();
              } else if (node.id === selectedNode?.id) {
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2 / globalScale;
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
            onBackgroundClick={() => setSelectedNode(null)}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkColor={(link) => {
              if (highlightData) {
                if (!highlightData.linkSet.has(link)) return 'rgba(255,255,255,0.03)';
                // Inferred connections stay visually distinct even while
                // highlighted, so a confirmed thread reply never looks like
                // the same fact as a guess based on shared wording.
                return link.inferred ? INFERRED_LINK_COLOR_HIGHLIGHT : '#FFD93D';
              }
              if (link.inferred) return INFERRED_LINK_COLOR_IDLE;
              // Idle state: tint edges between two members of the same
              // community so clusters read as connected paths, not just
              // colored dots.
              const sourceNode = typeof link.source === 'object' ? link.source : nodeById[link.source];
              const targetNode = typeof link.target === 'object' ? link.target : nodeById[link.target];
              if (
                sourceNode?.type === 'person' && targetNode?.type === 'person' &&
                sourceNode.community === targetNode.community && sourceNode.community !== -1 &&
                sourceNode.community !== undefined && sourceNode.community !== null
              ) {
                return communityColor(sourceNode.community);
              }
              return 'rgba(255,255,255,0.2)';
            }}
            linkWidth={(link) => {
              if (!highlightData) return 1;
              return highlightData.linkSet.has(link) ? 2 : 0.5;
            }}
            linkLineDash={(link) => link.inferred ? [2, 2] : null}
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
                <button className="close-btn" onClick={() => setSelectedNode(null)}><X size={20} /></button>
              </div>
              <div className="badge-container">
                {selectedNode.type === 'person' ? (
                  <>
                    <span className="badge" style={{background: communityColor(selectedNode.community), color: '#000'}}>
                      {selectedNode.community === -1 || selectedNode.community == null ? 'NO COMMUNITY' : `COMMUNITY ${selectedNode.community}`}
                    </span>
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
                  <div className="metric-box" title={selectedNode.pagerank ?? 0}><div className="metric-value">{selectedNode.pagerank?.toFixed(5) || 0}</div><div className="metric-label">Influence</div></div>
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
                          <br />Its reply-to and reply-from links are highlighted on the graph.
                        </p>
                      )}
                    </>
                  )}
                  {selectedNode.type === 'topic' && (
                    <>
                      <p style={{marginBottom: '10px'}}>
                        {topicMessages.length > 0
                          ? <>Came up in <strong>{topicMessages.length}</strong> message{topicMessages.length === 1 ? '' : 's'}:</>
                          : <>No messages matched this topic directly.</>}
                      </p>
                      <div className="topic-message-list">
                        {topicMessages.map(m => (
                          <div key={m.id} className="result-item" onClick={() => handleTopicMessageClick(m)}>
                            <div className="result-meta">
                              <span className="result-sender">{m.sender || ''}</span>
                              <span>{m.timestamp ? new Date(m.timestamp).toLocaleString() : ''}</span>
                            </div>
                            <div className="result-text">{m.text}</div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
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
                    {/* From src/conversation_linker.py's edge list, not the graph's own
                        `inferred` edges above (_infer_lexical_continuity) — a separate,
                        richer signal (semantic + temporal + turn-taking + lexical) the
                        backend attaches to /query results, not to graphData. */}
                    {result.linked_context && result.linked_context.length > 0 && (
                      <div className="linked-context">
                        <span className="linked-context-label">Linked context</span>
                        {result.linked_context.map((linked, lidx) => (
                          <div
                            key={lidx}
                            className="linked-context-item"
                            onClick={(e) => { e.stopPropagation(); handleResultClick(linked); }}
                          >
                            <span className="linked-context-sender">{linked.sender}</span>
                            <span className="linked-context-text">{linked.content}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="legend-panel glass-panel overlay-panel">
            <button className="legend-toggle" onClick={() => setLegendOpen(o => !o)}>
              <h4>Legend</h4>
              <ChevronDown size={16} className={legendOpen ? '' : 'legend-chevron-collapsed'} />
            </button>
            <div className={`legend-collapse ${legendOpen ? '' : 'collapsed'}`}>
              <div className="legend-collapse-inner">
                <div className="topic-count-control">
                  <label htmlFor="topic-count-slider">
                    Topics shown: <strong>{topicCount}</strong>{topicCountLoading && ' · updating…'}
                  </label>
                  <input
                    id="topic-count-slider"
                    type="range"
                    min={MIN_TOPIC_COUNT}
                    max={MAX_TOPIC_COUNT}
                    step={1}
                    value={topicCount}
                    disabled={topicCountLoading}
                    onChange={(e) => updateTopicCount(parseInt(e.target.value, 10))}
                  />
                </div>
                <div className="legend-item"><span className="dot" style={{background: `linear-gradient(135deg, ${COMMUNITY_PALETTE[0]}, ${COMMUNITY_PALETTE[3]}, ${COMMUNITY_PALETTE[6]})`}}></span> Person (colored by community)</div>
                <div className="legend-item"><span className="dot topic-dot" style={{borderRadius: '2px', transform: 'rotate(45deg)'}}></span> Topic</div>
                <div className="legend-item"><span className="dot message-dot"></span> Message</div>
                <div className="legend-item">
                  <label style={{display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer'}}>
                    <input
                      type="checkbox"
                      checked={showInferredLinks}
                      onChange={(e) => setShowInferredLinks(e.target.checked)}
                    />
                    <span className="inferred-link-swatch"></span>
                    <span style={{fontSize: '0.75rem', color: 'var(--text-muted)'}}>
                      Show inferred connections (shares wording, no formal reply — never affects influence scores)
                    </span>
                  </label>
                </div>
                <div className="legend-item" style={{marginTop: '8px'}}>
                  <span className="badge influencer" style={{fontSize: '0.65rem'}}>INFLUENCER</span>
                  <span style={{marginLeft: '6px', fontSize: '0.75rem', color: 'var(--text-muted)'}}>High PageRank — a central, high-influence person</span>
                </div>
                <div className="legend-item">
                  <span className="badge broker" style={{fontSize: '0.65rem'}}>BROKER</span>
                  <span style={{marginLeft: '6px', fontSize: '0.75rem', color: 'var(--text-muted)'}}>High betweenness — bridges otherwise separate groups</span>
                </div>
                <div className="legend-item" style={{marginTop: '8px', fontSize: '0.75rem', color: 'var(--text-muted)'}}>
                  Click a node to highlight everything connected to it
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default App;
