"""
ML-модель для предсказания исхода сигнала (win/loss).
Использует Random Forest и Gradient Boosting на исторических данных.
"""
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

import config

logger = logging.getLogger("ml")

MODEL_PATH = Path(config.DB_PATH).parent / "ml_model.pkl"
FEATURES_PATH = Path(config.DB_PATH).parent / "ml_features.pkl"


def _prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Извлекает признаки из DataFrame с индикаторами для ML-модели.
    """
    features = pd.DataFrame()

    required_cols = ["rsi", "macd_hist", "bb_width", "close", "ema_50", "ema_200",
                     "volume_ratio", "atr_pct", "stoch_rsi_k", "stoch_rsi_d",
                     "ema_9", "ema_21", "bb_upper", "bb_lower", "obv"]
    available = [c for c in required_cols if c in df.columns]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logger.warning(f"ML: отсутствуют колонки: {missing}")

    if "rsi" in df.columns:
        features["rsi"] = df["rsi"]
    if "macd_hist" in df.columns:
        features["macd_hist"] = df["macd_hist"]
    if "bb_width" in df.columns:
        features["bb_width"] = df["bb_width"]
    if all(c in df.columns for c in ["close", "ema_50"]):
        features["ema_50_dist"] = (df["close"] - df["ema_50"]) / df["close"] * 100
    if all(c in df.columns for c in ["close", "ema_200"]):
        features["ema_200_dist"] = (df["close"] - df["ema_200"]) / df["close"] * 100
    if "volume_ratio" in df.columns:
        features["volume_ratio"] = df["volume_ratio"]
    if "atr_pct" in df.columns:
        features["atr_pct"] = df["atr_pct"]
    if "stoch_rsi_k" in df.columns:
        features["stoch_rsi_k"] = df["stoch_rsi_k"]
    if "stoch_rsi_d" in df.columns:
        features["stoch_rsi_d"] = df["stoch_rsi_d"]

    if "rsi" in df.columns:
        features["rsi_overbought"] = (df["rsi"] > 70).astype(int)
        features["rsi_oversold"] = (df["rsi"] < 30).astype(int)
    if "macd_hist" in df.columns:
        features["macd_positive"] = (df["macd_hist"] > 0).astype(int)
    if all(c in df.columns for c in ["close", "bb_upper"]):
        features["bb_upper_dist"] = (df["close"] - df["bb_upper"]) / df["close"] * 100
    if all(c in df.columns for c in ["close", "bb_lower"]):
        features["bb_lower_dist"] = (df["close"] - df["bb_lower"]) / df["close"] * 100
    if all(c in df.columns for c in ["ema_9", "ema_21"]):
        features["ema_9_above_21"] = (df["ema_9"] > df["ema_21"]).astype(int)
    if all(c in df.columns for c in ["ema_50", "ema_200"]):
        features["ema_50_above_200"] = (df["ema_50"] > df["ema_200"]).astype(int)
    if "obv" in df.columns:
        features["obv_slope"] = df["obv"].pct_change(5) * 100
    if all(c in df.columns for c in ["stoch_rsi_k", "stoch_rsi_d"]):
        features["stoch_k_above_d"] = (df["stoch_rsi_k"] > df["stoch_rsi_d"]).astype(int)

    return features


def _create_labels(df: pd.DataFrame, forward_periods: int = 3) -> pd.Series:
    """
    Создаёт метки win/loss на основе будущего движения цены.
    forward_periods — количество свечей вперёд для проверки.
    """
    future_return = df["close"].shift(-forward_periods) / df["close"] - 1
    # win = 1 (цена пошла в правильную сторону), loss = 0
    # Пока без.direction — просто рост/падение
    labels = (future_return > 0).astype(int)
    return labels


def train_model(df_signals: pd.DataFrame, min_samples: int = 15) -> Optional[dict]:
    """
    Обучает ML-модель на исторических данных.
    df_signals: DataFrame с колонками индикаторов и outcome (win/loss/expired).
    Возвращает dict с моделью и метриками или None если данных недостаточно.
    """
    if len(df_signals) < min_samples:
        logger.warning(f"Недостаточно данных для обучения: {len(df_signals)} < {min_samples}")
        return None

    # Подготавливаем признаки
    features = _prepare_features(df_signals)

    # Целевая переменная
    outcome_map = {"win": 1, "loss": 0, "expired": 0}
    labels = df_signals["outcome"].map(outcome_map)

    # Убираем NaN
    mask = features.notna().all(axis=1) & labels.notna()
    features = features[mask]
    labels = labels[mask]

    if len(features) < min_samples:
        logger.warning(f"После очистки: {len(features)}样本不足")
        return None

    # Разделяем данные
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=42, stratify=labels
    )

    # Обучаем Random Forest
    rf_model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        random_state=42,
        n_jobs=-1
    )
    rf_model.fit(X_train, y_train)
    rf_pred = rf_model.predict(X_test)
    rf_accuracy = accuracy_score(y_test, rf_pred)

    # Обучаем Gradient Boosting
    gb_model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        random_state=42
    )
    gb_model.fit(X_train, y_train)
    gb_pred = gb_model.predict(X_test)
    gb_accuracy = accuracy_score(y_test, gb_pred)

    # Выбираем лучшую модель
    if gb_accuracy >= rf_accuracy:
        best_model = gb_model
        best_name = "GradientBoosting"
        best_accuracy = gb_accuracy
    else:
        best_model = rf_model
        best_name = "RandomForest"
        best_accuracy = rf_accuracy

    # Сохраняем модель
    model_data = {
        "model": best_model,
        "model_name": best_name,
        "accuracy": best_accuracy,
        "feature_names": list(features.columns),
        "rf_accuracy": rf_accuracy,
        "gb_accuracy": gb_accuracy,
    }

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    logger.info(f"ML модель обучена: {best_name} (accuracy={best_accuracy:.2%})")
    logger.info(f"  RandomForest accuracy: {rf_accuracy:.2%}")
    logger.info(f"  GradientBoosting accuracy: {gb_accuracy:.2%}")

    return model_data


def load_model() -> Optional[dict]:
    """Загружает сохранённую модель."""
    if not MODEL_PATH.exists():
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки ML модели: {e}")
        return None


def predict(df: pd.DataFrame, model_data: dict) -> Optional[float]:
    """
    Предсказывает вероятность win для текущих индикаторов.
    Возвращает вероятность от 0.0 до 1.0 или None при ошибке.
    """
    if model_data is None:
        return None

    try:
        features = _prepare_features(df)
        last_row = features.iloc[[-1]]  # последняя строка

        # Проверяем на NaN
        if last_row.isna().any(axis=1).iloc[0]:
            return None

        model = model_data["model"]
        proba = model.predict_proba(last_row)[0]

        # proba[0] = P(loss), proba[1] = P(win)
        return float(proba[1])
    except Exception as e:
        logger.error(f"Ошибка предсказания ML: {e}")
        return None


def get_feature_importance(model_data: dict) -> Optional[pd.DataFrame]:
    """Возвращает важность признаков для интерпретации."""
    if model_data is None:
        return None

    model = model_data["model"]
    importance = model.feature_importances_
    feature_names = model_data["feature_names"]

    df_importance = pd.DataFrame({
        "feature": feature_names,
        "importance": importance
    }).sort_values("importance", ascending=False)

    return df_importance
