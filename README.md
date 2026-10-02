# Noeud national de donnees geospatiales — Cameroun (V1 vecteur)

Un noeud central de donnees geospatiales **souverain** : il aspire les donnees
OpenStreetMap du Cameroun dans une base centrale, accueille des donnees
institutionnelles a acces restreint, et publie le tout via une API standard
(OGC Features + tuiles vectorielles) visualisable sur une plateforme web avec
tableau de bord.

> **Principe directeur :** rien ne depend de la machine en-dessous.
> Le meme dossier tourne **aujourd'hui sur ton PC Windows**, **demain sur un VPS**,
> **apres-demain sur un NAS ou un datacenter** — sans une seule ligne a reecrire.

---

## Ce que contient cette V1

| Brique | Role | Technologie (100% libre) |
|---|---|---|
| Base centrale | Stocke le vecteur OSM + institutionnel | PostgreSQL + PostGIS |
| Ingestion OSM | Aspire l'extrait Cameroun | osm2pgsql + Geofabrik |
| Synchro OSM | Met a jour par differentiels | osm2pgsql-replication |
| API + tuiles | Publie les couches ouvertes (consommable par Urban Sanity) | TiPg (OGC Features + MVT) |
| Raster | Orthophotos (COG) + tuiles a la volee | MinIO + TiTiler |
| Service d'acces | Comptes, demandes, validation, liens temporaires | FastAPI |
| Plateforme web | Carte + tableau de bord + portail + admin | MapLibre GL JS |
| Modele d'acces | Ouvert / restreint | Schemas PostgreSQL (`catalog` vs `restricted`) |

**Les niveaux d'acces :**
- **Open data** (schema `catalog`) : visible ET telechargeable librement (bouton ⭳ sur la carte). C'est aussi ce que **Urban Sanity** consomme via l'API.
- **Restreint** (schema `restricted` : institutionnel + orthophotos) : visible, mais **telechargement sur demande approuvee par un admin**. L'API publique ne voit jamais ce schema.

---

## Prerequis (une seule installation)

1. **Docker Desktop pour Windows** — https://www.docker.com/products/docker-desktop/
   Installe-le, lance-le, attends que l'icone Docker (en bas a droite) soit verte.
2. *(Optionnel, pour explorer la base)* **QGIS** et/ou **DBeaver**.

