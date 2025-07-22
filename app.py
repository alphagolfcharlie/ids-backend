from flask import Flask, redirect, url_for, render_template, request, jsonify, session, json, Response
import requests, re, sqlite3, random
from datetime import timedelta
from functools import wraps
from math import radians, cos, sin, asin, sqrt
from dist import getCoords
import urllib.parse
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv

load_dotenv()



app = Flask(__name__)

def is_api_request():
    return request.host.startswith("api.")

RUNWAY_FLOW_MAP = {
    "DTW": {
        "SOUTH": ["21", "22"],
        "NORTH": ["3", "4"],
        "WEST": ["27"]
    },
}


MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)

db = client["ids"]
routes_collection = db["routes"]
crossings_collection = db["crossings"]
faa_routes_collection = db["faa_prefroutes"]



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
        return None
    except Exception as e:
        print(f"Flow detection error for {airport_code}: {e}")
        return None

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

    cursor = routes_collection.find(query).sort([("origin", 1), ("destination", 1)])
    routes = []

    for row in cursor:
        CurrFlow = ''
        isActive = False
        hasFlows = False
        route_origin = row.get('origin')
        route_notes = row.get('notes', '')

        if destination in RUNWAY_FLOW_MAP:
            hasFlows = True
            CurrFlow = get_flow(destination)
            if CurrFlow and CurrFlow.upper() in route_notes.upper():
                isActive = True

        if origin and origin in route_notes:
            route_origin = origin

        routes.append({
            'origin': route_origin,
            'destination': row.get('destination'),
            'route': row.get('route'),
            'altitude': row.get('altitude'),
            'notes': route_notes,
            'flow': CurrFlow or '',
            'isActive': isActive,
            'hasFlows': hasFlows,
            'source': 'custom'  
        })

    # FAA routes
    faa_matches = list(faa_routes_collection.find({
        "Orig": origin,
        "Dest": destination
    }))

    for row in faa_matches:
        routes.append({
            'origin': origin,
            'destination': destination,
            'route': row.get("Route String", ""),
            'altitude': '',  
            'notes': row.get("Area", ""),
            'flow': '',
            'isActive': False,
            'hasFlows': False,
            'source': 'faa'  
        })

    return routes

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

@app.route('/aircraft')
def aircraft():
    if is_api_request():
        return "Not available on API subdomain", 404
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