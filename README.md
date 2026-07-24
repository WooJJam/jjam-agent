# jjam-agent

Discord로 사용하는 **Hermes 기반 개인 AI 비서 POC**.

- 매일 오전 8시 날씨 브리핑 (기본 서울, `WEATHER_LOCATION`으로 변경 가능)
- 매일 오전 9시 AI·개발 뉴스 브리핑 (최근 24h + 원문 링크)
- OpenAI 토큰 사용량·예상 비용 조회 (`/usage`)
- AWS 누적 비용 조회 (`/cost`)
- Discord 일반 대화 + 메모리

> 런타임: [Hermes](https://hermes-agent.nousresearch.com/docs/) (CLI + Discord 게이트웨이 + cron + 마크다운 메모리)
> 배포 대상: AWS EC2 t3.micro / Ubuntu LTS / systemd

---

## 📌 현재 상태

**P0 부트스트랩 — 실행계획만 푸시된 상태.** 실제 기능 구현은 아직 없음.
다른 데스크탑에서 이어서 작업하기 위한 계획 문서가 레포에 포함되어 있습니다.

- 개발 오케스트레이션 & 구현 계획 → [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md)
- 원본 POC 기획서 → [`docs/POC_SPEC.md`](docs/POC_SPEC.md)

## 🚀 다른 데스크탑에서 이어서 시작하기

```bash
git clone https://github.com/WooJJam/jjam-agent.git
cd jjam-agent
cp .env.example .env      # 값 채우기 (절대 커밋 금지)
```

그다음 `docs/DEVELOPMENT_PLAN.md`의 **6. 단계별 구현 계획(P1~P6)** 순서대로 진행.

## 🔐 보안 원칙

- 모든 비밀값은 `.env`에만. `.gitignore`가 `.env`를 차단하며 `.env.example`만 커밋됩니다.
- API Key·Discord Token을 로그로 출력하지 않습니다.
- AWS는 EC2에 읽기전용 IAM Role 연결(액세스 키 저장 금지).
- Discord 요청은 지정 사용자·채널 화이트리스트에서만 허용.

## 🗂 예정 디렉터리 구조

```
config/   hermes.yaml, sources.yaml, prompts/
scripts/  collect-news.py, get-weather.py, get-aws-cost.sh, get-token-usage.py
data/     assistant.db, cache/
logs/
systemd/  hermes-assistant.service
docs/     DEVELOPMENT_PLAN.md, POC_SPEC.md
```
