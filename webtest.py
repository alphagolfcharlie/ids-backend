from flask import Flask
app = Flask(__name__)
if __name__ == "main":
    app.run()

@app.route('/')
def home():
    return "Hello! This is an initial test <h1>HELLO</h1>"