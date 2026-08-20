# 심미성 청사진 — 테마 · 팔레트 · 타이포/레이아웃 · SVG 고유 표현

`01`~`03`, `10`의 A4/A5/A6/A9 조사를 종합해 4갈래 각각의 구체 설계 방향을 제시한다.

## 1. 테마 / 스타일시트 시스템

**채택**: pygal의 "테마 객체 → CSS 클래스 주입" 모델을 골격으로, seaborn의 "style × context 분리"를 얹는다.

- 테마는 하나의 불변 `Theme` 객체(배경/전경/팔레트/폰트/가이드선/투명도를 포괄) — pygal `Style`(`01-pygal.md` A4) 그대로 계승.
- **style(외관: 배경·그리드·스파인)과 context(스케일: 폰트·선굵기 배율)를 별도 축으로 분리** — seaborn의 2단 스케일링(`scaling × font_scale`, `03-seaborn.md` A4)을 그대로 채택. 단, **전역 rcParams mutate는 하지 않는다** — 이것이 seaborn 대비 명확한 개선점이다. 모든 스타일/컨텍스트는 렌더 호출에 전달되는 순수 값이며, 프로세스 전역을 건드리지 않는다.
- 경험적 최소 테마 스키마는 matplotlib 조사(`02-matplotlib.md` A4)가 제공한 수치를 따른다 — 344개 rcParams 중 실제 테마 정체성을 만드는 건 ~25개(prop_cycle, 배경/전경색, 그리드 색/굵기, 눈금 색/크기/방향, 라벨 크기, 선굵기). **테마 스키마를 이 25개 내외로 제한**해 pygal(83 config)/matplotlib(344 rcParams)의 옵션 과잉을 피한다.
- 테마 적용은 **렌더 시점의 값 주입**(CSS 변수 또는 인라인 클래스)이며, matplotlib처럼 텍스트로 CSS를 재조합하는 Jinja 스텝(`01-pygal.md`가 지적한 pygal의 비효율)은 생략하고 Python에서 직접 SVG `<style>` 블록을 조립한다.
- 파라메트릭 테마(시드 컬러 1개 → 전체 팔레트, `01-pygal.md` A5)를 1급 기능으로 유지 — "브랜드 컬러 하나만 알면 되는" UX는 세 라이브러리 중 pygal만 가진 강점이다.

## 2. 컬러 팔레트 엔진

**채택**: seaborn의 팔레트 미니 언어를 그대로 이식하되 파서를 견고화한다.

- `color_palette()`가 지원하는 문법(`"ch:..."`, `"light:X"`, `"dark:X"`, `"blend:a,b"`, 명명된 팔레트, matplotlib colormap 이름)을 1:1 채택(`03-seaborn.md` A5). 단 seaborn은 `split(":")`/`startswith` 같은 임시방편 파서를 쓰므로, 신규 패키지는 명시적 grammar(정규식 또는 작은 파서 콤비네이터)로 재구현해 에러 메시지 품질을 높인다.
- 정성(qualitative) / 시퀀셜 / 다이버징 3종을 처음부터 별개 타입으로 분리 — pygal이 정성 팔레트만 갖고 시퀀셜/다이버징이 아예 없는 공백(`01-pygal.md` A5)을 메운다. `heatmap`류 차트(A1 매트릭스 계열)를 지원하려면 필수.
- `dark_palette`/`light_palette`의 "목표색과 동일 hue를 유지한 회색 앵커" 알고리즘(`03-seaborn.md` A5)을 시드 컬러 기반 시퀀셜 생성에 채택.
- **기본 팔레트를 색맹 안전(Okabe-Ito 계열)으로 설정한다** — matplotlib/seaborn 둘 다 색맹 안전 팔레트를 갖고 있지만 전부 옵트인이며 기본값은 아니다(`02`/`03`의 A9). 이것이 세 라이브러리 대비 가장 값싸고 뚜렷한 차별점이다.
- `"jet"` 같은 지각적으로 문제 있는 컬러맵을 기본 네임스페이스에서 아예 제외하거나 경고 없이 선택할 수 없게 한다 — seaborn의 `"jet" → ValueError("No.")`(`03-seaborn.md` A5) 원칙을 그대로 계승.
- 색 부족 시 순환 확장은 pygal처럼 명도(HSL)만 조정하지 말고 지각균등 공간(OKLCH 등)에서 수행해 구분성을 보장한다.

