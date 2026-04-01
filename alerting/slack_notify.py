"""
network-monitoring-telegraf / alerting/slack_notify.py

목적:
    Grafana Alerting 의 Webhook 수신 후 Slack 채널로 알림을 전송하는 스크립트

동작 방식:
    Grafana Alert Rule 발동
        → Webhook Contact Point (http://localhost:5001/alert) 로 POST 요청
        → Flask 서버(이 스크립트)가 수신
        → Slack Incoming Webhook URL 로 포맷팅된 메시지 전송

Grafana Webhook 페이로드 구조 (Grafana 10.x 기준):
    {
        "receiver": "slack-webhook",
        "status": "firing" | "resolved",
        "alerts": [
            {
                "status": "firing" | "resolved",
                "labels": {"alertname": "...", "severity": "..."},
                "annotations": {"summary": "...", "description": "..."},
                "startsAt": "2024-01-01T00:00:00Z",
                "endsAt":   "0001-01-01T00:00:00Z",
                "generatorURL": "http://grafana:3000/..."
            }
        ],
        "groupLabels": {},
        "commonLabels": {},
        "commonAnnotations": {},
        "externalURL": "http://grafana:3000"
    }

실행 방법:
    # 의존성 설치
    pip install -r requirements.txt

    # 서버 실행 (개발)
    python slack_notify.py

    # 서버 실행 (운영 — Gunicorn 권장)
    gunicorn -w 2 -b 0.0.0.0:5001 slack_notify:app

환경변수:
    SLACK_WEBHOOK_URL : Slack Incoming Webhook URL
    NOTIFY_PORT       : Flask 서버 포트 (기본값: 5001)
    NOTIFY_HOST       : Flask 서버 바인딩 주소 (기본값: 0.0.0.0)

Slack Webhook URL 발급:
    1. https://api.slack.com/apps → Create New App
    2. Incoming Webhooks → Activate → Add New Webhook to Workspace
    3. 채널 선택 후 Webhook URL 복사 → .env 의 SLACK_WEBHOOK_URL 에 입력

코딩 규칙:
    - PEP 8 준수
    - 타입 힌트 사용
    - logging 모듈 사용 (print 금지)
    - 크리덴셜 하드코딩 금지 (os.environ 참조)
"""

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests
from flask import Flask, Response, jsonify, request

# =============================================================================
# 로깅 설정
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("slack_notify")

# =============================================================================
# Flask 앱 초기화
# =============================================================================
app: Flask = Flask(__name__)

# =============================================================================
# 상수 정의
# =============================================================================

# Slack 메시지 색상 매핑
# Grafana alert status 및 severity 에 따라 색상 구분
SEVERITY_COLOR_MAP: dict[str, str] = {
    "critical": "#FF0000",   # 빨강
    "major":    "#FF6600",   # 주황
    "minor":    "#FFCC00",   # 노랑
    "warning":  "#36A64F",   # 초록
    "info":     "#439FE0",   # 파랑
    "resolved": "#36A64F",   # 초록 (복구)
    "default":  "#808080",   # 회색 (알 수 없음)
}

# Grafana alert status 아이콘 매핑
STATUS_ICON_MAP: dict[str, str] = {
    "firing":   ":red_circle:",
    "resolved": ":large_green_circle:",
}

# HTTP 요청 타임아웃 (초)
REQUEST_TIMEOUT: int = 10


def get_slack_webhook_url() -> str:
    """
    환경변수에서 Slack Webhook URL 로드

    Returns:
        str: Slack Incoming Webhook URL

    Raises:
        SystemExit: 환경변수 미설정 시 exit code 1 로 종료
    """
    url: str = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        logger.error("SLACK_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    return url


def format_timestamp(iso_str: str) -> str:
    """
    ISO 8601 타임스탬프를 사람이 읽기 쉬운 형식으로 변환

    Args:
        iso_str: ISO 8601 형식 문자열 (예: 2024-01-01T00:00:00Z)

    Returns:
        str: 포맷팅된 시간 문자열 (예: 2024-01-01 09:00:00 KST)
             파싱 실패 시 원본 문자열 반환
    """
    try:
        # Z 를 +00:00 으로 치환하여 파싱
        dt: datetime = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        # UTC → KST (+9) 변환
        kst_offset = timezone.utc
        dt_kst = dt.astimezone(kst_offset)
        return dt_kst.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, AttributeError):
        return iso_str


