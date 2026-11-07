# Documents: one source, three images with different contents (build from the repository root: the images carry the shared kit in ../kit and the picture engine in ../images, and nothing of Finance).
#   app     - the service, its encrypted database and the model calls. Has the encryption library and the picture engine (to search), but NO document readers.
#   parser  - opens untrusted files (PDF, images, spreadsheets, mail). Runs with no network and sees the files read-only; the app never contains this code.
#   indexer - reads the photo folder with the picture engine and its models. Runs with no network and sees the photos read-only.
FROM python:3.12-slim AS base
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin library \
 && mkdir /data /parsed && chown 10001 /data /parsed
WORKDIR /app
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 ATLAS_HOME=/data

FROM base AS app
# sqlcipher3-binary has no prebuilt version for Linux on Apple chips, so build the library against the system SQLCipher, then remove the compilers again.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libsqlcipher-dev
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache MAKEFLAGS=-j1 pip install sqlcipher3
# the big, slow part (PyTorch) comes before the code, so a code change does not reinstall it; pip's download cache is kept between builds
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY kit /app/kit
COPY images /app/images
COPY library /app/library
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache pip install ./kit "./images[ml]" ./library
RUN apt-get purge -y build-essential libsqlcipher-dev && rm -rf /var/lib/apt/lists/*
USER 10001
ENV ATLAS_REQUIRE_ENCRYPTION=1 ATLAS_REQUIRE_SIGNATURE=1
ENTRYPOINT ["library"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8502"]

FROM base AS parser
# Tesseract (offline OCR, Dutch + English) reads scanned PDFs and photos of documents; everything else is read with Python libraries.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-nld poppler-utils && rm -rf /var/lib/apt/lists/*
COPY library /app/library
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache pip install "./library[parse]"
USER 10001
ENTRYPOINT ["library-parser"]
CMD ["--watch"]

FROM base AS indexer
# The picture indexer: the shared engine with its models (CPU PyTorch works on arm64 and x86), and Tesseract for the text in pictures. No network at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-nld build-essential libsqlcipher-dev \
 && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache MAKEFLAGS=-j1 pip install sqlcipher3 && apt-get purge -y build-essential
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY kit /app/kit
COPY images /app/images
COPY library /app/library
RUN --mount=type=cache,target=/pipcache PIP_CACHE_DIR=/pipcache pip install ./kit "./images[ml]" ./library
USER 10001
ENV APERTURE_NEVER_ONLINE=1 APERTURE_SANDBOXED=1 ATLAS_REQUIRE_ENCRYPTION=1
ENTRYPOINT ["library-indexer"]
