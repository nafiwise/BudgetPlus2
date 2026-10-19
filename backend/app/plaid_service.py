"""Local single-workspace Plaid adapter. Tokens never enter workspace snapshots."""
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException
from . import db
from .engines import importance
from .importers import detect_recurring

sync_lock = Lock()


def environment():
    return os.getenv('PLAID_ENV', 'production').strip().lower()


def configured():
    return environment() in ('production', 'sandbox') and all(os.getenv(k, '').strip() for k in ('PLAID_CLIENT_ID', 'PLAID_SECRET'))


def client():
    if not configured():
        raise HTTPException(503, 'Add PLAID_CLIENT_ID and PLAID_SECRET to backend/.env, set PLAID_ENV to production or sandbox, then restart BudgetPlus.')
    try:
        import plaid
        from plaid.api.plaid_api import PlaidApi
    except ImportError:
        raise HTTPException(503, 'Plaid dependencies are missing. Install backend/requirements.txt and restart BudgetPlus.') from None
    config = plaid.Configuration(host=plaid.Environment.Production if environment() == 'production' else plaid.Environment.Sandbox,
                                 api_key={'clientId': os.environ['PLAID_CLIENT_ID'].strip(), 'secret': os.environ['PLAID_SECRET'].strip()})
    return PlaidApi(plaid.ApiClient(config))


def cipher():
    from cryptography.fernet import Fernet
    # Keep the key out of SQLite, source control and the frontend. Back up both files together.
    path = Path(os.getenv('BUDGETPLUS_DB') or Path(__file__).parents[1] / 'data' / 'budgetplus.sqlite3').with_suffix('.plaid-key')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as f:
            f.write(Fernet.generate_key())
        path.chmod(0o600)
    except FileExistsError:
        pass
    return Fernet(path.read_bytes())


def error_code(exc):
    try:
        return json.loads(getattr(exc, 'body', '') or '{}').get('error_code', '')
    except (ValueError, TypeError):
        return ''


def safe_error(exc):
    # Do not expose SDK bodies, URLs, tokens or credentials in API errors.
    code = error_code(exc)
    return {
        'ITEM_LOGIN_REQUIRED': 'This institution needs you to reconnect. Choose Repair connection.',
        'ITEM_LOCKED': 'Your institution temporarily locked this connection. Try again later.',
        'INVALID_CREDENTIALS': 'Plaid credentials were rejected. Check the client ID and secret for the selected environment.',
        'INVALID_API_KEYS': 'Plaid credentials were rejected. Check the client ID and secret for the selected environment.',
        'PRODUCT_NOT_READY': 'Your institution is still preparing transaction history. BudgetPlus will retry.',
        'INSTITUTION_DOWN': 'Your institution is temporarily unavailable. Try syncing again later.',
        'INSTITUTION_NOT_RESPONDING': 'Your institution is not responding. Try syncing again later.',
        'RATE_LIMIT_EXCEEDED': 'Plaid is temporarily limiting requests. Try syncing again later.',
    }.get(code, 'Plaid could not complete this request. Your saved data is unchanged; check Plaid setup or try again later.')


def call(api, method, model, **kwargs):
    # Current generated Python SDK models; only this boundary sees access tokens.
    from importlib import import_module
    module, name = model
    request = getattr(import_module('plaid.model.' + module), name)(**kwargs)
    return getattr(api, method)(request, _request_timeout=25).to_dict()


def link_token(item_id=None):
    api = client()
    from plaid.model.products import Products
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.link_token_transactions import LinkTokenTransactions
    with db.connect() as c:
        c.execute('INSERT OR IGNORE INTO plaid_metadata VALUES (?,?)', ('user_id', str(uuid4())))
        user_id = c.execute("SELECT value FROM plaid_metadata WHERE key='user_id'").fetchone()['value']
        item = c.execute('SELECT * FROM plaid_items WHERE item_id=? AND environment=?', (item_id, environment())).fetchone() if item_id else None
    kwargs = dict(client_name='BudgetPlus', language='en', country_codes=[CountryCode('US')],
                  user=LinkTokenCreateRequestUser(client_user_id=user_id))
    if item_id and not item: raise HTTPException(404, 'Connection not found in the selected Plaid environment.')
    try:
        if item_id:
            kwargs['access_token'] = cipher().decrypt(item['access_token'].encode()).decode()
        else:
            kwargs.update(products=[Products('transactions')], transactions=LinkTokenTransactions(days_requested=730))
        result = call(api, 'link_token_create', ('link_token_create_request', 'LinkTokenCreateRequest'), **kwargs)
        return dict(link_token=result['link_token'], expiration=result['expiration'], environment=environment(), updateMode=bool(item))
    except Exception as exc:
        raise HTTPException(502, safe_error(exc)) from None


