// Imported balances are current snapshots; historical transactions are already reflected.
export const mockFinancialData = {
  version: 2, asOf: '2026-10-10', guardrail: 'balanced', walletAdded: false,
  accounts: [{ id: 'checking', institution: 'Campus Credit Union', name: 'Student checking', balance: 2850 }, { id: 'savings', institution: 'Ally', name: 'Emergency savings', balance: 800 }],
  cards: [
    { id: 'amex', name: 'Amex Gold', last4: '1008', balance: 340, limit: 2000, status: 'active', preferred: false, rewards: { Dining: 4, Groceries: 4, default: 1 } },
    { id: 'chase', name: 'Chase Freedom', last4: '4821', balance: 180, limit: 2500, status: 'active', preferred: true, rewards: { Dining: 3, Transportation: 3, default: 1.5 } },
    { id: 'discover', name: 'Discover Student', last4: '9034', balance: 100, limit: 1500, status: 'locked', preferred: false, rewards: { Groceries: 5, default: 1 } },
  ],
  debts: [{ name: 'Federal student loan', balance: 12400, monthlyPayment: 0, status: 'Deferred while enrolled' }],
  goals: [{ id: 'emergency', name: 'Emergency fund', saved: 800, target: 1500, protected: 800 }],
  buffer: 400,
  recurring: [
    { id: 'rent', merchant: 'Campus apartments', category: 'Housing', amount: 950, nextDate: '2026-11-01', essential: true },
    { id: 'phone', merchant: 'Mobile plan', category: 'Subscriptions', amount: 45, nextDate: '2026-10-18', essential: true },
    { id: 'spotify', merchant: 'Spotify Student', category: 'Subscriptions', amount: 6.99, nextDate: '2026-10-15', flag: 'Review eligibility for bundled student benefits' },
    { id: 'netflix', merchant: 'Netflix', category: 'Subscriptions', amount: 17.99, nextDate: '2026-10-21', flag: 'Two video services: consider keeping one' },
    { id: 'hulu', merchant: 'Hulu', category: 'Subscriptions', amount: 9.99, nextDate: '2026-10-24', flag: 'Potential overlap with Netflix' },
  ],
  upcoming: [{ id: 'books', merchant: 'Course materials', category: 'School', amount: 340, date: '2026-10-28', essential: true }],
  transactions: [
    { id: 'aid', date: '2026-09-01', merchant: 'Student loan disbursement', amount: 5800, category: 'Financial aid', type: 'deposit', source: 'loan' },
    { id: 'grant', date: '2026-09-01', merchant: 'Campus grant', amount: 1500, category: 'Financial aid', type: 'deposit', source: 'aid' },
    { id: 'work', date: '2026-10-04', merchant: 'Weekend tutoring', amount: 120, category: 'Irregular income', type: 'deposit', source: 'irregular' },
    ...[['Housing',950],['Groceries',270],['Dining',220],['Transportation',120],['School',180],['Subscriptions',79.97],['Personal Care',40]].map(([category,amount], i) => ({ id: `sep-${i}`, date: '2026-09-25', merchant: `${category} imported monthly activity`, category, amount, type: 'purchase', card: 'Imported account' })),
    ...[['Campus apartments','Housing',950],['Campus market','Groceries',86],['Campus dining','Dining',126],['Metro Transit','Transportation',28],['Bookstore','School',55],['Pharmacy','Personal Care',12]].map(([merchant,category,amount],i) => ({ id: `oct-${i}`, date: `2026-10-0${i+1}`, merchant, category, amount, type: 'purchase', card: 'Imported account' })),
  ], imports: [],
};
export const freshDemo = () => structuredClone(mockFinancialData);
