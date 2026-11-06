#!/bin/bash
# Active le lancement automatique de Valya Scan à l'ouverture de session macOS.
# À exécuter depuis le dossier du dépôt : bash macos/activer-demarrage-auto.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/run.sh"
DATA="$HOME/Library/Application Support/ValyaScan"
VENV="$DATA/venv"
LABEL="fr.valya.scan"
AGENTS="$HOME/Library/LaunchAgents"
PLIST="$AGENTS/$LABEL.plist"
LOGS="$HOME/Library/Logs"
OUT="$LOGS/ValyaScan-launchd.log"
ERR="$LOGS/ValyaScan-launchd-error.log"

if [ ! -x "$RUN" ]; then
  echo "Erreur : run.sh est introuvable ou non exécutable dans $ROOT"
  exit 1
fi

# Ne pas installer un agent qui déclencherait l'installation interactive
# de dépendances au prochain démarrage : on vérifie d'abord le premier lancement.
if [ ! -x "$VENV/bin/python" ]; then
  echo "Il faut d'abord lancer Valya Scan une fois manuellement :"
  echo "  bash \"$RUN\""
  echo "Attends que l'application s'ouvre, puis ferme-la et relance ce script."
  exit 1
fi

if ! command -v idevice_id >/dev/null 2>&1 && [ ! -x /opt/local/bin/idevice_id ]; then
  echo "Les outils iPhone ne semblent pas installés."
  echo "Lance d'abord Valya Scan manuellement pour terminer leur installation."
  exit 1
fi

mkdir -p "$AGENTS" "$LOGS"
chmod +x "$RUN"

# Génère un plist valide même si le chemin du dossier contient des caractères spéciaux.
ROOT="$ROOT" RUN="$RUN" OUT="$OUT" ERR="$ERR" PLIST="$PLIST" /usr/bin/python3 <<'PY'
import os
import plistlib

config = {
    "Label": "fr.valya.scan",
    "ProgramArguments": ["/bin/bash", os.environ["RUN"]],
    "WorkingDirectory": os.environ["ROOT"],
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 15,
    "StandardOutPath": os.environ["OUT"],
    "StandardErrorPath": os.environ["ERR"],
    "EnvironmentVariables": {
        "PATH": "/opt/local/bin:/opt/local/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "VALYA_PORT": "5757"
    }
}
with open(os.environ["PLIST"], "wb") as f:
    plistlib.dump(config, f)
PY

# Recharge proprement l'agent s'il était déjà installé.
UID_NOW="$(id -u)"
launchctl bootout "gui/$UID_NOW/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NOW" "$PLIST"
launchctl enable "gui/$UID_NOW/$LABEL"

echo ""
echo "Valya Scan démarrera automatiquement à chaque ouverture de session."
echo "Adresse locale : http://127.0.0.1:5757"
echo "Journal : $OUT"
echo "Erreurs : $ERR"
echo ""
echo "Pour désactiver : launchctl bootout gui/$UID_NOW/$LABEL"
