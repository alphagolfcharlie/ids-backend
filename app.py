from flask import Flask, redirect, url_for, render_template, request, jsonify, session, json, Response
import requests, re, sqlite3, random
from datetime import timedelta
from functools import wraps
from math import radians, cos, sin, asin, sqrt
from dist import getCoords
import urllib.parse
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv
from collections import OrderedDict
from flask_cors import CORS


load_dotenv()



app = Flask(__name__)

# Allow requests from localhost:5173 only (for development)
CORS(app, resources={r"/api/*": {"origins": [
    "http://localhost:5173",
    "https://idsnew.vercel.app"
]}})
def is_api_request():
    return request.host.startswith("api.")

RUNWAY_FLOW_MAP = {
    "DTW": {
        "SOUTH": ["21", "22"],
        "NORTH": ["3", "4"],
        "WEST": ["27"]
    },
    "ATL": {
        "WEST": ["26","27","28"],
        "EAST": ["8","9","10"]
    },
    "DFW": {
        "SOUTH": ["18","17"],
        "NORTH": ["36","35"]
    },
    "BUF": {
        "WEST": ["23"],
        "EAST": ["5"]
    },    
    "CLE": {
        "SOUTH": ["24"],
        "NORTH": ["6"]
    },
    "PIT": {
        "WEST": ["28","32"],
        "EAST": ["10","14"]
    },
}


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

@app.route("/api/airport_info")
def airport_info():
    airports = ["KDTW", "KCLE", "KPIT", "KBUF"]
    data = {}
    for airport in airports:
        code = airport.replace("K", "")
        data[airport] = {
            "metar": get_metar(airport),
            "atis": get_atis(code),
            "flow": "Normal",  # Placeholder for your custom flow logic
        }
    return jsonify(data)

@app.route("/")
def home():
    if is_api_request():
        return jsonify({"message": "API"}), 200
    return render_template("index.html")

@app.route("/SOPs")
def SOPs():
    if is_api_request():
        return "Not available on API subdomain", 404
    return redirect("https://clevelandcenter.org/downloads")

@app.route("/refs")
def refs():
    if is_api_request():
        return "Not available on API subdomain", 404
    return redirect("https://refs.clevelandcenter.org")

@app.route('/search', methods=['GET','POST'])
def search():
    if is_api_request():
        return "Not available on API subdomain", 404

    origin = request.args.get('origin','').upper()
    destination = request.args.get('destination','').upper()
    routes = searchroute(origin, destination)
    searched = True
    return render_template("search.html", routes=routes, searched=searched)

def normalize(text):
    try:
        return ' '.join(str(text).strip().upper().split())
    except Exception:
        return ''

@app.route('/api/routes')
def api_routes():
    origin = request.args.get('origin', '').upper()
    destination = request.args.get('destination', '').upper()
    routes = searchroute(origin, destination)

    return jsonify(routes)


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

