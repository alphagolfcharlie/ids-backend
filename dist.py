import requests, json
from flask import jsonify
from math import radians, cos, sin, asin, sqrt

def finddist(lat1, lon1, lat2, lon2):
    R = 6371  # Radius of Earth in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c

def getCoords():
    url = "https://data.vatsim.net/v3/vatsim-data.json"
    headers = {'Accept': 'application/json'}

    response = requests.get(url, headers=headers)
    data = response.json()

    pilots = data['pilots']
    result = []

    # Properly collect all pilot data
    for entry in pilots:
        callsign = entry.get("callsign")
        lat = entry.get("latitude")
        long = entry.get("longitude")
        flight_plan = entry.get("flight_plan")

        if flight_plan and "route" in flight_plan:
            route = flight_plan.get("route", "")
            departure = flight_plan.get("departure", "")
            arrival = flight_plan.get("arrival", "")
            result.append((callsign, departure, arrival, route, lat, long))

    # Filter criteria
    target_lat, target_lon = 41.2129, -82.9431  # lat long of DJB VOR

    filtere = [
        (callsign, departure, arrival, route, lat, long)
        for callsign, departure, arrival, route, lat, long in result
        if lat and long and finddist(target_lat, target_lon, lat, long) < 600
    ]

    acarr = []

    for row in filtere:
        aircraft_lat, aircraft_lon = row[4], row[5]
        d = finddist(target_lat, target_lon, aircraft_lat, aircraft_lon)
        acarr.append((row[0], row[1], row[2], d, row[3], aircraft_lat, aircraft_lon))

    structured = []
    for row in acarr:
        callsign = row[0]
        departure = row[1]
        destination = row[2]
        route = row[4]  
        lat = row[5]
        lon = row[6]

        structured.append({
            'callsign': callsign,
            'route': route,
            'departure': departure,
            'destination': destination,
            'lat': lat,
            'lon': lon
        })

    return structured
