from pathlib import Path

import pytest

from cmm.fetcher.downloader import download_file


class _FakeResponse:
    def __init__(self, chunks=None, error=None):
        self._chunks = chunks or []
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, uri):
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_download_file_streams_remote_content(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cmm.fetcher.downloader.build_async_client",
        lambda timeout=30.0: _FakeClient([_FakeResponse([b"hello ", b"world"])]),
    )

    path = await download_file("https://example.com/test.bin", str(tmp_path))

    assert Path(path).read_bytes() == b"hello world"


@pytest.mark.asyncio
async def test_download_file_retries_and_raises_clean_error(tmp_path, monkeypatch):
    client = _FakeClient([
        _FakeResponse(error=RuntimeError("boom-1")),
        _FakeResponse(error=RuntimeError("boom-2")),
    ])
    monkeypatch.setattr("cmm.fetcher.downloader.build_async_client", lambda timeout=30.0: client)

    with pytest.raises(RuntimeError, match="download failed"):
        await download_file("https://example.com/test.bin", str(tmp_path), max_retries=1)

    assert not list(tmp_path.glob("*.part"))
