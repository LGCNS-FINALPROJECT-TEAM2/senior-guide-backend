"""
밤 작업용 폰 도구 (11/25). 읽기 + '되돌릴 수 있는 누르기'만.

python -I phone.py shot <앱> <이름>            화면 저장(xml · txt · png) + 글자 요약 출력
python -I phone.py tap  <앱> "<글자>" [--card]  글자로 찾아 안전 검사 후 누름
python -I phone.py xy   <앱> <x> <y> "<이유>"   좌표 누름(그 자리 노드를 같은 안전 검사)
python -I phone.py back <앱> / scroll <앱> up|down / launch <앱> / home

안전 규칙 (우석님과 정함)
- 금지 단어가 버튼 자신 또는 안쪽 글자에 있으면 안 누름
- 버튼 안에 금액(○○원)이 있으면 안 누름 (--card: 목록의 큰 가게·상품 카드만 예외)
- 글자 없는 버튼은 안 누름
- 누르기 직전에 다시 읽어서 화면이 바뀌었으면 안 누름
- 허용 앱 밖(카톡 · 시스템 권한 창 등)이면 안 누름
- PHONE_UNTIL 시각 이후 누르지 않음 (밤 작업 땐 06:30)
- 밀기 · 뒤로 가기도 허용 앱 화면에서만 (safe_input)
"""
import datetime, hashlib, json, os, re, subprocess, sys, time

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
ADB = os.environ.get("ADB", "adb")  # adb 실행 파일 경로
DEV = os.environ.get("PHONE_DEV", "")  # 폰 주소(adb devices에 보이는 이름 또는 IP:포트). 폰 없이 도는 시험은 안 씀
LOG = os.path.join(BASE, "taplog.jsonl")
# 누르기 마감 시각: 밤 작업용이던 06:30 고정을 환경 변수로 (11/25 검수: 고정값이면 오늘부터 모든 누르기가 막힘)
#   PHONE_UNTIL="2026-11-25 18:00" 처럼 주면 그 시각 이후 안 누름. 없으면 시각 제한 없음
END = datetime.datetime.strptime(os.environ["PHONE_UNTIL"], "%Y-%m-%d %H:%M") if os.environ.get("PHONE_UNTIL") else None

APPS = {
    "korail": "com.korail.talk", "baemin": "com.sampleapp", "eats": "com.coupang.mobile.eats",
    "coupang": "com.coupang.mobile", "youtube": "com.google.android.youtube",
    "nmap": "com.nhn.android.nmap", "kakaomap": "net.daum.android.map", "bustago": "com.ebcard.bustago", "yogiyo": "com.fineapp.yogiyo",
}
ALLOWED_PKG = set(APPS.values())

BANNED = ["결제", "구매", "주문", "담기", "장바구니", "예매", "무료체험", "시작하기", "가입", "구독",
          "와우", "쿠폰", "로그인", "인증", "동의", "허용", "전송", "보내기", "송금", "충전", "호출",
          "선물", "좋아요", "댓글", "공유", "신고", "삭제", "탈퇴", "로그아웃", "설정", "집", "즐겨찾기",
          "저장", "알림 받기", "출발지로", "현위치", "내 위치", "리뷰 쓰기", "업데이트", "설치", "다운로드"]
# 카드(목록의 가게·상품)는 설명 글에 '최소주문 · 원'이 흔해서 강한 단어만 막음
#   11/25 검수: 큰 버튼도 이 목록을 써서 「예매」 · 「보내기」 · 「송금」 · 「호출」 · 「충전」만 적힌 큰 버튼이 통과했음 → 행동 동사 추가
BANNED_CARD = ["결제", "구매하기", "바로구매", "담기", "예매", "가입", "무료체험", "시작하기",
               "구독", "동의", "허용", "로그인", "장바구니", "주문하기", "선물하기",
               "전송", "보내기", "송금", "충전", "호출", "인증"]
OK_EXACT = {"동의하지 않음", "미동의", "닫기", "다음에", "오늘 그만 보기", "오늘은 그만 보기", "오늘 하루 보지 않기", "나중에", "다시 보지 않기",
            "취소", "건너뛰기"}
PRICE = re.compile(r"\d[\d,]*\s*원")


