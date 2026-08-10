import os
import sys
import time
import json
import base64
import struct
import shutil
import threading
import webbrowser
from typing import Optional, Dict
from tkinter import filedialog, messagebox
from PIL import Image

import customtkinter as ctk

from src.crypto.identity import Identity
from src.crypto.cipher import derive_conversation_key, encrypt, decrypt, CipherError, SequenceTracker
from src.network.relay import RelayConnection
from src.storage.contacts import ContactStore, Contact
from src.storage.messages import MessageStore
from src.storage.profile import Profile
from src.ui.themes import THEMES, DEFAULT_THEME, Theme
from src.updater import check_for_update, SOURCE_URL, CURRENT_VERSION

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
AVATARS_DIR = os.path.join(DATA_DIR, "avatars")
GUEST_PFP = os.path.join(BASE_DIR, "guest-pfp.png")


def load_avatar(path: str, size: int = 36) -> Optional[ctk.CTkImage]:
    try:
        if path and os.path.exists(path):
            img = Image.open(path)
        elif os.path.exists(GUEST_PFP):
            img = Image.open(GUEST_PFP)
        else:
            return None
        img = img.resize((size, size), Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    except Exception:
        return None


class CespoApp:

    def __init__(self):
        self._window = ctk.CTk()
        self._window.title("cespo")
        self._window.geometry("940x680")
        self._window.minsize(780, 560)

        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icon.png")
        if os.path.exists(icon_path):
            try:
                from PIL import ImageTk
                icon_img = Image.open(icon_path).resize((32, 32), Image.LANCZOS)
                self._icon_photo = ImageTk.PhotoImage(icon_img)
                self._window.iconphoto(True, self._icon_photo)
            except Exception:
                pass

        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(AVATARS_DIR, exist_ok=True)

        self._identity = Identity.load_or_create(os.path.join(DATA_DIR, "identity.key"))
        self._profile = Profile(os.path.join(DATA_DIR, "profile.json"))
        self._contacts = ContactStore(os.path.join(DATA_DIR, "contacts.json"))
        self._relay = RelayConnection()
        self._active_chat: Optional[str] = None
        self._msg_stores: Dict[str, MessageStore] = {}
        self._conv_keys: Dict[str, bytes] = {}
        self._settings_open = False
        self._seq_tracker = SequenceTracker()

        self._theme = THEMES.get(self._profile.theme, THEMES[DEFAULT_THEME])
        self._apply_theme()

        if not self._profile.setup_complete:
            self._show_setup()
        else:
            self._build_main()
            self._connect_relay()
            self._check_update()

    def _apply_theme(self):
        self._window.configure(fg_color=self._theme.bg)

    def _t(self) -> Theme:
        return self._theme

    def _copy_to_clipboard(self, text: str):
        self._window.clipboard_clear()
        self._window.clipboard_append(text)
        self._flash_status("Copied!")

    def _flash_status(self, msg: str, duration: int = 1500):
        """Briefly show a status message then revert."""
        if hasattr(self, '_status_text'):
            original = self._status_text.cget("text")
            original_color = self._status_text.cget("text_color")
            self._status_text.configure(text=msg, text_color=self._t().accent)
            self._window.after(duration, lambda: self._status_text.configure(
                text=original, text_color=original_color) if self._status_text.winfo_exists() else None)

    def _check_update(self):
        def on_result(new_version, download_url):
            if new_version:
                self._window.after(0, lambda: self._show_update_banner(new_version, download_url))
        check_for_update(on_result)

    def _show_update_banner(self, version: str, url: str):
        if not hasattr(self, '_main') or not self._main.winfo_exists():
            return
        banner = ctk.CTkFrame(self._main, fg_color=self._t().surface, height=32, corner_radius=0)
        banner.pack(fill="x", side="top", before=self._main.winfo_children()[0])
        inner = ctk.CTkFrame(banner, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(inner, text=f"v{version} available", font=ctk.CTkFont(size=10), text_color=self._t().warning).pack(side="left")
        if url:
            ctk.CTkButton(inner, text="Download", width=70, height=22, font=ctk.CTkFont(size=9), fg_color=self._t().accent, text_color="#000", hover_color=self._t().accent_hover, corner_radius=4, command=lambda: webbrowser.open(url)).pack(side="right")
        ctk.CTkButton(inner, text="✕", width=22, height=22, font=ctk.CTkFont(size=10), fg_color="transparent", hover_color=self._t().border, text_color=self._t().text_dim, corner_radius=4, command=banner.destroy).pack(side="right", padx=(0, 4))

    @staticmethod
    def _open_source():
        webbrowser.open(SOURCE_URL)

    def _show_setup(self):
        frame = ctk.CTkFrame(self._window, fg_color=self._t().bg)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(frame, text="cespo", font=ctk.CTkFont(family="Consolas", size=40, weight="bold"), text_color=self._t().accent).pack(pady=(0, 4))
        ctk.CTkLabel(frame, text="encrypted messaging", font=ctk.CTkFont(size=12), text_color=self._t().text_dim).pack(pady=(0, 28))

        ctk.CTkLabel(frame, text="YOUR ID", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w")
        id_frame = ctk.CTkFrame(frame, fg_color=self._t().input_bg, corner_radius=6)
        id_frame.pack(fill="x", pady=(4, 4))
        id_inner = ctk.CTkFrame(id_frame, fg_color="transparent")
        id_inner.pack(padx=12, pady=8)
        ctk.CTkLabel(id_inner, text=self._identity.void_id, font=ctk.CTkFont(family="Consolas", size=18, weight="bold"), text_color=self._t().text).pack(side="left")
        ctk.CTkButton(id_inner, text="Copy", width=50, height=26, font=ctk.CTkFont(size=10), fg_color=self._t().surface, hover_color=self._t().border, text_color=self._t().text_dim, corner_radius=4, command=lambda: self._copy_to_clipboard(self._identity.void_id)).pack(side="right", padx=(10, 0))
        ctk.CTkLabel(frame, text="", height=12).pack()  # spacer

        ctk.CTkLabel(frame, text="DISPLAY NAME", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w")
        self._setup_name = ctk.CTkEntry(frame, width=280, height=40, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text, corner_radius=8, font=ctk.CTkFont(size=14), placeholder_text="choose a name")
        self._setup_name.pack(pady=(4, 20))
        self._setup_name.bind("<Return>", lambda _: self._finish_setup())

        ctk.CTkButton(frame, text="Get Started", width=280, height=42, fg_color=self._t().accent, text_color="#000", hover_color=self._t().accent_hover, corner_radius=8, font=ctk.CTkFont(size=14, weight="bold"), command=self._finish_setup).pack()
        ctk.CTkLabel(frame, text="share your ID with others so they can message you", font=ctk.CTkFont(size=10), text_color=self._t().text_dim).pack(pady=(16, 0))

    def _finish_setup(self):
        name = self._setup_name.get().strip()[:15]
        if not name:
            messagebox.showerror("Error", "Enter a display name.")
            return
        self._profile.display_name = name
        self._profile.setup_complete = True
        for w in self._window.winfo_children():
            w.destroy()
        self._build_main()
        self._connect_relay()

    def _build_main(self):
        self._main = ctk.CTkFrame(self._window, fg_color=self._t().bg)
        self._main.pack(fill="both", expand=True)

        # Sidebar
        self._sidebar = ctk.CTkFrame(self._main, fg_color=self._t().sidebar, width=290, corner_radius=0)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # Sidebar header
        sh = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        sh.pack(fill="x", padx=14, pady=(14, 6))
        ctk.CTkLabel(sh, text="cespo", font=ctk.CTkFont(family="Consolas", size=18, weight="bold"), text_color=self._t().accent).pack(side="left")
        # Settings gear
        self._gear_btn = ctk.CTkButton(sh, text="⚙", width=28, height=28, font=ctk.CTkFont(size=14), fg_color="transparent", hover_color=self._t().surface, text_color=self._t().text_dim, corner_radius=14, command=self._toggle_settings)
        self._gear_btn.pack(side="right", padx=(0, 4))
        self._status_dot = ctk.CTkLabel(sh, text="●", font=ctk.CTkFont(size=8), text_color=self._t().danger)
        self._status_dot.pack(side="right", padx=(0, 6))

        # Search bar
        sf = ctk.CTkFrame(self._sidebar, fg_color=self._t().surface, corner_radius=6)
        sf.pack(fill="x", padx=10, pady=(0, 6))
        sfi = ctk.CTkFrame(sf, fg_color="transparent")
        sfi.pack(fill="x", padx=8, pady=6)
        self._search_entry = ctk.CTkEntry(sfi, height=30, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text, corner_radius=4, font=ctk.CTkFont(size=11), placeholder_text="Search or paste ID...")
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._search_entry.bind("<KeyRelease>", lambda _: self._on_search())
        self._search_entry.bind("<Return>", lambda _: self._on_search_enter())
        ctk.CTkButton(sfi, text="+", width=28, height=28, font=ctk.CTkFont(size=14, weight="bold"), fg_color=self._t().accent, text_color="#000", hover_color=self._t().accent_hover, corner_radius=4, command=self._add_contact_dialog).pack(side="right")

        ctk.CTkLabel(self._sidebar, text="MESSAGES", font=ctk.CTkFont(family="Consolas", size=9), text_color=self._t().text_dim).pack(anchor="w", padx=14, pady=(2, 4))

        # Contact list
        self._contact_list = ctk.CTkScrollableFrame(self._sidebar, fg_color="transparent")
        self._contact_list.pack(fill="both", expand=True, padx=6)

        # Profile at bottom
        pf = ctk.CTkFrame(self._sidebar, fg_color=self._t().surface, corner_radius=0)
        pf.pack(fill="x", side="bottom")
        pi = ctk.CTkFrame(pf, fg_color="transparent")
        pi.pack(fill="x", padx=12, pady=8)

        avatar_img = load_avatar(self._profile.avatar_path, 32)
        if avatar_img:
            self._avatar_label = ctk.CTkLabel(pi, text="", image=avatar_img, width=32, height=32, cursor="hand2", fg_color="transparent")
        else:
            self._avatar_label = ctk.CTkLabel(pi, text="●", width=32, height=32, font=ctk.CTkFont(size=20), text_color=self._t().text_dim, cursor="hand2", fg_color="transparent")
        self._avatar_label.pack(side="left", padx=(0, 10))
        self._avatar_label.bind("<Button-1>", lambda _: self._change_pfp())

        name_id_frame = ctk.CTkFrame(pi, fg_color="transparent")
        name_id_frame.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(name_id_frame, text=self._profile.display_name, font=ctk.CTkFont(size=12, weight="bold"), text_color=self._t().text, anchor="w").pack(anchor="w")
        id_row = ctk.CTkFrame(name_id_frame, fg_color="transparent")
        id_row.pack(anchor="w")
        ctk.CTkLabel(id_row, text=self._identity.void_id, font=ctk.CTkFont(family="Consolas", size=9), text_color=self._t().text_dim, anchor="w").pack(side="left")

        ctk.CTkButton(pi, text="Copy ID", width=54, height=24, font=ctk.CTkFont(size=9), fg_color=self._t().input_bg, hover_color=self._t().border, text_color=self._t().text_dim, corner_radius=4, command=lambda: self._copy_to_clipboard(self._identity.void_id)).pack(side="right")

        # Chat area
        self._chat_area = ctk.CTkFrame(self._main, fg_color=self._t().bg, corner_radius=0)
        self._chat_area.pack(side="right", fill="both", expand=True)
        self._show_empty_state()
        self._render_contacts()

        # Keybinds
        self._window.bind("<Escape>", lambda _: self._search_entry.delete(0, "end"))
        self._window.bind("<Control-comma>", lambda _: self._toggle_settings())
        self._window.bind("<Control-f>", lambda _: self._open_search())
        self._window.bind("<Control-F>", lambda _: self._open_search())

    def _toggle_settings(self):
        if self._settings_open:
            return
        self._settings_open = True
        dialog = ctk.CTkToplevel(self._window)
        dialog.title("Settings")
        dialog.geometry("420x620")
        dialog.configure(fg_color=self._t().bg)
        dialog.transient(self._window)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_settings(dialog))

        ctk.CTkLabel(dialog, text="SETTINGS", font=ctk.CTkFont(family="Consolas", size=16, weight="bold"), text_color=self._t().accent).pack(pady=(20, 16))

        # Theme
        ctk.CTkLabel(dialog, text="THEME", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w", padx=24)
        theme_var = ctk.StringVar(value=self._profile.theme)
        theme_menu = ctk.CTkOptionMenu(dialog, values=list(THEMES.keys()), variable=theme_var, width=340, height=34, fg_color=self._t().input_bg, button_color=self._t().surface, button_hover_color=self._t().border, dropdown_fg_color=self._t().surface, dropdown_hover_color=self._t().border, text_color=self._t().text, font=ctk.CTkFont(size=12), command=lambda v: self._change_theme(v))
        theme_menu.pack(padx=24, pady=(4, 14))

        # Display name
        ctk.CTkLabel(dialog, text="DISPLAY NAME", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w", padx=24)
        name_entry = ctk.CTkEntry(dialog, width=340, height=34, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text, corner_radius=6, font=ctk.CTkFont(size=12))
        name_entry.pack(padx=24, pady=(4, 14))
        name_entry.insert(0, self._profile.display_name)

        # Profile image
        ctk.CTkLabel(dialog, text="PROFILE IMAGE", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w", padx=24)
        img_row = ctk.CTkFrame(dialog, fg_color="transparent")
        img_row.pack(fill="x", padx=24, pady=(4, 14))

        avatar_preview = load_avatar(self._profile.avatar_path, 48)
        if avatar_preview:
            av_label = ctk.CTkLabel(img_row, text="", image=avatar_preview, width=48, height=48, cursor="hand2")
        else:
            av_label = ctk.CTkLabel(img_row, text="No image", font=ctk.CTkFont(size=10), text_color=self._t().text_dim, width=48, height=48)
        av_label.pack(side="left")

        ctk.CTkButton(img_row, text="Change", width=90, height=30, fg_color=self._t().surface, hover_color=self._t().border, text_color=self._t().text, corner_radius=4, font=ctk.CTkFont(size=11), command=lambda: self._pick_avatar_settings(av_label)).pack(side="left", padx=(12, 0))
        ctk.CTkButton(img_row, text="Remove", width=70, height=30, fg_color=self._t().surface, hover_color=self._t().border, text_color=self._t().danger, corner_radius=4, font=ctk.CTkFont(size=11), command=lambda: self._remove_avatar(av_label)).pack(side="left", padx=(8, 0))

        # Font size
        ctk.CTkLabel(dialog, text="FONT SIZE", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w", padx=24)
        font_var = ctk.IntVar(value=self._profile.font_size)
        font_slider = ctk.CTkSlider(dialog, from_=9, to=16, number_of_steps=7, variable=font_var, width=340, fg_color=self._t().input_bg, progress_color=self._t().accent, button_color=self._t().accent, button_hover_color=self._t().accent_hover)
        font_slider.pack(padx=24, pady=(4, 14))

        # Auto delete
        ctk.CTkLabel(dialog, text="AUTO-DELETE MESSAGES", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w", padx=24)
        del_var = ctk.StringVar(value=self._profile.auto_delete)
        ctk.CTkOptionMenu(dialog, values=["off", "24 hours", "3 days", "1 week"], variable=del_var, width=340, height=34, fg_color=self._t().input_bg, button_color=self._t().surface, button_hover_color=self._t().border, dropdown_fg_color=self._t().surface, dropdown_hover_color=self._t().border, text_color=self._t().text, font=ctk.CTkFont(size=12)).pack(padx=24, pady=(4, 14))

        # Privacy toggles
        ctk.CTkLabel(dialog, text="PRIVACY", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w", padx=24)
        toggles_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        toggles_frame.pack(fill="x", padx=24, pady=(4, 14))

        read_var = ctk.BooleanVar(value=self._profile.read_receipts)
        ctk.CTkSwitch(toggles_frame, text="Read receipts", variable=read_var, font=ctk.CTkFont(size=11), text_color=self._t().text, fg_color=self._t().input_bg, progress_color=self._t().accent, button_color=self._t().accent).pack(anchor="w", pady=(0, 6))

        seen_var = ctk.BooleanVar(value=self._profile.show_seen)
        ctk.CTkSwitch(toggles_frame, text="Show 'seen' status", variable=seen_var, font=ctk.CTkFont(size=11), text_color=self._t().text, fg_color=self._t().input_bg, progress_color=self._t().accent, button_color=self._t().accent).pack(anchor="w", pady=(0, 6))

        link_var = ctk.BooleanVar(value=self._profile.link_preview)
        ctk.CTkSwitch(toggles_frame, text="Link previews", variable=link_var, font=ctk.CTkFont(size=11), text_color=self._t().text, fg_color=self._t().input_bg, progress_color=self._t().accent, button_color=self._t().accent).pack(anchor="w")

        # Save button
        def save():
            new_name = name_entry.get().strip()[:15]
            if new_name:
                self._profile.display_name = new_name
            self._profile.font_size = font_var.get()
            self._profile.auto_delete = del_var.get()
            self._profile.read_receipts = read_var.get()
            self._profile.show_seen = seen_var.get()
            self._profile.link_preview = link_var.get()
            self._close_settings(dialog)
            self._rebuild()

        ctk.CTkButton(dialog, text="Save", width=340, height=38, fg_color=self._t().accent, text_color="#000", hover_color=self._t().accent_hover, corner_radius=8, font=ctk.CTkFont(size=13, weight="bold"), command=save).pack(padx=24, pady=(4, 0))

        # Footer
        footer = ctk.CTkFrame(dialog, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(14, 10))
        ctk.CTkLabel(footer, text=f"v{CURRENT_VERSION}", font=ctk.CTkFont(family="Consolas", size=9), text_color=self._t().text_dim).pack(side="left")
        ctk.CTkButton(footer, text="Source Code", width=80, height=22, font=ctk.CTkFont(size=9), fg_color="transparent", hover_color=self._t().border, text_color=self._t().accent, corner_radius=4, command=self._open_source).pack(side="right")

    def _close_settings(self, dialog):
        self._settings_open = False
        dialog.destroy()

    def _change_theme(self, name: str):
        self._profile.theme = name
        self._theme = THEMES.get(name, THEMES[DEFAULT_THEME])
        self._apply_theme()

    def _change_pfp(self):
        path = filedialog.askopenfilename(
            title="Choose profile picture",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.webp")]
        )
        if not path:
            return
        os.makedirs(AVATARS_DIR, exist_ok=True)
        ext = os.path.splitext(path)[1]
        dest = os.path.join(AVATARS_DIR, f"me{ext}")
        shutil.copy2(path, dest)
        self._profile.avatar_path = dest
        self._rebuild()

    def _pick_avatar(self, label):
        path = filedialog.askopenfilename(title="Choose image", filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.webp")])
        if not path:
            return
        os.makedirs(AVATARS_DIR, exist_ok=True)
        dest = os.path.join(AVATARS_DIR, f"me{os.path.splitext(path)[1]}")
        shutil.copy2(path, dest)
        self._profile.avatar_path = dest
        label.configure(text=os.path.basename(dest))

    def _rebuild(self):
        for w in self._window.winfo_children():
            w.destroy()
        self._apply_theme()
        self._build_main()

    def _pick_avatar_settings(self, label):
        path = filedialog.askopenfilename(title="Choose image", filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.webp")])
        if not path:
            return
        os.makedirs(AVATARS_DIR, exist_ok=True)
        dest = os.path.join(AVATARS_DIR, f"me{os.path.splitext(path)[1]}")
        shutil.copy2(path, dest)
        self._profile.avatar_path = dest
        new_img = load_avatar(dest, 48)
        if new_img:
            label.configure(image=new_img, text="")

    def _remove_avatar(self, label):
        if self._profile.avatar_path and os.path.exists(self._profile.avatar_path):
            os.remove(self._profile.avatar_path)
        self._profile.avatar_path = ""
        guest_img = load_avatar("", 48)
        if guest_img:
            label.configure(image=guest_img, text="")
        else:
            label.configure(image=None, text="No image")

    def _show_empty_state(self):
        for w in self._chat_area.winfo_children():
            w.destroy()
        header = ctk.CTkFrame(self._chat_area, fg_color=self._t().surface, height=54, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="   No conversation selected", font=ctk.CTkFont(size=12), text_color=self._t().text_dim).pack(side="left", padx=16, pady=14)

        center = ctk.CTkFrame(self._chat_area, fg_color="transparent")
        center.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(center, fg_color="transparent")
        inner.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(inner, text="cespo", font=ctk.CTkFont(family="Consolas", size=32, weight="bold"), text_color=self._t().accent).pack()
        ctk.CTkLabel(inner, text="end-to-end encrypted messaging", font=ctk.CTkFont(size=11), text_color=self._t().text_dim).pack(pady=(6, 16))
        ctk.CTkLabel(inner, text="select a conversation from the left\nor add a contact to get started", font=ctk.CTkFont(size=10), text_color=self._t().text_dim, justify="center").pack()

        bar = ctk.CTkFrame(self._chat_area, fg_color=self._t().surface, height=56, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        bi = ctk.CTkFrame(bar, fg_color="transparent")
        bi.pack(fill="x", padx=12, pady=10)
        ctk.CTkEntry(bi, height=36, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text_dim, corner_radius=6, font=ctk.CTkFont(size=12), placeholder_text="message...", state="disabled").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(bi, text="⬆", width=36, height=36, font=ctk.CTkFont(size=14), fg_color=self._t().input_bg, text_color=self._t().text_dim, corner_radius=6, state="disabled", hover=False).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bi, text="Send", width=70, height=36, fg_color=self._t().input_bg, text_color=self._t().text_dim, corner_radius=6, font=ctk.CTkFont(size=12), state="disabled", hover=False).pack(side="right")

    def _render_contacts(self):
        for w in self._contact_list.winfo_children():
            w.destroy()
        all_contacts = self._contacts.get_all()
        pinned = self._profile.pinned_contacts

        # Show pinned first
        pinned_shown = False
        for vid in pinned:
            if vid in all_contacts:
                if not pinned_shown:
                    ctk.CTkLabel(self._contact_list, text="PINNED", font=ctk.CTkFont(family="Consolas", size=8), text_color=self._t().text_dim).pack(anchor="w", padx=8, pady=(4, 2))
                    pinned_shown = True
                self._make_contact_row(all_contacts[vid], is_pinned=True)

        # Show rest
        for vid, contact in all_contacts.items():
            if vid not in pinned:
                self._make_contact_row(contact, is_pinned=False)

    def _on_search(self):
        query = self._search_entry.get().strip().lower()
        for w in self._contact_list.winfo_children():
            w.destroy()
        for vid, contact in self._contacts.get_all().items():
            if not query or query in contact.display_name.lower() or query in contact.void_id:
                self._make_contact_row(contact, is_pinned=(vid in self._profile.pinned_contacts))

    def _on_search_enter(self):
        query = self._search_entry.get().strip().lower()
        if len(query) == 16 and query.isalnum():
            if not self._contacts.exists(query):
                self._add_contact_with_id(query)
            else:
                contact = self._contacts.get(query)
                if contact:
                    self._open_chat(contact)

    def _make_contact_row(self, contact: Contact, is_pinned: bool = False):
        row = ctk.CTkFrame(self._contact_list, fg_color="transparent", cursor="hand2")
        row.pack(fill="x", pady=(0, 2))

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=6)

        av = load_avatar("", 28)
        if av:
            ctk.CTkLabel(inner, text="", image=av, width=28, height=28).pack(side="left", padx=(0, 8))

        text_frame = ctk.CTkFrame(inner, fg_color="transparent")
        text_frame.pack(side="left", fill="x", expand=True)
        name_text = f"📌 {contact.display_name}" if is_pinned else contact.display_name
        ctk.CTkLabel(text_frame, text=name_text, font=ctk.CTkFont(size=12, weight="bold"), text_color=self._t().text, anchor="w").pack(anchor="w")
        ctk.CTkLabel(text_frame, text=contact.void_id, font=ctk.CTkFont(family="Consolas", size=8), text_color=self._t().text_dim, anchor="w").pack(anchor="w")

        def show_context(event):
            menu = ctk.CTkToplevel(self._window)
            menu.geometry(f"120x70+{event.x_root}+{event.y_root}")
            menu.overrideredirect(True)
            menu.configure(fg_color=self._t().surface)
            menu.attributes("-topmost", True)
            if is_pinned:
                ctk.CTkButton(menu, text="Unpin", height=28, fg_color="transparent", hover_color=self._t().border, text_color=self._t().text, font=ctk.CTkFont(size=11), anchor="w", command=lambda: [self._unpin_contact(contact), menu.destroy()]).pack(fill="x", padx=4, pady=(4, 0))
            else:
                ctk.CTkButton(menu, text="Pin", height=28, fg_color="transparent", hover_color=self._t().border, text_color=self._t().text, font=ctk.CTkFont(size=11), anchor="w", command=lambda: [self._pin_contact(contact), menu.destroy()]).pack(fill="x", padx=4, pady=(4, 0))
            ctk.CTkButton(menu, text="Remove", height=28, fg_color="transparent", hover_color=self._t().border, text_color=self._t().danger, font=ctk.CTkFont(size=11), anchor="w", command=lambda: [self._delete_contact(contact), menu.destroy()]).pack(fill="x", padx=4, pady=(0, 4))
            menu.bind("<FocusOut>", lambda _: menu.destroy())
            menu.focus_set()

        for widget in [row, inner, text_frame] + text_frame.winfo_children() + inner.winfo_children():
            widget.bind("<Button-1>", lambda _, c=contact: self._open_chat(c))
            widget.bind("<Button-3>", show_context)
            widget.bind("<Enter>", lambda _, r=row: r.configure(fg_color=self._t().surface))
            widget.bind("<Leave>", lambda _, r=row: r.configure(fg_color="transparent"))

    def _add_contact_dialog(self):
        dialog = ctk.CTkToplevel(self._window)
        dialog.title("Add Contact")
        dialog.geometry("360x220")
        dialog.configure(fg_color=self._t().bg)
        dialog.transient(self._window)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="CESPO ID", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w", padx=20, pady=(20, 4))
        id_entry = ctk.CTkEntry(dialog, width=320, height=36, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text, corner_radius=6, font=ctk.CTkFont(family="Consolas", size=13), placeholder_text="16-character ID")
        id_entry.pack(padx=20)
        ctk.CTkLabel(dialog, text="NAME", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(anchor="w", padx=20, pady=(12, 4))
        name_entry = ctk.CTkEntry(dialog, width=320, height=36, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text, corner_radius=6, font=ctk.CTkFont(size=13), placeholder_text="display name")
        name_entry.pack(padx=20)

        def do_add():
            vid = id_entry.get().strip().lower()
            name = name_entry.get().strip()[:15]
            if len(vid) != 16:
                messagebox.showerror("Error", "ID must be 16 characters.", parent=dialog)
                return
            if not name:
                messagebox.showerror("Error", "Enter a name.", parent=dialog)
                return
            if vid == self._identity.void_id:
                messagebox.showerror("Error", "You cannot add yourself.", parent=dialog)
                return
            if self._contacts.exists(vid):
                messagebox.showinfo("Info", "Contact already exists.", parent=dialog)
                dialog.destroy()
                return
            self._contacts.add(Contact(void_id=vid, display_name=name, signing_pub_b64="", agreement_pub_b64=""))
            self._render_contacts()
            dialog.destroy()

        id_entry.focus()
        ctk.CTkButton(dialog, text="Add Contact", width=320, height=38, fg_color=self._t().accent, text_color="#000", hover_color=self._t().accent_hover, corner_radius=6, font=ctk.CTkFont(size=13, weight="bold"), command=do_add).pack(padx=20, pady=(16, 0))
        id_entry.bind("<Return>", lambda _: name_entry.focus())
        name_entry.bind("<Return>", lambda _: do_add())

    def _add_contact_with_id(self, void_id: str):
        dialog = ctk.CTkToplevel(self._window)
        dialog.title("New Contact")
        dialog.geometry("320x140")
        dialog.configure(fg_color=self._t().bg)
        dialog.transient(self._window)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text=f"Adding {void_id}", font=ctk.CTkFont(family="Consolas", size=10), text_color=self._t().text_dim).pack(padx=20, pady=(16, 8))
        name_entry = ctk.CTkEntry(dialog, width=280, height=34, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text, corner_radius=6, font=ctk.CTkFont(size=12), placeholder_text="display name")
        name_entry.pack(padx=20)
        name_entry.focus()

        def do_add(event=None):
            name = name_entry.get().strip()[:15]
            if not name:
                return
            self._contacts.add(Contact(void_id=void_id, display_name=name, signing_pub_b64="", agreement_pub_b64=""))
            self._render_contacts()
            self._search_entry.delete(0, "end")
            dialog.destroy()

        name_entry.bind("<Return>", do_add)
        ctk.CTkButton(dialog, text="Add", width=280, height=34, fg_color=self._t().accent, text_color="#000", hover_color=self._t().accent_hover, corner_radius=6, font=ctk.CTkFont(size=12, weight="bold"), command=do_add).pack(padx=20, pady=(10, 0))

    def _open_chat(self, contact: Contact):
        self._active_chat = contact.void_id
        for w in self._chat_area.winfo_children():
            w.destroy()

        header = ctk.CTkFrame(self._chat_area, fg_color=self._t().surface, height=54, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        hi = ctk.CTkFrame(header, fg_color="transparent")
        hi.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(hi, text=contact.display_name, font=ctk.CTkFont(size=14, weight="bold"), text_color=self._t().text).pack(side="left")
        ctk.CTkLabel(hi, text=contact.void_id, font=ctk.CTkFont(family="Consolas", size=9), text_color=self._t().text_dim).pack(side="left", padx=(10, 0))
        ctk.CTkButton(hi, text="✕", width=28, height=28, font=ctk.CTkFont(size=12), fg_color="transparent", hover_color=self._t().border, text_color=self._t().text_dim, corner_radius=14, command=lambda c=contact: self._delete_contact(c)).pack(side="right")
        ctk.CTkButton(hi, text="🗑", width=28, height=28, font=ctk.CTkFont(size=11), fg_color="transparent", hover_color=self._t().border, text_color=self._t().text_dim, corner_radius=14, command=lambda c=contact: self._clear_chat_history(c)).pack(side="right", padx=(0, 4))

        self._msg_display = ctk.CTkTextbox(self._chat_area, fg_color=self._t().bg, text_color=self._t().text, font=ctk.CTkFont(family="Consolas", size=self._profile.font_size), corner_radius=0, state="disabled", wrap="word", border_width=0)
        self._msg_display.pack(fill="both", expand=True)
        self._msg_display._textbox.tag_config("sent", foreground=self._t().accent)
        self._msg_display._textbox.tag_config("recv", foreground=self._t().incoming)
        self._msg_display._textbox.tag_config("info", foreground=self._t().text_dim)

        bar = ctk.CTkFrame(self._chat_area, fg_color=self._t().surface, height=56, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        bi = ctk.CTkFrame(bar, fg_color="transparent")
        bi.pack(fill="x", padx=12, pady=10)
        self._msg_entry = ctk.CTkEntry(bi, height=36, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text, corner_radius=6, font=ctk.CTkFont(size=12), placeholder_text="message...")
        self._msg_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._msg_entry.bind("<Return>", lambda _: self._send_message())
        ctk.CTkButton(bi, text="File", width=50, height=36, font=ctk.CTkFont(size=11), fg_color=self._t().input_bg, hover_color=self._t().border, text_color=self._t().text_dim, corner_radius=6, command=self._send_file).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bi, text="Send", width=70, height=36, fg_color=self._t().accent, text_color="#000", hover_color=self._t().accent_hover, corner_radius=6, font=ctk.CTkFont(size=12, weight="bold"), command=self._send_message).pack(side="right")

        self._msg_entry.focus()
        self._load_chat_history(contact)

    def _load_chat_history(self, contact: Contact):
        store = self._get_msg_store(contact.void_id)
        if not store:
            self._chat_print(f"  start of conversation with {contact.display_name}", "info")
            self._chat_print(f"  messages are end-to-end encrypted", "info")
            self._chat_print("", "info")
            return
        messages = store.load()
        if not messages:
            self._chat_print(f"  start of conversation with {contact.display_name}", "info")
            self._chat_print(f"  messages are end-to-end encrypted", "info")
            self._chat_print("", "info")
            return
        for msg in messages:
            ts = time.strftime("%H:%M", time.localtime(msg["ts"]))
            sender = msg.get("from", "")
            text = msg.get("text", "")
            if sender == self._identity.void_id:
                self._chat_print(f"  {ts}  you  {text}", "sent")
            else:
                self._chat_print(f"  {ts}  {contact.display_name}  {text}", "recv")

    def _delete_contact(self, contact: Contact):
        confirm = messagebox.askyesno("Remove Contact", f"Remove {contact.display_name} from contacts?")
        if confirm:
            self._contacts.remove(contact.void_id)
            self._active_chat = None
            self._render_contacts()
            self._show_empty_state()

    def _clear_chat_history(self, contact: Contact):
        confirm = messagebox.askyesno("Clear History", f"Delete all messages with {contact.display_name}?")
        if confirm:
            store = self._get_msg_store(contact.void_id)
            if store:
                store.clear()
            self._open_chat(contact)

    def _open_search(self):
        if not hasattr(self, '_msg_display') or not self._active_chat:
            return
        dialog = ctk.CTkToplevel(self._window)
        dialog.title("Search Messages")
        dialog.geometry("360x80")
        dialog.configure(fg_color=self._t().bg)
        dialog.transient(self._window)
        dialog.attributes("-topmost", True)

        sf = ctk.CTkFrame(dialog, fg_color="transparent")
        sf.pack(fill="x", padx=16, pady=16)
        search_input = ctk.CTkEntry(sf, height=34, fg_color=self._t().input_bg, border_color=self._t().border, text_color=self._t().text, corner_radius=6, font=ctk.CTkFont(size=12), placeholder_text="Find in conversation...")
        search_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        search_input.focus()

        def do_search(event=None):
            query = search_input.get().strip().lower()
            if not query:
                return
            self._msg_display._textbox.tag_remove("sel", "1.0", "end")
            content = self._msg_display._textbox.get("1.0", "end").lower()
            idx = content.find(query)
            if idx >= 0:
                line = content[:idx].count("\n") + 1
                col = idx - content[:idx].rfind("\n") - 1
                start = f"{line}.{col}"
                end = f"{line}.{col + len(query)}"
                self._msg_display._textbox.tag_add("sel", start, end)
                self._msg_display._textbox.see(start)

        search_input.bind("<Return>", do_search)
        ctk.CTkButton(sf, text="Find", width=60, height=34, fg_color=self._t().accent, text_color="#000", hover_color=self._t().accent_hover, corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), command=do_search).pack(side="right")
        dialog.bind("<Escape>", lambda _: dialog.destroy())

    def _pin_contact(self, contact: Contact):
        pinned = self._profile.pinned_contacts
        if contact.void_id not in pinned:
            pinned.insert(0, contact.void_id)
            self._profile.pinned_contacts = pinned
            self._render_contacts()

    def _unpin_contact(self, contact: Contact):
        pinned = self._profile.pinned_contacts
        if contact.void_id in pinned:
            pinned.remove(contact.void_id)
            self._profile.pinned_contacts = pinned
            self._render_contacts()

    def _get_msg_store(self, contact_id: str) -> Optional[MessageStore]:
        if contact_id not in self._conv_keys:
            contact = self._contacts.get(contact_id)
            if not contact or not contact.agreement_pub_b64:
                return None
            try:
                their_pub = base64.b64decode(contact.agreement_pub_b64)
                shared = self._identity.compute_shared_secret(their_pub)
                self._conv_keys[contact_id] = derive_conversation_key(shared, self._identity.void_id, contact_id)
            except Exception:
                return None
        if contact_id not in self._msg_stores:
            self._msg_stores[contact_id] = MessageStore(os.path.join(DATA_DIR, "messages"), self._conv_keys[contact_id], contact_id)
        return self._msg_stores[contact_id]

    def _chat_print(self, text: str, tag: str = "info"):
        self._msg_display.configure(state="normal")
        self._msg_display._textbox.insert("end", text + "\n", tag)
        self._msg_display._textbox.see("end")
        self._msg_display.configure(state="disabled")

    def _send_message(self):
        if not self._active_chat:
            return
        text = self._msg_entry.get().strip()
        if not text:
            return
        self._msg_entry.delete(0, "end")
        contact = self._contacts.get(self._active_chat)
        if not contact:
            return
        ts = time.strftime("%H:%M")
        self._chat_print(f"  {ts}  you  {text}", "sent")
        if self._active_chat in self._conv_keys:
            store = self._get_msg_store(self._active_chat)
            if store:
                store.append(self._identity.void_id, text)
        if self._relay.connected:
            try:
                seq = self._seq_tracker.next_outgoing(self._active_chat)
                msg_data = json.dumps({"type": "dm", "from": self._identity.void_id, "text": text, "nick": self._profile.display_name, "pub_bundle": self._identity.pub_bundle_b64, "seq": seq}).encode()
                sig = base64.b64encode(self._identity.sign(msg_data)).decode()
                signed = json.dumps({"payload": msg_data.decode(), "sig": sig}).encode()
                if self._active_chat in self._conv_keys:
                    encrypted = encrypt(self._conv_keys[self._active_chat], signed)
                    self._relay.send_to(self._active_chat, encrypted)
                else:
                    self._relay.send_to(self._active_chat, signed)
            except Exception as e:
                self._chat_print(f"  send failed: {e}", "info")

    def _send_file(self):
        if not self._active_chat or not self._relay.connected:
            return
        path = filedialog.askopenfilename(title="Select file")
        if not path:
            return
        name = os.path.basename(path)
        size = os.path.getsize(path)
        self._chat_print(f"  ↑ {name} ({size} bytes)", "info")

    def _connect_relay(self):
        def task():
            try:
                self._relay.connect(self._identity.void_id, self._on_relay_message)
                self._window.after(0, lambda: self._status_dot.configure(text_color=self._t().accent))
            except Exception:
                self._window.after(0, lambda: self._status_dot.configure(text_color=self._t().danger))
        threading.Thread(target=task, daemon=True).start()

    def _on_relay_message(self, raw: bytes):
        try:
            sender_id_len = struct.unpack(">H", raw[:2])[0]
            sender_id = raw[2:2 + sender_id_len].decode()
            payload = raw[2 + sender_id_len:]
            contact = self._contacts.get(sender_id)

            # Decrypt if we have a conversation key
            if contact and contact.agreement_pub_b64 and sender_id in self._conv_keys:
                try:
                    payload = decrypt(self._conv_keys[sender_id], payload)
                except CipherError:
                    pass

            # Parse outer envelope (signed wrapper)
            try:
                envelope = json.loads(payload.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                return

            # Handle new contact (first message, no signature yet)
            if not contact:
                msg = envelope if "type" in envelope else json.loads(envelope.get("payload", "{}"))
                nick = msg.get("nick", sender_id[:8])
                pub_bundle = msg.get("pub_bundle", "")
                signing_pub = ""
                agreement_pub = ""
                if pub_bundle:
                    bundle = base64.b64decode(pub_bundle)
                    signing_pub = base64.b64encode(bundle[:32]).decode()
                    agreement_pub = base64.b64encode(bundle[32:64]).decode()
                contact = Contact(void_id=sender_id, display_name=nick, signing_pub_b64=signing_pub, agreement_pub_b64=agreement_pub)
                self._contacts.add(contact)
                self._window.after(0, self._render_contacts)

                if not contact.agreement_pub_b64 and pub_bundle:
                    bundle = base64.b64decode(pub_bundle)
                    their_pub = bundle[32:64]
                    shared = self._identity.compute_shared_secret(their_pub)
                    self._conv_keys[sender_id] = derive_conversation_key(shared, self._identity.void_id, sender_id)

            # Verify signature (enforce: drop unsigned messages from known contacts)
            if "sig" in envelope and "payload" in envelope:
                sig = base64.b64decode(envelope["sig"])
                payload_bytes = envelope["payload"].encode()
                if contact.signing_pub_b64:
                    signing_pub = base64.b64decode(contact.signing_pub_b64)
                    from src.crypto.identity import Identity as IdCheck
                    if not IdCheck.verify_signature(signing_pub, sig, payload_bytes):
                        return  # signature invalid, drop
                msg = json.loads(envelope["payload"])
            elif contact.signing_pub_b64:
                return  # known contact sent unsigned message, drop
            else:
                msg = envelope

            # Establish key agreement if needed
            if msg.get("pub_bundle") and not contact.agreement_pub_b64:
                bundle = base64.b64decode(msg["pub_bundle"])
                contact.signing_pub_b64 = base64.b64encode(bundle[:32]).decode()
                contact.agreement_pub_b64 = base64.b64encode(bundle[32:64]).decode()
                self._contacts.add(contact)
                their_pub = bundle[32:64]
                shared = self._identity.compute_shared_secret(their_pub)
                self._conv_keys[sender_id] = derive_conversation_key(shared, self._identity.void_id, sender_id)

            # Validate sequence number (replay protection)
            seq = msg.get("seq")
            if seq is not None:
                if not self._seq_tracker.validate_incoming(sender_id, seq):
                    return  # replay detected, drop

            text = msg.get("text", "")
            if not text:
                return

            store = self._get_msg_store(sender_id)
            if store:
                store.append(sender_id, text)
            if self._active_chat == sender_id:
                ts = time.strftime("%H:%M")
                self._window.after(0, lambda t=text, n=contact.display_name, s=ts: self._chat_print(f"  {s}  {n}  {t}", "recv"))
        except Exception:
            pass

    def run(self):
        self._window.mainloop()
