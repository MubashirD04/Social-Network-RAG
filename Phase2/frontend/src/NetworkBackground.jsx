import { useEffect, useRef } from 'react';

// Ambient particle network for the landing page. Purely decorative — nodes
// drift and link up to nearby neighbors, echoing the force-graph the app
// renders once real data is loaded. Skips the animation loop entirely under
// prefers-reduced-motion, drawing one static frame instead.
const NODE_COLORS = ['#4ECDC4', '#FFD93D', '#A78BFA', '#FF6B6B', '#60A5FA'];
const LINK_DISTANCE = 150;
const NODE_COUNT_DIVISOR = 14000; // ~1 node per 14000px^2 of viewport

function NetworkBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let particles = [];
    let animationFrame;
    let width, height;

    const makeParticles = () => {
      const count = Math.min(90, Math.max(30, Math.floor((width * height) / NODE_COUNT_DIVISOR)));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        r: Math.random() * 1.5 + 1,
        color: NODE_COLORS[Math.floor(Math.random() * NODE_COLORS.length)]
      }));
    };

    const resize = () => {
      width = canvas.width = canvas.offsetWidth * devicePixelRatio;
      height = canvas.height = canvas.offsetHeight * devicePixelRatio;
      makeParticles();
    };

    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < particles.length; i++) {
        const a = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < LINK_DISTANCE * devicePixelRatio) {
            ctx.strokeStyle = `rgba(78, 205, 196, ${0.12 * (1 - dist / (LINK_DISTANCE * devicePixelRatio))})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      particles.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * devicePixelRatio, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = 0.7;
        ctx.fill();
        ctx.globalAlpha = 1;
      });
    };

    const step = () => {
      particles.forEach(p => {
        p.x += p.vx * devicePixelRatio;
        p.y += p.vy * devicePixelRatio;
        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;
      });
      draw();
      animationFrame = requestAnimationFrame(step);
    };

    resize();
    window.addEventListener('resize', resize);

    if (reduceMotion) {
      draw();
    } else {
      step();
    }

    return () => {
      window.removeEventListener('resize', resize);
      if (animationFrame) cancelAnimationFrame(animationFrame);
    };
  }, []);

  return <canvas ref={canvasRef} className="network-background" aria-hidden="true" />;
}

export default NetworkBackground;
