# 리뷰 정책

## 리뷰 실행 흐름

`/review [pr-number]` 호출 시:

1. PR 번호가 있으면 `gh pr view {n}` 과 `gh pr diff {n}` 을 가져옴
2. 없으면 현재 브랜치의 `git diff origin/main...HEAD` 사용
3. **4개 sub-agent 를 병렬로 실행** (Task 도구 활용)
4. 각 결과를 수집해 통합 리포트 생성
5. PR 번호가 있으면 `gh pr comment {n}` 으로 게시 옵션 제시

## 리뷰어 4종

| Agent | 모델 | 담당 |
|---|---|---|
| `code-quality-reviewer` | Sonnet | 가독성, 중복, 네이밍, 타입 힌트, PEP 준수, commit 단위 분리 검증 |
| `issue-goal-reviewer` | Sonnet | Acceptance Criteria 달성 여부, scope creep 감지 |
| `security-reviewer` | Opus | OWASP, secret 노출, 인증/인가, 입력 검증, 의존성 취약점 |
| `test-coverage-reviewer` | Sonnet | behavior coverage, edge case 누락, test 품질 |

## 공통 출력 포맷

각 리뷰어는 다음 형식으로 보고한다:

```markdown
## [에이전트 이름] 리뷰

### Critical (머지 전 필수 수정)
- ...

### Important (수정 권장)
- ...

### Suggestions (선택적 개선)
- ...

### Strengths (잘된 점)
- ...
```

각 항목 형식:
```
**파일**: path/to/file.py:123
**이슈**: 무엇이 문제인지
**이유**: 왜 문제인지 (영향)
**제안**: 어떻게 수정할지
```

## 판정 기준

- **Approve**: Critical 이슈 없음, 커버리지 기준 충족, 보안 이슈 없음
- **Request Changes**: Critical 이슈 1건 이상, Acceptance Criteria 미달, 보안 취약점 발견

## 리뷰어별 특이사항

### code-quality-reviewer
- CLAUDE.md 와 `.claude/rules/python-style.md` 준수 여부 우선 확인
- PR 의 commit 단위가 의미별로 잘 분리되었는지도 검토
- False positive 보수적으로 유지 (확실한 것만 보고)

### issue-goal-reviewer
- 이슈의 Acceptance Criteria 를 하나씩 체크 (GitHub 이슈 body 에서 추출)
- 이슈에서 요구하지 않은 변경이 섞였는지 (scope creep) 감지

### security-reviewer
- Proactive 톤: "확실하지 않으면 보고"
- diff 뿐 아니라 변경된 파일의 **전체 컨텍스트** (caller, auth flow 등) 도 함께 읽음
- 새 의존성이 추가됐으면 CVE/known vulnerability 확인

### test-coverage-reviewer
- Line coverage 가 아닌 **behavior coverage** 관점
- 새 로직에 대한 edge case 최소 3가지 이상 제안
- Happy path 테스트만 있고 error path 테스트가 없으면 지적
