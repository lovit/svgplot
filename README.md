# svgplot

markdown 문서에 박아넣을, 심미성 있고 수정이 쉬운 정적 SVG 차트를 만드는 Python 패키지.

matplotlib/seaborn에 익숙한 문법으로 SVG를 만들되, pygal보다 데이터 시맨틱 매핑(`hue=`, `data=`)과 접근성을 갖추고,
matplotlib보다 렌더 후에도 CSS로 재테마 가능한 SVG를 목표로 한다. 설계 배경은 [`docs/research/`](docs/research/00-overview.md)를 참고
(pygal/matplotlib/seaborn/Bokeh 기능 조사와 그로부터 도출한 설계 결정).

## 사용법

모든 `*plot()` 함수는 long-form 데이터(pandas DataFrame, 컬럼 dict, dict 레코드 리스트)를 받아 `Chart`를 돌려주고, `Chart`는 `.save()`/`.to_string()`/Jupyter 표시를 지원한다. 아래 예제들은 이 데이터를 공유한다.

```python
import svgplot as sp

data = {
    "day": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "sales": [10.0, 15.0, 7.0, 20.0, 12.0, 6.0, 9.0, 4.0, 14.0, 8.0],
    "size": [1.0, 3.0, 2.0, 5.0, 4.0, 2.0, 1.0, 3.0, 5.0, 2.0],
    "region": ["서울", "서울", "서울", "서울", "서울", "부산", "부산", "부산", "부산", "부산"],
}
```

### 차트 타입

```python
# 선 그래프 — hue=로 시리즈 분리, interpolate=로 보간(quadratic/cubic/hermite/lagrange/trigonometric)
sp.lineplot(data, x="day", y="sales", hue="region").save("line.svg")

# 산점도 — hue=는 색상, size=는 마커 크기에 매핑
sp.scatterplot(data, x="day", y="sales", hue="region", size="size").save("scatter.svg")

# 막대 — orient="v"|"h", stacked=True면 누적, hue=만 주면 그룹(dodge)
sp.barplot(data, x="region", y="sales", hue="region", stacked=True).save("bar.svg")

# 히스토그램 — bins는 정수 또는 전략 문자열("auto" 기본)
sp.histplot(data, x="sales", bins=5).save("hist.svg")

# 영역 — stacked=True면 누적 영역
sp.areaplot(data, x="day", y="sales", hue="region", stacked=True).save("area.svg")

# 파이 — inner_radius > 0이면 도넛(외곽 반지름 대비 비율)
sp.pieplot(data, values="sales", labels="region", inner_radius=0.5).save("pie.svg")

# 박스플롯 — mode는 extremes / 1.5IQR / tukey / stdev / pstdev
sp.boxplot(data, x="region", y="sales", mode="1.5IQR").save("box.svg")

# hue=는 카테고리 *안에서* 한 번 더 나눈다 — 밴드가 그룹 수만큼 쪼개져 나란히 그려진다
sp.boxplot(data, x="region", y="sales", hue="day").save("box-hue.svg")
```

### 분포와 회귀

```python
# 경험적 누적분포 — stat="proportion"|"count", complementary=True면 생존함수
sp.ecdfplot(data, x="sales", hue="region").save("ecdf.svg")

# 커널 밀도 — bandwidth는 "scott"|"silverman" 또는 수치, fill=True면 축까지 채움
# hue 그룹은 하나의 x 그리드를 공유하므로 곡선끼리 직접 비교된다
sp.kdeplot(data, x="sales", hue="region", fill=True).save("kde.svg")

# 바이올린 — boxplot과 위치 인자 (data, x, y, hue)가 같다(키워드는 다르다 — mode= 없음)
# inner="box"면 사분위 상자와 중앙값을 겹친다
# 모든 카테고리가 하나의 y 도메인과 하나의 peak을 공유해 폭이 비교 가능하다
sp.violinplot(data, x="region", y="sales", inner="box").save("violin.svg")

# 선형 회귀 — ci는 신뢰수준(None이면 대역 없이 선만), seed로 부트스트랩이 재현된다
sp.regplot(data, x="day", y="sales", ci=0.95, seed=0).save("reg.svg")
```

### 형태 차트