def exchange(public_token):
    api = client()
    digest = hashlib.sha256(public_token.encode()).hexdigest()
    with sync_lock:
        with db.connect() as c:
            prior = c.execute('SELECT item_id FROM plaid_items WHERE exchange_hash=? AND environment=?', (digest, environment())).fetchone()
            if prior: return dict(itemId=prior['item_id'])
        try:
            encryption = cipher()
            result = call(api, 'item_public_token_exchange', ('item_public_token_exchange_request', 'ItemPublicTokenExchangeRequest'), public_token=public_token)
            token = encryption.encrypt(result['access_token'].encode()).decode()
            with db.connect() as c:
                c.execute('INSERT INTO plaid_items (item_id,environment,access_token,exchange_hash) VALUES (?,?,?,?) '
                          'ON CONFLICT(item_id) DO UPDATE SET access_token=excluded.access_token, exchange_hash=excluded.exchange_hash, error=NULL',
                          (result['item_id'], environment(), token, digest))
            return dict(itemId=result['item_id'])
        except Exception as exc:
            raise HTTPException(502, safe_error(exc)) from None


def normalize_account(raw, institution, item_id):
    balances = raw['balances']
    mask = raw.get('mask') or ''
    return dict(id='plaid-' + raw['account_id'], plaidAccountId=raw['account_id'], plaidItemId=item_id,
                name=raw['name'], institution=institution, type=raw['type'], subtype=raw.get('subtype'),
                current=balances.get('current'), available=balances.get('available'), creditLimit=balances.get('limit'),
                currency=balances.get('iso_currency_code') or balances.get('unofficial_currency_code'),
                last4=mask[-4:] if len(mask) >= 4 else None, source='plaid')


def normalize_transaction(raw, accounts, institution, item_id):
    pfc = raw.get('personal_finance_category') or {}
    primary, detailed = pfc.get('primary', ''), pfc.get('detailed', '')
    amount = float(raw['amount'])  # Plaid: positive outflow, negative inflow.
    if primary in ('TRANSFER_IN', 'TRANSFER_OUT') or detailed == 'LOAN_PAYMENTS_CREDIT_CARD_PAYMENT':
        kind = 'transfer'
    elif primary == 'INCOME' and amount < 0:
        kind = 'deposit'
    elif amount < 0:
        kind = 'refund'
    else:
        kind = 'purchase'
    category = {'INCOME': 'Income', 'FOOD_AND_DRINK': 'Dining', 'GENERAL_MERCHANDISE': 'Shopping',
                'ENTERTAINMENT': 'Entertainment', 'TRAVEL': 'Travel', 'TRANSPORTATION': 'Transportation',
                'MEDICAL': 'Medical', 'LOAN_PAYMENTS': 'Debt Payments', 'RENT_AND_UTILITIES': 'Utilities',
                'BANK_FEES': 'Bank Fees', 'PERSONAL_CARE': 'Personal Care', 'HOME_IMPROVEMENT': 'Home',
                'GENERAL_SERVICES': 'Services', 'GOVERNMENT_AND_NON_PROFIT': 'Government & Giving',
                'TRANSFER_IN': 'Transfers', 'TRANSFER_OUT': 'Transfers'}.get(primary, 'Uncategorized')
    if 'GROCERIES' in detailed: category = 'Groceries'
    if detailed in ('RENT_AND_UTILITIES_RENT', 'LOAN_PAYMENTS_MORTGAGE_PAYMENT'): category = 'Housing'
    if 'EDUCATION' in detailed: category = 'School'
    if kind == 'transfer': category = 'Transfers'
    account = accounts.get(raw['account_id'], {})
    return dict(id='plaid-' + raw['transaction_id'], transactionId=raw['transaction_id'], plaidItemId=item_id,
                plaidAccountId=raw['account_id'], date=str(raw['date']), merchant=raw.get('merchant_name') or raw.get('name') or 'Unknown merchant',
                amount=abs(amount), signedAmount=amount, type=kind, category=category, importedCategory=category,
                account=account.get('name', 'Connected account'), institution=institution,
                personalFinanceCategory=pfc, pending=bool(raw.get('pending')), pendingTransactionId=raw.get('pending_transaction_id'),
                currency=raw.get('iso_currency_code') or raw.get('unofficial_currency_code'),
                importance=importance(category), source='salary' if kind == 'deposit' and detailed == 'INCOME_WAGES' else 'plaid',
                provider='plaid', simulated=False)


