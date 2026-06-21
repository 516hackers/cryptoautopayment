#!/usr/bin/env python3
"""
Infinity Meta Hub  v4.0.0
==========================
Single-file desktop admin app — Ayamil Coders

CHANGELOG v4.0.0  (Security Firewall + Live Refresh + UI fix)
---------------------------------------------------------------
  • FIX: Active tab label text was invisible. Root cause — the Windows
    "vista" ttk theme draws Notebook tabs with the native OS theme engine
    and silently ignores custom foreground/background colors, so the
    SELECTED tab's text was being rendered theme-default-on-theme-default
    instead of our white-on-navy scheme. Fixed by forcing the fully
    Python-drawn "clam" theme, which honors every color we set, plus an
    explicit hover/selected/unselected foreground map so text is always
    legible in every state.
  • LIVE, TAB-AWARE AUTO-REFRESH: whichever tab is currently in view now
    polls fast (5-8s, marked 🟢 LIVE) and refreshes the instant you switch
    to it. Tabs not being watched fall back to a slower background
    interval to save API/RPC calls. TX History now also auto-refreshes.
  • ADVANCED SECURITY / FIREWALL LAYER (new, on top of the v3.0.0 TX
    validation pipeline):
      - Per-transaction amount cap (configurable)
      - Daily cumulative approval cap (configurable, persisted)
      - Destination-address blocklist
      - Duplicate-destination & statistical anomaly advisory warnings
      - Rate limiting (max approvals / time window)
      - Emergency Kill Switch (instant, app-wide live-send block)
      - High-value typed re-confirmation ("type APPROVE")
      - Hard-coded sanity ceiling (independent of user config)
      - Strict regex wallet-address format validation
      - HTTPS-only RPC enforcement (rejects insecure endpoints)
      - Domain-allowlist firewall on outbound explorer links
      - Tamper-evident, hash-chained audit log (tx_history.json) with an
        integrity verifier
      - Idle auto-lock: decrypted private key is wiped from memory after
        inactivity
      - Failed-passphrase lockout (brute-force protection)
      - Dedicated 🛡 Security tab + quick-access header kill button
  • All v3.0.0 critical fixes (pre-flight balance checks, receipt status
    validation before approve, crash-safe pending TX store, etc.) are
    retained unchanged.
"""

import os, sys, json, base64, threading, traceback, webbrowser, time, hashlib, re, math, statistics
from datetime import datetime
from urllib.parse import urlparse

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ── App constants ──────────────────────────────────────────────────────
APP_TITLE   = "Infinity Meta Hub"
APP_VERSION = "4.0.0"
APP_CREDIT  = "Developed By Ayamil Coders"
CONFIG_DIR  = os.path.join(os.path.expanduser("~"), ".withdrawal_admin")
CONFIG_PATH      = os.path.join(CONFIG_DIR, "config.json")
PENDING_TX_PATH  = os.path.join(CONFIG_DIR, "pending_tx.json")
TX_HISTORY_PATH  = os.path.join(CONFIG_DIR, "tx_history.json")
DAILY_LIMIT_PATH = os.path.join(CONFIG_DIR, "daily_limits.json")
BLOCKLIST_PATH   = os.path.join(CONFIG_DIR, "blocked_addresses.json")
SECURITY_LOG_PATH= os.path.join(CONFIG_DIR, "security_log.json")
LOCKOUT_PATH     = os.path.join(CONFIG_DIR, "lockout.json")

# ── Live refresh intervals (seconds) ────────────────────────────────────
# v4.0.0: tab-aware adaptive refresh. The tab currently in view polls fast
# ("live"); tabs not being watched poll slower in the background.
LIVE_INTERVAL_ALL        = 8
LIVE_INTERVAL_PENDING    = 5
LIVE_INTERVAL_BALANCES   = 20
LIVE_INTERVAL_HISTORY    = 10
BACKGROUND_INTERVAL_ALL      = 45
BACKGROUND_INTERVAL_PENDING  = 30
BACKGROUND_INTERVAL_BALANCES = 90
BACKGROUND_INTERVAL_HISTORY  = 60

# TX confirmation — how many seconds to wait for mining, how many confirmations required
TX_WAIT_TIMEOUT      = 180   # seconds to wait for tx to be mined
TX_CONFIRMATIONS_REQ = 2     # minimum block confirmations before marking approved

# ── Security / firewall constants ───────────────────────────────────────
DEFAULT_MAX_TX_AMOUNT        = 5000.0    # max amount per single withdrawal
DEFAULT_DAILY_LIMIT          = 25000.0   # max cumulative approved per calendar day
DEFAULT_RATE_LIMIT_COUNT     = 10        # max approvals
DEFAULT_RATE_LIMIT_WINDOW    = 60        # seconds
DEFAULT_HIGH_VALUE_THRESHOLD = 1000.0    # batches above this need typed confirmation
SANITY_MAX_AMOUNT            = 1_000_000 # hard-coded backstop, independent of config
MAX_PASSPHRASE_ATTEMPTS      = 3
LOCKOUT_DURATION_SECONDS     = 300       # 5 minutes
IDLE_LOCK_SECONDS            = 600       # 10 minutes idle -> wipe key from memory
ANOMALY_STDEV_MULTIPLIER     = 3.0       # flag amounts > mean + k*stdev
ANOMALY_MIN_SAMPLES          = 8
ALLOWED_EXPLORER_HOSTS = {
    "polygonscan.com", "bscscan.com", "etherscan.io",
}
ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

# ── Colour palette ─────────────────────────────────────────────────────
C = {
    "bg":        "#F0F4FF",
    "card":      "#FFFFFF",
    "hdr_bg":    "#1E3A8A",
    "hdr_fg":    "#FFFFFF",
    "accent":    "#3B82F6",
    "accent2":   "#6366F1",
    "success":   "#16A34A",
    "warning":   "#D97706",
    "danger":    "#DC2626",
    "text":      "#1E293B",
    "text_dim":  "#64748B",
    "border":    "#CBD5E1",
    "sim_bg":    "#FEF9C3",
    "sim_fg":    "#92400E",
    "live_bg":   "#FEE2E2",
    "live_fg":   "#991B1B",
    "log_bg":    "#F8FAFC",
    "row_pend":  "#FFFBEB",
    "row_appr":  "#DCFCE7",
    "row_rej":   "#FEE2E2",
    "row_fail":  "#FFE4E6",
    "row_store": "#F3E8FF",
}

# ── Network definitions ────────────────────────────────────────────────
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
    "polygon_bh": {
        "label":"Polygon — BH Token  (sends net_amount_bh)",
        "chain_id":137, "token_contract":"0x68a6EA8e9aB0824251061DD122aDA8493e62409d",
        "decimals":18, "default_rpc":"https://polygon-rpc.com",
        "explorer_tx":"https://polygonscan.com/tx/", "native_symbol":"MATIC","amount_source":"bh",
    },
    "polygon_usdt": {
        "label":"Polygon — USDT  (sends net_amount_usd)",
        "chain_id":137, "token_contract":"0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "decimals":6, "default_rpc":"https://polygon-rpc.com",
        "explorer_tx":"https://polygonscan.com/tx/", "native_symbol":"MATIC","amount_source":"usd",
    },
    "bsc_usdt": {
        "label":"BSC — USDT  (sends net_amount_usd)",
        "chain_id":56, "token_contract":"0x55d398326f99059fF775485246999027B3197955",
        "decimals":18, "default_rpc":"https://bsc-dataseed.binance.org/",
        "explorer_tx":"https://bscscan.com/tx/", "native_symbol":"BNB","amount_source":"usd",
    },
}

