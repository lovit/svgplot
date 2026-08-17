---
description: main 브랜치를 최신화하고 현재 브랜치를 rebase 합니다
allowed-tools:
  - Bash
  - Read
---

다음 단계를 순서대로 실행하라:

## 현재 상태 확인

1. 미커밋 변경사항 확인:
   ```bash
   git status
   ```
   - 있으면 사용자에게 먼저 `/commit` 또는 `git stash` 하도록 안내

2. 현재 브랜치 확인:
   ```bash
   git branch --show-current
   ```

## main 업데이트

3. 원격 변경사항 가져오기:
   ```bash
   git fetch origin main
   ```

4. main 과 현재 브랜치의 차이 확인:
   ```bash
   git log --oneline HEAD..origin/main    # main 에만 있는 commit
   git log --oneline origin/main..HEAD    # 현재 브랜치에만 있는 commit
   ```

## 브랜치별 처리

### main 브랜치인 경우
5. fast-forward merge:
   ```bash
   git merge --ff-only origin/main
   ```

### feature 브랜치인 경우
5. 사용자에게 선택지 제시:
   - **Rebase** (권장): commit 히스토리가 깔끔해짐
   - **Merge**: 머지 commit 이 생기지만 안전

6. Rebase 선택 시:
   ```bash
   git rebase origin/main
   ```
   - 충돌 발생 시 충돌 파일을 알리고 사용자가 수동으로 해결하도록 안내
   - 해결 후: `git rebase --continue`
   - 취소: `git rebase --abort`

7. 완료 후 상태 요약:
   ```
   ✅ origin/main 동기화 완료
   현재 브랜치: feature/42
   main 보다 N commit 앞서 있음
   ```

## 주의사항

- force push 없이는 rebase 후 원격 push 가 거부될 수 있음
  → rebase 후 push 가 필요하면 사용자에게 명시적으로 알리고 확인 받기
- 공유 브랜치 (여러 사람이 작업 중) 는 rebase 대신 merge 권장
