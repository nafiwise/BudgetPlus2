import { useEffect, useId, useState } from 'react';
import { money } from '../utils/format.js';

export function AnimatedNumber({ value, currency = false }) {
  const [shown, setShown] = useState(value);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setShown(value); return; }
    let frame;
    const start = performance.now();
    const tick = now => {
      const progress = Math.min(1, (now - start) / 650);
      setShown(value * (1 - Math.pow(1 - progress, 3)));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <><span aria-hidden="true">{currency ? money(shown) : Math.round(shown)}</span><span className="sr-only">{currency ? money(value) : value}</span></>;
}

export function ScoreRing({ value, compact = false }) {
  const ratio = Math.max(0, Math.min(1, (value - 300) / 550));
  return <div className={`score-ring ${compact ? 'compact' : ''}`}>
    <svg viewBox="0 0 180 180" aria-hidden="true"><circle className="ring-track" cx="90" cy="90" r="76"/><circle className="ring-value" cx="90" cy="90" r="76" pathLength="100" strokeDasharray={`${ratio * 100} 100`}/><circle className="ring-inner" cx="90" cy="90" r="62"/></svg>
    <div><strong><AnimatedNumber value={value}/></strong><span>OF 850</span></div>
  </div>;
}

export function SpendingChart({ data }) {
  const gradient = useId().replaceAll(':', '');
  const month = data.asOf.slice(0, 7);
  const days = Number(data.asOf.slice(8));
  const totals = Array.from({length:days},(_,i)=>data.transactions.filter(t=>t.type==='purchase' && !t.pending && t.date===`${month}-${String(i+1).padStart(2,'0')}`).reduce((sum,t)=>sum+t.amount,0));
  let cumulative = 0;
  const values = totals.map(n=>(cumulative+=n));
  const ceiling = Math.max(...values,1);
  const points = values.map((n,i)=>`${30+i/Math.max(1,days-1)*660},${175-n/ceiling*130}`);
  const line = points.join(' ');
  return <section className="panel spending-panel"><div className="section-heading"><div><span className="eyebrow">THE BIG PICTURE</span><h2>Spending, in motion.</h2></div><span className="chart-legend"><i/>Month to date</span></div><div className="chart-total">{money(cumulative)}<span>Total purchases · {month}</span></div>
    <svg className="spending-chart" viewBox="0 0 720 215" role="img" aria-label={`Cumulative purchases from ${month}-01 through ${data.asOf}: ${money(cumulative)}`}>
      <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a4df9b" stopOpacity=".25"/><stop offset="100%" stopColor="#a4df9b" stopOpacity="0"/></linearGradient></defs>
      {[45,110,175].map(y=><line key={y} x1="30" y1={y} x2="690" y2={y} className="chart-grid"/>)}
      <polygon points={`30,175 ${line} 690,175`} fill={`url(#${gradient})`}/><polyline points={line} fill="none" className="chart-line"/>
      <circle cx={days===1?30:690} cy={175-values.at(-1)/ceiling*130} r="5" className="chart-dot"/>
      <text x="30" y="205">{month}-01</text><text x="690" y="205" textAnchor="end">{data.asOf}</text>
    </svg><details><summary>Daily breakdown</summary><div className="chart-data">{totals.map((total,i)=><div key={i}><span>{month}-{String(i+1).padStart(2,'0')}</span><strong>{money(total)}</strong></div>)}</div></details>
  </section>;
}
