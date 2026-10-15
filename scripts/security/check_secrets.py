"""Scan Git's actual index/objects with pinned Gitleaks; never print raw findings."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
VERSION = json.loads((HERE / 'gitleaks-release.json').read_text(encoding='utf-8'))['version']
OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
MAX_BYTES = 200 * 1024 * 1024
MAX_OBJECTS = 10000
EMPTY_BLOBS = {digest(f'blob {len(body)}\0'.encode('ascii') + body).hexdigest()
               for body in (b'', b'\n', b'\r\n') for digest in (hashlib.sha1, hashlib.sha256)}


class CheckError(Exception):
    pass


def git(root, *args, input=None):
    result = subprocess.run(['git', *args], cwd=root, input=input, capture_output=True, check=False)
    if result.returncode:
        raise CheckError('Git 검사 범위를 읽지 못했습니다. 충돌·얕은 이력·저장소 상태를 확인해 주세요.')
    return result.stdout


def forbidden_path(name):
    path = PurePosixPath(name)
    lower = name.lower()
    base = path.name.lower()
    if path.is_absolute() or '..' in path.parts or any(ord(char) < 32 for char in name):
        return True
    if any(part.lower() in {'.git', '.aws', '.gcloud', '.secrets', 'secrets', '.venv', 'venv', '__pycache__'} for part in path.parts):
        return True
    if lower.startswith(('.test-artifacts/', 'qa_dataset/', '.claude/worktrees/')):
        return True
    if re.match(r'^ai/[^/]+/(?:data|models|outputs)/', lower):
        return True
    environment_name = base == '.env' or base.startswith('.env.') or base.endswith('.env') or '.env.' in base
    example_name = base in {'.env.example', '.env.template'} or re.fullmatch(r'[^.]+(?:\.[^.]+)*\.env\.(?:example|template)', base)
    if environment_name and not example_name:
        return True
    if re.search(r'\.(?:key|pem|p12|pfx|jks|keystore|db|sqlite|sqlite3)(?:[.-].*)?$', base):
        return True
    if base in {'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519', 'key.json', 'secrets.json', 'secrets.yaml', 'secrets.yml', 'secrets.toml'}:
        return True
    return bool(re.search(r'(?:credentials?|service[-_]account|client_secret|api[-_]key|private[-_]key).*\.json$', base))


def check_paths(names):
    bad = sorted({name for name in names if forbidden_path(name)})
    if bad:
        for name in bad[:20]:
            print(f'게시 금지 경로: {json.dumps(name, ensure_ascii=True)}', file=sys.stderr)
        raise CheckError(f'게시 금지 경로 {len(bad)}개를 발견했습니다.')


def empty_placeholder(name, oid):
    # Only zero bytes or a single LF/CRLF are accepted as directory markers.
    return PurePosixPath(name).name == '.gitkeep' and oid in EMPTY_BLOBS


def scanner_binary(root, explicit=None):
    common = Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip())
    name = 'gitleaks.exe' if sys.platform == 'win32' else 'gitleaks'
    target = Path(explicit).resolve() if explicit else common / 'kdpp-security/bin' / VERSION / name
    receipt = target.with_suffix(target.suffix + '.sha256')
    if not target.is_file() or not receipt.is_file():
        raise CheckError('검사기가 없습니다. python scripts/security/setup.py를 먼저 실행해 주세요.')
    if hashlib.sha256(target.read_bytes()).hexdigest() != receipt.read_text().strip():
        raise CheckError('검사기 해시가 달라 검사를 중단합니다.')
    result = subprocess.run([str(target), 'version'], capture_output=True, check=False)
    if result.returncode or result.stdout.decode().strip().removeprefix('v') != VERSION:
        raise CheckError('검사기 버전이 고정 버전과 다릅니다.')
    return target


def snapshot_paths(root, ref):
    rows = git(root, 'ls-tree', '-r', '-z', ref).split(b'\0')
    result = {}
    inspected = []
    for row in rows:
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        _mode, kind, oid = header.decode().split()
        name = name.decode('utf-8', errors='surrogateescape')
        if kind != 'blob':
            raise CheckError('하위 저장소 내용은 자동 검사할 수 없어 게시를 중단합니다.')
        result.setdefault(oid, name)
        if not empty_placeholder(name, oid):
            inspected.append(name)
    check_paths(inspected)
    return result


def staged_objects(root):
    changed = set(git(root, 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z').split(b'\0')) - {b''}
    objects = {}
    inspected = []
    for row in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        mode, oid, stage = header.decode().split()
        if stage != '0':
            raise CheckError('충돌한 인덱스가 있어 검사를 중단합니다.')
        if name in changed:
            if mode not in {'100644', '100755', '120000'}:
                raise CheckError('하위 저장소 내용은 자동 검사할 수 없습니다.')
            objects[oid] = name.decode('utf-8', errors='surrogateescape')
            if not empty_placeholder(objects[oid], oid):
                inspected.append(objects[oid])
    check_paths(inspected)
    return objects


def history_objects(root, tip, base=None, *, check_tip=True):
    if not OID.fullmatch(tip) or base and not OID.fullmatch(base):
        raise CheckError('검사할 커밋 형식이 잘못됐습니다.')
    shallow = git(root, 'rev-parse', '--is-shallow-repository').strip()
    if shallow == b'true':
        raise CheckError('전체 이력이 필요합니다. CI checkout의 fetch-depth: 0을 확인해 주세요.')
    paths = snapshot_paths(root, tip) if check_tip else {}
    revisions = [tip] + ([f'^{base}'] if base else [])
    identifiers = git(root, 'rev-list', '--objects', '--no-object-names', *revisions).decode().splitlines()
    commits = set(git(root, 'rev-list', *revisions).decode().splitlines())
    # Inspect introduced/modified paths even when a later commit deletes them.
    introduced = git(root, 'log', '--format=', '--raw', '-z', '--no-abbrev', '--no-renames',
                     '--diff-filter=ACM', '--no-ext-diff', '--no-textconv',
                     '--diff-merges=separate', *revisions).split(b'\0')
    inspected = []
    position = 0
    while position < len(introduced):
        header = introduced[position].lstrip(b'\n')
        position += 1
        if not header:
            continue
        fields = header.split()
        if len(fields) != 5 or not fields[0].startswith(b':') or position >= len(introduced):
            raise CheckError('Git 변경 경로를 해석하지 못해 게시를 중단합니다.')
        name = introduced[position].decode('utf-8', errors='surrogateescape')
        position += 1
        oid = fields[3].decode('ascii')
        if not empty_placeholder(name, oid):
            inspected.append(name)
    check_paths(inspected)
    return {oid: paths.get(oid, f'Git객체:{oid}') for oid in identifiers}, commits


def export_objects(root, objects, destination):
    if len(objects) > MAX_OBJECTS:
        raise CheckError('검사 객체 수 제한을 초과했습니다. 범위를 나눠 별도로 검토해 주세요.')
    if not objects:
        return {}, 0
    # Git's batch protocol avoids shell interpolation and scans immutable index/history blobs.
    payload = ''.join(oid + '\n' for oid in objects).encode('ascii')
    headers = git(root, 'cat-file', '--batch-check', input=payload).decode().splitlines()
    selected = []
    total = 0
    kinds = {}
    for header in headers:
        oid, kind, size = header.split()
        if kind not in {'blob', 'commit', 'tag'}:
            continue
        total += int(size)
        if total > MAX_BYTES:
            raise CheckError('검사 용량 제한을 초과했습니다. 파일을 건너뛰지 않고 게시를 중단합니다.')
        selected.append(oid)
        kinds[oid] = kind
    data = git(root, 'cat-file', '--batch', input=''.join(oid + '\n' for oid in selected).encode('ascii'))
    position = 0
    mapping = {}
    for expected in selected:
        end = data.index(b'\n', position)
        oid, kind, size = data[position:end].decode().split()
        assert oid == expected and kind == kinds[oid]
        start = end + 1
        position = start + int(size) + 1
        content = data[start:start + int(size)]
        if kind in {'commit', 'tag'}:
            content = content.split(b'\n\n', 1)[-1]
        # Neutral names prevent upstream extension/path allowlists from hiding renamed secrets.
        filename = f'{oid}.txt'
        (destination / filename).write_bytes(content)
        mapping[filename] = {'source': f'커밋/태그메시지:{oid}' if kind != 'blob' else objects[oid], 'object': oid}
    return mapping, total


def scan(root, binary, objects, *, buffers=None):
    reviewed = json.loads((root / 'scripts/security/reviewed-findings.json').read_text(encoding='utf-8'))['reviewed']
    allowed = {(entry['object'], entry['rule'], line) for entry in reviewed for line in entry['lines']}
    with tempfile.TemporaryDirectory(prefix='kdpp-security-') as folder:
        folder = Path(folder)
        source = folder / 'objects'
        source.mkdir()
        if buffers is None:
            mapping, total = export_objects(root, objects, source)
        else:
            if len(buffers) > MAX_OBJECTS or sum(map(len, buffers.values())) > MAX_BYTES:
                raise CheckError('작업 파일 검사 한도를 초과해 중단합니다.')
            mapping = {}
            total = 0
            for oid, content in buffers.items():
                filename = f'{oid}.txt'
                (source / filename).write_bytes(content)
                mapping[filename] = {'source': objects[oid], 'object': oid}
                total += len(content)
        if not mapping:
            print('비밀정보 검사 통과: 검사할 변경 객체 없음')
            return
        report = folder / 'findings.json'
        env = {key: value for key, value in os.environ.items() if not key.startswith('GITLEAKS_')}
        result = subprocess.run([str(binary), 'dir', str(source), '--config', str(root / '.gitleaks.toml'),
                                 '--ignore-gitleaks-allow', '--gitleaks-ignore-path', str(folder / 'no-ignore-file'),
                                 '--redact=100', '--no-banner', '--no-color', '--log-level=error',
                                 '--exit-code=1', '--timeout=120', '--report-format=json', '--report-path', str(report)],
                                cwd=root, env=env, capture_output=True, check=False)
        if result.returncode not in (0, 1) or not report.is_file():
            raise CheckError('검사 도구 실행에 실패했습니다. 원시 로그는 출력하지 않습니다.')
        findings = json.loads(report.read_text(encoding='utf-8')) or []
        if result.returncode == 1 and not findings:
            raise CheckError('검사 도구가 실패했지만 결과를 확인할 수 없습니다.')
        remaining = []
        for item in findings:
            info = mapping.get(Path(item['File']).name, {'object': ''})
            if (info['object'], item['RuleID'], item['StartLine']) not in allowed:
                remaining.append(item)
        reviewed_count = len(findings) - len(remaining)
        findings = remaining
        if findings:
            for item in findings[:30]:
                info = mapping.get(Path(item['File']).name, {'source': '알 수 없는 객체', 'object': ''})
                safe = {'file': info['source'], 'line': item['StartLine'], 'rule': item['RuleID'], 'object': info['object']}
                print(json.dumps(safe, ensure_ascii=True), file=sys.stderr)
            raise CheckError(f'비밀정보 의심 항목 {len(findings)}건을 발견해 게시를 중단합니다. 값은 출력하지 않았습니다.')
        print(f'비밀정보 검사 통과: 객체 {len(mapping)}개, {total}바이트, 검토된 공개 해시 예외 {reviewed_count}건')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['staged', 'pre-push', 'history', 'working-tree'])
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--binary', type=Path, help='검증된 설치 파일 경로(자동화 테스트용)')
    args = parser.parse_args()
    root = Path(git(HERE, 'rev-parse', '--show-toplevel').decode().strip())
    binary = scanner_binary(root, args.binary)
    if args.mode == 'staged':
        scan(root, binary, staged_objects(root))
    elif args.mode == 'history':
        tip = git(root, 'rev-parse', '--verify', args.ref + '^{object}').decode().strip()
        objects, _ = history_objects(root, tip)
        scan(root, binary, objects)
    elif args.mode == 'pre-push':
        for line in sys.stdin:
            fields = line.split()
            if len(fields) != 4:
                raise CheckError('푸시할 참조 정보를 읽지 못했습니다.')
            _, tip, _, base = fields
            if set(tip) == {'0'}:
                continue
            if not OID.fullmatch(tip) or not OID.fullmatch(base):
                raise CheckError('푸시할 객체 ID 형식이 잘못됐습니다.')
            exists = subprocess.run(['git', 'cat-file', '-e', base + '^{commit}'], cwd=root, capture_output=True, check=False).returncode == 0
            objects, _ = history_objects(root, tip, base if exists else None)
            scan(root, binary, objects)
    else:
        # Read tracked and visible untracked files only; ignored credentials/caches stay untouched.
        names = [name.decode('utf-8', errors='surrogateescape') for name in
                 git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0') if name]
        digest = hashlib.sha256 if git(root, 'rev-parse', '--show-object-format').strip() == b'sha256' else hashlib.sha1
        objects, buffers, inspected = {}, {}, []
        total = 0
        for name in names:
            path = root / name
            if not path.is_file() or path.is_symlink():
                raise CheckError('작업 파일이 없거나 심볼릭 링크여서 전체 내용 확인을 중단합니다.')
            with path.open('rb') as source:
                content = source.read(MAX_BYTES + 1)
            total += len(content)
            if total > MAX_BYTES or len(objects) >= MAX_OBJECTS:
                raise CheckError('작업 파일 검사 한도를 초과해 중단합니다.')
            oid = digest(f'blob {len(content)}\0'.encode('ascii') + content).hexdigest()
            objects[oid], buffers[oid] = name, content
            if not empty_placeholder(name, oid):
                inspected.append(name)
        check_paths(inspected)
        # No init, hash-object -w, index update or other Git write is needed.
        scan(root, binary, objects, buffers=buffers)


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        if sys.version_info < (3, 11):
            raise CheckError('Python 3.11 이상이 필요합니다.')
        main()
    except (CheckError, OSError, ValueError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, CheckError) else '보안 검사 실행 오류: 검사를 완료하지 못해 게시를 중단합니다.'
        print(message, file=sys.stderr)
        raise SystemExit(2)
