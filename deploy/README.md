# K-DPP 배포 (Docker Compose)

서버 한 대에 **앱 + PostgreSQL + Caddy(자동 HTTPS)** 를 한 Compose 로 띄웁니다.
로컬 개발은 이 폴더가 아니라 `BACKEND/README.md`(DB 만 Compose, 앱은 venv)를 따릅니다.

```text
인터넷 ─ 80/443 ─▶ caddy ──▶ app:8000 ──▶ postgres:5432
                   (HTTPS)   (FastAPI)     (볼륨 pgdata)
                                ▲
                  migrate ──────┘ 시작 전에 `alembic upgrade head` 한 번
```

| 서비스 | 하는 일 | 밖으로 여는 포트 |
| --- | --- | --- |
| `postgres` | DB(`postgres:18-trixie`), 데이터는 볼륨 `pgdata` | 없음 |
| `migrate` | 표·소재를 최신 리비전으로 맞추고 종료 — 실패하면 `app` 이 시작하지 않음 | 없음 |
| `app` | 백엔드(`BACKEND/Dockerfile` 로 빌드), 워커 1개 | 없음 |
| `caddy` | HTTPS 인증서 자동 발급·갱신, http → https, 요청 본문 11MiB 상한 | 80, 443 |

## 서버 준비

- Docker Engine 25 이상(헬스체크 `start_interval`)과 Compose 플러그인(`docker compose version` 이 나와야 함).
- 방화벽: 22(SSH)·80·443(TCP)·443(UDP, HTTP/3) 만 엽니다. 5432·8000 은 열지 않습니다.
- 도메인의 DNS A 레코드가 서버 공인 IP 를 가리켜야 Caddy 가 인증서를 받습니다.
- 이미지는 **서버에서 빌드**합니다(맥 arm64 ↔ 서버 x86_64, 레지스트리 없음).

## 처음 배포

저장소를 받은 서버에서, 이 폴더(`deploy/`) 기준으로:

```sh
cp .env.example .env && chmod 600 .env
# .env 를 채웁니다: K_DPP_DOMAIN, POSTGRES_PASSWORD(openssl rand -hex 24)
mkdir -p secrets
sudo install -o 10001 -g 10001 -m 400 /경로/key.json secrets/vision_key.json   # 'Vision 키' 참고
docker compose up -d --build --wait
docker compose ps -a      # migrate: Exited (0), 나머지: healthy / Up
curl https://<도메인>/    # {"status":"success",...}
```

`--wait` 는 모든 서비스가 healthy 가 되거나 실패할 때까지 기다립니다. 실패하면
`docker compose logs migrate app` 부터 봅니다.

## 업데이트 (새 코드 배포)

**먼저 백업합니다.** `migrate` 가 새 리비전을 자동으로 적용하므로, 잘못된 리비전이면
되돌릴 길은 백업뿐입니다.

```sh
docker compose exec -T postgres pg_dump -U kdpp -d k_dpp -Fc > ~/k_dpp-$(date +%Y%m%d-%H%M).dump
git pull
docker compose up -d --build --wait   # postgres → migrate(새 리비전) → app 교체 → caddy
```

- 앱 컨테이너가 바뀌는 몇 초 동안 요청이 실패할 수 있습니다.
- 보안 패치: `docker compose pull postgres caddy` 와 `docker compose build --pull` 뒤 `up -d --wait`.
- 정기 백업·복구 연습은 아직 없습니다(다음 단계).

## Vision 키

- 앱은 `/run/secrets/vision_key` 를 `GOOGLE_APPLICATION_CREDENTIALS` 로 씁니다(저장소의
  `AI/…/key.json` 경로는 이미지에 들어가지 않습니다).
- 파일은 서버에서 그대로 연결되므로 **소유자·권한도 서버 파일 그대로**입니다. 앱은 uid
  10001 로 돌기 때문에 위의 `install -o 10001 -g 10001 -m 400` 처럼 넣어야 읽을 수 있습니다.
  못 읽으면 스캔이 502 가 되고 `docker compose logs app` 에 `[scan] OCR 실패` 가 남습니다.
- 키 없이 띄우려면 빈 파일(`: > secrets/vision_key.json`)을 둡니다. 스캔은 502 를 받고
  앱은 직접 입력으로 넘어갑니다(맥 리허설·로컬과 같은 동작).

## 맥 리허설

`.env` 에서 `K_DPP_DOMAIN=localhost` 로 두고 맨 아래 세 줄의 주석을 풉니다(이 맥 안에서만,
8080·8443). Vision 키는 빈 파일로 둡니다.

```sh
docker compose up -d --build --wait
curl -k https://localhost:8443/                         # Caddy 자체 인증서라 -k
curl -s -o /dev/null -w '%{redirect_url}\n' http://localhost:8080/   # https://localhost/… 로 넘김
docker compose down -v                                   # 끝나면 리허설 데이터까지 지움
```

http → https 이동 주소에 8443 이 빠지는 것은 컨테이너 안이 443 이기 때문이고, 서버(80·443)에서는 맞습니다.

## 주의

- **서버에서 `docker compose down -v` 금지** — 볼륨 `pgdata`(사용자 데이터)와 `caddy_data`(인증서)가
  지워집니다. 인증서를 짧은 시간에 여러 번 다시 받으면 Let's Encrypt 발급 한도에 걸립니다.
- **워커를 늘리지 않습니다** — 로그인 잠금(5회 실패 시 60초)이 프로세스 메모리에 있어 워커마다 갈립니다.
- 앱이 `DB 스키마가 최신이 아닙니다` 로 멈추면 `docker compose logs migrate` 를 보고
  `docker compose up -d --wait` 로 migrate 부터 다시 돌립니다.
- DB 비밀번호는 볼륨을 처음 만들 때만 적용됩니다. 바꾸려면
  `docker compose exec postgres psql -U kdpp -d k_dpp -c "ALTER USER kdpp PASSWORD '<새 값>'"` 뒤
  `.env` 를 고치고 `docker compose up -d --wait`.
- `docker inspect` 로 앱 환경변수(DB 주소·비밀번호 포함)를 볼 수 있습니다. 서버 접속 권한 = DB 접근 권한입니다.
- 로그는 `docker compose logs -f app caddy`. 서비스마다 10MB × 3개까지만 남습니다.
- 길이를 밝히지 않은(chunked) 11MiB 초과 요청은 Caddy 가 빈 본문의 413 으로 끊습니다.
  Content-Length 가 있는 요청은 앱이 먼저 JSON 413 으로 답합니다.
