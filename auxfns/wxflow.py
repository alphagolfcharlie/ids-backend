#get flow
from flask import json
import re
import requests
with open ("data/runway_flow.json", "r") as f:
    RUNWAY_FLOW_MAP = json.load(f)

def get_flow(airport_code):
    airport_code = airport_code.upper()
    if airport_code not in RUNWAY_FLOW_MAP:
        return None

    try:
        aptIcao = "K" + airport_code
        datis_url = f"https://datis.clowd.io/api/{aptIcao}"
        response = requests.get(datis_url)

        if response.status_code != 200:
            return None

        atis_data = response.json()
        atis_text = atis_data[1]
        atis_datis = atis_text['datis']

        flow_config = RUNWAY_FLOW_MAP[airport_code]
        for flow_direction, runways in flow_config.items():
            for rwy in runways:
                if re.search(rf"DEPG RWY {rwy}[LRC]?", atis_datis):
                    return flow_direction.upper()
                elif re.search(rf"DEPG RWYS {rwy}[LRC]?", atis_datis):
                    return flow_direction.upper()               
                elif re.search(rf"DEPTG RWY {rwy}[LRC]?", atis_datis):
                    return flow_direction.upper()
        return None
    except Exception as e:
        print(f"Flow detection error for {airport_code}: {e}")
        return None
    
#get metar
def get_metar(icao):
    url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=raw&hours=1"

    try:
        response = requests.get(url, timeout=5)

        # Ensure the response is valid
        if response.status_code != 200:
            return f"Error: API returned status {response.status_code}"

        text = response.text.strip()
        if not text:
            return "No METAR available"

        return text

    except Exception as e:
        return f"Error: {str(e)}"

# get ATIS 
def get_atis(station):
    try:
        response = requests.get(f"https://datis.clowd.io/api/K{station}", timeout=3)
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