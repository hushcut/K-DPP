#!/usr/bin/env bash
# K-DPP 배포 DB 백업. deploy/compose.yaml 의 backup·pre-migrate-backup 서비스가 씁니다.
# postgres 와 같은 이미지 안에서 돌아 pg_dump·pg_restore 버전이 DB 서버와 같습니다.
#
#   kdpp-backup once <daily|pre-migrate|manual>  백업 하나 → 임시 DB 에 되살려 검사 → 보관 개수 정리
#   kdpp-backup loop                             매일 K_DPP_BACKUP_AT(기본 04:00, TZ 기준)에 once daily
#   kdpp-backup check <파일>                     파일 하나를 임시 DB 에 되살려 검사만
#   kdpp-backup stage <파일>                     복구용: 새 DB k_dpp_restored 에 되살림(deploy/README.md '복구')
#   kdpp-backup health                           마지막 성공이 K_DPP_BACKUP_MAX_AGE_MIN 분 안인지
#
# 접속은 PGHOST·PGUSER·PGPASSWORD·PGDATABASE 환경변수로 받습니다(compose 가 넣음).
# 운영 DB 는 읽기만 합니다. 지우는 DB 는 검사용 임시 DB(k_dpp_restore_check)와, stage 가
# 방금 만들다 실패한 k_dpp_restored 뿐입니다.
set -euo pipefail
umask 077
# 매일 실행은 이 파일을 새로 읽어 돕니다(git pull 로 바뀐 스크립트를 컨테이너 재시작 없이 씀).
SELF=$(readlink -f "$0")
# dropdb --if-exists 의 NOTICE 같은 안내는 빼고 경고 이상만 남깁니다.
export PGOPTIONS="-c client_min_messages=warning"

BACKUP_DIR=${K_DPP_BACKUP_DIR:-/backups}
LIVE_DB=${PGDATABASE:?PGDATABASE 환경변수가 필요합니다}
CHECK_DB=k_dpp_restore_check
STAGE_DB=k_dpp_restored
LAST_SUCCESS="$BACKUP_DIR/.last-success"
declare -A KEEP=(
  [daily]=${K_DPP_BACKUP_KEEP_DAILY:-14}
  [pre-migrate]=${K_DPP_BACKUP_KEEP_PRE_MIGRATE:-10}
  [manual]=${K_DPP_BACKUP_KEEP_MANUAL:-10}
)
SUMMARY=""

log() { printf '%s %s\n' "$(date '+%F %T %Z')" "$*"; }
die() { log "FAIL $*"; exit 1; }
q() { psql -X -q -v ON_ERROR_STOP=1 -At "$@"; }

lock() {
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  exec 9>"$BACKUP_DIR/.lock"
  flock -w 600 9 || die "다른 백업이 10분 안에 끝나지 않았습니다"
}

# DB 의 public 표마다 "표이름 행수"(이름순). 표가 없으면 빈 출력.
db_counts() {
  local db=$1 t
  for t in $(q -d "$db" -c "select tablename from pg_tables where schemaname = 'public' order by 1"); do
    printf '%s %s\n' "$t" "$(q -d "$db" -c "select count(*) from public.\"$t\"")"
  done
}

# 백업 파일 안에 든 표마다 "표이름 행수"(이름순). COPY 블록의 줄 수를 셉니다.
dump_counts() {
  pg_restore --data-only -f - "$1" | awk '
    /^COPY public\./ { split($2, name, "."); table = name[2]; rows = 0; inside = 1; next }
    inside && $0 == "\\." { print table, rows; inside = 0; next }
    inside { rows++ }' | sort
}

revision() { q -d "$1" -c "select version_num from alembic_version" 2>/dev/null || true; }

# $1 = 되살린 DB, $2 = 파일, $3 = strict(방금 뜬 백업 — 운영과 표·리비전·소재가 같아야 함)/loose.
# 성공하면 SUMMARY 를 채웁니다. set -e 가 꺼진 자리(|| 뒤)에서 불리므로 단계마다 직접 확인합니다.
compare() {
  local db=$1 file=$2 mode=$3 restored expected live
  restored=$(db_counts "$db") || { log "되살린 DB 를 읽지 못했습니다"; return 1; }
  expected=$(dump_counts "$file") || { log "백업 파일 안의 행 수를 세지 못했습니다"; return 1; }
  if [[ $restored != "$expected" ]]; then
    log "행 수가 백업 파일과 다릅니다 — 파일: $(tr '\n' ' ' <<<"$expected")/ 되살린 DB: $(tr '\n' ' ' <<<"$restored")"
    return 1
  fi
  if [[ $mode == strict ]]; then
    live=$(db_counts "$LIVE_DB") || { log "운영 DB 를 읽지 못했습니다"; return 1; }
    if [[ $(cut -d' ' -f1 <<<"$restored") != "$(cut -d' ' -f1 <<<"$live")" ]]; then
      log "표 목록이 운영과 다릅니다 — 운영: $(cut -d' ' -f1 <<<"$live" | tr '\n' ' ')/ 되살린 DB: $(cut -d' ' -f1 <<<"$restored" | tr '\n' ' ')"
      return 1
    fi
    if [[ $(revision "$db") != "$(revision "$LIVE_DB")" ]]; then
      log "Alembic 리비전이 운영과 다릅니다 — 운영: $(revision "$LIVE_DB") / 되살린 DB: $(revision "$db")"
      return 1
    fi
    # 소재는 마이그레이션으로만 바뀌므로 운영과 같아야 합니다. 사용자 표는 로그아웃·탈퇴로
    # 그사이 줄 수 있어 운영과 비교하지 않고 기록만 합니다.
    if [[ $(grep '^materials ' <<<"$restored" || true) != "$(grep '^materials ' <<<"$live" || true)" ]]; then
      log "소재 행 수가 운영과 다릅니다"
      return 1
    fi
  fi
  SUMMARY="rev=$(revision "$db") $(tr '\n' ' ' <<<"$restored")"
  return 0
}

