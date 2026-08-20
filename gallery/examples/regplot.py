TITLE = "regplot"

SUMMARY = "산점도 위에 최소제곱 적합선을 얹고, 부트스트랩으로 잡은 신뢰대역을 함께 그린다."

REQUIRES = "x: 수치 · y: 수치 · x·y 가 모두 있는 행이 3개 이상 · hue 는 받지 않는다"

SETUP = """
import random

import svgplot as sp

_rng = random.Random(17)
_ad = [round(_rng.uniform(5, 95), 1) for _ in range(60)]
SPEND = {
    "광고비": _ad,
    "문의수": [round(18 + 1.9 * value + _rng.gauss(0, 22), 1) for value in _ad],
}
"""

EXAMPLES = [
    ("기본 — 95% 신뢰대역과 산점도", 'sp.regplot(SPEND, x="광고비", y="문의수")'),
    ("ci=None 은 대역 없이 선만 그린다", 'sp.regplot(SPEND, x="광고비", y="문의수", ci=None)'),
    ("ci=0.99 는 대역을 넓힌다", 'sp.regplot(SPEND, x="광고비", y="문의수", ci=0.99)'),
    ("scatter=False 는 점을 빼고 적합만 남긴다", 'sp.regplot(SPEND, x="광고비", y="문의수", scatter=False)'),
]

NOTES = [
    "같은 데이터와 같은 seed= 면 SVG 가 바이트 단위로 같다. 부트스트랩은 지역 난수 생성기를 쓰고 seed 의 기본값이 0 이다.",
    "ci=None 이면 부트스트랩 자체를 건너뛴다. 대역이 필요 없을 때 n_boot 만큼의 계산이 사라진다.",
    "x·y 가 모두 있는 행이 3개 미만이면 거부한다. 점 둘로 그은 선에는 신뢰대역이 의미를 갖지 않는다.",
    "hue= 가 없다. 그룹마다 적합을 따로 하려면 facet 으로 패널을 나눈다.",
    "logistic·robust·lowess 적합은 범위 밖이다 — statsmodels 의존이 생기고, 이 패키지는 런타임 의존성을 두지 않는다.",
]
