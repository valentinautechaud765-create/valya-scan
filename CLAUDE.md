# Valya Scan — contexte du projet

Ce fichier explique le projet à Claude Code. Il le lit au début de chaque session.
Le propriétaire est Valentin Autechaud (activité **Valya** : rachat, revente et réparation d'iPhone, avec son associé Yanis). Il n'est pas développeur : parle-lui en français, simplement.

**Lis d'abord `README.md`** : il décrit en détail les fonctions, l'installation et la structure.

## L'essentiel

- C'est une appli de technicien iPhone en **Python/Flask**, qui tourne **en local sur le Mac** de Valentin. Elle a besoin de l'iPhone branché en USB (libimobiledevice, idevicerestore), donc **elle n'est pas déployable sur Vercel**.
- L'interface s'ouvre sur `http://127.0.0.1:5757`.
- **Mise à jour automatique** : `run.sh` fait un `git pull` à chaque lancement. Pousser sur `main` revient donc à mettre à jour l'appli chez Valentin. Le code de `main` doit toujours fonctionner.
- Les données locales (`valya.db`, réglages, clé Google) sont dans `~/Library/Application Support/ValyaScan/`, **jamais dans le dépôt**.
- `requirements.txt` doit rester 100 % Python, sans module à compiler.

## Fichiers

- `app/server.py` : serveur Flask et routes.
- `app/device.py` : dialogue avec l'iPhone (USB).
- `app/db.py`, `app/models.py` : base SQLite locale.
- `app/jobs.py` : tâches longues (mises à jour iOS, sauvegardes…).
- `app/sheets.py` : synchro avec le Google Sheets de STOCKFLOW.
- `app/static/` : interface (HTML/CSS/JS). `app/templates/` : rapports et bons imprimables.
- `macos/` : icône Applications et installateur.

## Lien avec STOCKFLOW

Valya Scan envoie les fiches vers l'onglet `stock` du Google Sheets que lit STOCKFLOW (dépôt `stockflow-`). Les envois se font **uniquement après validation d'un récapitulatif**. Les colonnes sont repérées par leur titre. La colonne **Marge** (formule) n'est jamais touchée, et chaque écriture est relue.

## Règles

1. Aucun contournement d'iCloud, de code ou de blocage opérateur. Ne pas masquer le message Apple « Pièce inconnue ».
2. Ne rien casser de ce qui marche. Les ajouts demandés ne doivent pas changer le reste de l'appli.
3. L'appli doit rester simple et visuellement claire.
4. Aucun secret ni donnée client dans le dépôt.
5. Ce dépôt est actuellement **public** sur GitHub. Valentin voulait le passer en privé, c'est à vérifier avec lui. Dans ce cas, `run.sh` doit continuer à pouvoir faire `git pull` (authentification `gh`).
