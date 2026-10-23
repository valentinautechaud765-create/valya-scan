# Valya Scan

App de technicien iPhone pour l'activité Valya (achat-revente et réparation) : diagnostic complet par USB, outils de réparation, stock, rapports de vente et synchro avec le Google Sheets de STOCKFLOW.

> Cette app tourne **en local sur le Mac** : elle a besoin de l'iPhone branché en USB, donc elle ne peut pas être hébergée sur Vercel. Le code est sur GitHub et **l'app se met à jour toute seule à chaque lancement**.

## Fonctions

- **iPhone branché** : diagnostic automatique au branchement, avec un verdict clair (OK / À vérifier / Bloqué) : modèle, IMEI, série, iOS, batterie (santé, cycles, n° de série, température, charge en direct), stockage, activation, Localiser, origine, région.
- **Fiche technique complète** : tout ce que l'iPhone stocke (carte mère/puce : ECID, Chip/Board ID, iBoot ; modem ; batterie en détail : tension, courant, n° de série ; stockage ; système) + **données brutes Apple** domaine par domaine, filtrables et téléchargeables (JSON). Boutons vers les vérifications officielles en ligne (garantie/date d'achat Apple, liste noire IMEI) — ces infos ne sont pas stockées dans le téléphone.
- **Mise à jour & réinitialisation** : version iOS installée vs dernière signée par Apple, mise à jour (données gardées), réinitialisation usine (effacement + réinstallation), mode récupération.
- **Tests guidés** pas à pas (écran, tactile, Face ID, True Tone, caméras, micro, haut-parleurs, boutons, réseau, charge…) : ✓ / ✗, enregistrés dans la fiche et sur les rapports.
- **Traçabilité** : historique complet de chaque iPhone (scans, changements détectés, interventions, statuts, tests). Suivi **avant / après réparation** avec comparaison (ex. n° de série batterie changé = batterie remplacée).
- **Réparations clients** : fiche R-0001…, étapes (Reçu → Diagnostic → Devis → En réparation → Prêt → Rendu), devis/acompte, état au dépôt, **bon de dépôt** et **bon de restitution** imprimables.
- **Stock de pièces** : coût, qualité (origine / OEM / compatible), fournisseur, alerte de stock bas ; décompté automatiquement quand une pièce est posée.
- **Outils** : redémarrer, éteindre, mode récupération (entrée/sortie), mise à jour ou restauration iOS, sauvegarde complète, journal système en direct, apps installées, analyse des plantages (panic → pièce suspecte).
- **Mes téléphones** : prix, frais, réparations, marge, statut, export CSV, **rapport de vente** PDF.
- **Google Sheets (STOCKFLOW)** : envoi vers l'onglet « stock » après validation d'un récapitulatif ; colonnes repérées par leur titre, la colonne Marge n'est jamais touchée, relecture après écriture.

Ce que l'app ne fait pas : aucun contournement d'iCloud, de code ou d'opérateur, et elle ne masque pas le message « Pièce inconnue » d'Apple : les pièces non d'origine sont tracées et signalées sur les rapports.

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
