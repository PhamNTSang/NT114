import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .config import CONTAMINATION_FACTOR, MIN_DATA_POINTS, STD_DEVIATION_MULTIPLIER

logger = logging.getLogger(__name__)

@dataclass
class AnomalyResult:
    metric_name: str
    labels: str
    is_anomaly: bool
    current_value: float
    mean_value: float
    std_value: float
    anomaly_score: float
    threshold_upper: float
    threshold_lower: float
    description: str

def detect_anomalies(
    df: pd.DataFrame,
    metric_name: str,
    contamination: float = CONTAMINATION_FACTOR,
) -> List[AnomalyResult]:
    results = []
    if df is None or df.empty:
        logger.warning("No data to analyze for metric: %s", metric_name)
        return results

    for label_group, group_df in df.groupby("labels"):
        result = _analyze_group(
            group_df=group_df,
            metric_name=metric_name,
            labels=str(label_group),
            contamination=contamination,
        ) 
        if result and result.is_anomaly:
            results.append(result)

    logger.info(
        "Found %d anomalies out of %d label groups for %s",
        len(results),
        df["labels"].nunique(),
        metric_name,
    )
    return results

def _analyze_group(
    group_df: pd.DataFrame,
    metric_name: str,
    labels: str,
    contamination: float,
) -> Optional[AnomalyResult]:
    
    if "timestamp" in group_df.columns and not group_df.empty:
        latest_timestamp = group_df["timestamp"].iloc[-1]
        
        if not isinstance(latest_timestamp, pd.Timestamp):
            latest_timestamp = pd.to_datetime(latest_timestamp)
            
        time_diff = (pd.Timestamp.now() - latest_timestamp).total_seconds()
        
        if time_diff > 300:
            logger.debug("Skipping anomaly for %s: Data is too old (%d seconds ago). Pod likely deleted.", labels, time_diff)
            return None

    values = group_df["value"].values

    if len(values) < MIN_DATA_POINTS:
        logger.debug("Not enough data points for %s (%s): %d", metric_name, labels, len(values))
        return None

    latest_value = values[-1]
    mean_val = float(np.mean(values))
    std_val = float(np.std(values))

    if "cpu" in metric_name.lower() or "memory" in metric_name.lower():
        if latest_value <= mean_val and latest_value < 0.8 * mean_val:
            logger.debug("Skipping %s: Current value %f is below mean %f (cooling down).", labels, latest_value, mean_val)
            return None

    try:
        X = values.reshape(-1, 1)

        model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100,
        )
        model.fit(X)

        latest_score = model.decision_function([[latest_value]])[0]
        latest_prediction = model.predict([[latest_value]])[0]

        threshold_upper = float(mean_val + STD_DEVIATION_MULTIPLIER * std_val)
        threshold_lower = float(mean_val - STD_DEVIATION_MULTIPLIER * std_val)

        is_ml_anomaly = latest_prediction == -1
        
        if "cpu" in metric_name.lower() or "memory" in metric_name.lower():
            is_stat_anomaly = (latest_value > threshold_upper)
        else:
            is_stat_anomaly = (latest_value > threshold_upper) or (latest_value < threshold_lower)

        min_change_required = max(abs(mean_val * 0.01), 1e-6)
        is_significant_change = abs(latest_value - mean_val) > min_change_required

    
        is_above_absolute_threshold = True
        if "cpu" in metric_name.lower() and latest_value < 0.05:
            is_above_absolute_threshold = False
            logger.debug("Skipping anomaly for %s: %f < 0.05 cores", labels, latest_value)
        elif "app_memory" in metric_name.lower() and latest_value < 52428800:
            is_above_absolute_threshold = False
            logger.debug("Skipping anomaly for %s: %f < 50MiB", labels, latest_value)
        elif metric_name == "node_memory" and latest_value < 40.0:
            is_above_absolute_threshold = False
            logger.debug("Skipping anomaly for %s: %f%% < 40%%", labels, latest_value)

        is_emergency_ceiling = False
        if "node_cpu" in metric_name.lower() and latest_value >= 85.0:
            is_emergency_ceiling = True
        elif "node_memory" in metric_name.lower() and latest_value >= 85.0:
            is_emergency_ceiling = True
        elif "app_cpu" in metric_name.lower() and latest_value >= 1.0: # Giới hạn > 1 core (Pod limit là 2)
            is_emergency_ceiling = True
        elif "app_memory" in metric_name.lower() and latest_value >= 524288000: # Giới hạn > 500MiB
            is_emergency_ceiling = True

       
        if is_emergency_ceiling:
          
            is_anomaly = True
            status_text = "CRITICAL OVERLOAD"
        else:
           
            is_anomaly = is_ml_anomaly and is_stat_anomaly and is_significant_change and is_above_absolute_threshold
            status_text = "ANOMALY DETECTED" if is_anomaly else "Normal"

        description = (
            f"{status_text}: "
            f"{metric_name} for {labels}. "
            f"Current: {latest_value:.4f}, "
            f"Mean: {mean_val:.4f}, Std: {std_val:.4f}, "
            f"Dynamic range: [{threshold_lower:.4f}, {threshold_upper:.4f}]"
        )

        return AnomalyResult(
            metric_name=metric_name,
            labels=labels,
            is_anomaly=is_anomaly,
            current_value=float(latest_value),
            mean_value=mean_val,
            std_value=std_val,
            anomaly_score=float(latest_score),
            threshold_upper=threshold_upper,
            threshold_lower=threshold_lower,
            description=description,
        )

    except Exception as e:
        logger.error("Error analyzing %s (%s): %s", metric_name, labels, e)
        return None