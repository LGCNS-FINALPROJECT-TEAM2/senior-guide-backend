"""
실제 폰 한 바퀴: guide_sim 판단 → 길잡이 앱 SHOW(동그라미 + 말) → 스크린숏 → 안전 도구로 누름(어르신 역할)
python -I guide_live.py korail 8      (최대 8단계)
기록: live/<앱>_NN.png · live_log.jsonl
"""
import json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phone
import guide_sim as G
from validate2 import own_text

DONE = set(os.environ.get("GUIDE_DONE", "").split(",")) - {""}  # 세션(Redis)이 기억하는 '고른 칸'
SCROLLS = {}      # 칸별 밀기 횟수
HOMEBACK = [0]    # 시작 화면으로 돌아가려고 뒤로 간 횟수
REDO = set()      # 잘못 누름으로 다시 해야 하는 칸
WRONG = os.environ.get("GUIDE_WRONG", "")  # 시험: 첫 안내에서 어르신이 이 글자를 대신 누름
BASE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(BASE, "live"); os.makedirs(LIVE, exist_ok=True)
SLOTS = {"korail": (G.SLOTS_TRAIN, ["DEPARTURE", "ARRIVAL", "DATE", "SEARCH"]),
         "baemin": (G.SLOTS_FOOD, ["CATEGORY", "STORE", "ITEM"]),
         "eats": (G.SLOTS_FOOD2, ["CATEGORY", "BRAND", "STORE", "ITEM"])}


def q(s):
    return "'" + str(s).replace("'", "’") + "'"


def show(b, say):
    if b is None:
        phone.adb("shell", f"am broadcast -a com.edu.guide.SHOW -p com.edu.guide --ei l -1 --es say {q(say)} --es sub ''")
    else:
        l, t, r, bb = b
        phone.adb("shell", f"am broadcast -a com.edu.guide.SHOW -p com.edu.guide --ei l {l} --ei t {t} --ei r {r} --ei b {bb} --es say {q(say)} --es sub ''")


def decide(ns, slots, step):
    pkg = next((n["pkg"] for n in ns if n["pkg"]), "?")
    st, hint = G.screen_type(ns)
    if st in G.RULE_REPLY:
        a, say = G.RULE_REPLY[st]; return dict(layer="규칙", action=a, say=say, b=None, label=st)
    if st in ("ONBOARDING", "ALERT", "POPUP"):
        btn = G.find(ns, hint, contains=True)
        return dict(layer="규칙", action="TAP", say=f"'{hint}'를 눌러 주세요", b=btn["b"] if btn else None, label=hint, btn=btn)
    k = G.knowledge(pkg, ns, slots, step, DONE, REDO)
    home = G.KNOW.get(pkg, {}).get("home")
    labels = [phone.label(n) for n in ns if phone.label(n)]
    if not k and home and home not in labels and not DONE and HOMEBACK[0] < 3:
        HOMEBACK[0] += 1
        return dict(layer="규칙", action="BACK", say="처음 화면부터 할게요. '뒤로 가기'를 눌러 주세요.", b=None, label="시작 화면으로")
    if not k and REDO:
        return dict(layer="복구", action="BACK", say="앗, 다른 걸 누르셨어요. 아래 '뒤로 가기'를 눌러 주세요.", b=None, label="뒤로 가기")
    if k:
        act, lab, b, role = k
        btn = None
        if act == "TAP":
            cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
            btn = min([n for n in ns if n["click"] and n["b"][0] <= cx <= n["b"][2] and n["b"][1] <= cy <= n["b"][3]],
                      key=lambda n: (n["b"][2] - n["b"][0]) * (n["b"][3] - n["b"][1]))
        return dict(layer="앱 지식", action=act, say=(f"'{lab.split(',')[0][:14]}' 을(를) 눌러 주세요") if act == "TAP" else lab, b=b, label=lab, role=role, btn=btn)
    return dict(layer="AI 필요", action="AI", say="(여기서 스크린숏 + Haiku로 넘김)", b=None, label="")


