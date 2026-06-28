import requests

url = "http://localhost:8000/upload-transcript"

with open("test_transcript.txt", "rb") as f:
    response = requests.post(
        url,
        files={"file": ("test_transcript.txt", f, "text/plain")},
        data={"category": "email", "status": "solved"}
    )

print("Status code:", response.status_code)
print("Response:", response.text)