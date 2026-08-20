# seaborn — 기능 범위 조사 (8축)

레포: `references/seaborn` · 0.14.0.dev · 29k LOC · matplotlib 위의 순수 Python 래퍼(JS 아님)

핵심 관점: **seaborn이 굳이 감싸서 제공하는 기능은 "raw matplotlib만으로는 불편했던 실사용 수요"의 증거**다. 이 문서 전체에서 "matplotlib이라면 사용자가 뭘 직접 해야 했는가"를 병기한다.

---

## A1. 차트 타입 인벤토리

| 계열 | figure-level | axes-level | mark 조합 |
|---|---|---|---|
| Relational | relplot | scatterplot, lineplot | 점 / 선+오차대역 |
| Distributional | displot | histplot, kdeplot, ecdfplot, rugplot, (distplot, deprecated) | 막대 / 선·등고선 / 계단선 / 틱마크 |
| Categorical | catplot | stripplot, swarmplot, boxplot, violinplot, boxenplot, pointplot, barplot, countplot | 점/막대/박스/KDE영역 조합 |
| Regression | lmplot | regplot, residplot | 점+회귀선+신뢰대역 |
| Matrix | (clustermap) | heatmap | 색칠 격자 |
| 복합 Grid | jointplot, pairplot, clustermap | — | 중심+주변 플롯, NxN 격자, 격자+덴드로그램 |

**`kind=` 파라미터가 "mark 전환"을 문자열 하나로 통일**한다(relplot의 scatter/line, displot의 hist/kde/ecdf, catplot의 8종, jointplot의 6종). matplotlib 순정에서는 `ax.scatter` vs `ax.bar` 호출 자체를 갈아끼워야 하는 것을 문자열 스위치로 흡수 — SVG 패키지의 강한 차별화 후보.

violinplot(KDE fill+box), boxenplot(다단 box)처럼 "여러 mark의 합성"으로 정의되는 차트는 통계적 요약을 시각적으로 압축한다.

## A2. 데이터 입력·시맨틱 매핑

**long-form(tidy) DataFrame + 문자열 컬럼 참조가 기본값** — pygal(수동 시리즈 분해)·matplotlib(순수 array)과 근본적으로 다른 지점. wide-form DataFrame, dict, numpy array, GroupBy 결과도 모두 허용(입력 형태를 런타임에 자동 판별).

시맨틱 채널 3종 세트가 대칭적으로 설계됨: `hue`/`size`/`style` 각각 `_order`/`_norm` 페어를 동반 — "매핑 대상 컬럼 + 순서 고정 + 정규화 범위"의 재사용 가능한 3-tuple 추상화. `col`/`row`는 figure-level 함수 전용(단일 차트 내 인코딩 vs 멀티패널 분할이 레이어로 분리되어 있음).

`estimator`/`errorbar`/`weights`/`units`는 "동일 x에 여러 y 관측치가 있을 때 자동 집계" — matplotlib에서는 `df.groupby(x).agg()`를 사용자가 선행해야 하는 지점의 직접적 수요 증거.

**seaborn 객체(Properties) 인벤토리** (`_core/plot.py`/`objects.py`): x/y/color/alpha/fill/marker/pointsize/stroke/linewidth/linestyle/fillcolor/fillalpha/edgewidth/edgestyle/edgecolor/edgealpha/text/halign/valign/offset/fontsize/xmin/xmax/ymin/ymax/group — 총 26개 매핑 가능 채널.

## A3. API 문법

3중 API가 계단식 학습 곡선을 이룬다:

1. **axes-level 함수**(`sns.scatterplot(data=df, x=, y=, hue=)`) — matplotlib과 1:1, `ax=`로 합성 가능, `Axes` 반환
2. **figure-level 함수**(`sns.relplot(..., col=)`) — 내부적으로 axes-level을 호출하며 `FacetGrid` 생성. **`ax=`를 받지 못함**(경고 후 무시) — 기존 matplotlib 서브플롯에 끼워 넣을 수 없는 구조적 제약
3. **객체 인터페이스**(`so.Plot(df, x=, y=).add(so.Dot())`) — `Mark`/`Stat`/`Move`/`Scale` 4종 프리미티브 조합, 모든 메서드가 `_clone()`으로 새 인스턴스를 반환하는 **불변(immutable) 빌더 패턴**, `.add()`/`.facet()` 호출 시점엔 아무것도 그려지지 않고 스펙만 누적 → `.plot()/.show()/.save()`에서 지연 컴파일(lazy). `.on(target)`으로 기존 matplotlib Figure/Axes/SubFigure에 이식 가능(독립 렌더러 아님).

