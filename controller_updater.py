import requests
import re
import time
import json

CACHE_FILE = "controller_cache.json"

callsign_to_artcc = {
    "TOR": "CZYZ",
    "WPG": "CZWG",
    "CZVR": "CZVR",
    "MTL": "CZUL",
    "CZQM": "CZQM",
    "CZQX": "CZQM",
    "CZEG": "CZEG",
}

def fetch_controller_data():
    vnasurl = "https://live.env.vnas.vatsim.net/data-feed/controllers.json"
    vatsimurl = "https://data.vatsim.net/v3/vatsim-data.json"
    
    try:
        vnas_response = requests.get(vnasurl)
        vnas_response.raise_for_status()
        vnas_data = vnas_response.json()

        center_controllers = [
            c for c in vnas_data["controllers"]
            if c.get("isActive") and not c.get("isObserver")
            and c.get("vatsimData", {}).get("facilityType") == "Center"
        ]

        tracon_controllers = [
            c for c in vnas_data["controllers"]
            if c.get("isActive") and not c.get("isObserver")
            and c.get("vatsimData", {}).get("facilityType") == "ApproachDeparture"
            and c.get("artccId") == "ZOB"
        ]

        vatsim_response = requests.get(vatsimurl)
        vatsim_response.raise_for_status()
        vatsim_data = vatsim_response.json()

        canadian_controllers = []
        for controller in vatsim_data.get("controllers", []):
            callsign = controller.get("callsign", "").upper()
            match = re.match(r"^([A-Z]{3,4})_(?:\d{1,3}_)?(?:CTR|FSS)$", callsign)
            if match:
                prefix = match.group(1)
                if prefix in callsign_to_artcc:
                    controller["artccId"] = callsign_to_artcc[prefix]
                    canadian_controllers.append(controller)

        filtered_data = {
            "updatedAt": vnas_data.get("updatedAt"),
            "controllers": center_controllers + canadian_controllers,
            "tracon": tracon_controllers
        }

        return filtered_data

    except requests.RequestException as e:
        print(f"Error fetching controller data: {e}")
        return None

def update_cache():
    data = fetch_controller_data()
    if data:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
        print(f"Cache updated at {time.ctime()}")
    else:
        print("Failed to update cache")

if __name__ == "__main__":
    update_cache()
