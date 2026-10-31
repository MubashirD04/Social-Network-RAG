import { describe, expect, it } from 'vitest';
import {
  buildVisibleGraph, computeHighlight, connectionSummary, createLiveCache, expansionFor,
  formatGraphData, messagesForTopic, reconcileLive, EXPAND_LIMIT
} from './graphData.js';
import { contrastOnBackground, linkStyle } from './graphStyle.js';

const raw = {
  nodes: [
    { id: 'chat', type: 'chat', label: 'chat' },
    { id: 'p_A', type: 'person', label: 'A', pagerank: 0.8, community: 0 },
    { id: 'p_B', type: 'person', label: 'B', pagerank: 0.2, community: 0 },
    { id: 'm_1', type: 'message', timestamp: '2026-01-01T00:00:00' },
    { id: 'm_2', type: 'message', timestamp: '2026-01-01T00:01:00', reply_depth: 1 },
    { id: 'm_3', type: 'message', timestamp: '2026-01-01T00:02:00' },
    { id: 'coffee', type: 'topic', label: 'coffee' }
  ],
  edges: [
    { source: 'p_A', target: 'm_1', relationship: 'SENT' },
    { source: 'p_B', target: 'm_2', relationship: 'SENT' },
    { source: 'p_A', target: 'm_3', relationship: 'SENT' },
    { source: 'm_1', target: 'chat', relationship: 'PART_OF' },
    { source: 'm_2', target: 'm_1', relationship: 'REPLIED_TO' },
    { source: 'm_3', target: 'm_2', relationship: 'REPLIED_TO', inferred: true },
    { source: 'p_B', target: 'p_A', relationship: 'INTERACTS_WITH', hidden: true },
    { source: 'm_2', target: 'coffee', relationship: 'MENTIONS_TOPIC' },
    { source: 'chat', target: 'coffee', relationship: 'DISCUSSED' }
  ]
};
const graph = formatGraphData(raw);
const overview = (expanded = []) => buildVisibleGraph(graph, { showAllMessages: false, expandedIds: new Set(expanded), showInferred: true });

describe('formatGraphData', () => {
  it('flips replies to point forward in conversation order', () => {
    const reply = graph.links.find(l => l.id === 'REPLIED_TO:m_1->m_2');
    expect(reply).toMatchObject({ source: 'm_1', target: 'm_2', inferred: false });
  });

  it('sizes people by PageRank and keeps val in step with the radius', () => {
    const a = graph.nodes.find(n => n.id === 'p_A');
    const b = graph.nodes.find(n => n.id === 'p_B');
    expect(a.radius).toBeGreaterThan(b.radius);
    expect(a.val).toBeCloseTo(a.radius ** 2);
  });

  it('shrinks messages with reply depth', () => {
    const [root, reply] = ['m_1', 'm_2'].map(id => graph.nodes.find(n => n.id === id));
    expect(reply.radius).toBeLessThan(root.radius);
  });

  it('derives person-to-topic links through messages', () => {
    expect(graph.topicLinks.map(l => l.id)).toEqual(['DISCUSSES:p_B->coffee']);
  });
});

describe('buildVisibleGraph', () => {
  it('shows people and topics but no messages by default', () => {
    const { nodes, links } = overview();
    expect(nodes.some(n => n.type === 'message')).toBe(false);
    expect(links.map(l => l.relationship).sort()).toEqual(['DISCUSSED', 'DISCUSSES', 'INTERACTS_WITH']);
  });

  it('adds expanded messages without the PART_OF hub edge', () => {
    const { nodes, links } = overview(['m_1', 'm_2']);
    expect(nodes.map(n => n.id)).toContain('m_2');
    expect(links.some(l => l.relationship === 'REPLIED_TO')).toBe(true);
    expect(links.some(l => l.relationship === 'PART_OF')).toBe(false);
  });

  it('hides hidden edges and derived links in the full view', () => {
    const { nodes, links } = buildVisibleGraph(graph, { showAllMessages: true, expandedIds: new Set(), showInferred: true });
    expect(nodes).toHaveLength(raw.nodes.length);
    expect(links.some(l => l.hidden || l.relationship === 'DISCUSSES')).toBe(false);
    expect(links.some(l => l.relationship === 'PART_OF')).toBe(true);
  });

  it('drops only inferred edges when the toggle is off', () => {
    const { links } = buildVisibleGraph(graph, { showAllMessages: true, expandedIds: new Set(), showInferred: false });
    expect(links.some(l => l.inferred)).toBe(false);
    expect(links.some(l => l.relationship === 'REPLIED_TO')).toBe(true);
  });
});

