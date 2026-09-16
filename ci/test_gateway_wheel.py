"""Regression checks for stale build output accidentally entering a wheel."""
import base64
import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
from verify_gateway_wheel import verify


class WheelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'app'; self.source.mkdir()
        (self.source / 'main.py').write_bytes(b'CURRENT = True\n')
        (self.source / '__init__.py').write_bytes(b'')
        self.data = {'app/main.py': b'CURRENT = True\n', 'app/__init__.py': b''}

    def make(self, bad_record=False, duplicate=False):
        wheel = self.root / 'gateway.whl'
        record = 'gateway-0.1.0.dist-info/RECORD'
        csv_text = io.StringIO(); writer = csv.writer(csv_text)
        for name, data in self.data.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
            writer.writerow((name, 'sha256=' + ('wrong' if bad_record else digest), str(len(data))))
        writer.writerow((record, '', ''))
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, data in self.data.items(): archive.writestr(name, data)
            archive.writestr(record, csv_text.getvalue())
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    archive.writestr('app/main.py', self.data['app/main.py'])
        return wheel

    def test_current_source_passes(self):
        self.assertEqual(verify(self.make(), self.source)['python_files'], 2)

    def test_stale_built_source_fails(self):
        self.data['app/main.py'] = b'CURRENT = False\n'
        with self.assertRaisesRegex(ValueError, 'Wheel/source mismatch'):
            verify(self.make(), self.source)

    def test_missing_new_module_fails(self):
        (self.source / 'realtime.py').write_text('JOURNAL = True\n')
        with self.assertRaisesRegex(ValueError, 'Wheel/source mismatch'):
            verify(self.make(), self.source)

    def test_extra_old_module_fails(self):
        self.data['app/obsolete.py'] = b'OBSOLETE = True\n'
        with self.assertRaisesRegex(ValueError, 'Wheel/source mismatch'):
            verify(self.make(), self.source)

    def test_invalid_record_fails(self):
        with self.assertRaisesRegex(ValueError, 'Invalid RECORD digest'):
            verify(self.make(bad_record=True), self.source)

    def test_duplicate_entry_fails(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            verify(self.make(duplicate=True), self.source)


if __name__ == '__main__':
    unittest.main()
