# K-DPP 배포 (Docker Compose)

서버 한 대에 **앱 + PostgreSQL + Caddy(자동 HTTPS) + 백업** 을 한 Compose 로 띄웁니다.
로컬 개발은 이 폴더가 아니라 `BACKEND/README.md`(DB 만 Compose, 앱은 venv)를 따릅니다.

```text
인터넷 ─ 80/443 ─▶ caddy ──▶ app:8000 ──▶ postgres:5432 (볼륨 pgdata)
                   (HTTPS)   (FastAPI)       ▲      ▲
   up 할 때마다: pre-migrate-backup ─▶ migrate      │
   매일 04:00:   backup ───────────────────────────┘ → 서버의 deploy/backups/
```

| 서비스 | 하는 일 | 밖으로 여는 포트 |
| --- | --- | --- |
| `postgres` | DB(`postgres:18-trixie`), 데이터는 볼륨 `pgdata` | 없음 |
| `pre-migrate-backup` | `up` 할 때 migrate 보다 먼저 백업 + 되살리기 검사 후 종료 — 실패하면 migrate·app 이 시작하지 않음 | 없음 |
| `migrate` | 표·소재를 최신 리비전으로 맞추고 종료 — 실패하면 `app` 이 시작하지 않음 | 없음 |
| `app` | 백엔드(`BACKEND/Dockerfile` 로 빌드), 워커 1개 | 없음 |
| `caddy` | HTTPS 인증서 자동 발급·갱신, http → https, 요청 본문 11MiB 상한 | 80, 443 |
| `backup` | 매일 04:00(KST) 백업 + 되살리기 검사, 26시간 넘게 성공이 없으면 unhealthy | 없음 |

## 서버 준비

- Docker Engine 25 이상(헬스체크 `start_interval`)과 Compose 플러그인(`docker compose version` 이 나와야 함).
- 방화벽: 22(SSH)·80·443(TCP)·443(UDP, HTTP/3) 만 엽니다. 5432·8000 은 열지 않습니다.
- 도메인의 DNS A 레코드가 서버 공인 IP 를 가리켜야 Caddy 가 인증서를 받습니다.
- 이미지는 **서버에서 빌드**합니다(맥 arm64 ↔ 서버 x86_64, 레지스트리 없음).
- Lightsail 이면 인스턴스의 **자동 스냅샷**을 켭니다(아래 '백업' ③).

## 처음 배포

저장소를 받은 서버에서, 이 폴더(`deploy/`) 기준으로:

```sh
cp .env.example .env && chmod 600 .env
# .env 를 채웁니다: K_DPP_DOMAIN, POSTGRES_PASSWORD(openssl rand -hex 24)
mkdir -p secrets
sudo install -o 10001 -g 10001 -m 400 /경로/key.json secrets/vision_key.json   # 'Vision 키' 참고
docker compose up -d --build --wait
docker compose ps -a      # pre-migrate-backup·migrate: Exited (0), 나머지: healthy / Up
curl https://<도메인>/    # {"status":"success",...}
```

`--wait` 는 모든 서비스가 healthy 가 되거나 실패할 때까지 기다립니다. 실패하면
`docker compose logs pre-migrate-backup migrate app` 부터 봅니다.

## 업데이트 (새 코드 배포)

```sh
git pull
docker compose up -d --build --wait   # 배포 직전 백업 → migrate(새 리비전) → app 교체 → caddy
```

- 백업은 `pre-migrate-backup` 이 migrate 바로 전에 자동으로 뜹니다(`backups/pre-migrate/`).
  잘못된 리비전이 적용됐으면 그 파일로 '복구' 합니다.
- 앱 컨테이너가 바뀌는 몇 초 동안 요청이 실패할 수 있습니다.
- 보안 패치: `docker compose pull postgres caddy` 와 `docker compose build --pull` 뒤 `up -d --wait`.
- 받기 전에 그 커밋의 GitHub Actions `Backend image (docker build)` 잡이 초록인지 봅니다 — 서버와 같은
  x86_64 에서 이 이미지를 빌드하고 migrate·앱 시작까지 해 본 결과입니다.

## 의존성 버전

`BACKEND/requirements.txt` 는 간접 의존성까지 모두 `==` 로 고정합니다. 서버에서 언제 빌드해도 같은 판이
들어갑니다(바뀌는 것은 `build --pull` 로 받는 기본 이미지의 패치뿐입니다).

