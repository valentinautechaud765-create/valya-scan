#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VALYA SCAN — v1
Détection et diagnostic d'iPhone pour l'achat-revente et la réparation.

Branche un iPhone en USB, ouvre http://127.0.0.1:5000 dans Safari.
L'app affiche le modèle, iOS, le numéro de série, l'IMEI, la batterie
et l'état d'activation, et te permet d'enregistrer une fiche de stock.

Repose sur libimobiledevice (gratuit, open source).
Installation : voir les instructions fournies avec le fichier.
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime

try:
    from flask import Flask, jsonify, request, render_template_string
except ImportError:
    raise SystemExit(
        "Flask n'est pas installé. Lance dans le Terminal :\n"
        "    pip3 install flask\n"
        "puis relance :  python3 valya_scan.py"
    )

app = Flask(__name__)

# Fichier où sont enregistrées les fiches de stock (à côté du script)
STOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock_valya.json")

# ---------------------------------------------------------------------------
# Correspondance ProductType -> nom commercial
# (couvre les iPhone courants ; un modèle inconnu s'affiche avec son code brut)
# ---------------------------------------------------------------------------
MODELES = {
    "iPhone8,1": "iPhone 6s",
    "iPhone8,2": "iPhone 6s Plus",
    "iPhone8,4": "iPhone SE (1re gén.)",
    "iPhone9,1": "iPhone 7",
    "iPhone9,3": "iPhone 7",
    "iPhone9,2": "iPhone 7 Plus",
    "iPhone9,4": "iPhone 7 Plus",
    "iPhone10,1": "iPhone 8",
    "iPhone10,4": "iPhone 8",
    "iPhone10,2": "iPhone 8 Plus",
    "iPhone10,5": "iPhone 8 Plus",
    "iPhone10,3": "iPhone X",
    "iPhone10,6": "iPhone X",
    "iPhone11,2": "iPhone XS",
    "iPhone11,4": "iPhone XS Max",
    "iPhone11,6": "iPhone XS Max",
    "iPhone11,8": "iPhone XR",
    "iPhone12,1": "iPhone 11",
    "iPhone12,3": "iPhone 11 Pro",
    "iPhone12,5": "iPhone 11 Pro Max",
    "iPhone12,8": "iPhone SE (2e gén.)",
    "iPhone13,1": "iPhone 12 mini",
    "iPhone13,2": "iPhone 12",
    "iPhone13,3": "iPhone 12 Pro",
    "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,4": "iPhone 13 mini",
    "iPhone14,5": "iPhone 13",
    "iPhone14,2": "iPhone 13 Pro",
    "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,6": "iPhone SE (3e gén.)",
    "iPhone14,7": "iPhone 14",
    "iPhone14,8": "iPhone 14 Plus",
    "iPhone15,2": "iPhone 14 Pro",
    "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 15",
    "iPhone15,5": "iPhone 15 Plus",
    "iPhone16,1": "iPhone 15 Pro",
    "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone17,3": "iPhone 16",
    "iPhone17,4": "iPhone 16 Plus",
    "iPhone17,1": "iPhone 16 Pro",
    "iPhone17,2": "iPhone 16 Pro Max",
}


def outil_dispo(nom):
    """Vérifie qu'un binaire libimobiledevice est présent."""
    return shutil.which(nom) is not None


def lancer(cmd, timeout=15):
    """Exécute une commande et renvoie (code, sortie_texte)."""
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except FileNotFoundError:
        return 1, "outil introuvable"


def lister_devices():
    """Renvoie la liste des UDID des iPhone branchés en USB."""
    code, out = lancer(["idevice_id", "-l"])
    if code != 0:
        return []
    return [u.strip() for u in out.splitlines() if u.strip()]


def info_brute(udid, domaine=None):
    """Appelle ideviceinfo et renvoie un dict clé -> valeur."""
    cmd = ["ideviceinfo", "-u", udid]
    if domaine:
        cmd += ["-q", domaine]
    code, out = lancer(cmd)
    if code != 0:
        return {}
    d = {}
    for ligne in out.splitlines():
        if ": " in ligne:
            k, v = ligne.split(": ", 1)
            d[k.strip()] = v.strip()
    return d


def interpreter_activation(etat):
    """Traduit l'état d'activation en statut lisible pour l'achat."""
    if not etat:
        return ("Inconnu", "warn",
                "Impossible de lire l'état — vérifie à la main dans Réglages.")
    e = etat.lower()
    if e == "unactivated":
        return ("Non activé — écran de configuration",
                "ok",
                "L'iPhone est sur l'écran de démarrage. Avance jusqu'à voir si "
                "un verrouillage d'activation (iCloud) est demandé.")
    if e in ("activated", "factoryactivated"):
        return ("Activé",
                "warn",
                "Le téléphone est déjà configuré. Le statut Localiser/iCloud "
                "ne se lit pas de façon fiable ici : fais-toi déconnecter l'iCloud "
                "devant toi (Réglages > [nom] > Déconnexion) avant de payer.")
    return (etat, "warn", "État non reconnu — vérifie dans Réglages.")


