# One source, two images with different contents:
#   app    - UI/assistant/database. Has the encryption library, but NO document-parsing libraries.
#   parser - opens untrusted files (PyMuPDF). Runs with no network; the app never contains this code.
FROM python:3.12-slim AS base
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin orbit \
 && mkdir /data /parsed && chown 10001 /data /parsed
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 ORBIT_HOME=/data

FROM base AS app
RUN pip install --no-cache-dir ".[ui,secure]"
USER 10001
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false ORBIT_REQUIRE_ENCRYPTION=1
ENTRYPOINT ["orbit"]
CMD ["ui", "--server.address", "0.0.0.0", "--server.headless", "true", "--server.port", "8501"]

FROM base AS parser
RUN pip install --no-cache-dir ".[parse]"
USER 10001
ENTRYPOINT ["orbit-parser"]
CMD ["--watch"]
