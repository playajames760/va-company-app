from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
import os

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
    flight_id = db.Column(db.String(20))
    aircraft = db.Column(db.String(50))
    departure = db.Column(db.String(10))
    arrival = db.Column(db.String(10))
    total_weight = db.Column(db.String(20))
    pieces = db.Column(db.String(10))
    notes = db.Column(db.Text)
    dispatch_release_id = db.Column(db.Integer, db.ForeignKey('dispatch_release.id'))


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
    payload_planned = db.Column(db.String(20))  # Planned payload weight (lbs)
    fuel_planned = db.Column(db.String(20))     # Planned fuel (gal or lbs)
    cargo_plan = db.Column(db.Text)             # Summary of intended cargo items
    alt_airports = db.Column(db.Text)           # Alternate airports list
    weather_brief = db.Column(db.Text)          # Weather summary / risks
    special_notes = db.Column(db.Text)          # Special instructions / hazards
    actual_cargo_weight = db.Column(db.String(20))  # Aggregated from linked manifests
    cargo_manifests = db.relationship('CargoManifest', backref='dispatch_release', lazy='dynamic')


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
        'actual_cargo_weight': 'TEXT'
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
    return render_template('index.html', manifests=manifests, releases=releases, logs=logs, notams=notams, fleet_entries=fleet_entries, counts=counts)


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
        'flight_id': request.args.get('flight_id', ''),
        'aircraft': request.args.get('aircraft', ''),
        'departure': request.args.get('departure', ''),
        'arrival': request.args.get('arrival', ''),
        'total_weight': request.args.get('total_weight', ''),
        'pieces': request.args.get('pieces', ''),
        'notes': request.args.get('notes', ''),
        'dispatch_release_id': request.args.get('dispatch_release_id', '')
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
            route=request.form.get('route'),
            payload_planned=request.form.get('payload_planned'),
            fuel_planned=request.form.get('fuel_planned'),
            cargo_plan=request.form.get('cargo_plan'),
            alt_airports=request.form.get('alt_airports'),
            weather_brief=request.form.get('weather_brief'),
            special_notes=request.form.get('special_notes')
        )
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
            defaults = {k: request.form.get(k,'') for k in ['date','flight_id','aircraft','departure','destination','offblocks','arrival','route','payload_planned','fuel_planned','cargo_plan','alt_airports','weather_brief','special_notes']}
            return render_template('dispatch_form.html', defaults=defaults)
        db.session.add(dispatch_entry)
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
        'aircraft': request.args.get('aircraft', ''),
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
    return render_template('dispatch_form.html', defaults=defaults, cargo_manifest_options=cargo_manifest_options)

@app.route('/dispatch/<int:id>')
def dispatch_detail(id):
    d = DispatchRelease.query.get_or_404(id)
    linked_manifests = d.cargo_manifests.order_by(CargoManifest.id.desc()).all()
    return render_template('dispatch_detail.html', d=d, linked_manifests=linked_manifests)

@app.route('/dispatch/<int:id>/edit', methods=['GET', 'POST'])
def dispatch_edit(id):
    d = DispatchRelease.query.get_or_404(id)
    if request.method == 'POST':
        fields = ['date','flight_id','aircraft','departure','destination','offblocks','arrival','route',
                  'payload_planned','fuel_planned','cargo_plan','alt_airports','weather_brief','special_notes']
        for f in fields:
            setattr(d, f, request.form.get(f))
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
            return render_template('dispatch_form.html', defaults=defaults, edit_id=d.id, linked_manifests=linked_manifests)
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
    cargo_manifest_options = CargoManifest.query.filter_by(dispatch_release_id=None).order_by(CargoManifest.id.desc()).limit(25).all()
    linked_manifests = d.cargo_manifests.order_by(CargoManifest.id.desc()).all()
    return render_template('dispatch_form.html', defaults=defaults, edit_id=d.id, cargo_manifest_options=cargo_manifest_options, linked_manifests=linked_manifests)

@app.route('/dispatch/<int:dispatch_id>/unlink_manifest/<int:manifest_id>', methods=['POST'])
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

# Detail routes & editing for cargo
@app.route('/cargo/<int:id>', methods=['GET','POST'])
def cargo_detail(id):
    m = CargoManifest.query.get_or_404(id)
    if request.method == 'POST':
        old_dispatch_id = m.dispatch_release_id
        m.date = request.form.get('date')
        m.flight_id = request.form.get('flight_id')
        m.aircraft = request.form.get('aircraft')
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
            return render_template('cargo_detail.html', m=m, dispatch_options=dispatch_options, editing=True)
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
    return render_template('cargo_detail.html', m=m, dispatch_options=dispatch_options, editing=False)

@app.route('/cargo/<int:id>/unlink_dispatch', methods=['POST'])
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
def crew_detail(id):
    c = CrewLog.query.get_or_404(id)
    return render_template('crew_detail.html', c=c)

@app.route('/notams/<int:id>')
def notam_detail(id):
    n = CompanyNotam.query.get_or_404(id)
    return render_template('notam_detail.html', n=n)

@app.route('/fleet/<int:id>')
def fleet_detail(id):
    f = FleetEntry.query.get_or_404(id)
    return render_template('fleet_detail.html', f=f)


if __name__ == '__main__':
    app.run(debug=True)
