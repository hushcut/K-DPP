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
| `backup` | 매일 04:00(KST) 백업 + 되살리기 검사, 26시간 넘게 매일 백업 성공이 없으면 unhealthy(배포 직전·수동 백업은 세지 않음) | 없음 |

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
# .env 를 채웁니다: K_DPP_DOMAIN, POSTGRES_PASSWORD(openssl rand -hex 24), K_DPP_SCAN_DAILY_MAX(기본 100), K_DPP_KAKAO_APP_ID(카카오 앱 ID — 비우면 카카오 로그인 꺼짐)
mkdir -p secrets
sudo install -o 10001 -g 10001 -m 400 /경로/key.json secrets/vision_key.json   # 'Vision 키' 참고
sudo install -o 10001 -g 10001 -m 400 /경로/smtp_password secrets/smtp_password   # '메일 발송' 참고(.env 의 K_DPP_EMAIL_FROM 도)
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
- `.env.example` 에 새 필수 값이 생겼으면(`git diff <옛 커밋> -- .env.example`) `.env` 에도 넣습니다.
  빠지면 `up` 뿐 아니라 `ps`·`logs` 도 `required variable … is missing a value` 로 멈춥니다.
- 보안 패치: `docker compose pull postgres caddy` 와 `docker compose build --pull` 뒤 `up -d --wait`.

### 되돌리기 (새 리비전이 들어간 업데이트)

옛 코드는 DB 리비전이 자기 머리와 다르면 시작하지 않고, 옛 이미지의 alembic 은 모르는 리비전에서 멈춥니다. 그래서 리비전이 든
업데이트(예: 옷장 백업 `a28c2a50b363`)는 **올리기 전에** 준비하고, 되돌릴 때는 아래 순서를 지킵니다. 미리 실행하지 않습니다.

0. 올리기 전: `git rev-parse HEAD` 로 옛 커밋을 적고, 손 백업(`docker compose run --rm --no-deps backup once manual`)의 OK 줄을 봅니다.
1. 새 표가 아직 비었을 때(예: `closet_snapshots` 0행): **새 코드가 체크아웃된 채로** 새 이미지의 migrate 로 내린 뒤 옛 커밋으로 갑니다.
   ```sh
   docker compose run --rm --no-deps migrate alembic downgrade <옛 머리 리비전>   # 옷장이면 19b7eee3b75c
   git checkout --detach <옛 커밋>
   docker compose up -d --build --wait
   ```
   표에 행이 있으면 downgrade 가 `RuntimeError` 로 멈추고 아무것도 바꾸지 않습니다(사용자 백업을 리비전이 지우지 않음).
2. 행이 생긴 뒤: 앞으로 고칩니다. 꼭 옛 코드여야 하면 '복구' 1)~3) 으로 업데이트 전 덤프(`backups/pre-migrate/`)를 되돌린 뒤
   옛 커밋을 체크아웃하고 4) — 그 사이 생긴 데이터는 잃습니다.
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
| ① 배포 직전 | `up` 할 때마다, migrate 바로 전 | `backups/pre-migrate/`(최근 10개, 14일 안) | 마이그레이션 실패 |
| ② 매일 | 04:00 KST(`K_DPP_BACKUP_AT`) | `backups/daily/`(최근 13개 — 14일 안) | 실수·버그로 망가진 데이터 |
| ③ 서버 통째 | Lightsail 자동 스냅샷(하루 한 번) | AWS(서버 밖) | 서버 고장·삭제 |
| ④ 서버 밖 사본 | (아직 없음 — 서버·계정이 생기면 정함) | 다른 회사의 저장소 | AWS 계정 문제로 ③ 까지 잃는 경우 |

- 백업 파일은 `pg_dump -Fc` 형식이고, 뜬 직후 **임시 DB 에 실제로 되살려** 확인합니다.
  행 수가 파일과 같은지, 표 목록·Alembic 리비전·소재 수가 운영과 같은지 봅니다.
  검사에 실패하면 파일은 남기고 오래된 파일도 지우지 않습니다.
