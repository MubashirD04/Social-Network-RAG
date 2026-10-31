import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useRef } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import * as THREE from 'three';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import SpriteText from 'three-spritetext';
import { COLORS, linkStyle, nodeColor, prefersReducedMotion } from './graphStyle';
import { useLiveGraph, whenPositioned } from './useLiveGraph';

const CAMERA_DISTANCE = 220;
const FIT_PADDING = 60;
const IDLE_PAUSE_MS = 3000;
const ARROW_LENGTH = 5;
const BLOOM_MIN_CORES = 8;
const MSAA_SAMPLES = 4;

// One geometry per shape, scaled per node. The library's accessors rebuild
// the scene whenever they change, so everything selection-related happens by
// mutating these per-object materials instead.
const GEOMETRY = {
  person: new THREE.SphereGeometry(1, 48, 32),
  message: new THREE.SphereGeometry(1, 24, 16),
  topic: new THREE.OctahedronGeometry(1),
  chat: new THREE.BoxGeometry(2, 1.4, 1.4),
};
const ARROW_GEOMETRY = new THREE.ConeGeometry(1.4, ARROW_LENGTH, 16).rotateX(Math.PI / 2);
const FORWARD = new THREE.Vector3(0, 0, 1);
const direction = new THREE.Vector3();
const noRaycast = () => {};

const isImportant = (node) => node.type === 'topic' || node.type === 'chat' || node.is_influencer || node.is_info_broker;

const makeLabel = (node) => {
  const sprite = new SpriteText(node.label || node.id, 5, '#e4e6eb');
  sprite.fontFace = 'Inter, system-ui, sans-serif';
  sprite.backgroundColor = 'rgba(15, 17, 21, 0.75)';
  sprite.padding = 1.5;
  sprite.borderRadius = 2;
  sprite.material.depthWrite = false;
  sprite.position.y = node.radius + 6;
  sprite.raycast = noRaycast;
  return sprite;
};

const styleNode = (entry, node, highlight, selectedId) => {
  const isHighlighted = highlight?.nodeIds.has(node.id);
  const isDimmed = highlight && !isHighlighted;
  const material = entry.mesh.material;
  material.opacity = isDimmed ? 0.15 : 1;
  material.emissive.set(node.id === selectedId ? '#ffffff' : isHighlighted ? '#FFD93D' : '#000000');
  material.emissiveIntensity = node.id === selectedId ? 0.2 : 0.08;

  const wantsLabel = !isDimmed && (isHighlighted || isImportant(node));
  if (wantsLabel && !entry.label) {
    entry.label = makeLabel(node);
    entry.group.add(entry.label);
  }
  if (entry.label) entry.label.visible = wantsLabel;
};

const styleLink = (entry, link, highlight) => {
  const { color, opacity } = linkStyle(link, highlight);
  [entry.line.material, entry.arrow?.material].filter(Boolean).forEach(material => {
    material.color.set(color);
    material.opacity = opacity;
  });
};

const canAffordBloom = () => !prefersReducedMotion() && navigator.hardwareConcurrency >= BLOOM_MIN_CORES;

