"""
Tiffany OS — Test Suite for Intelligent Deal Validation Engine (P0.8)
=====================================================================
Validates real vs fake discount detection ("metade do dobro"), price inflation checks,
and reference market price calculations.
"""

import unittest
from tiffany_core.deal_validator import (
    validate_deal,
    DealVerdictCode,
    match_hardware_reference,
)

class TestDealValidator(unittest.TestCase):

    def test_rtx_4060ti_fake_discount_user_scenario(self):
        """
        User scenario: Store lists an RTX 4060 Ti / 5060 Ti at R$ 3.700 claiming 70% OFF 
        (from a fake R$ 12.300 original price).
        Expected: REJECTED as FAKE_DISCOUNT / METADE_DO_DOBRO because R$ 3.700 exceeds 
        the market baseline (~R$ 2.700).
        """
        deal = {
            "title": "Placa de Vídeo RTX 4060 Ti 8GB GDDR6 Dual Fan",
            "price": 3700.0,
            "original_price": 12300.0,
            "discount_pct": 70.0,
            "store": "Loja Exemplo",
            "category": "Placa de Vídeo",
        }
        
        res = validate_deal(deal)
        
        self.assertFalse(res.is_valid_deal)
        self.assertIn(res.verdict_code, (DealVerdictCode.FAKE_DISCOUNT, DealVerdictCode.METADE_DO_DOBRO))
        self.assertIn("Falso desconto", res.rejection_reason)
        self.assertEqual(res.expected_market_price, 2700.0)
        self.assertTrue("3700" in res.rejection_reason or "acima" in res.rejection_reason)

    def test_rtx_4060ti_real_ultra_deal(self):
        """
        Real deal scenario: RTX 4060 Ti listed at R$ 2.250 (below target deal price R$ 2.300).
        Expected: APPROVED as ULTRA_DEAL ("OPORTUNIDADE IMPERDÍVEL").
        """
        deal = {
            "title": "Placa de Vídeo RTX 4060 Ti 8GB Dual Fan Black",
            "price": 2250.0,
            "original_price": 2800.0,
            "discount_pct": 19.6,
            "store": "Terabyte",
            "category": "Placa de Vídeo",
        }

        res = validate_deal(deal)

        self.assertTrue(res.is_valid_deal)
        self.assertEqual(res.verdict_code, DealVerdictCode.ULTRA_DEAL)
        self.assertIn("IMPERDÍVEL", res.verdict_badge)
        self.assertGreater(res.real_discount_pct, 15.0)

    def test_ryzen_5_5600_real_deal(self):
        """
        Real deal scenario: Ryzen 5 5600 listed at R$ 620.
        Expected: APPROVED as ULTRA_DEAL / REAL_DEAL.
        """
        deal = {
            "title": "Processador AMD Ryzen 5 5600 3.5GHz (4.4GHz Turbo)",
            "price": 620.0,
            "original_price": 950.0,
            "discount_pct": 34.7,
            "store": "KaBuM!",
            "category": "Processador",
        }

        res = validate_deal(deal)

        self.assertTrue(res.is_valid_deal)
        self.assertIn(res.verdict_code, (DealVerdictCode.ULTRA_DEAL, DealVerdictCode.REAL_DEAL))
        self.assertEqual(res.matched_model, "AMD Ryzen 5 5600")
        self.assertEqual(res.expected_market_price, 850.0)

    def test_ssd_1tb_inflated_was_price(self):
        """
        Inflated original price scenario: 1TB NVMe SSD listed at R$ 1.200 claiming 'de R$ 6.000 por R$ 1.200' (80% OFF).
        Expected: REJECTED because R$ 1.200 is overpriced for a 1TB SSD (baseline R$ 450).
        """
        deal = {
            "title": "SSD 1TB NVMe M.2 3500MB/s",
            "price": 1200.0,
            "original_price": 6000.0,
            "discount_pct": 80.0,
            "store": "Amazon",
            "category": "SSD",
        }

        res = validate_deal(deal)

        self.assertFalse(res.is_valid_deal)
        self.assertIn(res.verdict_code, (DealVerdictCode.FAKE_DISCOUNT, DealVerdictCode.METADE_DO_DOBRO))

    def test_ps5_pro_great_deal(self):
        """
        PlayStation 5 Pro listed at R$ 5.500 (baseline R$ 6.500).
        Expected: APPROVED as ULTRA_DEAL.
        """
        deal = {
            "title": "Console PlayStation 5 Pro 2TB",
            "price": 5500.0,
            "original_price": 6990.0,
            "store": "Amazon",
            "category": "Console",
        }

        res = validate_deal(deal)

        self.assertTrue(res.is_valid_deal)
        self.assertEqual(res.matched_model, "PlayStation 5 Pro")
        self.assertGreaterEqual(res.real_discount_pct, 15.0)

    def test_generic_product_metade_do_dobro_heuristic(self):
        """
        Generic unindexed product claiming 70% OFF from an absurdly inflated original price ('De 10.000 por 1.000').
        Expected: REJECTED by heuristic price inflation check.
        """
        deal = {
            "title": "Cadeira Gamer Ultra Desconhecida",
            "price": 1000.0,
            "original_price": 10000.0,
            "discount_pct": 90.0,
            "store": "Shopee",
            "category": "Cadeira",
        }

        res = validate_deal(deal)

        self.assertFalse(res.is_valid_deal)
        self.assertEqual(res.verdict_code, DealVerdictCode.FAKE_DISCOUNT)


if __name__ == "__main__":
    unittest.main()
