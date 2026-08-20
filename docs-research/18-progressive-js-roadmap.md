> **이 문서는 원칙 문서다. v1.0 구현 대상이 아니다.** v1.0(markdown 임베드)에서는 JS가 실행되지 않으므로 여기 적힌 어떤 것도 지금 만들지 않는다. 목적은 오직 하나 — v1.0에서 SVG를 설계할 때 "나중에 v2.0에서 JS를 얹기 쉽도록 무엇을 미리 심어둘까"를 정하는 것이다.

# v2.0 진행형 개선 로드맵 — standalone에서만 켜지는 인터랙션

## 전제: v2.0이 언제 켜지는가

markdown에 `<img src="chart.svg">`로 삽입된 SVG는 이미지 컨텍스트라 `<script>`가 실행되지 않는다. 하지만 사용자가 그 `.svg` 파일을 **브라우저 탭에서 직접 열면**(top-level navigated document), SVG는 더 이상 이미지가 아니라 최상위 문서가 되고 `<script>`와 CSS `:hover`가 정상 동작한다. 즉 **같은 SVG 파일 하나가 두 컨텍스트에서 다르게 행동**한다 — markdown 안에서는 정적 그림, standalone으로 열면 인터랙티브 문서. 이 "이중 모드"가 v2.0의 핵심 아이디어다.

## Bokeh에서 훔칠 최소 추상화

Bokeh 조사(`04-bokeh.md`)에서 확인한 핵심: hover, linked pan/zoom, linked brushing이 전부 **Python 서버 없이** 정적 HTML+JS만으로 동작하는 이유는 단 하나의 추상화 때문이다 — **공유 데이터소스(`ColumnDataSource`) + 선택 상태(`Selection.indices`) + 변경 통지(`js_on_change`)**. 두 차트가 같은 `ColumnDataSource` 인스턴스를 참조하면, 한쪽에서 선택이 바뀔 때 다른 쪽이 자동으로 반응한다 — 콜백을 따로 배선할 필요조차 없다.

새 패키지가 v2.0에서 이 최소 추상화만 재현하면 된다:

```
데이터 배열(공유) → 각 SVG 마크에 data-index 속성 → 마크의 CSS class(선택/hover 상태) → 작은 JS 셰임이 인덱스 집합을 유지하고 class를 토글
```

## v1.0에서 지금 심어둘 것 (v1.0 스코프에 포함되는 유일한 부분)

v2.0을 나중에 무리 없이 얹으려면, v1.0 SVG 산출물이 처음부터 아래 관례를 지켜야 한다 — **이것만이 v1.0 구현에 실제로 영향을 준다**:

1. **모든 데이터 마크에 `data-index="N"` 속성을 붙인다.** Bokeh의 `ColumnDataSource` 행 인덱스에 대응. v1.0에서는 그냥 정적 속성이지만, v2.0 JS가 이 속성으로 "이 원이 몇 번째 데이터 포인트인지" 알 수 있다.
2. **선택/hover 상태를 표현할 CSS 클래스 이름을 예약해둔다.** 예: `.is-selected`, `.is-hovered`, `.is-muted`. v1.0에서는 아무도 이 클래스를 토글하지 않지만, 클래스 자체와 그에 대응하는 스타일(색상/투명도 변화)은 테마 시스템(`12-aesthetics.md`)에 이미 정의해둔다.
3. **여러 차트가 같은 데이터를 참조할 때, 그 데이터를 하나의 식별 가능한 JSON 블록으로 SVG(또는 감싸는 파일)에 남긴다.** Bokeh의 `ColumnDataSource` 공유에 대응 — v1.0에서는 렌더링에만 쓰고 버리더라도, "이 그리드의 여러 차트가 같은 데이터셋에서 나왔다"는 사실을 `<metadata>` 요소나 `data-source-id` 속성으로 표시해두면 v2.0이 "어떤 차트끼리 연동해야 하는지" 재구성할 수 있다.
4. **`<script>` 삽입 지점을 하나로 고정한다.** v1.0 렌더러가 `<script>` 태그를 아예 안 넣더라도, "만약 넣는다면 여기"라는 위치(SVG 최상위 `<defs>` 직후 등)를 지금 정해두면 v2.0에서 옵션 하나(`interactive=True`)로 스위치할 때 렌더러 구조를 바꾸지 않아도 된다.

## v2.0에서 만들 것 (지금 만들지 않음, 목록만)

- **CDS-유사 공유 데이터 객체**: JS 쪽에서 `{selected: Set<number>, hovered: number|null}` 정도의 최소 상태 + `onChange` 구독자 리스트. Bokeh의 `Selection`/`js_on_change`에 대응하지만 훨씬 작다(Bokeh는 범용 프레임워크라 크고, 이건 "선택 하나"만 있으면 됨).
- **hover → tooltip**: `data-index` 마크에 `mouseenter`로 `title`/`aria-label` 텍스트를 동적 위치에 표시. `17-static-hover-alternative.md`에서 만든 `label_spec`(이미 v1.0에 존재)을 그대로 재사용 — v1.0의 각주 테이블/인라인 라벨 콘텐츠 정의가 v2.0의 hover 텍스트 정의와 같은 소스여야 중복이 없다.
- **linked brushing**: 같은 `data-source-id`를 가진 여러 SVG(또는 하나의 SVG 안 여러 서브플롯)가 공유 selection 상태를 구독. Bokeh처럼 "같은 소스를 참조하면 자동 연동"을 목표로 하되, Bokeh와 달리 여러 개의 독립된 `.svg` 파일 사이에서도 동작하게 하려면(예: 폴더 안 svg 여러 개를 한 HTML에 inline) `localStorage`나 커스텀 이벤트 브로드캐스트가 필요 — 이건 별도 설계 문제로 남긴다.
- **정적 self-contained embed**: Bokeh의 `components()`/`json_item()`/`file_html()` 패턴 참고 — v2.0 산출물도 "SVG+JS를 하나의 self-contained HTML 파일"로 묶어내는 export 함수를 제공(`chart.save_interactive("out.html")` 같은). 별도 서버나 빌드 과정 없이 파일 하나로 끝나야 Bokeh 대비 사용성 우위를 유지한다.

## 명시적 비목표 (v2.0에서도 하지 않을 것)

- Bokeh 서버(`bokeh serve`) 같은 Python 백엔드 — 사용자 관심사(hover+연동)는 서버 없이 전부 재현 가능함이 Bokeh 조사에서 이미 확인됐다.
- `bokehjs` 수준의 범용 시각화 런타임 — 필요한 상호작용 3~4종(hover, 선택, linked brushing)만 아주 작은 셰임으로 구현한다.
- 3rd-party JS 프레임워크 의존 — v1.0의 "가벼운 코어" 철학을 v2.0도 유지한다.
