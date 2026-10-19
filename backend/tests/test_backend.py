import io
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from app.main import app
from app import db
from app.engines import analyze, route, apply_purchase
from app.importers import normalize


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('BUDGETPLUS_DB', str(tmp_path / 'test.sqlite3'))
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with TestClient(app) as client:
        yield client


def tx(**changes):
    return dict(cardToken='demo-card-001', merchant='Chipotle', amount=18.42, category='Dining', requestId='test-purchase-001', **changes)


def settings(state):
    keys = ['accounts','cards','goals','debts','upcoming','recurring','buffer','guardrail','balancesConfirmed','categoryImportance']
    return {**{k: state['data'][k] for k in keys}, 'revision':state['revision']}


CSV = b'date,merchant,amount,category,account,transaction type\n2026-08-01,Rent,-900,Housing,Checking,purchase\n2026-09-01,Rent,-900,Housing,Checking,purchase\n2026-09-02,Payroll,2400,Income,Checking,salary\n2026-09-03,Chipotle,-18.42,Dining,Checking,purchase\n'


def test_existing_engine_parity():
    data = db.demo()
    before = analyze(data)
    assert before['budget']['safeToSpend'] == 460.03
    assert before['score']['value'] == 756
    purchase = dict(id='test', merchant='Chipotle', amount=18.42, category='Dining')
    result = route(purchase, data)
    assert result['selectedCard'] == 'Amex Gold'
    assert result['estimatedReward'] == .74
    assert result['financialWarning']
    after = analyze(apply_purchase(data, purchase, result['cardId']))
    assert after['budget']['safeToSpend'] == 441.61
    assert after['score']['value'] == 752
    data['guardrail'] = 'strict'
    assert not route(purchase, data)['approved']


def test_atomic_retry_and_persistence(client):
    initial = client.get('/api/state').json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post('/api/authorize', json=tx()).json(), range(4)))
    assert all(r == results[0] for r in results)
    assert results[0]['approved'] and results[0]['simulated'] and not results[0]['settled']
    after = client.get('/api/state').json()
    assert len(after['data']['transactions']) == len(initial['data']['transactions'])+1
    assert after['data']['cards'][0]['balance'] == 358.42
    assert after['data']['accounts'] == initial['data']['accounts']
    db.init()
    assert client.get('/api/state').json()['data'] == after['data']
    changed = tx(); changed['amount'] = 12
    assert client.post('/api/authorize',json=changed).status_code == 409


def test_distinct_concurrent_purchases_do_not_overspend(client):
    def purchase(i):
        request = tx(); request.update(amount=250, requestId=f'parallel-{i}')
        return client.post('/api/authorize',json=request).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(purchase, range(2)))
    assert sum(r['approved'] for r in results) == 1


@pytest.mark.parametrize('amount',[0,-1,1.001,1000001])
def test_invalid_amounts(client, amount):
    request = tx(); request['amount'] = amount
    assert client.post('/api/authorize',json=request).status_code == 422


def test_blocked_purchase_leaves_balances(client):
    before = client.get('/api/state').json()
    request = tx(); request['amount'] = 500
    assert client.post('/api/authorize',json=request).json()['status'] == 'blocked'
    after = client.get('/api/state').json()
    assert after['data'] == before['data']
    assert len(after['decisions']) == 1


def test_import_replaces_demo_and_regenerates(client):
    response = client.post('/api/import',files={'file':('mine.csv',CSV,'text/csv')})
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['data']['mode'] == 'personal'
    assert len(state['data']['transactions']) == 4
    assert state['data']['accounts'] == state['data']['cards'] == state['data']['goals'] == state['data']['debts'] == []
    assert state['data']['recurring'][0]['merchant'] == 'Rent'
    assert state['analysis']['score']['provisional']
    assert not client.post('/api/authorize',json=tx()).json()['approved']
    assert client.post('/api/import',files={'file':('mine.csv',CSV,'text/csv')}).status_code == 409
    assert client.post('/api/reset').json()['data']['mode'] == 'demo'


def test_invalid_import_is_all_or_nothing(client):
    before = client.get('/api/state').json()
    invalid = CSV + b'bad date,Bad,2,Dining,Cash,purchase\n'
    response = client.post('/api/import',files={'file':('bad.csv',invalid)})
    assert response.status_code == 422
    assert 'Row 6' in response.json()['detail']
    assert client.get('/api/state').json() == before