축이 있는 차트로는 잘 읽히지 않는 모양들이다. `radarplot`/`gaugeplot`은 직교축 대신 자기 눈금(스포크와 링, 아크 눈금)을 그리고, `treemap`/`sparkline`은 눈금이 아예 없다. `heatmap`만 예외로 카테고리 축 위에 셀을 올리므로 스파인과 눈금 라벨을 그대로 가진다.

```python
# 히트맵 — 값을 9단계로 양자화해 색을 고른다(연속 램프가 아닌 이유는 모듈 docstring 참조)
# annot=True는 셀 값을 써넣고, 잉크 색은 셀 색의 휘도에서 고른다
sp.heatmap(data, x="day", y="region", values="sales", annot=True).save("heatmap.svg")

# center=는 발산 컬러맵과 함께 준다 — 가운데 단계가 "중심값"을 뜻하게 된다
# cmap=은 기본값이 sequential("blues")이므로 반드시 같이 바꿔야 한다
sp.heatmap(data, x="day", y="region", values="sales",
           cmap="coolwarm", center=10.0).save("heatmap-diverging.svg")

# 레이더 — x의 각 카테고리가 스포크, 시리즈마다 닫힌 다각형 하나
# 눈금 링은 원이 아니라 다각형이라 모든 스포크를 그 눈금이 말하는 값에서 지난다
sp.radarplot(data, x="day", y="sales", hue="region").save("radar.svg")

# 트리맵 — squarified(Bruls 2000), 단일 레벨. 면적이 값에 비례한다
sp.treemap(data, values="sales", labels="region").save("treemap.svg")

# 스파크라인 — 축도 범례도 라벨도 없는 120x24 미니 캔버스. 문장 안에 넣으라고 있는 것
sp.sparkline(data, y="sales").save("spark.svg")
```

`gaugeplot`은 이 패키지의 차트 중 유일하게 데이터 모델이 **비교가 아니라 스칼라**다. x/y 채널이 없고 `pieplot`처럼 단일 `value` 컬럼을 받으므로, 위 long-form 데이터가 아니라 자기 모양의 데이터를 쓴다.

```python
# 게이지 — [vmin, vmax] 안에서 값이 어디쯤인지. 범위 밖 값은 양 끝으로 클램핑된다
# 여러 행은 하나의 범위를 공유하는 동심 아크가 된다(pygal SolidGauge 모델)
sp.gaugeplot({"metric": ["가동률", "적중률"], "score": [72.0, 91.0]},
             "score", labels="metric", vmax=100).save("gauge.svg")
```

### 같은 x 의 여러 행 — `estimator=`

`bar`/`area`/`line`은 같은 x 를 가진 여러 행을 하나의 마크로 접는다. 접는 규칙은 차트마다 다르고 모두 기본값이다 — `bar`는 **마지막 행이 이기고**(나머지는 버려진다), `area`는 **합산**하며, `line`은 **두 꼭짓점을 모두** 그린다(x 가 같으므로 수직 선분이 된다).

```python
sp.barplot({"x": ["a", "a", "a"], "y": [10.0, 20.0, 60.0]}, x="x", y="y")
# 막대 하나가 60(마지막 행)으로 그려지고, AggregationWarning 이 몇 행을 버렸는지 알려준다

sp.barplot({"x": ["a", "a", "a"], "y": [10.0, 20.0, 60.0]}, x="x", y="y", estimator="mean")   # 30
sp.barplot({"x": ["a", "a", "a"], "y": [10.0, 20.0, 60.0]}, x="x", y="y", estimator="median") # 20
sp.barplot({"x": ["a", "a", "a"], "y": [10.0, 20.0, 60.0]}, x="x", y="y", estimator=min)      # 10
```

`estimator=`는 `"mean"` / `"median"` / `"sum"` 또는 그룹의 값을 **행 순서대로** 받아 숫자를 돌려주는 callable 을 받는다. 기본값 `None`은 위의 기존 규칙을 그대로 둔다 — 기본값을 `"mean"`으로 바꾸면 seaborn 과 맞지만 이미 만들어 둔 모든 차트가 조용히 다시 그려진다. 대신 **행이 실제로 버려질 때만** 경고한다(`bar`뿐이다 — `area`는 합산하고 `line`은 둘 다 그리므로 잃는 것이 없다).

```python
import warnings

warnings.filterwarnings("ignore", category=sp.AggregationWarning)   # 경고만 끄기
```

