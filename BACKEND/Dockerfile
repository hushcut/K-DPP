# 배포용 백엔드 이미지. 빌드 문맥은 저장소 루트입니다 — main.py 가 ../AI 의 OCR 모듈을
# 불러오기 때문입니다. 보통은 deploy/compose.yaml 이 빌드합니다(deploy/README.md).
#   docker build -f BACKEND/Dockerfile -t k-dpp-app:local .   # 저장소 루트에서 직접
# 이미지에 무엇이 들어가는지는 같은 폴더의 Dockerfile.dockerignore 가 정합니다.

# CI 와 같은 Python 3.12. 마이너 안의 보안 패치는 `docker compose build --pull` 로 받습니다.
FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/BACKEND

# 의존성을 먼저 깔아 두면 코드만 바뀔 때 이 층을 다시 쓰지 않습니다.
COPY BACKEND/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# 저장소와 같은 상대 위치(/app/AI, /app/BACKEND)에 둡니다(main.py 의 AI_MODULE_PATH).
COPY AI/kdpp_ai_ocr_integrated/apps /app/AI/kdpp_ai_ocr_integrated/apps
COPY BACKEND/ ./

# main.py 는 AI 모듈 import 실패를 삼켜 실사진 스캔이 전부 503 이 됩니다. CI 와 같은
# 검사를 빌드에서 돌려, 결합이 끊긴 이미지는 아예 만들어지지 않게 합니다.
RUN python check_ai_wiring.py

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER app

EXPOSE 8000

# 워커는 1개입니다 — 로그인 잠금(5회 실패 시 60초)을 프로세스 메모리에 두므로 워커를
# 늘리면 잠금이 워커마다 갈립니다. 앞단 Caddy 가 넘긴 X-Forwarded-For 를 믿어 로그에
# 실제 접속 주소가 남게 합니다(앱 포트는 Compose 안쪽에만 열려 있음).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
