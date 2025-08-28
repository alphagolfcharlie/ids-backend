from flask import Flask, redirect, request, jsonify, json
import requests, re, threading, time, os, jwt, datetime, urllib.parse
from functools import wraps
from auxfns.searchroute import searchroute
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from bson.json_util import dumps  # Helps with MongoDB's ObjectId serialization
from dotenv import load_dotenv
from flask_cors import CORS
from google.oauth2 import id_token
from google.auth.transport.requests import Request 
from math import radians, cos, sin, asin, sqrt
from update_cache import finddist



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

atis_cache = db["atis_cache"]
controller_cache = db["controller_cache"]
aircraft_cache = db["aircraft_cache"]


app = Flask(__name__)

# Allow requests from localhost:5173 only (for development)
CORS(app, resources={r"/ids/*": {
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
@app.route('/ids/google-login', methods=['POST'])
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



@app.route("/ids/airport_info")
def airport_info():
    try:
        # Get the most recent cache document
        latest_cache = atis_cache.find_one(sort=[("updatedAt", -1)])


        if not latest_cache:
            return jsonify({"error": "No airport info available"}), 503

        # Convert MongoDB doc to JSON-friendly format
        latest_cache['_id'] = str(latest_cache['_id'])
        return jsonify(json.loads(dumps(latest_cache)))
        

    except Exception as e:
        print(f"Error reading airport info cache from MongoDB: {e}")
        return jsonify({"error": "No airport info available"}), 503


@app.route('/ids/routes')
def api_routes():
    origin = request.args.get('origin', '').upper()
    destination = request.args.get('destination', '').upper()
    routes = searchroute(origin, destination)

    return jsonify(routes)

# PUT endpoint to update a route
@app.route('/ids/routes/<route_id>', methods=['PUT'])
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
@app.route('/ids/routes/<route_id>', methods=['DELETE'])
@jwt_required
def delete_route(route_id):
    # Delete the route from the database
    result = routes_collection.delete_one({"_id": ObjectId(route_id)})

    if result.deleted_count == 0:
        return jsonify({"error": "Route not found"}), 404

    return jsonify({"message": "Route deleted successfully"}), 200

# POST endpoint to create a new crossing
@app.route('/ids/routes', methods=['POST'])
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


@app.route('/ids/fix')
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

@app.route('/ids/airway')
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

@app.route('/ids/star')
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

@app.route('/ids/sid')
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


DEFAULT_RADIUS = 400  # nm

@app.route('/ids/aircraft')
def aircraft():
    try:
        radius = int(request.args.get("radius", DEFAULT_RADIUS))
    except ValueError:
        radius = DEFAULT_RADIUS
    includeOnGround = request.args.get("ground", "false").lower() in ("true", "1", "yes")
    try:
        cached_data = aircraft_cache.find_one({}, {"_id": 0})  # Get the single cache doc
        if not cached_data:
            return jsonify({"error": "Cache unavailable"}), 503
    except Exception as e:
        print(f"Error reading aircraft cache from MongoDB: {e}")
        return jsonify({"error": "Internal server error"}), 500

    target_lat, target_lon = 41.2129, -82.9431

    aircraft_list = cached_data.get("aircraft", [])

    filtered = [
        ac for ac in aircraft_list
        if finddist(ac["lat"], ac["lon"], target_lat, target_lon) <= radius
    ]

    if not includeOnGround:
        filtered = [ac for ac in filtered if ac["speed"] >= 50]
    else:
        pass

    return jsonify({
        "aircraft": filtered
    })


@app.route('/ids/crossings')
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
@app.route('/ids/crossings/<crossing_id>', methods=['PUT'])
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
@app.route('/ids/crossings/<crossing_id>', methods=['DELETE'])
@jwt_required
def delete_crossing(crossing_id):
    # Delete the crossing from the database
    result = crossings_collection.delete_one({"_id": ObjectId(crossing_id)})

    if result.deleted_count == 0:
        return jsonify({"error": "Crossing not found"}), 404

    return jsonify({"message": "Crossing deleted successfully"}), 200

# POST endpoint to create a new crossing
@app.route('/ids/crossings', methods=['POST'])
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

@app.route('/ids/enroute')
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

@app.route('/ids/enroute/<enroute_id>', methods=['DELETE'])
@jwt_required
def delete_enroute(enroute_id):
    # Delete the crossing from the database
    result = enroute_collection.delete_one({"_id": ObjectId(enroute_id)})

    if result.deleted_count == 0:
        return jsonify({"error": "Enroute entry not found"}), 404

    return jsonify({"message": "Enroute entry deleted successfully"}), 200

# PUT endpoint to update an enroute
@app.route('/ids/enroute/<enroute_id>', methods=['PUT'])
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
@app.route('/ids/enroute', methods=['POST'])
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

@app.route('/ids/controllers')
def get_center_controllers():
    try:
        doc = controller_cache.find_one({}, {"_id": 0})  # Exclude _id for cleaner response
        if not doc:
            return jsonify({"error": "No controller data available"}), 503
        
        return jsonify({
            "cacheUpdatedAt": doc.get("cacheUpdatedAt"),
            "controllers": doc.get("controllers", []),
            "tracon": doc.get("tracon", [])
        })
    except Exception as e:
        print(f"Error reading controller cache from MongoDB: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route('/ids/route-to-skyvector') #api 
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