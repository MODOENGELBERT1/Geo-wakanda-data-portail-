-- =============================================================================
--  Noeud national de donnees geospatiales - Cameroun
--  01 - Initialisation : extensions, schemas, modele d'acces
--  Ce script s'execute AUTOMATIQUEMENT au premier demarrage de la base.
-- =============================================================================

-- 1. Extensions requises
--    postgis : types et fonctions geo (le coeur)
--    hstore  : type cle-valeur utilise par osm2pgsql pour stocker les tags OSM
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS hstore;

-- 2. Les trois espaces de donnees = les trois niveaux de souverainete
--    public     : donnees OSM brutes importees par osm2pgsql (non exposees telles quelles)
--    catalog    : couches OUVERTES, propres, publiees par l'API (Niveau 1 - Open Data)
--    restricted : donnees INSTITUTIONNELLES / sensibles / payantes (Niveau 2 et 3)
CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS restricted;

COMMENT ON SCHEMA catalog   IS 'Donnees ouvertes publiees par l API (Niveau 1 - libre)';
COMMENT ON SCHEMA restricted IS 'Donnees institutionnelles / sensibles / payantes (Niveaux 2-3 - acces controle)';

-- 3. Exemple de table INSTITUTIONNELLE a acces restreint.
--    Elle vit dans le schema "restricted" : l'API publique (TiPg) ne la voit pas,
--    car TiPg n'est autorise que sur le schema "catalog" (cf. docker-compose.yml).
--    C'est ici que tu inseres les donnees que tu recois des institutions et
--    que tu pourras valoriser (vendre / partenariats).
CREATE TABLE IF NOT EXISTS restricted.projets_institutionnels (
    id           bigserial PRIMARY KEY,
    nom          text            NOT NULL,
    organisation text,                       -- source institutionnelle (mairie, ministere, BET...)
    categorie    text,                       -- ex : cadastre, reseau_eau, zone_risque
    niveau_acces text  DEFAULT 'institutionnel',  -- institutionnel | premium
    date_ajout   date  DEFAULT CURRENT_DATE,
    geom         geometry(Geometry, 4326)    -- 4326 = WGS84 (lat/lon), le standard web
);

CREATE INDEX IF NOT EXISTS idx_projets_inst_geom
    ON restricted.projets_institutionnels USING GIST (geom);

-- 4. CATALOGUE structure des donnees institutionnelles.
--    Chaque ligne = un jeu de donnees recu d'une institution, avec ses
--    metadonnees normalisees. 'table_ref' pointe vers la table restricted qui
--    porte reellement la donnee geographique (telechargee a l'approbation).
CREATE TABLE IF NOT EXISTS restricted.catalogue_institutionnel (
    id                   bigserial PRIMARY KEY,
    nom_jeu              text        NOT NULL,                 -- nom du jeu de donnees
    nom_institut_source  text,                                 -- institution / source (MINEE, mairie, BET...)
    theme                text,                                 -- eau | drains | sante | assainissement | cadastre | ...
    date_collecte        date,                                 -- date de collecte sur le terrain
    format_import        text,                                 -- shapefile | geojson | csv | gpkg | kml ...
    personne_organisme   text,                                 -- personne ou organisme fournisseur (contact)
    niveau_acces         text        DEFAULT 'institutionnel', -- institutionnel | premium
    table_ref            text,                                 -- table restricted qui porte la donnee
    date_ajout           timestamptz DEFAULT now()
);

COMMENT ON TABLE restricted.catalogue_institutionnel
    IS 'Registre structure des jeux institutionnels (source, theme, date de collecte, format, contact)';

-- Donnees d'exemple (a remplacer par tes vrais jeux)
INSERT INTO restricted.projets_institutionnels (nom, organisation, categorie, niveau_acces, geom)
VALUES
  ('Zone pilote cadastre - Yaounde', 'Exemple / a remplacer', 'cadastre',   'institutionnel',
     ST_SetSRID(ST_MakePoint(11.5021, 3.8480), 4326)),
  ('Reseau eau - secteur Douala',    'Exemple / a remplacer', 'reseau_eau', 'premium',
     ST_SetSRID(ST_MakePoint(9.7679, 4.0511), 4326))
ON CONFLICT DO NOTHING;

INSERT INTO restricted.catalogue_institutionnel
  (nom_jeu, nom_institut_source, theme, date_collecte, format_import, personne_organisme, niveau_acces, table_ref)
VALUES
  ('Reseau d''eau potable - Douala', 'CAMWATER', 'eau',   '2025-03-12', 'shapefile',
     'Ing. M. Service SIG CAMWATER', 'institutionnel', 'projets_institutionnels'),
  ('Reseau de drains - Yaounde',     'Communaute Urbaine de Yaounde', 'drains', '2024-11-05', 'geojson',
     'Direction technique CUY', 'institutionnel', 'projets_institutionnels'),
  ('Centres de sante - Centre',      'MINSANTE', 'sante', '2025-01-20', 'csv',
     'Cellule informatique MINSANTE', 'premium', 'projets_institutionnels')
ON CONFLICT DO NOTHING;
