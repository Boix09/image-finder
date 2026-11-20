# Partager Image Finder et le publier sur GitHub

Ce guide couvre deux cotes :

1. **Toi** : publier le projet sur GitHub.
2. **Ton ami** : recuperer le projet et l'installer dans son propre projet.

Le programme est deja rendu portable : aucune modification de code n'est
necessaire, `install.py` detecte automatiquement le dossier d'installation.

---

## 1. Toi : preparer une copie propre pour GitHub

Le dossier actuel `D:\easyshopeht\image_finder` se trouve dans le depot Git du
projet EasyShop. **Ne lance pas `git init` directement dedans** : cela creerait
un depot imbrique, source de confusion.

Cree plutot une copie propre, sans images telechargees ni cache :

```bat
robocopy "D:\easyshopeht\image_finder" "D:\image-finder" /E /XD __pycache__ images test_ia_voitures test_voitures /XF *.pyc
cd /d D:\image-finder
dir
```

Tu dois voir `install.py`, `mcp_server.py`, `README.md`, `imagefinder\`, etc.

> A chaque modification future, relance la commande `robocopy` pour mettre la
> copie a jour, puis commit et push.

---

## 2. Toi : creer le depot GitHub

GitHub CLI (`gh`) est deja installe et connecte sur ta machine (compte
**Boix09**). La methode la plus simple :

```bat
cd /d D:\image-finder
git init -b main
git add .
git commit -m "Image Finder 2.2.0"
gh repo create image-finder --public --source=. --remote=origin --push
```

- `--public` : n'importe qui peut cloner le depot. C'est le plus simple pour un
  ami.
- Pour un depot prive, remplace par `--private` puis ajoute ton ami :
  `gh repo edit --add-collaborator son-pseudo-github`.

### Variante sans GitHub CLI

1. Cree le depot sur <https://github.com/new> (sans README ni .gitignore).
2. Puis :

```bat
cd /d D:\image-finder
git remote add origin https://github.com/Boix09/image-finder.git
git push -u origin main
```

### Soigner la publication

```bat
git tag v2.2.0
git push origin v2.2.0
```

Ajoute une licence si tu veux autoriser explicitement la reutilisation :
fichier `LICENSE` avec le texte MIT, par exemple. Sans licence, les droits
restent reserves par defaut.

---

## 3. Ton ami : installer le projet

### Prerequis

- Python 3.10 ou plus (`python --version`)
- OpenCode installe
- Connexion Internet

### Installation globale (recommandee)

L'outil devient disponible dans **tous** ses projets OpenCode.

```bat
git clone https://github.com/Boix09/image-finder.git C:\tools\image-finder
cd /d C:\tools\image-finder
python install.py
```

Puis il redemarre OpenCode et demande, dans n'importe quel projet :

```text
telecharge 3 belles images de voiture de sport dans le dossier voitures
```

### Installation dans son projet uniquement

S'il veut garder l'outil dans son projet, comme toi :

```bat
cd /d D:\son-projet
git clone https://github.com/Boix09/image-finder.git image_finder
python image_finder\install.py --project
```

Cela cree `D:\son-projet\opencode.json` et
`D:\son-projet\.opencode\skills\image-downloader\SKILL.md`.

### Si `python` n'est pas reconnu

```bat
py -3 image_finder\install.py --project
```

---

## 4. Verifier l'installation

```bat
cd /d C:\tools\image-finder
python install.py --check
```

Sortie attendue :

```text
[OK]      Python : 3.12.x
[OK]      Dependances : requests et Pillow
[OK]      Serveur MCP : version 2.2.0
[OK]      Configuration OpenCode : C:\Users\...\.config\opencode\opencode.jsonc
[OK]      Skill image-downloader : ...\skills\image-downloader\SKILL.md
```

En cas de ligne `[MANQUANT]`, relancer :

```bat
python install.py
```

---

## 5. Mettre a jour le projet

### Toi

```bat
robocopy "D:\easyshopeht\image_finder" "D:\image-finder" /E /XD __pycache__ images test_ia_voitures test_voitures /XF *.pyc
cd /d D:\image-finder
git add .
git commit -m "Mise a jour Image Finder"
git push
```

### Ton ami

```bat
cd /d C:\tools\image-finder
git pull
python install.py
```

Puis redemarrer OpenCode.

---

## 6. Donner le projet sans GitHub

Cree un zip de la copie propre :

```bat
Compress-Archive -Path "D:\image-finder\*" -DestinationPath "D:\image-finder.zip"
```

Ton ami decompresse, ouvre un terminal dans le dossier et lance :

```bat
python install.py
```

---

## 7. Ce que l'installateur modifie

- **Global** : `C:\Users\<nom>\.config\opencode\opencode.jsonc` (ou
  `opencode.json`) et `...\.config\opencode\skills\image-downloader\SKILL.md`.
- **Projet** : `<projet>\opencode.json` et
  `<projet>\.opencode\skills\image-downloader\SKILL.md`.

Une sauvegarde `.bak-AAAAMMJJ-HHMMSS` est creee avant toute modification de la
configuration. L'installateur reecrit la configuration en JSON simple : les
commentaires eventuels du fichier JSONC ne sont pas conserves, mais la
sauvegarde permet de les retrouver.

Aucun secret n'est stocke dans le projet. Les images telechargees et les
dossiers de test sont ignores par `.gitignore`.

---

## 8. Depannage

| Probleme | Solution |
|---|---|
| L'outil n'apparait pas dans OpenCode | Redemarrer OpenCode, puis `python install.py --check` |
| `python` inconnu | Utiliser `py -3` |
| `pip` inconnu | `python -m pip install -r requirements.txt` |
| Configuration invalide | Restaurer la sauvegarde `.bak-*` puis relancer `python install.py` |
| Yandex timeout / captcha | Le programme bascule sur Wikimedia Commons ; sinon `--source commons` |
| Depot imbrique dans EasyShop | Ne pas `git init` dans `image_finder` ; publier la copie `D:\image-finder` |
| L'ami a deja une config OpenCode | L'installateur fusionne l'entree `image-finder` sans supprimer le reste |
| Interface web ne demarre pas | Verifier que Flask et Waitress sont installes : `python -m pip install -r requirements.txt` |
| Acces serveur en ligne refuse | Lancer avec `--password "secret"` ou `--insecure` (deconseille) |

## Interface web v3 (deploiement serveur)

Une fois le depot clone :

```bat
cd /d C:\tools\image-finder
python install.py
python web_app.py --host 0.0.0.0 --port 8420 --password "mon-secret"
```

L'interface est alors accessible sur `http://<ip-du-serveur>:8420/`.

---
