from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from functools import wraps
import secrets


app = Flask(__name__)

# Production Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Handle Render's DATABASE_URL format
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///alumni.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Security Headers
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='alumni')  # alumni, admin, guest
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Alumni profile data
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    graduation_year = db.Column(db.Integer)
    degree = db.Column(db.String(100))
    department = db.Column(db.String(100))
    company = db.Column(db.String(100))
    position = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    linkedin = db.Column(db.String(200))
    bio = db.Column(db.Text)
    
    # Relationships
    donations = db.relationship('Donation', backref='donor', lazy=True)
    jobs_posted = db.relationship('Job', backref='poster', lazy=True)
    stories = db.relationship('Story', backref='author', lazy=True)

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    purpose = db.Column(db.String(200))
    payment_method = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100))
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text)
    salary_range = db.Column(db.String(50))
    job_type = db.Column(db.String(20))  # full-time, part-time, contract, internship
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200))
    max_attendees = db.Column(db.Integer)
    registration_fee = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    registrations = db.relationship('EventRegistration', backref='event', lazy=True)

class EventRegistration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='registered')  # registered, attended, cancelled

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_featured = db.Column(db.Boolean, default=False)
    is_published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Decorators
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def approved_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_approved:
            flash('Your account is pending approval.', 'warning')
            return redirect(url_for('pending_approval'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def home():
    try:
        featured_stories = Story.query.filter_by(is_published=True, is_featured=True).limit(3).all()
        upcoming_events = Event.query.filter(Event.date > datetime.utcnow(), Event.is_active == True).limit(3).all()
    except Exception as e:
        # If database tables don't exist yet, use empty lists
        featured_stories = []
        upcoming_events = []
    
    return render_template('home.html', stories=featured_stories, events=upcoming_events)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        graduation_year = request.form['graduation_year']
        degree = request.form['degree']
        department = request.form['department']
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
        
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            graduation_year=int(graduation_year),
            degree=degree,
            department=department
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Your account is pending approval.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.is_approved:
                return redirect(url_for('alumni_dashboard'))
            else:
                return redirect(url_for('pending_approval'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/pending-approval')
@login_required
def pending_approval():
    if current_user.is_approved:
        return redirect(url_for('alumni_dashboard'))
    return render_template('pending_approval.html')

@app.route('/alumni-dashboard')
@login_required
@approved_required
def alumni_dashboard():
    user_donations = Donation.query.filter_by(user_id=current_user.id).count()
    user_jobs = Job.query.filter_by(user_id=current_user.id).count()
    upcoming_events = Event.query.filter(Event.date > datetime.utcnow()).limit(5).all()
    return render_template('alumni_dashboard.html', 
                         donations_count=user_donations,
                         jobs_count=user_jobs,
                         upcoming_events=upcoming_events)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
@approved_required
def profile():
    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')
        current_user.company = request.form.get('company')
        current_user.position = request.form.get('position')
        current_user.phone = request.form.get('phone')
        current_user.linkedin = request.form.get('linkedin')
        current_user.bio = request.form.get('bio')
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html')

@app.route('/donate', methods=['GET', 'POST'])
@login_required
@approved_required
def donate():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        purpose = request.form['purpose']
        payment_method = request.form['payment_method']
        
        donation = Donation(
            user_id=current_user.id,
            amount=amount,
            purpose=purpose,
            payment_method=payment_method,
            transaction_id=f"TXN{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        )
        
        db.session.add(donation)
        db.session.commit()
        
        flash('Thank you for your donation!', 'success')
        return redirect(url_for('donate'))
    
    return render_template('donate.html')

@app.route('/jobs')
def jobs():
    try:
        page = request.args.get('page', 1, type=int)
        jobs = Job.query.filter_by(is_active=True).order_by(Job.created_at.desc()).paginate(
            page=page, per_page=10, error_out=False)
    except Exception as e:
        # If database tables don't exist yet, use empty pagination
        jobs = type('obj', (object,), {'items': [], 'has_prev': False, 'has_next': False, 'prev_num': None, 'next_num': None, 'page': 1, 'pages': 0, 'total': 0})()
    
    return render_template('jobs.html', jobs=jobs)

@app.route('/post-job', methods=['GET', 'POST'])
@login_required
@approved_required
def post_job():
    if request.method == 'POST':
        job = Job(
            user_id=current_user.id,
            title=request.form['title'],
            company=request.form['company'],
            location=request.form['location'],
            description=request.form['description'],
            requirements=request.form['requirements'],
            salary_range=request.form['salary_range'],
            job_type=request.form['job_type']
        )
        
        db.session.add(job)
        db.session.commit()
        
        flash('Job posted successfully!', 'success')
        return redirect(url_for('jobs'))
    
    return render_template('post_job.html')

@app.route('/directory')
@login_required
@approved_required
def directory():
    search = request.args.get('search', '')
    graduation_year = request.args.get('year', '')
    department = request.args.get('department', '')
    
    query = User.query.filter_by(role='alumni', is_approved=True)
    
    if search:
        query = query.filter(
            (User.first_name.contains(search)) |
            (User.last_name.contains(search)) |
            (User.company.contains(search))
        )
    
    if graduation_year:
        query = query.filter_by(graduation_year=int(graduation_year))
    
    if department:
        query = query.filter_by(department=department)
    
    alumni = query.all()
    
    # Get unique years and departments for filters
    years = db.session.query(User.graduation_year).filter_by(role='alumni', is_approved=True).distinct().all()
    departments = db.session.query(User.department).filter_by(role='alumni', is_approved=True).distinct().all()
    
    return render_template('directory.html', 
                         alumni=alumni, 
                         years=[y[0] for y in years if y[0]], 
                         departments=[d[0] for d in departments if d[0]])

@app.route('/events')
def events():
    try:
        upcoming = Event.query.filter(Event.date > datetime.utcnow(), Event.is_active == True).all()
        past = Event.query.filter(Event.date <= datetime.utcnow()).all()
    except Exception as e:
        # If database tables don't exist yet, use empty lists
        upcoming = []
        past = []
    
    return render_template('events.html', upcoming_events=upcoming, past_events=past)

@app.route('/register-event/<int:event_id>')
@login_required
@approved_required
def register_event(event_id):
    event = Event.query.get_or_404(event_id)
    
    existing = EventRegistration.query.filter_by(event_id=event_id, user_id=current_user.id).first()
    if existing:
        flash('You are already registered for this event.', 'info')
        return redirect(url_for('events'))
    
    registration = EventRegistration(event_id=event_id, user_id=current_user.id)
    db.session.add(registration)
    db.session.commit()
    
    flash('Successfully registered for the event!', 'success')
    return redirect(url_for('events'))

@app.route('/stories')
def stories():
    try:
        published_stories = Story.query.filter_by(is_published=True).order_by(Story.created_at.desc()).all()
    except Exception as e:
        # If database tables don't exist yet, use empty list
        published_stories = []
    
    return render_template('stories.html', stories=published_stories)

@app.route('/submit-story', methods=['GET', 'POST'])
@login_required
@approved_required
def submit_story():
    if request.method == 'POST':
        story = Story(
            user_id=current_user.id,
            title=request.form['title'],
            content=request.form['content']
        )
        
        db.session.add(story)
        db.session.commit()
        
        flash('Story submitted for review!', 'success')
        return redirect(url_for('stories'))
    
    return render_template('submit_story.html')

# Admin Routes
@app.route('/admin-dashboard')
@login_required
@admin_required
def admin_dashboard():
    pending_users = User.query.filter_by(is_approved=False, role='alumni').count()
    total_donations = db.session.query(db.func.sum(Donation.amount)).scalar() or 0
    active_jobs = Job.query.filter_by(is_active=True).count()
    total_alumni = User.query.filter_by(role='alumni', is_approved=True).count()
    
    return render_template('admin_dashboard.html',
                         pending_users=pending_users,
                         total_donations=total_donations,
                         active_jobs=active_jobs,
                         total_alumni=total_alumni)

@app.route('/admin/pending-users')
@login_required
@admin_required
def pending_users():
    users = User.query.filter_by(is_approved=False, role='alumni').all()
    return render_template('admin_pending_users.html', users=users)

@app.route('/admin/approve-user/<int:user_id>')
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f'User {user.email} approved successfully!', 'success')
    return redirect(url_for('pending_users'))

@app.route('/admin/manage-events', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_events():
    if request.method == 'POST':
        event = Event(
            title=request.form['title'],
            description=request.form['description'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M'),
            location=request.form['location'],
            max_attendees=int(request.form['max_attendees']) if request.form['max_attendees'] else None,
            registration_fee=float(request.form['registration_fee']) if request.form['registration_fee'] else 0
        )
        
        db.session.add(event)
        db.session.commit()
        
        flash('Event created successfully!', 'success')
        return redirect(url_for('manage_events'))
    
    events = Event.query.order_by(Event.date.desc()).all()
    return render_template('admin_manage_events.html', events=events)

@app.route('/admin/manage-stories')
@login_required
@admin_required
def manage_stories():
    pending_stories = Story.query.filter_by(is_published=False).all()
    published_stories = Story.query.filter_by(is_published=True).all()
    return render_template('admin_manage_stories.html', 
                         pending_stories=pending_stories,
                         published_stories=published_stories)

@app.route('/admin/publish-story/<int:story_id>')
@login_required
@admin_required
def publish_story(story_id):
    story = Story.query.get_or_404(story_id)
    story.is_published = True
    db.session.commit()
    flash('Story published successfully!', 'success')
    return redirect(url_for('manage_stories'))

@app.route('/admin/feature-story/<int:story_id>')
@login_required
@admin_required
def feature_story(story_id):
    story = Story.query.get_or_404(story_id)
    story.is_featured = not story.is_featured
    db.session.commit()
    status = 'featured' if story.is_featured else 'unfeatured'
    flash(f'Story {status} successfully!', 'success')
    return redirect(url_for('manage_stories'))

# Database initialization route (for production setup)
@app.route('/init-db')
def initialize_database():
    """Initialize database tables and create admin user"""
    try:
        with app.app_context():
            db.create_all()
            
            # Create admin user if not exists
            admin = User.query.filter_by(email='pratik@gmail.com').first()
            if not admin:
                admin = User(
                    email='pratik@gmail.com',
                    password_hash=generate_password_hash('admin123'),
                    role='admin',
                    is_approved=True,
                    first_name='Admin',
                    last_name='User'
                )
                db.session.add(admin)
                db.session.commit()
                return jsonify({'message': 'Database initialized successfully! Admin user created.'})
            else:
                return jsonify({'message': 'Database already initialized. Admin user exists.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Routes for analytics
@app.route('/api/donation-stats')
@login_required
@admin_required
def donation_stats():
    monthly_donations = db.session.query(
        db.func.strftime('%Y-%m', Donation.created_at).label('month'),
        db.func.sum(Donation.amount).label('total')
    ).group_by('month').all()
    
    return jsonify([{'month': d.month, 'total': float(d.total)} for d in monthly_donations])

def init_db():
    """Initialize database and create admin user"""
    with app.app_context():
        db.create_all()
        
        # Create admin user if not exists
        admin = User.query.filter_by(email='pratik@gmail.com').first()
        if not admin:
            admin = User(
                email='pratik@gmail.com',
                password_hash=generate_password_hash('admin123'),
                role='admin',
                is_approved=True,
                first_name='Admin',
                last_name='User'
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")

if __name__ == '__main__':
    init_db()
    # Only run in debug mode locally
    if os.environ.get('FLASK_ENV') != 'production':
        app.run(debug=True, port=1001)
