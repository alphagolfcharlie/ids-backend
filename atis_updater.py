import requests
import re
import time
import json
import os

CACHE_FILE = "/opt/ids-backend/airport_info_cache.json"
CACHE_REFRESH_INTERVAL = 60  # seconds (1 minute)
ATIS_AIRPORTS = os.getenv("ATIS_AIRPORTS", "").split(",")

with open("data/runway_flow.json", "r") as f:
    RUNWAY_FLOW_MAP = json.load(f)

# Make sure these are defined somewhere accessible:
# RUNWAY_FLOW_MAP = {...}
# ATIS_AIRPORTS = [...]

def get_flow(airport_code):
    airport_code = airport_code.upper()
    if airport_code not in RUNWAY_FLOW_MAP:
        return None
    try:
        aptIcao = "K" + airport_code
        datis_url = f"https://datis.clowd.io/api/{aptIcao}"
        response = requests.get(datis_url, timeout=5)
        if response.status_code != 200:
            return None

        atis_data = response.json()
        if not isinstance(atis_data, list) or len(atis_data) == 0:
            return None

        # Prefer departure ATIS if available
        if len(atis_data) > 1:
            atis_text = atis_data[1]
        else:
            atis_text = atis_data[0]

        atis_datis = atis_text.get('datis', "")

        flow_config = RUNWAY_FLOW_MAP[airport_code]
        for flow_direction, runways in flow_config.items():
            for rwy in runways:
                if re.search(rf"DEPG RWY {rwy}[LRC]?", atis_datis) or \
                   re.search(rf"DEPG RWYS {rwy}[LRC]?", atis_datis) or \
                   re.search(rf"DEPTG RWY {rwy}[LRC]?", atis_datis):
                    return flow_direction.upper()
        return None
    except Exception as e:
        print(f"Flow detection error for {airport_code}: {e}")
        return None

def get_metar(icao):
    url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=raw&hours=1"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return f"Error: API returned status {response.status_code}"
        text = response.text.strip()
        if not text:
            return "No METAR available"
        return text
    except Exception as e:
        return f"Error: {str(e)}"

def get_atis(station):
    try:
        response = requests.get(f"https://datis.clowd.io/api/K{station}", timeout=5)
        if response.status_code != 200:
            return None
        datis = response.json()
        if datis[0]["type"] == "combined":
            return datis[0]["datis"]
        elif len(datis) > 1:
            return f"Departure: {datis[1]['datis']}\nArrival: {datis[0]['datis']}"
        return datis[0]["datis"]
    except Exception as e:
        return f"ATIS fetch failed: {e}"

def update_cache():
    print("Refreshing airport info cache...")
    data = {}
    for airport in ATIS_AIRPORTS:
        code = airport.replace("K", "")
        data[airport] = {
            "metar": get_metar(airport),
            "atis": get_atis(code),
            "flow": get_flow(code)
        }
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
        print(f"Airport info cache updated at {time.ctime()}")
    except Exception as e:
        print(f"Error writing airport info cache: {e}")
    time.sleep(CACHE_REFRESH_INTERVAL)

if __name__ == "__main__":
    update_cache()
