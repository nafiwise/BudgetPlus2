import { ArrowDown, ArrowRight, ArrowUpRight, CreditCard, Fingerprint, Layers3, Play, ShieldCheck, Sparkles, Zap } from 'lucide-react';
import CardOverview from './CardOverview.jsx';
import PurchasePreview from './PurchasePreview.jsx';
import { AnimatedNumber } from './Visuals.jsx';

export function priority(data, analysis) {
  if (!data.balancesConfirmed) return 'Confirm your balances in Money to enable purchase decisions.';
  const fast = analysis.budget.categories.find(c => c.importance !== 'MUST PAY' && c.pace > 1.2);
  if (fast) return `${fast.name} is moving too fast. ${data.guardrail === 'strict' ? 'Purchases with budget warnings will be blocked.' : 'Eligible purchases can proceed with a budget warning.'}`;
  return analysis.budget.safeRaw >= 0 ? 'Your obligations and reserves are covered. BudgetPlus checks them with every purchase.' : 'Your obligations need more room. BudgetPlus blocks purchases that put protected funds at risk.';
}

function SectionTitle({ number, label, title, accent, children }) {
  return <div className="landing-section-heading"><div><div className="eyebrow"><span className="section-index">{number} /</span>{label}</div><h2>{title}<span>{accent}</span></h2></div>{children}</div>;
}

export default function Home({ data, analysis, navigate }) {
  const cash = data.accounts.reduce((n,a)=>n+a.balance,0);
  const credit = data.cards.reduce((n,c)=>n+Math.max(0,c.limit-c.balance),0);
  const flexible = analysis.budget.categories.filter(c=>c.importance==='FLEXIBLE').reduce((n,c)=>n+Math.max(0,c.remaining),0);
  return <div className="home-page">
    <section className="card-hero">
      <div className="hero-copy"><div className="eyebrow"><span className="orange-dash"/>YOUR BUDGET EXECUTES ITSELF</div><h1>ONE CARD.<br/><span>NO DECISIONS.</span></h1><p>Replace your wallet with one intelligent card that automatically enforces your financial plan every time you spend.</p><div className="hero-actions"><a className="primary-button" href="#purchase-demo"><Play size={15} fill="currentColor"/>Watch purchase demo</a><button className="secondary-button" onClick={()=>navigate('wallet')}>View wallet <ArrowUpRight size={17}/></button></div><span className="hero-caption">Spend normally. We handle the decision.</span></div>
      <div className="hero-stage"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="stage-coordinate">01 / THE BUDGETPLUS CARD</div><div className="floating-chip"><ShieldCheck size={15}/>Your plan. Built in.</div><CardOverview data={data}/><div className="stage-footer"><span>ONE TAP. EVERYTHING ALIGNED.</span><ArrowDown size={15}/></div></div>
    </section>
    <section className="value-strip" aria-label="The BudgetPlus difference">{[[CreditCard,'01','One card','Carry one master card instead of juggling multiple cards.'],[Zap,'02','Auto decisioning','Your funding source and purchase rules, applied instantly.'],[ShieldCheck,'03','Budget execution','Your financial plan works at checkout, not in a spreadsheet.']].map(([Icon,index,title,copy])=><article key={title}><div className="feature-top"><Icon size={23}/><span>{index}</span></div><h2>{title}</h2><p>{copy}</p></article>)}</section>
    <section className="landing-section numbers-section"><SectionTitle number="01" label="YOUR MONEY, CONNECTED" title="Less mental math." accent="More living."><span className="live-badge"><i/>LIVE SNAPSHOT</span></SectionTitle><div className="home-metrics">{[
      ['Total cash',cash,true,'Across your cash accounts',Layers3],['Available credit',credit,true,'Across funding cards',CreditCard],['BudgetPlus Score',analysis.score.value,false,analysis.score.provisional?'Provisional':analysis.score.rating,ShieldCheck],['Flexible spend left',flexible,true,'Category allowances · this month',Zap]
    ].map(([label,value,currency,note,Icon],i)=><button className={`metric-card metric-${i}`} key={label} onClick={()=>navigate('money')}><div className="metric-label"><span>{label}</span><Icon size={17}/></div><strong><AnimatedNumber value={value} currency={currency}/></strong><div className="metric-bottom"><span>{note}</span><ArrowUpRight size={14}/></div><div className="metric-decoration" aria-hidden="true"/></button>)}</div></section>
    <section className="landing-section how-section"><SectionTitle number="02" label="IN THE MOMENT" title="One tap in the real world." accent="A whole plan behind it."/><div className="execution-steps">{[[Fingerprint,'Tap card','Pay like you always do.'],[Layers3,'Check the whole picture','Budget. Balances. Credit. Goals. Rules.'],[ShieldCheck,'Make the decision','Approve, route, warn, or block. Automatically.']].map(([Icon,title,copy],i)=><article key={title}><div className="flow-icon"><Icon size={25}/><span>0{i+1}</span></div><h3>{title}</h3><p>{copy}</p>{i<2&&<ArrowRight className="flow-arrow" size={24}/>}</article>)}</div></section>
    <section className="landing-section demo-section" id="purchase-demo"><SectionTitle number="03" label="SEE THE DECISION" title="A burrito. A tap." accent="A better decision."><p>Try the walkthrough.<br/>Then put your own plan to work.</p></SectionTitle><PurchasePreview/></section>
    <section className="landing-section coach-preview"><div className="coach-pitch"><div className="eyebrow"><span className="section-index">04 /</span>YOUR POCKET ACCOUNTANT</div><h2>A little clarity.<br/><span>A lot less guesswork.</span></h2><p>Your plan knows the numbers.<br/>Ask Gemini to help you make sense of them.</p><button className="primary-button" onClick={()=>navigate('coach')}>Ask BudgetPlus <ArrowUpRight size={17}/></button></div><div className="coach-preview-panel"><div className="assistant-identity"><span className="assistant-avatar"><Sparkles size={22}/></span><div><strong>BudgetPlus</strong><small>Your plan, at a glance</small></div><span className="tiny-label">LIVE SIGNAL</span></div><div className="preview-message"><p>{priority(data,analysis)}</p><span>From your financial plan</span></div><button className="suggested-prompt" onClick={()=>navigate('coach')}>Which purchase should I delay? <ArrowUpRight size={15}/></button><div className="coach-provider"><Sparkles size={13}/>Go deeper with Gemini in AI Coach</div></div></section>
    <section className="final-cta"><div className="eyebrow">YOUR LIFE. LESS ADMIN.</div><h2>Stop budgeting<br/><span>manually.</span></h2><p>Let one card handle the decision.</p><div className="hero-actions"><button className="primary-button" onClick={()=>navigate('wallet')}>Open Wallet <ArrowUpRight size={17}/></button><a className="secondary-button" href="/merchant" target="_blank" rel="noreferrer">Try Demo Purchase <ArrowUpRight size={17}/></a></div><div className="cta-orbit" aria-hidden="true"/></section>
  </div>;
}
