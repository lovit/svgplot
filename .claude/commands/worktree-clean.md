---
description: 머지 완료된 worktree 와 브랜치를 정리합니다
allowed-tools:
  - Bash
  - Read
---

다음 단계를 순서대로 실행하라:

## 상태 파악

1. 현재 worktree 목록 확인:
   ```bash
   git worktree list
   ```

2. 머지 완료된 PR 목록 확인:
   ```bash
   gh pr list --state merged --author @me --json number,headRefName,mergedAt,url
   ```

## 정리 대상 찾기

3. worktree 브랜치 중 머지된 PR 과 매칭되는 것을 찾는다
   - 예: worktree `feature/42` ↔ merged PR `#42`

4. 정리 대상 목록을 사용자에게 보여주고 확인 받기:
   ```
   정리할 항목:
   - worktree: ../claude-code-base-worktrees/feature/42  (PR #42, merged: 2024-01-15)
   - worktree: ../claude-code-base-worktrees/feature/38  (PR #38, merged: 2024-01-10)

   계속할까요?
   ```

## 정리 실행

5. 확인 후 각 항목 정리:
   ```bash
   # worktree 제거
   git worktree remove ../claude-code-base-worktrees/feature/<n>

   # 로컬 브랜치 제거
   git branch -d feature/<n>
   ```

6. 정리 후 남은 worktree 목록 표시

## 주의사항

- **현재 사용 중인 worktree 는 제거하지 않는다**
- `git worktree remove` 는 worktree 안에 미커밋 변경이 있으면 실패
  → 실패 시 사용자에게 알리고 수동 처리 안내
- 로컬 브랜치 삭제 시 `-d` (안전) 사용, `-D` (강제) 는 사용자가 명시 요청할 때만
- PR 없이 생성된 worktree (이슈가 닫힌 경우 등) 는 별도로 나열해 사용자가 직접 판단하도록 안내
