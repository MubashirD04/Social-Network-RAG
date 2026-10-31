import { useEffect, useRef } from 'react';
import {
  AdditiveBlending, BufferAttribute, BufferGeometry, Color, FogExp2, InstancedMesh, LineBasicMaterial,
  LineSegments, MathUtils, MeshBasicMaterial, Object3D, PerspectiveCamera, Quaternion, Scene,
  SphereGeometry, Vector3, WebGLRenderer,
} from 'three';
import { COLORS, prefersReducedMotion } from '../graph/graphStyle';
import { FLOW_COLORS } from './flow';

const CLUSTERS = 5;
const NEIGHBORS = 2;
const HOVER_RADIUS = 0.35;
const PULSE_HOP_MS = 90;
const PULSE_FADE_MS = 500;
const INTERACTIVE = 'a, button, input, label, pre';
const palette = FLOW_COLORS.map(c => new Color(c));

const gaussian = () => (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;

const samplePalette = (t, target) => {
  const scaled = ((t % 1) + 1) % 1 * palette.length;
  const index = Math.floor(scaled);
  return target.copy(palette[index]).lerp(palette[(index + 1) % palette.length], scaled - index);
};

// A small made-up social graph: tight clusters with a few long bridges, the
// same shape the app finds in real chats.
const buildNetwork = (count) => {
  // Stretched to the viewport's shape, so clusters reach the side margins.
  const stretch = Math.min(window.innerWidth / window.innerHeight, 1.8);
  const centers = Array.from({ length: CLUSTERS }, () => {
    const center = new Vector3().randomDirection().multiplyScalar(62);
    center.x *= stretch;
    return center;
  });
  const nodes = Array.from({ length: count }, (_, i) => {
    const cluster = i % CLUSTERS;
    return {
      base: new Vector3(gaussian() * 34, gaussian() * 34, gaussian() * 34).add(centers[cluster]),
      size: 0.5 + Math.random() ** 3 * 1.6,
      hue: cluster / CLUSTERS + Math.random() * 0.08,
      phase: Math.random() * Math.PI * 2,
      hover: 0,
      pulseAt: -Infinity,
    };
  });

  const seen = new Set();
  const links = [];
  const neighbors = nodes.map(() => []);
  nodes.forEach((node, i) => {
    nodes
      .map((other, j) => ({ j, distance: node.base.distanceToSquared(other.base) }))
      .filter(({ j }) => j !== i)
      .sort((a, b) => a.distance - b.distance)
      .slice(0, NEIGHBORS)
      .forEach(({ j }) => {
        const key = `${Math.min(i, j)}-${Math.max(i, j)}`;
        if (seen.has(key)) return;
        seen.add(key);
        links.push([i, j]);
        neighbors[i].push(j);
        neighbors[j].push(i);
      });
  });
  return { nodes, links, neighbors };
};

// Purely decorative. Hovering pushes nodes aside and lights them up, clicking
// sends a pulse hop by hop along the links, and scrolling flies through it.
function NodeField({ progress }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const reduceMotion = prefersReducedMotion();
    let renderer;
    try {
      renderer = new WebGLRenderer({ canvas, alpha: true, antialias: true });
    } catch {
      return undefined; // No WebGL: the page's CSS glow carries the background alone.
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const count = window.innerWidth < 768 ? 70 : 140;
    const { nodes, links, neighbors } = buildNetwork(count);

    const scene = new Scene();
    scene.fog = new FogExp2(COLORS.bg, 0.0065);
    const camera = new PerspectiveCamera(55, 1, 1, 500);
    const group = new Object3D();
    scene.add(group);

    const sphere = new SphereGeometry(1, 12, 8);
    const nodeMaterial = new MeshBasicMaterial();
    const mesh = new InstancedMesh(sphere, nodeMaterial, count);
    group.add(mesh);

    const linePositions = new Float32Array(links.length * 6);
    const lineColors = new Float32Array(links.length * 6);
    const lineGeometry = new BufferGeometry();
    lineGeometry.setAttribute('position', new BufferAttribute(linePositions, 3));
    lineGeometry.setAttribute('color', new BufferAttribute(lineColors, 3));
    const lineMaterial = new LineBasicMaterial({ vertexColors: true, transparent: true, blending: AdditiveBlending, depthWrite: false });
    const lines = new LineSegments(lineGeometry, lineMaterial);
    lines.frustumCulled = false;
    group.add(lines);

    const pointer = { x: 10, y: 10, parallaxX: 0, parallaxY: 0 };
    const dummy = new Object3D();
    const color = new Color();
    const position = new Vector3();
    const projected = new Vector3();
    const push = new Vector3();
    const inverse = new Quaternion();
    const live = nodes.map(() => new Vector3());
    const tint = nodes.map(() => new Color());
    let aspect = 1;

    const render = (now) => {
      const scroll = reduceMotion ? 0 : progress.get();
      pointer.parallaxX += (pointer.x > 1 ? 0 : pointer.x - pointer.parallaxX) * 0.03;
      pointer.parallaxY += (pointer.y > 1 ? 0 : pointer.y - pointer.parallaxY) * 0.03;

      camera.position.set(0, 0, MathUtils.lerp(130, 62, scroll));
      group.rotation.set(
        pointer.parallaxY * -0.18 + scroll * 0.5,
        pointer.parallaxX * 0.25 + scroll * Math.PI * 0.9 + (reduceMotion ? 0 : now * 0.00003),
        0,
      );
      group.updateMatrixWorld();
      camera.updateMatrixWorld();
      inverse.copy(group.quaternion).invert();

      nodes.forEach((node, i) => {
        const time = reduceMotion ? 0 : now * 0.0004;
        position.copy(node.base);
        position.x += Math.sin(time + node.phase) * 1.8;
        position.y += Math.cos(time * 0.8 + node.phase) * 1.8;

        projected.copy(position).applyMatrix4(group.matrixWorld).project(camera);
        const dx = (projected.x - pointer.x) * aspect;
        const dy = projected.y - pointer.y;
        const distance = Math.hypot(dx, dy);
        const target = Math.max(0, 1 - distance / HOVER_RADIUS);
        node.hover += (target - node.hover) * 0.12;
        if (node.hover > 0.001) {
          push.set(dx, dy, 0).normalize().applyQuaternion(inverse).multiplyScalar(node.hover * 9);
          position.add(push);
        }
        live[i].copy(position);

        const sincePulse = now - node.pulseAt;
        const pulse = sincePulse >= 0 ? Math.exp(-sincePulse / PULSE_FADE_MS) : 0;
        const glow = 0.5 + node.hover * 0.9 + pulse * 1.2;
        samplePalette(node.hue + scroll * 0.7, tint[i]).multiplyScalar(glow);

        dummy.position.copy(position);
        dummy.scale.setScalar(node.size * (1 + node.hover * 0.9 + pulse * 0.8));
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
        mesh.setColorAt(i, color.copy(tint[i]));
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.instanceColor.needsUpdate = true;

      links.forEach(([a, b], i) => {
        live[a].toArray(linePositions, i * 6);
        live[b].toArray(linePositions, i * 6 + 3);
        color.copy(tint[a]).multiplyScalar(0.4).toArray(lineColors, i * 6);
        color.copy(tint[b]).multiplyScalar(0.4).toArray(lineColors, i * 6 + 3);
      });
      lineGeometry.attributes.position.needsUpdate = true;
      lineGeometry.attributes.color.needsUpdate = true;

      renderer.render(scene, camera);
    };

    const onPointerMove = (event) => {
      if (event.pointerType !== 'mouse') return;
      pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
      pointer.y = -(event.clientY / window.innerHeight) * 2 + 1;
    };
    const onPointerLeave = () => { pointer.x = 10; pointer.y = 10; };

    const onPointerDown = (event) => {
      if (event.target.closest?.(INTERACTIVE)) return;
      const x = (event.clientX / window.innerWidth) * 2 - 1;
      const y = -(event.clientY / window.innerHeight) * 2 + 1;
      let start = 0;
      let nearest = Infinity;
      live.forEach((point, i) => {
        projected.copy(point).applyMatrix4(group.matrixWorld).project(camera);
        const distance = Math.hypot((projected.x - x) * aspect, projected.y - y);
        if (distance < nearest) { nearest = distance; start = i; }
      });

      const now = performance.now();
      const hops = new Map([[start, 0]]);
      const queue = [start];
      while (queue.length) {
        const current = queue.shift();
        neighbors[current].forEach(next => {
          if (hops.has(next)) return;
          hops.set(next, hops.get(current) + 1);
          queue.push(next);
        });
      }
      hops.forEach((hop, i) => { nodes[i].pulseAt = now + hop * PULSE_HOP_MS; });
    };

    const resize = () => {
      const { innerWidth: width, innerHeight: height } = window;
      aspect = width / height;
      renderer.setSize(width, height, false);
      camera.aspect = aspect;
      camera.updateProjectionMatrix();
      // The loop repaints on its own; a static frame needs redrawing.
      if (reduceMotion) render(0);
    };

    resize();
    window.addEventListener('resize', resize);
    let frame;
    if (!reduceMotion) {
      const loop = (now) => {
        render(now);
        frame = requestAnimationFrame(loop);
      };
      frame = requestAnimationFrame(loop);
      window.addEventListener('pointermove', onPointerMove, { passive: true });
      document.documentElement.addEventListener('pointerleave', onPointerLeave);
      window.addEventListener('pointerdown', onPointerDown, { passive: true });
    }

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointerMove);
      document.documentElement.removeEventListener('pointerleave', onPointerLeave);
      window.removeEventListener('pointerdown', onPointerDown);
      sphere.dispose();
      nodeMaterial.dispose();
      mesh.dispose();
      lineGeometry.dispose();
      lineMaterial.dispose();
      renderer.dispose();
    };
  }, [progress]);

  return <canvas ref={canvasRef} className="node-field" aria-hidden="true" />;
}

export default NodeField;
