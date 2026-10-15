"""Use disposable Git repositories and generated invalid credentials; no network."""
import contextlib
import importlib.util
import io
import json
import os
import random
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SECURITY = Path(__file__).resolve().parents[1]
ROOT = SECURITY.parents[1]
sys.path.insert(0, str(SECURITY))
import check_secrets as checker

spec = importlib.util.spec_from_file_location('kdpp_security_setup', SECURITY / 'setup.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def generated_key():
    rng = random.Random(12345)
    return 'AI' + 'za' + ''.join(rng.choices(string.ascii_letters + string.digits + '_-', k=35))


def quiet_scan(root, binary, objects):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
        try:
            checker.scan(root, binary, objects)
        except checker.CheckError:
            return False, err.getvalue()
    return True, err.getvalue()


class PathPolicyTests(unittest.TestCase):
    def test_sensitive_paths_and_public_source_distinction(self):
        denied = ['.env', '.env.local', 'x.env', 'foo.env.prod', '.env.example.local',
                  '.env.production.example', 'AI/key.json', 'configs/credentials.json',
                  'different/service_account_backup.json', 'ssh/id_ed25519', 'signing.p12',
                  'account.pem', 'BACKEND/k_dpp.db-wal', 'QA_DATASET/new.jpg',
                  '.test-artifacts/report.txt', 'AI/kdpp_ai_ocr_integrated/outputs/cache.json',
                  '.aws/credentials', 'secrets/private.txt', '../escape.py']
        allowed = ['.env.example', '.env.template', 'mail.env.example', 'mail.env.template',
                   'FRONTEND/lib/models/clothes.dart', 'config.json', 'id_ed25519.pub',
                   'AI/kdpp_ai_ocr_integrated/tests/fixtures/real_ocr_composition_cases.json',
                   'AI/kdpp_ai_ocr_integrated/requirements-text.lock', 'app.environment.dart',
                   '.github/workflows/secret-scan.yml']
        for name in denied:
            with self.subTest(path=name):
                self.assertTrue(checker.forbidden_path(name))
        for name in allowed:
            with self.subTest(path=name):
                self.assertFalse(checker.forbidden_path(name))

    def test_missing_or_changed_tool_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix='kdpp-security-tool-') as folder:
            target = Path(folder) / 'missing.exe'
            with self.assertRaises(checker.CheckError):
                checker.scanner_binary(ROOT, target)
            target.write_bytes(b'not an executable')
            target.with_suffix('.exe.sha256').write_text('0' * 64)
            with self.assertRaises(checker.CheckError):
                checker.scanner_binary(ROOT, target)


