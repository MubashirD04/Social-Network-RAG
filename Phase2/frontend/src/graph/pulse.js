// Turns a selection into pulses: which links light up, in what direction, and
// when. Pure data, so both renderers can draw the same animation.
const MAX_FAN_OUT = 60;
const MAX_THREAD_HOPS = 300;
const MAX_VISIBLE_NODES = 2000;
const FAN_OUT_MS = 1400;
const MAX_HOP_MS = 240;
const MAX_THREAD_MS = 4000;
const TOPIC_TRAVEL_MS = 1000;
const MAX_TOPIC_GAP_MS = 400;
const RING_MS = 1200;
const LOOP_PAUSE_MS = 800;
const ARRIVAL_MS = 450;
// Share of a link the pulse covers at once.
const PULSE_LENGTH = 0.3;

const fanOut = (selectedId, links) => {
  const hops = links
    .filter(l => l.source === selectedId || l.target === selectedId)
    .slice(0, MAX_FAN_OUT)
    .map(l => ({
      from: selectedId,
      to: l.source === selectedId ? l.target : l.source,
      inferred: l.inferred,
      start: 0,
      duration: FAN_OUT_MS,
    }));
  return { hops, duration: hops.length ? FAN_OUT_MS : 0 };
};

// A topic's messages aren't linked to each other, so its flow runs along each
// topic-message link in turn, from the earliest message to the latest.
const topicFlow = (selectedId, visible) => {
  const timeOf = new Map(visible.nodes.map(n => [n.id, new Date(n.timestamp).getTime()]));
  const mentions = visible.links
    .filter(l => l.relationship === 'MENTIONS_TOPIC' && l.target === selectedId)
    .sort((a, b) => timeOf.get(a.source) - timeOf.get(b.source))
    .slice(0, MAX_FAN_OUT);
  if (!mentions.length) return fanOut(selectedId, visible.links);

  const gapMs = Math.min(MAX_TOPIC_GAP_MS, MAX_THREAD_MS / mentions.length);
  const hops = mentions.map((l, i) => ({
    from: selectedId,
    to: l.source,
    inferred: l.inferred,
    start: i * gapMs,
    duration: TOPIC_TRAVEL_MS,
  }));
  return { hops, duration: (mentions.length - 1) * gapMs + TOPIC_TRAVEL_MS };
};

// Reply links run original -> reply once formatted, so the thread's start is
// found by walking back and its pulse flows forward from there, branching
// wherever a message drew several replies.
const threadFlow = (selectedId, links) => {
  const replies = links.filter(l => l.relationship === 'REPLIED_TO');
  const parentOf = new Map(replies.map(l => [l.target, l.source]));

  const walked = new Set([selectedId]);
  let root = selectedId;
  while (parentOf.has(root) && !walked.has(parentOf.get(root))) {
    root = parentOf.get(root);
    walked.add(root);
  }

  const childLinks = new Map();
  replies.forEach(l => {
    if (!childLinks.has(l.source)) childLinks.set(l.source, []);
    childLinks.get(l.source).push(l);
  });

  const reached = [];
  const seen = new Set([root]);
  const queue = [{ id: root, depth: 0 }];
  while (queue.length && reached.length < MAX_THREAD_HOPS) {
    const { id, depth } = queue.shift();
    (childLinks.get(id) || []).forEach(link => {
      if (seen.has(link.target)) return;
      seen.add(link.target);
      reached.push({ link, depth });
      queue.push({ id: link.target, depth: depth + 1 });
    });
  }
  if (!reached.length) return { hops: [], duration: 0 };

  const depths = Math.max(...reached.map(r => r.depth)) + 1;
  const hopMs = Math.min(MAX_HOP_MS, MAX_THREAD_MS / depths);
  const hopDuration = hopMs * (1 + PULSE_LENGTH);
  return {
    hops: reached.map(({ link, depth }) => ({
      from: link.source,
      to: link.target,
      inferred: link.inferred,
      // Each hop starts as the previous one's front reaches the node, at a
      // constant speed, so a thread reads as one pulse rather than a series.
      start: depth * hopMs,
      duration: hopDuration,
      steady: true,
    })),
    duration: (depths - 1) * hopMs + hopDuration,
  };
};

export const buildPulsePlan = (selected, visible) => {
  if (!selected || visible.nodes.length > MAX_VISIBLE_NODES) return null;
  const flows = {
    message: () => threadFlow(selected.id, visible.links),
    topic: () => topicFlow(selected.id, visible),
  };
  const { hops, duration } = (flows[selected.type] ?? (() => fanOut(selected.id, visible.links)))();
  return { origin: selected.id, hops, duration, cycle: Math.max(duration + ARRIVAL_MS, RING_MS) + LOOP_PAUSE_MS };
};

// The pulse repeats for as long as the node stays selected.
export const loopElapsed = (plan, elapsed) => elapsed % plan.cycle;

export const ringProgress = (elapsed) => elapsed / RING_MS;

const easeInOut = (t) => (1 - Math.cos(Math.PI * t)) / 2;

// Which stretch of its link a hop covers at some moment, as fractions from the
// source node (0) to the target (1), or null when it isn't showing. The pulse
// grows out of the source and drains into the target, instead of sliding along
// at a fixed length and vanishing when it gets there.
export const hopSegment = (hop, elapsed) => {
  const t = (elapsed - hop.start) / hop.duration;
  if (t < 0 || t > 1) return null;
  const front = (hop.steady ? t : easeInOut(t)) * (1 + PULSE_LENGTH);
  return { tail: Math.max(0, front - PULSE_LENGTH), head: Math.min(1, front) };
};

// How far through the target's arrival ripple a hop is, or null outside it.
export const arrivalProgress = (hop, elapsed) => {
  const t = (elapsed - hop.start - hop.duration) / ARRIVAL_MS;
  return t < 0 || t > 1 ? null : t;
};
