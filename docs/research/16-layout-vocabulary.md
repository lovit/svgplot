# 다중 차트 레이아웃 어휘 — 여러 차트를 하나의 "도판"으로 조직하기

Bokeh의 레이아웃 시스템(`04-bokeh.md` A10)에서 인터랙션 관련 부분(공유 툴바, 실시간 연동)을 걷어내고, **markdown에 박히는 정적 SVG/HTML을 위한 레이아웃 API**로 재설계한 안이다.

## 설계 원칙

1. **2계층이면 충분하다.** Bokeh는 `row`/`column`(1D) → `layout`(재귀 1D) → `grid`/`GridBox`(2D) → `gridplot`(2D+툴바)의 4단계지만, 툴바 병합이 무의미해지는 순간 `gridplot`과 `grid`가 사실상 같아진다. 새 패키지는 **`row`/`column`(1D 나열) + `grid`(2D, span 지원)** 두 함수만으로 Bokeh의 표현력을 대부분 커버한다.
2. **CSS Grid를 그대로 노출한다.** Bokeh의 `GridBox.children`이 `(child, row, col, rowspan, colspan)` 튜플이라는 사실 자체가 CSS Grid 문법의 재발명이다. 새 패키지는 처음부터 "Python 배치 함수 → CSS Grid 속성 직접 생성"으로 설계해 Bokeh보다 한 단계 더 직접적으로 구현한다.
3. **레이아웃 함수는 배치만 책임지고, 축/색상/범례 정렬은 별개의 데이터 레벨 문제로 분리한다.** Bokeh 조사에서 확인했듯 `row`/`column`/`grid`에 넣는다고 축이 자동 정렬되지 않는다 — 이건 레이아웃 문법이 아니라 "동일한 domain/scale 객체를 여러 subplot에 전달"하는 문제다. 새 패키지도 이 분리를 유지한다(레이아웃 API는 "어디에 놓을지"만, "축을 맞출지"는 `shared_x=`/`shared_color=` 같은 별도 파라미터로).

## 제안 API

```python
import svgpkg as sp

# 1D 나열 — Bokeh row()/column() 대응
sp.row([chart1, chart2, chart3], spacing=12)
sp.column([chart1, chart2], spacing=12)

# 2D 그리드 — Bokeh grid()/GridBox 대응, span 지원
sp.grid([
    [chart1, chart2],
    [None,   chart3],   # Bokeh의 None-빈칸 관용구 그대로 채택
], ncols=2, spacing=12)

sp.grid([
    (chart1, 0, 0, 1, 2),   # (chart, row, col, rowspan, colspan)
    (chart2, 1, 0, 1, 1),
    (chart3, 1, 1, 1, 1),
])

# 공통 캡션 — "공유 툴바"가 주던 시각적 통일감의 정적 대체
sp.grid([[c1, c2]], caption="Figure 3. 분기별 매출 추이", caption_location="below")
```

## sizing_mode → 2종으로 축소

| Bokeh 원본(8종) | 새 패키지 | 구현 |
|---|---|---|
| `fixed` | `size="fixed"`(기본) | SVG `width`/`height` 고정, `viewBox` 없음 |
| `scale_width` | `size="responsive"` | `viewBox="0 0 W H"` + CSS `max-width:100%; height:auto` — 비율 유지하며 뷰어 폭에 맞춤 |
| `stretch_width`/`stretch_height`/`stretch_both`/`scale_height`/`scale_both`/`inherit` | (폐기) | "뷰포트 높이"에 의존하는 개념은 세로 스크롤되는 markdown 문서에서 무의미 |

## Tabs 대체 관용구

Bokeh의 `Tabs`(탭 전환)는 markdown 임베드에서 **완전히 재현 불가**하다 — `<img src=".svg">`는 이미지 컨텍스트라 SVG 내부의 `:target`/`:checked` CSS 트릭조차 무력화된다. 세 가지 대체안을 제시하고 기본값을 정한다.

1. **기본안 — 전부 펼쳐서 소제목으로 나열.** `sp.column([chart_a, chart_b], titles=["연도별", "지역별"])`처럼 각 차트 위에 markdown 소제목(`###`)을 자동 삽입. markdown 네이티브라 어디서나 100% 동작하므로 **이걸 기본 동작으로 채택**.
2. **GitHub 한정 차선책 — `<details><summary>` 접기/펼치기.** GitHub Flavored Markdown은 이걸 스크립트 없이 네이티브로 지원한다. 단 이건 SVG 내부가 아니라 **markdown 소스 레벨**에 있어야 하므로, 패키지가 SVG 파일 하나만 뱉는 게 아니라 "SVG를 감싼 markdown 조각"까지 생성하는 옵션을 제공해야 가능(`sp.column(..., collapsible=True)` → 저자가 markdown에 그대로 붙여넣을 `<details>` 블록을 함께 출력).
3. **순수 SVG만 원할 때 — 탭 개념을 요약-상세 패턴으로 재해석.** 미니어처 여러 개를 그리드로 보여주고 그 아래 큰 "메인 뷰" 하나를 두는 구성. 탭이 하던 "선택"을 없애고 "전부 보이되 위계를 준다"로 치환.

## `GroupBox`/`ScrollBox` 처리

- `GroupBox`(제목+테두리 그룹핑) → 낮은 리스크로 v1.0 포함 가능. 그리드 셀 주변에 `<rect>` 테두리 + `<text>` 라벨을 그리는 것뿐이므로 구현이 단순하다.
- `ScrollBox`(스크롤 컨테이너) → 제외. 정적 문서는 문서 자체가 스크롤되는 캔버스이므로 "내부 스크롤"이라는 개념이 없다.

## MVP 스코프 판정

| 기능 | 판정 | 근거 |
|---|---|---|
| `row`/`column`(1D 나열, spacing, None 빈칸) | 필수 | 구현 비용 낮음, 수요 확실 |
| `grid`(2D, span 지원) | 필수 | CSS Grid 위임이라 구현 비용 낮음, "도판" 요구의 핵심 |
| 공통 캡션(그리드 상단/하단 타이틀) | 필수 | "공유 툴바"의 시각적 통일감을 대체하는 저비용 장치 |
| `size="fixed"`/`"responsive"` 2종 | 필수 | 8종 중 실제로 쓸모 있는 것만 |
| 소제목 자동 나열(Tabs 대체 기본안) | 필수 | markdown 네이티브, 추가 구현 거의 없음 |
| `GroupBox`류 그룹 테두리 | 2차 | 저비용이지만 우선순위 낮음 |
| `<details>` 접기/펼치기 markdown 조각 생성 | 2차 | GitHub 한정이라 범용성 낮음, v1.0 이후 |
| 축/색상 자동 정렬(`shared_x=` 등) | 2차 | 레이아웃 API와 분리된 별도 기능, 데이터 도메인 설계와 함께 검토 |
