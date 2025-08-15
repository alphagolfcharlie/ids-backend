from fastapi import FastAPI
import requests
from math import radians, cos, sin, asin, sqrt

app = FastAPI()

def finddist(lat1, lon1, lat2, lon2):
    R = 3440.065  # Radius of Earth in nautical miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c  # returns nautical miles

def getCoords(radius_nm=300):
    url = "https://data.vatsim.net/v3/vatsim-data.json"
    response = requests.get(url)
    data = response.json()

    pilots = data['pilots']
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

    target_lat, target_lon = 41.2129, -82.9431  # lat long of DJB VOR

    filtered = [
        (callsign, departure, arrival, route, lat, lon, alt)
        for callsign, departure, arrival, route, lat, lon, alt in result
        if lat and lon and finddist(target_lat, target_lon, lat, lon) < radius_nm 
    ]

    structured = []
    for row in filtered:
        d = finddist(target_lat, target_lon, row[4], row[5])
        structured.append({
            'callsign': row[0],
            'departure': row[1],
            'destination': row[2],
            'route': row[3],
            'distance_nm': d,
            'lat': row[4],
            'lon': row[5],
            'altitude': row[6]
        })

    return structured

