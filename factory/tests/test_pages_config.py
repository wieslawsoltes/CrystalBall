"""Public frontend pairing is explicit; it never changes gateway authentication."""
import json
import pytest
from factory.configure_gateway import configure

KEY = 'sk-' + 'SYNTHETIC-NOT-A-PROJECT-KEY'


def test_pages_origin_is_normalized_without_repository_path(tmp_path):
    env, device = configure('UNIT', 'https://orb-gateway.home.arpa', KEY,
        browser_origins=('https://WIESLAWSOLTES.github.io:443/', 'https://wieslawsoltes.github.io'), root=tmp_path)
    assert "CORS_ORIGINS='https://wieslawsoltes.github.io'" in env.read_text()
    assert KEY not in device.read_text()
    assert 'CORS_ORIGINS' not in json.loads(device.read_text())


@pytest.mark.parametrize('value', ['*', 'https://wieslawsoltes.github.io/CrystalBall/', 'http://public.example',
    'https://user:password@public.example', 'https://public.example\n', 'https://public.example?secret=x'])
def test_invalid_browser_origin_does_not_create_credentials(tmp_path, value):
    with pytest.raises(ValueError):
        configure('UNIT', 'https://orb-gateway.home.arpa', KEY, browser_origins=(value,), root=tmp_path)
    assert not (tmp_path / 'gateway/.env').exists()
    assert not (tmp_path / 'factory/private/UNIT.json').exists()


def test_frontend_cors_is_disabled_without_explicit_opt_in(tmp_path):
    env, _ = configure('UNIT', 'https://orb-gateway.home.arpa', KEY, root=tmp_path)
    assert "CORS_ORIGINS=''" in env.read_text()
