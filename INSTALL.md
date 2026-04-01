# 설치 및 실행 가이드


## 목차

- [사전 요구사항](#사전-요구사항)
- [설치](#설치)
- [환경변수 설정](#환경변수-설정)
- [스택 기동](#스택-기동)
- [기동 확인](#기동-확인)
- [홈 서버 연동](#홈-서버-연동)
- [스택 종료](#스택-종료)
- [환경변수 목록](#환경변수-목록)


## 사전 요구사항

- Docker 24.0 이상
- Docker Compose v2.0 이상
- 수집 대상 장비에 SNMPv3 설정 완료
- ACI APIC Read-only 계정 준비
- EVE-NG 홈 서버에 Node Exporter 실행 중 (포트 9100)


## 설치

### 1. 레포지토리 클론

```bash
git clone https://github.com/MinYongUm/network-monitoring-telegraf.git
cd network-monitoring-telegraf
```


## 환경변수 설정

### 1. .env 파일 생성

```bash
cp .env.example .env
```

### 2. 토큰 및 시크릿 키 생성

`.env` 파일 작성 전 아래 명령어로 각 값을 미리 생성합니다.

```bash
# INFLUXDB_TOKEN 생성 (32자 이상 랜덤 문자열)
openssl rand -hex 32

# INFLUXDB_PASSWORD, GRAFANA_ADMIN_PASSWORD 생성 (12자 이상)
openssl rand -base64 12

# GRAFANA_SECRET_KEY 생성
openssl rand -base64 24
```

### 3. .env 파일 편집

생성된 값을 `.env` 파일의 각 항목에 입력합니다.

```bash
vi .env
```

> 주의: `.env` 파일은 절대 Git 에 커밋하지 않습니다. `.gitignore` 에 등록되어 있습니다.


## 스택 기동

```bash
docker compose up -d
```

컨테이너 기동 순서는 아래와 같습니다.

```
1. influxdb    — 시계열 DB 초기화 및 healthcheck 대기
2. telegraf    — influxdb healthy 확인 후 기동
3. aci-collector — influxdb healthy 확인 후 기동, requirements.txt 설치
4. grafana     — influxdb healthy 확인 후 기동, 대시보드 자동 프로비저닝
```


## 기동 확인

### 컨테이너 상태 확인

```bash
docker compose ps
```

모든 컨테이너가 `running` 상태여야 합니다.

### InfluxDB 헬스체크 확인

```bash
docker compose exec influxdb influx ping
```

`OK` 응답이 반환되면 정상입니다.

### Telegraf 로그 확인

```bash
# 실시간 로그 확인
docker compose logs -f telegraf

# 에러 메시지만 필터링
docker compose logs telegraf | grep -i error
```

### Grafana 접속

브라우저에서 `http://localhost:3000` 접속 후 `.env` 에 설정한 관리자 계정으로 로그인합니다.


## 홈 서버 연동

EVE-NG 홈 서버(192.168.0.200)에서 Node Exporter 를 실행합니다.

### Node Exporter 실행 (홈 서버에서)

```bash
docker run -d \
  --name node-exporter \
  --net="host" \
  --restart unless-stopped \
  prom/node-exporter:latest
```

### 연결 확인 (노트북 VM 에서)

```bash
curl http://192.168.0.200:9100/metrics
```

정상적으로 메트릭 데이터가 출력되면 연결이 완료된 것입니다.


## 스택 종료

```bash
# 컨테이너만 종료 (데이터 볼륨 유지)
docker compose down

# 컨테이너 및 데이터 볼륨 모두 삭제 (초기화)
docker compose down -v
```


## 환경변수 목록

| 변수 | 설명 | 비고 |
|---|---|---|
| INFLUXDB_USERNAME | InfluxDB 관리자 계정 | |
| INFLUXDB_PASSWORD | InfluxDB 관리자 비밀번호 | 12자 이상 |
| INFLUXDB_ORG | InfluxDB 조직명 | 기본값: homelab |
| INFLUXDB_BUCKET | 메트릭 저장 버킷명 | 기본값: network-metrics |
| INFLUXDB_TOKEN | API 토큰 | 32자 이상, openssl rand -hex 32 |
| GRAFANA_ADMIN_USER | Grafana 관리자 계정 | |
| GRAFANA_ADMIN_PASSWORD | Grafana 관리자 비밀번호 | 12자 이상 |
| GRAFANA_SECRET_KEY | 세션 서명 시크릿 키 | openssl rand -base64 24 |
| APIC_URL | ACI APIC URL | https:// 포함 |
| APIC_USERNAME | ACI Read-only 계정 | |
| APIC_PASSWORD | ACI 계정 비밀번호 | |
| SNMP_AUTH_USERNAME | SNMPv3 사용자명 | 장비 설정과 일치 |
| SNMP_AUTH_PASSWORD | SNMPv3 SHA 인증 비밀번호 | 8자 이상 |
| SNMP_PRIV_PASSWORD | SNMPv3 AES128 암호화 비밀번호 | 8자 이상 |