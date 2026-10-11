import { money } from './format.js';
export function createCoachContext(data, analysis) {
 return { financialProfile: analysis.profile, categories: analysis.budget.categories, score: analysis.score, transactions: data.transactions, recurringExpenses: data.recurring, goals: data.goals, cards: data.cards, projections: analysis.budget };
}
export function getCoachResponse(topic, context) {
 const { financialProfile:p, projections:b, categories, recurringExpenses } = context;
 if (topic === 'dining') { const c = categories.find(c => c.name === 'Dining'); return c ? `Dining has ${money(c.remaining)} remaining against its ${money(c.target)} target. ${c.status}. ${c.recommendation} A reward is not a reason to exceed your plan.` : 'No dining activity has been imported yet.'; }
 if (topic === 'bills') return `Review ${recurringExpenses.filter(r => r.flag).map(r => r.merchant).join(', ')}. Those flagged costs total ${money(recurringExpenses.filter(r => r.flag).reduce((n,r) => n+r.amount,0))} monthly. Confirm what you use before cancelling; no cancellation has been made.`;
 return `Your strategy is ${p.strategy.toLowerCase()}. ${p.description} After current card balances and protected savings, runway is ${b.runway.toFixed(1)} months. ${money(b.obligations)} is reserved for upcoming bills and ${money(b.safeToSpend)} remains safe to spend. Start with your fastest-moving categories.`;
}
