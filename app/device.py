# -*- coding: utf-8 -*-
"""Communication avec l'iPhone via les outils libimobiledevice (USB).

Toutes les fonctions renvoient des dictionnaires simples, prêts pour l'interface.
Aucune fonction ici ne contourne une protection (iCloud, code, opérateur) :
elles lisent ce que l'iPhone accepte de donner à un ordinateur de confiance.
"""
import os
import plistlib
import re
import shutil
import subprocess
from datetime import datetime

import models

TOOLS = {
    "idevice_id": "libimobiledevice", "ideviceinfo": "libimobiledevice",
    "idevicepair": "libimobiledevice", "idevicediagnostics": "libimobiledevice",
    "idevicesyslog": "libimobiledevice", "idevicebackup2": "libimobiledevice",
    "idevicecrashreport": "libimobiledevice", "ideviceenterrecovery": "libimobiledevice",
    "idevicename": "libimobiledevice", "irecovery": "libirecovery",
    "idevicerestore": "idevicerestore", "ideviceinstaller": "ideviceinstaller",
}


class DeviceError(Exception):
    pass


def which(name):
    return shutil.which(name)


def tools_status():
    return {name: {"ok": bool(which(name)), "paquet": pkg} for name, pkg in TOOLS.items()}


def run(cmd, timeout=25, check=False):
    if not which(cmd[0]):
        raise DeviceError("Outil « %s » non installé (paquet %s). Relance Valya Scan pour l'installer."
                          % (cmd[0], TOOLS.get(cmd[0], "?")))
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, universal_newlines=True, errors="replace")
    except subprocess.TimeoutExpired:
        raise DeviceError("L'iPhone ne répond pas (délai dépassé pour %s)." % cmd[0])
    if check and p.returncode != 0:
        raise DeviceError((p.stderr or p.stdout or "Erreur %s" % p.returncode).strip())
    return p


def _plist(text):
    if not text:
        return None
    i = text.find("<?xml")
    if i < 0:
        return None
    try:
        return plistlib.loads(text[i:].encode("utf-8"))
    except Exception:
        return None


def _find_key(obj, key):
    """Cherche une clé à n'importe quelle profondeur d'un plist."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_key(v, key)
            if r is not None:
                return r
    return None


# ---------------------------------------------------------------- détection

def list_devices():
    """iPhones branchés en mode normal + éventuel iPhone en mode récupération/DFU."""
    out = {"normal": [], "recovery": None, "erreur": None}
    try:
        p = run(["idevice_id", "-l"], timeout=8)
        out["normal"] = [l.strip() for l in p.stdout.splitlines() if l.strip()]
    except DeviceError as e:
        out["erreur"] = str(e)
    if which("irecovery") and not out["normal"]:
        try:
            p = run(["irecovery", "-q"], timeout=6)
            if p.returncode == 0 and "MODE" in p.stdout:
                info = {}
                for line in p.stdout.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        info[k.strip()] = v.strip()
                pt = info.get("PRODUCT", "")
                info["nom"] = models.product_name(pt)
                out["recovery"] = info
        except DeviceError:
            pass
    return out


def pair_status(udid):
    p = run(["idevicepair", "-u", udid, "validate"], timeout=10)
    if p.returncode == 0:
        return {"ok": True, "message": "Ordinateur de confiance."}
    txt = (p.stdout + p.stderr)
    if "passcode" in txt.lower() or "locked" in txt.lower():
        msg = "Déverrouille l'iPhone puis appuie sur « Se fier » / « Faire confiance »."
    else:
        msg = "L'iPhone n'a pas encore accepté ce Mac. Déverrouille-le et appuie sur « Faire confiance »."
    return {"ok": False, "message": msg, "detail": txt.strip()}


def pair(udid):
    p = run(["idevicepair", "-u", udid, "pair"], timeout=30)
    ok = p.returncode == 0
    return {"ok": ok, "message": (p.stdout + p.stderr).strip() or ("Appairé." if ok else "Échec.")}


# ---------------------------------------------------------------- lecture

def lockdown(udid, domain=None):
    cmd = ["ideviceinfo", "-u", udid, "-x"]
    if domain:
        cmd += ["-q", domain]
    p = run(cmd, timeout=20)
    data = _plist(p.stdout)
    if data is None:
        if domain:
            return {}
        raise DeviceError((p.stderr or p.stdout or "Lecture impossible").strip())
    return data


def lockdown_key(udid, domain, key):
    try:
        p = run(["ideviceinfo", "-u", udid, "-q", domain, "-k", key], timeout=10)
    except DeviceError:
        return None
    if p.returncode != 0:
        return None
    v = p.stdout.strip()
    return v or None


def battery(udid):
    """Santé batterie : capacité max réelle / capacité d'origine, cycles, température."""
    res = {"sante": None, "cycles": None, "capacite_origine": None, "capacite_max": None,
           "temperature": None, "niveau": None, "en_charge": None, "source": None, "serie_batterie": None}
    data = None
    try:
        p = run(["idevicediagnostics", "-u", udid, "ioregentry", "AppleSmartBattery"], timeout=20)
        data = _plist(p.stdout)
        if data:
            res["source"] = "AppleSmartBattery"
    except DeviceError:
        pass
    if not data:
        try:
            p = run(["idevicediagnostics", "-u", udid, "diagnostics", "GasGauge"], timeout=20)
            data = _plist(p.stdout)
            if data:
                res["source"] = "GasGauge"
        except DeviceError:
            pass
    if data:
        design = _find_key(data, "DesignCapacity")
        maxcap = (_find_key(data, "NominalChargeCapacity") or _find_key(data, "AppleRawMaxCapacity")
                  or _find_key(data, "FullChargeCapacity"))
        cycles = _find_key(data, "CycleCount")
        temp = _find_key(data, "Temperature")
        res["capacite_origine"] = design
        res["capacite_max"] = maxcap
        res["cycles"] = cycles
        res["serie_batterie"] = _find_key(data, "Serial") or _find_key(data, "BatterySerialNumber")
        if isinstance(temp, int) and temp > 0:
            res["temperature"] = round(temp / 100.0, 1)
        if isinstance(design, int) and isinstance(maxcap, int) and design > 0:
            res["sante"] = min(100, int(round(maxcap * 100.0 / design)))
    bat = lockdown(udid, "com.apple.mobile.battery")
    if bat:
        res["niveau"] = bat.get("BatteryCurrentCapacity")
        res["en_charge"] = bat.get("BatteryIsCharging")
    return res


