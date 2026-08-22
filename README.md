# svgplot

markdown 문서에 넣을 정적 SVG 차트를 만드는 Python 패키지.

출력은 텍스트 SVG 한 장이다. 도형에는 `series-1`, `tick-label`, `grid-line` 같은 클래스가 붙고, 색과 두께는 그 파일 안의 `<style>` 블록에 규칙으로 모여 있다. 같은 입력에는 같은 SVG 를 낸다. 런타임 의존성은 없다.

JavaScript 는 내보내지 않는다 — `<script>` 태그와 `style=` 속성은 노드를 만드는 시점에 거부된다(직렬화까지 가지 않는다). 애니메이션·3D·등고선·수식 조판은 다루지 않는다.

상호작용은 브라우저가 SVG 에 대해 이미 하는 것까지다. `tooltip=True` 는 마크마다 `<title>` 을 붙이고 브라우저가 그것을 마우스오버 툴팁으로 띄운다. 그 이상 — 커서를 따라다니는 툴팁, 확대, 차트 간 연동 — 은 위치 계산이 필요하고 그건 JavaScript 다. 그리고 이것들은 SVG 를 페이지에 **인라인**했을 때만 동작한다: `<img>` 안의 SVG 는 별개 문서라 브라우저가 상호작용 없이 그린다.

GitHub 는 렌더된 markdown 에서 인라인 SVG 를 지운다. github.com 에서 보여야 하는 문서라면 `<img src="...svg">` 로 참조한다.

## 설치

PyPI 에 올리지 않았다. 저장소에서 바로 설치한다.

```bash
uv add "svgplot @ git+https://github.com/lovit/svgplot"
# 또는
pip install "git+https://github.com/lovit/svgplot"
```

PNG 출력에는 cairosvg 가 필요하다 — `uv add "svgplot[png] @ git+https://github.com/lovit/svgplot"`. cairosvg 는 시스템 libcairo 를 따로 요구한다. Python 3.12 이상.

## Quick start

모든 차트 함수는 long-form 데이터(pandas DataFrame, 컬럼 dict, dict 레코드 리스트)를 받아 `Chart` 를 돌려준다. `Chart` 는 `.save()` / `.to_string()` 과 Jupyter 표시를 지원한다.

```python
import svgplot as sp

data = {
    "요일": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "매출": [10.0, 15.0, 7.0, 20.0, 12.0, 6.0, 9.0, 4.0, 14.0, 8.0],
    "지역": ["서울", "서울", "서울", "서울", "서울", "부산", "부산", "부산", "부산", "부산"],
}

sp.lineplot(data, x="요일", y="매출", hue="지역").save("sales.svg")
```

`sales.svg` 안에서 두 지역의 선은 `class="series-1 line-series"` 와 `class="series-2 line-series"` 이고, 파일의 `<style>` 에 그에 대응하는 규칙이 있다.

```css
:where(.svgplot-ff989fa13) .series-1 { stroke: #E69F00; fill: none; stroke-width: 2; opacity: 1; }
```

앞의 `:where(.svgplot-…)` 는 이 규칙을 이 그림 안으로 묶는다. 한 HTML 문서에 차트를 둘 넣으면 둘 다 `.series-1` 을 정의하므로, 이것이 없으면 나중 차트가 앞 차트를 덧칠한다. `:where()` 는 특이도를 더하지 않으니 위 규칙의 무게는 `.series-1` 그대로이고, 호스트 스타일시트에서 `.series-1 { stroke: red }` 로 덮는 것도 그대로 동작한다. 이름을 직접 정하려면 `chart.set_scope("sales")`.

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

차트 16종 각각에 대해 그림과 그 그림을 만든 코드가 함께 있다. 갤러리 빌드가 페이지에 인쇄할 코드 문자열을 그대로 실행해 SVG 를 만든다.

## 그 밖의 기능

아래는 아직 전용 갤러리 페이지가 없다. 일부 인자는 일부 차트만 받고, 받지 않는 차트에 주면 `TypeError` 다.

전부:

- **`width=` / `height=`** — 기본 캔버스는 800x600, `sparkline` 만 120x24. 240x180 아래는 거부되고 여기서 면제되는 것도 `sparkline` 뿐이다(에러 문구는 "for an axed chart" 라고 하지만 축을 그리지 않는 `pieplot`·`treemap` 에도 적용된다)
- **`theme=`** — 프리셋 5종(`light` `dark` `minimal` `print` `high_contrast`), 컨텍스트 4종(`paper` `notebook` `talk` `poster`), `sp.parametric_theme("#3366cc")` 로 시드 컬러에서 팔레트 생성. 기본 팔레트는 색맹 안전(Okabe-Ito)
- **접근성** — `role="img"` · `aria-label` · `<title>` · `<desc>` 를 내보낸다. `<desc>` 는 제목을 되풀이하지 않고 차트 종류·데이터 규모·값 범위를 말한다