def build_slack_attachment(alert: dict[str, Any]) -> dict[str, Any]:
    """
    단일 Alert 딕셔너리를 Slack attachment 포맷으로 변환

    Slack attachment 구조:
        https://api.slack.com/reference/messaging/attachments

    Args:
        alert: Grafana Webhook 페이로드의 alerts 배열 내 단일 항목

    Returns:
        dict: Slack attachment 딕셔너리
    """
    status: str = alert.get("status", "unknown")
    labels: dict[str, str] = alert.get("labels", {})
    annotations: dict[str, str] = alert.get("annotations", {})

    alert_name: str = labels.get("alertname", "Unknown Alert")
    severity: str = labels.get("severity", "default")
    summary: str = annotations.get("summary", "요약 없음")
    description: str = annotations.get("description", "")
    starts_at: str = format_timestamp(alert.get("startsAt", ""))
    generator_url: str = alert.get("generatorURL", "")

    # 상태에 따른 색상 결정
    # resolved 상태는 severity 무관하게 녹색 사용
    if status == "resolved":
        color: str = SEVERITY_COLOR_MAP["resolved"]
    else:
        color = SEVERITY_COLOR_MAP.get(severity, SEVERITY_COLOR_MAP["default"])

    # 상태 아이콘
    icon: str = STATUS_ICON_MAP.get(status, ":white_circle:")

    # Slack attachment 구성
    attachment: dict[str, Any] = {
        "color": color,
        "title": f"{icon} [{status.upper()}] {alert_name}",
        "title_link": generator_url,
        "fields": [
            {
                "title": "Severity",
                "value": severity.upper(),
                "short": True,
            },
            {
                "title": "Status",
                "value": status.upper(),
                "short": True,
            },
            {
                "title": "Summary",
                "value": summary,
                "short": False,
            },
        ],
        "footer": "network-monitoring-telegraf | Grafana Alert",
        "ts": int(datetime.now().timestamp()),
    }

    # description 이 있는 경우에만 추가 (빈 값 표시 방지)
    if description:
        attachment["fields"].append(
            {
                "title": "Description",
                "value": description,
                "short": False,
            }
        )

    # 발생 시각 추가
    if starts_at:
        attachment["fields"].append(
            {
                "title": "발생 시각",
                "value": starts_at,
                "short": True,
            }
        )

    # labels 에 추가 정보가 있는 경우 표시
    # alertname / severity 외 나머지 label 을 추가 컨텍스트로 표시
    extra_labels: dict[str, str] = {
        k: v for k, v in labels.items()
        if k not in ("alertname", "severity")
    }
    if extra_labels:
        label_text: str = "\n".join(f"`{k}`: {v}" for k, v in extra_labels.items())
        attachment["fields"].append(
            {
                "title": "Labels",
                "value": label_text,
                "short": False,
            }
        )

    return attachment


