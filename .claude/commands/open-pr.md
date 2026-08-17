---
description: 현재 브랜치를 push 하고 GitHub PR 을 생성합니다
allowed-tools:
  - Bash
  - Read
---

다음 단계를 순서대로 실행하라:

## 사전 확인

1. `git status` 로 미커밋 변경사항 확인
   - 있으면 사용자에게 `/commit` 먼저 실행하도록 안내
2. `git branch --show-current` 로 현재 브랜치 확인
   - `main` 또는 `master` 이면 PR 생성 불가, 중단

## 이슈 번호 파악

3. 브랜치명에서 이슈 번호 추출: `feature/42` → `42`
   - 추출 실패 시 사용자에게 직접 입력 요청

## Push

4. 원격 브랜치에 push:
   ```bash
   git push -u origin HEAD
   ```

## PR 정보 구성

5. 다음 정보를 수집한다:
   - 이슈 정보: `gh issue view <n> --json title,body`
   - 커밋 목록: `git log --oneline origin/main..HEAD`
   - diff 요약: `git diff --stat origin/main..HEAD`

6. `.github/PULL_REQUEST_TEMPLATE.md` 를 읽어 PR body 초안을 구성:
   - **변경 요약**: commit 목록에서 자동 생성
   - **관련 이슈**: `Closes #<n>` (필수)
   - **변경 유형**: 커밋 type 에서 자동 체크
   - **테스트 방법**: 이슈/diff 에서 유추
   - **체크리스트**: 기본값

7. PR 제목 = 이슈 제목 또는 주요 commit 의 subject

8. 사용자에게 PR 제목과 body 초안을 보여주고 확인 (또는 수정)을 받는다

## PR 생성

9. 확인 후 PR 생성:
   ```bash
   gh pr create \
     --title "<PR 제목>" \
     --body "<PR body>" \
     --base main
   ```

10. 생성된 PR URL 을 사용자에게 안내한다

## 주의사항

- `gh pr create` 는 설정에서 `ask` 로 분류 → 실행 전 사용자 확인 필요
- PR 이 이미 존재하면 `gh pr view` 로 기존 PR URL 을 안내하고 중단
