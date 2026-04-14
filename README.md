# network-monitoring-telegraf

Cisco ACI, IOS, NX-OS 및 EVE-NG 홈 서버를 대상으로
TIG 스택(Telegraf + InfluxDB + Grafana)을 사용하여
네트워크 메트릭을 수집하고 시각화하는 포트폴리오 프로젝트입니다.

> 본 프로젝트는 [network-monitoring-zabbix](https://github.com/MinYongUm/network-monitoring-zabbix) 와
> 동일한 수집 대상을 다른 방식으로 구현하여 비교합니다.
> 비교 결과는 [docs/comparison-with-zabbix.md](docs/comparison-with-zabbix.md) 를 참고하십시오.

설치 및 실행 방법은 [INSTALL.md](INSTALL.md) 를 참고하십시오.


## 목차

- [스택 구성](#스택-구성)
- [프로젝트 구조](#프로젝트-구조)
- [수집 대상](#수집-대상)
- [Grafana 대시보드](#grafana-대시보드)
- [Slack 알림](#slack-알림)
- [관련 프로젝트](#관련-프로젝트)


## 스택 구성

```
Telegraf (수집) → InfluxDB (저장) → Grafana (시각화)

aci-collector (Python 컨테이너)
  └── ACI APIC REST API 호출 → InfluxDB HTTP API 직접 전송
```

| 컴포넌트 | 이미지 | 역할 |
|---|---|---|
| Telegraf | telegraf:1.29 | SNMP 플러그인으로 IOS/NX-OS 메트릭 수집 |
| InfluxDB | influxdb:2.7 | 시계열 메트릭 저장 |
| Grafana | grafana/grafana:10.4.2 | 대시보드 시각화 및 알림 |
| aci-collector | python:3.11-slim | ACI APIC REST API 수집 후 InfluxDB에 직접 전송 |
| slack-notifier | python:3.11-slim | Grafana Webhook 수신 후 Slack 채널로 알림 전달 |


## 프로젝트 구조

```
network-monitoring-telegraf/
├── docker-compose.yml
├── Dockerfile                      # Telegraf 커스텀 이미지 (MIB 설치 포함)
├── .env.example                    # 환경변수 템플릿 (실제 값 미포함)
├── .env                            # 실제 환경변수 (Git 추적 제외)
├── .gitignore
├── README.md
├── INSTALL.md                      # 설치 및 실행 가이드
├── telegraf/
│   ├── telegraf.conf               # 글로벌 설정 및 InfluxDB 출력 설정
│   ├── inputs.d/
│   │   ├── snmp_cisco_ios.conf     # Cisco IOS SNMPv2c/v3 수집
│   │   ├── snmp_nxos.conf          # Cisco NX-OS SNMPv2c/v3 수집
│   │   └── eve_ng.conf             # EVE-NG 홈 서버 Node Exporter 수집
│   └── mibs/                       # Cisco 커스텀 MIB 파일
│       ├── CISCO-MEMORY-POOL-MIB.my
│       ├── CISCO-PROCESS-MIB.my
│       ├── CISCO-SMI.my
│       └── CISCO-TC.my
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
│   └── slack_notify.py             # Grafana Webhook → Slack 전달 스크립트
└── docs/
    └── comparison-with-zabbix.md   # Zabbix 구현과의 비교 분석
```


## 수집 대상

| 대상 | 프로토콜 | 수집 항목 |
|---|---|---|
| Cisco ACI APIC | REST API (HTTPS) | Fault(Severity별), Health Score, Node 상태 |
| Cisco IOS | SNMPv2c / SNMPv3 (AuthPriv) | 인터페이스 트래픽(bps), 에러/드롭 카운터, 링크 상태 |
| Cisco NX-OS | SNMPv2c / SNMPv3 (AuthPriv) | 인터페이스 트래픽, 에러/드롭 카운터, CPU |
| EVE-NG 홈 서버 | Node Exporter (HTTP :9100) | CPU, 메모리, 디스크, 네트워크 I/O, 시스템 부하 |

### SNMPv3 설정 기준

| 항목 | 값 |
|---|---|
| 보안 모드 | AuthPriv |
| 인증 알고리즘 | SHA |
| 암호화 알고리즘 | AES (Telegraf `priv_protocol` 설정값) |

> Cisco NX-OS: `CISCO-MEMORY-POOL-MIB` 는 vNX-OS 이미지 미지원으로 수집 제외.
> 실 NX-OS 장비에서는 정상 수집 가능합니다.


## Grafana 대시보드

스택 기동 시 아래 대시보드가 자동으로 프로비저닝됩니다.

| 대시보드 | 파일 | 주요 패널 |
|---|---|---|
| ACI Fabric | aci_fabric.json | Fault(Severity별 집계), Fabric Health Score, Node 상태 목록 |
| SNMP Traffic | snmp_traffic.json | 인터페이스 bps, 에러/드롭 카운터, 링크 상태 목록 |
| Homelab | homelab.json | CPU/메모리/디스크 사용률, 네트워크 I/O, 시스템 부하 |


## Slack 알림

Grafana Alert 발생 시 `slack-notifier` 컨테이너가 지정된 Slack 채널로 알림을 전달합니다.

- 알림 조건: 인터페이스 에러율, Fabric Health Score 임계값 초과 등
- 동작 흐름: Grafana Alert → Webhook → slack-notifier → Slack Incoming Webhook


## 관련 프로젝트

- [network-monitoring-zabbix](https://github.com/MinYongUm/network-monitoring-zabbix) — 동일 수집 대상의 Zabbix 구현