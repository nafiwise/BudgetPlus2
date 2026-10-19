import json
from datetime import date
from random import Random
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import db, coach
from app.demo_generator import generate, SCENARIOS
from app.engines import analyze, route
from app.models import Settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('BUDGETPLUS_DB', str(tmp_path / 'demo.sqlite3'))
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_scenarios_are_valid_and_reconcile(scenario):
    for seed in range(12):
        data = generate(scenario=scenario, rng=Random(seed), today=date(2026, 10, [1, 11, 31][seed % 3]))
        Settings(revision=1, **{k: data[k] for k in Settings.model_fields if k != 'revision'})
        analysis = analyze(data)
        cash = sum(a['balance'] for a in data['accounts'])
        deposits = sum(t['amount'] for t in data['transactions'] if t['type'] == 'deposit')
        paid = sum(t['amount'] for t in data['transactions'] if t['type'] in ('purchase','transfer'))
        assert data['demoScenario']['openingCash'] + deposits - paid == pytest.approx(cash, abs=.01)
        assert data['demoScenario']['openingCash'] >= 0
        assert all(0 <= c['balance'] <= c['limit'] for c in data['cards'])
        assert sum(g['protected'] for g in data['goals']) <= data['accounts'][1]['balance']
        assert 300 <= analysis['score']['value'] <= 850
        assert all(t['date'] <= data['asOf'] for t in data['transactions'])
        assert {'MUST PAY','FLEXIBLE','CAN WAIT'} <= {c['importance'] for c in analysis['budget']['categories']}
        assert any(c['importance']=='CAN WAIT' for c in analysis['budget']['categories'])
        decision = route(dict(category='Dining',amount=18.42), data)
        if scenario in ('tight','upcoming','high_credit'): assert not decision['approved']
        if scenario in ('comfortable','professional','student','overspending'): assert decision['approved']
        assert analysis['profile']['incomeType'] == ('variable' if scenario in ('tight','student') else 'fixed')


def test_scenario_variety_changes_score_and_profile():
    rows = {s: analyze(generate(scenario=s, rng=Random(5), today=date(2026,10,11))) for s in SCENARIOS}
    assert len({r['score']['value'] for r in rows.values()}) >= 5
    assert rows['comfortable']['score']['value'] > rows['overspending']['score']['value']
    assert rows['student']['profile']['cashPreservation']
    assert not rows['professional']['profile']['cashPreservation']
    assert 'School' in rows['student']['profile']['categories']
    assert 'Medical' in rows['upcoming']['profile']['categories']


def test_randomize_is_atomic_persistent_and_revision_checked(client):
    previous = client.get('/api/state').json()
    for _ in range(8):
        response = client.post('/api/randomize',json={'revision':previous['revision']})
        assert response.status_code == 200
        current = response.json()
        assert current['revision'] > previous['revision']
        assert current['data']['demoScenario']['id'] != previous['data'].get('demoScenario',{}).get('id')
        assert current['analysis'] == analyze(current['data'])
        assert len(current['decisions']) == 1
        decision = current['decisions'][0]
        assert decision['simulated'] and decision['merchant'] == 'Chipotle'
        posted = [t for t in current['data']['transactions'] if t.get('simulated')]
        assert len(posted) == int(decision['approved'])
        if posted:
            assert posted[0]['id'] == decision['authorizationId']
            assert current['analysis']['score']['value'] == decision['scoreAfter']
        assert client.get('/api/state').json() == current
        assert client.post('/api/randomize',json={'revision':previous['revision']}).status_code == 409
        previous = current
    reset = client.post('/api/reset').json()
    assert 'demoScenario' not in reset['data']
    assert reset['analysis']['score']['value'] == 756


def test_randomize_cannot_modify_imported_data(client):
    csv = b'date,merchant,amount,category\n2026-10-01,Rent,-900,Housing\n'
    result = client.post('/api/import',files={'file':('personal.csv',csv,'text/csv')})
    assert result.status_code == 200
    before = client.get('/api/state').json()
    assert before['data']['mode'] == 'personal'
    assert client.post('/api/randomize',json={'revision':before['revision']}).status_code == 409
    assert client.get('/api/state').json() == before


def test_coach_uses_current_context_without_consent_and_excludes_secrets(client, monkeypatch):
    captured = {}
    class FakeClient:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text='A real provider response would appear here.', response_id='test-id')
    monkeypatch.setenv('GEMINI_API_KEY','test-api-secret')
    monkeypatch.setattr(coach.genai,'Client',FakeClient)
    initial = client.get('/api/state').json()
    current = client.post('/api/randomize',json={'revision':initial['revision']}).json()
    with db.connect() as c:
        data, _ = db.read(c)
        data['accounts'][0]['password'] = 'never-send-this'
        data['cards'][0]['fullCardNumber'] = '4111111111111111'
        data['rawUploadedFile'] = 'raw-file-sentinel'
        db.save(c,data)
    result = client.post('/api/coach',json={'question':'Can I afford a laptop? password=hunter2 4111 1111 1111 1111 test-api-secret'})
    assert result.status_code == 200
    context = json.loads(captured['contents'])['financialContext']
    assert context['accounts'][0]['balance'] == current['data']['accounts'][0]['balance']
    assert context['score'] == current['analysis']['score']
    assert context['recentRoutingDecisions'][0]['selectedCard'] == current['decisions'][0]['selectedCard']
    assert all('availableCredit' in card for card in context['cards'])
    for forbidden in ('never-send-this','4111111111111111','4111 1111 1111 1111','test-api-secret','raw-file-sentinel','hunter2','last4'):
        assert forbidden not in captured['contents']
    assert result.json()['contextRevision'] == client.get('/api/state').json()['revision']
    assert 'stable salary' in captured['config'].system_instruction


def test_missing_key_is_short_and_does_not_modify_data(client):
    before = client.get('/api/state').json()
    response = client.post('/api/coach',json={'question':'What should I cut this week?'})
    assert response.status_code == 503
    assert response.json()['detail'] == "Gemini isn't connected yet."
    assert client.get('/api/state').json() == before
