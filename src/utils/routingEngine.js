import { analyze, applyPurchase } from './financialState.js';
import { money, round } from './format.js';
export function routeTransaction(transaction, data) {
  const before = analyze(data);
  const category = before.budget.categories.find(c => c.name === transaction.category);
  const blocked = reason => ({ approved: false, status: 'blocked', reason, selectedCard: null, scoreImpact: 0, safeImpact: 0, estimatedReward: 0 });
  if (!transaction.merchant?.trim() || !Number.isFinite(transaction.amount) || transaction.amount <= 0 || round(transaction.amount) !== transaction.amount || !category) return blocked('Enter a merchant, valid category and positive amount with at most two decimals.');
  if (transaction.amount > before.budget.safeToSpend) return blocked('This purchase would use money reserved for upcoming obligations, card repayment, goals or your buffer.');
  const warnings = [];
  if (transaction.amount > category.remaining) warnings.push('This exceeds the personalized category target.');
  const projectedData = { ...data, transactions: [{ ...transaction, type: 'purchase', date: data.asOf, simulated: true }, ...data.transactions], cards: data.cards.map((c,i) => i === 0 ? { ...c, balance: c.balance + transaction.amount } : c) };
  const projected = analyze(projectedData);
  const projectedCategory = projected.budget.categories.find(c => c.name === transaction.category);
  if (projectedCategory.pace > 1.2) warnings.push('This category is spending faster than expected.');
  if (projected.budget.runway < 1) warnings.push('Your financial runway is short.');
  if (projected.score.value < 670) warnings.push('Your financial health needs extra care.');
  if (data.guardrail === 'strict' && warnings.length) return blocked(warnings.join(' ') + ' Strict guardrails require you to wait.');
  const candidates = data.cards.filter(c => c.status === 'active' && round(c.limit-c.balance) >= transaction.amount && (c.balance+transaction.amount)/c.limit <= .5)
    .map(c => ({ ...c, rewardRate: c.rewards[transaction.category] ?? c.rewards.default,
      // Reward differences are balanced against post-purchase debt concentration.
      utility: (c.rewards[transaction.category] ?? c.rewards.default) - 8*(c.balance+transaction.amount)/c.limit + (c.preferred ? .15 : 0) }))
    .sort((a,b) => b.utility-a.utility || a.id.localeCompare(b.id));
  if (!candidates.length) return blocked('No active linked card has enough credit within the 50% per-card debt guardrail.');
  const card = candidates[0];
  const after = analyze(applyPurchase(data, transaction, card.id));
  return { approved: !warnings.length, status: warnings.length ? 'warning' : 'approved', cardId: card.id, selectedCard: card.name,
    reason: `${warnings.join(' ')} ${card.name} balances rewards with available credit and debt concentration${card.preferred ? ', including your preferred-card setting' : ''}. Locked cards are excluded.`.trim(),
    rewardRate: card.rewardRate, estimatedReward: round(transaction.amount*card.rewardRate/100),
    budgetImpact: `${money(category.remaining-transaction.amount)} remaining in ${category.name}`,
    safeImpact: round(after.budget.safeToSpend-before.budget.safeToSpend), scoreImpact: after.score.value-before.score.value,
    scoreAfter: after.score.value, safeAfter: after.budget.safeToSpend, runwayAfter: after.budget.runway };
}
