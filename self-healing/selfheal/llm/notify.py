import logging

import requests

from ..config import SETTINGS

log = logging.getLogger("notify")


def post_slack(text: str, webhook: str = SETTINGS.slack_webhook) -> None:
    if not webhook:
        log.info("[slack] %s", text)
        return
    try:
        requests.post(webhook, json={"text": text}, timeout=10)
    except requests.RequestException as exc:
        log.warning("Slack error: %s", exc)


def incident_message(dep: str, rca, raw: dict) -> str:
    return (f":rotating_light: *Sự cố tại `{dep}`* — nguyên nhân: *{rca.category}* "
            f"(tin cậy {rca.confidence:.0%}, mức {rca.severity}, thành phần `{rca.affected_component}`)\n"
            f"> {rca.explanation}\n"
            f"P99 = {raw.get('lat_p99', 0):.0f} ms · error = {raw.get('err_rate', 0):.1%} · "
            f"anomaly = {raw.get('anomaly', 0):.2f}")


def recovery_message(dep: str, metrics: dict, actions: list[str], explanation: str) -> str:
    status = ":white_check_mark: Đã phục hồi" if metrics["recovered"] else ":warning: Chưa phục hồi"
    return (f"{status} `{dep}` sau {metrics['mttr_s']:.0f}s · hành động: {', '.join(actions) or 'không'} · "
            f"SLA {metrics['scr']:.0%}\n> {explanation}")
