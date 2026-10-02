FROM python:3.11-slim

# gdal-bin fournit ogr2ogr (export GeoPackage / KML / Shapefile des donnees ouvertes).
RUN apt-get update && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# Service d'acces : API de comptes / demandes / validation / telechargement / export.
RUN pip install --no-cache-dir \
      fastapi "uvicorn[standard]" "psycopg[binary]" bcrypt pyjwt minio python-multipart

WORKDIR /app
# Le code est monte en volume (./app/access) pour faciliter la maintenance.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
