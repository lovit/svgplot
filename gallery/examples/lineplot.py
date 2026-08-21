TITLE = "lineplot"

SUMMARY = "x 순으로 점을 이어 선을 그린다. x 는 수치 또는 날짜를 받는다."

REQUIRES = "x: 수치 또는 date/datetime · y: 수치 · hue(선택): 아무 타입"

SETUP = """
import svgplot as sp

SALES = {
    "day": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
    "sales": [10.0, 15.0, 7.0, 20.0, 12.0, 6.0, 9.0, 4.0, 14.0, 8.0],
    "region": ["서울"] * 5 + ["부산"] * 5,
}
"""

EXAMPLES = [
    ("기본", 'sp.lineplot(SALES, x="day", y="sales")'),
    ("hue= 로 시리즈를 나눈다", 'sp.lineplot(SALES, x="day", y="sales", hue="region")'),
    (
        "interpolate= 로 점 사이를 곡선으로 잇는다",
        'sp.lineplot(SALES, x="day", y="sales", hue="region", interpolate="cubic")',
    ),
    (
        "x 가 날짜면 시간축이 되고 눈금 표기가 도메인 폭을 따른다",
        """from datetime import date

TRAFFIC = {
    "day": [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)],
    "hits": [120.0, 180.0, 150.0, 240.0],
}
sp.lineplot(TRAFFIC, x="day", y="hits")""",
    ),
]

INTERACTIONS = {2: "toggle", 3: "focus"}

NOTES = [
    "두 번째와 세 번째 그림에 조작 장치가 붙어 있다. 이 페이지의 CSS 와 마크업이고 JavaScript 는 0줄이다.",
    "세 번째의 라디오가 얇은 선 차트의 답이다. lineplot 은 fill: none 을 내므로 시리즈 하나의 히트 영역이 "
    "선 굵기 2px 뿐이다 — :hover 를 달 수는 있지만 실제로 잡히지 않고, 툴팁도 시리즈당 <path> 하나에 걸리는데 "
    "그 하나에 닿기가 같은 이유로 어렵다. 독자가 *조작하는* 장치는 기하를 통째로 비켜간다.",
    '체크박스가 아니라 라디오인 것은 "하나를 고른다" 가 단일 선택이기 때문이다. 라디오 그룹은 화살표 키 '
    "이동까지 공짜로 준다 — 체크박스 여러 개는 그게 없다.",
    '대신 라디오는 다시 눌러 해제할 수 없어서 "전체" 항목이 하나 더 있다. 그게 없으면 독자가 기본 상태를 '
    "떠난 뒤 돌아올 길이 없는데, 그건 이 장치가 푸는 문제보다 나쁜 덫이다.",
    "고른 선이 밝아지는 게 아니라 나머지가 흐려진다. 켜고 끄는 것과 같은 규칙이라 페이지가 한 번만 설명하면 "
    "되고, 축이 안 움직이는 것도 같은 이유로 그대로다.",
    "툴팁은 없다. 시리즈당 <path> 가 하나라 걸 수 있는 것은 시리즈 이름뿐인데, 그건 범례가 이미 말한다. "
    "꼭짓점마다 값을 말하려면 마커를 그려야 하고 그건 상호작용이 아니라 차트 기능이다.",
    "점은 x 순으로 정렬된다. 같은 x 를 가진 행이 둘이면 수직 선분이 되고, estimator= 로 접을 수 있다.",
    "interpolate= 는 linear(기본)·quadratic·cubic·hermite·lagrange·trigonometric 을 받는다.",
    "estimator= 와 info= 는 함께 쓸 수 없다. 각주 표는 1행 = 1마크를 전제하는데 집계가 그 전제를 깬다.",
    '날짜 컬럼에 xscale="log" 는 거부된다. 타임스탬프의 로그는 1970 을 0 으로 골랐다는 사실에서만 나오는 비율이다.',
    "aware datetime 과 naive datetime 을 한 컬럼에 섞으면 컬럼명을 대고 거부한다.",
]
