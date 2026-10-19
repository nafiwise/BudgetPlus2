import { generateFinancialProfile } from './profileEngine.js';
import { calculateBudgets } from './budgetEngine.js';
import { calculateScore } from './scoreEngine.js';
import { round } from './format.js';
export function analyze(data) {
  const profile = generateFinancialProfile(data);
  const budget = calculateBudgets(data, profile);
  return { profile, budget, score: calculateScore(data, profile, budget) };
}
export function applyPurchase(data, transaction, cardId) {
  return { ...data, cards: data.cards.map(c => c.id === cardId ? { ...c, balance: round(c.balance + transaction.amount) } : c),
    transactions: [{ ...transaction, type: 'purchase', date: data.asOf, card: data.cards.find(c => c.id === cardId).name, simulated: true }, ...data.transactions] };
}
