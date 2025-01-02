

  from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/medusa.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    history = db.relationship('SearchHistory', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Symptom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    medications = db.relationship('Medication', secondary='symptom_medication', backref='symptoms')

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    dosage = db.Column(db.String(100))
    warnings = db.Column(db.Text)

class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symptoms = db.Column(db.String(500))
    medications = db.Column(db.String(500))  # Store recommended medications
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __init__(self, user_id, symptoms, medications=None):
        self.user_id = user_id
        self.symptoms = symptoms
        self.medications = medications

symptom_medication = db.Table('symptom_medication',
    db.Column('symptom_id', db.Integer, db.ForeignKey('symptom.id'), primary_key=True),
    db.Column('medication_id', db.Integer, db.ForeignKey('medication.id'), primary_key=True)
)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    return render_template('home.html')

@app.route('/symptom-checker')
def symptom_checker():
    symptoms = Symptom.query.all()
    return render_template('symptom_checker.html', symptoms=symptoms)

@app.route('/check-symptoms', methods=['POST'])
def check_symptoms():
    selected_symptoms = request.form.getlist('symptoms[]')
    medications = []
    for symptom_name in selected_symptoms:
        symptom = Symptom.query.filter_by(name=symptom_name).first()
        if symptom:
            medications.extend(symptom.medications)
    
    if current_user.is_authenticated:
        history = SearchHistory(user_id=current_user.id, symptoms=','.join(selected_symptoms), medications=','.join([med.name for med in medications]))
        db.session.add(history)
        db.session.commit()
    
    return render_template('results.html', medications=set(medications), symptoms=selected_symptoms)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('register.html')

        user_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()

        if user_exists:
            flash('Username already exists!', 'error')
            return render_template('register.html')
            
        if email_exists:
            flash('Email already registered!', 'error')
            return render_template('register.html')

        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration.', 'error')
            print(f"Registration error: {str(e)}")
            
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/search')
@login_required
def search_page():
    return render_template('search.html')

@app.route('/search', methods=['POST'])
@login_required
def search():
    query = request.form.get('query', '').lower()
    if not query:
        return jsonify({'medications': []})

    # Comprehensive medications database with symptoms
    medications = [
        {
            'name': 'Paracetamol',
            'description': 'Common pain reliever and fever reducer',
            'dosage': '500-1000mg every 4-6 hours',
            'warnings': 'Do not exceed 4000mg per day',
            'symptoms': ['headache', 'fever', 'body pain', 'cold', 'flu', 'toothache']
        },
        {
            'name': 'Ibuprofen',
            'description': 'Anti-inflammatory pain reliever',
            'dosage': '200-400mg every 4-6 hours',
            'warnings': 'Take with food. Avoid if you have stomach problems',
            'symptoms': ['headache', 'fever', 'inflammation', 'arthritis', 'muscle pain', 'menstrual pain']
        },
        {
            'name': 'Cetirizine',
            'description': 'Antihistamine for allergies',
            'dosage': '10mg once daily',
            'warnings': 'May cause drowsiness',
            'symptoms': ['allergy', 'cold', 'sneezing', 'runny nose', 'itchy eyes', 'hay fever']
        },
        {
            'name': 'Omeprazole',
            'description': 'Reduces stomach acid production',
            'dosage': '20mg once daily',
            'warnings': 'Take before meals',
            'symptoms': ['acidity', 'heartburn', 'stomach pain', 'acid reflux', 'indigestion']
        },
        {
            'name': 'Amoxicillin',
            'description': 'Antibiotic for bacterial infections',
            'dosage': '250-500mg three times daily',
            'warnings': 'Complete full course. May cause allergic reactions',
            'symptoms': ['bacterial infection', 'strep throat', 'ear infection', 'sinus infection']
        },
        {
            'name': 'Loratadine',
            'description': 'Non-drowsy antihistamine',
            'dosage': '10mg once daily',
            'warnings': 'Avoid if allergic to antihistamines',
            'symptoms': ['seasonal allergies', 'hives', 'skin rash', 'itching']
        },
        {
            'name': 'Diphenhydramine',
            'description': 'Antihistamine for allergies and sleep',
            'dosage': '25-50mg at bedtime',
            'warnings': 'Causes drowsiness. Do not drive',
            'symptoms': ['insomnia', 'allergies', 'cold symptoms', 'itching']
        },
        {
            'name': 'Naproxen',
            'description': 'Long-acting anti-inflammatory',
            'dosage': '250-500mg twice daily',
            'warnings': 'Take with food. May cause stomach upset',
            'symptoms': ['arthritis', 'back pain', 'menstrual cramps', 'gout']
        },
        {
            'name': 'Ranitidine',
            'description': 'Reduces stomach acid',
            'dosage': '150mg twice daily',
            'warnings': 'Take before meals',
            'symptoms': ['ulcer', 'acid reflux', 'stomach pain', 'heartburn']
        },
        {
            'name': 'Metformin',
            'description': 'Diabetes medication',
            'dosage': '500-1000mg twice daily',
            'warnings': 'Take with meals. Monitor blood sugar',
            'symptoms': ['diabetes', 'high blood sugar', 'excessive thirst', 'frequent urination']
        },
        {
            'name': 'Sertraline',
            'description': 'Antidepressant medication',
            'dosage': '50-200mg daily',
            'warnings': 'Do not stop abruptly. Consult doctor',
            'symptoms': ['depression', 'anxiety', 'panic attacks', 'obsessive thoughts']
        },
        {
            'name': 'Albuterol',
            'description': 'Bronchodilator for asthma',
            'dosage': '2 puffs every 4-6 hours',
            'warnings': 'Do not exceed recommended dose',
            'symptoms': ['asthma', 'wheezing', 'shortness of breath', 'chest tightness']
        },
        {
            'name': 'Metronidazole',
            'description': 'Antibiotic for infections',
            'dosage': '400mg three times daily',
            'warnings': 'Avoid alcohol. Complete full course',
            'symptoms': ['bacterial infection', 'dental infection', 'stomach infection']
        },
        {
            'name': 'Fluconazole',
            'description': 'Antifungal medication',
            'dosage': '150mg single dose',
            'warnings': 'May interact with other medications',
            'symptoms': ['fungal infection', 'yeast infection', 'thrush']
        },
        {
            'name': 'Cyclobenzaprine',
            'description': 'Muscle relaxant',
            'dosage': '5-10mg three times daily',
            'warnings': 'Causes drowsiness. Do not drive',
            'symptoms': ['muscle spasm', 'neck pain', 'back pain', 'fibromyalgia']
        },
        {
            'name': 'Ondansetron',
            'description': 'Anti-nausea medication',
            'dosage': '4-8mg as needed',
            'warnings': 'May cause headache',
            'symptoms': ['nausea', 'vomiting', 'motion sickness', 'chemotherapy nausea']
        },
        {
            'name': 'Prednisone',
            'description': 'Corticosteroid for inflammation',
            'dosage': 'Varies by condition',
            'warnings': 'Do not stop abruptly. Follow taper schedule',
            'symptoms': ['severe allergies', 'asthma', 'arthritis', 'skin conditions']
        },
        {
            'name': 'Gabapentin',
            'description': 'Nerve pain medication',
            'dosage': '300-600mg three times daily',
            'warnings': 'May cause dizziness',
            'symptoms': ['nerve pain', 'epilepsy', 'shingles pain', 'diabetic neuropathy']
        },
        {
            'name': 'Pantoprazole',
            'description': 'Proton pump inhibitor',
            'dosage': '40mg daily',
            'warnings': 'Take on empty stomach',
            'symptoms': ['acid reflux', 'stomach ulcers', 'heartburn', 'esophagitis']
        },
        {
            'name': 'Montelukast',
            'description': 'Asthma and allergy medication',
            'dosage': '10mg daily',
            'warnings': 'May cause mood changes',
            'symptoms': ['asthma', 'seasonal allergies', 'hay fever', 'breathing problems']
        }
    ]

    # Filter medications based on symptoms
    matching_medications = [
        {
            'name': med['name'],
            'description': med['description'],
            'dosage': med['dosage'],
            'warnings': med['warnings']
        }
        for med in medications
        if any(symptom in query for symptom in med['symptoms'])
    ]

    # Save search history if user is logged in
    if current_user.is_authenticated and matching_medications:
        try:
            history = SearchHistory(
                user_id=current_user.id,
                symptoms=query,
                medications=', '.join(med['name'] for med in matching_medications)
            )
            db.session.add(history)
            db.session.commit()
        except Exception as e:
            print(f"Error saving search history: {str(e)}")
            db.session.rollback()

    return jsonify({'medications': matching_medications})

@app.route('/profile')
@login_required
def profile():
    try:
        # Get user's search history ordered by timestamp
        history = SearchHistory.query.filter_by(user_id=current_user.id)\
            .order_by(SearchHistory.timestamp.desc())\
            .all()
        return render_template('profile.html', history=history)
    except Exception as e:
        print(f"Error accessing profile: {str(e)}")
        flash('Error loading profile data', 'error')
        return redirect(url_for('home'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create database tables
    app.run(debug=True)
