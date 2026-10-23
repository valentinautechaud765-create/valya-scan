# -*- coding: utf-8 -*-
"""Base de données locale (SQLite).

Tables : téléphones, scans (diagnostics), réparations, historique (traçabilité),
fiches de réparation clients, stock de pièces.
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
_lock = threading.RLock()

CLIENT = "Client (réparation)"
STATUTS = ["En stock", "En réparation", "En vente", "Vendu", "Réservé", "Pièces", CLIENT]
ETATS = ["Comme neuf", "Très bon état", "Bon état", "État correct", "Écran cassé", "Pour pièces"]
TICKET_STATUTS = ["Reçu", "Diagnostic", "Devis envoyé", "En réparation", "Prêt", "Rendu", "Annulé"]
QUALITES = ["Origine Apple", "Origine récupérée", "OEM / Premium", "Compatible"]
CATEGORIES = ["Écran", "Batterie", "Vitre arrière", "Châssis", "Caméra", "Connecteur de charge",
              "Haut-parleur", "Nappe", "Face ID", "Bouton", "Autre"]

DEFAULT_SETTINGS = {
    "boutique": "Valya",
    "slogan": "iPhones reconditionnés · Réparation · Rachat",
    "contact": "",
    "adresse": "",
    "garantie": "Garantie 6 mois",
    "garantie_reparation": "Pièces et main d'œuvre garanties 3 mois",
    "sheets_id": "1tsNTLiTlpoWszTUQxE4xHhznFSkpWLIzdh9aTqnoXhA",
    "sheets_onglet_stock": "stock",
    "sheets_onglet_scans": "scans",
    "sheets_scans_auto": False,
    "service_account_path": "",
    "son_connexion": True,
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
  id INTEGER PRIMARY KEY AUTOINCREMENT, phone_id INTEGER, date TEXT, data TEXT, etiquette TEXT
);
CREATE TABLE IF NOT EXISTS repairs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, phone_id INTEGER, date TEXT,
  piece TEXT, cout REAL, note TEXT, part_id INTEGER, ticket_id INTEGER, qualite TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, phone_id INTEGER, ticket_id INTEGER,
  date TEXT, type TEXT, texte TEXT
);
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT, phone_id INTEGER,
  client_nom TEXT, client_tel TEXT, appareil TEXT, imei TEXT, probleme TEXT,
  diagnostic TEXT DEFAULT '', devis REAL, acompte REAL, statut TEXT DEFAULT 'Reçu',
  date_depot TEXT, date_prevue TEXT, date_rendu TEXT, notes TEXT DEFAULT '',
  etat_depot TEXT DEFAULT '', info_piece INTEGER DEFAULT 0,
  cree_le TEXT, maj_le TEXT
);
CREATE TABLE IF NOT EXISTS parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT, categorie TEXT, compatible TEXT,
  qualite TEXT, fournisseur TEXT, cout REAL, quantite INTEGER DEFAULT 0, seuil INTEGER DEFAULT 1,
  maj_le TEXT
);
CREATE INDEX IF NOT EXISTS idx_scans_phone ON scans(phone_id);
CREATE INDEX IF NOT EXISTS idx_repairs_phone ON repairs(phone_id);
CREATE INDEX IF NOT EXISTS idx_events_phone ON events(phone_id);
CREATE INDEX IF NOT EXISTS idx_events_ticket ON events(ticket_id);
"""

# colonnes ajoutées après coup : (table, colonne, définition)
MIGRATIONS = [
    ("phones", "tests", "TEXT DEFAULT '{}'"),
    ("scans", "etiquette", "TEXT"),
    ("repairs", "part_id", "INTEGER"),
    ("repairs", "ticket_id", "INTEGER"),
    ("repairs", "qualite", "TEXT"),
]

EDITABLE = ["reference", "etat", "statut", "prix_achat", "frais", "prix_vente", "date_achat",
            "date_vente", "notes", "tests", "couleur", "stockage", "modele", "imei", "sante_batterie"]
TICKET_FIELDS = ["client_nom", "client_tel", "appareil", "imei", "probleme", "diagnostic", "devis",
                 "acompte", "statut", "date_prevue", "date_rendu", "notes", "etat_depot", "info_piece", "phone_id"]
