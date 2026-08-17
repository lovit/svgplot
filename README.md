# svgplot

markdown 문서에 박아넣을, 심미성 있고 수정이 쉬운 정적 SVG 차트를 만드는 Python 패키지.

matplotlib/seaborn에 익숙한 문법으로 SVG를 만들되, pygal보다 데이터 시맨틱 매핑(`hue=`, `data=`)과 접근성을 갖추고,
matplotlib보다 렌더 후에도 CSS로 재테마 가능한 SVG를 목표로 한다. 설계 배경은 [`docs/research/`](docs/research/00-overview.md)를 참고
(pygal/matplotlib/seaborn/Bokeh 기능 조사와 그로부터 도출한 설계 결정).

> 현재 이 레포는 인프라 세팅 단계이며, 실제 플로팅 기능은 아직 구현되지 않았다.

## 부트스트랩

```bash
# 0. mise, uv, gh 설치(최초 1회)
curl https://mise.run | sh
curl -LsSf https://astral.sh/uv/install.sh | sh
# gh: https://cli.github.com/

# 1. Python 버전 설치 + 의존성 동기화 + git hook 등록
mise install
mise run install

# 2. 동작 확인
mise run check
```

## 개발 워크플로

```
/start-issue "기능 설명"   # GitHub 이슈 생성 + worktree branch 분기
    ↓
코드 작업
    ↓
/commit                    # 의미 단위로 분리해 한국어 conventional commit
    ↓
/review                    # 4개 sub-agent 병렬 리뷰
    ↓
/open-pr                   # PR 생성 (Closes #N 자동 포함)
    ↓
머지 전: CI green + /review Approve 둘 다 필수
    ↓
머지 후: /worktree-clean   # 완료된 worktree/브랜치 정리
```

자세한 규칙: [`.claude/rules/branch.md`](.claude/rules/branch.md)

## 커밋 규칙

- **형식**: `<type>(<scope>): <한국어 설명>`
- **type**: `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `style` / `perf`
- **원칙**: 한 commit = 한 의도. 리팩터링과 기능 추가를 섞지 않는다.

예시:
```
feat(theme): 시드 컬러 기반 파라메트릭 팔레트 추가
fix(svg): 그룹 막대 라벨이 겹치는 문제 수정
refactor(core): 렌더러를 mark 프리미티브 기반으로 분리
```

## Python 도구 체인

```bash
mise install                # Python 버전 설치
mise run install             # uv sync + prek install
mise run lint                # prek run --all-files
mise run test                # pytest
mise run check                # lint + test (CI와 동일)

uv add <package>             # 의존성 추가
uv add --dev <package>       # dev 의존성 추가
uv sync                      # lock 파일 기준으로 환경 동기화
uv run <command>             # 가상 환경 안에서 명령 실행
uv run ruff check . --fix    # lint + 자동 수정
uv run ruff format .         # 포매팅
uv run pytest                # 테스트 실행
```

## 로컬 설정 (선택)

개인 override 가 필요하면 `.claude/settings.local.json` 을 생성한다 (gitignore 됨).
예시는 `.claude/settings.local.json.example` 참고. 환경변수/비밀값 로컬 override 는
`mise.local.toml`(gitignore 됨)의 `[env]` 테이블에 추가한다.

## 사전 조건

- [mise](https://mise.jdx.dev/) 설치: `curl https://mise.run | sh`
- [uv](https://docs.astral.sh/uv/) 설치: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [gh](https://cli.github.com/) 설치 + 인증: `gh auth login`
- Claude Code CLI 설치

## 라이선스

MIT License — [`LICENSE`](LICENSE) 참고.
