from flask import Flask, redirect, url_for, render_template, request
app = Flask(__name__)
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
    
@app.route("/<abc>",methods=["POST","GET"])
def user(abc):
    return f"welcome to the site"
if __name__ == "__main__":
    app.run()
