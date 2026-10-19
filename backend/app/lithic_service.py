"""Lithic Sandbox transport and signed ASA boundary; financial rules live in engines.py."""
import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from standardwebhooks import Webhook

from . import db
from .engines import analyze, apply_purchase, route
from .models import LithicSimulation

router = APIRouter(prefix='/api/lithic', tags=['Lithic Sandbox'])
setup_lock = Lock()
simulation_lock = Lock()
write_lock = Lock()
last_write = 0.0
# One configuration default, never duplicated in UI or individual API calls.
MASTERCARD_SANDBOX_PROGRAM = '00000000-0000-0000-2000-000000000000'
MCC_CATEGORIES = {'5812': 'Dining', '5814': 'Dining', '5813': 'Dining', '5411': 'Groceries',
                  '5541': 'Transportation', '5542': 'Transportation', '4121': 'Transportation',
                  '4111': 'Transportation', '4900': 'Utilities', '6513': 'Housing', '8211': 'School',
                  '8220': 'School', '8011': 'Medical', '5912': 'Medical', '5311': 'Shopping',
                  '5999': 'Shopping', '7922': 'Entertainment', '7999': 'Entertainment',
                  '4722': 'Travel', '7011': 'Travel', '4899': 'Subscriptions'}


def now():
    return datetime.now(timezone.utc).isoformat()


def enabled():
    return bool(os.getenv('LITHIC_API_KEY', '').strip())


def sandbox():
    if os.getenv('LITHIC_ENV', 'sandbox').strip().lower() != 'sandbox':
        raise HTTPException(503, 'Only Lithic Sandbox is supported. Set LITHIC_ENV=sandbox and restart.')


def client():
    sandbox()
    if not enabled(): raise HTTPException(503, 'Add your Lithic Sandbox API key to backend/.env and restart BudgetPlus.')
    from lithic import Lithic
    return Lithic(api_key=os.environ['LITHIC_API_KEY'].strip(), environment='sandbox', timeout=20, max_retries=0)


def provider_error(exc):
    # Never serialize SDK exceptions: request/response bodies can contain PANs or secrets.
    code = getattr(exc, 'status_code', None)
    if code in (401, 403): return HTTPException(502, 'Lithic rejected this operation. Check your Sandbox API key and card-issuing permissions.')
    if code == 429: return HTTPException(503, 'Lithic Sandbox is rate limiting requests. Wait a few seconds and retry.')
    return HTTPException(502, 'Lithic Sandbox is unavailable or rejected the request. Your financial profile is preserved. Check setup and retry.')


def write_call(method, **kwargs):
    # Sandbox permits one write per second. Never used by the ASA decision path.
    global last_write
    with write_lock:
        time.sleep(max(0, 1.1 - (time.monotonic() - last_write)))
        try: return method(**kwargs)
        finally: last_write = time.monotonic()


def cipher():
    path = db.database_path().with_suffix('.lithic-key')
    try:
        with path.open('xb') as f: f.write(Fernet.generate_key())
        path.chmod(0o600)
    except FileExistsError:
        pass
    return Fernet(path.read_bytes())


def config(c, key):
    row = c.execute('SELECT value FROM lithic_config WHERE key=?', (key,)).fetchone()
    return row['value'] if row else None


