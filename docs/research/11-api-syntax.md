# API 문법 결정 — 어느 문법을 채택할 것인가

세 후보를 같은 시나리오(막대그래프 하나)로 비교하고, 하나를 권고한다.

## 세 후보

### 후보 A — pyplot류 명령형 (matplotlib pyplot)
```python
plt.bar(categories, values)
plt.title("Sales")
plt.savefig("chart.svg")
```
전역 암묵 상태(`gcf()`/`gca()`)에 순차적으로 명령을 내리는 방식.

### 후보 B — seaborn류 고수준 함수 (data=, x=, y=, hue=, kind=)
```python
chart = svgpkg.barplot(data=df, x="category", y="value", hue="group")
chart.save("chart.svg")
```
데이터프레임 + 컬럼명 문자열 + 시맨틱 채널을 함수 하나에 넘기는 방식. 반환값은 (암묵 전역이 아닌) 명시적 차트/Axes 객체.

### 후보 C — 선언형 객체 (seaborn.objects류)
```python
(
    svgpkg.Plot(df, x="category", y="value", color="group")
    .add(svgpkg.Bar(), svgpkg.Dodge())
    .save("chart.svg")
)
```
Mark/Stat/Move/Scale 프리미티브를 조합하는 불변 빌더 패턴.

## 평가 기준별 채점

| 기준 | A. pyplot 명령형 | B. seaborn 함수형 | C. 선언형 객체 |
|---|---|---|---|
| matplotlib/seaborn 사용자 친숙도 | 높음(pyplot 경험자) | 높음(seaborn 경험자, 목표 사용자층과 최다 중복) | 낮음(seaborn 0.12+ 사용자만) |
| 시나리오당 코드 길이(12개 캐노니컬 시나리오 기준 정성 비교) | 중간 | **짧음**(data=+시맨틱 채널로 groupby/hue 로직이 사라짐) | 중간(체이닝은 짧지만 프리미티브 학습비용) |
| 표현력 상한(복잡한 조합) | 중간(수동 조합 가능하나 반복 코드) | 중간(kind=로 확장하지만 결국 유한 집합) | **높음**(Mark×Stat×Move 조합 폭발적 확장) |
| 구현 난이도(전체 Artist 모델 없이) | 낮음(상태만 관리하면 됨) | **낮음**(함수 = 데이터 변환 + 렌더 호출) | 높음(불변 spec 누적 + 지연 컴파일 엔진 필요) |
| SVG(문서 산출형, 무상태)와의 정합성 | **나쁨**(전역 `gcf()`가 "현재 그려지는 문서"라는 상태를 요구 — SVG는 결과물이 즉시 문자열/트리이므로 전역 상태가 불필요한 복잡도) | **좋음**(함수 호출 → 값 반환은 무상태 파이프라인과 자연히 맞음) | **좋음**(스펙 누적 → 단일 컴파일은 오히려 SVG 파이프라인에 유리하나, 엔진 자체가 무겁다) |
| 발견성/IDE 자동완성 | 중간(전역 함수 다수) | **좋음**(함수 시그니처 하나로 대부분 옵션 파악) | 낮음(체이닝 API는 다음 옵션이 뭔지 IDE로 예측 어려움) |
| 확장성(신규 차트 타입 추가 비용) | 낮음(새 top-level 함수 필요) | 중간(`kind=`에 문자열 추가) | **높음**(새 Mark 클래스 하나로 기존 Stat/Move 재사용) |
| 테스트 용이성 | 중간(전역 상태 mock 필요) | **좋음**(순수 함수에 가까움) | 좋음(불변 객체라 스냅샷 테스트 용이) |

## 권고: **B(seaborn류 고수준 함수)를 1차 API로, A는 최소한의 이스케이프 해치로, C는 후순위**

