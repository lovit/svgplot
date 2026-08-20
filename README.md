# svgplot

markdown 문서에 넣을 정적 SVG 차트를 만드는 Python 패키지.

출력은 텍스트 SVG 한 장이다. 도형에는 `series-1`, `tick-label`, `grid-line` 같은 클래스가 붙고, 색과 두께는 그 파일 안의 `<style>` 블록에 규칙으로 모여 있다. 같은 입력에는 같은 SVG 를 낸다. 런타임 의존성은 없다.

JavaScript 는 내보내지 않는다 — `<script>` 태그와 `style=` 속성은 직렬화 단계에서 차단된다. 상호작용·애니메이션·3D·등고선·수식 조판은 다루지 않는다.

GitHub 는 렌더된 markdown 에서 인라인 SVG 를 지운다. github.com 에서 보여야 하는 문서라면 `<img src="...svg">` 로 참조한다.

## 설치

PyPI 에 올리지 않았다. 저장소에서 바로 설치한다.

```bash
uv add "svgplot @ git+https://github.com/lovit/svgplot"
# 또는
pip install "git+https://github.com/lovit/svgplot"
```

PNG 출력이 필요하면 `svgplot[png]` (cairosvg). Python 3.12 이상.

## Quick start

모든 차트 함수는 long-form 데이터(pandas DataFrame, 컬럼 dict, dict 레코드 리스트)를 받아 `Chart` 를 돌려준다. `Chart` 는 `.save()` / `.to_string()` 과 Jupyter 표시를 지원한다.

```python
import svgplot as sp

data = {
    "day": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "sales": [10.0, 15.0, 7.0, 20.0, 12.0, 6.0, 9.0, 4.0, 14.0, 8.0],
    "region": ["서울", "서울", "서울", "서울", "서울", "부산", "부산", "부산", "부산", "부산"],
}

sp.lineplot(data, x="day", y="sales", hue="region").save("sales.svg")
```

`sales.svg` 안에서 두 지역의 선은 `class="series-1 line-series"` 와 `class="series-2 line-series"` 이고, 파일의 `<style>` 에 그에 대응하는 규칙이 있다.

```css
.series-1 { stroke: #E69F00; fill: none; stroke-width: 2; opacity: 1; }
```

## 차트

