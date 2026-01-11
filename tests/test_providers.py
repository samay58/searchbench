import os
import unittest
from unittest.mock import patch

import httpx

from searchbench.providers.exa import ExaProvider
from searchbench.providers.parallel import ParallelProvider


class TestProviders(unittest.IsolatedAsyncioTestCase):
    async def test_exa_timeout_sets_timed_out(self):
        provider = ExaProvider(api_key="test-key", endpoint="https://example.com")

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                raise httpx.TimeoutException("timeout")

        with patch("searchbench.providers.exa.httpx.AsyncClient", return_value=FakeClient()):
            result = await provider.search("test query", timeout=1)
            self.assertTrue(result.timed_out)
            self.assertEqual(result.error, "timeout")

    async def test_parallel_http_error_surfaces(self):
        provider = ParallelProvider(api_key="test-key", endpoint="https://example.com")

        request = httpx.Request("POST", "https://example.com")
        response = httpx.Response(400, request=request, text="bad request")

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                raise httpx.HTTPStatusError("error", request=request, response=response)

        with patch("searchbench.providers.parallel.httpx.AsyncClient", return_value=FakeClient()):
            result = await provider.search("test query", timeout=1)
            self.assertFalse(result.timed_out)
            self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main()
