import requests
import re
import time
import json
import os
from math import radians, sin, cos, asin, sqrt


INFO_CACHE_FILE = "/opt/ids-backend-1108/airport_info_cache.json"
CONTROLLER_CACHE_FILE = "/opt/ids-backend-1108/controller_cache.json"
AIRCRAFT_CACHE_FILE = "/opt/ids-backend-1108/aircraft_cache.json"
CACHE_REFRESH_INTERVAL = 60  # seconds (1 minute)
ATIS_AIRPORTS = ["KDTW","KCLE","KBUF","KPIT"]

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

def update_wx():
    print("Refreshing airport info cache...")
    data = {
        "updatedAt": time.ctime(),
        "airports": {}
    }
    for airport in ATIS_AIRPORTS:
        code = airport.replace("K", "")
        data["airports"][airport] = {
            "metar": get_metar(airport),
            "atis": get_atis(code),
            "flow": get_flow(code)
        }
    try:
        with open(INFO_CACHE_FILE, "w") as f:
            json.dump(data, f)
        print(f"Airport info cache updated at {data['updatedAt']}")
    except Exception as e:
        print(f"Error writing airport info cache: {e}")

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

def update_controllers():
    data = fetch_controller_data()
    if data:
        data['cacheUpdatedAt'] = time.ctime()  # Add your own local update time
        with open(CONTROLLER_CACHE_FILE, "w") as f:
            json.dump(data, f)
        print(f"Controller cache updated at {data['cacheUpdatedAt']}")
    else:
        print("Failed to update controller cache")


CACHE_REFRESH_INTERVAL = 60  # seconds (1 minute)
MAX_CACHE_RADIUS = 1000      # nautical miles for cache

def finddist(lat1, lon1, lat2, lon2):
    R = 3440.065  # Radius of Earth in nautical miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c

def fetch_aircraft_data(radius_nm):
    url = "https://data.vatsim.net/v3/vatsim-data.json"
    headers = {'Accept': 'application/json'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching VATSIM data: {e}")
        return None

    pilots = data.get('pilots', [])
    result = []

    for entry in pilots:
        callsign = entry.get("callsign")
        lat = entry.get("latitude")
        lon = entry.get("longitude")
        alt = entry.get("altitude")
        flight_plan = entry.get("flight_plan")

        if flight_plan and "route" in flight_plan:
            route = flight_plan.get("route", "")
            departure = flight_plan.get("departure", "")
            arrival = flight_plan.get("arrival", "")
            result.append((callsign, departure, arrival, route, lat, lon, alt))

    target_lat, target_lon = 41.2129, -82.9431  # DJB VOR

    filtered = [
        (callsign, departure, arrival, route, lat, lon, alt)
        for callsign, departure, arrival, route, lat, lon, alt in result
        if lat is not None and lon is not None and finddist(target_lat, target_lon, lat, lon) <= radius_nm
    ]

    structured = []
    for callsign, departure, arrival, route, lat, lon, altitude in filtered:
        structured.append({
            'callsign': callsign,
            'route': route,
            'departure': departure,
            'destination': arrival,
            'lat': lat,
            'lon': lon,
            'altitude': altitude
        })

    return structured

def update_aircraft():
    print("Refreshing aircraft data cache (max radius)...")
    data = fetch_aircraft_data(radius_nm=MAX_CACHE_RADIUS)
    if data is not None:
        wrapped = {
            "updatedAt": time.ctime(),
            "aircraft": data
        }
        try:
            with open(AIRCRAFT_CACHE_FILE, "w") as f:
                json.dump(wrapped, f)
            print(f"Aircraft cache updated at {wrapped['updatedAt']}")
        except Exception as e:
            print(f"Error writing aircraft cache file: {e}")
    else:
        print("No aircraft data fetched; cache not updated.")

if __name__ == "__main__":
    update_wx()
    update_controllers()
    update_aircraft()