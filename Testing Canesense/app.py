"""
CANESENSE NIR — Flask Backend
Industrial sugarcane quality prediction dashboard.
"""

import os
import json
import uuid
import threading
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    Response, stream_with_context
)
from werkzeug.utils import secure_filename

from predict import predict_batch, compute_summary
from payment import calculate_payment, batch_payment_report
from utils import (
    load_results, save_results, append_batch,
    compute_batch_summary, get_all_farmers,
    search_farmer, now_iso
)

# ── App setup ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

app = Flask(__name__)
app.config['UPLOAD_FOLDER']       = os.path.join(BASE_DIR, 'uploads')
app.config['MAX_CONTENT_LENGTH']  = 32 * 1024 * 1024   # 32 MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'models'),  exist_ok=True)

# ── In-memory session store  (session_id → filepath) ──────────────────────────
_sessions: dict = {}
_sessions_lock  = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/realtime')
def realtime():
    return render_template('realtime.html')


@app.route('/farmer')
def farmer():
    return render_template('farmer_dashboard.html')


@app.route('/payment')
def payment():
    return render_template('payment_dashboard.html')


# ─────────────────────────────────────────────────────────────────────────────
#  API — FILE UPLOAD
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'Only CSV files are accepted'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    session_id = str(uuid.uuid4())
    with _sessions_lock:
        _sessions[session_id] = filepath

    return jsonify({
        'success':    True,
        'session_id': session_id,
        'filename':   filename,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  API — SSE PREDICTION STREAM
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/predict')
def predict_stream():
    session_id  = request.args.get('session_id', '')
    farmer_id   = request.args.get('farmer_id',   f'farmer_{datetime.now().strftime("%Y%m%d%H%M%S")}')
    farmer_name = request.args.get('farmer_name', 'Unknown Farmer')

    with _sessions_lock:
        filepath = _sessions.get(session_id)

    if not filepath or not os.path.exists(filepath):
        def err_gen():
            yield 'data: ' + json.dumps({'error': 'Session not found or file missing'}) + '\n\n'
        return Response(stream_with_context(err_gen()), mimetype='text/event-stream')

    def generate():
        samples = []
        try:
            for result in predict_batch(filepath, delay=2.0):
                samples.append(result)
                payload = json.dumps({'type': 'prediction', 'data': result})
                yield f'data: {payload}\n\n'

        except Exception as exc:
            yield f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n'
            return

        # ── Persist batch to results.json ──────────────────────────────────
        if samples:
            summary = compute_batch_summary(samples)
            batch   = {
                'farmer_id':   farmer_id,
                'farmer_name': farmer_name,
                'timestamp':   now_iso(),
                'samples':     samples,
                **summary,
            }
            append_batch(batch)

            done_payload = json.dumps({
                'type':    'done',
                'summary': summary,
                'farmer':  {'farmer_id': farmer_id, 'farmer_name': farmer_name},
            })
            yield f'data: {done_payload}\n\n'

    response = Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
    )
    response.headers['Cache-Control']      = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Connection']         = 'keep-alive'
    return response


# ─────────────────────────────────────────────────────────────────────────────
#  API — DATA
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/data')
def get_data():
    return jsonify(load_results())


@app.route('/data/farmers')
def get_farmers():
    return jsonify(get_all_farmers())


@app.route('/farmer/search')
def farmer_search():
    query   = request.args.get('q', '').strip()
    results = search_farmer(query) if query else load_results()
    return jsonify(results)


@app.route('/model/info')
def model_info():
    metrics_path = os.path.join(BASE_DIR, 'models', 'metrics.json')
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            return jsonify(json.load(f))
    return jsonify({'error': 'Model not trained yet'}), 404


# ─────────────────────────────────────────────────────────────────────────────
#  API — PAYMENT
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/payment/calculate', methods=['POST'])
def calculate_payment_route():
    data = request.get_json(force=True)
    required = ['weight', 'base_price', 'pol_avg', 'pol_std',
                'adf_avg', 'adf_std', 'alpha']
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({'error': f'Missing fields: {missing}'}), 400

    result = calculate_payment(
        weight     = float(data['weight']),
        base_price = float(data['base_price']),
        pol_avg    = float(data['pol_avg']),
        pol_std    = float(data['pol_std']),
        adf_avg    = float(data['adf_avg']),
        adf_std    = float(data['adf_std']),
        alpha      = float(data['alpha']),
    )
    return jsonify(result)


@app.route('/payment/batch', methods=['POST'])
def batch_payment():
    data    = request.get_json(force=True)
    farmers = data.get('farmers', [])
    params  = data.get('params',  {})
    if not farmers:
        farmers = get_all_farmers()
    report  = batch_payment_report(farmers, params)
    return jsonify(report)


# ─────────────────────────────────────────────────────────────────────────────
#  API — SAVE (generic)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/save', methods=['POST'])
def save():
    data    = request.get_json(force=True)
    results = load_results()
    results.append(data)
    save_results(results)
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────────────────────
#  STARTUP — auto-train if model missing
# ─────────────────────────────────────────────────────────────────────────────

def ensure_model():
    model_path = os.path.join(BASE_DIR, 'models', 'plsr_model.pkl')
    csv_path   = os.path.join(BASE_DIR, 'nirscan_nano.csv')
    if not os.path.exists(model_path):
        print('\n[STARTUP] Model not found — training now...')
        if not os.path.exists(csv_path):
            print(f'[ERROR] Training CSV not found at: {csv_path}')
            return
        from model_training import train_plsr_model
        train_plsr_model(csv_path)
    else:
        print('[STARTUP] PLSR model loaded ✓')


if __name__ == '__main__':
    ensure_model()
    app.run(debug=True, port=5000, threaded=True)
