TITLE = "barplot"

SUMMARY = "카테고리마다 막대 하나를 그린다. orient= 로 방향을, hue= 와 stacked= 로 그룹을 정한다."

REQUIRES = "x: 카테고리(문자열로 변환된다) · y: 수치(음수 불가) · hue(선택): 아무 타입"

SETUP = """
import svgplot as sp

QUARTERS = {
    "분기": ["1분기", "2분기", "3분기", "4분기", "1분기", "2분기", "3분기", "4분기"],
    "매출": [120.0, 145.0, 98.0, 176.0, 84.0, 92.0, 110.0, 131.0],
    "채널": ["온라인"] * 4 + ["오프라인"] * 4,
}
"""

EXAMPLES = [
    (
        "기본 — 카테고리당 한 행",
        """ONE_ROW = {"분기": ["1분기", "2분기", "3분기", "4분기"], "매출": [120.0, 145.0, 98.0, 176.0]}
sp.barplot(ONE_ROW, x="분기", y="매출")""",
    ),
    ("hue= 는 밴드를 그룹 수만큼 나눠 나란히 놓는다", 'sp.barplot(QUARTERS, x="분기", y="매출", hue="채널")'),
    ("stacked=True 는 같은 자리에 쌓는다", 'sp.barplot(QUARTERS, x="분기", y="매출", hue="채널", stacked=True)'),
    ('orient="h" 는 카테고리를 왼쪽 축으로 보낸다', 'sp.barplot(QUARTERS, x="분기", y="매출", hue="채널", orient="h")'),
]

NOTES = [
    "음수 값을 거부한다.",
    "같은 카테고리에 행이 여럿이고 estimator= 를 주지 않으면 마지막 행이 이기고, 몇 행을 버렸는지 AggregationWarning 이 알린다. "
    'estimator="mean"/"median"/"sum" 또는 그룹의 값을 행 순서대로 받는 callable 로 접는 방법을 고를 수 있다.',
    "hue= 없이는 카테고리마다 팔레트가 돌고, hue= 가 있으면 hue 값마다 돈다 — 같은 그룹이 모든 카테고리에서 같은 색이 된다.",
    'orient="h" 면 값이 x 축으로 가므로 값 범위를 좁히는 인자도 xlim= 이다. xlim=/ylim= 은 화면의 축을 가리킨다.',
    "categories= 로 카테고리 목록을 지정하면 데이터에 없는 카테고리도 자리와 팔레트 색을 갖는다 — 여러 차트가 같은 색을 쓰게 만들 때 쓴다.",
]
