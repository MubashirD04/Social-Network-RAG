import { nodeRadius } from './graphStyle.js';

// Selecting a very active person shouldn't flood the overview they're looking at.
export const EXPAND_LIMIT = 40;

const linkId = (relationship, source, target) => `${relationship}:${source}->${target}`;

const byNewest = (a, b) => new Date(b.timestamp) - new Date(a.timestamp);

// Person -> topic edges aren't in the backend graph (the path runs through
// messages), but the overview hides messages, so without these a topic
// would float unconnected to anyone who talked about it.
const deriveTopicLinks = (links) => {
  const senderOf = new Map();
  links.forEach(l => { if (l.relationship === 'SENT') senderOf.set(l.target, l.source); });

  const derived = new Map();
  links.forEach(l => {
    if (l.relationship !== 'MENTIONS_TOPIC') return;
    const sender = senderOf.get(l.source);
    if (!sender) return;
    const id = linkId('DISCUSSES', sender, l.target);
    if (!derived.has(id)) {
      derived.set(id, { id, source: sender, target: l.target, relationship: 'DISCUSSES', inferred: false, hidden: false });
    }
  });
  return [...derived.values()];
};

// Shared by the initial upload and by the topic-count control, both of
// which swap a fresh {nodes, edges} payload from the backend into
// react-force-graph's {nodes, links} shape.
export const formatGraphData = (raw) => {
  const maxPagerank = Math.max(0, ...raw.nodes.map(n => n.pagerank || 0));
  const nodes = raw.nodes.map(n => {
    const radius = nodeRadius(n, maxPagerank);
    // The libraries derive hit areas and arrowhead offsets from val, so it
    // has to agree with the radius actually drawn (nodeRelSize is 1).
    return { ...n, id: String(n.id), radius, val: radius * radius };
  });
  const links = raw.edges.map(e => {
    // Backend stores REPLIED_TO as reply -> original (newer message
    // pointing at the one it replies to), which is what the reply
    // thread/stats calculations need during analysis. Flip it here so the
    // rendered arrow points forward in conversation order (original
    // -> reply) instead of backward.
    const isReply = e.relationship === 'REPLIED_TO';
    const source = String(isReply ? e.target : e.source);
    const target = String(isReply ? e.source : e.target);
    return {
      id: linkId(e.relationship, source, target),
      source,
      target,
      relationship: e.relationship,
      // Two messages that were never in a real reply thread but clearly
      // share content (see _infer_lexical_continuity in
      // social_graph_builder.py) still get a REPLIED_TO edge so thread
      // rendering picks them up, but it's a guess rather than a fact —
      // carried through so it can render visually distinct from a
      // confirmed reply instead of claiming the same certainty.
      inferred: !!e.inferred,
      hidden: !!e.hidden
    };
  });
  return { nodes, links, topicLinks: deriveTopicLinks(links) };
};

// Every message is a node and edges run at nearly 4x the message count, so
// the default view is people and topics, with messages added on demand.
export const buildVisibleGraph = (graph, { showAllMessages, expandedIds, showInferred }) => {
  const allowInferred = (l) => showInferred || !l.inferred;

  if (showAllMessages) {
    return { nodes: graph.nodes, links: graph.links.filter(l => !l.hidden && allowInferred(l)) };
  }

  const nodes = graph.nodes.filter(n => n.type !== 'message' || expandedIds.has(n.id));
  const visible = new Set(nodes.map(n => n.id));
  const links = [...graph.links, ...graph.topicLinks].filter(l => (
    // PART_OF ties every message to the chat node: pure noise once only a
    // handful of messages are showing. INTERACTS_WITH is hidden in the full
    // view but it's the overview's person-to-person summary.
    l.relationship !== 'PART_OF' && visible.has(l.source) && visible.has(l.target) && allowInferred(l)
  ));
  return { nodes, links };
};

