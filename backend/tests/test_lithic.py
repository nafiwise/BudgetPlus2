import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from standardwebhooks import Webhook

from app.main import app
from app import db, lithic_service as lithic, plaid_service
from app.engines import analyze

CARD = 'a83d3bb0-1df3-4f5a-8875-a097c60258c4'
PAN = '4111111111111111'
SECRET = 'whsec_' + base64.b64encode(b'x' * 32).decode()


def payload(amount=2000, token=None, card=CARD, **updates):
    return dict(event_type='card_authorization.approval_request', token=token or str(uuid4()),
                card=dict(token=card, state='OPEN', last_four='1111', type='VIRTUAL'),
                merchant=dict(descriptor='Test Restaurant', mcc='5812', acceptor_id='merchant-123', city='New York', state='NY', country='USA'),
                amounts=dict(cardholder=dict(amount=amount, currency='USD'), merchant=dict(amount=amount, currency='USD')),
                created=datetime.now(timezone.utc).isoformat(), network='MASTERCARD', status='AUTHORIZATION',
                pos=dict(entry_mode=dict(pan='MANUAL', card='NOT_PRESENT'), terminal=dict(type='PHONE')), **updates)


def signed(body, age=0):
    raw = json.dumps(body).encode()
    timestamp = datetime.fromtimestamp(time.time() - age, tz=timezone.utc)
    webhook_id = 'msg_' + uuid4().hex
    signature = Webhook(SECRET).sign(webhook_id, timestamp, raw.decode())
    return raw, {'webhook-id': webhook_id, 'webhook-timestamp': str(int(timestamp.timestamp())), 'webhook-signature': signature}


def send(client, body, **kw):
    raw, headers = signed(body, **kw)
    return client.post('/api/lithic/authorize', content=raw, headers=headers)


def profile(**updates):
    d = db.demo()
    d.update(mode='personal', asOf=date.today().isoformat(), transactions=[], cards=[], recurring=[], upcoming=[], goals=[], debts=[],
             accounts=[dict(id='checking', name='Checking', institution='Bank', balance=1000)], buffer=100,
             balancesConfirmed=True, categoryImportance={'Dining': 'FLEXIBLE'}, categoryLimits={'Dining': 100}, guardrail='balanced')
    d.update(updates)
    with db.connect() as c: db.save(c, d)
    return d


class FakeLithic:
    def __init__(self):
        self.card = SimpleNamespace(token=CARD, last_four='1111', state='OPEN', type='VIRTUAL', created=datetime.now(timezone.utc), pan=PAN, cvv='123')
        self.enrolled_url = None
        self.create_calls = []
        self.enroll_calls = []
        self.simulate_calls = []
        self.network = {}
        self.http = None
        self.fail = False
        self.cards = SimpleNamespace(create=self.create, retrieve=lambda token: self.card, update=self.update)
        self.responder_endpoints = SimpleNamespace(check_status=self.check_status, create=self.enroll)
        self.auth_stream_enrollment = SimpleNamespace(retrieve_secret=lambda: SimpleNamespace(secret=SECRET))
        self.transactions = SimpleNamespace(simulate_authorization=self.simulate, retrieve=lambda token: self.network[token])

    def __enter__(self): return self
    def __exit__(self, *args): pass

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.card

    def update(self, card_token, state):
        assert card_token == CARD
        self.card.state = state
        return self.card

    def check_status(self, type):
        assert type == 'AUTH_STREAM_ACCESS'
        return SimpleNamespace(enrolled=bool(self.enrolled_url), url=self.enrolled_url)

    def enroll(self, **kwargs):
        self.enroll_calls.append(kwargs)
        self.enrolled_url = kwargs['url']

    def simulate(self, **kwargs):
        self.simulate_calls.append(kwargs)
        if self.fail: raise RuntimeError('secret-key / PAN ' + PAN)
        assert kwargs['pan'] == PAN
        p = payload(kwargs['amount'])
        p['merchant'].update(descriptor=kwargs['descriptor'], mcc=kwargs['mcc'], acceptor_id=kwargs['merchant_acceptor_id'])
        response = send(self.http, p)
        assert response.status_code == 200
        approved = response.json()['result'] == 'APPROVED'
        self.network[p['token']] = SimpleNamespace(token=p['token'], result='APPROVED' if approved else 'DECLINED',
                status='PENDING' if approved else 'DECLINED', card_token=CARD, amount=kwargs['amount'])
        return SimpleNamespace(token=p['token'])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('BUDGETPLUS_DB', str(tmp_path / 'lithic.sqlite3'))
    monkeypatch.setenv('LITHIC_API_KEY', 'test-secret-key')
    monkeypatch.setenv('LITHIC_ENV', 'sandbox')
    monkeypatch.setenv('PUBLIC_BACKEND_URL', 'https://budgetplus-test.example')
    monkeypatch.delenv('LITHIC_CARD_PROGRAM_TOKEN', raising=False)
    fake = FakeLithic()
    monkeypatch.setattr(lithic, 'client', lambda: fake)
    monkeypatch.setattr(lithic, 'write_call', lambda method, **kwargs: method(**kwargs))
    with TestClient(app) as http:
        fake.http = http
        http.headers['x-budgetplus-local'] = db.local_api_key()
        assert http.post('/api/lithic/create-card').status_code == 200
        assert http.post('/api/lithic/responder/enroll').status_code == 200
        profile()
        yield http, fake