Tout le reste (PostGIS, osm2pgsql, l'API...) est fourni par Docker : **rien d'autre a installer.**

---

## Demarrage (sur ta machine Windows)

Ouvre **PowerShell**, place-toi dans le dossier du projet, puis :

### 1. Preparer la configuration
```powershell
Copy-Item .env.example .env
```
Ouvre `.env` et change au moins : `POSTGRES_PASSWORD`, `MINIO_PASSWORD`,
`JWT_SECRET`, et mets **ton** email dans `ADMIN_EMAIL` (le compte cree avec cet
email deviendra automatiquement administrateur).

### 2. Lancer la base + l'API + le web
```powershell
docker compose up -d --build
```
Au premier lancement, Docker telecharge les images (quelques minutes).
Verifie que tout tourne :
```powershell
docker compose ps
```

### 3. Importer les donnees OSM du Cameroun
```powershell
docker compose run --rm loader
```
Le script telecharge l'extrait Cameroun (Geofabrik), l'importe dans PostGIS,
puis cree les couches publiees. **Compte quelques minutes.**

### 4. Rendre les nouvelles couches visibles a l'API
```powershell
docker compose restart api
```

### 5. Ouvrir la plateforme

Tout passe par **une seule porte d'entrée** (la passerelle Caddy sur le port 8080) :

| Page / service | Adresse |
|---|---|
| **Carte + tableau de bord** | http://localhost:8080 |
| **Portail données restreintes** | http://localhost:8080/portal.html |
| **Administration** | http://localhost:8080/admin.html |
| API vecteur (via la passerelle) — pour Urban Sanity | http://localhost:8080/api |
| Tuiles raster (via la passerelle) | http://localhost:8080/tiles |
| Service d'accès (via la passerelle) | http://localhost:8080/access |

Ports directs (pratiques pour QGIS / debug) : PostGIS `5432`, TiPg `8000`,
TiTiler `8001`, service d'accès `8002`, console MinIO `9001`.

> **Conflit de port ?** Si le 8080 est déjà pris (ex. GeoServer), change
> `"8080:80"` en `"8090:80"` dans le service `web` du `docker-compose.yml`.

Tu dois voir le Cameroun se dessiner et les compteurs se remplir. 🎉

### 6. Créer ton compte administrateur

1. Va sur **http://localhost:8080/portal.html**, onglet **Créer un compte**, et
   inscris-toi avec **l'email que tu as mis dans `ADMIN_EMAIL`**. Ce compte est admin.
2. Pour valider les demandes des autres : **http://localhost:8080/admin.html**.

---

## Télécharger les données

- **Open data** : bouton **⭳** à côté de chaque couche sur la carte → GeoJSON direct, sans compte.
- **Données restreintes** (institutionnel + orthophotos) : sur le **portail**, l'utilisateur
  crée un compte, **demande** le jeu voulu (avec une raison). L'**admin** approuve dans
  `admin.html`, puis un **lien de téléchargement temporaire** (24 h) apparaît chez le demandeur.

---

## Brancher Urban Sanity (ou tout autre outil)

Ta plateforme devient la **source fiable**. Urban Sanity pointe simplement vers ton API :

```
# Liste des couches disponibles
GET http://TON_SERVEUR:8080/api/collections

# Récupérer une couche en GeoJSON, filtrée par zone (bbox = minLon,minLat,maxLon,maxLat)
GET http://TON_SERVEUR:8080/api/collections/catalog.routes/items?bbox=9.6,3.8,11.6,4.2&f=geojson
```

En local `TON_SERVEUR` = `localhost` ; une fois en ligne, ce sera l'IP ou le domaine.
**Côté Urban Sanity, il suffit de changer l'URL de la source de données.**

---

## Synchro OSM planifiée (mise à jour quasi-temps-réel)

Pour appliquer les changements OSM récents, sans tout réimporter :
```powershell
docker compose run --rm sync
```
Pour **automatiser**, crée une tâche planifiée qui lance cette commande (ex. chaque nuit) :
- **Windows** : Planificateur de tâches → action « Démarrer un programme » →
  `docker` avec les arguments `compose run --rm sync` (dossier de départ = ton projet).
- **VPS (Linux)** : une ligne cron, ex. tous les jours à 2h :
  `0 2 * * * cd /chemin/projet && docker compose run --rm sync`

---

## Explorer la base avec QGIS ou DBeaver

Connexion PostGIS :
- **Hote :** `localhost`  · **Port :** `5432`
- **Base :** `cameroon` (ou ta valeur `POSTGRES_DB`)
- **Utilisateur / mot de passe :** ceux de ton `.env`

Tu verras trois schemas : `public` (OSM brut), `catalog` (couches publiees),
`restricted` (institutionnel). C'est la que tu **inseres tes donnees
institutionnelles** (table `restricted.projets_institutionnels`).

---

## Ajouter une orthophoto (raster / drone)

Le raster suit une architecture propre : **les pixels vivent dans MinIO** (stockage
objet, en COG), **le catalogue vit dans PostGIS** (emprise + métadonnées), et
**TiTiler** sert les tuiles à la volée pour la superposition.

1. Dépose ton GeoTIFF dans le dossier `ortho_in/` du projet.
2. Lance l'ingestion (conversion COG + envoi MinIO + enregistrement de l'emprise) :
   ```powershell
   docker compose run --rm ortho /data/in/mon_vol.tif "Vol Douala 2026"
   ```
