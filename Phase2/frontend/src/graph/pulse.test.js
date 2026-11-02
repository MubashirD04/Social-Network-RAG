import { describe, expect, it } from 'vitest';
import { arrivalProgress, buildPulsePlan, hopSegment, loopElapsed } from './pulse.js';

const link = (source, target, extra = {}) => ({ id: `${source}-${target}`, source, target, relationship: 'REPLIED_TO', inferred: false, ...extra });
const visible = (links, nodes = []) => ({ nodes, links });

describe('fan-out from a person or topic', () => {
  it('always travels away from the selected node, whatever the edge direction', () => {
    const plan = buildPulsePlan({ id: 'p', type: 'person' }, visible([
      link('p', 'a', { relationship: 'SENT' }),
      link('b', 'p', { relationship: 'INTERACTS_WITH' }),
      link('x', 'y', { relationship: 'SENT' }),
    ]));
    expect(plan.hops.map(h => [h.from, h.to])).toEqual([['p', 'a'], ['p', 'b']]);
    expect(new Set(plan.hops.map(h => h.start))).toEqual(new Set([0]));
  });

  it('caps pulses from a hub', () => {
    const links = Array.from({ length: 500 }, (_, i) => link(`m${i}`, 'chat', { relationship: 'PART_OF' }));
    expect(buildPulsePlan({ id: 'chat', type: 'chat' }, visible(links)).hops).toHaveLength(60);
  });
});

describe('flow along a message thread', () => {
  const thread = [link('a', 'b'), link('b', 'c', { inferred: true }), link('b', 'd'), link('c', 'e')];

  it('starts at the root even when a later message was clicked', () => {
    const { hops } = buildPulsePlan({ id: 'c', type: 'message' }, visible(thread));
    expect(hops[0]).toMatchObject({ from: 'a', to: 'b', start: 0 });
  });

  it('flows in order, branches together, and keeps the inferred flag', () => {
    const { hops, duration } = buildPulsePlan({ id: 'a', type: 'message' }, visible(thread));
    const startOf = (to) => hops.find(h => h.to === to).start;
    expect(startOf('b')).toBeLessThan(startOf('c'));
    expect(startOf('c')).toBe(startOf('d'));
    expect(startOf('c')).toBeLessThan(startOf('e'));
    expect(hops.find(h => h.to === 'c').inferred).toBe(true);
    expect(duration).toBeCloseTo(792);
  });

  it('ignores links that are not replies', () => {
    const { hops } = buildPulsePlan({ id: 'a', type: 'message' }, visible([link('p', 'a', { relationship: 'SENT' })]));
    expect(hops).toEqual([]);
  });

  it('speeds up so a long thread stays within the time cap', () => {
    const links = Array.from({ length: 100 }, (_, i) => link(`m${i}`, `m${i + 1}`));
    const { duration, hops } = buildPulsePlan({ id: 'm50', type: 'message' }, visible(links));
    expect(hops).toHaveLength(100);
    expect(duration).toBeLessThan(4100);
  });

  it('survives a reply cycle', () => {
    const { hops } = buildPulsePlan({ id: 'a', type: 'message' }, visible([link('a', 'b'), link('b', 'a')]));
    expect(hops.length).toBeLessThanOrEqual(2);
  });
});

describe('flow through a topic', () => {
  const nodes = [{ id: 'old', timestamp: '2026-01-01' }, { id: 'mid', timestamp: '2026-02-01' }, { id: 'new', timestamp: '2026-03-01' }, { id: 't', type: 'topic' }];
  const mention = (message) => link(message, 't', { relationship: 'MENTIONS_TOPIC' });

  it('visits messages one at a time from earliest to latest, moving outward', () => {
    const { hops } = buildPulsePlan({ id: 't', type: 'topic' }, visible([mention('new'), mention('old'), mention('mid'), link('chat', 't', { relationship: 'DISCUSSED' })], nodes));
    expect(hops.map(h => [h.from, h.to])).toEqual([['t', 'old'], ['t', 'mid'], ['t', 'new']]);
    expect(hops[0].start).toBeLessThan(hops[1].start);
    expect(hops[1].start).toBeLessThan(hops[2].start);
  });

  it('falls back to a fan-out when no messages are visible', () => {
    const { hops } = buildPulsePlan({ id: 't', type: 'topic' }, visible([link('chat', 't', { relationship: 'DISCUSSED' })], nodes));
    expect(hops.map(h => h.to)).toEqual(['chat']);
  });
});

it('loops with a pause, so the pulse repeats while selected', () => {
  const plan = buildPulsePlan({ id: 'p', type: 'person' }, visible([link('p', 'a', { relationship: 'SENT' })]));
  expect(plan.cycle).toBeGreaterThan(plan.duration);
  expect(loopElapsed(plan, plan.cycle + 50)).toBeCloseTo(50);
});

it('skips pulses on very large views', () => {
  expect(buildPulsePlan({ id: 'p', type: 'person' }, visible([], Array(2001).fill({})))).toBeNull();
});

describe('hopSegment', () => {
  const hop = { start: 100, duration: 1000 };

  it('only shows while the hop is running', () => {
    expect(hopSegment(hop, 50)).toBeNull();
    expect(hopSegment(hop, 1101)).toBeNull();
  });

  it('grows out of the source, staying attached to it', () => {
    const early = hopSegment(hop, 200);
    expect(early.tail).toBe(0);
    expect(early.head).toBeGreaterThan(0);
  });

  it('never exceeds the pulse length, and never leaves the link', () => {
    for (let elapsed = 100; elapsed <= 1100; elapsed += 25) {
      const { tail, head } = hopSegment(hop, elapsed);
      expect(tail).toBeGreaterThanOrEqual(0);
      expect(head).toBeLessThanOrEqual(1);
      expect(head - tail).toBeLessThanOrEqual(0.3 + 1e-9);
    }
  });

  it('drains into the target smoothly rather than vanishing at full length', () => {
    const lengthAt = (elapsed) => { const { tail, head } = hopSegment(hop, elapsed); return head - tail; };
    expect(hopSegment(hop, 1050).head).toBe(1);
    expect(lengthAt(1050)).toBeLessThan(0.3);
    expect(lengthAt(1099)).toBeLessThan(lengthAt(1050));
    expect(lengthAt(1100)).toBeCloseTo(0);
  });
});

it('ripples the target only after the pulse has fully arrived', () => {
  const hop = { start: 0, duration: 1000 };
  expect(arrivalProgress(hop, 999)).toBeNull();
  expect(arrivalProgress(hop, 1000)).toBe(0);
  expect(arrivalProgress(hop, 2000)).toBeNull();
});

it('starts each thread hop before the last has drained, so the flow is unbroken', () => {
  const { hops } = buildPulsePlan({ id: 'a', type: 'message' }, visible([link('a', 'b'), link('b', 'c')]));
  expect(hops[1].start).toBeLessThan(hops[0].start + hops[0].duration);
  expect(hops[0].steady).toBe(true);
});
