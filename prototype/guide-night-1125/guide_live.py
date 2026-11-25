"""
실제 폰 한 바퀴: guide_sim 판단 → 길잡이 앱 SHOW(동그라미 + 말) → 스크린숏 → 안전 도구로 누름(어르신 역할)
python -I guide_live.py korail 8      (최대 8단계)
기록: live/<앱>_NN.png · live_log.jsonl
"""
import json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
if not sys.stdin.isatty():  # 파이프로 넣을 때 한글이 깨지지 않게(터미널에서 직접 칠 땐 그대로)
    sys.stdin.reconfigure(encoding="utf-8")
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


PAUSE = float(os.environ.get("GUIDE_PAUSE", "0"))  # 시연용: 화면마다 멈춤(초)
HUMAN = os.environ.get("GUIDE_HUMAN") == "1"  # 사람이 직접 누름: 도구는 안내만 띄우고 화면이 바뀔 때까지 기다림 (11/25 우석 · 우진 시험)


def _sig(ns):
    import re as _r
    grid = {tuple(round(v / 40) for v in n["b"]) for n in ns if n["click"]}
    labs = {phone.label(n) for n in ns if phone.label(n) and not _r.match(r"^\d{1,2}:\d{2}$", phone.label(n))}
    return grid, labs


def wait_change(ns, limit=120):
    """사람이 누를 때까지: 누를 칸 배치가 10% 넘게 바뀌거나 화면 글자가 바뀌면 다음으로"""
    g0, l0 = _sig(ns)
    t0 = time.time()
    while time.time() - t0 < limit:
        time.sleep(0.8)
        _, ns2 = phone.dump()
        if not ns2:
            continue
        g1, l1 = _sig(ns2)
        jac = len(g0 & g1) / max(1, len(g0 | g1))
        if jac < 0.9 or l0 != l1:
            time.sleep(1.0)  # 화면 전환이 끝날 때까지
            return True
    print("  ↳ 2분 동안 화면이 그대로 — 멈춤"); return False


def show(b, say, sub="", speak=None):
    """카드 글씨는 짧게(큰 글씨 한 줄 + 작은 글씨 한 줄). 자세한 말은 speak = 소리로 읽을 말(앱 TTS 몫) (11/25: 카드가 화면을 덮음)"""
    if speak:
        print("  🔊 소리로:", speak)
    if b is None:
        phone.adb("shell", f"am broadcast -a com.edu.guide.SHOW -p com.edu.guide --ei l -1 --es say {q(say)} --es sub {q(sub)}")
    else:
        l, t, r, bb = b
        phone.adb("shell", f"am broadcast -a com.edu.guide.SHOW -p com.edu.guide --ei l {l} --ei t {t} --ei r {r} --ei b {bb} --es say {q(say)} --es sub {q(sub)}")
    if PAUSE:
        time.sleep(PAUSE)


def _short(lab):
    """카드에 쓸 버튼 이름: 「도착역 대전 선택됨」 → 「도착역」 (11/25: 강릉 가는데 카드에 「대전」이 보임)"""
    import re as _r
    lab = lab.split(",")[0]
    lab = _r.sub(r"^(출발역|도착역) .+ 선택됨$", lambda m: m.group(1), lab)
    lab = _r.sub(r"\s*\([^)]*\)?$", "", lab)  # 「11월 27일 (금)」 → 「11월 27일」 (11/25: 「'11월 27일 (금' 누르세요」)
    return lab[:10]


