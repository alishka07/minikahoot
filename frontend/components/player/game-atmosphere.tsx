// x/y — смещение от центра слоя: x в cqw, y в cqh, поэтому разлёт держится на любом экране.
const shapes = [
  { symbol: '▲', x: -42, y: -32, size: 34, color: '#ef4444', delay: -1 },
  { symbol: '◆', x: 38, y: -36, size: 42, color: '#3b82f6', delay: -3 },
  { symbol: '●', x: -35, y: 28, size: 28, color: '#fbbf24', delay: -5 },
  { symbol: '■', x: 32, y: 24, size: 36, color: '#22c55e', delay: -2 },
  { symbol: '▲', x: 19, y: -12, size: 19, color: '#a78bfa', delay: -6 },
  { symbol: '◆', x: -22, y: -12, size: 22, color: '#ec4899', delay: -4 },
  { symbol: '●', x: 43, y: -1, size: 18, color: '#a3e635', delay: -7 },
  { symbol: '■', x: -45, y: 0, size: 17, color: '#22d3ee', delay: -3.5 },
  { symbol: '▲', x: -12, y: -40, size: 24, color: '#f472b6', delay: -2.5 },
  { symbol: '◆', x: 10, y: 38, size: 26, color: '#38bdf8', delay: -6.5 },
  { symbol: '●', x: -30, y: -19, size: 20, color: '#a3e635', delay: -1.5 },
  { symbol: '■', x: 45, y: -28, size: 22, color: '#8b5cf6', delay: -5.5 },
  { symbol: '▲', x: 30, y: 40, size: 18, color: '#22d3ee', delay: -4.5 },
  { symbol: '◆', x: -46, y: -21, size: 16, color: '#fbbf24', delay: -7.5 },
  { symbol: '●', x: 25, y: 9, size: 15, color: '#ef4444', delay: -.5 },
  { symbol: '■', x: -18, y: 42, size: 21, color: '#a78bfa', delay: -3 },
  { symbol: '▲', x: 47, y: 22, size: 20, color: '#3b82f6', delay: -6 },
  { symbol: '◆', x: -8, y: -26, size: 14, color: '#22c55e', delay: -2 },
];

// 'stack' собирает фигуры в плотный столбик за карточкой входа; в остальное время
// они просто дрейфуют и на курсор не реагируют.
export function GameAtmosphere({ focus }: { focus?: 'stack' }) {
  return <div className={`game-atmosphere${focus ? ` ${focus}` : ''}`} aria-hidden="true">{shapes.map((shape, index) => <span key={index} style={{ width: shape.size, height: shape.size, color: shape.color, animationDelay: `${shape.delay}s`, '--x': shape.x, '--y': shape.y, '--i': index, '--stack': `${(index - (shapes.length - 1) / 2) * 9}px` } as React.CSSProperties}>{shape.symbol}</span>)}</div>;
}