def storage(udid):
    d = lockdown(udid, "com.apple.disk_usage")
    total = d.get("TotalDiskCapacity")
    free = d.get("AmountDataAvailable") or d.get("TotalDataAvailable")
    return {
        "total_octets": total, "libre_octets": free,
        "capacite": models.human_storage(total) if total else None,
        "utilise_pct": int(round((1 - float(free) / total) * 100)) if total and free is not None else None,
    }


def full_scan(udid):
    """Diagnostic complet d'un iPhone appairé."""
    info = lockdown(udid)
    pt = info.get("ProductType")
    model_number = info.get("ModelNumber")
    region = info.get("RegionInfo")
    origin, origin_level = models.model_origin(model_number)

    fmip = lockdown_key(udid, "com.apple.fmip", "IsAssociated")
    findmy = None
    if fmip is not None:
        findmy = fmip.lower() in ("true", "1", "yes")

    try:
        bat = battery(udid)
    except DeviceError as e:
        bat = {"erreur": str(e)}
    try:
        sto = storage(udid)
    except DeviceError as e:
        sto = {"erreur": str(e)}

    activation = info.get("ActivationState")
    alerts = []
    if activation and activation not in ("Activated", "FactoryActivated"):
        alerts.append({"niveau": "danger", "texte": "Non activé (%s) : l'iPhone n'est pas utilisable en l'état." % activation})
    if findmy:
        alerts.append({"niveau": "danger", "texte": "Localiser est ACTIVÉ : le vendeur doit se déconnecter d'iCloud avant la vente, sinon l'iPhone restera bloqué après réinitialisation."})
    if findmy is None:
        alerts.append({"niveau": "warn", "texte": "Localiser non lisible par câble sur cet iPhone : vérifie dans Réglages › [nom] › Localiser."})
    if origin_level == "warn":
        alerts.append({"niveau": "warn", "texte": "Origine : %s." % origin})
    if isinstance(bat.get("sante"), int) and bat["sante"] < 80:
        alerts.append({"niveau": "warn", "texte": "Batterie à %s %% : remplacement conseillé (< 80 %%)." % bat["sante"]})
    if isinstance(bat.get("cycles"), int) and bat["cycles"] > 800:
        alerts.append({"niveau": "warn", "texte": "Batterie très utilisée : %s cycles." % bat["cycles"]})

    color_code = str(info.get("DeviceEnclosureColor") or info.get("DeviceColor") or "")
    sim = info.get("SIMStatus")
    verdict = make_verdict(alerts, findmy)

    return {
        "verdict": verdict,
        "udid": udid,
        "scanne_le": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nom_appareil": info.get("DeviceName"),
        "modele": models.product_name(pt),
        "product_type": pt,
        "hardware": info.get("HardwareModel"),
        "numero_modele": (model_number or "") + (region or ""),
        "origine": origin, "origine_niveau": origin_level,
        "region": models.region_name(region),
        "couleur": models.COLOR_HINTS.get(color_code, color_code or None),
        "ios": info.get("ProductVersion"), "build": info.get("BuildVersion"),
        "serie": info.get("SerialNumber"),
        "imei": info.get("InternationalMobileEquipmentIdentity"),
        "imei2": info.get("InternationalMobileEquipmentIdentity2"),
        "meid": info.get("MobileEquipmentIdentifier"),
        "ecid": info.get("UniqueChipID"),
        "wifi": info.get("WiFiAddress"), "bluetooth": info.get("BluetoothAddress"),
        "modem": info.get("BasebandVersion"),
        "activation": activation,
        "localiser": findmy,
        "code_actif": info.get("PasswordProtected"),
        "sim": sim,
        "iccid": info.get("IntegratedCircuitCardIdentity"),
        "batterie": bat,
        "stockage": sto,
        "alertes": alerts,
    }


