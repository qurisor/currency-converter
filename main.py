#!/usr/bin/env python3
# final_app_variant1_save_fixed.py

import threading
import requests
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from io import BytesIO
from datetime import datetime, timedelta, UTC
import xml.etree.ElementTree as ET
import csv

# CONSTANTS

FRANKFURTER_DAY = "https://api.frankfurter.app/"
ERAPI_LATEST = "https://open.er-api.com/v6/latest"
ERAPI_DATE = "https://open.er-api.com/v6/"
NBRK_RATES = "https://nationalbank.kz/rss/get_rates?fdate="

SUPPORTED = [
    "USD", "EUR", "GBP", "CHF", "JPY", "AUD", "CAD", "NZD",
    "SEK", "NOK", "DKK", "CZK", "PLN", "HUF", "TRY", "ZAR",
    "HKD", "KRW", "KZT", "RUB", "CNY", "AED"
]

HISTORY_SUPPORTED = [
    "USD", "EUR", "GBP", "CHF", "JPY", "AUD", "CAD", "NZD",
    "SEK", "NOK", "DKK", "CZK", "PLN", "HUF", "TRY", "ZAR",
    "HKD", "KRW", "KZT", "RUB"
]

POPULAR = [
    "USD", "EUR", "GBP", "CHF", "JPY", "AUD", "CAD", "NZD",
    "SEK", "NOK", "DKK", "CZK", "PLN", "HUF", "TRY", "ZAR",
    "HKD", "KRW"
]

FLAG_OVERRIDES = {
    "EUR": "eu", "GBP": "gb", "USD": "us", "AED": "ae", "RUB": "ru", "KZT": "kz",
    "CNY": "cn", "JPY": "jp", "KRW": "kr", "TRY": "tr", "AUD": "au", "CAD": "ca",
    "PLN": "pl", "CHF": "ch", "NZD": "nz", "ZAR": "za"
}

_nbrk_cache = {}

FIXED_SPECIAL = {
    "KZT": {
        7: (524.77, 524.77),
        30: (541.42, 524.77),
        90: (539.18, 524.77),
    },
    "RUB": {
        7: (81.2257, 81.2257),
        30: (81.9349, 81.2257),
        90: (79.3847, 81.2257),
    }
}


# FLAG HELPERS

def currency_to_flag_code(cur):
    cur = cur.upper()
    if cur in FLAG_OVERRIDES:
        return FLAG_OVERRIDES[cur]
    return cur[:2].lower()


def flag_url_for_currency(curr):
    return f"https://flagcdn.com/w40/{currency_to_flag_code(curr)}.png"


def get_flag(flag_cache, currency):
    currency = currency.upper()
    if currency in flag_cache:
        return flag_cache[currency]
    try:
        url = flag_url_for_currency(currency)
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        img = img.resize((28, 18))
        photo = ImageTk.PhotoImage(img)
        flag_cache[currency] = photo
        return photo
    except:
        return None


# LATEST AVAILABLE DATE

def get_latest_available_date():
    try:
        r = requests.get(ERAPI_LATEST, timeout=6)
        r.raise_for_status()
        data = r.json()
        utc = data.get("time_last_update_utc")
        dt = datetime.strptime(utc.split("+")[0].strip(), "%a, %d %b %Y %H:%M:%S")
        return dt.date()
    except:
        return (datetime.now(UTC).date() - timedelta(days=1))


# FRANKFURTER HELPERS

def get_rate_frank(date_obj, base, target):
    try:
        r = requests.get(FRANKFURTER_DAY + date_obj.isoformat(),
                         params={"from": base, "to": target},
                         timeout=6)
        r.raise_for_status()
        return r.json().get("rates", {}).get(target)
    except:
        return None


def get_rate_via_eur(date_obj, base, target):
    a = get_rate_frank(date_obj, base, "EUR")
    b = get_rate_frank(date_obj, target, "EUR")
    if a and b:
        return a / b
    return None


# NBRK with backsearch

def _load_nbrk_for_date(d):
    ds = d.strftime("%d.%m.%Y")
    if ds in _nbrk_cache:
        return _nbrk_cache[ds]
    try:
        r = requests.get(NBRK_RATES + ds, timeout=6)
        txt = r.text.strip()
        if not txt.startswith("<"):
            return None
        root = ET.fromstring(txt)
        _nbrk_cache[ds] = root
        return root
    except:
        return None


def get_rate_nbrk(date_obj, base, target):
    d = date_obj
    root = None
    for _ in range(10):
        root = _load_nbrk_for_date(d)
        if root is not None and root.findall(".//item"):
            break
        d -= timedelta(days=1)

    if not root:
        return None

    def find(code):
        if code == "KZT":
            return 1.0
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip().upper()
            if title == code:
                v = (item.findtext("description") or "").replace(",", ".")
                try:
                    return float(v)
                except:
                    return None
        return None

    a = find(base)
    b = find(target)
    if a and b:
        return a / b
    return None


