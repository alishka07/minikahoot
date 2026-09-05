'use client';

const answers = ['▲', '◆', '●', '■'];
// Счётчик проходит все значения: на паузе он стоит на 24 и 84, а обе эти формы
// согласуются с русским «ответа» — промежуточные числа только мелькают.
const counts = Array.from({ length: 61 }, (_, index) => 24 + index);

export function QuizDemo({ counter, question }: { counter: string; question: string }) {
  return <div className="quiz-demo" aria-hidden="true">
    <div className="demo-stage">
      <div className="demo-card"><small>{counter}</small><b>{question}</b></div>
      <div className="demo-answers">{answers.map((symbol, index) => <span key={symbol} className={index === answers.length - 1 ? 'demo-answer correct' : 'demo-answer'} style={{ '--i': index } as React.CSSProperties}>{symbol}</span>)}</div>
      <svg className="demo-cursor" viewBox="0 0 24 24"><path d="M5 3l14 8.4-6.2 1.4L9.5 20z" fill="#fff" stroke="#18181b" strokeWidth="1.5" strokeLinejoin="round"/></svg>
    </div>
  </div>;
}

export function DemoCount() {
  return <><span className="sr-only">{counts[0]}</span><span className="demo-count" aria-hidden="true"><span>{counts.map(count => <span key={count}>{count}</span>)}</span></span></>;
}
