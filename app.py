from flask import Flask, redirect, url_for, render_template, request, jsonify
import sqlite3
from datetime import timedelta
app = Flask(__name__)

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
        """, (destination,))

    else:
        cursor.execute("SELECT * FROM routes")
    
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        display_origin = origin if origin and origin in row[3] else row[0]
        routes.append({
            'origin': display_origin,
            'destination': row[1],
            'route': row[2],
            'altitude': row[3],
            'notes': row[4]
        })
    return render_template("search.html", routes=routes)
    

if __name__ == "__main__":
    app.run()

