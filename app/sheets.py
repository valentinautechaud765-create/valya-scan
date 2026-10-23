# -*- coding: utf-8 -*-
"""Synchronisation avec le Google Sheets de stock (celui que lit STOCKFLOW).

Règles appliquées (les tiennes) :
- rien n'est écrit sans que tu aies validé le récapitulatif complet dans l'app ;
- les colonnes sont repérées par leur titre (ligne 1), donc le tableau peut évoluer ;
- on n'écrit jamais dans la colonne « Marge » (formule) ni dans les colonnes inconnues ;
- avant d'écrire : la ligne cible doit être vide (ou être celle de ce téléphone pour une
  mise à jour), avoir sa formule de Marge et, s'il y a une colonne Statut, sa liste déroulante ;
- après l'écriture : on relit la ligne et on compare.
"""
import base64
import json
import re
import time
from datetime import datetime

# Modules 100 % Python (aucune compilation sur le Mac, contrairement à google-auth).
try:
    import requests
    import rsa
    HAS_GOOGLE = True
except ImportError:  # pragma: no cover
    HAS_GOOGLE = False

API = "https://sheets.googleapis.com/v4/spreadsheets/"
SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_token_cache = {}


class SheetsError(Exception):
    pass


def _der_read(data, pos):
    """Lit un élément DER : renvoie (tag, contenu, position suivante)."""
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    return tag, data[pos:pos + length], pos + length


def _load_private_key(pem):
    """Clé Google (PKCS#8 « BEGIN PRIVATE KEY ») -> clé rsa (PKCS#1)."""
    if "BEGIN RSA PRIVATE KEY" in pem:
        return rsa.PrivateKey.load_pkcs1(pem.encode())
    body = re.sub(r"-----[^-]+-----|\s", "", pem)
    der = base64.b64decode(body)
    _, seq, _ = _der_read(der, 0)            # PrivateKeyInfo
    _, _, p = _der_read(seq, 0)              # version
    _, _, p = _der_read(seq, p)              # algorithme
    _, pkcs1, _ = _der_read(seq, p)          # OCTET STRING = clé PKCS#1
    return rsa.PrivateKey.load_pkcs1(pkcs1, format="DER")


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=")


def _access_token(info):
    cached = _token_cache.get(info["client_email"])
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    now = int(time.time())
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64(json.dumps({"iss": info["client_email"], "scope": SCOPE,
                              "aud": info.get("token_uri", "https://oauth2.googleapis.com/token"),
                              "iat": now, "exp": now + 3600}).encode())
    signing_input = header + b"." + claims
    sig = rsa.sign(signing_input, _load_private_key(info["private_key"]), "SHA-256")
    jwt = (signing_input + b"." + _b64(sig)).decode()
    r = requests.post(info.get("token_uri", "https://oauth2.googleapis.com/token"),
                      data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt},
                      timeout=20)
    if r.status_code != 200:
        raise SheetsError("Google refuse la clé du compte de service : %s" % r.text[:200])
    d = r.json()
    _token_cache[info["client_email"]] = (d["access_token"], now + int(d.get("expires_in", 3600)))
    return d["access_token"]


def _session(settings):
    if not HAS_GOOGLE:
        raise SheetsError("Modules manquants : relance Valya Scan pour terminer l'installation.")
    path = settings.get("service_account_path")
    if not path:
        raise SheetsError("Aucune clé de compte de service configurée (Réglages > Synchro Google Sheets).")
    try:
        with open(path, "r", encoding="utf-8") as f:
            info = json.load(f)
        token = _access_token(info)
    except SheetsError:
        raise
    except Exception as e:
        raise SheetsError("Clé de compte de service illisible : %s" % e)
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + token
    return s


def _q(tab):
    return "'%s'" % tab.replace("'", "''")


def _get(s, url, **params):
    r = s.get(url, params=params, timeout=20)
    if r.status_code != 200:
        raise SheetsError(_err(r))
    return r.json()


def _err(r):
    try:
        msg = r.json().get("error", {}).get("message")
    except ValueError:
        msg = r.text[:200]
    if r.status_code == 403:
        return "Accès refusé : partage le Google Sheets avec l'adresse du compte de service (en éditeur). (%s)" % msg
    if r.status_code == 404:
        return "Google Sheets ou onglet introuvable. Vérifie l'identifiant dans les Réglages. (%s)" % msg
    return "Erreur Google Sheets %s : %s" % (r.status_code, msg)


def test(settings):
    s = _session(settings)
    meta = _get(s, API + settings["sheets_id"], fields="properties.title,sheets.properties.title")
    tabs = [x["properties"]["title"] for x in meta.get("sheets", [])]
    return {"titre": meta["properties"]["title"], "onglets": tabs,
            "stock_ok": settings["sheets_onglet_stock"] in tabs,
            "scans_ok": settings["sheets_onglet_scans"] in tabs}


def _values(s, sid, rng, render="FORMATTED_VALUE"):
    d = _get(s, API + sid + "/values/" + rng, valueRenderOption=render)
    return d.get("values", [])


