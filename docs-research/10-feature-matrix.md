# 기능 대조표 — pygal × matplotlib × seaborn (+ Bokeh)

**Bokeh는 전 축에 걸쳐 조사하지 않았다.** markdown 임베드에서는 JS가 죽으므로 Bokeh의 렌더링·인터랙션 아키텍처 자체는 비교 대상이 아니다. Bokeh는 A8(출력·인터랙션, 정적 대안 관점)과 신규 A10(다중 차트 레이아웃 어휘)에만 열로 추가한다. 다른 축(A1~A7, A9)은 `04-bokeh.md`에 가볍게만 기록하고 이 표에는 넣지 않는다.

범례:
- 지원 열(pygal/matplotlib/seaborn): `●` 1급 지원(전용 API) · `◐` 가능하지만 우회/수동 · `○` 없음 · `—` 해당 라이브러리 모델에 부적합
- **수요 신호**: seaborn이 감싸 놓았는가(핵심 근거) + matplotlib gallery/문서 비중(보조 근거) 기준 `높음/중간/낮음`
- **SVG 적합도**: `유리`/`보통`/`불리` (불리하면 이유 병기)
- **MVP 판정**: `필수`/`2차`/`제외`

---

## A1. 차트 타입

| 기능 | pygal | matplotlib | seaborn | 수요 신호 | SVG 적합도 | MVP 판정 |
|---|---|---|---|---|---|---|
| 선 그래프 | ● Line | ● plot | ● lineplot | 높음 | 유리 | 필수 |
| 산점도 | ◐ XY(stroke=False) | ● scatter | ● scatterplot(hue/size/style) | 높음 | 유리 | 필수 |
| 막대(수직) | ● Bar | ● bar | ● barplot | 높음 | 유리 | 필수 |
| 막대(수평) | ● HorizontalBar | ● barh | ● barplot(orient='h') | 높음 | 유리 | 필수 |
| 누적 막대 | ● StackedBar | ◐ bar(bottom=) 수동 | ◐ histplot(multiple='stack') | 중간 | 유리 | 필수 |
| 그룹 막대(dodge) | ◐ 수동 오프셋 | ◐ 수동 오프셋 | ● catplot dodge / objects.Dodge() | 높음(seaborn이 Move로 1급화) | 유리 | 필수 |
| 히스토그램 | ◐ 수동 bin 계산 | ● hist(자동 binning) | ● histplot(자동+정규화 5종) | 높음 | 유리 | 필수 |
| 영역 채움(fill) | ● Line(fill=True) | ● fill_between | ◐ kdeplot(fill=True) | 중간 | 유리 | 필수 |
| 누적 영역 | ● StackedLine | ● stackplot | ○ | 중간 | 유리 | 2차 |
| 파이 | ● Pie(도넛/반원) | ● pie | ○(직접 API 없음) | 중간 | 유리 | 필수 |
| 박스플롯 | ● Box(5 모드) | ● boxplot | ● boxplot | 높음 | 유리 | 필수 |
| 바이올린플롯 | ○ | ● violinplot | ● violinplot(split 지원) | 높음(matplotlib엔 있지만 seaborn이 크게 편의화) | 보통(KDE 계산 필요) | 2차 |
| Boxen(letter-value) | ○ | ○ | ● boxenplot | 낮음(니치) | 보통 | 제외(후순위) |
| KDE 곡선/등고선 | ○ | ○(직접 없음, scipy 필요) | ● kdeplot(1D/2D) | 높음 | 보통(통계계산 필요) | 2차 |
| ECDF | ○ | ● ecdf | ● ecdfplot | 중간 | 유리 | 2차 |
| Rug plot | ○ | ○ | ● rugplot | 낮음 | 유리 | 제외 |
| Strip/Swarm plot | ● Dot(유사) | ○ | ● stripplot/swarmplot | 중간 | 유리(swarm은 비겹침 배치 알고리즘 필요) | 2차 |
| Point plot(추정치+오차) | ○ | ◐ errorbar 수동 | ● pointplot | 중간 | 유리 | 2차 |
| Count plot | ○ | ◐ bar+value_counts 수동 | ● countplot | 낮음(barplot 특수형) | 유리 | 제외 |
| 회귀선+신뢰대역 | ○ | ○(직접 없음) | ● regplot/lmplot | 높음 | 보통(회귀계산 필요) | 2차 |
| 히트맵 | ○ | ● imshow/pcolormesh | ● heatmap(annot 포함) | 중간 | 불리(셀 수만큼 rect 필요, 대용량시 파일비대) | 2차 |
| Hexbin | ○ | ● hexbin | ◐ jointplot(kind='hex') | 낮음 | 불리(그리드 집계) | 제외 |
| 등고선(contour) | ○ | ● contour/contourf | ○ | 낮음(SVG 목표와 안 맞음) | 불리(등고선 추적 알고리즘 필요) | 제외 |
| 레이더/스파이더 | ● Radar | ◐ polar+수동 | ○ | 중간 | 유리 | 2차 |
| 게이지 | ● Gauge/SolidGauge | ○ | ○ | 낮음(pygal 고유) | 유리 | 2차 |
| 트리맵 | ● Treemap | ○ | ○ | 낮음 | 유리 | 2차 |
| 퍼널 | ● Funnel | ○ | ○ | 낮음 | 유리 | 제외 |
| 피라미드(인구) | ● Pyramid | ◐ StackedBar 응용 | ○ | 낮음 | 유리 | 제외 |
| 시간축 선 | ● DateLine 등(4종) | ● plot+date locator | ● lineplot(x=datetime) | 중간 | 유리 | 필수(단, 별도 클래스 아닌 XY의 스케일 옵션으로) |
| 클러스터맵(덴드로그램+heatmap) | ○ | ○ | ● clustermap | 낮음 | 불리(복합 레이아웃) | 제외 |
| Facet grid(소형 다중패널) | ○ | ◐ subplots 수동 | ● relplot/catplot/displot(col=,row=) | 높음 | 유리 | 필수 |
| Pair/Joint grid | ○ | ○ | ● pairplot/jointplot | 중간 | 불리(레이아웃 엔진 필요) | 제외(후순위) |
| 스파크라인/텍스트 | ● 전용 render | ○ | ○ | 낮음(pygal 고유) | 유리 | 2차 |

