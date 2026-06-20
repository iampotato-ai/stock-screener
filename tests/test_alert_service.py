import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

app = create_app()
app.testing = True

def test_alert_service():
    """Test the alert service functionality."""
    with app.app_context():
        from app.services.alert_service import alert_service

        # Test get_alert_config
        config = alert_service.get_alert_config()
        print("Alert config:", config)

        # Test send_telegram_alert (will fail without credentials, but should return False)
        result = alert_service.send_telegram_alert("Test message")
        print("Send telegram alert result:", result)

        # Test send_watchlist_trigger_alert
        result = alert_service.send_watchlist_trigger_alert("RELIANCE", "NSE", 2500.50)
        print("Send watchlist trigger alert result:", result)

        # Test send_ep_refresh_alerts
        alerts = ["Test alert 1", "Test alert 2"]
        sent_count = alert_service.send_ep_refresh_alerts(alerts)
        print(f"Sent {sent_count} EP refresh alerts")

if __name__ == "__main__":
    test_alert_service()
    print("Alert service tests completed.")