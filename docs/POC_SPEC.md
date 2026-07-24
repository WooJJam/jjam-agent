# Hermes 기반 개인 AI 비서 POC — 원본 기획서

> 이 문서는 사용자가 작성한 원본 POC 기획서 원문이다. 개발 진행 방식/에이전트 오케스트레이션은
> [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md) 참고.

## 1. 목표

Discord를 통해 사용하는 개인 AI 비서를 구축한다.

POC 핵심 기능:

1. 매일 오전 AI·개발 뉴스 브리핑 전송
2. 매일 오전 오늘의 날씨 전송
3. OpenAI 토큰 사용량 및 예상 비용 조회
4. AWS 누적 비용 조회
5. Discord를 통한 일반 대화

---

## 2. 시스템 구조

```
Discord
  ↓
Hermes Agent
  ├─ GPT-5.6 Luna API
  ├─ 뉴스/RSS 수집
  ├─ 날씨 API
  ├─ AWS Cost Explorer
  ├─ 토큰 사용량 기록
  └─ Hermes Memory
```

구성 원칙:

- Hermes가 모든 요청과 예약 작업을 관리한다.
- GPT-5.6 Luna를 기본 모델로 사용한다.
- 별도의 Spring Boot, Express, Next.js 서버는 만들지 않는다.
- 부족한 기능만 소형 Python 또는 Shell 스크립트로 구현한다.
- 데이터는 SQLite에 저장한다.
- AWS EC2 t3.micro에서 운영한다.
- Pi, Claude OAuth, Codex OAuth는 이번 POC에서 제외한다.

---

## 3. 기능

### 3.1 일일 AI·개발 브리핑

실행 시각:

- 매일 오전 9시 / Asia/Seoul / 최근 24시간 자료 기준

수집 대상: AI·IT 주요 뉴스, Java·OpenJDK 업데이트, Spring Framework/Boot 변경사항,
백엔드·클라우드·보안 이슈, 실서비스 장애·성능 개선 사례, 새 개발 아이디어, 실무 인사이트.

처리 과정:

1. RSS 및 검색 API로 자료 수집
2. 게시일 기준 최근 24시간 자료만 남김
3. URL·제목 기준 중복 제거
4. 출처·게시 시각 검증
5. 중요도·실무 관련성 정렬
6. GPT-5.6 Luna로 요약·인사이트 생성
7. Discord 메시지 길이에 맞게 분할 전송
8. 전송 URL 저장해 반복 추천 방지

출력 형식:

```
[오늘의 AI·개발 브리핑]

1. 오늘 꼭 볼 소식 (핵심/이유/실무 영향/원문 링크)
2. Java·Spring (업데이트·이슈/변경사항/주의점/링크)
3. 백엔드·인프라 (장애·성능·운영 사례/교훈)
4. 오늘 시도해볼 아이디어 (아이디어/기대효과/실험 방법)
5. 한 줄 결론
```

### 3.2 오늘의 날씨

- 매일 오전 8시 / Asia/Seoul / 기본 지역 서울(WEATHER_LOCATION 환경변수로 변경 가능)
- 조회: 현재기온, 최저·최고, 체감, 시간대별 강수확률, 예상 강수량, 습도, 풍속, 미세먼지, 기상특보

출력 예시:

```
[오늘의 날씨]
- 현재: 24℃
- 최저/최고: 21℃ / 31℃
- 비 가능 시간: 15시~18시
- 최고 강수 확률: 70%
- 특이사항: 오후 소나기 가능
- 추천: 우산 준비, 야외 일정은 오전 권장
```

### 3.3 토큰 사용량 및 API 비용

모든 모델 호출 기록: 호출 시각, 기능, 모델명, 입력·출력 토큰, 예상 비용, 응답 시간, 성공 여부.

통계: 오늘/이번 달 누적/기능별/예상 API 비용/월말 예상/전일 대비 증감.
저장: SQLite (별도 DB 서버 없음).
명령어: `/usage`, `/usage today`, `/usage month`.
주의: OpenAI 실제 청구액과 로컬 계산 예상액에 차이 가능 → 로컬은 "예상 비용" 표시.

### 3.4 AWS 비용 조회

AWS Cost Explorer API 또는 AWS CLI 사용.
조회: 이번 달 누적, 어제 비용, 서비스별, EC2 관련, 예상 월말, 전월 대비 증감.
명령어: `/cost`, `/cost month`, `/cost services`.
알림 예시: 월 예상 $5 초과 주의 / $10 초과 경고 / 하루 비용 급증 즉시 알림.
AWS 권한: `ce:GetCostAndUsage`, `ce:GetCostForecast`, `cloudwatch:GetMetricData`, `ec2:DescribeInstances`.
EC2에는 Access Key 저장 금지 → 읽기 전용 IAM Role 연결.

### 3.5 일반 대화와 기억

