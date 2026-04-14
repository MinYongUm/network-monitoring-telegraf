# 설치 및 실행 가이드


## 목차

- [사전 요구사항](#사전-요구사항)
- [환경변수 설정](#환경변수-설정)
- [스택 기동](#스택-기동)
- [기동 확인](#기동-확인)
- [홈 서버 연동](#홈-서버-연동)
- [Slack 알림 설정](#slack-알림-설정)
- [스택 종료](#스택-종료)
- [환경변수 목록](#환경변수-목록)


## 사전 요구사항

- Docker 24.0 이상
- Docker Compose v2.0 이상
- 수집 대상 장비에 SNMPv3 설정 완료
- ACI APIC Read-only 계정 준비
- EVE-NG 홈 서버에 Node Exporter 실행 중 (포트 9100)


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


## Docker 실행

```bash
docker compose up -d
```

컨테이너 실행 순서는 아래와 같습니다.

```
1. influxdb       — 시계열 DB 초기화 및 healthcheck 대기
2. telegraf       — influxdb healthy 확인 후 기동
3. aci-collector  — influxdb healthy 확인 후 기동, requirements.txt 설치
4. grafana        — influxdb healthy 확인 후 기동, 대시보드 자동 프로비저닝
5. slack-notifier — Grafana Webhook 수신 대기 (포트 5001)
```


## Docker 확인

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

EVE-NG 홈 서버에 Node Exporter 를 바이너리로 설치합니다.

> 주의: EVE-NG 서버에 Docker 를 설치하면 EVE-NG 의 네트워크 네임스페이스 및
> iptables 설정과 충돌하여 가상 장비 간 통신이 불가능해집니다.
> Node Exporter 는 반드시 바이너리 직접 설치 방식을 사용하십시오.

### Node Exporter 설치 (EVE-NG 서버에서 실행)

```bash
cd /tmp
wget https://github.com/prometheus/node_exporter/releases/download/v1.9.1/node_exporter-1.9.1.linux-amd64.tar.gz
tar xzf node_exporter-1.9.1.linux-amd64.tar.gz
mv node_exporter-1.9.1.linux-amd64/node_exporter /usr/local/bin/
```

### systemd 서비스 등록

```bash
cat << 'EOF' > /etc/systemd/system/node_exporter.service
[Unit]
Description=Node Exporter
After=network.target

[Service]
ExecStart=/usr/local/bin/node_exporter
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable node_exporter
systemctl start node_exporter
```

### 연결 확인

```bash
# <EVE-NG 서버 IP> 를 실제 EVE-NG 서버의 IP 주소로 변경하여 실행
curl http://<EVE-NG 서버 IP>:9100/metrics
```

정상적으로 메트릭 데이터가 출력되면 연결이 완료된 것입니다.


## Slack 알림 설정

Grafana Alert 발생 시 `slack-notifier` 컨테이너를 통해 Slack 채널로 알림이 전달됩니다.

### 1. Slack Incoming Webhook URL 발급

Slack 워크스페이스에서 Incoming Webhook 앱을 추가하고 URL 을 발급받습니다.

### 2. .env 에 Webhook URL 등록

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### 3. Grafana Webhook Contact Point 설정

Grafana → Alerting → Contact Points 에서 아래와 같이 설정합니다.

```
Type : Webhook
URL  : http://slack-notifier:5001/alert
```

### 4. Notification Policy 설정

Grafana → Alerting → Notification Policies 에서 매칭 조건을 설정합니다.

```
매칭 조건: grafana_folder = network-monitoring
Contact Point: (위에서 생성한 Webhook Contact Point)
```

> 주의: Alert Rule Labels 에 `severity` 는 Grafana 예약 label 이므로 사용하지 않습니다.
> Notification Policy 매칭 조건은 `grafana_folder` 또는 `alertname` 을 사용하십시오.


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
| `INFLUXDB_USERNAME` | InfluxDB 관리자 계정 | |
| `INFLUXDB_PASSWORD` | InfluxDB 관리자 비밀번호 | 12자 이상 |
| `INFLUXDB_ORG` | InfluxDB 조직명 | 기본값: homelab |
| `INFLUXDB_BUCKET` | 메트릭 저장 버킷명 | 기본값: network-metrics |
| `INFLUXDB_TOKEN` | API 토큰 | 32자 이상, openssl rand -hex 32 |
| `GRAFANA_ADMIN_USER` | Grafana 관리자 계정 | |
| `GRAFANA_ADMIN_PASSWORD` | Grafana 관리자 비밀번호 | 12자 이상 |
| `GRAFANA_SECRET_KEY` | 세션 서명 시크릿 키 | openssl rand -base64 24 |
| `APIC_URL` | ACI APIC URL | https:// 포함 |
| `APIC_USERNAME` | ACI Read-only 계정 | |
| `APIC_PASSWORD` | ACI 계정 비밀번호 | |
| `SNMP_COMMUNITY` | SNMPv2c 커뮤니티 문자열 | 기본값: public |
| `SNMP_AUTH_USERNAME` | SNMPv3 사용자명 | 장비 설정과 일치 |
| `SNMP_AUTH_PASSWORD` | SNMPv3 SHA 인증 비밀번호 | 8자 이상 |
| `SNMP_PRIV_PASSWORD` | SNMPv3 AES 암호화 비밀번호 | 8자 이상 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL | 알림 미사용 시 임의값 입력 |