"""Exercise release downloads with mocked Expo and network commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / 'build_android_release.sh'
BUILD_ID = 'f12961e9-779a-414c-8e9a-a3fda2122fa4'


class AndroidReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'devops').mkdir()
        (self.root / 'client').mkdir()
        self.script = self.root / 'devops/build_android_release.sh'
        shutil.copy2(SCRIPT, self.script)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'commands.log'
        self.archive = self.root / 'artifact.zip'
        self.build = self.root / 'build.json'
        self.metadata()
        self.make_archive()
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                        MOCK_LOG=str(self.log), MOCK_BUILD=str(self.build),
                        MOCK_ARCHIVE=str(self.archive))
        self.command('npm', 'printf "npm %s\\n" "$*" >> "$MOCK_LOG"\n')
        self.command('npx', '''printf 'npx %s\n' "$*" >> "$MOCK_LOG"
if [ "$3" = build ]; then
    [ "${MOCK_BUILD_FAIL:-0}" = 0 ] || exit 1
    printf 'See logs: https://expo.dev/accounts/test/projects/wordrecall/builds/f12961e9-779a-414c-8e9a-a3fda2122fa4\n'
else
    cat "$MOCK_BUILD"
fi
''')
        self.command('curl', '''printf 'curl\n' >> "$MOCK_LOG"
while [ "$#" -gt 0 ]; do
    if [ "$1" = --output ]; then cp "$MOCK_ARCHIVE" "$2"; exit; fi
    shift
done
exit 1
''')

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\nset -eu\n' + body)
        path.chmod(0o755)

    def metadata(self, status='FINISHED', extension='apk'):
        self.build.write_text(json.dumps({
            'id': BUILD_ID, 'platform': 'ANDROID', 'status': status,
            'appVersion': '1.0.0', 'appBuildVersion': '8',
            'artifacts': {'applicationArchiveUrl': f'https://example.invalid/app.{extension}'},
        }))

    def make_archive(self, manifest='AndroidManifest.xml'):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr(manifest, 'test manifest')

    def run_script(self, *args):
        return subprocess.run(['bash', str(self.script), *args], cwd=self.root,
                              env=self.env, capture_output=True, text=True)

    def test_build_checks_client_and_downloads_exact_build(self):
        result = self.run_script('--non-interactive')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        log = self.log.read_text()
        self.assertIn('npm ci', log)
        self.assertIn('npm run typecheck', log)
        self.assertIn('npm run lint', log)
        self.assertIn('--profile release-apk --wait --non-interactive', log)
        self.assertIn(f'build:view {BUILD_ID} --json', log)
        files = list((self.root / 'build/android').glob('*.apk'))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), self.archive.read_bytes())

    def test_download_existing_aab_skips_new_build_and_client_checks(self):
        self.metadata(extension='aab')
        self.make_archive('base/manifest/AndroidManifest.xml')
        result = self.run_script('aab', '--download-build', BUILD_ID)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        log = self.log.read_text()
        self.assertNotIn('npm ', log)
        self.assertNotIn('build --platform', log)
        self.assertEqual(len(list((self.root / 'build/android').glob('*.aab'))), 1)

    def test_default_build_works_with_macos_bash_and_keeps_interactive_mode(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        log = self.log.read_text()
        self.assertIn('--profile release-apk --wait', log)
        self.assertNotIn('--non-interactive', log)

    def test_failed_build_does_not_download(self):
        self.env['MOCK_BUILD_FAIL'] = '1'
        result = self.run_script('--non-interactive')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('curl', self.log.read_text())

    def test_rejects_unfinished_build_and_wrong_format_before_download(self):
        for status, extension in [('IN_PROGRESS', 'apk'), ('FINISHED', 'aab')]:
            with self.subTest(status=status, extension=extension):
                self.metadata(status, extension)
                result = self.run_script('--download-build', BUILD_ID)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('curl', self.log.read_text())

    def test_invalid_archive_is_not_saved_and_temporary_download_is_removed(self):
        for content in ('html', 'missing manifest'):
            with self.subTest(content=content):
                if content == 'html':
                    self.archive.write_text('<html>Not an APK</html>')
                else:
                    self.make_archive('wrong-file')
                result = self.run_script('--download-build', BUILD_ID)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(list((self.root / 'build/android').iterdir()), [])

    def test_invalid_arguments_fail_before_running_commands(self):
        for args in [('apk', 'aab'), ('--download-build',),
                     ('--download-build', '--non-interactive')]:
            with self.subTest(args=args):
                self.assertEqual(self.run_script(*args).returncode, 2)
                self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()