def scanner():
    """Scan complet du premier iPhone branché."""
    if not outil_dispo("idevice_id") or not outil_dispo("ideviceinfo"):
        return {"erreur": "outils_manquants"}

    udids = lister_devices()
    if not udids:
        return {"present": False}

    udid = udids[0]
    base = info_brute(udid)
    if not base:
        # Branché mais pas encore approuvé ("Faire confiance" sur l'iPhone)
        return {"present": True, "confiance": False, "udid": udid}

    batt = info_brute(udid, "com.apple.mobile.battery")

    ptype = base.get("ProductType", "")
    modele = MODELES.get(ptype, ptype or "Modèle inconnu")

    etat_label, etat_niveau, etat_note = interpreter_activation(
        base.get("ActivationState", "")
    )

    niveau_batt = batt.get("BatteryCurrentCapacity", "")

    fiche = {
        "present": True,
        "confiance": True,
        "udid": udid,
        "modele": modele,
        "product_type": ptype,
        "nom": base.get("DeviceName", ""),
        "ios": base.get("ProductVersion", ""),
        "build": base.get("BuildVersion", ""),
        "serie": base.get("SerialNumber", ""),
        "imei": base.get("InternationalMobileEquipmentIdentity", ""),
        "imei2": base.get("InternationalMobileEquipmentIdentity2", ""),
        "capacite": base.get("TotalDiskCapacity_lisible", formater_stockage(base)),
        "batterie_charge": f"{niveau_batt} %" if niveau_batt else "non lu",
        "activation_label": etat_label,
        "activation_niveau": etat_niveau,
        "activation_note": etat_note,
        "scan_date": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    return fiche


def formater_stockage(base):
    """Convertit la capacité disque en Go lisible si disponible."""
    brut = base.get("TotalDiskCapacity")
    if not brut:
        return "non lu"
    try:
        go = int(brut) / (1000 ** 3)
        # Arrondi vers la capacité commerciale la plus proche
        for seuil in (32, 64, 128, 256, 512, 1024):
            if go <= seuil * 1.05:
                return f"{seuil} Go" if seuil < 1024 else "1 To"
        return f"{round(go)} Go"
    except ValueError:
        return "non lu"


def charger_stock():
    if not os.path.exists(STOCK_FILE):
        return []
    try:
        with open(STOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def sauver_stock(liste):
    with open(STOCK_FILE, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Interface web
# ---------------------------------------------------------------------------
PAGE = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Valya Scan</title>
<style>
  :root {
    --bg: #0e1116; --card: #171b22; --line: #262c36;
    --txt: #e8eaed; --muted: #9aa4b2; --accent: #4f8cff;
    --ok: #35c66b; --warn: #e7b53c; --bad: #ef5a5a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--txt);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .wrap { max-width: 760px; margin: 0 auto; padding: 24px 16px 64px; }
  header { display: flex; align-items: baseline; gap: 10px; margin-bottom: 20px; }
  header h1 { font-size: 22px; margin: 0; letter-spacing: .5px; }
  header span { color: var(--muted); font-size: 13px; }
  .card {
    background: var(--card); border: 1px solid var(--line);
    border-radius: 14px; padding: 20px; margin-bottom: 16px;
  }
  .statut { font-size: 15px; color: var(--muted); }
  .badge {
    display: inline-block; padding: 4px 11px; border-radius: 999px;
    font-size: 13px; font-weight: 600;
  }
  .badge.ok { background: rgba(53,198,107,.15); color: var(--ok); }
  .badge.warn { background: rgba(231,181,60,.15); color: var(--warn); }
  .badge.bad { background: rgba(239,90,90,.15); color: var(--bad); }
  .modele { font-size: 26px; font-weight: 700; margin: 2px 0 2px; }
  .grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px 20px;
    margin-top: 16px;
  }
  .grid div { border-bottom: 1px solid var(--line); padding-bottom: 8px; }
  .k { color: var(--muted); font-size: 12px; text-transform: uppercase;
       letter-spacing: .4px; }
  .v { font-size: 16px; margin-top: 2px; word-break: break-all; }
  .note {
    margin-top: 16px; padding: 12px 14px; border-radius: 10px;
    background: rgba(79,140,255,.08); border: 1px solid rgba(79,140,255,.25);
    font-size: 14px; line-height: 1.5; color: #cfd8e6;
  }
  button {
    background: var(--accent); color: #fff; border: 0; border-radius: 10px;
    padding: 12px 18px; font-size: 15px; font-weight: 600; cursor: pointer;
    margin-top: 16px;
  }
  button:active { opacity: .8; }
  input {
    background: #0e1116; border: 1px solid var(--line); color: var(--txt);
    border-radius: 8px; padding: 10px; font-size: 14px; width: 100%;
    margin-top: 6px;
  }
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .stock-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 14px;
  }
  .stock-item small { color: var(--muted); }
  .vide { color: var(--muted); font-size: 14px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>VALYA SCAN</h1><span>diagnostic iPhone · v1</span>
  </header>

  <div class="card" id="zone">
    <div class="statut">Recherche d'un iPhone branché…</div>
  </div>

  <div class="card">
    <div class="k" style="margin-bottom:10px;">Stock enregistré</div>
    <div id="stock"><span class="vide">Chargement…</span></div>
  </div>
</div>

<script>
let ficheActuelle = null;

async function scan() {
  try {
    const r = await fetch('/api/scan');
    const d = await r.json();
    afficher(d);
  } catch (e) {
    document.getElementById('zone').innerHTML =
      '<div class="statut">Erreur de connexion à l\\'app.</div>';
  }
}

function ligne(k, v) {
  if (!v) return '';
  return `<div><div class="k">${k}</div><div class="v">${v}</div></div>`;
}

function afficher(d) {
  const z = document.getElementById('zone');

  if (d.erreur === 'outils_manquants') {
    z.innerHTML = '<div class="statut">⚠️ libimobiledevice n\\'est pas installé. '
      + 'Voir les instructions d\\'installation.</div>';
    return;
  }
  if (!d.present) {
    z.innerHTML = '<div class="statut">🔌 Aucun iPhone détecté. '
      + 'Branche un iPhone en USB.</div>';
    ficheActuelle = null;
    return;
  }
  if (d.present && d.confiance === false) {
    z.innerHTML = '<div class="statut">📱 iPhone détecté mais non approuvé. '
      + 'Déverrouille-le et appuie sur <b>Faire confiance</b>.</div>';
    ficheActuelle = null;
    return;
  }

  ficheActuelle = d;
  const bNiv = d.activation_niveau || 'warn';

  z.innerHTML = `
    <div class="modele">${d.modele}</div>
    <span class="badge ${bNiv}">${d.activation_label}</span>
    <div class="grid">
      ${ligne('iOS', d.ios + (d.build ? ' ('+d.build+')' : ''))}
      ${ligne('Capacité', d.capacite)}
      ${ligne('Batterie (charge)', d.batterie_charge)}
      ${ligne('N° de série', d.serie)}
      ${ligne('IMEI', d.imei)}
      ${ligne('IMEI 2', d.imei2)}
      ${ligne('Nom', d.nom)}
    </div>
    <div class="note">${d.activation_note}</div>
    <div style="margin-top:18px;">
      <div class="row2">
        <div><div class="k">Prix d'achat (€)</div>
          <input id="prix" type="number" placeholder="ex : 120"></div>
        <div><div class="k">Note</div>
          <input id="note" type="text" placeholder="écran OK, dos rayé…"></div>
      </div>
      <button onclick="enregistrer()">Enregistrer la fiche dans le stock</button>
    </div>
  `;
}

async function enregistrer() {
  if (!ficheActuelle) return;
  const prix = document.getElementById('prix').value;
  const note = document.getElementById('note').value;
  const payload = Object.assign({}, ficheActuelle, {prix_achat: prix, note_etat: note});
  const r = await fetch('/api/enregistrer', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  if (r.ok) { chargerStock(); }
}

async function chargerStock() {
  const r = await fetch('/api/stock');
  const liste = await r.json();
  const el = document.getElementById('stock');
  if (!liste.length) { el.innerHTML = '<span class="vide">Aucune fiche enregistrée.</span>'; return; }
  el.innerHTML = liste.slice().reverse().map(f => `
    <div class="stock-item">
      <div><b>${f.modele}</b> · ${f.capacite || ''}
        <small>${f.imei ? '· IMEI '+f.imei : ''}</small><br>
        <small>${f.scan_date}${f.prix_achat ? ' · acheté '+f.prix_achat+'€' : ''}${f.note_etat ? ' · '+f.note_etat : ''}</small>
      </div>
      <span class="badge ${f.activation_niveau||'warn'}">${f.activation_label||''}</span>
    </div>
  `).join('');
}

scan();
setInterval(scan, 3000);
chargerStock();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/api/scan")
def api_scan():
    return jsonify(scanner())


@app.route("/api/stock")
def api_stock():
    return jsonify(charger_stock())


@app.route("/api/enregistrer", methods=["POST"])
def api_enregistrer():
    fiche = request.get_json(force=True)
    liste = charger_stock()
    liste.append(fiche)
    sauver_stock(liste)
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("\n  VALYA SCAN — ouvre http://127.0.0.1:5000 dans Safari")
    print("  (Ctrl+C pour arrêter)\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