def adb(*a, binary=False, timeout=20):
    if not DEV:
        sys.exit("PHONE_DEV 환경 변수가 없어요(폰을 쓰는 도구만 필요)")
    r = subprocess.run([ADB, "-s", DEV, *a], capture_output=True, timeout=timeout)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def focus():
    for line in adb("shell", "dumpsys", "window").splitlines():
        if "mCurrentFocus" in line:
            m = re.search(r"u0 ([\w.]+)/", line)
            return m.group(1) if m else line.strip()
    return "?"


def dump():
    adb("shell", "uiautomator", "dump", "/sdcard/n.xml")
    x = adb("shell", "cat", "/sdcard/n.xml")
    nodes = []
    for s in re.findall(r"<node [^>]*>", x):
        g = lambda k: (re.search(" " + k + r'="([^"]*)"', s) or [None, ""])[1]
        b = list(map(int, re.findall(r"\d+", g("bounds"))))
        if len(b) != 4:
            continue
        nodes.append(dict(text=g("text").replace("&#10;", " ").replace("&amp;", "&"),
                          desc=g("content-desc").replace("&#10;", " "), click=g("clickable") == "true",
                          pkg=g("package"), rid=g("resource-id"), b=b,
                          edit=g("class").endswith("EditText")))
    return x, nodes


def label(n):
    return (n["text"] or n["desc"]).strip()


def inside(o, i):
    return o[0] <= i[0] and o[1] <= i[1] and i[2] <= o[2] and i[3] <= o[3]


def all_text(btn, nodes):
    return " ".join(label(n) for n in nodes if label(n) and inside(btn["b"], n["b"]))


def clickable_for(n, nodes):
    if n["click"]:
        return n
    best = None
    for m in nodes:
        if m["click"] and inside(m["b"], n["b"]):
            if best is None or (m["b"][2] - m["b"][0]) * (m["b"][3] - m["b"][1]) < \
                    (best["b"][2] - best["b"][0]) * (best["b"][3] - best["b"][1]):
                best = m
    return best


def sig(nodes):
    # 숫자는 지움: 타임세일 남은 시간 · 시계처럼 초마다 바뀌는 글자 때문에 같은 화면이 다른 화면으로 보임(배민 01:53 발견)
    return hashlib.md5(json.dumps([(re.sub(r"\d", "#", label(n)), n["b"]) for n in nodes if label(n)], ensure_ascii=False)
                       .encode()).hexdigest()


def check(btn, nodes, card=False):
    if END and datetime.datetime.now() >= END:
        return f"{END:%H:%M} 지남"
    if btn["pkg"] not in ALLOWED_PKG:
        return f"허용 앱 아님({btn['pkg']})"
    if btn["edit"]:
        return "입력칸(글자 입력 안 함)"
    t = all_text(btn, nodes)
    if not t.strip():
        return "글자 없는 버튼"
    if t.strip() in OK_EXACT:
        return None
    for w in (BANNED_CARD if card else BANNED):
        if w in t:
            return f"금지 단어 '{w}'"
    if card:
        w, h = btn["b"][2] - btn["b"][0], btn["b"][3] - btn["b"][1]
        if w < 300 or h < 150:
            return "카드라기엔 작음"
    elif PRICE.search(t):
        return "금액 들어 있음"
    return None


def safe_input(app, kind, *args, target=""):
    """밀기 · 뒤로 가기도 허용 앱 화면에서만 (11/25 검수: guide_live · guide_unknown이 adb로 바로 밀어서 이 검사를 건너뜀)"""
    pkg = focus()
    if pkg not in ALLOWED_PKG:
        log(app=app, action="REFUSE", target=f"{kind} {target}"[:80], why=f"허용 앱 아님({pkg})")
        print(f"안 함({kind}): 허용 앱 아님", pkg)
        return False
    if END and datetime.datetime.now() >= END:
        print(f"안 함({kind}): 마감 시각 지남"); return False
    if kind == "SWIPE":
        adb("shell", "input", "swipe", *map(str, args))
    elif kind == "BACK":
        adb("shell", "input", "keyevent", "KEYCODE_BACK")
    log(app=app, action=kind, target=target[:40])
    return True


