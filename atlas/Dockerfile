# Atlas: one address for every private app. Standard library only (plus the shared kit's signing helper): nothing is installed from the internet.
# Build from the repository root.
FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin atlas
WORKDIR /app
COPY kit /app/kit
COPY atlas /app/atlas
RUN pip install --no-cache-dir --no-deps ./kit ./atlas
USER 10001
ENV PYTHONDONTWRITEBYTECODE=1 ATLAS_HOST=0.0.0.0 ATLAS_PORT=8000 ATLAS_MODULES_DIR=/app/modules.d
CMD ["python", "-m", "atlas"]
