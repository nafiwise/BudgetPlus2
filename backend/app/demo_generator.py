"""Coherent synthetic statements, never applied to imported workspaces."""
from calendar import monthrange
from datetime import date, timedelta
from random import SystemRandom
from uuid import uuid4

from .engines import analyze, rnd

SCENARIOS = {
    'comfortable': ('Financially comfortable', 'salary', (2500, 4500), (.03, .12), .8),
    'tight': ('Tight cash', 'freelance', (-250, -40), (.15, .30), 1.25),
    'high_credit': ('High credit utilization', 'salary', (500, 1000), (.62, .82), 1.1),
    'student': ('Student / irregular income', 'aid', (100, 450), (.03, .15), 1.0),
    'upcoming': ('High upcoming expenses', 'salary', (-450, -100), (.10, .22), .9),
    'overspending': ('Strong savings / overspending', 'salary', (1000, 1800), (.10, .23), 2.8),
    'professional': ('Stable professional income', 'salary', (1300, 2400), (.04, .14), .95),
}


def generate(previous=None, *, rng=None, today=None, scenario=None):
    rng = rng or SystemRandom()
    today = today or date.today()
    scenario = scenario or rng.choice([key for key in SCENARIOS if key != previous])
    label, income, free_range, utilization, pace = SCENARIOS[scenario]
    scale = rng.uniform(.9, 1.15)
    student = scenario == 'student'
    monthly = {'Housing': rnd((650 if student else 1250) * scale),
               'Groceries': rnd(330 * scale), 'Transportation': rnd(110 * scale),
               'Dining': rnd(220 * scale), 'Utilities': rnd(95 * scale),
               'Subscriptions': rnd(35 * scale),
               'School' if student else 'Wellness': rnd((140 if student else 65) * scale),
               'Travel' if not student else 'School extras': rnd(90 * scale)}
    levels = {name: 'MUST PAY' if name in ('Housing', 'Utilities', 'School') else
              'CAN WAIT' if name in ('Travel', 'School extras') else 'FLEXIBLE' for name in monthly}
    levels['Laptop replacement'] = 'CAN WAIT'
    levels['Debt Payments'] = 'MUST PAY'
    batch = uuid4().hex
    transactions = []

    def add(day, merchant, amount, category, kind='purchase', source=None):
        transactions.append(dict(id=f'{batch}-{len(transactions)}', date=day.isoformat(), merchant=merchant,
                                 amount=rnd(amount), category=category, type=kind, account='Checking',
                                 source=source or 'synthetic', importance=levels.get(category, 'FLEXIBLE')))

    # Three prior statements establish personalized limits, followed by current spending.
    for offset in (3, 2, 1, 0):
        index = today.year * 12 + today.month - 1 - offset
        year, month = divmod(index, 12)
        month += 1
        days = monthrange(year, month)[1]
        for category, baseline in monthly.items():
            essential = levels[category] == 'MUST PAY'
            current_fraction = 1 if essential else today.day / days * pace
            amount = baseline * (current_fraction if offset == 0 else rng.uniform(.96, 1.04))
            count = 1 if essential else (4 if offset else min(4, today.day))
            total = rnd(amount)
            parts = [rnd(total / count)] * (count - 1)
            parts.append(rnd(total - sum(parts)))
            for i, part in enumerate(parts):
                day = 1 if essential else max(1, round((i+1) * (days if offset else today.day) / count))
                add(date(year, month, day), 'Rent' if category == 'Housing' else category, part, category)
        if income == 'salary':
            salary = rnd(sum(monthly.values()) * 1.35)
            for day in (1, 15):
                if offset or day <= today.day: add(date(year, month, day), 'Payroll', salary/2, 'Income', 'deposit', 'salary')
        elif income == 'freelance':
            day = 7 if offset else min(7, today.day)
            add(date(year, month, day), 'Freelance project', sum(monthly.values())*rng.uniform(.65, 1.05), 'Income', 'deposit', 'freelance')
    if income == 'aid':
        add(date(today.year, today.month, 1), 'Term aid disbursement', sum(monthly.values())*2.5, 'Income', 'deposit', 'financial_aid')

    limits = [4000, 5500, 3000] if not student else [2000, 2500, 1500]
    cards = [dict(id=card_id, name=name, last4=last4, balance=rnd(limit*rng.uniform(*utilization)),
                  limit=limit, status='active', preferred=i == 1, rewards=rewards)
             for i, (card_id, name, last4, limit, rewards) in enumerate(zip(
                 ['amex', 'chase', 'discover'], ['Amex Gold', 'Chase Freedom', 'Discover Student'],
                 ['1008', '4821', '9034'], limits,
                 [{'default':1, 'Dining':4, 'Groceries':4}, {'default':1.5, 'Transportation':3}, {'default':1, 'Groceries':5}]))]
    savings = rnd((700 if student else 6500 if scenario == 'overspending' else 3500) * scale)
    protected = rnd(savings * .7)
    next_month = today.replace(day=28) + timedelta(days=4)
    recurring = [dict(id=f'recurring-{name}', merchant='Rent' if name == 'Housing' else name,
                      category=name, amount=monthly[name], nextDate=next_month.replace(day=1).isoformat(),
                      essential=name != 'Subscriptions', inferred=False,
                      flag='Review unused services' if name == 'Subscriptions' and scenario in ('tight','overspending') else None)
                 for name in ('Housing', 'Utilities', 'Subscriptions')]
    due = today + timedelta(days=12)
    upcoming = [dict(id='planned-laptop', merchant='Laptop replacement', category='Laptop replacement',
                     amount=rnd(850*scale), date=(today+timedelta(days=45)).isoformat(), essential=False)]
    if student or scenario == 'upcoming':
        category = 'School' if student else 'Medical'
        levels[category] = 'MUST PAY'
        upcoming.append(dict(id='major-obligation', merchant='Course materials' if student else 'Medical bill',
                             category=category, amount=rnd((340 if student else 2200)*scale), date=due.isoformat(), essential=True))
    data = dict(version=3, mode='demo', asOf=today.isoformat(), balancesConfirmed=True, guardrail='balanced',
                accounts=[], cards=cards, goals=[dict(id='emergency',name='Emergency reserve',saved=savings,target=rnd(savings*1.7),protected=protected)],
                debts=[dict(name='Student loan' if student else 'Car loan',balance=rnd((12400 if student else 6500)*scale),
                            monthlyPayment=0 if student else rnd(180*scale),status='Deferred' if student else 'Repaying')],
                recurring=recurring, upcoming=upcoming, categoryImportance=levels, transactions=transactions,
                buffer=rnd((150 if student else 300)*scale), imports=[],
                demoScenario=dict(id=scenario,label=label,incomePattern=income))
    # Cash is derived from the same reserved-funds equation used by routing.
    budget = analyze(data)['budget']
    cash = rnd(sum(c['balance'] for c in cards) + protected + budget['obligations'] + data['buffer'] + rng.uniform(*free_range))
    cash = max(cash, savings + 50)
    data['accounts'] = [dict(id='checking',name='Checking',institution='Synthetic bank',balance=rnd(cash-savings)),
                        dict(id='savings',name='Savings',institution='Synthetic bank',balance=savings)]
    # Reconcile the cash-paid statement history to the current account snapshot.
    spent = sum(t['amount'] for t in transactions if t['type'] == 'purchase')
    deposited = sum(t['amount'] for t in transactions if t['type'] == 'deposit')
    opening = rnd(cash + spent - deposited)
    if opening < 0:
        # Surplus income was transferred to long-term investments, not lost from the ledger.
        add(today, 'Transfer to investments', -opening, 'Transfers', 'transfer')
        opening = 0
    data['demoScenario'].update(openingCash=opening, statementCash=cash)
    return data
