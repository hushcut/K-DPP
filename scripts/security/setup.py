"""Install a checksum-pinned scanner and Git hooks; standard library only."""
import argparse
import hashlib
import io
import json
import platform
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / 'gitleaks-release.json').read_text(encoding='utf-8'))


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode().strip()


def tool_directory(root):
    return Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')) / 'kdpp-security'


def binary_name():
    return 'gitleaks.exe' if sys.platform == 'win32' else 'gitleaks'


def install_binary(destination):
    system = {'win32': 'windows', 'linux': 'linux', 'darwin': 'darwin'}.get(sys.platform)
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(platform.machine().lower())
    key = f'{system}_{arch}'
    if key not in MANIFEST['archives']:
        raise RuntimeError('지원하지 않는 OS 또는 CPU입니다.')
    version = MANIFEST['version']
    target = destination / version / binary_name()
    receipt = target.with_suffix(target.suffix + '.sha256')
    if target.exists() and receipt.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() == receipt.read_text().strip():
            return target
        raise RuntimeError('설치된 검사기 해시가 달라 재검토가 필요합니다.')
    extension = 'zip' if system == 'windows' else 'tar.gz'
    archive = f'gitleaks_{version}_{key}.{extension}'
    url = f'https://github.com/gitleaks/gitleaks/releases/download/v{version}/{archive}'
    request = urllib.request.Request(url, headers={'User-Agent': 'K-DPP-security-setup'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(30 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != MANIFEST['archives'][key]:
        raise RuntimeError('다운로드 해시 검증에 실패했습니다. 설치하지 않습니다.')
    if system == 'windows':
        with zipfile.ZipFile(io.BytesIO(data)) as source:
            executable = source.read(binary_name())
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as source:
            member = source.getmember(binary_name())
            if not member.isfile():
                raise RuntimeError('검사기 파일 형식이 올바르지 않습니다.')
            executable = source.extractfile(member).read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(executable)
    target.chmod(0o755)
    receipt.write_text(hashlib.sha256(executable).hexdigest() + '\n', encoding='ascii')
    return target


def install_hooks(root):
    configured = subprocess.run(['git', 'config', '--get', 'core.hooksPath'], cwd=root, capture_output=True, check=False)
    if configured.returncode == 0:
        raise RuntimeError('기존 core.hooksPath가 있습니다. 기존 훅과의 연결을 먼저 검토해 주세요.')
    hooks = Path(git(root, 'rev-parse', '--path-format=absolute', '--git-path', 'hooks'))
    if hooks.is_symlink():
        raise RuntimeError('훅 폴더가 심볼릭 링크여서 자동 설치하지 않습니다.')
    names = ('pre-commit', 'pre-push')
    for name in names:
        target = hooks / name
        content = (root / '.githooks' / name).read_bytes()
        if target.is_symlink() or target.exists() and target.read_bytes() != content:
            raise RuntimeError(f'기존 {name} 훅이 있어 덮어쓰지 않습니다.')
    hooks.mkdir(parents=True, exist_ok=True)
    for name in names:
        content = (root / '.githooks' / name).read_bytes()
        target = hooks / name
        target.write_bytes(content)
        target.chmod(0o755)
    print('pre-commit·pre-push 보안 훅을 설치했습니다. 기존 commit-msg 훅은 유지했습니다.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-only', action='store_true')
    parser.add_argument('--destination', type=Path, help='다운로드 전용 모드의 검사기 저장 폴더')
    args = parser.parse_args()
    root = Path(git(HERE, 'rev-parse', '--show-toplevel'))
    if args.destination and not args.download_only:
        parser.error('--destination은 --download-only와 함께 사용합니다.')
    destination = args.destination.resolve() if args.destination else tool_directory(root) / 'bin'
    target = install_binary(destination)
    version = subprocess.run([str(target), 'version'], capture_output=True, text=True, check=True).stdout.strip()
    if version.removeprefix('v') != MANIFEST['version']:
        raise RuntimeError('검사기 버전이 고정 버전과 다릅니다.')
    print(f'Gitleaks {MANIFEST["version"]}: 다운로드·해시·버전 확인 완료')
    if not args.download_only:
        install_hooks(root)


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        if sys.version_info < (3, 11):
            raise RuntimeError('Python 3.11 이상이 필요합니다.')
        main()
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError,
            tarfile.TarError, zipfile.BadZipFile) as error:
        # Network/library exception strings may contain local paths or proxy credentials.
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(f'보안 검사기 설치 실패: {detail} 원시 외부 오류는 출력하지 않습니다.', file=sys.stderr)
        raise SystemExit(2)
