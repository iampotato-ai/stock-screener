from app import create_app

app = create_app()
app.testing = True
client = app.test_client()

if __name__ == '__main__':
    print("Testing EP Watchlist API...")

    # Test 1: Get initial EP watchlist
    print("\n1. Getting initial EP watchlist:")
    response = client.get('/api/v1/ep/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 2: Add an entry to EP watchlist
    print("\n2. Adding an entry to EP watchlist:")
    entry_data = {
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "entry_price": 150.0,
        "target_price": 160.0,
        "stop_loss": 145.0
    }
    response = client.post('/api/v1/ep/watchlist', json=entry_data)
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 3: Get EP watchlist to see the entry
    print("\n3. Getting EP watchlist after adding entry:")
    response = client.get('/api/v1/ep/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 4: Trigger the EP watchlist (get entry price and exchange)
    print("\n4. Triggering EP watchlist:")
    trigger_data = {
        "symbol": "AAPL"
    }
    response = client.post('/api/v1/ep/watchlist/trigger', json=trigger_data)
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 5: Remove the entry from EP watchlist
    print("\n5. Removing the entry from EP watchlist:")
    remove_data = {
        "symbol": "AAPL"
    }
    response = client.post('/api/v1/ep/watchlist/remove', json=remove_data)
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    # Test 6: Get EP watchlist to see the entry removed
    print("\n6. Getting EP watchlist after removing entry:")
    response = client.get('/api/v1/ep/watchlist')
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response:', data)

    print("\nEP Watchlist API test completed.")