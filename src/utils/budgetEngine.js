import { daysBetween, round, sum } from './format.js';
export function calculateBudgets(data, profile) {
  const month = data.asOf.slice(0, 7);
  const day = Number(data.asOf.slice(8));
  const monthDays = new Date(Date.UTC(Number(month.slice(0,4)), Number(month.slice(5)), 0)).getUTCDate();
  const upcoming = [...data.recurring.map(r => ({ ...r, date: r.nextDate })), ...data.upcoming].filter(r => daysBetween(data.asOf, r.date) >= 0 && daysBetween(data.asOf, r.date) <= 30).sort((a,b) => a.date.localeCompare(b.date));
  const categories = profile.categories.map(name => {
    const prior = data.transactions.filter(t => t.type === 'purchase' && t.category === name && t.date.slice(0,7) < month);
    const months = new Set(prior.map(t => t.date.slice(0,7))).size || 1;
    const spent = sum(data.transactions.filter(t => t.type === 'purchase' && t.category === name && t.date.startsWith(month)));
    const due = upcoming.filter(r => r.category === name);
    const thisMonth = sum(due.filter(r => r.date.startsWith(month)));
    const essential = ['Housing', 'School', 'Debt Payments'].includes(name);
    const reduction = profile.cashPreservation && ['Dining','Shopping','Entertainment'].includes(name) ? 0.8 : 1;
    const importedSpent = sum(data.transactions.filter(t => t.type === 'purchase' && !t.simulated && t.category === name && t.date.startsWith(month)));
    const target = round(Math.max(sum(prior) / months * reduction, essential ? importedSpent + thisMonth : thisMonth, 30));
    const remaining = round(target - spent);
    const pace = essential ? spent / target : spent / Math.max(1, target * day / monthDays);
    const status = remaining < 0 ? 'Over target' : essential ? 'Protected expense' : pace > 1.2 ? 'Faster than expected' : 'On track';
    return { name, spent, target, remaining, pace, status, upcoming: due[0], recommendation: essential ? 'Keep upcoming essentials protected.' : remaining <= 0 ? 'Pause optional purchases in this category.' : `Aim for no more than $${(remaining / (monthDays - day + 1) * 7).toFixed(0)} over the next 7 days.` };
  });
  const protectedGoals = sum(data.goals, 'protected');
  const obligations = sum(upcoming);
  // Card balances are fully reserved, so spending on credit never creates liquidity.
  const safeRaw = round(profile.availableLiquidity - profile.cardDebt - protectedGoals - obligations - data.buffer);
  const monthlyBurn = Math.max(profile.historicalMonthlySpend, sum(data.recurring), 1);
  const runway = Math.max(0, (profile.availableLiquidity - profile.cardDebt - protectedGoals) / monthlyBurn);
  const remainingVariable = sum(categories.filter(c => !['Housing','School','Subscriptions'].includes(c.name)).map(c => ({ amount: Math.max(0, c.target - c.spent) })));
  const endMonthDues = sum(upcoming.filter(r => r.date.startsWith(month)));
  return { categories, upcoming, protectedGoals, obligations, safeRaw, safeToSpend: Math.max(0, safeRaw), runway, monthlyBurn,
    projectedEndMonth: round(profile.availableLiquidity - profile.cardDebt - endMonthDues - remainingVariable), spent: sum(categories, 'spent') };
}
