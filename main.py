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
    "bsc": {
        "label": "BNB Smart Chain (BEP-20 USDT)",
        "chain_id": 56,
        "usdt_contract": "0x55d398326f99059fF775485246999027B3197955",
        "decimals": 18,
        "default_rpc": "https://bsc-mainnet.infura.io/v3/3eb6cf40e51349a19618c4b0c1b823a2",
        "explorer_tx": "https://bscscan.com/tx/",
        "native_symbol": "BNB",
    },
    "polygon": {
        "label": "Polygon (USDT)",
        "chain_id": 137,
        "usdt_contract": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "decimals": 6,
        "default_rpc": "https://polygon-rpc.com",
        "explorer_tx": "https://polygonscan.com/tx/",
        "native_symbol": "MATIC",
    },
}

DEFAULT_CONFIG = {
    "api_base_url": "https://yourdomain.com/api/v1/admin/withdrawals",
    "auth_header": "",          # full header value, e.g. "Bearer xxxxxxxx"
    "network": "bsc",
    "rpc_url": NETWORK_PRESETS["bsc"]["default_rpc"],
    "usdt_contract": NETWORK_PRESETS["bsc"]["usdt_contract"],
    "decimals": NETWORK_PRESETS["bsc"]["decimals"],
    "amount_source": "usd",     # "usd" -> net_amount_usd, "bh" -> net_amount_bh
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
