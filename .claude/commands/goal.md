---
description: 지정된 마일스톤(또는 전체 열린 이슈)을 순회하며 이슈별로 start-issue→구현→commit→review→open-pr→(게이트 통과 시)자동 머지까지 진행합니다
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Task
argument-hint: [milestone-name]
---

## 대상 이슈 결정

1. `$ARGUMENTS`가 있으면 `gh issue list --milestone "$ARGUMENTS" --state open --json number,title,body`
2. 없으면 전체 `gh issue list --state open --json number,title,body`
3. 이슈 번호 오름차순(= 대략 의존성 순서, 마일스톤 내 이슈는 계획에 적힌 순서로 번호를 매겨 생성함)으로 정렬

## 이슈별 반복 (순차 실행 — 병렬 금지)

후속 이슈가 앞 이슈의 병합 결과(이미 채워진 모듈)에 의존하는 경우가 많으므로 반드시 순차로 처리한다. 각 이슈에 대해:

1. worktree 생성 (`.claude/rules/branch.md`의 브랜치 규칙: `feature/{n}`, `../svgplot-worktrees/feature/{n}`, 분기점은 `origin/main`)
2. 이슈 body의 Acceptance Criteria를 `Edit`/`Write`로 직접 구현(sub-agent에 위임하지 않는다) — 필요한 테스트도 함께 작성
3. `.claude/rules/branch.md`의 **Commit 실행 절차**를 따라 의미 단위로 커밋
4. `gh pr create`로 PR 생성 (`Closes #n` 필수, `.github/PULL_REQUEST_TEMPLATE.md` 형식)
5. `.claude/rules/review-policy.md`에 따라 4개 sub-agent(code-quality/issue-goal/security/test-coverage)를 병렬 실행해 리뷰
   - Request Changes → Critical 항목 수정 → 재리뷰. 최대 3회 반복해도 Approve가 안 나오면 **중단하고 사용자에게 보고**(무한 루프 방지)
6. CI 완료 대기(`gh pr checks --watch`)
7. CI green **AND** review Approve **둘 다** 만족하면 `gh pr merge --squash --delete-branch`로 자동 머지
   - 하나라도 미충족이면 머지하지 않고 다음 이슈로 넘어가되 종료 보고에 남긴다
8. worktree 정리(`git worktree remove`, `git branch -d`)
9. 다음 이슈로

## 종료 보고

이슈별 결과(머지됨/PR만 열림/실패)를 표로 정리해 보고한다.

## 주의사항

- Acceptance Criteria가 모호하거나 기존 코드와 충돌하면 즉시 중단하고 사용자에게 확인받는다.
- CI+review 게이트를 절대 우회하지 않는다(설정 실수로도) — `.claude/rules/branch.md`의 머지 조건이 최종 근거.
- `main`에 직접 커밋하지 않는다 — 브랜치 보호(`enforce_admins`)가 실제로 이를 막는다.