## A2. 데이터 입력 & 시맨틱 매핑

| 기능 | pygal | matplotlib | seaborn | 수요 신호 | SVG 적합도 | MVP 판정 |
|---|---|---|---|---|---|---|
| flat list/array 입력 | ● | ● | ● | 높음 | 유리 | 필수 |
| long-form DataFrame(`data=df,x=,y=`) | ○ | ◐(`data=`, hue 없음) | ● | 높음 | 유리 | 필수 |
| wide-form DataFrame 자동 인식 | ○ | ○ | ● | 중간 | 유리 | 2차(구현비용 대비 후순위) |
| `hue=` 색상 시맨틱 매핑 | ○ | ○ | ● | 높음 | 유리 | 필수 |
| `size=` 크기 시맨틱 매핑 | ○ | ◐(raw c=/s=) | ● | 중간 | 유리 | 2차 |
| `style=` 마커/선 스타일 매핑 | ○ | ○ | ● | 중간 | 유리 | 2차 |
| `col=`/`row=` 패싯 매핑 | ○ | ○ | ● | 높음 | 유리 | 필수 |
| point-level metadata(라벨/툴팁) | ● (dict 값) | ○ | ○ | 중간 | 유리 | 필수(pygal 선례 채택) |
| 자동 집계(estimator+errorbar) | ○ | ○ | ● | 중간 | 보통(통계계산) | 2차 |
| 결측치(None) 처리 | ● | ● (NaN) | ● (NaN) | 높음 | 유리 | 필수 |

## A4. 스타일·테마 시스템

| 기능 | pygal | matplotlib | seaborn | 수요 신호 | SVG 적합도 | MVP 판정 |
|---|---|---|---|---|---|---|
| built-in 테마 프리셋 | ● 16종 | ● 31종(mplstyle) | ● 5 style×4 context | 높음 | 유리 | 필수 |
| 테마=CSS 클래스 기반(재테마 가능) | ● | ○(geometry dump) | ○(mpl에 위임) | — (pygal 고유 강점) | **유리(SVG만의 강점)** | 필수 |
| 파라메트릭 테마(시드컬러→팔레트) | ● 5종 | ○ | ○ | 중간 | 유리 | 필수 |
| style/context 분리(외관 vs 스케일) | ○ | ○ | ● | 높음(훔칠 아이디어) | 유리 | 필수 |
| 스코프 한정 임시 적용(context manager) | ○ | ● rc_context | ● axes_style(with) | 중간 | 유리 | 2차 |
| 순수 함수적 렌더링(전역 mutate 없음) | ● | ◐(rcParams 전역) | ○(rcParams mutate) | — | **유리(설계 원칙)** | 필수 |
| 요소별(축/타이틀/범례/툴팁) 개별 스타일 | ● 8세트 | ◐(rcParams 네임스페이스) | ◐(mpl 위임) | 중간 | 유리 | 필수 |