- **보관 기간**(`K_DPP_BACKUP_KEEP_DAYS`, 기본 14일): 어떤 백업 파일도 14일을 넘겨 남지 않습니다. 매일 백업이 뜨고
  되살리기 검사까지 성공하면 **종류와 상관없이**(매일·배포 직전·수동, 중간에 끊겨 남은 `.tmp-` 파일까지) 지웁니다.
  정리가 하루 한 번이라 다음 정리 전에 14일을 넘길 파일(이름의 시각이 13일 넘은 것)을 미리 지우므로, 매일 백업은
  오늘 것까지 13개가 남습니다. 방금 뜬 파일은 지우지 않습니다.
  나이는 수정 시각이 아니라 이름의 시각으로 셉니다. 이름 형식이 다른 파일은 건드리지 않습니다.
  매일 백업이 실패하는 동안에는 지우지 않습니다(쓸 만한 파일까지 잃지 않게). 개수 정리(위 표)는 그대로 함께 합니다.
  값은 7~14 정수만 받습니다 — 잘못된 값이면 백업이 시작하지 않아 `up` 도 `pre-migrate-backup` 에서 멈춥니다
  (`logs pre-migrate-backup` 의 `FAIL K_DPP_BACKUP_KEEP_DAYS …`). 14를 넘길 수 없는 이유는 아래 '운영 점검'(DECISIONS 243·250·251).
- 매일 백업이 `FAIL` 로 끝나는 그 밖의 정리 경우: 파일을 지우지 못함 · 이름의 시각이 1시간 넘게 미래인 파일이 있음
  (시계를 확인하고 손으로 정리) · 복구 뒤 남은 DB(아래 '복구' — 7일 넘은 `k_dpp_old_*`, 남은 `k_dpp_restored`).
  지울 것은 지운 뒤 실패로 끝나므로, 성공 기록이 멈춰 26시간 뒤 unhealthy 로 보입니다.
- 상태 확인: `docker compose ps backup`(healthy 여부), `docker compose logs backup`(`OK`·`FAIL` 줄),
  `sudo cat backups/.last-daily-success`(매일 백업의 마지막 성공 — healthy 는 이것만 봄),
  `sudo cat backups/.last-success`(종류와 상관없이 마지막 성공).
  새 서버는 매일 백업이 처음 성공하기 전까지 첫 백업 뒤 26시간 동안 healthy 로 봐줍니다(첫 `up --wait` 가 통과하게).
- 손으로 한 번 뜨기: `docker compose run --rm --no-deps backup once manual`(`backups/manual/`, 최근 10개 — 14일 뒤 지워짐).
- 파일 하나만 검사: `docker compose run --rm --no-deps backup check /backups/daily/<파일>`.
- 백업에는 **이메일과 비밀번호 해시**가 들어 있습니다. 폴더 700·파일 600 이고 서버에서는 root 소유라
  `sudo` 로 봅니다. Git 에 올리지 않습니다(`.gitignore`).
- ③ 켜는 법(사용자): Lightsail 콘솔 → 인스턴스 → 스냅샷 → 자동 스냅샷 켜기 → 시각은 04:00 이 아닌 때
  (예: 05:00 KST). 스냅샷은 최근 7개가 남습니다.
- ④ 는 같은 AWS 계정의 S3 가 아니라 다른 회사의 저장소(Google Cloud Storage·Cloudflare R2 등)로 정할 예정입니다
  — 같은 계정이면 ③ 과 함께 잃습니다.

### 운영 점검

- **주 1회 `docker compose ps backup`** 이 healthy 인지 봅니다(실패 알림이 아직 없음). unhealthy 면 `docker compose logs backup` 의 `FAIL` 줄부터.
  고친 뒤에는 다음 04:00 을 기다리지 말고 바로 `docker compose run --rm --no-deps backup once daily` 로 백업·정리까지 합니다.
