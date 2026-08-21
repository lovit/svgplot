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

# 그룹 크기가 다른 같은 데이터. stat="count" 는 이것을 하나의 y 축에 얹는다.
UNEVEN = {
    "ms": RESPONSE["ms"][:200] + RESPONSE["ms"][200:260],
    "버전": ["v1"] * 200 + ["v2"] * 60,
}
"""

EXAMPLES = [
    ('기본 — stat="proportion" 은 0에서 1까지 오른다', 'sp.ecdfplot(RESPONSE, x="ms")'),
    ('stat="count" 는 비율 대신 누적 행 수를 쓴다', 'sp.ecdfplot(RESPONSE, x="ms", stat="count")'),
    (
        "complementary=True 는 1에서 빼 생존함수로 뒤집는다",
        'sp.ecdfplot(RESPONSE, x="ms", complementary=True)',
    ),
    ("hue= 는 그룹마다 계단을 하나씩 그린다", 'sp.ecdfplot(UNEVEN, x="ms", hue="버전")'),
    (
        'stat="count" 와 hue= 를 함께 주면 그룹들이 하나의 y 축을 나눠 쓴다',
        'sp.ecdfplot(UNEVEN, x="ms", hue="버전", stat="count")',
    ),
]

INTERACTIONS = {4: "toggle", 5: "toggle"}

NOTES = [
    "네 번째와 다섯 번째 그림에 체크박스가 붙어 있다. 이 페이지의 CSS 와 마크업이고 JavaScript 는 0줄이다.",
    "네 번째와 다섯 번째는 같은 데이터(v1 200행, v2 60행)를 stat= 만 바꿔 그린 것이다. 두 그림이 같은 기제를 쓰지만 값은 다르게 치른다. "
    'stat="proportion" (네 번째)은 각 계단이 자기 그룹 수로 나뉘므로 60행짜리 v2 도 1까지 오른다 — 하나를 감춰도 남은 계단이 y 를 0에서 1까지 그대로 채우는, '
    "**y 축**이 거짓이 되지 않는 드문 경우다. "
    'stat="count" (다섯 번째)는 그룹들이 가장 큰 그룹에 맞춘 축을 나눠 쓰므로, v1 을 감추면 200까지 뻗은 축 위에 60까지만 오르는 계단 하나가 남는다. '
    "그런데도 둘 다 흐리게 한다 — 기제가 페이지마다 다르면 독자가 매번 어느 쪽인지 확인해야 하고, 그 확인은 그림이 아니라 문서를 읽어야 알 수 있다.",
    "y 축만 그렇다. x 축은 어느 쪽이든 남은 데이터보다 넓은 채로 남는다 — 위 문단이 말하는 그대로다. "
    "네 번째와 다섯 번째 모두 x 축이 41~444 인데, v2 를 감추면 남는 v1 은 41~225 구간에만 있다. 흐리게 하는 쪽을 고른 이유가 y 축 하나로 줄지 않는 것이 이 때문이다.",
    "정렬과 누적 비율만 쓰므로 stats 모듈을 거치지 않는다. 구간 폭이나 대역폭 같은 고를 것이 없어서 같은 데이터가 언제나 같은 계단을 만든다.",
    'stat 은 "proportion" 또는 "count" 다.',
    'complementary=True 는 꼬리를 읽을 때 쓴다 — "몇 퍼센트가 이 값을 넘는가"가 y 축이 된다.',
    'stat="count" 에 hue= 를 주면 그룹들이 가장 큰 그룹에 맞춘 y 축을 공유한다. 그룹 크기가 다르면 계단의 최종 높이도 다르다.',
    "히스토그램과 달리 구간 경계에 따라 모양이 바뀌지 않는다. 대신 값이 몰린 곳은 계단의 기울기로만 드러난다.",
]
