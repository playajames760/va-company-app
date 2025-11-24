from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, abort, session
import datetime
from flask_sqlalchemy import SQLAlchemy
import os
import re
import xml.etree.ElementTree as ET
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# Application version
APP_VERSION = 'v1.0.0'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'replace-this-with-env-secret'
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'palm_route_air.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class CargoManifest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    departure = db.Column(db.String(10))
    arrival = db.Column(db.String(10))
    total_weight = db.Column(db.String(20))
    pieces = db.Column(db.String(10))
    notes = db.Column(db.Text)
    dispatch_release_id = db.Column(db.Integer, db.ForeignKey('dispatch_release.id'))
    signoffs = db.relationship('CargoManifestSignOff', backref='manifest', lazy='dynamic')


class DispatchRelease(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    flight_id = db.Column(db.String(20))
    aircraft = db.Column(db.String(50))
    fleet_entry_id = db.Column(db.Integer, db.ForeignKey('fleet_entry.id'))
    departure = db.Column(db.String(10))
    destination = db.Column(db.String(10))
    offblocks = db.Column(db.String(10))
    arrival = db.Column(db.String(10))
    route = db.Column(db.Text)
    payload_planned = db.Column(db.String(20))  # Planned payload weight (lbs)
    fuel_planned = db.Column(db.String(20))     # Planned fuel (gal or lbs)
    cargo_plan = db.Column(db.Text)             # Summary of intended cargo items
    alt_airports = db.Column(db.Text)           # Alternate airports list
    weather_brief = db.Column(db.Text)          # Weather summary / risks
    special_notes = db.Column(db.Text)          # Special instructions / hazards
    actual_cargo_weight = db.Column(db.String(20))  # Aggregated from linked manifests
    flight_plan_raw = db.Column(db.Text)        # Raw uploaded flight plan content (SimBrief, etc.)
    flight_plan_source = db.Column(db.String(30))  # Source identifier e.g. 'simbrief'
    briefing_pdf_filename = db.Column(db.String(120))  # Stored PDF briefing filename (in ./briefings)
    completed = db.Column(db.Integer, default=0)  # 0 = planned/in-progress, 1 = completed
    cargo_manifests = db.relationship('CargoManifest', backref='dispatch_release', lazy='dynamic')
    fleet_entry = db.relationship('FleetEntry', lazy='joined')

class CompanyAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(10), default='USD')

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    type = db.Column(db.String(20))  # 'revenue' or 'expense'
    amount = db.Column(db.Float)
    description = db.Column(db.String(200))
    dispatch_release_id = db.Column(db.Integer, db.ForeignKey('dispatch_release.id'))
    cargo_manifest_id = db.Column(db.Integer, db.ForeignKey('cargo_manifest.id'))
    crew_log_id = db.Column(db.Integer, db.ForeignKey('crew_log.id'))


class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    severity = db.Column(db.String(20))  # e.g. Minor, Major, Critical
    dispatch_release_id = db.Column(db.Integer, db.ForeignKey('dispatch_release.id'))
    estimated_cost = db.Column(db.Float, default=0.0)
    resolved = db.Column(db.Integer, default=0)  # 0=open, 1=closed


class CrewLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    flight_id = db.Column(db.String(20))
    origin = db.Column(db.String(10))
    destination = db.Column(db.String(10))
    aircraft = db.Column(db.String(50))
    block_off = db.Column(db.String(10))
    block_on = db.Column(db.String(10))
    block_time = db.Column(db.String(10))
    cargo_weight = db.Column(db.String(20))
    fuel_used = db.Column(db.String(20))  # actual fuel used (numeric)
    remarks = db.Column(db.Text)
    dispatch_release_id = db.Column(db.Integer, db.ForeignKey('dispatch_release.id'))
    cargo_manifest_id = db.Column(db.Integer, db.ForeignKey('cargo_manifest.id'))
    dispatch_release = db.relationship('DispatchRelease', lazy='joined')
    cargo_manifest = db.relationship('CargoManifest', lazy='joined')
    signoffs = db.relationship('CrewLogSignOff', backref='crew_log', lazy='dynamic')


class CompanyNotam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    notam_id = db.Column(db.String(30))
    subject = db.Column(db.String(100))
    area = db.Column(db.String(50))
    text = db.Column(db.Text)
    status = db.Column(db.String(20))


class FleetEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aircraft_type = db.Column(db.String(50))
    registration = db.Column(db.String(20))
    base = db.Column(db.String(10))
    status = db.Column(db.String(20))
    max_takeoff_weight = db.Column(db.String(20))
    useful_load = db.Column(db.String(20))
    notes = db.Column(db.Text)


class AppSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), default='Palm Route Air')
    logo_filename = db.Column(db.String(120))  # stored in static/logos/
    difficulty = db.Column(db.String(20), default='Normal')  # Easy, Normal, Hard, Realistic
    realism_fuel_variance = db.Column(db.Float, default=0.05)  # ±5% revenue jitter
    realism_destination_penalty = db.Column(db.Float, default=0.25)  # 25% penalty for missed destination
    currency_symbol = db.Column(db.String(5), default='$')
    distance_unit = db.Column(db.String(10), default='NM')  # NM or KM
    weight_unit = db.Column(db.String(10), default='lbs')  # lbs or kg
    show_workflow_help = db.Column(db.Integer, default=1)  # 1 = show, 0 = hide

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True)
    role = db.Column(db.String(50), default='Pilot')
    hire_date = db.Column(db.Date, default=datetime.date.today)
    active = db.Column(db.Integer, default=1)
    password_hash = db.Column(db.String(255))

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class CargoManifestSignOff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cargo_manifest_id = db.Column(db.Integer, db.ForeignKey('cargo_manifest.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    employee = db.relationship('Employee', lazy='joined')

class CrewLogSignOff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crew_log_id = db.Column(db.Integer, db.ForeignKey('crew_log.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    employee = db.relationship('Employee', lazy='joined')

# Forward declaration - will be populated after helper functions are defined
_needs_seeding = False

# Create tables after all model classes have been declared
with app.app_context():
    db.create_all()
    # Runtime migration helper: add new DispatchRelease columns if DB existed earlier
    insp = db.session.execute(db.text("PRAGMA table_info(dispatch_release)")).fetchall()
    existing_cols = {row[1] for row in insp}
    new_cols = {
        'payload_planned': 'TEXT',
        'fuel_planned': 'TEXT',
        'cargo_plan': 'TEXT',
        'alt_airports': 'TEXT',
        'weather_brief': 'TEXT',
        'special_notes': 'TEXT'
    }
    additional_cols = {
        'actual_cargo_weight': 'TEXT',
        'fleet_entry_id': 'INTEGER',
        'flight_plan_raw': 'TEXT',
        'flight_plan_source': 'TEXT',
        'briefing_pdf_filename': 'TEXT',
        'completed': 'INTEGER'
    }
    for col, ddl in new_cols.items():
        if col not in existing_cols:
            db.session.execute(db.text(f"ALTER TABLE dispatch_release ADD COLUMN {col} {ddl}"))
    for col, ddl in additional_cols.items():
        if col not in existing_cols:
            db.session.execute(db.text(f"ALTER TABLE dispatch_release ADD COLUMN {col} {ddl}"))
    db.session.commit()
    # Ensure cargo_manifest has dispatch_release_id
    insp_cargo = db.session.execute(db.text("PRAGMA table_info(cargo_manifest)")).fetchall()
    cargo_cols = {row[1] for row in insp_cargo}
    if 'dispatch_release_id' not in cargo_cols:
        db.session.execute(db.text("ALTER TABLE cargo_manifest ADD COLUMN dispatch_release_id INTEGER"))
        db.session.commit()
    # Ensure fleet_entry_id column exists on dispatch_release
    if 'fleet_entry_id' not in existing_cols:
        db.session.execute(db.text("ALTER TABLE dispatch_release ADD COLUMN fleet_entry_id INTEGER"))
        db.session.commit()

    # Ensure single company account row exists
    if CompanyAccount.query.first() is None:
        db.session.add(CompanyAccount(balance=0.0))
        db.session.commit()
    
    # Add show_workflow_help to app_settings if missing (BEFORE querying AppSettings)
    insp_settings = db.session.execute(db.text("PRAGMA table_info(app_settings)")).fetchall()
    settings_cols = {row[1] for row in insp_settings}
    if 'show_workflow_help' not in settings_cols:
        db.session.execute(db.text("ALTER TABLE app_settings ADD COLUMN show_workflow_help INTEGER DEFAULT 1"))
        db.session.commit()
    
    # Ensure single app settings row exists
    if AppSettings.query.first() is None:
        db.session.add(AppSettings(
            company_name='Palm Route Air',
            difficulty='Normal',
            realism_fuel_variance=0.05,
            realism_destination_penalty=0.25,
            currency_symbol='$',
            distance_unit='NM',
            weight_unit='lbs',
            show_workflow_help=1
        ))
        db.session.commit()
    # Runtime add fuel_used to crew_log if missing
    insp_crew = db.session.execute(db.text("PRAGMA table_info(crew_log)")).fetchall()
    crew_cols = {row[1] for row in insp_crew}
    if 'fuel_used' not in crew_cols:
        db.session.execute(db.text("ALTER TABLE crew_log ADD COLUMN fuel_used TEXT"))
        db.session.commit()
    # Ensure incident table exists (created via model above). If older DBs lack estimated_cost or resolved, add.
    insp_incident = db.session.execute(db.text("PRAGMA table_info(incident)")).fetchall()
    incident_cols = {row[1] for row in insp_incident} if insp_incident else set()
    if not insp_incident:
        # Table will be created by db.create_all for new DBs; for existing DBs without it, nothing else required.
        pass
    
    # Seed sample data for testing (only if database is empty)
    if FleetEntry.query.count() == 0:
        _needs_seeding = True
        print("⏳ Database is empty - will seed sample data after initialization")
    # Ensure at least one employee exists for authentication
    if Employee.query.count() == 0:
        default_emp = Employee(name='Admin Pilot', email='admin@palmroute.local', role='Administrator')
        default_emp.set_password('pilot')  # default password
        db.session.add(default_emp)
        db.session.commit()

# --- Access Control Helpers -------------------------------------------------
MANAGEMENT_ROLES = {'Manager', 'Administrator'}

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('employee_id'):
            flash('Login required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def roles_required(*roles):
    roles_set = set(roles)
    @wraps(roles_required)
    def decorator(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if not session.get('employee_id'):
                flash('Login required.', 'error')
                return redirect(url_for('login'))
            emp = Employee.query.get(session['employee_id'])
            if not emp or (emp.role not in roles_set and emp.role != 'Administrator'):
                flash('Insufficient permissions.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return inner
    return decorator

@app.before_request
def enforce_login_globally():
    # Allow unauthenticated access only to login/logout/static assets
    public_endpoints = {'login', 'logout', 'static'}
    if request.endpoint in public_endpoints or request.endpoint is None:
        return
    if not session.get('employee_id'):
        return redirect(url_for('login'))


# Make settings available in all templates
@app.context_processor
def inject_settings():
    try:
        settings = AppSettings.query.first()
        if not settings:
            settings = AppSettings(company_name='Palm Route Air')
    except:
        settings = None
    current_employee = None
    if session.get('employee_id'):
        current_employee = Employee.query.get(session['employee_id'])
    return dict(app_settings=settings, app_version=APP_VERSION, current_employee=current_employee)


# --- Helper Parsers -------------------------------------------------------
def parse_pln(content: str):
    """Parse a Microsoft Flight Simulator .pln XML string.

    Returns a dict with keys:
      route_str: Reconstructed compact route string
      cruising_alt: Cruise altitude (string or None)
      departure_runway: e.g. '26L'
      arrival_runway: e.g. '29'
      approach_type: e.g. 'RNAV'
      waypoints: list of dicts {ident, type, airway}
    Any missing values are None. Silently fails returning minimal dict if XML invalid.
    """
    data = {
        'route_str': None,
        'cruising_alt': None,
        'departure_runway': None,
        'arrival_runway': None,
        'approach_type': None,
        'waypoints': []
    }
    if not content or '<SimBase.Document' not in content:
        return data
    try:
        # Some .pln files may have BOM or leading whitespace
        root = ET.fromstring(content.strip())
    except Exception:
        return data
    # Find FlightPlan node
    fp = None
    for child in root.iter():
        if child.tag.endswith('FlightPlan'):
            # Ensure we are at FlightPlan.FlightPlan level, not container
            # The sample structure is <FlightPlan.FlightPlan>
            fp = child
    if fp is None:
        return data
    # Basic fields
    ca = fp.find('CruisingAlt')
    if ca is not None and ca.text:
        data['cruising_alt'] = ca.text.strip()
    dep_details = fp.find('DepartureDetails')
    if dep_details is not None:
        rn = dep_details.find('RunwayNumberFP')
        rd = dep_details.find('RunwayDesignatorFP')
        if rn is not None and rn.text:
            rn_val = rn.text.strip()
            if rd is not None and rd.text and rd.text.strip().upper() != 'NONE':
                rn_val += rd.text.strip()[0]  # Use first letter (e.g. LEFT -> L)
            data['departure_runway'] = rn_val
    arr_details = fp.find('ArrivalDetails')
    if arr_details is not None:
        rn = arr_details.find('RunwayNumberFP')
        if rn is not None and rn.text:
            data['arrival_runway'] = rn.text.strip()
    appr_details = fp.find('ApproachDetails')
    if appr_details is not None:
        at = appr_details.find('ApproachTypeFP')
        if at is not None and at.text:
            data['approach_type'] = at.text.strip()
    # Waypoints
    prev_airway = None
    route_parts = []
    for wp in fp.findall('ATCWaypoint'):
        wptype_el = wp.find('ATCWaypointType')
        airway_el = wp.find('ATCAirway')
        ident_el = wp.find('./ICAO/ICAOIdent')
        wptype = wptype_el.text.strip() if (wptype_el is not None and wptype_el.text) else None
        airway = airway_el.text.strip() if (airway_el is not None and airway_el.text) else None
        ident = ident_el.text.strip() if (ident_el is not None and ident_el.text) else None
        if ident:
            data['waypoints'].append({'ident': ident, 'type': wptype, 'airway': airway})
            # Build route string: include airway when it changes, then ident
            if airway and airway != prev_airway:
                route_parts.append(airway)
                prev_airway = airway
            route_parts.append(ident)
        else:
            continue
    if route_parts:
        # De-duplicate consecutive identical idents (unlikely but safe)
        compact = []
        last = None
        for part in route_parts:
            if part != last:
                compact.append(part)
            last = part
        data['route_str'] = ' '.join(compact)
    return data

# --- Economy Helpers ------------------------------------------------------
ECONOMY_CONSTANTS = {
    'BASE_FLIGHT_REVENUE': 250.0,          # base revenue per dispatch
    'REVENUE_PER_LB': 0.35,                # revenue per pound of planned (or actual) payload
    'FUEL_COST_PER_UNIT': 5.25,            # cost per unit (gal or labeled unit)
    'MAINTENANCE_FLAT': 110.0,             # flat maintenance cost per flight
    'REVENUE_PER_NM': 1.15                # distance-based revenue component per nautical mile
}

def seed_sample_data():
    """Seed the database with sample data for testing and new games"""
    # Sample fleet entries
    fleet_sample = [
        FleetEntry(aircraft_type='Cessna 172', registration='N12345', base='KPOC', status='Available', max_takeoff_weight='2450', useful_load='890', notes='Primary trainer aircraft'),
        FleetEntry(aircraft_type='Cessna 208 Caravan', registration='N208PA', base='KPOC', status='Available', max_takeoff_weight='8750', useful_load='3500', notes='Cargo hauler'),
        FleetEntry(aircraft_type='Piper PA-28 Cherokee', registration='N4567P', base='KCRQ', status='Maintenance', max_takeoff_weight='2450', useful_load='930', notes='Under scheduled maintenance')
    ]
    db.session.add_all(fleet_sample)
    db.session.commit()
    
    # Sample NOTAMs
    notam_sample = [
        CompanyNotam(notam_id='PRA-001', subject='Fuel price increase at KCRQ', area='Operations', text='Effective immediately, fuel costs at KCRQ have increased by 8% due to supply chain issues.', status='Active'),
        CompanyNotam(notam_id='PRA-002', subject='New VFR reporting point established', area='Navigation', text='New reporting point VISTA established 5NM north of KPOC for VFR traffic coordination.', status='Active')
    ]
    db.session.add_all(notam_sample)
    db.session.commit()
    
    # Sample dispatch releases with linked fleet
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    fleet1 = fleet_sample[0]
    fleet2 = fleet_sample[1]
    
    dispatch_sample = [
        DispatchRelease(
            date=yesterday.isoformat(),
            flight_id='PRA101',
            aircraft=f'{fleet1.aircraft_type} {fleet1.registration}',
            fleet_entry_id=fleet1.id,
            departure='KPOC',
            destination='KCRQ',
            offblocks='1430Z',
            arrival='1545Z',
            route='KPOC direct KCRQ via coastline, VFR 3500ft',
            payload_planned='650',
            fuel_planned='28',
            cargo_plan='General cargo and mail',
            alt_airports='KOKB, KSNA',
            weather_brief='VFR conditions, light winds from 270, visibility 10+ SM',
            special_notes='First flight of the day, pre-flight complete',
            completed=1
        ),
        DispatchRelease(
            date=today.isoformat(),
            flight_id='PRA102',
            aircraft=f'{fleet2.aircraft_type} {fleet2.registration}',
            fleet_entry_id=fleet2.id,
            departure='KPOC',
            destination='KSBP',
            offblocks='0800Z',
            arrival='0930Z',
            route='KPOC V23 BASET V27 KSBP',
            payload_planned='2200',
            fuel_planned='85',
            cargo_plan='Priority freight shipment',
            alt_airports='KSBA, KPRB',
            weather_brief='MVFR becoming VFR, scattered at 1500ft, winds 310/12',
            special_notes='Heavy cargo - check weight and balance carefully',
            completed=0
        )
    ]
    db.session.add_all(dispatch_sample)
    db.session.commit()
    
    # Sample cargo manifests linked to dispatches
    cargo_sample = [
        CargoManifest(
            date=yesterday.isoformat(),
            departure='KPOC',
            arrival='KCRQ',
            total_weight='680',
            pieces='12',
            notes='Mixed cargo: 8 parcels general freight, 4 mail bags',
            dispatch_release_id=dispatch_sample[0].id
        ),
        CargoManifest(
            date=today.isoformat(),
            departure='KPOC',
            arrival='KSBP',
            total_weight='2150',
            pieces='6',
            notes='Industrial equipment parts - fragile, secure properly',
            dispatch_release_id=dispatch_sample[1].id
        )
    ]
    db.session.add_all(cargo_sample)
    
    # Update actual cargo weight on dispatches
    dispatch_sample[0].actual_cargo_weight = '680'
    dispatch_sample[1].actual_cargo_weight = '2150'
    db.session.commit()
    
    # Sample crew logs
    crew_sample = [
        CrewLog(
            date=yesterday.isoformat(),
            flight_id='PRA101',
            origin='KPOC',
            destination='KCRQ',
            aircraft=f'{fleet1.aircraft_type} {fleet1.registration}',
            block_off='1432Z',
            block_on='1543Z',
            block_time='1.18',
            cargo_weight='680',
            fuel_used='26.5',
            remarks='Smooth flight, light turbulence near destination. Cargo delivered on time.',
            dispatch_release_id=dispatch_sample[0].id,
            cargo_manifest_id=cargo_sample[0].id
        )
    ]
    db.session.add_all(crew_sample)
    db.session.commit()
    
    # Generate transactions for completed dispatch
    acct = CompanyAccount.query.first()
    rev, cost, profit, dist = compute_dispatch_financials(dispatch_sample[0])
    txn_revenue = Transaction(
        type='revenue',
        amount=rev,
        description=f'Dispatch #{dispatch_sample[0].id} - {dispatch_sample[0].flight_id} revenue',
        dispatch_release_id=dispatch_sample[0].id
    )
    txn_cost = Transaction(
        type='expense',
        amount=cost,
        description=f'Dispatch #{dispatch_sample[0].id} - {dispatch_sample[0].flight_id} operational costs',
        dispatch_release_id=dispatch_sample[0].id
    )
    db.session.add_all([txn_revenue, txn_cost])
    acct.balance += profit
    db.session.commit()
    
    # Sample incident
    incident_sample = Incident(
        date=yesterday.isoformat(),
        title='Bird strike on departure',
        description='Minor bird strike during takeoff roll at KPOC. No damage observed, continued flight as planned. Reported to tower and logged for maintenance inspection.',
        severity='Minor',
        dispatch_release_id=dispatch_sample[0].id,
        estimated_cost=150.0,
        resolved=1
    )
    db.session.add(incident_sample)
    # Deduct incident cost from balance
    acct.balance -= 150.0
    txn_incident = Transaction(
        type='expense',
        amount=150.0,
        description='Incident: Bird strike on departure',
        dispatch_release_id=dispatch_sample[0].id
    )
    db.session.add(txn_incident)
    db.session.commit()

def compute_dispatch_financials(dispatch: DispatchRelease):
    """Compute revenue, costs, profit for a dispatch release.
    Payload: prefer actual cargo weight if present else planned payload.
    Fuel cost: planned fuel * cost constant if numeric.
    Returns (revenue, costs, profit).
    """
    # Load settings for difficulty adjustments
    settings = AppSettings.query.first()
    if not settings:
        settings = AppSettings()  # fallback to defaults
    
    # Apply difficulty multipliers
    difficulty_multipliers = {
        'Easy': {'revenue': 1.20, 'penalty': 0.10, 'variance': 0.02},
        'Normal': {'revenue': 1.0, 'penalty': 0.25, 'variance': 0.05},
        'Hard': {'revenue': 0.90, 'penalty': 0.35, 'variance': 0.08},
        'Realistic': {'revenue': 0.80, 'penalty': 0.50, 'variance': 0.10}
    }
    diff_params = difficulty_multipliers.get(settings.difficulty, difficulty_multipliers['Normal'])
    
    rev_base = ECONOMY_CONSTANTS['BASE_FLIGHT_REVENUE'] * diff_params['revenue']
    # Derive payload from linked cargo manifests if present, else fall back
    payload_val = None
    linked_weights = []
    if hasattr(dispatch, 'cargo_manifests') and dispatch.cargo_manifests is not None:
        for m in dispatch.cargo_manifests.all():
            if m.total_weight:
                try:
                    linked_weights.append(float(m.total_weight))
                except ValueError:
                    continue
    if linked_weights:
        payload_val = sum(linked_weights)
    else:
        for candidate in [dispatch.actual_cargo_weight, dispatch.payload_planned]:
            if candidate:
                try:
                    payload_val = float(candidate)
                    break
                except ValueError:
                    continue
    payload_revenue = (payload_val or 0.0) * ECONOMY_CONSTANTS['REVENUE_PER_LB']
    # Attempt to use actual fuel from related crew logs (latest with numeric fuel_used)
    fuel_val = 0.0
    actual_fuel = None
    crew_logs = CrewLog.query.filter_by(dispatch_release_id=dispatch.id).order_by(CrewLog.id.desc()).all()
    # Prefer most recent numeric fuel_used
    for cl in crew_logs:
        if cl.fuel_used:
            try:
                actual_fuel = float(cl.fuel_used)
                break
            except ValueError:
                continue
    if actual_fuel is not None:
        fuel_val = actual_fuel
    elif dispatch.fuel_planned:
        try:
            fuel_val = float(dispatch.fuel_planned)
        except ValueError:
            fuel_val = 0.0
    fuel_cost = fuel_val * ECONOMY_CONSTANTS['FUEL_COST_PER_UNIT']
    maintenance = ECONOMY_CONSTANTS['MAINTENANCE_FLAT']
    # Distance revenue component (requires simple airport coordinate mapping)
    APT_COORDS = {
        'KPOC': (34.091, -117.781),
        'KCRQ': (33.128, -117.279),
        'KSBP': (35.236, -120.642),
        'KSNA': (33.6757, -117.8682),
        'KOKB': (33.2173, -117.353),
        'KVNY': (34.2098, -118.4904),
        'KRZS': (34.5113, -119.755),
        'KMQO': (35.237, -120.642)  # placeholder MQO VOR approx same as KSBP for demo
    }
    def haversine_nm(lat1, lon1, lat2, lon2):
        from math import radians, sin, cos, atan2, sqrt
        R = 3440.065
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c
    distance_nm = 0.0
    if dispatch.departure in APT_COORDS and dispatch.destination in APT_COORDS:
        (la1, lo1) = APT_COORDS[dispatch.departure]
        (la2, lo2) = APT_COORDS[dispatch.destination]
        try:
            distance_nm = haversine_nm(la1, lo1, la2, lo2)
        except Exception:
            distance_nm = 0.0
    distance_revenue = distance_nm * ECONOMY_CONSTANTS['REVENUE_PER_NM']

    # Immersion/realism adjustments based on execution vs plan
    bonus_multiplier = 1.0
    penalty = 0.0
    # Check if any crew log actually arrived at planned destination
    arrived_at_dest = False
    for cl in crew_logs:
        if cl.destination and dispatch.destination and cl.destination.strip().upper() == dispatch.destination.strip().upper():
            arrived_at_dest = True
            break
    if not arrived_at_dest and crew_logs:
        # Apply difficulty-based penalty if flight never reached planned destination
        penalty += diff_params['penalty'] * (payload_revenue + distance_revenue)
    # Small randomness for immersion (use difficulty variance setting)
    import random
    jitter = random.uniform(-diff_params['variance'], diff_params['variance'])
    bonus_multiplier += jitter
    # Apply multiplier to core revenue (base + payload + distance) then subtract penalties
    core_revenue = rev_base + payload_revenue + distance_revenue
    revenue = core_revenue * bonus_multiplier - penalty
    costs = fuel_cost + maintenance
    profit = revenue - costs
    return round(revenue,2), round(costs,2), round(profit,2), round(distance_nm,1)


def get_company_account():
    acct = CompanyAccount.query.first()
    if not acct:
        acct = CompanyAccount(balance=0.0)
        db.session.add(acct)
        db.session.commit()
    return acct

# Perform delayed seeding if needed
if _needs_seeding:
    with app.app_context():
        seed_sample_data()
        print("✅ Sample data initialized successfully!")


@app.route('/')
@login_required
def index():
    manifests = CargoManifest.query.order_by(CargoManifest.id.desc()).limit(5).all()
    releases = DispatchRelease.query.order_by(DispatchRelease.id.desc()).limit(5).all()
    logs = CrewLog.query.order_by(CrewLog.id.desc()).limit(5).all()
    notams = CompanyNotam.query.order_by(CompanyNotam.id.desc()).limit(5).all()
    incidents = Incident.query.order_by(Incident.id.desc()).limit(5).all()
    fleet_entries = FleetEntry.query.order_by(FleetEntry.id.desc()).all()
    acct = CompanyAccount.query.first()
    counts = {
        'cargo_manifests': CargoManifest.query.count(),
        'dispatch_releases': DispatchRelease.query.count(),
        'crew_logs': CrewLog.query.count(),
        'company_notams': CompanyNotam.query.count(),
        'fleet_entries': FleetEntry.query.count(),
        'incidents': Incident.query.count()
    }
    completed_dispatches = DispatchRelease.query.filter_by(completed=1).all()
    total_completed_profit = 0.0
    for cd in completed_dispatches:
        try:
            _rev,_cost,_prof,_dist = compute_dispatch_financials(cd)
            total_completed_profit += _prof
        except Exception:
            pass
    # Subtract open incident estimated costs from displayed completed profit to show net after-incident impact
    open_incidents = Incident.query.filter_by(resolved=0).all()
    total_incident_cost = sum(i.estimated_cost or 0.0 for i in open_incidents)
    net_profit_after_incidents = total_completed_profit - total_incident_cost
    return render_template(
        'index.html',
        manifests=manifests,
        releases=releases,
        logs=logs,
        notams=notams,
        fleet_entries=fleet_entries,
        counts=counts,
        completed_profit=round(total_completed_profit, 2),
        incident_costs=round(total_incident_cost, 2),
        net_profit=round(net_profit_after_incidents, 2),
        incidents=incidents
    )


@app.route('/cargo', methods=['GET', 'POST'])
@login_required
def cargo():
    if request.method == 'POST':
        manifest = CargoManifest(
            date=request.form.get('date'),
            departure=request.form.get('departure'),
            arrival=request.form.get('arrival'),
            total_weight=request.form.get('total_weight'),
            pieces=request.form.get('pieces'),
            notes=request.form.get('notes'),
            dispatch_release_id=request.form.get('dispatch_release_id') or None
        )
        # Validation
        errors = []
        if manifest.total_weight:
            try:
                float(manifest.total_weight)
            except ValueError:
                errors.append('Total weight must be numeric.')
        if manifest.pieces:
            try:
                int(manifest.pieces)
            except ValueError:
                errors.append('Pieces must be an integer.')
        if errors:
            for e in errors:
                flash(e, 'error')
            defaults = {k: request.form.get(k,'') for k in ['date','flight_id','aircraft','departure','arrival','total_weight','pieces','notes','dispatch_release_id']}
            return render_template('cargo_form.html', defaults=defaults)
        db.session.add(manifest)
        db.session.commit()
        # Auto-link if not provided by matching date + flight_id
        if manifest.dispatch_release_id is None:
            match = DispatchRelease.query.filter_by(date=manifest.date, flight_id=manifest.flight_id).first()
            if match:
                manifest.dispatch_release_id = match.id
                db.session.commit()
        # Update aggregated cargo weight on linked dispatch
        if manifest.dispatch_release_id:
            dr = DispatchRelease.query.get(manifest.dispatch_release_id)
            if dr:
                weights = []
                for m in dr.cargo_manifests.all():
                    try:
                        weights.append(float(m.total_weight))
                    except (TypeError, ValueError):
                        pass
                total = sum(weights)
                if weights:
                    dr.actual_cargo_weight = str(int(total)) if float(total).is_integer() else f"{total:.1f}"
                    db.session.commit()
        return redirect(url_for('cargo_history'))
    defaults = {
        'date': request.args.get('date', ''),
        'departure': request.args.get('departure', ''),
        'arrival': request.args.get('arrival', ''),
        'total_weight': request.args.get('total_weight', ''),
        'pieces': request.args.get('pieces', ''),
        'notes': request.args.get('notes', ''),
        'dispatch_release_id': request.args.get('dispatch_release_id', '')
    }
    return render_template('cargo_form.html', defaults=defaults)


@app.route('/incidents')
@login_required
def incident_history():
    incidents = Incident.query.order_by(Incident.id.desc()).all()
    return render_template('incident_history.html', incidents=incidents)


@app.route('/incident', methods=['GET', 'POST'])
@login_required
def incident():
    if request.method == 'POST':
        date = request.form.get('date') or datetime.date.today().isoformat()
        title = request.form.get('title')
        description = request.form.get('description')
        severity = request.form.get('severity') or 'Minor'
        dispatch_id = request.form.get('dispatch_release_id') or None
        est_cost_raw = request.form.get('estimated_cost') or '0'
        try:
            est_cost = float(est_cost_raw)
        except ValueError:
            est_cost = 0.0
        incident = Incident(
            date=date,
            title=title,
            description=description,
            severity=severity,
            dispatch_release_id=dispatch_id,
            estimated_cost=est_cost,
            resolved=0
        )
        db.session.add(incident)
        # Immediately impact company balance as an expense
        if est_cost > 0:
            acct = get_company_account()
            acct.balance -= est_cost
            t = Transaction(
                type='expense',
                amount=est_cost,
                description=f'Incident: {title or "Unnamed"}',
                dispatch_release_id=dispatch_id
            )
            db.session.add(t)
        db.session.commit()
        flash('Incident logged.', 'success')
        return redirect(url_for('incident_history'))
    defaults = {
        'date': datetime.date.today().isoformat(),
        'title': '',
        'description': '',
        'severity': 'Minor',
        'dispatch_release_id': request.args.get('dispatch_release_id', ''),
        'estimated_cost': ''
    }
    dispatch_options = DispatchRelease.query.order_by(DispatchRelease.id.desc()).all()
    return render_template('incident_form.html', defaults=defaults, dispatch_options=dispatch_options)


@app.route('/incident/<int:id>', methods=['GET', 'POST'])
@login_required
def incident_detail(id):
    inc = Incident.query.get_or_404(id)
    if request.method == 'POST':
        # Allow updating resolution status only for now
        resolved_flag = 1 if request.form.get('resolved') == 'on' else 0
        inc.resolved = resolved_flag
        db.session.commit()
        flash('Incident updated.', 'success')
        return redirect(url_for('incident_detail', id=id))
    linked_dispatch = None
    if inc.dispatch_release_id:
        linked_dispatch = DispatchRelease.query.get(inc.dispatch_release_id)
    return render_template('incident_detail.html', incident=inc, linked_dispatch=linked_dispatch)


@app.route('/cargo/history')
@login_required
def cargo_history():
    manifests = CargoManifest.query.order_by(CargoManifest.id.desc()).all()
    return render_template('cargo_history.html', manifests=manifests)


@app.route('/dispatch', methods=['GET', 'POST'])
@roles_required('Manager', 'Administrator')
def dispatch():
    if request.method == 'POST':
        fleet_entry_id = request.form.get('fleet_entry_id') or None
        aircraft_text = request.form.get('aircraft')  # fallback hidden field
        if fleet_entry_id:
            fe = FleetEntry.query.get(fleet_entry_id)
            if fe:
                aircraft_text = f"{fe.aircraft_type} {fe.registration}"
        fpl_file = request.files.get('fpl_file')
        briefing_pdf = request.files.get('briefing_pdf')
        flight_plan_raw = None
        flight_plan_source = None
        briefing_pdf_filename = None
        if fpl_file and fpl_file.filename:
            try:
                content = fpl_file.read().decode('utf-8', errors='replace')
            except Exception:
                content = None
            if content:
                flight_plan_raw = content
                # Detect MSFS .pln first
                filename_lower = fpl_file.filename.lower()
                if filename_lower.endswith('.pln') or '<SimBase.Document' in content:
                    flight_plan_source = 'msfs-pln'
                # Simple SimBrief detection heuristic (only override if not already msfs-pln)
                if (flight_plan_source is None) and ('<ofp>' in content or '<plan>' in content or 'SIMBRIEF' in content.upper()):
                    flight_plan_source = 'simbrief'
                # Attempt route extraction if not manually provided
                if not request.form.get('route'):
                    route_extracted = None
                    if flight_plan_source == 'simbrief':
                        m_rt = re.search(r'<route_text>(.*?)</route_text>', content, re.DOTALL)
                        if m_rt:
                            route_extracted = m_rt.group(1).strip()
                        else:
                            m_line = re.search(r'ROUTE:?\s*(.+)', content)
                            route_extracted = m_line.group(1).strip() if m_line else None
                    elif flight_plan_source == 'msfs-pln':
                        parsed = parse_pln(content)
                        route_extracted = parsed.get('route_str')
                    # Will assign after object creation if available
        dispatch_entry = DispatchRelease(
            date=request.form.get('date'),
            flight_id=request.form.get('flight_id'),
            aircraft=aircraft_text,
            fleet_entry_id=fleet_entry_id,
            departure=request.form.get('departure'),
            destination=request.form.get('destination'),
            offblocks=request.form.get('offblocks'),
            arrival=request.form.get('arrival'),
            route=request.form.get('route'),
            payload_planned=request.form.get('payload_planned'),
            fuel_planned=request.form.get('fuel_planned'),
            cargo_plan=request.form.get('cargo_plan'),
            alt_airports=request.form.get('alt_airports'),
            weather_brief=request.form.get('weather_brief'),
            special_notes=request.form.get('special_notes')
        )
        if flight_plan_raw:
            dispatch_entry.flight_plan_raw = flight_plan_raw
            dispatch_entry.flight_plan_source = flight_plan_source
            # If route blank, attempt extraction again (variables inside earlier block)
            if not dispatch_entry.route:
                if flight_plan_source == 'simbrief':
                    m_rt = re.search(r'<route_text>(.*?)</route_text>', flight_plan_raw, re.DOTALL)
                    if m_rt:
                        dispatch_entry.route = m_rt.group(1).strip()
                    else:
                        m_line = re.search(r'ROUTE:?\s*(.+)', flight_plan_raw)
                        if m_line:
                            dispatch_entry.route = m_line.group(1).strip()
                elif flight_plan_source == 'msfs-pln':
                    parsed = parse_pln(flight_plan_raw)
                    if parsed.get('route_str'):
                        dispatch_entry.route = parsed['route_str']
        # Persist now so we have an ID for PDF naming
        db.session.add(dispatch_entry)
        db.session.flush()  # obtain ID without full commit for naming
        # Handle PDF upload (store in ./briefings directory)
        if briefing_pdf and briefing_pdf.filename and briefing_pdf.filename.lower().endswith('.pdf'):
            # Ensure directory
            brief_dir = os.path.join(base_dir, 'briefings')
            os.makedirs(brief_dir, exist_ok=True)
            safe_name = f"dispatch_{dispatch_entry.id}_briefing.pdf"
            pdf_path = os.path.join(brief_dir, safe_name)
            try:
                briefing_pdf.save(pdf_path)
                briefing_pdf_filename = safe_name
                dispatch_entry.briefing_pdf_filename = briefing_pdf_filename
            except Exception as e:
                flash(f'Failed to save PDF briefing: {e}', 'error')
        errors = []
        if dispatch_entry.payload_planned:
            try:
                float(dispatch_entry.payload_planned)
            except ValueError:
                errors.append('Planned payload must be numeric.')
        if dispatch_entry.fuel_planned:
            try:
                float(dispatch_entry.fuel_planned)
            except ValueError:
                errors.append('Planned fuel must be numeric.')
        if errors:
            for e in errors:
                flash(e, 'error')
            defaults = {k: request.form.get(k,'') for k in ['date','flight_id','departure','destination','offblocks','arrival','route','payload_planned','fuel_planned','cargo_plan','alt_airports','weather_brief','special_notes']}
            defaults['fleet_entry_id'] = fleet_entry_id or ''
            cargo_manifest_options = CargoManifest.query.filter_by(dispatch_release_id=None).order_by(CargoManifest.id.desc()).limit(25).all()
            fleet_entry_options = FleetEntry.query.order_by(FleetEntry.status.asc(), FleetEntry.registration.asc()).all()
            return render_template('dispatch_form.html', defaults=defaults, cargo_manifest_options=cargo_manifest_options, fleet_entry_options=fleet_entry_options)
        db.session.commit()
        # Economy: create transactions (revenue and expenses) and update balance
        revenue, costs, profit, _dist = compute_dispatch_financials(dispatch_entry)
        acct = CompanyAccount.query.first()
        if acct:
            # Revenue transaction
            db.session.add(Transaction(type='revenue', amount=revenue, description=f'Dispatch #{dispatch_entry.id} revenue', dispatch_release_id=dispatch_entry.id))
            acct.balance += revenue
            # Expense transaction (costs)
            if costs > 0:
                db.session.add(Transaction(type='expense', amount=costs, description=f'Dispatch #{dispatch_entry.id} operational costs', dispatch_release_id=dispatch_entry.id))
                acct.balance -= costs
            db.session.commit()
        # Optional link existing cargo manifest
        cargo_manifest_id = request.form.get('cargo_manifest_id') or None
        create_cargo_next = request.form.get('create_cargo_next') == 'on'
        if cargo_manifest_id:
            manifest = CargoManifest.query.get(cargo_manifest_id)
            if manifest:
                manifest.dispatch_release_id = dispatch_entry.id
                db.session.commit()
                # Recalculate actual cargo weight
                weights = []
                for m in dispatch_entry.cargo_manifests.all():
                    try:
                        weights.append(float(m.total_weight))
                    except (TypeError, ValueError):
                        pass
                total = sum(weights)
                if weights:
                    dispatch_entry.actual_cargo_weight = str(int(total)) if float(total).is_integer() else f"{total:.1f}"
                    db.session.commit()
        if create_cargo_next:
            return redirect(url_for('cargo', date=dispatch_entry.date, flight_id=dispatch_entry.flight_id,
                                    aircraft=dispatch_entry.aircraft, departure=dispatch_entry.departure,
                                    arrival=dispatch_entry.destination, dispatch_release_id=dispatch_entry.id))
        return redirect(url_for('dispatch_detail', id=dispatch_entry.id))
    defaults = {
        'date': request.args.get('date', ''),
        'flight_id': request.args.get('flight_id', ''),
        'fleet_entry_id': request.args.get('fleet_entry_id', ''),
        'departure': request.args.get('departure', ''),
        'destination': request.args.get('destination', ''),
        'offblocks': request.args.get('offblocks', ''),
        'arrival': request.args.get('arrival', ''),
        'route': request.args.get('route', ''),
        'payload_planned': request.args.get('payload_planned', ''),
        'fuel_planned': request.args.get('fuel_planned', ''),
        'cargo_plan': request.args.get('cargo_plan', ''),
        'alt_airports': request.args.get('alt_airports', ''),
        'weather_brief': request.args.get('weather_brief', ''),
        'special_notes': request.args.get('special_notes', '')
    }
    cargo_manifest_options = CargoManifest.query.filter_by(dispatch_release_id=None).order_by(CargoManifest.id.desc()).limit(25).all()
    fleet_entry_options = FleetEntry.query.order_by(FleetEntry.status.asc(), FleetEntry.registration.asc()).all()
    return render_template('dispatch_form.html', defaults=defaults, cargo_manifest_options=cargo_manifest_options, fleet_entry_options=fleet_entry_options)

@app.route('/dispatch/<int:id>')
@login_required
def dispatch_detail(id):
    d = DispatchRelease.query.get_or_404(id)
    linked_manifests = d.cargo_manifests.order_by(CargoManifest.id.desc()).all()
    crew_logs = CrewLog.query.filter_by(dispatch_release_id=d.id).order_by(CrewLog.id.desc()).all()
    pln_data = None
    if d.flight_plan_raw and (d.flight_plan_source == 'msfs-pln' or '<SimBase.Document' in d.flight_plan_raw):
        pln_data = parse_pln(d.flight_plan_raw)
    revenue, costs, profit, distance_nm = compute_dispatch_financials(d)
    return render_template('dispatch_detail.html', d=d, linked_manifests=linked_manifests, crew_logs=crew_logs, pln=pln_data, fin_summary={'revenue':revenue,'costs':costs,'profit':profit,'distance_nm':distance_nm})

@app.route('/dispatch/<int:id>/simbrief')
@login_required
def dispatch_simbrief(id):
    d = DispatchRelease.query.get_or_404(id)
    import urllib.parse
    aircraft_type = None
    reg = None
    if d.aircraft:
        parts = d.aircraft.split()
        if len(parts) >= 2:
            aircraft_type = parts[0]
            reg = parts[1]
        else:
            aircraft_type = parts[0]
    alt_code = None
    if d.alt_airports:
        # Use first token (split on comma or whitespace)
        first = d.alt_airports.replace('\n',' ').split(',')[0].split()[0].strip()
        if first:
            alt_code = first
    params = {}
    if d.flight_id: params['callsign'] = d.flight_id
    if d.departure: params['orig'] = d.departure
    if d.destination: params['dest'] = d.destination
    if alt_code: params['alternate'] = alt_code
    if d.route: params['route'] = d.route[:1800]  # avoid overly long URL
    if aircraft_type: params['aircraft'] = aircraft_type
    if reg: params['reg'] = reg
    # Optional extras (best-effort; may be ignored by SimBrief)
    # if d.fuel_planned: params['fuel'] = d.fuel_planned
    base_url = 'https://www.simbrief.com/system/dispatch.php'
    url = base_url + '?' + urllib.parse.urlencode(params, doseq=True, safe='/:')
    return redirect(url)

@app.route('/dispatch/<int:id>/edit', methods=['GET', 'POST'])
@roles_required('Manager', 'Administrator')
def dispatch_edit(id):
    d = DispatchRelease.query.get_or_404(id)
    if request.method == 'POST':
        fields = ['date','flight_id','aircraft','departure','destination','offblocks','arrival','route',
                  'payload_planned','fuel_planned','cargo_plan','alt_airports','weather_brief','special_notes']
        for f in fields:
            setattr(d, f, request.form.get(f))
        # fleet selection
        fleet_entry_id = request.form.get('fleet_entry_id') or None
        if fleet_entry_id:
            fe = FleetEntry.query.get(fleet_entry_id)
            if fe:
                d.fleet_entry_id = fe.id
                d.aircraft = f"{fe.aircraft_type} {fe.registration}"
        else:
            d.fleet_entry_id = None
        # Optional new flight plan upload during edit
        fpl_file = request.files.get('fpl_file')
        briefing_pdf = request.files.get('briefing_pdf')
        if fpl_file and fpl_file.filename:
            try:
                content = fpl_file.read().decode('utf-8', errors='replace')
            except Exception:
                content = None
            if content:
                d.flight_plan_raw = content
                filename_lower = fpl_file.filename.lower()
                if filename_lower.endswith('.pln') or '<SimBase.Document' in content:
                    d.flight_plan_source = 'msfs-pln'
                elif '<ofp>' in content or '<plan>' in content or 'SIMBRIEF' in content.upper():
                    d.flight_plan_source = 'simbrief'
                # If route blank after edit, attempt extraction
                if not d.route:
                    if d.flight_plan_source == 'simbrief':
                        m_rt = re.search(r'<route_text>(.*?)</route_text>', content, re.DOTALL)
                        if m_rt:
                            d.route = m_rt.group(1).strip()
                        else:
                            m_line = re.search(r'ROUTE:?\s*(.+)', content)
                            if m_line:
                                d.route = m_line.group(1).strip()
                    elif d.flight_plan_source == 'msfs-pln':
                        parsed = parse_pln(content)
                        if parsed.get('route_str'):
                            d.route = parsed['route_str']
        # Handle briefing PDF upload on edit (outside of flight plan block so it works independently)
        if briefing_pdf and briefing_pdf.filename and briefing_pdf.filename.lower().endswith('.pdf'):
            brief_dir = os.path.join(base_dir, 'briefings')
            os.makedirs(brief_dir, exist_ok=True)
            safe_name = f"dispatch_{d.id}_briefing.pdf"
            pdf_path = os.path.join(brief_dir, safe_name)
            try:
                briefing_pdf.save(pdf_path)
                d.briefing_pdf_filename = safe_name
            except Exception as e:
                flash(f'Failed to save PDF briefing: {e}', 'error')
        errors = []
        if d.payload_planned:
            try:
                float(d.payload_planned)
            except ValueError:
                errors.append('Planned payload must be numeric.')
        if d.fuel_planned:
            try:
                float(d.fuel_planned)
            except ValueError:
                errors.append('Planned fuel must be numeric.')
        if errors:
            for e in errors:
                flash(e, 'error')
            defaults = {
                'date': d.date,
                'flight_id': d.flight_id,
                'aircraft': d.aircraft,
                'fleet_entry_id': d.fleet_entry_id or '',
                'departure': d.departure,
                'destination': d.destination,
                'offblocks': d.offblocks,
                'arrival': d.arrival,
                'route': d.route,
                'payload_planned': d.payload_planned,
                'fuel_planned': d.fuel_planned,
                'cargo_plan': d.cargo_plan,
                'alt_airports': d.alt_airports,
                'weather_brief': d.weather_brief,
                'special_notes': d.special_notes,
                'actual_cargo_weight': d.actual_cargo_weight
            }
            linked_manifests = d.cargo_manifests.order_by(CargoManifest.id.desc()).all()
            cargo_manifest_options = CargoManifest.query.filter_by(dispatch_release_id=None).order_by(CargoManifest.id.desc()).limit(25).all()
            fleet_entry_options = FleetEntry.query.order_by(FleetEntry.status.asc(), FleetEntry.registration.asc()).all()
            return render_template('dispatch_form.html', defaults=defaults, edit_id=d.id, linked_manifests=linked_manifests, cargo_manifest_options=cargo_manifest_options, fleet_entry_options=fleet_entry_options)
        db.session.commit()
        # Retroactively adjust revenue/expense transactions for this dispatch
        acct = CompanyAccount.query.first()
        if acct:
            new_rev, new_costs, new_profit, _dist = compute_dispatch_financials(d)
            rev_tx = Transaction.query.filter_by(dispatch_release_id=d.id, type='revenue').filter(Transaction.description.like(f'Dispatch #{d.id} revenue%')).first()
            cost_tx = Transaction.query.filter_by(dispatch_release_id=d.id, type='expense').filter(Transaction.description.like(f'Dispatch #{d.id} operational costs%')).first()
            if rev_tx:
                delta = new_rev - rev_tx.amount
                rev_tx.amount = new_rev
                acct.balance += delta
            else:
                db.session.add(Transaction(type='revenue', amount=new_rev, description=f'Dispatch #{d.id} revenue (retro)', dispatch_release_id=d.id))
                acct.balance += new_rev
            if cost_tx:
                delta_c = new_costs - cost_tx.amount
                cost_tx.amount = new_costs
                acct.balance -= delta_c
            else:
                db.session.add(Transaction(type='expense', amount=new_costs, description=f'Dispatch #{d.id} operational costs (retro)', dispatch_release_id=d.id))
                acct.balance -= new_costs
            db.session.commit()
        # Optional link existing cargo manifest on edit
        cargo_manifest_id = request.form.get('cargo_manifest_id') or None
        create_cargo_next = request.form.get('create_cargo_next') == 'on'
        if cargo_manifest_id:
            manifest = CargoManifest.query.get(cargo_manifest_id)
            if manifest:
                manifest.dispatch_release_id = d.id
                db.session.commit()
                # Recalculate aggregated cargo weight
                weights = []
                for m2 in d.cargo_manifests.all():
                    try:
                        weights.append(float(m2.total_weight))
                    except (TypeError, ValueError):
                        pass
                total = sum(weights)
                d.actual_cargo_weight = str(int(total)) if weights and float(total).is_integer() else (f"{total:.1f}" if weights else None)
                db.session.commit()
        if create_cargo_next:
            return redirect(url_for('cargo', date=d.date, flight_id=d.flight_id,
                                    aircraft=d.aircraft, departure=d.departure,
                                    arrival=d.destination, dispatch_release_id=d.id))
        return redirect(url_for('dispatch_detail', id=d.id))
    defaults = {
        'date': d.date,
        'flight_id': d.flight_id,
        'aircraft': d.aircraft,
        'fleet_entry_id': d.fleet_entry_id or '',
        'departure': d.departure,
        'destination': d.destination,
        'offblocks': d.offblocks,
        'arrival': d.arrival,
        'route': d.route,
        'payload_planned': d.payload_planned,
        'fuel_planned': d.fuel_planned,
        'cargo_plan': d.cargo_plan,
        'alt_airports': d.alt_airports,
        'weather_brief': d.weather_brief,
        'special_notes': d.special_notes,
        'actual_cargo_weight': d.actual_cargo_weight,
        'flight_plan_raw': d.flight_plan_raw,
        'flight_plan_source': d.flight_plan_source,
        'briefing_pdf_filename': d.briefing_pdf_filename
    }
    cargo_manifest_options = CargoManifest.query.filter_by(dispatch_release_id=None).order_by(CargoManifest.id.desc()).limit(25).all()
    linked_manifests = d.cargo_manifests.order_by(CargoManifest.id.desc()).all()
    crew_logs = CrewLog.query.filter_by(dispatch_release_id=d.id).order_by(CrewLog.id.desc()).all()
    fleet_entry_options = FleetEntry.query.order_by(FleetEntry.status.asc(), FleetEntry.registration.asc()).all()
    return render_template('dispatch_form.html', defaults=defaults, edit_id=d.id, cargo_manifest_options=cargo_manifest_options, linked_manifests=linked_manifests, crew_logs=crew_logs, fleet_entry_options=fleet_entry_options)

@app.route('/dispatch/<int:id>/toggle_complete', methods=['POST'])
@roles_required('Manager', 'Administrator')
def dispatch_toggle_complete(id):
    d = DispatchRelease.query.get_or_404(id)
    d.completed = 0 if d.completed == 1 else 1
    db.session.commit()
    flash(f'Dispatch #{d.id} marked {"completed" if d.completed==1 else "in-progress"}.', 'success')
    return redirect(url_for('dispatch_detail', id=d.id))

@app.route('/economy')
@login_required
def economy_ledger():
    acct = CompanyAccount.query.first()
    txns = Transaction.query.order_by(Transaction.timestamp.desc()).limit(200).all()
    return render_template('economy_ledger.html', account=acct, transactions=txns, constants=ECONOMY_CONSTANTS)


@app.route('/settings', methods=['GET', 'POST'])
@roles_required('Manager', 'Administrator')
def settings():
    settings_obj = AppSettings.query.first()
    if not settings_obj:
        settings_obj = AppSettings()
        db.session.add(settings_obj)
        db.session.commit()
    
    if request.method == 'POST':
        settings_obj.company_name = request.form.get('company_name') or 'Palm Route Air'
        settings_obj.difficulty = request.form.get('difficulty') or 'Normal'
        settings_obj.currency_symbol = request.form.get('currency_symbol') or '$'
        settings_obj.distance_unit = request.form.get('distance_unit') or 'NM'
        settings_obj.weight_unit = request.form.get('weight_unit') or 'lbs'
        settings_obj.show_workflow_help = 1 if request.form.get('show_workflow_help') == 'on' else 0
        
        # Realism settings - parse floats with validation
        try:
            settings_obj.realism_fuel_variance = float(request.form.get('realism_fuel_variance', 0.05))
        except ValueError:
            settings_obj.realism_fuel_variance = 0.05
        
        try:
            settings_obj.realism_destination_penalty = float(request.form.get('realism_destination_penalty', 0.25))
        except ValueError:
            settings_obj.realism_destination_penalty = 0.25
        
        # Handle logo upload
        logo_file = request.files.get('logo_file')
        if logo_file and logo_file.filename:
            # Create logos directory if it doesn't exist
            logos_dir = os.path.join(base_dir, 'static', 'logos')
            os.makedirs(logos_dir, exist_ok=True)
            
            # Save with sanitized filename
            safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', logo_file.filename)
            logo_path = os.path.join(logos_dir, safe_filename)
            logo_file.save(logo_path)
            settings_obj.logo_filename = safe_filename
        
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('settings'))
    
    return render_template('settings.html', settings=settings_obj)

@app.route('/reset_game', methods=['POST'])
@roles_required('Administrator')
def reset_game():
    """Reset the entire game database and optionally seed with sample data"""
    try:
        # Get the seed_data option from form
        seed_data = request.form.get('seed_data') == 'yes'
        
        # Delete all data from all tables (except settings which we'll reset separately)
        Transaction.query.delete()
        Incident.query.delete()
        CrewLog.query.delete()
        CargoManifest.query.delete()
        DispatchRelease.query.delete()
        CompanyNotam.query.delete()
        FleetEntry.query.delete()
        
        # Reset company account balance to 0
        acct = CompanyAccount.query.first()
        if acct:
            acct.balance = 0.0
        else:
            acct = CompanyAccount(balance=0.0)
            db.session.add(acct)
        
        db.session.commit()
        
        # Seed sample data if requested
        if seed_data:
            seed_sample_data()
            flash('Game reset successfully with sample data!', 'success')
        else:
            flash('Game reset successfully! Starting with a clean slate.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error resetting game: {str(e)}', 'error')
    
    return redirect(url_for('index'))


@app.route('/dispatch/<int:id>/briefing_pdf')
@login_required
def dispatch_briefing_pdf(id):
    d = DispatchRelease.query.get_or_404(id)
    if not d.briefing_pdf_filename:
        abort(404)
    brief_dir = os.path.join(base_dir, 'briefings')
    file_path = os.path.join(brief_dir, d.briefing_pdf_filename)
    if not os.path.isfile(file_path):
        abort(404)
    return send_from_directory(brief_dir, d.briefing_pdf_filename, mimetype='application/pdf')

@app.route('/dispatch/<int:dispatch_id>/unlink_manifest/<int:manifest_id>', methods=['POST'])
@roles_required('Manager', 'Administrator')
def dispatch_unlink_manifest(dispatch_id, manifest_id):
    d = DispatchRelease.query.get_or_404(dispatch_id)
    m = CargoManifest.query.get_or_404(manifest_id)
    if m.dispatch_release_id == d.id:
        m.dispatch_release_id = None
        db.session.commit()
        # Recalculate aggregated cargo after unlink
        weights = []
        for rem in d.cargo_manifests.all():
            try:
                weights.append(float(rem.total_weight))
            except (TypeError, ValueError):
                pass
        total = sum(weights)
        d.actual_cargo_weight = str(int(total)) if weights and float(total).is_integer() else (f"{total:.1f}" if weights else None)
        db.session.commit()
        flash(f'Cargo Manifest #{manifest_id} unlinked.', 'warning')
    return redirect(url_for('dispatch_edit', id=dispatch_id))


@app.route('/dispatch/history')
@login_required
def dispatch_history():
    releases = DispatchRelease.query.order_by(DispatchRelease.id.desc()).all()
    return render_template('dispatch_history.html', releases=releases)


@app.route('/crew', methods=['GET', 'POST'])
@login_required
def crew():
    if request.method == 'POST':
        log = CrewLog(
            date=request.form.get('date'),
            flight_id=request.form.get('flight_id'),
            origin=request.form.get('origin'),
            destination=request.form.get('destination'),
            aircraft=request.form.get('aircraft'),
            block_off=request.form.get('block_off'),
            block_on=request.form.get('block_on'),
            block_time=request.form.get('block_time'),
            cargo_weight=request.form.get('cargo_weight'),
            fuel_used=request.form.get('fuel_used'),
            remarks=request.form.get('remarks'),
            dispatch_release_id=request.form.get('dispatch_release_id') or None,
            cargo_manifest_id=request.form.get('cargo_manifest_id') or None
        )
        db.session.add(log)
        db.session.commit()
        # Fuel reconciliation: compare planned vs actual and create adjustment transaction
        if log.dispatch_release_id and log.fuel_used:
            dr = DispatchRelease.query.get(log.dispatch_release_id)
            acct = CompanyAccount.query.first()
            if dr and acct:
                try:
                    actual_fuel = float(log.fuel_used)
                except ValueError:
                    actual_fuel = None
                planned_fuel = None
                if dr.fuel_planned:
                    try:
                        planned_fuel = float(dr.fuel_planned)
                    except ValueError:
                        planned_fuel = None
                if actual_fuel is not None and planned_fuel is not None:
                    planned_cost = planned_fuel * ECONOMY_CONSTANTS['FUEL_COST_PER_UNIT']
                    actual_cost = actual_fuel * ECONOMY_CONSTANTS['FUEL_COST_PER_UNIT']
                    diff = actual_cost - planned_cost
                    if abs(diff) >= 0.01:  # meaningful difference
                        if diff > 0:  # extra expense
                            db.session.add(Transaction(type='expense', amount=diff, description=f'Fuel overrun dispatch #{dr.id}', dispatch_release_id=dr.id, crew_log_id=log.id))
                            acct.balance -= diff
                        else:  # savings
                            savings = -diff
                            db.session.add(Transaction(type='revenue', amount=savings, description=f'Fuel savings dispatch #{dr.id}', dispatch_release_id=dr.id, crew_log_id=log.id))
                            acct.balance += savings
                        db.session.commit()
        return redirect(url_for('crew_history'))
    defaults = {
        'date': request.args.get('date', ''),
        'flight_id': request.args.get('flight_id', ''),
        'origin': request.args.get('origin', ''),
        'destination': request.args.get('destination', ''),
        'aircraft': request.args.get('aircraft', ''),
        'block_off': request.args.get('block_off', ''),
        'block_on': request.args.get('block_on', ''),
        'block_time': request.args.get('block_time', ''),
        'cargo_weight': request.args.get('cargo_weight', ''),
        'remarks': request.args.get('remarks', ''),
        'dispatch_release_id': request.args.get('dispatch_release_id', ''),
        'cargo_manifest_id': request.args.get('cargo_manifest_id', '')
    }
    return render_template('crew_form.html', defaults=defaults)


@app.route('/crew/history')
@login_required
def crew_history():
    logs = CrewLog.query.order_by(CrewLog.id.desc()).all()
    return render_template('crew_history.html', logs=logs)


@app.route('/notams', methods=['GET', 'POST'])
@login_required
def notams():
    if request.method == 'POST':
        notam = CompanyNotam(
            notam_id=request.form.get('notam_id'),
            subject=request.form.get('subject'),
            area=request.form.get('area'),
            text=request.form.get('text'),
            status=request.form.get('status')
        )
        db.session.add(notam)
        db.session.commit()
        return redirect(url_for('notams_history'))
    return render_template('notams_form.html')


@app.route('/notams/history')
@login_required
def notams_history():
    notams = CompanyNotam.query.order_by(CompanyNotam.id.desc()).all()
    return render_template('notams_history.html', notams=notams)


@app.route('/fleet', methods=['GET', 'POST'])
@roles_required('Manager', 'Administrator')
def fleet():
    if request.method == 'POST':
        entry = FleetEntry(
            aircraft_type=request.form.get('aircraft_type'),
            registration=request.form.get('registration'),
            base=request.form.get('base'),
            status=request.form.get('status'),
            max_takeoff_weight=request.form.get('max_takeoff_weight'),
            useful_load=request.form.get('useful_load'),
            notes=request.form.get('notes')
        )
        errors = []
        for field in ['max_takeoff_weight','useful_load']:
            val = getattr(entry, field)
            if val:
                try:
                    float(val)
                except ValueError:
                    errors.append(f"{field.replace('_',' ').title()} must be numeric.")
        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('fleet_form.html', defaults={
                'aircraft_type': entry.aircraft_type,
                'registration': entry.registration,
                'base': entry.base,
                'status': entry.status,
                'max_takeoff_weight': entry.max_takeoff_weight,
                'useful_load': entry.useful_load,
                'notes': entry.notes
            })
        db.session.add(entry)
        db.session.commit()
        return redirect(url_for('fleet_history'))
    defaults = {
        'aircraft_type': request.args.get('aircraft_type',''),
        'registration': request.args.get('registration',''),
        'base': request.args.get('base',''),
        'status': request.args.get('status','Active'),
        'max_takeoff_weight': request.args.get('max_takeoff_weight',''),
        'useful_load': request.args.get('useful_load',''),
        'notes': request.args.get('notes','')
    }
    return render_template('fleet_form.html', defaults=defaults)


@app.route('/fleet/history')
@login_required
def fleet_history():
    entries = FleetEntry.query.order_by(FleetEntry.id.desc()).all()
    return render_template('fleet_history.html', entries=entries)

# Delete routes (POST only)
@app.route('/cargo/delete/<int:id>', methods=['POST'])
@roles_required('Manager', 'Administrator')
def delete_cargo(id):
    obj = CargoManifest.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('cargo_history'))

@app.route('/dispatch/delete/<int:id>', methods=['POST'])
@roles_required('Manager', 'Administrator')
def delete_dispatch(id):
    obj = DispatchRelease.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('dispatch_history'))

@app.route('/crew/delete/<int:id>', methods=['POST'])
@roles_required('Manager', 'Administrator')
def delete_crew(id):
    obj = CrewLog.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('crew_history'))

@app.route('/notams/delete/<int:id>', methods=['POST'])
@roles_required('Manager', 'Administrator')
def delete_notam(id):
    obj = CompanyNotam.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('notams_history'))

@app.route('/fleet/delete/<int:id>', methods=['POST'])
@roles_required('Manager', 'Administrator')
def delete_fleet(id):
    obj = FleetEntry.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('fleet_history'))

@app.route('/fleet/<int:id>/edit', methods=['GET','POST'])
@roles_required('Manager', 'Administrator')
def fleet_edit(id):
    f = FleetEntry.query.get_or_404(id)
    if request.method == 'POST':
        fields = ['aircraft_type','registration','base','status','max_takeoff_weight','useful_load','notes']
        for fld in fields:
            setattr(f, fld, request.form.get(fld))
        errors = []
        for numeric in ['max_takeoff_weight','useful_load']:
            val = getattr(f, numeric)
            if val:
                try:
                    float(val)
                except ValueError:
                    errors.append(f"{numeric.replace('_',' ').title()} must be numeric.")
        if errors:
            for e in errors:
                flash(e, 'error')
            defaults_err = {fld: getattr(f, fld) for fld in fields}
            return render_template('fleet_form.html', defaults=defaults_err, edit_id=f.id)
        db.session.commit()
        return redirect(url_for('fleet_detail', id=f.id))
    defaults = {
        'aircraft_type': f.aircraft_type,
        'registration': f.registration,
        'base': f.base,
        'status': f.status,
        'max_takeoff_weight': f.max_takeoff_weight,
        'useful_load': f.useful_load,
        'notes': f.notes
    }
    return render_template('fleet_form.html', defaults=defaults, edit_id=f.id)

# Detail routes & editing for cargo
@app.route('/cargo/<int:id>', methods=['GET','POST'])
@login_required
def cargo_detail(id):
    m = CargoManifest.query.get_or_404(id)
    if request.method == 'POST':
        old_dispatch_id = m.dispatch_release_id
        m.date = request.form.get('date')
        m.departure = request.form.get('departure')
        m.arrival = request.form.get('arrival')
        m.total_weight = request.form.get('total_weight')
        m.pieces = request.form.get('pieces')
        m.notes = request.form.get('notes')
        dispatch_val = request.form.get('dispatch_release_id')
        m.dispatch_release_id = int(dispatch_val) if dispatch_val else None
        errors = []
        if m.total_weight:
            try:
                float(m.total_weight)
            except ValueError:
                errors.append('Total weight must be numeric.')
        if m.pieces:
            try:
                int(m.pieces)
            except ValueError:
                errors.append('Pieces must be an integer.')
        if errors:
            for e in errors:
                flash(e,'error')
            dispatch_options = DispatchRelease.query.order_by(DispatchRelease.id.desc()).limit(50).all()
            signoffs = m.signoffs.order_by(CargoManifestSignOff.timestamp.asc()).all()
            return render_template('cargo_detail.html', m=m, dispatch_options=dispatch_options, editing=True, signoffs=signoffs)
        db.session.commit()
        # Recalculate cargo weights for old and new dispatch links
        if old_dispatch_id and old_dispatch_id != m.dispatch_release_id:
            d_old = DispatchRelease.query.get(old_dispatch_id)
            if d_old:
                weights = []
                for cm in d_old.cargo_manifests.all():
                    try:
                        weights.append(float(cm.total_weight))
                    except (TypeError, ValueError):
                        pass
                total = sum(weights)
                d_old.actual_cargo_weight = str(int(total)) if weights and float(total).is_integer() else (f"{total:.1f}" if weights else None)
                db.session.commit()
        if m.dispatch_release_id:
            d_new = DispatchRelease.query.get(m.dispatch_release_id)
            if d_new:
                weights = []
                for cm in d_new.cargo_manifests.all():
                    try:
                        weights.append(float(cm.total_weight))
                    except (TypeError, ValueError):
                        pass
                total = sum(weights)
                d_new.actual_cargo_weight = str(int(total)) if weights and float(total).is_integer() else (f"{total:.1f}" if weights else None)
                db.session.commit()
        flash('Cargo manifest updated.', 'success')
        return redirect(url_for('cargo_detail', id=m.id))
    dispatch_options = DispatchRelease.query.order_by(DispatchRelease.id.desc()).limit(50).all()
    editing_flag = True if request.args.get('edit') == '1' else False
    signoffs = m.signoffs.order_by(CargoManifestSignOff.timestamp.asc()).all()
    return render_template('cargo_detail.html', m=m, dispatch_options=dispatch_options, editing=editing_flag, signoffs=signoffs)

@app.route('/cargo/<int:id>/unlink_dispatch', methods=['POST'])
@roles_required('Manager', 'Administrator')
def cargo_unlink_dispatch(id):
    m = CargoManifest.query.get_or_404(id)
    if m.dispatch_release_id:
        old_id = m.dispatch_release_id
        m.dispatch_release_id = None
        db.session.commit()
        d_old = DispatchRelease.query.get(old_id)
        if d_old:
            weights = []
            for cm in d_old.cargo_manifests.all():
                try:
                    weights.append(float(cm.total_weight))
                except (TypeError, ValueError):
                    pass
            total = sum(weights)
            d_old.actual_cargo_weight = str(int(total)) if weights and float(total).is_integer() else (f"{total:.1f}" if weights else None)
            db.session.commit()
        flash('Dispatch linkage removed.', 'warning')
    return redirect(url_for('cargo_detail', id=id))

@app.route('/crew/<int:id>')
@login_required
def crew_detail(id):
    c = CrewLog.query.get_or_404(id)
    dispatch_ref = DispatchRelease.query.get(c.dispatch_release_id) if c.dispatch_release_id else None
    cargo_ref = CargoManifest.query.get(c.cargo_manifest_id) if c.cargo_manifest_id else None
    signoffs = c.signoffs.order_by(CrewLogSignOff.timestamp.asc()).all()
    return render_template('crew_detail.html', c=c, dispatch_ref=dispatch_ref, cargo_ref=cargo_ref, signoffs=signoffs)

@app.route('/crew/<int:id>/edit', methods=['GET','POST'])
@roles_required('Manager', 'Administrator')
def crew_edit(id):
    c = CrewLog.query.get_or_404(id)
    if request.method == 'POST':
        old_fuel = c.fuel_used
        fields = ['date','flight_id','origin','destination','aircraft','block_off','block_on','block_time','cargo_weight','fuel_used','remarks']
        for f in fields:
            setattr(c, f, request.form.get(f))
        db.session.commit()
        # Adjust fuel reconciliation transaction if fuel changed and dispatch linked
        if c.dispatch_release_id and c.fuel_used:
            dr = DispatchRelease.query.get(c.dispatch_release_id)
            acct = CompanyAccount.query.first()
            if dr and acct:
                try:
                    actual_fuel = float(c.fuel_used)
                except ValueError:
                    actual_fuel = None
                planned_fuel = None
                if dr.fuel_planned:
                    try:
                        planned_fuel = float(dr.fuel_planned)
                    except ValueError:
                        planned_fuel = None
                if actual_fuel is not None and planned_fuel is not None:
                    planned_cost = planned_fuel * ECONOMY_CONSTANTS['FUEL_COST_PER_UNIT']
                    diff = (actual_fuel * ECONOMY_CONSTANTS['FUEL_COST_PER_UNIT']) - planned_cost
                    existing_tx = Transaction.query.filter_by(crew_log_id=c.id).filter(Transaction.description.like(f'Fuel % dispatch #{dr.id}')).first()
                    if existing_tx:
                        # Reverse old balance effect
                        if existing_tx.type == 'expense':
                            acct.balance += existing_tx.amount
                        else:
                            acct.balance -= existing_tx.amount
                        db.session.delete(existing_tx)
                        db.session.commit()
                    if abs(diff) >= 0.01:
                        if diff > 0:
                            db.session.add(Transaction(type='expense', amount=diff, description=f'Fuel overrun dispatch #{dr.id}', dispatch_release_id=dr.id, crew_log_id=c.id))
                            acct.balance -= diff
                        else:
                            savings = -diff
                            db.session.add(Transaction(type='revenue', amount=savings, description=f'Fuel savings dispatch #{dr.id}', dispatch_release_id=dr.id, crew_log_id=c.id))
                            acct.balance += savings
                        db.session.commit()
        return redirect(url_for('crew_detail', id=c.id))
    defaults = {f: getattr(c,f) for f in ['date','flight_id','origin','destination','aircraft','block_off','block_on','block_time','cargo_weight','fuel_used','remarks']}
    return render_template('crew_edit.html', c=c, defaults=defaults)

@app.route('/notams/<int:id>')
@login_required
def notam_detail(id):
    n = CompanyNotam.query.get_or_404(id)
    return render_template('notam_detail.html', n=n)

@app.route('/fleet/<int:id>')
@login_required
def fleet_detail(id):
    f = FleetEntry.query.get_or_404(id)
    return render_template('fleet_detail.html', f=f)


# --- Authentication & Pilot Profile ---
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = Employee.query.filter(db.func.lower(Employee.email)==email).first()
        if user and user.check_password(password):
            session['employee_id'] = user.id
            flash(f'Welcome, {user.name}!', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('employee_id', None)
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET','POST'])
def profile():
    if not session.get('employee_id'):
        return redirect(url_for('login'))
    emp = Employee.query.get(session['employee_id'])
    if request.method == 'POST':
        emp.name = request.form.get('name') or emp.name
        emp.role = request.form.get('role') or emp.role
        new_pw = request.form.get('new_password')
        if new_pw:
            emp.set_password(new_pw)
            flash('Password updated.', 'success')
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))
    cargo_signed = CargoManifestSignOff.query.filter_by(employee_id=emp.id).count()
    crew_signed = CrewLogSignOff.query.filter_by(employee_id=emp.id).count()
    return render_template('profile.html', emp=emp, stats={'cargo_signed': cargo_signed, 'crew_signed': crew_signed})

