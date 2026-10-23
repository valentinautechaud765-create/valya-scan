# -*- coding: utf-8 -*-
"""Valya Scan — serveur local (http://127.0.0.1:5757)."""
import csv
import io
import os
import sys
import threading
import webbrowser

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import db  # noqa: E402
import device  # noqa: E402
import jobs  # noqa: E402
import sheets  # noqa: E402

VERSION = "4.0.1"
PORT = int(os.environ.get("VALYA_PORT", "5757"))

app = Flask(__name__, static_folder=os.path.join(HERE, "static"), template_folder=os.path.join(HERE, "templates"))
app.config["JSON_AS_ASCII"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
db.init()

FIRMWARE_DIR = os.path.join(db.DATA_DIR, "Firmwares")
BACKUP_DIR = os.path.join(db.DATA_DIR, "Sauvegardes")


def ok(**kw):
    kw.setdefault("ok", True)
    return jsonify(kw)


def fail(msg, code=400, **kw):
    kw.update({"ok": False, "erreur": msg})
    return jsonify(kw), code


@app.errorhandler(device.DeviceError)
def _dev_err(e):
    return fail(str(e), 409)


@app.errorhandler(sheets.SheetsError)
def _sheet_err(e):
    return fail(str(e), 409)


@app.errorhandler(ValueError)
def _val_err(e):
    return fail(str(e), 400)


@app.route("/")
def index():
    # numéro de version dans les liens : le navigateur recharge bien la nouvelle interface après une mise à jour
    with open(os.path.join(app.static_folder, "index.html"), "r", encoding="utf-8") as f:
        html = f.read().replace(".css\"", ".css?v=%s\"" % VERSION).replace(".js\"", ".js?v=%s\"" % VERSION)
    return Response(html, mimetype="text/html", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ appareil

@app.route("/api/status")
def status():
    devs = device.list_devices()
    pairing = {}
    for udid in devs["normal"]:
        try:
            pairing[udid] = device.pair_status(udid)
        except device.DeviceError as e:
            pairing[udid] = {"ok": False, "message": str(e)}
    busy = [j.to_dict(since=10 ** 9) for j in jobs.running()]
    return ok(version=VERSION, appareils=devs, appairage=pairing, outils=device.tools_status(), taches_en_cours=busy)


@app.route("/api/pair/<udid>", methods=["POST"])
def pair(udid):
    return ok(**device.pair(udid))


@app.route("/api/scan/<udid>", methods=["POST"])
def scan(udid):
    ps = device.pair_status(udid)
    if not ps["ok"]:
        return fail(ps["message"], 409, appairage=False)
    data = device.full_scan(udid)
    phone, changes = db.upsert_from_scan(data)
    for ch in changes:  # ex. batterie remplacée depuis le dernier branchement
        data["alertes"].append({"niveau": "info", "texte": "Changement depuis le dernier branchement — %s : %s → %s"
                                % (ch["champ"], ch["avant"], ch["apres"])})
    sync = None
    settings = db.load_settings()
    if settings.get("sheets_scans_auto") and settings.get("service_account_path"):
        try:
            sheets.append_scan(settings, phone, data)
            sync = "Scan ajouté à l'onglet « %s »." % settings["sheets_onglet_scans"]
        except sheets.SheetsError as e:
            sync = "Synchro du scan impossible : %s" % e
    fiche = db.get_phone(phone["id"])
    actifs = [t for t in fiche["tickets"] if t["statut"] not in ("Rendu", "Annulé")]
    return ok(diagnostic=data, fiche=fiche, changements=changes, synchro=sync,
              tickets_actifs=actifs, pieces_compatibles=db.parts_for(data.get("modele")))


@app.route("/api/live/<udid>")
def live(udid):
    return ok(**device.live(udid))


@app.route("/api/meta")
def meta():
    return ok(statuts=db.STATUTS, etats=db.ETATS, ticket_statuts=db.TICKET_STATUTS,
              qualites=db.QUALITES, categories=db.CATEGORIES, version=VERSION)


@app.route("/api/action/<udid>/<action>", methods=["POST"])
def action(udid, action):
    if action == "redemarrer":
        device.restart(udid)
        return ok(message="Redémarrage envoyé.")
    if action == "eteindre":
        device.shutdown(udid)
        return ok(message="Extinction envoyée.")
    if action == "recuperation":
        device.enter_recovery(udid)
        return ok(message="L'iPhone passe en mode récupération (écran câble + ordinateur).")
    if action == "renommer":
        name = (request.get_json(silent=True) or {}).get("nom", "").strip()
        if not name:
            return fail("Nom vide.")
        device.rename(udid, name)
        return ok(message="Renommé en « %s »." % name)
    return fail("Action inconnue.", 404)


@app.route("/api/recovery/exit", methods=["POST"])
def recovery_exit():
    device.exit_recovery()
    return ok(message="Sortie du mode récupération demandée : l'iPhone redémarre.")


@app.route("/api/apps/<udid>")
def apps(udid):
    return ok(apps=device.apps(udid))


# ------------------------------------------------------------------ tâches longues

def _serial_for(udid):
    try:
        return device.lockdown(udid).get("SerialNumber") or udid
    except device.DeviceError:
        return udid


@app.route("/api/jobs")
def jobs_list():
    return ok(taches=jobs.listing())


@app.route("/api/jobs/<int:jid>")
def job_get(jid):
    j = jobs.get(jid)
    if not j:
        return fail("Tâche introuvable.", 404)
    return ok(tache=j.to_dict(since=int(request.args.get("since", 0))))


@app.route("/api/jobs/<int:jid>/stop", methods=["POST"])
def job_stop(jid):
    return ok(arretee=jobs.stop(jid))


def _one_at_a_time(kind):
    if kind in ("restore", "backup") and (jobs.running("restore") or jobs.running("backup")):
        raise ValueError("Une restauration ou une sauvegarde est déjà en cours : attends qu'elle se termine.")


@app.route("/api/jobs/syslog/<udid>", methods=["POST"])
def job_syslog(udid):
    for j in jobs.running("syslog"):
        jobs.stop(j.id)
    j = jobs.start("syslog", "Journal système en direct", ["idevicesyslog", "-u", udid], udid=udid)
    return ok(tache=j.to_dict())


@app.route("/api/jobs/backup/<udid>", methods=["POST"])
def job_backup(udid):
    _one_at_a_time("backup")
    serial = _serial_for(udid)
    target = os.path.join(BACKUP_DIR, serial or udid)
    os.makedirs(target, exist_ok=True)

    def done(job):
        job.result = {"dossier": target}
        if job.status == "terminée":
            job.add("✅ Sauvegarde enregistrée dans : %s" % target)

    j = jobs.start("backup", "Sauvegarde complète", ["idevicebackup2", "-u", udid, "backup", "--full", target],
                   udid=udid, on_done=done)
    return ok(tache=j.to_dict())


@app.route("/api/jobs/crash/<udid>", methods=["POST"])
def job_crash(udid):
    serial = _serial_for(udid)
    folder = device.crash_dir(db.DATA_DIR, serial)

    def done(job):
        job.result = device.summarize_crashes(folder)
        job.result["dossier"] = folder
        job.add("Analyse : %d panic(s), %d autre(s) rapport(s)." % (job.result["nb_panics"], job.result["nb_autres"]))

    j = jobs.start("crash", "Rapports de plantage", ["idevicecrashreport", "-u", udid, "-e", "-k", folder],
                   udid=udid, on_done=done)
    return ok(tache=j.to_dict())


@app.route("/api/jobs/restore", methods=["POST"])
def job_restore():
    _one_at_a_time("restore")
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "maj")
    udid, ecid = data.get("udid"), data.get("ecid")
    ipsw = (data.get("ipsw") or "").strip()
    if mode not in ("maj", "effacer"):
        return fail("Mode inconnu.")
    if mode == "effacer" and data.get("confirmation") != "EFFACER":
        return fail("Pour une restauration complète, tape EFFACER pour confirmer.")
    if ipsw and not os.path.isfile(os.path.expanduser(ipsw)):
        return fail("Fichier IPSW introuvable : %s" % ipsw)
    cmd = ["idevicerestore", "-y"]
    if udid:
        cmd += ["-u", udid]
    elif ecid:
        cmd += ["-i", str(ecid)]
    if mode == "effacer":
        cmd.append("-e")
    if ipsw:
        cmd.append(os.path.expanduser(ipsw))
    else:
        cmd.append("-l")
    os.makedirs(FIRMWARE_DIR, exist_ok=True)
    label = "Restauration complète (effacement)" if mode == "effacer" else "Mise à jour iOS (données conservées)"
    j = jobs.start("restore", label, cmd, udid=udid or ecid, cwd=FIRMWARE_DIR)
    j.add("ℹ️ Ne débranche pas l'iPhone. Le téléchargement d'iOS peut prendre longtemps (plusieurs Go).")
    return ok(tache=j.to_dict())


# ------------------------------------------------------------------ stock

@app.route("/api/phones")
def phones():
    return ok(telephones=db.list_phones(request.args.get("q"), request.args.get("statut") or None),
              statuts=db.STATUTS, etats=db.ETATS, stats=db.stats())


@app.route("/api/phones/<int:pid>", methods=["GET", "PUT", "DELETE"])
def phone(pid):
    if request.method == "DELETE":
        db.delete_phone(pid)
        return ok()
    if request.method == "PUT":
        p = db.update_phone(pid, request.get_json(silent=True) or {})
    else:
        p = db.get_phone(pid)
    if not p:
        return fail("Fiche introuvable.", 404)
    return ok(fiche=p, statuts=db.STATUTS, etats=db.ETATS)


@app.route("/api/phones/<int:pid>/repairs", methods=["POST"])
def add_repair(pid):
    d = request.get_json(silent=True) or {}
    return ok(fiche=db.add_repair(pid, (d.get("piece") or "").strip(), d.get("cout"), d.get("note"),
                                  part_id=d.get("part_id") or None, ticket_id=d.get("ticket_id") or None,
                                  qualite=d.get("qualite") or None))


@app.route("/api/phones/<int:pid>/repairs/<int:rid>", methods=["DELETE"])
def del_repair(pid, rid):
    return ok(fiche=db.delete_repair(pid, rid))


@app.route("/api/phones/<int:pid>/compare")
def compare(pid):
    a, b = request.args.get("a", type=int), request.args.get("b", type=int)
    if not a or not b:
        return fail("Choisis deux diagnostics à comparer.")
    return ok(comparaison=db.compare_scans(a, b))


@app.route("/api/scans/<int:sid>")
def get_scan(sid):
    s = db.get_scan(sid)
    return ok(diagnostic=s) if s else fail("Scan introuvable.", 404)


@app.route("/api/scans/<int:sid>/label", methods=["POST"])
def label_scan(sid):
    db.label_scan(sid, ((request.get_json(silent=True) or {}).get("etiquette") or "").strip()[:60])
    return ok()


# ------------------------------------------------------------------ réparations clients

@app.route("/api/tickets", methods=["GET", "POST"])
def tickets():
    if request.method == "POST":
        return ok(ticket=db.create_ticket(request.get_json(silent=True) or {}))
    return ok(tickets=db.list_tickets(request.args.get("q"), request.args.get("statut") or None,
                                      request.args.get("actifs") == "1"),
              statuts=db.TICKET_STATUTS, compteurs=db.ticket_stats())


@app.route("/api/tickets/<int:tid>", methods=["GET", "PUT", "DELETE"])
def ticket(tid):
    if request.method == "DELETE":
        db.delete_ticket(tid)
        return ok()
    t = db.update_ticket(tid, request.get_json(silent=True) or {}) if request.method == "PUT" else db.get_ticket(tid)
    return ok(ticket=t) if t else fail("Fiche introuvable.", 404)


@app.route("/api/tickets/<int:tid>/repairs", methods=["POST"])
def ticket_repair(tid):
    t = db.get_ticket(tid)
    if not t:
        return fail("Fiche introuvable.", 404)
    if not t.get("phone_id"):
        return fail("Branche l'iPhone du client et associe-le à la fiche avant d'ajouter une intervention.")
    d = request.get_json(silent=True) or {}
    db.add_repair(t["phone_id"], (d.get("piece") or "").strip(), d.get("cout"), d.get("note"),
                  part_id=d.get("part_id") or None, ticket_id=tid, qualite=d.get("qualite") or None)
    return ok(ticket=db.get_ticket(tid))


@app.route("/bon/<int:tid>")
def ticket_print(tid):
    t = db.get_ticket(tid)
    if not t:
        return "Fiche introuvable", 404
    p = db.get_phone(t["phone_id"]) if t.get("phone_id") else None
    return render_template("bon.html", t=t, p=p, d=(p or {}).get("dernier_diagnostic") or {},
                           s=db.load_settings(), type=request.args.get("type", "depot"))


# ------------------------------------------------------------------ stock de pièces

@app.route("/api/parts", methods=["GET", "POST"])
def parts():
    if request.method == "POST":
        return ok(pieces=db.save_part(request.get_json(silent=True) or {}))
    return ok(pieces=db.list_parts(request.args.get("q")), categories=db.CATEGORIES, qualites=db.QUALITES)


@app.route("/api/parts/<int:part_id>", methods=["PUT", "DELETE"])
def part(part_id):
    if request.method == "DELETE":
        return ok(pieces=db.delete_part(part_id))
    return ok(pieces=db.save_part(request.get_json(silent=True) or {}, part_id))


@app.route("/api/export.csv")
def export_csv():
    rows = db.list_phones()
    buf = io.StringIO()
    cols = ["reference", "modele", "stockage", "couleur", "etat", "sante_batterie", "cycles", "serie", "imei",
            "ios", "activation", "statut", "date_achat", "prix_achat", "frais", "cout_reparations",
            "prix_vente", "marge", "date_vente", "notes"]
    w = csv.writer(buf, delimiter=";")
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=valya-stock.csv"})


@app.route("/rapport/<int:pid>")
def report(pid):
    p = db.get_phone(pid)
    if not p:
        return "Fiche introuvable", 404
    return render_template("report.html", p=p, d=p.get("dernier_diagnostic") or {}, s=db.load_settings())


# ------------------------------------------------------------------ Google Sheets

@app.route("/api/phones/<int:pid>/sheets/prepare", methods=["POST"])
def sheets_prepare(pid):
    p = db.get_phone(pid)
    if not p:
        return fail("Fiche introuvable.", 404)
    return ok(plan=sheets.prepare(db.load_settings(), p))


@app.route("/api/phones/<int:pid>/sheets/write", methods=["POST"])
def sheets_write(pid):
    d = request.get_json(silent=True) or {}
    if d.get("valide") is not True:
        return fail("Validation du récapitulatif manquante : rien n'a été écrit.")
    p = db.get_phone(pid)
    if not p:
        return fail("Fiche introuvable.", 404)
    res = sheets.write(db.load_settings(), p, int(d["ligne"]), d["mode"])
    if res["tout_ok"]:
        db.set_sheets_row(pid, res["ligne"])
    return ok(resultat=res)


# ------------------------------------------------------------------ réglages

@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        s = db.save_settings(request.get_json(silent=True) or {})
    else:
        s = db.load_settings()
    return ok(reglages=s, dossier_donnees=db.DATA_DIR, google_dispo=sheets.HAS_GOOGLE)


@app.route("/api/settings/key", methods=["POST"])
def upload_key():
    f = request.files.get("cle")
    if not f:
        return fail("Aucun fichier reçu.")
    raw = f.read()
    import json
    try:
        info = json.loads(raw.decode("utf-8"))
        assert info.get("type") == "service_account" and info.get("client_email")
    except Exception:
        return fail("Ce fichier n'est pas une clé JSON de compte de service Google.")
    path = os.path.join(db.DATA_DIR, "compte-service.json")
    os.makedirs(db.DATA_DIR, exist_ok=True)
    with open(path, "wb") as out:
        out.write(raw)
    os.chmod(path, 0o600)
    s = db.save_settings({"service_account_path": path})
    return ok(reglages=s, email=info["client_email"])


@app.route("/api/settings/test", methods=["POST"])
def test_settings():
    return ok(resultat=sheets.test(db.load_settings()))


def main():
    url = "http://127.0.0.1:%d" % PORT
    if os.environ.get("VALYA_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print("\n  Valya Scan %s est ouvert sur %s" % (VERSION, url))
    print("  Laisse cette fenêtre ouverte pendant que tu utilises l'app (ferme-la pour quitter).\n")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