나머지 차트가 `estimator=`를 받지 않는 이유는 `charts/_aggregate.py`에 적혀 있다 — 분포 차트(`hist`/`kde`/`ecdf`/`box`/`violin`)는 퍼짐 자체가 그림이라 미리 접으면 지워지고, `scatter`/`pie`/`treemap`/`gauge`는 1행 = 1마크이며, `heatmap`은 중복 셀을 접는 대신 **거부**한다. `lineplot`에서는 `estimator=`와 `info=`를 함께 줄 수 없다 — 각주 표는 "1행 = 1마크"를 전제하는데 집계가 바로 그 전제를 깬다.
### 차트 크기

`sparkline`을 뺀 15종이 `width=` / `height=`를 받는다. 둘 다 기본값은 `None`이고, 그때 800×600이 되므로 **기존 호출의 출력은 한 바이트도 바뀌지 않는다**.

```python
sp.lineplot(data, x="day", y="sales", width=400, height=300).save("narrow.svg")
sp.lineplot(data, x="day", y="sales", width=500)                 # 높이는 기본값 600
```

작은 캔버스에서 무너지지 않도록 두 가지가 함께 움직인다. **마진**은 가로/세로 각각 캔버스의 45%를 넘지 않게 같은 비율로 줄어든다 — 프리셋이 절대 픽셀값이라, 그대로 두면 폭 300에서 플롯 영역이 80px밖에 남지 않는다(300 − 160 − 60). 줄인 뒤 300×240 캔버스에는 165×160이 남는다 — 캔버스를 밝히는 이유는 세로 여백도 같이 줄기 때문이다(같은 폭이라도 300×220이면 165×140이다). **눈금 개수**는 플롯 영역 길이에 따라 정해지며, 기준은 기본 크기가 이미 쓰는 밀도(가로 128px·세로 104px당 눈금 하나)라서 800×600에서는 지금과 똑같은 5개가 나온다. 최소 2개, 최대 10개로 묶인다.

**240×180보다 작은 캔버스는 거부한다**(`ValueError`). 240은 범례 여백에서 나온 실측 하한 **두 개를 넘는** 값이다 — 마진 축소 후 범례 글자에 남는 자리가 `0.32727 × 폭 − 42`px이고, 라벨 축약이 더는 도움이 되지 않는 지점(2.4em)을 대입하면 209.0px, 다섯 글자 라벨이 잘리지 않고 들어가는 지점을 대입하면 227.5px이다. 240은 둘 다를 넘으면서 기본값과 같은 4:3(180)을 이루는 값이고, 240 자체가 경계는 아니다. 여백보다 긴 라벨은 더 넓은 캔버스를 요구하지 않는다 — 줄임표로 축약하고 전문을 `<title>`에 남긴다(보조기술이 읽는다).

**카테고리 라벨이 밴드에 들어가지 않으면 45도로 눕는다.** 자동이라 들어가는 라벨은 지금 그대로 수평이고, 기본 크기 출력은 바뀌지 않는다. 눕히는 쪽이 축약보다 나은 이유는 예산이 달라지기 때문이다 — 수평 라벨의 예산은 밴드 폭이라 카테고리가 늘수록 줄어들지만, 눕힌 라벨의 예산은 하단 여백이라 카테고리 수와 무관하다. 실측으로, 카테고리 8개(`2024년 N분기 실적 요약`)를 폭 600에 그리면 예전에는 여덟 라벨이 전부 `2024…`로 줄어 **축이 카테고리를 구분하지 못했고**, 지금은 폭 300까지 여덟 개가 서로 다르게 남는다. `barplot`(세로)·`boxplot`·`violinplot`·`heatmap`에 적용되며, 숫자 축은 대상이 아니다(숫자 라벨은 값 자체라 여백을 넓히는 쪽이 맞고, 눕히면 읽기만 나빠진다).

차트가 스스로 더 큰 최소치를 갖는 경우도 있고, 그때는 그 차트가 자기 한계를 말한다 — 범례 행이 캔버스 아래로 넘치면(`heatmap`의 9단계 범례는 상단 여백 아래로 168px 의 잉크를 놓아 캔버스 높이 198px 을 요구한다) 잘라 그리는 대신 거부하고, `gaugeplot`은 링 두께 규칙이 먼저 걸린다.

### 축 스케일

