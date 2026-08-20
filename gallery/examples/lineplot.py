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

NOTES = [
    "점은 x 순으로 정렬된다. 같은 x 를 가진 행이 둘이면 수직 선분이 되고, estimator= 로 접을 수 있다.",
    "interpolate= 는 linear(기본)·quadratic·cubic·hermite·lagrange·trigonometric 을 받는다.",
    "estimator= 와 info= 는 함께 쓸 수 없다. 각주 표는 1행 = 1마크를 전제하는데 집계가 그 전제를 깬다.",
    '날짜 컬럼에 xscale="log" 는 거부된다. 타임스탬프의 로그는 1970 을 0 으로 골랐다는 사실에서만 나오는 비율이다.',
    "aware datetime 과 naive datetime 을 한 컬럼에 섞으면 컬럼명을 대고 거부한다.",
]