figure-level은 axes-level을 감싸는 얇은 오케스트레이션(단일 진실 소스, SSOT) — "저수준 그리기 함수 + 고수준 파사드" 분리 패턴은 그대로 참고할 가치가 있다.

**주의**: 객체 인터페이스는 문서 곳곳에 "API가 아직 finalize되지 않았다"는 주석이 있어 실험적 단계.

### CJK 하위질문
seaborn 자체에는 폰트/텍스트 옵션이 `set_theme(font=...)` 정도뿐이며, 이는 단순 문자열을 `matplotlib rcParams["font.family"]`에 그대로 전달할 뿐이다. 코드베이스 전체에 CJK/한글/한자/일본어 관련 키워드 0건. **seaborn은 텍스트 렌더링을 전적으로 matplotlib에 위임하며, CJK 관련해 참고할 것이 없다.**

## A4. 스타일·테마 시스템

`rcmod.py`가 style(외관)과 context(스케일)를 **명확히 두 축으로 분리**한다:

- **style 5종**(darkgrid/dark/whitegrid/white/ticks): 배경색, 그리드 유무, 스파인 표시, 틱 방향의 조합만 다름
- **context 4종**(paper=.8/notebook=1/talk=1.5/poster=2): **모든 폰트·선굵기·틱크기 키에 동일 배율**을 곱한 뒤, `font_scale` 인자로 텍스트 관련 키만 추가로 독립 스케일하는 "2단 스케일링" 구조. **발표 매체에 따라 선굵기·폰트를 일관되게 키우는 이 아이디어는 그대로 훔칠 만한 설계.**

`despine(offset=, trim=)`(스파인 제거+바깥 이동+tick범위로 자르기), `move_legend()`(matplotlib에 없는 범례 사후 재배치 API)처럼 matplotlib의 정확한 pain point를 겨냥한 유틸 다수.

**핵심 비판**: `set_style`/`set_context`/`set_theme`/`set_palette`가 전부 **전역 `mpl.rcParams`를 mutate**한다 — 같은 프로세스의 다른 차트에도 영향을 주는 부수효과, Jupyter 셀 실행 순서에 따라 렌더링이 달라지는 재현성 문제. `with sns.axes_style(...)` context manager로 일부 완화하지만 기본 API는 여전히 전역적. **SVG 패키지는 스타일을 차트 객체(또는 명시적 Theme 객체)에 귀속시켜 순수 함수적으로 렌더링해야 한다.**

## A5. 컬러 팔레트 엔진

**seaborn이 세 라이브러리 중 압도적으로 우월한 축.** `color_palette()`가 미니 언어로 통합:

- `"deep"/"muted"/"pastel"/"bright"/"dark"/"colorblind"`(+`6` variant) — 12종 정성 팔레트
- `"hls"`/`"husl"` — 원형 색공간 등간격 샘플링(HUSL은 지각적으로 균일)
- `"ch:s=.25,r=-.5"` — cubehelix(밝기 단조 증가/감소 보장, 흑백 인쇄·색맹 안전)
- `"light:seagreen"`/`"dark:salmon_r"` — 목표색과 동일 hue를 유지한 회색 앵커로 sequential 팔레트 자동 생성
- `"blend:a,b"` — 임의 색 리스트 보간
- `"jet"` → **의도적으로 `ValueError("No.")`** — 알려진 나쁜 기본값을 API가 명시적으로 거부(코드 주석: `# Paternalism`)

rocket/mako/icefire/vlag/flare/crest(256단계 리터럴 LUT, perceptually uniform 목표)는 matplotlib colormap registry에도 등록됨.

`as_cmap` 플래그로 "이산 리스트 vs 연속 colormap"을 한 함수에서 분기(단, 타입 불안정성 트레이드오프 있음).

## A6. 타이포그래피 & 레이아웃

`FacetGrid`/`PairGrid`/`JointGrid`가 matplotlib `GridSpec` 수동 조작을 완전히 감춘다:

