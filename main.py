print("Hi")
import requests
import json

url = "https://api.vatsim.net/v2/atc/online"

payload={}
headers = {
  'Accept': 'application/json'
}

params = {
    'limit':10
}

response = requests.request("GET", url, headers=headers, data=payload, params=params)

list2 = []
lst = json.loads(response.text)


print(lst)