describe('expansionFor', () => {
  const node = (id) => graph.nodes.find(n => n.id === id);

  it('returns a person\'s messages, newest first', () => {
    expect(expansionFor(node('p_A'), graph)).toEqual(['m_3', 'm_1']);
  });

  it('returns a message and its reply neighbours, confirmed or inferred', () => {
    expect(expansionFor(node('m_2'), graph).sort()).toEqual(['m_1', 'm_2', 'm_3']);
  });

  it('returns messages mentioning a topic', () => {
    expect(expansionFor(node('coffee'), graph)).toEqual(['m_2']);
  });

  it('caps what one selection adds', () => {
    const count = EXPAND_LIMIT + 5;
    const big = formatGraphData({
      nodes: [{ id: 'p_X', type: 'person' }, ...Array.from({ length: count }, (_, i) => ({ id: `m_${i}`, type: 'message', timestamp: `2026-01-01T00:00:${String(i % 60).padStart(2, '0')}` }))],
      edges: Array.from({ length: count }, (_, i) => ({ source: 'p_X', target: `m_${i}`, relationship: 'SENT' }))
    });
    expect(expansionFor(big.nodes[0], big)).toHaveLength(EXPAND_LIMIT);
  });
});

describe('selection helpers', () => {
  it('highlights one hop from the selected node', () => {
    const highlight = computeHighlight('m_2', buildVisibleGraph(graph, { showAllMessages: true, expandedIds: new Set(), showInferred: true }));
    expect([...highlight.nodeIds].sort()).toEqual(['coffee', 'm_1', 'm_2', 'm_3', 'p_B']);
    expect(computeHighlight(null, overview())).toBeNull();
  });

  it('counts confirmed and inferred connections, skipping hidden edges', () => {
    expect(connectionSummary('m_2', graph.links)).toEqual({ confirmed: 3, inferred: 1 });
  });

  it('lists a topic\'s messages chronologically', () => {
    expect(messagesForTopic('coffee', graph).map(m => m.id)).toEqual(['m_2']);
  });
});

describe('reconcileLive', () => {
  it('keeps positions across data updates and fresh payloads', () => {
    const cache = createLiveCache();
    const first = reconcileLive(cache, overview());
    first.nodes.find(n => n.id === 'p_A').x = 42;
    const again = reconcileLive(cache, buildVisibleGraph(formatGraphData(raw), { showAllMessages: false, expandedIds: new Set(), showInferred: true }));
    expect(again.nodes.find(n => n.id === 'p_A').x).toBe(42);
  });

  it('seeds a new node beside a placed neighbour', () => {
    const cache = createLiveCache();
    const first = reconcileLive(cache, overview());
    first.nodes.forEach(n => { n.x = 100; n.y = 100; });
    const next = reconcileLive(cache, overview(['m_1']));
    const added = next.nodes.find(n => n.id === 'm_1');
    expect(Math.abs(added.x - 100)).toBeLessThanOrEqual(10);
  });

  it('drops links whose endpoint left, even after the library resolved them', () => {
    const cache = createLiveCache();
    const first = reconcileLive(cache, overview(['m_1', 'm_2']));
    const live = first.links.find(l => l.relationship === 'REPLIED_TO');
    const byId = new Map(first.nodes.map(n => [n.id, n]));
    live.source = byId.get(live.source);
    live.target = byId.get(live.target);
    const next = reconcileLive(cache, overview());
    expect(next.links.some(l => l.relationship === 'REPLIED_TO')).toBe(false);
    const back = reconcileLive(cache, overview(['m_1', 'm_2']));
    expect(typeof back.links.find(l => l.relationship === 'REPLIED_TO').source).toBe('string');
  });
});

describe('edge readability', () => {
  const link = (extra) => ({ id: 'x', relationship: 'REPLIED_TO', inferred: false, ...extra });

  it('keeps confirmed and inferred distinct in every state', () => {
    const highlight = { nodeIds: new Set(), linkIds: new Set(['x']) };
    [null, highlight].forEach(state => {
      expect(linkStyle(link(), state).color).not.toBe(linkStyle(link({ inferred: true }), state).color);
    });
  });

  it('meets 3:1 contrast for both edge kinds when idle', () => {
    [link(), link({ inferred: true })].forEach(l => {
      const { color, opacity } = linkStyle(l, null);
      expect(contrastOnBackground(color, opacity)).toBeGreaterThanOrEqual(3);
    });
  });
});
