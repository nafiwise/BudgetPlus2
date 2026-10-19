import { sum } from './format.js';
export function generateFinancialProfile(data) {
  const deposits = data.transactions.filter(t => t.type === 'deposit');
  const salary = deposits.filter(t => t.source === 'salary');
  const incomeType = salary.length >= 2 ? 'fixed' : deposits.some(t => ['irregular', 'salary'].includes(t.source)) ? 'variable' : 'none';
  const cashPreservation = !salary.length;
  const history = data.transactions.filter(t => t.type === 'purchase' && t.date.slice(0, 7) < data.asOf.slice(0, 7));
  const months = new Set(history.map(t => t.date.slice(0, 7))).size || 1;
  const categories = [...new Set([...data.transactions.filter(t => t.type === 'purchase').map(t => t.category), ...data.recurring.map(t => t.category), ...data.upcoming.map(t => t.category)])];
  return { incomeType, cashPreservation, categories, historicalMonthlySpend: sum(history) / months,
    availableLiquidity: sum(data.accounts, 'balance'), cardDebt: sum(data.cards, 'balance'), studentDebt: sum(data.debts, 'balance'),
    recurringTotal: sum(data.recurring), savings: sum(data.goals, 'saved'),
    strategy: cashPreservation ? 'Cash preservation' : 'Sustainable spending',
    description: cashPreservation ? 'Loan and aid deposits are finite resources, not a monthly salary. Cover essentials, protect your reserve, and extend your runway.' : 'Match spending to imported income while protecting upcoming obligations and goals.',
    priorities: ['Cover essential expenses', 'Protect emergency savings', 'Reduce avoidable recurring costs'],
  };
}