3. Recharge http://localhost:8080 : l'orthophoto apparaît dans la section
   **Orthophotos (raster)** — coche-la pour la superposer, règle l'opacité.

Consoles utiles :
- **MinIO (gestion des images) :** http://localhost:9001
- **TiTiler (tuiles raster) :** http://localhost:8001

> Les **emprises** (couverture) sont ouvertes ; les **pixels** seront filtrés par
> niveau d'accès quand la passerelle (APISIX) sera ajoutée. Aujourd'hui, la
> superposition est ouverte pour la démonstration.

---

## Maintenance : ajouter des couches, des données, migrer

Pensé pour être simple à faire évoluer :

**Ajouter une couche ouverte** → crée une **vue** dans le schéma `catalog`
(fichier `sql/02_views.sql`, ou directement en SQL), avec une colonne géométrie
nommée `geom` en 4326. Exemple :
```sql
CREATE VIEW catalog.ecoles AS
SELECT osm_id AS id, name AS nom, ST_Transform(way,4326) AS geom
FROM public.planet_osm_point WHERE amenity='school';
```
Puis `docker compose restart api`. **La couche apparaît toute seule** dans la
plateforme (la carte découvre automatiquement les couches du schéma `catalog`) —
rien à modifier dans le code web.

**Ajouter des données institutionnelles** → deux étapes :
1. Charge la donnée géo dans une table du schéma `restricted` (via QGIS/ogr2ogr).
2. Décris-la dans le **catalogue structuré** `restricted.catalogue_institutionnel` :
   ```sql
   INSERT INTO restricted.catalogue_institutionnel
     (nom_jeu, nom_institut_source, theme, date_collecte, format_import, personne_organisme, niveau_acces, table_ref)
   VALUES ('Réseau eau Douala','CAMWATER','eau','2025-03-12','shapefile',
           'Service SIG CAMWATER','institutionnel','reseau_eau_douala');
   ```
   Champs : nom du jeu, **institut/source**, **thème** (eau, drains, santé…),
   **date de collecte**, **format d'import**, **personne/organisme**, niveau d'accès,
   et `table_ref` = la table qui porte la donnée. Le jeu devient alors demandable
   sur le portail **avec toutes ses métadonnées affichées**.

**Ajouter une orthophoto** → `docker compose run --rm ortho /data/in/vol.tif "Nom"`.

**Mettre à jour l'OSM** → `docker compose run --rm sync` (différentiels).

**Migrer vers une autre machine** (VPS → NAS → datacenter) → tout est portable :
```bash
# sauvegarde complète de la base
docker compose exec db pg_dump -U cgn -Fc cameroon > cameroon.dump
# sur la nouvelle machine : copie le dossier + le dump, puis
docker compose up -d --build
docker compose exec -T db pg_restore -U cgn -d cameroon --clean < cameroon.dump
```
Les orthophotos (MinIO) se transportent en copiant le volume `miniodata` ou via
`mc mirror`. **Aucune ligne de code à réécrire.**

---

## Déployer en ligne — gratuitement — tout le process

Deux chemins gratuits, selon ton besoin.

### Option 1 — Mise en ligne instantanée (démo) : tunnel Cloudflare

Ta stack tourne sur ton PC ; un **tunnel** lui donne une URL publique en HTTPS,
gratuitement. Idéal pour montrer la plateforme (au jury, à un partenaire).
*Limite : en ligne seulement quand ton PC est allumé et la stack démarrée.*

1. Lance ta stack : `docker compose up -d`
2. Installe **cloudflared** (Cloudflare Tunnel), gratuit.
3. Une commande :
   ```
   cloudflared tunnel --url http://localhost:8080
   ```
4. Cloudflare affiche une URL publique `https://xxxx.trycloudflare.com` →
   **c'est ta plateforme en ligne**, tout de suite. (ngrok fait pareil.)

