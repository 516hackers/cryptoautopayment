#!/usr/bin/env python3
"""
Manual Withdrawal Admin Tool
=============================
A single-file desktop app (Tkinter) that talks to the Laravel
AdminWithdrawalController API (GET /pending, /completed, /stats,
POST /{id}/approve, POST /{id}/reject) and, on approval, broadcasts
a real on-chain USDT (BEP-20 / Polygon) transfer from an admin
"hot wallet" to the customer's wallet_address using web3.py -
this is the Python equivalent of the PHP Web3Service used elsewhere
in this project (that PHP class is used to VERIFY incoming deposits;
this app SENDS outgoing payouts).

Build to a Windows .exe with PyInstaller (see .github/workflows/build.yml).

SECURITY NOTE
-------------
This tool asks for a wallet PRIVATE KEY. Whoever runs this app and
holds that key can move real funds. Read the README.md that ships
with this file before using it with a real wallet.
"""

import os
import sys
import json
import base64
import threading
import traceback
import webbrowser
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


APP_TITLE = "Manual Withdrawal Admin"
APP_VERSION = "1.0.0"

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".withdrawal_admin")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# Minimal ERC20 ABI (transfer / balanceOf / decimals) - same shape as the
# usdtAbi used in the PHP Web3Service.
ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}],
     "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}],
     "type": "function"},
    {"constant": False,
     "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
     "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
]

NETWORK_PRESETS = {
    "polygon_bh": {
        "label": "Polygon — BH Token (net_amount_bh)",
        "chain_id": 137,
        "usdt_contract": "0x68a6EA8e9aB0824251061DD122aDA8493e62409d",  # BH token on Polygon
        "decimals": 18,   # ← adjust if your BH token uses different decimals
        "default_rpc": "https://polygon-rpc.com",
        "explorer_tx": "https://polygonscan.com/tx/",
        "native_symbol": "MATIC",
        "amount_source": "bh",   # hint: use net_amount_bh for this network
    },
    "polygon_usdt": {
        "label": "Polygon — USDT (net_amount_usd)",
        "chain_id": 137,
        "usdt_contract": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "decimals": 6,
        "default_rpc": "https://polygon-rpc.com",
        "explorer_tx": "https://polygonscan.com/tx/",
        "native_symbol": "MATIC",
        "amount_source": "usd",
    },
    "bsc_usdt": {
        "label": "BNB Smart Chain — USDT (net_amount_usd)",
        "chain_id": 56,
        "usdt_contract": "0x55d398326f99059fF775485246999027B3197955",
        "decimals": 18,
        "default_rpc": "https://bsc-mainnet.infura.io/v3/3eb6cf40e51349a19618c4b0c1b823a2",
        "explorer_tx": "https://bscscan.com/tx/",
        "native_symbol": "BNB",
        "amount_source": "usd",
    },
}

DEFAULT_CONFIG = {
    "api_base_url": "https://yourdomain.com/api/v1/admin/withdrawals",
    "auth_header": "",          # full header value, e.g. "Bearer xxxxxxxx"
    "network": "polygon_bh",   # default: BH token on Polygon
    "rpc_url": NETWORK_PRESETS["polygon_bh"]["default_rpc"],
    "usdt_contract": NETWORK_PRESETS["polygon_bh"]["usdt_contract"],
    "decimals": NETWORK_PRESETS["polygon_bh"]["decimals"],
    "amount_source": "bh",     # "bh" -> net_amount_bh, "usd" -> net_amount_usd
    "from_address": "",
    "simulate_only": True,      # safety default: ON. Must be turned off to send real funds.
    "pk_set": False,
    "pk_salt": "",
    "pk_token": "",
}


# ----------------------------------------------------------------------
#  Encryption helpers (for optionally persisting the private key)
# ----------------------------------------------------------------------

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt_secret(plaintext: str, passphrase: str):
    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)
    token = Fernet(key).encrypt(plaintext.encode("utf-8"))
    return base64.b64encode(salt).decode("ascii"), token.decode("ascii")


def decrypt_secret(salt_b64: str, token: str, passphrase: str) -> str:
    salt = base64.b64decode(salt_b64)
    key = _derive_key(passphrase, salt)
    return Fernet(key).decrypt(token.encode("ascii")).decode("utf-8")


# ----------------------------------------------------------------------
#  Config store
# ----------------------------------------------------------------------

