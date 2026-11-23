"""Exercise CD with a disposable Git remote and mocked SSH, never a live board."""
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

DEVOPS = Path(__file__).resolve().parents[1]
SHA = 'a' * 40


class RemoteDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.repo = self.root / 'board'
        self.repo.mkdir()
        self.env = dict(os.environ, HOME=str(self.root), MOCK_DEPLOY_LOG=str(self.root / 'deployed'))
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'CD Test')
        (self.repo / 'backend').mkdir()
        (self.repo / 'backend/.env').write_text('PRIVATE_TEST_VALUE=preserved\n')
        (self.repo / '.gitignore').write_text('.env\n')
        (self.repo / 'devops').mkdir()
        (self.repo / 'devops/deploy-jetson.sh').write_text(
            'printf "%s\\n" "$@" > "$MOCK_DEPLOY_LOG"\nexit "${MOCK_DEPLOY_STATUS:-0}"\n')
        self.git('add', '.')
        self.git('commit', '-m', 'Initial deployment')
        self.initial = self.git('rev-parse', 'HEAD')
        self.remote = self.root / 'origin.git'
        self.git('clone', '--bare', str(self.repo), str(self.remote))
        self.git('remote', 'add', 'origin', str(self.remote))
        self.author = self.root / 'author'
        self.git('clone', str(self.remote), str(self.author))
        self.git('-C', str(self.author), 'config', 'user.email', 'test@example.invalid')
        self.git('-C', str(self.author), 'config', 'user.name', 'CD Test')
        (self.author / 'change').write_text('tested change\n')
        self.git('-C', str(self.author), 'add', 'change')
        self.git('-C', str(self.author), 'commit', '-m', 'Tested change')
        self.git('-C', str(self.author), 'push', 'origin', 'main')
        self.revision = self.git('-C', str(self.author), 'rev-parse', 'HEAD')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        sudo = self.bin / 'sudo'
        sudo.write_text('#!/bin/sh\nexit 0\n')
        sudo.chmod(0o700)
        self.env['PATH'] = f'{self.bin}:{os.environ["PATH"]}'
        self.upload = tempfile.TemporaryDirectory(prefix='wordrecall-cd.', dir='/tmp')
        self.addCleanup(self.upload.cleanup)
        spa = self.root / 'index.html'
        spa.write_text('<html>Test SPA</html>')
        with tarfile.open(Path(self.upload.name) / 'web.tar.gz', 'w:gz') as archive:
            archive.add(spa, arcname='index.html')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, env=self.env,
                              check=True, capture_output=True, text=True).stdout.strip()

    def deploy(self, revision=None):
        return subprocess.run(['bash', str(DEVOPS / 'cd-jetson-remote.sh'), str(self.repo),
                               revision or self.revision, self.upload.name,
                               'example.invalid', '8088', '8001', '/srv/wordrecall', 'false'],
                              env=self.env, capture_output=True, text=True)

    def test_deploys_exact_commit_and_preserves_private_config(self):
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.revision)
        self.assertEqual((self.repo / 'backend/.env').read_text(), 'PRIVATE_TEST_VALUE=preserved\n')
        arguments = (self.root / 'deployed').read_text()
        self.assertIn('--web-build-dir\n', arguments)
        self.assertNotIn('--configure-nginx', arguments)
        self.assertNotIn('--skip-backend', arguments)

    def test_stale_run_cannot_change_checkout(self):
        result = self.deploy(self.initial)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stale', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)
        self.assertFalse((self.root / 'deployed').exists())

    def test_dirty_checkout_is_preserved(self):
        (self.repo / '.gitignore').write_text('.env\nlocal change\n')
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Tracked local changes', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)

    def test_divergent_checkout_is_preserved(self):
        (self.repo / 'board-only').write_text('local commit')
        self.git('add', 'board-only')
        self.git('commit', '-m', 'Board-only commit')
        before = self.git('rev-parse', 'HEAD')
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('diverged', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), before)

    def test_deployer_failure_is_reported_without_database_recovery(self):
        self.env['MOCK_DEPLOY_STATUS'] = '17'
        result = self.deploy()
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.revision)
        self.assertNotIn('Successfully deployed', result.stdout)


class SSHTransportTests(unittest.TestCase):
    def test_verified_ssh_arguments_failure_propagation_and_cleanup(self):
        for scp_status in (0, 23):
            with self.subTest(scp_status=scp_status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                build = root / 'web'
                build.mkdir()
                (build / 'index.html').write_text('<html>SPA</html>')
                binary = root / 'bin'
                binary.mkdir()
                for command in ('ssh', 'scp'):
                    script = binary / command
                    script.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['MOCK_LOG'], 'a') as output:
    output.write(json.dumps([Path(sys.argv[0]).name, args]) + '\\n')
if Path(sys.argv[0]).name == 'scp':
    sys.exit(int(os.environ['MOCK_SCP_STATUS']))
if 'mktemp' in args[-1]:
    print('/tmp/wordrecall-cd.Mock123')
elif args[-1].startswith('bash -s'):
    Path(os.environ['MOCK_INPUT']).write_text(sys.stdin.read())
''')
                    script.chmod(0o700)
                env = dict(os.environ, PATH=f'{binary}:{os.environ["PATH"]}',
                           TMPDIR=str(root), MOCK_LOG=str(root / 'log'),
                           MOCK_INPUT=str(root / 'input'), MOCK_SCP_STATUS=str(scp_status),
                           JETSON_HOST='board.example.invalid', JETSON_USER='deploy',
                           JETSON_REPO_PATH='/home/deploy/wordrecall', JETSON_SSH_PORT='2222',
                           JETSON_SSH_PRIVATE_KEY='fake-test-key',
                           JETSON_SSH_KNOWN_HOSTS='fake-test-host-key')
                result = subprocess.run(['bash', str(DEVOPS / 'cd-jetson.sh'), SHA, str(build)],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, scp_status, result.stderr)
                log = (root / 'log').read_text()
                self.assertIn('StrictHostKeyChecking=yes', log)
                self.assertIn('BatchMode=yes', log)
                self.assertIn('2222', log)
                self.assertIn("rm -rf -- '/tmp/wordrecall-cd.Mock123'", log)
                self.assertNotIn('fake-test-key', log)
                self.assertEqual(list(root.glob('tmp*/key')), [])
                if scp_status == 0:
                    self.assertEqual((root / 'input').read_text(),
                                     (DEVOPS / 'cd-jetson-remote.sh').read_text())
                else:
                    self.assertFalse((root / 'input').exists())


if __name__ == '__main__':
    unittest.main()
