from flask import Flask, render_template, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'palm_route_air.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class CargoManifest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    flight_id = db.Column(db.String(20))
    aircraft = db.Column(db.String(50))
    departure = db.Column(db.String(10))
    arrival = db.Column(db.String(10))
    total_weight = db.Column(db.String(20))
    pieces = db.Column(db.String(10))
    notes = db.Column(db.Text)


class DispatchRelease(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    flight_id = db.Column(db.String(20))
    aircraft = db.Column(db.String(50))
    departure = db.Column(db.String(10))
    destination = db.Column(db.String(10))
    offblocks = db.Column(db.String(10))
    arrival = db.Column(db.String(10))
    route = db.Column(db.Text)


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
    remarks = db.Column(db.Text)
    dispatch_release_id = db.Column(db.Integer, db.ForeignKey('dispatch_release.id'))
    cargo_manifest_id = db.Column(db.Integer, db.ForeignKey('cargo_manifest.id'))
    dispatch_release = db.relationship('DispatchRelease', lazy='joined')
    cargo_manifest = db.relationship('CargoManifest', lazy='joined')


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

# Create tables after all model classes have been declared
with app.app_context():
    db.create_all()





@app.route('/')
def index():
    manifests = CargoManifest.query.order_by(CargoManifest.id.desc()).limit(5).all()
    releases = DispatchRelease.query.order_by(DispatchRelease.id.desc()).limit(5).all()
    logs = CrewLog.query.order_by(CrewLog.id.desc()).limit(5).all()
    notams = CompanyNotam.query.order_by(CompanyNotam.id.desc()).limit(5).all()
    fleet_entries = FleetEntry.query.order_by(FleetEntry.id.desc()).all()
    counts = {
        'cargo_manifests': CargoManifest.query.count(),
        'dispatch_releases': DispatchRelease.query.count(),
        'crew_logs': CrewLog.query.count(),
        'company_notams': CompanyNotam.query.count(),
        'fleet_entries': FleetEntry.query.count()
    }
    return render_template('index.html',
                           counts=counts,
                           manifests=manifests,
                           releases=releases,
                           logs=logs,
                           notams=notams,
                           fleet_entries=fleet_entries)


@app.route('/cargo', methods=['GET', 'POST'])
def cargo():
    if request.method == 'POST':
        manifest = CargoManifest(
            date=request.form.get('date'),
            flight_id=request.form.get('flight_id'),
            aircraft=request.form.get('aircraft'),
            departure=request.form.get('departure'),
            arrival=request.form.get('arrival'),
            total_weight=request.form.get('total_weight'),
            pieces=request.form.get('pieces'),
            notes=request.form.get('notes')
        )
        db.session.add(manifest)
        db.session.commit()
        return redirect(url_for('cargo_history'))
    defaults = {
        'date': request.args.get('date', ''),
        'flight_id': request.args.get('flight_id', ''),
        'aircraft': request.args.get('aircraft', ''),
        'departure': request.args.get('departure', ''),
        'arrival': request.args.get('arrival', ''),
        'total_weight': request.args.get('total_weight', ''),
        'pieces': request.args.get('pieces', ''),
        'notes': request.args.get('notes', '')
    }
    return render_template('cargo_form.html', defaults=defaults)


@app.route('/cargo/history')
def cargo_history():
    manifests = CargoManifest.query.order_by(CargoManifest.id.desc()).all()
    return render_template('cargo_history.html', manifests=manifests)


@app.route('/dispatch', methods=['GET', 'POST'])
def dispatch():
    if request.method == 'POST':
        dispatch_entry = DispatchRelease(
            date=request.form.get('date'),
            flight_id=request.form.get('flight_id'),
            aircraft=request.form.get('aircraft'),
            departure=request.form.get('departure'),
            destination=request.form.get('destination'),
            offblocks=request.form.get('offblocks'),
            arrival=request.form.get('arrival'),
            route=request.form.get('route')
        )
        db.session.add(dispatch_entry)
        db.session.commit()
        return redirect(url_for('dispatch_history'))
    defaults = {
        'date': request.args.get('date', ''),
        'flight_id': request.args.get('flight_id', ''),
        'aircraft': request.args.get('aircraft', ''),
        'departure': request.args.get('departure', ''),
        'destination': request.args.get('destination', ''),
        'offblocks': request.args.get('offblocks', ''),
        'arrival': request.args.get('arrival', ''),
        'route': request.args.get('route', '')
    }
    return render_template('dispatch_form.html', defaults=defaults)


@app.route('/dispatch/history')
def dispatch_history():
    releases = DispatchRelease.query.order_by(DispatchRelease.id.desc()).all()
    return render_template('dispatch_history.html', releases=releases)


@app.route('/crew', methods=['GET', 'POST'])
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
            remarks=request.form.get('remarks'),
            dispatch_release_id=request.form.get('dispatch_release_id') or None,
            cargo_manifest_id=request.form.get('cargo_manifest_id') or None
        )
        db.session.add(log)
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
def crew_history():
    logs = CrewLog.query.order_by(CrewLog.id.desc()).all()
    return render_template('crew_history.html', logs=logs)


@app.route('/notams', methods=['GET', 'POST'])
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
def notams_history():
    notams = CompanyNotam.query.order_by(CompanyNotam.id.desc()).all()
    return render_template('notams_history.html', notams=notams)


@app.route('/fleet', methods=['GET', 'POST'])
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
        db.session.add(entry)
        db.session.commit()
        return redirect(url_for('fleet_history'))
    return render_template('fleet_form.html')


@app.route('/fleet/history')
def fleet_history():
    entries = FleetEntry.query.order_by(FleetEntry.id.desc()).all()
    return render_template('fleet_history.html', entries=entries)

# Delete routes (POST only)
@app.route('/cargo/delete/<int:id>', methods=['POST'])
def delete_cargo(id):
    obj = CargoManifest.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('cargo_history'))

@app.route('/dispatch/delete/<int:id>', methods=['POST'])
def delete_dispatch(id):
    obj = DispatchRelease.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('dispatch_history'))

@app.route('/crew/delete/<int:id>', methods=['POST'])
def delete_crew(id):
    obj = CrewLog.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('crew_history'))

@app.route('/notams/delete/<int:id>', methods=['POST'])
def delete_notam(id):
    obj = CompanyNotam.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('notams_history'))

@app.route('/fleet/delete/<int:id>', methods=['POST'])
def delete_fleet(id):
    obj = FleetEntry.query.get(id)
    if obj:
        db.session.delete(obj)
        db.session.commit()
    return redirect(url_for('fleet_history'))


if __name__ == '__main__':
    app.run(debug=True)
