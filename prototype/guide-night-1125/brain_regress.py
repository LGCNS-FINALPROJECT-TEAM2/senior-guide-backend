"""
brain.py 회귀 시험 (폰 · API 키 없이). python -I brain_regress.py  → 실패하면 종료 코드 1
  ① 후보 버튼 뽑기 ② 울타리(AI 안 부르는 화면) ③ 하네스 검사(틀린 AI 답 막기) ④ 화면 기억(밀면 · 누르면) ⑤ 경험 재사용 · 되돌아옴
  ⑥ 개인정보 가림 ⑦ 화면 지문 · 후보 자르기 · 짧은 답 ⑧ 폰 읽기(DUMP3 · CLICK)  (11/25 밤: 누른 버튼 신호 · 자리표시 경험 · 다시 판단 · 「다 됐어요」 확인 추가)
"""
import os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["GUIDE_LEARN"] = tempfile.mkdtemp(prefix="brain_test_")  # 진짜 learn/을 건드리지 않음
import warnings; warnings.filterwarnings("ignore")
import eval_v2
import brain as B

ok = bad = 0


def t(name, cond, info=""):
    global ok, bad
    ok += bool(cond); bad += (not cond)
    print("✅" if cond else "❌", name, "" if cond else f"| {info}")


N = eval_v2.nodes_of
SL = {"DEPARTURE": "서울", "ARRIVAL": "부산", "DATE": "11월 26일 (목)", "DATE_SHORT": "11월 26일"}

# ① 후보 버튼
c = B.candidates(N("korail/k00_main"))
t("코레일 첫 화면 후보에 '출발역선택'", any("출발역선택" in x["text"] for x in c), [x["text"] for x in c][:10])
t("코레일 첫 화면 후보에 '열차 조회'", any("열차 조회" in x["text"] for x in c))
t("후보 번호 c1부터", c and c[0]["id"] == "c1")
cc = B.candidates(N("coupang/c01_detail"))
t("쿠팡 상세: 구매 · 담기 버튼은 ⛔", any(x["ban"] for x in cc), [(x["text"][:15], x["ban"]) for x in cc][:12])
t("지문은 같은 화면이면 같음", B.fingerprint(N("korail/k00_main")) == B.fingerprint(N("korail/k00_main")))
t("지문은 다른 화면이면 다름", B.fingerprint(N("korail/k00_main")) != B.fingerprint(N("korail/k03_after_dep")))

# ② 울타리
for name, want in [("coupang/c01_detail", "STOP"), ("youtube/y02_player", "WAIT"), ("korail/F01_big", "PICK_BY_USER"),
                   ("bustago/t08_next_day", "ASK"), ("korail/k01_after_search", "TAP"), ("nmap/n00_home", "TAP")]:
    ns = N(name); pkg = next(n["pkg"] for n in ns if n["pkg"])
    g = B.guard(ns, pkg)
    t(f"울타리 · 빠른 길 {name} → {want}", g and g["action"] == want, g)
t("보통 화면(코레일 첫 화면)은 울타리 없음 → AI", B.guard(N("korail/k00_main"), "com.korail.talk") is None)
fake = [dict(text="비밀번호", desc="", click=False, pkg="com.korail.talk", b=[0, 0, 500, 100], edit=False),
        dict(text="확인", desc="", click=True, pkg="com.korail.talk", b=[0, 200, 500, 300], edit=False)]
g = B.guard(fake, "com.korail.talk")
t("비밀번호 글자 화면은 글자도 AI로 안 보냄", g and g["action"] == "STOP" and "AI로 안 보냄" in g["label"], g)
seat = [dict(text="2석 중 2석 선택됨", desc="", click=False, pkg="com.korail.talk", b=[0, 0, 500, 100], edit=False)]
g = B.guard(seat, "com.korail.talk")
t("좌석 다 고름 → 예매 앞 멈춤", g and g["action"] == "STOP" and g["label"] == "예매 앞 멈춤", g)

