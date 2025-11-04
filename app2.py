
from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from flask_cors import CORS
import bcrypt
from datetime import datetime
from bson.objectid import ObjectId

app = Flask(__name__)
CORS(app)

# 🔹 MongoDB Atlas Connection (replace with your credentials if needed)
app.config["MONGO_URI"] = "mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority"

mongo = PyMongo(app)
users = mongo.db.users          # Users collection
bookings = mongo.db.bookings    # Bookings collection

# Create helpful indexes (safe to run multiple times)
try:
    users.create_index("email", unique=True)
    bookings.create_index([("email", 1), ("created_at", -1)])
except Exception:
    pass

# ---------- Helpers ----------

def parse_iso_date(date_str: str):
    """
    Parse an ISO date or datetime string to a datetime object.
    Accepts formats like 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'.
    """
    if not isinstance(date_str, str):
        return None
    try:
        # Handles both date and datetime ISO formats
        return datetime.fromisoformat(date_str)
    except ValueError:
        try:
            # Fallback: append time if only date provided
            return datetime.fromisoformat(f"{date_str}T00:00:00")
        except Exception:
            return None

def serialize_booking(doc: dict) -> dict:
    """
    Convert MongoDB document to JSON-serializable dict.
    """
    if not doc:
        return None

    def to_iso(val):
        return val.isoformat() if isinstance(val, datetime) else val

    return {
        "id": str(doc.get("_id")) if doc.get("_id") else None,
        "email": doc.get("email"),
        "destination": doc.get("destination"),
        "start_date": to_iso(doc.get("start_date")),
        "end_date": to_iso(doc.get("end_date")),
        "num_guests": doc.get("num_guests"),
        "total_price": doc.get("total_price"),
        "notes": doc.get("notes"),
        "status": doc.get("status"),
        "created_at": to_iso(doc.get("created_at")),
        "updated_at": to_iso(doc.get("updated_at")),
        "cancelled_at": to_iso(doc.get("cancelled_at")),
    }

def get_object_id(id_str: str):
    try:
        return ObjectId(id_str)
    except Exception:
        return None

# =========================================
# ✅ Root route
# =========================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Backend is running 🚀"})

# =========================================
# ✅ Auth routes
# =========================================
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.json or {}
    name = data.get("name")
    phone = data.get("phone")
    email = data.get("email")
    password = data.get("password")
    confirmPassword = data.get("confirmPassword")

    if not name or not phone or not email or not password or not confirmPassword:
        return jsonify({"error": "All fields are required"}), 400

    if password != confirmPassword:
        return jsonify({"error": "Passwords do not match"}), 400

    if users.find_one({"email": email}):
        return jsonify({"error": "User already exists"}), 400

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    users.insert_one({"name": name, "phone": phone, "email": email, "password": hashed})

    return jsonify({"message": "Signup successful!"}), 201

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    user = users.find_one({"email": email})
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    if bcrypt.checkpw(password.encode("utf-8"), user["password"]):
        return jsonify({"message": "Login successful!", "email": email}), 200
    else:
        return jsonify({"error": "Invalid email or password"}), 401

@app.route("/dashboard/<email>", methods=["GET"])
def dashboard(email):
    user = users.find_one(
        {"email": email},
        {"_id": 0, "password": 0}  # hide _id and password
    )
    if user:
        return jsonify(user), 200
    else:
        return jsonify({"message": "User not found"}), 404

# =========================================
# ✅ Booking routes
# =========================================

