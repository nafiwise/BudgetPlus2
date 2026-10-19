"""Python port of the existing financial engines; no payment network calls."""
from copy import deepcopy
from datetime import date, timedelta
from calendar import monthrange
import math


def rnd(n):
    return math.floor(n * 100 + 0.50000001) / 100


def total(rows, key='amount'):
    return sum(r.get(key, 0) for r in rows)


def importance(category):
    if category.lower() in ('housing', 'rent', 'school', 'debt payments', 'utilities', 'medical'):
        return 'MUST PAY'
    if category.lower() in ('travel', 'shopping', 'entertainment'):
        return 'CAN WAIT'
    return 'FLEXIBLE'


def next_monthly_due(value, today):
    due = date.fromisoformat(value)
    original_day = due.day
    while due < today:
        year, month = due.year + (due.month == 12), due.month % 12 + 1
        due = date(year, month, min(original_day, monthrange(year, month)[1]))
    return due.isoformat()


def analyze(d):
    today = date.fromisoformat(d['asOf'])
    month, day = d['asOf'][:7], today.day
    month_days = monthrange(today.year, today.month)[1]
    purchases = [t for t in d['transactions'] if t['type'] == 'purchase' and not t.get('pending')]
    deposits = [t for t in d['transactions'] if t['type'] == 'deposit' and not t.get('pending')]
    salary = [t for t in deposits if t.get('source') == 'salary']
    history = [t for t in purchases if t['date'][:7] < month]
    categories = list(dict.fromkeys([*[t['category'] for t in purchases + d['recurring'] + d['upcoming']], *d.get('categoryImportance', {}), *d.get('categoryLimits', {})]))
    cash_preservation = not salary
    p = dict(incomeType='fixed' if len(salary) >= 2 else 'variable' if deposits else 'none',
             cashPreservation=cash_preservation, categories=categories,
             historicalMonthlySpend=total(history) / max(1, len({t['date'][:7] for t in history})),
             availableLiquidity=sum(min(a['balance'], a['available']) if a.get('source') == 'plaid' and a.get('available') is not None else a['balance'] for a in d['accounts']), cardDebt=total(d['cards'], 'balance'),
             studentDebt=total(d['debts'], 'balance'), recurringTotal=total(d['recurring']), savings=total(d['goals'], 'saved'),
             strategy='Cash preservation' if cash_preservation else 'Sustainable spending',
             description='Protect essentials, card repayment, goals and reserves before optional purchases. Imported deposits are not assumed to be salary.')
    debt_dues = [dict(id=f'debt-{i}', merchant=r['name'], category='Debt Payments', amount=r['monthlyPayment'], date=(today+timedelta(days=30)).isoformat(), essential=True) for i, r in enumerate(d['debts']) if r.get('monthlyPayment', 0) > 0]
    upcoming = sorted([r for r in [*[{**r, 'date': next_monthly_due(r['nextDate'], today)} for r in d['recurring']], *d['upcoming'], *debt_dues]
                       if 0 <= (date.fromisoformat(r['date']) - today).days <= 30], key=lambda r: r['date'])
    cats = []
    for name in categories:
        prior = [t for t in history if t['category'] == name]
        current = [t for t in purchases if t['category'] == name and t['date'][:7] == month]
        due = [r for r in upcoming if r['category'] == name]
        this_month = total([r for r in due if r['date'][:7] == month])
        level = d.get('categoryImportance', {}).get(name, importance(name))
        essential = level == 'MUST PAY'
        reduction = .8 if cash_preservation and name in ('Dining', 'Shopping', 'Entertainment') else 1
        target = rnd(max(total(prior) / max(1, len({t['date'][:7] for t in prior})) * reduction,
                         total([t for t in current if not t.get('simulated')]) + this_month if essential else this_month, 30))
        target = d.get('categoryLimits', {}).get(name, target)
        spent = rnd(total(current))
        remaining = rnd(target - spent)
        pace = spent / max(1, target if essential else target * day / month_days)
        cats.append(dict(name=name, importance=level, spent=spent, target=target, remaining=remaining, pace=pace,
                         status='Over target' if remaining < 0 else 'Protected expense' if essential else 'Faster than expected' if pace > 1.2 else 'On track',
                         upcoming=due[0] if due else None,
                         recommendation='Keep upcoming essentials protected.' if essential else 'Pause optional purchases.' if remaining <= 0 else f'Aim for ${remaining / (month_days-day+1)*7:.0f} or less over the next 7 days.'))
    protected = total(d['goals'], 'protected')
    # Sandbox authorizations reserve local cash without altering Plaid bank/card balances.
    holds = total([t for t in d['transactions'] if t.get('provider') == 'lithic' and t.get('authorizationStatus') == 'authorized'])
    obligations = total(upcoming)
    safe = rnd(p['availableLiquidity'] - p['cardDebt'] - holds - protected - obligations - d['buffer'])
    burn = max(p['historicalMonthlySpend'], p['recurringTotal'], 1)
    runway = max(0, (p['availableLiquidity']-p['cardDebt']-holds-protected) / burn)
    variable = sum(max(0, c['remaining']) for c in cats if c['name'] not in ('Housing', 'School', 'Subscriptions'))
    b = dict(categories=cats, upcoming=upcoming, protectedGoals=protected, obligations=rnd(obligations), safeRaw=safe,
             safeToSpend=max(0, safe), runway=runway, monthlyBurn=burn, authorizationHolds=rnd(holds),
             projectedEndMonth=rnd(p['availableLiquidity']-p['cardDebt']-holds-total([r for r in upcoming if r['date'][:7] == month])-variable), spent=total(cats, 'spent'))
    flexible = [c for c in cats if c['name'] not in ('Housing', 'School')]
    pace = sum(max(0, c['pace']-1) for c in flexible) / max(1, len(flexible))
    utilization = p['cardDebt'] / max(1, total(d['cards'], 'limit'))
    avoidable = total([r for r in d['recurring'] if r.get('flag')])
    clamp = lambda n: max(0, min(1, n))
    health = (25*clamp((p['availableLiquidity']-p['cardDebt']-holds-protected)/max(1, obligations+d['buffer']))
              +20*clamp(runway/2)+20*clamp(1-pace/2)+15*clamp(1-utilization*2)
              +10*clamp(b['projectedEndMonth']/max(1, protected+d['buffer']))+10*clamp(1-avoidable/100))
    value = math.floor(300+health*5.5+.5)
    score = dict(value=value, healthIndex=health, provisional=not d.get('balancesConfirmed', True),
                 rating='Poor' if value < 580 else 'Fair' if value < 670 else 'Good' if value < 740 else 'Very Good' if value < 800 else 'Excellent',
                 reasons=[f'{"Covered" if safe >= 0 else "Underfunded"}: obligations, card balances and reserves',
                          f'{runway:.1f} months of runway after card debt and protected savings',
                          'Flexible spending is faster than expected' if pace > .2 else 'Flexible spending is near expected pace',
                          f'{len([r for r in d["recurring"] if r.get("flag")])} recurring costs to review', f'{utilization:.0%} of linked credit limits used'])
    recommendations = [c['recommendation'] + ' ('+c['name']+')' for c in cats if c['pace'] > 1.2 and c['importance'] != 'MUST PAY']
    return dict(profile=p, budget=b, score=score, recommendations=recommendations or ['Keep essentials and reserves protected.'], projectedSavings=rnd(avoidable))


