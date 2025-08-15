from fastapi import FastAPI, HTTPException, Depends, Query, Body, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
import requests, re, threading, time, os, jwt, datetime, urllib.parse
from functools import wraps
from auxfns.searchroute import searchroute
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from bson.json_util import dumps  # Helps with MongoDB's ObjectId serialization
from dotenv import load_dotenv
from google.oauth2 import id_token
from google.auth.transport.requests import Request 
from math import radians, cos, sin, asin, sqrt
from update_cache import finddist

import os
from pymongo import MongoClient

# load environment variables 

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
SECRET_KEY = os.getenv("SECRET_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
AUTHORIZED_EMAILS = os.getenv("AUTHORIZED_EMAILS", "").split(",")
ATIS_AIRPORTS = os.getenv("ATIS_AIRPORTS", "").split(",")


# load DBs 

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

atis_cache = db["atis_cache"]
controller_cache = db["controller_cache"]
aircraft_cache = db["aircraft_cache"]


app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://idsnew.vercel.app",
        "https://ids.alphagolfcharlie.dev",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import json
with open("data/runway_flow.json", "r") as f:
    RUNWAY_FLOW_MAP = json.load(f)

client = MongoClient(MONGO_URI)


#jwt required
def jwt_required(token: str = Depends(lambda: None)):
    from fastapi import Request as FastRequest
    from fastapi.security import HTTPBearer
    auth = HTTPBearer(auto_error=False)
    async def verify(request: FastRequest):
        credentials = await auth(request)
        if not credentials:
            raise HTTPException(status_code=401, detail="Token is missing")
        try:
            jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    return verify

#google login 
@app.post("/api/google-login")
async def google_login(data: dict = Body(...)):
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token is missing")

    try:
        request_adapter = Request()
        idinfo = id_token.verify_oauth2_token(token, request_adapter, GOOGLE_CLIENT_ID)
        email = idinfo.get("email")
        name = idinfo.get("name")
        if email not in AUTHORIZED_EMAILS:
            raise HTTPException(status_code=403, detail="Unauthorized user")

        custom_token = jwt.encode(
            {
                "email": email,
                "name": name,
                "role": "admin",
                "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
            },
            SECRET_KEY,
            algorithm="HS256",
        )
        return {"message": "Login successful", "token": custom_token}

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")



@app.get("/api/airport_info")
async def airport_info():
    try:
        latest_cache = atis_cache.find_one(sort=[("updatedAt", -1)])
        if not latest_cache:
            raise HTTPException(status_code=503, detail="No airport info available")
        latest_cache["_id"] = str(latest_cache["_id"])
        return json.loads(dumps(latest_cache))
    except Exception as e:
        raise HTTPException(status_code=503, detail="No airport info available")


@app.get("/api/routes")
async def api_routes(origin: str = "", destination: str = ""):
    routes = searchroute(origin.upper(), destination.upper())
    return routes


@app.put("/api/routes/{route_id}")
async def update_route(route_id: str, data: dict = Body(...), token=Depends(jwt_required)):
    result = await routes_collection.update_one(
        {"_id": ObjectId(route_id)},
        {"$set": {
            "origin": data.get('origin'),
            "destination": data.get('destination'),
            "route": data.get('route'),
            "altitude": data.get('altitude'),
            "notes": data.get('notes'),
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"message": "Route updated successfully"}

@app.delete("/api/routes/{route_id}")
async def delete_route(route_id: str, token=Depends(jwt_required)):
    result = await routes_collection.delete_one({"_id": ObjectId(route_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"message": "Route deleted successfully"}

@app.post("/api/routes")
async def create_route(data: dict = Body(...), token=Depends(jwt_required)):
    required_fields = ['origin', 'destination', 'route', 'notes']
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"'{field}' is required")
    result = await routes_collection.insert_one({
        "origin": data['origin'],
        "destination": data['destination'],
        "route": data['route'],
        "altitude": data.get('altitude', ''),
        "notes": data['notes'],
    })
    return {"message": "Route created successfully", "route_id": str(result.inserted_id)}

@app.put("/api/routes/{route_id}")
async def update_route(route_id: str, data: dict = Body(...), token=Depends(jwt_required)):
    result = await routes_collection.update_one(
        {"_id": ObjectId(route_id)},
        {"$set": {
            "origin": data.get('origin'),
            "destination": data.get('destination'),
            "route": data.get('route'),
            "altitude": data.get('altitude'),
            "notes": data.get('notes'),
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"message": "Route updated successfully"}

@app.delete("/api/routes/{route_id}")
async def delete_route(route_id: str, token=Depends(jwt_required)):
    result = await routes_collection.delete_one({"_id": ObjectId(route_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"message": "Route deleted successfully"}


@app.post("/api/routes")
async def create_route(data: dict = Body(...), token=Depends(jwt_required)):
    required_fields = ['origin', 'destination', 'route',]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"'{field}' is required")
    result = await routes_collection.insert_one({
        "origin": data['origin'],
        "destination": data['destination'],
        "route": data['route'],
        "altitude": data.get('altitude', ''),
        "notes": data['notes'],
    })
    return {"message": "Route created successfully", "route_id": str(result.inserted_id)}

@app.get("/api/star")
async def get_star_transition(code: str = Query(..., description="STAR transition code")):
    code = code.upper()

    # Shared ARPT_RWY_ASSOC filter
    runway_filter = {
        "$or": [
            {"ARPT_RWY_ASSOC": {"$exists": False}},
            {"ARPT_RWY_ASSOC": ""},
            {"ARPT_RWY_ASSOC": {"$not": re.compile(r"/")}}
        ]
    }

    # First try: search by TRANSITION_COMPUTER_CODE
    rte_cursor = await star_rte_collection.find(
        {"TRANSITION_COMPUTER_CODE": code, **runway_filter}
    ).sort("POINT_SEQ", DESCENDING).to_list(length=None)

    # If no results, search by STAR_COMPUTER_CODE
    if not rte_cursor:
        rte_cursor = await star_rte_collection.find(
            {
                "STAR_COMPUTER_CODE": code,
                "ROUTE_NAME": {"$not": re.compile(r"TRANSITION", re.IGNORECASE)},
                **runway_filter
            }
        ).sort("POINT_SEQ", DESCENDING).to_list(length=None)

    # Collect unique waypoints
    waypoints = []
    for doc in rte_cursor:
        point = doc.get("POINT")
        if point and point not in waypoints:
            waypoints.append(point)

    # If no waypoints, fallback
    if not waypoints:
        if "." in code:
            _, after_dot = code.split(".", 1)
            return {"transition": code, "waypoints": [after_dot]}
        else:
            raise HTTPException(status_code=404, detail=f"No valid waypoints found for {code}")

    return {"transition": code, "waypoints": waypoints}

@app.get("/api/star")
async def get_star_transition(code: str = Query(..., description="STAR transition code")):
    code = code.upper()

    # Shared ARPT_RWY_ASSOC filter
    runway_filter = {
        "$or": [
            {"ARPT_RWY_ASSOC": {"$exists": False}},
            {"ARPT_RWY_ASSOC": ""},
            {"ARPT_RWY_ASSOC": {"$not": re.compile(r"/")}}
        ]
    }

    # First try: search by TRANSITION_COMPUTER_CODE
    rte_cursor = await star_rte_collection.find(
        {"TRANSITION_COMPUTER_CODE": code, **runway_filter}
    ).sort("POINT_SEQ", DESCENDING).to_list(length=None)

    # If no results, search by STAR_COMPUTER_CODE
    if not rte_cursor:
        rte_cursor = await star_rte_collection.find(
            {
                "STAR_COMPUTER_CODE": code,
                "ROUTE_NAME": {"$not": re.compile(r"TRANSITION", re.IGNORECASE)},
                **runway_filter
            }
        ).sort("POINT_SEQ", DESCENDING).to_list(length=None)

    # Collect unique waypoints
    waypoints = []
    for doc in rte_cursor:
        point = doc.get("POINT")
        if point and point not in waypoints:
            waypoints.append(point)

    # If no waypoints, fallback
    if not waypoints:
        if "." in code:
            _, after_dot = code.split(".", 1)
            return {"transition": code, "waypoints": [after_dot]}
        else:
            raise HTTPException(status_code=404, detail=f"No valid waypoints found for {code}")

    return {"transition": code, "waypoints": waypoints}


DEFAULT_RADIUS = 400  # nm

# ========================
# /api/aircraft
# ========================
@app.get("/api/aircraft")
async def get_aircraft(radius: Optional[int] = Query(DEFAULT_RADIUS)):
    try:
        cached_data = aircraft_cache.find_one({}, {"_id": 0})
        if not cached_data:
            raise HTTPException(status_code=503, detail="Cache unavailable")
    except Exception as e:
        print(f"Error reading aircraft cache from MongoDB: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    target_lat, target_lon = 41.2129, -82.9431
    aircraft_list = cached_data.get("aircraft", [])

    filtered = [
        ac for ac in aircraft_list
        if finddist(ac["lat"], ac["lon"], target_lat, target_lon) <= radius
    ]

    return {"aircraft": filtered}




# ========================
# /api/crossings
# ========================
@app.get("/api/crossings")
async def get_crossings(destination: Optional[str] = Query("")):
    dest = destination.upper()
    if len(dest) == 4 and dest.startswith(("K", "C")):
        dest = dest[1:]

    query = {"destination": dest} if dest else {}
    rows = crossings_collection.find(query).sort("destination", 1)

    crossings = []
    async for row in rows:
        crossings.append({
            "_id": str(row.get("_id")),
            "destination": row.get("destination"),
            "fix": row.get("bdry_fix"),
            "restriction": row.get("restriction"),
            "notes": row.get("notes"),
            "artcc": row.get("artcc")
        })
    return crossings

class CrossingModel(BaseModel):
    destination: str
    fix: Optional[str] = None
    restriction: str
    notes: Optional[str] = None
    artcc: str

@app.put("/api/crossings/{crossing_id}")
async def update_crossing(
    crossing_id: str = Path(...),
    data: CrossingModel = Body(...),
    user=Depends(jwt_required)
):
    result = await crossings_collection.update_one(
        {"_id": ObjectId(crossing_id)},
        {"$set": data.dict()}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Crossing not found")
    return {"message": "Crossing updated successfully"}

@app.delete("/api/crossings/{crossing_id}")
async def delete_crossing(
    crossing_id: str = Path(...),
    user=Depends(jwt_required)
):
    result = await crossings_collection.delete_one({"_id": ObjectId(crossing_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Crossing not found")
    return {"message": "Crossing deleted successfully"}

@app.post("/api/crossings", status_code=201)
async def create_crossing(
    data: CrossingModel = Body(...),
    user=Depends(jwt_required)
):
    result = await crossings_collection.insert_one(data.dict())
    return {
        "message": "Crossing created successfully",
        "crossing_id": str(result.inserted_id)
    }

# ========================
# /api/enroute
# ========================
@app.get("/api/enroute")
async def get_enroute(
    field: Optional[str] = Query(""),
    area: Optional[str] = Query(""),
    qualifier: Optional[str] = Query("")
):
    f = field.upper()
    if len(f) == 4 and f.startswith(("K", "C")):
        f = f[1:]

    query = {}
    if f:
        query["Field"] = {"$regex": f, "$options": "i"}
    if area:
        query["Areas"] = {"$regex": area, "$options": "i"}

    rows = enroute_collection.find(query)

    results = []
    seen = set()
    async for row in rows:
        result_tuple = (
            row.get("Field", ""),
            row.get("Qualifier", ""),
            row.get("Areas", ""),
            row.get("Rule", "")
        )
        if result_tuple not in seen:
            seen.add(result_tuple)
            results.append({
                "_id": str(row.get("_id")),
                "field": result_tuple[0],
                "qualifier": result_tuple[1],
                "areas": result_tuple[2],
                "rule": result_tuple[3]
            })

    results.sort(key=lambda x: x["field"])
    return results

class EnrouteModel(BaseModel):
    areas: str
    field: str
    qualifier: str
    rule: str

@app.delete("/api/enroute/{enroute_id}")
async def delete_enroute(
    enroute_id: str,
    user=Depends(jwt_required)
):
    result = await enroute_collection.delete_one({"_id": ObjectId(enroute_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Enroute entry not found")
    return {"message": "Enroute entry deleted successfully"}

@app.put("/api/enroute/{enroute_id}")
async def update_enroute(
    enroute_id: str,
    data: EnrouteModel = Body(...),
    user=Depends(jwt_required)
):
    result = await enroute_collection.update_one(
        {"_id": ObjectId(enroute_id)},
        {"$set": {
            "Areas": data.areas,
            "Field": data.field,
            "Qualifier": data.qualifier,
            "Rule": data.rule
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Enroute entry not found")
    return {"message": "Enroute entry updated successfully"}

@app.post("/api/enroute", status_code=201)
async def create_enroute(
    data: EnrouteModel = Body(...),
    user=Depends(jwt_required)
):
    new_doc = {
        "Areas": data.areas,
        "Field": data.field,
        "Qualifier": data.qualifier,
        "Rule": data.rule
    }
    result = await enroute_collection.insert_one(new_doc)
    return {
        "message": "Enroute entry created successfully",
        "enroute_id": str(result.inserted_id)
    }

# ========================
# /api/controllers
# ========================
@app.get("/api/controllers")
async def get_center_controllers():
    try:
        doc = controller_cache.find_one({}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=503, detail="No controller data available")
        return {
            "cacheUpdatedAt": doc.get("cacheUpdatedAt"),
            "controllers": doc.get("controllers", []),
            "tracon": doc.get("tracon", [])
        }
    except Exception as e:
        print(f"Error reading controller cache from MongoDB: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    app.run()