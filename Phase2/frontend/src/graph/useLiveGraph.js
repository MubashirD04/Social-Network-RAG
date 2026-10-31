import { useMemo } from 'react';
import { createLiveCache, reconcileLive } from './graphData.js';

// A renderer's private, position-carrying copy of the visible graph.
export function useLiveGraph(graph) {
  const cache = useMemo(() => createLiveCache(), []);
  const live = useMemo(() => reconcileLive(cache, graph), [cache, graph]);
  return { live, cache };
}

// A just-added node has no position until the simulation's next tick.
export function whenPositioned(cache, id, callback) {
  let attempts = 0;
  const check = () => {
    const node = cache.nodes.get(id);
    if (node?.x !== undefined) callback(node);
    else if (attempts++ < 60) requestAnimationFrame(check);
  };
  check();
}
