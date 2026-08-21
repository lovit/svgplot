TITLE = "violinplot"

SUMMARY = "카테고리마다 좌우 대칭 밀도 곡선을 그린다. 폭이 그 값 근처에 얼마나 몰려 있는지를 나타낸다."

REQUIRES = "x: 카테고리 · y: 수치(그룹마다 2개 이상, 분산 0 불가) · hue(선택): 카테고리 안에서 한 번 더 나눌 값"

SETUP = """
import random

import svgplot as sp

_rng = random.Random(11)
_teams = ["백엔드", "프론트", "데이터"]
REVIEW = {
    "팀": [team for team in _teams for _ in range(60)],
    "시간": (
        [round(_rng.gauss(4, 1.2), 2) for _ in range(60)]
        + [round(_rng.gauss(6, 2.5), 2) for _ in range(60)]
        + [round(_rng.gauss(9, 1.5), 2) for _ in range(60)]
    ),
    "규모": [("소" if _rng.random() < 0.5 else "대") for _ in range(180)],
}
"""

EXAMPLES = [
    ('기본 — inner="box" 가 사분위 상자를 겹친다', 'sp.violinplot(REVIEW, x="팀", y="시간")'),
    ("inner=None 은 밀도 윤곽만 남긴다", 'sp.violinplot(REVIEW, x="팀", y="시간", inner=None)'),
    (
        "bandwidth= 를 작게 주면 곡선이 데이터를 더 따라간다",
        'sp.violinplot(REVIEW, x="팀", y="시간", bandwidth=0.4)',
    ),
    ("hue= 는 카테고리 밴드를 나눠 바이올린을 나란히 놓는다", 'sp.violinplot(REVIEW, x="팀", y="시간", hue="규모")'),
    (
        "tooltip=True — 윤곽에서 읽을 수 없는 사분위를 말한다",
        'sp.violinplot(REVIEW, x="팀", y="시간", hue="규모", tooltip=True)',
    ),
    (
        "inner=None 이어도 사분위는 말한다 — 끈 것은 주석이지 데이터가 아니다",
        'sp.violinplot(REVIEW, x="팀", y="시간", inner=None, tooltip=True)',
    ),
]

INTERACTIONS = {4: "toggle", 5: "toggle"}

NOTES = [
    "네 번째와 다섯 번째 그림에 체크박스가 붙어 있다. 이 페이지의 CSS 와 마크업이고 JavaScript 는 0줄이다.",
    "이 패키지에서 값을 읽어낼 눈금이 없는 유일한 모양이다. y 축은 값의 범위를 주지만 폭은 차트 전체가 공유하는 "
    "peak 에 맞춰 스케일된 밀도라서, 데이터의 가운데 절반이 어디 있는지는 그림 어디에도 안 적혀 있다. "
    "tooltip=True 가 그걸 말한다 — 카테고리, hue 그룹, Q1·중앙값·Q3, 그리고 몇 개의 값에서 나온 곡선인지.",
    "여섯 번째 그림은 inner=None 인데도 사분위를 말한다. 끈 것은 주석이지 데이터가 아니다 — 숫자는 상자가 아니라 "
    "곡선이 계산된 값들을 설명한다. 오히려 상자가 없으니 그 숫자를 읽을 길이 툴팁밖에 없다.",
    "바이올린 하나의 세 마크(윤곽·안쪽 상자·중앙값 눈금)가 같은 문장을 받는다. 포인터는 자기 밑의 맨 위 요소에서 "
    "멈추므로 <title> 없는 마크는 글리프에 뚫린 구멍이다 — 제목 없는 안쪽 상자는 반응하는 바이올린 한가운데의 "
    "죽은 자리로 읽힌다.",
    "툴팁의 사분위와 안쪽 상자는 같은 quantiles() 호출에서 나온다. 두 번 계산하면 힌지 정의가 어긋나도 아무도 " "모른다.",
    "모든 카테고리가 하나의 y 그리드와 하나의 peak 을 공유한다. 그래서 폭끼리 견줘진다 — 카테고리마다 따로 정규화하면 폭이 서로 다른 것을 뜻하게 된다.",
    "그 공유에는 대가가 있다. 카테고리들의 크기가 자릿수로 다르면 그리드 간격이 좁은 쪽의 대역폭을 넘어서고, 그 카테고리는 어디서나 0 으로 평가돼 수직선처럼 그려진다.",
    "(카테고리, hue) 그룹마다 값이 2개 이상이고 분산이 0 이 아니어야 한다. 아니면 카테고리 이름을 대고 거부한다.",
    'inner 는 "box" 또는 None 이다. inner="box" 의 사분위는 기본 모드 boxplot 이 그렸을 상자와 같은 자리에 온다.',
    "bandwidth= 는 수치 또는 scott·silverman 이다. 작을수록 곡선이 데이터를 따라가고 클수록 매끄러워진다.",
    "boxplot 과 위치 인자 (data, x, y, hue) 가 같다. 다만 mode= 에 해당하는 인자는 없다.",
]
