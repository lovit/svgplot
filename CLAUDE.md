# svgplot

markdown 문서에 박아넣을, 심미성 있고 수정이 쉬운 정적 SVG 차트를 Python으로 만드는 패키지.
설계 배경은 `docs/research/`를 참고(pygal/matplotlib/seaborn/Bokeh 기능 조사 + 설계 결정, `docs/research/00-overview.md`부터 읽기).

## 개발 워크플로

```
/start-issue "기능 설명"   → GitHub 이슈 생성 + worktree branch 분기
코드 작업
/commit                    → 의미 단위 분리, 한국어 conventional commit
/review                    → 4개 sub-agent 병렬 리뷰 (품질/목표/보안/테스트)
/open-pr                   → PR 생성 (Closes #N 자동 포함)
머지 후: /worktree-clean   → 완료된 worktree/브랜치 정리
```

**기본 규칙**: 항상 이슈를 먼저 만들고, worktree 로 분기해서 작업한다.
단, 사용자가 **명시적으로 요청**한 경우에만 현재 브랜치에서 직접 작업한다.
자세한 절차·머지 조건: @.claude/rules/branch.md

## 커밋 규칙

- 형식: `<type>(<scope>): <한국어 설명>`
- type: `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `style` / `perf`
- **한 commit = 한 의도** — 리팩터링과 기능 추가를 섞지 않는다
- subject 는 한국어 50자 이내, 마침표 없음
- `Co-Authored-By`는 붙이지 않는다
- 자세한 예시: @.claude/rules/branch.md

## 브랜치/PR 규칙

- 브랜치: `feature/{issue-number}` (예: `feature/42`)
- worktree 위치: `../svgplot-worktrees/feature/<n>`
- PR body: `Closes #N` 필수
- **머지 전 CI green + `/review` Approve 둘 다 필수** (@.claude/rules/branch.md)

## 개발 환경

| 도구 | 용도 | 명령 |
|---|---|---|
| mise | Python 버전 고정 + 환경변수 + 태스크 러너 | `mise install`, `mise run install`, `mise run check` |
| uv | 의존성 관리 | `uv add`, `uv sync`, `uv run` |
| ruff | lint + format | `uv run ruff check . --fix` |
| prek | 커밋 전 자동 체크 (pre-commit 호환) | `uv run prek run --all-files` |
| pytest | 테스트 | `uv run pytest` |

line-length=127, target-version=py312
자세한 스타일 규칙: @.claude/rules/python-style.md

로컬 세팅: `mise install && mise run install`
CI와 동일하게 확인: `mise run check`

## Slash Commands

| 명령 | 설명 |
|---|---|
| `/start-issue` | 이슈 생성 + worktree branch 분기 |
| `/commit` | 의미 단위 분리해 한국어 conventional commit |
| `/review` | 4 sub-agent 병렬 리뷰 |
| `/open-pr` | PR 생성 |
| `/sync-main` | main 동기화 + 현재 브랜치 rebase |
| `/worktree-clean` | 머지 완료된 worktree/브랜치 정리 |

## PR 리뷰 Sub-agents

`/review` 호출 시 4개가 병렬로 실행됨:

| Agent | 모델 | 검토 관점 |
|---|---|---|
| `code-quality-reviewer` | Sonnet | 가독성, 네이밍, 중복, 타입, PEP 준수, commit 단위 |
| `issue-goal-reviewer` | Sonnet | 이슈 Acceptance Criteria 달성 여부, scope creep 감지 |
| `security-reviewer` | Opus | OWASP, secret 노출, 인증/인가, 의존성 취약점 |
| `test-coverage-reviewer` | Sonnet | behavior coverage, edge case |

리뷰 정책 상세: @.claude/rules/review-policy.md

## Writing style

- PR 본문, 이슈 본문, markdown 파일을 작성할 때 불필요한 하드랩(hard wrap)을 넣지 않는다.
  문단은 줄바꿈 없이 이어서 쓰고, 필요한 경우(리스트, 코드 블록 등)에만 줄바꿈한다.

## 참고 문서

- Git 워크플로: @.claude/rules/branch.md
- Python 스타일: @.claude/rules/python-style.md
- 리뷰 정책: @.claude/rules/review-policy.md
- 설계 배경(사전 조사): `docs/research/00-overview.md`
