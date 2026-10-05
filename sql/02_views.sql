-- =============================================================================
--  Noeud national de donnees geospatiales - Cameroun
--  02 - Couches publiees (schema "catalog")
--  A JOUER APRES l'import OSM (le script load-osm.sh s'en charge),
--  car ces vues s'appuient sur les tables creees par osm2pgsql.
--
--  osm2pgsql cree par defaut : planet_osm_point / _line / _polygon / _roads
--  avec une geometrie "way" en projection 3857 (Web Mercator).
--  On la reprojette en 4326 (WGS84) pour l'API OGC Features.
-- =============================================================================

-- Batiments -------------------------------------------------------------------
DROP VIEW IF EXISTS catalog.batiments CASCADE;
CREATE VIEW catalog.batiments AS
SELECT
    osm_id                          AS id,
    name                            AS nom,
    building                        AS type_batiment,
    ST_Transform(way, 4326)         AS geom
FROM public.planet_osm_polygon
WHERE building IS NOT NULL;

-- Routes / voirie -------------------------------------------------------------
DROP VIEW IF EXISTS catalog.routes CASCADE;
CREATE VIEW catalog.routes AS
SELECT
    osm_id                          AS id,
    name                            AS nom,
    highway                         AS type_route,
    ST_Transform(way, 4326)         AS geom
FROM public.planet_osm_line
WHERE highway IS NOT NULL;

-- Cours d'eau -----------------------------------------------------------------
DROP VIEW IF EXISTS catalog.cours_eau CASCADE;
CREATE VIEW catalog.cours_eau AS
SELECT
    osm_id                          AS id,
    name                            AS nom,
    waterway                        AS type_cours_eau,
    ST_Transform(way, 4326)         AS geom
FROM public.planet_osm_line
WHERE waterway IS NOT NULL;

-- Limites administratives -----------------------------------------------------
DROP VIEW IF EXISTS catalog.limites_admin CASCADE;
CREATE VIEW catalog.limites_admin AS
SELECT
    osm_id                          AS id,
    name                            AS nom,
    admin_level                     AS niveau_admin,
    ST_Transform(way, 4326)         AS geom
FROM public.planet_osm_polygon
WHERE boundary = 'administrative';

-- Lieux (villes, villages, quartiers) -- sert a la RECHERCHE DE LIEU ----------
DROP VIEW IF EXISTS catalog.lieux CASCADE;
CREATE VIEW catalog.lieux AS
SELECT
    osm_id                          AS id,
    name                            AS nom,
    place                           AS type_lieu,
    ST_Transform(way, 4326)         AS geom
FROM public.planet_osm_point
WHERE place IS NOT NULL AND name IS NOT NULL;

-- Points d'interet (POI : services, commerces, tourisme, loisirs) -------------
DROP VIEW IF EXISTS catalog.points_interet CASCADE;
CREATE VIEW catalog.points_interet AS
SELECT
    osm_id                                                   AS id,
    name                                                     AS nom,
    COALESCE(amenity, shop, tourism, leisure, office)        AS categorie,
    ST_Transform(way, 4326)                                  AS geom
FROM public.planet_osm_point
WHERE amenity IS NOT NULL OR shop IS NOT NULL OR tourism IS NOT NULL
   OR leisure IS NOT NULL OR office IS NOT NULL;

-- Usage du sol (polygones : landuse / naturel / loisirs) ----------------------
DROP VIEW IF EXISTS catalog.usage_sol CASCADE;
CREATE VIEW catalog.usage_sol AS
SELECT
    osm_id                                                   AS id,
    name                                                     AS nom,
    COALESCE(landuse, "natural", leisure)                    AS type_usage,
    ST_Transform(way, 4326)                                  AS geom
FROM public.planet_osm_polygon
WHERE landuse IS NOT NULL OR "natural" IS NOT NULL OR leisure IS NOT NULL;

-- Frontiere nationale (sert au MASQUE permanent sur le Cameroun) --------------
DROP VIEW IF EXISTS catalog.pays CASCADE;
CREATE VIEW catalog.pays AS
SELECT
    osm_id                          AS id,
    name                            AS nom,
    ST_Transform(way, 4326)         AS geom
FROM public.planet_osm_polygon
WHERE boundary = 'administrative' AND admin_level = '2';

-- Commentaires (servent de description dans l'API)
COMMENT ON VIEW catalog.batiments     IS 'Batiments OSM du Cameroun (donnee ouverte)';
COMMENT ON VIEW catalog.routes        IS 'Reseau routier OSM du Cameroun (donnee ouverte)';
COMMENT ON VIEW catalog.cours_eau     IS 'Cours d eau OSM du Cameroun (donnee ouverte)';
COMMENT ON VIEW catalog.limites_admin IS 'Limites administratives OSM du Cameroun (donnee ouverte)';
COMMENT ON VIEW catalog.lieux           IS 'Lieux habites OSM (recherche de lieu)';
COMMENT ON VIEW catalog.points_interet  IS 'Points d interet OSM : services, commerces, tourisme (donnee ouverte)';
COMMENT ON VIEW catalog.usage_sol       IS 'Usage du sol OSM : landuse, naturel, loisirs (donnee ouverte)';
