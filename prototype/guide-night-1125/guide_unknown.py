"""
처음 보는 앱 흉내: 앱 지식 없이 0 규칙 → 스크린숏(개인정보 칸 가림) + Haiku v2 → 검사 층 → 표시 → 통과하면 안전 도구로 누름(어르신 역할)
python guide_unknown.py yogiyo "햄버거 시켜 먹고 싶어" 10
"""
import base64, io, json, os, re, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
import ai, phone, eval_v2, validate2
import mask
import guide_sim as G
from guide_live import show

app, goal, maxn = sys.argv[1], sys.argv[2], int(sys.argv[3])
LIVE = os.path.join(eval_v2.BASE, "live")
ai.SYS = eval_v2.SYS2
hist = []
for i in range(maxn):
    x, ns = phone.dump()
    st, hint = G.screen_type(ns)
    if st in G.RULE_REPLY:
        a, say = G.RULE_REPLY[st]; print(i, "규칙", st, a); show(None, say); break
    if st in ("ONBOARDING", "ALERT", "POPUP"):
        b = G.find(ns, hint, contains=(hint != "닫기"))
        if b:
            print(i, "규칙", st, hint); phone.tap_node(app, b, ns, f"unknown 규칙 {hint}"); time.sleep(2); continue
    raw = phone.adb("exec-out", "screencap", "-p", binary=True)
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    masked = mask.mask_image(im, ns)  # 맨 위 줄 기본 가림(02:48 시트 뒤 주소) + 주소 · 전화 · 동호 · 이름 패턴 (11/25 검수: mask.py로 모음)
    im.save(os.path.join(LIVE, f"{app}_u{i:02d}_masked.png"))
    w, h = im.size; im2 = im.resize((540, int(h * 540 / w))); buf = io.BytesIO(); im2.save(buf, "JPEG", quality=80)
    prev = (" 지금까지 한 일: " + " → ".join(hist[-4:])) if hist else ""
    out = ai.call(ai.HAIKU, [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
                             {"type": "text", "text": f"목표: {goal}.{prev}\n화면은 원래 {w}x{h}인데 540 폭으로 줄였어. bounds는 원래 크기 좌표로."}], f"unknown:{app}:{i}")
    try:
        o = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
    except Exception:
        print(i, "JSON 실패 → 다시"); continue
    validate2.nodes_of = lambda name: ns  # 02:47 수정: validate2가 직접 import한 이름을 바꿔야 함
    fin, why = validate2.validate2("live", o)
    print(i, f"가림 {masked}칸 | AI {o.get('action')} '{(o.get('target') or '')[:20]}' → 검사 {fin} | {why[:50]}")
    with open(os.path.join(eval_v2.BASE, "unknown_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(app=app, i=i, out=o, final=fin, why=why, masked=masked), ensure_ascii=False) + "\n")
    if fin == "SCROLL" and o.get("scroll"):
        nscroll = sum(1 for h in hist[-6:] if h.startswith("밀기"))
        if nscroll >= 3:  # 02:50: 밀기 무한 반복 방지
            show(None, "찾는 게 잘 안 보여요. 화면에 보이는 것 중 골라 주시거나 '검색'을 눌러 주세요."); print("밀기 3번 → 멈추고 어르신께 물음"); break
        a = o["scroll"].get("area") or [0, 700, 1080, 1900]; dr = o["scroll"].get("dir", "next")
        dr = {"down": "next", "up": "next"}.get(dr, dr)  # 옛 표기는 '더 보기'로 (방향 뜻이 모델마다 달라서)
        cx, cy = (a[0] + a[2]) // 2, (a[1] + a[3]) // 2
        if dr in ("next", "prev"):  # next = 손가락을 위로 → 아래 내용이 올라옴
            y1, y2 = (a[3] - 100, a[1] + 100) if dr == "next" else (a[1] + 100, a[3] - 100)
            if not phone.safe_input(app, "SWIPE", cx, y1, cx, y2, 600, target="unknown AI"): break
        else:  # right = 오른쪽 내용 보기 → 손가락을 왼쪽으로
            x1, x2 = (a[2] - 100, a[0] + 100) if dr == "right" else (a[0] + 100, a[2] - 100)
            if not phone.safe_input(app, "SWIPE", x1, cy, x2, cy, 500, target="unknown AI"): break
        hist.append(f"밀기({dr})"); time.sleep(2); continue
    if fin not in ("TAP", "TAP_SCREEN_ONLY"):
        show(None, o.get("say", "")); print("멈춤:", fin); break
    show(validate2.shown_bounds(o), o.get("say", "")); time.sleep(1)
    open(os.path.join(LIVE, f"{app}_u{i:02d}_shown.png"), "wb").write(phone.adb("exec-out", "screencap", "-p", binary=True))
    phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide"); time.sleep(0.4)
    b = o["bounds"]; cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
    hits = [n for n in ns if n["click"] and n["b"][0] <= cx <= n["b"][2] and n["b"][1] <= cy <= n["b"][3]]
    if fin == "TAP" and validate2.LAST.get("btn"):
        btn = validate2.LAST["btn"]  # 검사한 그 칸을 누름
        big = (btn["b"][2] - btn["b"][0]) >= 300 and (btn["b"][3] - btn["b"][1]) >= 150
        if not phone.tap_node(app, btn, ns, f"unknown AI {o.get('target','')[:20]}", card=big):
            print("안전 도구 거부 — 멈춤"); break
    else:
        print("숨은 팝업 닫기 등 화면 기준 — 이번 시험에선 누르지 않고 멈춤"); break
    hist.append(f"'{(o.get('target') or '')[:12]}' 누름"); time.sleep(2)
phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide")