`lineplot`과 `scatterplot`이 `xscale=` / `yscale=`을 받는다. `"linear"`(기본)이거나 `"log"`다.

```python
# 공유 데이터는 자릿수로 벌어지지 않으므로 여기서는 그런 값을 직접 쓴다
latency = {"requests": [10.0, 100.0, 1000.0, 10000.0], "ms": [1.0, 12.0, 130.0, 1400.0]}

sp.scatterplot(latency, x="requests", y="ms", yscale="log").save("latency.svg")
sp.lineplot(latency, x="requests", y="ms", xscale="log", yscale="log").save("scaling.svg")
```

로그축이 필요한 자리는 응답시간·파일 크기·인구·벤치마크 배수처럼 값이 자릿수로 벌어지는 데이터다. 선형축에서는 작은 값들이 한 픽셀에 뭉개져 차트가 답을 못 준다 — 1부터 1e6까지 걸친 네 점을 실제로 그려 보면, 선형축에서는 앞의 두 점이 **0.05px** 떨어져 사실상 한 픽셀에 겹치고 세 번째까지도 5.2px 안에 들어온다. 로그축에서는 세 간격이 모두 **173.33px**로 똑같다 — 자릿수가 같은 간격으로 벌어지는 것이 로그축의 정의다.

눈금은 10의 거듭제곱에 서고, 한 자릿수 안에 갇힌 도메인은 둥근 선두 숫자(1 / 1,3 / 1,2,5 / …)로 잘게 나눈다. 그것으로도 눈금이 모자랄 만큼 비율이 좁으면(2..3에는 둥근 가수가 둘뿐) 선형 눈금으로 넘어간다 — 그 비율에서 로그축은 시각적으로 거의 선형이고, 가수를 더 쪼개면 `2.15443469` 같은 것이 축에 선다.

**0과 음수는 컬럼명을 대고 거부한다.** matplotlib은 `nonpositive="mask"|"clip"`을 주지만, 전자는 세어 놓은 행을 버리고 후자는 없던 값을 지어낸다 — 둘 다 데이터가 말하지 않는 차트를 그린다. **날짜 컬럼도 거부한다**: 타임스탬프의 로그는 1970을 0으로 골랐다는 사실에서만 나오는 비율이라 2000→2020이 1.67배로 읽힌다.

`areaplot`은 `xscale=`만 받는다. 영역 차트의 채워진 면적이 곧 값이고 그것은 0에서 재는데, 로그축에는 잴 0이 없어 채움이 임의의 자리에서 시작하고 면적이 무엇에도 비례하지 않게 된다.

### 여러 차트를 하나의 도판으로

`row`/`column`/`grid`는 `Chart`와 동일한 인터페이스를 가진 `Composition`을 돌려주므로 그대로 저장할 수 있다. `None`은 빈 칸이고, `titles=`는 각 칸 위에 소제목을 붙인다(markdown에서 재현 불가능한 탭 UI의 정적 대체).

```python
figure = sp.row([sp.lineplot(data, x="day", y="sales"), sp.barplot(data, x="region", y="sales")], spacing=16)
sp.add_caption(figure, "Figure 1. 지역별 매출")
figure.save("figure.svg")

sp.grid(
    [[sp.lineplot(data, x="day", y="sales"), sp.histplot(data, x="sales")], [None, sp.boxplot(data, x="region", y="sales")]],
    spacing=12,
    titles=["추이", "분포", None, "지역별"],
).save("grid.svg")
```

### 패싯

`facet`은 임의의 차트 함수를 그룹별로 반복 호출해 격자로 배치한다. `col=`만 주면 가로, `row=`만 주면 세로, 둘 다 주면 2D 격자가 된다.

```python
sp.facet(sp.lineplot, data, col="region", x="day", y="sales").save("facet.svg")
```

패널은 **기본적으로 축을 공유한다**(`sharex=False`/`sharey=False`로 끌 수 있다). 공유하지 않으면 두 패널의 선이 같은 높이에 그려지는데 하나는 3, 다른 하나는 300이고 그 사실이 지면 어디에도 적히지 않는다.

```python
sp.facet(sp.lineplot, data, col="region", x="day", y="sales", sharey=False)
```

### 테마

기본 팔레트는 색맹 안전(Okabe-Ito)이며, 스타일은 렌더 후에도 CSS 클래스로 재정의할 수 있다.