class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        explicit = os.environ.get('KDPP_TEST_GITLEAKS')
        cls.binary = checker.scanner_binary(ROOT, explicit)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kdpp-security-tests-')
        self.root = Path(self.temp.name) / 'repository with spaces'
        self.root.mkdir()
        self.run_git('init', '-q')
        self.run_git('config', 'user.name', 'Security fixture')
        self.run_git('config', 'user.email', 'security-fixture@example.invalid')
        self.run_git('config', 'core.autocrlf', 'false')
        shutil.copy2(ROOT / '.gitleaks.toml', self.root / '.gitleaks.toml')
        self.write('scripts/security/reviewed-findings.json',
                   (SECURITY / 'reviewed-findings.json').read_text(encoding='utf-8'))
        self.write('safe.txt', 'public fixture\n')
        self.run_git('add', '--', 'safe.txt')
        self.run_git('commit', '-qm', 'safe fixture')
        self.base = self.run_git('rev-parse', 'HEAD').stdout.decode().strip()

    def tearDown(self):
        # Git-created files may be read-only on Windows; TemporaryDirectory handles normal cleanup.
        self.temp.cleanup()

    def run_git(self, *args, check=True, input=None):
        result = subprocess.run(['git', '-C', str(self.root), *args], input=input, capture_output=True, check=False)
        if check and result.returncode:
            self.fail('일회용 Git 저장소 명령 실패(원시 출력 생략): ' + args[0])
        return result

    def write(self, name, body):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')

    def stage(self, name, body):
        self.write(name, body)
        self.run_git('add', '--', name)

    def install_local_hooks(self):
        shutil.copytree(ROOT / 'scripts/security', self.root / 'scripts/security', dirs_exist_ok=True)
        shutil.copytree(ROOT / '.githooks', self.root / '.githooks')
        binary = installer.tool_directory(self.root) / 'bin' / checker.VERSION / installer.binary_name()
        binary.parent.mkdir(parents=True)
        try:
            os.link(self.binary, binary)
        except OSError:
            shutil.copy2(self.binary, binary)
        shutil.copy2(self.binary.with_suffix(self.binary.suffix + '.sha256'),
                     binary.with_suffix(binary.suffix + '.sha256'))
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install_hooks(self.root)

    def assert_secret_blocked(self, objects):
        before = self.run_git('ls-files', '--stage', '-z').stdout
        passed, errors = quiet_scan(self.root, self.binary, objects)
        self.assertFalse(passed, '가짜 키를 차단하지 못했습니다.')
        self.assertTrue(generated_key() not in errors, '원문 값이 로그에 노출되었습니다.')
        self.assertTrue('rule' in errors and 'object' in errors)
        self.assertEqual(before, self.run_git('ls-files', '--stage', '-z').stdout)

    def test_clean_staged_files_pass(self):
        self.stage('public.py', 'api_key = "${API_KEY}"\n')
        objects = checker.staged_objects(self.root)
        self.assertTrue(quiet_scan(self.root, self.binary, objects)[0])

    def test_actual_index_scanned_when_worktree_is_clean(self):
        self.stage('ordinary.py', 'api_key = "' + generated_key() + '"\n')
        self.write('ordinary.py', 'api_key = "${API_KEY}"\n')
        self.assert_secret_blocked(checker.staged_objects(self.root))

    def test_extension_allowlist_and_inline_comment_cannot_hide_key(self):
        self.stage('ordinary.png', generated_key() + ' # gitleaks:allow\n')
        self.assert_secret_blocked(checker.staged_objects(self.root))

    def test_secret_in_example_is_still_blocked(self):
        self.stage('.env.example', 'GOOGLE_API_KEY=' + generated_key() + '\n')
        self.assert_secret_blocked(checker.staged_objects(self.root))

    def test_private_key_and_service_account_are_detected(self):
        for kind, body in [('private marker', '-----BEGIN ' + 'PRIVATE KEY-----\nnot-a-real-key\n'),
                           ('service account', json.dumps({'type': 'service_' + 'account', 'private_key': ''}))]:
            with self.subTest(case=kind):
                self.stage('ordinary.txt', body)
                self.assertFalse(quiet_scan(self.root, self.binary, checker.staged_objects(self.root))[0])

    def test_secret_deleted_in_later_commit_is_still_blocked(self):
        self.stage('ordinary.md', generated_key() + '\n')
        self.run_git('commit', '-qm', 'intermediate fixture')
        self.run_git('rm', '-q', '--', 'ordinary.md')
        self.run_git('commit', '-qm', 'remove fixture')
        tip = self.run_git('rev-parse', 'HEAD').stdout.decode().strip()
        objects, _ = checker.history_objects(self.root, tip, self.base)
        self.assert_secret_blocked(objects)

    def test_commit_message_is_scanned(self):
        self.run_git('commit', '--allow-empty', '-qm', generated_key())
        tip = self.run_git('rev-parse', 'HEAD').stdout.decode().strip()
        objects, _ = checker.history_objects(self.root, tip, self.base)
        self.assert_secret_blocked(objects)

    def test_annotated_tag_message_is_scanned(self):
        self.run_git('tag', '-a', 'fixture', '-m', generated_key())
        tag = self.run_git('rev-parse', 'refs/tags/fixture').stdout.decode().strip()
        objects, _ = checker.history_objects(self.root, tag)
        self.assert_secret_blocked(objects)

    def test_prohibited_path_deleted_later_is_still_blocked(self):
        self.stage('credentials.json', '{}\n')
        self.run_git('commit', '-qm', 'intermediate credential path fixture')
        self.run_git('rm', '-q', '--', 'credentials.json')
        self.run_git('commit', '-qm', 'remove credential path fixture')
        tip = self.run_git('rev-parse', 'HEAD').stdout.decode().strip()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(checker.CheckError):
            checker.history_objects(self.root, tip, self.base)

    def test_clean_history_and_initial_commit_pass(self):
        objects, commits = checker.history_objects(self.root, self.base)
        self.assertEqual(len(commits), 1)
        self.assertTrue(quiet_scan(self.root, self.binary, objects)[0])

    def test_empty_placeholder_is_allowed_but_cannot_hold_data(self):
        name = 'AI/component/models/symbol/.gitkeep'
        self.stage(name, '\n')
        self.assertTrue(quiet_scan(self.root, self.binary, checker.staged_objects(self.root))[0])
        self.run_git('commit', '-qm', 'empty directory marker')
        tip = self.run_git('rev-parse', 'HEAD').stdout.decode().strip()
        checker.history_objects(self.root, tip, self.base)
        self.stage(name, 'local model content\n')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(checker.CheckError):
            checker.staged_objects(self.root)
        self.run_git('commit', '-qm', 'nonempty directory marker')
        self.run_git('rm', '-q', '--', name)
        self.run_git('commit', '-qm', 'remove marker')
        tip = self.run_git('rev-parse', 'HEAD').stdout.decode().strip()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(checker.CheckError):
            checker.history_objects(self.root, tip, self.base)

    def test_size_limit_and_missing_objects_fail_closed(self):
        self.stage('more.txt', 'public data\n')
        objects = checker.staged_objects(self.root)
        with mock.patch.object(checker, 'MAX_BYTES', 1), self.assertRaises(checker.CheckError):
            checker.export_objects(self.root, objects, self.root)
        with self.assertRaises((checker.CheckError, ValueError)):
            checker.export_objects(self.root, {'f' * 40: 'missing.txt'}, self.root)

    def test_real_precommit_blocks_and_preserves_existing_message_hook(self):
        message_hook = self.root / '.git/hooks/commit-msg'
        original = b'#!/bin/sh\nexit 0\n'
        message_hook.write_bytes(original)
        message_hook.chmod(0o755)
        self.install_local_hooks()
        self.assertEqual(message_hook.read_bytes(), original)
        self.stage('ordinary.py', generated_key() + '\n')
        result = self.run_git('commit', '-qm', 'must be blocked', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'"rule"', result.stderr)
        self.assertEqual(self.base, self.run_git('rev-parse', 'HEAD').stdout.decode().strip())
        self.assertTrue(generated_key().encode() not in result.stdout + result.stderr)

    def test_real_prepush_blocks_new_branch_and_intermediate_secret(self):
        self.stage('ordinary.md', generated_key() + '\n')
        self.run_git('commit', '-qm', 'intermediate fixture')
        self.run_git('rm', '-q', '--', 'ordinary.md')
        self.run_git('commit', '-qm', 'remove fixture')
        self.install_local_hooks()
        remote = Path(self.temp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True, capture_output=True)
        result = self.run_git('push', str(remote), 'HEAD:refs/heads/fixture', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'"rule"', result.stderr)
        self.assertTrue(generated_key().encode() not in result.stdout + result.stderr)
        refs = subprocess.run(['git', '--git-dir', str(remote), 'show-ref'], capture_output=True, check=False)
        self.assertEqual(refs.returncode, 1)

    def test_real_hooks_allow_clean_commit_and_push(self):
        self.install_local_hooks()
        self.stage('public.py', 'api_key = "${API_KEY}"\n')
        self.run_git('commit', '-qm', 'clean fixture with hooks')
        remote = Path(self.temp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True, capture_output=True)
        self.run_git('push', str(remote), 'HEAD:refs/heads/fixture')
        refs = subprocess.run(['git', '--git-dir', str(remote), 'show-ref'], capture_output=True, check=False)
        self.assertEqual(refs.returncode, 0)

    def test_environment_config_cannot_replace_checked_config(self):
        self.stage('ordinary.py', generated_key() + '\n')
        with mock.patch.dict(os.environ, {'GITLEAKS_CONFIG_TOML': 'title = "empty config"'}):
            self.assert_secret_blocked(checker.staged_objects(self.root))

    def test_review_exception_does_not_cover_new_blob_content(self):
        body = 'api_key="' + generated_key()[4:] + '"\n'
        self.stage('ordinary.py', body)
        objects = checker.staged_objects(self.root)
        self.assertFalse(quiet_scan(self.root, self.binary, objects)[0])
        reviewed = {'reviewed': [{'object': next(iter(objects)), 'rule': 'generic-api-key',
                                  'lines': [1], 'reason': 'Generated test-only exception'}]}
        self.write('scripts/security/reviewed-findings.json', json.dumps(reviewed))
        self.assertTrue(quiet_scan(self.root, self.binary, objects)[0])
        self.stage('ordinary.py', body + '# changed content\n')
        self.assertFalse(quiet_scan(self.root, self.binary, checker.staged_objects(self.root))[0])

    def test_existing_managed_hooks_are_not_silently_replaced(self):
        shutil.copytree(ROOT / '.githooks', self.root / '.githooks')
        target = self.root / '.git/hooks/pre-commit'
        target.write_bytes(b'#!/bin/sh\n# user hook\nexit 0\n')
        with self.assertRaises(RuntimeError):
            installer.install_hooks(self.root)
        self.assertIn(b'# user hook', target.read_bytes())

    def test_edited_managed_hook_is_preserved(self):
        self.install_local_hooks()
        target = self.root / '.git/hooks/pre-commit'
        edited = target.read_bytes() + b'\n# additional user checks\n'
        target.write_bytes(edited)
        with self.assertRaises(RuntimeError):
            installer.install_hooks(self.root)
        self.assertEqual(target.read_bytes(), edited)

    def test_branch_missing_security_scripts_fails_closed(self):
        self.install_local_hooks()
        shutil.rmtree(self.root / 'scripts/security')
        result = self.run_git('commit', '--allow-empty', '-qm', 'must be blocked', check=False)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
