# MVP 기능 범위 제안

`10-feature-matrix.md`의 MVP 판정 열을 근거로 한 최종 스코프. "왜 이 결정인가"만 요약하고 세부 근거는 각 문서를 참조한다.

## 핵심 원칙 1 — "수정이 쉽다"의 두 가지 의미

패키지의 핵심 가치는 **markdown 문서에 박아넣을, 심미성 있고 수정이 쉬운 정적 SVG**다. "수정이 쉽다"는 두 의미 모두를 동등하게 중요하게 다룬다.

1. **코드로 다시 만들기 쉬움** — 데이터나 옵션을 바꿔 `render()`를 다시 호출하면 끝. pygal이 이미 잘하는 방식이며(`01-pygal.md` A3), `11-api-syntax.md`의 seaborn류 함수형 문법 채택으로 계승한다.
2. **SVG 소스 자체를 직접 편집하기 쉬움** — 생성된 XML이 사람이 읽을 수 있는 구조여야 한다: 들여쓰기된 pretty-print, 의미 있는 `class`/`id`(무작위 해시가 아닌 `bar-series-1` 같은 이름), 값이 계산식이 아니라 리터럴로 박혀 있음(예: `translate(120.5, 30)`처럼 최종 좌표가 그대로 보임), 스타일이 CSS 클래스로 분리되어 있어(`12-aesthetics.md` §4) 색 하나 바꾸려고 여러 곳을 고칠 필요가 없음. 이 요구사항은 렌더러 구현 시 "출력 XML의 가독성"을 별도 품질 기준으로 관리해야 함을 뜻한다 — 압축/minify 옵션은 기본값이 아니라 opt-in이어야 한다.

## 핵심 원칙 2 — v1.0(markdown-static) / v2.0(html-progressive) 단계 구분

markdown에 `<img src="chart.svg">`로 삽입된 SVG는 JS가 실행되지 않는다(`00-overview.md` 핵심 발견 4). 따라서 스코프를 두 단계로 명확히 나눈다.

- **v1.0(이 문서의 스코프 전부)**: 순수 정적 SVG. JS 없음. markdown 임베드가 1차 타깃.
- **v2.0(스코프 아님, `18-progressive-js-roadmap.md`에 원칙만 기록)**: 같은 SVG 파일을 standalone으로 열었을 때만 켜지는 가벼운 hover/연동. v1.0 산출물이 이 확장을 무리 없이 받아들이도록 `data-index` 속성, 예약된 CSS 상태 클래스 등을 v1.0부터 심어둔다(`18-progressive-js-roadmap.md` "v1.0에서 지금 심어둘 것" 참고) — 이것만이 v1.0 구현에 실제로 영향을 준다.

## 반드시 포함 (v0 / MVP)

### 차트 타입
선(line), 산점도(scatter, hue/size 매핑 포함), 막대(수직/수평, 그룹/누적), 히스토그램(자동 binning), 영역 채움, 파이/도넛, 박스플롯, Facet grid(소형다중패널), 시간축 지원(별도 클래스가 아닌 스케일 옵션으로).

**근거**: `10-feature-matrix.md` A1에서 수요 신호=높음 AND SVG 적합도=유리인 항목. pygal(24종)·matplotlib plot_types(27종, 3D 제외)·seaborn(22개 함수) 세 인벤토리 모두에서 공통으로 상위권.

### 데이터 & 문법
`data=DataFrame, x=, y=, hue=` 시그니처(seaborn 함수형 문법, `11-api-syntax.md`의 권고안 B), long-form 입력, point-level metadata(pygal 선례).

### 테마 & 팔레트
style×context 분리 테마 시스템(전역 mutate 없이), CSS 클래스 기반 재테마 가능한 SVG 출력(`12-aesthetics.md` §1, §4), 파라메트릭 테마(시드컬러→팔레트), 팔레트 미니 언어(seaborn 문법 이식), 정성+시퀀셜 팔레트, **기본값이 색맹 안전한 팔레트**.

### 접근성
`role="img"`+`aria-label`, `<title>`+`<desc>` 기본 채우기 — 구현 비용이 낮고 세 라이브러리 모두의 공백이므로 처음부터 포함.

### 출력
SVG 문자열/파일, PNG(optional dependency로 위임), Jupyter 자동 표시(`_repr_svg_`), CSS `:hover`+`<title>` 기반 자체 툴팁.

### 통계(최소)
보간(pygal 5종 계승), 히스토그램 binning(numpy 위임), Box plot 통계.

