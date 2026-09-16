# Repository-root build context; .dockerignore excludes all private configuration.
FROM python:3.13-slim
WORKDIR /opt/orb
COPY gateway/pyproject.toml ./
COPY gateway/app ./app
COPY web ./web
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --no-create-home orb \
    && mkdir -p /var/lib/orb \
    && chown 10001:10001 /var/lib/orb
ENV WEB_DIRECTORY=/opt/orb/web BUDGET_DATABASE=/var/lib/orb/budget.sqlite
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--workers","1","--no-access-log","--limit-concurrency","12","--timeout-keep-alive","5"]
