# Bokeh — 기능 범위 조사 (레이아웃/정적 hover 중심)

레포: `references/bokeh` · Python `src/bokeh` ~82.6k LOC + TypeScript `bokehjs/src` ~93.7k LOC · 버전 4.0.0-dev.1 · 매우 활성(최근 커밋 2026-08-14, 21,122 commits)

**조사 초점이 다른 3개 레포와 다르다.** 사용자가 Bokeh에서 좋아한 두 가지(hover tool, 다중 차트 연동)는 markdown 임베드(`<img src="chart.svg">`)에서 JS가 실행되지 않는다는 사실 때문에 "그대로 복제"가 아니라 "정적으로 무엇을 대신 가져올 것인가"로 재해석해서 조사했다. 따라서 A10(레이아웃 어휘)과 A8(정적 hover 대안)만 깊게, 나머지 축은 가볍게 다룬다.

---

## 아키텍처 전제 — Bokeh는 SVG를 만들지 않는다

가장 먼저 짚어야 할 사실: **Bokeh Python은 SVG를 직접 산출하지 않는다.** `bokeh.plotting`/`bokeh.models`로 만든 것은 JSON 모델 문서일 뿐이고, 실제 렌더링은 브라우저에서 BokehJS가 Canvas/WebGL로 수행한다. `figure(output_backend="svg")`도 BokehJS 쪽 canvas2svg 셰임이지 Python이 생성하는 SVG가 아니며, `export_svg()`는 헤드리스 브라우저(Selenium/Playwright)로 렌더 결과를 긁어오는 방식이다. 즉 Bokeh는 이 프로젝트가 지향하는 "Python이 SVG 문자열을 직접 만든다"는 모델과 근본적으로 다르다 — **참고할 것은 API 설계 어휘이지, 렌더링 아키텍처가 아니다.**

## A10. 다중 차트 레이아웃/구성 어휘 (깊게 — 최우선 조사 항목)

Bokeh의 레이아웃 함수는 4단계 정밀도로 나뉜다:

| 함수/모델 | 정밀도 | 무엇을 하는가 |
|---|---|---|
| `row()`/`column()` | 1D 단순 나열 | `sizing_mode`만 자식에 전파, flexbox 성격 |
| `layout()` | 재귀적 1D 트리 | 리스트의 리스트를 `Column(Row(...), ...)`로 변환하는 편의 함수 |
| `grid()`/`GridBox` | 진짜 2D | `(child, row, col, rowspan, colspan)` 튜플 기반 CSS-grid 스타일 배치, 불균등 span 지원 |
| `gridplot()` | 2D + 툴바 병합 | grid와 유사하지만 **여러 plot의 tool을 하나의 공유 Toolbar로 병합**(`merge_tools=True` 기본) |

부가 모델: `Tabs`/`TabPanel`(탭 전환), `GroupBox`(제목+테두리 그룹핑), `ScrollBox`(스크롤 컨테이너), `Spacer`(빈 셀). `sizing_mode` enum 8종(`fixed`/`stretch_width`/`stretch_height`/`stretch_both`/`scale_width`/`scale_height`/`scale_both`/`inherit`).

**중요한 발견**: 그리드에 넣는다고 축/범례/색상이 자동으로 맞춰지지 않는다 — `row`/`column`/`layout`은 레이아웃 배치와 sizing_mode만 공유하고, 축 정렬(range 공유)이나 색상 정렬은 사용자가 Python에서 객체를 명시적으로 재사용해야 발생한다. `gridplot`만 유일하게 tool/toolbar를 실제로 병합한다.

**정적 재현 가능성**: `row`/`column`은 CSS flexbox나 여러 `<svg>`를 나란히 배치하는 컨테이너로 쉽게 재현 가능. `grid`/`GridBox`의 `(child, row, col, rowspan, colspan)`은 CSS Grid의 `grid-row`/`grid-column` 문법과 사실상 동형이라 오히려 정적 HTML/CSS Grid 쪽이 표현력이 더 좋다. "공유 툴바"는 정적 SVG에서 의미가 없으므로(pan/zoom 진입점이라 JS가 죽으면 무용지물), 대신 그리드 전체를 감싸는 공통 캡션/외곽 프레임으로 "하나의 도판"이라는 시각적 통일감만 보존한다. `sizing_mode` 8종은 정적 문서에선 `fixed`와 `scale_width`(viewBox+max-width:100%로 근사) 2종으로 축소해도 충분 — `stretch_*`/`*_height` 계열은 "뷰포트 높이"라는 브라우저 전용 개념에 의존해 정적 markdown에서 무의미. `Tabs`는 markdown 임베드에서 완전히 재현 불가(`<img>` 컨텍스트는 CSS `:target`/`:checked` 트릭도 무력화) — 대체 관용구는 `16-layout-vocabulary.md` 참고.

## A8(재해석). 정적 hover 정보 밀도 (깊게)

HoverTool의 `tooltips` 필드 미니 언어는 세 계층으로 이루어진다:

