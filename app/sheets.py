# -*- coding: utf-8 -*-
"""Synchronisation avec le Google Sheets de stock (celui que lit STOCKFLOW).

Règles appliquées (les tiennes) :
- rien n'est écrit sans que tu aies validé le récapitulatif complet dans l'app ;
- on n'écrit que dans les colonnes A à I et K, jamais dans J (Marge) ;
- avant d'écrire : la ligne cible doit avoir une Référence vide (ou la même référence
  pour une mise à jour), une formule en J et une liste déroulante en K, sinon on s'arrête ;
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
COLS_AI = ["Référence", "Modèle", "Stockage", "État", "Batterie (%)", "Date d'achat",
           "Prix d'achat (€)", "frais (€)", "Prix vente (€)"]
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


def _row_state(s, settings, row):
    sid, tab = settings["sheets_id"], _q(settings["sheets_onglet_stock"])
    vals = _values(s, sid, "%s!A%d:K%d" % (tab, row, row))
    vals = (vals[0] if vals else []) + [""] * 11
    formula = _values(s, sid, "%s!J%d" % (tab, row), render="FORMULA")
    formula = formula[0][0] if formula and formula[0] else ""
    meta = _get(s, API + sid, ranges="%s!K%d" % (tab, row),
                fields="sheets(data(rowData(values(dataValidation))))")
    options = []
    try:
        dv = meta["sheets"][0]["data"][0]["rowData"][0]["values"][0]["dataValidation"]
        cond = dv["condition"]
        if cond.get("type") == "ONE_OF_LIST":
            options = [v.get("userEnteredValue") for v in cond.get("values", [])]
        else:
            options = ["(liste issue d'une plage)"]
    except (KeyError, IndexError):
        options = []
    return {"valeurs": vals[:11], "formule_marge": formula, "options_statut": options}


def _fmt_num(v):
    if v is None or v == "":
        return ""
    return float(v) if float(v) != int(float(v)) else int(float(v))


def phone_to_row(p):
    date = p.get("date_achat") or ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date)
    if m:
        date = "%s/%s/%s" % (m.group(3), m.group(2), m.group(1))
    frais = (p.get("frais") or 0) + (p.get("cout_reparations") or 0)
    return [p.get("reference") or "", p.get("modele") or "", p.get("stockage") or "",
            p.get("etat") or "", "" if p.get("sante_batterie") is None else int(p["sante_batterie"]),
            date, _fmt_num(p.get("prix_achat")), _fmt_num(frais) if frais else "",
            _fmt_num(p.get("prix_vente"))], p.get("statut") or ""


def prepare(settings, phone):
    """Calcule la ligne cible et vérifie qu'on peut écrire. Ne modifie rien."""
    s = _session(settings)
    sid, tab = settings["sheets_id"], _q(settings["sheets_onglet_stock"])
    col_a = _values(s, sid, "%s!A1:A2000" % tab)
    mode, row = "ajout", None
    if phone.get("sheets_ligne"):
        r = phone["sheets_ligne"]
        cur = col_a[r - 1][0] if len(col_a) >= r and col_a[r - 1] else ""
        if cur == phone.get("reference"):
            mode, row = "mise à jour", r
    if row is None:
        for ref_row, cells in enumerate(col_a, start=1):
            if ref_row > 1 and cells and cells[0] == phone.get("reference"):
                mode, row = "mise à jour", ref_row
                break
    if row is None:
        row = 2
        for i, cells in enumerate(col_a, start=1):
            if i == 1:
                continue
            if not cells or not str(cells[0]).strip():
                row = i
                break
        else:
            row = max(2, len(col_a) + 1)
    state = _row_state(s, settings, row)
    values, statut = phone_to_row(phone)
    problems = []
    if mode == "ajout" and str(state["valeurs"][0]).strip():
        problems.append("La ligne %d n'est pas vide (Référence = %s)." % (row, state["valeurs"][0]))
    if not str(state["formule_marge"]).startswith("="):
        problems.append("La ligne %d n'a pas la formule de Marge en colonne J." % row)
    if not state["options_statut"]:
        problems.append("La ligne %d n'a pas la liste déroulante de Statut en colonne K." % row)
    elif state["options_statut"][0] != "(liste issue d'une plage)" and statut not in state["options_statut"]:
        problems.append("Le statut « %s » n'existe pas dans la liste déroulante (%s)." %
                        (statut, ", ".join(state["options_statut"])))
    recap = [{"colonne": c, "avant": state["valeurs"][i], "apres": values[i]} for i, c in enumerate(COLS_AI)]
    recap.append({"colonne": "Marge (€) — J", "avant": state["valeurs"][9], "apres": "(formule conservée, non touchée)"})
    recap.append({"colonne": "Statut", "avant": state["valeurs"][10], "apres": statut})
    return {"mode": mode, "ligne": row, "recap": recap, "problemes": problems,
            "valeurs": values, "statut": statut}


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
        {"range": "%s!A%d:I%d" % (tab, row, row), "values": [plan["valeurs"]]},
        {"range": "%s!K%d" % (tab, row), "values": [[plan["statut"]]]},
    ]}
    r = s.post(API + sid + "/values:batchUpdate", json=body, timeout=20)
    if r.status_code != 200:
        raise SheetsError(_err(r))
    after = _row_state(s, settings, row)
    check = []
    for i, c in enumerate(COLS_AI):
        want, got = str(plan["valeurs"][i]), str(after["valeurs"][i])
        ok = _same(want, got)
        check.append({"colonne": c, "attendu": want, "lu": got, "ok": ok})
    check.append({"colonne": "Statut", "attendu": plan["statut"], "lu": after["valeurs"][10],
                  "ok": plan["statut"] == after["valeurs"][10]})
    check.append({"colonne": "Marge (J)", "attendu": "formule", "lu": after["formule_marge"],
                  "ok": str(after["formule_marge"]).startswith("=")})
    return {"ligne": row, "verification": check, "tout_ok": all(c["ok"] for c in check)}


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
    # dates : 23/10/2026 peut être relu 23/10/26
    try:
        return datetime.strptime(want, "%d/%m/%Y") == datetime.strptime(got, "%d/%m/%y")
    except ValueError:
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
