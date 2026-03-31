from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from cmm.utils.http import build_async_client


async def download_file(uri: str, output_dir: str, timeout: float = 30.0, max_retries: int = 1) -> str:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(uri)
    filename = Path(parsed.path).name or "download.bin"
    output_path = target_dir / filename
    if uri.startswith("http://") or uri.startswith("https://"):
        attempt = 0
        last_error = None
        while attempt <= max_retries:
            temp_path = output_path.with_suffix(output_path.suffix + ".part")
            try:
                async with build_async_client(timeout=timeout) as client:
                    async with client.stream("GET", uri) as response:
                        response.raise_for_status()
                        with temp_path.open("wb") as fh:
                            async for chunk in response.aiter_bytes():
                                if chunk:
                                    fh.write(chunk)
                temp_path.replace(output_path)
                return str(output_path)
            except Exception as exc:
                last_error = exc
                if temp_path.exists():
                    temp_path.unlink()
                attempt += 1
        raise RuntimeError("download failed for {0}: {1}".format(uri, last_error))
    else:
        source = Path(uri)
        if source.exists():
            output_path.write_bytes(source.read_bytes())
        else:
            output_path.write_text(uri, encoding="utf-8")
    return str(output_path)