# ③ 하네스
ids = {x["id"]: x for x in cc}
ban_id = next(x["id"] for x in cc if x["ban"])
okc = next((x["id"] for x in cc if not x["ban"]), None)
_, e = B.check_plan({"action": "TAP", "pick": "c999"}, cc); t("없는 후보 → 다시 묻기", e and "후보에 없음" in e, e)
_, e = B.check_plan({"action": "TAP", "pick": ban_id}, cc); t("⛔ 후보 → 다시 묻기", e and "⛔" in e, e)
_, e = B.check_plan({"action": "JUMP"}, cc); t("없는 action → 다시 묻기", e and "없는 값" in e, e)
_, e = B.check_plan({"action": "SCROLL", "scroll_dir": "none"}, cc); t("방향 없는 밀기 → 다시 묻기", e is not None)
_, e = B.check_plan("문자열", cc); t("JSON 객체 아님 → 다시 묻기", e is not None)
o, e = B.check_plan({"action": "tap", "pick": okc}, cc); t("맞는 답은 통과(소문자 action도)", o and e is None and o["action"] == "TAP", e)
d = B.to_decision(o, N("coupang/c01_detail"), "AI")
t("TAP 판단에 표시할 칸 · 누를 칸이 붙음", d["b"] == ids[okc]["b"] and d.get("btn") is ids[okc]["node"])

# ④ 화면 기억: 밀면 나온 것 · 누르면 간 화면이 다음 프롬프트에 들어감
B.reset()
a, b = N("baemin/b01_fastfood"), N("baemin/b02_list_scroll")
dA = dict(action="SCROLL", scroll_dir="down", layer="AI", plan={"expect_next": "맥도날드 가게가 보이는 목록"}, step_id="1")
B.track(B.fingerprint(a), dA)
B.observe(a, dA, b, {"BRAND": "맥도날드"})
r = B.mem().recall_text(a)
t("밀기 뒤: '아래로 밀면 나왔던 버튼'을 기억", "down로 밀면" in r and "맥도날드" in r, r[:200])
k0, k2 = N("korail/k00_main"), N("korail/k02_dep_station")
btn = next(x for x in B.candidates(k0) if "출발역선택" in x["text"])
dT = dict(action="TAP", pick_text=btn["text"], layer="AI", plan={"expect_next": "출발역 선택 시트"}, step_id="2")
B.reset(); B.track(B.fingerprint(k0), dT)
B.observe(k0, dT, k2, SL)
r = B.mem().recall_text(k0)
t("누른 뒤: '누르면 갔던 화면 + 그 화면 버튼'을 기억(다음 화면 미리 보기)", "누르면 갔던 화면" in r and "서울" in r, r[:300])
p = B.build_prompt("com.korail.talk", k0, B.candidates(k0), "서울에서 부산", SL)
t("프롬프트에 앱 지도 · 화면 기억 · 후보가 다 들어감", "[앱 지도]" in p and "[화면 기억]" in p and "[누를 수 있는 버튼]" in p)

# ⑤ 경험 (11/25 밤 바꿈): 실제로 누른 버튼이 안내와 같아야 「확인된 성공」, 값은 자리표시로 → 다른 목표에도
CALLS = []
def _fake_ai(pkg, ns, cands, goal, slots):  # 회귀 시험에선 진짜 AI를 안 부름
    CALLS.append(goal)
    return dict(action="STOP", pick="", scroll_dir="none", say="(가짜 AI)", screen="", confidence=0), ""
B.ask_ai = _fake_ai
ek0 = B.exp_key(k0, SL)
x = B.mem().exp.get(ek0)
t("누른 버튼을 모르는 성공은 ok_u로 따로 셈", x and x["ok_u"] == 1 and x["ok_v"] == 0 and x["fail"] == 0, x)
B.reset(); CALLS.clear()
d = B.decide("korail", k0, SL, "서울에서 부산")
t("확인 못 한 성공 1번은 아직 다시 안 씀 → AI", d["layer"] == "AI" and len(CALLS) == 1, (d["layer"], CALLS))
dT = dict(action="TAP", pick_text=btn["text"], b=btn["b"], layer="AI", plan={"action": "TAP"}, step_id="3", ek=ek0)
B.reset(); B.track(B.fingerprint(k0), dT)
B.observe(k0, dT, k2, SL, clicked=[dict(label="출발역선택", b=btn["b"])])
t("누른 버튼 = 안내 버튼 → 확인된 성공(ok_v)", B.mem().exp[ek0]["ok_v"] == 1)
B.reset(); CALLS.clear()
d = B.decide("korail", k0, SL, "서울에서 부산")
t("확인된 성공 → AI 안 부르고 경험으로", d["layer"] == "경험" and "출발역선택" in d["label"] and not CALLS, (d["layer"], d["label"], CALLS))

