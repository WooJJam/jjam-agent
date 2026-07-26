#!/usr/bin/env bash
#
# AWS 비용 조회 래퍼 (jjam-agent / cost-usage).
#
# AWS Cost Explorer(ce) API 를 감싸 이번 달 누적/서비스별 비용과
# 월말 예상(forecast)을 조회한다. jq 없이 AWS CLI 자체 --output table/json 을 쓴다.
#
# 사용법:
#   scripts/get-aws-cost.sh month      # 이번 달 누적 총비용
#   scripts/get-aws-cost.sh services   # 이번 달 서비스별 비용(내림차순은 CLI 미지원, 원자료)
#   scripts/get-aws-cost.sh forecast   # 월말까지 예상 비용
#
# 필요한 IAM 권한(읽기 전용):
#   - ce:GetCostAndUsage
#   - ce:GetCostForecast
#
# 배포 환경(EC2 Ubuntu): Access Key 하드코딩 금지.
#   위 권한만 부여한 읽기전용 IAM Role 을 인스턴스에 붙여 자격증명을 위임한다.
#   (로컬에서는 `aws configure` 또는 환경변수/SSO 프로파일 사용)
#
# 주의: Cost Explorer 는 US East (N. Virginia / us-east-1) 글로벌 엔드포인트를 쓴다.
#       또한 CE API 는 요청당 소액($0.01) 과금될 수 있다.

set -euo pipefail

# Cost Explorer 는 리전 무관 글로벌 서비스지만 엔드포인트는 us-east-1 고정.
CE_REGION="us-east-1"

usage() {
  cat <<'EOF'
사용법: get-aws-cost.sh <command>

  month      이번 달 누적 총비용(UnblendedCost)
  services   이번 달 서비스별 비용
  forecast   이번 달 말까지 예상 비용

예: scripts/get-aws-cost.sh month
EOF
}

# ── 사전 점검 ────────────────────────────────────────────────────────────
check_prereqs() {
  if ! command -v aws >/dev/null 2>&1; then
    echo "오류: AWS CLI(aws) 가 설치되어 있지 않습니다." >&2
    echo "  설치: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" >&2
    echo "  (EC2 라면 읽기전용 IAM Role 을 붙이고 CLI 를 설치하세요.)" >&2
    exit 2
  fi

  if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "오류: AWS 자격증명을 확인할 수 없습니다." >&2
    echo "  - 로컬: 'aws configure' 또는 AWS_PROFILE / 환경변수 설정" >&2
    echo "  - EC2 : ce:GetCostAndUsage, ce:GetCostForecast 권한의 IAM Role 연결" >&2
    exit 3
  fi
}

# 이번 달 기간 계산 (start=이달 1일, end=다음달 1일; CE 의 end 는 배타적)
month_start() { date -u +%Y-%m-01; }
next_month_start() {
  # GNU date(리눅스/EC2)와 BSD date(mac) 모두 시도
  date -u -d "$(date -u +%Y-%m-01) +1 month" +%Y-%m-01 2>/dev/null \
    || date -u -v+1m -j -f "%Y-%m-%d" "$(date -u +%Y-%m-01)" +%Y-%m-01
}
# forecast 의 end 는 미래여야 하므로 다음달 1일 사용.

cmd_month() {
  local start end
  start="$(month_start)"; end="$(next_month_start)"
  echo "[AWS 이번 달 누적 비용] ${start} ~ ${end} (예상/미확정 포함)"
  aws ce get-cost-and-usage \
    --region "$CE_REGION" \
    --time-period "Start=${start},End=${end}" \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --output table
}

cmd_services() {
  local start end
  start="$(month_start)"; end="$(next_month_start)"
  echo "[AWS 이번 달 서비스별 비용] ${start} ~ ${end}"
  aws ce get-cost-and-usage \
    --region "$CE_REGION" \
    --time-period "Start=${start},End=${end}" \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --group-by "Type=DIMENSION,Key=SERVICE" \
    --output table
}

cmd_forecast() {
  local start end
  start="$(date -u +%Y-%m-%d)"   # 예측 시작은 오늘(과거 불가)
  end="$(next_month_start)"
  echo "[AWS 월말 예상 비용] ${start} ~ ${end}"
  aws ce get-cost-forecast \
    --region "$CE_REGION" \
    --time-period "Start=${start},End=${end}" \
    --granularity MONTHLY \
    --metric "UNBLENDED_COST" \
    --output table
}

main() {
  local command="${1:-}"
  case "$command" in
    month)    check_prereqs; cmd_month ;;
    services) check_prereqs; cmd_services ;;
    forecast) check_prereqs; cmd_forecast ;;
    ""|-h|--help|help) usage ;;
    *) echo "알 수 없는 명령: ${command}" >&2; usage; exit 1 ;;
  esac
}

main "$@"
