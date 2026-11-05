# Documents: one source, two images with different contents (build from the repository root: the app image also carries the shared code in ../orbit).
#   app    - the service, its encrypted database and the model calls. Has the encryption library, but NO document-parsing libraries.
#   parser - opens untrusted files (PDF, images, spreadsheets, mail). Runs with no network and sees the files read-only; the app never contains this code.
FROM python:3.12-slim AS base
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin library \
 && mkdir /data /parsed && chown 10001 /data /parsed
WORKDIR /app
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 ORBIT_HOME=/data

FROM base AS app
# sqlcipher3-binary has no prebuilt version for Linux on Apple chips, so build the library against the system SQLCipher, then remove the compilers again.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libsqlcipher-dev
RUN MAKEFLAGS=-j1 pip install --no-cache-dir sqlcipher3
COPY orbit /app/orbit
COPY library /app/library
RUN pip install --no-cache-dir ./orbit ./library
RUN apt-get purge -y build-essential libsqlcipher-dev && rm -rf /var/lib/apt/lists/*
USER 10001
ENV ORBIT_REQUIRE_ENCRYPTION=1
ENTRYPOINT ["library"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8502"]

FROM base AS parser
# Tesseract (offline OCR, Dutch + English) reads scanned PDFs and photos of documents; everything else is read with Python libraries.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-nld poppler-utils && rm -rf /var/lib/apt/lists/*
COPY library /app/library
RUN pip install --no-cache-dir "./library[parse]"
USER 10001
ENTRYPOINT ["library-parser"]
CMD ["--watch"]