올리는 법: 올릴 줄을 새 버전으로 고치고 파일 끝 간접 의존성 묶음을 지운 뒤, 깨끗한 Python 3.12 에 깔아
나온 `pip freeze` 로 끝 묶음을 다시 적습니다(저장소 루트에서).

```sh
docker run --rm -v "$PWD/BACKEND/requirements.txt:/r.txt:ro" python:3.12-slim-trixie \
  sh -c 'pip install -q --root-user-action=ignore -r /r.txt && pip freeze'
```

- `psycopg-binary` 는 `psycopg[binary]` 가 같은 버전으로 끌어오므로 적지 않습니다.
- 파일에는 **ASCII 만** 씁니다. 한국어 Windows 의 옛 pip 는 이 파일을 cp949 로 읽어 한글 주석에서 설치가 멈춥니다.
- 고친 뒤 CI 세 잡이 초록인지 봅니다. 빌드 중 `check_ai_wiring.py` 가 AI 모듈·Pillow·google-cloud-vision 을
  불러 보므로, Vision 이 깨진 이미지는 만들어지지 않습니다(앱은 Vision 실패를 키 없음과 같은 502 로 삼킵니다).

## 백업

| 겹 | 언제 | 어디에 | 막는 사고 |
| --- | --- | --- | --- |
| ① 배포 직전 | `up` 할 때마다, migrate 바로 전 | `backups/pre-migrate/`(최근 10개) | 마이그레이션 실패 |
| ② 매일 | 04:00 KST(`K_DPP_BACKUP_AT`) | `backups/daily/`(최근 14개) | 실수·버그로 망가진 데이터 |
| ③ 서버 통째 | Lightsail 자동 스냅샷(하루 한 번) | AWS(서버 밖) | 서버 고장·삭제 |
| ④ 서버 밖 사본 | (아직 없음 — 서버·계정이 생기면 정함) | 다른 회사의 저장소 | AWS 계정 문제로 ③ 까지 잃는 경우 |

- 백업 파일은 `pg_dump -Fc` 형식이고, 뜬 직후 **임시 DB 에 실제로 되살려** 확인합니다.
  행 수가 파일과 같은지, 표 목록·Alembic 리비전·소재 수가 운영과 같은지 봅니다.
  검사에 실패하면 파일은 남기고 오래된 파일도 지우지 않습니다.
- 상태 확인: `docker compose ps backup`(healthy 여부), `docker compose logs backup`(`OK`·`FAIL` 줄),
  `sudo cat backups/.last-success`(마지막 성공 시각).
- 손으로 한 번 뜨기: `docker compose run --rm --no-deps backup once manual`(`backups/manual/`, 최근 10개).
- 파일 하나만 검사: `docker compose run --rm --no-deps backup check /backups/daily/<파일>`.
- 백업에는 **이메일과 비밀번호 해시**가 들어 있습니다. 폴더 700·파일 600 이고 서버에서는 root 소유라
  `sudo` 로 봅니다. Git 에 올리지 않습니다(`.gitignore`).
- ③ 켜는 법(사용자): Lightsail 콘솔 → 인스턴스 → 스냅샷 → 자동 스냅샷 켜기 → 시각은 04:00 이 아닌 때
  (예: 05:00 KST). 스냅샷은 최근 7개가 남습니다.
- ④ 는 같은 AWS 계정의 S3 가 아니라 다른 회사의 저장소(Google Cloud Storage·Cloudflare R2 등)로 정할 예정입니다
  — 같은 계정이면 ③ 과 함께 잃습니다.

### 백업이 실패해 앱이 안 뜰 때

`up` 이 `service "pre-migrate-backup" didn't complete successfully` 로 끝나면 migrate·app 이 멈춘
상태입니다(이때 함께 나오는 `dependency postgres failed to start` 는 Compose 의 표현일 뿐입니다).
`docker compose logs pre-migrate-backup` 의 `FAIL` 줄로 원인(디스크 가득·비밀번호 등)을 먼저 고칩니다.
급하면 마이그레이션 없이 앱만 띄웁니다. DB 리비전이 코드와 맞을 때만 뜹니다.

```sh
docker compose up -d --no-deps app caddy
```

## 복구

운영 DB 를 지우지 않고 **새 DB 에 되살려 확인한 뒤 이름만 바꿔 끼웁니다.** 옛 DB 는 남으므로 되돌릴 수 있습니다.

