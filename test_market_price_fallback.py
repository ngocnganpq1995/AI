import unittest
from unittest.mock import Mock, patch

import requests

from market_prices import PriceUnavailable, fetch_prices


class MarketPriceFallbackTests(unittest.TestCase):
    @patch("market_prices.requests.get")
    def test_vea_uses_simplize_when_yahoo_has_no_symbol(self, price_get):
        yahoo = Mock()
        yahoo.raise_for_status.side_effect = requests.HTTPError("404")
        simplize = Mock()
        simplize.json.return_value = {"status": 200, "data": [
            ["1790208000", 37000, 37100, 36900, 37000, 100000],
            ["1790294400", 36800, 37000, 36800, 36800, 202300],
        ]}
        price_get.side_effect = [yahoo, simplize]

        prices, meta = fetch_prices("VEA", "3mo")

        self.assertEqual(meta["source"], "Simplize")
        self.assertEqual(meta["currency"], "VND")
        self.assertEqual(prices.close.tolist(), [37000, 36800])
        self.assertEqual(prices.date.iloc[-1].strftime("%Y-%m-%d"), "2026-09-25")
        self.assertEqual(price_get.call_args.kwargs["params"], {"ticker": "VEA"})

    @patch("market_prices.requests.post")
    @patch("market_prices.requests.get")
    def test_vea_uses_vietcap_when_other_sources_fail(self, yahoo_get, vietcap_post):
        yahoo_get.return_value.raise_for_status.side_effect = requests.HTTPError("404")
        vietcap_post.return_value.json.return_value = [{
            "symbol": "VEA",
            "t": ["1790208000", "1790294400"],
            "c": [37000, 36800],
            "v": [100000, 202300],
        }]

        prices, meta = fetch_prices("VEA", "3mo")

        self.assertEqual(meta["source"], "Vietcap")
        self.assertEqual(meta["currency"], "VND")
        self.assertEqual(prices.close.tolist(), [37000, 36800])
        self.assertEqual(prices.volume.tolist(), [100000, 202300])
        self.assertEqual(prices.date.iloc[-1].strftime("%Y-%m-%d"), "2026-09-25")
        self.assertEqual(vietcap_post.call_args.kwargs["json"]["symbols"], ["VEA"])

    @patch("market_prices.requests.post")
    @patch("market_prices.requests.get")
    def test_wrong_symbol_is_not_plotted(self, yahoo_get, vietcap_post):
        yahoo_get.return_value.raise_for_status.side_effect = requests.HTTPError("404")
        vietcap_post.return_value.json.return_value = [{
            "symbol": "VEEA", "t": ["1790208000", "1790294400"],
            "c": [3, 4], "v": [100, 200],
        }]

        with self.assertRaises(PriceUnavailable):
            fetch_prices("VEA", "3mo")


if __name__ == "__main__":
    unittest.main()
