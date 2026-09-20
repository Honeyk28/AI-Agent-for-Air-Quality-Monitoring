import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import pickle
import os

def generate_synthetic_data(num_samples=3000):
    np.random.seed(42)

    # Generate pollutants in realistic ambient μg/m³ ranges
    # (matching what Open-Meteo actually returns)
    pm2_5 = np.random.uniform(5, 350, num_samples)
    pm10  = np.random.uniform(10, 500, num_samples)
    no2   = np.random.uniform(5, 200, num_samples)
    so2   = np.random.uniform(2, 100, num_samples)
    # CO from Open-Meteo is in μg/m³, typical ambient: 100–10000 μg/m³
    co    = np.random.uniform(100, 10000, num_samples)
    o3    = np.random.uniform(10, 180, num_samples)

    df = pd.DataFrame({
        'pm2_5': pm2_5,
        'pm10':  pm10,
        'no2':   no2,
        'so2':   so2,
        'co':    co,
        'o3':    o3
    })

    # ---------------------------------------------------------------
    # Sub-index breakpoints (Indian CPCB AQI standard)
    # All concentrations in μg/m³
    # Formula: SI = (AQI_hi - AQI_lo) / (BP_hi - BP_lo) * (C - BP_lo) + AQI_lo
    # We use a simplified linear slope to each pollutant's max BP for AQI 500
    # ---------------------------------------------------------------
    si_pm25 = (df['pm2_5'] / 250.0) * 500   # BP_hi = 250 μg/m³ → AQI 500
    si_pm10 = (df['pm10']  / 430.0) * 500   # BP_hi = 430 μg/m³ → AQI 500
    si_no2  = (df['no2']   / 400.0) * 500   # BP_hi = 400 μg/m³ → AQI 500
    si_so2  = (df['so2']   / 1600.0) * 500  # BP_hi = 1600 μg/m³ → AQI 500
    # CO BP_hi = 34000 μg/m³ for AQI 500 (CPCB standard)
    si_co   = (df['co']    / 34000.0) * 500
    si_o3   = (df['o3']    / 748.0) * 500   # BP_hi = 748 μg/m³ → AQI 500

    # AQI = max of all sub-indices (standard method) + small noise
    # np.clip() used instead of .clip(lower=, upper=) for Python 3.9 compatibility
    raw_aqi = (
        np.max([si_pm25, si_pm10, si_no2, si_so2, si_co, si_o3], axis=0)
        + np.random.normal(0, 8, num_samples)
    )
    df['AQI'] = np.clip(raw_aqi, 0, 500)

    return df


if __name__ == "__main__":
    print("Generating synthetic air quality data (realistic μg/m³ ranges)...")
    data = generate_synthetic_data()

    print(f"AQI stats → min: {data['AQI'].min():.1f}  max: {data['AQI'].max():.1f}  mean: {data['AQI'].mean():.1f}")

    X = data[['pm2_5', 'pm10', 'no2', 'so2', 'co', 'o3']]
    y = data['AQI']

    # Proper 80/20 train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print(f"Training on {len(X_train)} samples, testing on {len(X_test)} samples...")

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    train_r2 = model.score(X_train, y_train)
    test_r2  = model.score(X_test, y_test)
    print(f"Train R²: {train_r2:.4f}  |  Test R²: {test_r2:.4f}")

    # Feature importances
    feat_names = ['pm2_5', 'pm10', 'no2', 'so2', 'co', 'o3']
    importances = model.feature_importances_
    print("\nFeature Importances:")
    for name, imp in sorted(zip(feat_names, importances), key=lambda x: -x[1]):
        print(f"  {name:6s}: {imp:.4f}")

    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rf_aqi_model.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump(model, f)

    print(f"\nModel saved to: {model_path}")
    print("DELETE the old rf_aqi_model.pkl and use this newly generated one!")