class ConfigStore:
    @staticmethod
    def load() -> dict:
        cfg = dict(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                cfg.update(saved)
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


# ----------------------------------------------------------------------
#  API client (talks to AdminWithdrawalController routes)
# ----------------------------------------------------------------------

class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, base_url: str, auth_header: str):
        self.base_url = (base_url or "").rstrip("/")
        self.auth_header = auth_header or ""
        self.session = requests.Session()

    def _headers(self):
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.auth_header:
            h["Authorization"] = self.auth_header
        return h

    def _request(self, method, path, params=None, json_body=None):
        if not self.base_url:
            raise ApiError("API base URL is not configured. Go to the Settings tab.")
        url = self.base_url + path
        try:
            resp = self.session.request(method, url, headers=self._headers(),
                                         params=params, json=json_body, timeout=20)
        except requests.RequestException as e:
            raise ApiError(f"Network error calling API: {e}")

        try:
            data = resp.json()
        except ValueError:
            raise ApiError(f"API returned non-JSON response (HTTP {resp.status_code}).")

        if resp.status_code >= 400 or data.get("success") is False:
            msg = data.get("message") or f"API request failed (HTTP {resp.status_code})"
            raise ApiError(msg)
        return data

    def list_withdrawals(self, status=None, per_page=200):
        params = {"per_page": per_page}
        if status and status != "all":
            params["status"] = status
        data = self._request("GET", "/", params=params)
        return data.get("data", {}).get("data", data.get("data", []))

    def list_pending(self, per_page=200):
        data = self._request("GET", "/pending", params={"per_page": per_page})
        return data.get("data", {}).get("data", data.get("data", []))

    def get_stats(self):
        data = self._request("GET", "/stats")
        return data.get("data", {})

    def approve(self, withdrawal_id, transaction_hash, admin_note=""):
        body = {"transaction_hash": transaction_hash, "admin_note": admin_note or ""}
        return self._request("POST", f"/{withdrawal_id}/approve", json_body=body)

    def reject(self, withdrawal_id, admin_note):
        body = {"admin_note": admin_note}
        return self._request("POST", f"/{withdrawal_id}/reject", json_body=body)


# ----------------------------------------------------------------------
#  Chain client (this is the Python equivalent of App\Services\Web3Service,
#  but for SENDING payouts instead of verifying incoming deposits)
# ----------------------------------------------------------------------

class ChainError(Exception):
    pass


class ChainClient:
    def __init__(self, rpc_url: str):
        if not rpc_url:
            raise ChainError("RPC URL is not configured. Go to the Settings tab.")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if geth_poa_middleware is not None:
            try:
                self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            except Exception:
                pass
        try:
            if not self.w3.is_connected():
                raise ChainError("Could not connect to the RPC endpoint.")
        except Exception as e:
            raise ChainError(f"Could not connect to RPC: {e}")

    def checksum(self, address: str) -> str:
        try:
            return Web3.to_checksum_address(address)
        except Exception:
            raise ChainError(f"Invalid wallet address: {address}")

    def native_balance(self, address: str) -> float:
        addr = self.checksum(address)
        wei = self.w3.eth.get_balance(addr)
        return float(self.w3.from_wei(wei, "ether"))

    def token_balance(self, contract_address: str, address: str, decimals: int) -> float:
        contract = self.w3.eth.contract(address=self.checksum(contract_address), abi=ERC20_ABI)
        raw = contract.functions.balanceOf(self.checksum(address)).call()
        return raw / (10 ** decimals)

    def next_nonce(self, address: str) -> int:
        return self.w3.eth.get_transaction_count(self.checksum(address), "pending")

    def send_token(self, private_key: str, from_address: str, to_address: str,
                    amount: float, contract_address: str, decimals: int,
                    chain_id: int, nonce: int):
        """Builds, signs and broadcasts a single ERC20 transfer. Returns tx hash hex string."""
        from eth_account import Account

        from_cs = self.checksum(from_address)
        to_cs = self.checksum(to_address)
        contract_cs = self.checksum(contract_address)

        contract = self.w3.eth.contract(address=contract_cs, abi=ERC20_ABI)
        amount_units = int(round(amount * (10 ** decimals)))
        if amount_units <= 0:
            raise ChainError(f"Computed token amount is zero or invalid for amount={amount}")

        try:
            gas_price = self.w3.eth.gas_price
        except Exception:
            gas_price = self.w3.to_wei(5, "gwei")

        tx = contract.functions.transfer(to_cs, amount_units).build_transaction({
            "chainId": chain_id,
            "gas": 250000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "from": from_cs,
        })

        try:
            est = self.w3.eth.estimate_gas(tx)
            tx["gas"] = int(est * 1.25)
        except Exception:
            pass  # keep fallback gas limit

        acct = Account.from_key(private_key)
        if acct.address.lower() != from_cs.lower():
            raise ChainError(
                "The private key entered does not match the configured 'From wallet address'."
            )

        signed = acct.sign_transaction(tx)
        raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        return self.w3.to_hex(tx_hash)


# ----------------------------------------------------------------------
#  Small UI helpers
# ----------------------------------------------------------------------

def fmt(n, places=4):
    try:
        return f"{float(n):,.{places}f}"
    except (TypeError, ValueError):
        return str(n)


def fmt_usd(n):
    try:
        return f"${float(n):,.2f}"
    except (TypeError, ValueError):
        return str(n)


class PassphraseDialog(simpledialog.Dialog):
    """Asks for a passphrase, masked, with an optional confirmation field."""

    def __init__(self, parent, title, confirm=False):
        self.confirm = confirm
        self.value = None
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text="Passphrase:").grid(row=0, column=0, sticky="w", pady=4)
        self.e1 = tk.Entry(master, show="*", width=32)
        self.e1.grid(row=0, column=1, pady=4)
        if self.confirm:
            tk.Label(master, text="Confirm:").grid(row=1, column=0, sticky="w", pady=4)
            self.e2 = tk.Entry(master, show="*", width=32)
            self.e2.grid(row=1, column=1, pady=4)
        return self.e1

    def validate(self):
        p1 = self.e1.get()
        if not p1:
            messagebox.showwarning("Required", "Passphrase cannot be empty.", parent=self)
            return False
        if self.confirm and p1 != self.e2.get():
            messagebox.showwarning("Mismatch", "Passphrases do not match.", parent=self)
            return False
        self.value = p1
        return True