## 3. 타이포그래피 & 레이아웃

**가장 큰 리스크가 있는 영역** — `13-svg-opportunity.md`의 SVG-hazard와 직결되므로 여기서 설계 원칙만 못박는다.

- 요소별(축/타이틀/범례/툴팁 등) 폰트 family/size를 개별 지정 가능한 8세트 구조(`01-pygal.md` A6)를 채택하되, "디자인 토큰"으로 테마 객체 안에 통합한다(pygal은 Style과 Config에 흩어져 있던 것을 하나로 합침).
- margin/spacing은 CSS box model과 유사한 4방향 개별+fallback 패턴(pygal 선례)을 채택.
- **자동 레이아웃(legend 자동 배치, tight/constrained 여백 조정)은 실제 텍스트 bbox 측정을 전제로 하며, 순수 SVG 문자열 생성기에는 렌더러가 없어 이 측정이 불가능하다**(`02-matplotlib.md` A6의 핵심 발견). 세 가지 대응 옵션 중 선택이 필요:
  1. 폰트별 근사 advance-width 테이블을 내장(가볍지만 부정확)
  2. `freetype-py`/`fonttools` 등 폰트 셰이핑 라이브러리를 의존성으로 추가(정확하지만 무겁고 pygal이 지켜온 "가벼운 코어" 철학과 충돌)
  3. 측정이 필요 없는 형태로 레이아웃 요구 자체를 제한 — 상대적 크기 지정(`height`+`aspect`처럼, seaborn `03` A6), 고정 여백 프리셋, 회전(회전은 측정 불필요)으로 겹침을 회피
  - **권고**: 1차 버전은 (3)으로 시작해 "측정 없이도 대부분 잘 보이는" 기본 여백/폰트 크기 프리셋을 제공하고, (1)을 2차로 얹어 정밀도를 높인다. (2)는 무거운 의존성이므로 opt-in extra로만 고려.
- Facet/소형다중패널은 seaborn `FacetGrid`의 `col_wrap`+`height`+`aspect`(상대 크기 지정이라 텍스트 측정 불필요, `03-seaborn.md` A6)를 그대로 채택 — 위 리스크를 우회하는 설계이기도 하다.
- `despine`류 정교화 유틸(스파인 제거+offset+trim)을 1급 함수로 제공하되, SVG 네이티브 구현이므로 애초에 스파인을 안 그리는 옵션(`spines=False`)으로 대체 가능.

## 4. SVG 고유 표현 + 접근성

- **CSS 클래스 기반 재테마**를 아키텍처 원칙으로 확정한다. matplotlib의 `backend_svg.py`는 모든 시각 속성을 요소마다 인라인 `style=`로 하드코딩하는 geometry dump 방식(`02-matplotlib.md` A8)인 반면, pygal은 CSS 클래스+외부 스타일시트로 렌더 후에도 재테마 가능하다(`01-pygal.md` A4/A8). **이 선택이 전체 프로젝트에서 가장 중요한 아키텍처 결정**이며, pygal 방식을 계승한다 — 렌더링 파이프라인 전체(모든 mark가 시맨틱 클래스명을 갖도록)가 이 결정에 종속된다.
- hover 툴팁을 pygal처럼 외부 CDN JS에 위임하지 않고, **SVG `<title>` + CSS `:hover`**만으로 자체 구현한다(`10-feature-matrix.md` A8) — 오프라인/CSP 환경에서도 동작하는 것이 pygal 대비 개선점.
- 접근성을 옵트인이 아니라 **기본값**으로 설계한다: `role="img"` + `aria-label`을 모든 차트 루트에 자동 부여, `<title>`+`<desc>` 쌍을 표준 채우기, 기본 팔레트를 색맹 안전으로. 세 라이브러리 모두 `aria-*`/`role`이 전무하다는 것이 조사에서 확인된 명백한 공백(`01`/`02`/`03`의 A9).
- `prefers-reduced-motion` CSS 미디어쿼리를 애니메이션/트랜지션에 기본 적용 — 구현 비용이 거의 없는데 세 라이브러리 모두 안 하고 있다.
- 명도 대비(WCAG) 검증은 2차 기능으로, pygal의 `is_foreground_light()`(`01-pygal.md` A5)를 발전시켜 텍스트/배경 조합에 대해 기본 제공한다.
