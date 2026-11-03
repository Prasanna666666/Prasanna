FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin saathi \
 && mkdir /data && chown 10001 /data
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[ui]"
USER 10001
ENV SAATHI_HOME=/data HOME=/tmp STREAMLIT_BROWSER_GATHER_USAGE_STATS=false PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["saathi"]
CMD ["ui", "--server.address", "0.0.0.0", "--server.headless", "true", "--server.port", "8501"]
