# Hermes 런타임 설치 및 설정 (SETUP_HERMES)

jjam-agent의 런타임인 **Hermes**(NousResearch)를 설치하고, 기본 모델 **GPT-5.6 Luna**에
연결한 뒤 터미널 대화와 Discord 게이트웨이까지 올리는 절차다.

- 대상 환경: **EC2 Ubuntu Server LTS**(운영) / **로컬 Windows 11**(개발·테스트)
- 공식 문서: <https://hermes-agent.nousresearch.com/docs/>
- 이 레포의 설정 템플릿:
  - `config/hermes.yaml` → `~/.hermes/config.yaml` (모델·터미널·메모리·Discord 게이트웨이 화이트리스트 포함)
  - `config/SOUL.md` → `~/.hermes/SOUL.md` (에이전트 정체성/페르소나)
  - `config/prompts/{weather,daily-briefing}.md` → 각 스킬이 참조하는 요약 프롬프트

> 핵심 원칙: **시크릿은 파일에 하드코딩하지 않는다.** 모든 비밀값은
> `hermes config set KEY VALUE` 로 `~/.hermes/.env` 에 저장하고, 설정 파일에서는
> `${VAR}` 로 치환한다.

---

## 0. 사전 준비 (사용자 직접)

- OpenAI API Key 발급 (`OPENAI_API_KEY`)
- Discord 앱·봇 생성, 봇 토큰(`DISCORD_BOT_TOKEN`), 서버 초대
- 본인 Discord 사용자 ID(`DISCORD_ALLOWED_USER_ID`), (선택) 채널 ID(`DISCORD_ALLOWED_CHANNEL_ID`)
- EC2의 경우: t3.micro, Ubuntu LTS, Swap 2GB, TZ=Asia/Seoul, 읽기전용 IAM Role 연결

---

## 1. 설치

### 1-A. EC2 Ubuntu (운영)

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
# 설치 후 PATH 반영이 안 되면 셸 재시작 또는:  source ~/.bashrc
hermes --version
```

### 1-B. 로컬 Windows (개발)

PowerShell에서:

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
hermes --version
```

> 참고: Discord 게이트웨이의 systemd 서비스 등록(4장)은 Linux(EC2) 전용이다.
> Windows에서는 게이트웨이를 포그라운드(`hermes gateway`)로 테스트한다.

---

## 2. 초기 설정과 Luna 연결

### 2-1. 초기 설정 마법사

```bash
hermes setup --portal
```

포털 안내에 따라 계정/프로바이더 기본값을 잡는다.

### 2-2. 시크릿 저장 (~/.hermes/.env)

```bash
hermes config set OPENAI_API_KEY sk-xxxxxxxxxxxxxxxx
# Discord 사용 예정이면 지금 함께 저장
hermes config set DISCORD_BOT_TOKEN xxxxxxxxxxxxxxxx
```

시크릿은 `~/.hermes/.env` 에 저장되며 설정 파일에 노출되지 않는다.

### 2-3. 설정 파일 배치

레포 템플릿을 Hermes 설정 위치로 복사한다(최초 1회). 기존 `~/.hermes/config.yaml`이
있으면 내용을 병합한다.

```bash
mkdir -p ~/.hermes
cp config/hermes.yaml ~/.hermes/config.yaml
cp config/SOUL.md     ~/.hermes/SOUL.md      # 에이전트 정체성(페르소나)
# config.yaml 의 terminal.cwd 를 레포 절대경로로 수정(예: /home/ubuntu/jjam-agent)
hermes config edit
```

또는 개별 키만 반영:

```bash
hermes config set model.default gpt-5.6-luna
hermes config set model.provider openai
hermes config          # 현재 설정 확인
hermes model           # 활성 모델 확인(provider/base_url 여기서 확정)
```

기본 모델 `gpt-5.6-luna` 가 잡혀 있어야 한다. provider 는 `hermes model` 로
확정한다(OpenAI 계열은 provider 값과 별개로 OpenAI 호환 `base_url` 지정이 필요할 수 있다).

> 정체성 프롬프트는 `prompt.system_file` 같은 키가 아니라 **`~/.hermes/SOUL.md`** 로 관리된다.

---

## 3. P1 완료 검증 — 터미널에서 Luna와 대화 왕복

```bash
hermes
```

대화창에서 예: `안녕, 지금 연결된 모델 이름이 뭐야?` 라고 입력한다.

**완료 기준(P1):**
- `hermes model` 출력이 `gpt-5.6-luna` / `openai`
- 터미널 대화에서 정상적으로 한국어 응답이 왕복됨(요청→응답)
- API 키 오류/모델 미인식 오류가 없음

