import requests
import re
import time
import json
from math import radians, sin, cos, asin, sqrt

CACHE_FILE = "/opt/ids-backend-1108/aircraft_cache.json"
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

def update_cache():
    print("Refreshing aircraft data cache (max radius)...")
    data = fetch_aircraft_data(radius_nm=MAX_CACHE_RADIUS)
    if data is not None:
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(data, f)
            print(f"Aircraft cache updated at {time.ctime()}")
        except Exception as e:
            print(f"Error writing cache file: {e}")
    else:
        print("No data fetched; cache not updated.")

if __name__ == "__main__":
    update_cache()