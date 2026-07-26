---
name: cost
description: AWS 이번 달 누적/서비스별/예상 월말 비용을 조회한다. "AWS 얼마 나왔어", "이번 달 클라우드 비용", "서비스별 비용", "/cost" 등을 물을 때 사용.
version: 1.0.0
author: jjam-agent
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cost, aws, billing]
    category: jjam
    requires_toolsets: [terminal]
required_environment_variables:
  - name: AWS_REGION
    prompt: AWS 리전
    help: 기본 ap-northeast-2. (Cost Explorer 자체는 us-east-1 글로벌 엔드포인트 사용)
    required_for: 참고용(스크립트는 CE를 us-east-1로 호출)
---

# AWS 비용 조회 (cost)

## When to Use
- 사용자가 AWS 이번 달 비용·서비스별 비용·월말 예상 비용을 물을 때.
- `/cost`, `/cost services`, `/cost forecast` 명령.

## Procedure
1. 저장소 루트(`terminal.cwd`)에서 비용 조회 스크립트를 실행한다:
   ```bash
   bash scripts/get-aws-cost.sh month      # 이번 달 누적 총비용
   bash scripts/get-aws-cost.sh services   # 서비스별 비용
   bash scripts/get-aws-cost.sh forecast   # 월말까지 예상 비용
   ```
2. 표 형태 출력을 그대로 전하거나 핵심 수치(총액·상위 서비스·예상 월말)를 간결히 정리한다.

## Pitfalls
- **자격증명이 필요하다.** EC2에서는 **읽기전용 IAM Role**(`ce:GetCostAndUsage`,
  `ce:GetCostForecast`)을 인스턴스에 붙인다. **Access Key 하드코딩 금지.**
  로컬은 `aws configure`/`AWS_PROFILE`. 자격증명이 없으면 스크립트가 안내 후 종료한다(exit 2/3).
- AWS CLI(`aws`)가 설치돼 있어야 한다. 미설치 시 스크립트가 설치 링크를 안내한다.
- Cost Explorer API 는 **요청당 소액($0.01) 과금**될 수 있다 — 남발하지 않는다.
- 이번 달 누적은 미확정(예상 포함) 값이며, `forecast` 시작일은 오늘(과거 예측 불가)이다.
- 비용 급증/임계치(월 예상 $5 주의·$10 경고) 판단 시 사용자에게 사실만 전하고 과장하지 않는다.

## Verification
```bash
bash -n scripts/get-aws-cost.sh     # 문법 점검(자격증명 없이 가능)
bash scripts/get-aws-cost.sh --help
```
- 자격증명이 있는 환경에서 `month` 가 표를 출력하면 정상.
- 자격증명이 없으면 친절한 오류 메시지 후 종료(정상 동작).
