---
description: GitHub 이슈를 생성하고 worktree branch 를 분기합니다
allowed-tools:
  - Bash
  - Read
argument-hint: <이슈 제목>
---

다음 단계를 순서대로 실행하라:

## 사전 확인

1. `gh auth status` 로 GitHub 인증 상태 확인
   - 인증이 안 됐으면 사용자에게 `gh auth login` 안내 후 중단
2. `git remote get-url origin` 으로 원격 레포 URL 확인

## 이슈 생성

3. 다음 내용으로 GitHub 이슈를 생성한다:
   - **제목**: `$ARGUMENTS`
   - **Body**: ISSUE_TEMPLATE/feature.md 형식을 따르되, 제목에서 유추한 내용으로 초안을 채워 사용자에게 확인받는다
   - **Label**: 자동 감지 (feat → enhancement, fix → bug)

   ```bash
   gh issue create --title "$ARGUMENTS" --body "..." --label "enhancement"
   ```

4. 생성된 이슈 URL 과 번호를 파싱한다 (예: `#42`)

## Worktree 생성

5. 최신 main 을 가져온다:
   ```bash
   git fetch origin main
   ```

6. sibling 디렉토리에 worktree 를 생성한다:
   ```bash
   git worktree add ../<repo-name>-worktrees/feature/<issue-number> \
     -b feature/<issue-number> origin/main
   ```
   `<repo-name>` 은 `basename $(git remote get-url origin) .git` 으로 추출

7. 생성된 worktree 경로를 사용자에게 알린다:
   ```
   ✅ 이슈 #<n> 생성됨: <issue-url>
   ✅ Worktree 생성됨: ../<repo>-worktrees/feature/<n>

   다음 명령으로 이동하세요:
   cd ../<repo>-worktrees/feature/<n>
   ```

8. 사용자에게 새 worktree 에서 Claude Code 세션을 시작하도록 안내한다.

## 주의사항

- `$ARGUMENTS` 가 비어 있으면 이슈 제목을 사용자에게 물어본다
- worktree 디렉토리가 이미 존재하면 사용자에게 알리고 기존 worktree 사용 여부 확인
- 브랜치 `feature/<n>` 이 이미 존재하면 `origin/main` 대신 해당 브랜치에서 분기