def sync_item(api, item):
    token = cipher().decrypt(item['access_token'].encode()).decode()
    account_result = call(api, 'accounts_get', ('accounts_get_request', 'AccountsGetRequest'), access_token=token)
    institution_id = account_result.get('item', {}).get('institution_id') or item['institution_id']
    institution = item['institution']
    if institution_id and (not item['institution_id'] or institution == 'Connected institution'):
        from plaid.model.country_code import CountryCode
        result = call(api, 'institutions_get_by_id', ('institutions_get_by_id_request', 'InstitutionsGetByIdRequest'),
                      institution_id=institution_id, country_codes=[CountryCode('US')])
        institution = result['institution']['name']
    accounts = {r['account_id']: normalize_account(r, institution, item['item_id']) for r in account_result['accounts']}
    # A mutation invalidates the entire pagination run. Retry from the saved cursor.
    for attempt in range(3):
        cursor, changes, removed = item['cursor'], {}, set()
        try:
            for page in range(200):
                kwargs = dict(access_token=token, count=500)
                if cursor: kwargs['cursor'] = cursor
                result = call(api, 'transactions_sync', ('transactions_sync_request', 'TransactionsSyncRequest'), **kwargs)
                for raw in result['added'] + result['modified']:
                    transaction_id = raw['transaction_id']
                    changes[transaction_id] = normalize_transaction(raw, accounts, institution, item['item_id'])
                    removed.discard(transaction_id)
                    if raw.get('pending_transaction_id'):
                        removed.add(raw['pending_transaction_id'])
                        changes.pop(raw['pending_transaction_id'], None)
                for raw in result['removed']:
                    removed.add(raw['transaction_id'])
                    changes.pop(raw['transaction_id'], None)
                cursor = result['next_cursor']
                if not result['has_more']: break
            else:
                raise RuntimeError('Pagination limit reached')
            break
        except Exception as exc:
            if error_code(exc) != 'TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION' or attempt == 2: raise
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM plaid_accounts WHERE item_id=?', (item['item_id'],))
        c.executemany('INSERT INTO plaid_accounts VALUES (?,?,?)', [(key, item['item_id'], json.dumps(value)) for key, value in accounts.items()])
        c.executemany('DELETE FROM plaid_transactions WHERE transaction_id=? AND item_id=?', [(key, item['item_id']) for key in removed])
        c.executemany('INSERT INTO plaid_transactions VALUES (?,?,?) ON CONFLICT(transaction_id) DO UPDATE SET data=excluded.data',
                      [(key, item['item_id'], json.dumps(value)) for key, value in changes.items()])
        c.execute('UPDATE plaid_items SET cursor=?,institution_id=?,institution=?,history_status=?,last_sync=?,error=NULL WHERE item_id=?',
                  (cursor, institution_id, institution, result.get('transactions_update_status') or item['history_status'],
                   datetime.now(timezone.utc).isoformat(), item['item_id']))


def cached(c, table):
    return [json.loads(r['data']) for r in c.execute(f'SELECT p.data FROM {table} p JOIN plaid_items i ON p.item_id=i.item_id WHERE i.environment=?', (environment(),))]


