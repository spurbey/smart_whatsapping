import requests

url = "http://localhost:8000/webhook/whatsapp"
payload = {
    "message_id": "test_123",
    "from_phone": "+1234567899",
    "message_text": "Hi, I need help with my ourchases",
    "timestamp": "2025-01-10T15:30:00Z",
    "customer_name": "Sumit Purbey"
}
resp = requests.post(url, json=payload)
print(resp.json())