def test_allowed_purchase_updates_existing_category_and_holds_without_funding_card(setup):
    http, _ = setup
    before = http.get('/api/state').json()
    response = send(http, payload())
    assert response.status_code == 200, response.text
    assert response.json()['result'] == 'APPROVED'
    after = http.get('/api/state').json()
    assert after['analysis']['budget']['categories'][0]['remaining'] == 80
    assert after['analysis']['budget']['authorizationHolds'] == 20
    assert after['analysis']['budget']['safeToSpend'] == before['analysis']['budget']['safeToSpend'] - 20
    assert after['data']['accounts'] == before['data']['accounts']
    assert after['data']['cards'] == []
    assert after['data']['transactions'][0]['provider'] == 'lithic'
    assert after['decisions'][0]['asaVerified']


def test_category_limit_declines_without_spending(setup):
    http, _ = setup
    profile(categoryLimits={'Dining': 5})
    before = http.get('/api/state').json()
    response = send(http, payload())
    assert response.json()['result'] == 'VELOCITY_EXCEEDED'
    after = http.get('/api/state').json()
    assert after['data'] == before['data']
    assert after['analysis'] == before['analysis']
    assert after['decisions'][0]['decision_type'] == 'DECLINE'
    assert after['decisions'][0]['remaining_after_purchase'] == 5
    assert after['decisions'][0]['score_impact'] == 0


def test_duplicate_authorizations_and_concurrent_limits(setup):
    http, _ = setup
    p = payload(7000)
    with ThreadPoolExecutor(max_workers=3) as pool:
        same = list(pool.map(lambda _: send(http, p).json(), range(3)))
    assert all(r == same[0] for r in same)
    assert same[0]['result'] == 'APPROVED'
    assert send(http, payload(7000)).json()['result'] == 'VELOCITY_EXCEEDED'
    state = http.get('/api/state').json()
    assert len(state['data']['transactions']) == 1
    assert state['analysis']['budget']['authorizationHolds'] == 70
    altered = payload(9000, token=p['token'])
    assert send(http, altered).json()['result'] == 'UNAUTHORIZED_MERCHANT'


