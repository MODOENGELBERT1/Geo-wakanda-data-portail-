FROM python:3.11-slim

# TiPg (Development Seed) : OGC API Features + Tuiles vectorielles au-dessus de PostGIS.
# Aucune ligne d'API a ecrire : TiPg publie automatiquement les tables et vues du schema autorise.
RUN pip install --no-cache-dir "tipg" "uvicorn[standard]"

EXPOSE 8000

# TiPg lit la variable d'environnement DATABASE_URL (definie dans docker-compose.yml)
CMD ["uvicorn", "tipg.main:app", "--host", "0.0.0.0", "--port", "8000"]
