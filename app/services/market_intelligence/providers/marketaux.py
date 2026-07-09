import urllib.request
import urllib.parse
import json
import logging
import datetime
import os
from typing import List
from flask import current_app, has_app_context
from .base import BaseDataProvider
from ..schemas.normalized_event import NormalizedArticle

logger = logging.getLogger(__name__)


class MarketauxProvider(BaseDataProvider):
    """Data provider for fetching financial news articles from Marketaux API."""

    @property
    def name(self) -> str:
        return "Marketaux"

    def fetch(self, symbol: str) -> List[NormalizedArticle]:
        """Fetch news from Marketaux for the given stock symbol."""
        # Strip NSE prefix
        clean_symbol = symbol.split(':')[-1].upper() if ':' in symbol else symbol.upper()
        marketaux_symbol = f"{clean_symbol}.NS"
        
        # Load API token
        if has_app_context():
            api_token = current_app.config.get('MARKETAUX_API_TOKEN')
        else:
            api_token = os.environ.get('MARKETAUX_API_TOKEN')
            
        if not api_token:
            logger.warning("Marketaux API token not configured. Skipping fetch.")
            return []

        # Marketaux endpoint
        base_url = "https://api.marketaux.com/v1/news/all"
        query_params = {
            "symbols": marketaux_symbol,
            "filter_entities": "true",
            "api_token": api_token,
            "language": "en"
        }
        url = f"{base_url}?{urllib.parse.urlencode(query_params)}"
        
        articles = []
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                raw_data = json.loads(response.read().decode('utf-8'))
                
            data = raw_data.get('data', [])
            for item in data:
                # Parse published_at
                pub_str = item.get('published_at', '')
                dt = datetime.datetime.now(datetime.timezone.utc)
                if pub_str:
                    try:
                        # Format is '2026-07-07T14:30:00.000000Z'
                        iso_str = pub_str.replace('Z', '+00:00')
                        dt = datetime.datetime.fromisoformat(iso_str)
                    except Exception as parse_err:
                        logger.debug(f"Failed to parse published date {pub_str}: {parse_err}")

                articles.append(NormalizedArticle(
                    symbol=clean_symbol,
                    title=item.get('title', ''),
                    url=item.get('url', ''),
                    summary=item.get('description') or item.get('snippet') or '',
                    source=item.get('source', 'marketaux.com'),
                    external_id=item.get('uuid'),
                    published_at=dt
                ))
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP Error fetching from Marketaux: Code={e.code}, Reason={e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error fetching from Marketaux for symbol {clean_symbol}: {e}")
            raise
            
        return articles