def make_verdict(alerts, findmy):
    """Résumé en une phrase, pour savoir d'un coup d'œil si on peut acheter / vendre."""
    if any(a["niveau"] == "danger" for a in alerts):
        return {"niveau": "danger", "titre": "Bloqué",
                "texte": "Ne pas acheter / vendre en l'état : le téléphone est lié à un compte ou non activé."}
    if any(a["niveau"] == "warn" for a in alerts) or findmy is None:
        return {"niveau": "warn", "titre": "À vérifier",
                "texte": "Utilisable, mais certains points sont à contrôler (voir ci-dessous)."}
    return {"niveau": "ok", "titre": "OK",
            "texte": "Aucun blocage détecté. Termine par les tests guidés pour valider l'écran, Face ID, caméras…"}


def live(udid):
    """Infos qui bougent (charge en cours) — appelé souvent, donc léger."""
    bat = lockdown(udid, "com.apple.mobile.battery") or {}
    return {"niveau": bat.get("BatteryCurrentCapacity"), "en_charge": bat.get("BatteryIsCharging"),
            "externe": bat.get("ExternalConnected")}


# ---------------------------------------------------------------- actions rapides

def restart(udid):
    run(["idevicediagnostics", "-u", udid, "restart"], check=True)


def shutdown(udid):
    run(["idevicediagnostics", "-u", udid, "shutdown"], check=True)


def enter_recovery(udid):
    run(["ideviceenterrecovery", udid], timeout=30, check=True)


def exit_recovery():
    run(["irecovery", "-n"], timeout=30, check=True)


def rename(udid, name):
    run(["idevicename", "-u", udid, name], check=True)


def apps(udid):
    """Liste des apps installées par l'utilisateur."""
    for cmd in (["ideviceinstaller", "-u", udid, "list", "--user"],
                ["ideviceinstaller", "-u", udid, "-l", "-o", "list_user"],
                ["ideviceinstaller", "-u", udid, "-l"]):
        try:
            p = run(cmd, timeout=60)
        except DeviceError:
            raise
        if p.returncode == 0 and p.stdout.strip():
            out = []
            for line in p.stdout.splitlines():
                line = line.strip()
                if not line or line.lower().startswith(("total", "cfbundleidentifier")):
                    continue
                m = re.match(r'^([\w.\-]+)[,\s-]+\s*"?([^",]*)"?\s*,?\s*"?([^"]*)"?', line)
                if m:
                    out.append({"id": m.group(1), "version": m.group(2).strip(), "nom": m.group(3).strip() or m.group(1)})
            return out
    return []


def crash_dir(base, serial):
    d = os.path.join(base, "Rapports-plantage", serial or "inconnu")
    os.makedirs(d, exist_ok=True)
    return d


