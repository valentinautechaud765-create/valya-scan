# Valya Scan

App de technicien iPhone pour l'activité Valya (achat-revente et réparation) : diagnostic complet par USB, outils de réparation, stock, rapports de vente et synchro avec le Google Sheets de STOCKFLOW.

> Cette app tourne **en local sur le Mac** : elle a besoin de l'iPhone branché en USB, donc elle ne peut pas être hébergée sur Vercel. Le code est sur GitHub et **l'app se met à jour toute seule à chaque lancement**.

## Fonctions

- **Diagnostic** : modèle, IMEI, série, iOS, batterie (santé, cycles, température), stockage, activation, Localiser, origine (neuf / reconditionné Apple / échange SAV), région.
- **Outils** : redémarrer, éteindre, mode récupération (entrée/sortie), mise à jour ou restauration iOS, sauvegarde complète, journal système en direct, apps installées, analyse des plantages (panic → pièce suspecte).
- **Tests manuels** à cocher (Face ID, caméras, micro…), enregistrés dans la fiche.
- **Stock** : fiche par iPhone (VAL-0001…), prix, frais, réparations, marge, statut, export CSV.
- **Rapport de vente** imprimable / PDF.
- **Google Sheets** : envoi vers l'onglet « stock » après validation d'un récapitulatif ; colonnes A–I et K seulement (J = Marge jamais touchée), relecture après écriture.

Ce que l'app ne fait pas : aucun contournement d'iCloud, de code ou d'opérateur.

## Installation sur un Mac (une seule fois)

Dans le Terminal (MacPorts déjà installé sur un Mac Intel ; sur Apple Silicon remplace la 1re ligne par `brew install gh`) :

```bash
sudo port -N install gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
gh repo clone valentinautechaud765-create/valya-scan ~/ValyaScan
bash ~/ValyaScan/macos/installer.sh
```

Puis double-clic sur **Valya Scan** dans Applications. Au premier lancement, il installe les outils iPhone (libimobiledevice, idevicerestore…) et les modules Python.

L'interface s'ouvre sur **http://127.0.0.1:5757** (le port 5000 est pris par AirPlay sur macOS).

## Mises à jour

Chaque lancement fait un `git pull` : il suffit de pousser sur `main` et de relancer l'app.

## Données

`~/Library/Application Support/ValyaScan/` : base `valya.db`, réglages, clé Google, sauvegardes, firmwares, rapports de plantage. Jamais dans le dépôt.

## Structure

```
run.sh            lanceur (mise à jour, installation des outils, démarrage)
requirements.txt  modules Python (100 % Python, aucune compilation)
app/              serveur Flask + interface
macos/            icône Applications + installateur
```
