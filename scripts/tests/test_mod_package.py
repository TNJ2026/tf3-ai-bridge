import hashlib
from pathlib import Path
import zipfile

import pytest
from build_mod_package import build_package, RELEASE_FILES, SCRIPT
from check_mod_package import check_package

SOURCE = Path(__file__).resolve().parents[2] / 'mod/tf3_mcp_bridge'


def test_clean_enabled_reproducible_release(tmp_path):
    before = (SOURCE / SCRIPT).read_bytes()
    first = build_package(SOURCE, tmp_path / 'first')
    second = build_package(SOURCE, tmp_path / 'second')
    assert first['generation'] == second['generation']
    assert first['archiveSha256'] == second['archiveSha256']
    assert (SOURCE / SCRIPT).read_bytes() == before
    with zipfile.ZipFile(first['archive']) as archive:
        assert set(archive.namelist()) == set(RELEASE_FILES)
        text = archive.read(SCRIPT).decode()
        assert 'local HEADLESS_USERDATA = true' in text
        assert 'local HEADLESS_ON_DEMAND = true' in text
        assert f'local HEADLESS_GENERATION = "{first["generation"]}"' in text
        assert all(hashlib.sha256(archive.read(n)).hexdigest() == h for n, h in first['files'].items())
    with pytest.raises(FileExistsError):
        build_package(SOURCE, tmp_path / 'first')


def test_disabled_source_is_not_publishable_receiver():
    result = check_package(SOURCE, require_receiver=True)
    assert not result['passed']
    assert any('generation' in p for p in result['problems'])


def test_release_checker_rejects_runtime_files(tmp_path):
    release = build_package(SOURCE, tmp_path / 'release')
    root = Path(release['modRoot'])
    (root / 'content/tf3_mcp_bridge/ingress_probe.lua').write_text('return {}')
    result = check_package(root, require_receiver=True)
    assert not result['passed']
    assert any('Diagnostic' in p for p in result['problems'])
