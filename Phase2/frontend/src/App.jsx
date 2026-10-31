// This is the sole interactive graph UI for the app — the PyVis output
// served from GET /graph/{id}/visualisation is a separate, static HTML export
// (e.g. for viewing a graph outside the SPA, or from a non-browser MCP
// client) and is not meant to be embedded here.
import React, { lazy, Suspense, useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { AnimatePresence, MotionConfig, motion as Motion } from 'motion/react';
import { UploadCloud, Network, Search, FolderOpen, X, Users, Zap, MessageSquare, ShieldCheck, ChevronDown, List } from 'lucide-react';
import NetworkBackground from './NetworkBackground';
import CodeExample from './CodeExample';
import NodeBrowser from './NodeBrowser';
import { analyseFile, searchMessages, setTopicCountInWorker } from './pipeline/client';
import { buildVisibleGraph, computeHighlight, connectionSummary, expansionFor, formatGraphData, messagesForTopic, EXPAND_LIMIT } from './graph/graphData';
import { COLORS, COMMUNITY_PALETTE, communityColor } from './graph/graphStyle';
import './App.css';

// Split out so visitors who only read the landing page don't download a
// renderer, and only people who ask for 3D download three.js.
const Graph2D = lazy(() => import('./graph/Graph2D'));
const Graph3D = lazy(() => import('./graph/Graph3D'));

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
    desc: 'No external LLM calls for core analysis — your export never leaves your device.'
  }
];

// Node IDs are prefixed by type on the backend (social_graph_builder.py):
// person -> `p_{sender}`, message -> `m_{message_id}`. Topic and chat nodes
// use their raw string as-is. Build/parse IDs through these helpers rather
// than inline template literals so the convention lives in one place.
const nodeId = {
  message: (messageId) => `m_${messageId}`,
};

const MIN_TOPIC_COUNT = 5;
const MAX_TOPIC_COUNT = 10;

// 3D is desktop-only, and past this many visible nodes it falls back to 2D.
const MAX_3D_NODES = 1000;
const MIN_3D_WIDTH = 768;

const NARROW_LEGEND_WIDTH = 768;
const PANEL_MOTION = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 12 },
  transition: { duration: 0.2, ease: 'easeOut' }
};

const supportsWebGL = () => {
  try {
    return !!document.createElement('canvas').getContext('webgl2');
  } catch {
    return false;
  }
};

const reasonNo3D = (width, visibleNodeCount) => {
  if (width < MIN_3D_WIDTH || window.matchMedia('(pointer: coarse)').matches) return '3D is available on desktop only';
  if (!supportsWebGL()) return '3D needs WebGL, which this browser doesn\'t provide';
  if (visibleNodeCount > MAX_3D_NODES) return `3D supports up to ${MAX_3D_NODES} visible nodes`;
  return null;
};

const describeNode = (node) => `${node.type || 'node'} ${node.label || node.id}`;

