#!/usr/bin/env python3
"""
Manual Withdrawal Admin Tool  v1.1.0
======================================
Single-file desktop app (Tkinter + web3.py).

Tabs:
  1. All Withdrawals  – full list with status filter, stats bar
  2. Pending          – FIFO list, approve/reject, activity log
  3. Wallet Balances  – live token balances for the hot wallet,
                        add/remove custom token addresses
  4. Wallet & API     – settings, private-key management,
                        network/contract config, live/simulate toggle

All on-chain logic lives here.
API routes used (AdminWithdrawalController):
  GET  /                → list all
  GET  /pending         → list pending (FIFO)
  GET  /stats           → summary counts
  GET  /{id}            → single record
  POST /{id}/approve    → mark approved  { transaction_hash, admin_note }
  POST /{id}/reject     → mark rejected  { admin_note }
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

APP_TITLE   = "Manual Withdrawal Admin"
APP_VERSION = "1.1.0"
CONFIG_DIR  = os.path.join(os.path.expanduser("~"), ".withdrawal_admin")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# ── Minimal ERC-20 ABI ───────────────────────────────────────────────
ERC20_ABI = [
    {"constant": True,  "inputs": [],
     "name": "name",    "outputs": [{"name": "", "type": "string"}],   "type": "function"},
    {"constant": True,  "inputs": [],
     "name": "symbol",  "outputs": [{"name": "", "type": "string"}],   "type": "function"},
    {"constant": True,  "inputs": [],
     "name": "decimals","outputs": [{"name": "", "type": "uint8"}],    "type": "function"},
    {"constant": True,  "inputs": [{"name": "_owner", "type": "address"}],
     "name": "balanceOf","outputs": [{"name": "balance","type": "uint256"}],"type":"function"},
    {"constant": False,
     "inputs": [{"name": "_to","type":"address"},{"name": "_value","type":"uint256"}],
     "name": "transfer","outputs": [{"name": "","type": "bool"}],      "type": "function"},
]

# ── Network presets ───────────────────────────────────────────────────
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
        "default_rpc":    "https://bsc-mainnet.infura.io/v3/3eb6cf40e51349a19618c4b0c1b823a2",
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
    "extra_tokens":   [],    # list of {address, symbol, decimals, network}
}

# ═══════════════════════════════════════════════════════════════════════
#  Crypto helpers (private-key storage)
# ═══════════════════════════════════════════════════════════════════════

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

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
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)

# ═══════════════════════════════════════════════════════════════════════
#  API client  (talks to AdminWithdrawalController routes only)
# ═══════════════════════════════════════════════════════════════════════

class ApiError(Exception): pass

class ApiClient:
    def __init__(self, base_url: str, auth_header: str):
        self.base_url    = (base_url or "").rstrip("/")
        self.auth_header = auth_header or ""
        self.session     = requests.Session()

    def _h(self):
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.auth_header:
            h["Authorization"] = self.auth_header
        return h

    def _req(self, method, path, params=None, body=None):
        if not self.base_url:
            raise ApiError("API Base URL is not configured — go to Wallet & API Settings.")
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

    def approve(self, wid, tx_hash, note=""):
        return self._req("POST", f"/{wid}/approve",
                         body={"transaction_hash": tx_hash, "admin_note": note or ""})

    def reject(self, wid, note):
        return self._req("POST", f"/{wid}/reject", body={"admin_note": note})

# ═══════════════════════════════════════════════════════════════════════
#  Chain client  (all on-chain logic lives here)
# ═══════════════════════════════════════════════════════════════════════

class ChainError(Exception): pass

class ChainClient:
    def __init__(self, rpc_url: str):
        if not rpc_url:
            raise ChainError("RPC URL not configured — go to Wallet & API Settings.")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if geth_poa_middleware:
            try:
                self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            except Exception:
                pass
        if not self.w3.is_connected():
            raise ChainError(f"Cannot connect to RPC: {rpc_url}")

    def cs(self, addr: str) -> str:
        try:
            return Web3.to_checksum_address(addr)
        except Exception:
            raise ChainError(f"Invalid address: {addr}")

    # ── balances ──────────────────────────────────────────────────────

    def native_balance(self, address: str) -> float:
        return float(self.w3.from_wei(self.w3.eth.get_balance(self.cs(address)), "ether"))

    def token_balance(self, contract_addr: str, wallet: str, decimals: int) -> float:
        c = self.w3.eth.contract(address=self.cs(contract_addr), abi=ERC20_ABI)
        return c.functions.balanceOf(self.cs(wallet)).call() / (10 ** decimals)

    def token_info(self, contract_addr: str):
        """Returns (symbol, decimals). Falls back gracefully."""
        try:
            c = self.w3.eth.contract(address=self.cs(contract_addr), abi=ERC20_ABI)
            symbol   = c.functions.symbol().call()
            decimals = c.functions.decimals().call()
            return symbol, int(decimals)
        except Exception:
            return "???", 18

    # ── send ──────────────────────────────────────────────────────────

    def send_token(self, private_key: str, from_addr: str, to_addr: str,
                   amount: float, contract_addr: str, decimals: int,
                   chain_id: int, nonce: int) -> str:
        """
        Builds, signs and broadcasts one ERC-20 transfer.
        Returns the tx hash hex string.
        All validation, gas estimation, signing done here — no logic in the UI layer.
        """
        from eth_account import Account

        from_cs    = self.cs(from_addr)
        to_cs      = self.cs(to_addr)
        contract_cs = self.cs(contract_addr)

        acct = Account.from_key(private_key)
        if acct.address.lower() != from_cs.lower():
            raise ChainError(
                "Private key does not match 'From wallet address'.\n"
                f"Key address : {acct.address}\n"
                f"Config address: {from_cs}"
            )

        units = int(round(amount * (10 ** decimals)))
        if units <= 0:
            raise ChainError(f"Token amount rounds to zero (amount={amount}, decimals={decimals})")

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
            pass  # keep fallback 300k

        signed = acct.sign_transaction(tx)
        raw    = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
        return self.w3.to_hex(self.w3.eth.send_raw_transaction(raw))

    def next_nonce(self, address: str) -> int:
        return self.w3.eth.get_transaction_count(self.cs(address), "pending")

    def chain_id(self) -> int:
        return self.w3.eth.chain_id

# ═══════════════════════════════════════════════════════════════════════
#  Tiny helpers
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
    suffix   = f"\n\nCrash log saved to:\n{log_path}" if log_path else ""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, (text[:1500] + suffix), "WithdrawalAdmin — Fatal Error", 0x10)
            return
        except Exception:
            pass
    try:
        print(text, file=sys.stderr)
    except Exception:
        pass

# ─── Passphrase dialog ────────────────────────────────────────────────

class PassphraseDialog(simpledialog.Dialog):
    def __init__(self, parent, title, confirm=False):
        self.confirm = confirm
        self.value   = None
        super().__init__(parent, title)

    def body(self, m):
        tk.Label(m, text="Passphrase:").grid(row=0, column=0, sticky="w", pady=4)
        self.e1 = tk.Entry(m, show="*", width=34)
        self.e1.grid(row=0, column=1, pady=4)
        if self.confirm:
            tk.Label(m, text="Confirm:").grid(row=1, column=0, sticky="w", pady=4)
            self.e2 = tk.Entry(m, show="*", width=34)
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

# ─── Scrollable frame helper ──────────────────────────────────────────

def make_scrollable(parent) -> tk.Frame:
    """
    Returns an inner tk.Frame that scrolls vertically inside `parent`.
    Pack or grid `parent`; put widgets inside the returned frame.
    """
    canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
    vsb    = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner  = tk.Frame(canvas)

    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)

    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    return inner

# ═══════════════════════════════════════════════════════════════════════
#  Main application
# ═══════════════════════════════════════════════════════════════════════

COLS = ("id","user_id","gross_bh","fee_bh","net_bh","net_usd","wallet","status","created_at")
HEADS = ("ID","User","Gross BH","Fee BH","Net BH","Net USD","Wallet Address","Status","Created")
WIDTHS = (55,110,100,90,100,100,260,80,140)

class App:
    def __init__(self, root: tk.Tk):
        self.root    = root
        self.root.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.root.geometry("1220x720")
        self.root.minsize(900, 580)

        self.cfg  = ConfigStore.load()
        self.api  = ApiClient(self.cfg["api_base_url"], self.cfg["auth_header"])
        self.runtime_pk: str | None = None

        self.all_records     : list = []
        self.pending_records : list = []

        # var_simulate must exist before _build_ui so Pending tab can bind to it
        self.var_simulate = tk.BooleanVar(value=self.cfg.get("simulate_only", True))

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
        """Return the private key (may open a passphrase dialog). Main-thread only."""
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
        raise ChainError("No wallet key configured — go to Wallet & API Settings.")

    def _new_chain(self) -> ChainClient:
        return ChainClient(self.cfg["rpc_url"])

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

        self._build_all_tab()
        self._build_pending_tab()
        self._build_balances_tab()
        self._build_settings_tab()

    # ── shared: tree + scrollbar ──────────────────────────────────────

    def _make_tree(self, parent):
        wrap = ttk.Frame(parent)
        tree = ttk.Treeview(wrap, columns=COLS, show="headings",
                            selectmode="extended")
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
        # colour rows by status
        tree.tag_configure("approved", background="#e6f4ea")
        tree.tag_configure("rejected", background="#fce8e6")
        tree.tag_configure("pending",  background="#fff8e1")
        return wrap, tree

    def _sort_tree(self, tree, col, reverse):
        data = [(tree.set(k, col), k) for k in tree.get_children("")]
        try:
            data.sort(key=lambda t: float(t[0].replace(",","").replace("$","")),
                      reverse=reverse)
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
        p = self.tab_all

        # toolbar
        bar = ttk.Frame(p, padding=(8, 6))
        bar.pack(fill="x")

        ttk.Label(bar, text="Status:").pack(side="left")
        self.var_all_status = tk.StringVar(value="all")
        cb = ttk.Combobox(bar, textvariable=self.var_all_status, state="readonly",
                          values=["all","pending","approved","rejected"], width=11)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_all())

        ttk.Button(bar, text="⟳ Refresh",      command=self.refresh_all).pack(side="left", padx=4)
        ttk.Button(bar, text="View Details",    command=self._all_details).pack(side="left", padx=4)

        self.all_stats = ttk.Label(bar, text="Stats: loading…", foreground="#555")
        self.all_stats.pack(side="left", padx=16)

        # tree (fills remaining space)
        wrap, self.all_tree = self._make_tree(p)
        wrap.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.all_tree.bind("<Double-1>", lambda e: self._all_details())

    def refresh_all(self, silent=False):
        self._set_api()
        status = getattr(self, "var_all_status", None)
        sv     = status.get() if status else "all"

        def work():
            records = self.api.list_all(status=sv)
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
        win.geometry("460x440")
        win.grab_set()
        t = tk.Text(win, wrap="word", font=("Consolas", 9))
        s = ttk.Scrollbar(win, command=t.yview)
        t.configure(yscrollcommand=s.set)
        s.pack(side="right", fill="y")
        t.pack(fill="both", expand=True, padx=6, pady=6)
        for k, v in rec.items():
            t.insert("end", f"{k:25s}: {v}\n")
        t.config(state="disabled")

    # ══════════════════════════════════════════════════════════════════
    #  TAB 2 — Pending
    # ══════════════════════════════════════════════════════════════════

    def _build_pending_tab(self):
        p = self.tab_pending

        # toolbar row 1 — buttons
        bar = ttk.Frame(p, padding=(8, 6))
        bar.pack(fill="x")

        ttk.Button(bar, text="⟳ Refresh",         command=self.refresh_pending).pack(side="left", padx=3)
        ttk.Button(bar, text="✔ Approve Selected", command=self.approve_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="✖ Reject Selected",  command=self.reject_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="✔✔ Approve ALL",     command=self.approve_all).pack(side="left", padx=3)

        # live/sim badge — always visible
        self.pending_mode_lbl = tk.Label(bar, text="", font=("TkDefaultFont", 9, "bold"),
                                         padx=10, pady=2, relief="solid", bd=1)
        self.pending_mode_lbl.pack(side="left", padx=12)
        self.var_simulate.trace_add("write", lambda *_: self._update_mode_badge())
        self._update_mode_badge()

        # toolbar row 2 — summary
        bar2 = ttk.Frame(p, padding=(8, 0))
        bar2.pack(fill="x")
        self.pending_summary = ttk.Label(
            bar2,
            text="Pending: 0  │  Total Net BH: 0.0000  │  Total Net USD: $0.00",
            font=("TkDefaultFont", 10, "bold"), foreground="#333"
        )
        self.pending_summary.pack(side="left")

        # tree
        wrap, self.pending_tree = self._make_tree(p)
        wrap.pack(fill="both", expand=True, padx=6, pady=4)
        self.pending_tree.bind("<Double-1>", lambda e: self._pending_details())

        # activity log
        log_frame = ttk.LabelFrame(p, text="Activity Log", padding=4)
        log_frame.pack(fill="x", padx=6, pady=(0, 6))

        self.log_text = tk.Text(log_frame, height=8, wrap="word",
                                state="disabled", font=("Consolas", 9))
        log_vsb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_vsb.grid(row=0, column=1, sticky="ns")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text.tag_configure("link",  foreground="#0055cc", underline=1)
        self.log_text.tag_configure("ok",    foreground="#2e7d32")
        self.log_text.tag_configure("fail",  foreground="#c62828")
        self.log_text.tag_configure("sim",   foreground="#e65100")

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

    def refresh_pending(self, silent=False):
        self._set_api()

        def work():
            return self.api.list_pending()

        def done(records):
            self.pending_records = records
            self._populate_tree(self.pending_tree, records)
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
            out = []
            for r in recs:
                try:
                    self.api.reject(r["id"], note)
                    self.log(f"#{r['id']}: Rejected", tag="ok")
                    out.append((r["id"], True))
                except ApiError as e:
                    self.log(f"#{r['id']}: Reject FAILED — {e}", tag="fail")
                    out.append((r["id"], False))
            return out

        def done(_):
            self.refresh_pending()
            self.refresh_all()

        self.run_bg(work, on_done=done)

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
        cfg           = self.cfg
        amount_field  = "net_amount_bh" if cfg["amount_source"] == "bh" else "net_amount_usd"
        total         = sum(float(r.get(amount_field, 0) or 0) for r in recs)
        simulate      = self.var_simulate.get()
        mode_str      = "SIMULATION — no real funds will move" if simulate else "⚠ LIVE — REAL FUNDS WILL BE SENT"

        if not cfg["from_address"]:
            messagebox.showwarning("Missing", "Set 'From Wallet Address' in Settings first.")
            return

        if not messagebox.askyesno(
            "Confirm",
            f"Mode: {mode_str}\n\n"
            f"Approve {len(recs)} withdrawal(s)?\n"
            f"Total {amount_field}: {fmt(total, 4)}\n"
            f"From wallet: {cfg['from_address']}"
        ):
            return

        # Fetch/decrypt the private key on the MAIN thread (may show a dialog).
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
            f"Batch start: {len(recs)} tx  |  "
            f"{'SIMULATE' if simulate else 'LIVE'}  |  "
            f"network={cfg['network']}  |  contract={cfg['token_contract']}",
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
                        raise ChainError(
                            f"{amount_field} is {amount} — cannot send zero.")

                    if simulate:
                        tx_hash = "SIMULATED-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                        self.log(
                            f"#{rid}: [SIM] would send {fmt(amount, 4)} → {to_addr}",
                            tag="sim")
                    else:
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
                        url = explorer + tx_hash if explorer else ""
                        self.log(
                            f"#{rid}: sent {fmt(amount,4)} → {to_addr}  tx={tx_hash}",
                            url=url, tag="ok")

                    self.api.approve(rid, tx_hash,
                                     note=(f"Admin tool {'SIMULATED' if simulate else cfg['network']}. "
                                           f"{amount_field}={fmt(amount,4)}"))
                    self.log(f"#{rid}: marked APPROVED in backend.", tag="ok")

                except Exception as exc:
                    self.log(f"#{rid}: FAILED — {exc}", tag="fail")

        def done(_):
            self.log("Batch complete.", tag="ok")
            self.refresh_pending()
            self.refresh_all()
            messagebox.showinfo("Done", "Batch complete. See Activity Log for details.")

        self.run_bg(work, on_done=done)

    # ══════════════════════════════════════════════════════════════════
    #  TAB 3 — Wallet Balances
    # ══════════════════════════════════════════════════════════════════

    def _build_balances_tab(self):
        p = self.tab_balances

        # ── toolbar ──
        bar = ttk.Frame(p, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="⟳ Refresh All Balances",
                   command=self.refresh_balances).pack(side="left", padx=4)
        ttk.Button(bar, text="+ Add Token to Watch",
                   command=self._add_watch_token).pack(side="left", padx=4)
        self.bal_status = ttk.Label(bar, text="", foreground="#555")
        self.bal_status.pack(side="left", padx=12)

        # ── wallet address display ──
        addr_f = ttk.LabelFrame(p, text="Hot Wallet Address", padding=6)
        addr_f.pack(fill="x", padx=8, pady=(4, 0))
        self.bal_addr_lbl = ttk.Label(addr_f, text=self.cfg.get("from_address") or "(not set)",
                                      font=("Consolas", 10), foreground="#1a237e")
        self.bal_addr_lbl.pack(anchor="w")

        # ── scrollable balance cards area ──
        cards_outer = ttk.Frame(p)
        cards_outer.pack(fill="both", expand=True, padx=8, pady=6)

        canvas  = tk.Canvas(cards_outer, borderwidth=0, highlightthickness=0)
        vsb     = ttk.Scrollbar(cards_outer, orient="vertical", command=canvas.yview)
        self.bal_cards_inner = tk.Frame(canvas)
        self.bal_cards_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.bal_cards_inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ── watched-token list panel ──
        watch_f = ttk.LabelFrame(p, text="Watched Tokens (click row to remove)", padding=6)
        watch_f.pack(fill="x", padx=8, pady=(0, 6))

        cols_w = ("symbol", "contract", "decimals", "network")
        self.watch_tree = ttk.Treeview(watch_f, columns=cols_w,
                                        show="headings", height=4)
        for c, w in (("symbol",60),("contract",360),("decimals",70),("network",120)):
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

    def _reload_watch_tree(self):
        for row in self.watch_tree.get_children():
            self.watch_tree.delete(row)
        for t in self.cfg.get("extra_tokens", []):
            self.watch_tree.insert("", "end",
                values=(t.get("symbol","?"), t.get("address",""), t.get("decimals",18), t.get("network","?")))

    def _add_watch_token(self):
        addr = simpledialog.askstring(
            "Add Token", "Enter the ERC-20 contract address to watch:", parent=self.root)
        if not addr:
            return
        addr = addr.strip()

        # try to auto-detect symbol/decimals from chain
        rpc = self.cfg.get("rpc_url", "")
        net = self.cfg.get("network", "polygon_bh")

        def work():
            if rpc:
                try:
                    chain  = ChainClient(rpc)
                    sym, dec = chain.token_info(addr)
                    return sym, dec
                except Exception:
                    pass
            return "???", 18

        def done(res):
            sym, dec = res
            sym = simpledialog.askstring("Symbol", f"Token symbol (detected: {sym}):",
                                         initialvalue=sym, parent=self.root) or sym
            try:
                dec = int(simpledialog.askstring(
                    "Decimals", f"Decimals (detected: {dec}):",
                    initialvalue=str(dec), parent=self.root) or dec)
            except Exception:
                pass

            tokens = self.cfg.get("extra_tokens", [])
            tokens.append({"address": addr, "symbol": sym, "decimals": dec, "network": net})
            self.cfg["extra_tokens"] = tokens
            ConfigStore.save(self.cfg)
            self._reload_watch_tree()
            messagebox.showinfo("Added", f"{sym} added to watchlist.")

        self.run_bg(work, on_done=done)

    def _remove_watch_token(self):
        sel = self.watch_tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Select a token row to remove.")
            return
        idx  = self.watch_tree.index(sel[0])
        tokens = self.cfg.get("extra_tokens", [])
        if 0 <= idx < len(tokens):
            removed = tokens.pop(idx)
            self.cfg["extra_tokens"] = tokens
            ConfigStore.save(self.cfg)
            self._reload_watch_tree()
            messagebox.showinfo("Removed", f"Removed {removed.get('symbol','token')}.")

    def refresh_balances(self):
        wallet = self.cfg.get("from_address", "").strip()
        self.bal_addr_lbl.config(text=wallet or "(not set)")

        if not wallet:
            messagebox.showwarning("No wallet", "Set 'From Wallet Address' in Settings first.")
            return

        rpc      = self.cfg["rpc_url"]
        preset   = NETWORK_PRESETS.get(self.cfg["network"], {})
        native   = preset.get("native_symbol", "Coin")
        contract = self.cfg["token_contract"]
        decimals = self.cfg["decimals"]
        extras   = list(self.cfg.get("extra_tokens", []))

        self.bal_status.config(text="Fetching…")

        def work():
            chain  = ChainClient(rpc)
            cid    = chain.chain_id()
            result = []

            # native coin
            try:
                bal = chain.native_balance(wallet)
                result.append({"symbol": native, "balance": bal,
                                "contract": "native", "type": "native"})
            except Exception as e:
                result.append({"symbol": native, "balance": None, "error": str(e), "type": "native"})

            # primary configured token
            try:
                sym, _ = chain.token_info(contract)
                bal    = chain.token_balance(contract, wallet, decimals)
                result.append({"symbol": sym, "balance": bal, "contract": contract,
                                "type": "primary", "decimals": decimals})
            except Exception as e:
                result.append({"symbol": "PRIMARY TOKEN", "balance": None,
                                "error": str(e), "contract": contract, "type": "primary"})

            # watched extra tokens
            for tok in extras:
                try:
                    bal = chain.token_balance(tok["address"], wallet, tok["decimals"])
                    result.append({"symbol": tok["symbol"], "balance": bal,
                                   "contract": tok["address"], "type": "extra",
                                   "decimals": tok["decimals"]})
                except Exception as e:
                    result.append({"symbol": tok["symbol"], "balance": None,
                                   "error": str(e), "contract": tok["address"], "type": "extra"})
            return result, cid

        def done(res):
            items, cid = res
            self.bal_status.config(text=f"Chain ID {cid}  •  {datetime.now().strftime('%H:%M:%S')}")
            self._render_balance_cards(items)

        def err(e):
            self.bal_status.config(text=f"Error: {e}")
            messagebox.showerror("Balance fetch failed", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    def _render_balance_cards(self, items: list):
        # clear existing cards
        for w in self.bal_cards_inner.winfo_children():
            w.destroy()

        explorer = NETWORK_PRESETS.get(self.cfg["network"], {}).get("explorer_tx", "")

        cols = 3  # cards per row — adjust to taste
        for i, item in enumerate(items):
            row, col = divmod(i, cols)

            card = tk.Frame(self.bal_cards_inner, bd=1, relief="solid",
                            padx=14, pady=12, bg="#ffffff")
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            self.bal_cards_inner.columnconfigure(col, weight=1)

            type_color = {"native": "#1565c0", "primary": "#2e7d32", "extra": "#6a1b9a"}
            sym_color  = type_color.get(item.get("type","extra"), "#333")

            tk.Label(card, text=item.get("symbol","?"),
                     font=("TkDefaultFont", 16, "bold"),
                     fg=sym_color, bg="#ffffff").pack(anchor="w")

            if item.get("balance") is not None:
                bal = item["balance"]
                if item.get("type") == "native":
                    bal_str = f"{bal:.8f}"
                else:
                    bal_str = f"{bal:,.4f}"
                tk.Label(card, text=bal_str,
                         font=("Consolas", 14, "bold"),
                         fg="#212121", bg="#ffffff").pack(anchor="w", pady=(4, 2))
            else:
                tk.Label(card, text=f"Error: {item.get('error','')}",
                         font=("TkDefaultFont", 9), fg="#c62828",
                         bg="#ffffff", wraplength=220, justify="left").pack(anchor="w", pady=4)

            contract = item.get("contract","")
            if contract and contract != "native":
                short = contract[:10] + "…" + contract[-6:]
                lbl = tk.Label(card, text=short, font=("Consolas", 8),
                               fg="#888", bg="#ffffff", cursor="hand2")
                lbl.pack(anchor="w")
                if explorer:
                    url = f"https://polygonscan.com/token/{contract}"
                    lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

            badge_text = {"native": "Gas coin", "primary": "Payout token", "extra": "Watched"}.get(
                item.get("type","extra"), "")
            if badge_text:
                tk.Label(card, text=badge_text, font=("TkDefaultFont", 8),
                         fg="#fff",
                         bg=sym_color,
                         padx=4, pady=1).pack(anchor="w", pady=(4, 0))

    # ══════════════════════════════════════════════════════════════════
    #  TAB 4 — Wallet & API Settings  (scrollable)
    # ══════════════════════════════════════════════════════════════════

    def _build_settings_tab(self):
        # Make entire tab scrollable
        inner = make_scrollable(self.tab_settings)
        inner.columnconfigure(0, weight=1)

        pad = {"padx": 12, "pady": 6}

        # ── 1. API ────────────────────────────────────────────────────
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
        ttk.Label(api_box, text="e.g. Bearer 1|abcde…", foreground="gray").grid(
            row=2, column=1, sticky="w", padx=(8,0))
        ttk.Button(api_box, text="Test API Connection",
                   command=self._test_api).grid(row=3, column=1, sticky="w", pady=6, padx=(8,0))

        # ── 2. Blockchain ─────────────────────────────────────────────
        chain_box = ttk.LabelFrame(inner, text="Blockchain / Token", padding=10)
        chain_box.grid(row=1, column=0, sticky="ew", **pad)
        chain_box.columnconfigure(1, weight=1)

        ttk.Label(chain_box, text="Network preset").grid(row=0, column=0, sticky="w", pady=3)
        self.var_network = tk.StringVar(value=self.cfg["network"])
        net_cb = ttk.Combobox(chain_box, textvariable=self.var_network,
                               state="readonly", values=list(NETWORK_PRESETS.keys()), width=22)
        net_cb.grid(row=0, column=1, sticky="w", padx=(8,0), pady=3)
        net_cb.bind("<<ComboboxSelected>>", self._on_net_change)
        self.net_lbl = ttk.Label(chain_box,
            text=NETWORK_PRESETS.get(self.cfg["network"], {}).get("label",""),
            foreground="#005a9e")
        self.net_lbl.grid(row=0, column=2, sticky="w", padx=8)

        ttk.Label(chain_box, text="RPC URL").grid(row=1, column=0, sticky="w", pady=3)
        self.var_rpc = tk.StringVar(value=self.cfg["rpc_url"])
        ttk.Entry(chain_box, textvariable=self.var_rpc).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8,0), pady=3)

        ttk.Label(chain_box, text="Token Contract Address").grid(row=2, column=0, sticky="w", pady=3)
        self.var_contract = tk.StringVar(value=self.cfg["token_contract"])
        ttk.Entry(chain_box, textvariable=self.var_contract).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(8,0), pady=3)

        ttk.Label(chain_box, text="Token Decimals").grid(row=3, column=0, sticky="w", pady=3)
        self.var_decimals = tk.IntVar(value=self.cfg["decimals"])
        ttk.Spinbox(chain_box, from_=0, to=18, textvariable=self.var_decimals, width=6).grid(
            row=3, column=1, sticky="w", padx=(8,0), pady=3)

        ttk.Label(chain_box, text="Amount field to send").grid(row=4, column=0, sticky="w", pady=3)
        self.var_amount_src = tk.StringVar(value=self.cfg["amount_source"])
        af = ttk.Frame(chain_box)
        af.grid(row=4, column=1, columnspan=2, sticky="w", padx=(8,0))
        ttk.Radiobutton(af, text="net_amount_bh  (BH token amount)",
                         variable=self.var_amount_src, value="bh").pack(anchor="w")
        ttk.Radiobutton(af, text="net_amount_usd  (USD value, send as USDT)",
                         variable=self.var_amount_src, value="usd").pack(anchor="w")

        ttk.Button(chain_box, text="Test RPC Connection",
                   command=self._test_rpc).grid(row=5, column=1, sticky="w", pady=6, padx=(8,0))

        # ── 3. Wallet ─────────────────────────────────────────────────
        wallet_box = ttk.LabelFrame(inner, text="Sending Wallet (hot wallet)", padding=10)
        wallet_box.grid(row=2, column=0, sticky="ew", **pad)
        wallet_box.columnconfigure(1, weight=1)

        tk.Label(wallet_box,
                 text="⚠  This wallet pays customers. Only fund it with what you intend to send.",
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
        ttk.Checkbutton(pk_f, text="show",
                         variable=self.var_show_pk,
                         command=lambda: self.pk_entry.config(
                             show="" if self.var_show_pk.get() else "*")
                         ).pack(side="left", padx=4)

        self.var_persist_pk = tk.BooleanVar(value=self.cfg.get("pk_set", False))
        ttk.Checkbutton(wallet_box,
                         text="Encrypt and save key to disk (requires a passphrase)",
                         variable=self.var_persist_pk).grid(
            row=3, column=1, columnspan=2, sticky="w", padx=(8,0))

        status_str = "saved (encrypted)" if self.cfg.get("pk_set") else "not saved"
        self.pk_status = ttk.Label(wallet_box, text=f"Status: {status_str}", foreground="gray")
        self.pk_status.grid(row=4, column=1, sticky="w", padx=(8,0))

        btn_f = ttk.Frame(wallet_box)
        btn_f.grid(row=5, column=1, columnspan=2, sticky="w", padx=(8,0), pady=6)
        ttk.Button(btn_f, text="Save Wallet Settings",
                   command=self._save_wallet).pack(side="left", padx=3)
        ttk.Button(btn_f, text="Clear Saved Key",
                   command=self._clear_pk).pack(side="left", padx=3)
        ttk.Button(btn_f, text="Check Balances",
                   command=self._check_balances).pack(side="left", padx=3)

        # ── 4. Live / Simulation ──────────────────────────────────────
        sim_box = ttk.LabelFrame(inner, text="⚠  LIVE / SIMULATION MODE", padding=10)
        sim_box.grid(row=3, column=0, sticky="ew", **pad)
        sim_box.columnconfigure(0, weight=1)

        self.sim_banner = tk.Label(sim_box, text="", font=("TkDefaultFont", 11, "bold"),
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

        # ── 5. Bottom buttons ─────────────────────────────────────────
        bot = ttk.Frame(inner, padding=10)
        bot.grid(row=4, column=0, sticky="ew", **pad)
        ttk.Button(bot, text="💾 Save All Settings",
                   command=self._save_all).pack(side="left", padx=4)
        ttk.Button(bot, text="Reset to Defaults",
                   command=self._reset).pack(side="left", padx=4)

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
        net = self.var_network.get()
        p   = NETWORK_PRESETS.get(net, {})
        self.var_rpc.set(p.get("default_rpc", ""))
        self.var_contract.set(p.get("token_contract", ""))
        self.var_decimals.set(p.get("decimals", 18))
        if "amount_source" in p:
            self.var_amount_src.set(p["amount_source"])
        self.net_lbl.config(text=p.get("label", ""))

    def _save_all(self):
        self._collect()
        ConfigStore.save(self.cfg)
        self._set_api()
        messagebox.showinfo("Saved", "Settings saved.")

    def _save_wallet(self):
        self._collect()
        new_pk = self.var_pk.get().strip()
        if new_pk:
            if self.var_persist_pk.get():
                pw = ask_pass(self.root, "Set passphrase to encrypt key", confirm=True)
                if not pw:
                    messagebox.showwarning("Cancelled", "Key was not saved.")
                    return
                salt, token = encrypt_secret(new_pk, pw)
                self.cfg.update({"pk_set": True, "pk_salt": salt, "pk_token": token})
                self.pk_status.config(text="Status: saved (encrypted)")
            else:
                self.cfg.update({"pk_set": False, "pk_salt": "", "pk_token": ""})
                self.pk_status.config(text="Status: in memory only (not saved to disk)")
            self.runtime_pk = new_pk
            self.var_pk.set("")
        ConfigStore.save(self.cfg)
        self._set_api()
        messagebox.showinfo("Saved", "Wallet settings saved.")

    def _clear_pk(self):
        if not messagebox.askyesno("Confirm", "Delete the saved encrypted key from disk?"):
            return
        self.cfg.update({"pk_set": False, "pk_salt": "", "pk_token": ""})
        self.runtime_pk = None
        ConfigStore.save(self.cfg)
        self.pk_status.config(text="Status: not saved")
        messagebox.showinfo("Cleared", "Saved key removed.")

    def _reset(self):
        if not messagebox.askyesno("Confirm", "Reset ALL settings to defaults?"):
            return
        ConfigStore.delete()
        self.cfg = dict(DEFAULT_CONFIG)
        self.runtime_pk = None
        messagebox.showinfo("Reset", "Settings reset. Please restart the app.")

    def _test_api(self):
        self._collect()
        self._set_api()
        def work(): return self.api.stats()
        def done(st):
            messagebox.showinfo("API OK",
                f"Connected.\nPending: {st.get('pending_count',0)}\n"
                f"Total: {st.get('total_requests',0)}")
        def err(e): messagebox.showerror("API Test Failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _test_rpc(self):
        self._collect()
        def work():
            chain = ChainClient(self.cfg["rpc_url"])
            return chain.chain_id()
        def done(cid): messagebox.showinfo("RPC OK", f"Connected. Chain ID: {cid}")
        def err(e):    messagebox.showerror("RPC Test Failed", str(e))
        self.run_bg(work, on_done=done, on_error=err)

    def _check_balances(self):
        self._collect()
        if not self.cfg["from_address"]:
            messagebox.showwarning("Missing", "Enter 'From Wallet Address' first.")
            return
        # Switch to the Balances tab and refresh
        self.nb.select(self.tab_balances)
        self.refresh_balances()

    def _go_live(self):
        if not messagebox.askyesno("Enable LIVE mode?",
                "⚠ WARNING\n\nReal on-chain transactions will be sent.\n"
                "Real funds will move. This cannot be undone.\n\n"
                "Are you sure?", icon="warning"):
            return
        if not messagebox.askyesno("Second confirmation",
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
