import requests

TOKEN = "BOT_TOKEN"
CHAT_ID = "CHAT_ID"

def send(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{TOKEN}/sendMessage"
    )

    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        }
    )