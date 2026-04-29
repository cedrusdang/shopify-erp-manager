"""
Settings tab — load / save Shopify credentials to/from .env.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from ..config import load_env, save_env
from ..store_profiles import delete_profile, load_profiles, upsert_profile


class SettingsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app):
        super().__init__(parent)
        self._app = app
        self._profiles: list[dict[str, str]] = []
        self._build()

    # ──────────────────────────────────────────────────
    def _build(self) -> None:
        pad = ttk.Frame(self, padding=24)
        pad.pack(fill=tk.BOTH, expand=True)

        # ── Profile section (multiple stores) ───────
        profile_frame = ttk.LabelFrame(pad, text=" Store Profiles ", padding=14)
        profile_frame.pack(fill=tk.X, pady=(0, 12))
        profile_frame.columnconfigure(1, weight=1)

        ttk.Label(profile_frame, text="Profile Name:").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        self._profile_name = ttk.Entry(profile_frame, width=30)
        self._profile_name.grid(row=0, column=1, sticky=tk.W)

        ttk.Label(profile_frame, text="Saved Profiles:").grid(row=1, column=0, sticky=tk.NW, pady=6, padx=(0, 8))
        self._profile_list = tk.Listbox(profile_frame, height=5, exportselection=False)
        self._profile_list.grid(row=1, column=1, sticky=tk.EW, pady=6)
        self._profile_list.bind("<<ListboxSelect>>", lambda _: self._on_profile_select())

        pbtns = ttk.Frame(profile_frame)
        pbtns.grid(row=1, column=2, sticky=tk.N, padx=(8, 0), pady=6)
        ttk.Button(pbtns, text="Save/Update", command=self._save_profile).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(pbtns, text="Load (Apply)", command=self._load_profile_apply).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(pbtns, text="Delete", command=self._delete_profile).pack(fill=tk.X)

        # ── .env section ────────────────────────────
        env_frame = ttk.LabelFrame(pad, text=" Credentials (.env) ", padding=14)
        env_frame.pack(fill=tk.X, pady=(0, 16))
        env_frame.columnconfigure(1, weight=1)

        ttk.Label(env_frame, text="Store Domain:").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        self._env_store = ttk.Entry(env_frame, width=50)
        self._env_store.grid(row=0, column=1, sticky=tk.EW)
        ttk.Label(
            env_frame, text="e.g. mystore.myshopify.com",
            foreground="gray", font=("Segoe UI", 8),
        ).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(env_frame, text="Client ID:").grid(row=1, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        self._env_client_id = ttk.Entry(env_frame, width=50)
        self._env_client_id.grid(row=1, column=1, sticky=tk.EW)

        ttk.Label(env_frame, text="Client Secret:").grid(row=2, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        self._env_client_secret = ttk.Entry(env_frame, width=50, show="*")
        self._env_client_secret.grid(row=2, column=1, sticky=tk.EW)

        self._show_token = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            env_frame, text="Show secret",
            variable=self._show_token,
            command=self._toggle_show,
        ).grid(row=2, column=2, padx=(6, 0))

        btns = ttk.Frame(env_frame)
        btns.grid(row=3, column=0, columnspan=3, pady=(12, 0), sticky=tk.W)
        ttk.Button(btns, text="📂  Load .env to Form", command=self._load).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="💾  Save to .env",      command=self._save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="➡  Apply to Connection bar", command=self._apply).pack(side=tk.LEFT)

        # ── Info ────────────────────────────────────
        info = ttk.LabelFrame(pad, text=" Info ", padding=14)
        info.pack(fill=tk.X)
        ttk.Label(
            info,
            text=(
                "• .env is stored in the working directory and excluded from git.\n"
                "• 'Apply to Connection bar' copies these values to the top connection bar\n"
                "  without saving, so they only last for the current session.\n"
                "• API token is generated automatically from Client ID/Secret in the main screen.\n"
                "• 'Save to .env' persists them for next launch."
            ),
            justify=tk.LEFT,
            foreground="#444",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W)

        # Auto-populate from .env on open
        self._load(silent=True)
        self._refresh_profiles()

    # ──────────────────────────────────────────────────
    def _toggle_show(self) -> None:
        self._env_client_secret.config(show="" if self._show_token.get() else "*")

    def _load(self, *, silent: bool = False) -> None:
        env = load_env()
        s = env.get("SHOPIFY_STORE_DOMAIN", "")
        c = env.get("SHOPIFY_CLIENT_ID", "")
        k = env.get("SHOPIFY_CLIENT_SECRET", "")
        self._env_store.delete(0, tk.END)
        self._env_store.insert(0, s)
        self._env_client_id.delete(0, tk.END)
        self._env_client_id.insert(0, c)
        self._env_client_secret.delete(0, tk.END)
        self._env_client_secret.insert(0, k)
        if not silent:
            messagebox.showinfo(
                "Loaded", "Credentials loaded from .env.", parent=self
            )

    def _selected_profile(self) -> dict[str, str] | None:
        sel = self._profile_list.curselection()
        if not sel:
            return None
        idx = sel[0]
        if idx < 0 or idx >= len(self._profiles):
            return None
        return self._profiles[idx]

    def _refresh_profiles(self) -> None:
        self._profiles = load_profiles()
        self._profile_list.delete(0, tk.END)
        for p in self._profiles:
            self._profile_list.insert(tk.END, p.get("name", ""))

    def _on_profile_select(self) -> None:
        p = self._selected_profile()
        if not p:
            return
        self._profile_name.delete(0, tk.END)
        self._profile_name.insert(0, p.get("name", ""))

    def _save_profile(self) -> None:
        name = self._profile_name.get().strip()
        s = self._env_store.get().strip()
        c = self._env_client_id.get().strip()
        k = self._env_client_secret.get().strip()
        if not name or not s or not c or not k:
            messagebox.showwarning(
                "Incomplete",
                "Profile Name, Store Domain, Client ID, and Client Secret are required.",
                parent=self,
            )
            return
        upsert_profile(
            {
                "name": name,
                "store": s,
                "client_id": c,
                "client_secret": k,
            }
        )
        self._refresh_profiles()
        messagebox.showinfo("Saved", f"Profile '{name}' saved.", parent=self)

    def _load_profile_apply(self) -> None:
        p = self._selected_profile()
        if not p:
            messagebox.showwarning("No Profile", "Please select a profile.", parent=self)
            return

        # Load profile into the settings form for visibility/editing.
        self._profile_name.delete(0, tk.END)
        self._profile_name.insert(0, p.get("name", ""))
        self._env_store.delete(0, tk.END)
        self._env_store.insert(0, p.get("store", ""))
        self._env_client_id.delete(0, tk.END)
        self._env_client_id.insert(0, p.get("client_id", ""))
        self._env_client_secret.delete(0, tk.END)
        self._env_client_secret.insert(0, p.get("client_secret", ""))

        # Load now also applies directly to connection bar.
        self._app.store.set(p.get("store", ""))
        self._app.client_id.set(p.get("client_id", ""))
        self._app.client_secret.set(p.get("client_secret", ""))
        messagebox.showinfo(
            "Loaded + Applied",
            "Profile loaded and applied to connection bar.\n"
            "Token/connection will auto-init on startup, or click Get API Token manually.",
            parent=self,
        )

    def _delete_profile(self) -> None:
        p = self._selected_profile()
        if not p:
            messagebox.showwarning("No Profile", "Please select a profile.", parent=self)
            return
        name = p.get("name", "")
        if not self._app.confirm_danger("Delete Profile", f"Delete profile '{name}'?"):
            return
        delete_profile(name)
        self._refresh_profiles()
        self._profile_name.delete(0, tk.END)

    def _save(self) -> None:
        s = self._env_store.get().strip()
        c = self._env_client_id.get().strip()
        k = self._env_client_secret.get().strip()
        if not s or not c or not k:
            messagebox.showwarning(
                "Incomplete", "Please enter Store Domain, Client ID, and Client Secret.", parent=self
            )
            return
        if not self._app.confirm(
            "Save to .env",
            "Save credentials to .env?\n\n"
            "The file will be created / updated in the current working directory.",
        ):
            return
        try:
            save_env(s, c, k, self._app.token.get().strip())
            messagebox.showinfo("Saved", "Credentials saved to .env.", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _apply(self) -> None:
        s = self._env_store.get().strip()
        c = self._env_client_id.get().strip()
        k = self._env_client_secret.get().strip()
        if not s or not c or not k:
            messagebox.showwarning(
                "Incomplete", "Please enter Store Domain, Client ID, and Client Secret.", parent=self
            )
            return
        self._app.store.set(s)
        self._app.client_id.set(c)
        self._app.client_secret.set(k)
        messagebox.showinfo(
            "Applied",
            "Credentials applied to the connection bar.\n"
            "Then click 'Get API Token' to generate token automatically.\n"
            "(Not saved to disk — use 'Save to .env' to persist.)",
            parent=self,
        )
