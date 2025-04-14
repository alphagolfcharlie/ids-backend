from flask import Flask, redirect, url_for, render_template, request, jsonify, session, json
import requests
import re
import sqlite3
from datetime import timedelta
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
        route_origin = row[0]
        route_notes = row[4]

        flow = ''
        if destination in RUNWAY_FLOW_MAP:
            CurrFlow = get_flow(destination)
            if CurrFlow.upper() in route_notes.upper():
                isActive = True
            else:
                isActive = False
        if origin and origin in route_notes:
            route_origin = origin
        

        routes.append({
            'origin': route_origin,
            'destination': row[1],
            'route': row[2],
            'altitude': row[3],
            'notes': route_notes,
            'flow':CurrFlow or '',
            'isActive':isActive 
        })
    
    searched = True
    return render_template("search.html", routes=routes, searched=searched)    





if __name__ == "__main__":
    app.run()

