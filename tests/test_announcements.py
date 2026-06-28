from app import create_app

app = create_app()
app.testing = True
client = app.test_client()

if __name__ == '__main__':
    # Test the NLP processing endpoint
    response = client.post('/api/v1/announcements/process',
                           json={'desc': 'Test dividend announcement',
                                 'text': 'The company declared a dividend of $0.5 per share.'})
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response keys:', list(data.keys()) if data else 'None')

    # Test the fallback classification endpoint
    response = client.post('/api/v1/announcements/classify',
                           json={'desc': 'Test dividend announcement',
                                 'text': 'The company declared a dividend of $0.5 per share.'})
    print('Status Code:', response.status_code)
    data = response.get_json()
    print('Response keys:', list(data.keys()) if data else 'None')