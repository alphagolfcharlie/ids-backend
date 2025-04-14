from flask import Flask, redirect, url_for, render_template, request, jsonify, session, json, Response
import requests, re, sqlite3
from datetime import timedelta
from functools import wraps

app = Flask(__name__)

RUNWAY_FLOW_MAP = {
    "DTW": {
        "SOUTH": ["21","22"],
        "NORTH": ["3","4"],
        "WEST": ["27"]
    },
    # Add more airports if needed
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
        
        # Clean up the ATIS text to help matching
        atis_datis = atis_text['datis']

        # Look for any runway in the ATIS text and return the matching flow
        flow_config = RUNWAY_FLOW_MAP[airport_code]
        for flow_direction, runways in flow_config.items():
            for rwy in runways:
                # Match like "DEP RWY 21L" or "DEPARTURE RUNWAY 21L"
                if re.search(rf"DEPG RWY {rwy}[LRC]?", atis_datis):
                    return flow_direction.upper()
        print(f"No matching flow found for {airport_code}")

        return None
    except Exception as e:
        print(f"Flow detection error for {airport_code}: {e}")
        return None


@app.route("/")
def home():
    return render_template("index2.html")

@app.route("/SOPs")
def SOPs():
    return redirect("https://clevelandcenter.org/downloads")

@app.route("/refs")
def refs():
    return redirect("https://refs.clevelandcenter.org")


@app.route('/search', methods=['GET','POST'])
def search():

    origin = request.args.get('origin','').upper()
    destination = request.args.get('destination','').upper()
    
    routes = []
    conn = sqlite3.connect('routes.db')
    cursor = conn.cursor()

    if origin and destination:
        cursor.execute("""
            SELECT * FROM routes
            WHERE
                (origin = ? OR notes LIKE ?)
                AND destination = ?
        """, (origin,f"%{origin}%",destination))

    elif origin:
        cursor.execute("""
            SELECT * FROM routes
            WHERE 
                (origin = ? OR notes LIKE ?)
        """, (origin,f"%{origin}%"))

    elif destination:
        cursor.execute("""
            SELECT * FROM routes
            WHERE destination = ?
            ORDER BY origin ASC
        """, (destination,))

    else:
        cursor.execute(f"SELECT * FROM routes ORDER BY origin ASC, destination ASC")
    
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
                isActive = False
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
            'flow':CurrFlow or '',
            'isActive':isActive,
            'hasFlows':hasFlows
        })
    
    searched = True
    return render_template("search.html", routes=routes, searched=searched)    

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
    conn = sqlite3.connect('routes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT rowid, * FROM routes ORDER BY origin ASC, destination ASC")
    rows= cursor.fetchall()
    conn.close()
    return render_template("admin_routes.html",routes=rows)

@app.route('/admin/routes/add', methods=['GET', 'POST'])
@requires_auth
def add_route():
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
    conn = sqlite3.connect('routes.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM routes WHERE rowid=?", (route_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_routes'))


@app.route('/admin/routes/edit/<int:route_id>', methods=['GET', 'POST'])
@requires_auth
def edit_route(route_id):
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


if __name__ == "__main__":
    app.run()

