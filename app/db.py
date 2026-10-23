# -*- coding: utf-8 -*-
"""Base de données locale (SQLite) : téléphones, scans, réparations.

Le fichier est rangé dans ~/Library/Application Support/ValyaScan/ pour survivre
aux mises à jour de l'app.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime

DATA_DIR = os.environ.get("VALYA_DATA_DIR") or os.path.expanduser("~/Library/Application Support/ValyaScan")
DB_PATH = os.path.join(DATA_DIR, "valya.db")
SETTINGS_PATH = os.path.join(DATA_DIR, "reglages.json")
_lock = threading.Lock()

STATUTS = ["En stock", "En réparation", "En vente", "Vendu", "Réservé", "Pièces"]
ETATS = ["Comme neuf", "Très bon état", "Bon état", "État correct", "Écran cassé", "Pour pièces"]

DEFAULT_SETTINGS = {
    "boutique": "Valya",
    "slogan": "iPhones reconditionnés · Réparation · Rachat",
    "contact": "",
    "garantie": "Garantie 6 mois",
    "sheets_id": "1tsNTLiTlpoWszTUQxE4xHhznFSkpWLIzdh9aTqnoXhA",
    "sheets_onglet_stock": "stock",
    "sheets_onglet_scans": "scans",
    "sheets_scans_auto": False,
    "service_account_path": "",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS phones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reference TEXT, serie TEXT UNIQUE, udid TEXT, imei TEXT, imei2 TEXT,
  modele TEXT, product_type TEXT, stockage TEXT, couleur TEXT, ios TEXT,
  sante_batterie INTEGER, cycles INTEGER, activation TEXT, localiser INTEGER,
  origine TEXT, etat TEXT, statut TEXT DEFAULT 'En stock',
  prix_achat REAL, frais REAL, prix_vente REAL, date_achat TEXT, date_vente TEXT,
  notes TEXT DEFAULT '', tests TEXT DEFAULT '{}', sheets_ligne INTEGER, dernier_scan TEXT,
  cree_le TEXT, maj_le TEXT
);
CREATE TABLE IF NOT EXISTS scans (
  id INTEGER PRIMARY KEY AUTOINCREMENT, phone_id INTEGER, date TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS repairs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, phone_id INTEGER, date TEXT,
  piece TEXT, cout REAL, note TEXT
);
CREATE INDEX IF NOT EXISTS idx_scans_phone ON scans(phone_id);
CREATE INDEX IF NOT EXISTS idx_repairs_phone ON repairs(phone_id);
"""

EDITABLE = ["reference", "etat", "statut", "prix_achat", "frais", "prix_vente", "date_achat",
            "date_vente", "notes", "tests", "couleur", "stockage", "modele", "imei", "sante_batterie"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock:
        c = conn()
        c.executescript(SCHEMA)
        cols = [r["name"] for r in c.execute("PRAGMA table_info(phones)").fetchall()]
        if "tests" not in cols:  # migration d'une ancienne base
            c.execute("ALTER TABLE phones ADD COLUMN tests TEXT DEFAULT '{}'")
        c.commit()
        c.close()


def _row(r):
    return dict(r) if r else None


def margin(p):
    """Marge = prix de vente − prix d'achat − frais − pièces de réparation."""
    if p.get("prix_vente") is None or p.get("prix_achat") is None:
        return None
    return round((p.get("prix_vente") or 0) - (p.get("prix_achat") or 0) - (p.get("frais") or 0)
                 - (p.get("cout_reparations") or 0), 2)


def _enrich(c, p):
    try:
        p["tests"] = json.loads(p.get("tests") or "{}")
    except ValueError:
        p["tests"] = {}
    rep = c.execute("SELECT COALESCE(SUM(cout),0) s FROM repairs WHERE phone_id=?", (p["id"],)).fetchone()
    p["cout_reparations"] = rep["s"] or 0
    p["marge"] = margin(p)
    return p


def upsert_from_scan(scan):
    """Crée ou met à jour la fiche d'un iPhone à partir d'un diagnostic. Renvoie la fiche."""
    bat = scan.get("batterie") or {}
    sto = scan.get("stockage") or {}
    fields = {
        "udid": scan.get("udid"), "imei": scan.get("imei"), "imei2": scan.get("imei2"),
        "modele": scan.get("modele"), "product_type": scan.get("product_type"),
        "stockage": sto.get("capacite"), "ios": scan.get("ios"),
        "sante_batterie": bat.get("sante"), "cycles": bat.get("cycles"),
        "activation": scan.get("activation"),
        "localiser": None if scan.get("localiser") is None else int(bool(scan.get("localiser"))),
        "origine": scan.get("origine"), "dernier_scan": scan.get("scanne_le"),
    }
    serie = scan.get("serie") or scan.get("udid")
    with _lock:
        c = conn()
        cur = c.execute("SELECT * FROM phones WHERE serie=?", (serie,)).fetchone()
        if cur:
            sets = ", ".join("%s=?" % k for k in fields) + ", maj_le=?"
            c.execute("UPDATE phones SET %s WHERE id=?" % sets, list(fields.values()) + [now(), cur["id"]])
            pid = cur["id"]
        else:
            fields.update({"serie": serie, "statut": "En stock", "date_achat": datetime.now().strftime("%Y-%m-%d"),
                           "cree_le": now(), "maj_le": now(), "couleur": scan.get("couleur")})
            keys = list(fields.keys())
            c.execute("INSERT INTO phones (%s) VALUES (%s)" % (",".join(keys), ",".join("?" * len(keys))),
                      [fields[k] for k in keys])
            pid = c.execute("SELECT last_insert_rowid() i").fetchone()["i"]
            ref = "VAL-%04d" % pid
            c.execute("UPDATE phones SET reference=? WHERE id=?", (ref, pid))
        c.execute("INSERT INTO scans (phone_id, date, data) VALUES (?,?,?)",
                  (pid, scan.get("scanne_le") or now(), json.dumps(scan, ensure_ascii=False, default=str)))
        c.commit()
        p = _enrich(c, _row(c.execute("SELECT * FROM phones WHERE id=?", (pid,)).fetchone()))
        c.close()
    return p


def list_phones(q=None, statut=None):
    sql = "SELECT * FROM phones WHERE 1=1"
    args = []
    if q:
        like = "%" + q.strip() + "%"
        sql += " AND (modele LIKE ? OR serie LIKE ? OR imei LIKE ? OR reference LIKE ? OR notes LIKE ?)"
        args += [like] * 5
    if statut:
        sql += " AND statut=?"
        args.append(statut)
    sql += " ORDER BY COALESCE(maj_le, cree_le) DESC"
    with _lock:
        c = conn()
        rows = [_enrich(c, dict(r)) for r in c.execute(sql, args).fetchall()]
        c.close()
    return rows


def get_phone(pid):
    with _lock:
        c = conn()
        p = _row(c.execute("SELECT * FROM phones WHERE id=?", (pid,)).fetchone())
        if not p:
            c.close()
            return None
        _enrich(c, p)
        p["reparations"] = [dict(r) for r in c.execute(
            "SELECT * FROM repairs WHERE phone_id=? ORDER BY date DESC, id DESC", (pid,)).fetchall()]
        scans = c.execute("SELECT id, date, data FROM scans WHERE phone_id=? ORDER BY id DESC LIMIT 20", (pid,)).fetchall()
        p["scans"] = [{"id": s["id"], "date": s["date"]} for s in scans]
        p["dernier_diagnostic"] = json.loads(scans[0]["data"]) if scans else None
        c.close()
    return p


def find_by_serial(serie):
    with _lock:
        c = conn()
        r = c.execute("SELECT id FROM phones WHERE serie=?", (serie,)).fetchone()
        c.close()
    return r["id"] if r else None


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ".").replace("€", "").strip())
    except ValueError:
        raise ValueError("Valeur numérique invalide : %s" % v)


