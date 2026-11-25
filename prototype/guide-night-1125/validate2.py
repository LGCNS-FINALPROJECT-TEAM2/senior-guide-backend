"""검사 층 v2: ① 칸 안의 '따로 누를 수 있는 작은 버튼' 글자는 빼고 검사 ② AI가 본 글자와 그 자리 글자가 다르면 MISMATCH(숨은 팝업 의심)"""
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phone
from eval_v2 import nodes_of

LAST = {}  # 마지막으로 검사한 칸 — 누르는 쪽은 반드시 이 칸을 씀 (02:52: 검사한 칸 ≠ 누른 칸 사고)
CLOSE = ("X", "x", "닫기", "×", "오늘 그만", "나중에", "건너뛰기", "광고 건너뛰기")


def own_text(btn, ns):
    inner = [m for m in ns if m is not btn and m["click"] and phone.inside(btn["b"], m["b"])]
    out = []
    for n in ns:
        if not phone.label(n) or not phone.inside(btn["b"], n["b"]):
            continue
        if n is not btn and any(phone.inside(m["b"], n["b"]) for m in inner):
            continue  # 안쪽 다른 버튼의 글자
        out.append(phone.label(n))
    return " ".join(out)


def words_of(t):
    """AI가 말한 글자를 낱말로 (03:38: 셸 치환으로 [\\s()]가 [s()]로 망가져 's'로 나누고 있었음)"""
    return [norm(x) for x in re.split(r"[\s()+＋,·]+", t or "") if len(x) >= 2 and x not in ("버튼", "줄의", "칸", "글자")]


def is_close(t):
    """닫기 계열인지 — 낱말 단위로 (03:38: 「KTX」 안의 X를 닫기로 착각)"""
    toks = re.split(r"[\s()]+", t or "")
    return any(x in ("X", "x", "×", "닫기", "나중에", "건너뛰기") for x in toks) or any(w in (t or "") for w in ("닫기", "오늘 그만", "광고 건너뛰기"))


def norm(s):
    return re.sub(r"[\s()\[\],.·'\"]", "", s or "")


def validate2(name, o):
    LAST.clear()  # 지난 검사 칸이 남아 엉뚱한 칸을 표시 · 누르지 않게
    act = (o.get("action") or "").upper()
    if act != "TAP":
        return act, "TAP 아님"
    t = (o.get("target") or "").strip()
    for w in phone.BANNED_CARD + ["장바구니", "담기", "구매", "결제", "구독", "카트"]:
        if w in t:
            return "STOP", f"target에 금지 단어 '{w}'"
    # AI가 「＋ · − · X」 같은 아이콘을 말하면 낱말로 칸을 고르지 않고 그 자리의 가장 작은 실제 칸으로 검사 (03:41)
    #  ＋는 앱마다 뜻이 다름: 배민 = 장바구니 담기(막음) / 코레일 = 어른 인원증가(허용) → 실제 칸 이름으로 판단
    icon = bool(re.search(r"[+＋−]|아이콘|동그란", t))
    b = o.get("bounds")
    if not b or len(b) != 4:
        return "UNSURE", "bounds 없음"
    ns = nodes_of(name)
    cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
    hits = [n for n in ns if n["click"] and n["b"][0] <= cx <= n["b"][2] and n["b"][1] <= cy <= n["b"][3]]
    if not hits:
        return ("TAP_SCREEN_ONLY", "글자에 없는 닫기 → 숨은 팝업, 스크린숏 기준 허용") if is_close(t) \
            else ("UNSURE", "그 자리에 누를 칸 없음")
    # AI가 말한 글자를 가진 칸을 먼저 (가운데 좌표의 가장 작은 칸이 엉뚱한 안쪽 칸일 수 있음)
    named = [] if icon else [n for n in hits if t and any(k in norm(own_text(n, ns)) for k in words_of(t))]
    btn = min(named or hits, key=lambda n: (n["b"][2] - n["b"][0]) * (n["b"][3] - n["b"][1]))
    LAST["btn"] = btn
    txt = own_text(btn, ns)
    big = (btn["b"][2] - btn["b"][0]) >= 300 and (btn["b"][3] - btn["b"][1]) >= 150
    words = phone.BANNED_CARD if big else phone.BANNED
    for w in words:
        if w in txt:
            return "BLOCK", f"그 칸 글자에 금지 단어 '{w}' ('{txt[:30]}')"
    if not big and phone.PRICE.search(txt):
        return "BLOCK", "작은 버튼에 금액"
    if not txt:
        return ("TAP", "글자 없는 큰 칸(스크린숏 판단)") if big else ("BLOCK", "글자 없는 작은 버튼")
    # AI가 본 글자와 그 자리 글자 비교
    if t and not icon and not any(k in norm(txt) for k in [norm(t)] + words_of(t)):
        if is_close(t):
            return "TAP_SCREEN_ONLY", f"AI는 '{t}'를 봤는데 그 자리 글자는 '{txt[:20]}' → 숨은 팝업 의심, 닫기라 허용"
        return "MISMATCH", f"AI '{t[:15]}' ≠ 그 자리 '{txt[:20]}' → 다시 판단"
    return "TAP", f"통과 ('{txt[:25]}')"


def shown_bounds(o):
    """표시할 칸: 검사 층이 검사한 실제 칸. 그 자리에 칸이 없던 경우(숨은 팝업의 닫기)만 AI 좌표 (11/25: 검사한 칸 = 표시할 칸)"""
    return LAST["btn"]["b"] if LAST.get("btn") else o.get("bounds")


if __name__ == "__main__":
    for l in open("eval_v2_results.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r["rep"] != 0:
            continue
        fin, why = validate2(r["case"], r["out"])
        if fin != r["final"] or fin not in ("TAP", "STOP", "WAIT"):
            print(r["case"].split("/")[1][:14].ljust(14), r["method"][:10].ljust(10), r["final"], "→", fin, "|", why[:70])
