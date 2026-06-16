import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()
app.testing = True
client = app.test_client()

def test_alerts_api():
    """Test the alert API endpoints."""

    print("Testing Alerts API...")

    # Test 1: Get alert config
    print("\n1. Getting alert config:")
    response = client.get('/api/v1/config')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 2: Send telegram alert (will fail without credentials, but should return appropriate error)
    print("\n2. Sending telegram alert:")
    response = client.post('/api/v1/telegram-alert',
                          json={"message": "Test alert message"})
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 3: Send watchlist trigger alert
    print("\n3. Sending watchlist trigger alert:")
    response = client.post('/api/v1/watchlist-trigger',
                          json={
                              "symbol": "RELIANCE",
                              "exchange": "NSE",
                              "entry_price": 2500.50
                          })
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 4: Send EP refresh alerts
    print("\n4. Sending EP refresh alerts:")
    response = client.post('/api/v1/ep-refresh-alerts',
                          json={
                              "alerts": [
                                  "Test EP alert 1",
                                  "Test EP alert 2"
                              ]
                          })
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 5: Invalid request - missing message
    print("\n5. Testing invalid telegram alert (missing message):")
    response = client.post('/api/v1/telegram-alert',
                          json={})
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 6: Invalid request - missing symbol
    print("\n6. Testing invalid watchlist trigger (missing symbol):")
    response = client.post('/api/v1/watchlist-trigger',
                          json={
                              "exchange": "NSE",
                              "entry_price": 2500.50
                          })
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

if __name__ == "__main__":
    test_alerts_api()
    print("\nAlert API tests completed.")