def apply_purchase(d, tx, card_id=None):
    result = deepcopy(d)
    if card_id is None:
        result['transactions'].insert(0, {**tx, 'type': 'purchase', 'date': d['asOf'], 'card': 'BudgetPlus Sandbox',
                                        'account': 'BudgetPlus Sandbox', 'provider': 'lithic', 'source': 'Lithic Sandbox',
                                        'authorizationStatus': 'authorized', 'simulated': True})
        return result
    card = next(c for c in result['cards'] if c['id'] == card_id)
    card['balance'] = rnd(card['balance'] + tx['amount'])
    result['transactions'].insert(0, {**tx, 'type': 'purchase', 'date': d['asOf'], 'card': card['name'], 'account': card['name'], 'simulated': True})
    return result


def route(tx, d, *, execution='simulated'):
    before = analyze(d)
    category = next((c for c in before['budget']['categories'] if c['name'] == tx['category']), None)
    def blocked(reason, code='budget_warning'):
        return dict(approved=False, status='blocked', reason=reason, reasonCode=code, selectedCard=None, scoreImpact=0, estimatedReward=0, financialWarning=reason, categoryImpact=None)
    if not d.get('balancesConfirmed', True):
        return blocked('Confirm current cash, card balances, goals and obligations in Money first. History alone cannot establish available funds.', 'unconfirmed_balances')
    if not category:
        return blocked('Choose a personalized category from Money, or add this category there first.', 'unknown_category')
    if tx['amount'] > before['budget']['safeToSpend']:
        return blocked('This purchase would use money reserved for obligations, card repayment, goals or your buffer.', 'insufficient_funds')
    card = None
    if execution == 'lithic':
        if tx['amount'] > category['remaining']:
            return blocked(f"{tx['category']} has ${category['remaining']:.2f} remaining; this purchase exceeds its monthly spending limit.", 'category_limit')
    else:
        candidates = [c for c in d['cards'] if c['status'] == 'active' and c['limit']-c['balance'] >= tx['amount'] and (c['balance']+tx['amount'])/c['limit'] <= .5]
        if not candidates:
            return blocked('No active funding card has available credit within the 50% per-card debt guardrail.', 'insufficient_credit')
        def utility(c):
            return c['rewards'].get(tx['category'], c['rewards']['default']) - 8*(c['balance']+tx['amount'])/c['limit'] + (.15 if c['preferred'] else 0)
        card = sorted(candidates, key=lambda c: (-utility(c), c['id']))[0]
    after = analyze(apply_purchase(d, tx, card['id'] if card else None))
    cat_after = next(c for c in after['budget']['categories'] if c['name'] == tx['category'])
    warnings = []
    if tx['amount'] > category['remaining']: warnings.append('Exceeds the personalized category target.')
    if cat_after['pace'] > 1.2: warnings.append('Category spending is faster than expected.')
    if after['budget']['runway'] < 1: warnings.append('Financial runway is short.')
    if after['score']['value'] < 670: warnings.append('Financial health needs extra care.')
    level = tx.get('importance') or category['importance']
    if level == 'CAN WAIT' and warnings: warnings.append('This purchase can wait; consider postponing it.')
    if d['guardrail'] == 'strict' and warnings:
        return blocked(' '.join(warnings) + ' Strict guardrails require waiting.')
    if execution == 'lithic':
        return dict(approved=True, status='approved', selectedCard=None,
                    reason=f"{tx['category']} purchase remains within the category limit and protected-money guardrails.",
                    importance=level, financialWarning=' '.join(warnings) or None,
                    categoryImpact=dict(category=category['name'], remaining=cat_after['remaining']),
                    scoreImpact=after['score']['value']-before['score']['value'], scoreAfter=after['score']['value'],
                    safeAfter=after['budget']['safeToSpend'], estimatedReward=0, rewardRate=0)
    rate = card['rewards'].get(tx['category'], card['rewards']['default'])
    return dict(approved=True, status='approved', cardId=card['id'], selectedCard=card['name'], last4=card['last4'],
                reason=f'{card["name"]} balances rewards, available credit and debt concentration' + (' with your preferred-card setting.' if card['preferred'] else '.'),
                rewardRate=rate, estimatedReward=rnd(tx['amount']*rate/100), importance=level,
                financialWarning=' '.join(warnings) or None, categoryImpact=dict(category=category['name'], remaining=cat_after['remaining']),
                scoreImpact=after['score']['value']-before['score']['value'], scoreAfter=after['score']['value'],
                healthIndexImpact=after['score']['healthIndex']-before['score']['healthIndex'], safeAfter=after['budget']['safeToSpend'])