def save_config(c, key, value):
    c.execute('INSERT INTO lithic_config VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))


def card_info(c):
    row = c.execute('SELECT token,last_four,state,type,network,created FROM lithic_card WHERE id=1').fetchone()
    return dict(row) if row else None


def safe_card(card):
    # Explicit projection; never persist or return PAN, CVV, expiry or funding credentials.
    return dict(token=card.token, last_four=card.last_four, state=card.state, type=card.type,
                network='MASTERCARD', created=card.created.isoformat() if hasattr(card.created, 'isoformat') else str(card.created))


def save_card(c, card):
    c.execute('INSERT INTO lithic_card VALUES (1,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
              'token=excluded.token,last_four=excluded.last_four,state=excluded.state,type=excluded.type,network=excluded.network,created=excluded.created',
              tuple(card[k] for k in ('token', 'last_four', 'state', 'type', 'network', 'created')))


def asa_url():
    base = os.getenv('PUBLIC_BACKEND_URL', '').strip().rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise HTTPException(422, 'Set PUBLIC_BACKEND_URL to your tunnel HTTPS origin (no path), then restart BudgetPlus.')
    return base + '/api/lithic/authorize'


def local_status(c):
    latest = c.execute('SELECT received_at FROM lithic_authorizations ORDER BY received_at DESC LIMIT 1').fetchone()
    return dict(enabled=enabled(), environment=os.getenv('LITHIC_ENV', 'sandbox'), card=card_info(c),
                responder=json.loads(config(c, 'responder') or '{}'), signatureReady=bool(config(c, 'asa_secret')),
                lastVerifiedAuthorizationAt=latest['received_at'] if latest else None)


@router.get('/status')
def status():
    with db.connect() as c: return local_status(c)


@router.post('/create-card')
def create_card():
    sandbox()
    with setup_lock:
        with db.connect() as c:
            existing = card_info(c)
            if existing: return dict(card=existing, created=False)
            key = config(c, 'create_card_key') or str(uuid4())
            save_config(c, 'create_card_key', key)
        program = os.getenv('LITHIC_CARD_PROGRAM_TOKEN', MASTERCARD_SANDBOX_PROGRAM).strip()
        if program != MASTERCARD_SANDBOX_PROGRAM:
            raise HTTPException(422, 'Use the documented Mastercard Sandbox card program token for this milestone.')
        try:
            with client() as api:
                result = write_call(api.cards.create, type='VIRTUAL', state='OPEN', memo='BudgetPlus Sandbox',
                                    card_program_token=program, spend_limit=100_000_000, spend_limit_duration='TRANSACTION',
                                    extra_headers={'Idempotency-Key': key})
                safe = safe_card(result)
            with db.connect() as c: save_card(c, safe)
            return dict(card=safe, created=True)
        except HTTPException: raise
        except Exception as exc: raise provider_error(exc) from None


def responder_status(api):
    remote = api.responder_endpoints.check_status(type='AUTH_STREAM_ACCESS')
    return dict(enrolled=bool(remote.enrolled), url=remote.url, matches=bool(remote.enrolled) and remote.url == asa_url())


@router.post('/responder/enroll')
def enroll():
    url = asa_url()
    with setup_lock:
        try:
            with client() as api:
                remote = responder_status(api)
                if not remote['matches']:
                    write_call(api.responder_endpoints.create, type='AUTH_STREAM_ACCESS', url=url)
                    remote = responder_status(api)
                # This endpoint also enables the three signature headers in Sandbox.
                secret = api.auth_stream_enrollment.retrieve_secret().secret
                if not secret: raise RuntimeError('No ASA verification key')
                encrypted = cipher().encrypt(secret.encode()).decode()
            with db.connect() as c:
                save_config(c, 'asa_secret', encrypted)
                save_config(c, 'responder', json.dumps(remote))
                return {**local_status(c), 'notice': 'ASA enrolled. Signature headers can take a few minutes to activate; unsigned requests are rejected.'}
        except HTTPException: raise
        except Exception as exc: raise provider_error(exc) from None


@router.get('/responder/status')
def check_responder():
    try:
        with client() as api: remote = responder_status(api)
        with db.connect() as c:
            save_config(c, 'responder', json.dumps(remote))
            return local_status(c)
    except HTTPException: raise
    except Exception as exc: raise provider_error(exc) from None


def change_card(state):
    with setup_lock:
        with db.connect() as c: card = card_info(c)
        if not card: raise HTTPException(409, 'Create the BudgetPlus Sandbox card first.')
        try:
            with client() as api: safe = safe_card(write_call(api.cards.update, card_token=card['token'], state=state))
            with db.connect() as c: save_card(c, safe)
            return dict(card=safe)
        except HTTPException: raise
        except Exception as exc: raise provider_error(exc) from None


@router.post('/card/pause')
def pause_card():
    return change_card('PAUSED')


@router.post('/card/unpause')
def unpause_card():
    return change_card('OPEN')


def verify(payload, headers):
    sandbox()
    with db.connect(timeout=.25) as c: encrypted = config(c, 'asa_secret')
    if not encrypted: raise HTTPException(503, 'Enroll ASA before sending authorizations.')
    try:
        secret = cipher().decrypt(encrypted.encode()).decode()
        # Same implementation used by Lithic SDK webhooks.verify_signature: HMAC + timestamp tolerance.
        Webhook(secret).verify(payload, headers)
    except Exception:
        raise HTTPException(401, 'Invalid or expired Lithic signature.') from None


def clean_label(value, length=200):
    return re.sub(r'(?<!\d)\d{13,19}(?!\d)', '[redacted]', str(value or ''))[:length]


def normalize(payload):
    try:
        raw = json.loads(payload)
        if raw.get('event_type') != 'card_authorization.approval_request': raise ValueError()
        token, card_token = str(UUID(raw['token'])), str(UUID(raw['card']['token']))
        structured = raw.get('amounts') or {}
        base = structured.get('cardholder') or {}
        hold = structured.get('hold') or {}
        cents = base.get('amount', raw.get('authorization_amount', raw.get('amount')))
        currency = base.get('currency', raw.get('cardholder_currency'))
        if type(cents) is not int or cents < 0 or cents > 100_000_000: raise ValueError()
        requested = cents
        if hold:
            if type(hold.get('amount')) is not int or hold.get('currency') != currency: raise ValueError()
            cents = max(cents, hold['amount'])
        if cents > 100_000_000: raise ValueError()
        merchant = raw['merchant']
        timestamp = datetime.fromisoformat(raw['created'].replace('Z', '+00:00'))
        pos = raw.get('pos') or {}
        return dict(id='lithic-' + token, transactionToken=token, cardToken=card_token, amount=cents / 100,
                    requestedAmount=requested / 100, currency=currency, merchant=clean_label(merchant.get('descriptor') or 'Unknown merchant'),
                    mcc=clean_label(merchant.get('mcc'), 4), acceptorId=clean_label(merchant.get('acceptor_id'), 100),
                    timestamp=timestamp.isoformat(), network=clean_label(raw.get('network'), 20),
                    location={k: clean_label(merchant.get(k), 100) for k in ('city', 'state', 'country')},
                    pos={group: {k: clean_label((pos.get(group) or {}).get(k), 60) for k in keys} for group, keys in
                         [('entry_mode', ('card', 'cardholder', 'pan')), ('terminal', ('type', 'attended', 'on_premise'))]},
                    authorizationType=raw.get('status'), cardState=raw['card'].get('state'))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(400, 'Invalid ASA request schema.') from None


def category_for(tx, data, c):
    simulation = c.execute('SELECT * FROM lithic_simulations WHERE acceptor_id=?', (tx['acceptorId'],)).fetchone()
    if simulation:
        requested = json.loads(simulation['request'])
        if requested['cardToken'] == tx['cardToken'] and requested['amount'] == tx['requestedAmount']:
            return requested['category'], simulation['id']
    # Honor an existing personalized merchant category, including renamed categories.
    prior = next((t for t in data['transactions'] if t['merchant'].casefold() == tx['merchant'].casefold() and t['type'] == 'purchase'), None)
    return (prior['category'] if prior else MCC_CATEGORIES.get(tx['mcc'], 'Uncategorized')), None


def decline(reason, code):
    return dict(approved=False, status='blocked', reason=reason, reasonCode=code, selectedCard=None,
                financialWarning=reason, scoreImpact=0, categoryImpact=None, estimatedReward=0)


def authorize(payload, headers):
    try:
        verify(payload, headers)
        tx = normalize(payload)
        with db.connect(timeout=.25) as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute('SELECT request,response FROM lithic_authorizations WHERE token=?', (tx['transactionToken'],)).fetchone()
            if prior:
                original = json.loads(prior['request'])
                if any(original[k] != tx[k] for k in ('cardToken', 'amount', 'currency', 'authorizationType')):
                    return dict(result='UNAUTHORIZED_MERCHANT', token=tx['transactionToken'])
                return json.loads(prior['response'])
            data, revision = db.read(c)
            if data['mode'] == 'personal': data['asOf'] = date.today().isoformat()
            tx['category'], simulation_id = category_for(tx, data, c)
            card = card_info(c)
            if not card or tx['cardToken'] != card['token']:
                decision = decline('This card is not the linked BudgetPlus Sandbox card.', 'unknown_card')
            elif tx['cardState'] != 'OPEN' or card['state'] != 'OPEN':
                decision = decline('The BudgetPlus Sandbox card is paused or closed.', 'card_paused')
            elif tx['currency'] != 'USD' or tx['authorizationType'] != 'AUTHORIZATION' or tx['amount'] <= 0:
                decision = decline('This Sandbox integration supports positive USD purchase authorizations only.', 'unsupported_transaction')
            else:
                decision = route(tx, data, execution='lithic')
            code = decision.get('reasonCode')
            result = 'APPROVED' if decision['approved'] else {
                'insufficient_funds': 'INSUFFICIENT_FUNDS', 'unconfirmed_balances': 'INSUFFICIENT_FUNDS',
                'category_limit': 'VELOCITY_EXCEEDED', 'budget_warning': 'VELOCITY_EXCEEDED',
                'card_paused': 'CARD_PAUSED',
            }.get(code, 'UNAUTHORIZED_MERCHANT')
            before = analyze(data)
            category = next((v for v in before['budget']['categories'] if v['name'] == tx['category']), None)
            remaining = decision['categoryImpact']['remaining'] if decision.get('categoryImpact') else category['remaining'] if category else None
            decision.update(provider='Lithic Sandbox', simulated=True, asaVerified=True, authorizationId=tx['transactionToken'],
                            merchant=tx['merchant'], amount=tx['amount'], category=tx['category'], mcc=tx['mcc'],
                            cardToken=tx['cardToken'], timestamp=tx['timestamp'], currency=tx['currency'], network=tx['network'],
                            decision_type='APPROVE_WITH_WARNING' if decision['approved'] and decision.get('financialWarning') else 'APPROVE' if decision['approved'] else 'DECLINE',
                            remaining_after_purchase=remaining, score_impact=decision['scoreImpact'], lithicResult=result,
                            contextMode=data['mode'], contextRevision=revision, settled=False,
                            paymentNotice='Lithic Sandbox authorization. No real funds moved; approved amounts are reserved in this local profile.')
            if decision['approved']:
                tx['importance'] = decision['importance']
                db.save(c, apply_purchase(data, tx))
            response = dict(result=result, token=tx['transactionToken'])
            c.execute('INSERT INTO lithic_authorizations (token,card_token,request,result,response,received_at) VALUES (?,?,?,?,?,?)',
                      (tx['transactionToken'], tx['cardToken'], json.dumps(tx), json.dumps(decision), json.dumps(response), now()))
            if simulation_id: c.execute("UPDATE lithic_simulations SET token=?,state='received' WHERE id=?", (tx['transactionToken'], simulation_id))
            return response
    except sqlite3.OperationalError:
        # Fast failure permits Lithic's documented retry instead of exceeding the response budget.
        raise HTTPException(503, 'Financial state is busy. Retry this authorization.') from None


@router.post('/authorize')
async def asa(request: Request):
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 131072: raise HTTPException(413, 'ASA request too large.')
    return await run_in_threadpool(authorize, bytes(payload), dict(request.headers))


def display_decision(row):
    result = json.loads(row['result'])
    result.update(networkResult=row['network_result'], networkStatus=row['network_status'])
    if row['network_status'] in ('DECLINED', 'VOIDED', 'EXPIRED') and result['approved']:
        result.update(budgetplusApproved=True, approved=False, status='blocked', scoreImpact=0,
                      reason='BudgetPlus approved, but Lithic reported ' + row['network_status'] + '. The local reservation was released.')
    return result


def recent(c):
    return [display_decision(r) for r in c.execute('SELECT * FROM lithic_authorizations ORDER BY received_at DESC LIMIT 10')]


def reconcile(api, token):
    transaction = api.transactions.retrieve(token)
    network_result, network_status = transaction.result, transaction.status
    if network_result != 'APPROVED' and network_status not in ('DECLINED', 'VOIDED', 'EXPIRED'):
        raise HTTPException(409, 'Lithic has not confirmed the result yet. Retry this same authorization to check again without creating another purchase.')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM lithic_authorizations WHERE token=?', (token,)).fetchone()
        if not row:
            return dict(approved=False, status='blocked', provider='Lithic Sandbox', asaVerified=False,
                        reason='Lithic did not deliver a verified ASA decision to BudgetPlus. Check enrollment, signature activation and Lithic pre-authorization rules.',
                        authorizationId=token, networkResult=network_result, networkStatus=network_status,
                        amount=transaction.amount / 100, scoreImpact=0, categoryImpact=None, simulated=True,
                        paymentNotice='No BudgetPlus purchase was recorded. This is not a successful ASA round trip.')
        if transaction.card_token != row['card_token']: raise HTTPException(502, 'Lithic returned a different card for this authorization.')
        c.execute('UPDATE lithic_authorizations SET network_result=?,network_status=? WHERE token=?', (network_result, network_status, token))
        if network_status in ('DECLINED', 'VOIDED', 'EXPIRED'):
            data, _ = db.read(c)
            retained = [t for t in data['transactions'] if t['id'] != 'lithic-' + token]
            if len(retained) != len(data['transactions']):
                data['transactions'] = retained
                db.save(c, data)
        updated = c.execute('SELECT * FROM lithic_authorizations WHERE token=?', (token,)).fetchone()
        return display_decision(updated)


@router.get('/authorization/{token}')
def authorization_status(token: str):
    with db.connect() as c:
        if not c.execute('SELECT 1 FROM lithic_authorizations WHERE token=?', (token,)).fetchone(): raise HTTPException(404, 'Authorization not found.')
    try:
        with client() as api: return reconcile(api, token)
    except HTTPException: raise
    except Exception as exc: raise provider_error(exc) from None


@router.post('/simulate')
def simulate(body: LithicSimulation):
    sandbox()
    # Keep simulation retries distinct from fast, independent ASA workers.
    if not simulation_lock.acquire(blocking=False): raise HTTPException(409, 'A Sandbox simulation is running. Retry shortly.')
    try:
        with db.connect() as c:
            card = card_info(c)
            if not card: raise HTTPException(409, 'Create the BudgetPlus Sandbox card in Wallet first.')
            requested = {**body.model_dump(), 'cardToken': card['token']}
            canonical = json.dumps(requested, sort_keys=True)
            prior = c.execute('SELECT * FROM lithic_simulations WHERE id=?', (body.requestId,)).fetchone()
            if prior and prior['request'] != canonical: raise HTTPException(409, 'This request ID already belongs to another simulation.')
            if not prior:
                acceptor = hashlib.sha256(body.requestId.encode()).hexdigest()[:15]
                c.execute('INSERT INTO lithic_simulations VALUES (?,?,?,NULL,?,?)', (body.requestId, acceptor, canonical, 'ready', now()))
            else:
                acceptor = prior['acceptor_id']
        try:
            with client() as api:
                if prior and prior['token']: return reconcile(api, prior['token'])
                if prior and prior['state'] != 'ready':
                    raise HTTPException(409, 'The previous simulation may have reached Lithic. Retry to retrieve its callback; it will not be sent twice. Check Lithic Transactions if no callback arrives.')
                remote = responder_status(api)
                with db.connect() as c: secret_ready = bool(config(c, 'asa_secret'))
                if not remote['matches'] or not secret_ready: raise HTTPException(409, 'Enroll and verify ASA in Wallet before simulating a purchase.')
                retrieved = api.cards.retrieve(card['token'])
                pan = retrieved.pan  # Memory only, required by the Sandbox simulator; never logged or persisted.
                if not pan: raise HTTPException(502, 'Lithic did not return the Sandbox PAN. Check Sandbox card permissions.')
                mcc = next((k for k, v in MCC_CATEGORIES.items() if v == body.category), '5999')
                with db.connect() as c: c.execute("UPDATE lithic_simulations SET state='sending' WHERE id=?", (body.requestId,))
                simulation = write_call(api.transactions.simulate_authorization, amount=int(Decimal(str(body.amount))*100),
                                        descriptor=body.merchant, pan=pan, mcc=mcc, merchant_acceptor_id=acceptor,
                                        merchant_currency='USD', merchant_acceptor_country='USA', status='AUTHORIZATION')
                del pan, retrieved
                if not simulation.token: raise RuntimeError('No transaction token returned')
                with db.connect() as c:
                    c.execute("UPDATE lithic_simulations SET token=?,state='sent' WHERE id=?", (simulation.token, body.requestId))
                return reconcile(api, simulation.token)
        except HTTPException: raise
        except Exception as exc: raise provider_error(exc) from None
    finally:
        simulation_lock.release()