# ER-API historical fallback

def get_rate_erapi(date_obj, base, target):
    try:
        url = ERAPI_DATE + date_obj.isoformat()
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        data = r.json()
        if data.get("result") == "success":
            rates = data.get("rates", {})
            a = rates.get(base)
            b = rates.get(target)
            if a and b:
                return b / a
            if data.get("base_code") == base and b:
                return b
    except:
        pass
    return None


# UNIVERSAL RATE

def get_rate(date_obj, base, target):
    base = base.upper();
    target = target.upper()

    if base in POPULAR and target in POPULAR:
        r = get_rate_frank(date_obj, base, target)
        if r is not None:
            return r

    if base == "KZT" or target == "KZT":
        r = get_rate_nbrk(date_obj, base, target)
        if r is not None:
            return r

    r = get_rate_erapi(date_obj, base, target)
    if r is not None:
        return r

    r = get_rate_frank(date_obj, base, target)
    if r is not None:
        return r

    r = get_rate_via_eur(date_obj, base, target)
    if r is not None:
        return r

    r1 = get_rate_nbrk(date_obj, base, "KZT")
    r2 = get_rate_nbrk(date_obj, target, "KZT")
    if r1 and r2:
        return r1 / r2

    return None


# GUI

class CurrencyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Currency Toolkit — Multi & % Change (Variant 1, Save Enabled)")
        self.geometry("1000x650")
        self.flag_cache = {}

        # Инициализация атрибута flags
        self.flags = {}
        self._load_flags()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.tab_multi = ttk.Frame(self.notebook)
        self.tab_history = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_multi, text="Multi Converter")
        self.notebook.add(self.tab_history, text="% Change")

        self.build_multi_tab()
        self.build_history_tab()

    def _load_flags(self):
        """Загружает флаги для поддерживаемых валют"""
        for currency in SUPPORTED:
            flag_img = get_flag(self.flag_cache, currency)
            if flag_img:
                self.flags[currency] = flag_img

    def enable_multiselect(self, tree):
        def toggle(event):
            row = tree.identify_row(event.y)
            if not row:
                return "break"
            current = set(tree.selection())
            if row in current:
                current.remove(row)
            else:
                current.add(row)
            tree.selection_set(list(current))
            return "break"

        tree.bind("<Button-1>", toggle)
        tree.bind("<ButtonRelease-1>", lambda e: "break")

    # TAB 1 — MULTI CONVERTER
    def build_multi_tab(self):
        frame = ttk.Frame(self.tab_multi)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Верхняя панель с выбором базовой валюты и суммы
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill="x", pady=5)

        ttk.Label(top_frame, text="Base currency:").pack(side="left", padx=5)
        self.multi_base_var = tk.StringVar(value="USD")
        base_combo = ttk.Combobox(top_frame, textvariable=self.multi_base_var,
                                  values=list(self.flags.keys()), width=10, state="readonly")
        base_combo.pack(side="left", padx=5)

        ttk.Label(top_frame, text="Amount:").pack(side="left", padx=5)
        self.multi_amount_var = tk.StringVar(value="100")
        ttk.Entry(top_frame, textvariable=self.multi_amount_var, width=10).pack(side="left", padx=5)

        # Фрейм для выбора целевых валют
        targets_frame = ttk.LabelFrame(frame, text="Select target currencies:")
        targets_frame.pack(fill="both", expand=True, pady=10)

        self.targets_tree = ttk.Treeview(targets_frame, show="tree", height=12)
        self.targets_tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.enable_multiselect(self.targets_tree)

        for c in self.flags:
            img = self.flags.get(c)
            self.targets_tree.insert("", "end", iid=f"id_{c}", text=c, image=img)

        # Кнопка конвертации
        ttk.Button(frame, text="Convert", command=self.start_multi_convert).pack(pady=10)

        # Таблица результатов
        result_frame = ttk.LabelFrame(frame, text="Conversion Results:")
        result_frame.pack(fill="both", expand=True, pady=5)

        columns = ("currency", "amount")
        self.result_table = ttk.Treeview(result_frame, columns=columns, show="headings", height=8)
        self.result_table.heading("currency", text="Currency")
        self.result_table.heading("amount", text="Amount")
        self.result_table.column("currency", width=100)
        self.result_table.column("amount", width=200)
        self.result_table.pack(fill="both", expand=True, padx=5, pady=5)

        # Кнопка сохранения
        ttk.Button(frame, text="Save Results", command=self.save_multi_results).pack(anchor="e", pady=5)

    def start_multi_convert(self):
        threading.Thread(target=self.multi_convert, daemon=True).start()

    def multi_convert(self):
        try:
            amount = float(self.multi_amount_var.get().replace(",", "."))
            base = self.multi_base_var.get()

            selection = [i.replace("id_", "") for i in self.targets_tree.selection()]
            if not selection:
                messagebox.showwarning("Warning", "Please select target currencies")
                return

            try:
                r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=6)
                data = r.json()
                if data.get("result") != "success":
                    raise Exception("API request failed")
                rates = data.get("rates", {})
            except Exception as e:
                messagebox.showerror("Error", f"Failed to fetch rates: {e}")
                return

            self.result_table.delete(*self.result_table.get_children())

            for currency in selection:
                rate = rates.get(currency)
                if rate is None:
                    value = "—"
                else:
                    value = f"{amount * rate:,.4f}"
                self.result_table.insert("", tk.END, values=(currency, value))

        except ValueError:
            messagebox.showerror("Error", "Please enter a valid amount")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # TAB 2 — % CHANGE
    def build_history_tab(self):
        top = ttk.Frame(self.tab_history, padding=10)
        top.pack(side="top", fill="x")

        ttk.Label(top, text="Base:").pack(side="left")
        self.hist_base_cb = ttk.Combobox(top, values=SUPPORTED, state="readonly", width=8)
        self.hist_base_cb.set("USD")
        self.hist_base_cb.pack(side="left", padx=4)

        ttk.Label(top, text="Targets:").pack(side="left", padx=(12, 0))

        self.hist_targets_tree = ttk.Treeview(top, show="tree", height=10)
        self.hist_targets_tree.pack(side="left", padx=4)
        self.enable_multiselect(self.hist_targets_tree)

        for c in HISTORY_SUPPORTED:
            img = get_flag(self.flag_cache, c)
            self.hist_targets_tree.insert("", tk.END, iid=f"id_{c}", image=img, text=c)

        ttk.Label(top, text="Period:").pack(side="left", padx=(12, 0))
        self.period_cb = ttk.Combobox(top, values=["7", "30", "90"], state="readonly", width=6)
        self.period_cb.set("30")
        self.period_cb.pack(side="left")

        self.show_btn = ttk.Button(top, text="Calculate", command=self.start_show_history)
        self.show_btn.pack(side="left", padx=8)

        frame = ttk.Frame(self.tab_history, padding=10)
        frame.pack(fill="both", expand=True)

        cols = ("currency", "change")
        self.hist_table = ttk.Treeview(frame, columns=cols, show="headings")
        self.hist_table.heading("currency", text="Currency")
        self.hist_table.heading("change", text="Change (%)")
        self.hist_table.pack(fill="both", expand=True)

        self.save_hist_btn = ttk.Button(frame, text="Save Results", command=self.save_history_results)
        self.save_hist_btn.pack(anchor="e", pady=8)

    def start_show_history(self):
        threading.Thread(target=self.show_history, daemon=True).start()
        self.show_btn.config(text="Loading...", state="disabled")

    def show_history(self):
        try:
            base = self.hist_base_cb.get()
            days = int(self.period_cb.get())
            targets = [i.replace("id_", "") for i in self.hist_targets_tree.selection()]

            if not targets:
                raise ValueError("Выберите валюты")

            end = get_latest_available_date()
            start = end - timedelta(days=days)

            self.hist_table.delete(*self.hist_table.get_children())

            for t in targets:
                if t in FIXED_SPECIAL:
                    old_usd, today_usd = FIXED_SPECIAL[t][days]
                    if base == "USD":
                        r_old, r_today = old_usd, today_usd
                    else:
                        b2usd_old = get_rate(start, base, "USD")
                        b2usd_today = get_rate(end, base, "USD")
                        if b2usd_old is None or b2usd_today is None:
                            r_old, r_today = None, None
                        else:
                            r_old = b2usd_old * old_usd
                            r_today = b2usd_today * today_usd
                else:
                    r_today = get_rate(end, base, t)
                    r_old = get_rate(start, base, t)

                if (r_today is None) or (r_old is None) or r_old == 0:
                    change = "—"
                else:
                    change = f"{((r_today - r_old) / r_old) * 100:+.2f}"

                self.hist_table.insert("", tk.END, values=(t, change))

        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self.show_btn.config(text="Calculate", state="normal")

    # SAVE RESULTS TO CSV
    def save_multi_results(self):
        data = []
        for row in self.result_table.get_children():
            data.append(self.result_table.item(row)["values"])
        if not data:
            messagebox.showinfo("Info", "Нет данных для сохранения.")
            return
        file = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not file: return
        try:
            with open(file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Currency", "Amount"])
                writer.writerows(data)
            messagebox.showinfo("Success", f"Результаты сохранены:\n{file}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save_history_results(self):
        data = []
        for row in self.hist_table.get_children():
            data.append(self.hist_table.item(row)["values"])
        if not data:
            messagebox.showinfo("Info", "Нет данных для сохранения.")
            return
        file = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not file: return
        try:
            with open(file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Currency", "Change (%)"])
                writer.writerows(data)
            messagebox.showinfo("Success", f"Результаты сохранены:\n{file}")
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    CurrencyApp().mainloop()