seoul = next(x for x in B.candidates(k2) if x["text"] == "서울")
ek2 = B.exp_key(k2, SL)
d2 = dict(action="TAP", pick_text="서울", b=seoul["b"], layer="AI", plan={"action": "TAP"}, step_id="4", ek=ek2)
k3 = N("korail/k03_after_dep")
B.reset(); B.track(B.fingerprint(k2), d2)
B.observe(k2, d2, k3, SL, clicked=[dict(label="서울", b=seoul["b"])])
SL2 = dict(SL, ARRIVAL="대구")
B.reset(); CALLS.clear()
d = B.decide("korail", k2, SL2, "서울에서 대구")
t("서울 → 부산에서 배운 「출발역 시트에서 {DEPARTURE}」를 서울 → 대구에도 씀", d["layer"] == "경험" and d["label"] == "서울" and not CALLS, (d["layer"], d.get("label"), CALLS))
SL3 = dict(SL, DEPARTURE="정동진")
B.reset(); CALLS.clear()
t("수원처럼 시트에 보이는 역이면 같은 경험으로 「수원」", B.decide("korail", k2, dict(SL, DEPARTURE="수원"), "수원에서")["label"] == "수원")
B.reset(); CALLS.clear()
d = B.decide("korail", k2, SL3, "정동진에서 부산")
t("출발역이 시트에 안 보이면(정동진) 열쇠가 달라 AI로", d["layer"] == "AI" and len(CALLS) == 1, (d["layer"], d.get("label")))

# 다른 걸 누름: 성공으로 안 셈
other = next(x for x in B.candidates(k0) if "간편 예매" in x["text"])
B.reset(); B.track(B.fingerprint(k0), dT)
before = dict(B.mem().exp[ek0])
B.observe(k0, dT, k2, SL, clicked=[dict(label="간편 예매", b=other["b"])])
t("안내와 다른 버튼을 누르면 성공으로 안 셈", B.mem().exp[ek0]["ok_v"] == before["ok_v"] and B.STATS["wrong_click"] == 1, B.mem().exp[ek0])

# 되돌아옴(A4): k0 →(출발역선택) k2 →(뒤로) k0 : k0 안내는 실패, k2의 안내는 성공으로 안 셈
B.reset()
d2b = dict(d2, step_id="5")
B.track(B.fingerprint(k0), dT); B.track(B.fingerprint(k2), d2b)
ok2 = (B.mem().exp[ek2]["ok_v"], B.mem().exp[ek2]["ok_u"])
B.observe(k2, d2b, k0, SL)
t("되돌아오면 앞 화면 안내를 실패로 셈", B.mem().exp[ek0]["fail"] == 1)
t("되돌아온 화면의 안내(뒤로 누름)는 성공으로 안 셈(A4)", (B.mem().exp[ek2]["ok_v"], B.mem().exp[ek2]["ok_u"]) == ok2)
B.reset(); CALLS.clear()
d = B.decide("korail", k0, SL, "서울에서 부산")
t("실패가 있는 경험은 다시 안 씀(AI로)", d["layer"] == "AI" and len(CALLS) == 1)

# 45초 그대로 → 다시 판단(A2), 두 번이면 멈춤
B.reset(); CALLS.clear()
fp0 = B.fingerprint(k0)
d = B.decide("korail", k0, SL, "g")
B.reject(fp0, d); d = B.decide("korail", k0, SL, "g")
t("「안 됨」 한 번 → 같은 화면을 AI에 다시 물음", len(CALLS) == 2 and any("✗" in h for h in B.HIST), (CALLS, B.HIST[-2:]))
B.reject(fp0, d); d = B.decide("korail", k0, SL, "g")
t("「안 됨」 두 번 → 직접 해 주세요(STOP)", d["action"] == "STOP" and len(CALLS) == 2, d)

# 「다 됐어요」 확인(D5)
def _ns(*texts):
    return [dict(text=x, desc="", click=True, pkg="com.korail.talk", b=[0, 100 * i, 500, 100 * i + 90], edit=False) for i, x in enumerate(texts)]
