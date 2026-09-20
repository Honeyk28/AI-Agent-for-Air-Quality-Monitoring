from flask import Flask, render_template, request, jsonify
import requests
import pandas as pd
import numpy as np
import pickle
import os
import warnings
import threading
import webbrowser

warnings.filterwarnings('ignore')

app = Flask(__name__)

# ---------------------------------------------------------------
# TRAINING DATA RANGES (μg/m³) — used for out-of-range warnings
# ---------------------------------------------------------------
TRAIN_RANGES = {
    'pm2_5': (5,    350),
    'pm10':  (10,   500),
    'no2':   (5,    200),
    'so2':   (2,    100),
    'co':    (100,  10000),
    'o3':    (10,   180),
}

# --- LOAD MODEL ---
def load_model():
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rf_aqi_model.pkl')
    try:
        with open(model_path, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        print("Model file not found. Please run model_trainer.py first.")
        return None

model = load_model()

# --- AQI HELPERS ---
def get_aqi_info(aqi):
    if aqi <= 50:
        return "Good",        "#00E400", "Minimal impact",                                          "None required. Enjoy the outdoors!"
    elif aqi <= 100:
        return "Satisfactory","#9ACD32", "Minor breathing discomfort to sensitive people",          "Unusually sensitive people should consider reducing prolonged outdoor exertion."
    elif aqi <= 200:
        return "Moderate",    "#F59E0B", "Breathing discomfort to people with lung/heart diseases", "People with respiratory or heart disease, elderly and children should limit prolonged exertion."
    elif aqi <= 300:
        return "Poor",        "#EF4444", "Breathing discomfort to most on prolonged exposure",      "Everyone should reduce prolonged or heavy exertion."
    elif aqi <= 400:
        return "Very Poor",   "#8B5CF6", "Respiratory illness on prolonged exposure",               "Everyone should avoid prolonged or heavy exertion."
    else:
        return "Severe",      "#7E0023", "Affects healthy people; seriously impacts those with existing diseases", "Everyone should avoid all physical activity outdoors."

def compute_sub_indices(p):
    """Normalised sub-indices (0-500 scale) — used for dominant pollutant detection."""
    return {
        'PM2.5': (p['pm2_5'] / 250.0)  * 500,
        'PM10':  (p['pm10']  / 430.0)  * 500,
        'NO₂':   (p['no2']   / 400.0)  * 500,
        'SO₂':   (p['so2']   / 1600.0) * 500,
        'CO':    (p['co']    / 34000.0) * 500,
        'O₃':    (p['o3']    / 748.0)  * 500,
    }

# --- API: OPEN-METEO ---
def fetch_open_meteo(city, lat=None, lon=None):
    if lat is None or lon is None:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(city)}&count=1&language=en&format=json"
        try:
            geo_resp = requests.get(geo_url, timeout=10)
        except requests.exceptions.RequestException as e:
            return None, f"Network error (geocoding): {e}"

        if geo_resp.status_code != 200 or not geo_resp.json().get('results'):
            return None, f"City '{city}' not found."

        loc = geo_resp.json()['results'][0]
        lat, lon = loc['latitude'], loc['longitude']
        display_name = f"{loc.get('name')}, {loc.get('admin1', loc.get('country'))}"
    else:
        display_name = city

    aq_url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        f"&current=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone"
        f"&hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone"
        f"&past_days=1"
    )
    try:
        aq_resp = requests.get(aq_url, timeout=10)
    except requests.exceptions.RequestException as e:
        return None, f"Network error (air quality): {e}"

    if aq_resp.status_code != 200:
        return None, f"Open-Meteo AQ API error: {aq_resp.status_code}"

    json_data = aq_resp.json()
    current = json_data.get('current', {})

    pollutants = {
        'pm2_5': current.get('pm2_5', 0) or 0,
        'pm10':  current.get('pm10', 0) or 0,
        'no2':   current.get('nitrogen_dioxide', 0) or 0,
        'so2':   current.get('sulphur_dioxide', 0) or 0,
        'co':    current.get('carbon_monoxide', 0) or 0,
        'o3':    current.get('ozone', 0) or 0,
    }
    
    # Process history for trend graph (last 24 hours up to current time)
    history = []
    hourly = json_data.get('hourly', {})
    if 'time' in hourly:
        times = hourly['time']
        for i in range(len(times)):
            val = {k: hourly[k][i] for k in ['pm10','pm2_5','carbon_monoxide','nitrogen_dioxide','sulphur_dioxide','ozone'] if hourly.get(k)}
            if any(v is not None for v in val.values()):
                # Predict historical AQI
                p_hist = {'pm2_5': val.get('pm2_5',0) or 0, 'pm10': val.get('pm10',0) or 0, 'no2': val.get('nitrogen_dioxide',0) or 0, 'so2': val.get('sulphur_dioxide',0) or 0, 'co': val.get('carbon_monoxide',0) or 0, 'o3': val.get('ozone',0) or 0}
                feat = pd.DataFrame([p_hist])
                pred_aqi = max(0, int(round(model.predict(feat)[0])))
                history.append({'time': times[i], 'aqi': pred_aqi})
    
    # Keep only last 24 hours
    history = history[-24:] if len(history) > 24 else history

    return {'city': display_name, 'pollutants': pollutants, 'time': current.get('time'), 'history': history, 'lat': lat, 'lon': lon}, None