def status(c):
    items = [dict(r) for r in c.execute('SELECT item_id,institution_id,institution,history_status,last_sync,error FROM plaid_items WHERE environment=?', (environment(),))]
    accounts, transactions = cached(c, 'plaid_accounts'), cached(c, 'plaid_transactions')
    supported = [a for a in accounts if a['currency'] == 'USD' and (a['type'] == 'credit' or a['subtype'] in ('checking', 'savings'))]
    ids = {a['plaidAccountId'] for a in supported}
    analyzed = [t for t in transactions if t['plaidAccountId'] in ids and t['currency'] == 'USD' and not t['pending']]
    return dict(configured=configured(), environment=environment(), items=items,
                institutions=len({i['institution_id'] or i['item_id'] for i in items}), accounts=len(accounts),
                transactions=len(transactions), monthsAnalyzed=len({t['date'][:7] for t in analyzed}),
                historyReady=bool(items) and all(i['history_status'] == 'HISTORICAL_UPDATE_COMPLETE' and not i['error'] for i in items),
                excludedAccounts=len(accounts)-len(supported), pendingTransactions=sum(t['pending'] for t in transactions))


def build_profile(c):
    current, _ = db.read(c)
    if current['mode'] == 'demo':
        current = dict(version=3, mode='personal', asOf=date.today().isoformat(), accounts=[], cards=[], goals=[], debts=[],
                       upcoming=[], recurring=[], transactions=[], buffer=0, guardrail='balanced', categoryImportance={}, balancesConfirmed=False, imports=[])
        c.execute('DELETE FROM authorizations')
        c.execute('DELETE FROM imports')
    accounts = cached(c, 'plaid_accounts')
    previous_cards = {a['id']: a for a in current['cards'] if a.get('source') == 'plaid'}
    previous_transactions = {t['id']: t for t in current['transactions'] if t.get('provider') == 'plaid'}
    current['accounts'] = [a for a in current['accounts'] if a.get('source') != 'plaid']
    current['cards'] = [a for a in current['cards'] if a.get('source') != 'plaid']
    ids, complete = set(), True
    for a in accounts:
        if a['currency'] != 'USD' or not (a['type'] == 'credit' or a['subtype'] in ('checking', 'savings')): continue
        ids.add(a['plaidAccountId'])
        if a['current'] is None: complete = False
        if a['type'] == 'credit':
            # Never invent a credit limit or rewards. Unknown-limit cards cannot route purchases.
            limit = max(0, a['creditLimit'] or 0)
            previous = previous_cards.get(a['id'], {})
            current['cards'].append({**a, 'balance': max(0, a['current'] or 0), 'limit': limit,
                                     'status': previous.get('status', 'active') if limit and a['current'] is not None else 'locked',
                                     'preferred': previous.get('preferred', False), 'rewards': previous.get('rewards', {'default': 0}), 'last4': a['last4'] or ''})
            if not limit: complete = False
        else:
            # Available cash is conservative; keep the institution's current/available values as well.
            balance = a['current']
            current['accounts'].append({**a, 'balance': balance or 0})
    current['transactions'] = [t for t in current['transactions'] if t.get('provider') != 'plaid'] + [
        t for t in cached(c, 'plaid_transactions') if t['plaidAccountId'] in ids and t['currency'] == 'USD']
    for tx in current['transactions']:
        previous = previous_transactions.get(tx['id'])
        if previous and previous.get('importedCategory') and previous['category'] != previous['importedCategory']:
            tx.update(category=previous['category'], importance=previous['importance'])
    current.update(mode='personal', asOf=date.today().isoformat())
    current['recurring'] = [r for r in current['recurring'] if not r.get('inferred')] + detect_recurring(current['transactions'], current['asOf'])
    summary = status(c)
    current['plaid'] = summary
    current['balancesConfirmed'] = complete and bool(ids) and summary['historyReady']
    db.save(c, current)


def sync(background=False):
    api = client()
    if not sync_lock.acquire(blocking=False): raise HTTPException(409, 'A Plaid sync is already running. Please wait.')
    try:
        with db.connect() as c:
            data, revision = db.read(c)
            if background and (data['mode'] != 'personal' or not data.get('plaid')): return
            items = c.execute('SELECT * FROM plaid_items WHERE environment=?', (environment(),)).fetchall()
        if not items: raise HTTPException(409, 'Connect an institution first.')
        success = False
        for item in items:
            try:
                sync_item(api, item)
                success = True
            except Exception as exc:
                with db.connect() as c:
                    c.execute('UPDATE plaid_items SET error=? WHERE item_id=?', (safe_error(exc), item['item_id']))
        with db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            _, latest_revision = db.read(c)
            if latest_revision != revision:
                raise HTTPException(409, 'Your workspace changed during sync. Saved bank history is safe; sync again to apply it.')
            if success: build_profile(c)
    finally:
        sync_lock.release()
