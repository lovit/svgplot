TITLE = "ecdfplot"

SUMMARY = '값을 정렬해 "이 값 이하가 전체의 몇 퍼센트인가"를 계단으로 그린다. 구간도 대역폭도 고르지 않는다.'

REQUIRES = "x: 수치 · hue(선택): 아무 타입"

SETUP = """
import random

import svgplot as sp

_rng = random.Random(13)
RESPONSE = {
    "ms": (
        [round(_rng.gauss(120, 30)) for _ in range(200)]
        + [round(_rng.gauss(260, 90)) for _ in range(200)]
    ),
    "버전": ["v1"] * 200 + ["v2"] * 200,
}
"""

EXAMPLES = [
    ('기본 — stat="proportion" 은 0에서 1까지 오른다', 'sp.ecdfplot(RESPONSE, x="ms")'),
    ('stat="count" 는 비율 대신 누적 행 수를 쓴다', 'sp.ecdfplot(RESPONSE, x="ms", stat="count")'),
    (
        "complementary=True 는 1에서 빼 생존함수로 뒤집는다",
        'sp.ecdfplot(RESPONSE, x="ms", complementary=True)',
    ),
    ("hue= 는 그룹마다 계단을 하나씩 그린다", 'sp.ecdfplot(RESPONSE, x="ms", hue="버전")'),
]

NOTES = [
    "정렬과 누적 비율만 쓰므로 stats 모듈을 거치지 않는다. 구간 폭이나 대역폭 같은 고를 것이 없어서 같은 데이터가 언제나 같은 계단을 만든다.",
    'stat 은 "proportion" 또는 "count" 다.',
    'complementary=True 는 꼬리를 읽을 때 쓴다 — "몇 퍼센트가 이 값을 넘는가"가 y 축이 된다.',
    'stat="count" 에 hue= 를 주면 그룹들이 가장 큰 그룹에 맞춘 y 축을 공유한다. 그룹 크기가 다르면 계단의 최종 높이도 다르다.',
    "히스토그램과 달리 구간 경계에 따라 모양이 바뀌지 않는다. 대신 값이 몰린 곳은 계단의 기울기로만 드러난다.",
]
