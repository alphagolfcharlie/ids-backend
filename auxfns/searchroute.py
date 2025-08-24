import os
from flask import json
from auxfns.wxflow import get_flow
from pymongo import MongoClient, DESCENDING
from collections import OrderedDict

from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

with open ("data/runway_flow.json", "r") as f:
    RUNWAY_FLOW_MAP = json.load(f)

client = MongoClient(MONGO_URI)

db = client["ids"]
routes_collection = db["routes"]
crossings_collection = db["crossings"]
faa_routes_collection = db["faa_prefroutes"]
fixes_collection = db["fixes"]
navaids_collection = db["navaids"]
airway_collection = db["airways"]
star_rte_collection = db["star_rte"]
dp_rte_collection = db["sid_rte"]
enroute_collection = db["enroute"]

def normalize(text):
    try:
        return ' '.join(str(text).strip().upper().split())
    except Exception:
        return ''

def searchroute(origin, destination):
    if len(origin) == 4 and origin.startswith('K'):
        origin = origin[1:]
    elif len(origin) == 4 and origin.startswith('C'):
        origin = origin[1:]
    if len(destination) == 4 and destination.startswith('K'):
        destination = destination[1:]
    elif len(destination) == 4 and destination.startswith('C'): 
        destination = destination[1:]

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

    # If both origin and destination are not provided, return only custom routes
    if not origin and not destination:
        custom_matches = list(routes_collection.find({}))
        faa_matches = []  # Skip FAA routes
    else:
        # Step 1: Fetch all matches
        custom_matches = list(routes_collection.find(query))

        # FAA query
        faa_query = {}
        if origin and destination:
            faa_query = {
                "$and": [
                    {"$or": [
                        {"Orig": origin},
                        {"Area": {"$regex": origin, "$options": "i"}}
                    ]},
                    {"Dest": destination}
                ]
            }
        elif origin:
            faa_query = {
                "$or": [
                    {"Orig": origin},
                    {"Area": {"$regex": origin, "$options": "i"}}
                ]
            }
        elif destination:
            faa_query = {"Dest": destination}

        faa_matches = list(faa_routes_collection.find(faa_query))

    # Step 2: Prepare deduplication dictionary
    routes_dict = OrderedDict()

    # Step 3: Insert custom routes first
    for row in custom_matches:
        route_string = normalize(row.get("route", ""))
        route_origin = row.get("origin", "").upper()
        route_destination = row.get("destination", "").upper()
        route_notes = row.get("notes", "")
        key = (route_origin, route_destination, route_string)

        CurrFlow = ''
        isActive = False
        hasFlows = False
        eventRoute = 'EVENT' in route_notes.upper()

        if destination in RUNWAY_FLOW_MAP:
            hasFlows = True
            CurrFlow = get_flow(destination)
            if CurrFlow and CurrFlow.upper() in route_notes.upper():
                isActive = True

        routes_dict[key] = {
            '_id': str(row['_id']),  # Add ID
            'origin': route_origin,
            'destination': route_destination,
            'route': route_string,
            'altitude': row.get("altitude", ""),
            'notes': route_notes,
            'flow': CurrFlow or '',
            'isActive': isActive,
            'hasFlows': hasFlows,
            'source': 'custom',
            'isEvent': eventRoute
        }

    # Step 4: Overwrite duplicates with FAA routes (only if origin and destination are provided)
    if origin or destination:
        for row in faa_matches:
            route_string = normalize(row.get("Route String", ""))
            route_origin = origin.upper()
            route_destination = destination.upper()
            key = (route_origin, route_destination, route_string)

            isActive = False
            hasFlows = False
            flow = ''
            direction = row.get("Direction", "")

            if direction and destination in RUNWAY_FLOW_MAP:
                hasFlows = True
                flow = get_flow(destination)
                if flow and flow.upper() in direction.upper():
                    isActive = True
            
            fields = [row.get("Area", ""), row.get("Direction", ""), row.get("Aircraft", "")]
            notes = ', '.join(filter(None, fields))


            # Check if custom route already exists for this key
            custom_altitude = ''
            if key in routes_dict and routes_dict[key]['source'] == 'custom':
                custom_altitude = routes_dict[key].get('altitude', '')

            routes_dict[key] = {
                'origin': route_origin,
                'destination': route_destination,
                'route': route_string,
                'altitude': custom_altitude,  # retain custom altitude if present
                'notes': notes,
                'flow': flow,
                'isActive': isActive,
                'hasFlows': hasFlows,
                'source': 'faa',
                'isEvent': False
            }

    def sort_priority(route):
        if route['isEvent']:
            return 0
        elif route['isActive']:
            return 1
        elif route['source'] == 'custom':
            return 2
        else:
            return 3

    sorted_routes = sorted(routes_dict.values(), key=sort_priority)
    return sorted_routes    