- 사고를 조사하는 동안 오래된 백업을 지켜야 하면 정리 대상이 아닌 폴더로 복사합니다:
  `sudo mkdir -p -m 700 backups/hold && sudo cp -p backups/<종류>/<파일> backups/hold/`. 조사가 끝나면 바로 지웁니다
  (남아 있는 동안은 아래 '최대 30일' 약속 밖입니다).
- 탈퇴한 사용자의 데이터는 운영 DB 에서는 바로 지워지고, 백업에서는 **백업이 정상일 때 최대 30일 안에** 사라집니다(DECISIONS 243):
  백업 파일 최대 14일 + 매일 백업이 멈춘 걸 알아채는 데 최대 8일(unhealthy 까지 26시간 + 주 1회 점검) + Lightsail 스냅샷 7개 ≈ 29일.
  그래서 보관 기간은 14일을 넘길 수 없고, 복구 뒤 남는 옛 DB 도 7일 안에 지웁니다(아래 '복구').

### 백업이 실패해 앱이 안 뜰 때

`up` 이 `service "pre-migrate-backup" didn't complete successfully` 로 끝나면 migrate·app 이 멈춘
상태입니다(이때 함께 나오는 `dependency postgres failed to start` 는 Compose 의 표현일 뿐입니다).
`docker compose logs pre-migrate-backup` 의 `FAIL` 줄로 원인(디스크 가득·비밀번호·`K_DPP_BACKUP_KEEP_DAYS` 값 등)을 먼저 고칩니다.
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
- **7일 안에** 옛 DB 를 지웁니다: `docker compose exec -T postgres dropdb -U kdpp k_dpp_old_<시각>`.
  옛 DB 에는 그 뒤 탈퇴한 사용자의 데이터가 남아 있어, 오래 두면 '최대 30일' 약속(위 '운영 점검')이 깨집니다.
  7일이 넘으면 매일 백업이 정리를 마친 뒤 `FAIL 복구 뒤 남은 DB 를 지우세요` 로 끝납니다(unhealthy).
- 2) 만 하고 바꿔 끼우지 않기로 했으면 `k_dpp_restored` 를 바로 지웁니다(남아 있으면 다음 매일 백업이 같은 `FAIL`).
- 2) 가 `k_dpp_restored 가 이미 있습니다` 로 멈추면 지난 복구에서 남은 것입니다. 내용을 확인한 뒤 같은 `dropdb` 로 지웁니다.

### 복구 연습

- 매일 백업이 임시 DB 로 되살리기까지 하므로, '파일이 되살아나는가'는 매일 확인됩니다.
- **위 '복구' 전체를 한 번 실제로** 해 봅니다: 서버를 연 직후(11-01 이후) 한 번, 그다음은 한 달에 한 번이나
  배포 방식이 바뀔 때. 맥 리허설에서 같은 순서를 확인했습니다(백업 → 백업 뒤 가입·이력 삭제 → stage →
  바꿔 끼우기 → 백업 시점 상태로 돌아옴·옛 DB 남음, 옛 리비전 백업은 migrate 가 head 로 올림).

## 옷장 백업 확인

옷 내용(`items`)은 열지 않고 상태만 봅니다(DECISIONS 242).

```sh
docker compose exec -T postgres psql -U kdpp -d k_dpp -c "SELECT user_id, version, item_count, octet_length(items) AS bytes, updated_at FROM closet_snapshots ORDER BY updated_at DESC LIMIT 20"
```

- 새 환경변수·Caddy 변경은 없고, 매일 백업에 이 표도 함께 들어갑니다. 탈퇴하면 운영 DB 에서는 바로 지워지고, 백업 파일에는
  보관 기간(14일) 동안 남습니다 — 백업이 정상이면 최대 30일 안에 사라집니다('백업' → '운영 점검').
- 서버 로그는 충돌·거절만 `[closet]` 한 줄로 남깁니다(`docker compose logs app | grep '\[closet\]'`).

