# Manual Withdrawal Admin Tool

A desktop app (single `main.py`, Tkinter) for the manual withdrawal system described
by `AdminWithdrawalController` / `ManualWithdrawalRequest`. It:

- Lists **all** withdrawals (any status) and shows totals from the `/stats` endpoint.
- Has a separate **Pending** tab showing only pending requests, with live totals
  (count, total Net BH, total Net USD).
- Lets you **Approve** or **Reject** a withdrawal, one at a time or all at once.
- On approval, it can **actually send the payout on-chain** (USDT, BEP-20 or Polygon)
  from a wallet you configure, then call the backend's `/approve` endpoint with the
  resulting transaction hash. This is the Python equivalent of the PHP
  `App\Services\Web3Service` in your project — that class **verifies incoming
  deposits**; this app **sends outgoing payouts**, using `web3.py` instead of the
  PHP `web3.php` library.

## 1. Where each form maps to your code

| Form field (Settings tab)        | Used for |
|---|---|
| API Base URL                     | Should be `https://yourdomain.com/api/v1/admin/withdrawals` — matches the `Route::prefix('v1/admin/withdrawals')` group in your `routes/api.php`. |
| Authorization Header              | Whatever your admin API auth expects, e.g. `Bearer <token>`. Your routes aren't shown wrapped in `auth:sanctum` here, so add that header format to match whatever middleware actually protects them. |
| Network / RPC URL / USDT Contract / Decimals | Equivalent to `$rpcUrls` / `$networkConfig` / `$usdtAbi` in `Web3Service.php`. The RPC URL field defaults to the Infura BSC URL that was already in your code (`bsc-mainnet.infura.io/v3/...`) — verify that project/key is still yours and not rate-limited or revoked. |
| From Wallet Address / Private Key | The hot wallet that pays customers. Nothing like this existed in `Web3Service.php` (it only verifies deposits) — this is new, and it's the part that actually moves money. |
| Amount to send (USD vs BH)        | Whether each payout sends `net_amount_usd` worth of USDT, or `net_amount_bh` as a raw token amount. Pick whichever matches how your customers were quoted. |
| Simulation mode                   | When checked (default), nothing is broadcast on-chain — every "send" is logged as `SIMULATED-...` so you can test the whole approve/reject flow against your real API safely before touching real funds. |

## 2. Security — please read before using a real wallet

- The private key is **never written to disk in plain text**. If you check
  "Remember this key on disk, encrypted with a passphrase", it's encrypted with
  Fernet using a key derived (PBKDF2-SHA256, 390k iterations) from a passphrase
  you choose, which is **not stored anywhere**. Forgetting that passphrase means
  the saved key is unrecoverable — that's intentional.
- If you don't check that box, the key is kept only in memory for the current
  run and is never written to disk; you'll need to re-enter it next time you
  open the app.
- Anyone who can run this app and unlock the saved key can move every token
  in that wallet. Only fund the hot wallet with what you intend to pay out
  soon, and run this on a machine you trust (not a shared/public PC).
- Leave **Simulation mode** on until you've verified, with a small real
  test withdrawal, that addresses/amounts/decimals are all correct.
- This app does not validate that your API auth header is actually checked
  server-side — make sure those routes require admin authentication in
  Laravel (e.g. `auth:sanctum` + an admin gate), otherwise anyone who finds
  the URL could approve/reject withdrawals.
- Consider, for real production use, a multisig or a separate signer service
  with spending limits, rather than a single private key on an admin's
  laptop — that's a process risk, not something code can fully fix.

## 3. Running it

```bash
pip install -r requirements.txt
python main.py
```

On first run, go to the **Settings** tab and fill in:
1. API Base URL + Authorization Header → click "Test API Connection".
2. Network, RPC URL, USDT Contract, Decimals → click "Test RPC Connection".
3. From Wallet Address (+ Private Key if you intend to send real funds) →
   click "Check Balances" to confirm the wallet has both USDT and enough
   native coin (BNB/MATIC) for gas.
4. Click "Save All Settings" (and "Save Wallet Settings" if you entered a key).

Then use the **Pending** tab to approve/reject. "Approve ALL Pending" sends
one transaction per request, sequentially incrementing the nonce, and logs
each transaction hash (clickable, opens the block explorer) in the Activity
Log panel before marking it approved via the API.

## 4. Building the Windows .exe via GitHub Actions

This repo includes `.github/workflows/build.yml`. To use it:

1. Push `main.py`, `requirements.txt`, and `.github/workflows/build.yml` to
   the root of a GitHub repository.
2. Go to the **Actions** tab → run "Build Windows EXE" manually (or push to
   `main`).
3. When it finishes, open the run and download the `WithdrawalAdmin-windows`
   artifact — it contains `WithdrawalAdmin.exe`.

The workflow installs `pyinstaller` and your pinned `requirements.txt`, then
runs PyInstaller with `--copy-metadata` flags for the `web3`/`eth-*` packages.
That flag is required: without it, the frozen exe crashes on startup with
`PackageNotFoundError: No package metadata was found for py_ecc`, because
those libraries check their own version via `importlib.metadata` at runtime
and PyInstaller doesn't include that metadata by default. This was confirmed
by building and running the equivalent Linux binary before writing this
workflow.

## 5. Notes / things you may want to extend

- `requirements.txt` pins `setuptools==70.0.0` deliberately: `web3` imports
  `pkg_resources`, which newer `setuptools` releases (81+) removed entirely.
- The "Amount to send" choice and the USDT contract/decimals are global
  settings, not per-request — if some requests should pay out in a different
  asset, you'll need to extend the config to be per-network/per-token.
- There's no automatic retry if a transaction broadcasts successfully but the
  follow-up call to `/approve` fails (e.g. API hiccup) — the Activity Log will
  still show the transaction hash so you can call `/approve` manually with it,
  or extend the code to retry that step.
