import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import db, plaid_service as plaid
from app.coach import financial_context

real_client = plaid.client


def account(id='checking', type='depository', subtype='checking', current=2500, available=2400, limit=None, currency='USD'):
    return dict(account_id=id, name=id.title(), type=type, subtype=subtype, mask='1234',
                balances=dict(current=current, available=available, limit=limit, iso_currency_code=currency))


def transaction(id='tx-1', account_id='checking', amount=20, primary='FOOD_AND_DRINK', detailed='FOOD_AND_DRINK_RESTAURANT', **kwargs):
    return dict(transaction_id=id, account_id=account_id, amount=amount, date=date.today().isoformat(),
                merchant_name='Example cafe', name='Example', personal_finance_category=dict(primary=primary, detailed=detailed),
                pending=False, iso_currency_code='USD', **kwargs)


def page(added=None, modified=None, removed=None, cursor='cursor-1', more=False, status='HISTORICAL_UPDATE_COMPLETE'):
    return dict(added=added or [], modified=modified or [], removed=[{'transaction_id': x} for x in removed or []],
                next_cursor=cursor, has_more=more, transactions_update_status=status)


class PlaidError(Exception):
    def __init__(self, code):
        self.body = json.dumps(dict(error_code=code, access_token='access-secret-must-not-leak'))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('BUDGETPLUS_DB', str(tmp_path / 'plaid.sqlite3'))
    monkeypatch.setenv('PLAID_ENV', 'sandbox')
    monkeypatch.setenv('PLAID_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('PLAID_SECRET', 'test-secret')
    monkeypatch.setattr(plaid, 'client', lambda: object())
    responses = SimpleNamespace(accounts=[account(), account('credit', 'credit', 'credit card', 200, 1800, 2000)],
                                pages=[page([transaction()])], calls=[])
    def call(api, method, model, **kwargs):
        responses.calls.append((method, kwargs))
        if method == 'link_token_create': return dict(link_token='link-sandbox-example', expiration='2026-12-01')
        if method == 'item_public_token_exchange':
            suffix = kwargs['public_token'].split('-')[-1]
            return dict(item_id='item-' + suffix, access_token='access-secret-' + suffix)
        if method == 'accounts_get':
            return dict(accounts=responses.accounts, item=dict(institution_id='ins-' + kwargs['access_token'].split('-')[-1]))
        if method == 'institutions_get_by_id': return dict(institution=dict(name='Bank ' + kwargs['institution_id']))
        if method == 'transactions_sync':
            value = responses.pages.pop(0) if len(responses.pages) > 1 else responses.pages[0]
            if isinstance(value, Exception): raise value
            return value
        raise AssertionError(method)
    monkeypatch.setattr(plaid, 'call', call)
    with TestClient(app) as client:
        yield client, responses


def connect(client, suffix='one'):
    response = client.post('/api/plaid/exchange-token', json=dict(public_token='public-sandbox-' + suffix))
    assert response.status_code == 200, response.text
    return response


def test_link_requests_transactions_730_and_stable_user(setup):
    client, fake = setup
    for _ in range(2): assert client.post('/api/plaid/link-token').status_code == 200
    first, second = [x[1] for x in fake.calls]
    assert first['transactions'].days_requested == 730
    assert str(first['products'][0]) == 'transactions'
    assert first['user'].client_user_id == second['user'].client_user_id


def test_exchange_idempotent_encrypted_and_no_token_leaks(setup):
    client, fake = setup
    connect(client); connect(client)
    assert len([x for x in fake.calls if x[0] == 'item_public_token_exchange']) == 1
    with db.connect() as c:
        stored = c.execute('SELECT access_token FROM plaid_items').fetchone()[0]
    assert 'access-secret' not in stored
    assert plaid.cipher().decrypt(stored.encode()).decode() == 'access-secret-one'
    for path in ('/api/state', '/api/plaid/status', '/api/plaid/accounts'):
        assert 'access-secret' not in client.get(path).text
        assert 'test-secret' not in client.get(path).text


def test_profile_sync_idempotent_and_gemini_real_context(setup):
    client, fake = setup
    connect(client)
    for _ in range(2):
        response = client.post('/api/plaid/sync')
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['data']['mode'] == 'personal'
        assert len(result['data']['transactions']) == 1
        assert result['data']['balancesConfirmed']
        assert result['plaidStatus']['historyReady']
        assert result['analysis']['profile']['availableLiquidity'] == 2400
        assert result['analysis']['budget']['spent'] == 20
    context = financial_context(result['data'], result['analysis'], [])
    assert context['dataSource'] == 'Plaid sandbox'
    assert context['transactionCount'] == 1
    assert context['transactions'][0]['merchant'] == 'Example cafe'
    assert 'access-secret' not in json.dumps(context)
    assert result['data']['cards'][0]['rewards'] == {'default': 0}


def test_multiple_institutions_and_environment_isolation(setup, monkeypatch):
    client, fake = setup
    connect(client); client.post('/api/plaid/sync')
    connect(client, 'two')
    original = plaid.sync_item
    def per_item(api, item):
        suffix = item['item_id'].split('-')[-1]
        fake.accounts = [account(suffix)]
        fake.pages = [page([transaction('tx-' + suffix, account_id=suffix)])]
        original(api, item)
    monkeypatch.setattr(plaid, 'sync_item', per_item)
    result = client.post('/api/plaid/sync').json()
    assert result['plaidStatus']['institutions'] == 2
    assert len(result['data']['accounts']) == 2
    assert {t['id'] for t in result['data']['transactions']} == {'plaid-tx-one', 'plaid-tx-two'}
    monkeypatch.setenv('PLAID_ENV', 'production')
    assert client.get('/api/plaid/status').json()['accounts'] == 0
    assert client.get('/api/plaid/accounts').json()['accounts'] == []
    assert client.post('/api/plaid/sync').status_code == 409


def test_pagination_pending_to_posted_modified_and_removed(setup):
    client, fake = setup
    pending = transaction('pending'); pending['pending'] = True
    fake.pages = [page([pending], cursor='a', more=True), page([transaction('old')], cursor='b')]
    connect(client)
    first = client.post('/api/plaid/sync').json()
    assert len(first['data']['transactions']) == 2
    assert first['analysis']['budget']['spent'] == 20
    fake.pages = [page([transaction('posted', pending_transaction_id='pending')], [transaction('old', amount=30)], cursor='c')]
    second = client.post('/api/plaid/sync').json()
    assert {t['transactionId'] for t in second['data']['transactions']} == {'posted', 'old'}
    assert second['analysis']['budget']['spent'] == 50
    fake.pages = [page(removed=['old'], cursor='d')]
    final = client.post('/api/plaid/sync').json()
    assert len(final['data']['transactions']) == 1


def test_mutation_restarts_from_saved_cursor_and_failure_is_atomic(setup):
    client, fake = setup
    connect(client); client.post('/api/plaid/sync')
    fake.calls.clear()
    fake.pages = [page([transaction('discard')], cursor='partial', more=True),
                  PlaidError('TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION'), page([transaction('kept')], cursor='final')]
    result = client.post('/api/plaid/sync').json()
    assert {t['transactionId'] for t in result['data']['transactions']} == {'tx-1', 'kept'}
    cursors = [kw['cursor'] for method, kw in fake.calls if method == 'transactions_sync']
    assert cursors == ['cursor-1', 'partial', 'cursor-1']
    fake.pages = [page([transaction('discard-again')], cursor='bad', more=True), PlaidError('INSTITUTION_DOWN')]
    failed = client.post('/api/plaid/sync').json()
    assert failed['data'] == result['data']
    assert failed['plaidStatus']['items'][0]['error']
    assert 'access-secret' not in json.dumps(failed)
    with db.connect() as c:
        assert c.execute('SELECT cursor FROM plaid_items').fetchone()[0] == 'final'


def test_initial_empty_history_is_not_ready_and_can_retry(setup):
    client, fake = setup
    connect(client); fake.pages = [page(status='NOT_READY')]
    first = client.post('/api/plaid/sync').json()
    assert first['data']['mode'] == 'personal'
    assert not first['plaidStatus']['historyReady']
    assert first['analysis']['score']['provisional']
    fake.pages = [page([transaction()])]
    second = client.post('/api/plaid/sync').json()
    assert second['plaidStatus']['historyReady']
    assert second['plaidStatus']['transactions'] == 1


def test_demo_reset_keeps_connections_but_background_does_not_replace_demo(setup):
    client, fake = setup
    connect(client); client.post('/api/plaid/sync')
    reset = client.post('/api/reset').json()
    assert reset['data']['mode'] == 'demo'
    after = client.post('/api/plaid/sync', json={'background': True}).json()
    assert after['data'] == reset['data']
    assert client.get('/api/plaid/status').json()['institutions'] == 1
    assert client.post('/api/plaid/sync').json()['data']['mode'] == 'personal'


def test_pending_transfer_refund_income_mapping():
    accounts = {'checking': {'name': 'Checking'}}
    def normalize(**kw): return plaid.normalize_transaction(transaction(**kw), accounts, 'Bank', 'item')
    assert normalize(primary='TRANSFER_IN', amount=-500)['type'] == 'transfer'
    assert normalize(primary='LOAN_PAYMENTS', detailed='LOAN_PAYMENTS_CREDIT_CARD_PAYMENT')['type'] == 'transfer'
    assert normalize(amount=-10)['type'] == 'refund'
    assert normalize(primary='INCOME', detailed='INCOME_WAGES', amount=-2000)['source'] == 'salary'
    assert normalize(primary='INCOME', detailed='INCOME_OTHER_INCOME', amount=-100)['source'] == 'plaid'


def test_missing_balances_limits_and_non_usd_never_invent_money(setup):
    client, fake = setup
    fake.accounts = [account(current=None, available=None), account('card', 'credit', 'credit card', 100, None, None), account('eur', currency='EUR')]
    connect(client)
    result = client.post('/api/plaid/sync').json()
    assert result['analysis']['score']['provisional']
    assert result['data']['cards'][0]['limit'] == 0
    assert result['data']['cards'][0]['status'] == 'locked'
    assert result['plaidStatus']['excludedAccounts'] == 1
    assert len(result['data']['accounts']) == 1


def test_update_link_does_not_request_new_product_or_expose_access_token(setup):
    client, fake = setup
    connect(client)
    result = client.post('/api/plaid/link-token', json={'itemId': 'item-one'})
    assert result.status_code == 200
    assert result.json()['updateMode']
    assert 'access-secret' not in result.text
    request = fake.calls[-1][1]
    assert request['access_token'] == 'access-secret-one'
    assert 'products' not in request


def test_unconfigured_plaid_leaves_app_usable(setup, monkeypatch):
    client, fake = setup
    monkeypatch.delenv('PLAID_SECRET')
    monkeypatch.setattr(plaid, 'client', real_client)
    assert client.post('/api/plaid/link-token').status_code == 503
    assert not client.get('/api/plaid/status').json()['configured']
    assert client.get('/api/state').status_code == 200
    assert client.post('/api/randomize', json={'revision': client.get('/api/state').json()['revision']}).status_code == 200


def test_linked_settings_and_category_edits_survive_sync(setup):
    client, fake = setup
    connect(client)
    state = client.post('/api/plaid/sync').json()
    keys = ['accounts', 'cards', 'goals', 'debts', 'upcoming', 'recurring', 'buffer', 'guardrail', 'balancesConfirmed', 'categoryImportance']
    settings = {k: state['data'][k] for k in keys}
    settings['cards'][0]['rewards'] = {'default': 1.5}
    settings['cards'][0]['preferred'] = True
    result = client.put('/api/settings', json={**settings, 'revision': state['revision']})
    assert result.status_code == 200, result.text
    result = client.put('/api/categories', json=dict(revision=result.json()['revision'], oldName='Dining', name='My cafes', importance='CAN WAIT'))
    assert result.status_code == 200
    final = client.post('/api/plaid/sync').json()['data']
    assert final['transactions'][0]['category'] == 'My cafes'
    assert final['cards'][0]['rewards'] == {'default': 1.5}
    assert final['cards'][0]['preferred']


def test_first_sync_failure_preserves_demo_and_recovers(setup):
    client, fake = setup
    before = client.get('/api/state').json()['data']
    connect(client)
    fake.pages = [PlaidError('PRODUCT_NOT_READY')]
    result = client.post('/api/plaid/sync').json()
    assert result['data'] == before
    assert not result['plaidStatus']['historyReady']
    fake.pages = [page([transaction()])]
    assert client.post('/api/plaid/sync').json()['data']['mode'] == 'personal'


def test_coach_endpoint_reports_actual_context_and_does_not_change_math(setup, monkeypatch):
    client, fake = setup
    connect(client)
    state = client.post('/api/plaid/sync').json()
    from app import main
    captured = {}
    def ask(question, data, analysis, decisions):
        captured.update(financial_context(data, analysis, decisions))
        return dict(answer='Interpretation', provider='Google Gemini', contextTransactions=len(data['transactions']))
    monkeypatch.setattr(main, 'ask', ask)
    result = client.post('/api/coach', json={'question': 'Analyze my spending'}).json()
    assert result['contextMode'] == 'MY DATA'
    assert result['contextSource'] == 'Plaid sandbox'
    assert result['contextRevision'] == state['revision']
    assert captured['transactions'][0]['merchant'] == 'Example cafe'
    assert client.get('/api/state').json()['analysis'] == state['analysis']