# --- API: WAQI ---
def fetch_waqi(lat, lon, city, api_key):
    url = f"https://api.waqi.info/feed/geo:{lat};{lon}/?token={api_key}"
    try:
        resp = requests.get(url, timeout=15)
    except requests.exceptions.RequestException:
        return None, "Network error fetching WAQI data. Try Open-Meteo."

    if resp.status_code != 200:
        return None, "WAQI request failed. Try Open-Meteo."

    json_data = resp.json()
    if json_data.get('status') != 'ok':
        err_data = json_data.get('data', 'Unknown error')
        if err_data == "Invalid key":
            return None, "WAQI API Token is invalid or expired."
        return None, f"WAQI Error: {err_data}. Try Open-Meteo."

    d = json_data.get('data', {})
    if not d:
        return None, "No data available from WAQI for this location. Try Open-Meteo."

    station_name = d.get('city', {}).get('name', city)

    iaqi = d.get('iaqi', {})
    
    pollutants = {'pm2_5': 0, 'pm10': 0, 'no2': 0, 'so2': 0, 'co': 0, 'o3': 0}
    PARAM_MAP = {
        'pm25': 'pm2_5',
        'pm10': 'pm10',
        'no2': 'no2',
        'so2': 'so2',
        'co': 'co',
        'o3': 'o3'
    }

    found_any = False
    for waqi_key, our_key in PARAM_MAP.items():
        if waqi_key in iaqi:
            val = iaqi[waqi_key].get('v', 0)
            pollutants[our_key] = max(0, val)
            if val > 0:
                found_any = True

    if not found_any:
        return None, "WAQI does not have sufficient pollutant data for this location. Try Open-Meteo."

    last_time = d.get('time', {}).get('iso', 'N/A')
    
    # Return original lat/lon as requested to maintain globe location consistency
    return {'city': station_name, 'pollutants': pollutants, 'time': last_time, 'history': [], 'lat': lat, 'lon': lon}, None

# ===============================================================
# ROUTES
# ===============================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/geocode', methods=['GET'])
def geocode_api():
    query = request.args.get('query', '')
    if not query:
        return jsonify({"results": []})
    
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(query)}&count=5&language=en&format=json"
    try:
        geo_resp = requests.get(geo_url, timeout=10)
        if geo_resp.status_code == 200:
            results = geo_resp.json().get('results', [])
            return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
    return jsonify({"results": []})

