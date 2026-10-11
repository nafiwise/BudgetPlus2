"""Synthetic, signed ASA fixtures. No user database, credentials, tunnel or SDK network calls."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / 'backend'), str(root / 'backend/tests')]
from fastapi.testclient import TestClient
from test_lithic import FakeLithic, profile
from app.main import app
from app import db, lithic_service as lithic

with tempfile.TemporaryDirectory() as directory:
    os.environ.update(BUDGETPLUS_DB=str(Path(directory) / 'test.sqlite3'), LITHIC_API_KEY='fixture-only',
                      LITHIC_ENV='sandbox', PUBLIC_BACKEND_URL='https://budgetplus-test.example')
    fake = FakeLithic()
    with patch.object(lithic, 'client', lambda: fake), patch.object(lithic, 'write_call', lambda method, **kwargs: method(**kwargs)):
        with TestClient(app) as http:
            http.headers['x-budgetplus-local'] = db.local_api_key()
            fake.http = http
            profile(categoryLimits={'Dining': 50}, plaid={'environment': 'production', 'historyReady': True})
            result = {'before': http.get('/api/state').json(), 'initialStatus': http.get('/api/lithic/status').json()}
            result['created'] = http.post('/api/lithic/create-card').json()
            result['afterCreate'] = http.get('/api/state').json()
            result['readyStatus'] = http.post('/api/lithic/responder/enroll').json()
            result['approved'] = http.post('/api/lithic/simulate', json=dict(merchant='Chipotle', amount=10, category='Dining', requestId='browser-approved')).json()
            result['afterApprove'] = http.get('/api/state').json()
            result['limited'] = http.put('/api/categories', json=dict(revision=result['afterApprove']['revision'], oldName='Dining', name='Dining', importance='FLEXIBLE', limit=15)).json()
            result['declined'] = http.post('/api/lithic/simulate', json=dict(merchant='Chipotle', amount=10, category='Dining', requestId='browser-declined')).json()
            result['afterDecline'] = http.get('/api/state').json()
            (root / '.verification/lithic-fixtures.json').write_text(json.dumps(result), encoding='utf-8')
print('Synthetic Lithic fixtures generated; no live service called.')
