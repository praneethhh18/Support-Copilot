import requests

response = requests.post(
    "http://localhost:8000/search",
    json={"message": "my email is not sending anything since morning"}
)

print(response.json())