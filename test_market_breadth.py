from app import create_app

app = create_app()
app.testing = True
client = app.test_client()

print("Testing Market Breadth API...")

# Test 1: Get breadth history (should be empty initially)
print("\n1. Getting initial breadth history:")
response = client.get('/api/v1/breadth-history')
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 2: Save a breadth snapshot
print("\n2. Saving a breadth snapshot:")
snapshot_data = {
    "advances": 1200,
    "declines": 800,
    "unchanged": 50,
    "pct_sma21": 0.65,
    "pct_sma50": 0.58,
    "pct_52high": 0.32,
    "avg_recommend": 2.3,
    "regime_score": 75,
    "regime_band": "Accumulation"
}
response = client.post('/api/v1/breadth-snapshot', json=snapshot_data)
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 3: Get breadth history to see the snapshot
print("\n3. Getting breadth history after saving snapshot:")
response = client.get('/api/v1/breadth-history')
print('Status Code:', response.status_code)
data = response.get_json()
print('Number of records:', len(data.get('history', [])) if isinstance(data, dict) and 'history' in data else ('Not a dict' if not isinstance(data, list) else len(data)))
if isinstance(data, dict) and 'history' in data:
    print('First record:', data['history'][0] if data['history'] else 'No records')
elif isinstance(data, list):
    print('First record:', data[0] if data else 'No records')

# Test 4: Get latest breadth snapshot
print("\n4. Getting latest breadth snapshot:")
response = client.get('/api/v1/breadth-latest')
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 5: Save another snapshot with different data
print("\n5. Saving another breadth snapshot:")
snapshot_data2 = {
    "advances": 900,
    "declines": 1100,
    "unchanged": 30,
    "pct_sma21": 0.42,
    "pct_sma50": 0.38,
    "pct_52high": 0.18,
    "avg_recommend": 1.9,
    "regime_score": 35,
    "regime_band": "Distribution"
}
response = client.post('/api/v1/breadth-snapshot', json=snapshot_data2)
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 6: Get breadth history with limit=1
print("\n6. Getting breadth history with limit=1:")
response = client.get('/api/v1/breadth-history?limit=1')
print('Status Code:', response.status_code)
data = response.get_json()
print('Number of records:', len(data.get('history', [])) if isinstance(data, dict) and 'history' in data else ('Not a dict' if not isinstance(data, list) else len(data)))
if isinstance(data, dict) and 'history' in data:
    print('Record (should be the most recent):', data['history'][0] if data['history'] else 'No records')

# Test 7: Get breadth history with limit=2 to see both
print("\n7. Getting breadth history with limit=2:")
response = client.get('/api/v1/breadth-history?limit=2')
print('Status Code:', response.status_code)
data = response.get_json()
print('Number of records:', len(data.get('history', [])) if isinstance(data, dict) and 'history' in data else ('Not a dict' if not isinstance(data, list) else len(data)))
if isinstance(data, dict) and 'history' in data:
    print('Number of records returned:', len(data['history']))
    for i, record in enumerate(data['history']):
        print(f'  Record {i+1}: date={record["date"]}, time={record["time"]}, advances={record["advances"]}')

print("\nMarket Breadth API test completed.")