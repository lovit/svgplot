# Changelog

이 파일은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따르며, 버전 번호는 [유의적 버전](https://semver.org/lang/ko/)을 따른다.

## [Unreleased]

### Added

**분포·회귀 차트**

- `ecdfplot` — 경험적 누적분포. 정렬과 누적 비율뿐이라 `stats` 모듈을 쓰지 않는다. `stat="count"`, `complementary=`(생존함수) 지원.
- `kdeplot` — 가우시안 커널 밀도. `hue=` 그룹이 **하나의 x 그리드를 공유**해 곡선끼리 직접 비교된다(`histplot`이 bin 경계를 공유하는 것과 같은 이유). `fill=True`는 축까지 채우고 윤곽을 남긴다.
- `violinplot` — 카테고리별 좌우 대칭 밀도. `boxplot`과 **위치 인자 `(data, x, y)`가 같아** 그 부분은 바꿔 쓸 수 있다(키워드는 다르다 — `boxplot`의 `mode=`에 해당하는 것이 없다). 모든 카테고리가 하나의 y 도메인과 하나의 peak을 공유해 폭이 비교 가능하고, `inner="box"`는 기본 모드 `boxplot`이 그렸을 사분위 상자와 일치한다.
- `regplot` — 최소제곱 적합선과 백분위 부트스트랩 신뢰대역. 같은 `seed`면 SVG가 byte-identical하다.

**통계**

- `stats.kde` — 순수 stdlib 가우시안 KDE(Scott/Silverman). `grid_range=`로 여러 표본을 한 그리드에서 평가할 수 있다.
- `stats.regression` — OLS `linear_fit`, 시드 고정 부트스트랩 `confidence_band`. 대역 없이 적합선만 필요한 호출자를 위한 `svgplot.stats.regression.fit_curve`(서브모듈 전용, `stats` 재노출 대상 아님).
- `stats.quantile` — `box.py`의 private 헬퍼를 공개 승격.

**labels와 markdown 출력**

- `Chart`/`Composition`의 `.save("x.md")` / `.to_markdown()` — 인라인 SVG와 각주 표를 한 파일에. `labels/` 패키지가 이것으로 처음 사용자에게 도달한다.
- `lineplot`/`scatterplot`/`pieplot`의 `info=` — 차트가 실제로 그린 행만 표로 병기한다.
- 최상위 `LabelSpec` 재노출.

**접근성**

- `Composition`(`row`/`column`/`grid`/`facet`) 출력에도 `role="img"`/`aria-label`/`<title>`/`<desc>`를 부여한다. 0.1.0에서는 합성 도판에 접근성 요소가 하나도 없었다.
- `add_caption`이 제목을 따로 지정하지 않은 합성물의 접근 가능한 이름으로 캡션을 채택한다 — 눈에 보이는 캡션이 있는데 보조 기술에는 일반 기본값을 읽어주는 것이 더 나쁘기 때문이다.

**그 외**

- `theme.css`에 `level_colors=`와 `mark_style="outlined"` 추가.
- `palette.Normalize`, `palette.diverging`.
- `CategoricalScale(padding=)` — d3 `scaleBand().padding()`.
- `warnings` — `SvgplotWarning` / `HeatmapSizeWarning`.
- `charts/_polar.py` — `pie.py`에서 극좌표 기하 추출.
- `treemap`, `sparkline`.

### Fixed

- `add_caption`이 캡션 텍스트를 검증하기 *전에* 캔버스를 키워, 거부된 캡션이 도판을 영구히 늘리고 재시도마다 또 늘리던 문제.
- 공백만 있는 `set_title("   ")`이 `set_title()` 호출 시점이 아니라 한참 뒤 `to_string()`/`save()`에서 터지던 문제.
- `lineplot`이 NaN x 하나로 차트 전체를 죽이던 문제(필터가 x의 NaN을 보지 않았다).
- 비ASCII 컬럼명(`@매출{0,0}`)이 라벨 스펙에서 거부되던 문제.
- 표 셀의 개행이 HTML 출력에서 그대로 통과해 markdown 블록을 끊던 문제.

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

[Unreleased]: https://github.com/lovit/svgplot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lovit/svgplot/releases/tag/v0.1.0