// The messages that should appear when a node is selected in the overview.
export const expansionFor = (node, graph) => {
  const byId = new Map(graph.nodes.map(n => [n.id, n]));
  const latest = (ids) => ids.map(id => byId.get(id)).filter(Boolean).sort(byNewest).slice(0, EXPAND_LIMIT).map(n => n.id);

  if (node.type === 'person') {
    return latest(graph.links.filter(l => l.relationship === 'SENT' && l.source === node.id).map(l => l.target));
  }
  if (node.type === 'topic') {
    return latest(graph.links.filter(l => l.relationship === 'MENTIONS_TOPIC' && l.target === node.id).map(l => l.source));
  }
  if (node.type === 'message') {
    const neighbors = graph.links
      .filter(l => l.relationship === 'REPLIED_TO' && (l.source === node.id || l.target === node.id))
      .map(l => (l.source === node.id ? l.target : l.source));
    return [node.id, ...neighbors];
  }
  return [];
};

// Drives click-to-highlight: every link directly touching the selected node
// lights up, along with the neighbors on the other end. Everything else dims.
export const computeHighlight = (selectedId, visible) => {
  if (!selectedId) return null;
  const nodeIds = new Set([selectedId]);
  const linkIds = new Set();
  visible.links.forEach(l => {
    if (l.source === selectedId || l.target === selectedId) {
      linkIds.add(l.id);
      nodeIds.add(l.source);
      nodeIds.add(l.target);
    }
  });
  return { nodeIds, linkIds };
};

// Text equivalent of the solid/dashed distinction, for the details panel.
export const connectionSummary = (id, links) => {
  const touching = links.filter(l => !l.hidden && (l.source === id || l.target === id));
  const inferred = touching.filter(l => l.inferred).length;
  return { confirmed: touching.length - inferred, inferred };
};

// Topics are only meaningful in relation to what was actually said.
// MENTIONS_TOPIC edges run message -> topic (see social_graph_builder.py).
export const messagesForTopic = (topicId, graph) => {
  const byId = new Map(graph.nodes.map(n => [n.id, n]));
  return graph.links
    .filter(l => l.relationship === 'MENTIONS_TOPIC' && l.target === topicId)
    .map(l => byId.get(l.source))
    .filter(Boolean)
    // Edge order follows thread/link construction, not chronology.
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
};

export const createLiveCache = () => ({ nodes: new Map(), links: new Map() });

// The force libraries write positions onto node objects and swap link
// source/target for node references. Each renderer gets its own long-lived
// copies, so updating the data (topic slider, expanding messages, the inferred
// toggle) keeps the layout instead of restarting it, and App's data stays plain.
export const reconcileLive = (cache, visible) => {
  const nodeIds = new Set(visible.nodes.map(n => n.id));
  const linkIds = new Set(visible.links.map(l => l.id));
  cache.nodes.forEach((_, id) => { if (!nodeIds.has(id)) cache.nodes.delete(id); });
  // A kept link can't outlive either endpoint: its references would point at
  // a dropped node object.
  cache.links.forEach((link, id) => {
    if (!linkIds.has(id) || !nodeIds.has(endpointId(link.source)) || !nodeIds.has(endpointId(link.target))) {
      cache.links.delete(id);
    }
  });

  const added = [];
  const nodes = visible.nodes.map(n => {
    const live = cache.nodes.get(n.id);
    if (live) return Object.assign(live, n);
    const fresh = { ...n };
    cache.nodes.set(n.id, fresh);
    added.push(fresh);
    return fresh;
  });

  const links = visible.links.map(l => {
    const live = cache.links.get(l.id);
    if (live) {
      live.inferred = l.inferred;
      return live;
    }
    const fresh = { ...l };
    cache.links.set(l.id, fresh);
    return fresh;
  });

  // New nodes start beside something already placed, so they grow out of
  // the graph rather than flying in from the origin.
  added.forEach(node => {
    const link = visible.links.find(l => (l.source === node.id && hasPosition(cache.nodes.get(l.target)))
      || (l.target === node.id && hasPosition(cache.nodes.get(l.source))));
    if (!link) return;
    const anchor = cache.nodes.get(link.source === node.id ? link.target : link.source);
    node.x = anchor.x + (Math.random() - 0.5) * 20;
    node.y = anchor.y + (Math.random() - 0.5) * 20;
    if (anchor.z !== undefined) node.z = anchor.z + (Math.random() - 0.5) * 20;
  });

  return { nodes, links };
};

const endpointId = (end) => (typeof end === 'object' ? end.id : end);
const hasPosition = (node) => node?.x !== undefined;
