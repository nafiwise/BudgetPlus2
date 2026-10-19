import json
import os
import hmac
from pathlib import Path
from uuid import uuid4
from datetime import date
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from . import db
from .engines import analyze, route, apply_purchase
from .models import Authorization, Settings, CoachRequest, CategoryUpdate, RandomizeRequest
from .demo_generator import generate
from .importers import normalize, detect_recurring
from .providers import SimulatedProvider
from .coach import ask
from . import plaid_service
from .models import PlaidLinkRequest, PlaidExchangeRequest, PlaidSyncRequest
from . import lithic_service

load_dotenv(Path(__file__).parents[1] / '.env')


@asynccontextmanager
async def lifespan(app):
    db.init()
    yield


app = FastAPI(title='BudgetPlus decision engine', lifespan=lifespan)
app.include_router(lithic_service.router)
provider = SimulatedProvider()


@app.middleware('http')
async def protect_tunnel(request: Request, call_next):
    # The public tunnel reaches only signed ASA (and a non-sensitive health check).
    # Vite adds this local secret server-side; it is never sent to React.
    protected = lithic_service.enabled() or bool(os.getenv('PUBLIC_BACKEND_URL', '').strip())
    if protected and request.url.path not in ('/api/lithic/authorize', '/api/health'):
        supplied = request.headers.get('x-budgetplus-local', '')
        try: allowed = hmac.compare_digest(supplied, db.local_api_key())
        except OSError: allowed = False
        if not allowed: return JSONResponse(status_code=403, content={'detail': 'Use the local BudgetPlus app. This public endpoint accepts ASA callbacks only.'})
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def snapshot(c):
    if not c.in_transaction: c.execute('BEGIN')
    data, revision = db.read(c)
    if data['mode'] == 'personal': data['asOf'] = date.today().isoformat()
    data['lithicCard'] = lithic_service.card_info(c)
    return dict(data=data, analysis=analyze(data), revision=revision,
                decisions=(lithic_service.recent(c) + [json.loads(r['result']) for r in c.execute('SELECT result FROM authorizations ORDER BY rowid DESC LIMIT 10')])[:20])


@app.get('/api/health')
def health():
    return dict(status='ok', provider='simulated', geminiConfigured=bool(os.getenv('GEMINI_API_KEY', '').strip()), geminiModel=os.getenv('GEMINI_MODEL', '').strip() or 'gemini-flash-latest')


@app.get('/api/state')
def state():
    with db.connect() as c: return snapshot(c)


@app.put('/api/settings')
def settings(body: Settings):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        data, revision = db.read(c)
        if revision != body.revision: raise HTTPException(409, 'State changed on another device. Reload your settings and try again.')
        data.update(body.model_dump(mode='json', exclude={'revision'}))
        # Explicit user categories participate in routing, even without historical spending.
        db.save(c, data)
        return snapshot(c)


@app.post('/api/reset')
def reset():
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM authorizations')
        c.execute('DELETE FROM imports')
        db.save(c, db.demo())
        return snapshot(c)


@app.post('/api/randomize')
def randomize(body: RandomizeRequest):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current, revision = db.read(c)
        if current['mode'] != 'demo':
            raise HTTPException(409, 'Randomization is available only in Demo Mode. Your imported data was not changed.')
        if revision != body.revision:
            raise HTTPException(409, 'Your snapshot changed. Wait for it to refresh, then try again.')
        data = generate(current.get('demoScenario', {}).get('id'))
        # A genuine simulated authorization demonstrates the new scenario's routing.
        request_id = 'demo-' + str(uuid4())
        request = dict(cardToken='demo-card-001', merchant='Chipotle', amount=18.42, category='Dining', importance=None)
        tx = {k: v for k, v in request.items() if k != 'cardToken'}
        tx['id'] = request_id
        decision = provider.authorize(route(tx, data), request_id)
        decision.update(merchant=tx['merchant'], amount=tx['amount'], category=tx['category'])
        if decision['approved']:
            tx['importance'] = decision['importance']
            data = apply_purchase(data, tx, decision['cardId'])
        c.execute('DELETE FROM authorizations')
        c.execute('DELETE FROM imports')
        db.save(c, data)
        c.execute('INSERT INTO authorizations (id,request,result) VALUES (?,?,?)',
                  (request_id, json.dumps(request, sort_keys=True), json.dumps(decision)))
        return snapshot(c)


@app.put('/api/categories')
def categories(body: CategoryUpdate):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        data, revision = db.read(c)
        if revision != body.revision: raise HTTPException(409, 'State changed. Try again with the latest state.')
        if body.oldName:
            for row in data['transactions']:
                if row['category'] == body.oldName:
                    row.update(category=body.name, importance=body.importance)
            for row in data['upcoming'] + data['recurring']:
                if row['category'] == body.oldName: row['category'] = body.name
            # A renamed label preserves configured reward eligibility; merging keeps the destination rate.
            if body.oldName != body.name:
                data['categoryImportance'].pop(body.oldName, None)
                for card in data['cards']:
                    if body.oldName != 'default' and body.oldName in card['rewards']:
                        rate = card['rewards'].pop(body.oldName)
                        card['rewards'].setdefault(body.name, rate)
        data['categoryImportance'][body.name] = body.importance
        limits = data.setdefault('categoryLimits', {})
        if body.oldName and body.oldName != body.name:
            old_limit = limits.pop(body.oldName, None)
            if old_limit is not None: limits.setdefault(body.name, old_limit)
        if 'limit' in body.model_fields_set:
            if body.limit is None: limits.pop(body.name, None)
            else: limits[body.name] = body.limit
        db.save(c, data)
        return snapshot(c)


