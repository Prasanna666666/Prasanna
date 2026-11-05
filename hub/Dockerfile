# Home: one address for every private app. Standard library only: nothing is installed but the code itself.
FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hub
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .
USER 10001
ENV PYTHONDONTWRITEBYTECODE=1 HUB_HOST=0.0.0.0 HUB_PORT=8000 HUB_MODULES_DIR=/app/modules.d
CMD ["python", "-m", "hub"]
