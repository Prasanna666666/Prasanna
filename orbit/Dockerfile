# The Finance app image (build from the repository root: it carries the shared kit and Finance). It opens no files and has NO document-parsing libraries: the Documents service (../library) reads every file and mail.
FROM python:3.12-slim AS base
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin orbit \
 && mkdir /data /parsed && chown 10001 /data /parsed
WORKDIR /app
COPY kit /app/kit
COPY orbit /app/orbit
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 ORBIT_HOME=/data

FROM base AS app
# The secure (encrypted) database: sqlcipher3-binary has no prebuilt version for Linux on Apple chips, so build the library against the
# system SQLCipher, then remove the compilers again (the runtime library, installed as a dependency, stays: no auto-remove).
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libsqlcipher-dev
RUN MAKEFLAGS=-j1 pip install --no-cache-dir sqlcipher3
RUN pip install --no-cache-dir ./kit ./orbit
RUN apt-get purge -y build-essential libsqlcipher-dev && rm -rf /var/lib/apt/lists/*
USER 10001
ENV ORBIT_REQUIRE_ENCRYPTION=1
ENTRYPOINT ["orbit"]
CMD ["ui", "--host", "0.0.0.0", "--port", "8501"]
