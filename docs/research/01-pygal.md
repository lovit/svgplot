# pygal — 기능 범위 조사 (8축)

레포: `references/pygal` · 버전 3.1.3 · 7.9k LOC(테스트 제외) · 최근 1년 27 commits(저활성)

---

## A1. 차트 타입 인벤토리

24개 공개 차트 클래스. 계열별 정리:

| 계열 | 클래스 | 비고 |
|---|---|---|
| Bar | `Bar`, `StackedBar`, `HorizontalBar`, `HorizontalStackedBar`, `Histogram` | Horizontal*은 `HorizontalGraph` 믹스인으로 축만 전치(transpose) |
| Line | `Line`, `StackedLine`, `HorizontalLine`, `HorizontalStackedLine`, `XY` | XY는 `Line`+`Dual`(좌표쌍 값 모델) |
| Time | `DateTimeLine`, `DateLine`, `TimeLine`, `TimeDeltaLine` | 새 렌더 로직 없음 — XY의 x축 어댑터(`_x_adapters`)만 다름 |
| 원형 | `Pie`, `Radar`, `Gauge`, `SolidGauge` | Radar는 `PolarView` 위의 Line |
| 기타 | `Dot`, `Funnel`, `Box`, `Treemap`, `Pyramid`, `VerticalPyramid` | Pyramid류는 StackedBar를 홀/짝 인덱스로 좌우 분리 |
| 지도 | (외부 플러그인, `pygal_maps_world` 등) | `entry_points(group="pygal.maps")`로 동적 로드, 조사 범위 밖 |

**mark 프리미티브 분석**: 24개 클래스는 사실상 5~6개 마크(rect/path+circle/arc/polygon/rect+line)의 조합으로 수렴한다. 다중상속(mixin) 기반이라 API 표면은 넓어 보이지만 실제 자유도는 "mark × 방향(수직/수평) × 누적여부"의 조합에 가깝다.

## A2. 데이터 입력·시맨틱 매핑

`add(title, values, **kwargs)` 하나가 유일한 진입점. `values`는 아래를 모두 관대하게 받는다:

- flat list: `[0, 1, 1, 2, ...]`
- dict: `{'x_label': value}` — `x_labels`에 이미 있는 키와 매칭
- `None` 포함 리스트: 결측치, `allow_interruptions`로 선을 끊을지 보간할지 결정
- dict 원소: `{'value': v, 'label': ..., ...}` — point-level metadata(툴팁 등)
- tuple 원소: `(x, y)`(Dual 차트), Histogram은 `(count, low, high)` 3-tuple

`secondary=True`(보조 y축), `formatter`(시리즈별 값 포맷터) 등을 `add()` kwarg로 지정.

**hue/size 같은 컬럼 기반 시맨틱 채널 매핑은 전혀 없다.** 색상은 시리즈 순번 → 팔레트 자동 할당이며, DataFrame/Series 네이티브 지원도 없다. 이것이 pygal의 가장 근본적인 데이터 모델 한계다.

## A3. API 문법

**객체형(stateful object) API** — matplotlib pyplot과 달리 전역 암묵 상태가 없다. 각 차트가 독립 객체이며 그 안에서만 상태(`raw_series`)가 지연 누적되다가 `render()` 시점에 처리된다.

세 가지 진입 문법이 모두 동일한 내부 표현으로 수렴:
```python
# 1) 전통적: 생성자 → 속성 대입 → add 체이닝
bar_chart = pygal.HorizontalStackedBar()
bar_chart.title = "Remarquable sequences"
bar_chart.add('Fibonacci', [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55])

# 2) 생성자 kwargs + __call__ 단축 문법
bar_chart = pygal.HorizontalStackedBar(title="...", x_labels=map(str, range(11)))(
    0, 1, 1, 2, 3, title='Fibonacci')
```
`__call__` 단축 문법은 pygal 고유 관용구로 matplotlib/seaborn 사용자에게는 낯설다.

render 계열(`render`, `render_to_file`, `render_to_png`, `render_data_uri`, `render_response`, `render_django_response`, `render_table`, `render_sparktext`, `render_sparkline` 등)이 출력 타겟마다 얇은 어댑터로 분리되어 있다.

### CJK 하위질문
`Style.__init__`이 `*_font_family`(8종)를 순회하며 `None`이면 전역 `font_family`를 상속, `googlefont:` 프리픽스가 있으면 Google Fonts로 처리한다. 그러나 **CJK 폰트 fallback이나 language-aware 처리는 코드에 없다.** `svg.py`의 텍스트 노드 생성 함수도 폰트/정렬을 다루는 공용 헬퍼가 없고, `text-anchor`는 개별 차트(Pie/Gauge)에서 하드코딩될 뿐이다. **CJK는 pygal에서 참고할 선례가 없다.**

## A4. 스타일·테마 시스템

`pygal/config.py`에 `Key(...)` 선언 86개(유니크 83개), 6개 카테고리(Look 34/Value 16/Label 14/Text 8/Misc 10/Style 3)로 분류. `Key` 객체가 이름/기본값/타입/카테고리/문서를 한 곳에 묶어 자동 문서화까지 지원하는 선언형 메타데이터 구조.

테마는 `Style`을 상속하는 파이썬 클래스로, 클래스 속성 재정의만으로 성립(`LightSolarizedStyle(DarkSolarizedStyle)`처럼 상속 체인도 활용). `Style` 인스턴스는 `to_dict()`로 직렬화되어 Jinja 템플릿(`style.css`)에 주입된다.

커스터마이징 경로 2가지: (1) `Style(**kwargs)` 즉석 인스턴스, (2) parametric style — 단일 base color + step으로 팔레트 자동 파생, `base_style`로 기존 테마의 비-color 속성 상속 가능.

