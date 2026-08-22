TITLE = "heatmap"

SUMMARY = "행·열 카테고리가 만드는 격자에서 값을 색으로 나타낸다. 색은 9단계로 양자화된다."

REQUIRES = (
    "x: 열 카테고리 · y: 행 카테고리 · values: 수치 · hue 는 받지 않는다(색은 values 가 정한다) · 셀 하나에 행 하나(중복 거부)"
)

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
    "시각": [hour for _ in _days for hour in _hours],
    "요일": [day for day in _days for _ in _hours],
    "요청": [value for row in _load for value in row],
}
"""

EXAMPLES = [
    ('기본 — cmap= 기본값은 순차 컬러맵 "blues" 다', 'sp.heatmap(TRAFFIC, x="시각", y="요일", values="요청")'),
    ("annot=True 는 셀 안에 값을 쓴다", 'sp.heatmap(TRAFFIC, x="시각", y="요일", values="요청", annot=True)'),
    (
        "cmap= 을 발산으로 바꾸고 center= 로 가운데 단계를 정한다 — annot= 도 함께 켠 그림",
        """DIFF = {
    "시각": TRAFFIC["시각"],
    "요일": TRAFFIC["요일"],
    "증감": [value - 45.0 for value in TRAFFIC["요청"]],
}
sp.heatmap(DIFF, x="시각", y="요일", values="증감", cmap="coolwarm", center=0.0, annot=True)""",
    ),
    (
        "tooltip=True — 셀마다 자기 열·행·값·단계를 말한다",
        'sp.heatmap(TRAFFIC, x="시각", y="요일", values="요청", tooltip=True)',
    ),
]

INTERACTIONS = {4: "cell"}

NOTES = [
    "네 번째 그림에는 체크박스가 없다. 단계는 값의 구간이지 시리즈가 아니라서, 토글을 달면 "
    '"3단계를 끄시오" 가 되는데 그건 범례가 아니라 데이터 편집이다. 대신 커서가 얹힌 셀에 테두리가 생긴다 — '
    "이 페이지의 CSS 이고 JavaScript 는 0줄이다.",
    "tooltip=True 가 정확한 값에 닿는 유일한 길이다. 색은 9단계로 양자화된 구간이라 한 단계 차이나는 두 셀이 "
    "거의 같을 수도 있고 같은 색인 두 셀이 거의 한 단계만큼 다를 수도 있다. annot=True 가 숫자를 그리지만 "
    "셀이 글자를 담을 만큼 클 때뿐이고, 범례는 셀이 아니라 단계에 이름을 붙인다.",
    "단계 번호는 값과 다른 것을 답한다 — 두 셀이 눈금에서 얼마나 떨어져 있느냐. 51 과 49 는 한 단계 차이일 "
    "수도 같은 단계일 수도 있고, 격자를 가로질러 색을 눈으로 견주는 것은 안 되지만 서수는 된다. "
    "범례가 그 번호로 매겨져 있는 건 아니다 — 범례는 각 단계가 시작하는 값을 적는다.",
    "셀 하나에 <title> 하나이므로 격자가 크면 파일이 그만큼 커진다. tooltip=False 가 기본인 이유다 — "
    "200x200 빽빽한 격자는 3,352.6KB 에서 6,345.6KB 가 된다. 크기 경고도 이 값을 함께 센다: 그 항이 없으면 "
    "경고가 3,385KB 라고 말하는데 46.7% 낮다.",
    "long-form (x, y, value) 를 받는다. 행렬 모양의 wide-form 이 아니다.",
    "셀 하나에 행이 둘이면 거부한다. 어느 값을 쓸지 정하는 것은 이 차트의 몫이 아니다.",
    "빠진 셀은 0 이 아니라 구멍으로 남는다 — 값이 0 인 것과 값이 없는 것은 다르다.",
    "색이 9단계로 양자화된다. 연속 램프가 아닌 이유는 CSS 규칙 9개면 손으로 다시 칠할 수 있지만 셀마다 규칙 하나면 그러지 못하기 때문이고, 덤으로 범례가 스와치 9개로 끝난다.",
    'cmap= 과 center= 는 짝이 맞아야 한다 — 발산 컬러맵("coolwarm"·"purplegreen")에 center= 가 없거나 sequential("blues"·"greens"·"oranges")에 center= 를 주면 고치는 법을 알려주며 거부한다.',
    "annot=True 의 글자 색은 테마가 아니라 셀 색의 휘도에서 고른다. 그래서 어느 프리셋에서도 대비가 유지된다.",
    "격자 셀이 2,500 개를 넘으면 크기를 경고하되 그린다. 100x100 은 셀 하나가 7x5px 이라 개별 식별이 어려워진다.",
]
