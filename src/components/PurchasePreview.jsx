import { useState } from 'react';
import { ArrowUpRight, Check, CreditCard, Fingerprint, RotateCcw, ShieldCheck } from 'lucide-react';

const steps = ['Tap your card', 'Check your plan', 'Choose funding'];
export default function PurchasePreview() {
  const [step, setStep] = useState(0);
  return <div className="purchase-preview">
    <div className="preview-merchant"><div className="terminal-top"><span className="merchant-monogram">C</span><span>CHIPOTLE<small>Illustrative checkout</small></span><span className="terminal-dots">•••</span></div><div className="preview-total"><span>YOUR TOTAL</span><strong>$18<span>.42</span></strong></div><div className="receipt-line"><span>Burrito bowl + drink</span><span>$18.42</span></div><button className="tap-preview" onClick={()=>setStep(n=>Math.min(n+1,3))} disabled={step===3}><Fingerprint size={25}/>{step===0?'Tap to preview':step===3?'Preview complete':'Continue walkthrough'}<span>→</span></button><p className="preview-footnote">Illustrative preview · no purchase posted</p></div>
    <div className="preview-routing"><div className="section-heading"><span className="eyebrow">BEHIND THE TAP</span><span className="live-badge"><i/>BUDGETPLUS</span></div><div className="routing-timeline">{steps.map((label,i)=><div key={label} className={step>i?'completed':step===i?'current':''}><span className="step-icon">{step>i?<Check size={15}/>:i+1}</span><div><strong>{label}</strong><small>{['One card at checkout.','Obligations and reserves checked first.','An eligible card funds the purchase.'][i]}</small></div></div>)}</div>
    {step===3?<div className="preview-success" role="status"><ShieldCheck size={21}/><div><strong>Approved · with a budget warning</strong><p>Example funding: Amex Gold</p><small>Reserves covered; Dining pace is high.</small></div><span className="success-spark" aria-hidden="true">✦</span></div>:<div className="preview-placeholder"><CreditCard size={20}/><span>{step===0?'Your plan is ready when you are.':'Every decision starts with your budget.'}</span></div>}
    <div className="preview-actions"><button className="text-button" onClick={()=>setStep(0)}><RotateCcw size={13}/>Replay</button><a className="text-button" href="/merchant" target="_blank" rel="noreferrer">Try with your live plan <ArrowUpRight size={15}/></a></div></div>
  </div>;
}