문제 시 점검: `hermes config` 로 키 확인 → `OPENAI_API_KEY` 재설정 →
프로바이더 오타 확인.

---

## 4. Discord 게이트웨이

### 4-1. 화이트리스트 설정 (~/.hermes/config.yaml 의 `gateway:` 블록)

게이트웨이 화이트리스트는 별도 파일이 아니라 `config.yaml` 의 `gateway:` 블록에서
관리한다(`config/hermes.yaml` 에 템플릿 포함). 실제 필드는 다음과 같다:

- `allow_from` — 봇 사용을 허용할 사용자 ID 배열(목록 밖은 무시)
- `allow_admin_from` — 관리자 명령까지 허용할 사용자
- `group_allow_admin_from` — 채널/그룹 스코프의 관리자 허용 사용자
- `group_user_allowed_commands` — 채널에서 비관리자가 쓸 수 있는 슬래시 명령

사용자 ID는 환경변수로 지정한다:

```bash
hermes config set DISCORD_ALLOWED_USER_ID "실제_사용자_ID"   # ${...} 치환
```

> 채널 제한: 이전 템플릿의 `allow_channels` 는 실제 스키마에 없는 필드였다.
> 공식 문서 기준으로 채널 통제는 **봇을 원하는 채널에만 초대**하고
> `group_allow_admin_from` / `group_user_allowed_commands` 로 권한을 나눈다.
> (근거: <https://hermes-agent.nousresearch.com/docs/user-guide/messaging>)

### 4-2. 포그라운드 실행(테스트)

```bash
hermes gateway
```

Discord에서 봇에게 DM 또는 허용 채널에 메시지를 보내 응답을 확인한다.
화이트리스트에 없는 사용자는 무시되어야 한다.

### 4-3. 백그라운드 실행

```bash
hermes gateway start
```

---

## 5. systemd 등록 (EC2 상시 운영)

Hermes가 제공하는 user service 설치 명령을 사용한다.

```bash
hermes gateway install
```

이 명령이 게이트웨이를 user 레벨 systemd 서비스로 등록한다. 등록 후 확인:

```bash
systemctl --user status hermes-gateway    # 서비스명은 hermes 출력으로 확인
systemctl --user enable  hermes-gateway   # 자동 시작
# 재부팅 후에도 유지하려면 linger 활성화(user 서비스가 로그인 없이 실행되게)
sudo loginctl enable-linger $USER
```

> 참고: `hermes gateway install` 이 user 레벨 systemd 유닛을 등록한다. 레포의
> `systemd/hermes-assistant.service` 를 따로 두기보다 이 명령을 표준 경로로 쓴다.
> 재부팅 자동 실행은 위의 `enable-linger` 로 보장한다.

### 예약 작업(cron) — 오전 8시 날씨 / 9시 브리핑

Hermes cron 은 `~/.hermes/cron/jobs.json` 에 저장되며, 직접 편집보다 `hermes cron`
(또는 대화 중 cronjob 도구)로 관리한다. 잡의 핵심 필드는 `schedule`(cron 식),
`prompt`, `deliver`("discord:#채널"), `skill`, `no_agent`, `script` 이다.

레포 원본 템플릿은 `config/cron/jobs.json` 이며, **날씨/뉴스 기능 PR에서 각 잡을 추가**한다.
배포 시 다음처럼 등록한다(예):

```bash
hermes cron create --name weather-0800 --schedule "0 8 * * *" \
  --skill weather --deliver "discord:#daily"
hermes cron create --name briefing-0900 --schedule "0 9 * * *" \
  --skill briefing --deliver "discord:#daily"
hermes cron list
```

> 스케줄은 시스템 타임존(EC2 `TZ=Asia/Seoul`) 기준으로 해석된다.
> (근거: <https://hermes-agent.nousresearch.com/docs/user-guide/features/cron>)

---

## 6. 요약 체크리스트

- [ ] `hermes --version` 정상
- [ ] `hermes config set OPENAI_API_KEY ...` 완료 (`~/.hermes/.env`)
- [ ] `~/.hermes/config.yaml` 에 `model.default: gpt-5.6-luna` + `terminal.cwd` 레포 경로
- [ ] `~/.hermes/SOUL.md` 배치(정체성 프롬프트)
- [ ] `hermes` 터미널 대화에서 Luna 응답 왕복 (P1 완료)
- [ ] `config.yaml` 의 `gateway:` 화이트리스트에 본인 Discord ID(`allow_from`)
- [ ] `hermes gateway` 로 Discord 응답 확인
- [ ] (EC2) `hermes gateway install` + linger 로 재부팅 자동 실행
