'use client';
import { useEffect, useRef } from 'react';

const shapes = [
  { symbol: '▲', x: 8, y: 18, size: 34, color: '#ef4444', depth: .9, delay: -1 },
  { symbol: '◆', x: 88, y: 14, size: 42, color: '#3b82f6', depth: 1.2, delay: -3 },
  { symbol: '●', x: 15, y: 78, size: 28, color: '#fbbf24', depth: .7, delay: -5 },
  { symbol: '■', x: 82, y: 74, size: 36, color: '#22c55e', depth: 1, delay: -2 },
  { symbol: '▲', x: 69, y: 38, size: 19, color: '#a78bfa', depth: .55, delay: -6 },
  { symbol: '◆', x: 28, y: 38, size: 22, color: '#ec4899', depth: .65, delay: -4 },
  { symbol: '●', x: 93, y: 49, size: 18, color: '#a3e635', depth: .45, delay: -7 },
  { symbol: '■', x: 5, y: 50, size: 17, color: '#22d3ee', depth: .5, delay: -3.5 },
];

export function GameAtmosphere() {
  const layer = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let frame = 0;
    const move = (x: number, y: number) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        layer.current?.style.setProperty('--parallax-x', `${x}px`);
        layer.current?.style.setProperty('--parallax-y', `${y}px`);
      });
    };
    const onPointer = (event: PointerEvent) => move((.5 - event.clientX / window.innerWidth) * 18, (.5 - event.clientY / window.innerHeight) * 18);
    const onOrientation = (event: DeviceOrientationEvent) => move(Math.max(-18, Math.min(18, -(event.gamma ?? 0) * .55)), Math.max(-18, Math.min(18, -(event.beta ?? 0) * .25)));
    window.addEventListener('pointermove', onPointer, { passive: true });
    window.addEventListener('deviceorientation', onOrientation, { passive: true });
    return () => { cancelAnimationFrame(frame); window.removeEventListener('pointermove', onPointer); window.removeEventListener('deviceorientation', onOrientation); };
  }, []);
  return <div ref={layer} className="game-atmosphere" aria-hidden="true">{shapes.map((shape, index) => <span key={index} style={{ left: `${shape.x}%`, top: `${shape.y}%`, width: shape.size, height: shape.size, color: shape.color, animationDelay: `${shape.delay}s`, '--depth': shape.depth } as React.CSSProperties}>{shape.symbol}</span>)}</div>;
}
