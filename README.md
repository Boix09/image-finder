# Image Finder

Programme Python qui cherche sur Internet les images les plus pertinentes,
populaires ou belles pour une demande en langage naturel, les classe, puis
telecharge les meilleures dans un dossier.

Il s'integre a OpenCode via un serveur MCP : il suffit de demander
« telecharge 5 belles images de voiture de sport dans le dossier voitures »
pour que l'IA utilise automatiquement le programme.

## Ce que fait le programme

1. Nettoie la demande et extrait le sujet et le dossier eventuel.
2. Interroge Yandex Images (popularite) et Wikimedia Commons (fiabilite).
3. Classe les candidats : rang, pertinence du titre, resolution, nettete,
   contraste, couleurs et exposition.
4. Telecharge un pool de candidats et ecarte les doublons visuels.
5. Enregistre les meilleures images, un `manifest.json` et une galerie
   `index.html`.

Le programme recherche des images **existantes** : il ne genere pas d'images
par IA.

## Prerequis

- Python 3.10 ou plus
- OpenCode (ou tout autre client compatible MCP)
- Connexion Internet

## Installation chez un ami

```bat
git clone https://github.com/Boix09/image-finder.git C:\tools\image-finder
cd /d C:\tools\image-finder
python install.py
```

Puis redemarrer OpenCode. L'outil est disponible dans **tous** les projets.

### Installation limitee a un projet

Utile si l'ami veut garder l'outil dans son propre projet, comme ici :

```bat
cd /d D:\son-projet
git clone https://github.com/Boix09/image-finder.git image_finder
python image_finder\install.py --project
```

Cela cree :

```text
D:\son-projet\
├── opencode.json
└── .opencode\skills\image-downloader\SKILL.md
```

Et l'outil MCP pointe vers `D:\son-projet\image_finder\mcp_server.py`.

### Ce que fait install.py

- verifie Python et installe `requests` + `Pillow` si besoin ;
- ajoute (ou met a jour) le serveur `image-finder` dans la configuration
  OpenCode, avec une sauvegarde de l'ancien fichier ;
- installe la skill `image-downloader` qui indique a l'IA quand utiliser
  l'outil ;
- verifie le serveur avec `mcp_server.py --check`.

Options :

```bat
python install.py --check       REM verifier sans modifier
python install.py --dry-run     REM afficher les actions prevues
python install.py --skip-deps   REM ne pas installer les dependances
```

## Utilisation

Une fois OpenCode redemarre, demander simplement :

```text
telecharge 3 belles images de voiture de sport dans le dossier voitures
```

L'IA appelle l'outil `download_images`. Resultat :

```text
C:\tools\image-finder\voitures\
├── 01_voiture-de-sport_1920x1280.jpg
├── 02_voiture-de-sport_735x915.jpg
├── manifest.json
└── index.html
```

Pour ouvrir la galerie :

```bat
start "" "C:\tools\image-finder\voitures\index.html"
```

## Utilisation sans IA (ligne de commande)

```bat
cd /d C:\tools\image-finder

REM Apercu sans telechargement
python image_finder.py "voiture de sport" --dry-run -n 5

REM Telechargement
python image_finder.py "telecharge 5 images de voiture de sport" -o voitures -n 5

REM Sortie JSON pour un script ou une IA
python image_finder.py "voiture de sport" --json -n 5

REM Images Wikimedia Commons (licences explicites)
python image_finder.py "paysage de montagne" --source commons -o montagnes

REM URL directe ou fichier d'URLs
python image_finder.py https://exemple.com/photo.jpg -o images
python image_finder.py --file urls.txt -o images
```

## Options principales

