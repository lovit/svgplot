# SVG 기회와 위험 — SVG여서 가능한 것 vs SVG여서 어려운 것

## SVG여서 가능한 것 (differentiation thesis)

| 기회 | 근거 | 세 라이브러리 현황 |
|---|---|---|
| **렌더 후 재테마(다크모드 등)를 재렌더 없이 CSS 교체로** | SVG는 DOM/CSS 트리이므로 스타일과 지오메트리를 분리 가능 | pygal은 이미 증명(class 기반), matplotlib은 정반대(geometry dump, `02-matplotlib.md` A8) |
| **hover 툴팁을 외부 JS 없이 CSS `:hover`+`<title>`만으로** | SVG는 브라우저 네이티브 CSS 상호작용을 지원 | pygal조차 외부 CDN JS(`pygal.js`)에 위임(`01-pygal.md` A8) — 아무도 안 하고 있음 |
| **접근성(`role="img"`, `aria-label`, `<title>`/`<desc>`)을 기본값으로** | SVG는 표준 접근성 속성을 1급으로 지원하는 문서 포맷 | 세 라이브러리 모두 사실상 전무(`01`/`02`/`03` A9) — 가장 저비용·고차별화 지점 |
| **벡터 선명도 — 어떤 해상도/줌에서도 흐려지지 않음** | 벡터 포맷의 본질적 속성 | pygal/matplotlib SVG 백엔드 둘 다 이미 벡터이므로 이 자체는 차별점 아님(전제조건) |
| **매우 작은 파일 크기(단순 차트 기준)** | path/rect 요소 수가 적으면 PNG보다 훨씬 작음 | 데이터 포인트 수가 적을 때만 성립(아래 위험 참고) |
| **CSS `prefers-color-scheme`/`prefers-reduced-motion` 자동 대응** | 브라우저가 SVG를 일반 문서처럼 취급 | 세 라이브러리 모두 미대응 |
| **`<a>` 링크로 요소를 클릭 가능하게** | SVG는 `<a xlink:href>` 네이티브 지원 | 세 라이브러리 모두 활용 안 함 — 대시보드/리포트 용도로 실질 가치 있음 |
| **애니메이션(SMIL/CSS transition)을 무거운 GUI 이벤트 루프 없이** | matplotlib의 애니메이션은 GUI 백엔드 이벤트 루프 전제(`02-matplotlib.md` A8), SVG는 CSS transition만으로 정적 파일 안에서 애니메이션 가능 | matplotlib의 애니메이션 인프라는 SVG 출력과 완전히 분리된 별세계 — 참고할 선례가 없다는 것 자체가 기회 |
| **DOM 요소 단위로 스크립트가 개별 데이터 포인트에 접근** | 각 마크가 클래스/id를 가진 실제 DOM 노드 | pygal은 `<desc>`에 값을 심어두는 수준(`01-pygal.md` A8) — 더 정교화 가능 |

## SVG여서 어려운 것 (설계 시 인정하고 우회해야 할 것)

| 위험 | 근거 | 우회 전략 |
|---|---|---|
| **자동 레이아웃(legend 자동 배치, 여백 자동조정)이 텍스트 bbox 측정을 전제** | matplotlib의 constrained/tight layout은 FreeType 기반 glyph metrics 없이는 동작 불가(`02-matplotlib.md` A6) — 이것이 조사 전체에서 가장 중요한 기술적 제약 | `12-aesthetics.md` 참고 — 상대크기 지정/고정 프리셋/근사 폭 테이블로 시작, 정밀 측정은 후순위 opt-in |
| **대용량 산점도/히트맵에서 DOM 노드 폭증 → 파일 비대·렌더 성능 저하** | 데이터 포인트마다 `<circle>`/`<rect>` 하나씩 필요(`10-feature-matrix.md` A1의 SVG-위험 뷰) | 포인트 수 임계치 이상이면 canvas/PNG 폴백을 안내, 또는 포인트 클러스터링 |
| **등고선/삼각분할/유선적분 등 기하 알고리즘이 필요한 차트** | contour/streamplot/tricontour는 marching squares, Delaunay 등 비자명한 수치 알고리즘 전제(`02-matplotlib.md` A1) | 1차 스코프에서 명시적 제외(`14-scope-recommendation.md`) |
| **수식 렌더링(mathtext/LaTeX)** | 자체 TeX 서브셋 파서가 필요한 큰 구현 부담(`02-matplotlib.md` A6) | 1차 제외, 필요 시 MathML이나 이미지 임베드로 우회 |
| **3D** | SVG는 2D 벡터 포맷 — 원천적으로 부적합 | 스코프 밖(공식 비목표) |
| **CJK 등 비라틴 텍스트의 폭 측정/줄바꿈** | 폰트 메트릭 없이는 텍스트 폭 추정이 더 부정확해짐(라틴 문자보다 폭 변동이 큼) | 기본 폰트 스택에 CJK 폴백 포함 + 보수적인 고정 여백으로 시작 |
| **뷰어(브라우저/이미지 뷰어)마다 폰트 렌더링이 달라질 수 있음** | `<text>` 요소는 로컬 폰트 가용성에 의존(matplotlib `svg.fonttype='none'`과 동일한 트레이드오프, `02-matplotlib.md` A8) | 텍스트를 path로 구울지(`fonttype='path'`) 실제 text로 남길지(`fonttype='none'`) 선택 가능하게 — 단, CSS 재테마 원칙(`12-aesthetics.md`)을 지키려면 텍스트는 실제 `<text>`+CSS가 전제여야 함 |

## 결론

SVG 기회 항목 중 "접근성 기본값"과 "CSS 재테마"는 구현 비용이 낮으면서도 세 라이브러리 모두가 놓친 공백이라 최우선 차별화 지점으로 삼는다(`12-aesthetics.md`, `14-scope-recommendation.md`의 "필수" 항목과 직결). 반대로 텍스트 bbox 측정 문제는 "언젠가 풀어야 할 숙제"가 아니라 **아키텍처를 결정하는 최상위 제약**으로 취급해야 한다 — 이를 인정하지 않고 matplotlib 수준의 자동 레이아웃을 목표로 하면 프로젝트 범위가 통제 불능으로 커진다.
