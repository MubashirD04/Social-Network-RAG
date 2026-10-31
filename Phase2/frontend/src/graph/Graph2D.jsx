import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { COLORS, linkStyle, nodeColor, prefersReducedMotion, toRgba } from './graphStyle';
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

const Graph2D = forwardRef(function Graph2D({ graph, highlight, selectedId, width, height, onSelect, onClear }, ref) {
  const fgRef = useRef();
  const hasFitted = useRef(false);
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
    }
  }), [cache]);

  const drawNode = useCallback((node, ctx, globalScale) => {
    const isHighlighted = highlight?.nodeIds.has(node.id);
    const isDimmed = highlight && !isHighlighted;

    ctx.globalAlpha = isDimmed ? 0.15 : 1;
    ctx.fillStyle = nodeColor(node);
    tracePath(ctx, node);
    ctx.fill();

    if (node.id === selectedId) {
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2 / globalScale;
      ctx.stroke();
    } else if (isHighlighted) {
      ctx.strokeStyle = '#FFD93D';
      ctx.lineWidth = 1.5 / globalScale;
      ctx.stroke();
    }

    const showLabel = !isDimmed && (node.type !== 'message' || isHighlighted || globalScale >= MESSAGE_LABEL_MIN_SCALE);
    if (showLabel) {
      const label = node.label || node.id;
      const fontSize = 12 / globalScale;
      const labelY = node.y - node.radius - fontSize;
      ctx.font = `${fontSize}px Inter, sans-serif`;
      const textWidth = ctx.measureText(label).width;
      const padding = fontSize * 0.2;

      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.fillRect(node.x - (textWidth + padding) / 2, labelY - (fontSize + padding) / 2, textWidth + padding, fontSize + padding);

      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#000';
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
      nodeCanvasObject={drawNode}
      onNodeClick={handleNodeClick}
      onBackgroundClick={onClear}
      linkDirectionalArrowLength={3}
      linkDirectionalArrowRelPos={1}
      linkColor={linkColor}
      linkWidth={linkWidth}
      linkLineDash={linkLineDash}
    />
  );
});

export default memo(Graph2D);
