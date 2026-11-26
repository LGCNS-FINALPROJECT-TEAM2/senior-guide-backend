# Guide 판단 순서 시뮬레이션 결과 (guide_sim.py)

규칙 → 앱 지식 → AI(저장된 스크린숏+Haiku v2 답) → 검사 층. 새 AI 호출 없음.

| 화면 | 기대 | 화면 종류 | 푼 단계 | 결과 |
|---|---|---|---|---|
| korail/k00_main | 출발역선택 | NORMAL | 앱 지식 | TAP '출발역선택' [DEPARTURE(열기)] |
| korail/k02_dep_station | 서울 | NORMAL | 앱 지식 | TAP '서울' [DEPARTURE] |
| korail/k03_after_dep | 도착역선택 | NORMAL | 앱 지식 | TAP '도착역선택' [ARRIVAL(열기)] |
| korail/k05_arr_major | 부산 없음 → 초성/스크롤 | NORMAL | 앱 지식 | TAP '초성 탭 'ㅂ'' [ARRIVAL(목록에서 안 보임)] |
| korail/k06_arr_b | 부산 | NORMAL | 앱 지식 | TAP '부산' [ARRIVAL] |
| korail/k07_both | 가는날 열기(25일 → 26일) | NORMAL | 앱 지식 | TAP '가는날, 2026년 11월 25일 (수) 01:46, 버튼' [DATE(열기)] |
| korail/k01_after_search | 확인(안내 팝업) | ALERT | 규칙 | ALERT → TAP '확인' |
| korail/k08_result | 열차 줄(스크린숏) | NORMAL | AI | TAP 'KTX 001' → 검사 TAP |
| korail/k10_date | 11월 26일 (목) | NORMAL | 앱 지식 | TAP '11월 26일 (목)' [DATE(고름)] |
| baemin/b00_home | 팝업 닫기(숨은 팝업) / 패스트푸드 | NORMAL | 앱 지식 | TAP '패스트푸드' [CATEGORY] |
| baemin/b02_list_scroll | 맥도날드 ○○점 | NORMAL | 앱 지식 | TAP '맥도날드 ○○점, 배달팁 0원 4.4 (632) 알뜰배달 약 19분 배민' [STORE] |
| baemin/b04_store_menu | 불고기 버거 이름 | NORMAL | 앱 지식 | TAP '인기 5위 불고기 버거 불고기버거 ,4,700원 리뷰 25' [ITEM] |
| eats/e00_home | 카테고리 줄 밀기 | NORMAL | 앱 지식 | SCROLL ''버거' 안 보임 → left로 밀기' [CATEGORY] |
| eats/e02_cat3 | 버거 | NORMAL | 앱 지식 | TAP '버거' [CATEGORY] |
| eats/e03_burger | 맥도날드 칩 | NORMAL | 앱 지식 | TAP '맥도날드' [BRAND] |
| eats/e06_menu | 트리플 치즈버거 이름 | NORMAL | 앱 지식 | TAP '트리플 치즈버거 라지 세트 버거 + 후렌치 후라이 (L) + 콜라 (L)' [ITEM] |
| coupang/c01_detail | STOP | PAYMENT_NEAR | 규칙 | PAYMENT_NEAR → STOP |
| nmap/n00_home | 나중에 할게요 | POPUP | 규칙 | POPUP → TAP '나중에 할게요' |
| youtube/y02_player | WAIT | AD_PLAYING | 규칙 | AD_PLAYING → WAIT |
| bustago/t03 | 확인(알림) | ALERT | 규칙 | ALERT → TAP '확인' |
| bustago/t08_next_day | 결과 없음 안내 | NO_RESULT | 규칙 | NO_RESULT → ASK |

**21화면 중 규칙 6 · 앱 지식 14 · AI 1 · 못 풂 0**
→ AI 호출이 필요한 화면 비율 5% (모든 화면을 스크린숏+Haiku로 물으면 21회 × $0.00037 ≈ $0.0078, 이 순서면 ≈ $0.0004)