1. **필드 선택**: `@column`(데이터 컬럼), `@{공백 포함 컬럼}`, `@$name`(간접 참조), `$index`/`$name`/`$x`/`$y`/`$sx`/`$sy`(특수 변수), `$color[hex,swatch]:field`/`$swatch:field`(색상 전용 렌더링)
2. **포맷 스펙**: `{0,0.000}`(numeral.js 숫자), `{%F}`(datetime, `formatters`에 스킴 지정 필요), `{%.2f}`(printf), `{safe}`(HTML 이스케이프 해제), `{custom}`(CustomJSHover)
3. **표시 형태**: `[(label, field), ...]` 리스트 → 자유형 HTML 문자열 템플릿 → 선언적 `HTML`/`ValueRef`/`Index` DOM 트리(grid 레이아웃, 필드별 style/filter까지)

`filters`(SQL WHERE에 대응), `sort_by`(ORDER BY), `limit`은 "포인트 밀도가 높을 때 hover에 뜨는 정보를 추려내는" 기능 — 정적 렌더링에서도 동일한 문제(라벨 겹침)를 풀어야 하므로 그대로 참고할 가치가 있다.

**정적 재현 가능성 — 4가지 패턴** (상세 트레이드오프는 `17-static-hover-alternative.md`):
(a) 인라인 데이터 라벨, (b) 극값/이상치만 골라 보여주는 사이드 패널, (c) SVG `<title>`/`<desc>`(접근성 보너스일 뿐, markdown `<img>` 임베드에선 이마저 작동 안 함), (d) 각주형 데이터 테이블(pygal `render_table` 패턴과 유사, Bokeh의 라벨-값 쌍 구조와 정확히 대응).

핵심 관찰: **`tooltips` 리스트(`[("label", "@field{format}"), ...]`)는 "라벨 포맷터 스키마"로 그대로 이식 가능**하며, 인라인 라벨이든 각주 테이블이든 동일한 스펙 하나로 두 출력을 만들 수 있다.

## A1. 차트/glyph 인벤토리 (가볍게)

Bokeh에는 "차트 타입" 개념이 없다 — pygal(24 클래스)이나 matplotlib(69 메서드)과 달리, `scatter`/`line`/`vbar`/`hbar`/`patch`/`wedge` 등 **43개 glyph**를 조합해서 만든다. `bokeh.plotting`(고수준, `figure().scatter(...)`)과 `bokeh.models`(저수준, `Plot`+`add_glyph`)의 이원 구조. 마커 셰이프 shorthand(`circle_cross`, `diamond_dot` 등 24종)는 전부 `scatter(marker=...)` 위의 sugar.

## A3. API 문법 (가볍게)

```python
# 고수준: figure() + glyph 메서드
p = figure(width=250, height=250)
p.scatter(x, y, size=10, color="navy", alpha=0.5)

# 저수준: Plot + add_glyph
plot = Plot(min_border=80)
plot.add_glyph(source, Scatter(x="x", y="y", fill_color="red"))
plot.add_layout(LinearAxis(), 'below')
```
pygal의 "객체+체이닝", matplotlib의 "상태형/OO 이원", seaborn의 "함수형+객체형 이원"과 비교하면, Bokeh는 "glyph 조합형"이라는 네 번째 패턴 — 차트 타입이 아니라 마크(mark) 프리미티브를 조립한다는 점에서 seaborn objects 인터페이스(`Mark`)와 철학이 가장 가깝다.

## A4/A5. 테마·팔레트 (가볍게)

테마 6종(`caliber`/`carbon`/`dark_minimal`/`light_minimal`/`night_sky`/`contrast`), **`Document` 단위로 적용된다(차트별이 아님)** — pygal/matplotlib/seaborn이 차트/rcParams 단위인 것과 다르다. 팔레트는 `palettes.py`(~1946줄)에 ColorBrewer, d3(Category10/20 등), mpl 계열(Viridis/Magma/Plasma/Inferno/Cividis/Turbo), Tol, colorblind, Bokeh 하우스 팔레트까지 6개 계열, 크기별 변형 포함 ~200+ named export — seaborn(팔레트 12+컬러맵 6)보다 카탈로그 규모가 크다.

## A9. 접근성 (가볍게)

grep 확인 결과 `aria`/`role` 키워드가 `src/bokeh/models/`에 산발적으로 존재하나(위젯 클래스 일부), 체계적인 접근성 API는 확인되지 않았다(unknown — 전수 조사는 아님).

## A7. 통계 변환 — 스킵

Bokeh는 통계 계산 레이어가 거의 없다. `transform.py`의 `factor_cmap`/`linear_cmap`/`log_cmap`/`jitter`/`dodge`/`cumsum`/`stack`은 client-side(BokehJS) 변환이지 Python이 계산하는 통계가 아니다. seaborn과 비교 대상이 아니므로 "해당 없음"으로 표기.

## 강점 / 약점 종합 (프로젝트 관점)

**가져올 것**: 4단계 레이아웃 정밀도(1D/2D/span/공유), CSS Grid와 동형인 grid 배치 문법, tooltip 필드 미니 언어(라벨-값 쌍 + 포맷 스펙 3종), "밀도 높으면 추려낸다"(filters/sort_by/limit)는 설계 원칙, Document 단위 테마 적용 모델.

**가져오지 않을 것**: Canvas/WebGL 렌더링 아키텍처 전체, `ColumnDataSource`+`Selection` 기반 실시간 연동(v1.0에서는 markdown이 JS를 안 돌리므로 무의미 — v2.0 후보로만 `18-progressive-js-roadmap.md`에 기록), 공유 툴바 개념(정적 세계에 대응물 없음), `Tabs`(정적 재현 불가).