일부:

- **`tooltip=`** — `scatterplot` · `barplot` · `boxplot` · `violinplot` · `histplot` · `heatmap` · `treemap` · `regplot` · `gaugeplot` · `pieplot`. 마크마다 `<title>` 을 붙여 브라우저의 마우스오버 툴팁으로 만든다. 같은 것이 그 마크의 접근 가능한 이름이 되므로 점 무더기 하나가 아니라 이름 있는 마크 여러 개가 된다. 기본은 `False` 다 — 마크마다 요소가 하나씩 늘고, 켜면 기존 출력의 바이트가 바뀐다
- **`xscale=`** — `lineplot` · `scatterplot` · `areaplot`. **`yscale=`** — `lineplot` · `scatterplot`. `"linear"` / `"log"` 이고, 날짜 축에 `log` 는 거부된다
- **`estimator=`** — `lineplot` · `barplot` · `areaplot`. 같은 x 에 여러 행이 있을 때 `"mean"`/`"sum"`/`"median"` 등으로 접는다. 지정하지 않으면 차트별 기본 규칙이 적용되는데, 행을 버리면서 그 사실을 알리는 것은 `barplot` 뿐이다 — `AggregationWarning` 이 몇 행이 남았는지 말해준다(`areaplot` 은 합산하고 `lineplot` 은 둘 다 그리므로 잃는 것이 없다. `radarplot` 은 `estimator=` 를 받지 않으면서 `barplot` 과 같은 규칙으로 접는데 경고하지 않는다)
- **`info=`** — `lineplot` · `scatterplot` · `pieplot`. 차트가 실제로 그린 행만 담은 표를 함께 내보낸다. `tooltip=True` 를 함께 주면 `scatterplot`·`pieplot` 의 마크 툴팁도 같은 선언에서 나온다 — 선언 하나가 표와 툴팁을 함께 채우고, 짝은 마크 순번이 아니라 원본 행 번호로 맞춘다. 한 페이지에 `info=` 차트가 둘 이상이면 `Chart.set_table_id()` 로 표 `id` 를 나눠야 한다

그 밖:

- **`sp.row` / `column` / `grid`** — 차트 여러 개를 하나의 도판으로 합성. **`sp.add_caption`** 으로 도판에 캡션을 단다
- **`sp.facet`** — 아무 차트 함수나 그룹별로 반복 호출해 격자로. 패널은 기본적으로 축을 공유한다
- **`sp.apply_size(chart, "responsive")`** — `max-width:100%; height:auto` 규칙을 SVG 안에 넣는다(`viewBox` 는 원래 있다). 이 규칙은 SVG 를 호스트 DOM 에 인라인했을 때만 효과가 있다 — `<img>` 로 넣으면 크기를 정하는 것은 `<img>` 쪽이라 아무 일도 하지 않는다
- **출력** — `.save()` 는 확장자로 `.svg` / `.png` / `.md` 를 고른다. `.to_string()` · `.to_markdown()` · `.to_html_table()`

## 개발

```bash
curl https://mise.run | sh                       # 최초 1회
curl -LsSf https://astral.sh/uv/install.sh | sh
# gh: https://cli.github.com/ 설치 후 gh auth login — 이슈/PR 워크플로에 필요하다

mise install && mise run install                 # Python + 의존성 + git hook
mise run check                                   # lint + test (CI 와 동일)
```

개인 override 가 필요하면 `.claude/settings.local.json`(예시는 [`.claude/settings.local.json.example`](.claude/settings.local.json.example))과 `mise.local.toml` 을 만든다. 둘 다 gitignore 대상이다.

워크플로·커밋 규칙·스타일 규칙은 [`CLAUDE.md`](CLAUDE.md) 와 [`.claude/rules/`](.claude/rules/) 에 있다. 설계 배경(pygal·matplotlib·seaborn·Bokeh 기능 조사와 그로부터 도출한 결정)은 [`docs-research/00-overview.md`](docs-research/00-overview.md).

## 라이선스

MIT License — [`LICENSE`](LICENSE) 참고.
