from flask import Flask, redirect, request, jsonify, json
import requests, re, threading, time, os, jwt, datetime, urllib.parse
from functools import wraps
from auxfns.dist import getCoords
from auxfns.searchroute import searchroute
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from dotenv import load_dotenv
from flask_cors import CORS
from google.oauth2 import id_token
from google.auth.transport.requests import Request 
from math import radians, cos, sin, asin, sqrt

import os
from pymongo import MongoClient


load_dotenv()

import os
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI")


client = MongoClient(MONGO_URI)

db = client["ids"]
routes_collection = db["routes"]
crossings_collection = db["crossings"]
faa_routes_collection = db["faa_prefroutes"]
fixes_collection = db["fixes"]
navaids_collection = db["navaids"]
airway_collection = db["airways"]
star_rte_collection = db["star_rte"]
dp_rte_collection = db["sid_rte"]
enroute_collection = db["enroute"]

app = Flask(__name__)

# Allow requests from localhost:5173 only (for development)
CORS(app, resources={r"/api/*": {
    "origins": [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://idsnew.vercel.app",
        "https://ids.alphagolfcharlie.dev"
    ]
}})


SECRET_KEY = os.getenv("SECRET_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
AUTHORIZED_EMAILS = os.getenv("AUTHORIZED_EMAILS", "").split(",")
ATIS_AIRPORTS = os.getenv("ATIS_AIRPORTS", "").split(",")

with open("data/runway_flow.json", "r") as f:
    RUNWAY_FLOW_MAP = json.load(f)

client = MongoClient(MONGO_URI)

db = client["ids"]
routes_collection = db["routes"]
crossings_collection = db["crossings"]
faa_routes_collection = db["faa_prefroutes"]
fixes_collection = db["fixes"]
navaids_collection = db["navaids"]
airway_collection = db["airways"]
star_rte_collection = db["star_rte"]
dp_rte_collection = db["sid_rte"]
enroute_collection = db["enroute"]

#jwt required
def jwt_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "Token is missing"}), 401
        try:
            # Remove "Bearer " prefix if present
            token = token.split(" ")[1] if " " in token else token
            jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return func(*args, **kwargs)
    return wrapper

#google login 
@app.route('/api/google-login', methods=['POST'])
def google_login():
    data = request.json
    token = data.get("token")

    if not token:
        return jsonify({"error": "Token is missing"}), 400

    try:
        # Create a Request object for token verification
        request_adapter = Request()

        # Verify the Google ID token
        idinfo = id_token.verify_oauth2_token(token, request_adapter, GOOGLE_CLIENT_ID)

        # Extract user info from the token
        email = idinfo.get("email")
        name = idinfo.get("name")

        # Check if the user is authorized
        authorized_emails = os.getenv("AUTHORIZED_EMAILS", "").split(",")
        if email not in authorized_emails:
            return jsonify({"error": "Unauthorized user"}), 403

        # Issue a custom JWT
        custom_token = jwt.encode(
            {
                "email": email,
                "name": name,
                "role": "admin",  # You can add roles or permissions here
                "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),  # Token expiration
            },
            SECRET_KEY,
            algorithm="HS256",
        )

        return jsonify({"message": "Login successful", "token": custom_token}), 200

    except ValueError as e:
        # Invalid token
        print("Token verification failed:", e)
        return jsonify({"error": "Invalid token"}), 401

    except Exception as e:
        # Handle unexpected errors
        print("Unexpected error:", e)
        return jsonify({"error": "Internal server error"}), 500

# Cache dict to hold airport info data and last update time
airport_info_cache = {
    "data": None,
    "last_updated": None
}

CACHE_REFRESH_INTERVAL = 60  # seconds (1 minute)

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

def refresh_airport_info_cache():
    while True:
        print("Refreshing airport info cache...")
        data = {}
        for airport in ATIS_AIRPORTS:
            code = airport.replace("K", "")
            data[airport] = {
                "metar": get_metar(airport),
                "atis": get_atis(code),
                "flow": get_flow(code)
            }
        airport_info_cache["data"] = data
        airport_info_cache["last_updated"] = time.time()
        time.sleep(CACHE_REFRESH_INTERVAL)

@app.route("/api/airport_info")
def airport_info():
    if airport_info_cache["data"]:
        return jsonify(airport_info_cache["data"])
    else:
        # Cache empty at startup, fetch synchronously once
        refresh_airport_info_cache()
        if airport_info_cache["data"]:
            return jsonify(airport_info_cache["data"])
        else:
            return jsonify({"error": "No airport info available"}), 503

