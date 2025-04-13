from flask import Flask, redirect, url_for, render_template, request, g
import sqlite3
from datetime import timedelta
app = Flask(__name__)

DATABASE = '/database.db'

def get_db():
    db = getattr(g, '_database',None)
    if db is None:
        return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g,'_database',None)
    if db is not None:
        db.close()


name = "Bob"
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
@app.route("/logout")
def logout():
    return redirect(url_for("login"))
if __name__ == "__main__":
    app.run()
