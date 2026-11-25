"""
규칙 · 앱 지식 회귀 시험 (AI 호출 없음). 규칙을 고칠 때마다 돌려서 다른 화면이 깨지지 않았는지 확인.
python -I regress.py
설계 제안: 4.1.2 정답셋 옆에 '화면 → 기대 행동' 표로 두고 CI(GitHub Actions)에서 돌림
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings("ignore")
import eval_v2
import guide_sim as G

T = G.SLOTS_TRAIN
GJ = dict(T, ARRIVAL="경주", DATE="11월 27일 (금)", DATE_SHORT="11월 27일")
F, F2 = G.SLOTS_FOOD, G.SLOTS_FOOD2
# (화면, 슬롯, 세션이 기억하는 고른 칸, 기대: (행동, 글자 일부) 또는 화면 종류)
CASES = [
    ("korail/k00_main", T, (), ("TAP", "출발역선택")),
    ("korail/k02_dep_station", T, (), ("TAP", "서울")),
    ("korail/k03_after_dep", T, (), ("TAP", "도착역")),
    ("korail/k05_arr_major", T, (), ("TAP", "초성 탭 'ㅂ'")),
    ("korail/k06_arr_b", T, (), ("TAP", "부산")),
    ("korail/k07_both", T, (), ("TAP", "가는날")),
    ("korail/k10_date", T, (), ("TAP", "11월 26일")),
    ("korail/k01_after_search", T, (), "ALERT"),
    ("korail/k08_result", T, (), None),                       # 앱 지식 없음 → AI
    ("korail/k07_both", GJ, (), ("TAP", "도착역")),            # 도착이 부산인데 경주를 원함 → 조회로 건너뛰면 안 됨
    ("baemin/b00_home", F, (), ("TAP", "패스트푸드")),
    ("baemin/b01_fastfood", F, ("CATEGORY",), ("SCROLL", "맥도날드")),
    ("baemin/b02_list_scroll", F, ("CATEGORY",), ("TAP", "맥도날드 ○○점")),
    ("baemin/b04_store_menu", F, ("CATEGORY", "STORE"), ("TAP", "불고기 버거")),
    ("baemin/W01_wrong", F, (), ("SCROLL", "맥도날드")),       # 잘못 누른 화면: 세션 없이 보면 착각(알려진 한계 — clickedLabel로 해결)
    ("eats/e00_home", F2, (), ("SCROLL", "버거")),
    ("eats/e02_cat3", F2, (), ("TAP", "버거")),
    ("eats/e03_burger", F2, ("CATEGORY",), ("TAP", "맥도날드")),
    ("eats/e04_mcd", F2, ("CATEGORY", "BRAND"), ("TAP", "맥도날드 ○○")),
    ("coupang/c01_detail", {}, (), "PAYMENT_NEAR"),
    ("coupang/c00_home", {}, (), None),
    ("nmap/n00_home", {}, (), "POPUP"),
    ("youtube/y02_player", {}, (), "AD_PLAYING"),
    ("bustago/t03", {}, (), "ALERT"),
    ("bustago/t08_next_day", {}, (), "NO_RESULT"),
    ("yogiyo/Y05", {}, (), "POPUP"),
    ("korail/F02_bighome", GJ, (), ("TAP", "열차 조회")),       # 큰글씨 모드: 이미 다 맞음
    ("korail/F02_bighome", T, (), ("TAP", "도착역 경주")),       # 큰글씨 모드: 도착이 틀림 → 도착 칸 열기
    ("korail/F01_big", {}, (), "CONFIRM"),
    ("korail/k07_both", dict(T, DATE="11월 25일 (수)", DATE_SHORT="11월 25일", COUNT="2"), (), ("TAP", "인원")),  # 두 장 → 인원 칸 열기
    ("korail/k07_both", dict(T, DATE="11월 25일 (수)", DATE_SHORT="11월 25일"), (), ("TAP", "열차 조회")),
    ("korail/P01_count", dict(T, PAX="경로:2"), (), ("TAP", "경로 인원증가")),     # 경로 2명: 먼저 경로 늘리기
    ("korail/P01_count", dict(T, PAX="어른:1"), (), ("TAP", "선택 완료")),         # 이미 어른 1명 → 확정       # 인원 말 안 함 → 기본 1명                     # 「네/아니오」 확인 창 → 어르신이 고름
    ("korail/k00_main", {"ARRIVAL": "부산"}, (), ("ASK", "DEPARTURE")),  # 출발역을 말 안 함 → 되묻기
]


def run(name, slots, done):
    ns = eval_v2.nodes_of(name)
    st, _ = G.screen_type(ns)
    if st != "NORMAL":
        return st
    pkg = next((n["pkg"] for n in ns if n["pkg"]), "?")
    k = G.knowledge(pkg, ns, slots, 0, set(done))
    return (k[0], k[1]) if k else None


def main():
    ok = bad = 0
    for name, slots, done, exp in CASES:
        if not os.path.exists(os.path.join(eval_v2.DATA, name + ".xml")):
            print("파일 없음", name); continue
        got = run(name, slots, done)
        if isinstance(exp, tuple):
            good = isinstance(got, tuple) and got[0] == exp[0] and exp[1].replace(" ", "") in got[1].replace(" ", "")
        else:
            good = got == exp
        ok += good; bad += (not good)
        print("✅" if good else "❌", name.ljust(26), "기대", exp, "| 결과", got if not isinstance(got, tuple) else (got[0], got[1][:30]))
    print(f"\n{ok}/{ok + bad} 통과")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
