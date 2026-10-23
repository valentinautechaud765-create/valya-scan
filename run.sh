#!/bin/bash
# Valya Scan — lanceur : se met à jour depuis GitHub, installe ce qui manque, puis démarre l'app.
# Compatible Mac Apple Silicon (Homebrew) ET Mac Intel (MacPorts).

export PATH="/opt/homebrew/bin:/opt/local/bin:/opt/local/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
RES="$(cd "$(dirname "$0")" && pwd)"
DATA="$HOME/Library/Application Support/ValyaScan"
VENV="$DATA/venv"
# Port 5757 : le port 5000 est pris par le récepteur AirPlay de macOS (erreur 403)
export VALYA_PORT=5757
URL="http://127.0.0.1:$VALYA_PORT"
mkdir -p "$DATA"

pause_et_quitte() {
  echo ""
  read -n 1 -s -r -p "  Appuie sur une touche pour fermer."
  exit "$1"
}

clear
echo ""
echo "  ╔══════════════════════════════╗"
echo "  ║         VALYA  SCAN          ║"
echo "  ╚══════════════════════════════╝"
echo ""

# --- 0. Déjà ouvert ? -----------------------------------------------------------
if curl -sf --max-time 2 "$URL/api/settings" 2>/dev/null | grep -q reglages; then
  echo "  Valya Scan tourne déjà : ouverture dans le navigateur."
  open "$URL"
  sleep 2
  exit 0
fi

# --- 0 bis. Mise à jour automatique depuis GitHub ---------------------------------
if [ -d "$RES/.git" ] && command -v git >/dev/null 2>&1; then
  echo "  → Recherche de mise à jour…"
  AVANT="$(git -C "$RES" rev-parse --short HEAD 2>/dev/null)"
  if git -C "$RES" pull --ff-only -q 2>/dev/null; then
    APRES="$(git -C "$RES" rev-parse --short HEAD 2>/dev/null)"
    if [ "$AVANT" != "$APRES" ]; then
      echo "  ✅ Valya Scan mis à jour ($AVANT → $APRES). Redémarrage du lanceur…"
      chmod +x "$RES/run.sh"
      exec "$RES/run.sh"
    fi
    echo "  Déjà à jour ($APRES)."
  else
    echo "  (Mise à jour impossible pour l'instant : pas d'Internet ou accès GitHub expiré. On continue.)"
  fi
  echo ""
fi

# --- 1. python3 (outils de développement Apple) ---------------------------------
if ! xcode-select -p >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "  Installation des outils Apple (python3)…"
  echo "  Une fenêtre Apple va s'ouvrir : clique « Installer » et attends la fin,"
  echo "  puis relance Valya Scan."
  xcode-select --install 2>/dev/null
  pause_et_quitte 0
fi

# --- 2. Outils iPhone ---------------------------------------------------------------
PAQUETS="libimobiledevice libirecovery idevicerestore ideviceinstaller"
manquants=""
for outil in idevice_id irecovery idevicerestore ideviceinstaller; do
  command -v "$outil" >/dev/null 2>&1 || manquants="$manquants $outil"
done

if [ -n "$manquants" ]; then
  echo "  Installation des outils iPhone manquants :$manquants"
  echo "  (une seule fois, de 5 à 30 minutes selon le Mac)"
  echo ""

  if [ "$(uname -m)" = "arm64" ]; then
    # ---------- Mac Apple Silicon : Homebrew ----------
    if ! command -v brew >/dev/null 2>&1; then
      echo "  → Installation de Homebrew…"
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    for p in $PAQUETS; do
      echo "  → ${p}…"
      brew install "$p" || echo "  (échec de $p, on continue)"
    done
  else
    # ---------- Mac Intel : MacPorts ----------
    echo "  Mac Intel détecté : utilisation de MacPorts."
    echo "  Ton mot de passe Mac va être demandé (rien ne s'affiche quand tu tapes,"
    echo "  c'est normal : tape-le puis appuie sur Entrée)."
    echo ""
    if [ ! -x /opt/local/bin/port ]; then
      echo "  → Téléchargement de MacPorts…"
      MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
      PKG_URL="$(curl -fsSL https://api.github.com/repos/macports/macports-base/releases/latest \
        | grep '"browser_download_url"' \
        | grep -E "MacPorts-[0-9.]+-${MAJOR}-[A-Za-z]+\.pkg\"" \
        | head -n 1 \
        | sed -E 's/.*"(https[^"]+)".*/\1/')"
      if [ -z "$PKG_URL" ]; then
        echo "  ⚠️  MacPorts introuvable pour macOS ${MAJOR}. Installe-le depuis macports.org/install.php"
        pause_et_quitte 1
      fi
      TMP_PKG="/tmp/MacPorts-valya.pkg"
      curl -fL --progress-bar "$PKG_URL" -o "$TMP_PKG" || { echo "  ⚠️  Téléchargement échoué."; pause_et_quitte 1; }
      sudo installer -pkg "$TMP_PKG" -target / || { echo "  ⚠️  Installation de MacPorts échouée."; pause_et_quitte 1; }
      rm -f "$TMP_PKG"
      sudo /opt/local/bin/port -N selfupdate
    fi
    for p in $PAQUETS; do
      echo "  → ${p}…"
      sudo /opt/local/bin/port -N install "$p" || echo "  (échec de $p, on continue)"
    done
  fi
  hash -r
fi

if ! command -v idevice_id >/dev/null 2>&1; then
  echo ""
  echo "  ⚠️  L'outil de lecture iPhone n'a pas pu être installé."
  echo "      Relance Valya Scan, ou envoie une capture de cette fenêtre à Claude."
  pause_et_quitte 1
fi

# --- 3. Environnement Python de l'app ------------------------------------------------
# Modules 100 % Python (aucune compilation). Réinstallés seulement si requirements.txt change.
REQ_HASH="$(shasum "$RES/requirements.txt" 2>/dev/null | cut -d' ' -f1)"
if [ ! -x "$VENV/bin/python" ] || [ "$(cat "$VENV/.req" 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "  → Préparation de l'app (modules Python)…"
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV" || { echo "  ⚠️  Impossible de créer l'environnement Python."; pause_et_quitte 1; }
  "$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1
  "$VENV/bin/python" -m pip install --quiet --only-binary=:all: -r "$RES/requirements.txt" \
    || "$VENV/bin/python" -m pip install --quiet -r "$RES/requirements.txt" || {
    echo "  ⚠️  Installation des modules Python échouée (connexion Internet ?)."
    pause_et_quitte 1
  }
  echo "$REQ_HASH" > "$VENV/.req"
fi

# --- 4. Lancement ------------------------------------------------------------------
echo ""
echo "  ✅ Tout est prêt."
exec "$VENV/bin/python" "$RES/app/server.py"