### 근거
1. **SVG는 상태가 아니라 문서를 산출한다.** `plt.gcf()`처럼 "현재 활성 캔버스"라는 전역 가변 상태를 유지하는 것은 문서 생성 파이프라인(입력→변환→SVG 문자열)과 근본적으로 어울리지 않는다. `07-데이터 흐름` 관점에서 B와 C는 모두 "입력을 받아 값을 반환"하는 무상태 함수/빌더이므로 SVG의 본질에 더 가깝다.
2. **`40-demand-signal.md`(별도 문서 없이 이 문서에 요약)의 핵심 발견 — seaborn이 존재하는 이유 자체가 "matplotlib의 명령형 상태 조작이 tidy 데이터 시각화에 불편했기 때문"**이다. `A2` 조사에서 확인했듯 matplotlib 코어에는 `hue=`/`size=` 같은 시맨틱 채널이 없고, 사용자가 `for group in df.groupby(): ax.plot(...)`를 직접 작성해야 한다. B 문법을 채택하면 이 불편함을 처음부터 제거할 수 있다.
3. **구현 난이도가 결정적이다.** C(선언형 객체)는 seaborn 자체에서도 "아직 finalize되지 않은" 실험적 API로 남아 있고, `Mark`/`Stat`/`Scale`/`Move`의 조합 엔진은 이 조사가 확인한 seaborn `_core/` 모듈 전체(수천 LOC)에 해당하는 구현 부담이다. 반면 B는 "함수 하나 = 데이터 전처리(그룹핑/색상 매핑) + 렌더 호출"로 훨씬 얇게 구현 가능하다.
4. **목표 사용자층과 최대 중복.** "matplotlib/seaborn 사용자에게 익숙한 문법"이 요구사항인데, `data=, x=, y=, hue=, kind=` 시그니처는 seaborn 사용자 전원에게 이미 익숙하고, matplotlib 사용자에게도 (`data=` kwarg가 이미 존재하므로) 낯설지 않다.
5. **A(pyplot 명령형)를 완전히 버리지는 않는다.** 저수준 커스터마이징 진입점(예: 개별 요소 스타일 override, 여러 차트를 하나의 캔버스에 합성)을 위한 얇은 escape-hatch 레이어로 유지하되, 이는 B로 만든 차트 객체의 메서드(예: `chart.set_title()`, `chart.add_layer()`)로 노출한다 — pygal의 "체이닝 가능한 객체" 모델(`01-pygal.md` A3)과 seaborn axes-level 함수의 `ax=` 합성 가능성을 결합한 형태.
6. **C는 v2 이후 후보로 명시적으로 남겨둔다.** B로 커버되지 않는 복잡한 조합(다중 레이어, 커스텀 Stat)이 실제 사용자 요청으로 나타나면, 그때 B의 함수 시그니처를 깨지 않는 상위 확장으로 C를 얹는다(seaborn이 실제로 이 경로를 밟았다 — 함수 인터페이스가 먼저 성숙했고 objects는 나중에 얹혔다).

### 채택하는 구체 시그니처 (straw-man)
```python
svgpkg.lineplot(data=df, x="date", y="value", hue="category", theme="darkgrid")
svgpkg.barplot(data=df, x="category", y="value", hue="group", errorbar="sd")
svgpkg.scatterplot(data=df, x="a", y="b", hue="c", size="d")

# 저수준 커스터마이징은 반환 객체 메서드로
chart = svgpkg.barplot(data=df, x="category", y="value")
chart.set_title("Sales")
chart.palette("ch:s=.25,r=-.5")   # seaborn 미니 언어 채택(A5)
chart.save("out.svg")
```

### 채택하지 않는 것
- `plt.gcf()`류 전역 암묵 상태
- pygal의 `__call__` 단축 문법(`chart(1,2,3)`) — matplotlib/seaborn 사용자에게 낯설어 목표에 역행
- figure-level 함수가 `ax=`를 거부하는 seaborn의 제약(우리는 B의 반환 객체를 항상 합성 가능하게 설계)