# Start the background thread on app start
threading.Thread(target=refresh_airport_info_cache, daemon=True).start()


@app.route('/api/routes')
def api_routes():
    origin = request.args.get('origin', '').upper()
    destination = request.args.get('destination', '').upper()
    routes = searchroute(origin, destination)

    return jsonify(routes)

# PUT endpoint to update a route
@app.route('/api/routes/<route_id>', methods=['PUT'])
@jwt_required
def update_route(route_id):
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Update the route in the database
    result = routes_collection.update_one(
        {"_id": ObjectId(route_id)},
        {"$set": {
            "origin": data.get('origin'),
            "destination": data.get('destination'),
            "route": data.get('route'),
            "altitude": data.get('altitude'),
            "notes": data.get('notes'),
        }}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Route not found"}), 404

    return jsonify({"message": "Route updated successfully"}), 200

# DELETE endpoint to delete a crossing
@app.route('/api/routes/<route_id>', methods=['DELETE'])
@jwt_required
def delete_route(route_id):
    # Delete the route from the database
    result = routes_collection.delete_one({"_id": ObjectId(route_id)})

    if result.deleted_count == 0:
        return jsonify({"error": "Route not found"}), 404

    return jsonify({"message": "Route deleted successfully"}), 200

# POST endpoint to create a new crossing
@app.route('/api/routes', methods=['POST'])
@jwt_required
def create_route():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Validate required fields
    required_fields = ['origin', 'destination', 'route', 'notes']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400
    
    altitude = data.get('altitude', '')  # Default to an empty string if not provided


    # Insert the new crossing into the database
    new_route = {
        "origin": data.get('origin'),
        "destination": data.get('destination'),
        "route": data.get('route'),
        "altitude": altitude,
        "notes": data.get('notes'),
    }
    result = routes_collection.insert_one(new_route)

    return jsonify({
        "message": "Route created successfully",
        "route_id": str(result.inserted_id)  # Return the ID of the newly created crossing
    }), 201


@app.route('/api/fix')
def get_fix():
    fixes_param = request.args.get('fixes')
    single_fix = request.args.get('fix')

    # Support both single and multiple
    fix_list = []
    if fixes_param:
        fix_list = [f.strip().upper() for f in fixes_param.split(',') if f.strip()]
    elif single_fix:
        fix_list = [single_fix.strip().upper()]
    else:
        return jsonify({'error': 'Missing fix or fixes parameter'}), 400

    results = {}

    for fix in fix_list:
        fix_doc = fixes_collection.find_one({'FIX_ID': fix})
        if fix_doc and fix_doc.get('LAT_DECIMAL') is not None and fix_doc.get('LONG_DECIMAL') is not None:
            results[fix] = {
                'lat': fix_doc['LAT_DECIMAL'],
                'lon': fix_doc['LONG_DECIMAL']
            }
            continue

        nav_doc = navaids_collection.find_one({'NAV_ID': fix})
        if nav_doc and nav_doc.get('LAT_DECIMAL') is not None and nav_doc.get('LONG_DECIMAL') is not None:
            results[fix] = {
                'lat': nav_doc['LAT_DECIMAL'],
                'lon': nav_doc['LONG_DECIMAL']
            }

    return jsonify(results)

@app.route('/api/airway')
def expand_airway():
    airway_id = request.args.get('id', '').upper()
    start = request.args.get('from', '').upper()
    end = request.args.get('to', '').upper()

    if not airway_id:
        return jsonify({'error': 'Missing airway ID'}), 400

    airway_doc = airway_collection.find_one({'AWY_ID': airway_id})
    if not airway_doc:
        return jsonify({'error': f'Airway {airway_id} not found'}), 404

    fixes = airway_doc['AIRWAY_STRING'].split()

    # If both 'from' and 'to' are provided, return only that segment
    if start and end:
        try:
            i = fixes.index(start)
            j = fixes.index(end)
        except ValueError:
            return jsonify({'error': f'Either {start} or {end} not part of airway {airway_id}'}), 400

        if i <= j:
            segment = fixes[i:j+1]
        else:
            segment = list(reversed(fixes[j:i+1]))

        return jsonify({'segment': segment})

    # If only one of start/end is provided → invalid
    elif start or end:
        return jsonify({'error': 'Both from and to must be provided to extract a segment'}), 400

    # If neither is provided → return full airway
    else:
        return jsonify({'segment': fixes})

@app.route('/api/star')
def get_star_transition():
    code = request.args.get('code', '').upper()
    if not code:
        return jsonify({'error': 'Missing STAR transition code'}), 400

    # Shared ARPT_RWY_ASSOC filter
    runway_filter = {
        '$or': [
            {'ARPT_RWY_ASSOC': {'$exists': False}},
            {'ARPT_RWY_ASSOC': ''},
            {'ARPT_RWY_ASSOC': {'$not': re.compile(r'/')}}
        ]
    }

    # First try: search by TRANSITION_COMPUTER_CODE
    rte_cursor = list(star_rte_collection.find({
        'TRANSITION_COMPUTER_CODE': code,
        **runway_filter
    }).sort('POINT_SEQ', DESCENDING))

    if not rte_cursor:
        rte_cursor = list(star_rte_collection.find({
            'STAR_COMPUTER_CODE': code,
            'ROUTE_NAME': {'$not': re.compile(r'TRANSITION', re.IGNORECASE)},
            **runway_filter
        }).sort('POINT_SEQ', DESCENDING))

    waypoints = []
    for doc in rte_cursor:
        point = doc.get('POINT')
        if point and point not in waypoints:
            waypoints.append(point)

    if not waypoints:
        # Fallback for STAR: return part after the dot if code contains dot
        if '.' in code:
            _, after_dot = code.split('.', 1)
            return jsonify({
                'transition': code,
                'waypoints': [after_dot]
            })
        else:
            return jsonify({'error': f'No valid waypoints found for {code}'}), 404

    return jsonify({
        'transition': code,
        'waypoints': waypoints
    })

@app.route('/api/sid')
def get_sid_transition():
    code = request.args.get('code', '').upper()
    if not code:
        return jsonify({'error': 'Missing SID transition code'}), 400

    # Shared ARPT_RWY_ASSOC filter
    runway_filter = {
        '$or': [
            {'ARPT_RWY_ASSOC': {'$exists': False}},
            {'ARPT_RWY_ASSOC': ''},
            {'ARPT_RWY_ASSOC': {'$not': re.compile(r'/')}}
        ]
    }

    # First try: search by TRANSITION_COMPUTER_CODE
    rte_cursor = list(dp_rte_collection.find({
        'TRANSITION_COMPUTER_CODE': code,
        **runway_filter
    }).sort('POINT_SEQ', DESCENDING))  # Note: ASCENDING for SIDs

    # Fallback: search by SID_COMPUTER_CODE if nothing found
    if not rte_cursor:
        rte_cursor = list(dp_rte_collection.find({
            'SID_COMPUTER_CODE': code,
            **runway_filter
        }).sort('POINT_SEQ', DESCENDING))

    waypoints = []
    for doc in rte_cursor:
        point = doc.get('POINT')
        if point and point not in waypoints:
            waypoints.append(point)

    if not waypoints:
        # Fallback for SID: return part before the dot if code contains dot
        if '.' in code:
            before_dot = code.split('.', 1)[0]
            before_dot = before_dot[:-1]
            return jsonify({
                'transition': code,
                'waypoints': [before_dot]
            })
        else:
            return jsonify({'error': f'No valid waypoints found for {code}'}), 404

    return jsonify({
        'transition': code,
        'waypoints': waypoints
    })

# Cache for aircraft data (max radius)
aircraft_cache = {
    "data": None,
    "last_updated": None
}

CACHE_REFRESH_INTERVAL = 60  # 1 minute
MAX_CACHE_RADIUS = 1000       # nm for cache
DEFAULT_RADIUS = 400          # nm for default endpoint response

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

def background_aircraft_cache_refresher():
    while True:
        print("Refreshing aircraft data cache (max radius)...")
        data = fetch_aircraft_data(radius_nm=MAX_CACHE_RADIUS)
        if data is not None:
            aircraft_cache["data"] = data
            aircraft_cache["last_updated"] = time.time()
        time.sleep(CACHE_REFRESH_INTERVAL)

@app.route('/api/aircraft')
def aircraft():
    try:
        radius = int(request.args.get("radius", DEFAULT_RADIUS))
    except ValueError:
        radius = DEFAULT_RADIUS

    if aircraft_cache["data"]:
        target_lat, target_lon = 41.2129, -82.9431
        filtered = [
            ac for ac in aircraft_cache["data"]
            if finddist(target_lat, target_lon, ac["lat"], ac["lon"]) <= radius
        ]
        return jsonify(filtered)
    else:
        # Cache empty (first startup) → fetch just for this request
        data = fetch_aircraft_data(radius_nm=radius)
        if data is None:
            return jsonify({"error": "Failed to fetch aircraft data"}), 503
        return jsonify(data)

# Start background cache refresher thread
threading.Thread(target=background_aircraft_cache_refresher, daemon=True).start()

@app.route('/api/crossings')
def api_crossings():
    destination = request.args.get('destination', '').upper()
    if len(destination) == 4 and destination.startswith('K'):
        destination = destination[1:]
    elif len(destination) == 4 and destination.startswith('C'):
        destination = destination[1:]

    query = {"destination": destination} if destination else {}
    rows = crossings_collection.find(query).sort("destination", 1)

    crossings = []
    for row in rows:
        crossings.append({
            '_id': str(row.get('_id')),  # Convert ObjectId to string
            'destination': row.get('destination'),
            'fix': row.get('bdry_fix'),
            'restriction': row.get('restriction'),
            'notes': row.get('notes'),
            'artcc': row.get('artcc')
        })

    return jsonify(crossings)

# PUT endpoint to update a crossing
@app.route('/api/crossings/<crossing_id>', methods=['PUT'])
@jwt_required
def update_crossing(crossing_id):
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Update the crossing in the database
    result = crossings_collection.update_one(
        {"_id": ObjectId(crossing_id)},
        {"$set": {
            "destination": data.get('destination'),
            "bdry_fix": data.get('fix'),
            "restriction": data.get('restriction'),
            "notes": data.get('notes'),
            "artcc": data.get('artcc')
        }}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Crossing not found"}), 404

    return jsonify({"message": "Crossing updated successfully"}), 200

# DELETE endpoint to delete a crossing
@app.route('/api/crossings/<crossing_id>', methods=['DELETE'])
@jwt_required
def delete_crossing(crossing_id):
    # Delete the crossing from the database
    result = crossings_collection.delete_one({"_id": ObjectId(crossing_id)})

    if result.deleted_count == 0:
        return jsonify({"error": "Crossing not found"}), 404

    return jsonify({"message": "Crossing deleted successfully"}), 200

# POST endpoint to create a new crossing
@app.route('/api/crossings', methods=['POST'])
@jwt_required
def create_crossing():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Validate required fields
    required_fields = ['destination', 'restriction', 'artcc']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    # Insert the new crossing into the database
    new_crossing = {
        "destination": data.get('destination'),
        "bdry_fix": data.get('fix'),
        "restriction": data.get('restriction'),
        "notes": data.get('notes'),
        "artcc": data.get('artcc')
    }
    result = crossings_collection.insert_one(new_crossing)

    return jsonify({
        "message": "Crossing created successfully",
        "crossing_id": str(result.inserted_id)  # Return the ID of the newly created crossing
    }), 201

@app.route('/api/enroute')
def api_enroute():

    field = request.args.get('field', '').upper()
    if len(field) == 4 and field.startswith('K'):
        field = field[1:]
    elif len(field) == 4 and field.startswith('C'):
        field = field[1:]
    area = request.args.get('area', '').strip()
    qualifier = request.args.get('qualifier','').strip()

    # MongoDB query
    query = {}

    if field:
        query["Field"] = {"$regex": field, "$options": "i"}

    if area:
        query["Areas"] = {"$regex": area, "$options": "i"}

    rows = enroute_collection.find(query)

 
    rows = enroute_collection.find(query)

    results = []
    seen = set()

    for row in rows:
        result_tuple = (
            row.get('Field', ''),
            row.get('Qualifier', ''),
            row.get('Areas', ''),
            row.get('Rule', '')
    )
        if result_tuple not in seen:
            seen.add(result_tuple)
            results.append({
                '_id': str(row.get('_id')),  # Include Mongo ID!
                'field': result_tuple[0],
                'qualifier': result_tuple[1],
                'areas': result_tuple[2],
                'rule': result_tuple[3]
            })


    # Sort results alphabetically by the 'field' key
    results = sorted(results, key=lambda x: x['field'])

    return jsonify(results)    

# DELETE endpoint to delete an enroute

@app.route('/api/enroute/<enroute_id>', methods=['DELETE'])
@jwt_required
def delete_enroute(enroute_id):
    # Delete the crossing from the database
    result = enroute_collection.delete_one({"_id": ObjectId(enroute_id)})

    if result.deleted_count == 0:
        return jsonify({"error": "Enroute entry not found"}), 404

    return jsonify({"message": "Enroute entry deleted successfully"}), 200

# PUT endpoint to update an enroute
@app.route('/api/enroute/<enroute_id>', methods=['PUT'])
@jwt_required
def update_enroute(enroute_id):
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    print("Received update for ID:", enroute_id)
    print("Payload:", data)
    # Update the enroute in the database
    result = enroute_collection.update_one(
        {"_id": ObjectId(enroute_id)},
        {"$set": {
            "Areas": data.get('areas'),
            "Field": data.get('field'),
            "Qualifier": data.get('qualifier'),
            "Rule": data.get('rule'),
        }}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Enroute entry not found"}), 404

    return jsonify({"message": "Enroute entry updated successfully"}), 200

# POST endpoint to create a new crossing
@app.route('/api/enroute', methods=['POST'])
@jwt_required
def create_enroute():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Validate required fields
    required_fields = ['areas', 'field', 'qualifier', 'rule']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    # Insert the new enroute into the database
    new_enroute = {
        "Areas": data.get('areas'),
        "Field": data.get('field'),
        "Qualifier": data.get('qualifier'),
        "Rule": data.get('rule'),
    }
    result = enroute_collection.insert_one(new_enroute)

    return jsonify({
        "message": "Crossing created successfully",
        "enroute_id": str(result.inserted_id)  # Return the ID of the newly created enroute
    }), 201

# Global cache for controller data
controller_cache = {
    "data": None,
    "last_updated": None
}

CACHE_REFRESH_INTERVAL = 300  # seconds (5 minutes)

callsign_to_artcc = {
    "TOR": "CZYZ",  # Toronto Center
    "WPG": "CZWG",  # Winnipeg Center
    "CZVR": "CZVR",  # Vancouver Center
    "MTL": "CZUL",  # Montreal Center
    "CZQM": "CZQM",  # Moncton/Gander Center
    "CZQX": "CZQM",  # Moncton/Gander Center
    "CZEG": "CZEG",  # Edmonton Center
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
            if c.get("isActive") == True
            and c.get("isObserver") == False
            and c.get("vatsimData", {}).get("facilityType") == "Center"
        ]

        tracon_controllers = [
            c for c in vnas_data["controllers"]
            if c.get("isActive") == True
            and c.get("isObserver") == False
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

        # Update the cache
        controller_cache["data"] = filtered_data
        controller_cache["last_updated"] = time.time()
    
    except requests.RequestException as e:
        print(f"Error fetching controller data: {e}")

def background_cache_refresher():
    while True:
        fetch_controller_data()
        time.sleep(CACHE_REFRESH_INTERVAL)

# Start the background thread when app starts
threading.Thread(target=background_cache_refresher, daemon=True).start()

@app.route('/api/controllers')
def get_center_controllers():
    if controller_cache["data"]:
        return jsonify(controller_cache["data"])
    else:
        # Cache is empty on startup; fetch synchronously once
        fetch_controller_data()
        if controller_cache["data"]:
            return jsonify(controller_cache["data"])
        else:
            return jsonify({"error": "No controller data available"}), 503


@app.route('/api/route-to-skyvector') #api 
def route_to_skyvector():


    callsign = request.args.get('callsign', '').upper().strip()
    if not callsign:
        return "Missing callsign parameter", 400

    try:
        print(f"Looking for: {callsign}")
        datafeed = "https://data.vatsim.net/v3/vatsim-data.json"
        response = requests.get(datafeed, timeout=5)
        data = response.json()

        for pilot in data.get('pilots', []):
            current = pilot.get('callsign', '').upper()
            if current == callsign:
                fp = pilot.get('flight_plan')
                if not fp:
                    return f"No flight plan found for {callsign}", 404

                dep = fp.get("departure", "").strip()
                rte = fp.get("route", "").strip()
                arr = fp.get("arrival", "").strip()

                if not (dep and arr):
                    return "Flight plan is missing departure or arrival", 400

                full_route = f"{dep} {rte} {arr}".strip()
                encoded = urllib.parse.quote(" ".join(full_route.split()))
                return redirect(f"https://skyvector.com/?fpl={encoded}")

        return f"Callsign {callsign} not found in VATSIM data", 404
    except Exception as e:
        return f"Error: {str(e)}", 500


if __name__ == "__main__":
    app.run()