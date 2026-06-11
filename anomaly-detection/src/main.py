import logging
import sys

from .config import METRICS_QUERIES
from .prometheus_client import fetch_metric_range
from .detector import detect_anomalies
from .alerting import send_alerts

# Cau hinh logging de ghi log chi tiet va  theo doi ket qua phat hien bat thuong
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Ham chinh de thuc hien toan bo quy trinh phat hien bat thuong, tu truy van metric, phan tich va gui canh bao, ghi log ket qua tung buoc
def main() -> None:
    logger.info("Starting anomaly detection pipeline...")

    all_anomalies = []
# Vong lap qua tung metric duoc cau hinh, truy van du lieu tu Prometheus, phan tich de phat hien bat thuong va gui canh bao neu co, ghi log ket qua tung buoc
    for metric_name, metric_config in METRICS_QUERIES.items():
        logger.info("Analyzing metric: %s - %s", metric_name, metric_config["description"])

      
        df = fetch_metric_range(query=metric_config["query"])
# Neu khong co du lieu de phan tich, ghi log va tiep tuc metric tiep theo
        if df is None:
            logger.warning("Skipping metric %s: no data available", metric_name)
            continue

# Phan tich de phat hien bat thuong, neu co ket qua thi them vao danh sach ket qua va ghi log  
        anomalies = detect_anomalies(df=df, metric_name=metric_name)
        all_anomalies.extend(anomalies)

# Neu co bat thuong duoc phat hien, gui canh bao va ghi log ket qua tong quan, neu khong co bat thuong nao thi ghi log va ket thuc quy trinh 
    if all_anomalies:
        logger.info("Total anomalies detected: %d", len(all_anomalies))
        send_alerts(all_anomalies)
    else:
        logger.info("No anomalies detected across all metrics")

    logger.info("Anomaly detection pipeline completed")


if __name__ == "__main__":
    main()
