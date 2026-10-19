"""File adapter registry: PDF, OFX/QFX and Plaid can supply the same normalized rows."""
import csv
import hashlib
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from zipfile import ZipFile
from openpyxl import load_workbook
from .engines import importance

MAX_ROWS = 20000
ALIASES = {
    'date': ['date', 'transaction date', 'posted date', 'posting date'],
    'merchant': ['merchant', 'description', 'payee', 'name', 'transaction description'],
    'amount': ['amount', 'transaction amount'], 'category': ['category', 'category name'],
    'account': ['account', 'account name'], 'type': ['type', 'transaction type'],
    'debit': ['debit', 'withdrawal', 'withdrawals'], 'credit': ['credit', 'deposit', 'deposits'],
}


def csv_rows(content):
    text = content.decode('utf-8-sig')
    try: dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
    except csv.Error: dialect = csv.excel
    rows = []
    for row in csv.reader(io.StringIO(text), dialect):
        rows.append(row)
        if len(rows) > MAX_ROWS + 1: raise ValueError('Maximum 20,000 rows per upload.')
    return rows


def xlsx_rows(content):
    with ZipFile(io.BytesIO(content)) as z:
        if sum(i.file_size for i in z.infolist()) > 50_000_000:
            raise ValueError('Expanded workbook exceeds 50 MB.')
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        result = []
        for row in workbook.active.iter_rows(values_only=True):
            result.append(list(row))
            if len(result) > MAX_ROWS + 1: raise ValueError('Maximum 20,000 rows per upload.')
        return result
    finally: workbook.close()


ADAPTERS = {'.csv': csv_rows, '.xlsx': xlsx_rows}


def number(value):
    s = str(value or '0').strip().replace('$', '').replace(',', '')
    if s.startswith('(') and s.endswith(')'): s = '-' + s[1:-1]
    n = Decimal(s)
    if not n.is_finite() or abs(n) > 100_000_000 or n.quantize(Decimal('.01')) != n:
        raise ValueError('Amount must be finite USD with at most two decimals.')
    return float(n)


def infer_category(merchant):
    for pattern, category in [('rent|apartment|mortgage', 'Housing'), ('grocery|market|whole foods', 'Groceries'),
                              ('chipotle|restaurant|coffee|cafe', 'Dining'), ('uber|transit|gas|fuel', 'Transportation'),
                              ('netflix|spotify|subscription', 'Subscriptions'), ('payroll|salary', 'Income')]:
        if re.search(pattern, merchant, re.I): return category
    return 'Uncategorized'


def normalize(content, suffix, mapping, sign, date_format, account):
    if suffix not in ADAPTERS: raise ValueError('Upload a CSV or XLSX file.')
    try: rows = ADAPTERS[suffix](content)
    except ValueError: raise
    except Exception as exc: raise ValueError('Cannot read file. Use UTF-8 CSV or a valid XLSX workbook.') from exc
    if len(rows) < 2 or len(rows) > MAX_ROWS + 1: raise ValueError('File must contain a header and 1–20,000 transaction rows.')
    headers = [str(h or '').strip().lower() for h in rows[0]]
    columns = {}
    for key, aliases in ALIASES.items():
        chosen = mapping.get(key, '').strip().lower()
        if chosen and chosen not in headers: raise ValueError(f'Mapped column not found: {chosen}')
        match = chosen or next((h for h in aliases if h in headers), None)
        if match: columns[key] = headers.index(match)
    if not {'date', 'merchant'} <= columns.keys() or not ('amount' in columns or 'debit' in columns or 'credit' in columns):
        raise ValueError('Required columns: date, merchant/description, and amount (or debit/credit). Use column mapping for other headers.')
    result, errors = [], []
    digest = hashlib.sha256(content).hexdigest()
    for index, row in enumerate(rows[1:], 2):
        if not any(v is not None and str(v).strip() for v in row): continue
        def get(key):
            i = columns.get(key)
            return row[i] if i is not None and i < len(row) else None
        try:
            raw_date = get('date')
            if isinstance(raw_date, datetime): parsed = raw_date.date()
            elif isinstance(raw_date, date): parsed = raw_date
            else:
                s = str(raw_date).strip()
                try: parsed = date.fromisoformat(s[:10])
                except ValueError: parsed = datetime.strptime(s, '%d/%m/%Y' if date_format == 'DMY' else '%m/%d/%Y').date()
            merchant = str(get('merchant') or '').strip()
            if not merchant or len(merchant) > 200: raise ValueError('Merchant must be 1–200 characters.')
            raw_type = str(get('type') or '').strip().lower()
            types = {'purchase':'purchase', 'debit':'purchase', 'expense':'purchase', 'withdrawal':'purchase',
                     'deposit':'deposit', 'credit':'deposit', 'income':'deposit', 'salary':'deposit',
                     'transfer':'transfer', 'payment':'transfer', 'refund':'refund', 'fee':'purchase'}
            if raw_type and raw_type not in types: raise ValueError(f'Unknown transaction type: {raw_type}')
            if 'amount' in columns:
                amount = number(get('amount'))
                kind = types.get(raw_type) or ('purchase' if (amount > 0) == (sign == 'positive_expenses') else 'deposit')
            else:
                debit, credit = abs(number(get('debit'))), abs(number(get('credit')))
                if debit and credit: raise ValueError('Both debit and credit are populated.')
                amount, kind = debit or credit, types.get(raw_type) or ('purchase' if debit else 'deposit')
            if not amount: raise ValueError('Zero amount is not a transaction.')
            category = str(get('category') or infer_category(merchant)).strip()
            acct = str(get('account') or account).strip()
            if not category or not acct or len(category) > 80 or len(acct) > 100: raise ValueError('Category/account label is blank or too long.')
            result.append(dict(id=f'import-{digest[:20]}-{index}', date=parsed.isoformat(), merchant=merchant,
                               amount=abs(amount), category=category, account=acct, type=kind, importance=importance(category),
                               source='salary' if raw_type == 'salary' else 'import', simulated=False))
        except (ValueError, InvalidOperation, TypeError) as exc:
            errors.append(f'Row {index}: {exc}')
    if errors: raise ValueError('No rows imported. ' + '; '.join(errors[:10]))
    if not result: raise ValueError('No transaction rows found.')
    return result, digest


def detect_recurring(transactions, as_of):
    groups = defaultdict(list)
    for tx in transactions:
        if tx['type'] == 'purchase' and not tx.get('simulated') and not tx.get('pending'):
            groups[(tx['merchant'].lower(), tx['account'])].append(tx)
    output = []
    today = date.fromisoformat(as_of)
    for key, rows in groups.items():
        rows.sort(key=lambda t: t['date'])
        if len(rows) < 2: continue
        a, b = rows[-2:]
        days = (date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days
        if not 25 <= days <= 35 or abs(a['amount']-b['amount']) > max(2, b['amount']*.1): continue
        due = date.fromisoformat(b['date']) + timedelta(days=days)
        while due < today: due += timedelta(days=days)
        essential = importance(b['category']) == 'MUST PAY'
        output.append(dict(id=hashlib.sha256(str(key).encode()).hexdigest()[:16], merchant=b['merchant'], category=b['category'],
                           amount=b['amount'], nextDate=due.isoformat(), essential=essential, inferred=True,
                           flag=None if essential else 'Possible recurring cost; confirm whether still needed.'))
    return output
