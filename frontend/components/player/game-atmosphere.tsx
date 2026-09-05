'use client';
import { useEffect, useRef } from 'react';

// x/y — смещение от центра слоя: x в cqw, y в cqh, поэтому разлёт держится на любом экране.
const shapes = [
  { symbol: '▲', x: -42, y: -32, size: 34, color: '#ef4444', depth: .9, delay: -1 },
  { symbol: '◆', x: 38, y: -36, size: 42, color: '#3b82f6', depth: 1.2, delay: -3 },
  { symbol: '●', x: -35, y: 28, size: 28, color: '#fbbf24', depth: .7, delay: -5 },
  { symbol: '■', x: 32, y: 24, size: 36, color: '#22c55e', depth: 1, delay: -2 },
  { symbol: '▲', x: 19, y: -12, size: 19, color: '#a78bfa', depth: .55, delay: -6 },
  { symbol: '◆', x: -22, y: -12, size: 22, color: '#ec4899', depth: .65, delay: -4 },
  { symbol: '●', x: 43, y: -1, size: 18, color: '#a3e635', depth: .45, delay: -7 },
  { symbol: '■', x: -45, y: 0, size: 17, color: '#22d3ee', depth: .5, delay: -3.5 },
];

export function GameAtmosphere({ gathered = false }: { gathered?: boolean }) {
  const layer = useRef<HTMLDivElement>(null);
  const scattered = useRef(!gathered);
  useEffect(() => { scattered.current = !gathered; }, [gathered]);
  useEffect(() => {
    let frame = 0;
    const move = (x: number, y: number) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        layer.current?.style.setProperty('--parallax-x', `${x}px`);
        layer.current?.style.setProperty('--parallax-y', `${y}px`);
      });
    };
    // Пока фигуры собраны в стопку, параллакс им не нужен — он бы дёргал ровный столбик.
    const onPointer = (event: PointerEvent) => scattered.current && move((.5 - event.clientX / window.innerWidth) * 18, (.5 - event.clientY / window.innerHeight) * 18);
    const onOrientation = (event: DeviceOrientationEvent) => scattered.current && move(Math.max(-18, Math.min(18, -(event.gamma ?? 0) * .55)), Math.max(-18, Math.min(18, -(event.beta ?? 0) * .25)));
    window.addEventListener('pointermove', onPointer, { passive: true });
    window.addEventListener('deviceorientation', onOrientation, { passive: true });
    return () => { cancelAnimationFrame(frame); window.removeEventListener('pointermove', onPointer); window.removeEventListener('deviceorientation', onOrientation); };
  }, []);
  return <div ref={layer} className={`game-atmosphere${gathered ? ' gathered' : ''}`} aria-hidden="true">{shapes.map((shape, index) => <span key={index} style={{ width: shape.size, height: shape.size, color: shape.color, animationDelay: `${shape.delay}s`, '--depth': shape.depth, '--x': shape.x, '--y': shape.y, '--i': index, '--stack': `${(index - (shapes.length - 1) / 2) * 15}px` } as React.CSSProperties}>{shape.symbol}</span>)}</div>;
}