| | |
|---|---|
| [`lineplot`](https://lovit.github.io/svgplot/gallery/lineplot.html) | x 순으로 점을 이어 선을 그린다. x 는 수치 또는 날짜 |
| [`scatterplot`](https://lovit.github.io/svgplot/gallery/scatterplot.html) | 두 수치 컬럼을 점으로 놓는다. `hue=` 는 색, `size=` 는 마커 크기 |
| [`barplot`](https://lovit.github.io/svgplot/gallery/barplot.html) | 카테고리마다 막대 하나. `orient=` 로 방향, `hue=`·`stacked=` 로 그룹 |
| [`areaplot`](https://lovit.github.io/svgplot/gallery/areaplot.html) | 선 아래를 0까지 채운다 |
| [`histplot`](https://lovit.github.io/svgplot/gallery/histplot.html) | 수치 한 컬럼을 구간으로 나눠 구간별 행 수를 막대로 |
| [`pieplot`](https://lovit.github.io/svgplot/gallery/pieplot.html) | 값을 원의 조각으로. `inner_radius=` 로 도넛 |
| [`boxplot`](https://lovit.github.io/svgplot/gallery/boxplot.html) | 카테고리마다 사분위 상자와 수염. `mode=` 가 수염의 끝을 정한다 |
| [`violinplot`](https://lovit.github.io/svgplot/gallery/violinplot.html) | 카테고리마다 좌우 대칭 밀도 곡선 |
| [`kdeplot`](https://lovit.github.io/svgplot/gallery/kdeplot.html) | 분포를 곡선 하나로 추정. 구간 경계가 없다 |
| [`ecdfplot`](https://lovit.github.io/svgplot/gallery/ecdfplot.html) | "이 값 이하가 전체의 몇 퍼센트인가"를 계단으로 |
| [`regplot`](https://lovit.github.io/svgplot/gallery/regplot.html) | 산점도 위에 최소제곱 적합선과 부트스트랩 신뢰대역 |
| [`heatmap`](https://lovit.github.io/svgplot/gallery/heatmap.html) | 행·열 격자에서 값을 색으로. 색은 9단계로 양자화된다 |
| [`radarplot`](https://lovit.github.io/svgplot/gallery/radarplot.html) | 카테고리를 스포크에 놓고 값을 반지름으로 삼는 닫힌 다각형 |
| [`treemap`](https://lovit.github.io/svgplot/gallery/treemap.html) | 값에 면적이 비례하는 타일. squarified 배치, 단일 레벨 |
| [`gaugeplot`](https://lovit.github.io/svgplot/gallery/gaugeplot.html) | 값 하나가 범위 안 어디쯤인지를 240도 아크로 |
| [`sparkline`](https://lovit.github.io/svgplot/gallery/sparkline.html) | 축도 범례도 없는 120x24 미니 선. 문장 안이나 표의 셀에 |

## 갤러리

**<https://lovit.github.io/svgplot/gallery/>**

차트 16종 각각에 대해 그림과 그 그림을 만든 코드가 함께 있다. 페이지에 인쇄된 코드가 곧 그 그림을 만든 코드다 — 갤러리 빌드가 코드 문자열을 그대로 실행해 SVG 를 만든다.

## 그 밖의 기능

아래는 아직 갤러리 페이지가 없다. 각 함수의 docstring 에 사용법이 있다.

- **`estimator=`** — 같은 x 에 여러 행이 있을 때 `"mean"`/`"sum"`/`"median"` 등으로 접는다. 지정하지 않으면 차트별 기본 규칙이 적용되고 몇 행을 접었는지 `AggregationWarning` 이 알려준다
- **`width=` / `height=`** — 기본 캔버스는 800x600(`sparkline` 만 120x24), 최소 240x180
- **`xscale=` / `yscale=`** — `"linear"` / `"log"`. 날짜 축에 `log` 는 거부된다
- **`sp.row` / `column` / `grid`** — 차트 여러 개를 하나의 도판으로 합성
- **`sp.facet`** — 아무 차트 함수나 그룹별로 반복 호출해 격자로. 패널은 기본적으로 축을 공유한다
- **`theme=`** — 프리셋 5종(`light` `dark` `minimal` `print` `high_contrast`), 컨텍스트 4종(`paper` `notebook` `talk` `poster`), `sp.parametric_theme("#3366cc")` 로 시드 컬러에서 팔레트 생성. 기본 팔레트는 색맹 안전(Okabe-Ito)
- **출력** — `.save()` 는 확장자로 `.svg` / `.png` / `.md` 를 고른다. `.to_string()` · `.to_markdown()` · `.to_html_table()`
- **`info=`** — 차트가 실제로 그린 행만 담은 표를 함께 내보낸다. 1행 = 1마크인 `lineplot`/`scatterplot`/`pieplot` 이 대상
- **접근성** — 모든 차트가 `role="img"` · `aria-label` · `<title>` · `<desc>` 를 내보낸다. `<desc>` 는 차트 종류·데이터 규모·값 범위를 실제로 말한다

## 개발

```bash
curl https://mise.run | sh                       # 최초 1회
curl -LsSf https://astral.sh/uv/install.sh | sh

mise install && mise run install                 # Python + 의존성 + git hook
mise run check                                   # lint + test (CI 와 동일)
```

워크플로·커밋 규칙·스타일 규칙은 [`CLAUDE.md`](CLAUDE.md) 와 [`.claude/rules/`](.claude/rules/) 에 있다. 설계 배경(pygal·matplotlib·seaborn·Bokeh 기능 조사와 그로부터 도출한 결정)은 [`docs-research/00-overview.md`](docs-research/00-overview.md).

## 라이선스

MIT License — [`LICENSE`](LICENSE) 참고.