function App() {
  const [analysisId, setAnalysisId] = useState(null);
  const [graphData, setGraphData] = useState({ nodes: [], links: [], topicLinks: [] });
  const [loading, setLoading] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [focusRequest, setFocusRequest] = useState(null);
  const [query, setQuery] = useState('');
  const [queryResults, setQueryResults] = useState([]);
  const [queryLoading, setQueryLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [legendOpen, setLegendOpen] = useState(() => window.innerWidth >= NARROW_LEGEND_WIDTH);
  const [topicCount, setTopicCount] = useState(MIN_TOPIC_COUNT);
  const [topicCountLoading, setTopicCountLoading] = useState(false);
  const [showInferredLinks, setShowInferredLinks] = useState(true);
  const [showAllMessages, setShowAllMessages] = useState(false);
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const [wants3D, setWants3D] = useState(false);
  const [browserOpen, setBrowserOpen] = useState(false);

  // The graph view relies on fixed-position panels that never overflow the
  // viewport, so body scroll stays off there; the landing page is a normal
  // flowing document and needs it back, which the global `overflow: hidden`
  // in index.css otherwise blocks regardless of any container's own
  // overflow rules.
  useEffect(() => {
    document.body.classList.toggle('scrollable', !analysisId);
    return () => document.body.classList.remove('scrollable');
  }, [analysisId]);

  const nodeById = useMemo(() => new Map(graphData.nodes.map(n => [n.id, n])), [graphData]);
  // Derived rather than stored, so it's always the current node: a selected
  // topic simply disappears if the slider regenerates it away.
  const selectedNode = selectedId ? nodeById.get(selectedId) ?? null : null;

  // Inferred connections (_infer_lexical_continuity) never affect influence
  // scores during analysis, but they can still visually suggest a relationship
  // that isn't confirmed — this lets a viewer drop them from the picture
  // entirely rather than just dimming them.
  const visibleGraphData = useMemo(() => buildVisibleGraph(graphData, {
    showAllMessages,
    expandedIds,
    showInferred: showInferredLinks
  }), [graphData, showAllMessages, expandedIds, showInferredLinks]);

  const highlight = useMemo(
    () => computeHighlight(selectedNode?.id, visibleGraphData),
    [selectedNode?.id, visibleGraphData]
  );

  const topicMessages = useMemo(
    () => (selectedNode?.type === 'topic' ? messagesForTopic(selectedNode.id, graphData) : []),
    [selectedNode, graphData]
  );

  const connections = useMemo(
    () => (selectedNode ? connectionSummary(selectedNode.id, graphData.links) : null),
    [selectedNode, graphData]
  );

  const graphRef = useRef();
  const fileInputRef = useRef();
  const [windowSize, setWindowSize] = useState({ width: window.innerWidth, height: window.innerHeight });

  useEffect(() => {
    const handleResize = () => setWindowSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const no3DReason = reasonNo3D(windowSize.width, visibleGraphData.nodes.length);
  const is3D = wants3D && !no3DReason;

  // Runs after the render that adds any newly expanded nodes.
  useEffect(() => {
    if (focusRequest) graphRef.current?.focusNode(focusRequest.id);
  }, [focusRequest]);

  const selectNode = useCallback((id) => {
    const node = nodeById.get(id);
    if (!node) return;
    setExpandedIds(prev => new Set([...prev, ...expansionFor(node, graphData)]));
    setSelectedId(id);
    setFocusRequest({ id });
  }, [nodeById, graphData]);

  const clearSelection = useCallback(() => setSelectedId(null), []);

  const collapseMessages = () => {
    setExpandedIds(new Set());
    if (selectedNode?.type === 'message') setSelectedId(null);
  };

  const handleFileUpload = async (file) => {
    if (!file) return;
    
    const validExtensions = ['.txt', '.json', '.zip'];
    if (!validExtensions.some(ext => file.name.toLowerCase().endsWith(ext))) {
      alert("Invalid file format. Please upload a .txt, .json, or .zip file.");
      return;
    }

    setLoading(true);
    setLoadingStatus('Starting…');

    try {
      const data = await analyseFile(file, setLoadingStatus);
      setAnalysisId(data.id);
      setTopicCount(MIN_TOPIC_COUNT);
      setGraphData(formatGraphData(data.graph));
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
      const graphDataRaw = await setTopicCountInWorker(nextCount);
      setGraphData(formatGraphData(graphDataRaw));
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
      const data = await searchMessages(query.trim(), 8);
      setQueryResults(data.results || []);
    } catch (err) {
      alert("Search failed: " + err.message);
    } finally {
      setQueryLoading(false);
    }
  };

  const handleResultClick = (result) => selectNode(nodeId.message(result.message_id));

  const resetApp = () => {
    setAnalysisId(null);
    setGraphData({ nodes: [], links: [], topicLinks: [] });
    setSelectedId(null);
    setQuery('');
    setQueryResults([]);
    setDragActive(false);
    setTopicCount(MIN_TOPIC_COUNT);
    setExpandedIds(new Set());
    setShowAllMessages(false);
    setBrowserOpen(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <MotionConfig reducedMotion="user">
    <div className={`app-container ${!analysisId ? 'landing-mode' : ''} ${is3D ? 'view-3d' : ''}`}>
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
                  <div className="loading-state" role="status">
                    <div className="spinner"></div>
                    <p>{loadingStatus}</p>
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
                The drop zone above runs entirely in your browser: Python compiled to
                WebAssembly builds the graph and a quantised model embeds your messages,
                so your export is never uploaded. Running the FastAPI service locally
                exposes the same analysis as a plain REST API — the same two calls
                you'd make from your own code:
              </p>
              <CodeExample />
            </section>
          </div>
        </div>
      )}


      {analysisId && (
        <>
          <Suspense fallback={<div className="graph-loading" role="status">Loading graph…</div>}>
            {is3D ? (
              <Graph3D
                key={`${analysisId}-3d`}
                ref={graphRef}
                graph={visibleGraphData}
                highlight={highlight}
                selectedId={selectedNode?.id}
                width={windowSize.width}
                height={windowSize.height}
                onSelect={selectNode}
                onClear={clearSelection}
              />
            ) : (
              <Graph2D
                key={`${analysisId}-2d`}
                ref={graphRef}
                graph={visibleGraphData}
                highlight={highlight}
                selectedId={selectedNode?.id}
                width={windowSize.width}
                height={windowSize.height}
                onSelect={selectNode}
                onClear={clearSelection}
              />
            )}
          </Suspense>

          <div className="sr-only" role="status">
            {selectedNode ? `Selected ${describeNode(selectedNode)}` : ''}
          </div>

          <div className="top-bar glass-panel overlay-panel">
            <div className="branding">
              <Network size={20} /> <span className="branding-name">Social RAG</span>
            </div>
            <form className="search-container" role="search" onSubmit={(e) => { e.preventDefault(); executeSearch(); }}>
              <button type="submit" className="search-submit" aria-label="Search messages">
                <Search className="search-icon" size={18} />
              </button>
              <input 
                type="text" 
                id="rag-search" 
                aria-label="Ask a question about the chat"
                placeholder="Ask a question about the chat..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {queryLoading && <div className="search-spinner" role="status" aria-label="Searching"></div>}
            </form>
            <div className="view-toggle" role="group" aria-label="Graph view">
              <button type="button" aria-pressed={!is3D} onClick={() => setWants3D(false)}>2D</button>
              <button type="button" aria-pressed={is3D} disabled={!!no3DReason} title={no3DReason || 'Show the graph in 3D'} onClick={() => setWants3D(true)}>3D</button>
            </div>
            <button type="button" className="icon-btn" title="Browse nodes" aria-label="Browse nodes" aria-expanded={browserOpen} onClick={() => setBrowserOpen(o => !o)}>
              <List size={20} />
            </button>
            <button type="button" className="icon-btn" title="Load another chat" aria-label="Load another chat" onClick={resetApp}>
              <FolderOpen size={20} />
            </button>
          </div>

          <AnimatePresence mode="wait">
            {browserOpen ? (
              <Motion.div key="browser" {...PANEL_MOTION} className="results-panel glass-panel overlay-panel">
                <NodeBrowser nodes={graphData.nodes} selectedId={selectedNode?.id} onSelect={selectNode} onClose={() => setBrowserOpen(false)} />
              </Motion.div>
            ) : queryResults.length > 0 && (
              <Motion.div key="results" {...PANEL_MOTION} className="results-panel glass-panel overlay-panel">
                <div className="panel-header">
                  <h3>Search Results</h3>
                  <button type="button" className="close-btn" aria-label="Close search results" onClick={() => setQueryResults([])}><X size={20} /></button>
                </div>
                <div className="results-list">
                  {queryResults.map((result, idx) => (
                    <div key={idx} className="result-entry">
                      <button type="button" className="result-item" onClick={() => handleResultClick(result)}>
                        <span className="result-meta">
                          <span className="result-sender">{result.sender}</span>
                          <span>Match: {(result.score * 100).toFixed(0)}%</span>
                        </span>
                        <span className="result-text">{result.content}</span>
                      </button>
                      {/* From src/conversation_linker.py's edge list, not the graph's own
                          `inferred` edges above (_infer_lexical_continuity) — a separate,
                          richer signal (semantic + temporal + turn-taking + lexical) the
                          backend attaches to /query results, not to graphData. */}
                      {result.linked_context && result.linked_context.length > 0 && (
                        <div className="linked-context">
                          <span className="linked-context-label">Linked context</span>
                          {result.linked_context.map((linked, lidx) => (
                            <button
                              type="button"
                              key={lidx}
                              className="linked-context-item"
                              onClick={() => handleResultClick(linked)}
                            >
                              <span className="linked-context-sender">{linked.sender}</span>
                              <span className="linked-context-text">{linked.content}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Motion.div>
            )}
          </AnimatePresence>

          <div className="right-rail">
          <AnimatePresence>
            {selectedNode && (
              <Motion.div key="details" {...PANEL_MOTION} className="details-sidebar glass-panel overlay-panel">
                <div className="panel-header">
                  <h2>{selectedNode.label || selectedNode.id}</h2>
                  <button type="button" className="close-btn" aria-label="Close details" onClick={clearSelection}><X size={20} /></button>
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
                            <button type="button" key={m.id} className="result-item" onClick={() => selectNode(m.id)}>
                              <span className="result-meta">
                                <span className="result-sender">{m.sender || ''}</span>
                                <span>{m.timestamp ? new Date(m.timestamp).toLocaleString() : ''}</span>
                              </span>
                              <span className="result-text">{m.text}</span>
                            </button>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}
                <p className="connection-summary">
                  {connections.confirmed} confirmed connection{connections.confirmed === 1 ? '' : 's'}, {connections.inferred} inferred
                  {!showAllMessages && (selectedNode.type === 'person' || selectedNode.type === 'topic') && <><br />The graph adds up to {EXPAND_LIMIT} of the latest related messages.</>}
                </p>
              </Motion.div>
            )}
          </AnimatePresence>

          <div className="legend-panel glass-panel overlay-panel">
            <button type="button" className="legend-toggle" aria-expanded={legendOpen} onClick={() => setLegendOpen(o => !o)}>
              <h4>Legend</h4>
              <ChevronDown size={16} className={legendOpen ? '' : 'legend-chevron-collapsed'} />
            </button>
            <div className={`legend-collapse ${legendOpen ? '' : 'collapsed'}`} inert={!legendOpen}>
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
                <div className="topic-count-control">
                  <label className="legend-check">
                    <input type="checkbox" checked={showAllMessages} onChange={(e) => setShowAllMessages(e.target.checked)} />
                    <span>Show every message</span>
                  </label>
                  {!showAllMessages && expandedIds.size > 0 && (
                    <button type="button" className="text-btn" onClick={collapseMessages}>
                      Hide {expandedIds.size} expanded message{expandedIds.size === 1 ? '' : 's'}
                    </button>
                  )}
                </div>
                <div className="legend-item"><span className="dot" style={{background: `linear-gradient(135deg, ${COMMUNITY_PALETTE[0]}, ${COMMUNITY_PALETTE[3]}, ${COMMUNITY_PALETTE[6]})`}}></span> Person (color: group, size: influence)</div>
                <div className="legend-item"><span className="dot topic-dot" style={{borderRadius: '2px', transform: 'rotate(45deg)'}}></span> Topic</div>
                <div className="legend-item"><span className="dot message-dot"></span> Message</div>
                <div className="legend-item"><span className="dot chat-dot"></span> Chat</div>
                <div className="legend-item"><span className="reply-link-swatch"></span> Confirmed reply</div>
                <div className="legend-item">
                  <label className="legend-check">
                    <input
                      type="checkbox"
                      checked={showInferredLinks}
                      onChange={(e) => setShowInferredLinks(e.target.checked)}
                    />
                    <span className="inferred-link-swatch"></span>
                    <span style={{fontSize: '0.75rem', color: 'var(--text-muted)'}}>
                      Show inferred connections (shares wording, no formal reply — never affects influence scores{is3D && '; no arrowhead in 3D'})
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
          </div>
        </>
      )}
    </div>
    </MotionConfig>
  );
}

export default App;