def update_phone(pid, data):
    vals = {}
    for k in EDITABLE:
        if k in data:
            v = data[k]
            if k in ("prix_achat", "frais", "prix_vente"):
                v = _num(v)
            elif k == "tests":
                v = json.dumps(v if isinstance(v, dict) else {}, ensure_ascii=False)
            elif k == "sante_batterie":
                v = None if v in (None, "") else int(float(v))
            vals[k] = v
    if "statut" in vals and vals["statut"] == "Vendu" and not data.get("date_vente"):
        vals.setdefault("date_vente", datetime.now().strftime("%Y-%m-%d"))
    if not vals:
        return get_phone(pid)
    with _lock:
        c = conn()
        sets = ", ".join("%s=?" % k for k in vals) + ", maj_le=?"
        c.execute("UPDATE phones SET %s WHERE id=?" % sets, list(vals.values()) + [now(), pid])
        c.commit()
        c.close()
    return get_phone(pid)


def set_sheets_row(pid, row):
    with _lock:
        c = conn()
        c.execute("UPDATE phones SET sheets_ligne=? WHERE id=?", (row, pid))
        c.commit()
        c.close()


def delete_phone(pid):
    with _lock:
        c = conn()
        c.execute("DELETE FROM repairs WHERE phone_id=?", (pid,))
        c.execute("DELETE FROM scans WHERE phone_id=?", (pid,))
        c.execute("DELETE FROM phones WHERE id=?", (pid,))
        c.commit()
        c.close()


def add_repair(pid, piece, cout, note):
    with _lock:
        c = conn()
        c.execute("INSERT INTO repairs (phone_id, date, piece, cout, note) VALUES (?,?,?,?,?)",
                  (pid, datetime.now().strftime("%Y-%m-%d"), piece, _num(cout) or 0, note or ""))
        c.execute("UPDATE phones SET maj_le=? WHERE id=?", (now(), pid))
        c.commit()
        c.close()
    return get_phone(pid)


def delete_repair(pid, rid):
    with _lock:
        c = conn()
        c.execute("DELETE FROM repairs WHERE id=? AND phone_id=?", (rid, pid))
        c.commit()
        c.close()
    return get_phone(pid)


def get_scan(sid):
    with _lock:
        c = conn()
        r = c.execute("SELECT data FROM scans WHERE id=?", (sid,)).fetchone()
        c.close()
    return json.loads(r["data"]) if r else None


def stats():
    phones = list_phones()
    stock = [p for p in phones if p["statut"] != "Vendu"]
    sold = [p for p in phones if p["statut"] == "Vendu"]
    invested = sum((p["prix_achat"] or 0) + (p["frais"] or 0) + (p["cout_reparations"] or 0) for p in stock)
    profit = sum(p["marge"] or 0 for p in sold)
    potential = sum(p["marge"] or 0 for p in stock if p["marge"] is not None)
    return {"total": len(phones), "en_stock": len(stock), "vendus": len(sold),
            "investi": round(invested, 2), "benefice": round(profit, 2), "benefice_potentiel": round(potential, 2)}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s.update(json.load(f))
    except (IOError, ValueError):
        pass
    return s


def save_settings(new):
    s = load_settings()
    for k in DEFAULT_SETTINGS:
        if k in new:
            s[k] = new[k]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    return s
