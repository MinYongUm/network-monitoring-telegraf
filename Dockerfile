# =============================================================================
# network-monitoring-telegraf / telegraf/Dockerfile
#
# 목적: Telegraf 공식 이미지에 SNMP MIB 파일을 추가한 커스텀 이미지
#
# 필요 이유:
#   telegraf:1.29 공식 이미지에는 SNMP MIB 파일이 포함되어 있지 않음
#   IF-MIB, CISCO-PROCESS-MIB 등 MIB 이름으로 OID 를 참조하려면
#   snmp-mibs-downloader 설치 및 MIB 다운로드가 필요
#
# 포함 MIB:
#   - IF-MIB         : ifHCInOctets, ifOperStatus 등 인터페이스 표준 MIB
#   - RFC1213-MIB    : sysName 등 기본 시스템 MIB
#   - CISCO-PROCESS-MIB   : NX-OS CPU 수집용
#   - CISCO-MEMORY-POOL-MIB: NX-OS 메모리 수집용
# =============================================================================

FROM telegraf:1.29

# SNMP MIB 다운로더 설치 및 표준 MIB 다운로드
# non-free 저장소 활성화 필요 (snmp-mibs-downloader 가 non-free 패키지)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        snmp \
        snmp-mibs-downloader && \
    download-mibs && \
    # /etc/snmp/snmp.conf 의 mibs 주석 해제 → MIB 이름 사용 활성화
    sed -i 's/^mibs :$/mibs +ALL/' /etc/snmp/snmp.conf || true && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*