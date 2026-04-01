"""
network-monitoring-telegraf / scripts/aci_collector.py

목적:
    Cisco ACI APIC REST API 에서 메트릭을 수집하고
    InfluxDB HTTP API 로 직접 write 하는 스크립트

수집 항목:
    - faultInst        : Fault 목록 (severity 별 집계: critical/major/minor/warning)
    - fabricHealthTotal: Fabric 전체 Health Score
    - fabricNode       : ACI Node 상태 (APIC/Leaf/Spine)

실행 방식 (v0.2.0 변경):
    aci-collector 컨테이너가 이 스크립트를 루프로 직접 실행 (COLLECT_INTERVAL 주기)
    수집 결과를 InfluxDB HTTP API 로 직접 write
    Telegraf exec 플러그인 의존성 제거 (aci_rest.conf 삭제)

아키텍처 변경 이력:
    v0.1.x: Telegraf exec 플러그인 → stdout line protocol → Telegraf → InfluxDB
    v0.2.0: aci-collector 루프 → InfluxDB 직접 write (C안)

    C안 채택 근거:
        A안 (telegraf 에 python3 추가): 최소 권한 원칙 위반, 불필요한 패키지 증가
        B안 (Flask HTTP 서버): 불필요한 포트 노출, 구조 복잡
        C안 (InfluxDB 직접 write): 크리덴셜 격리, 공격 표면 최소화

환경변수 (docker-compose.yml 의 aci-collector 서비스에서 주입):
    APIC_URL          : ACI APIC URL (예: https://192.168.1.1)
    APIC_USERNAME     : Read-only 계정명
    APIC_PASSWORD     : 계정 비밀번호
    INFLUXDB_URL      : InfluxDB URL (예: http://influxdb:8086)
    INFLUXDB_TOKEN    : InfluxDB 인증 토큰
    INFLUXDB_ORG      : InfluxDB 조직명 (예: homelab)
    INFLUXDB_BUCKET   : InfluxDB 버킷명 (예: network-metrics)

line protocol 형식 (InfluxDB write 페이로드):
    aci_fault,severity=critical count=3i 1700000000000000000
    aci_fault,severity=major count=1i 1700000000000000000
    aci_health score=98i 1700000000000000000
    aci_node,node_id=101,role=leaf,pod_id=1 state=1i 1700000000000000000

코딩 규칙:
    - PEP 8 준수
    - 타입 힌트 사용
    - logging 모듈 사용 (print 금지)
    - 크리덴셜 하드코딩 금지 (os.environ 참조)
"""

import logging
import os
import sys
import time
from typing import Any

import requests
import urllib3
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

# =============================================================================
# 로깅 설정
#
# v0.2.0: stdout 은 더 이상 메트릭 출력에 사용하지 않으므로
#         로그를 stdout 으로 변경 (컨테이너 로그에서 확인 가능)
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("aci_collector")

# =============================================================================
# APIC 자체 서명 인증서 경고 억제
#
# APIC 는 기본적으로 자체 서명 인증서를 사용하므로
# verify=False 설정 시 urllib3 의 InsecureRequestWarning 이 반복 출력됨
# =============================================================================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# =============================================================================
# 상수 정의
# =============================================================================

# 수집 루프 주기 (초)
# v0.2.0: Telegraf exec interval 대신 이 스크립트가 직접 루프 관리
COLLECT_INTERVAL: int = 60

# APIC 인증 토큰 갱신 주기 (초)
# APIC 기본 토큰 만료 시간은 600초 (10분)
TOKEN_REFRESH_INTERVAL: int = 300

# APIC REST API 타임아웃 (초)
REQUEST_TIMEOUT: int = 30

# ACI Node 운영 상태 값 매핑
# APIC API 응답의 state 필드 값 → line protocol 정수 변환
NODE_STATE_MAP: dict[str, int] = {
    "in-service": 1,
    "out-of-service": 0,
    "unknown": -1,
}

# Fault severity 우선순위 목록
# 수집 대상 severity 정의
FAULT_SEVERITIES: list[str] = ["critical", "major", "minor", "warning", "info"]