## 메일 발송

가입·비밀번호 찾기 인증번호 메일은 Resend 를 SMTP 로 씁니다(무료 하루 100통·월 3,000통, DECISIONS 171).
다른 SMTP 서버로 바꿀 때는 `.env` 의 `K_DPP_SMTP_*` 와 비밀번호 파일만 바꿉니다.

- 도메인: Resend 에 하위 도메인(예 `mail.<도메인>` — Resend 가 그 앞에 `send.` 를 붙여 반송 주소로 씀)을 추가하고 Resend 가 보여 주는 SPF·DKIM 레코드를 DNS 에
  넣어 Verified 를 확인합니다. DMARC(`_dmarc` TXT `v=DMARC1; p=none;`)는 그 48시간 뒤, 첫 시험 발송은 도메인을
  등록하고 24시간 뒤에 합니다(네이버·다음은 SPF 가 맞지 않으면 반송).
- `.env`: `K_DPP_EMAIL_DELIVERY=smtp`, `K_DPP_EMAIL_FROM`(예 `K-DPP <no-reply@mail.<도메인>>`),
  `K_DPP_EMAIL_DAILY_MAX=100`(Resend 하루 한도와 같은 UTC 날짜 — 넘는 요청은 앱이 503 으로 먼저 막음).
  SMTP 값(`smtp.resend.com`·587·`resend`)은 `.env.example` 그대로 둡니다. 하나라도 비었거나 틀리면 앱이
  시작하지 않고 `docker compose logs app` 에 그 이름이 나옵니다.
- 비밀번호 = Resend API 키(권한은 'Sending access', 도메인을 위 하위 도메인으로 제한). `secrets/smtp_password`
  에 한 줄로, Vision 키처럼 `sudo install -o 10001 -g 10001 -m 400 …` 로 넣습니다. 환경변수로 두지 않는 것은
  `docker inspect` 에 보이기 때문입니다.
- 587 은 STARTTLS 이고, 서버가 STARTTLS 를 내놓지 않으면 로그인하지 않고 실패합니다(비밀번호를 평문으로
  보내지 않음). 587 이 막혔으면 `K_DPP_SMTP_PORT=2587`(STARTTLS) 또는 465·2465(처음부터 TLS).
- 메일은 응답 뒤에 보내므로 앱 응답은 발송 결과와 상관없이 같습니다. `docker compose logs app` 에 보낸 것은
  `[email] 메일을 보냈습니다(signup)`, 실패는 `[email] 인증 메일 처리 실패(…)` 로 남고 주소·번호·비밀번호는
  남기지 않습니다(받는 서버가 되돌려 준 주소도 `<주소>` 로 가림 — DECISIONS 253). 받는 사람별 기록은 Resend
  화면의 Emails 에서 봅니다.
- **시연 날 발송이 막히면** `.env` 를 `K_DPP_EMAIL_DELIVERY=log` 로 바꾸고 `docker compose up -d --wait` —
  번호가 `docker compose logs app` 에 `[email] #3f9a1c2b | <제목> | 인증번호 123456` 으로 남습니다. 주소 대신
  app 이 켜질 때마다 바뀌는 지문이라, 시연 계정의 줄은 번호를 요청한 시각으로 찾습니다.
- log 로 띄울 때도 secret 파일은 있어야 하므로 빈 파일(`: > secrets/smtp_password`)을 둡니다.
- **띄운 직후 한 번 확인합니다**: 앱(또는 `curl`)으로 진짜 메일함에 가입 인증번호를 요청하고 메일이 왔는지,
  `docker compose logs app` 에 `메일을 보냈습니다` 가 남았는지 봅니다. 형식만 맞고 값이 틀린 설정(API 키·호스트 오타,
  인증 안 된 발신 도메인)은 앱이 정상으로 뜨고 메일만 실패하므로 이 확인으로만 드러납니다.