def ask_passphrase(parent, title="Enter Passphrase", confirm=False):
    dlg = PassphraseDialog(parent, title, confirm=confirm)
    return dlg.value


# ----------------------------------------------------------------------
#  Main application
# ----------------------------------------------------------------------

class App:
    COLUMNS = ("id", "user_id", "gross_bh", "fee_bh", "net_bh", "net_usd",
               "wallet", "status", "created_at")
    HEADINGS = ("ID", "User", "Gross BH", "Fee BH", "Net BH", "Net USD",
                "Wallet Address", "Status", "Created")

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.geometry("1180x680")

        self.config_data = ConfigStore.load()
        self.api = ApiClient(self.config_data["api_base_url"], self.config_data["auth_header"])

        # Private key kept ONLY in memory for this run, never logged.
        self.runtime_private_key = None

        self.all_records = []
        self.pending_records = []

        self._build_ui()
        self.refresh_all(silent=True)
        self.refresh_pending(silent=True)

    # ---------------- generic helpers ----------------

    def ui(self, fn):
        """Schedule fn to run on the Tk main thread."""
        self.root.after(0, fn)

    def run_bg(self, fn, on_done=None, on_error=None):
        def wrapper():
            try:
                result = fn()
                if on_done:
                    self.ui(lambda r=result: on_done(r))
            except Exception as e:
                captured = e
                if on_error:
                    self.ui(lambda err=captured: on_error(err))
                else:
                    self.ui(lambda err=captured: messagebox.showerror("Error", str(err)))
        threading.Thread(target=wrapper, daemon=True).start()

    def get_private_key(self):
        """Returns the private key to sign with, prompting for a passphrase
        if it's stored encrypted on disk. MUST be called on the main thread
        (it may open a dialog)."""
        if self.runtime_private_key:
            return self.runtime_private_key
        if self.config_data.get("pk_set"):
            passphrase = ask_passphrase(self.root, "Unlock Wallet Key")
            if not passphrase:
                raise ChainError("Passphrase required to unlock the wallet key.")
            try:
                pk = decrypt_secret(self.config_data["pk_salt"], self.config_data["pk_token"], passphrase)
            except Exception:
                raise ChainError("Incorrect passphrase, or the saved key is corrupted.")
            self.runtime_private_key = pk
            return pk
        raise ChainError("No wallet private key is configured. Go to the Settings tab.")

    # ---------------- UI construction ----------------

    def _build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True)

        self.tab_all = ttk.Frame(nb)
        self.tab_pending = ttk.Frame(nb)
        self.tab_settings = ttk.Frame(nb)

        nb.add(self.tab_all, text="All Withdrawals")
        nb.add(self.tab_pending, text="Pending")
        nb.add(self.tab_settings, text="Wallet & API Settings")

        self._build_all_tab(self.tab_all)
        self._build_pending_tab(self.tab_pending)
        self._build_settings_tab(self.tab_settings)

    def _make_tree(self, parent, selectmode="browse"):
        wrap = ttk.Frame(parent)
        tree = ttk.Treeview(wrap, columns=self.COLUMNS, show="headings",
                             selectmode=selectmode, height=16)
        for col, head in zip(self.COLUMNS, self.HEADINGS):
            tree.heading(col, text=head)
            width = 70 if col == "id" else (260 if col == "wallet" else 110)
            tree.column(col, width=width, anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        return wrap, tree

    @staticmethod
    def _row_values(rec):
        return (
            rec.get("id"),
            rec.get("user_id"),
            fmt(rec.get("gross_amount_bh", 0)),
            fmt(rec.get("platform_fee_bh", 0)),
            fmt(rec.get("net_amount_bh", 0)),
            fmt_usd(rec.get("net_amount_usd", 0)),
            rec.get("wallet_address"),
            rec.get("status"),
            (rec.get("created_at") or "")[:19],
        )

    # ---------- Tab 1: All Withdrawals ----------

    def _build_all_tab(self, parent):
        top = ttk.Frame(parent, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Filter status:").pack(side="left")
        self.all_status_var = tk.StringVar(value="all")
        cb = ttk.Combobox(top, textvariable=self.all_status_var, state="readonly",
                           values=["all", "pending", "approved", "rejected"], width=12)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_all())

        ttk.Button(top, text="Refresh", command=self.refresh_all).pack(side="left", padx=6)
        ttk.Button(top, text="View Details", command=self.show_details_all).pack(side="left", padx=6)

        self.all_stats_label = ttk.Label(top, text="Stats: loading...")
        self.all_stats_label.pack(side="left", padx=20)

        wrap, self.all_tree = self._make_tree(parent, selectmode="browse")
        wrap.pack(fill="both", expand=True, padx=8, pady=4)

    def refresh_all(self, silent=False):
        status = getattr(self, "all_status_var", None)
        status_val = status.get() if status else "all"
        self._set_client()

        def work():
            records = self.api.list_withdrawals(status=status_val, per_page=500)
            stats = None
            try:
                stats = self.api.get_stats()
            except ApiError:
                pass
            return records, stats

        def done(result):
            records, stats = result
            self.all_records = records
            for row in self.all_tree.get_children():
                self.all_tree.delete(row)
            for rec in records:
                self.all_tree.insert("", "end", iid=str(rec.get("id")), values=self._row_values(rec))
            if stats:
                self.all_stats_label.config(text=(
                    f"Total: {stats.get('total_requests', 0)}  |  "
                    f"Pending: {stats.get('pending_count', 0)}  |  "
                    f"Approved: {stats.get('approved_count', 0)}  |  "
                    f"Rejected: {stats.get('rejected_count', 0)}  |  "
                    f"Pending USD: {fmt_usd(stats.get('pending_usd', 0))}  |  "
                    f"Paid USD: {fmt_usd(stats.get('total_paid_usd', 0))}"
                ))

        def err(e):
            if not silent:
                messagebox.showerror("Failed to load withdrawals", str(e))
            self.all_stats_label.config(text="Stats: unavailable")

        self.run_bg(work, on_done=done, on_error=err)

    def show_details_all(self):
        sel = self.all_tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Select a withdrawal first.")
            return
        rec_id = sel[0]
        rec = next((r for r in self.all_records if str(r.get("id")) == rec_id), None)
        if not rec:
            return
        self._show_record_popup(rec)

    def _show_record_popup(self, rec):
        win = tk.Toplevel(self.root)
        win.title(f"Withdrawal #{rec.get('id')}")
        win.geometry("420x420")
        text = tk.Text(win, wrap="word")
        text.pack(fill="both", expand=True, padx=8, pady=8)
        for k, v in rec.items():
            text.insert("end", f"{k}: {v}\n")
        text.config(state="disabled")

    # ---------- Tab 2: Pending ----------

    def _build_pending_tab(self, parent):
        top = ttk.Frame(parent, padding=8)
        top.pack(fill="x")

        ttk.Button(top, text="Refresh", command=self.refresh_pending).pack(side="left", padx=4)
        ttk.Button(top, text="Approve Selected", command=self.approve_selected).pack(side="left", padx=4)
        ttk.Button(top, text="Reject Selected", command=self.reject_selected).pack(side="left", padx=4)
        ttk.Button(top, text="Approve ALL Pending", command=self.approve_all).pack(side="left", padx=4)

        self.pending_mode_label = tk.Label(top, text="", font=("TkDefaultFont", 9, "bold"), padx=8, pady=2)
        self.pending_mode_label.pack(side="left", padx=10)

        def _update_mode_label(*_):
            if self.var_simulate.get():
                self.pending_mode_label.config(text="🟡 SIMULATE", bg="#fff3cd", fg="#856404")
            else:
                self.pending_mode_label.config(text="🔴 LIVE", bg="#f8d7da", fg="#721c24")

        # defer binding until var_simulate exists (it's created in _build_settings_tab)
        self.root.after(100, lambda: (
            self.var_simulate.trace_add("write", _update_mode_label),
            _update_mode_label()
        ))

        self.pending_summary = ttk.Label(top, text="Pending: 0  |  Total BH: 0  |  Total USD: $0.00",
                                          font=("TkDefaultFont", 10, "bold"))
        self.pending_summary.pack(side="left", padx=20)

        wrap, self.pending_tree = self._make_tree(parent, selectmode="extended")
        wrap.pack(fill="both", expand=True, padx=8, pady=4)

        log_frame = ttk.LabelFrame(parent, text="Activity Log")
        log_frame.pack(fill="both", expand=False, padx=8, pady=(0, 8))
        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.log_text.tag_configure("link", foreground="blue", underline=1)

    def log(self, message, url=None):
        def do():
            self.log_text.config(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] {message}")
            if url:
                start = self.log_text.index("end-1c")
                self.log_text.insert("end", f"  ({url})")
                end = self.log_text.index("end-1c")
                self.log_text.tag_add("link", start, end)
                self.log_text.tag_bind("link", "<Button-1>", lambda e, u=url: webbrowser.open(u))
            self.log_text.insert("end", "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.ui(do)

    def refresh_pending(self, silent=False):
        self._set_client()

        def work():
            return self.api.list_pending(per_page=500)

        def done(records):
            self.pending_records = records
            for row in self.pending_tree.get_children():
                self.pending_tree.delete(row)
            total_bh = 0.0
            total_usd = 0.0
            for rec in records:
                self.pending_tree.insert("", "end", iid=str(rec.get("id")), values=self._row_values(rec))
                try:
                    total_bh += float(rec.get("net_amount_bh", 0) or 0)
                    total_usd += float(rec.get("net_amount_usd", 0) or 0)
                except (TypeError, ValueError):
                    pass
            self.pending_summary.config(
                text=f"Pending: {len(records)}  |  Total Net BH: {fmt(total_bh)}  |  Total Net USD: {fmt_usd(total_usd)}"
            )

        def err(e):
            if not silent:
                messagebox.showerror("Failed to load pending withdrawals", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    # ---------- Settings ----------

    def _build_settings_tab(self, parent):
        outer = ttk.Frame(parent, padding=12)
        outer.pack(fill="both", expand=True)

        # --- API section ---
        api_box = ttk.LabelFrame(outer, text="Backend API", padding=10)
        api_box.pack(fill="x", pady=6)

        ttk.Label(api_box, text="API Base URL").grid(row=0, column=0, sticky="w", pady=3)
        self.var_api_base = tk.StringVar(value=self.config_data["api_base_url"])
        ttk.Entry(api_box, textvariable=self.var_api_base, width=60).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(api_box, text="Authorization Header").grid(row=1, column=0, sticky="w", pady=3)
        self.var_auth_header = tk.StringVar(value=self.config_data["auth_header"])
        ttk.Entry(api_box, textvariable=self.var_auth_header, width=60, show="*").grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(api_box, text="e.g. Bearer 1|abcde12345...", foreground="gray").grid(row=2, column=1, sticky="w")

        ttk.Button(api_box, text="Test API Connection", command=self.test_api).grid(row=3, column=1, sticky="w", pady=6)

        # --- Blockchain section ---
        chain_box = ttk.LabelFrame(outer, text="Blockchain / Token", padding=10)
        chain_box.pack(fill="x", pady=6)

        ttk.Label(chain_box, text="Network").grid(row=0, column=0, sticky="w", pady=3)
        self.var_network = tk.StringVar(value=self.config_data["network"])
        net_cb = ttk.Combobox(chain_box, textvariable=self.var_network, state="readonly",
                               values=list(NETWORK_PRESETS.keys()), width=30)
        net_cb.grid(row=0, column=1, sticky="w", pady=3)
        net_cb.bind("<<ComboboxSelected>>", self._on_network_change)
        # Show the human-readable label beside the key
        self.net_label = ttk.Label(chain_box, text=NETWORK_PRESETS.get(self.config_data["network"], {}).get("label", ""), foreground="#005a9e")
        self.net_label.grid(row=0, column=2, sticky="w", padx=8)

        ttk.Label(chain_box, text="RPC URL").grid(row=1, column=0, sticky="w", pady=3)
        self.var_rpc = tk.StringVar(value=self.config_data["rpc_url"])
        ttk.Entry(chain_box, textvariable=self.var_rpc, width=60).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(chain_box, text="USDT Contract Address").grid(row=2, column=0, sticky="w", pady=3)
        self.var_contract = tk.StringVar(value=self.config_data["usdt_contract"])
        ttk.Entry(chain_box, textvariable=self.var_contract, width=60).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(chain_box, text="Token Decimals").grid(row=3, column=0, sticky="w", pady=3)
        self.var_decimals = tk.IntVar(value=self.config_data["decimals"])
        ttk.Spinbox(chain_box, from_=0, to=18, textvariable=self.var_decimals, width=6).grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(chain_box, text="Amount to send per payout").grid(row=4, column=0, sticky="w", pady=3)
        self.var_amount_source = tk.StringVar(value=self.config_data["amount_source"])
        af = ttk.Frame(chain_box)
        af.grid(row=4, column=1, sticky="w")
        ttk.Radiobutton(af, text="net_amount_usd (USD value, in USDT)", variable=self.var_amount_source,
                         value="usd").pack(anchor="w")
        ttk.Radiobutton(af, text="net_amount_bh (BH amount)", variable=self.var_amount_source,
                         value="bh").pack(anchor="w")

        ttk.Button(chain_box, text="Test RPC Connection", command=self.test_rpc).grid(row=5, column=1, sticky="w", pady=6)

        # --- Wallet section ---
        wallet_box = ttk.LabelFrame(outer, text="Sending Wallet (hot wallet that pays customers)", padding=10)
        wallet_box.pack(fill="x", pady=6)

        warn = ("⚠ Whoever has this private key can move all funds in this wallet. "
                "Only use a wallet funded with what you intend to pay out, on a machine you trust.")
        ttk.Label(wallet_box, text=warn, foreground="#a13a00", wraplength=620, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(wallet_box, text="From Wallet Address").grid(row=1, column=0, sticky="w", pady=3)
        self.var_from_addr = tk.StringVar(value=self.config_data["from_address"])
        ttk.Entry(wallet_box, textvariable=self.var_from_addr, width=60).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(wallet_box, text="Private Key").grid(row=2, column=0, sticky="w", pady=3)
        pk_frame = ttk.Frame(wallet_box)
        pk_frame.grid(row=2, column=1, sticky="w", pady=3)
        self.var_pk = tk.StringVar(value="")
        self.pk_entry = ttk.Entry(pk_frame, textvariable=self.var_pk, width=50, show="*")
        self.pk_entry.pack(side="left")
        self.var_pk_show = tk.BooleanVar(value=False)

        def toggle_pk():
            self.pk_entry.config(show="" if self.var_pk_show.get() else "*")
        ttk.Checkbutton(pk_frame, text="show", variable=self.var_pk_show, command=toggle_pk).pack(side="left", padx=4)

        self.var_persist_key = tk.BooleanVar(value=self.config_data.get("pk_set", False))
        ttk.Checkbutton(wallet_box, text="Remember this key on disk, encrypted with a passphrase",
                         variable=self.var_persist_key).grid(row=3, column=1, sticky="w")

        key_status = "saved (encrypted)" if self.config_data.get("pk_set") else "not saved"
        self.pk_status_label = ttk.Label(wallet_box, text=f"Status: {key_status}", foreground="gray")
        self.pk_status_label.grid(row=4, column=1, sticky="w")

        btn_row = ttk.Frame(wallet_box)
        btn_row.grid(row=5, column=1, sticky="w", pady=6)
        ttk.Button(btn_row, text="Save Wallet Settings", command=self.save_wallet_settings).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Clear Saved Key", command=self.clear_saved_key).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Check Balances", command=self.check_balances).pack(side="left", padx=4)

        # --- Safety section ---
        safety_box = ttk.LabelFrame(outer, text="⚠  LIVE / SIMULATION MODE", padding=10)
        safety_box.pack(fill="x", pady=6)

        self.var_simulate = tk.BooleanVar(value=self.config_data.get("simulate_only", True))

        self.sim_banner = tk.Label(
            safety_box,
            text="",
            font=("TkDefaultFont", 11, "bold"),
            anchor="center",
            pady=6,
        )
        self.sim_banner.pack(fill="x")

        def _update_sim_banner(*_):
            if self.var_simulate.get():
                self.sim_banner.config(
                    text="🟡  SIMULATION MODE — no real transactions will be sent",
                    bg="#fff3cd", fg="#856404"
                )
            else:
                self.sim_banner.config(
                    text="🔴  LIVE MODE — real funds WILL be sent on-chain",
                    bg="#f8d7da", fg="#721c24"
                )
        self.var_simulate.trace_add("write", _update_sim_banner)
        _update_sim_banner()

        btn_row_sim = ttk.Frame(safety_box)
        btn_row_sim.pack(pady=(6, 0))
        ttk.Button(btn_row_sim, text="Enable SIMULATION mode (safe)",
                   command=lambda: self.var_simulate.set(True)).pack(side="left", padx=6)
        ttk.Button(btn_row_sim, text="Enable LIVE mode (sends real funds)",
                   command=lambda: self._confirm_go_live()).pack(side="left", padx=6)

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=10)
        ttk.Button(bottom, text="Save All Settings", command=self.save_all_settings).pack(side="left", padx=4)
        ttk.Button(bottom, text="Reset All Settings", command=self.reset_settings).pack(side="left", padx=4)

    def _on_network_change(self, event=None):
        net = self.var_network.get()
        preset = NETWORK_PRESETS.get(net)
        if not preset:
            return
        self.var_rpc.set(preset["default_rpc"])
        self.var_contract.set(preset["usdt_contract"])
        self.var_decimals.set(preset["decimals"])
        # Auto-select the recommended amount source for this network
        if "amount_source" in preset:
            self.var_amount_source.set(preset["amount_source"])
        if hasattr(self, "net_label"):
            self.net_label.config(text=preset.get("label", ""))

    def _collect_settings_into_config(self):
        self.config_data["api_base_url"] = self.var_api_base.get().strip()
        self.config_data["auth_header"] = self.var_auth_header.get().strip()
        self.config_data["network"] = self.var_network.get()
        self.config_data["rpc_url"] = self.var_rpc.get().strip()
        self.config_data["usdt_contract"] = self.var_contract.get().strip()
        self.config_data["decimals"] = int(self.var_decimals.get())
        self.config_data["amount_source"] = self.var_amount_source.get()
        self.config_data["from_address"] = self.var_from_addr.get().strip()
        self.config_data["simulate_only"] = bool(self.var_simulate.get())

    def _confirm_go_live(self):
        if not messagebox.askyesno(
            "Enable LIVE mode?",
            "⚠ WARNING ⚠\n\n"
            "LIVE mode will send REAL on-chain transactions from your wallet.\n"
            "Real funds will move. This cannot be undone.\n\n"
            "Are you sure you want to enable LIVE mode?",
            icon="warning"
        ):
            return
        if not messagebox.askyesno(
            "Confirm LIVE mode",
            "Second confirmation required.\n\n"
            "You understand that clicking 'Approve' will broadcast\n"
            "real token transfers from your configured wallet.\n\n"
            "Enable LIVE mode — YES I am sure.",
            icon="warning"
        ):
            return
        self.var_simulate.set(False)

    def _set_client(self):
        self.api = ApiClient(self.config_data["api_base_url"], self.config_data["auth_header"])

    def save_all_settings(self):
        self._collect_settings_into_config()
        ConfigStore.save(self.config_data)
        self._set_client()
        messagebox.showinfo("Saved", "Settings saved.")

    def save_wallet_settings(self):
        self._collect_settings_into_config()
        new_key = self.var_pk.get().strip()

        if new_key:
            if self.var_persist_key.get():
                passphrase = ask_passphrase(self.root, "Set a passphrase to encrypt the key", confirm=True)
                if not passphrase:
                    messagebox.showwarning("Cancelled", "Key was not saved.")
                    return
                salt_b64, token = encrypt_secret(new_key, passphrase)
                self.config_data["pk_set"] = True
                self.config_data["pk_salt"] = salt_b64
                self.config_data["pk_token"] = token
                self.pk_status_label.config(text="Status: saved (encrypted)")
            else:
                self.config_data["pk_set"] = False
                self.config_data["pk_salt"] = ""
                self.config_data["pk_token"] = ""
                self.pk_status_label.config(text="Status: kept in memory only (not saved to disk)")
            self.runtime_private_key = new_key
            self.var_pk.set("")  # clear from the visible widget

        ConfigStore.save(self.config_data)
        self._set_client()
        messagebox.showinfo("Saved", "Wallet settings saved.")

    def clear_saved_key(self):
        if not messagebox.askyesno("Confirm", "Delete the saved encrypted private key from disk?"):
            return
        self.config_data["pk_set"] = False
        self.config_data["pk_salt"] = ""
        self.config_data["pk_token"] = ""
        self.runtime_private_key = None
        ConfigStore.save(self.config_data)
        self.pk_status_label.config(text="Status: not saved")
        messagebox.showinfo("Cleared", "Saved key removed.")

    def reset_settings(self):
        if not messagebox.askyesno("Confirm", "Reset ALL settings (including the saved wallet key) to defaults?"):
            return
        ConfigStore.delete()
        self.config_data = dict(DEFAULT_CONFIG)
        self.runtime_private_key = None
        messagebox.showinfo("Reset", "Settings were reset. Please restart the app.")

    def test_api(self):
        self._collect_settings_into_config()
        self._set_client()

        def work():
            return self.api.get_stats()

        def done(stats):
            messagebox.showinfo("API OK", f"Connected. Pending: {stats.get('pending_count', 0)}, "
                                           f"Total: {stats.get('total_requests', 0)}")

        def err(e):
            messagebox.showerror("API Test Failed", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    def test_rpc(self):
        self._collect_settings_into_config()
        rpc = self.config_data["rpc_url"]

        def work():
            chain = ChainClient(rpc)
            return chain.w3.eth.chain_id

        def done(chain_id):
            messagebox.showinfo("RPC OK", f"Connected. Chain ID: {chain_id}")

        def err(e):
            messagebox.showerror("RPC Test Failed", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    def check_balances(self):
        self._collect_settings_into_config()
        from_addr = self.config_data["from_address"]
        if not from_addr:
            messagebox.showwarning("Missing", "Enter the 'From Wallet Address' first.")
            return
        rpc = self.config_data["rpc_url"]
        contract = self.config_data["usdt_contract"]
        decimals = self.config_data["decimals"]
        preset = NETWORK_PRESETS.get(self.config_data["network"], {})
        symbol = preset.get("native_symbol", "native coin")

        def work():
            chain = ChainClient(rpc)
            native = chain.native_balance(from_addr)
            token = chain.token_balance(contract, from_addr, decimals)
            return native, token

        def done(result):
            native, token = result
            messagebox.showinfo(
                "Balances",
                f"{from_addr}\n\nUSDT balance: {fmt(token, 2)}\n{symbol} balance (for gas): {fmt(native, 6)}"
            )

        def err(e):
            messagebox.showerror("Balance Check Failed", str(e))

        self.run_bg(work, on_done=done, on_error=err)

    # ---------- Approve / Reject actions ----------

    def _selected_pending_records(self):
        sel = self.pending_tree.selection()
        recs = [r for r in self.pending_records if str(r.get("id")) in sel]
        return recs

    def reject_selected(self):
        recs = self._selected_pending_records()
        if not recs:
            messagebox.showinfo("Select rows", "Select one or more pending withdrawals first.")
            return
        note = simpledialog.askstring("Reject", f"Reason for rejecting {len(recs)} withdrawal(s):", parent=self.root)
        if not note:
            messagebox.showwarning("Cancelled", "A rejection reason is required.")
            return
        self._set_client()

        def work():
            results = []
            for rec in recs:
                try:
                    self.api.reject(rec["id"], note)
                    results.append((rec["id"], True, None))
                except ApiError as e:
                    results.append((rec["id"], False, str(e)))
            return results

        def done(results):
            for rid, ok, err_msg in results:
                self.log(f"Reject #{rid}: {'OK' if ok else 'FAILED - ' + err_msg}")
            self.refresh_pending()
            self.refresh_all()

        self.run_bg(work, on_done=done)

    def approve_selected(self):
        recs = self._selected_pending_records()
        if not recs:
            messagebox.showinfo("Select rows", "Select one or more pending withdrawals first.")
            return
        self._approve_batch(recs)

    def approve_all(self):
        if not self.pending_records:
            messagebox.showinfo("Nothing to do", "There are no pending withdrawals loaded.")
            return
        self._approve_batch(list(self.pending_records))

    def _approve_batch(self, recs):
        self._collect_settings_into_config()
        cfg = self.config_data

        if not cfg["from_address"]:
            messagebox.showwarning("Missing settings", "Configure the 'From Wallet Address' in Settings first.")
            return

        amount_field = "net_amount_usd" if cfg["amount_source"] == "usd" else "net_amount_bh"
        total_amount = 0.0
        for r in recs:
            try:
                total_amount += float(r.get(amount_field, 0) or 0)
            except (TypeError, ValueError):
                pass

        mode = "SIMULATION (no real funds will move)" if cfg["simulate_only"] else "LIVE - REAL FUNDS WILL BE SENT"
        confirm = messagebox.askyesno(
            "Confirm Approval",
            f"Mode: {mode}\n\n"
            f"You are about to approve {len(recs)} withdrawal(s).\n"
            f"Total amount ({amount_field}): {fmt(total_amount, 2)}\n"
            f"From wallet: {cfg['from_address']}\n\n"
            "Each one will be sent on-chain to the customer's wallet_address "
            "and then marked approved via the API. Continue?"
        )
        if not confirm:
            return

        # Must fetch/decrypt the private key on the MAIN thread (it may show a dialog).
        if not cfg["simulate_only"]:
            try:
                private_key = self.get_private_key()
            except ChainError as e:
                messagebox.showerror("Wallet key required", str(e))
                return
        else:
            private_key = None

        self._set_client()
        network = cfg["network"]
        preset = NETWORK_PRESETS.get(network, {})
        chain_id = preset.get("chain_id", 56)
        explorer = preset.get("explorer_tx", "")
        rpc_url = cfg["rpc_url"]
        contract_address = cfg["usdt_contract"]
        decimals = cfg["decimals"]
        from_address = cfg["from_address"]
        simulate = cfg["simulate_only"]

        self.log(f"Starting approval of {len(recs)} withdrawal(s)... mode={'SIMULATE' if simulate else 'LIVE'}")

        def work():
            results = []
            chain = None
            nonce = None
            if not simulate:
                chain = ChainClient(rpc_url)
                nonce = chain.next_nonce(from_address)

            for rec in recs:
                rid = rec.get("id")
                to_addr = rec.get("wallet_address")
                try:
                    amount = float(rec.get(amount_field, 0) or 0)
                    if amount <= 0:
                        raise ChainError(f"Amount is zero/invalid ({amount_field}={amount})")

                    if simulate:
                        tx_hash = "SIMULATED-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                        self.log(f"#{rid}: [SIMULATED] would send {fmt(amount, 2)} to {to_addr}")
                    else:
                        tx_hash = chain.send_token(
                            private_key=private_key,
                            from_address=from_address,
                            to_address=to_addr,
                            amount=amount,
                            contract_address=contract_address,
                            decimals=decimals,
                            chain_id=chain_id,
                            nonce=nonce,
                        )
                        nonce += 1
                        url = (explorer + tx_hash) if explorer else None
                        self.log(f"#{rid}: broadcast {fmt(amount, 2)} to {to_addr} -> tx {tx_hash}", url=url)

                    self.api.approve(rid, tx_hash,
                                      admin_note=f"Sent via admin tool ({'simulated' if simulate else network}). "
                                                 f"Amount: {fmt(amount, 2)} ({amount_field}).")
                    self.log(f"#{rid}: marked APPROVED in backend.")
                    results.append((rid, True, tx_hash, None))

                except (ChainError, ApiError, Exception) as e:
                    self.log(f"#{rid}: FAILED - {e}")
                    results.append((rid, False, None, str(e)))
                    # If sending succeeded but the API call failed, the tx hash is
                    # still in the log above so it can be confirmed manually.
            return results

        def done(results):
            ok_count = sum(1 for r in results if r[1])
            fail_count = len(results) - ok_count
            self.log(f"Batch complete: {ok_count} succeeded, {fail_count} failed.")
            self.refresh_pending()
            self.refresh_all()
            messagebox.showinfo("Batch complete", f"{ok_count} succeeded, {fail_count} failed. See Activity Log.")

        def err(e):
            self.log(f"Batch aborted: {e}")
            messagebox.showerror("Batch failed", str(e))

        self.run_bg(work, on_done=done, on_error=err)


def main():
    root = tk.Tk()

    def report_callback_exception(exc, val, tb):
        _show_fatal_error("".join(traceback.format_exception(exc, val, tb)))

    root.report_callback_exception = report_callback_exception

    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app = App(root)
    root.mainloop()


def _write_crash_log(text: str) -> str:
    """Writes startup-failure details to a file. Returns the path, or '' if
    that failed too (e.g. no write permission)."""
    try:
        log_dir = os.path.join(os.path.expanduser("~"), ".withdrawal_admin")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now().isoformat()} ---\n{text}\n")
        return log_path
    except Exception:
        return ""


def _show_fatal_error(text: str):
    """Surfaces a startup error in a way that works even when stdout/stderr
    don't (e.g. a --noconsole build, or a console whose output isn't being
    seen). Uses a native Win32 MessageBox via ctypes, which doesn't depend
    on Python's stdio at all."""
    log_path = _write_crash_log(text)
    suffix = f"\n\nDetails were also saved to:\n{log_path}" if log_path else ""
    shown = False
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, text[:1500] + suffix, "WithdrawalAdmin - Startup Error", 0x10
            )
            shown = True
        except Exception:
            pass
    if not shown:
        try:
            print(text, file=sys.stderr)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        _show_fatal_error(traceback.format_exc())
