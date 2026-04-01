# Telegraf(TIG) vs Zabbix 비교 분석

> 작성 기준: network-monitoring-telegraf / network-monitoring-zabbix 두 구현 완료 후 작성
> 현재 상태: Telegraf 구현 완료 / Zabbix 구현 진행 예정
> 관련 레포: [network-monitoring-zabbix](https://github.com/MinYongUm/network-monitoring-zabbix)

---

## 목차

- [개요](#개요)
- [환경 및 전제 조건](#환경-및-전제-조건)
- [구현 복잡도](#구현-복잡도)
- [수집 방식](#수집-방식)
- [데이터 저장](#데이터-저장)
- [시각화](#시각화)
- [알림](#알림)
- [운영 관리](#운영-관리)
- [리소스 사용량](#리소스-사용량)
- [학습 곡선](#학습-곡선)
- [결론 및 선택 기준](#결론-및-선택-기준)

---

## 개요

동일한 수집 대상(Cisco ACI / IOS / NX-OS / EVE-NG 홈 서버)을 두 가지 방식으로 구현하고
실제 운용 경험을 바탕으로 비교한 문서입니다.

| 항목 | Telegraf (TIG 스택) | Zabbix |
|---|---|---|
| 구성 | Telegraf + InfluxDB + Grafana | Zabbix Server + PostgreSQL + Grafana |
| 수집 방식 | Pull (SNMP, exec, prometheus) | Push/Pull 혼용 |
| 데이터 저장 | InfluxDB (시계열 특화) | PostgreSQL (범용 RDBMS) |
| 알림 | Grafana Alert + Webhook | Zabbix 내장 알림 엔진 |
| 설정 관리 | conf 파일 (코드 기반) | XML 템플릿 + Web UI |
| 에이전트 | Telegraf / Node Exporter | Zabbix Agent2 |


## 환경 및 전제 조건

### 테스트 환경

```
호스트: 업무 노트북 VM (Docker Compose)
OS: Ubuntu 22.04 LTS
CPU: (작성 예정)
RAM: (작성 예정)
수집 대상:
  - Cisco ACI APIC
  - Cisco IOS 장비 n대
  - Cisco NX-OS 장비 n대
  - EVE-NG 홈 서버 (192.168.0.200)
```

### 수집 주기

| 대상 | Telegraf | Zabbix |
|---|---|---|
| ACI APIC | 60초 | (작성 예정) |
| Cisco IOS | 60초 | (작성 예정) |
| Cisco NX-OS | 60초 | (작성 예정) |
| EVE-NG 홈 서버 | 120초 | (작성 예정) |


## 구현 복잡도

### 초기 구성 소요 시간

| 단계 | Telegraf | Zabbix |
|---|---|---|
| 환경 구성 (docker compose up) | (작성 예정) | (작성 예정) |
| 수집 설정 | (작성 예정) | (작성 예정) |
| 대시보드 구성 | (작성 예정) | (작성 예정) |
| 알림 설정 | (작성 예정) | (작성 예정) |
| 전체 | (작성 예정) | (작성 예정) |

### 코드/설정 파일 수

| 항목 | Telegraf | Zabbix |
|---|---|---|
| 설정 파일 수 | (작성 예정) | (작성 예정) |
| 총 라인 수 | (작성 예정) | (작성 예정) |
| GUI 작업 필요 여부 | 불필요 | GUI 초기 설정 필요 |

### 비고

- Telegraf: `docker compose up` 이후 별도 GUI 작업 없이 수집 시작
- Zabbix: 컨테이너 기동 후 Web UI 에서 템플릿 임포트, 호스트 등록, SNMPv3 매크로 설정 필요


## 수집 방식

### ACI APIC

| 항목 | Telegraf | Zabbix |
|---|---|---|
| 수집 방식 | exec 플러그인 → Python 스크립트 | External Check → Python 스크립트 |
| 스크립트 위치 | scripts/aci_collector.py | /usr/lib/zabbix/externalscripts/ |
| 인증 방식 | REST API 토큰 (환경변수) | REST API 토큰 (환경변수) |
| 실제 동작 여부 | (작성 예정) | (작성 예정) |
| 특이사항 | (작성 예정) | (작성 예정) |

### Cisco IOS / NX-OS (SNMPv3)

| 항목 | Telegraf | Zabbix |
|---|---|---|
| 수집 방식 | SNMP 플러그인 (conf 파일) | SNMP Template (XML 임포트) |
| 크리덴셜 관리 | .env → environment 주입 | Web UI 매크로 등록 |
| OID 관리 | conf 파일에 직접 명시 | 템플릿 XML 내 정의 |
| 장비 추가 방법 | agents 목록 수정 후 restart | Web UI 호스트 등록 |
| 실제 동작 여부 | (작성 예정) | (작성 예정) |

### EVE-NG 홈 서버

| 항목 | Telegraf | Zabbix |
|---|---|---|
| 에이전트 | Node Exporter (포트 9100) | Zabbix Agent2 (포트 10050) |
| 수집 방향 | Pull (Telegraf → 서버) | Passive (Zabbix → 서버) |
| 암호화 | 없음 (로컬 네트워크) | PSK 암호화 |
| 홈 서버 작업 | Docker 컨테이너 1개 실행 | Docker 컨테이너 1개 + PSK 파일 |
| 실제 동작 여부 | (작성 예정) | (작성 예정) |


## 데이터 저장

### 저장소 특성 비교

| 항목 | InfluxDB v2 | PostgreSQL (Zabbix) |
|---|---|---|
| DB 종류 | 시계열 특화 TSDB | 범용 RDBMS |
| 쿼리 언어 | Flux | SQL (Zabbix API 경유) |
| 데이터 압축 | 자동 압축 | 표준 RDBMS 저장 |
| 장기 보존 정책 | Retention Policy | Housekeeper (자동 삭제) |
| 실측 저장 용량 (1주) | (작성 예정) | (작성 예정) |
| 실측 저장 용량 (1개월) | (작성 예정) | (작성 예정) |

### 쿼리 복잡도

| 시나리오 | Flux | SQL/Zabbix API |
|---|---|---|
| 인터페이스 BPS 계산 | derivative() 내장 함수 사용 | (작성 예정) |
| 시간 범위 집계 | aggregateWindow() | (작성 예정) |
| 다중 측정값 조합 | join()/union() | (작성 예정) |
| 체감 난이도 | (작성 예정) | (작성 예정) |


## 시각화

### Grafana 연동

| 항목 | Telegraf (InfluxDB) | Zabbix |
|---|---|---|
| 데이터소스 플러그인 | 내장 | alexanderzobnin-zabbix-app (외부) |
| 플러그인 설치 | 불필요 | GF_INSTALL_PLUGINS 자동 설치 |
| 자동 프로비저닝 | datasources + dashboards yml | datasources yml |
| 대시보드 JSON 재사용 | 가능 (동일 구조) | 데이터소스 쿼리 수정 필요 |
| 실제 대시보드 구성 시간 | (작성 예정) | (작성 예정) |

### 대시보드 기능 비교

| 패널 | Telegraf | Zabbix |
|---|---|---|
| 인터페이스 BPS | Flux derivative() | (작성 예정) |
| ACI Fault 추이 | aci_fault measurement | (작성 예정) |
| 템플릿 변수 (hostname 등) | InfluxDB schema.tagValues() | Zabbix API |
| 체감 응답 속도 | (작성 예정) | (작성 예정) |


## 알림

### 알림 아키텍처

| 항목 | Telegraf | Zabbix |
|---|---|---|
| 알림 엔진 | Grafana Alert Rules | Zabbix Trigger + Action |
| Slack 연동 | Webhook → slack_notify.py | alertscripts/slack_notify.sh |
| 알림 조건 설정 위치 | Grafana Web UI | Zabbix Web UI |
| 알림 이력 저장 | Grafana DB | Zabbix DB |
| 알림 억제/그룹화 | Grafana Silences | Zabbix Maintenance |
| 실제 알림 수신 여부 | (작성 예정) | (작성 예정) |
| 오탐(False Positive) 발생 | (작성 예정) | (작성 예정) |


## 운영 관리

### 장비 추가 절차

**Telegraf:**
```
1. telegraf/inputs.d/snmp_cisco_ios.conf 의 agents 에 IP 추가
2. docker compose restart telegraf
```

**Zabbix:**
```
1. Zabbix Web UI → Configuration → Hosts → Create Host
2. 호스트명, IP, 인터페이스 설정
3. 템플릿 연결
4. SNMPv3 매크로 확인
```

### 설정 백업 및 복원

| 항목 | Telegraf | Zabbix |
|---|---|---|
| 백업 대상 | conf 파일, .env | XML 템플릿 내보내기, DB 백업 |
| Git 관리 | 전체 설정 파일 관리 가능 | XML 템플릿만 관리 가능 |
| 복원 절차 | git clone → docker compose up | DB 복원 + 템플릿 임포트 |
| 체감 편의성 | (작성 예정) | (작성 예정) |

### 트러블슈팅

| 시나리오 | Telegraf | Zabbix |
|---|---|---|
| 수집 실패 원인 확인 | docker compose logs telegraf | Zabbix Web UI → Monitoring → Latest data |
| SNMPv3 인증 오류 | 로그에서 직접 확인 | Web UI 에서 시각적 확인 가능 |
| 스크립트 오류 | stderr 로그 | External Check 오류 로그 |
| 체감 디버깅 난이도 | (작성 예정) | (작성 예정) |


## 리소스 사용량

> Zabbix 구현 완료 후 동일 조건에서 측정 예정
> 측정 조건: 수집 대상 n대, 수집 주기 60초, 측정 시간 1시간 평균

### 컨테이너 리소스

| 컴포넌트 | CPU (평균) | 메모리 (평균) |
|---|---|---|
| Telegraf | (작성 예정) | (작성 예정) |
| InfluxDB | (작성 예정) | (작성 예정) |
| Grafana (TIG) | (작성 예정) | (작성 예정) |
| **TIG 합계** | (작성 예정) | (작성 예정) |
| Zabbix Server | (작성 예정) | (작성 예정) |
| PostgreSQL | (작성 예정) | (작성 예정) |
| Grafana (Zabbix) | (작성 예정) | (작성 예정) |
| **Zabbix 합계** | (작성 예정) | (작성 예정) |


## 학습 곡선

### 사전 지식 요구 수준

| 항목 | Telegraf | Zabbix |
|---|---|---|
| SNMP 기본 지식 | 필요 | 필요 |
| Docker / Compose | 필요 | 필요 |
| 쿼리 언어 | Flux (신규 학습) | SQL 수준 |
| 설정 파일 형식 | TOML | XML + Web UI |
| 알림 설정 | Grafana UI | Zabbix UI (복잡) |
| 전반적 진입 장벽 | (작성 예정) | (작성 예정) |


## 결론 및 선택 기준

> Zabbix 구현 완료 후 실제 운용 경험을 바탕으로 작성 예정

### 잠정 결론 (Telegraf 구현 완료 시점)

(작성 예정)

### 선택 기준 제안

| 상황 | 추천 도구 |
|---|---|
| 코드 기반 설정 관리 선호 | Telegraf (TIG) |
| GUI 중심 운영 환경 | Zabbix |
| 시계열 분석/쿼리 복잡도 중요 | Telegraf (TIG) |
| 다양한 내장 템플릿 필요 | Zabbix |
| 소규모 인프라 빠른 구성 | Telegraf (TIG) |
| 대규모 인프라 중앙 관리 | Zabbix |
| 알림 고도화 필요 | Zabbix |

### TTL64 블로그 포스팅 링크

- (Zabbix 구현 및 포스팅 완료 후 링크 추가 예정)