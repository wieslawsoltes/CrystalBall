import csv
import io
import os
import pytest
from factory.common import origin, wifi, token, unit_id, private_write, private_json
from factory.configure_gateway import configure
from factory.provision import nvs_csv, partition

@pytest.mark.parametrize('value', ['http://orb.local','https://','https://x/y','https://x?','https://u:p@x','https://x#frag','https://x\\y','https://x:0','https://x:65536','https://x\n','https://-bad.local','https://a..b'])
def test_reject_bad_origin(value):
    with pytest.raises(ValueError):origin(value)

@pytest.mark.parametrize('value,expected',[('https://orb-gateway.home.arpa/','https://orb-gateway.home.arpa'),('https://[::1]:8443','https://[::1]:8443'),('https://127.0.0.1','https://127.0.0.1')])
def test_origin(value,expected):assert origin(value)==expected

def test_utf8_ssid_bytes_and_wpa2():
    assert wifi('ą'*16, 'passphrase')[0]=='ą'*16
    for ssid,password in [('ą'*17,'passphrase'),('x','short'),('x','x'*64),('x','a\0bcdefg')]:
        with pytest.raises(ValueError):wifi(ssid,password)
    assert wifi('x','a'*64)[1]=='a'*64

def test_private_exclusive(tmp_path):
    p=tmp_path/'secret.json';private_write(p,'{}')
    assert private_json(p)=={}
    with pytest.raises(FileExistsError):private_write(p,'overwritten')
    assert p.read_text()=='{}'
    if os.name!='nt':
        assert p.stat().st_mode&0o777==0o600
        p.chmod(0o644)
        with pytest.raises(ValueError):private_json(p)

def test_no_final_symlink(tmp_path):
    target=tmp_path/'target';target.write_text('original')
    link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(FileExistsError):private_write(link,'new')
    assert target.read_text()=='original'

def test_credentials_not_in_gateway_digest(tmp_path):
    env,device=configure('orb-test','https://orb.local','sk-test-placeholder-not-a-real-key',root=tmp_path)
    cfg=private_json(device)
    assert cfg['token'] not in env.read_text()
    assert 'sk-test' not in device.read_text()
    assert "PUBLIC_TTS='false'" in env.read_text()
    assert "REALTIME_ENABLED='false'" in env.read_text()
    with pytest.raises(FileExistsError):configure('other','https://orb.local','sk-test-placeholder-not-a-real-key',root=tmp_path)
    assert not (tmp_path/'factory/private/other.json').exists()

def test_csv_quoting_and_no_secret_on_record(tmp_path):
    result=nvs_csv('orb1','https://orb.local/','x'*64,'network, "quoted"','phrase,"quoted"')
    rows=list(csv.reader(io.StringIO(result)))
    assert rows[5][-1]=='network, "quoted"'
    assert rows[6][-1]=='phrase,"quoted"'
    assert rows[3][-1]=='https://orb.local'

def test_partition_source_of_truth(tmp_path):
    p=tmp_path/'part.csv';p.write_text('# heading\nnvs,data,nvs,0x9000,24K,\n')
    assert partition(p)==(0x9000,0x6000)
    p.write_text('nvs,data,nvs,,24K,\n')
    with pytest.raises(ValueError):partition(p)

@pytest.mark.parametrize('value',['','a/b','é','x'*33,None])
def test_invalid_unit(value):
    with pytest.raises(ValueError):unit_id(value)

@pytest.mark.parametrize('value',['short','x'*129,'x'*32+'\n',None])
def test_invalid_token(value):
    with pytest.raises(ValueError):token(value)
