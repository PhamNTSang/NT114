import logging
from typing import List

import requests

from .config import SLACK_WEBHOOK_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from .detector import AnomalyResult

logger = logging.getLogger(__name__)

# Ham gui canh bao khi phat hien bat thuong, gui den Slack va Telegram , ghi log ket qua
def send_alerts(anomalies: List[AnomalyResult]) -> None:
    if not anomalies:
        logger.info("No anomalies to alert on")
        return

    logger.info("Sending alerts for %d anomalies", len(anomalies))

    if SLACK_WEBHOOK_URL:
        _send_slack_alert(anomalies)
    else:
        logger.warning("Slack webhook URL not configured, skipping Slack alerts")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        _send_telegram_alert(anomalies)
    else:
        logger.warning("Telegram not configured, skipping Telegram alerts")

# Ham gui canh bao den Slack, tao noi dung canh bao chi tiet va gui bang API, ghi log ket qua
def _send_slack_alert(anomalies: List[AnomalyResult]) -> None:
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"AI Anomaly Detection Alert ({len(anomalies)} anomalies)",
            },
        },
        {"type": "divider"},
    ]

    for anomaly in anomalies:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Metric:*\n{anomaly.metric_name}"},
                {"type": "mrkdwn", "text": f"*Labels:*\n{anomaly.labels}"},
                {"type": "mrkdwn", "text": f"*Current Value:*\n{anomaly.current_value:.4f}"},
                {"type": "mrkdwn", "text": f"*Anomaly Score:*\n{anomaly.anomaly_score:.4f}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Dynamic Range:*\n[{anomaly.threshold_lower:.4f}, {anomaly.threshold_upper:.4f}]",
                },
                {"type": "mrkdwn", "text": f"*Mean:*\n{anomaly.mean_value:.4f} +/- {anomaly.std_value:.4f}"},
            ],
        })
        blocks.append({"type": "divider"})

    _post_json(
        url=SLACK_WEBHOOK_URL,
        payload={"blocks": blocks},
        service_name="Slack",
    )

# Ham gui canh bao den Telegram, tao noi dung canh bao chi tiet va gui bang API, ghi log ket qua
def _send_telegram_alert(anomalies: List[AnomalyResult]) -> None:
    message_lines = [f"AI Anomaly Detection Alert ({len(anomalies)} anomalies)", ""]

    for anomaly in anomalies:
        message_lines.extend([
            f"Metric: {anomaly.metric_name}",
            f"Labels: {anomaly.labels}",
            f"Current: {anomaly.current_value:.4f}",
            f"Mean: {anomaly.mean_value:.4f} +/- {anomaly.std_value:.4f}",
            f"Score: {anomaly.anomaly_score:.4f}",
            f"Range: [{anomaly.threshold_lower:.4f}, {anomaly.threshold_upper:.4f}]",
            "",
        ])

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "\n".join(message_lines),
    }

    _post_json(
        url=url,
        payload=payload,
        service_name="Telegram",
    )

# Ham gui yeu cau POST den API, xu ly loi va ghi log ket qua
def _post_json(url: str, payload: dict, service_name: str) -> None:
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("%s alert sent successfully", service_name)
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to send %s alert: %s", service_name, exc)
