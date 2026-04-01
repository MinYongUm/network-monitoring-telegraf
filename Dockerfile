# =============================================================================
# network-monitoring-telegraf / Dockerfile
#
# 목적: Telegraf 공식 이미지에 SNMP MIB 파일을 추가한 커스텀 이미지
#
# 필요 이유:
#   telegraf:1.29 공식 이미지(Debian Bookworm 기반)에는 SNMP MIB 파일 미포함
#   IF-MIB, CISCO-PROCESS-MIB 등 MIB 이름으로 OID 를 참조하려면
#   snmp-mibs-downloader 설치 및 MIB 다운로드 필요
#
#   snmp-mibs-downloader 는 Debian non-free 저장소에 있으므로
#   apt sources.list 에 non-free 를 명시적으로 추가해야 함
#
#   Cisco 전용 MIB 는 라이선스 문제로 자동 다운로드 불가
#   telegraf/mibs/ 디렉토리에 직접 저장 후 이미지에 복사
#
# 포함 MIB:
#   표준 MIB (download-mibs 자동 다운로드):
#   - IF-MIB              : ifHCInOctets, ifOperStatus 등 인터페이스 표준 MIB
#   - RFC1213-MIB         : sysName 등 기본 시스템 MIB
#
#   Cisco 전용 MIB (telegraf/mibs/ 에서 복사):
#   - CISCO-PROCESS-MIB   : NX-OS CPU 수집용
#   - CISCO-MEMORY-POOL-MIB: NX-OS 메모리 수집용
#
# MIB 파일 출처:
#   https://github.com/cisco/cisco-mibs
# =============================================================================

FROM telegraf:1.29

# -----------------------------------------------------------------------------
# 표준 SNMP MIB 설치
#
# 1. Debian Bookworm non-free 저장소 추가
#    snmp-mibs-downloader 가 non-free 패키지이므로 반드시 필요
# 2. snmp (클라이언트 도구) 및 snmp-mibs-downloader 설치
# 3. download-mibs 실행으로 표준 MIB 파일 다운로드
# 4. /etc/snmp/snmp.conf 에 "mibs +ALL" 추가
#    기본 설정은 MIB 이름 사용이 비활성화되어 있으므로 활성화 필요
# -----------------------------------------------------------------------------
RUN echo "deb http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        snmp \
        snmp-mibs-downloader && \
    download-mibs && \
    echo "mibs +ALL" > /etc/snmp/snmp.conf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Cisco 전용 MIB 파일 복사
#
# telegraf/mibs/ 디렉토리의 MIB 파일을 표준 MIB 경로에 복사
# /usr/share/snmp/mibs/ 는 download-mibs 가 사용하는 표준 MIB 경로
# CISCO-PROCESS-MIB.my, CISCO-MEMORY-POOL-MIB.my 포함
# -----------------------------------------------------------------------------
COPY telegraf/mibs/ /usr/share/snmp/mibs/