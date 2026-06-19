"""
Infinity Meta Hub  v2.1.0
==========================
Single-file desktop admin app — Enhanced UI + Live Auto-Refresh + Favicon
Developed by Ayamil Coders

Changes in v2.1.0:
  • Live auto-refresh every 30 s (All tab) and every 15 s (Pending tab) with countdown
  • Favicon from imh.png in the same folder as the EXE / script
  • Light modern 3-D style UI — soft shadows, gradient headers, card elevation
  • Proper "View Details" form popup with labelled fields and copy buttons
  • Manual Refresh button on every tab
  • Status-bar live clock
  • Startup fast-path: web3 import deferred to first send so the window opens instantly
"""

import os, sys, json, base64, threading, traceback, webbrowser, time
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ── App constants ──────────────────────────────────────────────────────
APP_TITLE   = "Infinity Meta Hub"
APP_VERSION = "2.1.0"
APP_CREDIT  = "Developed By Ayamil Coders"
CONFIG_DIR  = os.path.join(os.path.expanduser("~"), ".withdrawal_admin")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
PENDING_TX_PATH = os.path.join(CONFIG_DIR, "pending_tx.json")
SHOW_ZERO_BAL_DEFAULT = False

# Live refresh intervals (seconds)
REFRESH_ALL_INTERVAL     = 30
REFRESH_PENDING_INTERVAL = 15
REFRESH_BALANCES_INTERVAL = 60

# ── Colours ────────────────────────────────────────────────────────────
C = {
    "bg":          "#F0F4FF",   # window background — very light blue-grey
    "card":        "#FFFFFF",   # card background
    "card_shadow": "#D8E0F0",   # subtle shadow colour
    "header_bg":   "#1E3A8A",   # deep navy header
    "header_fg":   "#FFFFFF",
    "accent":      "#3B82F6",   # bright blue accent
    "accent2":     "#6366F1",   # indigo
    "success":     "#16A34A",
    "warning":     "#D97706",
    "danger":      "#DC2626",
    "text":        "#1E293B",
    "text_dim":    "#64748B",
    "border":      "#CBD5E1",
    "tab_sel":     "#DBEAFE",
    "sim_bg":      "#FEF9C3",
    "sim_fg":      "#92400E",
    "live_bg":     "#FEE2E2",
    "live_fg":     "#991B1B",
    "row_pend":    "#FFFBEB",
    "row_appr":    "#DCFCE7",
    "row_rej":     "#FEE2E2",
    "row_stored":  "#F3E8FF",
    "log_bg":      "#F8FAFC",
}

# ── Multi-RPC network definitions ─────────────────────────────────────
SCAN_NETWORKS = {
    "polygon": {
        "label": "Polygon  (Chain 137)", "chain_id": 137, "native": "MATIC",
        "explorer": "https://polygonscan.com",
        "rpcs": ["https://polygon-rpc.com","https://rpc-mainnet.maticvigil.com",
                 "https://polygon-bor-rpc.publicnode.com","https://rpc.ankr.com/polygon"],
        "tokens": [
            {"symbol":"BH",    "address":"0x68a6EA8e9aB0824251061DD122aDA8493e62409d","decimals":18},
            {"symbol":"USDT",  "address":"0xc2132D05D31c914a87C6611C10748AEb04B58e8F","decimals":6},
            {"symbol":"USDC",  "address":"0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174","decimals":6},
            {"symbol":"DAI",   "address":"0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063","decimals":18},
            {"symbol":"WETH",  "address":"0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619","decimals":18},
            {"symbol":"WBTC",  "address":"0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6","decimals":8},
            {"symbol":"WMATIC","address":"0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270","decimals":18},
        ],
    },
    "bsc": {
        "label": "BNB Smart Chain  (Chain 56)", "chain_id": 56, "native": "BNB",
        "explorer": "https://bscscan.com",
        "rpcs": ["https://bsc-dataseed.binance.org/","https://bsc-dataseed1.binance.org/",
                 "https://bsc-rpc.publicnode.com","https://rpc.ankr.com/bsc"],
        "tokens": [
            {"symbol":"USDT","address":"0x55d398326f99059fF775485246999027B3197955","decimals":18},
            {"symbol":"USDC","address":"0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d","decimals":18},
            {"symbol":"BUSD","address":"0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56","decimals":18},
            {"symbol":"DAI", "address":"0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3","decimals":18},
            {"symbol":"WBNB","address":"0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c","decimals":18},
            {"symbol":"ETH", "address":"0x2170Ed0880ac9A755fd29B2688956BD959F933F8","decimals":18},
            {"symbol":"BTCB","address":"0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c","decimals":18},
        ],
    },
}

NETWORK_PRESETS = {
    "polygon_bh":   {"label":"Polygon — BH Token  (sends net_amount_bh)","chain_id":137,
                     "token_contract":"0x68a6EA8e9aB0824251061DD122aDA8493e62409d","decimals":18,
                     "default_rpc":"https://polygon-rpc.com","explorer_tx":"https://polygonscan.com/tx/",
                     "native_symbol":"MATIC","amount_source":"bh"},
    "polygon_usdt": {"label":"Polygon — USDT  (sends net_amount_usd)","chain_id":137,
                     "token_contract":"0xc2132D05D31c914a87C6611C10748AEb04B58e8F","decimals":6,
                     "default_rpc":"https://polygon-rpc.com","explorer_tx":"https://polygonscan.com/tx/",
                     "native_symbol":"MATIC","amount_source":"usd"},
    "bsc_usdt":     {"label":"BSC — USDT  (sends net_amount_usd)","chain_id":56,
                     "token_contract":"0x55d398326f99059fF775485246999027B3197955","decimals":18,
                     "default_rpc":"https://bsc-dataseed.binance.org/","explorer_tx":"https://bscscan.com/tx/",
                     "native_symbol":"BNB","amount_source":"usd"},
}

DEFAULT_CONFIG = {
    "api_base_url":"https://yourdomain.com/api/v1/admin/withdrawals",
    "auth_header":"","network":"polygon_bh",
    "rpc_url":NETWORK_PRESETS["polygon_bh"]["default_rpc"],
    "token_contract":NETWORK_PRESETS["polygon_bh"]["token_contract"],
    "decimals":NETWORK_PRESETS["polygon_bh"]["decimals"],
    "amount_source":"bh","from_address":"","simulate_only":True,
    "pk_set":False,"pk_salt":"","pk_token":"","extra_tokens":[],
}