@app.post('/api/authorize')
def authorize(body: Authorization):
    if lithic_service.enabled():
        raise HTTPException(409, 'Lithic Sandbox is enabled. Use /api/lithic/simulate so the authorization passes through Lithic ASA.')
    if body.cardToken != 'demo-card-001': raise HTTPException(404, 'Unknown prototype card token.')
    request_id = body.requestId or str(uuid4())
    request = body.model_dump(exclude={'requestId'})
    canonical = json.dumps(request, sort_keys=True)
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        prior = c.execute('SELECT * FROM authorizations WHERE id=?', (request_id,)).fetchone()
        if prior:
            if prior['request'] != canonical: raise HTTPException(409, 'Request ID was already used for a different purchase.')
            return json.loads(prior['result'])
        data, _ = db.read(c)
        if data['mode'] == 'personal': data['asOf'] = date.today().isoformat()
        tx = {**request, 'id': request_id}
        tx.pop('cardToken')
        decision = provider.authorize(route(tx, data), request_id)
        decision.update(merchant=body.merchant, amount=body.amount, category=body.category)
        if decision['approved']:
            tx['importance'] = decision['importance']
            data = apply_purchase(data, tx, decision['cardId'])
        db.save(c, data)
        c.execute('INSERT INTO authorizations (id,request,result) VALUES (?,?,?)', (request_id, canonical, json.dumps(decision)))
        return decision


def import_data(content, filename, mapping, sign, date_format, account, mode):
    try:
        mapped = json.loads(mapping)
        if not isinstance(mapped, dict) or not all(isinstance(v, str) for v in mapped.values()): raise ValueError('Mapping must be a JSON object of column names.')
        rows, digest = normalize(content, Path(filename).suffix.lower(), mapped, sign, date_format, account)
    except (ValueError, KeyError, TypeError) as exc: raise HTTPException(422, str(exc)) from exc
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        data, _ = db.read(c)
        if c.execute('SELECT digest FROM imports WHERE digest=?', (digest,)).fetchone():
            raise HTTPException(409, 'This exact file has already been imported. No duplicate rows added.')
        if data['mode'] == 'demo' or mode == 'replace':
            data = dict(version=3, mode='personal', asOf=date.today().isoformat(), accounts=[], cards=[], goals=[], debts=[],
                        upcoming=[], recurring=[], transactions=[], buffer=0, guardrail='balanced', categoryImportance={}, balancesConfirmed=False, imports=[])
            c.execute('DELETE FROM imports')
            c.execute('DELETE FROM authorizations')
        else:
            # Additional exports may change inferred obligations; reconfirm snapshots.
            data['balancesConfirmed'] = False
        data['transactions'].extend(rows)
        data['asOf'] = date.today().isoformat()
        data['recurring'] = [r for r in data['recurring'] if not r.get('inferred')] + detect_recurring(data['transactions'], data['asOf'])
        data['imports'].append(dict(rows=len(rows), digest=digest))
        db.save(c, data)
        c.execute('INSERT INTO imports VALUES (?,?)', (digest, len(rows)))
        return {**snapshot(c), 'importedRows': len(rows), 'notice': 'Imported real history. Confirm current balances and obligations in Money. Overlapping exports can contain duplicate activity; append only non-overlapping files.'}


@app.post('/api/import')
async def upload(file: UploadFile = File(...), mapping: str = Form('{}'), sign: str = Form('negative_expenses'),
                 date_format: str = Form('MDY'), account: str = Form('Imported account'), mode: str = Form('replace')):
    if sign not in ('negative_expenses', 'positive_expenses') or date_format not in ('MDY', 'DMY') or mode not in ('replace', 'append'):
        raise HTTPException(422, 'Invalid import options.')
    content = await file.read(10_000_001)
    await file.close()
    if len(content) > 10_000_000: raise HTTPException(413, 'Maximum upload size is 10 MB.')
    return await run_in_threadpool(import_data, content, file.filename or '', mapping, sign, date_format, account[:100], mode)


@app.post('/api/coach')
def coach(body: CoachRequest):
    with db.connect() as c: current = snapshot(c)
    return {**ask(body.question, current['data'], current['analysis'], current['decisions']), 'contextRevision': current['revision'],
            'contextMode': 'MY DATA' if current['data']['mode'] == 'personal' else 'DEMO',
            'contextSource': 'Plaid ' + current['data']['plaid']['environment'] if current['data'].get('plaid') else 'Imported/manual' if current['data']['mode'] == 'personal' else 'Demo'}


@app.post('/api/plaid/link-token')
def plaid_link_token(body: PlaidLinkRequest = PlaidLinkRequest()):
    return plaid_service.link_token(body.itemId)


@app.post('/api/plaid/exchange-token')
def plaid_exchange_token(body: PlaidExchangeRequest):
    return plaid_service.exchange(body.public_token)


@app.post('/api/plaid/sync')
def plaid_sync(body: PlaidSyncRequest = PlaidSyncRequest()):
    plaid_service.sync(body.background)
    with db.connect() as c:
        return {**snapshot(c), 'plaidStatus': plaid_service.status(c)}


@app.get('/api/plaid/accounts')
def plaid_accounts():
    with db.connect() as c:
        return dict(accounts=plaid_service.cached(c, 'plaid_accounts'), environment=plaid_service.environment())


@app.get('/api/plaid/status')
def plaid_status():
    with db.connect() as c:
        return plaid_service.status(c)