def test_asa_uses_cached_plaid_context_without_plaid_or_gemini_calls(setup, monkeypatch):
    http, _ = setup
    def forbidden(*args, **kwargs): raise AssertionError('Network call inside ASA')
    monkeypatch.setattr(plaid_service, 'client', forbidden)
    from app import main
    monkeypatch.setattr(main, 'ask', forbidden)
    profile(accounts=[dict(id='plaid-checking', name='Real checking', source='plaid', balance=400, available=105)],
            plaid={'environment': 'production'}, buffer=100)
    result = send(http, payload(1000))
    assert result.json()['result'] == 'INSUFFICIENT_FUNDS'
    assert http.get('/api/state').json()['decisions'][0]['contextMode'] == 'personal'
    profile(accounts=[dict(id='plaid-checking', name='Real checking', source='plaid', balance=400, available=300)], plaid={'environment': 'production'})
    assert send(http, payload(1000)).json()['result'] == 'APPROVED'


def test_signatures_missing_invalid_expired_and_sensitive_data_not_persisted(setup):
    http, _ = setup
    p = payload()
    assert http.post('/api/lithic/authorize', json=p).status_code == 401
    assert send(http, p, age=600).status_code == 401
    raw, headers = signed(p)
    assert http.post('/api/lithic/authorize', content=raw.replace(b'Test Restaurant', b'Bad Restaurant'), headers=headers).status_code == 401
    p['card'].update(pan=PAN, cvv='123')
    p['pos']['pin'] = '1234'
    assert send(http, p).json()['result'] == 'APPROVED'
    with db.connect() as c:
        stored = c.execute('SELECT request,result FROM lithic_authorizations').fetchone()
        assert PAN not in ''.join(stored)
        assert 'cvv' not in ''.join(stored)
        assert 'pin' not in ''.join(stored)
        assert SECRET not in c.execute("SELECT value FROM lithic_config WHERE key='asa_secret'").fetchone()[0]


def test_card_creation_enrollment_idempotent_safe_projection_and_controls(setup):
    http, fake = setup
    card = http.post('/api/lithic/create-card').json()['card']
    assert set(card) == {'token', 'last_four', 'state', 'type', 'network', 'created'}
    assert card['network'] == 'MASTERCARD'
    assert len(fake.create_calls) == 1
    assert fake.create_calls[0]['card_program_token'] == lithic.MASTERCARD_SANDBOX_PROGRAM
    assert fake.create_calls[0]['type'] == 'VIRTUAL'
    assert fake.create_calls[0]['extra_headers']['Idempotency-Key']
    assert http.post('/api/lithic/responder/enroll').status_code == 200
    assert len(fake.enroll_calls) == 1
    assert http.get('/api/lithic/responder/status').json()['signatureReady']
    assert http.post('/api/lithic/card/pause').json()['card']['state'] == 'PAUSED'
    assert send(http, payload()).json()['result'] == 'CARD_PAUSED'
    assert http.post('/api/lithic/card/unpause').json()['card']['state'] == 'OPEN'


def test_simulation_travels_provider_callback_and_final_result_retry_is_safe(setup):
    http, fake = setup
    request = dict(merchant='Test Restaurant', amount=10, category='Dining', requestId='simulation-0001')
    result = http.post('/api/lithic/simulate', json=request)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body['approved'] and body['asaVerified'] and body['networkResult'] == 'APPROVED'
    assert body['provider'] == 'Lithic Sandbox'
    assert len(fake.simulate_calls) == 1
    assert fake.simulate_calls[0]['amount'] == 1000
    assert http.post('/api/lithic/simulate', json=request).json() == body
    assert len(fake.simulate_calls) == 1
    assert len(http.get('/api/state').json()['data']['transactions']) == 1
    assert PAN not in result.text and SECRET not in result.text
    assert http.post('/api/authorize', json=dict(cardToken='demo-card-001', merchant='Test', amount=10, category='Dining')).status_code == 409


def test_lithic_unavailable_no_profile_damage_and_no_unsafe_resimulation(setup):
    http, fake = setup
    before = http.get('/api/state').json()
    fake.fail = True
    request = dict(merchant='Test Restaurant', amount=10, category='Dining', requestId='simulation-failure')
    response = http.post('/api/lithic/simulate', json=request)
    assert response.status_code == 502
    assert PAN not in response.text and 'secret-key' not in response.text
    assert http.get('/api/state').json() == before
    assert http.get('/api/plaid/status').status_code == 200
    assert http.post('/api/lithic/simulate', json=request).status_code == 409
    assert len(fake.simulate_calls) == 1


