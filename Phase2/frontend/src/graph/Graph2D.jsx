import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { COLORS, linkStyle, nodeColor, prefersReducedMotion, pulseColor, pulseHeadColor, toRgba } from './graphStyle';
import { arrivalProgress, hopSegment, loopElapsed, ringProgress } from './pulse';
import { useLiveGraph, whenPositioned } from './useLiveGraph';

const tracePath = (ctx, node) => {
  const { x, y, radius: r } = node;
  ctx.beginPath();
  if (node.type === 'topic') {
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r, y);
    ctx.lineTo(x, y + r);
    ctx.lineTo(x - r, y);
    ctx.closePath();
  } else if (node.type === 'message') {
    ctx.ellipse(x, y, r * 1.4, r * 0.8, 0, 0, 2 * Math.PI);
  } else if (node.type === 'chat') {
    ctx.rect(x - r, y - r * 0.7, r * 2, r * 1.4);
  } else {
    ctx.arc(x, y, r, 0, 2 * Math.PI);
  }
};

const MESSAGE_LABEL_MIN_SCALE = 2;
const FIT_PADDING = 60;
const PULSE_WIDTH_PX = 1.75;
const PULSE_GLOW_WIDTH_PX = 7;
const PULSE_HEAD_PX = 1.5;
const HEAD_FADE_LENGTH = 0.12;
const ARRIVAL_SPREAD_PX = 12;
const LABEL_SIZE_PX = 11;

const drawHop = (ctx, hop, cache, elapsed, globalScale) => {
  const from = cache.nodes.get(hop.from);
  const to = cache.nodes.get(hop.to);
  if (from?.x === undefined || to?.x === undefined) return;

  const color = pulseColor(hop.inferred);
  const arrival = arrivalProgress(hop, elapsed);
  if (arrival !== null) {
    ctx.strokeStyle = toRgba(color, 0.7 * (1 - arrival));
    ctx.lineWidth = 1 / globalScale;
    ctx.beginPath();
    ctx.arc(to.x, to.y, to.radius + (ARRIVAL_SPREAD_PX * arrival) / globalScale, 0, 2 * Math.PI);
    ctx.stroke();
    return;
  }

  const segment = hopSegment(hop, elapsed);
  if (!segment) return;

  // Runs from edge to edge, because nodes hide what's drawn at their centers.
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy) || 1;
  const usable = Math.max(0, length - from.radius - to.radius);
  const tail = from.radius + segment.tail * usable;
  const head = from.radius + segment.head * usable;

  const startX = from.x + (dx / length) * tail;
  const startY = from.y + (dy / length) * tail;
  const endX = from.x + (dx / length) * head;
  const endY = from.y + (dy / length) * head;
  const trail = ctx.createLinearGradient(startX, startY, endX, endY);
  trail.addColorStop(0, toRgba(color, 0));
  trail.addColorStop(1, color);

  ctx.save();
  ctx.setLineDash([]);
  ctx.lineCap = 'round';
  ctx.strokeStyle = trail;
  // A wide faint pass under a fine one: a glow without canvas shadows, which
  // are slow to draw on every frame.
  [[PULSE_GLOW_WIDTH_PX, 0.18], [PULSE_WIDTH_PX, 1]].forEach(([width, alpha]) => {
    ctx.globalAlpha = alpha;
    ctx.lineWidth = width / globalScale;
    ctx.beginPath();
    ctx.moveTo(startX, startY);
    ctx.lineTo(endX, endY);
    ctx.stroke();
  });
  // The head fades as it enters the node, so it doesn't end on a hard point.
  ctx.globalAlpha = Math.min(1, (segment.head - segment.tail) / HEAD_FADE_LENGTH);
  ctx.fillStyle = pulseHeadColor(hop.inferred);
  ctx.beginPath();
  ctx.arc(endX, endY, PULSE_HEAD_PX / globalScale, 0, 2 * Math.PI);
  ctx.fill();
  ctx.restore();
};

const drawRing = (ctx, node, elapsed, globalScale) => {
  const t = ringProgress(elapsed);
  if (t > 1 || node?.x === undefined) return;
  ctx.strokeStyle = toRgba('#ffffff', 0.6 * (1 - t));
  ctx.lineWidth = 1 / globalScale;
  ctx.beginPath();
  ctx.arc(node.x, node.y, node.radius + (24 * t) / globalScale + 2 / globalScale, 0, 2 * Math.PI);
  ctx.stroke();
};