## A5. 컬러 팔레트 엔진

16개 built-in 테마(Default/Dark/Light/Neon/Clean/Dark·LightSolarized/RedBlue/Light·DarkColorized/Turquoise/LightGreen/DarkGreen/DarkGreenBlue/Blue/SolidColor), 각각 실제 hex 팔레트 보유. 문서(14개 언급)와 코드(16개)의 불일치 확인.

5개 parametric style 클래스(`LightenStyle`/`DarkenStyle`/`SaturateStyle`/`DesaturateStyle`/`RotateStyle`)는 모두 `ParametricStyleBase` 상속, `_op`만 다름. HSL 공간에서 H/S/L 중 하나만 조정(rotate=H, saturate/desaturate=S, lighten/darken=L). API가 극히 간결: `LightenStyle(color, step, max_, base_style)`.

**한계**: 정성적(categorical) 팔레트 전용 — 시퀀셜/다이버징 연속 컬러 스케일 클래스가 없다. 팔레트 부족 시 `darken()` 순환 확장(명도만 조정, 지각균등 공간 아님). `value_colors`가 비면 `is_foreground_light()`로 흑/백 자동 결정(WCAG 대비비까지는 아님).

## A6. 타이포그래피 & 레이아웃

요소별 폰트 제어가 8세트(`label_/major_label_/value_/value_label_/tooltip_/title_/legend_/no_data_`)로 세밀하게 분리 — matplotlib의 전역 `font.size` 하나보다 훨씬 정교함. 폰트 크기는 px 정수 하드코딩, 상대 단위/반응형 스케일링 없음.

레이아웃은 `Config` 쪽(`width`/`height`/`spacing`/`margin`/`margin_{top,right,bottom,left}`)에 분리되어 있어, 타이포(Style)와 레이아웃(Config)이 하나의 "디자인 토큰"으로 통합되어 있지 않다. `margin_*` 4방향 개별 + fallback 패턴은 CSS box model과 유사해 직관적.

자동 라벨 줄바꿈/자동 폰트 축소 같은 고급 겹침 회피 기능은 config/문서 수준에서 확인되지 않음(본문 로직은 조사 범위 밖).

## A7. 통계 변환

**pygal은 통계 계산 엔진이 아니라 렌더러**라는 결론이 명확하다.

- **보간(interpolation)**: 5종(quadratic/cubic/hermite/lagrange/trigonometric), Hermite는 4개 서브타입(cardinal 등)까지 파라미터화. 원값 사이를 매끄럽게 잇는 "표시용" 기능이지 통계 추정이 아니다.
- **Box plot**: median/quartile/stdev/outlier를 직접 계산하는 유일한 진짜 통계 기능. `box_mode` 5종(extremes/1.5IQR/tukey/stdev/pstdev).
- **신뢰구간(CI)**: `pygal.stats`에 continuous/dichotomous/manual 3종. scipy 있으면 t분포, 없으면 정규분포 근사로 폴백. `serie.add(value, {'ci': {...}})`처럼 **metadata-driven opt-in** 설계 — 통계 레이어를 그리기 레이어와 분리한 좋은 선례.
- **히스토그램 자동 비닝, KDE, 회귀선, 이동평균 등은 전무.** Histogram조차 사용자가 `(count, bin_start, bin_end)`를 직접 계산해 넣어야 한다.

## A8. 출력·인터랙션·확장성

**출력 포맷이 매우 풍부**: SVG 문자열/파일, etree, HTML table, data URI, PNG(cairosvg 위임), sparktext(유니코드 막대문자), sparkline, Flask/Django response, pyquery, 브라우저 팝업. 전부 `render()`/`svg.root`를 소비하는 얇은 어댑터로 계층화되어 있어 신규 export 추가 비용이 낮다.

**인터랙션은 자체 구현이 아니라 "데이터 임베딩 + 외부 JS 위임"**: `Svg.add_scripts()`가 chart config 전체를 JSON으로 `window.pygal.config`에 노출하고, 실제 hover/툴팁은 별도 CDN 프로젝트 `pygal.js`가 담당(`js` config 기본값이 외부 CDN URL). 오프라인/CSP 환경에서는 툴팁이 동작하지 않는다.

확장성은 두 계층: (1) `css`/`js`/`defs` 리스트를 통한 선언적 주입(임의 CSS/JS/gradient), (2) `entry_points(group="pygal.maps")` + `sys.meta_path` 후킹 — 다만 이는 "지도 데이터셋 확장"에 특화되어 범용 플러그인 아키텍처는 아니다.

## A9. 접근성

**pygal은 실질적인 접근성 기능을 제공하지 않는다.**

- root `<svg>`에 `<title>` 요소는 있음(`graph.title or 'Pygal'`).
- `<desc>`는 존재하지만 데이터포인트 값 메타데이터(JS 툴팁용)일 뿐 WAI-ARIA 의미의 설명이 아님.
- `aria-*`, `role` 속성 전무.
- CSS에 `prefers-color-scheme`, `prefers-reduced-motion`, `:focus` 스타일 없음.
- 16개 테마 중 색맹 안전성을 검증/언급한 것 없음.

## 강점 / 약점 종합

**강점**: 세밀한 config 옵션(83개), CSS 클래스 기반 재테마 가능한 SVG(A5/A8 참고, `pygal/css/*.css`), 풍부한 출력 포맷, point-level metadata를 통한 유연한 데이터 입력, 선언적 확장(css/js/defs).

**약점**: hue/size 시맨틱 매핑 부재, DataFrame 네이티브 미지원, 통계 변환 레이어 전무, 진짜 인터랙션은 외부 JS 의존, 접근성 기능 전무, 다중상속 기반 클래스 계층으로 API 표면 대비 실제 자유도가 낮음, 저활성 유지보수.
