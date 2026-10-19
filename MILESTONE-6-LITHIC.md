# Milestone 6: Lithic Sandbox authorization

The existing profile, Plaid synchronization, Gemini, Money and Wallet layouts remain in place. Lithic Sandbox uses the same Python financial engine as the existing local demo. It does not charge real accounts, transfer between funding cards, or settle real payments.

## 1. Configure the Sandbox API key

Copy the **Sandbox API key** from [Lithic account settings](https://app.lithic.com/settings). [Official key setup](https://docs.lithic.com/docs/get-api-key).

Paste it into `C:\Users\swago\OneDrive\Desktop\BudgetPlus\backend\.env`. The placeholders have been added; keep the existing Plaid and Gemini values:

```dotenv
LITHIC_API_KEY=your_sandbox_key
LITHIC_ENV=sandbox
PUBLIC_BACKEND_URL=
LITHIC_CARD_PROGRAM_TOKEN=00000000-0000-0000-2000-000000000000
```

Production is intentionally rejected. The card-program token selects Lithic's Mastercard test BIN. [Official ASA Sandbox documentation](https://docs.lithic.com/docs/auth-stream-access-asa).

## 2. Start BudgetPlus and load your profile

From the main BudgetPlus folder, double-click `STOP-BUDGETPLUS.bat`, then `START-BUDGETPLUS.bat`. Open http://localhost:5173. In Money, confirm **MY DATA** and your synchronized balances. If currently using a demo, select **Use MY DATA**. Incomplete balances/history remain subject to the existing conservative guardrails.

The current Lithic Python SDK and webhook-verification dependency are installed. On a new checkout, install `backend/requirements.txt` into the backend virtual environment.

## 3. Create the Mastercard test card

Open **Wallet**, expand **Lithic Sandbox card & ASA**, then click **Create Mastercard Sandbox card**. Repeated clicks return the existing card. The backend also uses Lithic's UUID `Idempotency-Key` for safe Create Card retries. The existing BudgetPlus card displays its last four once the workspace refreshes.

Only the card token, last four, state, type, network and creation time are stored in SQLite or returned to the browser. PAN/CVV are never persisted. The simulator retrieves its required Sandbox PAN server-side, uses it in memory, and never returns it to React.

## 4. Create a temporary public HTTPS tunnel

Any HTTPS tunnel that forwards the original request body and webhook headers to `http://127.0.0.1:8000` is supported. No provider is hardcoded.

One quick Windows option is [Cloudflare's cloudflared](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/). Download the **Windows 64-bit executable**, save it in the main BudgetPlus folder as `cloudflared.exe`, and open PowerShell in that folder. Run:

```powershell
.\cloudflared.exe tunnel --url http://127.0.0.1:8000
```

Copy the generated `https://...trycloudflare.com` origin into `PUBLIC_BACKEND_URL` in `backend/.env`, without a trailing path. Restart BudgetPlus with STOP then START while leaving the tunnel window running. See [Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

The final responder URL is `PUBLIC_BACKEND_URL/api/lithic/authorize`. A new tunnel URL requires updating `.env`, restarting and enrolling again. Do not tunnel port 5173. When Lithic is configured, port 8000 exposes only signed ASA callbacks and a non-sensitive health check publicly. Other routes, including the financial profile, Plaid, card creation and enrollment, require a backend-local key that Vite adds server-side. Use the local UI at port 5173 for setup; no key is exposed to React. LAN access remains the existing trusted local demo behavior.

## 5. Enroll and verify ASA

In **Wallet > Lithic Sandbox card & ASA**, click **Enroll ASA**. BudgetPlus checks the existing responder first and only updates it if the URL differs. It enrolls `AUTH_STREAM_ACCESS`, retrieves/creates the ASA HMAC secret through Lithic's API, and saves it encrypted locally.

Click **Check ASA connection**. It should show **Enrolled at the configured URL** and **Signature verification: Ready**. This confirms enrollment and local key setup; the first signed authorization proves actual reachability. Signature headers may take a few minutes to activate after first enrollment. Unsigned, tampered and expired requests are rejected throughout; there is no insecure bypass.

After a successful simulation, check **Last verified ASA authorization**. In Merchant Demo's **View decision**, check **Verified ASA: Yes**, the ASA response, and Lithic's final result/token. A missing verified callback is reported as an unsuccessful ASA round trip even if Lithic's own response says approved.

No manual ASA Dashboard enrollment or secret copy is normally required. The one normal Dashboard step is copying your Sandbox API key. If enrollment/key retrieval is denied, verify that the key belongs to the intended Sandbox program and has issuing permissions, then contact Lithic support if needed. Re-click **Enroll ASA** after fixing permissions; it fetches the verification secret automatically. [ASA setup and verification](https://docs.lithic.com/docs/auth-stream-access-asa).

## 6. Approve a $10 purchase

1. Ensure the chosen category has at least $10 remaining and the profile has at least $10 safe to spend after obligations, goals, existing debt and reserves. A valid card alone does not bypass financial guardrails.
2. Open **Try a card tap** in Wallet (or http://localhost:5173/merchant).
3. Expand **Configure demo purchase**, select **Dining**, and set **Amount ($)** to `10`.
4. Click **Tap / Simulate BudgetPlus Card**.
5. BudgetPlus sends a Sandbox simulation to Lithic. Lithic sends the signed ASA request back, the existing local financial engine evaluates it, and Lithic receives the response.
6. Expand **View decision**. An approval should show `APPROVED`, **Verified ASA: Yes**, and **Lithic result: APPROVED / PENDING**. `PENDING` means authorization, not settled payment. `APPROVE_WITH_WARNING` also maps to ASA `APPROVED`; strict guardrails can decline warnings.

If the first purchase is declined by your existing protected-money or strict-mode rules, the displayed reason explains why. Do not expect a guaranteed approval for an underfunded profile. For a controlled demo, use an adequately funded demo profile and Balanced mode; do not falsify real balances.

## 7. Force the next $10 Dining purchase to decline

Open **Money > Personalize categories**, select **Dining**, enter a **Monthly spending limit ($)**, and save. This number is the total monthly category limit, not an additional allowance. To leave $5, enter the category's month-to-date spent amount plus $5. Setting the limit to `0` guarantees that the next positive Dining purchase exceeds the category allowance (other guardrails may also decline it).

Back in Merchant Demo, click **Start another purchase**, keep Dining and $10, then submit again. With sufficient general safe-to-spend and only the category limit exceeded, ASA returns `VELOCITY_EXCEEDED`. The stored reason gives the category's remaining amount. Declines do not reduce balances, category remaining, safe-to-spend or score. Leave the limit blank to restore the automatic target.

## 8. View transactions and explanations

- **Wallet > Recent decisions** shows approvals and declines, deterministic reasons, ASA results, network results, transaction tokens, remaining category amount and score impact.
- **Money > Recent activity** shows approved Sandbox purchases with **Authorization details**. Declines remain in the decision log and are excluded from spending.
- Ask Gemini in **AI Coach**, for example, "Why did BudgetPlus decline my $10 restaurant purchase?" The context includes the stored decision, reason, relevant profile and network results. Gemini cannot change the decision or financial math.
- **Pause Sandbox card** and **Unpause Sandbox card** in Wallet call Lithic's card-state API. A paused card may be declined by Lithic before ASA, which is clearly distinguished from a BudgetPlus decision.

## API and implementation notes

Local setup endpoints (via the Vite proxy at `http://localhost:5173`):

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/lithic/create-card` | Create/reuse safe Sandbox card metadata |
| POST | `/api/lithic/authorize` | Public, signed ASA callback only |
| POST | `/api/lithic/simulate` | Genuine Lithic Sandbox simulation, never a local substitute |
| GET | `/api/lithic/status` | Local card/enrollment/signature status |
| POST | `/api/lithic/responder/enroll` | Idempotent responder setup and HMAC retrieval |
| GET | `/api/lithic/responder/status` | Check current Lithic enrollment |
| POST | `/api/lithic/card/pause` | Pause the Sandbox card |
| POST | `/api/lithic/card/unpause` | Unpause it |
| GET | `/api/lithic/authorization/{token}` | Retrieve final network state and reconcile a rejected/voided/expired local hold |

`/api/authorize` remains the original local demo when Lithic is not configured. When `LITHIC_API_KEY` is present, it rejects attempts to bypass Lithic; Merchant Demo exclusively calls `/api/lithic/simulate`. Provider errors never cause a silent local approval.

ASA uses structured `amounts.cardholder` and, when larger, the adjusted `amounts.hold`; deprecated amount fields are accepted as a compatibility fallback. It preserves useful merchant/MCC, network, location, safe POS indicators and timestamps, without storing raw payloads or sensitive card fields. Signed unknown cards, unsupported currencies and unsupported authorization types fail closed. This milestone supports USD purchase `AUTHORIZATION`; refund/credit, ATM, balance-inquiry and settlement processing are not implemented.

Financial authorization shares `engines.route` and `engines.apply_purchase` with the existing profile engine. The Lithic branch enforces remaining category targets/explicit limits and the same reserves/pace/score rules, but never chooses another card to fund the purchase. Approved Sandbox authorizations create a separate local reservation included in the existing budget/score analysis; Plaid balances remain authoritative and are not edited. Reservations and category limits survive Plaid synchronization. Existing demo behavior remains unchanged when Lithic is disabled.

The ASA path performs signature verification, SQLite reads, local deterministic math and one atomic write. It makes no Plaid, Gemini or Lithic network calls. Database contention returns a prompt 503 for Lithic's documented retry rather than waiting beyond ASA's response budget. Transaction tokens provide durable duplicate protection. A duplicate with changed amount/card/currency/type is rejected. A declined decision is audited without spending. The audit remains available after a demo reset, while reset restores the demo financial snapshot.

Simulation request IDs prevent duplicate POSTs. Since the Sandbox simulation API does not document idempotency guarantees, an ambiguous timeout is never blindly re-sent. **Retry same authorization** retrieves the callback/result when available. If no callback/token arrives, inspect Lithic Sandbox Transactions before intentionally starting a different simulation. The simulator checks enrollment before sending and compares the final network transaction; rejection/void/expiry releases an existing local hold when reconciled. This milestone is not a complete settlement or reversal-webhook processor; Sandbox holds remain until reset or explicit status reconciliation.

Storage: safe card metadata and authorization audit are in `backend/data/budgetplus.sqlite3`; the encrypted ASA secret uses the adjacent `budgetplus.lithic-key`. The local proxy key is `budgetplus.local-api-key`. All are ignored by Git along with `.env`. Keep the database and encryption keys together when backing up. The current Python SDK is pinned in `backend/requirements.txt`.

## Verification and changed files

Run from the main project folder:

```powershell
$env:PATH = "$PWD\.tools\node-v22.16.0-win-x64;$env:PATH"
npm.cmd test
npm.cmd run build
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests -q
Pop-Location
```

Backend tests cover signed ASA approvals/declines, exactly-once updates, protected money and category limits, cached Plaid context, missing/invalid/expired signatures, card metadata projection, idempotent setup, pause/unpause, provider failure, final-network reconciliation, public route isolation and local authorization timing with substantial history. Synthetic browser checks cover Wallet setup, the Merchant approval/decline sequence, category edits, no bypass and desktop/mobile layouts. These tests do not substitute for a live Sandbox round trip using your key and tunnel.

Added: `backend/app/lithic_service.py`, `backend/tests/test_lithic.py`, `backend/tests/conftest.py`, `src/components/LithicControls.jsx`, this guide, `.verification/lithic-fixtures.py`, `.verification/lithic-ui.mjs` and their synthetic fixture/screenshots.

Updated: `backend/app/main.py`, `backend/app/db.py`, `backend/app/engines.py`, `backend/app/models.py`, `backend/app/coach.py`, `backend/requirements.txt`, `backend/.env`, `backend/.env.example`, `src/components/BudgetPlusWallet.jsx`, `src/components/CardOverview.jsx`, `src/components/MerchantDemo.jsx`, `src/components/Money.jsx`, `src/components/RecentTransactions.jsx`, `vite.config.js`, `.gitignore`, and `README.md`. The frontend production bundle is regenerated. The START/STOP scripts are unchanged.

No further milestone was started.