class ApicClient:
    """
    ACI APIC REST API 클라이언트

    인증 토큰 발급 및 갱신, REST API 호출을 담당
    """

    def __init__(self, url: str, username: str, password: str) -> None:
        """
        Args:
            url      : APIC URL (예: https://192.168.1.1)
            username : Read-only 계정명
            password : 계정 비밀번호
        """
        self.url: str = url.rstrip("/")
        self.username: str = username
        self.password: str = password
        self.token: str = ""
        self.token_acquired_at: float = 0.0

        # requests 세션 재사용으로 TCP 연결 오버헤드 감소
        self.session: requests.Session = requests.Session()
        # APIC 자체 서명 인증서 검증 비활성화
        self.session.verify = False

    def _is_token_expired(self) -> bool:
        """
        토큰 만료 여부 확인

        Returns:
            bool: TOKEN_REFRESH_INTERVAL 경과 시 True
        """
        elapsed: float = time.time() - self.token_acquired_at
        return elapsed >= TOKEN_REFRESH_INTERVAL

    def authenticate(self) -> None:
        """
        APIC 인증 토큰 발급

        POST /api/aaaLogin.json 으로 토큰을 발급받아 세션 쿠키에 설정

        Raises:
            requests.RequestException: 인증 요청 실패 시
            KeyError: 응답 구조 파싱 실패 시
        """
        login_url: str = f"{self.url}/api/aaaLogin.json"
        payload: dict[str, Any] = {
            "aaaUser": {
                "attributes": {
                    "name": self.username,
                    "pwd": self.password,
                }
            }
        }

        logger.info("APIC 인증 토큰 발급 요청: %s", login_url)

        response: requests.Response = self.session.post(
            login_url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        # 응답에서 토큰 추출
        # 응답 구조: {"imdata": [{"aaaLogin": {"attributes": {"token": "..."}}}]}
        token: str = (
            response.json()["imdata"][0]["aaaLogin"]["attributes"]["token"]
        )
        self.token = token
        self.token_acquired_at = time.time()

        # 이후 요청에 토큰을 쿠키로 전송 (APIC REST API 표준 방식)
        self.session.cookies.set("APIC-Cookie", token)
        logger.info("APIC 인증 토큰 발급 완료")

    def ensure_authenticated(self) -> None:
        """
        토큰 유효성 확인 후 필요 시 재인증

        토큰이 없거나 만료된 경우 authenticate() 호출
        """
        if not self.token or self._is_token_expired():
            logger.info("토큰 갱신 필요, 재인증 수행")
            self.authenticate()

    def get(self, path: str, params: dict[str, str] | None = None) -> list[dict]:
        """
        APIC REST API GET 요청

        Args:
            path   : API 경로 (예: /api/class/faultInst.json)
            params : 쿼리 파라미터 (예: {"query-target-filter": "..."})

        Returns:
            list[dict]: imdata 배열 (각 오브젝트 딕셔너리 목록)

        Raises:
            requests.RequestException: API 요청 실패 시
        """
        self.ensure_authenticated()
        api_url: str = f"{self.url}{path}"

        logger.debug("API 요청: %s, params: %s", api_url, params)

        response: requests.Response = self.session.get(
            api_url,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data: list[dict] = response.json().get("imdata", [])
        logger.debug("API 응답 오브젝트 수: %d", len(data))
        return data


def collect_faults(client: ApicClient) -> list[str]:
    """
    ACI Fault 메트릭 수집

    severity 별로 Fault 개수를 집계하여 line protocol 로 반환

    Args:
        client: ApicClient 인스턴스

    Returns:
        list[str]: line protocol 라인 목록

    line protocol 형식:
        aci_fault,severity=<severity> count=<int>i <timestamp_ns>
    """
    logger.info("Fault 메트릭 수집 시작")

    # severity 별 카운터 초기화
    fault_counts: dict[str, int] = {sev: 0 for sev in FAULT_SEVERITIES}

    # APIC 에서 전체 Fault 목록 조회
    # rsp-subtree-include=count 옵션으로 개수만 가져오는 최적화도 가능하나
    # severity 별 집계를 위해 전체 조회 후 로컬에서 집계
    faults: list[dict] = client.get(
        "/api/class/faultInst.json",
        params={
            "query-target-filter": "ne(faultInst.severity,\"cleared\")",
            "rsp-prop-include": "config-only",
        },
    )

    for fault in faults:
        severity: str = fault.get("faultInst", {}).get("attributes", {}).get(
            "severity", "unknown"
        )
        if severity in fault_counts:
            fault_counts[severity] += 1

    # line protocol 생성
    timestamp_ns: int = int(time.time() * 1_000_000_000)
    lines: list[str] = []

    for severity, count in fault_counts.items():
        line: str = f"aci_fault,severity={severity} count={count}i {timestamp_ns}"
        lines.append(line)
        logger.debug("Fault 집계 — severity=%s, count=%d", severity, count)

    logger.info("Fault 메트릭 수집 완료 (총 %d 건)", sum(fault_counts.values()))
    return lines


def collect_fabric_health(client: ApicClient) -> list[str]:
    """
    ACI Fabric Health Score 수집

    Fabric 전체의 Health Score 를 수집하여 line protocol 로 반환

    Args:
        client: ApicClient 인스턴스

    Returns:
        list[str]: line protocol 라인 목록

    line protocol 형식:
        aci_health score=<int>i <timestamp_ns>
    """
    logger.info("Fabric Health Score 수집 시작")

    health_data: list[dict] = client.get("/api/class/fabricHealthTotal.json")

    lines: list[str] = []
    timestamp_ns: int = int(time.time() * 1_000_000_000)

    for item in health_data:
        attrs: dict = item.get("fabricHealthTotal", {}).get("attributes", {})
        # cur: 현재 Health Score (0~100)
        score_str: str = attrs.get("cur", "0")

        try:
            score: int = int(score_str)
        except ValueError:
            logger.warning("Health Score 파싱 실패: %s", score_str)
            continue

        line: str = f"aci_health score={score}i {timestamp_ns}"
        lines.append(line)
        logger.debug("Fabric Health Score: %d", score)

    logger.info("Fabric Health Score 수집 완료 (%d 건)", len(lines))
    return lines


def collect_nodes(client: ApicClient) -> list[str]:
    """
    ACI Node 상태 수집

    APIC, Leaf, Spine 노드의 운영 상태를 수집하여 line protocol 로 반환

    Args:
        client: ApicClient 인스턴스

    Returns:
        list[str]: line protocol 라인 목록

    line protocol 형식:
        aci_node,node_id=<id>,role=<role>,pod_id=<pod> state=<int>i <timestamp_ns>

    state 값:
        1  = in-service (정상)
        0  = out-of-service (비정상)
        -1 = unknown
    """
    logger.info("Node 상태 수집 시작")

    nodes: list[dict] = client.get("/api/class/fabricNode.json")

    lines: list[str] = []
    timestamp_ns: int = int(time.time() * 1_000_000_000)

    for node in nodes:
        attrs: dict = node.get("fabricNode", {}).get("attributes", {})

        node_id: str = attrs.get("id", "unknown")
        role: str = attrs.get("role", "unknown")    # apic / leaf / spine
        pod_id: str = attrs.get("podId", "1")
        state_str: str = attrs.get("state", "unknown")

        # state 문자열을 정수로 변환
        state: int = NODE_STATE_MAP.get(state_str, -1)

        # 태그에 특수문자가 포함되지 않도록 정제
        # line protocol 태그 값에 공백/쉼표/등호 포함 불가
        node_id = node_id.replace(" ", "_")
        role = role.replace(" ", "_")

        line: str = (
            f"aci_node,node_id={node_id},role={role},pod_id={pod_id} "
            f"state={state}i {timestamp_ns}"
        )
        lines.append(line)
        logger.debug(
            "Node 상태 — node_id=%s, role=%s, state=%s(%d)",
            node_id, role, state_str, state,
        )

    logger.info("Node 상태 수집 완료 (%d 건)", len(nodes))
    return lines


def write_to_influxdb(
    lines: list[str],
    influxdb_url: str,
    influxdb_token: str,
    influxdb_org: str,
    influxdb_bucket: str,
) -> None:
    """
    수집된 메트릭을 InfluxDB 에 write

    influxdb_client 라이브러리의 write_api 를 통해
    line protocol 문자열 목록을 InfluxDB HTTP API 로 전송

    Args:
        lines          : line protocol 라인 목록
        influxdb_url   : InfluxDB URL (예: http://influxdb:8086)
        influxdb_token : InfluxDB 인증 토큰
        influxdb_org   : InfluxDB 조직명
        influxdb_bucket: InfluxDB 버킷명

    Raises:
        Exception: InfluxDB write 실패 시
    """
    # InfluxDBClient 는 컨텍스트 매니저로 사용하여 연결 자원을 명시적으로 해제
    with InfluxDBClient(
        url=influxdb_url,
        token=influxdb_token,
        org=influxdb_org,
    ) as influx_client:
        # SYNCHRONOUS: write 완료를 동기적으로 확인 (에러 즉시 감지)
        write_api = influx_client.write_api(write_options=SYNCHRONOUS)
        write_api.write(
            bucket=influxdb_bucket,
            org=influxdb_org,
            record=lines,   # list[str] 직접 전달 가능 (line protocol 자동 인식)
        )

    logger.info(
        "InfluxDB write 완료 — bucket=%s, lines=%d", influxdb_bucket, len(lines)
    )


def load_env() -> tuple[str, str, str, str, str, str, str]:
    """
    필수 환경변수 로드 및 누락 검사

    Returns:
        tuple: (apic_url, apic_username, apic_password,
                influxdb_url, influxdb_token, influxdb_org, influxdb_bucket)

    Raises:
        SystemExit: 필수 환경변수 누락 시 exit code 1 로 종료
    """
    apic_url: str = os.environ.get("APIC_URL", "")
    apic_username: str = os.environ.get("APIC_USERNAME", "")
    apic_password: str = os.environ.get("APIC_PASSWORD", "")
    influxdb_url: str = os.environ.get("INFLUXDB_URL", "")
    influxdb_token: str = os.environ.get("INFLUXDB_TOKEN", "")
    influxdb_org: str = os.environ.get("INFLUXDB_ORG", "")
    influxdb_bucket: str = os.environ.get("INFLUXDB_BUCKET", "")

    missing: list[str] = []
    for name, value in [
        ("APIC_URL", apic_url),
        ("APIC_USERNAME", apic_username),
        ("APIC_PASSWORD", apic_password),
        ("INFLUXDB_URL", influxdb_url),
        ("INFLUXDB_TOKEN", influxdb_token),
        ("INFLUXDB_ORG", influxdb_org),
        ("INFLUXDB_BUCKET", influxdb_bucket),
    ]:
        if not value:
            missing.append(name)

    if missing:
        logger.error("필수 환경변수 누락: %s", ", ".join(missing))
        sys.exit(1)

    return (
        apic_url,
        apic_username,
        apic_password,
        influxdb_url,
        influxdb_token,
        influxdb_org,
        influxdb_bucket,
    )


def main() -> None:
    """
    메인 실행 함수

    환경변수에서 접속 정보를 읽어 COLLECT_INTERVAL 주기로 메트릭을 수집하고
    InfluxDB 에 직접 write 하는 루프를 실행

    v0.2.0 변경:
        - 단발 실행 → while True 루프 (COLLECT_INTERVAL 주기)
        - stdout line protocol 출력 → InfluxDB 직접 write
        - 수집/write 실패 시 루프 중단 없이 다음 주기에 재시도

    Raises:
        SystemExit: 환경변수 누락 시 exit code 1 로 종료
    """
    (
        apic_url,
        apic_username,
        apic_password,
        influxdb_url,
        influxdb_token,
        influxdb_org,
        influxdb_bucket,
    ) = load_env()

    apic_client: ApicClient = ApicClient(apic_url, apic_username, apic_password)

    logger.info(
        "aci-collector 시작 — APIC=%s, InfluxDB=%s, org=%s, bucket=%s, interval=%ds",
        apic_url,
        influxdb_url,
        influxdb_org,
        influxdb_bucket,
        COLLECT_INTERVAL,
    )

    # -------------------------------------------------------------------------
    # 수집 루프
    #
    # 수집 또는 write 실패 시 에러 로그 후 다음 주기에 재시도
    # 환경변수 누락 등 복구 불가능한 오류는 load_env() 에서 이미 종료
    # -------------------------------------------------------------------------
    while True:
        loop_start: float = time.time()

        try:
            all_lines: list[str] = []
            all_lines.extend(collect_faults(apic_client))
            all_lines.extend(collect_fabric_health(apic_client))
            all_lines.extend(collect_nodes(apic_client))

            write_to_influxdb(
                all_lines,
                influxdb_url,
                influxdb_token,
                influxdb_org,
                influxdb_bucket,
            )

            logger.info("수집 주기 완료 (총 %d 라인)", len(all_lines))

        except requests.RequestException as e:
            logger.error("APIC API 요청 실패: %s", e)

        except (KeyError, IndexError, ValueError) as e:
            logger.error("응답 데이터 파싱 실패: %s", e)

        except Exception as e:  # noqa: BLE001 — InfluxDB write 실패 등 예상치 못한 오류
            logger.error("수집 주기 처리 중 예외 발생: %s", e)

        # 루프 처리 시간을 고려하여 잔여 sleep 시간 계산
        elapsed: float = time.time() - loop_start
        sleep_time: float = max(0.0, COLLECT_INTERVAL - elapsed)
        logger.debug("다음 수집까지 %.1f 초 대기", sleep_time)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()