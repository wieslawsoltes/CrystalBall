#!/usr/bin/env bash
set -euo pipefail
mkdir -p verification/container
cleanup() {
  docker logs orb-ci >verification/container/log.txt 2>&1 || true
  docker rm -f orb-ci || true
  docker volume rm orb-ci-budget || true
  rm -f gateway/.env
}
trap cleanup EXIT
cp gateway/.env.example gateway/.env
docker compose -f gateway/compose.yaml config --quiet
rm gateway/.env
docker build -t crystalball-ci -f gateway/Dockerfile .
# Non-secret invalid provider credential. Health/static checks never call OpenAI.
docker run -d --name orb-ci --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:size=16m --mount type=volume,source=orb-ci-budget,target=/var/lib/orb -p 127.0.0.1:8099:8080 -e 'ALLOWED_HOSTS=127.0.0.1,localhost' -e OPENAI_API_KEY=ci-placeholder-not-a-real-key -e 'DEVICE_TOKEN_SHA256={"ci":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' crystalball-ci
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8099/healthz; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8099/ >verification/container/index.html
grep -q 'CrystalBall' verification/container/index.html
docker exec orb-ci python -c "import os; assert os.getuid()==10001; assert os.path.isfile('/var/lib/orb/budget.sqlite'); assert not os.path.exists('/opt/orb/.env')"
docker inspect crystalball-ci --format '{{.Id}}' >verification/container/image-id.txt
printf 'PASS: read-only root; UID 10001; SQLite volume; web assets; no paid API calls.\n' >verification/container/result.txt