DEFAULT_CONFIG = {
    "api_base_url":"https://yourdomain.com/api/v1/admin/withdrawals",
    "auth_header":"", "network":"polygon_bh",
    "rpc_url":NETWORK_PRESETS["polygon_bh"]["default_rpc"],
    "token_contract":NETWORK_PRESETS["polygon_bh"]["token_contract"],
    "decimals":NETWORK_PRESETS["polygon_bh"]["decimals"],
    "amount_source":"bh", "from_address":"", "simulate_only":True,
    "pk_set":False, "pk_salt":"", "pk_token":"", "extra_tokens":[],
    # v4.0.0 security/firewall settings
    "max_tx_amount": DEFAULT_MAX_TX_AMOUNT,
    "daily_limit": DEFAULT_DAILY_LIMIT,
    "rate_limit_count": DEFAULT_RATE_LIMIT_COUNT,
    "rate_limit_window": DEFAULT_RATE_LIMIT_WINDOW,
    "high_value_threshold": DEFAULT_HIGH_VALUE_THRESHOLD,
    "kill_switch_enabled": False,
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
#  TX History — permanent, tamper-evident (hash-chained) audit cache
# ══════════════════════════════════════════════════════════════════════
class TxHistory:
    """
    Permanent audit log stored in tx_history.json.
    Every approve/reject/blocked action is recorded here.

    v4.0.0: each record is hash-chained to the previous one
    (record_hash = SHA256(prev_hash + sorted-json(record))). Editing or
    deleting a past entry breaks the chain from that point forward, which
    TxHistory.verify_integrity() will detect. Records written before this
    upgrade have no record_hash and are treated as "legacy" — the chain
    simply starts fresh at the first hashed record.
    """
    @staticmethod
    def _load() -> list:
        try:
            with open(TX_HISTORY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @staticmethod
    def _write(data: list):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(TX_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _hash_record(rec: dict, prev_hash: str) -> str:
        payload = json.dumps(rec, sort_keys=True, default=str)
        return hashlib.sha256((prev_hash + "|" + payload).encode("utf-8")).hexdigest()

    @classmethod
    def record(cls, withdrawal_id, action: str, tx_hash: str = "",
                tx_status: str = "", amount: float = 0,
                wallet: str = "", network: str = "",
                note: str = "", error: str = ""):
        data = cls._load()
        prev_hash = data[-1].get("record_hash", "") if data else ""
        rec = {
            "id":            len(data) + 1,
            "withdrawal_id": withdrawal_id,
            "action":        action,           # approve / reject / approve_failed_tx / approve_preflight_fail / approve_blocked_* / approve_error
            "tx_hash":       tx_hash,
            "tx_status":     tx_status,        # success / failed / reverted / simulated / skipped / timeout / n/a
            "amount":        amount,
            "wallet":        wallet,
            "network":       network,
            "note":          note,
            "error":         error,
            "timestamp":     datetime.now().isoformat(),
            "prev_hash":     prev_hash,
        }
        rec["record_hash"] = cls._hash_record(rec, prev_hash)
        data.append(rec)
        cls._write(data)

    @classmethod
    def all(cls) -> list:
        return cls._load()

    @classmethod
    def for_withdrawal(cls, wid) -> list:
        return [r for r in cls._load() if str(r.get("withdrawal_id")) == str(wid)]

    @classmethod
    def verify_integrity(cls):
        """
        Recomputes the hash chain and compares against stored record_hash
        values. Returns (ok: bool, broken_at_record_id: int|None, legacy_count: int).
        """
        data = cls._load()
        prev = ""
        legacy_count = 0
        for rec in data:
            if "record_hash" not in rec:
                legacy_count += 1
                continue
            stored_hash = rec.get("record_hash", "")
            check = {k: v for k, v in rec.items() if k != "record_hash"}
            expected = cls._hash_record(check, prev)
            if stored_hash != expected:
                return False, rec.get("id"), legacy_count
            prev = stored_hash
        return True, None, legacy_count

# ══════════════════════════════════════════════════════════════════════
#  Pending TX store — double-payment prevention
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
    def put(cls, wid, tx_hash, to_addr, amount, network):
        d = cls._load()
        d[str(wid)] = {"tx_hash":tx_hash,"to_addr":to_addr,"amount":amount,
                        "network":network,"sent_at":datetime.now().isoformat()}
        cls._write(d)

    @classmethod
    def remove(cls, wid):
        d = cls._load(); d.pop(str(wid), None); cls._write(d)

    @classmethod
    def all(cls) -> dict: return cls._load()

# ══════════════════════════════════════════════════════════════════════
#  SECURITY / FIREWALL LAYER  (v4.0.0)
# ══════════════════════════════════════════════════════════════════════
class SecurityLog:
    """Append-only log of security-relevant events (separate from the
    financial TX audit trail): lockouts, blocked-address attempts, kill
    switch toggles, rate-limit hits, manual locks, etc."""
    @staticmethod
    def _load() -> list:
        try:
            with open(SECURITY_LOG_PATH, encoding="utf-8") as f: return json.load(f)
        except Exception: return []

    @staticmethod
    def _write(data: list):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SECURITY_LOG_PATH, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

    @classmethod
    def record(cls, event_type: str, detail: str = ""):
        data = cls._load()
        data.append({"id": len(data) + 1, "event": event_type, "detail": detail,
                     "timestamp": datetime.now().isoformat()})
        cls._write(data)

    @classmethod
    def all(cls) -> list:
        return cls._load()


class DailyLimitTracker:
    """Tracks cumulative approved amount per calendar day so a daily
    spending cap can be enforced even across app restarts."""
    @staticmethod
    def _load() -> dict:
        try:
            with open(DAILY_LIMIT_PATH, encoding="utf-8") as f: return json.load(f)
        except Exception: return {}

    @staticmethod
    def _write(d: dict):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(DAILY_LIMIT_PATH, "w", encoding="utf-8") as f: json.dump(d, f, indent=2)

    @classmethod
    def today_total(cls) -> float:
        d = cls._load()
        key = datetime.now().strftime("%Y-%m-%d")
        return float(d.get(key, 0.0))

    @classmethod
    def add(cls, amount: float):
        d = cls._load()
        key = datetime.now().strftime("%Y-%m-%d")
        d[key] = float(d.get(key, 0.0)) + float(amount)
        cutoff = datetime.now().timestamp() - 30 * 86400
        for k in list(d.keys()):
            try:
                if datetime.strptime(k, "%Y-%m-%d").timestamp() < cutoff:
                    del d[k]
            except Exception:
                pass
        cls._write(d)


class AddressBlocklist:
    """Admin-managed list of destination addresses that must never receive
    an automated payout (known compromised wallets, disputed accounts,
    sanctioned addresses, etc)."""
    @staticmethod
    def _load() -> list:
        try:
            with open(BLOCKLIST_PATH, encoding="utf-8") as f: return json.load(f)
        except Exception: return []

    @staticmethod
    def _write(lst: list):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(BLOCKLIST_PATH, "w", encoding="utf-8") as f: json.dump(lst, f, indent=2)

    @classmethod
    def is_blocked(cls, addr: str) -> bool:
        addr = (addr or "").strip().lower()
        return any(addr == a.get("address", "").lower() for a in cls._load())

    @classmethod
    def add(cls, addr: str, reason: str = ""):
        lst = cls._load()
        lst.append({"address": addr, "reason": reason, "added_at": datetime.now().isoformat()})
        cls._write(lst)

    @classmethod
    def remove(cls, addr: str):
        lst = [a for a in cls._load() if a.get("address", "").lower() != addr.lower()]
        cls._write(lst)

    @classmethod
    def all(cls) -> list:
        return cls._load()


class LockoutGuard:
    """Brute-force protection on the wallet passphrase. After
    MAX_PASSPHRASE_ATTEMPTS consecutive failures, wallet operations are
    locked for LOCKOUT_DURATION_SECONDS."""
    @staticmethod
    def _load() -> dict:
        try:
            with open(LOCKOUT_PATH, encoding="utf-8") as f: return json.load(f)
        except Exception: return {"failed_attempts": 0, "locked_until": None}

    @staticmethod
    def _write(d: dict):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LOCKOUT_PATH, "w", encoding="utf-8") as f: json.dump(d, f, indent=2)

    @classmethod
    def is_locked(cls):
        d = cls._load()
        lu = d.get("locked_until")
        if lu and datetime.now().timestamp() < lu:
            return True, lu
        return False, None

    @classmethod
    def record_failure(cls) -> dict:
        d = cls._load()
        d["failed_attempts"] = d.get("failed_attempts", 0) + 1
        if d["failed_attempts"] >= MAX_PASSPHRASE_ATTEMPTS:
            d["locked_until"] = datetime.now().timestamp() + LOCKOUT_DURATION_SECONDS
            d["failed_attempts"] = 0
        cls._write(d)
        return d

    @classmethod
    def record_success(cls):
        cls._write({"failed_attempts": 0, "locked_until": None})


def is_valid_address(addr: str) -> bool:
    """Strict 0x + 40 hex char format check — the input-sanitization
    'firewall' for anything coming back from the API before it's ever
    used to build a transaction or a link."""
    return bool(addr) and bool(ADDR_RE.match(addr.strip()))


def safe_open_url(url: str):
    """Domain-allowlist firewall for outbound browser links built from
    on-chain / API data (tx hashes, wallet addresses). Refuses non-HTTPS
    links outright and asks for confirmation before opening an
    unrecognized domain."""
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if parsed.scheme != "https":
            messagebox.showwarning("Blocked", "Refusing to open a non-HTTPS link for security reasons.")
            return
        known = any(host == h or host.endswith("." + h) for h in ALLOWED_EXPLORER_HOSTS)
        if not known:
            if not messagebox.askyesno("Unrecognized domain",
                    f"This link points to a domain that isn't a known block explorer:\n\n{host}\n\nOpen anyway?"):
                return
        webbrowser.open(url)
    except Exception:
        pass

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
#  Config
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
        # Note: intentionally does NOT remove tx_history.json or
        # security_log.json — a "reset to defaults" should never be able
        # to erase the audit trail.
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
        if not self.base_url: raise ApiError("API Base URL not set.")
        try:
            r = self.session.request(method, self.base_url + path,
                                     headers=self._h(), params=params, json=body, timeout=20)
        except requests.RequestException as e: raise ApiError(f"Network error: {e}")
        try:    data = r.json()
        except: raise ApiError(f"Non-JSON response (HTTP {r.status_code})")
        if r.status_code >= 400 or data.get("success") is False:
            raise ApiError(data.get("message") or f"API error (HTTP {r.status_code})")
        return data

    def list_all(self, status=None, per_page=500):
        p = {"per_page": per_page}
        if status and status != "all": p["status"] = status
        d = self._req("GET", "/", params=p)
        return d.get("data",{}).get("data", d.get("data",[]))

    def list_pending(self, per_page=500):
        d = self._req("GET", "/pending", params={"per_page": per_page})
        return d.get("data",{}).get("data", d.get("data",[]))

    def stats(self):
        return self._req("GET", "/stats").get("data", {})

    def approve(self, wid, tx_hash: str, note: str = ""):
        return self._req("POST", f"/{wid}/approve",
                         body={"transaction_hash": tx_hash, "admin_note": note})

    def reject(self, wid, note: str):
        return self._req("POST", f"/{wid}/reject", body={"admin_note": note})

# ══════════════════════════════════════════════════════════════════════
#  Chain client — web3 import deferred (fast startup)
# ══════════════════════════════════════════════════════════════════════
class ChainError(Exception): pass
class TxFailedError(ChainError):
    """Raised when a tx was broadcast but mined with status=0 (reverted)."""
    def __init__(self, tx_hash: str, reason: str = ""):
        self.tx_hash = tx_hash
        self.reason  = reason
        super().__init__(f"TX FAILED on-chain (status=0): {tx_hash}\nReason: {reason or 'execution reverted'}")

class PreflightError(ChainError):
    """Raised when a pre-send validation fails (balance, address, amount)."""
    pass

class ChainClient:
    def __init__(self, rpc_url: str):
        if not rpc_url: raise ChainError("RPC URL not configured.")
        # v4.0.0 firewall: refuse insecure (non-HTTPS) RPC endpoints outright.
        if not rpc_url.lower().startswith("https://"):
            raise ChainError(f"🚫 Insecure RPC blocked — HTTPS is required: {rpc_url}")
        # Deferred import — web3 loads only when first ChainClient is created
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

    def chain_id(self) -> int: return self.w3.eth.chain_id

    def next_nonce(self, address: str) -> int:
        return self.w3.eth.get_transaction_count(self.cs(address), "pending")

    def current_block(self) -> int:
        return self.w3.eth.block_number

    def get_receipt(self, tx_hash: str) -> dict:
        """Returns receipt dict or None if not yet mined."""
        try:    return self.w3.eth.get_transaction_receipt(tx_hash)
        except: return None

    def wait_for_receipt(self, tx_hash: str,
                         timeout: int = TX_WAIT_TIMEOUT,
                         poll_interval: int = 3) -> dict:
        """
        Poll for receipt until mined or timeout.
        Returns receipt dict.
        Raises ChainError on timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            receipt = self.get_receipt(tx_hash)
            if receipt is not None:
                return receipt
            time.sleep(poll_interval)
        raise ChainError(
            f"TX not mined within {timeout}s: {tx_hash}\n"
            f"Check the explorer manually. TX may still confirm later."
        )

    def validate_receipt(self, receipt: dict, tx_hash: str):
        """
        CRITICAL: Check receipt.status.
        status=1 → success
        status=0 → reverted/failed — raises TxFailedError
        """
        status = receipt.get("status")
        if status == 1:
            return  # success
        elif status == 0:
            raise TxFailedError(tx_hash,
                "ERC20 transfer reverted on-chain (likely insufficient token balance or contract error).")
        else:
            raise ChainError(f"Unknown receipt status={status} for tx {tx_hash}")

    def preflight_checks(self, from_addr: str, to_addr: str,
                          amount: float, contract_addr: str,
                          decimals: int, required_gas_native: float = 0.001):
        """
        Run ALL pre-send validation checks BEFORE touching the chain.
        Raises PreflightError with a clear message if anything fails.
        """
        errors = []

        # 1. Amount
        if amount <= 0:
            errors.append(f"Amount is {amount} — cannot send zero or negative.")
        units = int(round(amount * (10 ** decimals)))
        if units <= 0:
            errors.append(f"Amount {amount} rounds to 0 units at {decimals} decimals.")

        # 2. To address validity
        try:
            to_cs = self.cs(to_addr)
            if to_cs == self.cs(from_addr):
                errors.append("To address is the same as From address — would send to yourself.")
        except ChainError as e:
            errors.append(f"Invalid recipient address: {e}")

        if errors:
            raise PreflightError("Pre-send validation failed:\n• " + "\n• ".join(errors))

        # 3. Token balance check
        try:
            token_bal = self.token_balance(contract_addr, from_addr, decimals)
            if token_bal < amount:
                errors.append(
                    f"Insufficient token balance: wallet has {token_bal:.6f}, "
                    f"need {amount:.6f}. "
                    f"Difference: {amount - token_bal:.6f} tokens short."
                )
        except Exception as e:
            errors.append(f"Could not check token balance: {e}")

        # 4. Native coin (gas) check
        try:
            native_bal = self.native_balance(from_addr)
            if native_bal < required_gas_native:
                errors.append(
                    f"Insufficient native coin for gas: wallet has {native_bal:.6f}, "
                    f"need at least {required_gas_native:.4f} for gas fees."
                )
        except Exception as e:
            errors.append(f"Could not check native balance: {e}")

        if errors:
            raise PreflightError("Pre-send validation failed:\n• " + "\n• ".join(errors))

    def send_token(self, private_key: str, from_addr: str, to_addr: str,
                   amount: float, contract_addr: str, decimals: int,
                   chain_id: int, nonce: int) -> str:
        """
        Build, sign and broadcast one ERC-20 transfer.
        Returns tx_hash ONLY — does NOT check receipt here.
        Receipt must be checked separately via wait_for_receipt + validate_receipt.
        """
        from eth_account import Account
        from_cs     = self.cs(from_addr)
        to_cs       = self.cs(to_addr)
        contract_cs = self.cs(contract_addr)

        acct = Account.from_key(private_key)
        if acct.address.lower() != from_cs.lower():
            raise ChainError(
                f"Private key address ({acct.address}) ≠ configured From address ({from_cs}).")

        units = int(round(amount * (10 ** decimals)))
        if units <= 0:
            raise ChainError(f"Amount rounds to zero ({amount} × 10^{decimals})")

        try:    gas_price = self.w3.eth.gas_price
        except: gas_price = self.w3.to_wei(30, "gwei")

        contract = self.w3.eth.contract(address=contract_cs, abi=ERC20_ABI)
        tx = contract.functions.transfer(to_cs, units).build_transaction({
            "chainId":chain_id, "gas":300_000, "gasPrice":gas_price,
            "nonce":nonce, "from":from_cs,
        })
        try:
            estimated = self.w3.eth.estimate_gas(tx)
            tx["gas"] = int(estimated * 1.3)
        except Exception:
            pass  # use default 300k gas

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
    if getattr(sys, "frozen", False): return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════════════
#  Scrollable frame helper
# ══════════════════════════════════════════════════════════════════════
def make_scrollable(parent) -> tk.Frame:
    canvas = tk.Canvas(parent, bg=C["bg"], borderwidth=0, highlightthickness=0)
    vsb    = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner  = tk.Frame(canvas, bg=C["bg"])
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0,0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>",
        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
    return inner

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
            messagebox.showwarning("Required", "Passphrase cannot be empty.", parent=self)
            return False
        if self.confirm and p != self.e2.get():
            messagebox.showwarning("Mismatch", "Passphrases do not match.", parent=self)
            return False
        self.value = p; return True

def ask_pass(parent, title="Enter Passphrase", confirm=False):
    return PassphraseDialog(parent, title, confirm=confirm).value

# ══════════════════════════════════════════════════════════════════════
#  Column definitions
# ══════════════════════════════════════════════════════════════════════
COLS   = ("id","user_id","gross_bh","fee_bh","net_bh","net_usd","wallet","status","created_at")
HEADS  = ("ID","User","Gross BH","Fee BH","Net BH","Net USD","Wallet Address","Status","Created")
WIDTHS = (55, 110, 100, 90, 100, 100, 260, 80, 140)

DETAIL_FIELDS = [
    ("Withdrawal ID",     "id"),
    ("User ID",           "user_id"),
    ("Status",            "status"),
    ("Wallet Address",    "wallet_address"),
    ("Gross Amount (BH)", "gross_amount_bh"),
    ("Platform Fee (BH)", "platform_fee_bh"),
    ("Net Amount (BH)",   "net_amount_bh"),
    ("Net Amount (USD)",  "net_amount_usd"),
    ("Transaction Hash",  "transaction_hash"),
    ("Admin Note",        "admin_note"),
    ("Rejection Reason",  "rejection_reason"),
    ("Created At",        "created_at"),
    ("Updated At",        "updated_at"),
    ("Processed At",      "processed_at"),
]

# ══════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE}  v{APP_VERSION}  —  {APP_CREDIT}")
        self.root.geometry("1300x800")
        self.root.minsize(1000, 640)
        self.root.configure(bg=C["bg"])

        self._load_favicon()
        self.cfg             = ConfigStore.load()
        self.api             = ApiClient(self.cfg["api_base_url"], self.cfg["auth_header"])
        self.runtime_pk      = None
        self.all_records     = []
        self.pending_records = []
        self.var_simulate    = tk.BooleanVar(value=self.cfg.get("simulate_only", True))
        self._show_zero      = False
        self._last_bal_res   = {}
        self._live_paused    = False
        self._all_countdown  = 0
        self._pend_countdown = 0
        self._bal_countdown  = 0
        self._hist_countdown = 0

        # v4.0.0: tab-aware live refresh + security state
        self._tab_keys           = ["all", "pending", "balances", "security", "history", "settings"]
        self._active_tab_key     = "all"
        self._last_activity      = time.time()
        self._approval_timestamps = []  # in-memory sliding window for rate limiting

        self._apply_style()
        self._build_ui()
        self.refresh_all(silent=True)
        self.refresh_pending(silent=True)
        self._tick_all()
        self._tick_pending()
        self._tick_balances()
        self._tick_history()
        self._tick_clock()
        self._tick_security()

    # ── Favicon ───────────────────────────────────────────────────────
    def _load_favicon(self):
        for name in ("imh.png", "ayamil.jpg"):
            p = os.path.join(_exe_dir(), name)
            if os.path.exists(p):
                try:
                    img = tk.PhotoImage(file=p)
                    self.root.iconphoto(True, img)
                    self._favicon_ref = img
                    return
                except Exception:
                    continue

    # ── Style ─────────────────────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style()
        # v4.0.0 FIX: the Windows "vista"/"xpnative" ttk themes render
        # Notebook tabs using the native OS theme engine and silently
        # ignore custom background/foreground colors. That is what made
        # the ACTIVE tab's label text disappear (it was being drawn
        # theme-default-on-theme-default by the OS instead of our white-
        # on-navy scheme), while inactive tabs happened to still be
        # legible. "clam" is fully Python-drawn and honors every color we
        # set, so we force it to guarantee tab text is always visible.
        try:
            if "clam" in s.theme_names(): s.theme_use("clam")
            elif "alt" in s.theme_names(): s.theme_use("alt")
        except Exception: pass
        s.configure(".", background=C["bg"], foreground=C["text"], font=("Segoe UI", 9))
        s.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=[4,6,4,0])
        s.configure("TNotebook.Tab", background="#DBEAFE", foreground=C["hdr_bg"],
                    padding=[16,8], font=("Segoe UI",9,"bold"))
        s.map("TNotebook.Tab",
              background=[("selected",C["hdr_bg"]), ("active","#BFDBFE")],
              foreground=[("selected","#FFFFFF"), ("active",C["hdr_bg"]), ("!selected",C["hdr_bg"])],
              expand=[("selected",[1,2,1,0])])
        s.configure("TFrame", background=C["bg"])
        s.configure("TLabel", background=C["bg"], foreground=C["text"])
        s.configure("TLabelframe", background=C["bg"])
        s.configure("TLabelframe.Label", background=C["bg"], foreground=C["hdr_bg"],
                    font=("Segoe UI",9,"bold"))
        s.configure("TButton", padding=[10,5], font=("Segoe UI",9))
        s.configure("Accent.TButton",  background=C["accent"],  foreground="#fff",
                    font=("Segoe UI",9,"bold"), padding=[12,6])
        s.configure("Success.TButton", background=C["success"], foreground="#fff",
                    font=("Segoe UI",9,"bold"), padding=[12,6])
        s.configure("Danger.TButton",  background=C["danger"],  foreground="#fff",
                    font=("Segoe UI",9,"bold"), padding=[12,6])
        s.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                    foreground=C["text"], rowheight=26, font=("Segoe UI",9))
        s.configure("Treeview.Heading", background=C["hdr_bg"], foreground="#fff",
                    font=("Segoe UI",9,"bold"), relief="flat")
        s.map("Treeview", background=[("selected",C["accent"])],
              foreground=[("selected","#fff")])

    # ── Live tickers ──────────────────────────────────────────────────
    def _tick_all(self):
        if not self._live_paused:
            interval = LIVE_INTERVAL_ALL if self._active_tab_key == "all" else BACKGROUND_INTERVAL_ALL
            if self._all_countdown <= 0:
                self.refresh_all(silent=True); self._all_countdown = interval
            else: self._all_countdown -= 1
            if hasattr(self, "all_next_lbl"):
                live = self._active_tab_key == "all"
                self.all_next_lbl.config(
                    text=(f"🟢 LIVE • next in {self._all_countdown}s" if live
                          else f"⏸ background • next in {self._all_countdown}s"))
        self.root.after(1000, self._tick_all)

    def _tick_pending(self):
        if not self._live_paused:
            interval = LIVE_INTERVAL_PENDING if self._active_tab_key == "pending" else BACKGROUND_INTERVAL_PENDING
            if self._pend_countdown <= 0:
                self.refresh_pending(silent=True); self._pend_countdown = interval
            else: self._pend_countdown -= 1
            if hasattr(self, "pend_next_lbl"):
                live = self._active_tab_key == "pending"
                self.pend_next_lbl.config(
                    text=(f"🟢 LIVE • next in {self._pend_countdown}s" if live
                          else f"⏸ background • next in {self._pend_countdown}s"))
        self.root.after(1000, self._tick_pending)

    def _tick_balances(self):
        if not self._live_paused:
            interval = LIVE_INTERVAL_BALANCES if self._active_tab_key == "balances" else BACKGROUND_INTERVAL_BALANCES
            if self._bal_countdown <= 0:
                if self.cfg.get("from_address"): self.refresh_balances(silent=True)
                self._bal_countdown = interval
            else: self._bal_countdown -= 1
            if hasattr(self, "bal_next_lbl"):
                live = self._active_tab_key == "balances"
                self.bal_next_lbl.config(
                    text=(f"🟢 LIVE • next in {self._bal_countdown}s" if live
                          else f"⏸ background • next in {self._bal_countdown}s"))
        self.root.after(1000, self._tick_balances)

    def _tick_history(self):
        if not self._live_paused:
            interval = LIVE_INTERVAL_HISTORY if self._active_tab_key == "history" else BACKGROUND_INTERVAL_HISTORY
            if self._hist_countdown <= 0:
                self.refresh_history(); self._hist_countdown = interval
            else: self._hist_countdown -= 1
            if hasattr(self, "hist_next_lbl"):
                live = self._active_tab_key == "history"
                self.hist_next_lbl.config(
                    text=(f"🟢 LIVE • next in {self._hist_countdown}s" if live
                          else f"⏸ background • next in {self._hist_countdown}s"))
        self.root.after(1000, self._tick_history)

    def _tick_clock(self):
        if hasattr(self, "status_clock"):
            self.status_clock.config(text=f"🕐 {datetime.now().strftime('%H:%M:%S')}")
        self.root.after(1000, self._tick_clock)

    def _tick_security(self):
        # Idle auto-lock: wipe the decrypted private key from memory after inactivity
        if self.runtime_pk and (time.time() - self._last_activity) > IDLE_LOCK_SECONDS:
            self.runtime_pk = None
            SecurityLog.record("idle_lock", "Wallet key cleared from memory after idle timeout.")
            self.log("🔒 Wallet key auto-locked after idle timeout. Re-enter passphrase to approve.", tag="warn")
        if hasattr(self, "_refresh_security_banner"):
            self._refresh_security_banner()
        self.root.after(1000, self._tick_security)

    # ── Tab-awareness / activity tracking ──────────────────────────────
    def _on_tab_changed(self, event=None):
        try:
            idx = self.nb.index(self.nb.select())
            self._active_tab_key = self._tab_keys[idx] if idx < len(self._tab_keys) else ""
        except Exception:
            return
        self._mark_activity()
        # Snap-refresh the instant you switch onto a tab, then keep it "live"
        if self._active_tab_key == "all":
            self._all_countdown = 0
        elif self._active_tab_key == "pending":
            self._pend_countdown = 0
        elif self._active_tab_key == "balances":
            if self.cfg.get("from_address"): self._bal_countdown = 0
        elif self._active_tab_key == "history":
            self._hist_countdown = 0
        elif self._active_tab_key == "security":
            self._reload_security_log()
            self._reload_block_tree()

    def _mark_activity(self, event=None):
        self._last_activity = time.time()

    # ── Thread helpers ────────────────────────────────────────────────
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
        locked, until = LockoutGuard.is_locked()
        if locked:
            wait = max(int(until - datetime.now().timestamp()), 1)
            raise ChainError(f"🔒 Wallet locked after repeated failed passphrase attempts. Try again in {wait}s.")
        if self.cfg.get("pk_set"):
            pw = ask_pass(self.root, "Unlock Wallet Key")
            if not pw: raise ChainError("Passphrase required.")
            try:
                pk = decrypt_secret(self.cfg["pk_salt"], self.cfg["pk_token"], pw)
            except Exception:
                d = LockoutGuard.record_failure()
                SecurityLog.record("passphrase_fail", f"attempt #{d.get('failed_attempts',0)}")
                if d.get("locked_until"):
                    SecurityLog.record("passphrase_lockout", f"{LOCKOUT_DURATION_SECONDS}s lockout engaged")
                    raise ChainError(f"🔒 Too many failed attempts. Wallet locked for {LOCKOUT_DURATION_SECONDS//60} minutes.")
                remaining = MAX_PASSPHRASE_ATTEMPTS - d.get("failed_attempts", 0)
                raise ChainError(f"Wrong passphrase or corrupted key. {max(remaining,0)} attempt(s) remaining before lockout.")
            LockoutGuard.record_success()
            self.runtime_pk = pk
            self._last_activity = time.time()
            return pk
        raise ChainError("No wallet key — go to Settings.")

    def _new_chain(self) -> ChainClient:
        rpcs = [self.cfg["rpc_url"]]
        rpcs += (SCAN_NETWORKS["polygon"] if "polygon" in self.cfg["network"]
                 else SCAN_NETWORKS["bsc"])["rpcs"]
        return ChainClient.from_rpcs(list(dict.fromkeys(rpcs)))

    def _set_api(self):
        self.api = ApiClient(self.cfg["api_base_url"], self.cfg["auth_header"])

    # ══════════════════════════════════════════════════════════════════
    #  UI skeleton
    # ══════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=C["hdr_bg"], pady=10)
        hdr.pack(fill="x")
        logo_f = tk.Frame(hdr, bg=C["hdr_bg"]); logo_f.pack(side="left", padx=16)
        tk.Label(logo_f, text="∞", font=("Segoe UI",22,"bold"),
                 bg=C["hdr_bg"], fg="#60A5FA").pack(side="left")
        tf = tk.Frame(logo_f, bg=C["hdr_bg"]); tf.pack(side="left", padx=6)
        tk.Label(tf, text=APP_TITLE, font=("Segoe UI",13,"bold"),
                 bg=C["hdr_bg"], fg="#FFFFFF").pack(anchor="w")
        tk.Label(tf, text=APP_CREDIT, font=("Segoe UI",8),
                 bg=C["hdr_bg"], fg="#93C5FD").pack(anchor="w")
        hdr_r = tk.Frame(hdr, bg=C["hdr_bg"]); hdr_r.pack(side="right", padx=16)
        self.mode_badge = tk.Label(hdr_r, text="", font=("Segoe UI",9,"bold"),
                                    padx=10, pady=4)
        self.mode_badge.pack(side="right", padx=8)
        # v4.0.0: quick-access emergency kill switch, always visible
        self.kill_btn = tk.Label(hdr_r, text="🛑 KILL", font=("Segoe UI",8,"bold"),
                                  bg=C["danger"], fg="#fff", padx=8, pady=4, cursor="hand2")
        self.kill_btn.pack(side="right", padx=4)
        self.kill_btn.bind("<Button-1>", lambda e: self._activate_kill_switch())
        tk.Label(hdr_r, text=f"v{APP_VERSION}", font=("Segoe UI",8),
                 bg=C["hdr_bg"], fg="#93C5FD").pack(side="right", padx=4)

        # Notebook
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)
        self.tab_all      = ttk.Frame(self.nb)
        self.tab_pending  = ttk.Frame(self.nb)
        self.tab_balances = ttk.Frame(self.nb)
        self.tab_security = ttk.Frame(self.nb)
        self.tab_history  = ttk.Frame(self.nb)
        self.tab_settings = ttk.Frame(self.nb)
        self.nb.add(self.tab_all,      text="  📋 All Withdrawals  ")
        self.nb.add(self.tab_pending,  text="  ⏳ Pending  ")
        self.nb.add(self.tab_balances, text="  💰 Balances  ")
        self.nb.add(self.tab_security, text="  🛡 Security  ")
        self.nb.add(self.tab_history,  text="  📜 TX History  ")
        self.nb.add(self.tab_settings, text="  ⚙ Settings  ")
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Status bar
        sbar = tk.Frame(self.root, bg=C["hdr_bg"], pady=3)
        sbar.pack(fill="x", side="bottom")
        tk.Label(sbar, text=f"  {APP_CREDIT}  •  {APP_TITLE} v{APP_VERSION}",
                 bg=C["hdr_bg"], fg="#93C5FD", font=("Segoe UI",8)).pack(side="left")
        self.status_clock = tk.Label(sbar, text="", bg=C["hdr_bg"],
                                      fg="#E2E8F0", font=("Segoe UI",8,"bold"))
        self.status_clock.pack(side="right", padx=10)

        self._build_all_tab()
        self._build_pending_tab()
        self._build_balances_tab()
        self._build_security_tab()
        self._build_history_tab()
        self._build_settings_tab()
        self._update_mode_badge()

    # ── Shared tree builder ───────────────────────────────────────────
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
        tree.tag_configure("stored_tx",background=C["row_store"])
        return wrap, tree

    def _sort_tree(self, tree, col, reverse):
        data = [(tree.set(k, col), k) for k in tree.get_children("")]
        try:    data.sort(key=lambda t: float(t[0].replace(",","").replace("$","")), reverse=reverse)
        except: data.sort(key=lambda t: t[0], reverse=reverse)
        for idx, (_,k) in enumerate(data): tree.move(k, "", idx)
        tree.heading(col, command=lambda: self._sort_tree(tree, col, not reverse))

    @staticmethod
    def _row_values(rec):
        return (rec.get("id"), rec.get("user_id"),
                fmt(rec.get("gross_amount_bh",0)), fmt(rec.get("platform_fee_bh",0)),
                fmt(rec.get("net_amount_bh",0)),  fmt_usd(rec.get("net_amount_usd",0)),
                rec.get("wallet_address"), rec.get("status"),
                (rec.get("created_at") or "")[:19])

    def _populate_tree(self, tree, records):
        for row in tree.get_children(): tree.delete(row)
        for rec in records:
            tag = rec.get("status","pending")
            tree.insert("", "end", iid=str(rec.get("id")),
                        values=self._row_values(rec), tags=(tag,))

    def _update_mode_badge(self):
        if self.var_simulate.get():
            cfg = {"text":"🟡  SIMULATION", "bg":C["sim_bg"], "fg":C["sim_fg"]}
        else:
            cfg = {"text":"🔴  LIVE MODE",  "bg":C["live_bg"],"fg":C["live_fg"]}
        if hasattr(self,"pending_mode_lbl"): self.pending_mode_lbl.config(**cfg)
        self.mode_badge.config(**cfg)

    # ── Detail popup ─────────────────────────────────────────────────
    def _record_popup(self, rec):
        win = tk.Toplevel(self.root)
        win.title(f"Withdrawal #{rec.get('id')} — Details")
        win.geometry("580x680"); win.configure(bg=C["bg"]); win.grab_set()

        # Title bar
        title_bar = tk.Frame(win, bg=C["hdr_bg"], pady=10); title_bar.pack(fill="x")
        sv = rec.get("status","").upper()
        sc = {"APPROVED":C["success"],"REJECTED":C["danger"],"PENDING":C["warning"]}.get(sv,C["text_dim"])
        tk.Label(title_bar, text=f"  Withdrawal #{rec.get('id')}",
                 font=("Segoe UI",13,"bold"), bg=C["hdr_bg"], fg="#fff").pack(side="left")
        tk.Label(title_bar, text=f"  {sv}  ", font=("Segoe UI",9,"bold"),
                 bg=sc, fg="#fff", padx=6, pady=2).pack(side="right", padx=12)

        # Pending TX warning
        stored = PendingTxStore.get(rec.get("id"))
        if stored:
            w = tk.Frame(win, bg="#FEF3C7", pady=8, padx=12); w.pack(fill="x")
            tk.Label(w, text="⚠ ON-CHAIN TX STORED (sent but API not confirmed)",
                     font=("Segoe UI",9,"bold"), bg="#FEF3C7", fg="#92400E").pack(anchor="w")
            tk.Label(w, text=f"TX: {stored['tx_hash']}",
                     font=("Consolas",8), bg="#FEF3C7", fg="#78350F").pack(anchor="w")

        # Scrollable body
        outer = tk.Frame(win, bg=C["bg"]); outer.pack(fill="both", expand=True)
        cv = tk.Canvas(outer, bg=C["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(outer, command=cv.yview)
        body = tk.Frame(cv, bg=C["bg"])
        body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0,0), window=body, anchor="nw")
        cv.configure(yscrollcommand=vsb.set)
        cv.pack(side="left", fill="both", expand=True); vsb.pack(side="right", fill="y")

        for i, (label, key) in enumerate(DETAIL_FIELDS):
            val = rec.get(key)
            val_str = "—" if val is None else str(val)
            row_bg  = C["card"] if i % 2 == 0 else "#F8FAFC"
            row = tk.Frame(body, bg=row_bg, pady=7, padx=14); row.pack(fill="x")
            tk.Label(row, text=label, font=("Segoe UI",9,"bold"),
                     bg=row_bg, fg=C["text_dim"], width=20, anchor="w").pack(side="left")
            vc = C["text"]; vf = ("Segoe UI",9)
            if key in ("wallet_address","transaction_hash"):
                vf = ("Consolas",8); vc = "#1E40AF"
            elif key == "status": vc = sc; vf = ("Segoe UI",9,"bold")
            elif key in ("net_amount_bh","net_amount_usd","gross_amount_bh"):
                vf = ("Segoe UI",10,"bold")
                try: vc = C["success"] if float(val or 0) > 0 else C["text_dim"]
                except: pass
            tk.Label(row, text=val_str, font=vf, fg=vc, bg=row_bg,
                     anchor="w", wraplength=340, justify="left").pack(side="left")
            if key in ("wallet_address","transaction_hash","id"):
                def _copy(v=val_str):
                    win.clipboard_clear(); win.clipboard_append(v)
                tk.Button(row, text="⎘", font=("Segoe UI",8), bg=C["card"],
                          fg=C["accent"], relief="flat", bd=0, cursor="hand2",
                          command=_copy, padx=4).pack(side="right")

        # TX History for this withdrawal
        hist = TxHistory.for_withdrawal(rec.get("id"))
        if hist:
            sep = tk.Frame(body, bg=C["border"], height=1); sep.pack(fill="x", pady=4)
            tk.Label(body, text=f"TX History ({len(hist)} action(s))",
                     font=("Segoe UI",9,"bold"), bg=C["bg"],
                     fg=C["hdr_bg"], padx=14).pack(anchor="w", pady=(2,0))
            for h in reversed(hist):
                hbg = C["row_appr"] if h.get("tx_status")=="success" else \
                      C["row_fail"] if h.get("tx_status") in ("failed","reverted") else "#F8FAFC"
                hrow = tk.Frame(body, bg=hbg, pady=4, padx=14); hrow.pack(fill="x")
                tk.Label(hrow,
                         text=f"[{h.get('timestamp','')[:19]}]  {h.get('action','').upper()}  "
                              f"status={h.get('tx_status','?')}  "
                              f"tx={str(h.get('tx_hash',''))[:20]}…",
                         font=("Consolas",8), bg=hbg,
                         fg=C["danger"] if h.get("error") else C["text"]).pack(anchor="w")
                if h.get("error"):
                    tk.Label(hrow, text=f"  Error: {h['error'][:120]}",
                             font=("Segoe UI",8), bg=hbg, fg=C["danger"]).pack(anchor="w")

        btn_row = tk.Frame(win, bg=C["bg"], pady=8); btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Close", command=win.destroy).pack(side="right", padx=12)
        if rec.get("wallet_address"):
            preset = NETWORK_PRESETS.get(self.cfg.get("network","polygon_bh"),{})
            exp = preset.get("explorer_tx","https://polygonscan.com/tx/").rsplit("/tx/",1)[0]
            def _open():
                safe_open_url(f"{exp}/address/{rec['wallet_address']}")
            ttk.Button(btn_row, text="🔗 Explorer", command=_open).pack(side="right", padx=4)

    # ══════════════════════════════════════════════════════════════════
    #  TAB 1 — All Withdrawals
    # ══════════════════════════════════════════════════════════════════
    def _build_all_tab(self):
        p = self.tab_all

        # Stats row
        sc = tk.Frame(p, bg=C["bg"]); sc.pack(fill="x", padx=10, pady=(8,4))
        self.stat_boxes = {}
        for i, (key, label, col) in enumerate([
            ("total_requests","Total","#1E3A8A"),("pending_count","Pending","#D97706"),
            ("approved_count","Approved","#16A34A"),("rejected_count","Rejected","#DC2626"),
            ("pending_usd","Pending USD","#7C3AED"),("total_paid_usd","Paid USD","#0891B2"),
        ]):
            box = tk.Frame(sc, bg=C["bg"], padx=12, pady=6,
                           highlightbackground=col, highlightthickness=2)
            box.grid(row=0, column=i, padx=4, pady=2, sticky="nsew")
            sc.columnconfigure(i, weight=1)
            tk.Label(box, text=label, font=("Segoe UI",8,"bold"), bg=C["bg"], fg=col).pack()
            v = tk.Label(box, text="—", font=("Segoe UI",13,"bold"), bg=C["bg"], fg=col)
            v.pack(); self.stat_boxes[key] = v

        # Toolbar
        bar = tk.Frame(p, bg=C["bg"], pady=6, padx=8); bar.pack(fill="x")
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.var_all_status = tk.StringVar(value="all")
        cb = ttk.Combobox(bar, textvariable=self.var_all_status, state="readonly",
                           values=["all","pending","approved","rejected"], width=11)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_all())
        ttk.Button(bar, text="⟳ Refresh Now", command=self.refresh_all,
                   style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(bar, text="🔍 View Details", command=self._all_details).pack(side="left", padx=4)
        self.all_next_lbl = tk.Label(bar, text="", font=("Segoe UI",8),
                                      bg=C["bg"], fg=C["text_dim"])
        self.all_next_lbl.pack(side="right", padx=8)

        wrap, self.all_tree = self._make_tree(p)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0,8))
        self.all_tree.bind("<Double-1>", lambda e: self._all_details())

    def refresh_all(self, silent=False):
        self._set_api(); self._all_countdown = LIVE_INTERVAL_ALL if self._active_tab_key == "all" else BACKGROUND_INTERVAL_ALL
        sv = getattr(self,"var_all_status",None)
        status = sv.get() if sv else "all"
        def work():
            records = self.api.list_all(status=status)
            try: st = self.api.stats()
            except: st = {}
            return records, st
        def done(res):
            records, st = res
            self.all_records = records
            self._populate_tree(self.all_tree, records)
            for key, w in self.stat_boxes.items():
                val = st.get(key, 0)
                w.config(text=fmt_usd(val) if "usd" in key else str(val))
        def err(e):
            if not silent: messagebox.showerror("Failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _all_details(self):
        sel = self.all_tree.selection()
        if not sel: messagebox.showinfo("Select", "Click a row first."); return
        rec = next((r for r in self.all_records if str(r.get("id"))==sel[0]), None)
        if rec: self._record_popup(rec)

    # ══════════════════════════════════════════════════════════════════
    #  TAB 2 — Pending
    # ══════════════════════════════════════════════════════════════════
    def _build_pending_tab(self):
        p = self.tab_pending

        # Summary card
        sc = tk.Frame(p, bg=C["card"], highlightbackground=C["border"],
                      highlightthickness=1); sc.pack(fill="x", padx=10, pady=(8,4))
        si = tk.Frame(sc, bg=C["card"], padx=12, pady=8); si.pack(fill="x")
        self.pend_count_lbl = tk.Label(si, text="0", font=("Segoe UI",20,"bold"),
                                        bg=C["card"], fg=C["warning"])
        self.pend_count_lbl.grid(row=0,column=0,padx=16)
        tk.Label(si,text="Pending",font=("Segoe UI",8),bg=C["card"],fg=C["text_dim"]).grid(row=1,column=0)
        tk.Frame(si,bg=C["border"],width=1).grid(row=0,column=1,rowspan=2,sticky="ns",padx=8,pady=4)
        self.pend_bh_lbl = tk.Label(si, text="0.0000", font=("Segoe UI",15,"bold"),
                                     bg=C["card"], fg=C["accent2"])
        self.pend_bh_lbl.grid(row=0,column=2,padx=16)
        tk.Label(si,text="Total Net BH",font=("Segoe UI",8),bg=C["card"],fg=C["text_dim"]).grid(row=1,column=2)
        tk.Frame(si,bg=C["border"],width=1).grid(row=0,column=3,rowspan=2,sticky="ns",padx=8,pady=4)
        self.pend_usd_lbl = tk.Label(si, text="$0.00", font=("Segoe UI",15,"bold"),
                                      bg=C["card"], fg=C["success"])
        self.pend_usd_lbl.grid(row=0,column=4,padx=16)
        tk.Label(si,text="Total Net USD",font=("Segoe UI",8),bg=C["card"],fg=C["text_dim"]).grid(row=1,column=4)
        self.pending_mode_lbl = tk.Label(si, text="", font=("Segoe UI",9,"bold"),
                                          padx=10, pady=4)
        self.pending_mode_lbl.grid(row=0,column=5,padx=20)
        tk.Label(si,text="Mode",font=("Segoe UI",8),bg=C["card"],fg=C["text_dim"]).grid(row=1,column=5)
        self.var_simulate.trace_add("write", lambda *_: self._update_mode_badge())

        # Toolbar
        bar = tk.Frame(p, bg=C["bg"], pady=6, padx=8); bar.pack(fill="x")
        ttk.Button(bar, text="⟳ Refresh",      command=self.refresh_pending,  style="Accent.TButton").pack(side="left",padx=3)
        ttk.Button(bar, text="✔ Approve Sel",  command=self.approve_selected, style="Success.TButton").pack(side="left",padx=3)
        ttk.Button(bar, text="✖ Reject Sel",   command=self.reject_selected,  style="Danger.TButton").pack(side="left",padx=3)
        ttk.Button(bar, text="✔✔ Approve ALL", command=self.approve_all,      style="Success.TButton").pack(side="left",padx=3)
        ttk.Button(bar, text="🔍 Details",     command=self._pending_details).pack(side="left",padx=3)
        ttk.Button(bar, text="⚠ TX Store",     command=self._show_pending_store).pack(side="left",padx=3)
        self.pend_next_lbl = tk.Label(bar, text="", font=("Segoe UI",8),
                                       bg=C["bg"], fg=C["text_dim"])
        self.pend_next_lbl.pack(side="right", padx=8)

        wrap, self.pending_tree = self._make_tree(p)
        wrap.pack(fill="both", expand=True, padx=10, pady=4)
        self.pending_tree.bind("<Double-1>", lambda e: self._pending_details())

        # Activity log
        lc = tk.Frame(p, bg=C["card"], highlightbackground=C["border"], highlightthickness=1)
        lc.pack(fill="x", padx=10, pady=(0,8))
        lh = tk.Frame(lc, bg=C["hdr_bg"], pady=4); lh.pack(fill="x")
        tk.Label(lh, text="  📜 Activity Log", font=("Segoe UI",9,"bold"),
                 bg=C["hdr_bg"], fg="#fff").pack(side="left")
        def _clear_log():
            self.log_text.config(state="normal")
            self.log_text.delete("1.0","end")
            self.log_text.config(state="disabled")
        tk.Button(lh, text="Clear", font=("Segoe UI",8), bg=C["hdr_bg"],
                  fg="#93C5FD", relief="flat", bd=0, command=_clear_log).pack(side="right",padx=8)

        lb = tk.Frame(lc, bg=C["log_bg"]); lb.pack(fill="x")
        self.log_text = tk.Text(lb, height=9, wrap="word", state="disabled",
                                 font=("Consolas",9), bg=C["log_bg"], fg=C["text"],
                                 relief="flat", bd=0)
        lvsb = ttk.Scrollbar(lb, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lvsb.set)
        self.log_text.grid(row=0,column=0,sticky="nsew",padx=4,pady=4)
        lvsb.grid(row=0,column=1,sticky="ns")
        lb.rowconfigure(0,weight=1); lb.columnconfigure(0,weight=1)
        self.log_text.tag_configure("link",    foreground=C["accent"],  underline=1)
        self.log_text.tag_configure("ok",      foreground=C["success"])
        self.log_text.tag_configure("fail",    foreground=C["danger"])
        self.log_text.tag_configure("warn",    foreground=C["warning"])
        self.log_text.tag_configure("sim",     foreground="#92400E")
        self.log_text.tag_configure("stored",  foreground=C["accent2"], font=("Consolas",9,"bold"))
        self.log_text.tag_configure("preflight",foreground="#7C2D12",   font=("Consolas",9,"bold"))

    def log(self, msg: str, url: str = "", tag: str = ""):
        def do():
            self.log_text.config(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] ")
            self.log_text.insert("end", msg, tag or "")
            if url:
                start = self.log_text.index("end-1c")
                self.log_text.insert("end", f"  ↗ {url}")
                end   = self.log_text.index("end-1c")
                self.log_text.tag_add("link", start, end)
                self.log_text.tag_bind("link","<Button-1>",
                                        lambda e, u=url: safe_open_url(u))
            self.log_text.insert("end", "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.ui(do)

    def _show_pending_store(self):
        store = PendingTxStore.all()
        win   = tk.Toplevel(self.root)
        win.title("Pending TX Store"); win.geometry("720x380"); win.grab_set()
        t = tk.Text(win, wrap="word", font=("Consolas",9), bg=C["log_bg"])
        vsb = ttk.Scrollbar(win, command=t.yview); t.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right",fill="y"); t.pack(fill="both",expand=True,padx=8,pady=8)
        if not store:
            t.insert("end","✓ No pending transactions — all API calls confirmed.\n")
        else:
            t.insert("end","⚠ Withdrawals with tx sent but API not confirmed:\n\n")
            for wid, info in store.items():
                t.insert("end",f"Withdrawal #{wid}:\n")
                for k,v in info.items(): t.insert("end",f"  {k:12s}: {v}\n")
                t.insert("end","\n")
        t.config(state="disabled")

    def refresh_pending(self, silent=False):
        self._set_api(); self._pend_countdown = LIVE_INTERVAL_PENDING if self._active_tab_key == "pending" else BACKGROUND_INTERVAL_PENDING
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
            total_bh  = sum(float(r.get("net_amount_bh",0) or 0) for r in records)
            total_usd = sum(float(r.get("net_amount_usd",0) or 0) for r in records)
            self.pend_count_lbl.config(text=str(len(records)))
            self.pend_bh_lbl.config(text=fmt(total_bh))
            self.pend_usd_lbl.config(text=fmt_usd(total_usd))
        def err(e):
            if not silent: messagebox.showerror("Failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _pending_details(self):
        sel = self.pending_tree.selection()
        if not sel: return
        rec = next((r for r in self.pending_records if str(r.get("id"))==sel[0]), None)
        if rec: self._record_popup(rec)

    def _selected_pending(self):
        sel  = self.pending_tree.selection()
        recs = [r for r in self.pending_records if str(r.get("id")) in sel]
        if not recs: messagebox.showinfo("Nothing selected","Click rows first.")
        return recs

    def reject_selected(self):
        recs = self._selected_pending()
        if not recs: return
        note = simpledialog.askstring("Reject",
            f"Reason for rejecting {len(recs)} withdrawal(s):", parent=self.root)
        if not note:
            messagebox.showwarning("Cancelled","A rejection reason is required."); return
        self._set_api()
        def work():
            for r in recs:
                try:
                    self.api.reject(r["id"], note)
                    TxHistory.record(r["id"], "reject", tx_status="n/a", note=note)
                    self.log(f"#{r['id']}: Rejected — {note[:50]}", tag="warn")
                except ApiError as e:
                    TxHistory.record(r["id"], "reject", tx_status="n/a", error=str(e))
                    self.log(f"#{r['id']}: Reject FAILED — {e}", tag="fail")
        self.run_bg(work,
                    on_done=lambda _: (self.refresh_pending(), self.refresh_all(),
                                       self.refresh_history()))

    def approve_selected(self):
        recs = self._selected_pending()
        if recs: self._approve_batch(recs)

    def approve_all(self):
        if not self.pending_records:
            messagebox.showinfo("Nothing to do","No pending withdrawals."); return
        self._approve_batch(list(self.pending_records))

    # ── Security advisory pre-checks (duplicate destination, anomalies) ─
    def _security_precheck(self, recs: list, amount_field: str) -> list:
        warnings = []
        addr_counts = {}
        for r in recs:
            a = (r.get("wallet_address") or "").lower()
            if a: addr_counts[a] = addr_counts.get(a, 0) + 1
        dupes = [a for a, c in addr_counts.items() if c > 1]
        if dupes:
            warnings.append(f"⚠ {len(dupes)} destination address(es) appear more than once in this batch.")
        hist = [h for h in TxHistory.all()
                if h.get("action") == "approve" and h.get("tx_status") in ("success", "simulated")]
        amounts = [float(h.get("amount", 0) or 0) for h in hist[-50:]]
        if len(amounts) >= ANOMALY_MIN_SAMPLES:
            mean = statistics.mean(amounts)
            stdev = statistics.pstdev(amounts) or 0.0001
            threshold = mean + ANOMALY_STDEV_MULTIPLIER * stdev
            outliers = [r for r in recs if float(r.get(amount_field, 0) or 0) > threshold]
            if outliers:
                ids = ", ".join(f"#{r.get('id')}" for r in outliers[:6])
                warnings.append(f"⚠ {len(outliers)} withdrawal(s) are unusually large vs recent history ({ids}).")
        return warnings

    # ══════════════════════════════════════════════════════════════════
    #  CORE APPROVE BATCH — with full TX validation + security firewall
    # ══════════════════════════════════════════════════════════════════
    def _approve_batch(self, recs: list):
        cfg          = self.cfg
        amount_field = "net_amount_bh" if cfg["amount_source"] == "bh" else "net_amount_usd"
        simulate     = self.var_simulate.get()
        mode_str     = "SIMULATION" if simulate else "⚠ LIVE — REAL FUNDS WILL BE SENT"

        # ── Kill switch gate (checked here for instant feedback, and
        #    again inside the worker thread as defense-in-depth) ───────
        if not simulate and cfg.get("kill_switch_enabled"):
            messagebox.showerror("🛑 Kill Switch Active",
                "All LIVE approvals are blocked by the Emergency Kill Switch.\n"
                "Disable it in the 🛡 Security tab to resume.")
            return

        if not cfg["from_address"]:
            messagebox.showwarning("Missing","Set 'From Wallet Address' in Settings."); return

        total       = sum(float(r.get(amount_field,0) or 0) for r in recs)
        stored_ids  = [str(r["id"]) for r in recs if PendingTxStore.get(r["id"])]
        stored_msg  = (f"\n\n⚠ {len(stored_ids)} withdrawal(s) have stored pending TX.\n"
                       f"Chain send will be SKIPPED; only API call retried."
                       ) if stored_ids else ""

        sec_warnings = self._security_precheck(recs, amount_field)
        warn_block   = ("\n\n" + "\n".join(sec_warnings)) if sec_warnings else ""

        if not messagebox.askyesno("Confirm Approval",
            f"Mode: {mode_str}\n\nApprove {len(recs)} withdrawal(s)?\n"
            f"Total {amount_field}: {fmt(total,4)}\n"
            f"From: {cfg['from_address']}{stored_msg}{warn_block}"):
            return

        # ── High-value typed re-confirmation ───────────────────────────
        threshold = float(cfg.get("high_value_threshold") or DEFAULT_HIGH_VALUE_THRESHOLD)
        if not simulate and threshold > 0 and total > threshold:
            typed = simpledialog.askstring("High-Value Confirmation",
                f"This batch totals {fmt(total)} ({amount_field}), above your "
                f"high-value threshold of {fmt(threshold)}.\n\nType APPROVE to continue:",
                parent=self.root)
            if (typed or "").strip().upper() != "APPROVE":
                messagebox.showwarning("Cancelled", "High-value confirmation failed or was cancelled.")
                return
            SecurityLog.record("high_value_confirmed", f"batch total={fmt(total)}")

        pk = None
        if not simulate:
            try:    pk = self._get_pk()
            except ChainError as e: messagebox.showerror("Key required", str(e)); return

        self._set_api()
        preset   = NETWORK_PRESETS.get(cfg["network"], {})
        chain_id = preset.get("chain_id", 137)
        explorer = preset.get("explorer_tx", "")

        self.log(f"Batch start: {len(recs)} | {'SIMULATE' if simulate else 'LIVE'} | {cfg['network']}",
                 tag="sim" if simulate else "fail")

        def work():
            # Defense-in-depth: re-check the kill switch inside the worker
            # in case it was engaged between confirmation and execution.
            if not simulate and cfg.get("kill_switch_enabled"):
                self.log("🛑 ABORT: Kill switch engaged. No live transactions sent.", tag="fail")
                SecurityLog.record("kill_switch_block_inflight", f"batch of {len(recs)}")
                return 0, len(recs)

            chain = None
            nonce = None
            if not simulate:
                try:
                    chain = self._new_chain()
                    nonce = chain.next_nonce(cfg["from_address"])
                except ChainError as e:
                    self.log(f"ABORT: Cannot connect to chain — {e}", tag="fail")
                    TxHistory.record(0, "batch_abort", error=str(e))
                    return 0, len(recs)

            failed_count        = 0
            success_count       = 0
            batch_running_total = 0.0
            max_tx      = float(cfg.get("max_tx_amount") or 0)
            daily_limit = float(cfg.get("daily_limit") or 0)
            rate_limit_n      = int(cfg.get("rate_limit_count") or 0)
            rate_limit_window = float(cfg.get("rate_limit_window") or DEFAULT_RATE_LIMIT_WINDOW)

            for idx, rec in enumerate(recs):
                rid      = str(rec.get("id"))
                to_addr  = (rec.get("wallet_address") or "").strip()
                try:
                    amount = float(rec.get(amount_field, 0) or 0)
                except Exception:
                    amount = 0

                # ── LAYER 1: Format & sanity validation (the input firewall) ──
                if not math.isfinite(amount) or amount <= 0:
                    msg = f"Amount is {amount} — cannot send zero, negative, or non-finite values."
                    self.log(f"#{rid}: ⛔ {msg}", tag="fail")
                    TxHistory.record(rid, "approve_preflight_fail", tx_status="skipped",
                                     amount=amount, wallet=to_addr, network=cfg["network"], error=msg)
                    failed_count += 1; continue

                if amount > SANITY_MAX_AMOUNT:
                    msg = f"Amount {amount} exceeds the hard sanity ceiling of {SANITY_MAX_AMOUNT} — likely bad data."
                    self.log(f"#{rid}: ⛔ {msg}", tag="fail")
                    TxHistory.record(rid, "approve_blocked_sanity", tx_status="skipped",
                                     amount=amount, wallet=to_addr, network=cfg["network"], error=msg)
                    SecurityLog.record("sanity_ceiling_block", f"#{rid} amount={amount}")
                    failed_count += 1; continue

                if not is_valid_address(to_addr):
                    msg = f"Invalid wallet address format: '{to_addr}'"
                    self.log(f"#{rid}: ⛔ {msg}", tag="fail")
                    TxHistory.record(rid, "approve_preflight_fail", tx_status="skipped",
                                     amount=amount, wallet=to_addr, network=cfg["network"], error=msg)
                    failed_count += 1; continue

                # ── LAYER 1B: Destination blocklist ───────────────────────
                if AddressBlocklist.is_blocked(to_addr):
                    msg = "Destination address is on the security blocklist."
                    self.log(f"#{rid}: ⛔ BLOCKLISTED ADDRESS — {msg}", tag="preflight")
                    TxHistory.record(rid, "approve_blocked_address", tx_status="skipped",
                                     amount=amount, wallet=to_addr, network=cfg["network"], error=msg)
                    SecurityLog.record("blocked_address_attempt", f"#{rid} -> {to_addr}")
                    failed_count += 1; continue

                if not simulate:
                    # ── LAYER 1C: Per-transaction cap ───────────────────
                    if max_tx > 0 and amount > max_tx:
                        msg = f"Amount {fmt(amount)} exceeds per-transaction cap of {fmt(max_tx)}."
                        self.log(f"#{rid}: ⛔ {msg}", tag="preflight")
                        TxHistory.record(rid, "approve_blocked_cap", tx_status="skipped",
                                         amount=amount, wallet=to_addr, network=cfg["network"], error=msg)
                        SecurityLog.record("tx_cap_block", f"#{rid} amount={amount} cap={max_tx}")
                        failed_count += 1; continue

                    # ── LAYER 1D: Daily cumulative cap ──────────────────
                    if daily_limit > 0:
                        running = DailyLimitTracker.today_total() + batch_running_total
                        if running + amount > daily_limit:
                            msg = (f"Would exceed today's cumulative limit "
                                   f"({fmt(running)} + {fmt(amount)} > {fmt(daily_limit)}).")
                            self.log(f"#{rid}: ⛔ {msg}", tag="preflight")
                            TxHistory.record(rid, "approve_blocked_daily_limit", tx_status="skipped",
                                             amount=amount, wallet=to_addr, network=cfg["network"], error=msg)
                            SecurityLog.record("daily_limit_block", f"#{rid} {msg}")
                            failed_count += 1; continue

                    # ── LAYER 1E: Rate limiting ──────────────────────────
                    now_ts = time.time()
                    self._approval_timestamps = [t for t in self._approval_timestamps
                                                  if now_ts - t < rate_limit_window]
                    if rate_limit_n > 0 and len(self._approval_timestamps) >= rate_limit_n:
                        remaining = recs[idx:]
                        msg = (f"Rate limit reached ({rate_limit_n} approvals / "
                               f"{int(rate_limit_window)}s). {len(remaining)} remaining "
                               f"withdrawal(s) skipped — retry shortly.")
                        self.log(f"⛔ {msg}", tag="fail")
                        for skip_rec in remaining:
                            TxHistory.record(skip_rec.get("id"), "approve_blocked_rate_limit",
                                             tx_status="skipped",
                                             amount=float(skip_rec.get(amount_field,0) or 0),
                                             wallet=skip_rec.get("wallet_address",""),
                                             network=cfg["network"], error=msg)
                        SecurityLog.record("rate_limit_hit", msg)
                        failed_count += len(remaining)
                        break

                try:
                    stored = PendingTxStore.get(rid)

                    if stored:
                        # ── STORED TX: skip send, retry API ───────
                        tx_hash = stored["tx_hash"]
                        self.log(f"#{rid}: ♻ Existing TX stored. Retrying API only. "
                                 f"tx={tx_hash[:22]}…", tag="stored")

                        # Still validate stored tx receipt if live
                        if not simulate and chain:
                            try:
                                receipt = chain.wait_for_receipt(tx_hash, timeout=60)
                                chain.validate_receipt(receipt, tx_hash)
                                self.log(f"#{rid}: ✓ Stored TX confirmed on-chain.", tag="ok")
                            except TxFailedError as tf:
                                self.log(f"#{rid}: ❌ STORED TX IS FAILED ON-CHAIN! "
                                         f"Will NOT approve. Manual review required.", tag="fail")
                                TxHistory.record(rid, "approve_failed_tx", tx_hash=tx_hash,
                                                 tx_status="reverted", amount=amount,
                                                 wallet=to_addr, network=cfg["network"],
                                                 error=str(tf))
                                PendingTxStore.remove(rid)
                                failed_count += 1; continue
                            except ChainError as ce:
                                self.log(f"#{rid}: ⚠ Could not verify stored TX receipt: {ce}", tag="warn")

                    elif simulate:
                        # ── SIMULATE ───────────────────────────────
                        tx_hash = f"SIMULATED-{rid}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                        self.log(f"#{rid}: [SIM] would send {fmt(amount,4)} → {to_addr}", tag="sim")

                    else:
                        # ── LIVE SEND ──────────────────────────────

                        # LAYER 2: Pre-flight checks (balance, address, amount)
                        self.log(f"#{rid}: 🔍 Running pre-flight checks…", tag="ok")
                        try:
                            chain.preflight_checks(
                                cfg["from_address"], to_addr, amount,
                                cfg["token_contract"], cfg["decimals"],
                                required_gas_native=0.002
                            )
                            self.log(f"#{rid}: ✓ Pre-flight passed.", tag="ok")
                        except PreflightError as pe:
                            self.log(f"#{rid}: ⛔ PRE-FLIGHT FAILED:\n  {pe}", tag="preflight")
                            TxHistory.record(rid, "approve_preflight_fail", tx_status="skipped",
                                             amount=amount, wallet=to_addr, network=cfg["network"],
                                             error=str(pe))
                            failed_count += 1; continue

                        # LAYER 3: Send on-chain
                        self.log(f"#{rid}: 📡 Sending {fmt(amount,4)} → {to_addr[:20]}…", tag="ok")
                        tx_hash = chain.send_token(pk, cfg["from_address"], to_addr,
                                                    amount, cfg["token_contract"],
                                                    cfg["decimals"], chain_id, nonce)
                        nonce += 1

                        # LAYER 4: Save to pending store BEFORE waiting (crash safety)
                        PendingTxStore.put(rid, tx_hash, to_addr, amount, cfg["network"])
                        url = explorer + tx_hash if explorer else ""
                        self.log(f"#{rid}: 📤 Broadcast: {tx_hash[:22]}…  Waiting for confirmation…",
                                 url=url, tag="ok")

                        # LAYER 5: Wait for mining
                        self.log(f"#{rid}: ⏳ Waiting up to {TX_WAIT_TIMEOUT}s for confirmation…")
                        try:
                            receipt = chain.wait_for_receipt(tx_hash, timeout=TX_WAIT_TIMEOUT)
                        except ChainError as ce:
                            self.log(f"#{rid}: ⚠ Timeout waiting for receipt. TX may still confirm. "
                                     f"Hash saved to TX store. Manual check required.", tag="warn")
                            TxHistory.record(rid, "approve_timeout", tx_hash=tx_hash,
                                             tx_status="timeout", amount=amount,
                                             wallet=to_addr, network=cfg["network"],
                                             error=str(ce))
                            failed_count += 1; continue

                        # LAYER 6: CRITICAL — Check receipt status
                        # status=0 means REVERTED. Do NOT call api.approve().
                        try:
                            chain.validate_receipt(receipt, tx_hash)
                            confirmations = (chain.current_block() -
                                             receipt.get("blockNumber", 0))
                            self.log(f"#{rid}: ✅ TX SUCCESS on-chain "
                                     f"(block={receipt.get('blockNumber')}, "
                                     f"{confirmations} confirmations).", tag="ok")
                        except TxFailedError as tf:
                            self.log(
                                f"#{rid}: ❌❌ TX FAILED ON-CHAIN (status=0)! "
                                f"This is '{tf.reason}'. "
                                f"The withdrawal will NOT be marked approved. "
                                f"Admin action required.", tag="fail")
                            TxHistory.record(rid, "approve_failed_tx", tx_hash=tx_hash,
                                             tx_status="reverted", amount=amount,
                                             wallet=to_addr, network=cfg["network"],
                                             error=str(tf))
                            # Leave in PendingTxStore so admin can see it
                            failed_count += 1

                            # Show a popup alert for failed TX
                            exp_url = (explorer + tx_hash) if explorer else ""
                            self.ui(lambda wid=rid, h=tx_hash, u=exp_url:
                                messagebox.showerror(
                                    f"TX FAILED — Withdrawal #{wid}",
                                    f"The on-chain transaction FAILED (reverted).\n\n"
                                    f"TX Hash: {h}\n\n"
                                    f"Likely cause: Insufficient token balance in wallet.\n\n"
                                    f"This withdrawal was NOT marked as approved.\n"
                                    f"Please top up the wallet and try again.\n\n"
                                    f"Explorer: {u}"
                                ))
                            continue

                        # LAYER 7: Confirm enough blocks
                        if confirmations < TX_CONFIRMATIONS_REQ:
                            self.log(f"#{rid}: ⏳ Only {confirmations}/{TX_CONFIRMATIONS_REQ} "
                                     f"confirmations. Waiting for more blocks…", tag="warn")
                            time.sleep(6)  # wait ~1 more block

                    # ── LAYER 8: Call api.approve() ────────────────
                    tx_status = "simulated" if simulate else "success"
                    self.log(f"#{rid}: 📞 Calling API approve…", tag="ok")
                    self.api.approve(rid, tx_hash,
                                     note=(f"{'SIMULATED' if simulate else cfg['network']}. "
                                           f"{amount_field}={fmt(amount,4)}. "
                                           f"status={'simulated' if simulate else 'confirmed'}."))

                    # ── SUCCESS ────────────────────────────────────
                    PendingTxStore.remove(rid)
                    TxHistory.record(rid, "approve", tx_hash=tx_hash, tx_status=tx_status,
                                     amount=amount, wallet=to_addr, network=cfg["network"],
                                     note=f"{'simulated' if simulate else 'confirmed on-chain'}")
                    if not simulate:
                        DailyLimitTracker.add(amount)
                        self._approval_timestamps.append(time.time())
                        batch_running_total += amount
                    exp_url = (explorer + tx_hash) if explorer else ""
                    self.log(f"#{rid}: ✅ APPROVED. {fmt(amount,4)} → {to_addr[:20]}…",
                             url=exp_url, tag="ok")
                    success_count += 1

                except ApiError as ae:
                    self.log(f"#{rid}: ⚠ TX sent but API approve FAILED: {ae}", tag="warn")
                    TxHistory.record(rid, "approve_api_fail", tx_hash=tx_hash if "tx_hash" in dir() else "",
                                     tx_status="success_tx_api_fail", amount=amount,
                                     wallet=to_addr, network=cfg["network"], error=str(ae))
                    # Don't remove from PendingTxStore — allow retry
                except Exception as exc:
                    err_str = traceback.format_exc()
                    self.log(f"#{rid}: ❌ UNEXPECTED ERROR: {exc}", tag="fail")
                    TxHistory.record(rid, "approve_error", tx_status="error",
                                     amount=amount, wallet=to_addr, network=cfg["network"],
                                     error=str(exc))
                    failed_count += 1

            summary = (f"Batch complete: {success_count} succeeded, "
                       f"{failed_count} failed/skipped.")
            self.log(f"{'✅' if failed_count==0 else '⚠'} {summary}", tag="ok" if failed_count==0 else "warn")
            return success_count, failed_count

        def done(result):
            if result is None: return
            s, f = result
            self.refresh_pending(); self.refresh_all(); self.refresh_history()
            if f == 0:
                messagebox.showinfo("Batch Complete",
                    f"✅ All {s} withdrawal(s) processed successfully.")
            else:
                messagebox.showwarning("Batch Complete with Errors",
                    f"⚠ {s} succeeded, {f} failed or skipped.\n"
                    f"Check Activity Log, TX History, and the 🛡 Security tab for details.")

        self.run_bg(work, on_done=done)

    # ══════════════════════════════════════════════════════════════════
    #  TAB 3 — Wallet Balances
    # ══════════════════════════════════════════════════════════════════
    _NET_STYLE = {
        "polygon": {"hdr_bg":"#7B2FBE","hdr_fg":"#fff","border":"#C084FC","explorer":"https://polygonscan.com"},
        "bsc":     {"hdr_bg":"#B45309","hdr_fg":"#fff","border":"#FCD34D","explorer":"https://bscscan.com"},
    }

    def _build_balances_tab(self):
        p = self.tab_balances
        ac = tk.Frame(p, bg=C["card"], highlightbackground=C["border"],
                      highlightthickness=1); ac.pack(fill="x",padx=10,pady=(8,4))
        ai = tk.Frame(ac, bg=C["card"], padx=12, pady=8); ai.pack(fill="x")
        tk.Label(ai, text="Hot Wallet:", font=("Segoe UI",9,"bold"),
                 bg=C["card"], fg=C["text_dim"]).pack(side="left")
        self.bal_addr_lbl = tk.Label(ai,
            text=self.cfg.get("from_address") or "(not set)",
            font=("Consolas",10), fg=C["accent"], bg=C["card"])
        self.bal_addr_lbl.pack(side="left", padx=8)

        bar = tk.Frame(p, bg=C["bg"], pady=6, padx=8); bar.pack(fill="x")
        ttk.Button(bar, text="⟳ Refresh", command=self.refresh_balances,
                   style="Accent.TButton").pack(side="left",padx=4)
        ttk.Button(bar, text="+ Custom Token", command=self._add_watch_token).pack(side="left",padx=4)
        ttk.Button(bar, text="Show/Hide Zero",  command=self._toggle_zero_bal).pack(side="left",padx=4)
        self.bal_status = ttk.Label(bar, text="Click Refresh to scan", foreground=C["text_dim"])
        self.bal_status.pack(side="left", padx=12)
        self.bal_next_lbl = tk.Label(bar, text="", font=("Segoe UI",8),
                                      bg=C["bg"], fg=C["text_dim"])
        self.bal_next_lbl.pack(side="right", padx=8)

        co = tk.Frame(p, bg=C["bg"]); co.pack(fill="both",expand=True,padx=10,pady=4)
        self.bal_canvas = tk.Canvas(co, bg=C["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(co, orient="vertical", command=self.bal_canvas.yview)
        self.bal_cards_inner = tk.Frame(self.bal_canvas, bg=C["bg"])
        self.bal_cards_inner.bind("<Configure>",
            lambda e: self.bal_canvas.configure(scrollregion=self.bal_canvas.bbox("all")))
        self.bal_canvas.create_window((0,0), window=self.bal_cards_inner, anchor="nw")
        self.bal_canvas.configure(yscrollcommand=vsb.set)
        self.bal_canvas.pack(side="left",fill="both",expand=True)
        vsb.pack(side="right",fill="y")
        self.bal_canvas.bind("<MouseWheel>",
            lambda e: self.bal_canvas.yview_scroll(int(-1*(e.delta/120)),"units"))

        wc = tk.Frame(p, bg=C["card"], highlightbackground=C["border"], highlightthickness=1)
        wc.pack(fill="x",padx=10,pady=(0,8))
        wh = tk.Frame(wc, bg=C["hdr_bg"], pady=4); wh.pack(fill="x")
        tk.Label(wh, text="  📌 Custom Watched Tokens", font=("Segoe UI",9,"bold"),
                 bg=C["hdr_bg"], fg="#fff").pack(side="left")
        ttk.Button(wh, text="Remove Selected",
                   command=self._remove_watch_token).pack(side="right",padx=8,pady=2)
        cols_w = ("symbol","contract","decimals","network")
        self.watch_tree = ttk.Treeview(wc, columns=cols_w, show="headings", height=3)
        for c, w in (("symbol",70),("contract",390),("decimals",70),("network",130)):
            self.watch_tree.heading(c, text=c.title())
            self.watch_tree.column(c, width=w, anchor="w")
        wsb = ttk.Scrollbar(wc, orient="vertical", command=self.watch_tree.yview)
        self.watch_tree.configure(yscrollcommand=wsb.set)
        self.watch_tree.pack(side="left",fill="x",expand=True,padx=4,pady=4)
        wsb.pack(side="right",fill="y",pady=4)
        self._reload_watch_tree()

    def _toggle_zero_bal(self):
        self._show_zero = not self._show_zero
        if self._last_bal_res: self._render_all_network_cards(self._last_bal_res)

    def _reload_watch_tree(self):
        for row in self.watch_tree.get_children(): self.watch_tree.delete(row)
        for t in self.cfg.get("extra_tokens",[]):
            self.watch_tree.insert("","end",
                values=(t.get("symbol","?"),t.get("address",""),
                        t.get("decimals",18),t.get("network","?")))

    def _add_watch_token(self):
        win = tk.Toplevel(self.root); win.title("Add Custom Watched Token")
        win.grab_set(); win.geometry("440x200"); win.resizable(False,False)
        ttk.Label(win,text="Network:").grid(row=0,column=0,sticky="w",padx=12,pady=8)
        var_net = tk.StringVar(value="polygon")
        ttk.Combobox(win,textvariable=var_net,state="readonly",
                     values=list(SCAN_NETWORKS.keys()),width=22).grid(row=0,column=1,padx=8,pady=8)
        ttk.Label(win,text="Contract Address:").grid(row=1,column=0,sticky="w",padx=12,pady=8)
        var_addr = tk.StringVar()
        ttk.Entry(win,textvariable=var_addr,width=44).grid(row=1,column=1,padx=8,pady=8)
        def _confirm():
            addr=var_addr.get().strip(); net=var_net.get()
            if not addr: messagebox.showwarning("Required","Enter contract address.",parent=win); return
            if not is_valid_address(addr):
                messagebox.showwarning("Invalid","That doesn't look like a valid 0x… contract address.",parent=win); return
            win.destroy()
            rpcs=SCAN_NETWORKS.get(net,{}).get("rpcs",[self.cfg.get("rpc_url","")])
            def work():
                try:    return ChainClient.from_rpcs(rpcs).token_info(addr)
                except: return "???", 18
            def done(res):
                sym,dec=res
                sym=simpledialog.askstring("Symbol",f"Symbol (detected: {sym}):",
                                            initialvalue=sym,parent=self.root) or sym
                try:
                    dec=int(simpledialog.askstring("Decimals",f"Decimals (detected: {dec}):",
                                                    initialvalue=str(dec),parent=self.root) or dec)
                except Exception: pass
                tokens=self.cfg.get("extra_tokens",[])
                tokens.append({"address":addr,"symbol":sym,"decimals":dec,"network":net})
                self.cfg["extra_tokens"]=tokens; ConfigStore.save(self.cfg)
                self._reload_watch_tree()
                messagebox.showinfo("Added",f"{sym} added to {net} watchlist.")
            self.run_bg(work,on_done=done)
        ttk.Button(win,text="Detect & Add",command=_confirm).grid(row=2,column=1,sticky="w",padx=8,pady=12)

    def _remove_watch_token(self):
        sel=self.watch_tree.selection()
        if not sel: messagebox.showinfo("Select","Select a token row."); return
        idx=self.watch_tree.index(sel[0])
        tokens=self.cfg.get("extra_tokens",[])
        if 0<=idx<len(tokens):
            removed=tokens.pop(idx); self.cfg["extra_tokens"]=tokens
            ConfigStore.save(self.cfg); self._reload_watch_tree()
            messagebox.showinfo("Removed",f"Removed {removed.get('symbol','token')}.")

    def refresh_balances(self, silent=False):
        wallet=self.cfg.get("from_address","").strip()
        self.bal_addr_lbl.config(text=wallet or "(not set)")
        if not wallet:
            if not silent: messagebox.showwarning("No wallet","Set wallet address in Settings.")
            return
        self._bal_countdown = LIVE_INTERVAL_BALANCES if self._active_tab_key == "balances" else BACKGROUND_INTERVAL_BALANCES
        extras=list(self.cfg.get("extra_tokens",[]))
        self.bal_status.config(text="⏳ Scanning Polygon + BSC…")
        def _scan(net_key, net_cfg):
            items=[]; rpcs=net_cfg.get("rpcs",[])
            try:    chain=ChainClient.from_rpcs(rpcs)
            except ChainError as e:
                items.append({"symbol":net_cfg["native"],"balance":None,"error":str(e),
                               "type":"native","network":net_key}); return net_key, items
            try:
                items.append({"symbol":net_cfg["native"],"balance":chain.native_balance(wallet),
                               "contract":"native","type":"native","network":net_key})
            except Exception as e:
                items.append({"symbol":net_cfg["native"],"balance":None,"error":str(e),
                               "type":"native","network":net_key})
            for tok in net_cfg.get("tokens",[]):
                try:
                    bal=chain.token_balance(tok["address"],wallet,tok["decimals"])
                    items.append({"symbol":tok["symbol"],"balance":bal,"contract":tok["address"],
                                   "decimals":tok["decimals"],"type":"known","network":net_key})
                except Exception as e:
                    items.append({"symbol":tok["symbol"],"balance":None,"error":str(e),
                                   "contract":tok["address"],"type":"known","network":net_key})
            for tok in extras:
                if tok.get("network")==net_key:
                    try:
                        bal=chain.token_balance(tok["address"],wallet,tok["decimals"])
                        items.append({"symbol":tok["symbol"],"balance":bal,"contract":tok["address"],
                                       "decimals":tok["decimals"],"type":"extra","network":net_key})
                    except Exception as e:
                        items.append({"symbol":tok["symbol"],"balance":None,"error":str(e),
                                       "contract":tok["address"],"type":"extra","network":net_key})
            return net_key, items
        def work():
            results={}; lock=threading.Lock()
            def run(k,c):
                key,items=_scan(k,c)
                with lock: results[key]=items
            threads=[threading.Thread(target=run,args=(k,c),daemon=True)
                     for k,c in SCAN_NETWORKS.items()]
            for t in threads: t.start()
            for t in threads: t.join(timeout=35)
            return results
        def done(results):
            self._last_bal_res=results
            nonzero=sum(1 for items in results.values()
                        for it in items if it.get("balance") and float(it.get("balance",0))>0)
            self.bal_status.config(
                text=f"✓ Scanned • {nonzero} token(s) with balance • {datetime.now().strftime('%H:%M:%S')}")
            self._render_all_network_cards(results)
        def err(e):
            self.bal_status.config(text=f"Error: {e}")
            if not silent: messagebox.showerror("Balance failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _render_all_network_cards(self, results: dict):
        for w in self.bal_cards_inner.winfo_children(): w.destroy()
        CARD_COLS=4; row_offset=0
        for net_key, items in results.items():
            net_info=SCAN_NETWORKS.get(net_key,{})
            style=self._NET_STYLE.get(net_key,{"hdr_bg":"#374151","hdr_fg":"#fff","border":"#9CA3AF","explorer":""})
            visible=[it for it in items if self._show_zero or it.get("balance") is None
                     or float(it.get("balance",0))>0]
            nonzero=sum(1 for it in items if it.get("balance") and float(it.get("balance",0))>0)
            hdr=tk.Frame(self.bal_cards_inner, bg=style["hdr_bg"], pady=8)
            hdr.grid(row=row_offset, column=0, columnspan=CARD_COLS, sticky="ew", padx=4, pady=(12,2))
            for c in range(CARD_COLS): self.bal_cards_inner.columnconfigure(c, weight=1)
            tk.Label(hdr, text=f"  {net_info.get('label',net_key)}  —  {nonzero} with balance",
                     font=("Segoe UI",10,"bold"), bg=style["hdr_bg"], fg=style["hdr_fg"]).pack(side="left")
            tk.Label(hdr, text=f"Chain {net_info.get('chain_id','?')}  ",
                     font=("Segoe UI",9), bg=style["hdr_bg"], fg=style["hdr_fg"]).pack(side="right")
            row_offset+=1
            if not visible:
                tk.Label(self.bal_cards_inner, text="  No non-zero balances.",
                         fg=C["text_dim"], bg=C["bg"], font=("Segoe UI",9)
                         ).grid(row=row_offset, column=0, columnspan=CARD_COLS, sticky="w", padx=14, pady=4)
                row_offset+=1; continue
            for i, item in enumerate(visible):
                cr, cc = divmod(i, CARD_COLS); r = row_offset+cr
                has_bal=item.get("balance") is not None
                is_zero=has_bal and float(item.get("balance",0))==0
                tt=item.get("type","known")
                border={"native":style["hdr_bg"],"extra":"#7C3AED"}.get(tt,style["border"])
                card_bg="#F8FAFC" if is_zero else C["card"]
                card=tk.Frame(self.bal_cards_inner, bg=card_bg,
                              highlightbackground=border, highlightthickness=2, padx=12, pady=10)
                card.grid(row=r, column=cc, padx=5, pady=5, sticky="nsew")
                self.bal_cards_inner.rowconfigure(r, weight=0)
                sym_color={"native":style["hdr_bg"],"extra":"#7C3AED"}.get(
                    tt, C["text_dim"] if is_zero else C["text"])
                tk.Label(card, text=item.get("symbol","?"),
                         font=("Segoe UI",14,"bold"), fg=sym_color, bg=card_bg).pack(anchor="w")
                if has_bal:
                    bal=float(item["balance"])
                    tk.Label(card, text=f"{bal:.8f}" if tt=="native" else f"{bal:,.6f}",
                             font=("Consolas",11,"bold"),
                             fg=C["text_dim"] if is_zero else "#0F172A", bg=card_bg).pack(anchor="w",pady=(3,1))
                else:
                    tk.Label(card, text=f"⚠ {str(item.get('error',''))[:80]}",
                             font=("Segoe UI",8), fg=C["danger"], bg=card_bg,
                             wraplength=180, justify="left").pack(anchor="w")
                contract=item.get("contract","")
                if contract and contract!="native":
                    exp=style.get("explorer","")
                    lbl=tk.Label(card, text=contract[:8]+"…"+contract[-5:],
                                 font=("Consolas",7), fg="#94A3B8", bg=card_bg, cursor="hand2")
                    lbl.pack(anchor="w")
                    if exp: lbl.bind("<Button-1>",lambda e,u=f"{exp}/token/{contract}": safe_open_url(u))
                badge_text={"native":"Gas Coin","known":"Token","extra":"Custom"}.get(tt,"")
                badge_color={"native":style["hdr_bg"],"extra":"#7C3AED"}.get(tt,"#64748B")
                if badge_text:
                    tk.Label(card, text=f" {badge_text} ", font=("Segoe UI",7,"bold"),
                             fg="#fff", bg=badge_color, padx=3).pack(anchor="w", pady=(4,0))
            row_offset+=(len(visible)+CARD_COLS-1)//CARD_COLS+1

    # ══════════════════════════════════════════════════════════════════
    #  TAB 4 — 🛡 Security  (v4.0.0)
    # ══════════════════════════════════════════════════════════════════
    def _build_security_tab(self):
        inner = make_scrollable(self.tab_security)
        inner.columnconfigure(0, weight=1)
        pad = {"padx":14,"pady":6}

        self.kill_banner = tk.Label(inner, text="", font=("Segoe UI",11,"bold"), pady=10)
        self.kill_banner.grid(row=0, column=0, sticky="ew", **pad)

        def section(title, row):
            f = ttk.LabelFrame(inner, text=title, padding=12)
            f.grid(row=row, column=0, sticky="ew", **pad)
            f.columnconfigure(1, weight=1)
            return f

        # ── Emergency Kill Switch ───────────────────────────────────────
        ks_box = section("🛑 Emergency Kill Switch", 1)
        tk.Label(ks_box,
                 text="Instantly blocks ALL live on-chain approvals app-wide, regardless of "
                      "any other setting or limit. Simulation mode is unaffected.",
                 bg=C["bg"], fg=C["text_dim"], wraplength=680, justify="left"
                 ).grid(row=0,column=0,columnspan=2,sticky="w")
        ksf = ttk.Frame(ks_box); ksf.grid(row=1,column=0,pady=8,sticky="w")
        ttk.Button(ksf, text="🛑 ACTIVATE KILL SWITCH", style="Danger.TButton",
                   command=self._activate_kill_switch).pack(side="left", padx=4)
        ttk.Button(ksf, text="✅ Deactivate Kill Switch", style="Success.TButton",
                   command=self._deactivate_kill_switch).pack(side="left", padx=4)

        # ── Transaction limits ──────────────────────────────────────────
        lim_box = section("📊 Transaction Limits (apply to LIVE mode only)", 2)
        ttk.Label(lim_box,text="Max per-transaction").grid(row=0,column=0,sticky="w",pady=3)
        self.var_max_tx = tk.StringVar(value=str(self.cfg.get("max_tx_amount", DEFAULT_MAX_TX_AMOUNT)))
        ttk.Entry(lim_box,textvariable=self.var_max_tx,width=16).grid(row=0,column=1,sticky="w",padx=(8,0))
        ttk.Label(lim_box,text="Daily cumulative limit").grid(row=1,column=0,sticky="w",pady=3)
        self.var_daily_limit = tk.StringVar(value=str(self.cfg.get("daily_limit", DEFAULT_DAILY_LIMIT)))
        ttk.Entry(lim_box,textvariable=self.var_daily_limit,width=16).grid(row=1,column=1,sticky="w",padx=(8,0))
        ttk.Label(lim_box,text="High-value confirm threshold").grid(row=2,column=0,sticky="w",pady=3)
        self.var_high_value = tk.StringVar(value=str(self.cfg.get("high_value_threshold", DEFAULT_HIGH_VALUE_THRESHOLD)))
        ttk.Entry(lim_box,textvariable=self.var_high_value,width=16).grid(row=2,column=1,sticky="w",padx=(8,0))
        ttk.Label(lim_box,text="Rate limit (approvals / window sec)").grid(row=3,column=0,sticky="w",pady=3)
        rl = ttk.Frame(lim_box); rl.grid(row=3,column=1,sticky="w",padx=(8,0))
        self.var_rate_count  = tk.StringVar(value=str(self.cfg.get("rate_limit_count", DEFAULT_RATE_LIMIT_COUNT)))
        self.var_rate_window = tk.StringVar(value=str(self.cfg.get("rate_limit_window", DEFAULT_RATE_LIMIT_WINDOW)))
        ttk.Entry(rl,textvariable=self.var_rate_count,width=6).pack(side="left")
        ttk.Label(rl,text=" / ").pack(side="left")
        ttk.Entry(rl,textvariable=self.var_rate_window,width=6).pack(side="left")
        ttk.Label(rl,text="s").pack(side="left")
        self.daily_usage_lbl = ttk.Label(lim_box, text="", foreground=C["accent2"])
        self.daily_usage_lbl.grid(row=4,column=0,columnspan=2,sticky="w",pady=(6,0))
        ttk.Button(lim_box, text="💾 Save Limits", style="Success.TButton",
                   command=self._save_security_limits).grid(row=5,column=1,sticky="w",pady=6)

        # ── Address blocklist ───────────────────────────────────────────
        bl_box = section("🚫 Destination Address Blocklist", 3)
        addf = ttk.Frame(bl_box); addf.grid(row=0,column=0,columnspan=2,sticky="ew")
        self.var_block_addr   = tk.StringVar()
        self.var_block_reason = tk.StringVar()
        ttk.Entry(addf,textvariable=self.var_block_addr,width=46).pack(side="left",padx=2)
        ttk.Entry(addf,textvariable=self.var_block_reason,width=20).pack(side="left",padx=2)
        ttk.Button(addf,text="+ Block",command=self._add_blocked_address).pack(side="left",padx=4)
        self.block_tree = ttk.Treeview(bl_box, columns=("address","reason","added"), show="headings", height=4)
        for c,w in (("address",330),("reason",180),("added",140)):
            self.block_tree.heading(c,text=c.title()); self.block_tree.column(c,width=w)
        self.block_tree.grid(row=1,column=0,columnspan=2,sticky="ew",pady=6)
        ttk.Button(bl_box,text="Remove Selected",command=self._remove_blocked_address).grid(row=2,column=0,sticky="w")
        self._reload_block_tree()

        # ── Session / lockout status ────────────────────────────────────
        st_box = section("🔐 Session & Lockout Status", 4)
        tk.Label(st_box,
                 text=f"Wallet key auto-locks from memory after {IDLE_LOCK_SECONDS//60} minutes idle. "
                      f"{MAX_PASSPHRASE_ATTEMPTS} failed passphrase attempts trigger a "
                      f"{LOCKOUT_DURATION_SECONDS//60}-minute lockout.",
                 bg=C["bg"], fg=C["text_dim"], wraplength=680, justify="left"
                 ).grid(row=0,column=0,columnspan=2,sticky="w")
        self.lockout_status_lbl = ttk.Label(st_box, text="")
        self.lockout_status_lbl.grid(row=1,column=0,sticky="w",pady=(6,0))
        self.idle_status_lbl = ttk.Label(st_box, text="", foreground=C["text_dim"])
        self.idle_status_lbl.grid(row=2,column=0,sticky="w")
        ttk.Button(st_box, text="🔒 Lock Wallet Key Now",
                   command=self._manual_lock).grid(row=3,column=0,sticky="w",pady=6)

        # ── Tamper-evident audit log ────────────────────────────────────
        aud_box = section("🧾 Tamper-Evident Audit Log", 5)
        tk.Label(aud_box, text="Every approval/rejection/block in tx_history.json is hash-chained — "
                               "editing or deleting a past record breaks the chain and is detectable.",
                 bg=C["bg"], fg=C["text_dim"], wraplength=680, justify="left").grid(row=0,column=0,sticky="w")
        ttk.Button(aud_box, text="🔍 Verify Audit Log Integrity",
                   style="Accent.TButton", command=self._verify_audit_log).grid(row=1,column=0,sticky="w",pady=6)

        # ── Security event log ──────────────────────────────────────────
        sl_box = section("📋 Security Event Log", 6)
        self.sec_log_tree = ttk.Treeview(sl_box, columns=("event","detail","timestamp"), show="headings", height=6)
        for c,w in (("event",170),("detail",380),("timestamp",150)):
            self.sec_log_tree.heading(c,text=c.title()); self.sec_log_tree.column(c,width=w)
        self.sec_log_tree.grid(row=0,column=0,columnspan=2,sticky="ew")
        ttk.Button(sl_box, text="⟳ Refresh Log", command=self._reload_security_log).grid(row=1,column=0,sticky="w",pady=6)
        self._reload_security_log()

        self._refresh_security_banner()

    # ── Security tab handlers ───────────────────────────────────────────
    def _activate_kill_switch(self):
        if not messagebox.askyesno("Confirm Kill Switch",
                "This will block ALL live on-chain approvals immediately.\nContinue?", icon="warning"):
            return
        reason = simpledialog.askstring("Reason","Reason for activating kill switch (optional):", parent=self.root) or ""
        self.cfg["kill_switch_enabled"] = True
        ConfigStore.save(self.cfg)
        SecurityLog.record("kill_switch_on", reason)
        self.log("🛑 KILL SWITCH ACTIVATED — all live approvals blocked.", tag="fail")
        self._refresh_security_banner()
        messagebox.showinfo("Kill Switch Active","🛑 All live approvals are now blocked.")

    def _deactivate_kill_switch(self):
        if not messagebox.askyesno("Confirm","Resume live approvals?"): return
        self.cfg["kill_switch_enabled"] = False
        ConfigStore.save(self.cfg)
        SecurityLog.record("kill_switch_off", "")
        self.log("✅ Kill switch deactivated — live approvals resumed.", tag="ok")
        self._refresh_security_banner()
        messagebox.showinfo("Resumed","Live approvals re-enabled.")

    def _save_security_limits(self):
        try:
            self.cfg["max_tx_amount"]        = float(self.var_max_tx.get() or 0)
            self.cfg["daily_limit"]          = float(self.var_daily_limit.get() or 0)
            self.cfg["high_value_threshold"] = float(self.var_high_value.get() or 0)
            self.cfg["rate_limit_count"]     = int(float(self.var_rate_count.get() or 0))
            self.cfg["rate_limit_window"]    = float(self.var_rate_window.get() or 0)
        except ValueError:
            messagebox.showerror("Invalid","Limits must be numeric."); return
        ConfigStore.save(self.cfg)
        SecurityLog.record("limits_updated",
            f"max_tx={self.cfg['max_tx_amount']} daily={self.cfg['daily_limit']} "
            f"high_value={self.cfg['high_value_threshold']} "
            f"rate={self.cfg['rate_limit_count']}/{self.cfg['rate_limit_window']}s")
        messagebox.showinfo("Saved","Security limits saved.")

    def _add_blocked_address(self):
        addr = self.var_block_addr.get().strip()
        if not is_valid_address(addr):
            messagebox.showwarning("Invalid","Enter a valid 0x… address (40 hex characters)."); return
        AddressBlocklist.add(addr, self.var_block_reason.get().strip())
        SecurityLog.record("address_blocked", addr)
        self.var_block_addr.set(""); self.var_block_reason.set("")
        self._reload_block_tree()

    def _remove_blocked_address(self):
        sel = self.block_tree.selection()
        if not sel: return
        addr = self.block_tree.item(sel[0])["values"][0]
        AddressBlocklist.remove(addr)
        SecurityLog.record("address_unblocked", addr)
        self._reload_block_tree()

    def _reload_block_tree(self):
        if not hasattr(self, "block_tree"): return
        for r in self.block_tree.get_children(): self.block_tree.delete(r)
        for a in AddressBlocklist.all():
            self.block_tree.insert("","end",
                values=(a.get("address"), a.get("reason",""), (a.get("added_at") or "")[:19]))

    def _manual_lock(self):
        self.runtime_pk = None
        SecurityLog.record("manual_lock","Admin manually locked wallet key.")
        messagebox.showinfo("Locked","Wallet key cleared from memory.")
        self._refresh_security_banner()

    def _verify_audit_log(self):
        ok, broken_at, legacy = TxHistory.verify_integrity()
        if ok:
            messagebox.showinfo("Integrity OK",
                f"✅ Audit log verified.\n{legacy} legacy (pre-v4.0.0) record(s) skipped, "
                f"the remaining records form an unbroken hash chain.")
        else:
            messagebox.showerror("TAMPERING DETECTED",
                f"❌ Audit log integrity check FAILED at record #{broken_at}.\n"
                f"This indicates tx_history.json may have been edited or corrupted "
                f"outside the app. Investigate immediately.")
        SecurityLog.record("integrity_check", f"ok={ok} broken_at={broken_at} legacy={legacy}")

    def _reload_security_log(self):
        if not hasattr(self, "sec_log_tree"): return
        for r in self.sec_log_tree.get_children(): self.sec_log_tree.delete(r)
        for e in reversed(SecurityLog.all()):
            self.sec_log_tree.insert("","end",
                values=(e.get("event"), (e.get("detail") or "")[:90], (e.get("timestamp") or "")[:19]))

    def _refresh_security_banner(self):
        if not hasattr(self, "kill_banner"): return
        if self.cfg.get("kill_switch_enabled"):
            self.kill_banner.config(text="🛑 KILL SWITCH ACTIVE — all live approvals are blocked",
                                     bg=C["live_bg"], fg=C["live_fg"])
        else:
            self.kill_banner.config(text="✅ Normal operation — live approvals allowed (subject to limits below)",
                                     bg=C["row_appr"], fg=C["success"])
        locked, until = LockoutGuard.is_locked()
        if locked:
            wait = max(int(until - datetime.now().timestamp()), 0)
            self.lockout_status_lbl.config(text=f"🔒 Passphrase locked out — retry in {wait}s", foreground=C["danger"])
        else:
            self.lockout_status_lbl.config(text="🔓 No active passphrase lockout.", foreground=C["success"])
        if self.runtime_pk:
            idle = int(time.time() - self._last_activity)
            self.idle_status_lbl.config(
                text=f"🔑 Wallet key unlocked in memory — auto-locks after {IDLE_LOCK_SECONDS//60}min idle (idle {idle}s)")
        else:
            self.idle_status_lbl.config(text="🔒 Wallet key is not currently loaded in memory.")
        if hasattr(self, "daily_usage_lbl"):
            used = DailyLimitTracker.today_total()
            cap  = float(self.cfg.get("daily_limit") or 0)
            pct  = f" ({used/cap*100:.0f}%)" if cap > 0 else ""
            self.daily_usage_lbl.config(text=f"Today's approved total: {fmt(used)} / {fmt(cap) if cap>0 else '∞'}{pct}")

    # ══════════════════════════════════════════════════════════════════
    #  TAB 5 — TX History
    # ══════════════════════════════════════════════════════════════════
    def _build_history_tab(self):
        p = self.tab_history

        bar = tk.Frame(p, bg=C["bg"], pady=6, padx=8); bar.pack(fill="x")
        ttk.Button(bar, text="⟳ Refresh", command=self.refresh_history,
                   style="Accent.TButton").pack(side="left",padx=4)
        ttk.Button(bar, text="📂 Open File",
                   command=lambda: webbrowser.open(TX_HISTORY_PATH)
                   ).pack(side="left",padx=4)
        self.hist_count_lbl = tk.Label(bar, text="0 records", font=("Segoe UI",9),
                                        bg=C["bg"], fg=C["text_dim"])
        self.hist_count_lbl.pack(side="left",padx=12)

        # Filter
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.var_hist_filter = tk.StringVar(value="all")
        hf = ttk.Combobox(bar, textvariable=self.var_hist_filter, state="readonly", width=22,
                           values=["all","approve","reject","approve_failed_tx",
                                   "approve_preflight_fail","approve_timeout","approve_api_fail",
                                   "approve_blocked_cap","approve_blocked_daily_limit",
                                   "approve_blocked_address","approve_blocked_rate_limit",
                                   "approve_blocked_sanity"])
        hf.pack(side="left", padx=4)
        hf.bind("<<ComboboxSelected>>", lambda e: self.refresh_history())
        self.hist_next_lbl = tk.Label(bar, text="", font=("Segoe UI",8),
                                       bg=C["bg"], fg=C["text_dim"])
        self.hist_next_lbl.pack(side="right", padx=8)

        # Treeview
        hist_cols = ("id","withdrawal_id","action","tx_status","amount","wallet","network","timestamp","error")
        hist_heads = ("Rec","WD#","Action","TX Status","Amount","Wallet","Network","Timestamp","Error")
        hist_widths = (40,60,160,90,90,200,100,155,200)

        wrap = tk.Frame(p, bg=C["bg"]); wrap.pack(fill="both", expand=True, padx=10, pady=(0,8))
        self.hist_tree = ttk.Treeview(wrap, columns=hist_cols, show="headings")
        for col, head, w in zip(hist_cols, hist_heads, hist_widths):
            self.hist_tree.heading(col, text=head)
            self.hist_tree.column(col, width=w, minwidth=40, anchor="w")
        vhsb = ttk.Scrollbar(wrap, orient="vertical",   command=self.hist_tree.yview)
        hhsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.hist_tree.xview)
        self.hist_tree.configure(yscrollcommand=vhsb.set, xscrollcommand=hhsb.set)
        self.hist_tree.grid(row=0,column=0,sticky="nsew")
        vhsb.grid(row=0,column=1,sticky="ns")
        hhsb.grid(row=1,column=0,sticky="ew")
        wrap.rowconfigure(0,weight=1); wrap.columnconfigure(0,weight=1)

        self.hist_tree.tag_configure("success",  background=C["row_appr"])
        self.hist_tree.tag_configure("reverted", background=C["row_fail"])
        self.hist_tree.tag_configure("failed",   background=C["row_fail"])
        self.hist_tree.tag_configure("timeout",  background="#FEF3C7")
        self.hist_tree.tag_configure("simulated",background=C["row_pend"])
        self.hist_tree.tag_configure("skipped",  background="#F3E8FF")

        self.refresh_history()

    def refresh_history(self):
        if not hasattr(self, "hist_tree"): return
        data = TxHistory.all()
        flt  = getattr(self, "var_hist_filter", None)
        fval = flt.get() if flt else "all"
        if fval != "all":
            data = [r for r in data if r.get("action") == fval]
        # Show newest first
        data = list(reversed(data))

        for row in self.hist_tree.get_children(): self.hist_tree.delete(row)
        for r in data:
            wallet = r.get("wallet","")
            short_wallet = (wallet[:12]+"…"+wallet[-6:]) if len(wallet)>20 else wallet
            tag = r.get("tx_status","")
            self.hist_tree.insert("","end", values=(
                r.get("id",""),
                r.get("withdrawal_id",""),
                r.get("action",""),
                r.get("tx_status",""),
                fmt(r.get("amount",0)),
                short_wallet,
                r.get("network",""),
                (r.get("timestamp","") or "")[:19],
                (r.get("error","") or "")[:80],
            ), tags=(tag,))

        if hasattr(self,"hist_count_lbl"):
            self.hist_count_lbl.config(text=f"{len(data)} record(s)")

    # ══════════════════════════════════════════════════════════════════
    #  TAB 6 — Settings
    # ══════════════════════════════════════════════════════════════════
    def _build_settings_tab(self):
        inner = make_scrollable(self.tab_settings)
        inner.columnconfigure(0, weight=1)
        pad = {"padx":14,"pady":6}

        def section(title, row):
            f = ttk.LabelFrame(inner, text=title, padding=12)
            f.grid(row=row, column=0, sticky="ew", **pad)
            f.columnconfigure(1, weight=1)
            return f

        # ── API ──────────────────────────────────────────────────────
        api_box = section("🌐  Backend API", 0)
        ttk.Label(api_box,text="API Base URL").grid(row=0,column=0,sticky="w",pady=3)
        self.var_api_base = tk.StringVar(value=self.cfg["api_base_url"])
        ttk.Entry(api_box,textvariable=self.var_api_base).grid(row=0,column=1,columnspan=2,sticky="ew",padx=(8,0),pady=3)
        ttk.Label(api_box,text="Authorization Header").grid(row=1,column=0,sticky="w",pady=3)
        self.var_auth_hdr = tk.StringVar(value=self.cfg["auth_header"])
        ttk.Entry(api_box,textvariable=self.var_auth_hdr,show="*").grid(row=1,column=1,columnspan=2,sticky="ew",padx=(8,0),pady=3)
        ttk.Label(api_box,text="e.g.  Bearer 1|abc…",foreground=C["text_dim"]).grid(row=2,column=1,sticky="w",padx=(8,0))
        ttk.Button(api_box,text="Test API Connection",command=self._test_api,
                   style="Accent.TButton").grid(row=3,column=1,sticky="w",pady=6,padx=(8,0))

        # ── Blockchain ────────────────────────────────────────────────
        chain_box = section("⛓  Blockchain / Payout Token", 1)
        ttk.Label(chain_box,text="Network").grid(row=0,column=0,sticky="w",pady=3)
        self.var_network = tk.StringVar(value=self.cfg["network"])
        net_cb = ttk.Combobox(chain_box,textvariable=self.var_network,state="readonly",
                               values=list(NETWORK_PRESETS.keys()),width=24)
        net_cb.grid(row=0,column=1,sticky="w",padx=(8,0),pady=3)
        net_cb.bind("<<ComboboxSelected>>",self._on_net_change)
        self.net_lbl=ttk.Label(chain_box,
            text=NETWORK_PRESETS.get(self.cfg["network"],{}).get("label",""),
            foreground=C["accent"])
        self.net_lbl.grid(row=0,column=2,sticky="w",padx=8)

        for (lbl,attr,row) in [("RPC URL","var_rpc",1),("Token Contract","var_contract",2)]:
            ttk.Label(chain_box,text=lbl).grid(row=row,column=0,sticky="w",pady=3)
            setattr(self, attr, tk.StringVar(value=self.cfg[
                "rpc_url" if "rpc" in attr else "token_contract"]))
            ttk.Entry(chain_box,textvariable=getattr(self,attr)).grid(
                row=row,column=1,columnspan=2,sticky="ew",padx=(8,0),pady=3)
        ttk.Label(chain_box,text="RPC must be HTTPS (insecure RPCs are rejected).",
                  foreground=C["text_dim"]).grid(row=1,column=1,sticky="w",padx=(8,180))

        ttk.Label(chain_box,text="Token Decimals").grid(row=3,column=0,sticky="w",pady=3)
        self.var_decimals = tk.IntVar(value=self.cfg["decimals"])
        ttk.Spinbox(chain_box,from_=0,to=18,textvariable=self.var_decimals,width=6).grid(
            row=3,column=1,sticky="w",padx=(8,0),pady=3)

        ttk.Label(chain_box,text="Amount field").grid(row=4,column=0,sticky="w",pady=3)
        self.var_amount_src = tk.StringVar(value=self.cfg["amount_source"])
        af=ttk.Frame(chain_box); af.grid(row=4,column=1,columnspan=2,sticky="w",padx=(8,0))
        ttk.Radiobutton(af,text="net_amount_bh  (BH token)",
                         variable=self.var_amount_src,value="bh").pack(anchor="w")
        ttk.Radiobutton(af,text="net_amount_usd  (USDT)",
                         variable=self.var_amount_src,value="usd").pack(anchor="w")
        ttk.Button(chain_box,text="Test RPC Connection",command=self._test_rpc,
                   style="Accent.TButton").grid(row=5,column=1,sticky="w",pady=6,padx=(8,0))

        # ── Wallet ────────────────────────────────────────────────────
        wallet_box = section("💳  Sending Wallet", 2)
        tk.Label(wallet_box,
                 text="⚠  This wallet pays customers. Only fund it with what you need to send.",
                 fg=C["warning"],wraplength=680,justify="left",bg=C["bg"]
                 ).grid(row=0,column=0,columnspan=3,sticky="w",pady=(0,8))
        ttk.Label(wallet_box,text="From Address").grid(row=1,column=0,sticky="w",pady=3)
        self.var_from = tk.StringVar(value=self.cfg["from_address"])
        ttk.Entry(wallet_box,textvariable=self.var_from).grid(row=1,column=1,columnspan=2,sticky="ew",padx=(8,0),pady=3)
        ttk.Label(wallet_box,text="Private Key").grid(row=2,column=0,sticky="w",pady=3)
        pk_f=ttk.Frame(wallet_box); pk_f.grid(row=2,column=1,columnspan=2,sticky="ew",padx=(8,0),pady=3)
        self.var_pk=tk.StringVar()
        self.pk_entry=ttk.Entry(pk_f,textvariable=self.var_pk,show="*")
        self.pk_entry.pack(side="left",fill="x",expand=True)
        self.var_show_pk=tk.BooleanVar(value=False)
        ttk.Checkbutton(pk_f,text="show",variable=self.var_show_pk,
                         command=lambda: self.pk_entry.config(
                             show="" if self.var_show_pk.get() else "*")).pack(side="left",padx=4)
        self.var_persist_pk=tk.BooleanVar(value=self.cfg.get("pk_set",False))
        ttk.Checkbutton(wallet_box,text="Encrypt and save key to disk (passphrase required)",
                         variable=self.var_persist_pk).grid(row=3,column=1,columnspan=2,sticky="w",padx=(8,0))
        status_str="saved (encrypted)" if self.cfg.get("pk_set") else "not saved to disk"
        self.pk_status=ttk.Label(wallet_box,text=f"Key status: {status_str}",foreground=C["text_dim"])
        self.pk_status.grid(row=4,column=1,sticky="w",padx=(8,0))
        btn_f=ttk.Frame(wallet_box); btn_f.grid(row=5,column=1,columnspan=2,sticky="w",padx=(8,0),pady=6)
        ttk.Button(btn_f,text="Save Wallet Settings",command=self._save_wallet,
                   style="Success.TButton").pack(side="left",padx=3)
        ttk.Button(btn_f,text="Clear Saved Key",command=self._clear_pk).pack(side="left",padx=3)
        ttk.Button(btn_f,text="Check Balances",command=self._check_balances,
                   style="Accent.TButton").pack(side="left",padx=3)

        # ── TX Validation Pipeline summary ──────────────────────────────
        val_box = section("🔒  TX Validation Pipeline (v4.0.0)", 3)
        tk.Label(val_box,
                 text=(f"✅  Format & sanity validation, hard sanity ceiling, address regex check\n"
                       f"✅  Destination blocklist, per-tx cap, daily cap, rate limiting, kill switch\n"
                       f"✅  Pre-flight balance check (token + gas), HTTPS-only RPC enforcement\n"
                       f"✅  On-chain send with nonce mgmt, crash-safe pending TX store\n"
                       f"✅  Wait for mining (timeout: {TX_WAIT_TIMEOUT}s), receipt status check — "
                       f"FAILED TX = NO approve call\n"
                       f"✅  Block confirmation check (min: {TX_CONFIRMATIONS_REQ} blocks)\n"
                       f"✅  API approve call with hash-chained, tamper-evident audit log\n"
                       f"✅  Idle wallet-key auto-lock, failed-passphrase lockout\n"
                       f"→  Configure caps, blocklist, kill switch & view security events in the "
                       f"🛡 Security tab."),
                 bg=C["bg"], fg=C["text"], justify="left",
                 font=("Segoe UI",9)).grid(row=0,column=0,columnspan=3,sticky="w",pady=4)

        # ── Simulation ────────────────────────────────────────────────
        sim_box = section("⚠  LIVE / SIMULATION MODE", 4)
        sim_box.columnconfigure(0,weight=1)
        self.sim_banner = tk.Label(sim_box, text="", font=("Segoe UI",10,"bold"),
                                    anchor="center", pady=10)
        self.sim_banner.grid(row=0,column=0,columnspan=3,sticky="ew")
        def _upd(*_):
            if self.var_simulate.get():
                self.sim_banner.config(text="🟡  SIMULATION MODE — no real on-chain transactions",
                                        bg=C["sim_bg"],fg=C["sim_fg"])
            else:
                self.sim_banner.config(text="🔴  LIVE MODE — real funds WILL be sent on-chain",
                                        bg=C["live_bg"],fg=C["live_fg"])
            self._update_mode_badge()
        self.var_simulate.trace_add("write",_upd); _upd()
        bf=ttk.Frame(sim_box); bf.grid(row=1,column=0,pady=(8,0))
        ttk.Button(bf,text="Enable SIMULATION (safe)",
                   command=lambda: self.var_simulate.set(True),
                   style="Accent.TButton").pack(side="left",padx=6)
        ttk.Button(bf,text="Enable LIVE MODE (real funds)",
                   command=self._go_live,style="Danger.TButton").pack(side="left",padx=6)

        # ── Auto-refresh control ──────────────────────────────────────
        lr_box = section("🔄  Live, Tab-Aware Auto-Refresh", 5)
        tk.Label(lr_box,
                 text=(f"Whichever tab you're viewing polls fast and is marked 🟢 LIVE "
                       f"(All: {LIVE_INTERVAL_ALL}s · Pending: {LIVE_INTERVAL_PENDING}s · "
                       f"Balances: {LIVE_INTERVAL_BALANCES}s · History: {LIVE_INTERVAL_HISTORY}s). "
                       f"Tabs you're not watching fall back to a slower ⏸ background interval "
                       f"(All: {BACKGROUND_INTERVAL_ALL}s · Pending: {BACKGROUND_INTERVAL_PENDING}s · "
                       f"Balances: {BACKGROUND_INTERVAL_BALANCES}s · History: {BACKGROUND_INTERVAL_HISTORY}s). "
                       f"Switching tabs refreshes instantly."),
                 bg=C["bg"],fg=C["text_dim"],font=("Segoe UI",9), wraplength=680, justify="left"
                 ).grid(row=0,column=0,columnspan=3,sticky="w",pady=(0,6))
        self.var_pause=tk.BooleanVar(value=False)
        ttk.Checkbutton(lr_box,text="Pause all auto-refresh",variable=self.var_pause,
                         command=lambda: setattr(self,"_live_paused",self.var_pause.get())
                         ).grid(row=1,column=0,sticky="w")

        # ── Audit log paths ───────────────────────────────────────────
        path_box = section("📁  Data File Locations", 6)
        for i,(lbl,path) in enumerate([("TX History",TX_HISTORY_PATH),
                                        ("Pending TX Store",PENDING_TX_PATH),
                                        ("Daily Limits",DAILY_LIMIT_PATH),
                                        ("Address Blocklist",BLOCKLIST_PATH),
                                        ("Security Log",SECURITY_LOG_PATH),
                                        ("Config",CONFIG_PATH)]):
            tk.Label(path_box,text=lbl,font=("Segoe UI",9,"bold"),
                     bg=C["bg"],fg=C["text_dim"],width=16,anchor="w").grid(row=i,column=0,sticky="w",pady=2)
            tk.Label(path_box,text=path,font=("Consolas",8),
                     bg=C["bg"],fg=C["accent"]).grid(row=i,column=1,sticky="w",padx=8)
            def _open(p=path):
                if os.path.exists(p): webbrowser.open(p)
                else: messagebox.showinfo("Not found","File not created yet.")
            tk.Button(path_box,text="Open",font=("Segoe UI",8),bg=C["bg"],
                      fg=C["accent"],relief="flat",bd=0,cursor="hand2",
                      command=_open).grid(row=i,column=2,padx=4)

        # ── Save buttons ──────────────────────────────────────────────
        bot=ttk.Frame(inner); bot.grid(row=7,column=0,sticky="ew",padx=14,pady=8)
        ttk.Button(bot,text="💾 Save All Settings",command=self._save_all,
                   style="Success.TButton").pack(side="left",padx=4)
        ttk.Button(bot,text="Reset to Defaults",command=self._reset).pack(side="left",padx=4)

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
        net=self.var_network.get(); p=NETWORK_PRESETS.get(net,{})
        self.var_rpc.set(p.get("default_rpc",""))
        self.var_contract.set(p.get("token_contract",""))
        self.var_decimals.set(p.get("decimals",18))
        if "amount_source" in p: self.var_amount_src.set(p["amount_source"])
        self.net_lbl.config(text=p.get("label",""))

    def _save_all(self):
        self._collect(); ConfigStore.save(self.cfg); self._set_api()
        messagebox.showinfo("Saved","All settings saved.")

    def _save_wallet(self):
        self._collect()
        if self.cfg["from_address"] and not is_valid_address(self.cfg["from_address"]):
            if not messagebox.askyesno("Unusual address",
                    "The 'From Address' doesn't look like a standard 0x… wallet address. Save anyway?"):
                return
        new_pk=self.var_pk.get().strip()
        if new_pk:
            if self.var_persist_pk.get():
                pw=ask_pass(self.root,"Set passphrase to encrypt the key",confirm=True)
                if not pw: messagebox.showwarning("Cancelled","Key not saved."); return
                salt,token=encrypt_secret(new_pk,pw)
                self.cfg.update({"pk_set":True,"pk_salt":salt,"pk_token":token})
                self.pk_status.config(text="Key status: saved (encrypted)")
            else:
                self.cfg.update({"pk_set":False,"pk_salt":"","pk_token":""})
                self.pk_status.config(text="Key status: in memory only")
            self.runtime_pk=new_pk; self._last_activity = time.time(); self.var_pk.set("")
        ConfigStore.save(self.cfg); self._set_api()
        messagebox.showinfo("Saved","Wallet settings saved.")

    def _clear_pk(self):
        if not messagebox.askyesno("Confirm","Delete encrypted key from disk?"): return
        self.cfg.update({"pk_set":False,"pk_salt":"","pk_token":""})
        self.runtime_pk=None; ConfigStore.save(self.cfg)
        self.pk_status.config(text="Key status: not saved")
        messagebox.showinfo("Cleared","Saved key removed.")

    def _reset(self):
        if not messagebox.askyesno("Confirm","Reset ALL settings to defaults?"): return
        ConfigStore.delete(); self.cfg=dict(DEFAULT_CONFIG); self.runtime_pk=None
        messagebox.showinfo("Reset","Settings reset. Restart the app.")

    def _test_api(self):
        self._collect(); self._set_api()
        def work(): return self.api.stats()
        def done(st):
            messagebox.showinfo("API OK",
                f"Connected.\nPending: {st.get('pending_count',0)}\n"
                f"Total: {st.get('total_requests',0)}")
        def err(e): messagebox.showerror("API Failed",str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _test_rpc(self):
        self._collect(); rpcs=[self.cfg["rpc_url"]]
        def work(): return ChainClient.from_rpcs(rpcs).chain_id()
        def done(cid): messagebox.showinfo("RPC OK",f"Connected. Chain ID: {cid}")
        def err(e): messagebox.showerror("RPC Failed",str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _check_balances(self):
        self._collect()
        if not self.cfg["from_address"]:
            messagebox.showwarning("Missing","Enter 'From Wallet Address' first."); return
        self.nb.select(self.tab_balances); self.refresh_balances()

    def _go_live(self):
        if self.cfg.get("kill_switch_enabled"):
            messagebox.showwarning("Kill Switch Active",
                "The Emergency Kill Switch is currently ON, so live approvals will still be "
                "blocked even after enabling Live Mode. Disable it in the 🛡 Security tab when ready.")
        if not messagebox.askyesno("Enable LIVE mode?",
            "⚠ WARNING\n\nReal on-chain transactions will be sent. Real funds will move.\n"
            "All validation + security/firewall layers are active but nothing is 100% risk-free.\n\n"
            "Continue?", icon="warning"): return
        if not messagebox.askyesno("Second confirmation",
            "Confirm: clicking Approve will broadcast real token transfers.\n\n"
            "YES — enable LIVE mode.", icon="warning"): return
        self.var_simulate.set(False)
        SecurityLog.record("live_mode_enabled", "")

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