def test_xlsx_mapping_sign_dates_and_duplicate_rows(client):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['When','Shop','Value'])
    sheet.append(['25/09/2026','Market',20])
    sheet.append(['25/09/2026','Market',20])
    file = io.BytesIO(); workbook.save(file)
    response = client.post('/api/import',files={'file':('mine.xlsx',file.getvalue())},
                           data={'mapping':json.dumps({'date':'When','merchant':'Shop','amount':'Value'}),'date_format':'DMY','sign':'positive_expenses'})
    assert response.status_code == 200, response.text
    rows = response.json()['data']['transactions']
    assert len(rows) == 2 and rows[0]['id'] != rows[1]['id']
    assert rows[0]['date'] == '2026-09-25' and rows[0]['type'] == 'purchase'


def test_debit_credit_and_transfer():
    file = b'date,description,debit,credit,type\n2026-10-01,Market,12,,\n2026-10-02,Pay,,100,income\n2026-10-03,Card payment,40,,transfer\n'
    rows, _ = normalize(file,'.csv',{},'negative_expenses','MDY','Checking')
    assert [r['type'] for r in rows] == ['purchase','deposit','transfer']


def test_settings_conflict_and_personal_purchase(client):
    state = client.post('/api/import',files={'file':('mine.csv',CSV)}).json()
    body = settings(state)
    body['accounts'] = [dict(id='cash',name='Cash',balance=6000)]
    body['cards'] = [dict(id='card',name='My card',last4='1234',balance=0,limit=5000,rewards={'default':1,'Dining':4})]
    body['balancesConfirmed'] = True
    assert client.put('/api/settings',json=body).status_code == 200
    assert client.put('/api/settings',json=body).status_code == 409
    result = client.post('/api/authorize',json=tx()).json()
    assert result['approved'] and result['selectedCard'] == 'My card'


def test_category_rename_and_importance(client):
    state = client.get('/api/state').json()
    response = client.put('/api/categories',json=dict(revision=state['revision'],oldName='Dining',name='Eating out',importance='CAN WAIT'))
    assert response.status_code == 200
    state = response.json()
    assert not any(t['category'] == 'Dining' for t in state['data']['transactions'])
    assert state['data']['categoryImportance']['Eating out'] == 'CAN WAIT'
    assert state['data']['cards'][0]['rewards']['Eating out'] == 4


def test_credit_and_debt_guardrails():
    data = db.demo()
    purchase = dict(id='p',merchant='Chipotle',amount=18.42,category='Dining')
    data['cards'][0]['balance'] = 980
    data['accounts'][0]['balance'] += 640
    assert route(purchase,data)['selectedCard'] == 'Chase Freedom'
    for card in data['cards']: card['status'] = 'locked'
    assert not route(purchase,data)['approved']
    before = analyze(data)['budget']['safeToSpend']
    data['debts'][0]['monthlyPayment'] = 100
    assert analyze(data)['budget']['safeToSpend'] == before - 100


def test_coach_never_fakes_a_response(client):
    response = client.post('/api/coach',json={'question':'Help'})
    assert response.status_code == 503
    assert response.json()['detail'] == "Gemini isn't connected yet."


def test_coach_sdk_context_and_metadata(client, monkeypatch):
    from app import coach
    from types import SimpleNamespace
    captured = {}
    class FakeClient:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text='SDK test response', response_id='test-response')
    monkeypatch.setenv('GEMINI_API_KEY','test-secret')
    monkeypatch.setattr(coach.genai,'Client',FakeClient)
    response = client.post('/api/coach',json={'question':'Which card?'})
    assert response.status_code == 200
    assert response.json()['provider'] == 'Google Gemini'
    assert 'test-secret' not in captured['contents']
    context = json.loads(captured['contents'])['financialContext']
    assert context['cards'][0]['rewards']['Dining'] == 4
    assert 'last4' not in context['cards'][0]
    assert context['score']['value'] == 756


def test_provider_failure_is_not_a_fake_answer(client, monkeypatch):
    from app import coach
    def fail(**kwargs): raise RuntimeError('sensitive provider detail')
    monkeypatch.setenv('GEMINI_API_KEY','test-secret')
    monkeypatch.setattr(coach.genai,'Client',fail)
    response = client.post('/api/coach',json={'question':'Help'})
    assert response.status_code == 502
    assert 'sensitive' not in response.text
    assert response.json()['detail'] == "Gemini couldn't respond. Please try again."


def test_recurring_obligations_roll_forward():
    data = db.demo()
    data['asOf'] = '2026-12-10'
    budget = analyze(data)['budget']
    rent = next(r for r in budget['upcoming'] if r['id'] == 'rent')
    assert rent['date'] == '2027-01-01'
    assert budget['obligations'] >= 950


def test_invalid_workbook_and_token(client):
    assert client.post('/api/import',files={'file':('broken.xlsx',b'not-a-workbook')}).status_code == 422
    request = tx(); request['cardToken'] = 'unknown'
    assert client.post('/api/authorize',json=request).status_code == 404
