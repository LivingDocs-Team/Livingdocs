import { useEffect, useRef } from 'react';

// Decorative page background: a slow constellation of connected points that reacts to the pointer,
// plus two drifting glows (CSS). Static when the user prefers reduced motion; paused in hidden tabs.
const LINK_DISTANCE_SQ = 120 * 120;
const POINTER_DISTANCE_SQ = 170 * 170;

export default function AnimatedBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return undefined;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const pointer = { x: -999, y: -999 };
    let width = 0;
    let height = 0;
    let points = [];
    let frame = 0;

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const count = Math.round(Math.min(80, (width * height) / 20000));
      points = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.28,
        vy: (Math.random() - 0.5) * 0.28,
        r: Math.random() * 1.3 + 0.5,
      }));
    }

    function draw() {
      ctx.clearRect(0, 0, width, height);
      for (let i = 0; i < points.length; i += 1) {
        const a = points[i];
        if (!reduceMotion) {
          a.x += a.vx;
          a.y += a.vy;
          if (a.x < -10) a.x = width + 10;
          if (a.x > width + 10) a.x = -10;
          if (a.y < -10) a.y = height + 10;
          if (a.y > height + 10) a.y = -10;
        }
        for (let j = i + 1; j < points.length; j += 1) {
          const b = points[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distance = dx * dx + dy * dy;
          if (distance < LINK_DISTANCE_SQ) {
            ctx.strokeStyle = `rgba(110, 130, 255, ${(0.16 * (1 - distance / LINK_DISTANCE_SQ)).toFixed(3)})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
        const px = a.x - pointer.x;
        const py = a.y - pointer.y;
        const pointerDistance = px * px + py * py;
        if (pointerDistance < POINTER_DISTANCE_SQ) {
          ctx.strokeStyle = `rgba(140, 160, 255, ${(0.35 * (1 - pointerDistance / POINTER_DISTANCE_SQ)).toFixed(3)})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(pointer.x, pointer.y);
          ctx.stroke();
        }
        ctx.fillStyle = 'rgba(150, 170, 255, 0.55)';
        ctx.beginPath();
        ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function loop() {
      draw();
      frame = window.requestAnimationFrame(loop);
    }
    function start() {
      if (reduceMotion) draw();
      else if (!frame) loop();
    }
    function stop() {
      if (frame) window.cancelAnimationFrame(frame);
      frame = 0;
    }
    const onResize = () => { resize(); if (reduceMotion) draw(); };
    const onVisibility = () => (document.hidden ? stop() : start());
    const onPointer = (event) => { pointer.x = event.clientX; pointer.y = event.clientY; };
    const onLeave = () => { pointer.x = -999; pointer.y = -999; };

    resize();
    start();
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pointermove', onPointer, { passive: true });
    document.documentElement.addEventListener('pointerleave', onLeave);
    return () => {
      stop();
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pointermove', onPointer);
      document.documentElement.removeEventListener('pointerleave', onLeave);
    };
  }, []);

  return (
    <>
      <canvas ref={canvasRef} className="bg-canvas" aria-hidden="true" />
      <div className="bg-aurora" aria-hidden="true"><i /><i /></div>
    </>
  );
}