Comme tout passe par la passerelle (port 8080), **une seule URL suffit** : la
carte, l'API (`/api`), les tuiles (`/tiles`) et le portail fonctionnent.

### Option 2 — Serveur en ligne permanent et gratuit : Oracle Cloud « Always Free »

Pour une plateforme **toujours accessible**, sans payer : Oracle Cloud offre une
VM **gratuite à vie** (ARM, jusqu'à 4 cœurs / 24 Go RAM) — largement assez.
*(Alternatives gratuites limitées : Google Cloud / AWS free tier, mais 12 mois
et plus petites.)*

Le processus :
1. Crée un compte **Oracle Cloud Free Tier**, puis une instance **« Always Free »**
   (image **Ubuntu**, forme **Ampere A1**).
2. Autorise les ports **80** et **443** (et **22** pour SSH) dans la sécurité réseau.
3. Connecte-toi en SSH, installe Docker :
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
4. Copie ton dossier projet sur le serveur (`scp`, `git clone`, ou glisser via SFTP).
5. Crée le `.env` (mots de passe forts ; mets `MINIO_PUBLIC_ENDPOINT=IP_DU_SERVEUR:9000`).
6. Pour servir sur le port 80 : dans `docker-compose.yml`, service `web`, mets
   `"80:80"` (au lieu de `8080:80`).
7. Lance :
   ```bash
   docker compose up -d --build
   docker compose run --rm loader
   docker compose restart api
   ```
8. Ouvre `http://IP_DU_SERVEUR`. 🎉

**HTTPS + nom de domaine (gratuit, recommandé)** : prends un sous-domaine gratuit
(ex. DuckDNS) ou un domaine, fais-le pointer vers l'IP, puis remplace `:80` par
ton domaine dans le `Caddyfile` : Caddy obtient **automatiquement un certificat
HTTPS gratuit** (Let's Encrypt). Plus rien à configurer.

> **Souveraineté :** quand tu voudras, tu reprends exactement ce dossier et tu le
> poses sur un **NAS au Cameroun** ou un **datacenter national**. Même commande,
> mêmes données — c'est le sens de « aujourd'hui un VPS, demain un NAS ».

---

## Passer sur le VPS (le moment venu)

C'est la partie qui prouve la portabilite. Sur le VPS (Ubuntu) :

1. Installe Docker.
2. Copie **ce meme dossier** (via `git clone` ou `scp`).
3. Cree le `.env` (mot de passe fort !).
4. Lance exactement les memes commandes :
   ```bash
   docker compose up -d --build
   docker compose run --rm loader
   docker compose restart api
   ```
La carte est alors accessible sur `http://IP_DU_VPS:8080` et l'API sur `:8000`.
**Aucune modification du code.** La page web detecte automatiquement l'hote.

### Transporter aussi les donnees (au lieu de re-importer)
```bash
# Sur la source : creer un dump
docker compose exec db pg_dump -U cgn -Fc cameroon > cameroon.dump
# Sur la cible : restaurer
docker compose exec -T db pg_restore -U cgn -d cameroon --clean < cameroon.dump
```

---

## Commandes utiles

```powershell
docker compose logs -f api      # voir les logs de l'API
docker compose down             # tout arreter (les donnees restent)
docker compose down -v          # tout arreter ET effacer les donnees
```

---

## Prochaines etapes (phases suivantes, hors V1)

- **Niveaux d'acces** : placer une passerelle (APISIX) devant l'API pour gerer
  cles API, quotas et acces premium.
- **Synchro planifiee** : tache cron qui applique les diffs OSM (quasi-temps-reel).
- **Modele de donnees camerounais** : enrichir `restricted` (cadastre coutumier,
  habitat informel, voirie non-bitumee).

---

*Souverainete = tout en conteneurs, que du libre, aucun verrou proprietaire.
Le noeud se transporte, il ne se reecrit pas.*