def summarize_crashes(folder):
    """Repère les « panic » (souvent signe d'une pièce défectueuse) dans les rapports récupérés."""
    panics, others = [], 0
    for root, _, files in os.walk(folder):
        for f in files:
            path = os.path.join(root, f)
            if "panic" in f.lower():
                reason = ""
                try:
                    with open(path, "r", errors="replace") as fh:
                        txt = fh.read(20000)
                    m = re.search(r'panicString\\?"?\s*:\s*\\?"((?:[^"\\]|\\.){0,240})', txt)
                    if m:
                        reason = m.group(1)
                    else:
                        m = re.search(r"panic\(cpu \d+ caller [^)]*\):\s*(.{0,200})", txt)
                        reason = m.group(1) if m else ""
                except Exception:
                    pass
                panics.append({"fichier": f, "raison": reason.replace("\\n", " ").strip()})
            else:
                others += 1
    hints = []
    joined = " ".join(p["raison"] for p in panics).lower()
    for key, hint in (("mic", "micro / nappe de charge"), ("prox", "capteur de proximité / nappe Face ID"),
                      ("thermalmonitord", "capteur de température (souvent nappe de charge ou batterie)"),
                      ("i2c", "bus I2C : nappe ou composant mal branché"), ("smc", "gestion d'alimentation"),
                      ("watchdog", "blocage système (watchdog)"), ("nand", "mémoire de stockage"),
                      ("baseband", "modem / réseau")):
        if key in joined:
            hints.append(hint)
    return {"panics": panics[:50], "nb_panics": len(panics), "nb_autres": others, "pistes": hints}


# ---------------------------------------------------------------- fiche technique complète

DOMAINS = [
    None, "com.apple.disk_usage", "com.apple.disk_usage.factory", "com.apple.mobile.battery",
    "com.apple.mobile.internal", "com.apple.international", "com.apple.fmip", "com.apple.mobile.iTunes",
    "com.apple.mobile.wireless_lockdown", "com.apple.mobile.data_sync", "com.apple.mobile.restriction",
    "com.apple.mobile.backup", "com.apple.PurpleBuddy", "com.apple.purplebuddy", "com.apple.mobile.chaperone",
    "com.apple.mobile.software_behavior", "com.apple.mobile.lockdown_cache", "com.apple.mobile.tethered_sync",
    "com.apple.xcode.developerdomain", "com.apple.mobile.sync_data_class", "com.apple.fairplay",
    "com.apple.iqagent", "com.apple.mobile.third_party_termination", "com.apple.mobile.ldwatch",
]

GESTALT_KEYS = ["MLBSerialNumber", "BasebandSerialNumber", "RegionalBehaviorAll", "ScreenDimensions",
                "main-screen-class", "ArtworkDeviceProductDescription", "DeviceColorRGB", "HWModelStr",
                "ChipID", "BoardId", "DieId", "BatteryCurrentCapacity", "BatteryIsFullyCharged",
                "WifiVendor", "BluetoothAddress", "RearFacingCameraCapability", "FrontFacingCameraCapability"]


def _clean(v):
    """Rend un plist affichable : bytes -> hexa, dates -> texte."""
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, bytes):
        return v.hex() if len(v) <= 64 else "(%d octets) %s…" % (len(v), v[:32].hex())
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v


def raw_dump(udid):
    """Tout ce que l'iPhone accepte de donner : chaque domaine lockdown, la batterie (registre IO),
    les diagnostics matériels et MobileGestalt."""
    out = {}
    for dom in DOMAINS:
        try:
            data = lockdown(udid, dom)
        except DeviceError:
            data = {}
        if data:
            out[dom or "Général (lockdown)"] = _clean(data)
    for entry in ("AppleSmartBattery", "AppleARMPMUCharger", "AppleAuthCP"):
        try:
            p = run(["idevicediagnostics", "-u", udid, "ioregentry", entry], timeout=20)
            d = _plist(p.stdout)
            if d:
                out["Registre IO : " + entry] = _clean(d)
        except DeviceError:
            pass
    for diag in ("All",):
        try:
            p = run(["idevicediagnostics", "-u", udid, "diagnostics", diag], timeout=25)
            d = _plist(p.stdout)
            if d:
                out["Diagnostics matériels"] = _clean(d)
        except DeviceError:
            pass
    try:
        p = run(["idevicediagnostics", "-u", udid, "mobilegestalt"] + GESTALT_KEYS, timeout=20)
        d = _plist(p.stdout)
        if d:
            out["MobileGestalt"] = _clean(d)
    except DeviceError:
        pass
    return out


