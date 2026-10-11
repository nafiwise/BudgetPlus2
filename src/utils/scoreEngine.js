export function calculateScore(data, profile, budget) {
  const clamp = n => Math.max(0, Math.min(1, n));
  const variable = budget.categories.filter(c => !['Housing','School'].includes(c.name));
  const pace = variable.reduce((n,c) => n + Math.max(0,c.pace - 1),0) / Math.max(1,variable.length);
  const utilization = profile.cardDebt / data.cards.reduce((n,c) => n+c.limit,0);
  const avoidable = data.recurring.filter(r => r.flag).reduce((n,r) => n+r.amount,0);
  const healthIndex = Math.max(0, Math.min(100,
    25 * clamp((profile.availableLiquidity - profile.cardDebt - budget.protectedGoals) / Math.max(1,budget.obligations + data.buffer)) +
    20 * clamp(budget.runway / 2) + 20 * clamp(1-pace/2) + 15 * clamp(1-utilization*2) +
    10 * clamp(budget.projectedEndMonth / Math.max(1,budget.protectedGoals+data.buffer)) +
    10 * clamp(1-avoidable/100)));
  const value = Math.round(300 + healthIndex * 5.5);
  const rating = value < 580 ? 'Poor' : value < 670 ? 'Fair' : value < 740 ? 'Good' : value < 800 ? 'Very Good' : 'Excellent';
  return { value, rating, healthIndex, reasons: [
    `${budget.safeRaw >= 0 ? '+' : '−'} ${budget.safeRaw >= 0 ? 'Essentials, card balances and reserves remain covered' : 'Resources are below protected obligations and reserves'}`,
    `${budget.runway >= 2 ? '+' : '−'} ${budget.runway.toFixed(1)} months of runway after card debt and protected savings`,
    `${pace > .2 ? '−' : '+'} ${pace > .2 ? 'Some flexible categories are spending faster than expected' : 'Flexible spending is near its expected pace'}`,
    `− ${data.recurring.filter(r => r.flag).length} recurring costs are worth reviewing`,
    `${utilization < .3 ? '+' : '−'} ${(utilization*100).toFixed(0)}% of linked credit limits used; deferred student debt tracked separately`,
  ] };
}
