"""Create per-unit ESP-IDF NVS data; explicit detached-DevKit confirmation gates flashing.

No automatic eFuse changes, secure-boot key generation, flash encryption or chip erase.
The development NVS partition is plaintext. Never ship it as protected storage.
"""
from __future__ import annotations
import argparse
import csv
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
try:
    from .common import ROOT, origin, private_json, private_write, token, unit_id, wifi
except ImportError:
    from common import ROOT, origin, private_json, private_write, token, unit_id, wifi

def nvs_csv(unit: str, url: str, secret: str, ssid: str, password: str) -> str:
    unit, url, secret = unit_id(unit), origin(url), token(secret)
    ssid, password = wifi(ssid, password)
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['key','type','encoding','value'])
    writer.writerow(['orb','namespace','',''])
    for key, value in [('unit',unit),('url',url),('token',secret),('ssid',ssid),('password',password)]:
        writer.writerow([key,'data','string',value])
    return stream.getvalue()

def partition(path: Path) -> tuple[int, int]:
    for row in csv.reader(path.read_text().splitlines()):
        if not row or row[0].lstrip().startswith('#'):
            continue
        row = [value.strip() for value in row]
        if len(row) >= 5 and row[:3] == ['nvs','data','nvs']:
            def number(value: str) -> int:
                if not value:
                    raise ValueError('NVS partition offset and size must be explicit')
                return int(value[:-1],0)*{'K':1024,'M':1048576}[value[-1].upper()] if value[-1].upper() in ('K','M') else int(value,0)
            address, size = number(row[3]), number(row[4])
            if address % 4096 or size % 4096 or size < 12288:
                raise ValueError('Invalid NVS partition alignment/size')
            return address, size
    raise ValueError('No explicitly addressed NVS data partition found')

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', type=Path, required=True, help='Private unit JSON from configure_gateway.py')
    parser.add_argument('--ssid', help='Wi-Fi SSID; passphrase is read without echo')
    parser.add_argument('--generate', action='store_true', help='Invoke ESP-IDF nvs_partition_gen.py')
    parser.add_argument('--flash', action='store_true', help='Flash only the generated NVS partition')
    parser.add_argument('--port')
    parser.add_argument('--devkit-detached', action='store_true', help='Confirm DevKit removed from BOTH carrier sockets; USB is sole supply')
    args = parser.parse_args()
    if args.flash and (not args.port or not args.devkit_detached):
        parser.error('--flash requires --port and --devkit-detached; do not dual-power the carrier')
    cfg = private_json(args.device)
    unit = unit_id(cfg.get('unit'))
    ssid = args.ssid if args.ssid is not None else input('Wi-Fi SSID: ')
    password = getpass.getpass('WPA2 Wi-Fi passphrase (hidden): ')
    content = nvs_csv(unit, cfg.get('url'), cfg.get('token'), ssid, password)
    address, size = partition(ROOT/'firmware/partitions.csv')
    folder = ROOT/'factory/private'/unit
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = folder/'nvs.csv'; binary = folder/'nvs.bin'
    private_write(source, content)
    if args.generate or args.flash:
        idf = os.environ.get('IDF_PATH')
        if not idf:
            raise ValueError('Source ESP-IDF export.sh first; private CSV was created but nothing flashed')
        generator = Path(idf)/'components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'
        if not generator.is_file():
            raise ValueError('ESP-IDF NVS generator was not found')
        old_mask = os.umask(0o077)
        try:
            subprocess.run([sys.executable,str(generator),'generate',str(source),str(binary),hex(size)],check=True)
        finally:
            os.umask(old_mask)
        if binary.stat().st_size != size:
            raise ValueError('Generated NVS length does not match the partition table')
        os.chmod(binary,0o600)
        report = {'unit':unit,'nvs_offset':hex(address),'nvs_size':size,
                  'nvs_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
                  'production_secure_storage':False, 'flash_requested':args.flash}
        private_write(folder/'record.json',json.dumps(report,indent=2)+'\n')
        if args.flash:
            subprocess.run([sys.executable,'-m','esptool','--chip','esp32s3','--port',args.port,
                            'write_flash',hex(address),str(binary)],check=True)
    print(f'Private provisioning files: {folder.relative_to(ROOT)}')
    print('Treat CSV and BIN as credentials. No eFuses were changed. Provision production security separately.')

if __name__ == '__main__':
    try:
        main()
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Provisioning stopped: {exc}',file=sys.stderr)
        raise SystemExit(2)
