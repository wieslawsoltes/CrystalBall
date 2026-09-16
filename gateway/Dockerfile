FROM python:3.13-slim
WORKDIR /opt/orb
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . && useradd --system --uid 10001 --no-create-home orb
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--workers","1","--no-access-log","--limit-concurrency","12","--timeout-keep-alive","5"]
