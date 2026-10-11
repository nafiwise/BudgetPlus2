"""Generate only synthetic UI fixtures; never open the user's database."""
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from app import db, plaid_service as plaid
from app.engines import analyze
from datetime import date

with tempfile.TemporaryDirectory() as directory:
    os.environ.update(BUDGETPLUS_DB=str(Path(directory) / 'test.sqlite3'), PLAID_ENV='sandbox', PLAID_CLIENT_ID='fixture', PLAID_SECRET='fixture')
    db.init()
    with db.connect() as c:
        demo, revision = db.read(c)
        c.execute('INSERT INTO plaid_items (item_id,environment,access_token,exchange_hash,institution_id,institution,history_status,last_sync) VALUES (?,?,?,?,?,?,?,?)',
                  ('fixture-item', 'sandbox', 'unused', 'fixture-hash', 'fixture-institution', 'Example Bank', 'HISTORICAL_UPDATE_COMPLETE', '2026-10-11T12:00:00Z'))
        raw = dict(account_id='fixture-account', name='Everyday Checking', type='depository', subtype='checking', mask='1234',
                   balances=dict(current=3500, available=3400, limit=None, iso_currency_code='USD'))
        a = plaid.normalize_account(raw, 'Example Bank', 'fixture-item')
        c.execute('INSERT INTO plaid_accounts VALUES (?,?,?)', ('fixture-account', 'fixture-item', json.dumps(a)))
        for id, amount, category, detailed, merchant in [('coffee', 12.5, 'FOOD_AND_DRINK', 'FOOD_AND_DRINK_COFFEE', 'Sample Coffee'), ('pay', -2500, 'INCOME', 'INCOME_WAGES', 'Sample Payroll')]:
            tx = plaid.normalize_transaction(dict(transaction_id=id, account_id='fixture-account', amount=amount, date=date.today().isoformat(),
                name=merchant, pending=False, iso_currency_code='USD', personal_finance_category=dict(primary=category, detailed=detailed)),
                {'fixture-account': a}, 'Example Bank', 'fixture-item')
            c.execute('INSERT INTO plaid_transactions VALUES (?,?,?)', (id, 'fixture-item', json.dumps(tx)))
        plaid.build_profile(c)
        personal, next_revision = db.read(c)
        status = plaid.status(c)
        accounts = plaid.cached(c, 'plaid_accounts')
    fixture = dict(demo=dict(data=demo, analysis=analyze(demo), revision=revision, decisions=[]),
                   personal=dict(data=personal, analysis=analyze(personal), revision=next_revision, decisions=[], plaidStatus=status),
                   status=status, accounts=accounts)
    (root / '.verification' / 'plaid-fixtures.json').write_text(json.dumps(fixture), encoding='utf-8')
print('Synthetic Plaid fixtures generated; user database untouched.')
