import json
import os
import sqlite3
import secrets
from pathlib import Path
from contextlib import contextmanager
from .engines import importance


def demo():
    data = json.loads(Path(__file__).with_name('demo.json').read_text())
    data.update(mode='demo', balancesConfirmed=True, categoryImportance={})
    for t in data['transactions']:
        t['account'] = t.get('card', 'Demo checking')
        t['importance'] = importance(t['category'])
    return data


def database_path():
    return Path(os.getenv('BUDGETPLUS_DB') or Path(__file__).parents[1] / 'data' / 'budgetplus.sqlite3')


def local_api_key():
    return database_path().with_suffix('.local-api-key').read_text().strip()


@contextmanager
def connect(timeout=30):
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL, revision INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, date TEXT NOT NULL, merchant TEXT NOT NULL, amount REAL NOT NULL, category TEXT NOT NULL, account TEXT NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS authorizations (id TEXT PRIMARY KEY, request TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS imports (digest TEXT PRIMARY KEY, row_count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS plaid_items (item_id TEXT PRIMARY KEY, environment TEXT NOT NULL,
            access_token TEXT NOT NULL, exchange_hash TEXT UNIQUE NOT NULL, cursor TEXT NOT NULL DEFAULT '',
            institution_id TEXT, institution TEXT NOT NULL DEFAULT 'Connected institution',
            history_status TEXT NOT NULL DEFAULT 'NOT_READY', last_sync TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS plaid_accounts (account_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS plaid_transactions (transaction_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS plaid_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lithic_card (id INTEGER PRIMARY KEY CHECK(id=1), token TEXT UNIQUE NOT NULL,
            last_four TEXT NOT NULL, state TEXT NOT NULL, type TEXT NOT NULL, network TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lithic_config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lithic_authorizations (token TEXT PRIMARY KEY, card_token TEXT NOT NULL,
            request TEXT NOT NULL, result TEXT NOT NULL, response TEXT NOT NULL, received_at TEXT NOT NULL,
            network_result TEXT, network_status TEXT);
        CREATE TABLE IF NOT EXISTS lithic_simulations (id TEXT PRIMARY KEY, acceptor_id TEXT UNIQUE NOT NULL,
            request TEXT NOT NULL, token TEXT, state TEXT NOT NULL, created_at TEXT NOT NULL);
        ''')
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT id FROM workspace').fetchone():
            save(c, demo())
    key_path = database_path().with_suffix('.local-api-key')
    try:
        with key_path.open('x') as f: f.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass


def read(c):
    row = c.execute('SELECT * FROM workspace WHERE id=1').fetchone()
    data = json.loads(row['data'])
    data['transactions'] = [json.loads(t['data']) for t in c.execute('SELECT data FROM transactions ORDER BY date DESC, id DESC')]
    return data, row['revision']


def save(c, data):
    config = {k: v for k, v in data.items() if k != 'transactions'}
    c.execute('INSERT INTO workspace VALUES (1, ?, 1) ON CONFLICT(id) DO UPDATE SET data=excluded.data, revision=workspace.revision+1', (json.dumps(config),))
    c.execute('DELETE FROM transactions')
    c.executemany('INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                  [(t['id'], t['date'], t['merchant'], t['amount'], t['category'], t.get('account', ''), t['type'], json.dumps(t)) for t in data['transactions']])
