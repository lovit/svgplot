# Changelog

이 파일은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따르며, 버전 번호는 [유의적 버전](https://semver.org/lang/ko/)을 따른다.

## [Unreleased]

### Added

**분포·회귀 차트**

- `ecdfplot` — 경험적 누적분포. 정렬과 누적 비율뿐이라 `stats` 모듈을 쓰지 않는다. `stat="count"`, `complementary=`(생존함수) 지원.
- `kdeplot` — 가우시안 커널 밀도. `hue=` 그룹이 **하나의 x 그리드를 공유**해 곡선끼리 직접 비교된다(`histplot`이 bin 경계를 공유하는 것과 같은 이유). `fill=True`는 축까지 채우고 윤곽을 남긴다.
- `violinplot` — 카테고리별 좌우 대칭 밀도. `boxplot`과 **위치 인자 `(data, x, y)`가 같아** 그 부분은 바꿔 쓸 수 있다(키워드는 다르다 — `boxplot`의 `mode=`에 해당하는 것이 없다). 모든 카테고리가 하나의 y 도메인과 하나의 peak을 공유해 폭이 비교 가능하고, `inner="box"`는 기본 모드 `boxplot`이 그렸을 사분위 상자와 일치한다.
- `regplot` — 최소제곱 적합선과 백분위 부트스트랩 신뢰대역. 같은 `seed`면 SVG가 byte-identical하다.

**형태 차트**

- `heatmap` — 값을 **9단계로 양자화**해 색을 고른다. 연속 램프가 아닌 이유는 재테마가 실제로 동작하게 하기 위해서다 — CSS 규칙 9개는 손으로 고칠 수 있지만 셀당 규칙 하나는 못 고친다. 덤으로 범례가 공짜이고(스와치 9개가 기존 `render_legend`로) 출력이 대략 절반이다. `center=`는 발산 컬러맵(`"coolwarm"`/`"purplegreen"`)과 **함께** 줘야 한다 — `cmap=`의 기본값은 sequential이라 `center=`만 주면 거부된다. `annot=True`의 글자 색은 테마가 아니라 **셀 색의 휘도**에서 고르며(셀 색은 컬러맵에서 오므로 모든 프리셋에서 동일하다) 전 프리셋 × 전 컬러맵에서 WCAG AA(4.5:1)를 넘는다. 2,500셀을 넘으면 크기를 경고하되 **막지는 않는다**.
- `radarplot` — 극좌표 위의 선 그래프(pygal 모델). 새 스케일 타입 없이 기존 `CategoricalScale`/`LinearScale`을 각도 스케일로 그대로 쓴다. 눈금 링은 원이 아니라 **다각형**이라 모든 스포크를 그 눈금이 말하는 값에서 지난다.
- `treemap` — squarified(Bruls 2000), 단일 레벨. 면적이 값에 비례한다.
- `sparkline` — 축·범례·라벨 없는 120x24 미니 캔버스. 문장 안에 넣으라고 있는 것이라 800x600 기본 캔버스를 쓰지 않는 유일한 차트다.
- `gaugeplot` — 240도 아크 위의 스칼라 값. 이 패키지의 차트 16종 중 유일하게 데이터 모델이 비교가 아니라 스칼라라 `pieplot`처럼 단일 `value` 컬럼을 받는다. 범위 밖 값은 양 끝으로 **클램핑**된다 — 감아 돌게 두면 큰 값이 더 작은 아크로 그려진다.

**차트 크기**

- `sparkline`을 뺀 15종이 `width=`/`height=`를 받는다. 기본값 `None`은 800×600이므로 **기존 호출의 출력이 byte-identical**하다 — 16종 전부를 `origin/main`과 대조해 확인했다.
- 마진 프리셋이 캔버스에 맞춰 줄어든다. 가로/세로 각각 45%를 넘으면 그 쌍을 같은 비율로 축소한다 — 한쪽만 깎으면 범례 여백과 눈금 라벨 여백 중 하나가 다른 하나를 위해 희생된다. 기본 크기에서는 클램프가 걸리지 않으므로 byte-identical이 유지된다. 이슈의 예시(폭 300)에서 플롯 영역이 80px → 165px가 된다.
- 눈금 개수가 플롯 영역 길이에서 나온다. 기준은 기본 크기가 이미 쓰는 밀도(가로 128px, 세로 104px당 하나)이며, 두 마진 프리셋이 남기는 700px과 580px이 **모두 5로 반올림되는** 값이라 기본 크기에서는 지금과 같은 5개가 나온다. 2~10개로 묶인다.
- **240×180 미만은 거부한다.** 임의의 하한이 아니라 범례 여백에서 푼 값이다 — 마진 축소 후 범례 글자에 남는 자리가 `0.32727×폭 − 42`px이고, 기본 범례 글꼴에서 6글자가 36.3px이므로 239.25px이 경계다. 테스트가 이 계산을 다시 수행해 상수와 대조하므로 근거와 상수가 어긋날 수 없다. 높이 180은 기본값과 같은 4:3.
- 범례 행이 캔버스 아래로 넘치면 **거부한다**(예전에는 캔버스 밖에 그렸다). `heatmap`의 9단계 범례는 상단 여백 아래로 180px, 즉 캔버스 높이 210px을 요구해 최소 높이에서 들어가지 않는다. 800×600에서 29개 이상의 범례 항목을 갖는 차트도 이제 조용히 잘리는 대신 한계를 말한다.

**통계**

- `stats.kde` — 순수 stdlib 가우시안 KDE(Scott/Silverman). `grid_range=`로 여러 표본을 한 그리드에서 평가할 수 있다.
- `stats.regression` — OLS `linear_fit`, 시드 고정 부트스트랩 `confidence_band`. 대역 없이 적합선만 필요한 호출자를 위한 `svgplot.stats.regression.fit_curve`(서브모듈 전용, `stats` 재노출 대상 아님).
- `stats.quantile` — `box.py`의 private 헬퍼를 공개 승격.

**labels와 markdown 출력**

- `Chart`/`Composition`의 `.save("x.md")` / `.to_markdown()` — 인라인 SVG와 각주 표를 한 파일에. `labels/` 패키지가 이것으로 처음 사용자에게 도달한다.
- `lineplot`/`scatterplot`/`pieplot`의 `info=` — 차트가 실제로 그린 행만 표로 병기한다.
- 최상위 `LabelSpec` 재노출.

**접근성**

- `Chart` 렌더 경로에 접근성 기본값을 연결한다 — `role="img"`/`aria-label`/`<title>`/`<desc>`. 0.1.0에서는 `accessibility.py`가 존재했을 뿐 어떤 렌더 경로에도 연결되어 있지 않아, **차트와 합성 도판 모두** 접근성 요소를 하나도 내보내지 않았다.
- `Composition`(`row`/`column`/`grid`/`facet`) 출력에도 같은 요소를 부여한다.
- 제목을 지정하지 않았거나 공백만 지정한 경우 기본 접근 가능한 이름(`"Chart"`)으로 대체한다 — 보조 기술에 빈 이름을 읽어주는 것보다 낫다.
- `add_caption`이 제목을 따로 지정하지 않은 합성물의 접근 가능한 이름으로 캡션을 채택한다 — 눈에 보이는 캡션이 있는데 보조 기술에는 일반 기본값을 읽어주는 것이 더 나쁘기 때문이다.

**그 외**

- `theme.css`에 `level_colors=`와 `mark_style="outlined"` 추가.
- `palette.Normalize`, `palette.diverging`.
- `CategoricalScale(padding=)` — d3 `scaleBand().padding()`.
- `warnings` — `SvgplotWarning` / `HeatmapSizeWarning`. 경고 정책의 첫 구현이다("출력은 유효하나 품질 저하"면 warn, 무효면 raise).
- `charts/_polar.py` — `pie.py`에서 극좌표 기하 추출. `pie`/`radar`/`gauge`가 공유한다.
- `theme.css`의 `ink_colors=` — 값으로 칠한 마크 **위에 얹는 글자** 색. `level_colors=`와 분리한 이유는 둘이 불투명도에 대해 정반대를 원하기 때문이다: 레벨 색은 다른 마크처럼 `theme.opacity`를 지니고, 잉크는 아래 마크와 대비되도록 고른 색이라 어떤 불투명도든 그 선택을 무효화한다.

### 알려진 제약

의도적으로 범위 밖에 둔 것들이며, 각각의 근거는 괄호 안 위치에 적혀 있다.

- **계층형 treemap 미지원**(`charts/treemap.py` 모듈 docstring) — 단일 레벨만. 계층 입력은 `data/_columns.py`가 표현하지 못하는 트리 구조를 요구한다.
- **`violinplot(split=)` 미지원**(`charts/violin.py` 모듈 docstring) — hue 두 그룹을 한 바이올린의 좌우로 나누는 형태.
- **연속 컬러바 미지원**(`charts/heatmap.py` 모듈 docstring) — `heatmap`이 양자화인 것의 이면이다. 연속 램프는 `<linearGradient>`/`stop-color`가 필요한데, 이는 CSS 클래스 계약 밖의 스타일링이고 합성 시 네임스페이싱 재작성에도 잡히지 않는다.
- **여러 줄 라벨 미지원**(`_svg.py`의 `_fold_newlines` docstring) — 텍스트 노드의 개행은 공백으로 접힌다. 진짜 여러 줄 라벨은 `dy`를 가진 `<tspan>`이 필요하고 이 패키지는 글리프를 측정하지 않는다.
- **markdown 표 셀의 GFM autolink**(`labels/table.py`의 `_escape_markdown_cell` docstring) — 맨 URL·`www.` 접두·이메일 주소는 마크업 없이 링크가 되므로 이스케이프로 막을 수 없다. 값을 고쳐 쓰는 것은 호출자가 주지 않은 데이터를 보고하는 일이라 하지 않는다.

### Fixed

- `add_caption`이 캡션 텍스트를 검증하기 *전에* 캔버스를 키워, 거부된 캡션이 도판을 영구히 늘리고 재시도마다 또 늘리던 문제.
- `lineplot`이 NaN x 하나로 차트 전체를 죽이던 문제(필터가 x의 NaN을 보지 않았다).
- 비ASCII 컬럼명(`@매출{0,0}`)이 라벨 스펙에서 거부되던 문제.
- 표 셀의 개행이 HTML 출력에서 그대로 통과해 markdown 블록을 끊던 문제.
- 표 셀의 markdown 인라인 문법이 그대로 렌더돼 `[click](url)`이 살아있는 링크가, `![x](url)`이 원격 이미지(문서를 여는 사람의 IP 비컨)가 되던 문제.
- 텍스트 노드의 개행이 SVG에 빈 줄을 만들어, markdown에 인라인으로 넣으면 CommonMark HTML 블록이 그 지점에서 끝나고 이후 SVG 원문이 본문으로 파싱되던 문제.

## [0.1.0] - 2026-08-18

첫 릴리스. markdown 문서에 박아넣을 정적 SVG 차트를 만드는 데 필요한 최소 기능 세트를 갖췄다.

### Added

**코어**

- `_svg.py` — SVG 문서 빌더. 패키지 전체의 단일 이스케이프 초크포인트로, 사용자 문자열은 전부 `add_node`/`add_text`/`set_attribute`를 거친다. 태그·속성 이름을 검증하고 `style`/`on*` 속성과 `script` 태그를 차단하며, 좌표는 수식이 아닌 리터럴로 직렬화해 결과물을 손으로 고칠 수 있게 한다.
- `Chart` / `Composition` — 모든 플로팅·레이아웃 함수의 반환 타입. `.save()` / `.to_string()` / `._repr_svg_()`(Jupyter)를 공통 인터페이스로 제공한다.
- 출력: SVG 문자열·파일, Jupyter 인라인 표시, PNG(optional `png` extra, cairosvg 위임).
- `data` — long-form 데이터 인입(pandas DataFrame은 duck-typing으로 지원해 의존성으로 넣지 않음, 컬럼 dict, dict 레코드 리스트)과 `hue=`/`col=`/`row=` 시맨틱 채널 추출, 포인트별 metadata.
- `scales` — linear / categorical / time 스케일과 "nice" tick 생성. 텍스트 폭 측정 없이 동작한다.
- `accessibility` — 차트 루트에 `role="img"` + `aria-label` + `<title>`/`<desc>`를 넣는 기본값.

**테마와 색상**

- `Theme` — ~25키 불변 스타일 스키마. 전역 상태를 바꾸지 않고 렌더 호출마다 명시적으로 전달한다.
- 내장 프리셋 5종(`light` / `dark` / `minimal` / `print` / `high_contrast`), style × context 분리(`paper` / `notebook` / `talk` / `poster`), 시드 컬러 하나로 팔레트를 만드는 `parametric_theme`.
- `palette` — 정성/시퀀셜 팔레트, 미니 언어 파서(`light:#rrggbb`, `blend:#a,#b`, `ch:s=.5,r=-1.5`), 색맹 안전 기본 팔레트(Okabe-Ito), `jet`류 지각적 비균일 컬러맵 차단.
- `theme/css.py` — Theme을 CSS `<style>` 블록으로 렌더링. 임베드되는 모든 값(색상·폰트·클래스명·수치)을 검증해 CSS 규칙 밖으로 새어나가는 것을 막는다.

**통계와 라벨**

- `stats` — 보간 5종(quadratic / cubic / hermite / lagrange / trigonometric), `numpy.histogram_bin_edges`에 위임하는 히스토그램 binning, box plot 통계 5모드(extremes / 1.5IQR / tukey / stdev / pstdev).
- `labels` — Bokeh HoverTool의 필드+포맷 미니 언어를 이식한 `LabelSpec`(numeral / datetime / printf 3스킴)과 각주형 데이터 테이블 렌더러(markdown / HTML).

**차트 타입 7종**

- `lineplot`(시간축·보간), `scatterplot`(hue·size 매핑), `barplot`(수직/수평 × 그룹/누적), `histplot`(자동 binning), `areaplot`(누적 영역), `pieplot`(도넛·값 라벨), `boxplot`(5모드·이상치 마커).

**레이아웃**

- `row` / `column` / `grid` — spacing, `None` 빈 칸, `(chart, row, col, rowspan, colspan)` span 배치. 합성 시 각 자식의 CSS 클래스를 네임스페이싱해 서로의 스타일을 덮어쓰지 않게 한다.
- `add_caption`(공통 캡션), `apply_size`(fixed / responsive), `titles=`로 각 칸에 소제목을 붙이는 탭 대체 관용구.
- `facet` — `col=`/`row=`로 그룹을 나눠 임의의 차트 함수를 반복 호출하고 격자로 배치한다.

### 알려진 제약

- 다이버징 팔레트(`palette.diverging`)는 2차로 미뤘다. 파일과 시그니처만 예약되어 있고 호출하면 `NotImplementedError`가 난다.
- 패널 간 축·색상 공유(`shared_x=` 류)는 레이아웃이 아닌 데이터 레벨 문제로 분리했다. 각 패싯 패널은 자기 그룹 기준으로 독립 스케일링된다.
- `barplot`은 음수 값을 받지 않는다(명시적 `ValueError`).
- v1.0은 JavaScript를 내보내지 않는다. 인터랙션 대신 정적 대체 수단(각주 테이블, 소제목 나열)을 쓴다.

[Unreleased]: https://github.com/lovit/svgplot/compare/2fbe2dc...HEAD
[0.1.0]: https://github.com/lovit/svgplot/commit/2fbe2dc
