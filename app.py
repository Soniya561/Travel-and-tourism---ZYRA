# app.py
import os
import json
import urllib.request
import urllib.parse
from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    UserMixin,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Use project root as template folder so it can render the existing *.html files directly
app = Flask(__name__, template_folder=BASE_DIR)
CORS(app)  # allow frontend requests during local dev
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-change-this')

# SQLite DB in ./instance/zyra.db
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'zyra.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Auth setup
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ---------------------------------
# Upload configuration (PDF, 10 MB)
# ---------------------------------
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_email(email: str) -> bool:
    import re
    pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    return re.match(pattern, email) is not None

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_e):
    flash('File too large. Max size is 10 MB.', 'error')
    return redirect(url_for('documents')), 413

# ----------------------
# Routes
# ----------------------

@app.route('/')
def home():
    return redirect(url_for('login'))

# Serve frontend files - this must come after specific routes
@app.route('/<path:filename>')
def serve_frontend(filename):
    # First check if it's a frontend file
    frontend_path = os.path.join(BASE_DIR, '..', 'Frontend', filename)
    if os.path.exists(frontend_path):
        return send_from_directory(os.path.join(BASE_DIR, '..', 'Frontend'), filename)
    # If file doesn't exist in Frontend, try to render as template
    try:
        return render_template(filename)
    except:
        abort(404)

# Login & Signup
@app.route('/login', methods=['GET', 'POST'])
@app.route('/api/auth/login', methods=['POST'])
def login():
    if request.method == 'GET':
        # Renders your login.html which toggles between login/signup UI
        return render_template('login.html')

    # Handle both form data and JSON requests
    if request.is_json:
        data = request.get_json()
        email = (data.get('email') or '').lower().strip()
        password = data.get('password') or ''
    else:
        # Handle login submit (email, password, rememberMe)
        email = (request.form.get('email') or '').lower().strip()
        password = request.form.get('password') or ''
        remember = bool(request.form.get('rememberMe'))

    # Validate email format
    if not validate_email(email):
        if request.is_json:
            return jsonify({"error": "Invalid email format"}), 400
        flash('Please enter a valid email address', 'error')
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        login_user(user, remember=remember if not request.is_json else False)
        if request.is_json:
            return jsonify({"message": "Login successful"})
        return redirect(url_for('dashboard'))

    if request.is_json:
        return jsonify({"error": "Invalid credentials"}), 401
    flash('Invalid email or password', 'error')
    return redirect(url_for('login'))

@app.route('/signup', methods=['POST'])
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    # Handle both form data (legacy) and JSON requests
    if request.is_json:
        data = request.get_json()
        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip()
        email = (data.get('email') or '').lower().strip()
        password = data.get('password') or ''
        confirm_password = data.get('confirmPassword') or ''
        agree_terms = True  # Assume agreed for API calls
    else:
        # Handle signup submit (name, phone, email, password, confirmPassword, agreeTerms)
        name = (request.form.get('name') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        email = (request.form.get('email') or '').lower().strip()
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirmPassword') or ''
        agree_terms = request.form.get('agreeTerms')  # 'on' if checked

    # Basic validations
    if not email or not password or not name or not phone:
        if request.is_json:
            return jsonify({"error": "All fields are required"}), 400
        flash('Please fill all required fields', 'error')
        return redirect(url_for('login'))

    if not validate_email(email):
        if request.is_json:
            return jsonify({"error": "Invalid email format"}), 400
        flash('Please enter a valid email address', 'error')
        return redirect(url_for('login'))

    if password != confirm_password:
        if request.is_json:
            return jsonify({"error": "Passwords do not match"}), 400
        flash('Passwords do not match', 'error')
        return redirect(url_for('login'))

    if not request.is_json:
        if not agree_terms:
            flash('Please agree to the Terms & Conditions', 'error')
            return redirect(url_for('login'))

    if User.query.filter_by(email=email).first():
        if request.is_json:
            return jsonify({"error": "Email already registered"}), 409
        flash('An account with this email already exists', 'error')
        return redirect(url_for('login'))

    # Create user - name is optional for initial signup
    user = User(name=name or email.split('@')[0], phone=phone, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)

    if request.is_json:
        return jsonify({"message": "Signup successful"}), 201
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/auth/me')
@login_required
def me():
    return jsonify({
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "phone": current_user.phone
    })

# Dashboard (example protected page)
@app.route('/dashboard')
@login_required
def dashboard():
    # Renders dashboard.html if present; otherwise a simple welcome message
    try:
        return render_template('dashboard.html')
    except Exception:
        # Add quick link to documents page for convenience
        return (
            f"<h1>Welcome, {current_user.name or current_user.email}!</h1>"
            f"<p><a href='/documents'>Upload/View Documents</a></p>"
            f"<a href='/logout'>Logout</a>"
        )

# -------------
# Site pages (header links)
# -------------
# NOTE: If you want these pages to require login, add @login_required above each route.

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/reviews')
def reviews():
    return render_template('reviews.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/booking')
def booking_root():
    return render_template('booking.html')

@app.route('/booking/<int:step>')
def booking_step(step: int):
    # Dynamically render booking0.html, booking1.html, etc., if they exist
    filename = f'booking{step}.html'
    candidate_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(candidate_path):
        return render_template(filename)
    abort(404)

@app.route('/checkout')
def checkout():
    return render_template('checkout.html')

# ----------------------
# Documents (upload/list/view)
# ----------------------
@app.route('/documents', methods=['GET', 'POST'])
@login_required
def documents():
    if request.method == 'POST':
        # Try to get 'file' field or fallback to first available file key
        file = request.files.get('file')
        if not file and request.files:
            file = next(iter(request.files.values()))
        if not file:
            flash('No file received in request', 'error')
            return redirect(request.url)

        if not file.filename:
            flash('No selected file', 'error')
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash('Invalid file type. Only PDF allowed.', 'error')
            return redirect(request.url)

        # Ensure unique filename to avoid overwrite
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        final_name = filename
        counter = 1
        while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], final_name)):
            final_name = f"{name}_{counter}{ext}"
            counter += 1

        file.save(os.path.join(app.config['UPLOAD_FOLDER'], final_name))
        flash('File uploaded successfully', 'success')
        return redirect(url_for('documents'))

    # List PDFs in upload folder
    files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.lower().endswith('.pdf')]

    # Try to render template if exists; else fallback simple HTML
    try:
        return render_template('documents.html', files=files)
    except Exception:
        items = ''.join(
            f"<li><a href='/documents/view/{name}' target='_blank'>{name}</a></li>" for name in files
        ) or '<li>No documents yet</li>'
        return (
            "<h2>Documents</h2>"
            "<form method='POST' enctype='multipart/form-data'>"
            "<input type='file' name='file' accept='application/pdf' required>"
            "<button type='submit'>Upload PDF</button>"
            "</form>"
            f"<ul>{items}</ul>"
            "<p><a href='/dashboard'>Back to Dashboard</a></p>"
        )