@app.route('/api/predict', methods=['POST'])
def predict_api():
    if not model:
        return jsonify({"error": "Model object not found! Please verify model_trainer.py was executed."}), 500

    data = request.json
    city = data.get('city', 'Nagpur')
    lat = data.get('lat')
    lon = data.get('lon')
    api_source = data.get('api_source', 'Open-Meteo')
    api_key = data.get('api_key', '')

    fetched_data, err = None, None
    ml_data = None
    if api_source == "Open-Meteo":
        fetched_data, err = fetch_open_meteo(city, lat, lon)
        ml_data = fetched_data
    else:
        if not api_key:
            err = "Please provide your WAQI API Token."
        else:
            fetched_data, err = fetch_waqi(lat, lon, city, api_key)
            if not err:
                ml_data, ml_err = fetch_open_meteo(city, lat, lon)
                if ml_err:
                    err = f"WAQI fetch succeeded, but ML model needs Open-Meteo data which failed: {ml_err}"

    if err:
        return jsonify({"error": err}), 400

    p = fetched_data['pollutants']
    for k in p:
        if p[k] is None or p[k] < 0:
            p[k] = 0

    ml_p = ml_data['pollutants']
    for k in ml_p:
        if ml_p[k] is None or ml_p[k] < 0:
            ml_p[k] = 0

    warnings_list = []
    for k, (lo, hi) in TRAIN_RANGES.items():
        v = ml_p[k]
        if v > hi * 1.5:
            warnings_list.append(f"{k.upper()} value ({v:.1f} μg/m³) is far above training range. Prediction may be less reliable.")

    features = pd.DataFrame([{k: ml_p[k] for k in ['pm2_5','pm10','no2','so2','co','o3']}])

    predicted_aqi = model.predict(features)[0]
    predicted_aqi = max(0, int(round(predicted_aqi)))

    # CI
    tree_preds = np.array([tree.predict(features)[0] for tree in model.estimators_])
    ci_low  = max(0, int(np.percentile(tree_preds, 10)))
    ci_high = int(np.percentile(tree_preds, 90))

    cat, color, impact, prec = get_aqi_info(predicted_aqi)

    # Sub index dominance based on ML inputs
    sub_idx = compute_sub_indices(ml_p)
    dominant_pol  = max(sub_idx, key=sub_idx.get)
    dominant_val  = sub_idx[dominant_pol]

    # Feature Importance
    feat_labels = ['PM2.5','PM10','NO₂','SO₂','CO','O₃']
    importances = model.feature_importances_
    features_imp_list = [{'feature': label, 'importance': round(float(imp), 3)} for label, imp in zip(feat_labels, importances)]
    features_imp_list.sort(key=lambda x: x['importance'], reverse=True)

    # Agent Decision Logic
    risk_level = "Low"
    decision = "Normal operations."
    reason = "AQI is within safe limits."
    recommendation = "Normal outdoor activity."
    alert_triggered = False
    alert_severity = "NONE"
    alert_msg = "No alert required."

    if predicted_aqi <= 50:
        alert_triggered = False
        alert_severity = "LOW"
        alert_msg = "Air quality is considered satisfactory, and air pollution poses little or no risk."
    elif predicted_aqi <= 100:
        risk_level = "Moderate"
        decision = "Monitor sensitive groups."
        reason = "AQI indicates moderate pollution."
        recommendation = "Unusually sensitive people should consider reducing prolonged outdoor exertion."
        alert_triggered = False
        alert_severity = "MODERATE"
        alert_msg = "Acceptable air quality; moderate health concern for a very small number of people."
    elif predicted_aqi <= 200:
        risk_level = "Elevated"
        decision = "Issue health precaution."
        reason = "Pollution levels may affect sensitive individuals."
        recommendation = "People with respiratory or heart disease, elderly and children should limit prolonged exertion."
        alert_triggered = True
        alert_severity = "HIGH"
        alert_msg = "Health precaution alert. Limit outdoor exertion for sensitive groups."
    elif predicted_aqi <= 300:
        risk_level = "High"
        decision = "Issue strong alert."
        reason = "AQI has exceeded safety threshold for general public."
        recommendation = "Reduce prolonged outdoor exposure."
        alert_triggered = True
        alert_severity = "HIGH"
        alert_msg = "Strong alert. Reduce prolonged outdoor exposure."
    elif predicted_aqi <= 400:
        risk_level = "Very High"
        decision = "Issue severe alert."
        reason = "Very poor air quality detected."
        recommendation = "Avoid prolonged outdoor activity."
        alert_triggered = True
        alert_severity = "VERY HIGH"
        alert_msg = "Severe alert. Avoid prolonged outdoor activity."
    else:
        risk_level = "Critical"
        decision = "Issue critical alert."
        reason = "Hazardous air quality detected."
        recommendation = "Avoid all outdoor exposure."
        alert_triggered = True
        alert_severity = "CRITICAL"
        alert_msg = "Critical alert. Avoid all physical activity outdoors."

    return jsonify({
        "city": fetched_data['city'],
        "time": fetched_data['time'],
        "aqi": predicted_aqi,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "category": cat,
        "color": color,
        "health_impact": impact,
        "precautions": prec,
        "dominant_pollutant": dominant_pol,
        "dominant_sub_index": dominant_val,
        "pollutants": p,
        "warnings": warnings_list,
        "feature_importances": features_imp_list,
        "history": fetched_data['history'],
        "lat": fetched_data.get('lat', lat),
        "lon": fetched_data.get('lon', lon),
        
        "agent": {
            "status": "completed",
            "steps": [
                {"name": "Location Identification", "status": "completed", "message": "Location and coordinates resolved."},
                {"name": "Data Retrieval", "status": "completed", "message": "Air quality parameters fetched."},
                {"name": "Pollutant Analysis", "status": "completed", "message": "Individual pollutants assessed."},
                {"name": "ML Prediction", "status": "completed", "message": "Random Forest AQI model executed."},
                {"name": "Risk Evaluation", "status": "completed", "message": "Dominant pollutant and health impact determined."},
                {"name": "Agent Decision", "status": "completed", "message": "Automated alert evaluated."}
            ]
        },
        "location": {
            "name": fetched_data['city'],
            "latitude": fetched_data.get('lat', lat),
            "longitude": fetched_data.get('lon', lon)
        },
        "air_quality": {
            "aqi": predicted_aqi,
            "category": cat,
            "dominant_pollutant": dominant_pol,
            "pollutants": p
        },
        "decision": {
            "risk_level": risk_level,
            "decision": decision,
            "reason": reason,
            "recommendation": recommendation
        },
        "alert": {
            "triggered": alert_triggered,
            "severity": alert_severity,
            "message": alert_msg
        }
    })

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5001")

if __name__ == '__main__':
    threading.Timer(1.25, open_browser).start()
    app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False)