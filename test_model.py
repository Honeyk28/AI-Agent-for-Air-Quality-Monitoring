import pickle
import pandas as pd
import numpy as np

# Load model
with open('rf_aqi_model.pkl', 'rb') as f:
    model = pickle.load(f)

# The values provided by the user
data = {
    'pm2_5': 30.0,
    'pm10': 15.0,
    'no2': 12.4,
    'so2': 0.6,
    'co': 1.9,
    'o3': 29.7
}

df = pd.DataFrame([data])

print("==================================================")
print("1. EXACT VALUES PASSED TO MODEL")
print("==================================================")
for k, v in data.items():
    print(f"{k}: {v}")

print("\n==================================================")
print("3. MODEL OUTPUT")
print("==================================================")
pred = model.predict(df)[0]
print(f"Final Prediction (Random Forest AQI): {pred:.2f}")

tree_preds = np.array([tree.predict(df)[0] for tree in model.estimators_])
print(f"Tree Predictions -> Mean: {np.mean(tree_preds):.2f}, Median: {np.median(tree_preds):.2f}, Min: {np.min(tree_preds):.2f}, Max: {np.max(tree_preds):.2f}")

print("\n==================================================")
print("4. FEATURE IMPORTANCES")
print("==================================================")
feat_names = ['pm2_5', 'pm10', 'no2', 'so2', 'co', 'o3']
importances = model.feature_importances_
for name, imp in sorted(zip(feat_names, importances), key=lambda x: -x[1]):
    print(f"{name:6s}: {imp:.4f}")

