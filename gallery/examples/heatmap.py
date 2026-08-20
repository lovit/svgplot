TITLE = "heatmap"

SUMMARY = "행·열 카테고리가 만드는 격자에서 값을 색으로 나타낸다. 색은 9단계로 양자화된다."

REQUIRES = "x: 열 카테고리 · y: 행 카테고리 · values: 수치 · 셀 하나에 행 하나(중복 거부)"

SETUP = """
import svgplot as sp

_hours = ["09시", "12시", "15시", "18시", "21시"]
_days = ["월", "수", "금"]
_load = [
    [12.0, 48.0, 35.0, 61.0, 44.0],
    [18.0, 52.0, 41.0, 58.0, 39.0],
    [22.0, 66.0, 47.0, 82.0, 71.0],
]
TRAFFIC = {
    "시간": [hour for _ in _days for hour in _hours],
    "요일": [day for day in _days for _ in _hours],
    "요청": [value for row in _load for value in row],
}
"""

EXAMPLES = [
    ("기본 — sequential 컬러맵", 'sp.heatmap(TRAFFIC, x="시간", y="요일", values="요청")'),
    ("annot=True 는 셀 안에 값을 쓴다", 'sp.heatmap(TRAFFIC, x="시간", y="요일", values="요청", annot=True)'),
    (
        "center= 는 발산 컬러맵과 함께 준다 — 가운데 단계가 그 값을 뜻하게 된다",
        """DIFF = {
    "시간": TRAFFIC["시간"],
    "요일": TRAFFIC["요일"],
    "증감": [value - 45.0 for value in TRAFFIC["요청"]],
}
sp.heatmap(DIFF, x="시간", y="요일", values="증감", cmap="coolwarm", center=0.0, annot=True)""",
    ),
]

NOTES = [
    "long-form (x, y, value) 를 받는다. 행렬 모양의 wide-form 이 아니다.",
    "셀 하나에 행이 둘이면 거부한다. 어느 값을 쓸지 정하는 것은 이 차트의 몫이 아니다.",
    "빠진 셀은 0 이 아니라 구멍으로 남는다 — 값이 0 인 것과 값이 없는 것은 다르다.",
    "색이 9단계로 양자화된다. 연속 램프가 아닌 이유는 CSS 규칙 9개면 손으로 다시 칠할 수 있지만 셀마다 규칙 하나면 그러지 못하기 때문이고, 덤으로 범례가 스와치 9개로 끝난다.",
    'cmap 과 center 는 짝이 맞아야 한다 — 발산 컬러맵("coolwarm"·"purplegreen")에 center= 가 없거나 sequential("blues"·"greens"·"oranges")에 center= 를 주면 고치는 법을 알려주며 거부한다.',
    "annot=True 의 글자 색은 테마가 아니라 셀 색의 휘도에서 고른다. 그래서 어느 프리셋에서도 대비가 유지된다.",
    "격자 셀이 2,500 개를 넘으면 크기를 경고하되 그린다. 100x100 은 셀 하나가 7x5px 이라 개별 식별이 어려워진다.",
]
