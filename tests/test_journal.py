import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

app = create_app()
app.testing = True
client = app.test_client()

print("Testing Journal API...")

# Test 1: Get journal
print("\n1. Getting journal:")
response = client.get('/api/v1/journal')
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)
if isinstance(data, dict) and 'data' in data:
    journal_data = data['data']
    print('Number of entries:', len(journal_data) if isinstance(journal_data, list) else 'Not a list')
elif isinstance(data, list):
    journal_data = data
    print('Number of entries:', len(journal_data))
else:
    journal_data = []
    print('Unexpected response format')

# Test 2: Create a journal entry
print("\n2. Creating a journal entry:")
entry_data = {
    "id": "trade-001",
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "date": "2026-06-15",
    "setupLabel": "Breakout",
    "swingband": "150-170",
    "entry": 155.0,
    "stop": 150.0,
    "target1": 160.0,
    "target2": 165.0,
    "target3": 170.0,
    "riskAmount": 5.0,
    "qty": 10,
    "status": "open"
}
response = client.post('/api/v1/journal', json=entry_data)
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 3: Get journal to see the entry
print("\n3. Getting journal after creating entry:")
response = client.get('/api/v1/journal')
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)
if isinstance(data, dict) and 'data' in data:
    journal_data = data['data']
    print('Number of entries:', len(journal_data) if isinstance(journal_data, list) else 'Not a list')
elif isinstance(data, list):
    journal_data = data
    print('Number of entries:', len(journal_data))
else:
    journal_data = []
    print('Unexpected response format')

# Test 4: Create another entry
print("\n4. Creating another journal entry:")
entry_data2 = {
    "id": "trade-002",
    "ticker": "GOOGL",
    "name": "Alphabet Inc.",
    "date": "2026-06-14",
    "setupLabel": "Pullback",
    "swingband": "2500-2700",
    "entry": 2600.0,
    "stop": 2550.0,
    "target1": 2650.0,
    "target2": 2700.0,
    "target3": 2750.0,
    "riskAmount": 50.0,
    "qty": 2,
    "status": "open"
}
response = client.post('/api/v1/journal', json=entry_data2)
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 5: Get journal to see both entries
print("\n5. Getting journal after creating second entry:")
response = client.get('/api/v1/journal')
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)
if isinstance(data, dict) and 'data' in data:
    journal_data = data['data']
    print('Number of entries:', len(journal_data) if isinstance(journal_data, list) else 'Not a list')
    if isinstance(journal_data, list) and len(journal_data) > 0:
        print('First entry:', journal_data[0])
elif isinstance(data, list):
    journal_data = data
    print('Number of entries:', len(journal_data))
    if len(journal_data) > 0:
        print('First entry:', journal_data[0])
else:
    journal_data = []
    print('Unexpected response format')

# Test 6: Update the first entry (add exit price to trigger P&L calculation)
print("\n6. Updating first entry with exit price:")
update_data = {
    "exitPrice": 160.0,
    "exitDate": "2026-06-16"
}
response = client.put('/api/v1/journal/trade-001', json=update_data)
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 7: Get journal to see the updated entry with P&L
print("\n7. Getting journal after updating first entry:")
response = client.get('/api/v1/journal')
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)
journal_data = []
if isinstance(data, dict) and 'data' in data:
    journal_data = data['data']
elif isinstance(data, list):
    journal_data = data

if isinstance(journal_data, list):
    for entry in journal_data:
        if entry.get('id') == 'trade-001':
            print('Updated entry:', entry)
            break

# Test 8: Try to create duplicate entry (should fail)
print("\n8. Trying to create duplicate entry:")
response = client.post('/api/v1/journal', json=entry_data)
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 9: Delete the second entry
print("\n9. Deleting second entry:")
response = client.delete('/api/v1/journal/trade-002')
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)

# Test 10: Get journal to see the entry deleted
print("\n10. Getting journal after deleting second entry:")
response = client.get('/api/v1/journal')
print('Status Code:', response.status_code)
data = response.get_json()
print('Response:', data)
if isinstance(data, dict) and 'data' in data:
    journal_data = data['data']
    print('Number of entries:', len(journal_data) if isinstance(journal_data, list) else 'Not a list')
elif isinstance(data, list):
    journal_data = data
    print('Number of entries:', len(journal_data))
else:
    journal_data = []
    print('Unexpected response format')

print("\nJournal API test completed.")