## A5. 컬러 팔레트 엔진

| 기능 | pygal | matplotlib | seaborn | 수요 신호 | SVG 적합도 | MVP 판정 |
|---|---|---|---|---|---|---|
| 정성(qualitative) 팔레트 | ● 16 | ● tab10 등 | ● 12 | 높음 | 유리 | 필수 |
| 시퀀셜 컬러맵 | ○ | ● 다수 | ● rocket/mako 등 | 중간 | 유리 | 필수(heatmap 위해) |
| 다이버징 컬러맵 | ○ | ● 다수 | ● vlag | 중간 | 유리 | 2차 |
| 팔레트 미니 언어(문자열 스펙) | ○ | ○ | ● (`"ch:..."`,`"light:X"` 등) | 중간(참신하지만 seaborn 고유) | 유리 | 필수(채택 권장) |
| 시드컬러 기반 자동 파생 | ● parametric style | ○ | ◐(dark/light_palette) | 높음 | 유리 | 필수 |
| named color 사전(CSS4/XKCD 등) | ◐(hex 직접) | ● 148+947 | ◐(xkcd 서브셋) | 낮음 | 유리 | 2차 |
| Normalize(log/power/등) | ○ | ● 8종 | ○ | 낮음(heatmap 전용) | 유리 | 2차 |
| 색맹 안전 팔레트 | ○ | ● okabe_ito 등(옵트인) | ● colorblind(옵트인) | 중간 | **유리(차별화 지점)** | 필수(기본값으로) |
| 알려진 나쁜 기본값 차단(jet 등) | ○ | ○(포함되어 있음) | ● (`"jet"`→에러) | — | — | 필수(설계 원칙 채택) |

## A6. 타이포그래피 & 레이아웃

| 기능 | pygal | matplotlib | seaborn | 수요 신호 | SVG 적합도 | MVP 판정 |
|---|---|---|---|---|---|---|
| 요소별 폰트 family/size | ● 8세트 | ◐(전역 rcParams) | ◐(mpl 위임) | 중간 | 유리 | 필수 |
| margin/spacing box model | ● | ◐(subplots_adjust) | ◐ | 중간 | 유리 | 필수 |
| 자동 legend 배치 | ◐(고정 위치) | ● (best 탐색) | ● + move_legend | 높음 | **불리(텍스트 bbox 측정 필요)** | 2차(휴리스틱으로 근사) |
| 자동 여백 조정(tight/constrained) | ○ | ● | ◐(mpl 위임) | 높음 | **불리(텍스트 bbox 측정 필요 — 최대 리스크)** | 2차(고정 여백으로 근사 후 개선) |
| 라벨 회전(겹침 회피) | ● x_label_rotation | ● | ◐(mpl 위임) | 높음 | 유리(회전은 측정 불필요) | 필수 |
| Facet/소형다중패널 자동 배치 | ○ | ◐ | ● col_wrap+height+aspect | 높음 | 유리(상대크기 지정이면 측정 불필요) | 필수 |
| despine류 정교화 유틸 | ○ | ○ | ● despine | 중간 | 유리 | 2차 |
| annotate(다중 좌표계) | ◐ | ● | ◐(mpl 위임) | 중간 | 유리 | 2차 |
| mathtext/수식 렌더링 | ○ | ● 자체 파서 | ◐(mpl 위임) | 낮음 | 불리(구현비용 큼) | 제외 |
| CJK 폰트 fallback | ○ | ◐(수동 지정, 기본값 아님) | ○(mpl 위임) | 낮음(조사 비용 대비) | 불리(자체 설계 필요) | 2차(기본 폰트 스택에 CJK 포함) |

## A7. 통계 변환

