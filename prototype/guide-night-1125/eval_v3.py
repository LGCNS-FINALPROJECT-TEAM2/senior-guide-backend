"""AI 비교 표본 늘리기: 오늘 새로 모은 어려운 화면 10개 (v2 프롬프트 + 검사 층). 결과 eval_v3_results.jsonl"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings("ignore")
import eval_v2
TOPM = [(0, 60, 1080, 360)]
eval_v2.CASES = [
    ("korail/P01_count", "기차표 어른 두 장으로 알아보고 싶어", "어른 인원증가", []),
    ("korail/F02_bighome", "내일 서울에서 부산 가는 기차 알아보고 싶어", "도착역 칸(경주 → 부산) 열기", []),
    ("korail/F01_big", "기차표 알아보고 싶어", "확인 창 → PICK_BY_USER/STOP ('네' 대신 누르면 안 됨)", []),
    ("yogiyo/Y05", "햄버거 시켜 먹고 싶어", "홍보 시트 닫기", TOPM),
    ("eats/L01", "맥도날드 햄버거 먹고 싶어", "맥도날드 칩(맨 위 광고 버거킹 아님)", TOPM),
    ("baemin/S02_search", "맥도날드 햄버거 먹고 싶어", "검색창 · 음성 안내 / 삭제 · 최근 검색어 누르면 안 됨", [(0, 380, 1080, 640)]),
    ("baemin/M01_list", "맥도날드 햄버거 먹고 싶어", "SCROLL next (할인 가게 아님)", TOPM),
    ("bustago/t01_home", "동서울에서 부산 가는 버스 알아보고 싶어", "출발지 칸", []),
    ("kakaomap/m01_route", "기차로 부산 가는 제일 빠른 방법", "첫 기차 경로(2시간 19분 KTX) 안내", [(0, 220, 940, 480)]),
    ("nmap/n02_time", "내일 아침 9시 출발로 바꾸고 싶어", "휠 → SCROLL · PICK_BY_USER · unsure (확인 먼저 누르면 틀림)", []),
]
eval_v2.OUT = os.path.join(eval_v2.BASE, "eval_v3_results.jsonl")
eval_v2.main()
