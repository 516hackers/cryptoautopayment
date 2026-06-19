#!/usr/bin/env python3
"""
Infinity Meta Hub  v2.0.0
==========================
Single-file desktop admin app.
Developed by Ayamil Coders

Double-payment protection: if the on-chain send succeeds but the API
approve call fails (network hiccup etc.), the tx_hash is stored locally
in pending_tx.json.  On the next approve attempt the app detects the
stored hash, skips the chain send entirely, and only retries the API call.

Wallet Balances tab scans BOTH Polygon (chain 137) and BSC (chain 56)
simultaneously for native coins and all known tokens.

API routes used (AdminWithdrawalController):
  GET  /                → list all
  GET  /pending         → list pending (FIFO)
  GET  /stats           → summary counts
  POST /{id}/approve    → { transaction_hash, admin_note }
  POST /{id}/reject     → { admin_note }
"""

import os, sys, json, base64, threading, traceback, webbrowser
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from web3 import Web3

try:
    from web3.middleware import geth_poa_middleware
except ImportError:
    geth_poa_middleware = None

# ── App constants ─────────────────────────────────────────────────────
APP_TITLE   = "Infinity Meta Hub"
APP_VERSION = "2.0.0"
APP_CREDIT  = "Developed By Ayamil Coders"
CONFIG_DIR  = os.path.join(os.path.expanduser("~"), ".withdrawal_admin")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
PENDING_TX_PATH = os.path.join(CONFIG_DIR, "pending_tx.json")
SHOW_ZERO_BAL_DEFAULT = False

