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

@app.route("/admin")
def admin():
    return redirect(url_for("usern", name="Admin!"))

@app.route("/login",methods=["POST","GET"])
def login():
    if request.method == "POST": 
        user = request.form.get("nm")
        return redirect(url_for("user",abc=user))
    else:
        return render_template("login.html")
    
@app.route("/user",methods=["POST","GET"])
def user():
    return redirect(url_for("IDS"))

@app.route("/IDS")
def IDS():
    return redirect("https://refs.clevelandcenter.org")

@app.route('/routes', methods=['GET'])
def get_routes():
    origin = request.args.get('origin')
    destination = request.args.get('destination')

    conn = sqlite3.connect('routes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM routes WHERE 1=1"
    params = []

    if origin:
        query += " AND origin = ?"
        params.append(origin.upper())

    if destination:
        query += " AND destination = ?"
        params.append(destination.upper())

    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()

    if results:
        return jsonify([dict(row) for row in results])
    else:
        return jsonify({"message": "No matching routes found, sorry!"}), 404

if __name__ == "__main__":
    app.run()
