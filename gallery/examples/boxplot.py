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
]

NOTES = [
    "mode= 는 extremes·1.5IQR·tukey·stdev·pstdev 다섯이다. 앞의 셋은 사분위에서, 뒤의 둘은 평균 ± 1 표준편차에서 수염 끝을 잡는다.",
    "stdev·pstdev 모드에서는 수염 끝이 사분위와 무관하므로 상자 안쪽에 놓여 거꾸로 그려질 수 있다. 통계의 정의가 그런 것이고, 상자에 맞춰 자르면 통계를 왜곡한다.",
    "hue= 없이는 카테고리마다 팔레트가 돌고, hue= 가 있으면 hue 값마다 돈다 — 같은 그룹이 모든 요일에서 같은 색이 된다.",
    "1.5IQR 모드에서 수염 밖의 값은 개별 점으로 그린다. extremes 모드에는 수염이 끝까지 가므로 그런 점이 없다.",
    "violinplot 과 위치 인자 (data, x, y, hue) 가 같다. 같은 데이터를 두 방식으로 번갈아 볼 때 호출을 그대로 바꿔 쓰면 된다.",
]
