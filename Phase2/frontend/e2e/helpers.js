import { expect } from '@playwright/test';

// Builds the backend's {nodes, edges} shape at a chosen size, at the same
// edge mix the real builder produces, so UI tests and benchmarks don't need
// Pyodide or the embedding model.
export const syntheticGraph = (messageCount, peopleCount = 10, topicCount = 5) => {
  const people = Array.from({ length: peopleCount }, (_, i) => ({
    id: `p_User ${i}`, type: 'person', label: `User ${i}`, pagerank: 1 / (i + 1), community: i % 3,
    message_count: 5, replies_received: 2, is_influencer: i === 0, is_info_broker: i === 1,
  }));
  const topics = (count) => Array.from({ length: count }, (_, i) => ({ id: `topic ${i}`, type: 'topic', label: `topic ${i}` }));
  const nodes = [{ id: 'chat', type: 'chat', label: 'chat' }, ...people, ...topics(topicCount)];
  const edges = topics(topicCount).map(t => ({ source: 'chat', target: t.id, relationship: 'DISCUSSED' }));
  for (let i = 0; i < messageCount; i++) {
    const id = `m_${i}`;
    nodes.push({
      id, type: 'message', label: `message ${i}...`, text: `message ${i} body`, sender: `User ${i % peopleCount}`,
      timestamp: new Date(1767225600000 + i * 60000).toISOString(), reply_depth: i % 4, thread_root: 'm_0', thread_size: 4,
    });
    edges.push({ source: `p_User ${i % peopleCount}`, target: id, relationship: 'SENT' });
    edges.push({ source: id, target: 'chat', relationship: 'PART_OF' });
    if (i) edges.push({ source: id, target: `m_${i - 1}`, relationship: 'REPLIED_TO', inferred: i % 2 === 0 });
    if (i % 4 === 0) edges.push({ source: id, target: `topic ${i % topicCount}`, relationship: 'MENTIONS_TOPIC' });
  }
  people.forEach((p, i) => edges.push({ source: p.id, target: people[(i + 1) % peopleCount].id, relationship: 'INTERACTS_WITH', hidden: true, weight: 1 }));
  return { nodes, edges };
};

// Replaces the pipeline worker with one answering from canned data.
export const useFakePipeline = async (page, graph, results = []) => {
  await page.addInitScript(({ graph, results }) => {
    window.__graphUpdates = 0;
    window.Worker = class {
      postMessage({ id, type, payload }) {
        let result;
        if (type === 'analyse') result = { id: 'fake', stats: {}, graph };
        if (type === 'query') result = { results };
        if (type === 'setTopicCount') {
          const extra = { id: `topic ${payload.topN}`, type: 'topic', label: `topic ${payload.topN}` };
          result = { nodes: [...graph.nodes, extra], edges: graph.edges };
        }
        setTimeout(() => this.onmessage({ data: { id, result } }), 0);
      }
    };
  }, { graph, results });
};

export const uploadFixture = async (page) => {
  await page.locator('input[type="file"]').setInputFiles({ name: 'chat.txt', mimeType: 'text/plain', buffer: Buffer.from('x') });
  await expect(page.locator('canvas').first()).toBeVisible();
};

export const openBrowser = (page) => page.getByRole('button', { name: 'Browse nodes' }).click();
