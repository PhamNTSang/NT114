import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import requests

from .config import PROMETHEUS_URL, LOOKBACK_HOURS, QUERY_STEP, PROMETHEUS_TIMEOUT

logger = logging.getLogger(__name__)

# Ham lay du lieu metric tu Prometheus API
def fetch_metric_range(query: str, hours: int = LOOKBACK_HOURS, step: str = QUERY_STEP) -> Optional[pd.DataFrame]:
    # Tinh toan thoi gian bat dau va ket thuc cho truy van
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    # Cau hinh tham so truy van cho Prometheus API
    params = {
        "query": query,
        "start": start_time.timestamp(),
        "end": end_time.timestamp(),
        "step": step,
    }
    
    # Thuc hien truy van va xu ly ket qua, tra ve DataFrame hoac None neu co loi va ghi log
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params=params,
            timeout=PROMETHEUS_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        if data["status"] != "success":
            logger.error("Prometheus query failed: %s", data.get("error", "Unknown error"))
            return None

        results = data["data"]["result"]
        if not results:
            logger.warning("No data returned for query: %s", query)
            return None

        all_records = []
        for result in results:
            labels = result["metric"]
            label_str = ", ".join(f'{k}="{v}"' for k, v in labels.items())

            for timestamp, value in result["values"]:
                all_records.append({
                    "timestamp": datetime.fromtimestamp(float(timestamp)),
                    "value": float(value),
                    "labels": label_str,
                })

        df = pd.DataFrame(all_records)
        
        # Đồng bộ hóa định dạng Datetime cho Pandas DataFrame
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            
        logger.info("Fetched %d data points for query", len(df))
        return df

    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch data from Prometheus: %s", e)
        return None

# Ham lay du lieu metric hien tai tu Prometheus API
def fetch_current_metric(query: str) -> Optional[List[Dict]]:
    # Thuc hien truy van va xu ly ket qua, tra ve danh sach ket qua hoac None neu co loi va ghi log
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=PROMETHEUS_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        if data["status"] != "success":
            logger.error("Prometheus instant query failed: %s", data.get("error", "Unknown error"))
            return None

        return data["data"]["result"]

    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch instant metric: %s", e)
        return None