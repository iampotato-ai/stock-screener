"""
News service for managing news fetching and caching.
"""
import time
import urllib.parse
import xml.etree.ElementTree as ET
import urllib.request
import os
from typing import List, Dict, Any, Optional
from email.utils import parsedate_to_datetime
import datetime
from flask import current_app, has_app_context


class NewsService:
    """Service for news-related operations."""

    def __init__(self):
        # In-memory cache for news data
        self.NEWS_CACHE = {}
        self.NEWS_CACHE_TIMEOUT = 900  # 15 minutes

    def fetch_google_news(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Fetch news for a given ticker from Google News.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of news dictionaries
        """
        now = time.time()
        if ticker in self.NEWS_CACHE:
            if now - self.NEWS_CACHE[ticker]["timestamp"] < self.NEWS_CACHE_TIMEOUT:
                return self.NEWS_CACHE[ticker]["data"]

        query = urllib.parse.quote(f"{ticker} NSE India OR {ticker} stock")
        # Get Google News URL from Flask config or fall back to env/default
        _DEFAULT_GOOGLE_URL = 'https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en'
        if has_app_context():
            google_news_url = current_app.config.get('GOOGLE_NEWS_URL', _DEFAULT_GOOGLE_URL)
        else:
            google_news_url = os.environ.get('GOOGLE_NEWS_URL', _DEFAULT_GOOGLE_URL)
        url = google_news_url.format(query=query)

        news_list = []
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

                    # Filter out news older than 30 days
                    if pub_date:
                        try:
                            dt = parsedate_to_datetime(pub_date)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=datetime.timezone.utc)
                            if (now_utc - dt).days > 30:
                                continue
                        except Exception:
                            pass  # If parsing fails, we'll keep it

                    title = item.find('title').text if item.find('title') is not None else ''
                    link = item.find('link').text if item.find('link') is not None else ''
                    source = item.find('source').text if item.find('source') is not None else ''

                    news_list.append({
                        'title': title,
                        'link': link,
                        'pub_date': pub_date,
                        'source': source,
                        '_dt': dt
                    })

                    if len(news_list) >= 8:
                        break

                # Sort by latest date first, then remove the temporary _dt key
                news_list.sort(key=lambda x: x['_dt'], reverse=True)
                for news in news_list:
                    news.pop('_dt', None)

                self.NEWS_CACHE[ticker] = {"timestamp": now, "data": news_list}
        except Exception as e:
            print(f"Error fetching news for {ticker}: {e}")
            if ticker in self.NEWS_CACHE:
                return self.NEWS_CACHE[ticker]["data"]

        return news_list

    def get_news_for_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Get news for a given symbol (similar to the original API endpoint).

        Args:
            symbol: Stock symbol (may include NSE: prefix)

        Returns:
            Dictionary with symbol and news list
        """
        # Strip "NSE:" if present
        if symbol.startswith("NSE:"):
            symbol = symbol[4:]

        symbol = symbol.strip().upper()
        if not symbol:
            return {"error": "Symbol required", "news": []}

        articles = self.fetch_google_news(symbol)
        return {"symbol": symbol, "news": articles}


# Singleton instance
news_service = NewsService()