| Option | Description |
|---|---|
| `-o, --output` | dossier de destination |
| `-n, --limit` | nombre d'images a garder (1 a 60, defaut 10) |
| `-s, --source` | `all` (Yandex + Commons), `yandex`, `commons`, `ddg`, `openverse` |
| `-j, --workers` | telechargements simultanes (defaut 6) |
| `--min-side` | petit cote minimum en pixels (defaut 700, `0` desactive) |
| `--max-mb` | taille maximale par image (defaut 25 Mo) |
| `--orientation` | `any`, `landscape`, `portrait`, `square` |
| `--dry-run` | afficher les resultats sans telecharger |
| `--json` | sortie JSON structuree |
| `--no-gallery` | ne pas creer `index.html` |
| `--raw` | ne pas nettoyer la demande |

## Utiliser avec un autre client MCP

Le serveur est standard (transport stdio). Exemple de configuration :

```json
{
  "mcpServers": {
    "image-finder": {
      "command": "python",
      "args": ["D:/tools/image-finder/mcp_server.py"]
    }
  }
}
```

Adapte le chemin. Verification rapide :

```bat
python mcp_server.py --check
```

## Interface web (v3)

Image Finder inclut une interface web autonome (Flask + Waitress) pour
chercher, organiser, afficher et supprimer vos images depuis un navigateur,
en local ou sur un serveur en ligne.

### Lancement

```bat
python web_app.py
```

Puis ouvrez `http://127.0.0.1:8420/`.

Options utiles :

| Option | Description |
|---|---|
| `--host` | adresse d'ecoute (defaut : 127.0.0.1) |
| `--port` | port d'ecoute (defaut : 8420) |
| `--root` | repertoire racine de la bibliotheque |
| `--password` | mot de passe HTTP Basic (obligatoire hors de 127.0.0.1) |
| `--insecure` | autoriser l'acces public sans mot de passe (deconseille) |
| `--open` | ouvrir le navigateur au demarrage |

Sur un serveur en ligne :

```bat
python web_app.py --host 0.0.0.0 --port 8420 --password "votre-secret"
```

L'interface inclut :
- une grande barre de recherche avec suggestions,
- la creation de dossiers depuis l'interface (crees automatiquement sur disque),
- un bouton **Parcourir** pour choisir visuellement le repertoire racine (Chrome/Edge récents),
- le changement de repertoire racine,
- une galerie avec miniatures, filtre et tri,
- un aperçu (lightbox) avec telechargement et suppression,
- un bouton corbeille visible au survol sur chaque image,
- un suivi de progression des recherches en temps reel.

## Utiliser avec un autre client MCP

- **Yandex Images** : classement par popularite, mais peut limiter les requetes
  ou demander un captcha.
- **Wikimedia Commons** : source fiable avec auteur et licence.
- **DuckDuckGo** : experimental, peut imposer un challenge anti-robot.
- **Openverse** : necessite un jeton `OPENVERSE_ACCESS_TOKEN`.

Les images trouvees via Yandex peuvent etre protegees par le droit d'auteur.
Verifie le `manifest.json` avant toute reutilisation. Utilise
`--source commons` pour privilegier les images librement reutilisables.

## Partager le projet / GitHub

Voir `GUIDE_PARTAGE.md` pour les etapes detaillees : creation du depot,
publication et installation chez l'ami.

## Depannage

- `python` inconnu : utilise `py -3` sous Windows.
- L'outil n'apparait pas dans OpenCode : redemarre OpenCode, puis
  `python install.py --check`.
- Yandex timeout ou captcha : le programme continue avec Commons ; sinon
  ajoute `--source commons`.
- Aucune image valide : baisse `--min-side 0` ou change `--orientation`.

## Structure

```text
image_finder/
├── image_finder.py
├── download_images.py
├── web_app.py
├── mcp_server.py
├── install.py
├── imagefinder/
├── webui/
│   ├── config.py
│   ├── library.py
│   ├── jobs.py
│   ├── thumbs.py
│   ├── server.py
│   ├── templates/index.html
│   └── static/app.css, app.js
├── skills/image-downloader/SKILL.md.template
├── requirements.txt
├── README.md
├── GUIDE_PARTAGE.md
└── .gitignore
```