```sh
# 1) 고를 파일을 봅니다(시각이 이름에 있음)
sudo ls -l backups/daily backups/pre-migrate backups/manual
# 2) 새 DB k_dpp_restored 에 되살리고 검사합니다. 운영 DB 는 그대로입니다.
docker compose run --rm --no-deps backup stage /backups/daily/<파일>
# 3) 앱을 멈추고 이름을 바꿔 끼웁니다(옛 DB 는 k_dpp_old_<시각>)
TS=$(date +%Y%m%d_%H%M%S)
docker compose stop app
docker compose exec -T postgres psql -U kdpp -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('k_dpp', 'k_dpp_restored') AND pid <> pg_backend_pid()" \
  -c "ALTER DATABASE k_dpp RENAME TO k_dpp_old_$TS" \
  -c "ALTER DATABASE k_dpp_restored RENAME TO k_dpp"
# 4) 다시 띄웁니다. 백업이 옛 리비전이면 migrate 가 최신으로 올립니다.
docker compose up -d --wait
```

- 5) 로그인·이력을 확인합니다. 백업 시각 이후에 생긴 가입·기록은 없는 것이 정상입니다.
- 잘못 골랐으면 같은 3)·4) 를 거꾸로 합니다(`k_dpp` → 다른 이름, `k_dpp_old_<시각>` → `k_dpp`).
- 며칠 지켜본 뒤 옛 DB 를 지웁니다: `docker compose exec -T postgres dropdb -U kdpp k_dpp_old_<시각>`.
- 2) 가 `k_dpp_restored 가 이미 있습니다` 로 멈추면 지난 복구에서 남은 것입니다. 내용을 확인한 뒤 같은 `dropdb` 로 지웁니다.

### 복구 연습

- 매일 백업이 임시 DB 로 되살리기까지 하므로, '파일이 되살아나는가'는 매일 확인됩니다.
- **위 '복구' 전체를 한 번 실제로** 해 봅니다: 서버를 연 직후(11-01 이후) 한 번, 그다음은 한 달에 한 번이나
  배포 방식이 바뀔 때. 맥 리허설에서 같은 순서를 확인했습니다(백업 → 백업 뒤 가입·이력 삭제 → stage →
  바꿔 끼우기 → 백업 시점 상태로 돌아옴·옛 DB 남음, 옛 리비전 백업은 migrate 가 head 로 올림).

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
docker compose down -v && rm -rf backups                 # 끝나면 리허설 데이터·백업까지 지움
```

http → https 이동 주소에 8443 이 빠지는 것은 컨테이너 안이 443 이기 때문이고, 서버(80·443)에서는 맞습니다.

## 주의

- **서버에서 `docker compose down -v` 금지** — 볼륨 `pgdata`(사용자 데이터)와 `caddy_data`(인증서)가
  지워집니다(`backups/` 폴더는 서버 디스크라 남습니다). 인증서를 짧은 시간에 여러 번 다시 받으면
  Let's Encrypt 발급 한도에 걸립니다.
- **워커를 늘리지 않습니다** — 로그인 잠금(5회 실패 시 60초)이 프로세스 메모리에 있어 워커마다 갈립니다.
- 앱이 `DB 스키마가 최신이 아닙니다` 로 멈추면 `docker compose logs migrate` 를 보고
  `docker compose up -d --wait` 로 migrate 부터 다시 돌립니다.
- DB 비밀번호는 볼륨을 처음 만들 때만 적용됩니다. 바꾸려면
  `docker compose exec postgres psql -U kdpp -d k_dpp -c "ALTER USER kdpp PASSWORD '<새 값>'"` 뒤
  `.env` 를 고치고 `docker compose up -d --wait`(앱·migrate·백업이 새 값으로 다시 만들어짐).
- `docker inspect` 로 앱·백업 환경변수(DB 주소·비밀번호 포함)를 볼 수 있습니다. 서버 접속 권한 = DB 접근 권한입니다.
- 로그는 `docker compose logs -f app caddy backup`. 서비스마다 10MB × 3개까지만 남습니다.
- 길이를 밝히지 않은(chunked) 11MiB 초과 요청은 Caddy 가 빈 본문의 413 으로 끊습니다.
  Content-Length 가 있는 요청은 앱이 먼저 JSON 413 으로 답합니다.