def main():
    app, maxn = sys.argv[1], int(sys.argv[2])
    slots, roles = SLOTS[app]
    if os.environ.get("GUIDE_UTT"):  # 말 한마디부터: /intent(Haiku) → 정규화 → 앱 지식
        import ai, intent_test, normalize, re as _re
        txt = ai.call(ai.HAIKU, f"어르신 말: \"{os.environ['GUIDE_UTT']}\"", "chain-intent")
        o = json.loads(_re.search(r"\{.*\}", txt, _re.S).group(0))
        pkg = {"korail": "com.korail.talk", "baemin": "com.sampleapp", "eats": "com.coupang.mobile.eats"}[app]
        slots = normalize.to_app(o.get("taskType"), o.get("slots"), pkg)
        print("말 해석:", o.get("taskType"), o.get("slots"), "missing", o.get("missing"), "→ 앱 칸:", slots)
        if o.get("missing"):
            print("되묻기 필요 → 멈춤"); return
    if os.environ.get("GUIDE_SLOTS"):
        slots = dict(slots, **json.loads(os.environ["GUIDE_SLOTS"]))
    step = 0
    last = None
    for i in range(maxn):
        _, ns = phone.dump()
        d = decide(ns, slots, step)
        # 같은 칸을 눌렀는데 화면 구조가 그대로면 → 숨은 팝업 등 의심 → AI(스크린숏)로 (02:27 추가)
        sig = (tuple(sorted(tuple(n["b"]) for n in ns if n["click"])), d.get("label"))
        if last is not None and sig == last:
            d = dict(layer="AI 필요", action="AI", say="(같은 곳을 눌렀는데 그대로 → 스크린숏 판단)", b=None, label="반복")
        last = sig
        show(d["b"], d["say"]); time.sleep(1.2)
        png = os.path.join(LIVE, f"{app}_{i:02d}.png")
        open(png, "wb").write(phone.adb("exec-out", "screencap", "-p", binary=True))
        rec = {k: v for k, v in d.items() if k != "btn"}; rec.update(i=i, step=step, focus=phone.focus())
        print(i, rec)
        with open(os.path.join(BASE, "live_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if d["action"] == "SCROLL":
            SCROLLS[d.get("role")] = SCROLLS.get(d.get("role"), 0) + 1
            if SCROLLS[d["role"]] > 4:
                pkg = phone.focus(); know = G.KNOW.get(pkg, {})
                word = slots.get("BRAND") or slots.get("ITEM") or ""
                sb = next((G.find(ns, w) for w in know.get("search_entry", []) if G.find(ns, w)), None)
                if sb and word:  # 음성 검색 안내 — 대신 입력하지 않음
                    show(sb["b"], f"'검색'을 누르고, 키보드의 마이크를 눌러 '{word}'라고 말씀해 주세요.")
                    time.sleep(1.2); open(os.path.join(LIVE, f"{app}_voicesearch.png"), "wb").write(phone.adb("exec-out", "screencap", "-p", binary=True))
                    print("밀기 4번 넘음 → 음성 검색 안내 표시(VOICE_SEARCH)"); break
                print("밀기 4번 넘음 → AI(스크린숏)로 넘김"); break
        if d["action"] == "SCROLL" and d.get("b"):
            l, t, r, bb = d["b"]
            if "아래" in d["label"] or d["label"].endswith("up로 밀기"):
                x = (l + r) // 2; moved = phone.safe_input(app, "SWIPE", x, bb - 100, x, t + 100, 600, target=d["label"])
            else:
                y = (t + bb) // 2; moved = phone.safe_input(app, "SWIPE", r - 120, y, l + 120, y, 500, target=d["label"])
            if not moved:
                print("밀기 거부 — 멈춤"); break
            time.sleep(2); continue
        if d["action"] == "BACK":
            phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide"); time.sleep(0.3)
            if not phone.safe_input(app, "BACK", target="복구"):
                print("뒤로 가기 거부 — 멈춤"); break
            time.sleep(2); continue
        if d["action"] != "TAP" or not d.get("btn"):
            print("멈춤:", d["action"]); break
        phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide"); time.sleep(0.5)
        big = (d["btn"]["b"][2] - d["btn"]["b"][0]) >= 300 and (d["btn"]["b"][3] - d["btn"]["b"][1]) >= 150
        global WRONG
        if WRONG:
            # 시험: 어르신이 안내와 다른 칸을 누름 → 앱(접근성 클릭 이벤트)이 '누른 칸 글자'를 Guide에 알려 줌
            wbtn = G.find(ns, WRONG)
            ok = wbtn is not None and phone.tap_node(app, wbtn, ns, f"시험: 잘못 누름 '{WRONG}'")
            clicked, WRONG = WRONG, ""
        else:
            ok = phone.tap_node(app, d["btn"], ns, f"guide_live {d['layer']} {d['label'][:20]}", card=big and d.get("role") == "STORE")
            clicked = d["label"]
        if ok and clicked != d["label"]:
            print(f"  ↳ 잘못 누름 감지: 안내 '{d['label'][:15]}' ≠ 누른 '{clicked}' → {d.get('role')} 다시")
            REDO.add(d.get("role")); time.sleep(1.5); continue
        if ok and d.get("role") in REDO:
            REDO.discard(d.get("role")); print("  ↳ 복구 완료")
        if not ok:
            print("안전 도구가 거부 — 멈춤"); break
        if d.get("role") and "(" not in d["role"]:
            DONE.add(d["role"])
        # 단계 번호는 안 올림: 칸이 채워졌는지는 매번 화면 글자(check)로 확인 (02:27 수정)
        time.sleep(1.5)
    phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide")


if __name__ == "__main__":
    main()
