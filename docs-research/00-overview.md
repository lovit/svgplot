# 조사 개요 — SVG 기반 Python 차트 패키지를 위한 pygal/matplotlib/seaborn/Bokeh 기능 범위 조사

## 목적

새로운 SVG 기반 Python 차트/그래프 패키지를 설계하기 전, 다음 네 질문에 답하기 위한 조사다.

1. pygal이 이미 커버하는 SVG 차트 기능 범위는 어디까지이고, 무엇이 비어 있는가?
2. matplotlib pyplot 명령형 문법과 seaborn 고수준 함수 문법 중 무엇을 채택할 것인가?
3. "심미성"(테마·팔레트·타이포/레이아웃·SVG 고유 표현·접근성)을 구체적으로 어떻게 구현할 것인가?
4. Bokeh가 강점으로 가진 hover와 다중 차트 연동을, markdown 임베드라는 제약 안에서 무엇으로 대체할 것인가?

핵심 관점: **seaborn은 matplotlib을 편하게 쓰기 위한 래퍼이므로, seaborn이 감싸서 제공하는 기능 목록 자체가 "실사용자가 반복적으로 필요로 한 것"의 증거다.** 이 증거를 SVG로 구현하는 방향을 찾는 것이 조사의 목표다.

## 패키지의 핵심 가치와 단계 구분

조사 도중 패키지의 1차 목표가 명확해졌다: **markdown 문서에 박아넣을, 심미성 있고 수정이 쉬운 정적 SVG 그림**을 Python으로 만드는 것(v1.0). "수정이 쉽다"는 두 의미 모두를 뜻한다 — (a) Python 코드로 데이터/옵션을 바꿔 다시 렌더링하기 쉬움, (b) 생성된 SVG 소스 자체를 텍스트 에디터로 열어 직접 고치기 쉬움. 이후 SVG가 standalone으로(브라우저 탭에서 직접) 열렸을 때만 켜지는 가벼운 인터랙션을 v2.0으로 확장한다 — `14-scope-recommendation.md`, `18-progressive-js-roadmap.md` 참고.

**결정적 제약**: GitHub 등 markdown 렌더러에 `<img src="chart.svg">`로 삽입된 SVG는 브라우저가 이미지로 취급해 `<script>`가 실행되지 않고 `:hover`도 대부분 동작하지 않는다. 즉 v1.0에서는 JS 기반 인터랙션이 원천적으로 무의미하며, 이것이 Bokeh 조사의 초점을 "복제"가 아니라 "정적 대안 찾기"로 재설정했다.

## 방법

`references/{pygal,matplotlib,seaborn}`에 clone된 3개 레포를 대상으로, 9개 축(A1~A9)에 대해 12개 조사 에이전트를 병렬 실행했다. 각 에이전트는 공식 문서를 우선하고, 소스는 시그니처·docstring·리터럴 데이터 수준까지만 읽었다(함수 본문 로직·렌더링 수학·테스트 코드는 조사 범위 밖). 상세 실행 계획은 세션의 plan 파일을 참고.

## 조사 축

| 축 | 이름 | 답한 질문 |
|---|---|---|
| A1 | 차트 타입 인벤토리 | 무엇을 그릴 수 있나 |
| A2 | 데이터 입력 & 시맨틱 매핑 | 어떤 데이터 형태를 받고, hue/size 같은 채널 매핑이 있나 |
| A3 | API 문법 | 상태형/객체형/선언형, 커스터마이징 진입 경로 |
| A4 | 스타일·테마 시스템 | 옵션 체계, 테마 정의·상속·스코프 |
| A5 | 컬러 팔레트 엔진 | 팔레트 종류, 생성 알고리즘, 접근성 |
| A6 | 타이포그래피 & 레이아웃 | 폰트 제어, 자동 배치, 라벨 충돌 회피 |
| A7 | 통계 변환 | binning/KDE/회귀/집계를 라이브러리가 대신 계산하나 |
| A8 | 출력·인터랙션·확장성 | 출력 포맷, 툴팁/애니메이션, 플러그인 |
| A9 | 접근성 | 색맹 안전성, ARIA, 명도 대비 (사용자 승인으로 추가) |

## 레포 요약