def decide(ns, slots, step):
    pkg = next((n["pkg"] for n in ns if n["pkg"]), "?")
    st, hint = G.screen_type(ns)
    if st in G.RULE_REPLY:
        a, say = G.RULE_REPLY[st]
        first, _, rest = say.partition(". ")  # 카드는 첫 문장만 크게, 나머지는 작게
        return dict(layer="규칙", action=a, say=first.rstrip(".")[:18], sub=rest[:24], b=None, label=st)
    if st in ("ONBOARDING", "ALERT", "POPUP"):
        btn = G.find(ns, hint, contains=True)
        return dict(layer="규칙", action="TAP", say=f"'{hint}'를 눌러 주세요", b=btn["b"] if btn else None, label=hint, btn=btn)
    # 코레일 열차를 고른 뒤 (11/25 우석 · 우진: 「몇 시 기차로 할까요?」 다음 안내가 없음)
    #  · 열차 창(좌석 선택 · 바로 예매) → 「좌석 선택」까지만 안내. 「바로 예매」 · 「예매」는 로그인 · 결제로 이어져 안내 안 함
    #  · 좌석 화면 → 자리는 어르신이 고름 → 다 고르면 「예매」 앞에서 끊음
    if pkg == "com.korail.talk":
        import re as _rk
        labels = [phone.label(n) for n in ns if phone.label(n)]
        if "좌석 선택" in labels and "바로 예매" in labels:
            btn = G.find(ns, "좌석 선택")
            if btn:
                return dict(layer="규칙", action="TAP", say="'좌석 선택' 누르세요", sub="자리를 직접 고를 수 있어요", b=btn["b"], label="좌석 선택(열차 창)", role="SEAT(열기)", btn=btn)
        mseat = next((m for L in labels for m in [_rk.match(r"^(\d+)석 중 (\d+)석 선택됨$", L)] if m), None)
        if mseat:
            need, got = int(mseat.group(1)), int(mseat.group(2))
            if got < need:
                return dict(layer="규칙", action="PICK_BY_USER", say="앉을 자리를 골라 주세요", sub=f"{need - got}자리 · 창측이 창가예요", b=None, label=f"좌석 고르기 {got}/{need}")
            return dict(layer="규칙", action="STOP", say="여기부터는 직접 해 주세요", sub="'예매'부터 로그인 · 결제예요", b=None, label="예매 앞 멈춤")
    k = G.knowledge(pkg, ns, slots, step, DONE, REDO)
    home = G.KNOW.get(pkg, {}).get("home")
    labels = [phone.label(n) for n in ns if phone.label(n)]
    if not k and "출발 빠른 순" in labels:  # 열차 목록(조회 결과) = 처음 화면으로 돌아갈 곳이 아님 (11/25: 뒤로 · 조회를 반복함)
        hdr = next((L for L in labels if L.endswith(" 도착") and " 출발 " in L), "")
        want = f"{slots.get('DEPARTURE', '')} 출발 {slots.get('ARRIVAL', '')} 도착"
        if slots.get("ARRIVAL") and hdr.strip() != want:  # 지난번 목록 그대로 열림(11/25: 서울→대전 목록에서 부산을 찾음)
            return dict(layer="규칙", action="BACK", say="'뒤로' 누르세요", sub="조건을 바꿀게요", b=None, label="다른 조건 목록")
        return dict(layer="AI 필요", action="AI", say="(열차 목록 → 읽어 주고 어르신께 묻기)", b=None, label="열차 목록")
    if not k and home and home not in labels and not DONE and HOMEBACK[0] < 3:
        HOMEBACK[0] += 1
        return dict(layer="규칙", action="BACK", say="'뒤로' 누르세요", sub="처음 화면부터 할게요", b=None, label="시작 화면으로")
    if not k and REDO:
        return dict(layer="복구", action="BACK", say="다른 걸 누르셨어요", sub="'뒤로'를 눌러 주세요", b=None, label="뒤로 가기")
    if k:
        act, lab, b, role = k
        if act == "ASK":  # 앱 지식 중간에 칸이 비면 개발자 문구 대신 어르신 말로 (11/25: 「DEPARTURE 칸을 몰라요」가 화면에 뜸)
            if role in ("STORE", "BRAND"):
                return dict(layer="앱 지식", action="PICK_BY_USER", say="가게를 골라 주세요", sub="마음에 드는 곳을 누르세요", b=None, label="가게 고르기", role=role)
            FRIENDLY = {"DEPARTURE": ("어디서 출발하세요?", ""), "ARRIVAL": ("어디로 가세요?", ""), "DATE": ("언제 가세요?", "오늘 · 내일 · 모레"),
                        "ITEM": ("어떤 메뉴로 할까요?", ""), "CATEGORY": ("뭘 드시고 싶으세요?", "")}
            a2, b2 = FRIENDLY.get(role, ("조금 더 알려 주세요", ""))
            return dict(layer="앱 지식", action="ASK", say=a2, sub=b2, b=None, label=f"{role} 되묻기", role=role)
        btn = None
        if act == "TAP":
            cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
            btn = min([n for n in ns if n["click"] and n["b"][0] <= cx <= n["b"][2] and n["b"][1] <= cy <= n["b"][3]],
                      key=lambda n: (n["b"][2] - n["b"][0]) * (n["b"][3] - n["b"][1]))
        return dict(layer="앱 지식", action=act, say=(f"'{_short(lab)}' 누르세요") if act == "TAP" else lab[:16], b=b, label=lab, role=role, btn=btn)
    return dict(layer="AI 필요", action="AI", say="(여기서 스크린숏 + Haiku로 넘김)", b=None, label="")


