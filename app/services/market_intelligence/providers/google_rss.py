import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import datetime
import os
import logging
import hashlib
from typing import List
from email.utils import parsedate_to_datetime
from flask import current_app, has_app_context
from .base import BaseDataProvider
from ..schemas.normalized_event import NormalizedArticle

logger = logging.getLogger(__name__)

_DEFAULT_GOOGLE_NEWS_URL = 'https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en'


class GoogleRSSProvider(BaseDataProvider):
    """Fallback news provider using Google News RSS feeds."""

    @property
    def name(self) -> str:
        return "GoogleRSS"

    def fetch(self, symbol: str) -> List[NormalizedArticle]:
        """Fetch news from Google News RSS feed for the given symbol."""
        clean_symbol = symbol.split(':')[-1].upper() if ':' in symbol else symbol.upper()
        
        query = urllib.parse.quote(f"{clean_symbol} NSE India OR {clean_symbol} stock")
        if has_app_context():
            google_news_url = current_app.config.get('GOOGLE_NEWS_URL', _DEFAULT_GOOGLE_NEWS_URL)
        else:
            google_news_url = os.environ.get('GOOGLE_NEWS_URL', _DEFAULT_GOOGLE_NEWS_URL)
            
        url = google_news_url.format(query=query)
        
        articles = []
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            channel = root.find('channel')
            if channel:
                items = channel.findall('item')
                now_utc = datetime.datetime.now(datetime.timezone.utc)

                for item in items:
                    pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
                    dt = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

                    if pub_date:
                        try:
                            dt = parsedate_to_datetime(pub_date)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=datetime.timezone.utc)
                            # Exclude older than 30 days
                            if (now_utc - dt).days > 30:
                                continue
                        except Exception:
                            pass

                    title = item.find('title').text if item.find('title') is not None else ''
                    link = item.find('link').text if item.find('link') is not None else ''
                    source = item.find('source').text if item.find('source') is not None else 'Google News'

                    # Generate an external_id based on link hash
                    link_hash = hashlib.sha256(link.encode('utf-8')).hexdigest()[:16]

                    articles.append(NormalizedArticle(
                        symbol=clean_symbol,
                        title=title,
                        url=link,
                        summary=title,
                        source=source,
                        external_id=f"googlerss-{link_hash}",
                        published_at=dt
                    ))
                    
                    if len(articles) >= 8:
                        break
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP Error fetching from Google RSS: Code={e.code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching from Google RSS for {clean_symbol}: {e}")
            raise
            
        return articles