@app.route('/documents/view/<path:filename>')
@login_required
def view_document(filename):
    # Serve the PDF file from uploads directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

# ----------------------
# Simple Weather API (no external API key required)
# ----------------------
# This uses open-meteo.com for current weather and a basic suitability heuristic.
@app.route('/weather')
def weather_api():
    city = (request.args.get('city') or '').strip()
    if not city:
        return jsonify({'error': 'city is required'}), 400

    try:
        # Geocode city → lat/lon via Open-Meteo geocoding
        q = urllib.parse.urlencode({'name': city, 'count': 1})
        with urllib.request.urlopen(f'https://geocoding-api.open-meteo.com/v1/search?{q}', timeout=8) as r:
            gj = json.loads(r.read().decode('utf-8'))
        if not gj.get('results'):
            return jsonify({'error': 'city not found'}), 404
        lat = gj['results'][0]['latitude']
        lon = gj['results'][0]['longitude']
        resolved_name = gj['results'][0].get('name') or city

        # Current weather
        cw_url = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=relative_humidity_2m,wind_speed_10m'
        with urllib.request.urlopen(cw_url, timeout=8) as r:
            wj = json.loads(r.read().decode('utf-8'))

        cur = (wj.get('current_weather') or {})
        temp_c = cur.get('temperature')
        wind_kph = None
        # Open-Meteo returns windspeed in km/h
        if cur.get('windspeed') is not None:
            wind_kph = round(float(cur['windspeed']), 1)

        # Get humidity from nearest hour
        humidity = None
        hourly = wj.get('hourly') or {}
        if hourly.get('time') and hourly.get('relative_humidity_2m'):
            # pick first value
            try:
                humidity = int(hourly['relative_humidity_2m'][0])
            except Exception:
                pass

        # Map weathercode to simple condition text
        code = cur.get('weathercode')
        code_map = {
            0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
            45: 'Fog', 48: 'Depositing rime fog', 51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Dense drizzle',
            56: 'Freezing drizzle', 57: 'Dense freezing drizzle', 61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
            66: 'Freezing rain', 67: 'Heavy freezing rain', 71: 'Slight snow', 73: 'Moderate snow', 75: 'Heavy snow',
            77: 'Snow grains', 80: 'Rain showers', 81: 'Moderate rain showers', 82: 'Violent rain showers',
            85: 'Snow showers', 86: 'Heavy snow showers', 95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Severe thunderstorm with hail'
        }
        condition = code_map.get(code, 'Unknown')

        # Suitability heuristic
        reason_parts = []
        suitable = True
        if temp_c is not None:
            if temp_c < 5:
                suitable = False; reason_parts.append('Too cold (< 5°C)')
            elif temp_c > 35:
                suitable = False; reason_parts.append('Too hot (> 35°C)')
        if humidity is not None and humidity > 85:
            suitable = False; reason_parts.append('High humidity')
        if wind_kph is not None and wind_kph > 40:
            suitable = False; reason_parts.append('Strong wind')
        bad_codes = {63,65,66,67,71,73,75,77,80,81,82,85,86,95,96,99}
        if code in bad_codes:
            suitable = False; reason_parts.append('Precipitation/storm conditions')

        reason = ' • '.join(reason_parts) if reason_parts else 'Looks good for travel.'

        return jsonify({
            'city': resolved_name,
            'tempC': round(temp_c, 1) if temp_c is not None else None,
            'condition': condition,
            'humidity': humidity,
            'windKph': wind_kph,
            'suitable': suitable,
            'reason': reason
        })
    except Exception as e:
        return jsonify({'error': 'failed to fetch weather', 'detail': str(e)}), 502

# 404 fallback
@app.errorhandler(404)
def page_not_found(_):
    return render_template('dashboard.html') if current_user.is_authenticated else redirect(url_for('login'))

if __name__ == '__main__':
    # For local development
    app.run(debug=True, host='127.0.0.1', port=5000)
