TITLE = "kdeplot"

SUMMARY = "수치 한 컬럼의 분포를 곡선 하나로 추정해 그린다. 히스토그램과 달리 구간 경계가 없다."

REQUIRES = "x: 수치(그룹마다 2개 이상, 분산 0 불가) · hue(선택): 아무 타입"

SETUP = """
import random

import svgplot as sp

_rng = random.Random(5)
SESSION = {
    "체류분": (
        [round(_rng.gauss(3, 1.0), 2) for _ in range(150)]
        + [round(_rng.gauss(11, 3.5), 2) for _ in range(150)]
    ),
    "기기": ["모바일"] * 150 + ["데스크톱"] * 150,
}
"""

EXAMPLES = [
    ("기본", 'sp.kdeplot(SESSION, x="체류분")'),
    ("fill=True 는 곡선 아래를 축까지 채우고 윤곽을 남긴다", 'sp.kdeplot(SESSION, x="체류분", fill=True)'),
    (
        "hue= 그룹은 하나의 x 그리드를 공유한다",
        'sp.kdeplot(SESSION, x="체류분", hue="기기", fill=True)',
    ),
    (
        "bandwidth= 를 작게 주면 곡선이 데이터를 더 따라간다",
        'sp.kdeplot(SESSION, x="체류분", hue="기기", bandwidth=0.3)',
    ),
]

NOTES = [
    "hue= 그룹은 하나의 x 그리드를 공유한다. histplot 이 구간 경계를 공유하는 것과 같은 이유로, 그래야 곡선끼리 같은 자리에서 견줘진다.",
    "그 공유의 대가는 violinplot 과 같다 — 그룹들의 크기가 자릿수로 다르면 그리드 간격이 좁은 쪽의 대역폭을 넘어서고 그 그룹이 어디서나 0 으로 평가된다.",
    "그룹마다 값이 2개 이상이고 분산이 0 이 아니어야 한다. 아니면 그룹 이름을 대고 거부한다.",
    "bandwidth= 는 수치 또는 scott·silverman 이다. 곡선의 매끄러움은 데이터가 아니라 이 값이 정한다.",
    "입력이 2,000 점에서 잘린다. 그보다 많은 표본이 곡선 모양을 눈에 띄게 바꾸지 않기 때문이다.",
]
