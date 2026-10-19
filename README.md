# BudgetPlus

**One card. No decisions.**

A card-first prototype with a real FastAPI decision engine, SQLite persistence, personal CSV/XLSX imports, and server-side Google Gemini coaching. The BudgetPlus Card chooses a manually configured underlying funding card. Authorization decisions are functional; every charge, reward and settlement remains simulated. No issuance, PCI card-number storage, Apple Pay provisioning, or payment-network integration is implemented.

## 1. Install Python dependencies

Use Python 3.11+ and Node 22.12+ (or Node 24). Install Python first if neither `python` nor `py` is available. From the project root in PowerShell:

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

If Windows uses the Python launcher, replace the first `python` with `py -3`. A project virtual environment has already been created in this workspace. You can reuse it without recreating it. On macOS/Linux, use `python3 -m venv backend/.venv`, then `backend/.venv/bin/python` instead of the Windows executable paths below.

## 2. Set GEMINI_API_KEY

```powershell
if (!(Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
notepad backend/.env
```

Set these values locally; do not put the key in React, a `VITE_` variable, or source control:

```dotenv
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-flash-latest
```

Create a key through [Google AI Studio](https://aistudio.google.com/apikey). Set `GEMINI_MODEL` to a model available to your key if needed. The integration uses the maintained [`google-genai` Python SDK](https://googleapis.github.io/python-genai/), `genai.Client`, and `client.models.generate_content`. Restart FastAPI after changing environment settings. The model is configurable; successful access depends on your account, quota and network.

## 3. Start FastAPI

From the project root:

```powershell
./backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

API documentation: <http://127.0.0.1:8000/docs>. Health: <http://127.0.0.1:8000/api/health>.

SQLite is created automatically at `backend/data/budgetplus.sqlite3`. Restarting either server preserves imported transactions, profiles, preferences, cards and decisions. Optional `BUDGETPLUS_DB` selects a different database file. `.env`, SQLite files, virtual environments and caches are ignored by Git. The repository is in OneDrive: local database files may be synchronized by your existing OneDrive settings; use `BUDGETPLUS_DB` outside OneDrive if you want to avoid that.

## 4. Start React

In a second PowerShell terminal, from the project root:

```powershell
npm install
npm run dev
```

Open <http://localhost:5173>. Vite forwards `/api` to FastAPI on `127.0.0.1:8000`, so every device uses the same SQLite workspace. Port 5173 is fixed; if already occupied by this app, reuse it or stop that existing server before restarting. `npm run build` checks the production bundle. `npm run preview` is not configured as an API proxy; use the development server for this milestone's multi-device demo.

Home leads with the card promise, cash, available credit, and score. Money groups the account snapshot, score, and category plan, with imports, upcoming expenses, recurring bills, and activity behind disclosures. Wallet keeps funding controls and the latest authorization together. AI Coach automatically attaches structured financial context when you submit a question; technical details stay behind the info disclosure. Home insights come from the existing financial engine; no Gemini call runs automatically.

### UI refocus smoke check

1. **Home:** Check the headline, card, three live metrics, Tap/Decide/Execute, and Ask BudgetPlus navigation. Click the score to open Money.
2. **Money:** Expand Why [score], a category, Accounts & import, Can wait, Upcoming money, and Recent activity. Import remains under Accounts & import. Edit financial snapshot and Personalize categories retain their existing save flows. Planned expenses in categories marked CAN WAIT appear in the dedicated list; timing is not invented.
3. **Wallet:** Expand Manage card to lock/unlock or set a preferred card. Expand Purchase controls to choose balanced or strict guardrails. Open Try a card tap; after a simulated purchase, verify the recent decision and View decision. Balanced can approve with warnings; strict blocks warnings.
4. **AI Coach:** Choose a suggested question, edit it, then Ask BudgetPlus. Verify the answer or a clear provider error. Privacy & AI details explains what is shared. Requires a configured API key.
5. **Merchant:** Open `/merchant`, configure a purchase, tap, and expand View decision. Retry and decline behavior use the unchanged authorization flow.
6. Repeat at a narrow mobile width and use keyboard Tab/Enter to operate navigation and disclosures.


## 5. Upload your own CSV/XLSX

1. Open **Money > Accounts & import** and select a real `.csv` or `.xlsx` file.
2. Select the amount sign convention and slash date format. Explicit transaction types override sign conventions. ISO dates (`YYYY-MM-DD`) work in either mode.
3. Use **Replace** for a fresh dataset or **Append** for a non-overlapping additional export. The first personal import always removes fictional demo history, balances, goals, obligations and cards.
4. If needed, expand column mapping. Example: `{"date":"Posting Date","merchant":"Payee","amount":"Value"}`.
5. Click **Upload and analyze**. Categories, profile, spending analysis, recurring candidates, recommendations and score regenerate from stored history immediately.
6. Open **Edit financial snapshot**. Enter current cash balances, funding card snapshots, goals, debt, upcoming obligations and your buffer. Review inferred recurring items. Check the confirmation box and save. Transaction history alone cannot establish present-day liquidity; routing remains blocked and the score provisional until you confirm these snapshots.

Supported headers (case insensitive):

| Normalized field | Recognized export headers |
| --- | --- |
| date | date, transaction date, posted date, posting date |
| merchant | merchant, description, payee, name, transaction description |
| amount | amount, transaction amount; or debit/withdrawal and credit/deposit columns |
| category | category, category name; inferred if omitted |
| account | account, account name; form label if omitted |
| transaction type | type, transaction type; inferred from amount sign if omitted |

Example UTF-8 CSV:

```csv
date,merchant,amount,category,account,transaction type
2026-09-01,Apartment rent,-950,Housing,Checking,purchase
2026-10-01,Apartment rent,-950,Housing,Checking,purchase
2026-10-04,Payroll,2400,Income,Checking,salary
2026-10-05,Chipotle,-18.42,Dining,Checking,purchase
2026-10-06,Credit card payment,-200,Payments,Checking,transfer
```

- Limits: 10 MB, 20,000 transaction rows, XLSX active worksheet, 50 MB expanded workbook. USD only. No currency conversion.
- Common aliases include purchase/debit/expense/withdrawal/fee, deposit/credit/income/salary, transfer/payment and refund. Unknown explicit types reject the file with row numbers.
- Invalid rows reject the whole upload; no partial data is committed. An exact file reupload is blocked. Legitimate identical rows within a file are retained. Different overlapping exports are **not** deduplicated; use non-overlapping exports or replace with a consolidated file.
- Card repayments and account transfers must be classified as `transfer`/`payment` to avoid treating them as purchases. Refunds are retained separately and do not reduce category spending automatically in this prototype.
- Imports do not replay historical purchases against current cash/card balances. Additional imports require snapshot reconfirmation.
- Authorization does not automatically reconcile or mark scheduled bills as paid. Update the relevant upcoming/recurring obligation and account snapshot after a real-world bill payment; the demo never performs that payment.
- Monthly recurring detection looks for similar merchant/account amounts approximately a month apart. Inferred recurring expenses are estimates, not verified active subscriptions. Edit/remove them in the snapshot editor. Recurring obligations roll forward monthly. Do not duplicate a debt's monthly payment in upcoming expenses.
- Category importance is editable as **MUST PAY**, **FLEXIBLE**, or **CAN WAIT**. Rename/refine a category to update matching history and obligations. Add a category without building an entire manual budget. Checkout can override importance for a specific urgent purchase.
- **Reset Demo** removes personal workspace data and restores the original fictional fixture after confirmation. It is not an import undo feature.

## 6. Verify Gemini really responds

Open **AI Coach**, enter "Can I afford a $600 laptop right now?", and click **Ask BudgetPlus**. There is no sharing checkbox. A successful answer has a **Response details** disclosure showing Google Gemini, model, timestamp, context transaction count, and the provider response ID when supplied. The server's `/api/coach` response also includes the financial revision used. If finances change, the UI marks the answer stale.

`/api/health` reports `geminiConfigured: true` when a key exists; that alone does **not** prove the key works. Only a successful coach request verifies provider access. Missing keys show "Gemini isn't connected yet." (HTTP 503); provider/network/quota/model errors return HTTP 502. There is no deterministic fallback or fabricated response. Live provider access was not tested during implementation because no user Gemini key was configured; the SDK boundary/context and failure paths are tested with a stub.

Gemini receives up to 1,000 recent normalized transactions plus aggregates over all history, profile, category importance, score and factors, cash balances, available credit, recurring expenses, goals, debt, card reward rules, preferences, upcoming expenses, delayable purchases, and the last ten routing decisions. Raw uploaded files and unknown columns are discarded. API keys, bank login credentials and full card numbers are not context fields. Do not enter credentials into free-text labels/questions. Coach suggestions never mutate financial data or approve purchases; apply refinements in Money.


### Restart FastAPI after pasting your key

The exact file is `C:\Users\swago\OneDrive\Desktop\BudgetPlus\backend\.env`. Paste the key after `GEMINI_API_KEY=` and save. Keep it out of React, VITE variables, and chat.

In the terminal running FastAPI, press **Ctrl+C**, then run from the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

A `.env` change requires this restart; Python auto-reload alone is not sufficient. Existing process environment variables take precedence over `.env`; remove a stale `GEMINI_API_KEY` override if applicable. The default `gemini-flash-latest` model alias can be overridden with `GEMINI_MODEL` in the same backend file.

### Randomize Financial Snapshot (demo only)

At the bottom of any app page, beside **Reset demo**, click **RANDOMIZE FINANCIAL SNAPSHOT**. No confirmation is needed for synthetic data. The button is disabled in Personal workspace, and the backend also rejects randomization there. Reset demo remains an explicitly confirmed destructive switch back to the original demo.

Seven scenario families cover comfortable finances, tight cash, high card utilization, student/irregular income, high upcoming bills, strong savings with overspending, and stable professional income. Consecutive generations select different families. Numbers vary within each family. The scenario label appears in the existing demo controls and the success notice.

Each generation creates three months of statement history plus month-to-date activity, reconciles current cash against an opening balance and deposits/spending/transfers, derives reserves and funds available using the existing engine, and persists the complete snapshot atomically. It clears old synthetic routing records and generates one actual simulated $18.42 Chipotle authorization against the new plan. An approval is recorded exactly once in the synthetic ledger; a decline does not create a purchase. No real funds move. Existing routing and score formulas are unchanged.

To verify:

1. Click Randomize several times. Compare the scenario label, cash, available credit, score, and flexible spend on Home. Different families need not produce a different integer score on every single click.
2. In Money, compare category limits, protected expenses, score factors, upcoming money, and Can wait. Student scenarios include School; high-obligation scenarios include Medical. Inspect the current profile through `/api/state` under `analysis.profile`.
3. In Wallet, open the new Chipotle decision. Tight-cash/high-obligation profiles protect reserves; high utilization rejects ineligible cards; comfortable profiles can fund the purchase. Reload and confirm the snapshot persists.
4. In AI Coach, ask the same laptop question after randomizing. Each request uses the current revision, including the new score, categories, and routing decision. A previous answer is marked stale when finances change.
5. Imported data cannot be randomized. The endpoint returns 409 without modifying the imported snapshot. Stale revision requests also return 409 rather than replacing newer data.

Tests: `npm test`, `npm run build`, and `$env:PYTHONPATH='backend'; .\backend\.venv\Scripts\python.exe -m pytest backend/tests -q`. Backend coverage includes 84 generated scenario/date combinations, coherent reconciliation, persistence, personal-data protection, current Gemini context, allowlisting/redaction, and short provider errors. Live Gemini access still needs your own working key; no canned answers are used by the application.

## 7. Run a merchant transaction

Open <http://localhost:5173/merchant> on another browser/device. It is a separate merchant interface with no BudgetPlus sidebar or dashboard shell. The default Chipotle order is a $14.75 bowl plus a $3.67 drink, totaling $18.42.

Click **Tap / Simulate BudgetPlus Card**. FastAPI evaluates finances, importance, spending pace, obligations, goals, debt, score, credit availability, rewards and preference. The result names the chosen funding card, cash-equivalent reward estimate, category impact, score impact and warnings. The main app polls every 2.5 seconds and shows the latest decision; Wallet/Money show the purchase. With the original fixture, balanced mode selects Amex Gold for dining and returns a pace warning.

Balanced guardrails approve financially eligible purchases with visible warnings. Strict guardrails decline warnings. Both always block protected-resource violations and cards exceeding 50% post-purchase utilization. MUST PAY never overrides insufficient resources. The preference bonus is a tie-influencing factor, not an override of credit eligibility. Rewards are configured cash-equivalent percentages, not live points valuations.

Direct API example:

```powershell
$body = @{
  cardToken = 'demo-card-001'
  merchant = 'Chipotle'
  amount = 18.42
  category = 'Dining'
  importance = 'FLEXIBLE'
  requestId = 'my-demo-purchase-001'
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/authorize -ContentType 'application/json' -Body $body
```

Reuse the same request ID/body to retry safely. A different body with the same ID is rejected. Use a new request ID for a new purchase. The UI retains its request ID on network retries (within the open page). Reloading the merchant page starts a new checkout; check activity first if a previous response was lost. SQLite serializes decisions and atomically stores the authorization, ledger entry and card balance. Declines are audited without changing balances. `simulated: true`, `settled: false` and `provider: simulated` are explicit response fields.

## 8. Access from an iPhone on the same Wi-Fi

Keep both servers running on the Windows computer. Run `ipconfig` and find the Wi-Fi adapter's IPv4 address, for example `192.168.1.42`. On the iPhone open:

```text
http://192.168.1.42:5173
```

On the merchant laptop/second phone open:

```text
http://192.168.1.42:5173/merchant
```

Use your actual address, not the example and not `localhost` on the phone. Vite listens on all interfaces and proxies to the loopback-only backend. If Windows Firewall prompts, allow Node on your private network. Guest Wi-Fi/client isolation or a VPN can block device-to-device access. Phones do not need direct access to port 8000. The request-ID fallback supports ordinary LAN HTTP where `crypto.randomUUID` may be unavailable.

At implementation time this computer reported Wi-Fi IPv4 `10.66.37.180`: app `http://10.66.37.180:5173`, merchant `http://10.66.37.180:5173/merchant`, NFC `http://10.66.37.180:5173/tap/demo-card-001`. This address can change. Its network name suggests client isolation may be enabled; if the phone cannot connect, use a trusted home network or hotspot that permits device-to-device traffic.

This is one shared local workspace, without user authentication or tenant isolation. Anyone who can reach this development server can access or change its finances. Use a trusted private network; do not expose it publicly or port-forward it. Authentication and HTTPS are prerequisites for deployment beyond this local prototype.

## 9. Physical NFC demo URL

Write this URL as an NDEF URL record to a writable NFC tag/card using your NFC writer:

```text
http://YOUR-COMPUTER-WIFI-IP:5173/tap/demo-card-001
```

Scan with an NFC-capable phone. The phone opens the independent merchant checkout, recognizes the prototype token from the path, and the merchant clicks **Tap / Simulate BudgetPlus Card** to submit the purchase to the same Python engine. Opening/scanning the URL alone does not create a transaction. A blank NFC card contains only a URL; it does not contain a payment credential or provision a payment card. A changed computer IP requires rewriting the tag (or using a stable local address). Typing/opening the URL is the button-based fallback. Physical NFC and iPhone behavior must be verified on your devices.

## Architecture and validation

- `backend/app/engines.py` ports the original financial profile, budget, routing and score rules. The original JavaScript financial engines and regression tests are preserved as references, but active React screens obtain their financial state/decisions through APIs. No important active financial state depends on React/localStorage.
- Health index stays 0–100; only its display is `round(300 + healthIndex * 5.5)`, between 300 and 850. It is **not a credit score**.
- SQLite has workspace configuration, normalized transaction rows, authorization records and import digests. Optimistic revisions protect settings against stale writes from another device. Analysis is derived from persistent source data.
- `AuthorizationProvider` is the adapter boundary. `SimulatedProvider` is the only implementation. Future Lithic, Marqeta or Stripe Issuing adapters can be added without replacing the routing engine. None is currently connected.
- File adapters share a normalized contract through the importer registry. CSV/XLSX and Plaid feed the same profile pipeline. PDF and OFX/QFX remain extension points.
- The financial profile uses USD. Plaid synchronizes live checking, savings and credit-card data; other currencies and account types are listed but excluded from profile math. Identity management and real settlement are not implemented.

Run tests from the project root:

```powershell
npm test
npm run build
Push-Location backend
./.venv/Scripts/python.exe -m pytest tests -q
Pop-Location
```

Backend tests cover legacy financial-engine parity, CSV and XLSX uploads, mappings/signs/dates/types, recurring inference, transactional import rejection, idempotent concurrent retries, simultaneous purchase guardrails, persistence, personal-data isolation, optimistic settings conflicts, category refinement, protected debt payments, and Gemini context/error behavior. The frontend build and original engine tests also run. Desktop/mobile browser rendering and local simulated purchase flows have been checked. Physical NFC and actual iPhone hardware are not claimed as tested.

## 10. Created and changed files

Created:

- `backend/requirements.txt`, `backend/.env.example`, `backend/data/.gitkeep`
- `backend/app/__init__.py`, `backend/app/demo.json`, `backend/app/db.py`
- `backend/app/engines.py`, `backend/app/models.py`, `backend/app/providers.py`
- `backend/app/importers.py`, `backend/app/coach.py`, `backend/app/main.py`
- `backend/tests/test_backend.py`
- `src/utils/api.js`
- `src/components/Money.jsx`, `src/components/ImportTransactions.jsx`

Changed:

- `src/App.jsx`
- `src/components/BudgetPlusWallet.jsx`, `src/components/MerchantDemo.jsx`, `src/components/AICoach.jsx`
- `src/components/BudgetCategories.jsx`, `src/components/BudgetPlusScore.jsx`
- `src/styles.css`, `vite.config.js`, `.gitignore`, `README.md`

Generated locally and ignored: `backend/.venv/`, Python/pytest caches, `backend/data/budgetplus.sqlite3` (and SQLite sidecars), and the `dist/` production bundle. No Gemini key was created or stored in source code.


## Milestone 5: connect your own accounts with Plaid

1. Sign in or create a Plaid developer account at https://dashboard.plaid.com/. Open **Developers / Keys** at https://dashboard.plaid.com/developers/keys. Copy the **client_id** into `PLAID_CLIENT_ID` and the **Production secret** into `PLAID_SECRET`. Request Production access and enable Transactions in your Plaid dashboard. Real institutions (including OAuth banks) depend on Plaid approving the app and the relevant institution access; Sandbox credentials cannot connect a real bank. See https://plaid.com/docs/quickstart/ and https://plaid.com/docs/link/oauth/.
2. Edit `C:\Users\swago\OneDrive\Desktop\BudgetPlus\backend\.env`. The placeholders are already present. Preserve the existing Gemini settings:

   ```dotenv
   PLAID_CLIENT_ID=your_client_id
   PLAID_SECRET=your_production_secret
   PLAID_ENV=production
   ```

   For test accounts, use the Sandbox secret and `PLAID_ENV=sandbox`. Sandbox and Production Items are stored separately and never merged. The UI explicitly labels Sandbox. Do not put either secret or any access token in React, a `VITE_` setting, screenshots, or source control.
3. Restart from the main BudgetPlus folder: double-click `STOP-BUDGETPLUS.bat`, then `START-BUDGETPLUS.bat`. The scripts wait for both servers before opening http://localhost:5173. Dependencies have been installed; on a fresh checkout, run `npm.cmd install` with the bundled Node on PATH and `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt` first.
4. Open **Money**. **CONNECT MY ACCOUNTS** appears inside **Account snapshot**, above the balances. Click it, select your institution in Plaid Link, complete its sign-in/consent flow, and select accounts. Enter bank credentials only inside the bank/Plaid flow. Desktop browser OAuth uses Plaid's popup flow; allow its popup. This local desktop setup does not require a custom redirect URI.
5. BudgetPlus stores the Item securely on the backend, imports accounts and transaction changes, switches to **MY DATA**, and automatically rebuilds the existing profile, targets, income pattern, recurring estimates, obligations, classifications, score, and recommendation context. No manual budget creation is required. The progress checklist finishes with **YOUR PROFILE IS READY** after Plaid confirms historical import completion. Up to 730 days are requested; actual history depends on the institution.
6. Add another institution with **CONNECT ANOTHER ACCOUNT** in the same place. Its data merges with existing linked institutions. To repair an expired connection, expand **Connected institutions and accounts** and select **Repair connection**; do not create a second connection to the same accounts.
7. Verify the institution/account/transaction/month counts below the buttons. Expand **Connected institutions and accounts** for balances, available balances, limits, last four and last-sync times. Open **Money > Recent activity**, then **Import details**, to inspect the imported merchant, date, institution, account, pending flag, Plaid category and transaction ID. **More imported activity** shows older entries. Months analyzed counts distinct months with settled, supported transactions, not a promise of 24 full months.
8. Open **AI Coach** and ask, for example, "Summarize my actual spending and income, and explain my top priority." Expand **Response details**: it should say **MY DATA / Plaid production**, followed by the Gemini model, context transaction count and response timestamp. A stale-answer notice appears if the profile has changed since that answer. Context includes up to 1,000 recent transactions; deterministic aggregates and categories use all imported supported history. Gemini never changes balances, math, scores or settings.

### Sync, fallback and storage behavior

- While BudgetPlus is open on this computer, it retries incomplete history about every 15 seconds and checks completed connections every five minutes. **Sync accounts** requests an immediate incremental sync. No background server is installed and no webhooks are exposed; after closing the app, reopen it to resume. Plaid/institution data may lag real-time activity.
- SQLite stores Item metadata, encrypted access tokens, account snapshots, normalized transactions and per-Item cursors. Cursor and transaction changes commit together after all pages succeed. Pagination mutations retry from the saved cursor. Transaction IDs prevent repeat imports; modified/removed entries and pending-to-posted replacements are reconciled.
- Default database: `backend/data/budgetplus.sqlite3`. The token encryption key is the adjacent `budgetplus.plaid-key`; both are ignored by Git. Keep both private and back them up together. Losing the key requires repairing local credential storage/reconnecting. Bank access tokens and secrets never enter workspace snapshots, React or Gemini context. The app remains the existing shared local prototype without multi-user authentication; use it only on your trusted private network.
- The profile uses checking/savings balances and credit balances/limits, excluding unsupported currencies/types rather than adding unlike money. Missing balances or limits leave the score provisional. Unknown card rewards are zero, unknown limits are not invented, and such cards cannot fund a simulated purchase. Available cash is limited by the lesser of reported current and available balance. Pending entries are shown but excluded from settled spending/income and recurring inference. Credit-card payments and transfers do not duplicate purchases or payroll.
- **Reset demo** and randomized demos remain available; they do not erase Plaid connection records. Background sync does not overwrite Demo Mode. Choose **Use MY DATA** to restore cached linked history and sync it. Existing CSV/XLSX replacement and append uploads remain available. CSV history is preserved when linking from a personal workspace; overlapping exports and bank history can represent the same activity, so use non-overlapping uploads.
- A failed institution preserves its previous data and shows a repair/retry message; other institutions can still synchronize. Existing category edits and card reward/preferences survive subsequent bank syncs.
- No card issuing, Apple Pay, real payment settlement or Milestone 6 work was added.

Validation: backend tests use mocked Plaid responses and isolated temporary SQLite databases, including delayed history, idempotency, pagination mutation, pending replacement, multi-institution imports, environment separation, encrypted storage, failure preservation and real-data Gemini context. Live institution linking requires your own approved Plaid Production credentials and consent.

## Milestone 6: Lithic Sandbox authorization

See [MILESTONE-6-LITHIC.md](MILESTONE-6-LITHIC.md) for the Sandbox API key, Mastercard test card, public HTTPS tunnel, signed ASA enrollment, approve/decline demo, storage, endpoint details and validation. Wallet and Merchant Demo use the existing layouts. With Lithic configured, the Merchant Demo uses a genuine Lithic Sandbox round trip and never silently falls back to local authorization.