DS = {"DEPARTURE": "서울", "ARRIVAL": "부산", "DATE": "11월 26일 (목)", "DATE_SHORT": "11월 26일", "PAX": "어른:2"}
scr = _ns("서울 → 부산", "11월 25일 (수)", "다시 조회")
_, e = B.check_plan({"action": "DONE"}, B.candidates(scr), scr, DS)
t("DONE인데 날짜가 다르면 거절", e and "DATE" in e, e)
scr = _ns("서울 → 부산", "11월 26일 (목)", "다시 조회")
o, e = B.check_plan({"action": "DONE"}, B.candidates(scr), scr, DS)
t("DONE + 목표 값이 다 보이면 통과(「어른:2」 같은 내부 표기는 안 봄)", o and e is None, e)
scr = _ns("서울 → 부산", "11월 18일 (수)")
t("값 비교는 숫자를 지우지 않음(11월 18일 ≠ 11월 25일)", B.done_missing(scr, {"DATE": "11월 25일 (수)"}) == ["DATE=11월 25일 (수)"])

# ⑥ 개인정보 가림
pv = [dict(text="010-1234-5678 홍길동님", desc="", click=True, pkg="com.sampleapp", b=[0, 0, 500, 100], edit=False),
      dict(text="서울 강남구 테헤란로 123", desc="", click=False, pkg="com.sampleapp", b=[0, 300, 500, 400], edit=False)]
p = B.build_prompt("com.sampleapp", pv, B.candidates(pv), "치킨", {})
t("프롬프트에 전화번호 · 주소가 안 들어감", "010-1234-5678" not in p and "테헤란로 123" not in p, p[-200:])

# ⑦ 화면 지문 · 후보 자르기 · 짧은 답 (11/25 밤)
def _scr(banner, items):
    ns = [dict(text="검색", desc="", click=True, pkg="com.sampleapp", b=[0, 0, 300, 100], edit=False),
          dict(text=banner, desc="", click=True, pkg="com.sampleapp", b=[0, 120, 1080, 400], edit=False)]
    ns += [dict(text=x, desc="", click=True, pkg="com.sampleapp", b=[0, 420 + 200 * i, 1080, 600 + 200 * i], edit=False) for i, x in enumerate(items)]
    return ns
L1 = ["맥도날드 ○○점 배달팁 0원", "버거킹 ○○점", "롯데리아 ○○점", "맘스터치 ○○점"]
L2 = ["버거킹 ○○점", "롯데리아 ○○점", "맘스터치 ○○점", "KFC ○○점"]
t("도는 배너 글자만 바뀌면 같은 화면(AI 다시 안 부름)",
  B.fingerprint(_scr("오늘만 치킨 3천원 할인 쿠폰 받으세요 지금", L1)) == B.fingerprint(_scr("겨울 신메뉴 출시 기념 배달팁 무료 이벤트", L1)))