@app.route('/employees', methods=['GET','POST'])
@roles_required('Manager', 'Administrator')
def employees():
    if request.method == 'POST':
        target_id = request.form.get('employee_id')
        new_role = request.form.get('role')
        if target_id and new_role:
            e = Employee.query.get(int(target_id))
            if e:
                e.role = new_role
                db.session.commit()
                flash('Employee role updated.', 'success')
        return redirect(url_for('employees'))
    emps = Employee.query.order_by(Employee.name.asc()).all()
    roles = ['Pilot','Manager','Administrator']
    return render_template('employees.html', employees=emps, roles=roles)

def _require_login():
    if not session.get('employee_id'):
        flash('Login required for sign-off.', 'error')
        return False
    return True

@app.route('/cargo/<int:id>/sign', methods=['POST'])
def cargo_sign(id):
    if not _require_login():
        return redirect(url_for('login'))
    m = CargoManifest.query.get_or_404(id)
    emp_id = session['employee_id']
    existing = CargoManifestSignOff.query.filter_by(cargo_manifest_id=m.id, employee_id=emp_id).first()
    if existing:
        flash('You already signed off this manifest.', 'warning')
    else:
        so = CargoManifestSignOff(cargo_manifest_id=m.id, employee_id=emp_id)
        db.session.add(so)
        db.session.commit()
        flash('Cargo manifest signed off.', 'success')
    return redirect(url_for('cargo_detail', id=m.id))

@app.route('/crew/<int:id>/sign', methods=['POST'])
def crew_sign(id):
    if not _require_login():
        return redirect(url_for('login'))
    c = CrewLog.query.get_or_404(id)
    emp_id = session['employee_id']
    existing = CrewLogSignOff.query.filter_by(crew_log_id=c.id, employee_id=emp_id).first()
    if existing:
        flash('You already signed off this crew log.', 'warning')
    else:
        so = CrewLogSignOff(crew_log_id=c.id, employee_id=emp_id)
        db.session.add(so)
        db.session.commit()
        flash('Crew log signed off.', 'success')
    return redirect(url_for('crew_detail', id=c.id))


if __name__ == '__main__':
    app.run(debug=True)
