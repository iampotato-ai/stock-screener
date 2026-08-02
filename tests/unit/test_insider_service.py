"""
Unit tests for the Insider & Promoter Transactions tracking service.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from app.services.insider_service import (
    classify_transaction_mode,
    filter_meaningful_transactions,
    aggregate_insider_metrics,
    compute_insider_score,
    get_stock_insider_summary,
    get_batch_insider_summary,
)


class TestTransactionClassification:

    def test_market_purchase_classified_as_open_market_buy(self):
        mode = classify_transaction_mode("Market Purchase", "BUY")
        assert mode == "OPEN_MARKET_BUY"

    def test_market_sale_classified_as_open_market_sell(self):
        mode = classify_transaction_mode("Market Sale", "SELL")
        assert mode == "OPEN_MARKET_SELL"

    def test_esop_classified_as_neutral(self):
        mode = classify_transaction_mode("ESOP Allotment", "BUY")
        assert mode == "NEUTRAL"

    def test_gift_classified_as_neutral(self):
        mode = classify_transaction_mode("Inter-se Gift Transfer", "BUY")
        assert mode == "NEUTRAL"

    def test_pledge_classified_as_pledge(self):
        mode = classify_transaction_mode("Creation of Pledge", "PLEDGE")
        assert mode == "PLEDGE"

    def test_block_deal_classified_as_block_deal(self):
        mode = classify_transaction_mode("Block Deal", "BUY")
        assert mode == "BLOCK_DEAL"


class TestTransactionFiltering:

    def test_esops_and_gifts_filtered_out(self):
        txs = [
            {"mode": "OPEN_MARKET_BUY", "transaction_type": "BUY", "acq_mode": "Market Purchase", "value_cr": 10.0},
            {"mode": "NEUTRAL", "transaction_type": "BUY", "acq_mode": "ESOP Allotment", "value_cr": 2.0},
            {"mode": "NEUTRAL", "transaction_type": "BUY", "acq_mode": "Inter-se Gift", "value_cr": 5.0},
            {"mode": "OPEN_MARKET_SELL", "transaction_type": "SELL", "acq_mode": "Market Sale", "value_cr": 3.0},
        ]
        filtered = filter_meaningful_transactions(txs)
        assert len(filtered) == 2
        modes = [t["classified_mode"] for t in filtered]
        assert "OPEN_MARKET_BUY" in modes
        assert "OPEN_MARKET_SELL" in modes


class TestMetricAggregation:

    def test_30d_and_90d_net_promoter_buying(self):
        today = date.today()
        txs = [
            # 10 days ago: Buy ₹15 Cr by Promoter
            {"category": "Promoter", "classified_mode": "OPEN_MARKET_BUY", "value_cr": 15.0, "transaction_date": today - timedelta(days=10)},
            # 20 days ago: Sell ₹5 Cr by Promoter
            {"category": "Promoter", "classified_mode": "OPEN_MARKET_SELL", "value_cr": 5.0, "transaction_date": today - timedelta(days=20)},
            # 60 days ago: Buy ₹10 Cr by Promoter
            {"category": "Promoter", "classified_mode": "OPEN_MARKET_BUY", "value_cr": 10.0, "transaction_date": today - timedelta(days=60)},
        ]
        metrics = aggregate_insider_metrics(txs, ref_date=today)
        # 30d net = +15 - 5 = 10.0
        assert metrics["net_promoter_buy_30d"] == 10.0
        # 90d net = +15 - 5 + 10 = 20.0
        assert metrics["net_promoter_buy_90d"] == 20.0

    def test_bulk_deal_counting(self):
        today = date.today()
        txs = [
            {"category": "Institutional", "classified_mode": "BLOCK_DEAL", "value_cr": 12.0, "transaction_date": today - timedelta(days=5)},
            {"category": "Promoter", "classified_mode": "OPEN_MARKET_BUY", "value_cr": 8.0, "transaction_date": today - timedelta(days=15)},
        ]
        metrics = aggregate_insider_metrics(txs, ref_date=today)
        assert metrics["bulk_deal_count_30d"] == 2


class TestScoreAndBadges:

    def test_promoter_buy_badge_and_score(self):
        metrics = {
            "net_promoter_buy_30d": 12.0,
            "net_promoter_buy_90d": 20.0,
            "bulk_deal_net_val_30d": 0.0,
            "promoter_pledged_pct": 0.0,
            "pledge_change_pct": 0.0,
        }
        res = compute_insider_score(metrics)
        assert res["insider_score"] >= 75.0
        assert "🔥 PROMOTER BUY" in res["badges"]

    def test_promoter_sell_badge_and_score(self):
        metrics = {
            "net_promoter_buy_30d": -15.0,
            "net_promoter_buy_90d": -20.0,
            "bulk_deal_net_val_30d": 0.0,
            "promoter_pledged_pct": 0.0,
            "pledge_change_pct": 0.0,
        }
        res = compute_insider_score(metrics)
        assert res["insider_score"] <= 25.0
        assert "⚠️ PROMOTER SELL" in res["badges"]

    def test_pledge_risk_badge(self):
        metrics = {
            "net_promoter_buy_30d": 0.0,
            "net_promoter_buy_90d": 0.0,
            "bulk_deal_net_val_30d": 0.0,
            "promoter_pledged_pct": 20.0,
            "pledge_change_pct": 6.0,
        }
        res = compute_insider_score(metrics)
        assert "🚨 PLEDGE RISK" in res["badges"]


class TestOrchestrators:

    @patch("app.services.insider_service._fetch_disclosures_from_db")
    def test_get_stock_insider_summary(self, mock_fetch):
        today = date.today()
        mock_fetch.return_value = [
            {
                "symbol": "RELIANCE",
                "insider_name": "Promoter Trust",
                "category": "Promoter",
                "transaction_type": "BUY",
                "mode": "OPEN_MARKET_BUY",
                "acq_mode": "Market Purchase",
                "num_shares": 100000,
                "price": 1250.0,
                "value_cr": 12.5,
                "transaction_date": str(today - timedelta(days=5)),
            }
        ]
        summary = get_stock_insider_summary("RELIANCE")
        assert summary["success"] is True
        assert summary["symbol"] == "RELIANCE"
        assert summary["insider_score"] >= 65.0
        assert "🔥 PROMOTER BUY" in summary["badges"]
        assert len(summary["recent_transactions"]) == 1

    @patch("app.services.insider_service.get_stock_insider_summary")
    def test_get_batch_insider_summary(self, mock_summary):
        mock_summary.return_value = {
            "symbol": "INFY",
            "insider_score": 70.0,
            "badges": ["🔥 PROMOTER BUY"],
            "metrics": {
                "net_promoter_buy_30d": 5.0,
                "net_promoter_buy_90d": 10.0,
                "bulk_deal_count_30d": 1,
            },
        }
        batch = get_batch_insider_summary(["INFY"])
        assert "INFY" in batch
        assert batch["INFY"]["insider_score"] == 70.0
        assert batch["INFY"]["net_promoter_buy_30d"] == 5.0
