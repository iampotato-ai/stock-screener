"""
Alert service for managing alert notifications and configurations.
"""
import os
import json
import urllib.request
from typing import Dict, Any, Optional
from flask import current_app


class AlertService:
    """Service for alert-related operations."""

    def send_telegram_alert(self, message: str) -> bool:
        """
        Send a notification message to the configured Telegram chat/channel.

        Args:
            message: The message to send

        Returns:
            True if sent successfully, False otherwise
        """
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            current_app.logger.warning("Telegram credentials not configured")
            return False

        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                response.read()
            current_app.logger.info(f"Telegram alert sent successfully: {message[:50]}{'...' if len(message) > 50 else ''}")
            return True
        except Exception as e:
            current_app.logger.error(f"Error sending telegram alert: {e}")
            return False

    def send_watchlist_trigger_alert(self, symbol: str, exchange: str, entry_price: float) -> bool:
        """
        Send a watchlist trigger alert via Telegram.

        Args:
            symbol: Stock symbol
            exchange: Exchange (e.g., NSE, BSE)
            entry_price: Entry price that triggered the alert

        Returns:
            True if sent successfully, False otherwise
        """
        price_str = f"₹{entry_price:.2f}" if entry_price is not None else "₹0.00"
        alert_msg = (
            f"🔔 <b>EP Watchlist Triggered!</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Exchange:</b> {exchange}\n"
            f"<b>Price:</b> {price_str}"
        )
        return self.send_telegram_alert(alert_msg)

    def send_ep_refresh_alerts(self, alerts: list) -> int:
        """
        Send a batch of EP refresh alerts via Telegram.

        Args:
            alerts: List of alert messages to send

        Returns:
            Number of alerts sent successfully
        """
        sent_count = 0
        for alert_msg in alerts:
            if self.send_telegram_alert(alert_msg):
                sent_count += 1
        return sent_count

    def get_alert_config(self) -> Dict[str, Any]:
        """
        Get current alert configuration from environment variables.

        Returns:
            Dictionary containing alert configuration
        """
        configured = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
        return {
            "telegram_configured": configured,
            # Add other alert configurations as needed
        }


# Singleton instance
alert_service = AlertService()