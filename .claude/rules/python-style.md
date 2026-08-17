# Python 스타일 규칙

## 의존성 관리 (uv)

```bash
uv add <package>              # 의존성 추가
uv add --dev <package>        # dev 의존성 추가
uv remove <package>           # 의존성 제거
uv sync                       # lock 파일 기준 환경 동기화
uv sync --no-dev              # dev 제외 동기화
uv lock --upgrade             # lock 전체 업그레이드
uv lock --upgrade-package <p> # 특정 패키지만 업그레이드
uv run <command>              # 가상 환경 안에서 실행
uvx <tool>                    # 임시 도구 실행 (설치 없이)
```

`uv.lock` 과 `.python-version` 은 반드시 커밋한다.

## Python 버전 / 환경변수 관리 (mise)

Python 인터프리터 버전 고정과 리포 로컬 환경변수는 `mise.toml`이 관리한다.

```bash
mise install       # mise.toml 에 고정된 Python 버전 설치
mise run install   # uv sync + prek install (git hook 등록)까지 한 번에
mise run lint      # prek run --all-files
mise run test      # pytest
mise run check     # lint + test (CI 가 실행하는 것과 동일)
```

로컬 전용 환경변수/override 는 `mise.local.toml`(gitignore 대상)의 `[env]` 테이블에 추가한다.

## ruff 설정

- **line-length**: 127
- **target-version**: py312
- **src 경로**: `src`, `tests`

### 활성 룰셋

| 코드 | 의미 |
|---|---|
| E, F | pycodestyle errors + pyflakes (기본) |
| I | isort (import 정렬) |
| UP | pyupgrade (구버전 문법 현대화) |
| B | flake8-bugbear (잠재적 버그) |
| SIM | flake8-simplify |
| RUF | ruff 자체 룰 |
| N | pep8-naming |
| C4 | flake8-comprehensions |
| PTH | pathlib 사용 권장 |

`E501` (line too long) 은 ruff format 이 처리하므로 lint 에서 무시.

### 일상 명령

```bash
uv run ruff check . --fix        # lint + 자동 수정
uv run ruff format .              # 포매팅
uv run ruff check . --fix && uv run ruff format .  # 일반적인 로컬 실행
```

## prek (lint/format 훅 러너)

`pre-commit`의 Rust 드롭인 대체. `.pre-commit-config.yaml` 대신 네이티브 `prek.toml`을 사용한다.

```bash
uv run prek install                          # git hook 등록
uv run prek install --hook-type commit-msg  # commit-msg hook
uv run prek run --all-files                  # 전체 파일 실행
uv run prek autoupdate                       # hook 버전 업데이트
```

`mise run lint`가 `uv run prek run --all-files`를 그대로 감싼 것이므로 둘 중 편한 쪽을 쓰면 된다.

포함된 hook (`prek.toml`):
- `ruff` (lint + --fix), `ruff-format` (포매팅)
- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml/toml/json`
- `check-merge-conflict`, `check-added-large-files`, `mixed-line-ending`, `detect-private-key`
- `uv-lock` (uv.lock 동기화 강제)

## 코딩 규칙

- **Type hint**: 모든 함수 인자/반환값에 필수
- **Docstring**: Google 스타일, 필요할 때만 (자명한 함수는 생략)
- **import 순서**: ruff I 가 자동 정렬 (stdlib → third-party → local)
- **문자열**: 더블 쿼트 (`"`) 기본
- **`__init__.py`**: F401 (unused import) 무시 — re-export 허용