Hermes가 GPT-5.6 Luna로 일반 대화 응답.
기억 대상: 관심 기술, 선호 브리핑 형식, 기본 날씨 지역, 알림 시간, 자주 쓰는 명령, 명시 저장 정보.
민감 정보는 저장하지 않음.
명령어: `/ask [질문]`, `/remember [내용]`, `/forget [내용]`, `/status`.

---

## 4. 서버 구성

AWS: EC2 t3.micro / Ubuntu Server LTS / 메모리 1GB / Swap 2GB / 저장 15~20GB gp3 / TZ Asia/Seoul.
운영: Hermes만 상시 실행, systemd 관리, SQLite, Docker 미사용/최소, Redis·MySQL·PostgreSQL 미사용, 외부 웹서버 미개방.
보안: SSH 키 인증, 비밀번호·root 로그인 차단, UFW, 자동 보안 업데이트, 로그 로테이션, 비밀값 환경변수 관리, Discord 사용자 ID 화이트리스트.

---

## 5. 디렉터리 구조

```
personal-ai-assistant/
├── config/
│   ├── hermes.yaml
│   ├── sources.yaml
│   └── prompts/{system.md, daily-briefing.md, weather.md}
├── scripts/{collect-news.py, get-weather.py, get-aws-cost.sh, get-token-usage.py}
├── data/{assistant.db, cache/}
├── logs/
├── systemd/hermes-assistant.service
├── .env.example
└── README.md
```

---

## 6. 환경변수

```
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_USER_ID=
DISCORD_ALLOWED_CHANNEL_ID=
OPENAI_API_KEY=
DEFAULT_MODEL=gpt-5.6-luna
WEATHER_API_KEY=
WEATHER_LOCATION=서울
AWS_REGION=ap-northeast-2
TZ=Asia/Seoul
```

보안 원칙: 실제 `.env`는 Git 미커밋, API Key·Discord Token 로그 미출력, AWS는 IAM Role, Discord 요청은 지정 사용자·채널만 허용.

---

## 7. 역할 분담

### 사용자가 직접 해야 할 일
1. AWS 계정·예산 알림 설정  2. EC2 t3.micro 생성  3. EC2에 읽기전용 IAM Role 연결
4. Discord 앱·봇 생성  5. 봇 서버 초대  6. Discord Bot Token 준비  7. OpenAI API Key 발급
8. 날씨 API Key 발급  9. 기본 지역·알림 시간 결정  10. 비밀값 서버 환경변수 입력

### AI가 수행할 일
1. Hermes 설치·설정  2. Discord 연동  3. 뉴스 수집 도구  4. 날씨 도구  5. AWS 비용 도구
6. 토큰 사용량 집계  7. 브리핑·날씨 프롬프트  8. 예약 작업  9. systemd 서비스
10. 보안 체크리스트  11. 테스트·오류 수정  12. 운영 문서

계정 생성·결제·OAuth 인증·비밀키 입력은 사용자가 직접 수행.

---

## 8. 개발 순서 (완료 기준)

1. **로컬 최소 기능** — Hermes 설치, Luna 연결, 터미널 대화, 토큰 사용량. → Luna로 정상 응답.
2. **Discord 연동** — 봇 생성·연결, 사용자·채널 제한, 송수신. → Discord 메시지에 Hermes 응답.
3. **날씨** — API 연결, `/weather`, 오전 8시 예약. → 수동·자동 모두 작동.
4. **개발 브리핑** — RSS 등록, 24h 필터·중복 제거, Luna 요약, `/briefing`, 오전 9시 예약. → 링크 포함 브리핑 수동·자동.
5. **비용 조회** — OpenAI 호출량 기록, SQLite 통계, AWS Cost Explorer, `/usage`·`/cost`. → 오늘·이번 달 예상 비용 확인.
6. **AWS 배포·안정화** — EC2 설치, Swap, systemd, 로그 로테이션, 재부팅·복구 테스트, 모니터링. → 재부팅 후 자동 실행, 7일 안정.

---

## 9. POC 완료 조건

- Discord에서 Hermes와 대화 가능
- 매일 오전 8시 기본 지역(서울) 날씨 전달
- 매일 오전 9시 AI·개발 브리핑 전달(최근 24h + 원문 링크)
- OpenAI 토큰 사용량·예상 비용 확인 가능
- AWS 이번 달 비용·예상 월말 비용 확인 가능
- 서버 재부팅 후 자동 복구
- t3.micro에서 7일 이상 안정 실행
- 비밀키가 코드·Git에 노출되지 않음

---

## 10. POC 제외 범위

Pi 연동, Claude OAuth, OpenAI Codex OAuth, Spring Boot, Express·Next.js, 별도 웹 관리 페이지,
Redis, MySQL·PostgreSQL, 벡터 DB, 복잡한 RAG, 다중 사용자, 모바일 앱, 음성 인터페이스, 자동 코드 수정.

POC 검증 후 실제 필요성이 확인된 기능만 2차 개발에 추가.
