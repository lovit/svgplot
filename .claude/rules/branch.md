# Git 워크플로 규칙

## Conventional Commit 형식

```
<type>(<scope>): <한국어 설명>

<선택: 한국어 본문 — 왜 이 변경이 필요한지>

<선택: footer>
Closes #<issue-number>
```

### Type 표

| type | 의미 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변화 없는 구조 개선 |
| `docs` | 문서만 변경 |
| `test` | 테스트 추가/수정 |
| `chore` | 빌드, 의존성, 설정 |
| `style` | 포매팅 (로직 변화 없음) |
| `perf` | 성능 개선 |

### Subject 규칙

- 한국어 50자 이내
- 마침표로 끝내지 않는다
- 명령형/현재형 권장: "추가", "수정", "개선"
- type 과 scope 는 영어 소문자

### BREAKING CHANGE

```
feat(api)!: /users 응답 구조 변경

BREAKING CHANGE: name 필드가 firstName, lastName 으로 분리됨.
```

---

## Commit Unit 분리 원칙

**한 commit = 한 의도.** 다음은 한 커밋에 섞으면 안 된다:

- 리팩터링 + 기능 추가
- 여러 무관한 버그 수정
- 테스트 + 로직 변경 (단, "테스트로 로직을 보호하는" 의도라면 OK)

### 좋은 분리 예시

```
refactor(auth): 토큰 검증 로직을 별도 함수로 추출
feat(auth): 리프레시 토큰 만료 시 자동 갱신
test(auth): 리프레시 토큰 갱신 케이스 추가
```

### 나쁜 예시

```
feat: 인증 개선          # 너무 추상적 + 3가지가 섞임
update                   # 무엇을? 왜?
작업중                   # type 없음, 의미 없음
Feat: 기능 추가함.       # type 대문자, 마침표
```

---

## Commit 실행 절차

사용자가 "커밋해줘", "commit 해줘", "변경사항 저장해줘" 등을 요청하면 다음 절차를 따른다.

### 1단계: 변경사항 파악

```bash
git status
git diff
```

### 2단계: 의도 분석

diff 를 읽고 변경사항을 **의도 단위**로 분류한다.

- 단일 의도 → 3단계로 바로 이동
- 복수 의도 → 아래 형식으로 분리 계획을 사용자에게 먼저 제안하고 확인받는다

```
변경사항을 N개 commit 으로 분리하겠습니다:

1. refactor(auth): 토큰 검증 로직을 별도 함수로 추출
   → src/auth/validator.py

2. feat(auth): 리프레시 토큰 만료 시 자동 갱신
   → src/auth/service.py

3. test(auth): 리프레시 토큰 갱신 케이스 추가
   → tests/test_auth.py

진행할까요?
```

### 3단계: Commit 메시지 초안 제시

메시지 초안을 사용자에게 보여주고 확인받은 뒤 실행한다.

```bash
git add <관련 파일>
git commit -m "<type>(<scope>): <한국어 설명>"
```

복수 의도인 경우 각 commit 을 순차적으로 stage + commit 한다.

### 주의사항

- `Co-Authored-By` 는 붙이지 않는다
- BREAKING CHANGE 가 있으면 type 에 `!` + footer 에 `BREAKING CHANGE:` 설명
- 스테이지된 변경이 없으면 무엇을 stage 할지 사용자에게 안내한다

---

## 브랜치 규칙

- 이름: `feature/{issue-number}` (예: `feature/42`)
- worktree 위치: `../<repo>-worktrees/feature/<n>` (sibling 디렉토리)
- 기본 분기점: `origin/main`
- **사용자 명시 요청 없이는 현재 브랜치에서 직접 작업하지 않는다**
- 예외: 레포 초기 세팅(인프라/설정 부트스트랩) 등 사용자가 명시적으로 "이슈/worktree 없이 main에 바로 커밋"을 지시한 경우에는 이 규칙을 따르지 않는다 — 단, 이 경우에도 커밋은 여전히 기능 단위로 분리한다.

---

## PR 규칙

- PR body 에 `Closes #N` 필수 (자동 이슈 닫기)
- PR 제목 = 주요 commit 의 subject 또는 그 요약
- PR 생성은 `/open-pr` 명령 사용

---

## 머지 조건 (필수)

다음 두 가지를 **모두** 만족해야 머지한다. 하나라도 미충족이면 머지하지 않는다.

- GitHub Actions **CI가 green**이다 (lint + test).
- 가장 최근 `/review` 결과가 **Approve**다 (Critical 이슈 없음).

CI는 review 실행 여부를 자동으로 강제하지 않는다 — `/review`는 에이전트/개발자가 PR 생성 후 직접 실행하는 프로세스 규칙이다. 따라서 머지하기 전 "review-policy.md 기준으로 Approve를 받았는가"를 스스로 반드시 확인한다.

### 지켜야 할 것

- `main`에 직접 push 금지(위 부트스트랩 예외 제외).
- CI가 red인 상태로 머지 금지.
- `/review`의 미해결 Critical 지적사항이 있는 상태로 머지 금지.

---

## Worktree 사용법

```bash
# 새 worktree 생성 (/start-issue 가 자동으로 실행)
git worktree add ../svgplot-worktrees/feature/42 -b feature/42 origin/main

# worktree 목록
git worktree list

# worktree 제거 (/worktree-clean 이 자동으로 실행)
git worktree remove ../svgplot-worktrees/feature/42
git branch -d feature/42
```
