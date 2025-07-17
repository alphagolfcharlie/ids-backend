import json, random

rancid = random.randint(000,999)
rancid = str(rancid)
ranbcn = random.randint(0000,7777)
ranbcn = str(ranbcn)
spd = random.randint(200,500)
spd = str(spd)

def load_data(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_data(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def add_flight_plan(filepath):
    incorrect = {
        "aid": input("Aircraft ID: "),
        "cid": rancid,
        "bcn": ranbcn,
        "typ": input("Aircraft Type: "),
        "eq": input("Equipment: "),
        "dep": input("Departure: "),
        "dest": input("Destination: "),
        "spd": spd,
        "alt": input("Altitude (incorrect): "),
        "rte": input("Route (incorrect): "),
    }

    correct = {
        "rte": input("Correct Route: "),
        "alt": input("Correct Altitude: ")
    }

    data = load_data(filepath)
    data.append({"incorrect": incorrect, "correct": correct})
    save_data(filepath, data)
    print("Flight plan added successfully.")

while True:
    add_flight_plan('data/flight_plans.json')
