"""QR code artifact helpers for ChatPost."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

QR_CODE_MIME = "image/png"


def generate_qr_code_image(
    data: str,
    destination: Path,
    *,
    box_size: int = 10,
    border: int = 4,
) -> dict[str, Any]:
    """Render *data* as a QR code PNG artifact without echoing the payload.

    The returned payload intentionally records the data length, not the QR payload
    itself. Callers that are deliberately handing a clickable URL to a user can add
    that URL in their own short-lived result object.
    """

    if not isinstance(data, str) or not data:
        raise ValueError("QR code data must be a non-empty string")
    if box_size < 1:
        raise ValueError("QR code box_size must be positive")
    if border < 0:
        raise ValueError("QR code border must be non-negative")
    try:
        import qrcode
    except ImportError as error:  # pragma: no cover - dependency metadata guard
        raise RuntimeError("qrcode[pil] dependency is required to render QR artifacts") from error

    output = destination.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    with tempfile.NamedTemporaryFile(
        "wb",
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        image.save(stream, format="PNG")
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
        os.chmod(output, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "artifact_path": str(output),
        "artifact_mime": QR_CODE_MIME,
        "data_length": len(data),
    }


__all__ = ["QR_CODE_MIME", "generate_qr_code_image"]