# 파일을 임시 DB 에 되살려 compare. 임시 DB 는 끝나면 지웁니다.
verify() {
  local file=$1 mode=$2 rc=0
  dropdb --if-exists "$CHECK_DB" && createdb "$CHECK_DB" || { log "임시 DB 를 만들지 못했습니다"; return 1; }
  if pg_restore --exit-on-error --no-owner --no-privileges -d "$CHECK_DB" "$file"; then
    compare "$CHECK_DB" "$file" "$mode" || rc=1
  else
    log "pg_restore 가 실패했습니다: $file"
    rc=1
  fi
  dropdb --if-exists "$CHECK_DB" || log "임시 DB $CHECK_DB 를 지우지 못했습니다(다음 검사가 다시 지움)"
  return $rc
}

# 종류마다 최신 KEEP 개만 남깁니다. 파일 이름에 시각이 들어 있어 이름순 = 시간순입니다.
rotate() {
  local kind=$1 keep=${KEEP[$1]} files n f
  mapfile -t files < <(find "$BACKUP_DIR/$kind" -maxdepth 1 -type f -name 'k_dpp-*.dump' | sort)
  n=${#files[@]}
  (( n > keep )) || return 0
  for f in "${files[@]:0:n-keep}"; do
    rm -f -- "$f"
    log "보관 개수 초과로 지움: $kind/${f##*/}"
  done
}

once() {
  local kind=${1:-} name dir file tmp
  [[ -n $kind && -n ${KEEP[$kind]+x} ]] || die "once 다음에 daily·pre-migrate·manual 중 하나를 줍니다"
  lock
  dir="$BACKUP_DIR/$kind"
  mkdir -p "$dir"
  name="k_dpp-$kind-$(date +%Y%m%d-%H%M%S).dump"
  file="$dir/$name"
  tmp="$dir/.tmp-$name"
  if ! pg_dump -Fc -d "$LIVE_DB" -f "$tmp"; then
    rm -f -- "$tmp"
    die "pg_dump 실패($kind)"
  fi
  mv -- "$tmp" "$file"
  verify "$file" strict || die "되살리기 검사 실패: $kind/$name(파일은 남겨 둠, 보관 정리 안 함)"
  rotate "$kind"
  printf '%s %s\n' "$(date '+%F %T %Z')" "$kind/$name" >"$LAST_SUCCESS"
  log "OK $kind/$name $(du -h -- "$file" | cut -f1) $SUMMARY"
}

check() {
  local file=${1:-}
  [[ -f $file ]] || die "check 다음에 백업 파일 경로를 줍니다(예: /backups/daily/k_dpp-daily-….dump)"
  lock
  verify "$file" loose || die "되살리기 검사 실패: $file"
  log "OK check $file $SUMMARY"
}

stage() {
  local file=${1:-}
  [[ -f $file ]] || die "stage 다음에 백업 파일 경로를 줍니다(예: /backups/daily/k_dpp-daily-….dump)"
  lock
  if [[ -n $(q -d postgres -c "select 1 from pg_database where datname = '$STAGE_DB'") ]]; then
    die "$STAGE_DB 가 이미 있습니다. 지난 복구에서 남은 것이면 확인한 뒤 직접 지우세요(README '복구')"
  fi
  createdb "$STAGE_DB" || die "$STAGE_DB 를 만들지 못했습니다"
  if ! pg_restore --exit-on-error --no-owner --no-privileges -d "$STAGE_DB" "$file" \
    || ! compare "$STAGE_DB" "$file" loose; then
    dropdb --if-exists "$STAGE_DB" || true
    die "되살리기 실패 — 방금 만든 $STAGE_DB 는 지웠습니다. 운영 DB 는 그대로입니다"
  fi
  log "OK stage $file → $STAGE_DB $SUMMARY"
  log "운영 DB($LIVE_DB)는 그대로입니다. 바꿔 끼우는 순서는 deploy/README.md '복구'."
}

health() {
  local max=${K_DPP_BACKUP_MAX_AGE_MIN:-1560}
  [[ -n $(find "$LAST_SUCCESS" -mmin "-$max" 2>/dev/null) ]] || {
    echo "마지막 성공 백업이 ${max}분보다 오래됐거나 없습니다: $(cat "$LAST_SUCCESS" 2>/dev/null || echo 없음)"
    exit 1
  }
}

loop() {
  local at=${K_DPP_BACKUP_AT:-04:00} now next
  trap 'log "멈춤"; exit 0' TERM INT
  log "매일 백업 대기 — 매일 $at($(date +%Z)), 보관 매일 ${KEEP[daily]}·배포 직전 ${KEEP[pre-migrate]}·수동 ${KEEP[manual]}"
  while true; do
    now=$(date +%s)
    next=$(date -d "today $at" +%s)
    (( next > now )) || next=$(date -d "tomorrow $at" +%s)
    log "다음 매일 백업: $(date -d "@$next" '+%F %T %Z')"
    sleep $((next - now)) &
    wait $!
    bash "$SELF" once daily || log "매일 백업 실패 — 다음 예약은 그대로 둡니다"
  done
}

cmd=${1:-}
shift || true
case $cmd in
  once | check | stage | health | loop) "$cmd" "$@" ;;
  *) die "사용법: kdpp-backup once <daily|pre-migrate|manual> | loop | check <파일> | stage <파일> | health" ;;
esac