def _col(n):
    """0 -> A, 25 -> Z, 26 -> AA."""
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _norm(h):
    h = (h or "").strip().lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("’", "'")):
        h = h.replace(a, b)
    return re.sub(r"\s*\(.*?\)\s*", "", h).strip()


# en-tête du Google Sheets (normalisé) -> champ de la fiche Valya Scan
HEADER_MAP = {
    "imei": "imei", "reference": "reference", "ref": "reference", "modele": "modele",
    "stockage": "stockage", "etat": "etat", "batterie": "sante_batterie",
    "date d'achat": "date_achat", "date de vente": "date_vente", "prix d'achat": "prix_achat",
    "frais": "frais", "prix vente": "prix_vente", "prix de vente": "prix_vente", "statut": "statut",
}


def _layout(s, settings):
    """Lit la ligne d'en-tête : le tableau peut changer de colonnes, on s'adapte."""
    sid, tab = settings["sheets_id"], _q(settings["sheets_onglet_stock"])
    head = _values(s, sid, "%s!1:1" % tab)
    head = head[0] if head else []
    cols, marge = {}, None
    for i, h in enumerate(head):
        n = _norm(h)
        if n.startswith("marge"):
            marge = i
        elif n in HEADER_MAP and HEADER_MAP[n] not in cols:
            cols[HEADER_MAP[n]] = i
    if "reference" not in cols:
        raise SheetsError("Colonne « Référence » introuvable dans la 1re ligne de l'onglet « %s »." % settings["sheets_onglet_stock"])
    return {"entetes": head, "cols": cols, "marge": marge, "largeur": max(len(head), 1)}


def _row_state(s, settings, lay, row):
    sid, tab = settings["sheets_id"], _q(settings["sheets_onglet_stock"])
    last = _col(lay["largeur"] - 1)
    vals = _values(s, sid, "%s!A%d:%s%d" % (tab, row, last, row))
    vals = (vals[0] if vals else []) + [""] * lay["largeur"]
    formula = ""
    if lay["marge"] is not None:
        f = _values(s, sid, "%s!%s%d" % (tab, _col(lay["marge"]), row), render="FORMULA")
        formula = f[0][0] if f and f[0] else ""
    options = None
    if "statut" in lay["cols"]:
        meta = _get(s, API + sid, ranges="%s!%s%d" % (tab, _col(lay["cols"]["statut"]), row),
                    fields="sheets(data(rowData(values(dataValidation))))")
        options = []
        try:
            cond = meta["sheets"][0]["data"][0]["rowData"][0]["values"][0]["dataValidation"]["condition"]
            options = ([v.get("userEnteredValue") for v in cond.get("values", [])]
                       if cond.get("type") == "ONE_OF_LIST" else ["(liste issue d'une plage)"])
        except (KeyError, IndexError):
            options = []
    return {"valeurs": vals[:lay["largeur"]], "formule_marge": formula, "options_statut": options}


def _fmt_num(v):
    if v is None or v == "":
        return ""
    return float(v) if float(v) != int(float(v)) else int(float(v))


def phone_values(p):
    """Valeurs à écrire, par champ, au format du tableau (stockage « 128 », dates AAAA-MM-JJ)."""
    frais = (p.get("frais") or 0) + (p.get("cout_reparations") or 0)
    sto = re.sub(r"\s*(go|gb)$", "", (p.get("stockage") or "").strip(), flags=re.I)
    if sto.lower().endswith("to"):
        sto = str(int(re.sub(r"\D", "", sto) or 1) * 1024)
    return {
        "imei": p.get("imei") or "", "reference": p.get("reference") or "", "modele": p.get("modele") or "",
        "stockage": sto, "etat": p.get("etat") or "",
        "sante_batterie": "" if p.get("sante_batterie") is None else int(p["sante_batterie"]),
        "date_achat": p.get("date_achat") or "", "date_vente": p.get("date_vente") or "",
        "prix_achat": _fmt_num(p.get("prix_achat")), "frais": _fmt_num(frais) if frais else "",
        "prix_vente": _fmt_num(p.get("prix_vente")), "statut": p.get("statut") or "",
    }