- 서버에서 시험 메일은 진짜 메일함이나 `delivered@resend.dev` 로만 보냅니다. 지어낸 주소는 반송되어
  Resend 반송률에 들어가고, 반송률이 높으면 계정이 멈춥니다.

## Vision 키

- 앱은 `/run/secrets/vision_key` 를 `GOOGLE_APPLICATION_CREDENTIALS` 로 씁니다(저장소의
  `AI/…/key.json` 경로는 이미지에 들어가지 않습니다).
- 파일은 서버에서 그대로 연결되므로 **소유자·권한도 서버 파일 그대로**입니다. 앱은 uid
  10001 로 돌기 때문에 위의 `install -o 10001 -g 10001 -m 400` 처럼 넣어야 읽을 수 있습니다.
  못 읽으면 스캔이 502 가 되고 `docker compose logs app` 에 `[scan] OCR 실패` 가 남습니다.
- 키 없이 띄우려면 빈 파일(`: > secrets/vision_key.json`)을 둡니다. 스캔은 502 를 받고(한 계정
  하루 21번째부터는 아래 하루 상한의 429) 앱은 직접 입력으로 넘어갑니다(맥 리허설·로컬과 같은 동작).
- **하루 상한**: Vision 을 부르는 스캔은 한 계정 하루 20번(넘으면 429), 서버 전체 하루
  `K_DPP_SCAN_DAILY_MAX` 번(넘으면 503)이고 한국 자정에 풀립니다. 앱은 둘 다 직접 입력으로
  넘어갑니다. 서버 전체 상한에 닿으면 `docker compose logs app` 에 `[scan] <날짜 시각> KST … 서버 전체
  하루 상한` 이 그날 한 번 남습니다 — 평소보다 이른 시각이면 남용을 의심합니다(한 사람이 계정 여럿으로
  다 쓰면 그날 자정까지 모든 사용자가 503). 기록은 메모리라 app 을 다시 띄우면(`docker compose restart app`)
  그날 수가 0 부터 다시 셉니다. 시연 날 늘리려면 `.env` 값을 고치고 `docker compose up -d --wait`.

## 맥 리허설

`.env` 에서 `K_DPP_DOMAIN=localhost` 로 두고 맨 아래 세 줄의 주석을 풉니다(이 맥 안에서만,
8080·8443). Vision 키·SMTP 비밀번호는 빈 파일로 두고 `K_DPP_EMAIL_DELIVERY=log`(번호는
`docker compose logs app`)로 띄웁니다.

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
  DB 연결도 워커마다 최대 40개(요청 스레드 수, `BACKEND/database.py`)라 워커 수만큼 곱해집니다(PostgreSQL 기본 상한 100).
- 앱이 `DB 스키마가 최신이 아닙니다` 로 멈추면 `docker compose logs migrate` 를 보고
  `docker compose up -d --wait` 로 migrate 부터 다시 돌립니다.
- DB 비밀번호는 볼륨을 처음 만들 때만 적용됩니다. 바꾸려면
  `docker compose exec postgres psql -U kdpp -d k_dpp -c "ALTER USER kdpp PASSWORD '<새 값>'"` 뒤
  `.env` 를 고치고 `docker compose up -d --wait`(앱·migrate·백업이 새 값으로 다시 만들어짐).
- `docker inspect` 로 앱·백업 환경변수(DB 주소·비밀번호 포함)를 볼 수 있습니다. 서버 접속 권한 = DB 접근 권한입니다.
- 로그는 `docker compose logs -f app caddy backup`. 서비스마다 10MB × 3개까지만 남습니다.
- 길이를 밝히지 않은(chunked) 11MiB 초과 요청은 Caddy 가 빈 본문의 413 으로 끊습니다.
  Content-Length 가 있는 요청은 앱이 먼저 JSON 413 으로 답합니다. 사진 업로드(multipart)가 아닌 요청은
  앱이 1MiB 에서 JSON 413 으로 끊습니다(chunked 포함 — Caddy 상한은 사진 업로드 기준이라 그대로).
