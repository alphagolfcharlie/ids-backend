from flask import Flask, redirect, url_for, render_template, request, jsonify, session, json, Response
import requests, re, sqlite3, random
from datetime import timedelta
from functools import wraps
from math import radians, cos, sin, asin, sqrt
from dist import getCoords
import urllib.parse

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
    routes = []
    conn = sqlite3.connect('routes.db')
    cursor = conn.cursor()

    if origin and destination:
        cursor.execute("""
            SELECT * FROM routes
            WHERE (origin = ? OR notes LIKE ?) AND destination = ?
        """, (origin, f"%{origin}%", destination))
    elif origin:
        cursor.execute("""
            SELECT * FROM routes
            WHERE (origin = ? OR notes LIKE ?)
        """, (origin, f"%{origin}%"))
    elif destination:
        cursor.execute("""
            SELECT * FROM routes
            WHERE destination = ?
            ORDER BY origin ASC
        """, (destination,))
    else:
        cursor.execute("SELECT * FROM routes ORDER BY origin ASC, destination ASC")

    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        CurrFlow = ''
        isActive = False
        hasFlows = False
        route_origin = row[0]
        route_notes = row[4]

        flow = ''
        if destination in RUNWAY_FLOW_MAP:
            hasFlows = True
            CurrFlow = get_flow(destination)
            if CurrFlow and CurrFlow.upper() in route_notes.upper():
                isActive = True
        else:
            hasFlows = False
        if origin and origin in route_notes:
            route_origin = origin

        routes.append({
            'origin': route_origin,
            'destination': row[1],
            'route': row[2],
            'altitude': row[3],
            'notes': route_notes,
            'flow': CurrFlow or '',
            'isActive': isActive,
            'hasFlows': hasFlows
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
        from flask import request
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
    conn = sqlite3.connect('routes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT rowid, * FROM routes ORDER BY origin ASC, destination ASC")
    rows= cursor.fetchall()
    conn.close()
    return render_template("admin_routes.html", routes=rows)

@app.route('/admin/routes/add', methods=['GET', 'POST'])
@requires_auth
def add_route():
    if is_api_request():
        return "Admin unavailable via API domain", 403
    if request.method == 'POST':
        origin = request.form['origin']
        destination = request.form['destination']
        route = request.form['route']
        altitude = request.form['altitude']
        notes = request.form['notes']

        conn = sqlite3.connect('routes.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO routes (origin, destination, route, altitude, notes) VALUES (?, ?, ?, ?, ?)",
                       (origin, destination, route, altitude, notes))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_routes'))
    return render_template("edit_route.html", action="Add")

@app.route('/admin/routes/delete/<int:route_id>')
@requires_auth
def delete_route(route_id):
    if is_api_request():
        return "Admin unavailable via API domain", 403
    conn = sqlite3.connect('routes.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM routes WHERE rowid=?", (route_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_routes'))

@app.route('/admin/routes/edit/<int:route_id>', methods=['GET', 'POST'])
@requires_auth
def edit_route(route_id):
    if is_api_request():
        return "Admin unavailable via API domain", 403
    conn = sqlite3.connect('routes.db')
    cursor = conn.cursor()
    if request.method == 'POST':
        origin = request.form['origin']
        destination = request.form['destination']
        route = request.form['route']
        altitude = request.form['altitude']
        notes = request.form['notes']
        cursor.execute("""
            UPDATE routes SET origin=?, destination=?, route=?, altitude=?, notes=?
            WHERE rowid=?
        """, (origin, destination, route, altitude, notes, route_id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_routes'))

    cursor.execute("SELECT * FROM routes WHERE rowid=?", (route_id,))
    row = cursor.fetchone()
    conn.close()
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
    crossings = []
    conn = sqlite3.connect('crossings.db')
    cursor = conn.cursor()

    if destination:
        cursor.execute("""
            SELECT * FROM crossings
            WHERE destination = ?""", (destination,))
    else:
        cursor.execute("SELECT * FROM crossings ORDER BY destination ASC")
    
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        crossings.append({
            'destination': row[0],
            'fix': row[1],
            'restriction': row[2],
            'notes': row[3],
            'artcc': row[4]
        })

    searched = True
    return render_template("crossings.html", crossings=crossings)

@app.route('/admin/crossings')
@requires_auth
def admin_crossings():
    if is_api_request():
        return "Admin unavailable via API domain", 403
    conn = sqlite3.connect('crossings.db')
    cursor = conn.cursor()
    cursor.execute("SELECT rowid, * FROM crossings ORDER BY destination ASC")
    rows = cursor.fetchall()
    conn.close()
    return render_template("admin_crossings.html", crossings=rows)

@app.route('/admin/crossings/add', methods=['GET', 'POST'])
@requires_auth
def add_crossing():
    if is_api_request():
        return "Admin unavailable via API domain", 403
    if request.method == 'POST':
        destination = request.form['destination']
        fix = request.form['fix']
        restriction = request.form['restriction']
        notes = request.form['notes']
        artcc = request.form['artcc']

        conn = sqlite3.connect('crossings.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO crossings (destination, bdry_fix, restriction, notes, artcc) VALUES (?, ?, ?, ?, ?)",
                       (destination, fix, restriction, notes, artcc))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_crossings'))
    return render_template("edit_crossing.html", action="Add")

@app.route('/admin/crossings/delete/<int:crossing_id>')
@requires_auth
def delete_crossing(crossing_id):
    if is_api_request():
        return "Admin unavailable via API domain", 403
    conn = sqlite3.connect('crossings.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM crossings WHERE rowid=?", (crossing_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_crossings'))

@app.route('/admin/crossings/edit/<int:crossing_id>', methods=['GET', 'POST'])
@requires_auth
def edit_crossing(crossing_id):
    if is_api_request():
        return "Admin unavailable via API domain", 403
    conn = sqlite3.connect('crossings.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        destination = request.form['destination']
        fix = request.form['fix']
        restriction = request.form['restriction']
        notes = request.form['notes']
        artcc = request.form['artcc']

        cursor.execute("""
            UPDATE crossings SET destination=?, bdry_fix=?, restriction=?, notes=?, artcc=? 
            WHERE rowid=?
        """, (destination, fix, restriction, notes, artcc, crossing_id))

        conn.commit()
        conn.close()
        return redirect(url_for('admin_crossings'))

    cursor.execute("SELECT * FROM crossings WHERE rowid=?", (crossing_id,))
    row = cursor.fetchone()
    conn.close()
    return render_template("edit_crossing.html", crossing=row, action="Edit")

@app.route('/route-to-skyvector')
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

if __name__ == "__main__":
    app.run()