const Graph2D = forwardRef(function Graph2D({ graph, highlight, selectedId, width, height, onSelect, onClear }, ref) {
  const fgRef = useRef();
  const hasFitted = useRef(false);
  const activePulse = useRef(null);
  const [pulsing, setPulsing] = useState(false);
  const { live, cache } = useLiveGraph(graph);
  const reduceMotion = prefersReducedMotion();

  // Push nodes further apart than the library defaults so dense graphs
  // don't collapse into an unreadable clump. The library digests data
  // asynchronously, so this lands before the first layout runs.
  useEffect(() => {
    fgRef.current.d3Force('charge').strength(-220).distanceMax(800);
    fgRef.current.d3Force('link').distance(90);
  }, []);

  useImperativeHandle(ref, () => ({
    focusNode(id) {
      whenPositioned(cache, id, (node) => {
        const duration = prefersReducedMotion() ? 0 : 1000;
        fgRef.current?.centerAt(node.x, node.y, duration);
        fgRef.current?.zoom(3, duration);
      });
    },
    // Runs until replaced or cleared with null. Updating the plan for the same
    // node keeps its timing, so filtering the graph doesn't restart the pulse.
    pulse(plan) {
      if (!plan || prefersReducedMotion()) {
        activePulse.current = null;
        setPulsing(false);
        return;
      }
      const sameNode = activePulse.current?.plan.origin === plan.origin;
      activePulse.current = { plan, startedAt: sameNode ? activePulse.current.startedAt : performance.now() };
      setPulsing(true);
    }
  }), [cache]);

  const drawPulse = useCallback((ctx, globalScale) => {
    if (!activePulse.current) return;
    const { plan, startedAt } = activePulse.current;
    const elapsed = loopElapsed(plan, performance.now() - startedAt);
    drawRing(ctx, cache.nodes.get(plan.origin), elapsed, globalScale);
    plan.hops.forEach(hop => drawHop(ctx, hop, cache, elapsed, globalScale));
  }, [cache]);

  const drawNode = useCallback((node, ctx, globalScale) => {
    const isHighlighted = highlight?.nodeIds.has(node.id);
    const isDimmed = highlight && !isHighlighted;

    ctx.globalAlpha = isDimmed ? 0.15 : 1;
    ctx.fillStyle = nodeColor(node);
    tracePath(ctx, node);
    ctx.fill();

    if (node.id === selectedId) {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.lineWidth = 1.25 / globalScale;
      ctx.stroke();
    } else if (isHighlighted) {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
      ctx.lineWidth = 1 / globalScale;
      ctx.stroke();
    }

    const showLabel = !isDimmed && (node.type !== 'message' || isHighlighted || globalScale >= MESSAGE_LABEL_MIN_SCALE);
    if (showLabel) {
      const label = node.label || node.id;
      const fontSize = LABEL_SIZE_PX / globalScale;
      const paddingX = fontSize * 0.55;
      const pillHeight = fontSize * 1.6;
      const labelY = node.y - node.radius - pillHeight / 2 - 4 / globalScale;
      ctx.font = `500 ${fontSize}px Inter, sans-serif`;
      const pillWidth = ctx.measureText(label).width + paddingX * 2;

      ctx.fillStyle = 'rgba(15, 17, 21, 0.82)';
      ctx.beginPath();
      ctx.roundRect(node.x - pillWidth / 2, labelY - pillHeight / 2, pillWidth, pillHeight, pillHeight / 2);
      ctx.fill();

      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#E4E6EB';
      ctx.fillText(label, node.x, labelY);
    }

    ctx.globalAlpha = 1;
  }, [highlight, selectedId]);

  const linkColor = useCallback((link) => {
    const { color, opacity } = linkStyle(link, highlight);
    return toRgba(color, opacity);
  }, [highlight]);
  const linkWidth = useCallback((link) => linkStyle(link, highlight).width, [highlight]);
  const linkLineDash = useCallback((link) => (link.inferred ? [2, 2] : null), []);
  const handleEngineStop = useCallback(() => {
    if (hasFitted.current) return;
    hasFitted.current = true;
    fgRef.current?.zoomToFit(prefersReducedMotion() ? 0 : 600, FIT_PADDING);
  }, []);
  const handleNodeClick = useCallback((node) => onSelect(node.id), [onSelect]);

  return (
    <div data-pulsing={pulsing}>
    <ForceGraph2D
      ref={fgRef}
      width={width}
      height={height}
      graphData={live}
      backgroundColor={COLORS.bg}
      nodeId="id"
      nodeRelSize={1}
      nodeLabel=""
      d3VelocityDecay={0.25}
      warmupTicks={reduceMotion ? 300 : 0}
      cooldownTicks={reduceMotion ? 0 : Infinity}
      cooldownTime={4000}
      onEngineStop={handleEngineStop}
      onRenderFramePost={drawPulse}
      autoPauseRedraw={!pulsing}
      nodeCanvasObject={drawNode}
      onNodeClick={handleNodeClick}
      onBackgroundClick={onClear}
      linkDirectionalArrowLength={3}
      linkDirectionalArrowRelPos={1}
      linkColor={linkColor}
      linkWidth={linkWidth}
      linkLineDash={linkLineDash}
    />
    </div>
  );
});

export default memo(Graph2D);
