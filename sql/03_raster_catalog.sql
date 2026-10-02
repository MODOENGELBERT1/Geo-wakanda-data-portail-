-- =============================================================================
--  Noeud national de donnees geospatiales - Cameroun
--  03 - Catalogue RASTER (orthophotos)
--  Applique automatiquement par le script add-ortho.sh (idempotent).
--
--  PRINCIPE : les PIXELS vivent dans MinIO (COG), pas ici.
--  Cette table ne garde que le CATALOGUE : metadonnees + emprise + chemin S3.
-- =============================================================================

CREATE TABLE IF NOT EXISTS restricted.orthophotos (
    id            bigserial PRIMARY KEY,
    nom           text        NOT NULL,
    s3_path       text        NOT NULL,          -- ex : s3://orthophotos/vol_douala_2026.tif
    date_vol      date,
    resolution_cm numeric,                       -- resolution au sol (cm/pixel)
    niveau_acces  text        DEFAULT 'premium', -- institutionnel | premium
    date_ajout    timestamptz DEFAULT now(),
    emprise       geometry(Polygon, 4326)        -- footprint en WGS84
);

CREATE INDEX IF NOT EXISTS idx_ortho_emprise
    ON restricted.orthophotos USING GIST (emprise);

-- Vue OUVERTE : uniquement les EMPRISES + metadonnees, jamais les pixels.
-- Elle permet a la carte publique de montrer OU une orthophoto est disponible
-- (la couverture), sans donner l'image elle-meme.
-- NB : s3_path est expose ici pour la demo de superposition ; en production,
--      l'acces aux pixels (TiTiler) passera par la passerelle (APISIX) selon
--      le niveau_acces. La couverture reste ouverte, les pixels sont gated.
DROP VIEW IF EXISTS catalog.orthophotos_couverture CASCADE;
CREATE VIEW catalog.orthophotos_couverture AS
SELECT
    id,
    nom,
    date_vol,
    resolution_cm,
    niveau_acces,
    s3_path,
    emprise AS geom
FROM restricted.orthophotos;

COMMENT ON VIEW catalog.orthophotos_couverture
    IS 'Couverture des orthophotos (emprises) - metadonnees ouvertes, pixels gardes dans MinIO';