READ_SYS = ("너는 기차 시간표 화면을 읽는 도우미야. 화면에 보이는 열차만 위에서부터 JSON 하나로 답해. 추측하지 마. "
            "{\"trains\":[{\"dep\":\"05:03\",\"arr\":\"06:02\",\"from\":\"서울\",\"to\":\"대전\",\"kind\":\"KTX-산천\",\"no\":\"201\","
            "\"mins\":59,\"price\":21600,\"soldout\":false}]} · price는 일반실 원 단위 숫자, 모르면 null")


def hm(t):
    h, m = map(int, t.split(":"))
    return f"{'오전' if h < 12 else '오후'} {h if h <= 12 else h - 12}시" + (f" {m}분" if m else "")


def train_choice(app, ns, slots):
    """열차 목록: AI가 대신 고르지 않음. 출발 · 도착이 맞는 열차 3개를 읽어 주고 어르신께 몇 시로 할지 물음 (11/25 시나리오 3)"""
    import ai, base64, io, re as _re
    from PIL import Image
    import mask
    why = G.capture_block_reason(ns, phone.focus())
    if why:
        show(None, "직접 확인해 주세요", "이 화면은 보지 않을게요"); print("캡처 안 함:", why); return
    phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide"); time.sleep(0.6)  # 우리 카드가 사진을 가리지 않게 (11/25: 두 번째 열차를 가림)
    raw = phone.adb("exec-out", "screencap", "-p", binary=True)
    im = Image.open(io.BytesIO(raw)).convert("RGB"); mask.mask_image(im, ns)
    w, h = im.size; im2 = im.resize((540, int(h * 540 / w))); buf = io.BytesIO(); im2.save(buf, "JPEG", quality=80)
    old, ai.SYS = ai.SYS, READ_SYS
    try:
        out = ai.call(ai.HAIKU, [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
                                 {"type": "text", "text": "이 화면의 열차를 읽어 줘."}], f"read:{app}")
    finally:
        ai.SYS = old
    after = phone.focus()
    if after not in phone.ALLOWED_PKG:  # 사진 찍는 사이 알림창 · 다른 앱이 덮음(11/25: 알림 내용이 AI로 감) → 결과 버림
        show(None, "직접 확인해 주세요", "화면이 바뀌었어요"); print("캡처 뒤 화면 바뀜:", after); return
    try:
        trains = json.loads(_re.search(r"\{.*\}", out, _re.S).group(0)).get("trains", [])
    except Exception:  # AI가 열차 화면이 아니라고 답함(알림창 등)
        show(None, "직접 확인해 주세요", "화면을 못 읽었어요"); print("읽기 실패:", out[:80]); return
    dep, arr = slots.get("DEPARTURE"), slots.get("ARRIVAL")
    trains = [t for t in trains if _re.match(r"^\d{1,2}:\d{2}$", str(t.get("dep") or ""))]  # 시각을 못 읽은 줄은 빼기(화면 끝에 반쯤 걸린 카드)
    seen, uniq = set(), []
    for t in trains:  # 같은 열차를 두 번 읽는 경우(11/25 실제)
        k = (t.get("no"), t.get("dep"), t.get("kind"))  # 같은 시각 다른 열차가 있음(05:03 KTX-산천 201 · 251) → 열차 번호로
        if k not in seen:
            seen.add(k); uniq.append(t)
    trains = uniq
    ok = [t for t in trains if t.get("from") == dep and t.get("to") == arr and not t.get("soldout")]
    other = [t for t in trains if t not in ok]
    if not ok:
        show(None, "열차가 안 보여요", "아래로 밀어 볼게요"); print("맞는 열차 없음", trains); return
    parts = [f"{i + 1}번, {hm(t['dep'])} 출발 {t.get('kind', '')}" + (f" {t['mins']}분 걸리고" if t.get("mins") else "") + (f" {t['price']:,}원" if t.get("price") else "")
             for i, t in enumerate(ok[:3])]
    speak = f"{slots.get('DATE_SHORT', '')} {dep}에서 {arr} 가는 기차예요. " + ", ".join(parts) + ". 몇 시 기차로 하실래요?"
    times = " · ".join(t["dep"] for t in ok[:3])  # 같은 시각이 두 번 나오면 그대로 둠(번호는 소리로)
    show(None, "몇 시 기차로 할까요?", f"{times} ({dep}→{arr})", speak=speak)
    print("읽어 주기(카드):", "몇 시 기차로 할까요? /", f"{times} ({dep}→{arr})")
    if other:
        print("  ↳ 뺀 열차(출발 · 도착이 다름 · 매진):", [(t.get('dep'), t.get('from'), t.get('to')) for t in other])
    time.sleep(1.5)
    open(os.path.join(LIVE, f"{app}_trainchoice.png"), "wb").write(phone.adb("exec-out", "screencap", "-p", binary=True))


