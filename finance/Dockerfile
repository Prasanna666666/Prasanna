# The Finance app image (build from the repository root: it carries the shared kit and Finance). It opens no files and has NO document-parsing libraries: the Documents service (../library) reads every file and mail.
FROM python:3.12-slim AS base
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin finance \
 && mkdir /data && chown 10001 /data
WORKDIR /app
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 ATLAS_HOME=/data

FROM base AS app
# The secure (encrypted) database: sqlcipher3-binary has no prebuilt version for Linux on Apple chips, so build the library against the
# system SQLCipher, then remove the compilers again (the runtime library, installed as a dependency, stays: no auto-remove).
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libsqlcipher-dev
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache MAKEFLAGS=-j1 pip install sqlcipher3
# the code comes after the slow part, so a code change rebuilds only what follows (pip's download cache is kept between builds)
COPY kit /app/kit
COPY finance /app/finance
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache pip install ./kit ./finance
RUN apt-get purge -y build-essential libsqlcipher-dev && rm -rf /var/lib/apt/lists/*
USER 10001
ENV ATLAS_REQUIRE_ENCRYPTION=1 ATLAS_REQUIRE_SIGNATURE=1
ENTRYPOINT ["finance"]
CMD ["ui", "--host", "0.0.0.0", "--port", "8501"]