# ── Multi-RPC network definitions for balance scanning ───────────────
# Both Polygon (137) and BSC (56) are always scanned.
SCAN_NETWORKS = {
    "polygon": {
        "label":    "Polygon  (Chain 137)",
        "chain_id": 137,
        "native":   "MATIC",
        "explorer": "https://polygonscan.com",
        "rpcs": [
            "https://polygon-rpc.com",
            "https://rpc-mainnet.maticvigil.com",
            "https://polygon-bor-rpc.publicnode.com",
            "https://rpc.ankr.com/polygon",
        ],
        "tokens": [
            {"symbol": "BH",    "address": "0x68a6EA8e9aB0824251061DD122aDA8493e62409d", "decimals": 18},
            {"symbol": "USDT",  "address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "decimals": 6},
            {"symbol": "USDC",  "address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", "decimals": 6},
            {"symbol": "DAI",   "address": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", "decimals": 18},
            {"symbol": "WETH",  "address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "decimals": 18},
            {"symbol": "WBTC",  "address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "decimals": 8},
            {"symbol": "WMATIC","address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "decimals": 18},
        ],
    },
    "bsc": {
        "label":    "BNB Smart Chain  (Chain 56)",
        "chain_id": 56,
        "native":   "BNB",
        "explorer": "https://bscscan.com",
        "rpcs": [
            "https://bsc-dataseed.binance.org/",
            "https://bsc-dataseed1.binance.org/",
            "https://bsc-rpc.publicnode.com",
            "https://rpc.ankr.com/bsc",
        ],
        "tokens": [
            {"symbol": "USDT",  "address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
            {"symbol": "USDC",  "address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
            {"symbol": "BUSD",  "address": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "decimals": 18},
            {"symbol": "DAI",   "address": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3", "decimals": 18},
            {"symbol": "WBNB",  "address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "decimals": 18},
            {"symbol": "ETH",   "address": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "decimals": 18},
            {"symbol": "BTCB",  "address": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "decimals": 18},
        ],
    },
}

# ── Payout network presets (for sending, not scanning) ───────────────
NETWORK_PRESETS = {
    "polygon_bh": {
        "label":          "Polygon — BH Token  (sends net_amount_bh)",
        "chain_id":       137,
        "token_contract": "0x68a6EA8e9aB0824251061DD122aDA8493e62409d",
        "decimals":       18,
        "default_rpc":    "https://polygon-rpc.com",
        "explorer_tx":    "https://polygonscan.com/tx/",
        "native_symbol":  "MATIC",
        "amount_source":  "bh",
    },
    "polygon_usdt": {
        "label":          "Polygon — USDT  (sends net_amount_usd)",
        "chain_id":       137,
        "token_contract": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "decimals":       6,
        "default_rpc":    "https://polygon-rpc.com",
        "explorer_tx":    "https://polygonscan.com/tx/",
        "native_symbol":  "MATIC",
        "amount_source":  "usd",
    },
    "bsc_usdt": {
        "label":          "BSC — USDT  (sends net_amount_usd)",
        "chain_id":       56,
        "token_contract": "0x55d398326f99059fF775485246999027B3197955",
        "decimals":       18,
        "default_rpc":    "https://bsc-dataseed.binance.org/",
        "explorer_tx":    "https://bscscan.com/tx/",
        "native_symbol":  "BNB",
        "amount_source":  "usd",
    },
}

DEFAULT_CONFIG = {
    "api_base_url":   "https://yourdomain.com/api/v1/admin/withdrawals",
    "auth_header":    "",
    "network":        "polygon_bh",
    "rpc_url":        NETWORK_PRESETS["polygon_bh"]["default_rpc"],
    "token_contract": NETWORK_PRESETS["polygon_bh"]["token_contract"],
    "decimals":       NETWORK_PRESETS["polygon_bh"]["decimals"],
    "amount_source":  "bh",
    "from_address":   "",
    "simulate_only":  True,
    "pk_set":         False,
    "pk_salt":        "",
    "pk_token":       "",
    "extra_tokens":   [],
}

# ── ERC-20 ABI (minimal) ─────────────────────────────────────────────
ERC20_ABI = [
    {"constant": True,  "inputs": [], "name": "name",
     "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True,  "inputs": [], "name": "symbol",
     "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True,  "inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True,  "inputs": [{"name": "_owner", "type": "address"}],
     "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": False,
     "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
     "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
]

# ═══════════════════════════════════════════════════════════════════════
#  Pending-TX store  — double-payment prevention
# ═══════════════════════════════════════════════════════════════════════

class PendingTxStore:
    """
    Persists {withdrawal_id: {tx_hash, ...}} for transactions where the
    on-chain send succeeded but the API /approve call failed.

    On the next Approve attempt we:
      1. Check get(wid) — if found, skip chain.send_token() entirely
      2. Retry only the api.approve() call with the stored hash
      3. On API success, call remove(wid)

    This guarantees each withdrawal is paid on-chain at most once.
    """

    @staticmethod
    def _load() -> dict:
        try:
            with open(PENDING_TX_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _write(data: dict):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(PENDING_TX_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def get(cls, wid) -> dict:
        return cls._load().get(str(wid))

    @classmethod
    def put(cls, wid, tx_hash: str, to_addr: str, amount: float, network: str):
        data = cls._load()
        data[str(wid)] = {
            "tx_hash":  tx_hash,
            "to_addr":  to_addr,
            "amount":   amount,
            "network":  network,
            "sent_at":  datetime.now().isoformat(),
        }
        cls._write(data)

    @classmethod
    def remove(cls, wid):
        data = cls._load()
        data.pop(str(wid), None)
        cls._write(data)

    @classmethod
    def all(cls) -> dict:
        return cls._load()

# ═══════════════════════════════════════════════════════════════════════
#  Crypto helpers
# ═══════════════════════════════════════════════════════════════════════

def _derive_key(pw: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000)
    return base64.urlsafe_b64encode(kdf.derive(pw.encode()))

def encrypt_secret(plain: str, pw: str):
    salt  = os.urandom(16)
    token = Fernet(_derive_key(pw, salt)).encrypt(plain.encode())
    return base64.b64encode(salt).decode(), token.decode()

def decrypt_secret(salt_b64: str, token: str, pw: str) -> str:
    salt = base64.b64decode(salt_b64)
    return Fernet(_derive_key(pw, salt)).decrypt(token.encode()).decode()

# ═══════════════════════════════════════════════════════════════════════
#  Config store
# ═══════════════════════════════════════════════════════════════════════

class ConfigStore:
    @staticmethod
    def load() -> dict:
        cfg = dict(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except Exception:
                pass
        return cfg

    @staticmethod
    def save(cfg: dict):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    @staticmethod
    def delete():
        for p in (CONFIG_PATH, PENDING_TX_PATH):
            if os.path.exists(p):
                os.remove(p)

# ═══════════════════════════════════════════════════════════════════════
#  API client
# ═══════════════════════════════════════════════════════════════════════

class ApiError(Exception): pass

class ApiClient:
    def __init__(self, base_url: str, auth: str):
        self.base_url = (base_url or "").rstrip("/")
        self.auth     = auth or ""
        self.session  = requests.Session()

    def _h(self):
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.auth:
            h["Authorization"] = self.auth
        return h

    def _req(self, method, path, params=None, body=None):
        if not self.base_url:
            raise ApiError("API Base URL not set — go to Wallet & API Settings.")
        try:
            r = self.session.request(method, self.base_url + path,
                                     headers=self._h(), params=params, json=body, timeout=20)
        except requests.RequestException as e:
            raise ApiError(f"Network error calling API: {e}")
        try:
            data = r.json()
        except ValueError:
            raise ApiError(f"Non-JSON response (HTTP {r.status_code})")
        if r.status_code >= 400 or data.get("success") is False:
            raise ApiError(data.get("message") or f"API error (HTTP {r.status_code})")
        return data

    def list_all(self, status=None, per_page=500):
        p = {"per_page": per_page}
        if status and status != "all":
            p["status"] = status
        d = self._req("GET", "/", params=p)
        return d.get("data", {}).get("data", d.get("data", []))

    def list_pending(self, per_page=500):
        d = self._req("GET", "/pending", params={"per_page": per_page})
        return d.get("data", {}).get("data", d.get("data", []))

    def stats(self):
        return self._req("GET", "/stats").get("data", {})

    def approve(self, wid, tx_hash: str, note: str = ""):
        return self._req("POST", f"/{wid}/approve",
                         body={"transaction_hash": tx_hash, "admin_note": note})

    def reject(self, wid, note: str):
        return self._req("POST", f"/{wid}/reject", body={"admin_note": note})

# ═══════════════════════════════════════════════════════════════════════
#  Chain client  — all on-chain logic lives here
# ═══════════════════════════════════════════════════════════════════════

class ChainError(Exception): pass

class ChainClient:
    def __init__(self, rpc_url: str):
        if not rpc_url:
            raise ChainError("RPC URL not configured.")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if geth_poa_middleware:
            try:
                self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            except Exception:
                pass
        if not self.w3.is_connected():
            raise ChainError(f"Cannot connect to RPC: {rpc_url}")

    @classmethod
    def from_rpcs(cls, rpcs: list) -> "ChainClient":
        """Try multiple RPC endpoints and return the first that connects."""
        errors = []
        for rpc in rpcs:
            try:
                return cls(rpc)
            except ChainError as e:
                errors.append(f"{rpc}: {e}")
        raise ChainError("All RPC endpoints failed:\n" + "\n".join(errors))

    def cs(self, addr: str) -> str:
        try:
            return Web3.to_checksum_address(addr)
        except Exception:
            raise ChainError(f"Invalid address: {addr}")

    def native_balance(self, address: str) -> float:
        return float(self.w3.from_wei(self.w3.eth.get_balance(self.cs(address)), "ether"))

    def token_balance(self, contract: str, wallet: str, decimals: int) -> float:
        c = self.w3.eth.contract(address=self.cs(contract), abi=ERC20_ABI)
        return c.functions.balanceOf(self.cs(wallet)).call() / (10 ** decimals)

    def token_info(self, contract: str):
        try:
            c = self.w3.eth.contract(address=self.cs(contract), abi=ERC20_ABI)
            return c.functions.symbol().call(), int(c.functions.decimals().call())
        except Exception:
            return "???", 18

    def next_nonce(self, address: str) -> int:
        return self.w3.eth.get_transaction_count(self.cs(address), "pending")

    def chain_id(self) -> int:
        return self.w3.eth.chain_id

    def send_token(self, private_key: str, from_addr: str, to_addr: str,
                   amount: float, contract_addr: str, decimals: int,
                   chain_id: int, nonce: int) -> str:
        """
        Build, sign and broadcast one ERC-20 transfer.
        Returns the transaction hash hex string.
        All validation, gas estimation, and signing done here.
        """
        from eth_account import Account

        from_cs     = self.cs(from_addr)
        to_cs       = self.cs(to_addr)
        contract_cs = self.cs(contract_addr)

        acct = Account.from_key(private_key)
        if acct.address.lower() != from_cs.lower():
            raise ChainError(
                f"Private key address ({acct.address}) does not match "
                f"configured From address ({from_cs})."
            )

        units = int(round(amount * (10 ** decimals)))
        if units <= 0:
            raise ChainError(f"Amount rounds to zero ({amount} × 10^{decimals})")

        try:
            gas_price = self.w3.eth.gas_price
        except Exception:
            gas_price = self.w3.to_wei(30, "gwei")

        contract = self.w3.eth.contract(address=contract_cs, abi=ERC20_ABI)
        tx = contract.functions.transfer(to_cs, units).build_transaction({
            "chainId":  chain_id,
            "gas":      300_000,
            "gasPrice": gas_price,
            "nonce":    nonce,
            "from":     from_cs,
        })

        try:
            estimated = self.w3.eth.estimate_gas(tx)
            tx["gas"] = int(estimated * 1.3)
        except Exception:
            pass

        signed = acct.sign_transaction(tx)
        raw    = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
        return self.w3.to_hex(self.w3.eth.send_raw_transaction(raw))

# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def fmt(n, places=4):
    try:    return f"{float(n):,.{places}f}"
    except: return str(n)

def fmt_usd(n):
    try:    return f"${float(n):,.2f}"
    except: return str(n)

def _write_crash_log(text: str) -> str:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        p = os.path.join(CONFIG_DIR, "crash.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now().isoformat()} ---\n{text}\n")
        return p
    except Exception:
        return ""

def _show_fatal(text: str):
    log_path = _write_crash_log(text)
    suffix   = f"\n\nLog: {log_path}" if log_path else ""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, text[:1500] + suffix, f"{APP_TITLE} — Fatal Error", 0x10)
            return
        except Exception:
            pass
    try:
        print(text, file=sys.stderr)
    except Exception:
        pass

# ── Passphrase dialog ─────────────────────────────────────────────────

class PassphraseDialog(simpledialog.Dialog):
    def __init__(self, parent, title, confirm=False):
        self.confirm = confirm
        self.value   = None
        super().__init__(parent, title)

    def body(self, m):
        tk.Label(m, text="Passphrase:").grid(row=0, column=0, sticky="w", pady=4)
        self.e1 = tk.Entry(m, show="*", width=36)
        self.e1.grid(row=0, column=1, pady=4)
        if self.confirm:
            tk.Label(m, text="Confirm:").grid(row=1, column=0, sticky="w", pady=4)
            self.e2 = tk.Entry(m, show="*", width=36)
            self.e2.grid(row=1, column=1, pady=4)
        return self.e1

    def validate(self):
        p = self.e1.get()
        if not p:
            messagebox.showwarning("Required", "Passphrase cannot be empty.", parent=self)
            return False
        if self.confirm and p != self.e2.get():
            messagebox.showwarning("Mismatch", "Passphrases do not match.", parent=self)
            return False
        self.value = p
        return True

def ask_pass(parent, title="Enter Passphrase", confirm=False):
    return PassphraseDialog(parent, title, confirm=confirm).value

# ── Scrollable frame ──────────────────────────────────────────────────

def make_scrollable(parent) -> tk.Frame:
    canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
    vsb    = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner  = tk.Frame(canvas)
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
    return inner

# ═══════════════════════════════════════════════════════════════════════
#  Treeview column definitions
# ═══════════════════════════════════════════════════════════════════════

COLS  = ("id","user_id","gross_bh","fee_bh","net_bh","net_usd","wallet","status","created_at")
HEADS = ("ID","User","Gross BH","Fee BH","Net BH","Net USD","Wallet Address","Status","Created")
WIDTHS = (55, 110, 100, 90, 100, 100, 260, 80, 140)

# ═══════════════════════════════════════════════════════════════════════
#  Main application
# ═══════════════════════════════════════════════════════════════════════

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE}  v{APP_VERSION}  —  {APP_CREDIT}")
        self.root.geometry("1280x760")
        self.root.minsize(960, 600)

        self.cfg        = ConfigStore.load()
        self.api        = ApiClient(self.cfg["api_base_url"], self.cfg["auth_header"])
        self.runtime_pk = None

        self.all_records     = []
        self.pending_records = []

        self.var_simulate    = tk.BooleanVar(value=self.cfg.get("simulate_only", True))
        self._show_zero      = SHOW_ZERO_BAL_DEFAULT
        self._last_bal_res   = {}

        self._build_ui()
        self.refresh_all(silent=True)
        self.refresh_pending(silent=True)

    # ── thread helpers ────────────────────────────────────────────────

    def ui(self, fn):
        self.root.after(0, fn)

    def run_bg(self, fn, on_done=None, on_error=None):
        def wrapper():
            try:
                result = fn()
                if on_done:
                    self.ui(lambda r=result: on_done(r))
            except Exception as exc:
                cap = exc
                if on_error:
                    self.ui(lambda e=cap: on_error(e))
                else:
                    self.ui(lambda e=cap: messagebox.showerror("Error", str(e)))
        threading.Thread(target=wrapper, daemon=True).start()

    def _get_pk(self):
        if self.runtime_pk:
            return self.runtime_pk
        if self.cfg.get("pk_set"):
            pw = ask_pass(self.root, "Unlock Wallet Key")
            if not pw:
                raise ChainError("Passphrase required.")
            try:
                pk = decrypt_secret(self.cfg["pk_salt"], self.cfg["pk_token"], pw)
            except Exception:
                raise ChainError("Wrong passphrase or corrupted key.")
            self.runtime_pk = pk
            return pk
        raise ChainError("No wallet key — go to Wallet & API Settings.")

    def _new_chain(self) -> ChainClient:
        preset = NETWORK_PRESETS.get(self.cfg["network"], {})
        # Try configured RPC first, then Polygon fallbacks if it matches polygon
        rpcs = [self.cfg["rpc_url"]]
        if "polygon" in self.cfg["network"]:
            rpcs += SCAN_NETWORKS["polygon"]["rpcs"]
        else:
            rpcs += SCAN_NETWORKS["bsc"]["rpcs"]
        return ChainClient.from_rpcs(list(dict.fromkeys(rpcs)))  # dedup, preserve order

    def _set_api(self):
        self.api = ApiClient(self.cfg["api_base_url"], self.cfg["auth_header"])

    # ── UI skeleton ───────────────────────────────────────────────────

    def _build_ui(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)

        self.tab_all      = ttk.Frame(self.nb)
        self.tab_pending  = ttk.Frame(self.nb)
        self.tab_balances = ttk.Frame(self.nb)
        self.tab_settings = ttk.Frame(self.nb)

        self.nb.add(self.tab_all,      text="  All Withdrawals  ")
        self.nb.add(self.tab_pending,  text="  Pending  ")
        self.nb.add(self.tab_balances, text="  Wallet Balances  ")
        self.nb.add(self.tab_settings, text="  Wallet & API Settings  ")

        # ── footer ──
        footer = tk.Frame(self.root, bg="#1a237e", pady=3)
        footer.pack(fill="x", side="bottom")
        tk.Label(footer, text=f"  {APP_CREDIT}  •  {APP_TITLE} v{APP_VERSION}",
                 bg="#1a237e", fg="#ffffff", font=("TkDefaultFont", 8)).pack(side="left")
        tk.Label(footer, text="Simulation mode is ON by default — go to Settings to enable LIVE  ",
                 bg="#1a237e", fg="#aab4e8", font=("TkDefaultFont", 8)).pack(side="right")

        self._build_all_tab()
        self._build_pending_tab()
        self._build_balances_tab()
        self._build_settings_tab()

    # ── shared: tree ──────────────────────────────────────────────────

    def _make_tree(self, parent):
        wrap = ttk.Frame(parent)
        tree = ttk.Treeview(wrap, columns=COLS, show="headings", selectmode="extended")
        for col, head, w in zip(COLS, HEADS, WIDTHS):
            tree.heading(col, text=head,
                         command=lambda c=col: self._sort_tree(tree, c, False))
            tree.column(col, width=w, minwidth=50, anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal",  command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0,  column=1, sticky="ns")
        hsb.grid(row=1,  column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        tree.tag_configure("approved", background="#e6f4ea")
        tree.tag_configure("rejected", background="#fce8e6")
        tree.tag_configure("pending",  background="#fff8e1")
        return wrap, tree

    def _sort_tree(self, tree, col, reverse):
        data = [(tree.set(k, col), k) for k in tree.get_children("")]
        try:
            data.sort(key=lambda t: float(t[0].replace(",","").replace("$","")), reverse=reverse)
        except ValueError:
            data.sort(key=lambda t: t[0], reverse=reverse)
        for idx, (_, k) in enumerate(data):
            tree.move(k, "", idx)
        tree.heading(col, command=lambda: self._sort_tree(tree, col, not reverse))

    @staticmethod
    def _row_values(rec):
        return (
            rec.get("id"),
            rec.get("user_id"),
            fmt(rec.get("gross_amount_bh", 0)),
            fmt(rec.get("platform_fee_bh", 0)),
            fmt(rec.get("net_amount_bh",   0)),
            fmt_usd(rec.get("net_amount_usd", 0)),
            rec.get("wallet_address"),
            rec.get("status"),
            (rec.get("created_at") or "")[:19],
        )

    def _populate_tree(self, tree, records):
        for row in tree.get_children():
            tree.delete(row)
        for rec in records:
            tag = rec.get("status", "pending")
            tree.insert("", "end", iid=str(rec.get("id")),
                        values=self._row_values(rec), tags=(tag,))

    # ══════════════════════════════════════════════════════════════════
    #  TAB 1 — All Withdrawals
    # ══════════════════════════════════════════════════════════════════

    def _build_all_tab(self):
        bar = ttk.Frame(self.tab_all, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="Status:").pack(side="left")
        self.var_all_status = tk.StringVar(value="all")
        cb = ttk.Combobox(bar, textvariable=self.var_all_status, state="readonly",
                          values=["all","pending","approved","rejected"], width=11)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_all())
        ttk.Button(bar, text="⟳ Refresh",   command=self.refresh_all).pack(side="left", padx=4)
        ttk.Button(bar, text="View Details", command=self._all_details).pack(side="left", padx=4)
        self.all_stats = ttk.Label(bar, text="Stats: loading…", foreground="#555")
        self.all_stats.pack(side="left", padx=16)
        wrap, self.all_tree = self._make_tree(self.tab_all)
        wrap.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.all_tree.bind("<Double-1>", lambda e: self._all_details())

    def refresh_all(self, silent=False):
        self._set_api()
        sv = getattr(self, "var_all_status", None)
        status = sv.get() if sv else "all"

        def work():
            records = self.api.list_all(status=status)
            try:    st = self.api.stats()
            except: st = {}
            return records, st

        def done(res):
            records, st = res
            self.all_records = records
            self._populate_tree(self.all_tree, records)
            if st:
                self.all_stats.config(text=(
                    f"Total: {st.get('total_requests',0)}  │  "
                    f"Pending: {st.get('pending_count',0)}  │  "
                    f"Approved: {st.get('approved_count',0)}  │  "
                    f"Rejected: {st.get('rejected_count',0)}  │  "
                    f"Pending USD: {fmt_usd(st.get('pending_usd',0))}  │  "
                    f"Paid USD: {fmt_usd(st.get('total_paid_usd',0))}"
                ))

        def err(e):
            if not silent:
                messagebox.showerror("Failed to load withdrawals", str(e))
            self.all_stats.config(text="Stats: unavailable")

        self.run_bg(work, on_done=done, on_error=err)

    def _all_details(self):
        sel = self.all_tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Click a row first.")
            return
        rec = next((r for r in self.all_records if str(r.get("id")) == sel[0]), None)
        if rec:
            self._record_popup(rec)

    def _record_popup(self, rec):
        win = tk.Toplevel(self.root)
        win.title(f"Withdrawal #{rec.get('id')}")
        win.geometry("480x460")
        win.grab_set()
        t   = tk.Text(win, wrap="word", font=("Consolas", 9))
        vsb = ttk.Scrollbar(win, command=t.yview)
        t.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        t.pack(fill="both", expand=True, padx=6, pady=6)
        # highlight if there's a pending tx stored for this withdrawal
        stored = PendingTxStore.get(rec.get("id"))
        if stored:
            t.insert("end",
                f"⚠ PENDING TX STORED (sent but API not confirmed):\n"
                f"  tx_hash : {stored['tx_hash']}\n"
                f"  sent_at : {stored['sent_at']}\n"
                f"  to_addr : {stored['to_addr']}\n\n",
                "warn")
            t.tag_configure("warn", foreground="#a13a00", font=("Consolas", 9, "bold"))
        for k, v in rec.items():
            t.insert("end", f"{k:25s}: {v}\n")
        t.config(state="disabled")

    # ══════════════════════════════════════════════════════════════════
    #  TAB 2 — Pending
    # ══════════════════════════════════════════════════════════════════

    def _build_pending_tab(self):
        p = self.tab_pending

        bar = ttk.Frame(p, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="⟳ Refresh",          command=self.refresh_pending).pack(side="left", padx=3)
        ttk.Button(bar, text="✔ Approve Selected",  command=self.approve_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="✖ Reject Selected",   command=self.reject_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="✔✔ Approve ALL",      command=self.approve_all).pack(side="left", padx=3)
        ttk.Button(bar, text="⚠ Pending TX Store",  command=self._show_pending_store).pack(side="left", padx=3)

        self.pending_mode_lbl = tk.Label(bar, text="", font=("TkDefaultFont", 9, "bold"),
                                         padx=10, pady=2, relief="solid", bd=1)
        self.pending_mode_lbl.pack(side="left", padx=12)
        self.var_simulate.trace_add("write", lambda *_: self._update_mode_badge())
        self._update_mode_badge()

        bar2 = ttk.Frame(p, padding=(8, 0))
        bar2.pack(fill="x")
        self.pending_summary = ttk.Label(
            bar2,
            text="Pending: 0  │  Total Net BH: 0.0000  │  Total Net USD: $0.00",
            font=("TkDefaultFont", 10, "bold"), foreground="#333")
        self.pending_summary.pack(side="left")

        wrap, self.pending_tree = self._make_tree(p)
        wrap.pack(fill="both", expand=True, padx=6, pady=4)
        self.pending_tree.bind("<Double-1>", lambda e: self._pending_details())

        log_frame = ttk.LabelFrame(p, text="Activity Log", padding=4)
        log_frame.pack(fill="x", padx=6, pady=(0, 6))
        self.log_text = tk.Text(log_frame, height=9, wrap="word",
                                state="disabled", font=("Consolas", 9))
        log_vsb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_vsb.grid(row=0, column=1, sticky="ns")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text.tag_configure("link",   foreground="#0055cc", underline=1)
        self.log_text.tag_configure("ok",     foreground="#2e7d32")
        self.log_text.tag_configure("fail",   foreground="#c62828")
        self.log_text.tag_configure("sim",    foreground="#e65100")
        self.log_text.tag_configure("stored", foreground="#7b1fa2", font=("Consolas", 9, "bold"))

    def _update_mode_badge(self):
        if self.var_simulate.get():
            self.pending_mode_lbl.config(text="🟡  SIMULATION", bg="#fff3cd", fg="#856404")
        else:
            self.pending_mode_lbl.config(text="🔴  LIVE MODE",  bg="#f8d7da", fg="#721c24")

    def log(self, msg: str, url: str = "", tag: str = ""):
        def do():
            self.log_text.config(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] ")
            self.log_text.insert("end", msg, tag or "")
            if url:
                start = self.log_text.index("end-1c")
                self.log_text.insert("end", f"  ↗ {url}")
                end = self.log_text.index("end-1c")
                self.log_text.tag_add("link", start, end)
                self.log_text.tag_bind("link", "<Button-1>",
                                       lambda e, u=url: webbrowser.open(u))
            self.log_text.insert("end", "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.ui(do)

    def _show_pending_store(self):
        store = PendingTxStore.all()
        win   = tk.Toplevel(self.root)
        win.title("Pending TX Store  (sent but API not confirmed)")
        win.geometry("720x360")
        win.grab_set()
        t   = tk.Text(win, wrap="word", font=("Consolas", 9))
        vsb = ttk.Scrollbar(win, command=t.yview)
        t.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        t.pack(fill="both", expand=True, padx=6, pady=6)
        if not store:
            t.insert("end", "✓ No pending transactions — all API calls confirmed.\n\n"
                            "This means no double payments are possible.\n")
        else:
            t.insert("end",
                "⚠ The following withdrawal IDs have an on-chain TX already sent\n"
                "  but the API /approve call has not been confirmed yet.\n"
                "  Click 'Approve' again — the app will skip the chain send\n"
                "  and only retry the API call.\n\n")
            for wid, info in store.items():
                t.insert("end", f"Withdrawal #{wid}:\n")
                for k, v in info.items():
                    t.insert("end", f"  {k:10s}: {v}\n")
                t.insert("end", "\n")
        t.config(state="disabled")

    def refresh_pending(self, silent=False):
        self._set_api()

        def work():
            return self.api.list_pending()

        def done(records):
            self.pending_records = records
            self._populate_tree(self.pending_tree, records)
            # Highlight rows that have a stored tx (payment sent, API not confirmed)
            stored_ids = set(PendingTxStore.all().keys())
            for rec in records:
                rid = str(rec.get("id"))
                if rid in stored_ids:
                    # mark the row to alert the admin
                    try:
                        self.pending_tree.item(rid, tags=("stored_tx",))
                    except Exception:
                        pass
            self.pending_tree.tag_configure("stored_tx", background="#f3e5f5")

            total_bh  = sum(float(r.get("net_amount_bh",  0) or 0) for r in records)
            total_usd = sum(float(r.get("net_amount_usd", 0) or 0) for r in records)
            self.pending_summary.config(
                text=f"Pending: {len(records)}  │  "
                     f"Total Net BH: {fmt(total_bh)}  │  "
                     f"Total Net USD: {fmt_usd(total_usd)}"
            )

        def err(e):
            if not silent:
                messagebox.showerror("Failed to load pending", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    def _pending_details(self):
        sel = self.pending_tree.selection()
        if not sel:
            return
        rec = next((r for r in self.pending_records if str(r.get("id")) == sel[0]), None)
        if rec:
            self._record_popup(rec)

    def _selected_pending(self):
        sel  = self.pending_tree.selection()
        recs = [r for r in self.pending_records if str(r.get("id")) in sel]
        if not recs:
            messagebox.showinfo("Nothing selected",
                                "Click one or more rows in the Pending list first.")
        return recs

    def reject_selected(self):
        recs = self._selected_pending()
        if not recs:
            return
        note = simpledialog.askstring(
            "Reject", f"Reason for rejecting {len(recs)} withdrawal(s):", parent=self.root)
        if not note:
            messagebox.showwarning("Cancelled", "A rejection reason is required.")
            return
        self._set_api()

        def work():
            for r in recs:
                try:
                    self.api.reject(r["id"], note)
                    self.log(f"#{r['id']}: Rejected.", tag="ok")
                except ApiError as e:
                    self.log(f"#{r['id']}: Reject FAILED — {e}", tag="fail")

        self.run_bg(work, on_done=lambda _: (self.refresh_pending(), self.refresh_all()))

    def approve_selected(self):
        recs = self._selected_pending()
        if recs:
            self._approve_batch(recs)

    def approve_all(self):
        if not self.pending_records:
            messagebox.showinfo("Nothing to do", "No pending withdrawals loaded.")
            return
        self._approve_batch(list(self.pending_records))

    def _approve_batch(self, recs: list):
        """
        ─── Double-payment protection ───────────────────────────────────
        For each withdrawal we check PendingTxStore first:
          • STORED  → tx already sent; skip chain.send_token(), retry API only
          • NOT STORED, SIMULATE → fake hash, no chain call
          • NOT STORED, LIVE → send on chain; SAVE to store BEFORE api.approve();
                               remove from store AFTER api.approve() succeeds

        This guarantees that even if the admin clicks Approve multiple times,
        the on-chain transfer happens exactly once per withdrawal.
        ─────────────────────────────────────────────────────────────────
        """
        cfg          = self.cfg
        amount_field = "net_amount_bh" if cfg["amount_source"] == "bh" else "net_amount_usd"
        total        = sum(float(r.get(amount_field, 0) or 0) for r in recs)
        simulate     = self.var_simulate.get()
        mode_str     = "SIMULATION — no real funds will move" if simulate else "⚠ LIVE — REAL FUNDS WILL BE SENT"

        if not cfg["from_address"]:
            messagebox.showwarning("Missing", "Set 'From Wallet Address' in Settings first.")
            return

        # Check for already-stored (partially-sent) withdrawals
        stored_ids = [str(r["id"]) for r in recs if PendingTxStore.get(r["id"])]
        stored_msg = ""
        if stored_ids:
            stored_msg = (
                f"\n\n⚠ {len(stored_ids)} withdrawal(s) already have an on-chain TX stored "
                f"(IDs: {', '.join(stored_ids)}).\n"
                f"The app will SKIP the chain send for these and only retry the API call."
            )

        if not messagebox.askyesno(
            "Confirm Approval",
            f"Mode: {mode_str}\n\n"
            f"Approve {len(recs)} withdrawal(s)?\n"
            f"Total {amount_field}: {fmt(total, 4)}\n"
            f"From wallet: {cfg['from_address']}"
            f"{stored_msg}"
        ):
            return

        pk = None
        if not simulate:
            try:
                pk = self._get_pk()
            except ChainError as e:
                messagebox.showerror("Key required", str(e))
                return

        self._set_api()
        preset   = NETWORK_PRESETS.get(cfg["network"], {})
        chain_id = preset.get("chain_id", 137)
        explorer = preset.get("explorer_tx", "")

        self.log(
            f"Batch start: {len(recs)} withdrawal(s)  |  "
            f"{'SIMULATE' if simulate else 'LIVE'}  |  "
            f"network={cfg['network']}",
            tag="sim" if simulate else "fail"
        )

        def work():
            chain = None
            nonce = None
            if not simulate:
                chain = self._new_chain()
                nonce = chain.next_nonce(cfg["from_address"])

            for rec in recs:
                rid     = rec.get("id")
                to_addr = rec.get("wallet_address", "")
                try:
                    amount = float(rec.get(amount_field, 0) or 0)
                    if amount <= 0:
                        raise ChainError(f"{amount_field}={amount} — cannot send zero.")

                    # ── DOUBLE-PAYMENT CHECK ──────────────────────────
                    stored = PendingTxStore.get(rid)

                    if stored:
                        # Payment already sent on-chain; skip the send entirely
                        tx_hash = stored["tx_hash"]
                        self.log(
                            f"#{rid}: ⚠ Existing TX found (sent {stored['sent_at'][:19]}). "
                            f"Skipping chain send — retrying API only.  tx={tx_hash[:20]}…",
                            tag="stored"
                        )
                    elif simulate:
                        tx_hash = "SIMULATED-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                        self.log(
                            f"#{rid}: [SIM] would send {fmt(amount,4)} → {to_addr}",
                            tag="sim")
                    else:
                        # Send on chain
                        tx_hash = chain.send_token(
                            private_key   = pk,
                            from_addr     = cfg["from_address"],
                            to_addr       = to_addr,
                            amount        = amount,
                            contract_addr = cfg["token_contract"],
                            decimals      = cfg["decimals"],
                            chain_id      = chain_id,
                            nonce         = nonce,
                        )
                        nonce += 1
                        # ── CRITICAL: save BEFORE the API call ───────
                        # If the API call fails, we can retry without re-sending
                        PendingTxStore.put(rid, tx_hash, to_addr, amount, cfg["network"])
                        url = explorer + tx_hash if explorer else ""
                        self.log(
                            f"#{rid}: ✓ Sent {fmt(amount,4)} → {to_addr}  tx={tx_hash}",
                            url=url, tag="ok")

                    # ── API approve call ──────────────────────────────
                    self.api.approve(
                        rid, tx_hash,
                        note=(f"{'SIMULATED' if simulate else cfg['network']}. "
                              f"{amount_field}={fmt(amount,4)}.")
                    )

                    # ── Only remove from store after API succeeds ─────
                    PendingTxStore.remove(rid)
                    self.log(f"#{rid}: ✓ Marked APPROVED in backend.", tag="ok")

                except Exception as exc:
                    self.log(f"#{rid}: FAILED — {exc}", tag="fail")
                    # Keep in PendingTxStore (if stored) so admin can retry API

        def done(_):
            self.log("Batch complete.", tag="ok")
            self.refresh_pending()
            self.refresh_all()
            messagebox.showinfo("Done", "Batch complete. See Activity Log.")

        self.run_bg(work, on_done=done)

    # ══════════════════════════════════════════════════════════════════
    #  TAB 3 — Wallet Balances (Polygon + BSC simultaneously)
    # ══════════════════════════════════════════════════════════════════

    def _build_balances_tab(self):
        p = self.tab_balances

        bar = ttk.Frame(p, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="⟳ Refresh All Networks",
                   command=self.refresh_balances).pack(side="left", padx=4)
        ttk.Button(bar, text="+ Add Custom Token",
                   command=self._add_watch_token).pack(side="left", padx=4)
        ttk.Button(bar, text="Show/Hide Zero Balances",
                   command=self._toggle_zero_bal).pack(side="left", padx=4)
        self.bal_status = ttk.Label(bar,
            text="Click 'Refresh' — scans Polygon (137) + BSC (56) simultaneously",
            foreground="#555")
        self.bal_status.pack(side="left", padx=12)

        addr_f = ttk.LabelFrame(p,
            text="Hot Wallet Address  (same address checked on Polygon AND BSC)",
            padding=6)
        addr_f.pack(fill="x", padx=8, pady=(4, 0))
        self.bal_addr_lbl = ttk.Label(addr_f,
            text=self.cfg.get("from_address") or "(not set — configure in Wallet & API Settings)",
            font=("Consolas", 10), foreground="#1a237e")
        self.bal_addr_lbl.pack(anchor="w")

        # Scrollable cards area
        cards_outer = ttk.Frame(p)
        cards_outer.pack(fill="both", expand=True, padx=8, pady=6)
        self.bal_canvas = tk.Canvas(cards_outer, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(cards_outer, orient="vertical", command=self.bal_canvas.yview)
        self.bal_cards_inner = tk.Frame(self.bal_canvas)
        self.bal_cards_inner.bind(
            "<Configure>",
            lambda e: self.bal_canvas.configure(scrollregion=self.bal_canvas.bbox("all")))
        self.bal_canvas.create_window((0, 0), window=self.bal_cards_inner, anchor="nw")
        self.bal_canvas.configure(yscrollcommand=vsb.set)
        self.bal_canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.bal_canvas.bind("<MouseWheel>",
            lambda e: self.bal_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Custom watched tokens list
        watch_f = ttk.LabelFrame(p, text="Custom Watched Tokens", padding=6)
        watch_f.pack(fill="x", padx=8, pady=(0, 6))
        cols_w  = ("symbol","contract","decimals","network")
        self.watch_tree = ttk.Treeview(watch_f, columns=cols_w, show="headings", height=4)
        for c, w in (("symbol",70),("contract",390),("decimals",70),("network",130)):
            self.watch_tree.heading(c, text=c.title())
            self.watch_tree.column(c, width=w, anchor="w")
        wsb = ttk.Scrollbar(watch_f, orient="vertical", command=self.watch_tree.yview)
        self.watch_tree.configure(yscrollcommand=wsb.set)
        self.watch_tree.grid(row=0, column=0, sticky="nsew")
        wsb.grid(row=0, column=1, sticky="ns")
        watch_f.rowconfigure(0, weight=1)
        watch_f.columnconfigure(0, weight=1)
        ttk.Button(watch_f, text="Remove Selected",
                   command=self._remove_watch_token).grid(row=1, column=0, sticky="w", pady=4)
        self._reload_watch_tree()

    def _toggle_zero_bal(self):
        self._show_zero = not self._show_zero
        if self._last_bal_res:
            self._render_all_network_cards(self._last_bal_res)

    def _reload_watch_tree(self):
        for row in self.watch_tree.get_children():
            self.watch_tree.delete(row)
        for t in self.cfg.get("extra_tokens", []):
            self.watch_tree.insert("", "end",
                values=(t.get("symbol","?"), t.get("address",""),
                        t.get("decimals",18), t.get("network","?")))

    def _add_watch_token(self):
        win = tk.Toplevel(self.root)
        win.title("Add Custom Watched Token")
        win.grab_set()
        win.geometry("440x200")
        win.resizable(False, False)

        ttk.Label(win, text="Network:").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        var_net = tk.StringVar(value="polygon")
        ttk.Combobox(win, textvariable=var_net, state="readonly",
                     values=list(SCAN_NETWORKS.keys()), width=22).grid(
            row=0, column=1, sticky="w", padx=8, pady=8)

        ttk.Label(win, text="Contract Address:").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        var_addr = tk.StringVar()
        ttk.Entry(win, textvariable=var_addr, width=44).grid(row=1, column=1, padx=8, pady=8)

        def _confirm():
            addr = var_addr.get().strip()
            net  = var_net.get()
            if not addr:
                messagebox.showwarning("Required", "Enter a contract address.", parent=win)
                return
            win.destroy()
            rpcs = SCAN_NETWORKS.get(net, {}).get("rpcs", [self.cfg.get("rpc_url","")])

            def work():
                try:
                    chain = ChainClient.from_rpcs(rpcs)
                    return chain.token_info(addr)
                except Exception:
                    return "???", 18

            def done(res):
                sym, dec = res
                sym = simpledialog.askstring("Symbol",
                    f"Token symbol (detected: {sym}):", initialvalue=sym, parent=self.root) or sym
                try:
                    dec = int(simpledialog.askstring("Decimals",
                        f"Decimals (detected: {dec}):", initialvalue=str(dec), parent=self.root) or dec)
                except Exception:
                    pass
                tokens = self.cfg.get("extra_tokens", [])
                tokens.append({"address": addr, "symbol": sym, "decimals": dec, "network": net})
                self.cfg["extra_tokens"] = tokens
                ConfigStore.save(self.cfg)
                self._reload_watch_tree()
                messagebox.showinfo("Added", f"{sym} added to {net} watchlist.")

            self.run_bg(work, on_done=done)

        ttk.Button(win, text="Detect & Add", command=_confirm).grid(
            row=2, column=1, sticky="w", padx=8, pady=12)

    def _remove_watch_token(self):
        sel = self.watch_tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Select a token row to remove.")
            return
        idx    = self.watch_tree.index(sel[0])
        tokens = self.cfg.get("extra_tokens", [])
        if 0 <= idx < len(tokens):
            removed = tokens.pop(idx)
            self.cfg["extra_tokens"] = tokens
            ConfigStore.save(self.cfg)
            self._reload_watch_tree()
            messagebox.showinfo("Removed", f"Removed {removed.get('symbol','token')}.")

    def refresh_balances(self):
        wallet = self.cfg.get("from_address", "").strip()
        self.bal_addr_lbl.config(
            text=wallet or "(not set — configure in Wallet & API Settings)")
        if not wallet:
            messagebox.showwarning("No wallet",
                "Set 'From Wallet Address' in Wallet & API Settings first.")
            return

        extras = list(self.cfg.get("extra_tokens", []))
        self.bal_status.config(
            text="⏳  Scanning Polygon (Chain 137) and BSC (Chain 56) simultaneously…")

        def _scan_network(net_key: str, net_cfg: dict):
            """Scan one network for native + all known tokens. Thread-safe."""
            items  = []
            rpcs   = net_cfg.get("rpcs", [])
            try:
                chain = ChainClient.from_rpcs(rpcs)
            except ChainError as e:
                items.append({"symbol": net_cfg["native"], "balance": None,
                               "error": str(e), "type": "native", "network": net_key})
                return net_key, items

            # Native coin
            try:
                items.append({"symbol": net_cfg["native"],
                               "balance": chain.native_balance(wallet),
                               "contract": "native", "type": "native", "network": net_key})
            except Exception as e:
                items.append({"symbol": net_cfg["native"], "balance": None,
                               "error": str(e), "type": "native", "network": net_key})

            # Known tokens
            for tok in net_cfg.get("tokens", []):
                try:
                    bal = chain.token_balance(tok["address"], wallet, tok["decimals"])
                    items.append({"symbol": tok["symbol"], "balance": bal,
                                   "contract": tok["address"], "decimals": tok["decimals"],
                                   "type": "known", "network": net_key})
                except Exception as e:
                    items.append({"symbol": tok["symbol"], "balance": None,
                                   "error": str(e), "contract": tok["address"],
                                   "type": "known", "network": net_key})

            # Custom watched tokens for this network
            for tok in extras:
                if tok.get("network") == net_key:
                    try:
                        bal = chain.token_balance(tok["address"], wallet, tok["decimals"])
                        items.append({"symbol": tok["symbol"], "balance": bal,
                                       "contract": tok["address"], "decimals": tok["decimals"],
                                       "type": "extra", "network": net_key})
                    except Exception as e:
                        items.append({"symbol": tok["symbol"], "balance": None,
                                       "error": str(e), "contract": tok["address"],
                                       "type": "extra", "network": net_key})
            return net_key, items

        def work():
            results = {}
            lock    = threading.Lock()
            threads = []

            def run(k, cfg_n):
                key, items = _scan_network(k, cfg_n)
                with lock:
                    results[key] = items

            for k, cfg_n in SCAN_NETWORKS.items():
                t = threading.Thread(target=run, args=(k, cfg_n), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join(timeout=35)
            return results

        def done(results):
            self._last_bal_res = results
            total_nonzero = sum(
                1 for items in results.values()
                for it in items
                if it.get("balance") and float(it.get("balance", 0)) > 0
            )
            self.bal_status.config(
                text=f"✓  Both networks scanned  •  "
                     f"{total_nonzero} token(s) with balance  •  "
                     f"{datetime.now().strftime('%H:%M:%S')}"
            )
            self._render_all_network_cards(results)

        def err(e):
            self.bal_status.config(text=f"Error: {e}")
            messagebox.showerror("Balance fetch failed", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    # Network header colours
    _NET_STYLE = {
        "polygon": {"hdr_bg": "#7b1fa2", "hdr_fg": "#ffffff",
                    "border": "#ce93d8", "explorer": "https://polygonscan.com"},
        "bsc":     {"hdr_bg": "#f57f17", "hdr_fg": "#212121",
                    "border": "#ffe082", "explorer": "https://bscscan.com"},
    }

    def _render_all_network_cards(self, results: dict):
        for w in self.bal_cards_inner.winfo_children():
            w.destroy()

        CARD_COLS = 3
        row_offset = 0

        for net_key, items in results.items():
            net_info  = SCAN_NETWORKS.get(net_key, {})
            style     = self._NET_STYLE.get(net_key,
                        {"hdr_bg":"#37474f","hdr_fg":"#fff","border":"#90a4ae","explorer":""})
            visible   = [it for it in items
                         if self._show_zero
                         or it.get("balance") is None
                         or float(it.get("balance", 0)) > 0]
            nonzero   = sum(1 for it in items
                            if it.get("balance") and float(it.get("balance",0)) > 0)

            # ── Section header ────────────────────────────────────────
            hdr = tk.Frame(self.bal_cards_inner, bg=style["hdr_bg"], pady=7)
            hdr.grid(row=row_offset, column=0, columnspan=CARD_COLS,
                     sticky="ew", padx=4, pady=(12, 2))
            for c in range(CARD_COLS):
                self.bal_cards_inner.columnconfigure(c, weight=1)

            tk.Label(hdr,
                     text=f"  {net_info.get('label', net_key)}  —  "
                          f"{nonzero} token(s) with balance",
                     font=("TkDefaultFont", 11, "bold"),
                     bg=style["hdr_bg"], fg=style["hdr_fg"]).pack(side="left")

            chain_id_str = str(net_info.get("chain_id","?"))
            tk.Label(hdr, text=f"Chain ID {chain_id_str}  ",
                     font=("TkDefaultFont", 9),
                     bg=style["hdr_bg"], fg=style["hdr_fg"]).pack(side="right")
            row_offset += 1

            if not visible:
                tk.Label(self.bal_cards_inner,
                         text="  No non-zero balances on this network.",
                         fg="#888", font=("TkDefaultFont", 9)
                         ).grid(row=row_offset, column=0, columnspan=CARD_COLS,
                                sticky="w", padx=14, pady=4)
                row_offset += 1
                continue

            # ── Token cards ───────────────────────────────────────────
            for i, item in enumerate(visible):
                card_row, card_col = divmod(i, CARD_COLS)
                r = row_offset + card_row
                self.bal_cards_inner.columnconfigure(card_col, weight=1)

                has_bal  = item.get("balance") is not None
                is_zero  = has_bal and float(item.get("balance", 0)) == 0
                type_tag = item.get("type", "known")
                border   = {"native":"#1565c0","extra":"#6a1b9a"}.get(type_tag, style["border"])
                card_bg  = "#f9f9f9" if is_zero else "#ffffff"

                card = tk.Frame(self.bal_cards_inner, bd=0, padx=12, pady=10,
                                bg=card_bg, highlightbackground=border, highlightthickness=2)
                card.grid(row=r, column=card_col, padx=6, pady=6, sticky="nsew")

                sym_color = {"native":"#1565c0","extra":"#6a1b9a"}.get(
                    type_tag, "#555" if is_zero else "#212121")

                tk.Label(card, text=item.get("symbol","?"),
                         font=("TkDefaultFont", 15, "bold"),
                         fg=sym_color, bg=card_bg).pack(anchor="w")

                if has_bal:
                    bal = float(item["balance"])
                    bal_str = f"{bal:.8f}" if type_tag == "native" else f"{bal:,.6f}"
                    tk.Label(card, text=bal_str,
                             font=("Consolas", 12, "bold"),
                             fg="#aaa" if is_zero else "#111",
                             bg=card_bg).pack(anchor="w", pady=(3,1))
                else:
                    tk.Label(card,
                             text=f"⚠ {str(item.get('error',''))[:80]}",
                             font=("TkDefaultFont", 8), fg="#c62828",
                             bg=card_bg, wraplength=200, justify="left").pack(anchor="w", pady=2)

                contract = item.get("contract","")
                if contract and contract != "native":
                    short = contract[:8] + "…" + contract[-5:]
                    exp   = style.get("explorer","")
                    lbl   = tk.Label(card, text=short, font=("Consolas", 7),
                                     fg="#999", bg=card_bg, cursor="hand2")
                    lbl.pack(anchor="w")
                    if exp:
                        url = f"{exp}/token/{contract}"
                        lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

                badge = {"native":"Gas coin","known":"Token","extra":"Custom"}.get(type_tag,"")
                if badge:
                    tk.Label(card, text=badge, font=("TkDefaultFont", 7, "bold"),
                             fg="#fff", bg=border, padx=3, pady=1).pack(anchor="w", pady=(4,0))

            row_offset += (len(visible) + CARD_COLS - 1) // CARD_COLS + 1

    # ══════════════════════════════════════════════════════════════════
    #  TAB 4 — Settings (scrollable)
    # ══════════════════════════════════════════════════════════════════

    def _build_settings_tab(self):
        inner = make_scrollable(self.tab_settings)
        inner.columnconfigure(0, weight=1)
        pad = {"padx": 12, "pady": 6}

        # ── API ──────────────────────────────────────────────────────
        api_box = ttk.LabelFrame(inner, text="Backend API", padding=10)
        api_box.grid(row=0, column=0, sticky="ew", **pad)
        api_box.columnconfigure(1, weight=1)

        ttk.Label(api_box, text="API Base URL").grid(row=0, column=0, sticky="w", pady=3)
        self.var_api_base = tk.StringVar(value=self.cfg["api_base_url"])
        ttk.Entry(api_box, textvariable=self.var_api_base).grid(
            row=0, column=1, sticky="ew", padx=(8,0), pady=3)

        ttk.Label(api_box, text="Authorization Header").grid(row=1, column=0, sticky="w", pady=3)
        self.var_auth_hdr = tk.StringVar(value=self.cfg["auth_header"])
        ttk.Entry(api_box, textvariable=self.var_auth_hdr, show="*").grid(
            row=1, column=1, sticky="ew", padx=(8,0), pady=3)
        ttk.Label(api_box, text="e.g.  Bearer 1|abcde…", foreground="gray").grid(
            row=2, column=1, sticky="w", padx=(8,0))
        ttk.Button(api_box, text="Test API Connection",
                   command=self._test_api).grid(row=3, column=1, sticky="w", pady=6, padx=(8,0))

        # ── Blockchain / token ────────────────────────────────────────
        chain_box = ttk.LabelFrame(inner, text="Blockchain / Payout Token", padding=10)
        chain_box.grid(row=1, column=0, sticky="ew", **pad)
        chain_box.columnconfigure(1, weight=1)

        ttk.Label(chain_box, text="Payout network").grid(row=0, column=0, sticky="w", pady=3)
        self.var_network = tk.StringVar(value=self.cfg["network"])
        net_cb = ttk.Combobox(chain_box, textvariable=self.var_network, state="readonly",
                               values=list(NETWORK_PRESETS.keys()), width=24)
        net_cb.grid(row=0, column=1, sticky="w", padx=(8,0), pady=3)
        net_cb.bind("<<ComboboxSelected>>", self._on_net_change)
        self.net_lbl = ttk.Label(chain_box,
            text=NETWORK_PRESETS.get(self.cfg["network"],{}).get("label",""),
            foreground="#005a9e")
        self.net_lbl.grid(row=0, column=2, sticky="w", padx=8)

        ttk.Label(chain_box, text="RPC URL").grid(row=1, column=0, sticky="w", pady=3)
        self.var_rpc = tk.StringVar(value=self.cfg["rpc_url"])
        ttk.Entry(chain_box, textvariable=self.var_rpc).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8,0), pady=3)

        ttk.Label(chain_box, text="Token Contract").grid(row=2, column=0, sticky="w", pady=3)
        self.var_contract = tk.StringVar(value=self.cfg["token_contract"])
        ttk.Entry(chain_box, textvariable=self.var_contract).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(8,0), pady=3)

        ttk.Label(chain_box, text="Token Decimals").grid(row=3, column=0, sticky="w", pady=3)
        self.var_decimals = tk.IntVar(value=self.cfg["decimals"])
        ttk.Spinbox(chain_box, from_=0, to=18, textvariable=self.var_decimals, width=6).grid(
            row=3, column=1, sticky="w", padx=(8,0), pady=3)

        ttk.Label(chain_box, text="Amount field").grid(row=4, column=0, sticky="w", pady=3)
        self.var_amount_src = tk.StringVar(value=self.cfg["amount_source"])
        af = ttk.Frame(chain_box)
        af.grid(row=4, column=1, columnspan=2, sticky="w", padx=(8,0))
        ttk.Radiobutton(af, text="net_amount_bh  (BH token amount)",
                         variable=self.var_amount_src, value="bh").pack(anchor="w")
        ttk.Radiobutton(af, text="net_amount_usd  (USD value in USDT)",
                         variable=self.var_amount_src, value="usd").pack(anchor="w")

        ttk.Button(chain_box, text="Test RPC Connection",
                   command=self._test_rpc).grid(row=5, column=1, sticky="w", pady=6, padx=(8,0))

        # ── Wallet ────────────────────────────────────────────────────
        wallet_box = ttk.LabelFrame(inner, text="Sending Wallet (hot wallet)", padding=10)
        wallet_box.grid(row=2, column=0, sticky="ew", **pad)
        wallet_box.columnconfigure(1, weight=1)

        tk.Label(wallet_box,
                 text="⚠  This wallet pays customers. Only fund it with what you need to send.",
                 fg="#a13a00", wraplength=680, justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(wallet_box, text="From Address").grid(row=1, column=0, sticky="w", pady=3)
        self.var_from = tk.StringVar(value=self.cfg["from_address"])
        ttk.Entry(wallet_box, textvariable=self.var_from).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8,0), pady=3)

        ttk.Label(wallet_box, text="Private Key").grid(row=2, column=0, sticky="w", pady=3)
        pk_f = ttk.Frame(wallet_box)
        pk_f.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8,0), pady=3)
        self.var_pk    = tk.StringVar()
        self.pk_entry  = ttk.Entry(pk_f, textvariable=self.var_pk, show="*")
        self.pk_entry.pack(side="left", fill="x", expand=True)
        self.var_show_pk = tk.BooleanVar(value=False)
        ttk.Checkbutton(pk_f, text="show", variable=self.var_show_pk,
                         command=lambda: self.pk_entry.config(
                             show="" if self.var_show_pk.get() else "*")
                         ).pack(side="left", padx=4)

        self.var_persist_pk = tk.BooleanVar(value=self.cfg.get("pk_set", False))
        ttk.Checkbutton(wallet_box,
                         text="Encrypt and save key to disk (passphrase required)",
                         variable=self.var_persist_pk).grid(
            row=3, column=1, columnspan=2, sticky="w", padx=(8,0))

        status_str = "saved (encrypted)" if self.cfg.get("pk_set") else "not saved to disk"
        self.pk_status = ttk.Label(wallet_box, text=f"Key status: {status_str}", foreground="gray")
        self.pk_status.grid(row=4, column=1, sticky="w", padx=(8,0))

        btn_f = ttk.Frame(wallet_box)
        btn_f.grid(row=5, column=1, columnspan=2, sticky="w", padx=(8,0), pady=6)
        ttk.Button(btn_f, text="Save Wallet Settings", command=self._save_wallet).pack(side="left", padx=3)
        ttk.Button(btn_f, text="Clear Saved Key",       command=self._clear_pk).pack(side="left", padx=3)
        ttk.Button(btn_f, text="Check Balances",        command=self._check_balances).pack(side="left", padx=3)

        # ── Live / Simulation ─────────────────────────────────────────
        sim_box = ttk.LabelFrame(inner, text="⚠  LIVE / SIMULATION MODE", padding=10)
        sim_box.grid(row=3, column=0, sticky="ew", **pad)
        sim_box.columnconfigure(0, weight=1)

        self.sim_banner = tk.Label(sim_box, text="",
                                   font=("TkDefaultFont", 11, "bold"),
                                   anchor="center", pady=8)
        self.sim_banner.pack(fill="x")

        def _upd(*_):
            if self.var_simulate.get():
                self.sim_banner.config(
                    text="🟡  SIMULATION MODE — no real on-chain transactions will be sent",
                    bg="#fff3cd", fg="#856404")
            else:
                self.sim_banner.config(
                    text="🔴  LIVE MODE — real funds WILL be sent on-chain",
                    bg="#f8d7da", fg="#721c24")
            self._update_mode_badge()

        self.var_simulate.trace_add("write", _upd)
        _upd()

        btn_sim = ttk.Frame(sim_box)
        btn_sim.pack(pady=(6, 0))
        ttk.Button(btn_sim, text="Enable SIMULATION (safe)",
                   command=lambda: self.var_simulate.set(True)).pack(side="left", padx=6)
        ttk.Button(btn_sim, text="Enable LIVE MODE (real funds)",
                   command=self._go_live).pack(side="left", padx=6)

        # ── Bottom buttons ────────────────────────────────────────────
        bot = ttk.Frame(inner, padding=10)
        bot.grid(row=4, column=0, sticky="ew", **pad)
        ttk.Button(bot, text="💾 Save All Settings", command=self._save_all).pack(side="left", padx=4)
        ttk.Button(bot, text="Reset to Defaults",    command=self._reset).pack(side="left", padx=4)

    # ── settings helpers ──────────────────────────────────────────────

    def _collect(self):
        self.cfg["api_base_url"]   = self.var_api_base.get().strip()
        self.cfg["auth_header"]    = self.var_auth_hdr.get().strip()
        self.cfg["network"]        = self.var_network.get()
        self.cfg["rpc_url"]        = self.var_rpc.get().strip()
        self.cfg["token_contract"] = self.var_contract.get().strip()
        self.cfg["decimals"]       = int(self.var_decimals.get())
        self.cfg["amount_source"]  = self.var_amount_src.get()
        self.cfg["from_address"]   = self.var_from.get().strip()
        self.cfg["simulate_only"]  = bool(self.var_simulate.get())

    def _on_net_change(self, event=None):
        net = self.var_network.get()
        p   = NETWORK_PRESETS.get(net, {})
        self.var_rpc.set(p.get("default_rpc",""))
        self.var_contract.set(p.get("token_contract",""))
        self.var_decimals.set(p.get("decimals", 18))
        if "amount_source" in p:
            self.var_amount_src.set(p["amount_source"])
        self.net_lbl.config(text=p.get("label",""))

    def _save_all(self):
        self._collect()
        ConfigStore.save(self.cfg)
        self._set_api()
        messagebox.showinfo("Saved", "All settings saved.")

    def _save_wallet(self):
        self._collect()
        new_pk = self.var_pk.get().strip()
        if new_pk:
            if self.var_persist_pk.get():
                pw = ask_pass(self.root, "Set a passphrase to encrypt the key", confirm=True)
                if not pw:
                    messagebox.showwarning("Cancelled", "Key was not saved.")
                    return
                salt, token = encrypt_secret(new_pk, pw)
                self.cfg.update({"pk_set": True, "pk_salt": salt, "pk_token": token})
                self.pk_status.config(text="Key status: saved (encrypted)")
            else:
                self.cfg.update({"pk_set": False, "pk_salt": "", "pk_token": ""})
                self.pk_status.config(text="Key status: in memory only (not saved to disk)")
            self.runtime_pk = new_pk
            self.var_pk.set("")
        ConfigStore.save(self.cfg)
        self._set_api()
        messagebox.showinfo("Saved", "Wallet settings saved.")

    def _clear_pk(self):
        if not messagebox.askyesno("Confirm", "Delete the encrypted key from disk?"):
            return
        self.cfg.update({"pk_set": False, "pk_salt": "", "pk_token": ""})
        self.runtime_pk = None
        ConfigStore.save(self.cfg)
        self.pk_status.config(text="Key status: not saved to disk")
        messagebox.showinfo("Cleared", "Saved key removed.")

    def _reset(self):
        if not messagebox.askyesno("Confirm",
                "Reset ALL settings (including saved key and pending TX store) to defaults?"):
            return
        ConfigStore.delete()
        self.cfg        = dict(DEFAULT_CONFIG)
        self.runtime_pk = None
        messagebox.showinfo("Reset", "Settings reset. Please restart the app.")

    def _test_api(self):
        self._collect()
        self._set_api()
        def work(): return self.api.stats()
        def done(st):
            messagebox.showinfo("API OK",
                f"Connected.\nPending: {st.get('pending_count',0)}\n"
                f"Total requests: {st.get('total_requests',0)}")
        def err(e): messagebox.showerror("API Test Failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _test_rpc(self):
        self._collect()
        rpcs = [self.cfg["rpc_url"]]
        def work():
            chain = ChainClient.from_rpcs(rpcs)
            return chain.chain_id()
        def done(cid): messagebox.showinfo("RPC OK", f"Connected. Chain ID: {cid}")
        def err(e):    messagebox.showerror("RPC Test Failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _check_balances(self):
        self._collect()
        if not self.cfg["from_address"]:
            messagebox.showwarning("Missing", "Enter 'From Wallet Address' first.")
            return
        self.nb.select(self.tab_balances)
        self.refresh_balances()

    def _go_live(self):
        if not messagebox.askyesno(
            "Enable LIVE mode?",
            "⚠ WARNING\n\nReal on-chain transactions will be sent. Real funds will move.\n"
            "This cannot be undone. Are you sure?", icon="warning"):
            return
        if not messagebox.askyesno(
            "Second confirmation",
            "Confirm: clicking Approve will broadcast real token transfers.\n\n"
            "YES — I am sure, enable LIVE mode.", icon="warning"):
            return
        self.var_simulate.set(False)


# ═══════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════

def main():
    root = tk.Tk()

    def report_callback_exception(exc, val, tb):
        _show_fatal("".join(traceback.format_exception(exc, val, tb)))
    root.report_callback_exception = report_callback_exception

    try:
        style = ttk.Style()
        for theme in ("vista", "xpnative", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
    except Exception:
        pass

    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        _show_fatal(traceback.format_exc())
