#!/bin/bash
# Installe (ou réinstalle) l'icône Valya Scan dans Applications.
# Le code reste dans ~/ValyaScan (clone GitHub) et se met à jour tout seul à chaque lancement.
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$DIR/run.sh" "$DIR/macos/Valya Scan.app/Contents/MacOS/valya-scan"
rm -rf "/Applications/Valya Scan.app"
cp -R "$DIR/macos/Valya Scan.app" "/Applications/Valya Scan.app"
xattr -cr "/Applications/Valya Scan.app" 2>/dev/null || true
echo ""
echo "  ✅ Valya Scan est installé dans Applications."
echo "     Double-clique dessus pour le lancer (il se mettra à jour tout seul)."
open -R "/Applications/Valya Scan.app"