AI_CACHE, AI_MAX = {}, 8  # 같은 화면은 다시 묻지 않음, 한 번 안내에 AI 최대 8번
GOAL = [""]


def _gridsig(ns):
    return tuple(sorted({tuple(round(v / 40) for v in n["b"]) for n in ns if n["click"]}))


def ai_next(app, ns):
    """B4 모르는 화면 → AI에게 다음 한 수 (11/25 우석: 금지 규칙에 안 걸리면 멈추지 말고 AI로)
    사진 찍기 전 멈출 화면이면 안 보냄 · 우리 카드 내리고 찍음 · 가림 · 검사 층 통과한 답만"""
    import ai, base64, io, re as _re, eval_v2, validate2, mask
    from PIL import Image
    why = G.capture_block_reason(ns, phone.focus())
    if why:
        return dict(layer="AI", action="STOP", say="직접 해 주세요", sub="이 화면은 보지 않을게요", b=None, label=f"캡처 안 함: {why}")
    if sum(1 for v in AI_CACHE.values() if v.get("layer") == "AI") >= AI_MAX:
        return dict(layer="AI", action="STOP", say="직접 해 주세요", sub="제가 더 도와드리기 어려워요", b=None, label="AI 횟수 다 씀")
    phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide"); time.sleep(0.5)
    raw = phone.adb("exec-out", "screencap", "-p", binary=True)
    if phone.focus() not in phone.ALLOWED_PKG:
        return dict(layer="AI", action="STOP", say="직접 해 주세요", sub="화면이 바뀌었어요", b=None, label="캡처 뒤 화면 바뀜")
    im = Image.open(io.BytesIO(raw)).convert("RGB"); mask.mask_image(im, ns)
    w, h = im.size; im2 = im.resize((540, int(h * 540 / w))); buf = io.BytesIO(); im2.save(buf, "JPEG", quality=80)
    old, ai.SYS = ai.SYS, eval_v2.SYS2
    try:
        out = ai.call(ai.HAIKU, [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
                                 {"type": "text", "text": f"목표: {GOAL[0]}\n화면은 원래 {w}x{h}인데 540 폭으로 줄였어. bounds는 원래 크기 좌표로."}], f"b4:{app}")
    finally:
        ai.SYS = old
    try:
        o = json.loads(_re.search(r"\{.*\}", out, _re.S).group(0))
    except Exception:
        return dict(layer="AI", action="STOP", say="직접 해 주세요", sub="화면을 못 읽었어요", b=None, label="AI 답 형식 틀림")
    act = (o.get("action") or "").upper()
    say_long = o.get("say") or ""
    if act == "TAP":
        validate2.nodes_of = lambda name: ns
        fin, why = validate2.validate2("live", o)
        b = validate2.shown_bounds(o)
        if fin == "TAP" and b:
            return dict(layer="AI", action="TAP", say=f"'{_short(o.get('target') or '')}' 누르세요", sub="", b=b, label=f"AI: {o.get('target')}", speak=say_long)
        return dict(layer="AI", action="STOP", say="직접 해 주세요", sub="제가 확실하지 않아요", b=None, label=f"검사 층 {fin}: {why}")
    if act == "SCROLL":
        a = (o.get("scroll") or {}).get("area") or [0, 700, 1080, 1900]
        return dict(layer="AI", action="SCROLL", say="화면을 밀어 주세요", sub="찾는 게 아래에 있어요", b=a, label="AI: 밀기", speak=say_long)
    if act == "BACK":
        return dict(layer="AI", action="BACK", say="'뒤로' 누르세요", sub="", b=None, label="AI: 뒤로", speak=say_long)
    if act == "WAIT":
        return dict(layer="AI", action="WAIT", say="잠깐 기다려 주세요", sub="", b=None, label="AI: 기다림", speak=say_long)
    if act == "PICK_BY_USER":
        return dict(layer="AI", action="PICK_BY_USER", say="직접 골라 주세요", sub=say_long[:24], b=None, label="AI: 어르신이 고름", speak=say_long)
    return dict(layer="AI", action="STOP", say="여기서는 직접 해 주세요", sub=say_long[:24], b=None, label=f"AI: {act}", speak=say_long)