ERC20_ABI = [
    {"constant":True,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"},
    {"constant":True,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
    {"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
    {"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf",
     "outputs":[{"name":"balance","type":"uint256"}],"type":"function"},
    {"constant":False,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],
     "name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"},
]

# ══════════════════════════════════════════════════════════════════════
#  Pending-TX store
# ══════════════════════════════════════════════════════════════════════
class PendingTxStore:
    @staticmethod
    def _load() -> dict:
        try:
            with open(PENDING_TX_PATH, encoding="utf-8") as f: return json.load(f)
        except Exception: return {}

    @staticmethod
    def _write(data: dict):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(PENDING_TX_PATH, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

    @classmethod
    def get(cls, wid) -> dict: return cls._load().get(str(wid))

    @classmethod
    def put(cls, wid, tx_hash: str, to_addr: str, amount: float, network: str):
        data = cls._load()
        data[str(wid)] = {"tx_hash":tx_hash,"to_addr":to_addr,"amount":amount,
                           "network":network,"sent_at":datetime.now().isoformat()}
        cls._write(data)

    @classmethod
    def remove(cls, wid):
        data = cls._load(); data.pop(str(wid), None); cls._write(data)

    @classmethod
    def all(cls) -> dict: return cls._load()

# ══════════════════════════════════════════════════════════════════════
#  Crypto helpers
# ══════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════
#  Config store
# ══════════════════════════════════════════════════════════════════════
class ConfigStore:
    @staticmethod
    def load() -> dict:
        cfg = dict(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f: cfg.update(json.load(f))
            except Exception: pass
        return cfg

    @staticmethod
    def save(cfg: dict):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2)

    @staticmethod
    def delete():
        for p in (CONFIG_PATH, PENDING_TX_PATH):
            if os.path.exists(p): os.remove(p)

# ══════════════════════════════════════════════════════════════════════
#  API client
# ══════════════════════════════════════════════════════════════════════
class ApiError(Exception): pass

class ApiClient:
    def __init__(self, base_url: str, auth: str):
        self.base_url = (base_url or "").rstrip("/")
        self.auth     = auth or ""
        self.session  = requests.Session()

    def _h(self):
        h = {"Accept":"application/json","Content-Type":"application/json"}
        if self.auth: h["Authorization"] = self.auth
        return h

    def _req(self, method, path, params=None, body=None):
        if not self.base_url: raise ApiError("API Base URL not set — go to Wallet & API Settings.")
        try:
            r = self.session.request(method, self.base_url + path,
                                     headers=self._h(), params=params, json=body, timeout=20)
        except requests.RequestException as e:
            raise ApiError(f"Network error: {e}")
        try:    data = r.json()
        except: raise ApiError(f"Non-JSON response (HTTP {r.status_code})")
        if r.status_code >= 400 or data.get("success") is False:
            raise ApiError(data.get("message") or f"API error (HTTP {r.status_code})")
        return data

    def list_all(self, status=None, per_page=500):
        p = {"per_page": per_page}
        if status and status != "all": p["status"] = status
        d = self._req("GET", "/", params=p)
        return d.get("data", {}).get("data", d.get("data", []))

    def list_pending(self, per_page=500):
        d = self._req("GET", "/pending", params={"per_page": per_page})
        return d.get("data", {}).get("data", d.get("data", []))

    def stats(self):
        return self._req("GET", "/stats").get("data", {})

    def approve(self, wid, tx_hash: str, note: str = ""):
        return self._req("POST", f"/{wid}/approve", body={"transaction_hash": tx_hash, "admin_note": note})

    def reject(self, wid, note: str):
        return self._req("POST", f"/{wid}/reject", body={"admin_note": note})

# ══════════════════════════════════════════════════════════════════════
#  Chain client  — web3 import deferred for fast startup
# ══════════════════════════════════════════════════════════════════════
class ChainError(Exception): pass

class ChainClient:
    def __init__(self, rpc_url: str):
        if not rpc_url: raise ChainError("RPC URL not configured.")
        from web3 import Web3
        try:
            from web3.middleware import geth_poa_middleware
            self._poa = geth_poa_middleware
        except ImportError:
            self._poa = None
        self.Web3 = Web3
        self.w3   = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if self._poa:
            try: self.w3.middleware_onion.inject(self._poa, layer=0)
            except Exception: pass
        if not self.w3.is_connected():
            raise ChainError(f"Cannot connect to RPC: {rpc_url}")

    @classmethod
    def from_rpcs(cls, rpcs: list) -> "ChainClient":
        errors = []
        for rpc in rpcs:
            try:    return cls(rpc)
            except ChainError as e: errors.append(f"{rpc}: {e}")
        raise ChainError("All RPC endpoints failed:\n" + "\n".join(errors))

    def cs(self, addr: str) -> str:
        try:    return self.Web3.to_checksum_address(addr)
        except: raise ChainError(f"Invalid address: {addr}")

    def native_balance(self, address: str) -> float:
        return float(self.w3.from_wei(self.w3.eth.get_balance(self.cs(address)), "ether"))

    def token_balance(self, contract: str, wallet: str, decimals: int) -> float:
        c = self.w3.eth.contract(address=self.cs(contract), abi=ERC20_ABI)
        return c.functions.balanceOf(self.cs(wallet)).call() / (10 ** decimals)

    def token_info(self, contract: str):
        try:
            c = self.w3.eth.contract(address=self.cs(contract), abi=ERC20_ABI)
            return c.functions.symbol().call(), int(c.functions.decimals().call())
        except Exception: return "???", 18

    def next_nonce(self, address: str) -> int:
        return self.w3.eth.get_transaction_count(self.cs(address), "pending")

    def chain_id(self) -> int: return self.w3.eth.chain_id

    def send_token(self, private_key, from_addr, to_addr, amount, contract_addr, decimals, chain_id, nonce) -> str:
        from eth_account import Account
        from_cs = self.cs(from_addr); to_cs = self.cs(to_addr); contract_cs = self.cs(contract_addr)
        acct = Account.from_key(private_key)
        if acct.address.lower() != from_cs.lower():
            raise ChainError(f"Private key address ({acct.address}) ≠ configured From address ({from_cs}).")
        units = int(round(amount * (10 ** decimals)))
        if units <= 0: raise ChainError(f"Amount rounds to zero ({amount} × 10^{decimals})")
        try:    gas_price = self.w3.eth.gas_price
        except: gas_price = self.w3.to_wei(30, "gwei")
        contract = self.w3.eth.contract(address=contract_cs, abi=ERC20_ABI)
        tx = contract.functions.transfer(to_cs, units).build_transaction(
            {"chainId":chain_id,"gas":300_000,"gasPrice":gas_price,"nonce":nonce,"from":from_cs})
        try:
            estimated = self.w3.eth.estimate_gas(tx); tx["gas"] = int(estimated * 1.3)
        except Exception: pass
        signed = acct.sign_transaction(tx)
        raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
        return self.w3.to_hex(self.w3.eth.send_raw_transaction(raw))

# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════
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
    except Exception: return ""

def _show_fatal(text: str):
    log_path = _write_crash_log(text)
    suffix   = f"\n\nLog: {log_path}" if log_path else ""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text[:1500]+suffix, f"{APP_TITLE} — Fatal Error", 0x10)
            return
        except Exception: pass
    try: print(text, file=sys.stderr)
    except Exception: pass

def _exe_dir() -> str:
    """Return folder of the running EXE or script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════════════
#  Passphrase dialog
# ══════════════════════════════════════════════════════════════════════
class PassphraseDialog(simpledialog.Dialog):
    def __init__(self, parent, title, confirm=False):
        self.confirm = confirm; self.value = None
        super().__init__(parent, title)

    def body(self, m):
        tk.Label(m, text="Passphrase:").grid(row=0, column=0, sticky="w", pady=4)
        self.e1 = tk.Entry(m, show="*", width=36); self.e1.grid(row=0, column=1, pady=4)
        if self.confirm:
            tk.Label(m, text="Confirm:").grid(row=1, column=0, sticky="w", pady=4)
            self.e2 = tk.Entry(m, show="*", width=36); self.e2.grid(row=1, column=1, pady=4)
        return self.e1

    def validate(self):
        p = self.e1.get()
        if not p:
            messagebox.showwarning("Required", "Passphrase cannot be empty.", parent=self); return False
        if self.confirm and p != self.e2.get():
            messagebox.showwarning("Mismatch", "Passphrases do not match.", parent=self); return False
        self.value = p; return True

def ask_pass(parent, title="Enter Passphrase", confirm=False):
    return PassphraseDialog(parent, title, confirm=confirm).value

# ══════════════════════════════════════════════════════════════════════
#  Scrollable frame
# ══════════════════════════════════════════════════════════════════════
def make_scrollable(parent) -> tk.Frame:
    canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0, bg=C["bg"])
    vsb    = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner  = tk.Frame(canvas, bg=C["bg"])
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0,0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
    return inner

# ══════════════════════════════════════════════════════════════════════
#  Treeview column definitions
# ══════════════════════════════════════════════════════════════════════
COLS   = ("id","user_id","gross_bh","fee_bh","net_bh","net_usd","wallet","status","created_at")
HEADS  = ("ID","User","Gross BH","Fee BH","Net BH","Net USD","Wallet Address","Status","Created")
WIDTHS = (55, 110, 100, 90, 100, 100, 260, 80, 140)

# ══════════════════════════════════════════════════════════════════════
#  Detail field definitions for the popup form
# ══════════════════════════════════════════════════════════════════════
DETAIL_FIELDS = [
    ("Withdrawal ID",      "id"),
    ("User ID",            "user_id"),
    ("Status",             "status"),
    ("Wallet Address",     "wallet_address"),
    ("Gross Amount (BH)",  "gross_amount_bh"),
    ("Platform Fee (BH)",  "platform_fee_bh"),
    ("Net Amount (BH)",    "net_amount_bh"),
    ("Net Amount (USD)",   "net_amount_usd"),
    ("Transaction Hash",   "transaction_hash"),
    ("Admin Note",         "admin_note"),
    ("Rejection Reason",   "rejection_reason"),
    ("Created At",         "created_at"),
    ("Updated At",         "updated_at"),
    ("Processed At",       "processed_at"),
]

# ══════════════════════════════════════════════════════════════════════
#  UI helper — rounded card frame
# ══════════════════════════════════════════════════════════════════════
def card_frame(parent, **kw):
    """A white card with a soft border — simulates elevation."""
    f = tk.Frame(parent, bg=C["card"], highlightbackground=C["border"],
                 highlightthickness=1, bd=0, **kw)
    return f

# ══════════════════════════════════════════════════════════════════════
#  Main application
# ══════════════════════════════════════════════════════════════════════
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE}  v{APP_VERSION}  —  {APP_CREDIT}")
        self.root.geometry("1300x780")
        self.root.minsize(1000, 640)
        self.root.configure(bg=C["bg"])

        # ── Favicon from imh.png ─────────────────────────────────────
        self._load_favicon()

        self.cfg        = ConfigStore.load()
        self.api        = ApiClient(self.cfg["api_base_url"], self.cfg["auth_header"])
        self.runtime_pk = None

        self.all_records     = []
        self.pending_records = []

        self.var_simulate = tk.BooleanVar(value=self.cfg.get("simulate_only", True))
        self._show_zero   = SHOW_ZERO_BAL_DEFAULT
        self._last_bal_res = {}

        # Live refresh countdown vars
        self._all_countdown     = 0
        self._pending_countdown = 0
        self._bal_countdown     = 0
        self._live_paused       = False

        self._apply_style()
        self._build_ui()

        # Initial data load + start live refresh tickers
        self.refresh_all(silent=True)
        self.refresh_pending(silent=True)
        self._tick_all()
        self._tick_pending()
        self._tick_balances()
        self._tick_clock()

    # ── favicon ───────────────────────────────────────────────────────
    def _load_favicon(self):
        ico_path = os.path.join(_exe_dir(), "imh.png")
        if not os.path.exists(ico_path):
            return
        try:
            img = tk.PhotoImage(file=ico_path)
            self.root.iconphoto(True, img)
            self._favicon_ref = img          # keep reference so GC doesn't collect it
        except Exception:
            pass

    # ── ttk style ─────────────────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style()
        try:
            if "vista" in s.theme_names(): s.theme_use("vista")
            elif "clam" in s.theme_names(): s.theme_use("clam")
        except Exception: pass

        s.configure(".", background=C["bg"], foreground=C["text"], font=("Segoe UI", 9))
        s.configure("TNotebook",        background=C["bg"],    borderwidth=0)
        s.configure("TNotebook.Tab",    background="#DBEAFE",  foreground=C["text"],
                    padding=[14, 6], font=("Segoe UI", 9, "bold"))
        s.map("TNotebook.Tab",
              background=[("selected", C["header_bg"])],
              foreground=[("selected", "#FFFFFF")])
        s.configure("TFrame",           background=C["bg"])
        s.configure("TLabel",           background=C["bg"],    foreground=C["text"])
        s.configure("TLabelframe",      background=C["bg"],    foreground=C["text"])
        s.configure("TLabelframe.Label",background=C["bg"],    foreground=C["header_bg"],
                    font=("Segoe UI", 9, "bold"))
        s.configure("Card.TFrame",      background=C["card"],  relief="flat")

        # Buttons
        s.configure("TButton", padding=[10, 5], font=("Segoe UI", 9))
        s.configure("Accent.TButton",   background=C["accent"],  foreground="#fff",
                    font=("Segoe UI", 9, "bold"), padding=[12, 6])
        s.map("Accent.TButton",
              background=[("active", "#2563EB"), ("pressed", "#1D4ED8")])
        s.configure("Success.TButton",  background=C["success"], foreground="#fff",
                    font=("Segoe UI", 9, "bold"), padding=[12, 6])
        s.map("Success.TButton",
              background=[("active","#15803D"),("pressed","#166534")])
        s.configure("Danger.TButton",   background=C["danger"],  foreground="#fff",
                    font=("Segoe UI", 9, "bold"), padding=[12, 6])
        s.map("Danger.TButton",
              background=[("active","#B91C1C"),("pressed","#991B1B")])

        # Treeview
        s.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                    foreground=C["text"], rowheight=26, font=("Segoe UI", 9))
        s.configure("Treeview.Heading", background=C["header_bg"], foreground="#fff",
                    font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Treeview", background=[("selected", C["accent"])],
              foreground=[("selected","#ffffff")])

    # ── live tickers ──────────────────────────────────────────────────
    def _tick_all(self):
        if not self._live_paused:
            if self._all_countdown <= 0:
                self.refresh_all(silent=True)
                self._all_countdown = REFRESH_ALL_INTERVAL
            else:
                self._all_countdown -= 1
            if hasattr(self, "all_next_lbl"):
                self.all_next_lbl.config(text=f"Auto-refresh in {self._all_countdown}s")
        self.root.after(1000, self._tick_all)

    def _tick_pending(self):
        if not self._live_paused:
            if self._pending_countdown <= 0:
                self.refresh_pending(silent=True)
                self._pending_countdown = REFRESH_PENDING_INTERVAL
            else:
                self._pending_countdown -= 1
            if hasattr(self, "pending_next_lbl"):
                self.pending_next_lbl.config(text=f"Auto-refresh in {self._pending_countdown}s")
        self.root.after(1000, self._tick_pending)

    def _tick_balances(self):
        if not self._live_paused:
            if self._bal_countdown <= 0:
                # Only auto-refresh balances if wallet is set and tab is visible
                if self.cfg.get("from_address"):
                    self.refresh_balances(silent=True)
                self._bal_countdown = REFRESH_BALANCES_INTERVAL
            else:
                self._bal_countdown -= 1
            if hasattr(self, "bal_next_lbl"):
                self.bal_next_lbl.config(text=f"Auto-refresh in {self._bal_countdown}s")
        self.root.after(1000, self._tick_balances)

    def _tick_clock(self):
        now = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, "status_clock"):
            self.status_clock.config(text=f"🕐 {now}")
        self.root.after(1000, self._tick_clock)

    # ── thread helpers ────────────────────────────────────────────────
    def ui(self, fn): self.root.after(0, fn)

    def run_bg(self, fn, on_done=None, on_error=None):
        def wrapper():
            try:
                result = fn()
                if on_done: self.ui(lambda r=result: on_done(r))
            except Exception as exc:
                cap = exc
                if on_error: self.ui(lambda e=cap: on_error(e))
                else:        self.ui(lambda e=cap: messagebox.showerror("Error", str(e)))
        threading.Thread(target=wrapper, daemon=True).start()

    def _get_pk(self):
        if self.runtime_pk: return self.runtime_pk
        if self.cfg.get("pk_set"):
            pw = ask_pass(self.root, "Unlock Wallet Key")
            if not pw: raise ChainError("Passphrase required.")
            try:    pk = decrypt_secret(self.cfg["pk_salt"], self.cfg["pk_token"], pw)
            except: raise ChainError("Wrong passphrase or corrupted key.")
            self.runtime_pk = pk; return pk
        raise ChainError("No wallet key — go to Wallet & API Settings.")

    def _new_chain(self) -> ChainClient:
        rpcs = [self.cfg["rpc_url"]]
        if "polygon" in self.cfg["network"]: rpcs += SCAN_NETWORKS["polygon"]["rpcs"]
        else:                                 rpcs += SCAN_NETWORKS["bsc"]["rpcs"]
        return ChainClient.from_rpcs(list(dict.fromkeys(rpcs)))

    def _set_api(self):
        self.api = ApiClient(self.cfg["api_base_url"], self.cfg["auth_header"])

    # ══════════════════════════════════════════════════════════════════
    #  UI skeleton
    # ══════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # ── header bar ────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=C["header_bg"], pady=10)
        hdr.pack(fill="x")

        # Logo area
        logo_frame = tk.Frame(hdr, bg=C["header_bg"])
        logo_frame.pack(side="left", padx=16)
        tk.Label(logo_frame, text="∞", font=("Segoe UI", 22, "bold"),
                 bg=C["header_bg"], fg="#60A5FA").pack(side="left")
        title_frame = tk.Frame(logo_frame, bg=C["header_bg"])
        title_frame.pack(side="left", padx=6)
        tk.Label(title_frame, text=APP_TITLE, font=("Segoe UI", 13, "bold"),
                 bg=C["header_bg"], fg="#FFFFFF").pack(anchor="w")
        tk.Label(title_frame, text=APP_CREDIT, font=("Segoe UI", 8),
                 bg=C["header_bg"], fg="#93C5FD").pack(anchor="w")

        # Right side of header
        hdr_right = tk.Frame(hdr, bg=C["header_bg"])
        hdr_right.pack(side="right", padx=16)
        self.mode_badge = tk.Label(hdr_right, text="", font=("Segoe UI", 9, "bold"),
                                    padx=10, pady=4, relief="flat", bd=0)
        self.mode_badge.pack(side="right", padx=8)
        tk.Label(hdr_right, text=f"v{APP_VERSION}", font=("Segoe UI", 8),
                 bg=C["header_bg"], fg="#93C5FD").pack(side="right", padx=4)

        # ── notebook ──────────────────────────────────────────────────
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=0, pady=0)

        self.tab_all      = ttk.Frame(self.nb)
        self.tab_pending  = ttk.Frame(self.nb)
        self.tab_balances = ttk.Frame(self.nb)
        self.tab_settings = ttk.Frame(self.nb)

        self.nb.add(self.tab_all,      text="  📋 All Withdrawals  ")
        self.nb.add(self.tab_pending,  text="  ⏳ Pending  ")
        self.nb.add(self.tab_balances, text="  💰 Wallet Balances  ")
        self.nb.add(self.tab_settings, text="  ⚙ Settings  ")

        # ── status bar ────────────────────────────────────────────────
        sbar = tk.Frame(self.root, bg=C["header_bg"], pady=3)
        sbar.pack(fill="x", side="bottom")
        tk.Label(sbar, text=f"  {APP_CREDIT}  •  {APP_TITLE} v{APP_VERSION}",
                 bg=C["header_bg"], fg="#93C5FD", font=("Segoe UI", 8)).pack(side="left")
        self.status_clock = tk.Label(sbar, text="", bg=C["header_bg"], fg="#E2E8F0",
                                      font=("Segoe UI", 8, "bold"))
        self.status_clock.pack(side="right", padx=10)
        tk.Label(sbar, text="Simulation mode ON by default — change in Settings  ",
                 bg=C["header_bg"], fg="#60A5FA", font=("Segoe UI", 8)).pack(side="right")

        self._build_all_tab()
        self._build_pending_tab()
        self._build_balances_tab()
        self._build_settings_tab()
        self._update_mode_badge()

    # ── shared tree builder ───────────────────────────────────────────
    def _make_tree(self, parent):
        wrap = tk.Frame(parent, bg=C["bg"])
        tree = ttk.Treeview(wrap, columns=COLS, show="headings", selectmode="extended")
        for col, head, w in zip(COLS, HEADS, WIDTHS):
            tree.heading(col, text=head, command=lambda c=col: self._sort_tree(tree, c, False))
            tree.column(col, width=w, minwidth=50, anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)
        tree.tag_configure("approved", background=C["row_appr"])
        tree.tag_configure("rejected", background=C["row_rej"])
        tree.tag_configure("pending",  background=C["row_pend"])
        tree.tag_configure("stored_tx",background=C["row_stored"])
        return wrap, tree

    def _sort_tree(self, tree, col, reverse):
        data = [(tree.set(k, col), k) for k in tree.get_children("")]
        try:    data.sort(key=lambda t: float(t[0].replace(",","").replace("$","")), reverse=reverse)
        except: data.sort(key=lambda t: t[0], reverse=reverse)
        for idx, (_, k) in enumerate(data): tree.move(k, "", idx)
        tree.heading(col, command=lambda: self._sort_tree(tree, col, not reverse))

    @staticmethod
    def _row_values(rec):
        return (rec.get("id"), rec.get("user_id"),
                fmt(rec.get("gross_amount_bh", 0)), fmt(rec.get("platform_fee_bh", 0)),
                fmt(rec.get("net_amount_bh",   0)), fmt_usd(rec.get("net_amount_usd", 0)),
                rec.get("wallet_address"), rec.get("status"),
                (rec.get("created_at") or "")[:19])

    def _populate_tree(self, tree, records):
        for row in tree.get_children(): tree.delete(row)
        for rec in records:
            tag = rec.get("status", "pending")
            tree.insert("", "end", iid=str(rec.get("id")), values=self._row_values(rec), tags=(tag,))

    # ── toolbar helper ────────────────────────────────────────────────
    def _toolbar(self, parent):
        """Returns a styled toolbar frame."""
        bar = tk.Frame(parent, bg=C["bg"], pady=6, padx=8)
        bar.pack(fill="x")
        return bar

    def _btn(self, parent, text, cmd, style="TButton", **kw):
        return ttk.Button(parent, text=text, command=cmd, style=style, **kw)

    # ══════════════════════════════════════════════════════════════════
    #  TAB 1 — All Withdrawals
    # ══════════════════════════════════════════════════════════════════
    def _build_all_tab(self):
        p = self.tab_all

        # Stats card
        stats_card = card_frame(p)
        stats_card.pack(fill="x", padx=10, pady=(8,4))

        # Inner stats row
        self.stat_boxes = {}
        stats_inner = tk.Frame(stats_card, bg=C["card"])
        stats_inner.pack(fill="x", padx=12, pady=8)
        for i, (key, label, color) in enumerate([
            ("total_requests","Total","#1E3A8A"),
            ("pending_count","Pending","#D97706"),
            ("approved_count","Approved","#16A34A"),
            ("rejected_count","Rejected","#DC2626"),
            ("pending_usd","Pending USD","#7C3AED"),
            ("total_paid_usd","Paid USD","#0891B2"),
        ]):
            box = tk.Frame(stats_inner, bg=C["bg"], padx=12, pady=6,
                           highlightbackground=color, highlightthickness=2)
            box.grid(row=0, column=i, padx=4, pady=2, sticky="nsew")
            stats_inner.columnconfigure(i, weight=1)
            tk.Label(box, text=label, font=("Segoe UI", 8, "bold"),
                     bg=C["bg"], fg=color).pack()
            val = tk.Label(box, text="—", font=("Segoe UI", 13, "bold"),
                           bg=C["bg"], fg=color)
            val.pack()
            self.stat_boxes[key] = val

        # Toolbar
        bar = self._toolbar(p)
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.var_all_status = tk.StringVar(value="all")
        cb = ttk.Combobox(bar, textvariable=self.var_all_status, state="readonly",
                           values=["all","pending","approved","rejected"], width=11)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_all())
        self._btn(bar, "⟳ Refresh Now", self.refresh_all, "Accent.TButton").pack(side="left", padx=4)
        self._btn(bar, "🔍 View Details", self._all_details).pack(side="left", padx=4)
        self.all_next_lbl = tk.Label(bar, text="", font=("Segoe UI", 8),
                                      bg=C["bg"], fg=C["text_dim"])
        self.all_next_lbl.pack(side="right", padx=8)

        wrap, self.all_tree = self._make_tree(p)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.all_tree.bind("<Double-1>", lambda e: self._all_details())

    def refresh_all(self, silent=False):
        self._set_api()
        self._all_countdown = REFRESH_ALL_INTERVAL
        status = getattr(self, "var_all_status", None)
        sv = status.get() if status else "all"

        def work():
            records = self.api.list_all(status=sv)
            try:    st = self.api.stats()
            except: st = {}
            return records, st

        def done(res):
            records, st = res
            self.all_records = records
            self._populate_tree(self.all_tree, records)
            for key, lbl_widget in self.stat_boxes.items():
                val = st.get(key, 0)
                if "usd" in key.lower():
                    lbl_widget.config(text=fmt_usd(val))
                else:
                    lbl_widget.config(text=str(val))

        def err(e):
            if not silent: messagebox.showerror("Failed to load withdrawals", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    def _all_details(self):
        sel = self.all_tree.selection()
        if not sel: messagebox.showinfo("Select a row", "Click a row first."); return
        rec = next((r for r in self.all_records if str(r.get("id")) == sel[0]), None)
        if rec: self._record_popup(rec)

    # ── Detail popup — proper labelled form ───────────────────────────
    def _record_popup(self, rec):
        win = tk.Toplevel(self.root)
        win.title(f"Withdrawal #{rec.get('id')} — Details")
        win.geometry("560x620")
        win.configure(bg=C["bg"])
        win.grab_set()
        win.resizable(False, True)

        # Title bar
        title_bar = tk.Frame(win, bg=C["header_bg"], pady=10)
        title_bar.pack(fill="x")
        status_val = rec.get("status","").upper()
        status_color = {"APPROVED":C["success"],"REJECTED":C["danger"],"PENDING":C["warning"]}.get(
            status_val, C["text_dim"])
        tk.Label(title_bar, text=f"  Withdrawal #{rec.get('id')}",
                 font=("Segoe UI",13,"bold"), bg=C["header_bg"], fg="#fff").pack(side="left")
        tk.Label(title_bar, text=f"  {status_val}  ", font=("Segoe UI",9,"bold"),
                 bg=status_color, fg="#fff", padx=6, pady=2).pack(side="right", padx=12)

        # Pending TX warning
        stored = PendingTxStore.get(rec.get("id"))
        if stored:
            warn = tk.Frame(win, bg="#FEF3C7", pady=8, padx=12)
            warn.pack(fill="x")
            tk.Label(warn, text="⚠  ON-CHAIN TX STORED (sent but API not confirmed)",
                     font=("Segoe UI",9,"bold"), bg="#FEF3C7", fg="#92400E").pack(anchor="w")
            tk.Label(warn, text=f"TX: {stored['tx_hash']}",
                     font=("Consolas",8), bg="#FEF3C7", fg="#78350F").pack(anchor="w")
            tk.Label(warn, text=f"Sent at: {stored['sent_at'][:19]}",
                     font=("Consolas",8), bg="#FEF3C7", fg="#78350F").pack(anchor="w")

        # Scrollable form body
        outer = tk.Frame(win, bg=C["bg"])
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=C["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(outer, command=canvas.yview)
        body = tk.Frame(canvas, bg=C["bg"])
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Form rows
        for i, (label, key) in enumerate(DETAIL_FIELDS):
            val = rec.get(key)
            if val is None: val = "—"
            else: val = str(val)

            row_bg = C["card"] if i % 2 == 0 else "#F8FAFC"
            row = tk.Frame(body, bg=row_bg, pady=6, padx=14)
            row.pack(fill="x")

            tk.Label(row, text=label, font=("Segoe UI",9,"bold"),
                     bg=row_bg, fg=C["text_dim"], width=20, anchor="w").pack(side="left")

            # Value display
            val_frame = tk.Frame(row, bg=row_bg)
            val_frame.pack(side="left", fill="x", expand=True)

            # Highlight important fields
            val_color = C["text"]
            val_font  = ("Segoe UI", 9)
            if key == "wallet_address" or key == "transaction_hash":
                val_font  = ("Consolas", 8)
                val_color = "#1E40AF"
            elif key == "status":
                val_color = status_color
                val_font  = ("Segoe UI", 9, "bold")
            elif key in ("net_amount_bh","net_amount_usd","gross_amount_bh"):
                val_font  = ("Segoe UI", 10, "bold")
                val_color = C["success"] if float(val or 0) > 0 else C["text_dim"]

            tk.Label(val_frame, text=val, font=val_font, fg=val_color,
                     bg=row_bg, anchor="w", wraplength=320, justify="left").pack(side="left")

            # Copy button for long values
            if key in ("wallet_address","transaction_hash","id","user_id"):
                def _copy(v=val):
                    win.clipboard_clear(); win.clipboard_append(v)
                tk.Button(row, text="⎘", font=("Segoe UI",8), bg=C["card"],
                          fg=C["accent"], relief="flat", bd=0, cursor="hand2",
                          command=_copy, padx=4).pack(side="right")

        # Extra raw fields not in DETAIL_FIELDS
        known_keys = {k for _, k in DETAIL_FIELDS}
        extras = {k: v for k, v in rec.items() if k not in known_keys and v is not None}
        if extras:
            sep = tk.Frame(body, bg=C["border"], height=1)
            sep.pack(fill="x", pady=4)
            tk.Label(body, text="Additional Fields", font=("Segoe UI",9,"bold"),
                     bg=C["bg"], fg=C["text_dim"], padx=14).pack(anchor="w", pady=(2,0))
            for k, v in extras.items():
                row = tk.Frame(body, bg=C["bg"], pady=3, padx=14)
                row.pack(fill="x")
                tk.Label(row, text=str(k), font=("Segoe UI",8,"bold"),
                         bg=C["bg"], fg=C["text_dim"], width=20, anchor="w").pack(side="left")
                tk.Label(row, text=str(v), font=("Segoe UI",8),
                         bg=C["bg"], fg=C["text"], anchor="w",
                         wraplength=340, justify="left").pack(side="left")

        # Bottom buttons
        btn_row = tk.Frame(win, bg=C["bg"], pady=8)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Close", command=win.destroy).pack(side="right", padx=12)
        if rec.get("wallet_address"):
            def _open_scan():
                addr = rec["wallet_address"]
                preset = NETWORK_PRESETS.get(self.cfg.get("network","polygon_bh"),{})
                exp = preset.get("explorer_tx","https://polygonscan.com/tx/").rsplit("/tx/",1)[0]
                webbrowser.open(f"{exp}/address/{addr}")
            ttk.Button(btn_row, text="🔗 View on Explorer",
                       command=_open_scan).pack(side="right", padx=4)

    # ══════════════════════════════════════════════════════════════════
    #  TAB 2 — Pending
    # ══════════════════════════════════════════════════════════════════
    def _build_pending_tab(self):
        p = self.tab_pending

        # Summary card
        sum_card = card_frame(p)
        sum_card.pack(fill="x", padx=10, pady=(8,2))
        sum_inner = tk.Frame(sum_card, bg=C["card"])
        sum_inner.pack(fill="x", padx=12, pady=8)

        self.pend_count_lbl = tk.Label(sum_inner, text="0",
            font=("Segoe UI",20,"bold"), bg=C["card"], fg=C["warning"])
        self.pend_count_lbl.grid(row=0, column=0, padx=16)
        tk.Label(sum_inner, text="Pending", font=("Segoe UI",8),
                 bg=C["card"], fg=C["text_dim"]).grid(row=1, column=0)

        tk.Frame(sum_inner, bg=C["border"], width=1).grid(row=0, column=1, rowspan=2, sticky="ns", padx=8, pady=4)

        self.pend_bh_lbl = tk.Label(sum_inner, text="0.0000",
            font=("Segoe UI",16,"bold"), bg=C["card"], fg=C["accent2"])
        self.pend_bh_lbl.grid(row=0, column=2, padx=16)
        tk.Label(sum_inner, text="Total Net BH", font=("Segoe UI",8),
                 bg=C["card"], fg=C["text_dim"]).grid(row=1, column=2)

        tk.Frame(sum_inner, bg=C["border"], width=1).grid(row=0, column=3, rowspan=2, sticky="ns", padx=8, pady=4)

        self.pend_usd_lbl = tk.Label(sum_inner, text="$0.00",
            font=("Segoe UI",16,"bold"), bg=C["card"], fg=C["success"])
        self.pend_usd_lbl.grid(row=0, column=4, padx=16)
        tk.Label(sum_inner, text="Total Net USD", font=("Segoe UI",8),
                 bg=C["card"], fg=C["text_dim"]).grid(row=1, column=4)

        self.pending_mode_lbl = tk.Label(sum_inner, text="",
            font=("Segoe UI",9,"bold"), padx=10, pady=4, relief="flat")
        self.pending_mode_lbl.grid(row=0, column=5, padx=20)
        tk.Label(sum_inner, text="Mode", font=("Segoe UI",8),
                 bg=C["card"], fg=C["text_dim"]).grid(row=1, column=5)

        # Toolbar
        bar = self._toolbar(p)
        self._btn(bar, "⟳ Refresh Now",     self.refresh_pending, "Accent.TButton").pack(side="left", padx=3)
        self._btn(bar, "✔ Approve Selected", self.approve_selected,"Success.TButton").pack(side="left", padx=3)
        self._btn(bar, "✖ Reject Selected",  self.reject_selected, "Danger.TButton").pack(side="left", padx=3)
        self._btn(bar, "✔✔ Approve ALL",     self.approve_all,     "Success.TButton").pack(side="left", padx=3)
        self._btn(bar, "⚠ TX Store",         self._show_pending_store).pack(side="left", padx=3)
        self._btn(bar, "🔍 Details",         self._pending_details).pack(side="left", padx=3)
        self.pending_next_lbl = tk.Label(bar, text="", font=("Segoe UI",8),
                                          bg=C["bg"], fg=C["text_dim"])
        self.pending_next_lbl.pack(side="right", padx=8)

        self.var_simulate.trace_add("write", lambda *_: self._update_mode_badge())

        wrap, self.pending_tree = self._make_tree(p)
        wrap.pack(fill="both", expand=True, padx=10, pady=4)
        self.pending_tree.bind("<Double-1>", lambda e: self._pending_details())

        # Activity log
        log_card = card_frame(p)
        log_card.pack(fill="x", padx=10, pady=(0, 8))
        log_hdr = tk.Frame(log_card, bg=C["header_bg"], pady=4)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text="  📜 Activity Log", font=("Segoe UI",9,"bold"),
                 bg=C["header_bg"], fg="#fff").pack(side="left")
        tk.Button(log_hdr, text="Clear", font=("Segoe UI",8), bg=C["header_bg"],
                  fg="#93C5FD", relief="flat", bd=0,
                  command=lambda: (self.log_text.config(state="normal"),
                                   self.log_text.delete("1.0","end"),
                                   self.log_text.config(state="disabled"))
                  ).pack(side="right", padx=8)

        log_body = tk.Frame(log_card, bg=C["log_bg"])
        log_body.pack(fill="x")
        self.log_text = tk.Text(log_body, height=8, wrap="word",
                                 state="disabled", font=("Consolas",9),
                                 bg=C["log_bg"], fg=C["text"], relief="flat", bd=0)
        log_vsb = ttk.Scrollbar(log_body, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        log_vsb.grid(row=0, column=1, sticky="ns")
        log_body.rowconfigure(0, weight=1); log_body.columnconfigure(0, weight=1)
        self.log_text.tag_configure("link",   foreground=C["accent"], underline=1)
        self.log_text.tag_configure("ok",     foreground=C["success"])
        self.log_text.tag_configure("fail",   foreground=C["danger"])
        self.log_text.tag_configure("sim",    foreground=C["warning"])
        self.log_text.tag_configure("stored", foreground=C["accent2"],
                                     font=("Consolas",9,"bold"))

    def _update_mode_badge(self):
        if self.var_simulate.get():
            cfg = {"text":"🟡  SIMULATION", "bg":C["sim_bg"], "fg":C["sim_fg"]}
        else:
            cfg = {"text":"🔴  LIVE MODE",  "bg":C["live_bg"],"fg":C["live_fg"]}
        if hasattr(self, "pending_mode_lbl"):
            self.pending_mode_lbl.config(**cfg)
        self.mode_badge.config(**cfg)

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
                self.log_text.tag_bind("link", "<Button-1>", lambda e, u=url: webbrowser.open(u))
            self.log_text.insert("end", "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.ui(do)

    def _show_pending_store(self):
        store = PendingTxStore.all()
        win   = tk.Toplevel(self.root)
        win.title("Pending TX Store  (sent but API not confirmed)")
        win.geometry("720x380"); win.grab_set()
        win.configure(bg=C["bg"])
        t   = tk.Text(win, wrap="word", font=("Consolas",9),
                      bg=C["log_bg"], fg=C["text"], relief="flat")
        vsb = ttk.Scrollbar(win, command=t.yview)
        t.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        t.pack(fill="both", expand=True, padx=8, pady=8)
        if not store:
            t.insert("end", "✓ No pending transactions — all API calls confirmed.\n")
        else:
            t.insert("end", "⚠ The following have an on-chain TX sent but API not confirmed:\n\n")
            for wid, info in store.items():
                t.insert("end", f"Withdrawal #{wid}:\n")
                for k, v in info.items(): t.insert("end", f"  {k:10s}: {v}\n")
                t.insert("end", "\n")
        t.config(state="disabled")

    def refresh_pending(self, silent=False):
        self._set_api()
        self._pending_countdown = REFRESH_PENDING_INTERVAL

        def work(): return self.api.list_pending()

        def done(records):
            self.pending_records = records
            self._populate_tree(self.pending_tree, records)
            stored_ids = set(PendingTxStore.all().keys())
            for rec in records:
                rid = str(rec.get("id"))
                if rid in stored_ids:
                    try: self.pending_tree.item(rid, tags=("stored_tx",))
                    except Exception: pass

            total_bh  = sum(float(r.get("net_amount_bh",  0) or 0) for r in records)
            total_usd = sum(float(r.get("net_amount_usd", 0) or 0) for r in records)
            self.pend_count_lbl.config(text=str(len(records)))
            self.pend_bh_lbl.config(text=fmt(total_bh))
            self.pend_usd_lbl.config(text=fmt_usd(total_usd))

        def err(e):
            if not silent: messagebox.showerror("Failed to load pending", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    def _pending_details(self):
        sel = self.pending_tree.selection()
        if not sel: return
        rec = next((r for r in self.pending_records if str(r.get("id")) == sel[0]), None)
        if rec: self._record_popup(rec)

    def _selected_pending(self):
        sel  = self.pending_tree.selection()
        recs = [r for r in self.pending_records if str(r.get("id")) in sel]
        if not recs: messagebox.showinfo("Nothing selected", "Click one or more rows first.")
        return recs

    def reject_selected(self):
        recs = self._selected_pending()
        if not recs: return
        note = simpledialog.askstring("Reject",
            f"Reason for rejecting {len(recs)} withdrawal(s):", parent=self.root)
        if not note: messagebox.showwarning("Cancelled", "A rejection reason is required."); return
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
        if recs: self._approve_batch(recs)

    def approve_all(self):
        if not self.pending_records:
            messagebox.showinfo("Nothing to do", "No pending withdrawals loaded."); return
        self._approve_batch(list(self.pending_records))

    def _approve_batch(self, recs: list):
        cfg          = self.cfg
        amount_field = "net_amount_bh" if cfg["amount_source"] == "bh" else "net_amount_usd"
        total        = sum(float(r.get(amount_field, 0) or 0) for r in recs)
        simulate     = self.var_simulate.get()
        mode_str     = "SIMULATION — no real funds will move" if simulate else "⚠ LIVE — REAL FUNDS WILL BE SENT"

        if not cfg["from_address"]:
            messagebox.showwarning("Missing", "Set 'From Wallet Address' in Settings first."); return

        stored_ids  = [str(r["id"]) for r in recs if PendingTxStore.get(r["id"])]
        stored_msg  = (f"\n\n⚠ {len(stored_ids)} withdrawal(s) already have an on-chain TX stored "
                       f"(IDs: {', '.join(stored_ids)}).\n"
                       f"The app will SKIP the chain send and only retry the API call."
                       ) if stored_ids else ""

        if not messagebox.askyesno("Confirm Approval",
            f"Mode: {mode_str}\n\nApprove {len(recs)} withdrawal(s)?\n"
            f"Total {amount_field}: {fmt(total, 4)}\nFrom wallet: {cfg['from_address']}{stored_msg}"):
            return

        pk = None
        if not simulate:
            try:    pk = self._get_pk()
            except ChainError as e: messagebox.showerror("Key required", str(e)); return

        self._set_api()
        preset   = NETWORK_PRESETS.get(cfg["network"], {})
        chain_id = preset.get("chain_id", 137)
        explorer = preset.get("explorer_tx", "")

        self.log(f"Batch start: {len(recs)} withdrawal(s)  |  "
                 f"{'SIMULATE' if simulate else 'LIVE'}  |  network={cfg['network']}",
                 tag="sim" if simulate else "fail")

        def work():
            chain = None; nonce = None
            if not simulate:
                chain = self._new_chain()
                nonce = chain.next_nonce(cfg["from_address"])

            for rec in recs:
                rid     = rec.get("id")
                to_addr = rec.get("wallet_address", "")
                try:
                    amount = float(rec.get(amount_field, 0) or 0)
                    if amount <= 0: raise ChainError(f"{amount_field}={amount} — cannot send zero.")

                    stored = PendingTxStore.get(rid)
                    if stored:
                        tx_hash = stored["tx_hash"]
                        self.log(f"#{rid}: ⚠ Existing TX found ({stored['sent_at'][:19]}). "
                                 f"Skipping chain send — retrying API only. tx={tx_hash[:20]}…",
                                 tag="stored")
                    elif simulate:
                        tx_hash = "SIMULATED-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                        self.log(f"#{rid}: [SIM] would send {fmt(amount,4)} → {to_addr}", tag="sim")
                    else:
                        tx_hash = chain.send_token(pk, cfg["from_address"], to_addr, amount,
                                                    cfg["token_contract"], cfg["decimals"],
                                                    chain_id, nonce)
                        nonce += 1
                        PendingTxStore.put(rid, tx_hash, to_addr, amount, cfg["network"])
                        url = explorer + tx_hash if explorer else ""
                        self.log(f"#{rid}: ✓ Sent {fmt(amount,4)} → {to_addr}  tx={tx_hash}",
                                 url=url, tag="ok")

                    self.api.approve(rid, tx_hash,
                        note=(f"{'SIMULATED' if simulate else cfg['network']}. "
                              f"{amount_field}={fmt(amount,4)}."))
                    PendingTxStore.remove(rid)
                    self.log(f"#{rid}: ✓ Marked APPROVED in backend.", tag="ok")

                except Exception as exc:
                    self.log(f"#{rid}: FAILED — {exc}", tag="fail")

        def done(_):
            self.log("Batch complete.", tag="ok")
            self.refresh_pending(); self.refresh_all()
            messagebox.showinfo("Done", "Batch complete. See Activity Log.")

        self.run_bg(work, on_done=done)

    # ══════════════════════════════════════════════════════════════════
    #  TAB 3 — Wallet Balances
    # ══════════════════════════════════════════════════════════════════
    _NET_STYLE = {
        "polygon": {"hdr_bg":"#7B2FBE","hdr_fg":"#ffffff","border":"#C084FC","explorer":"https://polygonscan.com"},
        "bsc":     {"hdr_bg":"#B45309","hdr_fg":"#ffffff","border":"#FCD34D","explorer":"https://bscscan.com"},
    }

    def _build_balances_tab(self):
        p = self.tab_balances

        # Wallet address card
        addr_card = card_frame(p)
        addr_card.pack(fill="x", padx=10, pady=(8,4))
        addr_inner = tk.Frame(addr_card, bg=C["card"], padx=12, pady=8)
        addr_inner.pack(fill="x")
        tk.Label(addr_inner, text="Hot Wallet:", font=("Segoe UI",9,"bold"),
                 bg=C["card"], fg=C["text_dim"]).pack(side="left")
        self.bal_addr_lbl = tk.Label(addr_inner,
            text=self.cfg.get("from_address") or "(not set — configure in Settings)",
            font=("Consolas",10), fg=C["accent"], bg=C["card"])
        self.bal_addr_lbl.pack(side="left", padx=8)

        # Toolbar
        bar = self._toolbar(p)
        self._btn(bar, "⟳ Refresh Now", self.refresh_balances, "Accent.TButton").pack(side="left", padx=4)
        self._btn(bar, "+ Add Custom Token", self._add_watch_token).pack(side="left", padx=4)
        self._btn(bar, "Show/Hide Zero Balances", self._toggle_zero_bal).pack(side="left", padx=4)
        self.bal_status = ttk.Label(bar, text="Click 'Refresh' to scan Polygon + BSC",
                                     foreground=C["text_dim"])
        self.bal_status.pack(side="left", padx=12)
        self.bal_next_lbl = tk.Label(bar, text="", font=("Segoe UI",8),
                                      bg=C["bg"], fg=C["text_dim"])
        self.bal_next_lbl.pack(side="right", padx=8)

        # Scrollable cards area
        cards_outer = tk.Frame(p, bg=C["bg"])
        cards_outer.pack(fill="both", expand=True, padx=10, pady=4)
        self.bal_canvas = tk.Canvas(cards_outer, bg=C["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(cards_outer, orient="vertical", command=self.bal_canvas.yview)
        self.bal_cards_inner = tk.Frame(self.bal_canvas, bg=C["bg"])
        self.bal_cards_inner.bind("<Configure>",
            lambda e: self.bal_canvas.configure(scrollregion=self.bal_canvas.bbox("all")))
        self.bal_canvas.create_window((0,0), window=self.bal_cards_inner, anchor="nw")
        self.bal_canvas.configure(yscrollcommand=vsb.set)
        self.bal_canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.bal_canvas.bind("<MouseWheel>",
            lambda e: self.bal_canvas.yview_scroll(int(-1*(e.delta/120)),"units"))

        # Custom token watch list
        watch_card = card_frame(p)
        watch_card.pack(fill="x", padx=10, pady=(0,8))
        wh = tk.Frame(watch_card, bg=C["header_bg"], pady=4)
        wh.pack(fill="x")
        tk.Label(wh, text="  📌 Custom Watched Tokens", font=("Segoe UI",9,"bold"),
                 bg=C["header_bg"], fg="#fff").pack(side="left")
        ttk.Button(wh, text="Remove Selected",
                   command=self._remove_watch_token).pack(side="right", padx=8, pady=2)

        cols_w = ("symbol","contract","decimals","network")
        self.watch_tree = ttk.Treeview(watch_card, columns=cols_w, show="headings", height=3)
        for c, w in (("symbol",70),("contract",390),("decimals",70),("network",130)):
            self.watch_tree.heading(c, text=c.title())
            self.watch_tree.column(c, width=w, anchor="w")
        wsb = ttk.Scrollbar(watch_card, orient="vertical", command=self.watch_tree.yview)
        self.watch_tree.configure(yscrollcommand=wsb.set)
        self.watch_tree.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        wsb.pack(side="right", fill="y", pady=4)
        self._reload_watch_tree()

    def _toggle_zero_bal(self):
        self._show_zero = not self._show_zero
        if self._last_bal_res: self._render_all_network_cards(self._last_bal_res)

    def _reload_watch_tree(self):
        for row in self.watch_tree.get_children(): self.watch_tree.delete(row)
        for t in self.cfg.get("extra_tokens", []):
            self.watch_tree.insert("", "end",
                values=(t.get("symbol","?"), t.get("address",""),
                        t.get("decimals",18), t.get("network","?")))

    def _add_watch_token(self):
        win = tk.Toplevel(self.root); win.title("Add Custom Watched Token")
        win.grab_set(); win.geometry("440x200"); win.resizable(False, False)
        win.configure(bg=C["bg"])
        ttk.Label(win, text="Network:").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        var_net = tk.StringVar(value="polygon")
        ttk.Combobox(win, textvariable=var_net, state="readonly",
                     values=list(SCAN_NETWORKS.keys()), width=22).grid(row=0, column=1, padx=8, pady=8)
        ttk.Label(win, text="Contract Address:").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        var_addr = tk.StringVar()
        ttk.Entry(win, textvariable=var_addr, width=44).grid(row=1, column=1, padx=8, pady=8)

        def _confirm():
            addr = var_addr.get().strip(); net = var_net.get()
            if not addr: messagebox.showwarning("Required","Enter a contract address.",parent=win); return
            win.destroy()
            rpcs = SCAN_NETWORKS.get(net,{}).get("rpcs",[self.cfg.get("rpc_url","")])
            def work():
                try:    return ChainClient.from_rpcs(rpcs).token_info(addr)
                except: return "???", 18
            def done(res):
                sym, dec = res
                sym = simpledialog.askstring("Symbol",f"Token symbol (detected: {sym}):",
                                              initialvalue=sym, parent=self.root) or sym
                try:
                    dec = int(simpledialog.askstring("Decimals",f"Decimals (detected: {dec}):",
                                                      initialvalue=str(dec), parent=self.root) or dec)
                except Exception: pass
                tokens = self.cfg.get("extra_tokens", [])
                tokens.append({"address":addr,"symbol":sym,"decimals":dec,"network":net})
                self.cfg["extra_tokens"] = tokens
                ConfigStore.save(self.cfg); self._reload_watch_tree()
                messagebox.showinfo("Added", f"{sym} added to {net} watchlist.")
            self.run_bg(work, on_done=done)
        ttk.Button(win, text="Detect & Add", command=_confirm).grid(row=2, column=1, sticky="w", padx=8, pady=12)

    def _remove_watch_token(self):
        sel = self.watch_tree.selection()
        if not sel: messagebox.showinfo("Select a row","Select a token row to remove."); return
        idx = self.watch_tree.index(sel[0])
        tokens = self.cfg.get("extra_tokens", [])
        if 0 <= idx < len(tokens):
            removed = tokens.pop(idx)
            self.cfg["extra_tokens"] = tokens
            ConfigStore.save(self.cfg); self._reload_watch_tree()
            messagebox.showinfo("Removed", f"Removed {removed.get('symbol','token')}.")

    def refresh_balances(self, silent=False):
        wallet = self.cfg.get("from_address","").strip()
        self.bal_addr_lbl.config(text=wallet or "(not set — configure in Settings)")
        if not wallet:
            if not silent:
                messagebox.showwarning("No wallet","Set 'From Wallet Address' in Settings first.")
            return
        self._bal_countdown = REFRESH_BALANCES_INTERVAL
        extras = list(self.cfg.get("extra_tokens",[]))
        self.bal_status.config(text="⏳  Scanning Polygon (137) and BSC (56) simultaneously…")

        def _scan_network(net_key, net_cfg):
            items = []; rpcs = net_cfg.get("rpcs",[])
            try:    chain = ChainClient.from_rpcs(rpcs)
            except ChainError as e:
                items.append({"symbol":net_cfg["native"],"balance":None,
                               "error":str(e),"type":"native","network":net_key})
                return net_key, items
            try:
                items.append({"symbol":net_cfg["native"],
                               "balance":chain.native_balance(wallet),
                               "contract":"native","type":"native","network":net_key})
            except Exception as e:
                items.append({"symbol":net_cfg["native"],"balance":None,
                               "error":str(e),"type":"native","network":net_key})
            for tok in net_cfg.get("tokens",[]):
                try:
                    bal = chain.token_balance(tok["address"],wallet,tok["decimals"])
                    items.append({"symbol":tok["symbol"],"balance":bal,"contract":tok["address"],
                                   "decimals":tok["decimals"],"type":"known","network":net_key})
                except Exception as e:
                    items.append({"symbol":tok["symbol"],"balance":None,"error":str(e),
                                   "contract":tok["address"],"type":"known","network":net_key})
            for tok in extras:
                if tok.get("network") == net_key:
                    try:
                        bal = chain.token_balance(tok["address"],wallet,tok["decimals"])
                        items.append({"symbol":tok["symbol"],"balance":bal,
                                       "contract":tok["address"],"decimals":tok["decimals"],
                                       "type":"extra","network":net_key})
                    except Exception as e:
                        items.append({"symbol":tok["symbol"],"balance":None,"error":str(e),
                                       "contract":tok["address"],"type":"extra","network":net_key})
            return net_key, items

        def work():
            results = {}; lock = threading.Lock()
            def run(k, cfg_n):
                key, items = _scan_network(k, cfg_n)
                with lock: results[key] = items
            threads = [threading.Thread(target=run,args=(k,cfg_n),daemon=True)
                       for k, cfg_n in SCAN_NETWORKS.items()]
            for t in threads: t.start()
            for t in threads: t.join(timeout=35)
            return results

        def done(results):
            self._last_bal_res = results
            nonzero = sum(1 for items in results.values()
                          for it in items if it.get("balance") and float(it.get("balance",0)) > 0)
            self.bal_status.config(
                text=f"✓  Scanned  •  {nonzero} token(s) with balance  •  {datetime.now().strftime('%H:%M:%S')}")
            self._render_all_network_cards(results)

        def err(e):
            self.bal_status.config(text=f"Error: {e}")
            if not silent: messagebox.showerror("Balance fetch failed", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    def _render_all_network_cards(self, results: dict):
        for w in self.bal_cards_inner.winfo_children(): w.destroy()
        CARD_COLS = 4; row_offset = 0

        for net_key, items in results.items():
            net_info = SCAN_NETWORKS.get(net_key, {})
            style    = self._NET_STYLE.get(net_key,
                       {"hdr_bg":"#374151","hdr_fg":"#fff","border":"#9CA3AF","explorer":""})
            visible  = [it for it in items
                        if self._show_zero or it.get("balance") is None
                        or float(it.get("balance",0)) > 0]
            nonzero  = sum(1 for it in items if it.get("balance") and float(it.get("balance",0)) > 0)

            # Section header
            hdr = tk.Frame(self.bal_cards_inner, bg=style["hdr_bg"], pady=8)
            hdr.grid(row=row_offset, column=0, columnspan=CARD_COLS,
                     sticky="ew", padx=4, pady=(12,2))
            for c in range(CARD_COLS): self.bal_cards_inner.columnconfigure(c, weight=1)
            tk.Label(hdr, text=f"  {net_info.get('label',net_key)}  —  {nonzero} with balance",
                     font=("Segoe UI",10,"bold"), bg=style["hdr_bg"], fg=style["hdr_fg"]).pack(side="left")
            tk.Label(hdr, text=f"Chain {net_info.get('chain_id','?')}  ",
                     font=("Segoe UI",9), bg=style["hdr_bg"], fg=style["hdr_fg"]).pack(side="right")
            row_offset += 1

            if not visible:
                tk.Label(self.bal_cards_inner, text="  No non-zero balances.",
                         fg=C["text_dim"], bg=C["bg"], font=("Segoe UI",9)
                         ).grid(row=row_offset, column=0, columnspan=CARD_COLS,
                                sticky="w", padx=14, pady=4)
                row_offset += 1; continue

            for i, item in enumerate(visible):
                card_row, card_col = divmod(i, CARD_COLS)
                r = row_offset + card_row

                has_bal  = item.get("balance") is not None
                is_zero  = has_bal and float(item.get("balance",0)) == 0
                type_tag = item.get("type","known")
                border   = {"native":style["hdr_bg"],"extra":"#7C3AED"}.get(type_tag, style["border"])
                card_bg  = "#F8FAFC" if is_zero else C["card"]

                card = tk.Frame(self.bal_cards_inner, bg=card_bg,
                                highlightbackground=border, highlightthickness=2,
                                padx=12, pady=10)
                card.grid(row=r, column=card_col, padx=5, pady=5, sticky="nsew")
                self.bal_cards_inner.rowconfigure(r, weight=0)

                sym_color = {"native":style["hdr_bg"],"extra":"#7C3AED"}.get(
                    type_tag, C["text_dim"] if is_zero else C["text"])
                tk.Label(card, text=item.get("symbol","?"),
                         font=("Segoe UI",14,"bold"), fg=sym_color, bg=card_bg).pack(anchor="w")

                if has_bal:
                    bal = float(item["balance"])
                    bal_str = f"{bal:.8f}" if type_tag=="native" else f"{bal:,.6f}"
                    tk.Label(card, text=bal_str,
                             font=("Consolas",11,"bold"),
                             fg=C["text_dim"] if is_zero else "#0F172A",
                             bg=card_bg).pack(anchor="w", pady=(3,1))
                else:
                    tk.Label(card, text=f"⚠ {str(item.get('error',''))[:80]}",
                             font=("Segoe UI",8), fg=C["danger"],
                             bg=card_bg, wraplength=180, justify="left").pack(anchor="w")

                contract = item.get("contract","")
                if contract and contract != "native":
                    short = contract[:8]+"…"+contract[-5:]
                    exp   = style.get("explorer","")
                    lbl   = tk.Label(card, text=short, font=("Consolas",7),
                                     fg="#94A3B8", bg=card_bg, cursor="hand2")
                    lbl.pack(anchor="w")
                    if exp:
                        url = f"{exp}/token/{contract}"
                        lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

                badge_color = {"native":style["hdr_bg"],"extra":"#7C3AED"}.get(type_tag, "#64748B")
                badge_text  = {"native":"Gas Coin","known":"Token","extra":"Custom"}.get(type_tag,"")
                if badge_text:
                    tk.Label(card, text=f" {badge_text} ", font=("Segoe UI",7,"bold"),
                             fg="#fff", bg=badge_color, padx=3).pack(anchor="w", pady=(4,0))

            row_offset += (len(visible) + CARD_COLS - 1) // CARD_COLS + 1

    # ══════════════════════════════════════════════════════════════════
    #  TAB 4 — Settings
    # ══════════════════════════════════════════════════════════════════
    def _build_settings_tab(self):
        inner = make_scrollable(self.tab_settings)
        inner.columnconfigure(0, weight=1)
        pad = {"padx": 14, "pady": 6}

        def section(title, row):
            f = ttk.LabelFrame(inner, text=title, padding=12)
            f.grid(row=row, column=0, sticky="ew", **pad)
            f.columnconfigure(1, weight=1)
            return f

        def row_lbl(f, text, r):
            ttk.Label(f, text=text).grid(row=r, column=0, sticky="w", pady=3)

        def row_entry(f, var, r, show=""):
            e = ttk.Entry(f, textvariable=var, show=show)
            e.grid(row=r, column=1, columnspan=2, sticky="ew", padx=(8,0), pady=3)
            return e

        # ── API ──────────────────────────────────────────────────────
        api_box = section("🌐  Backend API", 0)
        row_lbl(api_box, "API Base URL", 0)
        self.var_api_base = tk.StringVar(value=self.cfg["api_base_url"])
        row_entry(api_box, self.var_api_base, 0)
        row_lbl(api_box, "Authorization Header", 1)
        self.var_auth_hdr = tk.StringVar(value=self.cfg["auth_header"])
        row_entry(api_box, self.var_auth_hdr, 1, show="*")
        ttk.Label(api_box, text="e.g.  Bearer 1|abcde…", foreground=C["text_dim"]
                  ).grid(row=2, column=1, sticky="w", padx=(8,0))
        self._btn(api_box, "Test API Connection", self._test_api, "Accent.TButton"
                  ).grid(row=3, column=1, sticky="w", pady=6, padx=(8,0))

        # ── Blockchain ────────────────────────────────────────────────
        chain_box = section("⛓  Blockchain / Payout Token", 1)
        row_lbl(chain_box, "Payout network", 0)
        self.var_network = tk.StringVar(value=self.cfg["network"])
        net_cb = ttk.Combobox(chain_box, textvariable=self.var_network, state="readonly",
                               values=list(NETWORK_PRESETS.keys()), width=24)
        net_cb.grid(row=0, column=1, sticky="w", padx=(8,0), pady=3)
        net_cb.bind("<<ComboboxSelected>>", self._on_net_change)
        self.net_lbl = ttk.Label(chain_box,
            text=NETWORK_PRESETS.get(self.cfg["network"],{}).get("label",""), foreground=C["accent"])
        self.net_lbl.grid(row=0, column=2, sticky="w", padx=8)

        row_lbl(chain_box, "RPC URL", 1)
        self.var_rpc = tk.StringVar(value=self.cfg["rpc_url"])
        row_entry(chain_box, self.var_rpc, 1)
        row_lbl(chain_box, "Token Contract", 2)
        self.var_contract = tk.StringVar(value=self.cfg["token_contract"])
        row_entry(chain_box, self.var_contract, 2)
        row_lbl(chain_box, "Token Decimals", 3)
        self.var_decimals = tk.IntVar(value=self.cfg["decimals"])
        ttk.Spinbox(chain_box, from_=0, to=18, textvariable=self.var_decimals, width=6
                    ).grid(row=3, column=1, sticky="w", padx=(8,0), pady=3)
        row_lbl(chain_box, "Amount field", 4)
        self.var_amount_src = tk.StringVar(value=self.cfg["amount_source"])
        af = ttk.Frame(chain_box); af.grid(row=4, column=1, columnspan=2, sticky="w", padx=(8,0))
        ttk.Radiobutton(af, text="net_amount_bh  (BH token)", variable=self.var_amount_src, value="bh").pack(anchor="w")
        ttk.Radiobutton(af, text="net_amount_usd  (USDT)",    variable=self.var_amount_src, value="usd").pack(anchor="w")
        self._btn(chain_box, "Test RPC Connection", self._test_rpc, "Accent.TButton"
                  ).grid(row=5, column=1, sticky="w", pady=6, padx=(8,0))

        # ── Wallet ────────────────────────────────────────────────────
        wallet_box = section("💳  Sending Wallet (hot wallet)", 2)
        tk.Label(wallet_box, text="⚠  This wallet pays customers. Only fund it with what you need to send.",
                 fg=C["warning"], wraplength=680, justify="left", bg=C["bg"]
                 ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,8))
        row_lbl(wallet_box, "From Address", 1)
        self.var_from = tk.StringVar(value=self.cfg["from_address"])
        row_entry(wallet_box, self.var_from, 1)
        row_lbl(wallet_box, "Private Key", 2)
        pk_f = ttk.Frame(wallet_box); pk_f.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8,0), pady=3)
        self.var_pk   = tk.StringVar()
        self.pk_entry = ttk.Entry(pk_f, textvariable=self.var_pk, show="*")
        self.pk_entry.pack(side="left", fill="x", expand=True)
        self.var_show_pk = tk.BooleanVar(value=False)
        ttk.Checkbutton(pk_f, text="show", variable=self.var_show_pk,
                         command=lambda: self.pk_entry.config(
                             show="" if self.var_show_pk.get() else "*")).pack(side="left", padx=4)
        self.var_persist_pk = tk.BooleanVar(value=self.cfg.get("pk_set", False))
        ttk.Checkbutton(wallet_box, text="Encrypt and save key to disk (passphrase required)",
                         variable=self.var_persist_pk).grid(row=3, column=1, columnspan=2, sticky="w", padx=(8,0))
        status_str = "saved (encrypted)" if self.cfg.get("pk_set") else "not saved to disk"
        self.pk_status = ttk.Label(wallet_box, text=f"Key status: {status_str}", foreground=C["text_dim"])
        self.pk_status.grid(row=4, column=1, sticky="w", padx=(8,0))
        btn_f = ttk.Frame(wallet_box); btn_f.grid(row=5, column=1, columnspan=2, sticky="w", padx=(8,0), pady=6)
        self._btn(btn_f, "Save Wallet Settings", self._save_wallet, "Success.TButton").pack(side="left", padx=3)
        self._btn(btn_f, "Clear Saved Key",       self._clear_pk).pack(side="left", padx=3)
        self._btn(btn_f, "Check Balances",        self._check_balances, "Accent.TButton").pack(side="left", padx=3)

        # ── Simulation / Live ─────────────────────────────────────────
        sim_box = section("⚠  LIVE / SIMULATION MODE", 3)
        sim_box.columnconfigure(0, weight=1)
        self.sim_banner = tk.Label(sim_box, text="", font=("Segoe UI",10,"bold"),
                                    anchor="center", pady=10)
        self.sim_banner.grid(row=0, column=0, columnspan=3, sticky="ew")

        def _upd(*_):
            if self.var_simulate.get():
                self.sim_banner.config(text="🟡  SIMULATION MODE — no real on-chain transactions",
                                        bg=C["sim_bg"], fg=C["sim_fg"])
            else:
                self.sim_banner.config(text="🔴  LIVE MODE — real funds WILL be sent on-chain",
                                        bg=C["live_bg"], fg=C["live_fg"])
            self._update_mode_badge()
        self.var_simulate.trace_add("write", _upd); _upd()

        btn_sim = ttk.Frame(sim_box); btn_sim.grid(row=1, column=0, pady=(8,0))
        self._btn(btn_sim, "Enable SIMULATION (safe)",
                  lambda: self.var_simulate.set(True), "Accent.TButton").pack(side="left", padx=6)
        self._btn(btn_sim, "Enable LIVE MODE (real funds)",
                  self._go_live, "Danger.TButton").pack(side="left", padx=6)

        # ── Live refresh control ──────────────────────────────────────
        lr_box = section("🔄  Live Auto-Refresh", 4)
        tk.Label(lr_box, text=f"All Withdrawals: every {REFRESH_ALL_INTERVAL}s  |  "
                               f"Pending: every {REFRESH_PENDING_INTERVAL}s  |  "
                               f"Balances: every {REFRESH_BALANCES_INTERVAL}s",
                 bg=C["bg"], fg=C["text_dim"], font=("Segoe UI",9)).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0,6))
        self.var_pause = tk.BooleanVar(value=False)
        ttk.Checkbutton(lr_box, text="Pause all auto-refresh",
                         variable=self.var_pause,
                         command=lambda: setattr(self, "_live_paused", self.var_pause.get())
                         ).grid(row=1, column=0, sticky="w")

        # ── Bottom save ───────────────────────────────────────────────
        bot = ttk.Frame(inner); bot.grid(row=5, column=0, sticky="ew", padx=14, pady=8)
        self._btn(bot, "💾 Save All Settings", self._save_all, "Success.TButton").pack(side="left", padx=4)
        self._btn(bot, "Reset to Defaults",    self._reset).pack(side="left", padx=4)

    # ── Settings helpers ──────────────────────────────────────────────
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
        net = self.var_network.get(); p = NETWORK_PRESETS.get(net, {})
        self.var_rpc.set(p.get("default_rpc",""))
        self.var_contract.set(p.get("token_contract",""))
        self.var_decimals.set(p.get("decimals",18))
        if "amount_source" in p: self.var_amount_src.set(p["amount_source"])
        self.net_lbl.config(text=p.get("label",""))

    def _save_all(self):
        self._collect(); ConfigStore.save(self.cfg); self._set_api()
        messagebox.showinfo("Saved", "All settings saved.")

    def _save_wallet(self):
        self._collect()
        new_pk = self.var_pk.get().strip()
        if new_pk:
            if self.var_persist_pk.get():
                pw = ask_pass(self.root, "Set a passphrase to encrypt the key", confirm=True)
                if not pw: messagebox.showwarning("Cancelled","Key was not saved."); return
                salt, token = encrypt_secret(new_pk, pw)
                self.cfg.update({"pk_set":True,"pk_salt":salt,"pk_token":token})
                self.pk_status.config(text="Key status: saved (encrypted)")
            else:
                self.cfg.update({"pk_set":False,"pk_salt":"","pk_token":""})
                self.pk_status.config(text="Key status: in memory only (not saved to disk)")
            self.runtime_pk = new_pk; self.var_pk.set("")
        ConfigStore.save(self.cfg); self._set_api()
        messagebox.showinfo("Saved","Wallet settings saved.")

    def _clear_pk(self):
        if not messagebox.askyesno("Confirm","Delete the encrypted key from disk?"): return
        self.cfg.update({"pk_set":False,"pk_salt":"","pk_token":""})
        self.runtime_pk = None; ConfigStore.save(self.cfg)
        self.pk_status.config(text="Key status: not saved to disk")
        messagebox.showinfo("Cleared","Saved key removed.")

    def _reset(self):
        if not messagebox.askyesno("Confirm",
            "Reset ALL settings (including saved key and pending TX store) to defaults?"): return
        ConfigStore.delete(); self.cfg = dict(DEFAULT_CONFIG); self.runtime_pk = None
        messagebox.showinfo("Reset","Settings reset. Please restart the app.")

    def _test_api(self):
        self._collect(); self._set_api()
        def work(): return self.api.stats()
        def done(st):
            messagebox.showinfo("API OK",
                f"Connected.\nPending: {st.get('pending_count',0)}\n"
                f"Total: {st.get('total_requests',0)}")
        def err(e): messagebox.showerror("API Test Failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _test_rpc(self):
        self._collect(); rpcs = [self.cfg["rpc_url"]]
        def work(): return ChainClient.from_rpcs(rpcs).chain_id()
        def done(cid): messagebox.showinfo("RPC OK", f"Connected. Chain ID: {cid}")
        def err(e):    messagebox.showerror("RPC Test Failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _check_balances(self):
        self._collect()
        if not self.cfg["from_address"]:
            messagebox.showwarning("Missing","Enter 'From Wallet Address' first."); return
        self.nb.select(self.tab_balances); self.refresh_balances()

    def _go_live(self):
        if not messagebox.askyesno("Enable LIVE mode?",
            "⚠ WARNING\n\nReal on-chain transactions will be sent. Real funds will move.\n"
            "This cannot be undone. Are you sure?", icon="warning"): return
        if not messagebox.askyesno("Second confirmation",
            "Confirm: clicking Approve will broadcast real token transfers.\n\n"
            "YES — I am sure, enable LIVE mode.", icon="warning"): return
        self.var_simulate.set(False)

# ══════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()

    def report_callback_exception(exc, val, tb):
        _show_fatal("".join(traceback.format_exception(exc, val, tb)))
    root.report_callback_exception = report_callback_exception

    App(root)
    root.mainloop()

if __name__ == "__main__":
    try:    main()
    except SystemExit: raise
    except BaseException: _show_fatal(traceback.format_exc())
