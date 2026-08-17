---
description: 4개 sub-agent 를 병렬 실행해 PR 을 리뷰하고 통합 리포트를 생성합니다
allowed-tools:
  - Bash
  - Read
  - Task
argument-hint: [pr-number]
---

다음 단계를 순서대로 실행하라:

## 리뷰 대상 결정

1. `$ARGUMENTS` 에 PR 번호가 있으면 그 PR 을 리뷰
   ```bash
   gh pr view $ARGUMENTS --json number,title,body,url
   gh pr diff $ARGUMENTS
   ```

2. 없으면 현재 브랜치로 판단:
   - `gh pr list --head $(git branch --show-current) --json number,url` 로 PR 존재 확인
   - PR 이 있으면 그 PR 리뷰
   - PR 이 없으면 `git diff origin/main...HEAD` 로 현재 변경사항 리뷰

## 이슈 번호 파악

3. PR 번호 또는 브랜치명에서 이슈 번호 추출
   - `gh pr view {n} --json body` 에서 `Closes #\d+` 패턴 검색
   - 또는 브랜치명 `feature/<n>` 에서 추출

## 컨텍스트 수집

4. 리뷰에 필요한 컨텍스트를 수집한다:
   - diff 내용
   - 이슈 정보 (이슈 번호가 있을 경우)
   - 변경된 파일 목록
   - commit 히스토리

## 4 Agent 병렬 리뷰

5. **Task 도구**를 사용해 4개 sub-agent 를 병렬로 실행한다:

   각 Task 에 다음을 포함해 전달:
   - 리뷰 대상 (diff 내용 또는 PR 번호)
   - 이슈 번호 (있을 경우)
   - 각 에이전트의 역할 및 출력 포맷

   병렬 실행:
   - Task 1: `code-quality-reviewer` — 코드 품질, 가독성, commit 단위
   - Task 2: `issue-goal-reviewer` — Acceptance Criteria 달성, scope creep
   - Task 3: `security-reviewer` — OWASP, secret, 인증/인가
   - Task 4: `test-coverage-reviewer` — behavior coverage, edge case

6. 모든 Task 가 완료될 때까지 대기

## 통합 리포트 생성

7. 4개 결과를 다음 형식으로 통합한다:

```markdown
# PR 리뷰 통합 리포트

**PR**: #N — {제목}
**이슈**: #M — {이슈 제목}
**리뷰 시각**: {datetime}

---

## 요약

| 리뷰어 | Critical | Important | Suggestions | 판정 |
|---|---|---|---|---|
| Code Quality | N | N | N | ✅/❌ |
| Issue Goal | N | N | N | ✅/❌ |
| Security | N | N | N | ✅/❌ |
| Test Coverage | N | N | N | ✅/❌ |

**최종 판정**: ✅ Approve / ❌ Request Changes

---

## Code Quality 리뷰
{code-quality-reviewer 결과}

---

## Issue Goal 리뷰
{issue-goal-reviewer 결과}

---

## Security 리뷰
{security-reviewer 결과}

---

## Test Coverage 리뷰
{test-coverage-reviewer 결과}
```

## PR 코멘트 게시 (선택)

8. PR 번호가 있고 리뷰 결과에 Critical 이슈가 있으면, 사용자에게 PR 코멘트 게시 여부를 묻는다:
   ```bash
   gh pr comment {n} --body "..."
   ```

## 주의사항

- Task 병렬 실행이 불가능한 환경이면 순차 실행으로 대체
- 각 agent 결과에 에러가 있으면 "리뷰 실패" 로 표시하고 계속 진행
- diff 가 매우 크면 (1000줄 이상) 사용자에게 경고하고 계속 진행할지 확인