def _show_for(d, level=0):
    nudge = ["", "여기를 눌러 주세요", "어려우시면 '안 돼요'를 눌러요"][level]
    if d["action"] == "BACK":
        show(None, "'뒤로' 누르세요", nudge or d.get("sub", ""))
    elif d["action"] == "SCROLL":
        show(d.get("b"), "화면을 밀어 주세요", nudge or "찾는 게 아래에 있어요")
    else:
        show(d.get("b"), d["say"], nudge or d.get("sub", ""), speak=d.get("speak") if level == 0 else None)


def human_loop(app, slots, maxsec=600):
    """사람이 직접 누름: 0.5초 화면 읽기(길잡이 앱 접근성)로 계속 다시 판단 (11/25 우석 · 우진 직접 시험 피드백)
    - 판단이 바뀌면 새 카드, 그대로면 4초마다 다시 띄움(앱이 누를 때 카드를 「잘하셨어요」로 바꿔도 돌아옴)
    - 20초 그대로면 「여기를 눌러 주세요」, 45초면 「어려우시면 '안 돼요'」"""
    cur, shown_at, since, level, prev = None, 0, 0, 0, None
    t_end = time.time() + maxsec
    while time.time() < t_end:
        _, ns = phone.dump_fast()
        if not ns:
            time.sleep(0.4); continue
        hb = HOMEBACK[0]
        d = decide(ns, slots, 0)
        if d["action"] == "AI" and _gridsig(ns) in AI_CACHE:  # 이 화면은 이미 AI(또는 열차 읽기)로 판단함
            d = AI_CACHE[_gridsig(ns)]
        key = (d["action"], d.get("label"), tuple(d.get("b") or []))
        now = time.time()
        if key == cur:
            HOMEBACK[0] = hb  # 같은 판단을 다시 셀 때는 「뒤로」 횟수를 늘리지 않음
            if now - since > 45 and level < 2:
                level = 2; _show_for(d, level); shown_at = now; print("  ⏰ 45초 그대로 → 「안 돼요」 안내")
            elif now - since > 20 and level < 1:
                level = 1; _show_for(d, level); shown_at = now; print("  ⏰ 20초 그대로 → 「여기를 눌러 주세요」")
            elif now - shown_at > 4:
                _show_for(d, level); shown_at = now
            time.sleep(0.4); continue
        # 새 안내는 0.5초 뒤 한 번 더 읽어 같을 때만 (11/25: 화면이 넘어가는 2초 동안 「'뒤로' 누르세요」가 잠깐 뜸)
        time.sleep(0.5); _, ns_chk = phone.dump_fast()
        if ns_chk:
            hb2 = HOMEBACK[0]
            d_chk = decide(ns_chk, slots, 0)
            HOMEBACK[0] = hb2
            if d_chk["action"] == "AI" and _gridsig(ns_chk) in AI_CACHE:
                d_chk = AI_CACHE[_gridsig(ns_chk)]
            if (d_chk["action"], d_chk.get("label"), tuple(d_chk.get("b") or [])) != key:
                continue
        if cur and cur[0] == "TAP" and prev and "(" not in prev:
            DONE.add(prev)  # 앞 안내가 바뀌었으면 그 칸은 한 것으로
        cur, prev, since, level = key, d.get("role"), now, 0
        print(time.strftime("%H:%M:%S"), d["layer"], d["action"], "|", d["say"], "|", d.get("sub", ""))
        if d["action"] == "AI" and app == "korail" and any(phone.label(n) == "출발 빠른 순" for n in ns):
            train_choice(app, ns, slots)  # 열차는 어르신이 고름 → 끝내지 않고 다음 화면(열차 선택 창 등)도 계속 지켜봄
            AI_CACHE[_gridsig(ns)] = dict(layer="열차 읽기", action="PICK_BY_USER", say="몇 시 기차로 할까요?", sub="골라서 눌러 주세요", b=None, label="열차 목록 읽음")
            cur = ("PICK_BY_USER", "열차 목록 읽음", ()); shown_at = time.time(); continue
        if d["action"] == "AI":
            # B4 모르는 화면: 넘어가는 중일 수 있으니 3초 보고, 그대로면 AI에게 다음 한 수 (11/25 우석)
            t_hold = time.time(); same = True
            while time.time() - t_hold < 3:
                time.sleep(0.6); _, ns2 = phone.dump_fast()
                if ns2 and decide(ns2, slots, 0)["action"] != "AI":
                    same = False; break
            if not same:
                cur = None; continue
            _, ns = phone.dump_fast()
            d = ai_next(app, ns) if ns else d
            AI_CACHE[_gridsig(ns)] = d
            key = (d["action"], d.get("label"), tuple(d.get("b") or []))
            cur, prev = key, d.get("role")
            print(time.strftime("%H:%M:%S"), "  ↳ AI:", d["action"], "|", d["say"], "|", d.get("label"))
            _show_for(d); shown_at = time.time()
            continue
        if d["action"] in ("PICK_BY_USER", "WAIT"):  # 어르신이 고르거나 기다리는 화면: 멈추지 않고 계속 지켜봄
            _show_for(d); shown_at = now; continue
        if d["action"] not in ("TAP", "BACK", "SCROLL"):
            # 화면이 넘어가는 중일 수 있음 → 같은 판단이 3초 이어질 때만 멈춤 (11/25: 열차 목록이 뜨기 직전에 멈춤)
            t_hold = time.time(); same = True
            while time.time() - t_hold < 3:
                time.sleep(0.6); _, ns2 = phone.dump_fast()
                d2 = decide(ns2, slots, 0) if ns2 else d
                if (d2["action"], d2.get("label")) != (d["action"], d.get("label")):
                    same = False; break
            if not same:
                cur = None; continue
            say = d["say"] if not d["say"].startswith("(") else "직접 해 주세요"
            show(None, say, d.get("sub", "")); print("  ↳ 여기서 멈춤:", d["action"], d.get("label")); return
        _show_for(d); shown_at = now
    print("시간 끝")