const Graph3D = forwardRef(function Graph3D({ graph, highlight, selectedId, width, height, onSelect, onClear }, ref) {
  const fgRef = useRef();
  const containerRef = useRef();
  const nodeObjects = useRef(new Map());
  const linkObjects = useRef(new Map());
  const selection = useRef({ highlight, selectedId });
  const pauseTimer = useRef();
  const engineRunning = useRef(true);
  const hasFitted = useRef(false);
  const { live, cache } = useLiveGraph(graph);
  const reduceMotion = prefersReducedMotion();

  // Rendering stops once the layout settles and nothing is moving, and any
  // interaction brings it back.
  const wake = useCallback(() => {
    fgRef.current?.resumeAnimation();
    clearTimeout(pauseTimer.current);
    if (!engineRunning.current) {
      pauseTimer.current = setTimeout(() => fgRef.current?.pauseAnimation(), IDLE_PAUSE_MS);
    }
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    const events = ['pointerdown', 'pointermove', 'wheel', 'keydown'];
    events.forEach(type => container.addEventListener(type, wake, { passive: true }));
    return () => {
      events.forEach(type => container.removeEventListener(type, wake));
      clearTimeout(pauseTimer.current);
    };
  }, [wake]);

  useEffect(() => {
    const fg = fgRef.current;
    fg.d3Force('charge').strength(-120).distanceMax(600);
    fg.d3Force('link').distance(60);
    if (!canAffordBloom()) return undefined;

    // Thresholded so only bright fills bloom. Inferred edges stay well below
    // it, keeping their dashes crisp.
    const composer = fg.postProcessingComposer();
    // Bloom renders through off-screen targets, which skip the canvas's own
    // anti-aliasing and would leave every silhouette jagged.
    [composer.renderTarget1, composer.renderTarget2].forEach(target => {
      target.samples = MSAA_SAMPLES;
      target.dispose();
    });
    // The renderer's clear color isn't linearized for the composer's targets,
    // so OutputPass would brighten it. A scene background is handled correctly.
    fg.scene().background = new THREE.Color(COLORS.bg);
    const passes = [
      new UnrealBloomPass(new THREE.Vector2(width, height), 0.15, 0.3, 0.92),
      new OutputPass(),
    ];
    passes.forEach(pass => composer.addPass(pass));
    return () => passes.forEach(pass => composer.removePass(pass));
    // Bloom is set up once; the composer tracks size changes itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    engineRunning.current = true;
    wake();
  }, [graph, wake]);

  useEffect(() => {
    selection.current = { highlight, selectedId };
    cache.nodes.forEach((node, id) => {
      const entry = nodeObjects.current.get(id);
      if (entry) styleNode(entry, node, highlight, selectedId);
    });
    cache.links.forEach((link, id) => {
      const entry = linkObjects.current.get(id);
      if (entry) styleLink(entry, link, highlight);
    });
    wake();
  }, [cache, highlight, selectedId, wake]);

  useImperativeHandle(ref, () => ({
    focusNode(id) {
      wake();
      whenPositioned(cache, id, (node) => {
        const { x, y, z = 0 } = node;
        const ratio = 1 + CAMERA_DISTANCE / (Math.hypot(x, y, z) || 1);
        fgRef.current?.cameraPosition({ x: x * ratio, y: y * ratio, z: z * ratio }, { x, y, z }, prefersReducedMotion() ? 0 : 1000);
      });
    }
  }), [cache, wake]);

  const makeNode = useCallback((node) => {
    const material = new THREE.MeshLambertMaterial({ color: nodeColor(node), transparent: true });
    const mesh = new THREE.Mesh(GEOMETRY[node.type] || GEOMETRY.person, material);
    mesh.scale.setScalar(node.radius);
    if (node.type === 'message') mesh.scale.set(node.radius * 1.4, node.radius * 0.8, node.radius * 0.8);
    const group = new THREE.Group();
    group.add(mesh);
    const entry = { group, mesh, label: null };
    nodeObjects.current.set(node.id, entry);
    styleNode(entry, node, selection.current.highlight, selection.current.selectedId);
    return group;
  }, []);

  const makeLink = useCallback((link) => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
    const material = link.inferred
      ? new THREE.LineDashedMaterial({ dashSize: 3, gapSize: 3, transparent: true })
      : new THREE.LineBasicMaterial({ transparent: true });
    const line = new THREE.Line(geometry, material);
    line.frustumCulled = false;
    line.raycast = noRaycast;

    const group = new THREE.Group();
    group.add(line);
    // Depth compresses dashes, so inferred edges carry a second cue: only
    // confirmed edges get an arrowhead.
    let arrow = null;
    // PART_OF has a single direction by definition, and every message has one.
    if (!link.inferred && link.relationship !== 'PART_OF') {
      arrow = new THREE.Mesh(ARROW_GEOMETRY, new THREE.MeshBasicMaterial({ transparent: true }));
      arrow.raycast = noRaycast;
      group.add(arrow);
    }
    const entry = { line, arrow };
    linkObjects.current.set(link.id, entry);
    styleLink(entry, link, selection.current.highlight);
    return group;
  }, []);

  const positionLink = useCallback((_group, { start, end }, link) => {
    const entry = linkObjects.current.get(link.id);
    if (!entry) return true;
    const position = entry.line.geometry.getAttribute('position');
    position.setXYZ(0, start.x, start.y, start.z);
    position.setXYZ(1, end.x, end.y, end.z);
    position.needsUpdate = true;
    if (link.inferred) entry.line.computeLineDistances();
    if (entry.arrow) {
      direction.set(end.x - start.x, end.y - start.y, end.z - start.z).normalize();
      const offset = (link.target.radius || 0) + ARROW_LENGTH / 2;
      entry.arrow.position.set(end.x - direction.x * offset, end.y - direction.y * offset, end.z - direction.z * offset);
      entry.arrow.quaternion.setFromUnitVectors(FORWARD, direction);
    }
    return true;
  }, []);

  const handleNodeClick = useCallback((node) => onSelect(node.id), [onSelect]);
  const handleEngineStop = useCallback(() => {
    engineRunning.current = false;
    if (!hasFitted.current) {
      hasFitted.current = true;
      fgRef.current?.zoomToFit(prefersReducedMotion() ? 0 : 600, FIT_PADDING);
    }
    wake();
  }, [wake]);

  return (
    <div ref={containerRef}>
      <ForceGraph3D
        ref={fgRef}
        width={width}
        height={height}
        graphData={live}
        backgroundColor={COLORS.bg}
        nodeId="id"
        nodeLabel=""
        linkLabel=""
        showNavInfo={false}
        warmupTicks={reduceMotion ? 300 : 0}
        cooldownTicks={reduceMotion ? 0 : Infinity}
        cooldownTime={4000}
        nodeThreeObject={makeNode}
        linkThreeObject={makeLink}
        linkPositionUpdate={positionLink}
        onNodeClick={handleNodeClick}
        onBackgroundClick={onClear}
        onEngineStop={handleEngineStop}
      />
    </div>
  );
});

export default memo(Graph3D);