t("목록을 밀어 항목이 바뀌면 다른 화면(밀기 결과를 알아챔)", B.fingerprint(_scr("배너", L1)) != B.fingerprint(_scr("배너", L2)))
t("「출발역 서울 선택됨」처럼 고른 값이 바뀌면 다른 화면", B.fingerprint(N("korail/k00_main")) != B.fingerprint(N("korail/k03_after_dep")))
many = [dict(text=f"{i}일", desc="", click=True, pkg="com.korail.talk", b=[(i % 7) * 150, 200 + (i // 7) * 100, (i % 7) * 150 + 140, 290 + (i // 7) * 100], edit=False) for i in range(1, 78)]
many.append(dict(text="선택 완료", desc="", click=True, pkg="com.korail.talk", b=[0, 2200, 1080, 2300], edit=False))
cm = B.candidates(many)
t("칸이 60개 넘어도 맨 아래 「선택 완료」는 안 잘림(A6)", len(cm) <= B.MAXC and any(c["text"] == "선택 완료" for c in cm), len(cm))
sch = B.schema(False)
t("짧은 답 모드(GUIDE_BRAIN_VERBOSE=0): 이유 · 예측 · 소리 말 없음, progress는 맨 앞", set(sch["required"]) == set(B.SHORT_FIELDS) and "why" not in sch["properties"] and sch["required"][0] == "progress")
t("기록용(VERBOSE)이면 이유 · 예측까지", "expect_next" in B.schema(True)["required"])

# ⑧ 폰 읽기: 새 시험 앱 DUMP3(resource-id · 클래스) · CLICK 로그, 옛 DUMP2도 그대로 (폰 없이 adb를 가짜로)
import phone as P
_LOG = ("11-25 I GUIDE: CLICK|1764000000000|com.korail.talk|10,20,300,120|출발역선택\n"
        "11-25 I GUIDE: DUMP3|com.korail.talk|true|false|10,20,300,120|com.korail.talk:id/dep|Button|출발역선택\n"
        "11-25 I GUIDE: DUMP2|com.korail.talk|true|false|0,200,500,300|열차 조회\n"
        "11-25 I GUIDE: DUMP2|end\n")
_adb0 = P.adb
P.adb = lambda *a: _LOG if a[:1] == ("logcat",) and "-d" in a else ""
P.CLICKS.clear(); P._SEEN_CLICK.clear()
_, nsx = P.dump_fast(timeout=0.5)
P.adb = _adb0
t("DUMP3 줄: resource-id · 클래스를 읽음", nsx and nsx[0]["rid"] == "com.korail.talk:id/dep" and nsx[0]["cls"] == "Button" and nsx[0]["text"] == "출발역선택", nsx[:1])
t("옛 DUMP2 줄도 읽음", len(nsx) == 2 and nsx[1]["text"] == "열차 조회" and nsx[1]["rid"] == "")
t("CLICK 줄: 누른 칸 글자 · 위치를 한 번만 모음(두 번 읽어도)", len(P.CLICKS) == 1 and P.CLICKS[0]["label"] == "출발역선택" and P.CLICKS[0]["b"] == [10, 20, 300, 120], P.CLICKS)
t("누른 칸 ↔ 안내 칸 맞추기(위치)", B.click_matches(dict(b=[0, 0, 400, 200], pick_text="x"), P.CLICKS) is True)
t("누른 칸 ↔ 안내 칸 다름", B.click_matches(dict(b=[0, 500, 400, 700], pick_text="열차 조회"), P.CLICKS) is False)

# ⑨ 실제 폰에서 터진 것(11/25 밤): 날짜만 바뀐 첫 화면을 같은 화면으로 봐서 「가는날」을 또 안내
def _home(date, clock="15:58"):
    return [dict(text=clock, desc="", click=False, pkg="com.korail.talk", b=[0, 0, 200, 50], edit=False),
            dict(text="출발역 서울 선택됨", desc="", click=True, pkg="com.korail.talk", b=[0, 100, 500, 200], edit=False),
            dict(text=f"가는날, 2026년 {date}", desc="", click=True, pkg="com.korail.talk", b=[0, 300, 1080, 400], edit=False),
            dict(text="남은 시간 4:59", desc="", click=True, pkg="com.korail.talk", b=[600, 100, 1000, 200], edit=False)]
t("가는날 날짜가 바뀌면 다른 화면(옛 안내 다시 안 씀)", B.fingerprint(_home("11월 25일 (수)")) != B.fingerprint(_home("11월 27일 (금)")))
t("시계 · 남은 시간만 바뀌면 같은 화면", B.fingerprint(_home("11월 27일 (금)", "15:58")) == B.fingerprint([dict(n, text=n["text"].replace("4:59", "4:31")) for n in _home("11월 27일 (금)", "16:02")]))

def _sheet(title):
    ns = [dict(text=title, desc="", click=False, pkg="com.korail.talk", b=[0, 80, 600, 150], edit=False),
          dict(text="닫기", desc="", click=True, pkg="com.korail.talk", b=[900, 80, 1060, 150], edit=False)]
    ns += [dict(text=x, desc="", click=True, pkg="com.korail.talk", b=[(i % 4) * 260, 300 + (i // 4) * 120, (i % 4) * 260 + 240, 400 + (i // 4) * 120], edit=False)
           for i, x in enumerate(["서울", "용산", "영등포", "광명", "수원", "대전", "동대구", "부산"])]
    return ns
t("출발역 시트와 도착역 시트(제목만 다름)는 다른 화면", B.fingerprint(_sheet("출발역 선택")) != B.fingerprint(_sheet("도착역 선택")))

print(f"\n{ok}/{ok + bad} 통과")
sys.exit(1 if bad else 0)