def searchroute(origin, destination):
    query = {}
    if origin and destination:
        query = {
            "$and": [
                {"$or": [
                    {"origin": origin},
                    {"notes": {"$regex": origin, "$options": "i"}}
                ]},
                {"destination": destination}
            ]
        }
    elif origin:
        query = {"$or": [
            {"origin": origin},
            {"notes": {"$regex": origin, "$options": "i"}}
        ]}
    elif destination:
        query = {"destination": destination}

    # FAA query
    faa_query = {}
    if origin and destination:
        faa_query = {
            "$and": [
                {"$or": [
                    {"Orig": origin},
                    {"Area": {"$regex": origin, "$options": "i"}}
                ]},
                {"Dest": destination}
            ]
        }
    elif origin:
        faa_query = {
            "$or": [
                {"Orig": origin},
                {"Area": {"$regex": origin, "$options": "i"}}
            ]
        }
    elif destination:
        faa_query = {"Dest": destination}

    # Step 1: Fetch all matches
    custom_matches = list(routes_collection.find(query))
    faa_matches = list(faa_routes_collection.find(faa_query))

    # Step 2: Prepare deduplication dictionary
    routes_dict = OrderedDict()

    # Step 3: Insert custom routes first
    for row in custom_matches:
        route_string = normalize(row.get("route", ""))
        route_origin = row.get("origin", "").upper()
        route_destination = row.get("destination", "").upper()
        route_notes = row.get("notes", "")
        key = (route_origin, route_destination, route_string)

        CurrFlow = ''
        isActive = False
        hasFlows = False
        eventRoute = 'EVENT' in route_notes.upper()

        if destination in RUNWAY_FLOW_MAP:
            hasFlows = True
            CurrFlow = get_flow(destination)
            if CurrFlow and CurrFlow.upper() in route_notes.upper():
                isActive = True

        routes_dict[key] = {
            'origin': route_origin,
            'destination': route_destination,
            'route': route_string,
            'altitude': row.get("altitude", ""),
            'notes': route_notes,
            'flow': CurrFlow or '',
            'isActive': isActive,
            'hasFlows': hasFlows,
            'source': 'custom',
            'isEvent': eventRoute
        }

    # Step 4: Overwrite duplicates with FAA routes
    for row in faa_matches:
        route_string = normalize(row.get("Route String", ""))
        route_origin = origin.upper()
        route_destination = destination.upper()
        key = (route_origin, route_destination, route_string)

        isActive = False
        hasFlows = False
        flow = ''
        direction = row.get("Direction", "")

        if direction and destination in RUNWAY_FLOW_MAP:
            hasFlows = True
            flow = get_flow(destination)
            if flow and flow.upper() in direction.upper():
                isActive = True

        routes_dict[key] = {
            'origin': route_origin,
            'destination': route_destination,
            'route': route_string,
            'altitude': '',
            'notes': row.get("Area", ""),
            'flow': flow,
            'isActive': isActive,
            'hasFlows': hasFlows,
            'source': 'faa',
            'isEvent': False
        }

    def sort_priority(route):
        if route['isEvent']:
            return 0
        elif route['isActive']:
            return 1
        elif route['source'] == 'custom':
            return 2
        else:
            return 3

    sorted_routes = sorted(routes_dict.values(), key=sort_priority)
    return sorted_routes

def check_auth(username, password): 
    return username == 'admin' and password == 'password'