PART_FIELDS = ["nom", "categorie", "compatible", "qualite", "fournisseur", "cout", "quantite", "seuil"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock:
        c = conn()
        c.executescript(SCHEMA)
        for table, col, definition in MIGRATIONS:
            cols = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % table).fetchall()]
            if col not in cols:
                c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, definition))
        c.commit()
        c.close()


def _row(r):
    return dict(r) if r else None


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ".").replace("€", "").strip())
    except ValueError:
        raise ValueError("Valeur numérique invalide : %s" % v)


def _int(v, default=None):
    if v in (None, ""):
        return default
    try:
        return int(float(str(v).replace(",", ".")))
    except ValueError:
        raise ValueError("Nombre invalide : %s" % v)


# ------------------------------------------------------------------ historique

def _event(c, phone_id, typ, texte, ticket_id=None):
    c.execute("INSERT INTO events (phone_id, ticket_id, date, type, texte) VALUES (?,?,?,?,?)",
              (phone_id, ticket_id, now(), typ, texte))


def add_event(phone_id, typ, texte, ticket_id=None):
    with _lock:
        c = conn()
        _event(c, phone_id, typ, texte, ticket_id)
        c.commit()
        c.close()


# ------------------------------------------------------------------ téléphones

def margin(p):
    """Marge = prix de vente − prix d'achat − frais − pièces de réparation."""
    if p.get("prix_vente") is None or p.get("prix_achat") is None:
        return None
    return round((p.get("prix_vente") or 0) - (p.get("prix_achat") or 0) - (p.get("frais") or 0)
                 - (p.get("cout_reparations") or 0), 2)


def normalize_tests(t):
    """Anciennes fiches : {test: true} -> {test: "ok"}."""
    out = {}
    for k, v in (t or {}).items():
        if v is True or v == "ok":
            out[k] = "ok"
        elif v in ("ko", "na"):
            out[k] = v
    return out


def _enrich(c, p):
    try:
        p["tests"] = normalize_tests(json.loads(p.get("tests") or "{}"))
    except ValueError:
        p["tests"] = {}
    rep = c.execute("SELECT COALESCE(SUM(cout),0) s FROM repairs WHERE phone_id=?", (p["id"],)).fetchone()
    p["cout_reparations"] = rep["s"] or 0
    p["marge"] = margin(p)
    return p


def _field(scan, path):
    cur = scan
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


# Ce qu'on surveille d'un scan à l'autre (traçabilité des pièces et de l'appareil)
WATCH = [
    ("serie", "Numéro de série"), ("imei", "IMEI"), ("numero_modele", "Référence modèle"),
    ("ios", "Version iOS"), ("activation", "Activation"), ("localiser", "Localiser"),
    ("batterie.serie_batterie", "N° de série batterie"), ("batterie.capacite_origine", "Capacité d'origine batterie"),
    ("batterie.sante", "Santé batterie (%)"), ("batterie.cycles", "Cycles batterie"),
    ("stockage.capacite", "Stockage"), ("modem", "Firmware modem"), ("couleur", "Couleur"),
]


def diff_scans(a, b):
    """Différences entre deux diagnostics (a = avant, b = après)."""
    out = []
    for path, label in WATCH:
        va, vb = _field(a, path), _field(b, path)
        out.append({"champ": label, "avant": va, "apres": vb, "change": va != vb and not (va in (None, "") and vb in (None, ""))})
    return out