def test_tunnel_exposes_only_asa_and_health(setup):
    http, _ = setup
    for path in ('/api/state', '/api/plaid/accounts', '/api/lithic/status', '/docs', '/openapi.json'):
        assert http.get(path, headers={'x-budgetplus-local': ''}).status_code == 403
    assert http.post('/api/lithic/create-card', headers={'x-budgetplus-local': ''}).status_code == 403
    assert http.get('/api/health', headers={'x-budgetplus-local': ''}).status_code == 200
    raw, headers = signed(payload())
    assert http.post('/api/lithic/authorize', content=raw, headers={**headers, 'x-budgetplus-local': ''}).status_code == 200


def test_hold_adjustment_unknown_currency_and_nonpurchase_fail_closed(setup):
    http, _ = setup
    p = payload(1000)
    p['amounts']['hold'] = dict(amount=1500, currency='USD')
    assert send(http, p).json()['result'] == 'APPROVED'
    assert http.get('/api/state').json()['analysis']['budget']['authorizationHolds'] == 15
    p = payload(); p['amounts']['cardholder']['currency'] = 'EUR'
    assert send(http, p).json()['result'] == 'UNAUTHORIZED_MERCHANT'
    p = payload(); p['status'] = 'FINANCIAL_AUTHORIZATION'
    assert send(http, p).json()['result'] == 'UNAUTHORIZED_MERCHANT'


def test_final_network_decline_releases_local_hold(setup):
    http, fake = setup
    body = http.post('/api/lithic/simulate', json=dict(merchant='Test Restaurant', amount=10, category='Dining', requestId='network-decline')).json()
    token = body['authorizationId']
    fake.network[token].status = 'DECLINED'; fake.network[token].result = 'DECLINED'
    result = http.get('/api/lithic/authorization/' + token).json()
    assert not result['approved'] and result['budgetplusApproved']
    assert http.get('/api/state').json()['analysis']['budget']['authorizationHolds'] == 0
    assert http.get('/api/state').json()['data']['transactions'] == []


def test_category_limit_route_and_sandbox_only(setup, monkeypatch):
    http, _ = setup
    revision = http.get('/api/state').json()['revision']
    result = http.put('/api/categories', json=dict(revision=revision, oldName='Dining', name='Dining', importance='FLEXIBLE', limit=5))
    assert result.status_code == 200
    assert send(http, payload()).json()['result'] == 'VELOCITY_EXCEEDED'
    monkeypatch.setenv('LITHIC_ENV', 'production')
    assert http.post('/api/lithic/create-card').status_code == 503
    assert send(http, payload()).status_code == 503


def test_asa_timing_is_local_and_fast(setup):
    http, _ = setup
    started = time.perf_counter()
    assert send(http, payload()).status_code == 200
    assert time.perf_counter() - started < 2.5


def test_history_sized_profile_remains_fast_and_decline_does_not_call_provider(setup, monkeypatch):
    http, _ = setup
    d = profile()
    d['transactions'] = [dict(id=f'history-{i}', merchant='Historical Store', amount=1, type='purchase',
                              category='Shopping', account='Checking', date='2026-01-01', simulated=False) for i in range(10000)]
    with db.connect() as c: db.save(c, d)
    def forbidden(): raise AssertionError('ASA must not call Lithic SDK')
    monkeypatch.setattr(lithic, 'client', forbidden)
    started = time.perf_counter()
    assert send(http, payload()).json()['result'] == 'APPROVED'
    assert time.perf_counter() - started < 2.5


def test_approved_hold_and_limits_survive_plaid_profile_rebuild(setup):
    http, _ = setup
    assert send(http, payload()).json()['result'] == 'APPROVED'
    with db.connect() as c:
        plaid_service.build_profile(c)
        data, _ = db.read(c)
    assert data['categoryLimits']['Dining'] == 100
    assert analyze(data)['budget']['authorizationHolds'] == 20
