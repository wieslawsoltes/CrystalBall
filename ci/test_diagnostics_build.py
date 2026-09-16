import json
from pathlib import Path
import tempfile
import unittest
from verify_diagnostics_build import verify, FILES, REQUIRED

class DiagnosticBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'config').mkdir()
        self.config={'ORB_FACTORY_DIAGNOSTICS':True,'IDF_TARGET':'esp32s3'}
        self.write_config()
        (self.root/'defined-symbols.txt').write_text('\n'.join('123 T '+s for s in REQUIRED))
        self.arguments={'flash_files':FILES,'extra_esptool_args':{'chip':'esp32s3'}}
        self.write_arguments()
        for name in FILES.values():
            p=self.root/name;p.parent.mkdir(exist_ok=True);p.write_bytes(b'\xe9test image')
    def write_config(self): (self.root/'config/sdkconfig.json').write_text(json.dumps(self.config))
    def write_arguments(self): (self.root/'flasher_args.json').write_text(json.dumps(self.arguments))
    def test_isolated_image(self): self.assertTrue(verify(self.root,'a'*40)['passed'])
    def test_prefixed_header_names_are_not_json_configuration(self):
        self.config={'CONFIG_ORB_FACTORY_DIAGNOSTICS':True,'CONFIG_IDF_TARGET':'esp32s3'}
        self.write_config()
        with self.assertRaisesRegex(ValueError,'Not a diagnostic build'):verify(self.root,'a'*40)
    def test_normal_firmware_rejected(self):
        self.config['ORB_FACTORY_DIAGNOSTICS']=False;self.write_config()
        with self.assertRaises(ValueError):verify(self.root,'a'*40)
    def test_conflicting_mode(self):
        self.config['ORB_PUBLIC_TTS']=True;self.write_config()
        with self.assertRaises(ValueError):verify(self.root,'a'*40)
    def test_network_path_rejected(self):
        p=self.root/'defined-symbols.txt';p.write_text(p.read_text()+'\n123 T orb_network_init')
        with self.assertRaisesRegex(ValueError,'Network'):verify(self.root,'a'*40)
    def test_ca_rejected(self):
        p=self.root/'defined-symbols.txt';p.write_text(p.read_text()+'\n123 T _binary_gateway_ca_pem_start')
        with self.assertRaises(ValueError):verify(self.root,'a'*40)
    def test_non_diag_symbols_rejected(self):
        (self.root/'defined-symbols.txt').write_text('123 T app_main')
        with self.assertRaises(ValueError):verify(self.root,'a'*40)
    def test_unknown_address_rejected(self):
        self.arguments['flash_files']={'0x9000':'nvs.bin'};self.write_arguments()
        with self.assertRaises(ValueError):verify(self.root,'a'*40)
    def test_wrong_chip_rejected(self):
        self.arguments['extra_esptool_args']['chip']='esp32';self.write_arguments()
        with self.assertRaises(ValueError):verify(self.root,'a'*40)
    def test_exact_commit_required(self):
        with self.assertRaises(ValueError):verify(self.root,'main')
    def test_missing_image_rejected(self):
        (self.root/'aether_orb.bin').unlink()
        with self.assertRaises(ValueError):verify(self.root,'a'*40)
    def test_image_magic_rejected(self):
        (self.root/'aether_orb.bin').write_bytes(b'not firmware')
        with self.assertRaises(ValueError):verify(self.root,'a'*40)
    def test_symlink_image_rejected(self):
        original=self.root/'aether_orb.bin';original.rename(self.root/'secret');original.symlink_to(self.root/'secret')
        with self.assertRaises(ValueError):verify(self.root,'a'*40)

if __name__=='__main__':unittest.main()