```python
sp.lineplot(data, x="day", y="sales", theme="dark")                                  # 내장 프리셋
sp.lineplot(data, x="day", y="sales", theme=sp.parametric_theme("#3366cc"))          # 브랜드 시드 컬러
sp.lineplot(data, x="day", y="sales", theme=sp.apply_context(sp.PRESETS["light"], "poster"))  # 발표용 확대
```

내장 프리셋은 `light` / `dark` / `minimal` / `print` / `high_contrast`, context는 `paper` / `notebook` / `talk` / `poster`다.

### 출력

```python
chart = sp.apply_size(sp.lineplot(data, x="day", y="sales"), "responsive")  # viewBox + max-width:100%
markup = chart.to_string()      # SVG 문자열 (pretty-print)
chart.save("chart.svg")          # 파일로 저장
chart.save("chart.png")          # PNG는 optional dep: uv add "svgplot[png]"
chart.save("chart.md")           # 인라인 SVG + (info= 있으면) 각주 표
```

`info=`를 주면 차트가 실제로 그린 행만 담은 표가 `.md` 출력에 함께 실린다. 1행 = 1마크인 `lineplot`/`scatterplot`/`pieplot`이 대상이다 — 여러 행을 하나의 마크로 접는 차트(`bar`는 같은 카테고리의 마지막 행이 이기고, `area`는 합산하며, `box`/`hist`는 버킷에 넣는다) 옆에 원본 행 표를 붙이면 표와 그림이 서로 다른 말을 하게 된다.

```python
chart = sp.lineplot(data, x="day", y="sales",
                    info=[("날짜", "@day{0,0}"), ("매출", "@sales{0,0}")])
chart.save("chart.md")
markdown = chart.to_markdown()
```

포맷은 선택이다. 중괄호를 빼면 값이 그대로 실린다 — 텍스트 컬럼을 표에 넣는 방법이고, 숫자에는 축이 쓰는 것과 같은 표기가 적용된다(`2.0`이 아니라 `2`).

```python
sp.lineplot(data, x="day", y="sales",
            info=[("지점", "@region"), ("매출", "@sales{0,0}")])   # 이름은 그대로, 금액은 천 단위 구분
```

`@field{}`(빈 중괄호)는 계속 거부한다 — 포맷을 안 쓰기로 한 것과 쓰려다 만 것은 다르다.

GitHub는 렌더된 markdown에서 인라인 SVG를 제거하므로 github.com에서는 표만 보인다. MkDocs·Sphinx·VS Code 미리보기에서는 도판과 표가 함께 렌더된다.

### 접근성

모든 차트가 `role="img"` · `aria-label`(제목) · `<title>` · `<desc>`를 내보낸다. `<desc>`는 차트 종류, 데이터 규모, 값 범위를 실제로 말한다 — 제목을 되풀이하지 않는다.

```python
sp.barplot({"x": ["Mon", "Tue", "Wed"], "y": [1.0, 5.0, 9.0]}, x="x", y="y").to_string()
# <desc>Bar chart, 3 categories (Mon, Tue, Wed), values 1 to 9.</desc>

sales = {"region": ["east", "west", "east"], "quarter": ["Q1", "Q1", "Q2"], "amount": [1.0, 2.0, 3.0]}
sp.heatmap(sales, x="region", y="quarter", values="amount").to_string()
# <desc>Heatmap, 2 columns (east, west), 2 rows (Q1, Q2), 3 of 4 cells filled, values 1 to 3, quantised into 9 levels.</desc>
```

문장은 영어다(패키지의 다른 접근성 문구와 같다). 그 안의 카테고리·시리즈 이름은 데이터에 쓰인 언어 그대로이므로 `lang` 속성은 붙이지 않는다 — 섞인 문장에 한 언어를 못 박으면 나머지 절반을 잘못 읽게 만든다. 이름은 최대 6개, 합쳐서 60자까지만 나열하고 나머지는 `and N more`로 센다. 이름을 잘라 줄이는 일은 없다(잘린 이름은 다른 이름이다). 첫 이름조차 한도를 넘으면 괄호 전체를 생략하고 개수만 말한다.

`info=`로 표를 붙이면 SVG root가 `aria-describedby`로 그 표를 참조한다. 참조는 **호스트 HTML 문서 안에서만** 성립하므로 표를 같은 페이지에 함께 내보내야 한다.