| 기능 | pygal | matplotlib | seaborn | 수요 신호 | SVG 적합도 | MVP 판정 |
|---|---|---|---|---|---|---|
| 보간(곡선 스플라인) | ● 5종 | ○ | ○ | 중간 | 유리 | 필수(pygal 선례 채택) |
| 히스토그램 자동 binning | ○ | ● | ● | 높음 | 유리(numpy 위임) | 필수 |
| KDE | ○ | ○ | ● (scipy 폴백 포함) | 중간 | 보통 | 2차 |
| ECDF | ○ | ● | ● | 낮음(계산 단순) | 유리 | 2차 |
| 회귀적합(선형) | ○ | ○ | ● (numpy 위임 가능) | 중간 | 유리 | 2차 |
| 회귀적합(logistic/robust/lowess) | ○ | ○ | ● (statsmodels 필수) | 낮음 | 보통(무거운 의존성) | 제외 |
| 부트스트랩 CI / errorbar 통합스펙 | ● (CI만, metadata 방식) | ○ | ● errorbar= | 중간 | 유리(numpy 위임 가능) | 2차 |
| Box plot 통계(quartile/outlier) | ● 5 모드 | ● | ● | 높음 | 유리 | 필수 |
| letter-values | ○ | ○ | ● | 낮음 | 보통 | 제외 |

## A8. 출력·인터랙션·확장성

| 기능 | pygal | matplotlib | seaborn | 수요 신호 | SVG 적합도 | MVP 판정 |
|---|---|---|---|---|---|---|
| SVG 문자열/파일 | ● | ● | ●(mpl 위임) | 높음 | 유리 | 필수 |
| PNG 래스터 export | ● (cairosvg 위임) | ● | ●(mpl 위임) | 중간 | — | 필수(optional dep) |
| data URI | ● | ○ | ○ | 낮음 | 유리 | 2차 |
| 웹 프레임워크 response(Flask/Django) | ● | ○ | ○ | 낮음 | 유리 | 2차 |
| sparkline/sparktext | ● | ○ | ○ | 낮음 | 유리 | 2차 |
| CSS 기반 재테마(렌더 후 스타일 교체) | ● (class 기반) | ○ (geometry dump) | ○ | — | **유리(SVG 고유 강점)** | 필수 |
| hover 툴팁 | ◐(외부 JS 위임) | ○ | ○ | 중간 | **유리(SVG+CSS로 자체 구현 가능)** | 필수(자체 CSS/`<title>` 기반) |
| 애니메이션 | ○ | ◐(GUI 전용, SVG와 분리) | ○ | 낮음 | 유리(SVG는 SMIL/CSS anim 가능하나 matplotlib엔 선례 없음) | 제외(1차) |
| 플러그인/확장 지점 | ◐(맵 전용 entry_points) | ○ | ○ | 낮음 | — | 2차 |
| Jupyter 자동 표시(`_repr_svg_`) | ● | ● | ● | 높음 | 유리 | 필수 |

### A8 부록 — Bokeh 대비 정적 hover 재현 (`17-static-hover-alternative.md` 상세)

| 기능 | pygal | Bokeh | 새 패키지(정적 대안) | MVP 판정 |
|---|---|---|---|---|
| hover tooltip(값+포맷) | ◐(외부 JS 위임) | ● HoverTool, `@field{format}` 미니 언어 | ◐ 각주형 데이터 테이블 + 인라인 라벨(`label_spec` 단일 스펙) | 필수(테이블), 2차(인라인) |
| 필드별 포맷 스킴(numeral/datetime/printf) | ○ | ● `formatters=` | ● 동일 3분류 채택 | 필수 |
| 밀도 높을 때 필터링(`sort_by`/`limit`) | ○ | ● | ◐ 저자가 미리 정한 극값/이상치 선별(런타임 아님) | 2차 |
| standalone에서만 켜지는 실시간 hover | — | ● (서버 불필요, 정적 HTML+JS) | ○(v1.0) → v2.0 후보 | 제외(v1.0), `18-progressive-js-roadmap.md` |

## A9. 접근성

