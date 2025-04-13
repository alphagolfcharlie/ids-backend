import requests

# URL of the API
url = "https://datis.clowd.io/api/KDTW"

# Send a GET request to the API
response = requests.get(url)

# Check if the request was successful
if response.status_code == 200:
    # The API usually returns JSON data
    data = response.json()
    
    # Print the data or work with it
    print(data)
else:
    print(f"Failed to retrieve data. Status code: {response.status_code}")
