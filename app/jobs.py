# -*- coding: utf-8 -*-
"""Tâches longues (restauration, sauvegarde, journal système…) lancées en arrière-plan.

Chaque tâche garde son journal en mémoire ; l'interface le lit au fur et à mesure.
"""
import itertools
import os
import signal
import subprocess
import threading
import time

_ids = itertools.count(1)
_jobs = {}
_lock = threading.Lock()
MAX_LINES = 5000


class Job(object):
    def __init__(self, kind, label, cmd, udid=None, on_done=None, env=None, cwd=None):
        self.id = next(_ids)
        self.kind = kind
        self.label = label
        self.cmd = cmd
        self.udid = udid
        self.lines = []
        self.offset = 0  # nombre de lignes supprimées en tête (journal tournant)
        self.status = "en cours"
        self.returncode = None
        self.started = time.time()
        self.ended = None
        self.proc = None
        self.on_done = on_done
        self.env = env
        self.cwd = cwd
        self.result = None

    def add(self, line):
        with _lock:
            self.lines.append(line.rstrip("\n"))
            if len(self.lines) > MAX_LINES:
                drop = len(self.lines) - MAX_LINES
                del self.lines[:drop]
                self.offset += drop

    def to_dict(self, since=0):
        with _lock:
            start = max(0, since - self.offset)
            return {
                "id": self.id, "kind": self.kind, "label": self.label, "udid": self.udid,
                "status": self.status, "returncode": self.returncode,
                "started": self.started, "ended": self.ended,
                "lines": self.lines[start:], "next": self.offset + len(self.lines),
                "result": self.result,
            }


def start(kind, label, cmd, udid=None, on_done=None, env=None, cwd=None):
    job = Job(kind, label, cmd, udid, on_done, env, cwd)
    with _lock:
        _jobs[job.id] = job
    t = threading.Thread(target=_run, args=(job,), daemon=True)
    t.start()
    return job


def _run(job):
    job.add("$ " + " ".join(job.cmd))
    try:
        env = dict(os.environ)
        if job.env:
            env.update(job.env)
        job.proc = subprocess.Popen(
            job.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1, universal_newlines=True, errors="replace",
            preexec_fn=os.setsid, env=env, cwd=job.cwd)
        for line in job.proc.stdout:
            job.add(line)
        job.proc.wait()
        job.returncode = job.proc.returncode
        if job.status == "arrêtée":
            pass
        elif job.returncode == 0:
            job.status = "terminée"
        else:
            job.status = "erreur"
            job.add("⚠️ La commande s'est terminée avec le code %s." % job.returncode)
    except FileNotFoundError:
        job.status = "erreur"
        job.add("⚠️ Outil introuvable : %s. Relance Valya Scan pour terminer l'installation." % job.cmd[0])
    except Exception as exc:  # pragma: no cover
        job.status = "erreur"
        job.add("⚠️ Erreur : %s" % exc)
    job.ended = time.time()
    if job.on_done:
        try:
            job.on_done(job)
        except Exception as exc:  # pragma: no cover
            job.add("⚠️ Erreur après la tâche : %s" % exc)


def get(job_id):
    return _jobs.get(job_id)


def stop(job_id):
    job = _jobs.get(job_id)
    if not job or not job.proc or job.proc.poll() is not None:
        return False
    job.status = "arrêtée"
    try:
        os.killpg(os.getpgid(job.proc.pid), signal.SIGINT)
        time.sleep(1.5)
        if job.proc.poll() is None:
            os.killpg(os.getpgid(job.proc.pid), signal.SIGTERM)
    except Exception:
        job.proc.terminate()
    job.add("■ Tâche arrêtée.")
    return True


def running(kind=None):
    out = []
    for j in list(_jobs.values()):
        if j.status == "en cours" and (kind is None or j.kind == kind):
            out.append(j)
    return out


def listing():
    return [j.to_dict(since=10 ** 9) for j in sorted(_jobs.values(), key=lambda j: -j.id)][:30]