| | pygal | matplotlib | seaborn | Bokeh |
|---|---|---|---|---|
| 버전 / 규모 | 3.1.3 / 7.9k LOC | ~3.11 / 143k LOC | 0.14.0.dev / 29k LOC | 4.0.0-dev / Py 82.6k + TS 93.7k LOC |
| 활성도 | 낮음 | 매우 높음 | 높음 | 매우 높음 |
| 차트 타입 | 24 클래스 | Axes 69메서드/plot_types 27종(3D 제외) | 함수 22 + Mark 13 | "차트 타입" 없음 — glyph 43개 조합 |
| 옵션 체계 | config Key 83개 | rcParams 344개 | mpl rcParams 위임 + style×context | Document 단위 테마(6종) |
| 테마 | 16 built-in + 5 parametric | 31 `.mplstyle` | 5 style × 4 context | 6종, 차트별 아닌 Document 단위 |
| SVG | `svg.py`, CSS class 기반(재테마 가능) | `backend_svg.py`, geometry dump(재테마 불가) | 없음(mpl 위임) | **Python이 SVG를 만들지 않음** — Canvas/WebGL, `export_svg`는 헤드리스 브라우저 스크린샷 |
| 핵심 성격 | SVG 렌더러(통계 계산 없음) | 범용 플로팅 엔진(하위 API) | 통계 시각화 편의 레이어(상위 API) | 브라우저 렌더링 + 실시간 연동 프레임워크 |

## 핵심 발견 (5가지)

1. **아키텍처 분기점**: pygal은 SVG를 CSS 클래스 기반으로 산출해 렌더 후에도 재테마 가능하지만, matplotlib SVG 백엔드는 모든 스타일을 요소마다 인라인 하드코딩하는 geometry dump 방식이다. 이 선택이 프로젝트 전체 아키텍처를 결정한다 → `12-aesthetics.md` §4, `13-svg-opportunity.md`.
2. **최대 기술 리스크**: matplotlib의 모든 자동 레이아웃(legend 자동배치, 여백 자동조정)은 실제 폰트 렌더러의 텍스트 bbox 측정에 의존한다. 순수 SVG 문자열 생성기에는 이 렌더러가 없다 → `12-aesthetics.md` §3, `13-svg-opportunity.md`.
3. **수요 신호와 문법 결정**: seaborn이 존재하는 이유(= matplotlib에 없는 tidy-data 시맨틱 매핑, 자동 집계, facet)가 그대로 새 패키지의 v0 기능 목록이 되고, 문법도 seaborn의 `data=, x=, y=, hue=` 함수형이 SVG의 무상태 문서 산출 모델과 가장 잘 맞는다 → `11-api-syntax.md`.
4. **markdown 임베드는 JS를 죽인다**: `<img src="chart.svg">`는 이미지 컨텍스트로 취급되어 `<script>`/`:hover`가 대부분 작동하지 않는다. 이 사실이 Bokeh의 hover·연동 기능을 "복제 대상"에서 "정적 재해석 대상"으로 바꿨다 → `16-layout-vocabulary.md`, `17-static-hover-alternative.md`.
5. **Bokeh는 SVG 렌더러가 아니다**: Python이 JSON 모델을 만들고 브라우저가 Canvas/WebGL로 그린다. 가져올 것은 렌더링 아키텍처가 아니라 API 설계 어휘(레이아웃 정밀도 단계, tooltip 필드 미니 언어) → `04-bokeh.md`.

## 읽는 순서

1. `01-pygal.md` / `02-matplotlib.md` / `03-seaborn.md` / `04-bokeh.md` — 라이브러리별 원자료
2. `10-feature-matrix.md` — 축별 기능 대조표 + 갭 분석 (가장 먼저 훑어볼 요약표)
3. `11-api-syntax.md` — API 문법 결정 (권고안 1개)
4. `12-aesthetics.md` — 심미성 4갈래 구체 설계
5. `13-svg-opportunity.md` — SVG 기회/위험
6. `16-layout-vocabulary.md` — 다중 차트 레이아웃 어휘 (v1.0)
7. `17-static-hover-alternative.md` — 정적 hover 대안 (v1.0)
8. `18-progressive-js-roadmap.md` — v2.0 진행형 개선 원칙 (v1.0 구현 대상 아님)
9. `14-scope-recommendation.md` — MVP 스코프 최종 제안

## 비목표

D3/Vega-Lite/Plotly는 미조사(Bokeh는 사용자 요청으로 예외적으로 조사). 내부 알고리즘·렌더링 수학 미조사(Bokeh의 `bokehjs/` TypeScript 런타임도 동일하게 제외). 성능 벤치마크 없음. 아키텍처(모듈/클래스 설계)는 이 조사의 다음 단계.