- `FacetGrid`: `col_wrap`(자동 줄바꿈), `height`+`aspect`(상대적 크기 지정), `margin_titles=True`(타이틀 반복 제거, data-ink 최소화), `.map()`으로 임의 함수를 각 facet에 적용, `.add_legend()`로 공통 범례 자동 배치+중복 제거
- `PairGrid`: `.map_diag/.map_offdiag/.map_lower/.map_upper` — 격자 위치별로 다른 시각화를 선언적으로 지정(matplotlib/seaborn 사용자에게 익숙한 패턴)
- `JointGrid`: 중앙+주변 3-axes 레이아웃을 GridSpec으로 자동 구성, marginal axis 틱 자동 숨김

**한계**: 세 클래스가 메서드 이름 규칙이 서로 다름(`map_offdiag` vs `plot_joint`)이라 일관성이 부족하고, 모두 matplotlib Figure/Axes에 강결합되어 있어 **레이아웃 로직이 렌더러와 분리되지 않은 구조**다. SVG 패키지는 레이아웃 로직을 렌더러로부터 분리해야 재사용 가능.

## A7. 통계 변환

matplotlib에는 없는 seaborn 고유의 핵심 레이어:

| 변환 | API | 의존성 |
|---|---|---|
| KDE(1D/2D) | `kdeplot`, `objects.KDE()` | scipy 있으면 사용, 없으면 순수 numpy 폴백(`external/kde.py`) — cumulative만 scipy 필수 |
| Histogram binning | `histplot`, `objects.Hist()` | `numpy.histogram_bin_edges` 위임, numpy만 |
| ECDF | `ecdfplot` | numpy만 |
| 회귀적합 | `regplot`의 order/logistic/lowess/robust | 1차·polyfit은 numpy, logistic/robust/lowess는 statsmodels 필수 |
| 부트스트랩 CI | `errorbar=` 통합 스펙 | 부트스트랩 자체는 순수 numpy 자체구현(`algorithms.bootstrap`), 외부 의존 없음 |
| letter-values | `boxenplot`의 `k_depth` | numpy만 |
| 카운팅/집계 | `countplot`, `objects.Agg()` | 없음 |

**`errorbar=` 통합 스펙은 그대로 벤치마킹할 가치가 있는 API 설계**다 — 문자열(`"sd"`/`"se"`/`"pi"`/`"ci"`)/튜플/callable 세 형태를 하나의 파라미터로 흡수(`_validate_errorbar_arg`).

`Stat` 데이터클래스(`_stats/*.py`)가 `__call__(data, groupby, orient, scales) -> DataFrame`로 "데이터→변환된 DataFrame"과 "배열→SVG geometry"를 분리하는 아키텍처는 참고 가치가 높다. 단, `objects` 인터페이스 전용 내부 타입에 강결합되어 설계만 참고 가능.

**시사점**: KDE/hist/ecdf/errorbar(sd,se,pi) 정도를 좁게 시작하고, logistic/robust/lowess 회귀·letter-values는 후순위/optional extra로 미루는 것이 현실적. seaborn 자체도 OLSFit이 미구현 스텁으로 남아있을 만큼 "통계 변환 전부 자체 구현"은 진행형 과제.

## A9. 접근성

- `"colorblind"`/`"colorblind6"` 팔레트(옵트인, 기본 팔레트는 `"deep"`)
- cubehelix의 밝기 단조성이 색맹 안전을 알고리즘적으로 보장(역시 옵트인)
- 색맹 시뮬레이션 검증 도구, 명도 대비 체크 등 체계적 접근성 도구는 조사 범위 내 확인되지 않음

## 강점 / 약점 종합

**강점**: `data=`+컬럼명+`hue`/`size`/`style`/`col`/`row` 조합이 seaborn을 seaborn답게 만드는 핵심 문법으로 "익숙함" 목표에 직결. 컬러 팔레트 미니 언어, context 2단 스케일링, `errorbar=` 통합 스펙, FacetGrid/PairGrid/JointGrid의 선언적 레이아웃은 전부 이식 가치가 높은 설계.

**약점**: 전역 rcParams mutate(재현성 문제), 3중 API 간 파라미터명 불일치(`hue`→`color`, `size`→`pointsize`), figure-level이 `ax=`를 못 받는 구조적 제약, 통계 변환 레이어 구현 비용이 큼, Grid 클래스들의 메서드 이름 비일관성과 렌더러 강결합, 접근성이 전부 옵트인.