# Create a booking
@app.route("/bookings", methods=["POST"])
def create_booking():
    """
    Body JSON:
    {
      "email": "user@example.com",
      "destination": "Paris",
      "start_date": "2025-09-10",
      "end_date": "2025-09-15",
      "num_guests": 2,
      "total_price": 1200.0,
      "notes": "Optional notes"
    }
    """
    data = request.json or {}

    email = data.get("email")
    destination = data.get("destination")
    start_date_str = data.get("start_date")
    end_date_str = data.get("end_date")
    num_guests = data.get("num_guests")
    total_price = data.get("total_price")
    notes = data.get("notes")

    # Basic validation
    if not email or not destination or not start_date_str or not end_date_str:
        return jsonify({"message": "email, destination, start_date, end_date are required"}), 400

    start_date = parse_iso_date(start_date_str)
    end_date = parse_iso_date(end_date_str)
    if not start_date or not end_date:
        return jsonify({"message": "Invalid date format. Use ISO format like YYYY-MM-DD"}), 400
    if end_date < start_date:
        return jsonify({"message": "end_date cannot be before start_date"}), 400

    try:
        num_guests = int(num_guests) if num_guests is not None else 1
        if num_guests <= 0:
            return jsonify({"message": "num_guests must be >= 1"}), 400
    except Exception:
        return jsonify({"message": "num_guests must be an integer"}), 400

    try:
        total_price = float(total_price) if total_price is not None else 0.0
        if total_price < 0:
            return jsonify({"message": "total_price must be >= 0"}), 400
    except Exception:
        return jsonify({"message": "total_price must be a number"}), 400

    # Ensure user exists
    if not users.find_one({"email": email}):
        return jsonify({"message": "User does not exist"}), 404

    now = datetime.utcnow()
    booking_doc = {
        "email": email,
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "num_guests": num_guests,
        "total_price": total_price,
        "notes": notes,
        "status": "confirmed",       # simple flow: confirmed on creation
        "created_at": now,
        "updated_at": now,
        "cancelled_at": None,
    }

    result = bookings.insert_one(booking_doc)
    saved = bookings.find_one({"_id": result.inserted_id})
    return jsonify({"message": "Booking created", "booking": serialize_booking(saved)}), 201

# List bookings (by user)
@app.route("/bookings", methods=["GET"])
def list_bookings():
    """
    Query params:
      - email (required): list bookings for this user
      - status (optional): filter by status (confirmed|cancelled)
    """
    email = request.args.get("email")
    status = request.args.get("status")

    if not email:
        return jsonify({"message": "email query parameter is required"}), 400

    query = {"email": email}
    if status:
        query["status"] = status

    cursor = bookings.find(query).sort("created_at", -1)
    return jsonify([serialize_booking(doc) for doc in cursor]), 200

# Get a specific booking by ID
@app.route("/bookings/<booking_id>", methods=["GET"])
def get_booking(booking_id):
    oid = get_object_id(booking_id)
    if not oid:
        return jsonify({"message": "Invalid booking id"}), 400

    doc = bookings.find_one({"_id": oid})
    if not doc:
        return jsonify({"message": "Booking not found"}), 404

    return jsonify(serialize_booking(doc)), 200

# Cancel a booking
@app.route("/bookings/<booking_id>/cancel", methods=["PUT"])
def cancel_booking(booking_id):
    oid = get_object_id(booking_id)
    if not oid:
        return jsonify({"message": "Invalid booking id"}), 400

    doc = bookings.find_one({"_id": oid})
    if not doc:
        return jsonify({"message": "Booking not found"}), 404

    if doc.get("status") == "cancelled":
        return jsonify({"message": "Booking already cancelled", "booking": serialize_booking(doc)}), 200

    now = datetime.utcnow()
    bookings.update_one(
        {"_id": oid},
        {"$set": {"status": "cancelled", "cancelled_at": now, "updated_at": now}}
    )
    updated = bookings.find_one({"_id": oid})
    return jsonify({"message": "Booking cancelled", "booking": serialize_booking(updated)}), 200

# Delete a booking (e.g., after cancellation or by admin)
@app.route("/bookings/<booking_id>", methods=["DELETE"])
def delete_booking(booking_id):
    oid = get_object_id(booking_id)
    if not oid:
        return jsonify({"message": "Invalid booking id"}), 400

    doc = bookings.find_one({"_id": oid})
    if not doc:
        return jsonify({"message": "Booking not found"}), 404

    # Simple rule: allow delete if already cancelled OR created within last 10 minutes
    allow_delete = doc.get("status") == "cancelled"
    if not allow_delete and doc.get("created_at"):
        try:
            age_seconds = (datetime.utcnow() - doc["created_at"]).total_seconds()
            if age_seconds < 600:
                allow_delete = True
        except Exception:
            pass

    if not allow_delete:
        return jsonify({"message": "Deletion not allowed for this booking"}), 403

    bookings.delete_one({"_id": oid})
    return jsonify({"message": "Booking deleted"}), 200

# =========================================
# ✅ Main
# =========================================
if __name__ == "__main__":
    app.run(debug=True)