def log(**k):
    k["time"] = datetime.datetime.now().strftime("%H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(k, ensure_ascii=False) + "\n")


def tap_node(app, btn, nodes, reason, card=False):
    why = check(btn, nodes, card)
    if why:
        log(app=app, action="REFUSE", target=all_text(btn, nodes)[:80], why=why, reason=reason)
        print("안 누름:", why)
        return False
    # 화면 확인 = 누를 수 있는 칸들의 위치 + 누를 버튼 안 글자가 그대로인가
    # (전체 글자 비교는 타임세일 시계 · 회전 추천 문구 때문에 매번 다름 — 배민 · 쿠팡이츠 02:02 발견)
    # 화면 확인 = 누를 칸 글자(숫자 뺌)가 그대로 + 누름 칸 구조가 90% 이상 겹침 (02:59: 배민 홈은 가만히 둬도 구조가 2가지로 흔들림)
    def grid(ns):
        return {tuple(round(v / 40) for v in n["b"]) for n in ns if n["click"]}
    def same(a, b, btn):
        ga, gb = grid(a), grid(b)
        jac = len(ga & gb) / max(1, len(ga | gb))
        hit = [m for m in b if m["click"] and tuple(round(v / 40) for v in m["b"]) == tuple(round(v / 40) for v in btn["b"])]
        txt_ok = any(re.sub(r"\d", "#", all_text(m, b)) == re.sub(r"\d", "#", all_text(btn, a)) for m in hit)
        return jac >= 0.9 and txt_ok, round(jac, 2)
    _, again = dump()
    ok_same, jac = same(nodes, again, btn)
    if not ok_same:
        log(app=app, action="REFUSE", target=all_text(btn, nodes)[:80], why=f"화면 바뀜(겹침 {jac})", reason=reason)
        print("안 누름: 누르기 직전 화면이 바뀜")
        return False
    x, y = (btn["b"][0] + btn["b"][2]) // 2, (btn["b"][1] + btn["b"][3]) // 2
    adb("shell", "input", "tap", str(x), str(y))
    log(app=app, action="TAP", target=all_text(btn, nodes)[:80], xy=[x, y], reason=reason)
    print(f"누름: '{all_text(btn, nodes)[:60]}' ({x},{y})")
    time.sleep(2.5)
    return True


def shot(app, name):
    d = os.path.join(BASE, app)
    os.makedirs(d, exist_ok=True)
    x, nodes = dump()
    open(os.path.join(d, name + ".xml"), "w", encoding="utf-8").write(x)
    open(os.path.join(d, name + ".png"), "wb").write(adb("exec-out", "screencap", "-p", binary=True))
    f = focus()
    lines = [f"focus {f} | nodes {len(nodes)} | text {sum(1 for n in nodes if label(n))}"]
    for n in nodes:
        if label(n) or n["click"]:
            lines.append(f"{'C' if n['click'] else ' '} {label(n)[:90]!r} {n['b']}" + (" [EDIT]" if n["edit"] else ""))
    open(os.path.join(d, name + ".txt"), "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines[:120]))


def main():
    cmd, app = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
    if cmd == "shot":
        shot(app, sys.argv[3])
    elif cmd == "tap":
        want, card = sys.argv[3], "--card" in sys.argv
        _, nodes = dump()
        cand = [n for n in nodes if label(n) == want] or [n for n in nodes if want in label(n)]
        cand = [n for n in cand if n["b"][2] > n["b"][0] and n["b"][3] > n["b"][1]]
        if not cand:
            print("못 찾음:", want); return
        btn = clickable_for(cand[0], nodes)
        if not btn:
            print("누를 수 있는 칸 없음:", want); return
        tap_node(app, btn, nodes, f"tap '{want}'", card)
    elif cmd == "xy":
        x, y, reason = int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
        _, nodes = dump()
        hits = [n for n in nodes if n["click"] and n["b"][0] <= x <= n["b"][2] and n["b"][1] <= y <= n["b"][3]]
        if not hits:
            print("그 자리에 누를 칸 없음"); return
        btn = min(hits, key=lambda n: (n["b"][2] - n["b"][0]) * (n["b"][3] - n["b"][1]))
        tap_node(app, btn, nodes, reason, "--card" in sys.argv)
    elif cmd == "back":
        if safe_input(app, "BACK"):
            time.sleep(2)
    elif cmd == "scroll":
        a, b = (1700, 700) if sys.argv[3] == "down" else (700, 1700)
        if safe_input(app, "SWIPE", 540, a, 540, b, 400, target="scroll " + sys.argv[3]):
            time.sleep(2)
    elif cmd == "launch":
        adb("shell", "monkey", "-p", APPS[app], "-c", "android.intent.category.LAUNCHER", "1"); log(app=app, action="LAUNCH"); time.sleep(6)
        print("focus", focus())
    elif cmd == "home":
        adb("shell", "input", "keyevent", "KEYCODE_HOME"); log(app="-", action="HOME")


if __name__ == "__main__":
    main()
