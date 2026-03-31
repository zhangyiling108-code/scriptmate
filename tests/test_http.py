from cmm.utils.http import build_async_client


def test_build_async_client_respects_env_proxies():
    client = build_async_client()
    try:
        assert client._trust_env is True
    finally:
        __import__("asyncio").run(client.aclose())
