# Valya Scan

Outil de diagnostic d'iPhone pour l'achat-revente et la réparation (activité Valya).

Branche un iPhone en USB sur ton Mac, ouvre l'app dans le navigateur, et récupère en quelques secondes : modèle, version iOS, numéro de série, IMEI, niveau de batterie et état d'activation. Chaque appareil peut être enregistré dans une fiche de stock locale.

> ⚠️ Cette app tourne **en local sur ton Mac** : elle a besoin d'un accès physique à l'iPhone branché en USB. Elle ne peut pas être hébergée sur un serveur cloud (Vercel, etc.).

## Installation (une seule fois)

1. Installer [Homebrew](https://brew.sh) s'il n'est pas déjà présent :
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
2. Installer les outils iPhone et Flask :
   ```bash
   brew install libimobiledevice
   pip3 install flask
   ```

## Lancer l'app

```bash
python3 valya_scan.py
```

Puis ouvrir **http://127.0.0.1:5000** dans Safari.

Branche l'iPhone, déverrouille-le et appuie sur **« Faire confiance »** quand il le demande. L'app affiche les infos et se rafraîchit toute seule.

## Limites connues

- La **santé réelle de la batterie** (capacité max en %) n'est pas lisible de façon fiable par ces outils — seul le niveau de charge est affiché. Pour l'usure, voir Réglages > Batterie.
- L'**état iCloud** exact ne se lit pas à 100 % en USB. L'app donne l'état d'activation ; le réflexe sûr à l'achat reste de se faire déconnecter l'iCloud devant soi avant de payer.

## Ce que l'app ne fait pas

Pas de contournement de verrouillage iCloud ni de FRP Google — c'est illégal et réservé aux appareils volés. L'app aide à **acheter propre**, pas à débloquer.

## Stock

Les fiches enregistrées sont stockées dans `stock_valya.json`, à côté du script. Ce fichier n'est pas versionné (voir `.gitignore`).