def authenticate():
    return Response(
        'Access denied. Provide correct credentials.', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/routes')
@requires_auth
def admin_routes():
    if is_api_request():
        return "Admin unavailable via API domain", 403
    rows = list(routes_collection.find())
    return render_template("admin_routes.html", routes=rows)

@app.route('/admin/routes/add', methods=['GET', 'POST'])
@requires_auth
def add_route():
    if is_api_request():
        return "Admin unavailable via API domain", 403
    if request.method == 'POST':
        routes_collection.insert_one({
            "origin": request.form['origin'],
            "destination": request.form['destination'],
            "route": request.form['route'],
            "altitude": request.form['altitude'],
            "notes": request.form['notes']
        })
        return redirect(url_for('admin_routes'))
    return render_template("edit_route.html", action="Add")

@app.route('/admin/routes/delete/<route_id>')
@requires_auth
def delete_route(route_id):
    if is_api_request():
        return "Admin unavailable via API domain", 403
    routes_collection.delete_one({"_id": ObjectId(route_id)})
    return redirect(url_for('admin_routes'))

@app.route('/admin/routes/edit/<route_id>', methods=['GET', 'POST'])
@requires_auth
def edit_route(route_id):
    if is_api_request():
        return "Admin unavailable via API domain", 403
    if request.method == 'POST':
        routes_collection.update_one(
            {"_id": ObjectId(route_id)},
            {"$set": {
                "origin": request.form['origin'],
                "destination": request.form['destination'],
                "route": request.form['route'],
                "altitude": request.form['altitude'],
                "notes": request.form['notes']
            }}
        )
        return redirect(url_for('admin_routes'))
    row = routes_collection.find_one({"_id": ObjectId(route_id)})
    return render_template("edit_route.html", route=row, action="Edit")

@app.route('/map')
def show_map():
    if is_api_request():
        return "Not available on API subdomain", 404
    return render_template("map.html")

@app.route('/api/aircraft')
def aircraft():
    acarr = getCoords()
    return jsonify(acarr)

@app.route('/crossings')
def crossings():
    if is_api_request():
        return "Not available on API subdomain", 404

    destination = request.args.get('destination','').upper()
    query = {"destination": destination} if destination else {}
    rows = crossings_collection.find(query).sort("destination", 1)

    crossings = []
    for row in rows:
        crossings.append({
            'destination': row.get('destination'),
            'fix': row.get('bdry_fix'),
            'restriction': row.get('restriction'),
            'notes': row.get('notes'),
            'artcc': row.get('artcc')
        })

    searched = True
    return render_template("crossings.html", crossings=crossings)


@app.route('/api/crossings')
def api_crossings():
    destination = request.args.get('destination', '').upper()
    query = {"destination": destination} if destination else {}
    rows = crossings_collection.find(query).sort("destination", 1)

    crossings = []
    for row in rows:
        crossings.append({
            'destination': row.get('destination'),
            'fix': row.get('bdry_fix'),
            'restriction': row.get('restriction'),
            'notes': row.get('notes'),
            'artcc': row.get('artcc')
        })

    return jsonify(crossings)


@app.route('/api/enroute')
def api_enroute():
    field = request.args.get('field', '').upper()
    area = request.args.get('area', '').strip()
    qualifier = request.args.get('qualifier','').strip()

    if not field:
        return jsonify({"error": "field is required"}), 400

    # MongoDB query
    query = {
        "Field": {"$regex": field, "$options": "i"}
    }

    if area:
        query["Areas"] = {"$regex": area, "$options": "i"}

 
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
                'field': result_tuple[0],
                'qualifier': result_tuple[1],
                'areas': result_tuple[2],
                'rule': result_tuple[3]
            })

    return jsonify(results)
    

@app.route('/admin/crossings')
@requires_auth
def admin_crossings():
    if is_api_request():
        return "Admin unavailable via API domain", 403
    rows = list(crossings_collection.find())
    return render_template("admin_crossings.html", crossings=rows)

@app.route('/admin/crossings/add', methods=['GET', 'POST'])
@requires_auth
def add_crossing():
    if is_api_request():
        return "Admin unavailable via API domain", 403
    if request.method == 'POST':
        crossings_collection.insert_one({
            "destination": request.form['destination'],
            "bdry_fix": request.form['fix'],
            "restriction": request.form['restriction'],
            "notes": request.form['notes'],
            "artcc": request.form['artcc']
        })
        return redirect(url_for('admin_crossings'))
    return render_template("edit_crossing.html", action="Add")

@app.route('/admin/crossings/delete/<crossing_id>')
@requires_auth
def delete_crossing(crossing_id):
    if is_api_request():
        return "Admin unavailable via API domain", 403
    crossings_collection.delete_one({"_id": ObjectId(crossing_id)})
    return redirect(url_for('admin_crossings'))

@app.route('/admin/crossings/edit/<crossing_id>', methods=['GET', 'POST'])
@requires_auth
def edit_crossing(crossing_id):
    if is_api_request():
        return "Admin unavailable via API domain", 403
    if request.method == 'POST':
        crossings_collection.update_one(
            {"_id": ObjectId(crossing_id)},
            {"$set": {
                "destination": request.form['destination'],
                "bdry_fix": request.form['fix'],
                "restriction": request.form['restriction'],
                "notes": request.form['notes'],
                "artcc": request.form['artcc']
            }}
        )
        return redirect(url_for('admin_crossings'))
    row = crossings_collection.find_one({"_id": ObjectId(crossing_id)})
    return render_template("edit_crossing.html", crossing=row, action="Edit")


@app.route('/route-to-skyvector') #api 
def route_to_skyvector():
    if not is_api_request():
        return "This endpoint is only available on api.alphagolfcharlie.dev", 403

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

with open('data/flight_plans.json') as f: 
    flight_plans = json.load(f)