def prepare(settings, phone):
    """Calcule la ligne cible et vérifie qu'on peut écrire. Ne modifie rien."""
    s = _session(settings)
    sid, tab = settings["sheets_id"], _q(settings["sheets_onglet_stock"])
    lay = _layout(s, settings)
    cref = lay["cols"]["reference"]
    cimei = lay["cols"].get("imei")
    data = _values(s, sid, "%s!A1:%s2000" % (tab, _col(lay["largeur"] - 1)))
    cell = lambda r, c: (data[r - 1][c] if len(data) >= r and c is not None and len(data[r - 1]) > c else "").strip()
    mode, row = "ajout", None
    ref, imei = phone.get("reference") or "", phone.get("imei") or ""
    for r in range(2, len(data) + 1):
        if (ref and cell(r, cref) == ref) or (imei and cimei is not None and cell(r, cimei) == imei):
            mode, row = "mise à jour", r
            break
    if row is None:
        key_cols = [c for c in (cref, cimei, lay["cols"].get("modele")) if c is not None]
        row = max(2, len(data) + 1)
        for r in range(2, len(data) + 1):
            if not any(cell(r, c) for c in key_cols):
                row = r
                break
    state = _row_state(s, settings, lay, row)
    vals = phone_values(phone)
    problems = []
    if mode == "ajout" and any(str(state["valeurs"][c]).strip() for c in lay["cols"].values()):
        problems.append("La ligne %d n'est pas vide." % row)
    if lay["marge"] is not None and not str(state["formule_marge"]).startswith("="):
        problems.append("La ligne %d n'a pas de formule dans la colonne Marge (%s) : ajoute-la (copie celle de la ligne 2) puis relance."
                        % (row, _col(lay["marge"])))
    if state["options_statut"] is not None:
        opts = state["options_statut"]
        if not opts:
            problems.append("La ligne %d n'a pas la liste déroulante dans la colonne Statut." % row)
        elif opts[0] != "(liste issue d'une plage)" and vals["statut"] not in opts:
            problems.append("Le statut « %s » n'existe pas dans la liste déroulante (%s)." % (vals["statut"], ", ".join(opts)))
    writes, recap = [], []
    for i, h in enumerate(lay["entetes"]):
        field = next((f for f, c in lay["cols"].items() if c == i), None)
        if i == lay["marge"]:
            recap.append({"colonne": "%s (%s)" % (h, _col(i)), "avant": state["valeurs"][i], "apres": "(formule conservée, non touchée)"})
        elif field:
            writes.append((i, vals[field]))
            recap.append({"colonne": "%s (%s)" % (h, _col(i)), "avant": state["valeurs"][i], "apres": vals[field]})
    return {"mode": mode, "ligne": row, "recap": recap, "problemes": problems, "ecritures": writes}


def write(settings, phone, row, expected_mode):
    """Écrit après validation, en refaisant toutes les vérifications."""
    plan = prepare(settings, phone)
    if plan["ligne"] != row or plan["mode"] != expected_mode:
        raise SheetsError("La feuille a changé depuis le récapitulatif (ligne %s). Rien n'a été écrit : relance l'envoi." % plan["ligne"])
    if plan["problemes"]:
        raise SheetsError("Écriture annulée : " + " ".join(plan["problemes"]))
    s = _session(settings)
    sid, tab = settings["sheets_id"], _q(settings["sheets_onglet_stock"])
    body = {"valueInputOption": "USER_ENTERED", "data": [
        {"range": "%s!%s%d" % (tab, _col(c), row), "values": [[v]]} for c, v in plan["ecritures"]]}
    r = s.post(API + sid + "/values:batchUpdate", json=body, timeout=20)
    if r.status_code != 200:
        raise SheetsError(_err(r))
    lay = _layout(s, settings)
    after = _row_state(s, settings, lay, row)
    check = []
    for c, v in plan["ecritures"]:
        got = str(after["valeurs"][c])
        check.append({"colonne": lay["entetes"][c], "attendu": str(v), "lu": got, "ok": _same(str(v), got)})
    if lay["marge"] is not None:
        check.append({"colonne": "Marge", "attendu": "formule", "lu": after["formule_marge"],
                      "ok": str(after["formule_marge"]).startswith("=")})
    return {"ligne": row, "verification": check, "tout_ok": all(x["ok"] for x in check)}


def _same(want, got):
    if want == got:
        return True
    def norm(x):
        x = x.replace(" ", "").replace("\xa0", "").replace(" ", "").replace("€", "").replace("%", "").replace(",", ".")
        try:
            return float(x)
        except ValueError:
            return x.lower()
    a, b = norm(want), norm(got)
    if a == b:
        return True
    # dates : 2026-10-23 peut être relue 23/10/2026
    for fw in ("%Y-%m-%d", "%d/%m/%Y"):
        for fg in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
            try:
                if datetime.strptime(want, fw) == datetime.strptime(got, fg):
                    return True
            except ValueError:
                pass
    return False


def append_scan(settings, phone, scan):
    """Ajoute une ligne de journal dans l'onglet « scans » (seulement s'il existe et si activé)."""
    s = _session(settings)
    sid, tab = settings["sheets_id"], _q(settings["sheets_onglet_scans"])
    bat = scan.get("batterie") or {}
    row = [scan.get("scanne_le"), phone.get("reference"), scan.get("modele"), scan.get("serie"),
           scan.get("imei"), scan.get("ios"), bat.get("sante"), bat.get("cycles"),
           scan.get("activation"), {True: "Activé", False: "Désactivé"}.get(scan.get("localiser"), "?"),
           scan.get("origine")]
    row = ["" if v is None else v for v in row]
    r = s.post(API + sid + "/values/%s!A1:append" % tab,
               params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
               json={"values": [row]}, timeout=20)
    if r.status_code != 200:
        raise SheetsError(_err(r))
    return True
