from pathlib import Path

import pytest

from chatpost.qr import QR_CODE_MIME, generate_qr_code_image


def test_generate_qr_code_image_writes_png_with_restrictive_permissions(tmp_path: Path):
    artifact = tmp_path / "qr.png"

    payload = generate_qr_code_image("https://example.com/login", artifact)

    assert payload == {
        "artifact_path": str(artifact.resolve()),
        "artifact_mime": QR_CODE_MIME,
        "data_length": len("https://example.com/login"),
    }
    assert artifact.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert artifact.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("data", ["", None])
def test_generate_qr_code_image_rejects_empty_data(tmp_path: Path, data):
    with pytest.raises(ValueError, match="non-empty"):
        generate_qr_code_image(data, tmp_path / "qr.png")