@app.route('/flightdata')
def flightdata():
    plan = random.choice(flight_plans)
    return render_template('trainer.html', plan=plan['incorrect'], correct=plan['correct'])


def normalize_route(s):
    return ' '.join(s.upper().split())

@app.route('/trainer/check', methods=['POST'])
def check_trainer():
    data = request.json

    def normalize(text):
        return ' '.join(text.upper().split())

    rte_input = normalize(data.get('rte', ''))
    alt_input = data.get('alt', '').strip()

    # Get correct values from the form POST data
    correct_rtes = data.get('correct_rte')
    correct_alts = data.get('correct_alt')

    # Handle multiple correct values (list or string)
    correct_rte_list = eval(correct_rtes) if correct_rtes.startswith("[") else [correct_rtes]
    correct_alt_list = eval(correct_alts) if correct_alts.startswith("[") else [correct_alts]

    rte_correct = rte_input in [normalize(r) for r in correct_rte_list]
    alt_correct = alt_input in [str(a).strip() for a in correct_alt_list]

    return jsonify({
        'rte_correct': rte_correct,
        'alt_correct': alt_correct
    })

@app.route('/checkroute')
def checkroute():
    #if not is_api_request():
        #return jsonify({
            #"status": "error",
            #"message": "This endpoint is only available on api.alphagolfcharlie.dev"
       # }), 403

    callsign = request.args.get('callsign', '').upper().strip()
    if not callsign:
        return jsonify({
            "status": "error",
            "message": "Missing 'callsign' parameter"
        }), 400

    try:
        print(f"Looking for: {callsign}")
        datafeed = "https://data.vatsim.net/v3/vatsim-data.json"
        response = requests.get(datafeed, timeout=5)
        data = response.json()

        for pilot in data.get('pilots', []):
            if pilot.get('callsign', '').upper() == callsign:
                fp = pilot.get('flight_plan')
                if not fp:
                    return jsonify({
                        "status": "not_found",
                        "message": f"No flight plan found for {callsign}"
                    }), 404

                origin = fp.get("departure", "").strip().upper()[1:]
                destination = fp.get("arrival", "").strip().upper()[1:]
                route = fp.get("route", "").strip().upper()

                if not (origin and destination):
                    return jsonify({
                        "status": "error",
                        "message": "Flight plan is missing departure or arrival"
                    }), 400

                def normalize(r): return ' '.join(r.upper().split())
                route_normalized = normalize(route)

                # --- Search your custom routes DB
                custom_matches = list(routes_collection.find({
                    "$and": [
                        {"destination": destination},
                        {"$or": [
                            {"origin": origin},
                            {"notes": {"$regex": origin, "$options": "i"}}
                        ]}
                    ]
                }))
                custom_normalized = [normalize(row.get("route", "")) for row in custom_matches]

                # --- Search FAA preferred routes DB
                faa_matches = list(faa_routes_collection.find({
                    "Orig": origin,
                    "Dest": destination
                }))

                faa_normalized = [normalize(row.get("Route String", "")) for row in faa_matches]


                is_valid = route_normalized in custom_normalized or route_normalized in faa_normalized


                faa_routes = [
                {
                    "route": row.get("Route String", ""),
                    "type": row.get("Type", ""),
                    "aircraft": row.get("Aircraft", ""),
                    "area": row.get("Area", ""),
                    "acntr": row.get("ACNTR", ""),
                    "dcntr": row.get("DCNTR", "")
                }
                for row in faa_matches
                ]

                return jsonify({
                    "status": "valid" if is_valid else "invalid",
                    "filed_route": route,
                    "origin": origin,
                    "destination": destination,
                    "message": (
                        f"Route is valid for {origin} to {destination}"
                        if is_valid else
                        f"Filed route does not match known routes for {origin} to {destination}"
                    ),
                    "valid_routes": [row.get("route", "") for row in custom_matches],
                    "faa_routes": faa_routes
                }), 200

        return jsonify({
            "status": "not_found",
            "message": f"Callsign {callsign} not found in VATSIM data"
        }), 404

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }), 500

if __name__ == "__main__":
    app.run()