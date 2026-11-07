"""Connectivity regression checks, without pairing or account credentials."""

import importlib.util
import sys
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch


api = types.ModuleType("musegadget.muse_api")
api.API_BASE = "https://api.muse.ai"
sys.modules["musegadget"] = types.ModuleType("musegadget")
sys.modules["musegadget.muse_api"] = api
spec = importlib.util.spec_from_file_location("muse_network", Path(__file__).resolve().parents[1] / "sdk" / "muse-network.py")
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


class NetworkChecks(unittest.TestCase):
    def test_proxy_route_reaches_origin_without_sending_credentials(self):
        response = MagicMock()
        response.__enter__.return_value.status = 204
        with patch.object(network.urllib.request, "getproxies", return_value={"https": "http://127.0.0.1:7890"}), \
             patch.object(network.urllib.request, "proxy_bypass", return_value=False), \
             patch.object(network.urllib.request, "urlopen", return_value=response) as open_url, \
             patch.object(network.socket, "create_connection") as direct:
            self.assertTrue(network.is_online())
        direct.assert_not_called()
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, api.API_BASE)
        self.assertEqual(request.get_method(), "HEAD")
        self.assertIsNone(request.data)
        self.assertFalse(request.has_header("Authorization"))
        self.assertLessEqual(open_url.call_args.kwargs["timeout"], 3)

    def test_origin_responses_and_proxy_failures_are_distinct(self):
        for status, expected in [(401, True), (404, True), (407, False), (502, False), (503, False)]:
            with self.subTest(status=status), \
                 patch.object(network.urllib.request, "getproxies", return_value={"https": "http://127.0.0.1:7890"}), \
                 patch.object(network.urllib.request, "proxy_bypass", return_value=False), \
                 patch.object(network.urllib.request, "urlopen", side_effect=urllib.error.HTTPError(api.API_BASE, status, "test", {}, None)), \
                 patch.object(network.socket, "create_connection") as direct:
                self.assertEqual(network.is_online(), expected)
                direct.assert_not_called()

    def test_proxy_transport_failures_do_not_fall_back_to_direct_tcp(self):
        for failure in [urllib.error.URLError("unreachable"), TimeoutError(), ValueError("invalid proxy")]:
            with self.subTest(failure=type(failure).__name__), \
                 patch.object(network.urllib.request, "getproxies", return_value={"https": "http://127.0.0.1:7890"}), \
                 patch.object(network.urllib.request, "proxy_bypass", return_value=False), \
                 patch.object(network.urllib.request, "urlopen", side_effect=failure), \
                 patch.object(network.socket, "create_connection") as direct:
                self.assertFalse(network.is_online())
                direct.assert_not_called()

    def test_no_proxy_and_explicit_proxy_bypass_keep_original_direct_route(self):
        for proxies, bypass in [({}, False), ({"https": "http://127.0.0.1:7890"}, True)]:
            with self.subTest(proxies=bool(proxies), bypass=bypass), \
                 patch.object(network.urllib.request, "getproxies", return_value=proxies), \
                 patch.object(network.urllib.request, "proxy_bypass", return_value=bypass), \
                 patch.object(network.urllib.request, "urlopen") as open_url, \
                 patch.object(network.socket, "create_connection", return_value=MagicMock()) as direct:
                self.assertTrue(network.is_online(timeout=1.5))
                direct.assert_called_once_with(("api.muse.ai", 443), timeout=1.5)
                open_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