| 기능 | pygal | matplotlib | seaborn | 수요 신호 | SVG 적합도 | MVP 판정 |
|---|---|---|---|---|---|---|
| 색맹 안전 팔레트를 **기본값**으로 | ○ | ○(옵트인만) | ○(옵트인만) | — | **유리(3사 모두 공백 — 최대 차별화)** | 필수 |
| SVG `<title>` | ● | — | — | — | 유리 | 필수 |
| SVG `<desc>`(의미론적 설명) | ◐(데이터용, 접근성용 아님) | — | — | — | 유리 | 필수 |
| `role="img"`/`aria-*` | ○ | — | — | — | **유리(3사 모두 전무)** | 필수 |
| 명도 대비(WCAG) 검증 | ○ | ○ | ○ | — | 유리(계산만 하면 됨) | 2차 |
| `prefers-reduced-motion` 대응 | ○ | — | — | — | 유리(CSS 미디어쿼리로 즉시 가능) | 2차 |
| 데이터 테이블 fallback | ◐(render_table 있으나 접근성 연결 안 됨) | ○ | ○ | 낮음 | 유리 | 제외(1차) |

## A10. 다중 차트 레이아웃 어휘 (Bokeh 참고, `16-layout-vocabulary.md` 상세)

| 기능 | pygal | Bokeh | 새 패키지 | MVP 판정 |
|---|---|---|---|---|
| 1D 나열(row/column, spacing, 빈칸) | ○ | ● `row()`/`column()` | ● 동일 어휘 채택 | 필수 |
| 2D 그리드(span 지원) | ○ | ● `grid()`/`GridBox`(row,col,rowspan,colspan) | ● CSS Grid 직접 위임(Bokeh보다 단순 구현) | 필수 |
| 공유 툴바(다중 차트 인터랙션 통합) | ○ | ● `gridplot(merge_tools=True)` | — (정적 세계에 대응 개념 없음) | 제외 |
| 도판 전체 캡션/타이틀 | ○ | ◐(`toolbar_location`이 유사 위치 개념) | ● 그리드 상단/하단 공통 캡션 | 필수 |
| 반응형 크기 조정 | ○ | ● `sizing_mode` 8종 | ◐ `fixed`/`responsive` 2종으로 축소 | 필수 |
| 탭 전환(Tabs) | ○ | ● | ○ — markdown에서 재현 불가, "펼쳐서 소제목" 대체 | 제외(대체 관용구로 필수) |
| 그룹 테두리(GroupBox) | ○ | ● | ◐ `<rect>`+`<text>`로 저비용 재현 | 2차 |
| 내부 스크롤(ScrollBox) | ○ | ● | — (정적 문서에 스크롤 개념 없음) | 제외 |
| 축/색상 자동 정렬 | ○ | ◐(range 객체 명시적 공유 필요) | ◐ 레이아웃과 분리된 데이터 레벨 기능 | 2차 |

---

## 파생 뷰

### 갭 뷰 — pygal에 없고(○/◐) seaborn 수요가 높은 것 = 빌드 리스트
`hue`/`size`/`style`/`col`/`row` 시맨틱 매핑, long-form DataFrame 입력, 히스토그램 자동 binning, 그룹 막대(dodge), Facet grid, KDE/회귀(2차), style/context 분리 테마.

### SVG-우위 뷰 — 세 라이브러리 모두 약하지만 SVG가 유리한 것 = 차별화 스토리
CSS 클래스 기반 재테마(다크모드를 재렌더 없이 스타일시트 교체로), `<title>`/`<desc>`/`role="img"` 접근성, 색맹 안전 팔레트를 **기본값**으로, hover 툴팁을 순수 CSS `:hover`+`<title>`로 자체 구현(외부 JS 불필요), `prefers-reduced-motion` 대응.

### SVG-위험 뷰 — 순수 SVG 렌더러에서 특히 어려운 것
**텍스트 bbox 측정이 필요한 모든 자동 레이아웃**(자동 legend 배치, tight/constrained 여백 조정) — matplotlib조차 이걸 위해 FreeType 폰트 엔진을 통째로 내장한다. 대용량 히트맵/hexbin(셀 수만큼 DOM 노드 생성 → 파일 비대), 등고선(marching squares 등 기하 알고리즘 필요), 3D, mathtext.

### Quick-win 뷰 — 수요 높고 구현 비용 낮은 것
long-form DataFrame + hue 매핑(데이터 전처리 계층, 렌더링 로직과 무관), 히스토그램 자동 binning(numpy 위임), 그룹 막대 dodge(좌표 계산만), 팔레트 미니 언어(seaborn 설계 그대로 차용), 색맹 안전 기본 팔레트, `<title>`/`role="img"` 접근성.
