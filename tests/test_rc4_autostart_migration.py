from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[1] / "payload"


def test_installer_removes_only_legacy_direct_flex_autostart():
    source = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")
    assert 'LEGACY_FLEX_AUTOSTART_PATH="${AUTOSTART_DIR}/openhtpc-flex.desktop"' in source
    assert 'grep -Fq "openhtpc-session-start" "$LEGACY_FLEX_AUTOSTART_PATH"' in source
    assert 'rm -f -- "$LEGACY_FLEX_AUTOSTART_PATH"' in source


def test_canonical_autostart_still_uses_openhtpc_start():
    source = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")
    assert 'AUTOSTART_PATH="${AUTOSTART_DIR}/openhtpc.desktop"' in source
    assert 'Exec=${OPENHTPC_COMMAND_PATH} start' in source
