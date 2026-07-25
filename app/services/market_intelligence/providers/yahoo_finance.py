import logging
import datetime
import hashlib
import re
from typing import List
from .base import BaseDataProvider
from ..schemas.normalized_event import NormalizedArticle

logger = logging.getLogger(__name__)


class YahooFinanceProvider(BaseDataProvider):
    """Data provider for fetching news articles from Yahoo Finance API."""

    @property
    def name(self) -> str:
        return "YahooFinance"

    def fetch(self, symbol: str) -> List[NormalizedArticle]:
        """Fetch news from Yahoo Finance for the given symbol."""
        # Strip exchange prefix if present (e.g. NSE:RELIANCE -> RELIANCE)
        clean_symbol = symbol.split(':')[-1].upper() if ':' in symbol else symbol.upper()
        # Query Yahoo Finance using the Indian NSE suffix (.NS)
        ticker_symbol = f"{clean_symbol}.NS"

        articles = []
        try:
            import yfinance as yf
            ticker = yf.Ticker(ticker_symbol)
            raw_news = ticker.news
            
            if not raw_news:
                # Try fallback to BSE suffix (.BO) if NSE suffix returned nothing
                logger.info(f"No news for {ticker_symbol}, trying {clean_symbol}.BO")
                ticker_symbol = f"{clean_symbol}.BO"
                ticker = yf.Ticker(ticker_symbol)
                raw_news = ticker.news

            if not raw_news:
                return []

            now_utc = datetime.datetime.now(datetime.timezone.utc)

            for item in raw_news:
                # 1. Related Tickers Check
                related_tickers = item.get("relatedTickers", [])
                has_indian_suffix = False
                has_matching_symbol = False

                for t in related_tickers:
                    t_upper = t.upper()
                    if t_upper.endswith(".NS") or t_upper.endswith(".BO"):
                        has_indian_suffix = True
                    if t_upper.split('.')[0] == clean_symbol:
                        has_matching_symbol = True

                # 2. Title / Summary Regex Check
                title = item.get("title", "")
                summary = item.get("summary", "") or title
                
                # Check for symbol as a whole word in title or summary (case-insensitive)
                pattern = r"\b" + re.escape(clean_symbol) + r"\b"
                matches_regex = bool(re.search(pattern, title, re.IGNORECASE)) or bool(re.search(pattern, summary, re.IGNORECASE))

                # Check validation to ensure relevance to the Indian stock ticker
                if not (matches_regex or (has_matching_symbol and has_indian_suffix)):
                    logger.debug(f"Filtered out unrelated Yahoo Finance article: {title} (tickers: {related_tickers})")
                    continue

                # Parse published time (providerPublishTime is epoch timestamp in seconds)
                pub_time_epoch = item.get("providerPublishTime")
                if pub_time_epoch:
                    dt = datetime.datetime.fromtimestamp(pub_time_epoch, tz=datetime.timezone.utc)
                else:
                    dt = now_utc

                # Filter older than 30 days
                if (now_utc - dt).days > 30:
                    continue

                link = item.get("link", "")
                source = item.get("publisher", "Yahoo Finance")
                uuid = item.get("uuid")
                if not uuid and link:
                    uuid = hashlib.sha256(link.encode('utf-8')).hexdigest()[:16]
                
                articles.append(NormalizedArticle(
                    symbol=clean_symbol,
                    title=title,
                    url=link,
                    summary=summary,
                    source=source,
                    external_id=f"yfinance-{uuid}" if uuid else None,
                    published_at=dt
                ))

                if len(articles) >= 8:
                    break

        except Exception as e:
            logger.error(f"Error fetching from Yahoo Finance for symbol {clean_symbol}: {e}")
            raise

        return articles
