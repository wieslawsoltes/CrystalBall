"""Network-free tests for strict published-byte verification."""
import hashlib
import json
import unittest
from verify_live_pages import BASE, validate_manifest, verify_once


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.content = {n: n.encode() for n in ('index.html', 'style.css', 'src/app.js',
                        'src/orb.wgsl', 'assets/assembly.json')}
        self.manifest = {'schema': 1, 'source_commit': 'a' * 40,
                         'release': 'ENGINEERING_CANDIDATE_NOT_PRODUCTION_RELEASED',
                         'files': {n: hashlib.sha256(b).hexdigest() for n, b in self.content.items()}}

    def raw(self):
        return json.dumps(self.manifest).encode()

    def read(self, url, limit):
        self.assertTrue(url.startswith(BASE))
        name = url.removeprefix(BASE).split('?')[0]
        value = self.raw() if name == 'build.json' else self.content[name]
        self.assertLessEqual(len(value), limit)
        return value

    def test_exact_bytes_pass(self):
        self.assertTrue(verify_once(self.raw(), self.read)['passed'])

    def test_wrong_asset_fails(self):
        self.content['src/app.js'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'asset differs'):
            verify_once(self.raw(), self.read)

    def test_stale_manifest_fails(self):
        expected = self.raw()
        self.manifest['source_commit'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'manifest differs'):
            verify_once(expected, self.read)

    def test_unsafe_paths_rejected(self):
        for name in ('/index.html', '../private', 'src/../../.env', 'src//app.js',
                     'src\\app.js', 'https://evil.test', '%2e%2e/foo', 'src/app.js?q=1'):
            with self.subTest(name=name):
                self.setUp()
                self.manifest['files'][name] = 'b' * 64
                with self.assertRaises(ValueError):
                    validate_manifest(self.raw())

    def test_missing_entry_rejected(self):
        del self.manifest['files']['index.html']
        with self.assertRaises(ValueError):
            validate_manifest(self.raw())

    def test_invalid_commit_rejected(self):
        self.manifest['source_commit'] = 'main'
        with self.assertRaises(ValueError):
            validate_manifest(self.raw())

    def test_invalid_hash_rejected(self):
        self.manifest['files']['src/app.js'] = 'not-a-sha256'
        with self.assertRaises(ValueError):
            validate_manifest(self.raw())

    def test_size_bounded(self):
        with self.assertRaises(ValueError):
            validate_manifest(b' ' * (128 * 1024 + 1))


if __name__ == '__main__':
    unittest.main()
