# Modifications à venir - Image Finder v3.5.0+

## Déploiement distant / nom de domaine

**Objectif** : pouvoir accéder à l'interface web depuis n'importe où (smartphone, autre PC, bureau distant) sans laisser son ordinateur allumé en permanence.

### Idées à implémenter

1. **Nom de domaine**
   - Acheter un domaine (ex: `imagefinder.mon-domaine.com`)
   - DNS `A` pointant vers l'IP du serveur hébergeant `web_app.py`
   - Documentation dans `GUIDE_PARTAGE.md` pour configurer le DNS

2. **Hébergement 24/7**
   - Option A : laisser un PC allumé avec `python web_app.py --host 0.0.0.0 --password "secret"`
   - Option B : VPS (serveur privé virtuel) tournant en continu
   - Option C : Raspberry Pi chez soi avec IP fixe ou DNS dynamique

3. **Accès distant sécurisé**
   - `--host 0.0.0.0` pour écouter sur toutes les interfaces
   - `--password` obligatoire (déjà implémenté)
   - Port forwarding sur la box/routeur (port 8420 par défaut)
   - Ou reverse proxy (nginx, Cloudflare Tunnel, Tailscale, ngrok pour tester)

4. **HTTPS / SSL**
   - Certificat Let's Encrypt pour le domaine
   - Reverse proxy devant Flask/Waifress pour terminer le TLS
   - Ne pas exposer Flask directement sur Internet en production

5. **Accès smartphone**
   - L'interface est déjà responsive (v3.0+)
   - Tester sur navigateur mobile une fois en ligne

### Fichiers concernés
- `web_app.py` (options `--host`, `--port`, `--password`, `--insecure`)
- `README.md` (section déploiement serveur à compléter)
- `GUIDE_PARTAGE.md` (instructions ami + serveur distant)
- Nouveau fichier `DEPLOYMENT.md` (guide complet hébergement distant)

### Statut
Non implémenté — à faire dans une version future (v3.5.0 ou v4.0.0).

## Autres idées en attente (backlog)

- Vue grille / vue liste (colonnes : nom, taille, dimensions, date)
- Filtres avancés (dimensions, licence, source, format)
- Tri manuel par glisser-déposer
- Renommage en lot d'images sélectionnées
- Raccourcis clavier (flèches, Espace pour aperçu rapide, Suppr)
- Aperçu rapide (Quick Look) sans ouvrir la lightbox complète
- Import d'images existantes (glisser-déposer depuis l'ordinateur)
- Export de la bibliothèque (CSV / JSON avec métadonnées)
- Confirmation avant téléchargement groupé
- Indicateur de progression pendant téléchargement en lot
- Gestion d'image supprimée entre sélection et téléchargement
