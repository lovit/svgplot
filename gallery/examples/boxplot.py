TITLE = "boxplot"

SUMMARY = "카테고리마다 사분위 상자와 수염을 그린다. mode= 가 수염의 끝을 무엇으로 정할지 고른다."

REQUIRES = "x: 카테고리 · y: 수치 · hue(선택): 카테고리 안에서 한 번 더 나눌 값"

SETUP = """
import random

import svgplot as sp

_rng = random.Random(3)
_days = ["월", "화", "수", "목", "금"]
DELIVERY = {
    "요일": [day for day in _days for _ in range(40)],
    "분": [round(_rng.gauss(28 + index * 2, 6 + index), 1) for index in range(5) for _ in range(40)],
    "지역": [("도심" if _rng.random() < 0.5 else "외곽") for _ in range(200)],
}
"""

EXAMPLES = [
    ('기본 — mode="1.5IQR"', 'sp.boxplot(DELIVERY, x="요일", y="분")'),
    ('mode="extremes" 는 수염을 최솟값·최댓값까지 늘린다', 'sp.boxplot(DELIVERY, x="요일", y="분", mode="extremes")'),
    ('mode="tukey" 는 다른 힌지 정의를 쓴다', 'sp.boxplot(DELIVERY, x="요일", y="분", mode="tukey")'),
    ("hue= 는 카테고리 밴드를 나눠 상자를 나란히 놓는다", 'sp.boxplot(DELIVERY, x="요일", y="분", hue="지역")'),
    (
        "tooltip=True — 상자의 모든 마크가 같은 요약을, 이상치는 자기 값을 말한다",
        'sp.boxplot(DELIVERY, x="요일", y="분", hue="지역", tooltip=True)',
    ),
]

INTERACTIONS = {4: "toggle", 5: "toggle"}

NOTES = [
    "네 번째와 다섯 번째 그림에 체크박스가 붙어 있다. 이 페이지의 CSS 와 마크업이고 JavaScript 는 0줄이다.",
    "이 페이지의 규칙이 :is(.series-N, .series-N-marker) 인 것은 boxplot 이 시리즈 하나를 클래스 둘로 그리는 "
    "유일한 차트이기 때문이다. 수염과 중앙값 선은 series-N 이고 상자 본체와 이상치 원은 series-N-marker 다. "
    "결함이 아니라 theme/css.py 의 mark_style 짝이다 — 선은 stroke 로, 채운 도형은 fill 로 색을 받아야 하므로 "
    "규칙이 둘로 갈린다. 클래스 하나만 적으면 체크를 껐을 때 수염만 흐려지고 상자는 그대로 남아, "
    "선택자가 절반만 들은 것이 아니라 렌더링 버그처럼 보인다. 손으로 CSS 를 쓸 때도 같은 얘기다.",
    "tooltip=True 는 상자의 여섯 마크(본체·중앙값 선·수염 줄기 둘·캡 둘)에 같은 문장을 붙인다. 반복이 의도다 — "
    "포인터는 자기 밑의 맨 위 요소에서 멈추므로, <title> 이 없는 마크는 글리프에 뚫린 구멍이 된다. "
    "제목 없는 중앙값 선은 반응하는 상자 한가운데를 가로지르는 죽은 띠로 읽힌다.",
    "상자는 여러 행의 요약이라 어느 행인지 말할 수 없지만 이상치 원은 관측 하나라서 자기 값을 말한다. "
    "이상치는 자기 카테고리도 다시 적는다 — 원은 위에 그려지고 대개 상자 바깥에 있어서, 거기서는 상자의 <title> 이 "
    "포인터에 닿는 것이 아니다.",
    "수염은 닫힌 구간 [a, b] 로 적는다. 1.5IQR 에서는 양 끝이 실제로 관측된 값이다. histplot 의 구간과 다른 점이고, "
    "stdev·pstdev 모드에서는 평균 ± 1 표준편차라 관측값이 아닐 수도 있어서 min·max 가 아니라 whiskers 라고 적는다.",
    "mode= 는 extremes·1.5IQR·tukey·stdev·pstdev 다섯이다. 앞의 셋은 사분위에서, 뒤의 둘은 평균 ± 1 표준편차에서 수염 끝을 잡는다.",
    "stdev·pstdev 모드에서는 수염 끝이 사분위와 무관하므로 상자 안쪽에 놓여 거꾸로 그려질 수 있다. 통계의 정의가 그런 것이고, 상자에 맞춰 자르면 통계를 왜곡한다.",
    "hue= 없이는 카테고리마다 팔레트가 돌고, hue= 가 있으면 hue 값마다 돈다 — 같은 그룹이 모든 요일에서 같은 색이 된다.",
    "1.5IQR 모드에서 수염 밖의 값은 개별 점으로 그린다. extremes 모드에는 수염이 끝까지 가므로 그런 점이 없다.",
    "violinplot 과 위치 인자 (data, x, y, hue) 가 같다. 같은 데이터를 두 방식으로 번갈아 볼 때 호출을 그대로 바꿔 쓰면 된다.",
]
