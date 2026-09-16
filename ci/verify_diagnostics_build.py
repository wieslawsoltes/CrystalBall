"""Check the real linked bench image and package only three non-credential images.

This checks build provenance and application isolation, not physical behavior,
calibration, firmware authenticity or production authorization.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

FILES = {'0x0': 'bootloader/bootloader.bin', '0x8000': 'partition_table/partition-table.bin',
         '0x10000': 'aether_orb.bin'}
REQUIRED = {'orb_diagnostics_run', 'orb_diag_pattern', 'orb_diag_pcm_stats', 'orb_audio_test_tone', 'orb_halo_pixel'}
FORBIDDEN = {'orb_network_init', 'orb_network_online', 'orb_fortune', 'orb_speech', 'orb_config_load', 'esp_wifi_start'}
WARNING = '''BENCH DIAGNOSTICS ONLY. NOT CUSTOMER FIRMWARE. NOT PHYSICALLY QUALIFIED.
Target: ESP32-S3-DevKitC-1-N8R8; CrystalBall Rev B module carrier.
No gateway certificate, credentials or NVS provisioning image is included.
Before connecting either DevKit USB port: disconnect carrier power and remove
DevKit from BOTH carrier sockets. Never dual-power the installed controller.
Review docs/bench-diagnostics.md and every flash address before programming.
Use only a development board without an irreversible production security policy.
This tool does not burn eFuses, bypass secure boot or authorize production.
After bench work rebuild and install the intended customer firmware using its
own trusted gateway CA and approved provisioning process.
Tone is intentionally quiet and requires held TALK. Keep speaker away from ears.
Digital microphone counts and successful driver calls are NOT acceptance passes.
'''

def verify(build, commit):
    if not re.fullmatch('[0-9a-f]{40}', commit): raise ValueError('Exact source commit required')
    # kconfgen JSON uses bare Kconfig symbol names, unlike sdkconfig.h/.cmake.
    config=json.loads((build/'config/sdkconfig.json').read_text())
    if config.get('ORB_FACTORY_DIAGNOSTICS') is not True: raise ValueError('Not a diagnostic build')
    if config.get('ORB_PUBLIC_TTS') or config.get('ORB_CALIBRATION_BOOT'): raise ValueError('Conflicting build modes')
    if config.get('IDF_TARGET') != 'esp32s3': raise ValueError('Wrong chip target')
    symbols={line.split()[-1] for line in (build/'defined-symbols.txt').read_text().splitlines() if line.split()}
    if not REQUIRED <= symbols: raise ValueError('Diagnostic entry points missing')
    if FORBIDDEN & symbols or any('gateway_ca_pem' in s for s in symbols): raise ValueError('Network, credentials or CA linked into bench image')
    arguments=json.loads((build/'flasher_args.json').read_text())
    addresses={hex(int(k,0)):v for k,v in arguments.get('flash_files',{}).items()}
    if addresses != FILES: raise ValueError('Unexpected flash image/address set')
    if arguments.get('extra_esptool_args',{}).get('chip') != 'esp32s3': raise ValueError('Unexpected flasher chip')
    hashes={}
    for address,name in FILES.items():
        path=build/name
        if not path.is_file() or any(p.is_symlink() for p in [path,*path.parents]): raise ValueError('Unsafe image path')
        data=path.read_bytes()
        if not data or len(data)>{'0x0':0x8000,'0x8000':0x1000,'0x10000':0x300000}[address]: raise ValueError('Invalid image size')
        if name.endswith('aether_orb.bin') and data[0]!=0xe9: raise ValueError('Not an ESP image')
        hashes[name]=hashlib.sha256(data).hexdigest()
    return {'schema':1,'passed':True,'source_commit':commit,'profile':'factory-diagnostics',
            'target':'esp32s3','release':'BENCH_ONLY_NOT_PHYSICALLY_QUALIFIED',
            'application_network_symbols_absent':True,'flash_files':FILES,'sha256':hashes,
            'meaning':'Build isolation and file integrity; not hardware qualification or firmware signing'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--source-commit',required=True)
    args=parser.parse_args();report=verify(args.build,args.source_commit)
    out=args.build/'bench-package'
    if out.exists(): raise ValueError('Refusing to overwrite existing bench package')
    out.mkdir()
    for name in FILES.values():
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(args.build/name,dest)
    shutil.copyfile(args.build/'flasher_args.json',out/'flasher_args.json')
    (out/'BENCH-ONLY.txt').write_text(WARNING)
    (out/'MANIFEST.json').write_text(json.dumps(report,indent=2)+'\n')
    (args.build/'diagnostics-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