def _g(raw, key, *domains):
    for dom in domains or ("Général (lockdown)",):
        v = _find_key(raw.get(dom, {}), key)
        if v not in (None, ""):
            return v
    return None


def technical_sheet(udid):
    """Fiche technique lisible (en français) + données brutes complètes."""
    raw = raw_dump(udid)
    G = "Général (lockdown)"
    bat_dom = ["Registre IO : AppleSmartBattery", "Diagnostics matériels", "com.apple.mobile.battery"]
    pt = _g(raw, "ProductType")
    mg = raw.get("MobileGestalt", {})
    mgv = lambda k: (_find_key(mg, k) if not isinstance(_find_key(mg, k), str) or "Deprecated" not in _find_key(mg, k) else None)
    design = _g(raw, "DesignCapacity", *bat_dom)
    maxc = _g(raw, "NominalChargeCapacity", *bat_dom) or _g(raw, "AppleRawMaxCapacity", *bat_dom)
    temp = _g(raw, "Temperature", *bat_dom)
    volt = _g(raw, "Voltage", *bat_dom)
    amp = _g(raw, "InstantAmperage", *bat_dom) or _g(raw, "Amperage", *bat_dom)
    disk = raw.get("com.apple.disk_usage", {})
    gb = lambda x: ("%.1f Go" % (float(x) / 1e9)) if isinstance(x, (int, float)) else None
    model_number = _g(raw, "ModelNumber")
    region = _g(raw, "RegionInfo")

    sections = [
        ("Identité de l'appareil", [
            ("Modèle", models.product_name(pt)), ("Identifiant Apple", pt), ("Nom", _g(raw, "DeviceName")),
            ("Numéro de série", _g(raw, "SerialNumber")), ("IMEI", _g(raw, "InternationalMobileEquipmentIdentity")),
            ("IMEI 2", _g(raw, "InternationalMobileEquipmentIdentity2")), ("MEID", _g(raw, "MobileEquipmentIdentifier")),
            ("UDID", _g(raw, "UniqueDeviceID")), ("Référence commerciale", (model_number or "") + (region or "")),
            ("Origine (1re lettre de la référence)", models.model_origin(model_number)[0]),
            ("Région de vente", models.region_name(region)), ("Code couleur coque", _g(raw, "DeviceEnclosureColor")),
            ("Code couleur façade", _g(raw, "DeviceColor")),
        ]),
        ("Carte mère & puce", [
            ("N° de série carte mère (MLB)", _g(raw, "MLBSerialNumber") or mgv("MLBSerialNumber")),
            ("Modèle de carte (HardwareModel)", _g(raw, "HardwareModel")), ("Plateforme (SoC)", _g(raw, "HardwarePlatform")),
            ("Chip ID", _g(raw, "ChipID")), ("Board ID", _g(raw, "BoardId")), ("ECID (identifiant unique de la puce)", _g(raw, "UniqueChipID")),
            ("Die ID", _g(raw, "DieID")), ("Architecture", _g(raw, "CPUArchitecture")),
            ("Puce de production", _g(raw, "ProductionSOC")), ("Bootloader (iBoot)", _g(raw, "FirmwareVersion")),
        ]),
        ("Système", [
            ("Version iOS", _g(raw, "ProductVersion")), ("Build", _g(raw, "BuildVersion")),
            ("État d'activation", _g(raw, "ActivationState")),
            ("Localiser (Find My)", {True: "ACTIVÉ", False: "Désactivé"}.get(_g(raw, "IsAssociated", "com.apple.fmip"), "Non lisible")),
            ("Code de verrouillage", "Oui" if _g(raw, "PasswordProtected") else "Non"),
            ("Langue", _g(raw, "Language", "com.apple.international")), ("Région / format", _g(raw, "Locale", "com.apple.international")),
            ("Fuseau horaire", _g(raw, "TimeZone")), ("Mode développeur", _g(raw, "DeveloperStatus", "com.apple.xcode.developerdomain")),
            ("Ordinateur de confiance", "Oui" if _g(raw, "TrustedHostAttached") else None),
        ]),
        ("Réseau & modem", [
            ("Firmware modem", _g(raw, "BasebandVersion")), ("N° de série modem", _g(raw, "BasebandSerialNumber") or mgv("BasebandSerialNumber")),
            ("Puce modem", _g(raw, "BasebandChipID")), ("Statut SIM", (_g(raw, "SIMStatus") or "").replace("kCTSIMSupportSIMStatus", "") or None),
            ("ICCID (carte SIM)", _g(raw, "IntegratedCircuitCardIdentity")),
            ("Opérateur de la SIM", _find_key(_g(raw, "CarrierBundleInfoArray") or {}, "CFBundleIdentifier")),
            ("Adresse Wi-Fi", _g(raw, "WiFiAddress")), ("Adresse Bluetooth", _g(raw, "BluetoothAddress")),
        ]),
        ("Batterie (données de la puce de charge)", [
            ("Santé (capacité max / origine)", ("%d %%" % round(maxc * 100.0 / design)) if isinstance(design, int) and isinstance(maxc, int) and design else None),
            ("Cycles de charge", _g(raw, "CycleCount", *bat_dom)), ("Capacité d'origine", design and "%s mAh" % design),
            ("Capacité max actuelle", maxc and "%s mAh" % maxc), ("Capacité brute (AppleRawMaxCapacity)", _g(raw, "AppleRawMaxCapacity", *bat_dom)),
            ("N° de série batterie", _g(raw, "Serial", *bat_dom) or _g(raw, "BatterySerialNumber", *bat_dom)),
            ("Fabricant / date (code)", _g(raw, "ManufactureDate", *bat_dom) or _g(raw, "ManufacturerData", *bat_dom)),
            ("Température", ("%.1f °C" % (temp / 100.0)) if isinstance(temp, int) and temp > 0 else None),
            ("Tension", ("%.2f V" % (volt / 1000.0)) if isinstance(volt, int) and volt > 0 else None),
            ("Courant instantané", amp and "%s mA" % amp), ("Charge actuelle", _g(raw, "BatteryCurrentCapacity", "com.apple.mobile.battery")),
            ("En charge", "Oui" if _g(raw, "BatteryIsCharging", "com.apple.mobile.battery") else "Non"),
            ("Chargeur branché", "Oui" if _g(raw, "ExternalConnected", *bat_dom) else None),
        ]),
        ("Stockage", [
            ("Capacité totale", gb(disk.get("TotalDiskCapacity"))), ("Partition système", gb(disk.get("TotalSystemCapacity"))),
            ("Espace données", gb(disk.get("TotalDataCapacity"))), ("Libre", gb(disk.get("AmountDataAvailable") or disk.get("TotalDataAvailable"))),
            ("Réservé", gb(disk.get("AmountDataReserved"))), ("Type de mémoire", disk.get("NANDInfo") and "NAND"),
        ]),
    ]
    sections = [{"titre": t, "lignes": [{"cle": k, "valeur": v} for k, v in rows if v not in (None, "", "None")]}
                for t, rows in sections]
    serial = _g(raw, "SerialNumber")
    imei = _g(raw, "InternationalMobileEquipmentIdentity")
    return {"sections": sections, "brut": raw, "serie": serial, "imei": imei, "product_type": pt,
            "ios": _g(raw, "ProductVersion"), "build": _g(raw, "BuildVersion"), "lu_le": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


_fw_cache = {}


def latest_signed(product_type):
    """Versions d'iOS encore signées par Apple pour ce modèle (via api.ipsw.me)."""
    import json
    import time
    import urllib.request
    if not product_type:
        return None
    c = _fw_cache.get(product_type)
    if c and c[0] > time.time() - 3600:
        return c[1]
    try:
        req = urllib.request.Request("https://api.ipsw.me/v4/device/%s?type=ipsw" % product_type,
                                     headers={"User-Agent": "ValyaScan"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode("utf-8"))
        signed = [{"version": f["version"], "build": f["buildid"], "taille": f.get("filesize"),
                   "date": (f.get("releasedate") or "")[:10]} for f in d.get("firmwares", []) if f.get("signed")]
        res = {"nom": d.get("name"), "signees": signed}
    except Exception as e:
        res = {"erreur": "Impossible de vérifier les versions iOS en ligne (%s)." % e.__class__.__name__, "signees": []}
    _fw_cache[product_type] = (time.time(), res)
    return res
