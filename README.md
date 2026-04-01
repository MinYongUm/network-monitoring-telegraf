# network-monitoring-telegraf

Cisco ACI, IOS, NX-OS 및 EVE-NG 홈 서버를 대상으로 TIG 스택(Telegraf + InfluxDB + Grafana)을 사용하여 네트워크 메트릭을 수집하고 시각화하는 프로젝트입니다.

> 본 프로젝트는 [network-monitoring-zabbix](https://github.com/MinYongUm/network-monitoring-zabbix) 와 동일한 수집 대상을 다른 방식으로 구현하여 비교합니다.<br>
> 비교 결과는 [docs/comparison-with-zabbix.md](docs/comparison-with-zabbix.md) 를 참고하십시오.


## 목차

- [스택 구성](#스택-구성)
- [프로젝트 구조](#프로젝트-구조)
- [수집 대상](#수집-대상)
- [Grafana 대시보드](#grafana-대시보드)
- [관련 프로젝트](#관련-프로젝트)


## 스택 구성

```
Telegraf (수집) → InfluxDB (저장) → Grafana (시각화)
     ↑
aci-collector (Python 컨테이너)
     └── ACI APIC REST API 호출 → Telegraf exec 플러그인 경유
```

| 컴포넌트 | 이미지 | 역할 |
|---|---|---|
| Telegraf | telegraf:1.29 | SNMP 및 exec 플러그인으로 메트릭 수집 |
| InfluxDB | influxdb:2.7 | 시계열 메트릭 저장 |
| Grafana | grafana/grafana:10.4.2 | 대시보드 시각화 |
| aci-collector | python:3.11-slim | ACI APIC REST API 수집 스크립트 실행 환경 |


## 프로젝트 구조

```
network-monitoring-telegraf/
├── docker-compose.yml              # 스택 전체 구성 정의
├── .env.example                    # 환경변수 템플릿 (실제 값 미포함)
├── .env                            # 실제 환경변수 (Git 추적 제외)
├── .gitignore                      # Git 추적 제외 목록
├── README.md                       # 프로젝트 개요 (본 문서)
├── INSTALL.md                      # 설치 및 실행 가이드
├── telegraf/
│   ├── telegraf.conf               # 글로벌 설정 및 InfluxDB 출력 설정
│   └── inputs.d/
│       ├── aci_rest.conf           # ACI 수집 (exec 플러그인)
│       ├── snmp_cisco_ios.conf     # Cisco IOS SNMPv3 수집
│       ├── snmp_nxos.conf          # Cisco NX-OS SNMPv3 수집
│       └── eve_ng.conf             # EVE-NG 홈 서버 Node Exporter 수집
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── influxdb.yml        # InfluxDB 데이터소스 자동 프로비저닝
│   │   └── dashboards/
│   │       └── dashboard.yml       # 대시보드 자동 로드 설정
│   └── dashboards/
│       ├── aci_fabric.json         # ACI Fabric 대시보드
│       ├── snmp_traffic.json       # 인터페이스 트래픽 대시보드
│       └── homelab.json            # 홈 서버 시스템 대시보드
├── scripts/
│   ├── aci_collector.py            # ACI APIC REST API 수집 스크립트
│   └── requirements.txt            # Python 패키지 의존성
├── alerting/
│   └── slack_notify.py             # Slack 알림 스크립트
└── docs/
    └── comparison-with-zabbix.md   # Zabbix 구현과의 비교 분석
```


## 수집 대상

| 대상 | 프로토콜 | 수집 항목 |
|---|---|---|
| Cisco ACI APIC | REST API (HTTPS) | Fault(severity별), Health Score, Node 상태 |
| Cisco IOS | SNMPv3 (AuthPriv) | 인터페이스 트래픽(BPS/PPS), 에러 카운터, 링크 상태 |
| Cisco NX-OS | SNMPv3 (AuthPriv) | 인터페이스 트래픽, 에러 카운터, CPU/메모리 |
| EVE-NG 홈 서버 | Node Exporter (HTTP) | CPU, 메모리, 디스크, 네트워크 I/O |

### SNMPv3 설정 기준

- 인증 모드: AuthPriv
- 인증 알고리즘: SHA
- 암호화 알고리즘: AES128


## Grafana 대시보드

스택 기동 시 아래 대시보드가 자동으로 프로비저닝됩니다.

| 대시보드 | 파일 | 주요 패널 |
|---|---|---|
| ACI Fabric | aci_fabric.json | Fault(severity별 집계), Fabric Health Score, Node Up/Down |
| SNMP Traffic | snmp_traffic.json | 인터페이스 BPS/PPS, 에러율, 링크 상태 |
| Homelab | homelab.json | CPU, 메모리, 디스크 사용률, 네트워크 I/O |


## 관련 프로젝트

- [network-monitoring-zabbix](https://github.com/MinYongUm/network-monitoring-zabbix) — 동일 수집 대상의 Zabbix 구현