### 다중 차트 레이아웃 (Bokeh 참고, `16-layout-vocabulary.md`)
1D 나열(`row`/`column`, spacing, 빈칸), 2D 그리드(span 지원, CSS Grid 위임), 도판 공통 캡션, `fixed`/`responsive` 2종 크기 조정, Tabs 대체(펼쳐서 소제목 나열).

### 정적 hover 대안 (Bokeh 참고, `17-static-hover-alternative.md`)
`label_spec`(필드+포맷 단일 스펙) + numeral/datetime/printf 3종 포맷 스킴, 각주형 데이터 테이블 렌더러, `<title>`/`<desc>`(접근성 목적, hover 대체 아님을 문서에 명시).

**근거**: 이 항목들은 `10-feature-matrix.md`에서 "필수" 판정을 받은 것들이며, 공통적으로 (a) 세 라이브러리 조사에서 수요 신호가 높거나, (b) SVG 고유의 저비용 차별화 지점(`13-svg-opportunity.md`), (c) Bokeh 조사에서 확인된 "markdown에서도 유효한" 레이아웃/정보 밀도 어휘(`16`/`17`)이다.

## 2차 (v1, MVP 이후)

바이올린플롯, KDE, ECDF, strip/swarm plot, point plot, 회귀선+신뢰대역(선형만), 히트맵(시퀀셜/다이버징 팔레트 필요), 레이더, 게이지, 트리맵, despine류 유틸, 자동 legend 배치(근사 폭 테이블 기반), 부트스트랩 errorbar, size=/style= 시맨틱 매핑, wide-form DataFrame 자동 인식, named color 사전, 명도 대비(WCAG) 검증, `prefers-reduced-motion` 대응, CJK 폰트 스택 포함, 그룹 테두리(GroupBox 대응), 극값/이상치 자동 선별 hover 패널, 인라인 라벨 겹침 회피 알고리즘, `<details>` 접기/펼치기 markdown 조각 생성(GitHub 한정), 축/색상 자동 정렬.

**근거**: 수요는 있으나 구현 비용이 v0 항목보다 크거나(통계 계산, 텍스트 측정 근사), 니치한 사용자층(게이지/트리맵은 pygal 고유 수요) — v0 안정화 후 개발.

## 제외 (당분간 안 함)

등고선(contour류), hexbin, 3D, mathtext/수식 렌더링, 클러스터맵(덴드로그램+heatmap), pair/joint grid(복합 레이아웃 엔진 필요), logistic/robust/lowess 회귀(statsmodels 의존), letter-values(boxenplot), 애니메이션(1차), 범용 플러그인 아키텍처, 퍼널/피라미드(pygal 고유 니치), Tabs류 탭 전환 UI(markdown에서 재현 불가), 내부 스크롤 컨테이너(ScrollBox 대응), `{safe}`류 원시 HTML 삽입(보안), standalone-only 실시간 hover/연동 전체(v2.0으로 이연, `18-progressive-js-roadmap.md`), Bokeh 서버류 Python 백엔드 아키텍처.

**근거**: `13-svg-opportunity.md`의 "SVG여서 어려운 것"에 해당하거나(등고선/hexbin/3D), 구현 비용 대비 수요가 낮은 니치 기능. 이 항목들을 v0/v1 스코프에서 명시적으로 제외함으로써 "pygal 대비 3배 범위 확장"(matplotlib 전체 커버리지 시도) 함정을 피한다.

## 최상위 아키텍처 결정 (스코프보다 먼저 확정해야 하는 것)

1. **CSS 클래스 기반 재테마 vs geometry dump** → 전자 채택(`12-aesthetics.md` §4). 이후 모든 렌더링 코드가 이 결정에 종속되므로 v0 착수 전 확정.
2. **API 문법: seaborn 함수형(B) 우선, pyplot 명령형은 이스케이프 해치, 선언형 객체는 v2+** (`11-api-syntax.md`).
3. **텍스트 bbox 측정 문제에 대한 입장**: v0는 측정 없이 동작하는 레이아웃(상대크기, 고정 프리셋, 회전)으로 시작하고, 정밀 자동 여백 조정은 v1에서 근사 폭 테이블로 개선(`12-aesthetics.md` §3, `13-svg-opportunity.md`).
4. **v1.0/v2.0 경계**: JS는 v1.0에 절대 포함하지 않는다. v1.0이 만드는 SVG의 마크업 관례(`data-index`, 예약된 상태 클래스)만 v2.0을 염두에 두고 정한다 — 이 경계가 흐려지면 "정적 패키지"라는 정체성이 무너진다(`18-progressive-js-roadmap.md`).