def upsert_from_scan(scan):
    """Crée ou met à jour la fiche d'un iPhone à partir d'un diagnostic.

    Renvoie (fiche, changements depuis le scan précédent)."""
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
    changes = []
    with _lock:
        c = conn()
        cur = c.execute("SELECT * FROM phones WHERE serie=?", (serie,)).fetchone()
        if cur:
            pid = cur["id"]
            prev = c.execute("SELECT data FROM scans WHERE phone_id=? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
            if prev:
                changes = [d for d in diff_scans(json.loads(prev["data"]), scan)
                           if d["change"] and d["champ"] not in ("Santé batterie (%)", "Cycles batterie")]
            sets = ", ".join("%s=?" % k for k in fields) + ", maj_le=?"
            c.execute("UPDATE phones SET %s WHERE id=?" % sets, list(fields.values()) + [now(), pid])
            for ch in changes:
                _event(c, pid, "changement", "%s : %s → %s" % (ch["champ"], ch["avant"], ch["apres"]))
        else:
            fields.update({"serie": serie, "statut": "En stock", "date_achat": today(),
                           "cree_le": now(), "maj_le": now(), "couleur": scan.get("couleur")})
            keys = list(fields.keys())
            c.execute("INSERT INTO phones (%s) VALUES (%s)" % (",".join(keys), ",".join("?" * len(keys))),
                      [fields[k] for k in keys])
            pid = c.execute("SELECT last_insert_rowid() i").fetchone()["i"]
            c.execute("UPDATE phones SET reference=? WHERE id=?", ("VAL-%04d" % pid, pid))
            _event(c, pid, "creation", "Fiche créée au premier branchement (%s)." % (scan.get("modele") or "iPhone"))
        c.execute("INSERT INTO scans (phone_id, date, data) VALUES (?,?,?)",
                  (pid, scan.get("scanne_le") or now(), json.dumps(scan, ensure_ascii=False, default=str)))
        verdict = (scan.get("verdict") or {}).get("titre", "")
        _event(c, pid, "scan", "Diagnostic : %s" % verdict if verdict else "Diagnostic effectué.")
        c.commit()
        p = _enrich(c, _row(c.execute("SELECT * FROM phones WHERE id=?", (pid,)).fetchone()))
        c.close()
    return p, changes


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
        scans = c.execute("SELECT id, date, data, etiquette FROM scans WHERE phone_id=? ORDER BY id DESC LIMIT 50",
                          (pid,)).fetchall()
        p["scans"] = [{"id": s["id"], "date": s["date"], "etiquette": s["etiquette"]} for s in scans]
        p["dernier_diagnostic"] = json.loads(scans[0]["data"]) if scans else None
        p["historique"] = [dict(r) for r in c.execute(
            "SELECT * FROM events WHERE phone_id=? ORDER BY id DESC LIMIT 200", (pid,)).fetchall()]
        p["tickets"] = [dict(r) for r in c.execute(
            "SELECT id, numero, statut, probleme, date_depot FROM tickets WHERE phone_id=? ORDER BY id DESC", (pid,)).fetchall()]
        c.close()
    return p


def find_by_serial(serie):
    with _lock:
        c = conn()
        r = c.execute("SELECT id FROM phones WHERE serie=?", (serie,)).fetchone()
        c.close()
    return r["id"] if r else None


def update_phone(pid, data):
    before = get_phone(pid)
    if not before:
        return None
    vals = {}
    for k in EDITABLE:
        if k in data:
            v = data[k]
            if k in ("prix_achat", "frais", "prix_vente"):
                v = _num(v)
            elif k == "tests":
                v = json.dumps(normalize_tests(v if isinstance(v, dict) else {}), ensure_ascii=False)
            elif k == "sante_batterie":
                v = _int(v)
            vals[k] = v
    if vals.get("statut") == "Vendu" and not data.get("date_vente") and not before.get("date_vente"):
        vals["date_vente"] = today()
    if not vals:
        return before
    with _lock:
        c = conn()
        sets = ", ".join("%s=?" % k for k in vals) + ", maj_le=?"
        c.execute("UPDATE phones SET %s WHERE id=?" % sets, list(vals.values()) + [now(), pid])
        if "statut" in vals and vals["statut"] != before.get("statut"):
            _event(c, pid, "statut", "Statut : %s → %s" % (before.get("statut"), vals["statut"]))
        if "prix_vente" in vals and vals["prix_vente"] != before.get("prix_vente"):
            _event(c, pid, "prix", "Prix de vente : %s € → %s €" % (before.get("prix_vente") or "—", vals["prix_vente"] or "—"))
        if "tests" in vals:
            t = json.loads(vals["tests"])
            old = before.get("tests") or {}
            if t != old:
                ok = sum(1 for v in t.values() if v == "ok")
                ko = [k for k, v in t.items() if v == "ko"]
                _event(c, pid, "tests", "Tests : %d OK%s" % (ok, (", défaut : " + ", ".join(ko)) if ko else ""))
        c.commit()
        c.close()
    return get_phone(pid)


def set_sheets_row(pid, row):
    with _lock:
        c = conn()
        c.execute("UPDATE phones SET sheets_ligne=? WHERE id=?", (row, pid))
        _event(c, pid, "sheets", "Envoyé au Google Sheets (ligne %s)." % row)
        c.commit()
        c.close()


def delete_phone(pid):
    with _lock:
        c = conn()
        for t in ("repairs", "scans", "events"):
            c.execute("DELETE FROM %s WHERE phone_id=?" % t, (pid,))
        c.execute("UPDATE tickets SET phone_id=NULL WHERE phone_id=?", (pid,))
        c.execute("DELETE FROM phones WHERE id=?", (pid,))
        c.commit()
        c.close()


def add_repair(pid, piece, cout, note, part_id=None, ticket_id=None, qualite=None):
    """Enregistre une intervention ; si une pièce du stock est utilisée, le stock baisse de 1."""
    with _lock:
        c = conn()
        part = None
        if part_id:
            part = _row(c.execute("SELECT * FROM parts WHERE id=?", (part_id,)).fetchone())
            if not part:
                c.close()
                raise ValueError("Pièce introuvable dans le stock.")
            if (part["quantite"] or 0) <= 0:
                c.close()
                raise ValueError("Plus de « %s » en stock." % part["nom"])
            piece = piece or part["nom"]
            if cout in (None, ""):
                cout = part["cout"]
            qualite = qualite or part["qualite"]
            c.execute("UPDATE parts SET quantite=quantite-1, maj_le=? WHERE id=?", (now(), part_id))
        if not (piece or "").strip():
            c.close()
            raise ValueError("Indique la pièce ou l'intervention.")
        c.execute("INSERT INTO repairs (phone_id, date, piece, cout, note, part_id, ticket_id, qualite) VALUES (?,?,?,?,?,?,?,?)",
                  (pid, today(), piece.strip(), _num(cout) or 0, note or "", part_id, ticket_id, qualite or ""))
        c.execute("UPDATE phones SET maj_le=? WHERE id=?", (now(), pid))
        _event(c, pid, "reparation", "Intervention : %s%s%s" % (
            piece.strip(), " (%s)" % qualite if qualite else "", " — " + note if note else ""), ticket_id)
        c.commit()
        c.close()
    return get_phone(pid)


def delete_repair(pid, rid, restock=True):
    with _lock:
        c = conn()
        r = _row(c.execute("SELECT * FROM repairs WHERE id=? AND phone_id=?", (rid, pid)).fetchone())
        if r:
            if restock and r.get("part_id"):
                c.execute("UPDATE parts SET quantite=quantite+1 WHERE id=?", (r["part_id"],))
            c.execute("DELETE FROM repairs WHERE id=?", (rid,))
            _event(c, pid, "reparation", "Intervention supprimée : %s" % r["piece"])
        c.commit()
        c.close()
    return get_phone(pid)


def get_scan(sid):
    with _lock:
        c = conn()
        r = c.execute("SELECT data FROM scans WHERE id=?", (sid,)).fetchone()
        c.close()
    return json.loads(r["data"]) if r else None


def label_scan(sid, etiquette):
    with _lock:
        c = conn()
        r = c.execute("SELECT phone_id FROM scans WHERE id=?", (sid,)).fetchone()
        c.execute("UPDATE scans SET etiquette=? WHERE id=?", (etiquette, sid))
        if r and etiquette:
            _event(c, r["phone_id"], "scan", "Diagnostic marqué « %s »." % etiquette)
        c.commit()
        c.close()


def compare_scans(a_id, b_id):
    a, b = get_scan(a_id), get_scan(b_id)
    if not a or not b:
        raise ValueError("Diagnostic introuvable.")
    return {"avant": {"id": a_id, "date": a.get("scanne_le")}, "apres": {"id": b_id, "date": b.get("scanne_le")},
            "lignes": diff_scans(a, b)}


def stats():
    phones = [p for p in list_phones() if p["statut"] != CLIENT]
    stock = [p for p in phones if p["statut"] != "Vendu"]
    sold = [p for p in phones if p["statut"] == "Vendu"]
    invested = sum((p["prix_achat"] or 0) + (p["frais"] or 0) + (p["cout_reparations"] or 0) for p in stock)
    profit = sum(p["marge"] or 0 for p in sold)
    potential = sum(p["marge"] or 0 for p in stock if p["marge"] is not None)
    return {"total": len(phones), "en_stock": len(stock), "vendus": len(sold),
            "investi": round(invested, 2), "benefice": round(profit, 2), "benefice_potentiel": round(potential, 2)}


# ------------------------------------------------------------------ fiches de réparation clients

def _ticket_enrich(c, t):
    t["reparations"] = [dict(r) for r in c.execute(
        "SELECT * FROM repairs WHERE ticket_id=? ORDER BY id DESC", (t["id"],)).fetchall()]
    t["cout_pieces"] = sum(r["cout"] or 0 for r in t["reparations"])
    t["reste_a_payer"] = None if t.get("devis") is None else round((t["devis"] or 0) - (t.get("acompte") or 0), 2)
    t["historique"] = [dict(r) for r in c.execute(
        "SELECT * FROM events WHERE ticket_id=? ORDER BY id DESC LIMIT 100", (t["id"],)).fetchall()]
    if t.get("phone_id"):
        ph = c.execute("SELECT reference, modele, serie, imei FROM phones WHERE id=?", (t["phone_id"],)).fetchone()
        t["telephone"] = dict(ph) if ph else None
    return t


def list_tickets(q=None, statut=None, actifs=False):
    sql = "SELECT * FROM tickets WHERE 1=1"
    args = []
    if q:
        like = "%" + q.strip() + "%"
        sql += " AND (numero LIKE ? OR client_nom LIKE ? OR client_tel LIKE ? OR appareil LIKE ? OR imei LIKE ?)"
        args += [like] * 5
    if statut:
        sql += " AND statut=?"
        args.append(statut)
    if actifs:
        sql += " AND statut NOT IN ('Rendu','Annulé')"
    sql += " ORDER BY id DESC"
    with _lock:
        c = conn()
        rows = [_ticket_enrich(c, dict(r)) for r in c.execute(sql, args).fetchall()]
        c.close()
    return rows


def get_ticket(tid):
    with _lock:
        c = conn()
        t = _row(c.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone())
        if t:
            _ticket_enrich(c, t)
        c.close()
    return t


def _ticket_vals(data):
    vals = {}
    for k in TICKET_FIELDS:
        if k in data:
            v = data[k]
            if k in ("devis", "acompte"):
                v = _num(v)
            elif k == "info_piece":
                v = 1 if v in (True, 1, "1", "on", "true") else 0
            elif k == "phone_id":
                v = _int(v, None)
            elif isinstance(v, str):
                v = v.strip()
            vals[k] = v
    if "statut" in vals and vals["statut"] not in TICKET_STATUTS:
        raise ValueError("Statut inconnu.")
    return vals


def create_ticket(data):
    vals = _ticket_vals(data)
    if not (vals.get("client_nom") or "").strip():
        raise ValueError("Indique le nom du client.")
    if not (vals.get("probleme") or "").strip():
        raise ValueError("Décris la panne ou la réparation demandée.")
    vals.setdefault("statut", "Reçu")
    vals.update({"date_depot": today(), "cree_le": now(), "maj_le": now()})
    with _lock:
        c = conn()
        keys = list(vals.keys())
        c.execute("INSERT INTO tickets (%s) VALUES (%s)" % (",".join(keys), ",".join("?" * len(keys))),
                  [vals[k] for k in keys])
        tid = c.execute("SELECT last_insert_rowid() i").fetchone()["i"]
        numero = "R-%04d" % tid
        c.execute("UPDATE tickets SET numero=? WHERE id=?", (numero, tid))
        _event(c, vals.get("phone_id"), "ticket", "Fiche %s ouverte : %s" % (numero, vals["probleme"]), tid)
        if vals.get("phone_id"):
            c.execute("UPDATE phones SET statut=? WHERE id=? AND statut IN ('En stock')", (CLIENT, vals["phone_id"]))
        c.commit()
        c.close()
    return get_ticket(tid)


def update_ticket(tid, data):
    before = get_ticket(tid)
    if not before:
        return None
    vals = _ticket_vals(data)
    if vals.get("statut") == "Rendu" and not vals.get("date_rendu") and not before.get("date_rendu"):
        vals["date_rendu"] = today()
    if not vals:
        return before
    with _lock:
        c = conn()
        sets = ", ".join("%s=?" % k for k in vals) + ", maj_le=?"
        c.execute("UPDATE tickets SET %s WHERE id=?" % sets, list(vals.values()) + [now(), tid])
        pid = vals.get("phone_id", before.get("phone_id"))
        if "statut" in vals and vals["statut"] != before["statut"]:
            _event(c, pid, "ticket", "%s : %s → %s" % (before["numero"], before["statut"], vals["statut"]), tid)
        if "phone_id" in vals and vals["phone_id"] and vals["phone_id"] != before.get("phone_id"):
            _event(c, vals["phone_id"], "ticket", "iPhone associé à la fiche %s." % before["numero"], tid)
            c.execute("UPDATE phones SET statut=? WHERE id=? AND statut IN ('En stock')", (CLIENT, vals["phone_id"]))
        if "diagnostic" in vals and vals["diagnostic"] != before.get("diagnostic") and vals["diagnostic"]:
            _event(c, pid, "ticket", "%s — diagnostic : %s" % (before["numero"], vals["diagnostic"][:150]), tid)
        c.commit()
        c.close()
    return get_ticket(tid)


def delete_ticket(tid):
    with _lock:
        c = conn()
        c.execute("UPDATE repairs SET ticket_id=NULL WHERE ticket_id=?", (tid,))
        c.execute("DELETE FROM events WHERE ticket_id=? AND phone_id IS NULL", (tid,))
        c.execute("DELETE FROM tickets WHERE id=?", (tid,))
        c.commit()
        c.close()


def ticket_stats():
    with _lock:
        c = conn()
        rows = c.execute("SELECT statut, COUNT(*) n FROM tickets GROUP BY statut").fetchall()
        c.close()
    return {r["statut"]: r["n"] for r in rows}


# ------------------------------------------------------------------ stock de pièces

def list_parts(q=None):
    sql = "SELECT * FROM parts WHERE 1=1"
    args = []
    if q:
        like = "%" + q.strip() + "%"
        sql += " AND (nom LIKE ? OR compatible LIKE ? OR categorie LIKE ? OR fournisseur LIKE ?)"
        args += [like] * 4
    sql += " ORDER BY categorie, nom"
    with _lock:
        c = conn()
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
        c.close()
    for r in rows:
        r["alerte"] = (r["quantite"] or 0) <= (r["seuil"] or 0)
    return rows


def _part_vals(data):
    vals = {}
    for k in PART_FIELDS:
        if k in data:
            v = data[k]
            if k == "cout":
                v = _num(v)
            elif k in ("quantite", "seuil"):
                v = _int(v, 0)
            elif isinstance(v, str):
                v = v.strip()
            vals[k] = v
    return vals


def save_part(data, pid=None):
    vals = _part_vals(data)
    vals["maj_le"] = now()
    with _lock:
        c = conn()
        if pid:
            sets = ", ".join("%s=?" % k for k in vals)
            c.execute("UPDATE parts SET %s WHERE id=?" % sets, list(vals.values()) + [pid])
        else:
            if not vals.get("nom"):
                c.close()
                raise ValueError("Indique le nom de la pièce.")
            keys = list(vals.keys())
            c.execute("INSERT INTO parts (%s) VALUES (%s)" % (",".join(keys), ",".join("?" * len(keys))),
                      [vals[k] for k in keys])
        c.commit()
        c.close()
    return list_parts()


def delete_part(pid):
    with _lock:
        c = conn()
        c.execute("DELETE FROM parts WHERE id=?", (pid,))
        c.commit()
        c.close()
    return list_parts()


def parts_for(modele):
    """Pièces compatibles avec un modèle (recherche simple sur le nom du modèle)."""
    if not modele:
        return []
    m = modele.lower().replace("iphone", "").strip()
    return [p for p in list_parts() if m and m in (p.get("compatible") or "").lower()]


# ------------------------------------------------------------------ réglages

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