def send_slack_message(
    webhook_url: str,
    payload: dict[str, Any],
) -> bool:
    """
    Slack Incoming Webhook 으로 메시지 전송

    Args:
        webhook_url : Slack Incoming Webhook URL
        payload     : 전송할 Slack 메시지 페이로드

    Returns:
        bool: 전송 성공 시 True, 실패 시 False
    """
    try:
        response: requests.Response = requests.post(
            webhook_url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info("Slack 메시지 전송 성공 (status: %d)", response.status_code)
        return True

    except requests.exceptions.Timeout:
        logger.error("Slack 메시지 전송 타임아웃 (%d초)", REQUEST_TIMEOUT)
        return False
    except requests.exceptions.ConnectionError as e:
        logger.error("Slack 연결 실패: %s", e)
        return False
    except requests.exceptions.HTTPError as e:
        logger.error("Slack HTTP 오류: %s", e)
        return False
    except requests.exceptions.RequestException as e:
        logger.error("Slack 요청 실패: %s", e)
        return False


# =============================================================================
# Flask 라우트
# =============================================================================

@app.route("/health", methods=["GET"])
def health_check() -> tuple[Response, int]:
    """
    헬스체크 엔드포인트

    docker-compose healthcheck 또는 외부 모니터링에서 사용
    GET /health → 200 OK

    Returns:
        tuple: JSON 응답, HTTP 상태 코드
    """
    return jsonify({"status": "ok"}), 200


@app.route("/alert", methods=["POST"])
def receive_alert() -> tuple[Response, int]:
    """
    Grafana Webhook Alert 수신 엔드포인트

    Grafana Contact Point (Webhook) 에서 POST 요청을 수신하고
    각 alert 를 Slack 메시지로 변환하여 전송

    Returns:
        tuple: JSON 응답, HTTP 상태 코드
            200: 정상 처리 (Slack 전송 성공 여부와 무관)
            400: 잘못된 요청 페이로드
            500: 내부 처리 오류
    """
    # 요청 페이로드 파싱
    data: dict[str, Any] | None = request.get_json(silent=True)
    if data is None:
        logger.warning("유효하지 않은 JSON 페이로드 수신")
        return jsonify({"error": "Invalid JSON payload"}), 400

    receiver: str = data.get("receiver", "unknown")
    status: str = data.get("status", "unknown")
    alerts: list[dict[str, Any]] = data.get("alerts", [])

    logger.info(
        "Grafana Alert 수신 — receiver: %s, status: %s, alerts: %d건",
        receiver, status, len(alerts),
    )

    if not alerts:
        logger.warning("alerts 배열이 비어 있습니다.")
        return jsonify({"message": "No alerts to process"}), 200

    # Slack Webhook URL 로드
    slack_webhook_url: str = get_slack_webhook_url()

    # 각 alert 를 Slack attachment 로 변환
    attachments: list[dict[str, Any]] = [
        build_slack_attachment(alert) for alert in alerts
    ]

    # Slack 메시지 페이로드 구성
    # 전체 상태를 헤더 텍스트로 표시
    status_icon: str = STATUS_ICON_MAP.get(status, ":white_circle:")
    slack_payload: dict[str, Any] = {
        "text": f"{status_icon} *Grafana Alert* — {len(alerts)}건 ({status.upper()})",
        "attachments": attachments,
    }

    # Slack 전송
    success: bool = send_slack_message(slack_webhook_url, slack_payload)

    if success:
        return jsonify({"message": "Alert forwarded to Slack"}), 200
    else:
        # Slack 전송 실패해도 Grafana 에는 200 반환
        # 200 이 아닌 경우 Grafana 가 재전송을 시도할 수 있어 루프 발생 가능
        logger.error("Slack 전송 실패 — Grafana 에는 200 반환하여 재시도 방지")
        return jsonify({"message": "Alert received but Slack delivery failed"}), 200


# =============================================================================
# 진입점
# =============================================================================

if __name__ == "__main__":
    # 환경변수에서 서버 설정 로드
    host: str = os.environ.get("NOTIFY_HOST", "0.0.0.0")
    port: int = int(os.environ.get("NOTIFY_PORT", "5001"))

    # Slack Webhook URL 사전 검증 (서버 기동 전 누락 여부 확인)
    get_slack_webhook_url()

    logger.info("Slack 알림 서버 시작 — %s:%d", host, port)
    logger.info("Grafana Webhook URL: http://%s:%d/alert", host, port)

    # 개발 환경 실행
    # 운영 환경에서는 Gunicorn 사용 권장:
    # gunicorn -w 2 -b 0.0.0.0:5001 slack_notify:app
    app.run(host=host, port=port, debug=False)