```python
chart = sp.lineplot(data, x="day", y="sales", info=[("날짜", "@day{0,0}"), ("매출", "@sales{0,0}")])
page = chart.to_string() + chart.to_html_table()   # <svg aria-describedby="svgplot-data-table"> + <table id="svgplot-data-table">
chart.set_table_id("sales-table")                  # 한 페이지에 차트가 둘 이상이면 id를 나눈다
```

`.md` 출력에는 이 속성이 붙지 않는다 — GFM 표는 `id`를 실을 요소가 없어서 참조가 허공을 가리키게 되기 때문이다. 그 경우 보조 기술은 `<desc>`를 읽는다.

합성 도판(`row`/`column`/`grid`/`facet`)에는 이 참조가 붙지 않는다 — 자식 차트의 원본 문서를 중첩하므로 도판은 자기 이름 하나만 갖는다. 표를 함께 내보내도 가리키는 쪽이 없다.

주의: `info=`가 있으면 `to_string()`은 표를 실제로 내보냈는지와 무관하게 참조를 붙인다. 표를 함께 내보내지 않으면 참조는 해소되지 않고(무해하게 무시된다) `<desc>`가 읽힌다. 그리고 기본 `id`는 모든 차트가 공유하므로, 한 페이지에 `info=` 차트가 둘 이상이면 반드시 `set_table_id()`로 나눠야 한다 — 그러지 않으면 두 번째 차트가 첫 번째 차트의 표로 설명된다.

## 부트스트랩

```bash
# 0. mise, uv, gh 설치(최초 1회)
curl https://mise.run | sh
curl -LsSf https://astral.sh/uv/install.sh | sh
# gh: https://cli.github.com/

# 1. Python 버전 설치 + 의존성 동기화 + git hook 등록
mise install
mise run install

# 2. 동작 확인
mise run check
```

## 개발 워크플로

```
/start-issue "기능 설명"   # GitHub 이슈 생성 + worktree branch 분기
    ↓
코드 작업
    ↓
/commit                    # 의미 단위로 분리해 한국어 conventional commit
    ↓
/review                    # 4개 sub-agent 병렬 리뷰
    ↓
/open-pr                   # PR 생성 (Closes #N 자동 포함)
    ↓
머지 전: CI green + /review Approve 둘 다 필수
    ↓
머지 후: /worktree-clean   # 완료된 worktree/브랜치 정리
```

자세한 규칙: [`.claude/rules/branch.md`](.claude/rules/branch.md)

## 커밋 규칙

- **형식**: `<type>(<scope>): <한국어 설명>`
- **type**: `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `style` / `perf`
- **원칙**: 한 commit = 한 의도. 리팩터링과 기능 추가를 섞지 않는다.

예시:
```
feat(theme): 시드 컬러 기반 파라메트릭 팔레트 추가
fix(svg): 그룹 막대 라벨이 겹치는 문제 수정
refactor(core): 렌더러를 mark 프리미티브 기반으로 분리
```

## Python 도구 체인

```bash
mise install                # Python 버전 설치
mise run install             # uv sync + prek install
mise run lint                # prek run --all-files
mise run test                # pytest
mise run check                # lint + test (CI와 동일)

uv add <package>             # 의존성 추가
uv add --dev <package>       # dev 의존성 추가
uv sync                      # lock 파일 기준으로 환경 동기화
uv run <command>             # 가상 환경 안에서 명령 실행
uv run ruff check . --fix    # lint + 자동 수정
uv run ruff format .         # 포매팅
uv run pytest                # 테스트 실행
```

## 로컬 설정 (선택)

개인 override 가 필요하면 `.claude/settings.local.json` 을 생성한다 (gitignore 됨).
예시는 `.claude/settings.local.json.example` 참고. 환경변수/비밀값 로컬 override 는
`mise.local.toml`(gitignore 됨)의 `[env]` 테이블에 추가한다.

## 사전 조건

- [mise](https://mise.jdx.dev/) 설치: `curl https://mise.run | sh`
- [uv](https://docs.astral.sh/uv/) 설치: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [gh](https://cli.github.com/) 설치 + 인증: `gh auth login`
- Claude Code CLI 설치

## 라이선스

MIT License — [`LICENSE`](LICENSE) 참고.