def main():
    app, maxn = sys.argv[1], int(sys.argv[2])
    slots, roles = SLOTS[app]
    utt0 = os.environ.get("GUIDE_UTT") or (input("어르신 말> ").strip() if HUMAN else "")
    while utt0:  # 말 한마디부터: /intent(Haiku) → 정규화 → 앱 지식. HUMAN이면 되묻기에 키보드로 답하고 다시 해석
        import ai, intent_test, normalize, re as _re
        utt = utt0
        txt = ai.call(ai.HAIKU, f"어르신 말: \"{utt}\"", "chain-intent")
        try:
            o = json.loads(_re.search(r"\{.*\}", txt, _re.S).group(0))
        except Exception:  # AI 답이 형식에 안 맞음(11/25) → 죽지 않고 다시 말해 달라고
            show(None, "다시 한번 말해 주세요"); print("말 해석 실패:", txt[:80]); return
        task = o.get("taskType")
        if task in (None, "UNSUPPORTED"):  # 지원 안 하는 일(「기차표 취소」) → 안내를 이어 가지 않음 (11/25: 개발자 문구가 화면에 뜸)
            show(None, "이건 아직 못 도와드려요", (o.get("say") or "")[:24]); print("지원 안 함:", utt); return
        raw = dict(o.get("slots") or {})
        missing = list(o.get("missing") or [])
        for k in ("DEPARTURE",):  # 말에 없는 출발역을 AI가 채웠으면 버림 (11/25: 「케이티엑스 부싼」 → 출발 서울을 지어냄). 도착역은 「부싼 → 부산」처럼 고쳐 쓰므로 검사 안 함
            v = str(raw.get(k) or "")
            if v and v.replace("역", "") not in utt and v not in utt:
                print(f"  ↳ 말에 없는 {k}='{v}' 버림"); raw.pop(k); missing.append(k)
        REQUIRED = {"BOOK_TRAIN": ["DEPARTURE", "ARRIVAL", "DATE"], "BOOK_BUS": ["DEPARTURE", "ARRIVAL", "DATE"],
                    "TRAVEL": ["ARRIVAL", "DATE", "MODE"], "ORDER_FOOD": ["ITEM"], "SEND_PHOTO": ["RECIPIENT"]}
        missing = [m for m in dict.fromkeys(missing) if m in REQUIRED.get(task, missing)]  # 꼭 필요한 칸만 되묻기 (11/25: 「몇 시」를 되물어 멈춤)
        pkg = {"korail": "com.korail.talk", "baemin": "com.sampleapp", "eats": "com.coupang.mobile.eats"}[app]
        slots = normalize.to_app(task, raw, pkg)
        print("말 해석:", task, raw, "missing", missing, "→ 앱 칸:", slots)
        if app == "korail":
            _, ns0 = (phone.dump_fast() if HUMAN else phone.dump())
            home = G.KNOW["com.korail.talk"]["home"]
            for _ in range(3):  # 앱이 지난 화면(열차 목록 등)에서 열리면 처음 화면으로 (단계표 · 11/25 실제)
                if any(phone.label(n) == home for n in ns0):
                    break
                if HUMAN:  # 사람이 누르는 모드: 도구는 누르지 않고 안내만 (11/25: 뒤로 가기를 스스로 누름)
                    show(None, "'뒤로' 누르세요", "처음 화면부터 할게요"); print("  ⏳ 처음 화면으로: 사람이 뒤로 누르기를 기다림")
                    t_w = time.time()
                    while time.time() - t_w < 60:
                        time.sleep(0.6); _, ns0 = phone.dump_fast()
                        if any(phone.label(n) == home for n in ns0):
                            break
                    continue
                phone.safe_input(app, "BACK", target="처음 화면으로"); time.sleep(2); _, ns0 = phone.dump()
        if "DEPARTURE" in missing and app == "korail":
            # 열린 질문 대신 확인형: 앱에 이미 들어 있는 출발역으로 「여기서 출발하시죠?」 (11/25 시나리오 3)
            import re as _r2
            cur = next((m.group(1) for n in ns0 for m in [_r2.match(r"^출발역 (.+) 선택됨$", phone.label(n))] if m), None)
            if cur:
                say = f"{cur}에서 출발하세요?"
                show(None, say, "맞으면 '네'라고 말해 주세요", speak=f"출발역이 {cur}로 되어 있어요. {cur}에서 출발하시면 '네'라고 해 주세요.")
                print("확인형 되묻기:", say)
                if HUMAN:
                    ans = input("  대답(네 / 다른 역 이름)> ").strip()
                    if not ans.startswith(("네", "예", "응", "어", "맞")):
                        utt0 = f"{utt0} {ans}에서 출발"; continue
                elif os.environ.get("GUIDE_YES") != "1":
                    return
                print("  ↳ 어르신: 네"); slots["DEPARTURE"] = cur; missing.remove("DEPARTURE"); time.sleep(1.5)
        if app == "korail" and "COUNT" not in slots and "PAX" not in slots:
            # 말에 인원이 없는데 앱에 지난번 인원이 남아 있으면 확인 (11/25: 「모레 대전」인데 2명으로 조회됨)
            import re as _r3
            mc = next((m for n in ns0 for m in [_r3.match(r"^인원, 어른 (\d+)명", phone.label(n))] if m), None)
            if mc and mc.group(1) != "1":
                k = mc.group(1)
                show(None, f"{k}명 맞아요?", "맞으면 '네', 아니면 몇 명인지")
                print(f"확인형 되묻기: {k}명 맞아요?")
                if HUMAN:
                    ans = input("  대답(네 / 몇 명)> ").strip()
                    if ans.startswith(("네", "예", "응", "어", "맞")) and "명" not in ans:  # 「네 명」은 4명
                        slots["COUNT"] = k
                    else:
                        num = _r3.sub(r"\D", "", ans) or {"한": "1", "두": "2", "세": "3", "네": "4"}.get(ans[:1], "1")
                        slots["COUNT"] = num
                else:
                    slots["COUNT"] = "1"
                slots["PAX"] = f"어른:{slots['COUNT']}"
        if missing:  # 한 번에 하나씩, 짧게 (11/25: 출발역 · 날짜를 한 문장에 같이 물음)
            ASKS = {"DEPARTURE": ("어디서 출발하세요?", "예: 서울역"), "ARRIVAL": ("어디로 가세요?", "예: 대전"),
                    "DATE": ("언제 가세요?", "오늘 · 내일 · 모레"), "MODE": ("기차? 버스?", "편한 걸 말해 주세요"),
                    "ITEM": ("뭘 드시고 싶으세요?", "예: 치킨 · 짜장면"), "RECIPIENT": ("누구한테 보낼까요?", "예: 손녀")}
            a, b = ASKS.get(missing[0], (f"{missing[0]}?", ""))
            show(None, a, b); print(f"되묻기(1개만): {a} / 남은 칸 {missing}")
            if HUMAN:
                ans = input(f"  대답({a})> ").strip()
                if ans:
                    utt0 = f"{utt0} {ans}"; continue
            return
        break
    if os.environ.get("GUIDE_SLOTS"):
        slots = dict(slots, **json.loads(os.environ["GUIDE_SLOTS"]))
    if HUMAN:
        GOAL[0] = (os.environ.get("GUIDE_UTT") or utt0 or "") + " / 칸: " + json.dumps({k: v for k, v in slots.items() if k != "DATE_SHORT"}, ensure_ascii=False) + " (결제 · 예매 확정은 어르신이 직접)"
        human_loop(app, slots); return
    step = 0
    last = None
    for i in range(maxn):
        _, ns = phone.dump()
        if not ns:  # 화면을 못 읽음(움직이는 화면 등) → 옛 화면으로 안내하지 않음
            show(None, "잠깐만요", "화면을 다시 볼게요"); print("화면 읽기 실패 → 멈춤"); break
        d = decide(ns, slots, step)
        # 같은 칸을 눌렀는데 화면 구조가 그대로면 → 숨은 팝업 등 의심 → AI(스크린숏)로 (02:27 추가)
        sig = (tuple(sorted(tuple(n["b"]) for n in ns if n["click"])), d.get("label"))
        if last is not None and sig == last:
            d = dict(layer="AI 필요", action="AI", say="(같은 곳을 눌렀는데 그대로 → 스크린숏 판단)", b=None, label="반복")
        last = sig
        if d["action"] != "AI":  # AI로 넘길 화면엔 카드를 띄우지 않음(사진을 가림)
            show(d["b"], d["say"], d.get("sub", "")); time.sleep(1.2)
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
                    show(sb["b"], "'검색' 누르세요", f"마이크로 '{word}' 말하기")
                    time.sleep(1.2); open(os.path.join(LIVE, f"{app}_voicesearch.png"), "wb").write(phone.adb("exec-out", "screencap", "-p", binary=True))
                    print("밀기 4번 넘음 → 음성 검색 안내 표시(VOICE_SEARCH)"); break
                print("밀기 4번 넘음 → AI(스크린숏)로 넘김"); break
        if HUMAN and d["action"] in ("TAP", "BACK", "SCROLL"):
            if d["action"] == "BACK":
                show(None, "'뒤로' 누르세요", d.get("sub", ""))
            elif d["action"] == "SCROLL":
                show(d.get("b"), "화면을 밀어 주세요", "찾는 게 아래에 있어요")
            print(f"  ⏳ 사람이 누르기를 기다림: {d['say']}")
            if not wait_change(ns):
                break
            if d["action"] == "TAP" and d.get("role") and "(" not in d["role"]:
                DONE.add(d["role"])
            continue
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
        if d["action"] == "AI" and app == "korail" and any(phone.label(n) == "출발 빠른 순" for n in ns):
            train_choice(app, ns, slots); break  # 열차는 어르신이 고름
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
