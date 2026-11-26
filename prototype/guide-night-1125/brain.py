"""
AI 판단기(두뇌) · 11/25 저녁 우석
  규칙으로 모든 화면 예외를 다 막을 수 없음 → AI가 「목표에 가장 가까운 버튼」을 고르고,
  규칙은 AI가 넘을 수 없는 「안전 울타리」만, 앱 지식 표는 AI에게 주는 「앱 지도(힌트)」로 바꿈.
  화면에 없는 정보(밀면 나오는 것 · 누르면 나오는 다음 화면)는 쓰면 쓸수록 쌓이는 「화면 기억」으로 채움.

판단 순서 (decide)
  0 울타리   : 캡처 · 전송 금지 화면, 돈 · 권한 · 동의, 코레일 「예매」 앞 → 바로 멈춤 · 어르신이 고름 (AI 안 부름)
  1 빠른 길  : 확인 · 닫기 팝업(규칙으로 확실한 것만)
  2 경험     : 같은 화면 + 같은 목표에서 전에 성공한 선택 → AI 안 부름 (AI 캐싱)
  3 AI       : 후보 버튼 c1..cN(글자만 · 개인정보 가림) + 목표 + 앱 지도 + 화면 기억 + 비슷한 화면 성공 사례
               → JSON 스키마로 답을 강제(structured outputs)
  4 하네스   : 고른 후보가 실제로 있나 · ⛔ 버튼 아닌가 · 형식 → 틀리면 이유를 알려 주고 한 번 더, 또 틀리면 멈춤
  글자로 판단이 안 되는 화면(글자 없는 큰 칸 등)은 AI가 NEED_IMAGE → 스크린숏 판단으로 넘김 (AI 라우팅)

쌓는 것 (learn/, 저장소에 안 올림 · 개인정보 가린 글자만)
  steps.jsonl      : 단계마다 화면 후보 · AI 답 · 결과(화면 넘어감 · 되돌아옴 · 예측 맞음) = 학습 데이터 · 골든셋 후보
  screen_map.json  : 화면 지문 → 버튼 글자, 밀면 나온 글자, 누르면 간 화면 (나중에 GraphDB로 옮기기 좋은 모양)
  experience.json  : (화면, 목표) → 성공한 선택 · 실패 수
"""
import hashlib, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phone
import guide_sim as G
from mask import mask_text

BASE = os.path.dirname(os.path.abspath(__file__))
LEARN = os.environ.get("GUIDE_LEARN") or os.path.join(BASE, "learn")
MAXC = 60          # AI에게 보여 줄 후보 버튼 최대 수
AI_MAX = 40        # 한 번 안내에 AI 최대 호출 수(글자 판단은 싸서 사진보다 넉넉히)
EFFORT = os.environ.get("GUIDE_BRAIN_EFFORT", "medium")  # 11/25 brain_eval 2번씩: medium 23/24 · 약 3.9초, low 21 ~ 22/24 · 약 2.7초
# 11/25 밤 brain_eval(저장 화면 24개)로 잰 결과 → 기본은 「긴 답 + medium + 생각 켬」 그대로 둠. 속도는 경험 재사용으로 얻기
#   긴 답 · medium · 생각 켬 23/24 · 4.0초 | 짧은 답 · medium 21/24 · 3.3초 | 짧은 답 · low 16/24 · 2.0초
#   짧은 답 · low · 생각 끔 18/24 · 2.0초 | 긴 답 · low · 생각 끔 16/24 · 4.1초   (why · progress를 적는 게 생각 역할을 함)
THINK = os.environ.get("GUIDE_BRAIN_THINK", "on") != "off"   # off = Haiku 생각 끄기(effort high 이하에서만) — 정확도가 크게 떨어짐(위)
VERBOSE = os.environ.get("GUIDE_BRAIN_VERBOSE", "1") == "1"  # 0 = 짧은 답(빠르지만 21/24). 기본 1 = 이유 · 예측 · 소리 말까지
REJECT_SEC = 45   # 같은 안내가 이만큼 그대로면 「안 됨」으로 보고 다시 판단(A2)
ACTIONS = ["TAP", "SCROLL", "BACK", "WAIT", "PICK_BY_USER", "ASK", "STOP", "DONE", "NEED_IMAGE"]

# ---------------------------------------------------------------- 앱 지도: 규칙이 아니라 AI에게 주는 힌트(사람이 적는 「이 앱은 이렇게 생김」)
APP_MAP = {
    "com.korail.talk": (
        "코레일톡. 첫 화면 「어디로 떠나볼까요?」에 출발역선택 · 도착역선택 · 가는날 · 인원 · 열차 조회 버튼이 있다. "
        "고른 값은 버튼 글자에 「출발역 서울 선택됨」처럼 보인다. 순서: 출발역 → 도착역 → 가는날 → (인원) → 열차 조회. "
        "역 고르는 시트: 「주요역」 탭에 큰 역, 안 보이면 초성 탭(부산=ㅂ, 경주=ㄱ)을 누르거나 목록을 민다. "
        "가는날 시트: 달력. 보이는 달이 다르면 다음달 · 이전달, 날짜를 누른 뒤 「선택 완료」. "
        "인원 시트: 종류별 인원증가 · 인원감소, 다 맞으면 「선택 완료」. 출발 · 도착이 거꾸로면 「출발역과 도착역 바꾸기」. "
        "열차 목록(출발 빠른 순): 열차는 어르신이 고른다(PICK_BY_USER). 열차를 고르면 창에 「좌석 선택」 · 「바로 예매」가 뜬다 → 「좌석 선택」만 안내. "
        "좌석 화면: 자리는 어르신이 고른다. 「예매」 · 「바로 예매」부터는 로그인 · 결제라 STOP."),
    "com.sampleapp": (
        "배달의민족. 첫 화면 음식배달 칸에 카테고리 7칸이 있고, 원하는 카테고리가 없으면 「음식배달에서 더보기」. "
        "햄버거는 「패스트푸드」 카테고리. 가게 목록(기본순)은 아래로 밀면 가게가 더 나온다. 가게 카드를 누르면 메뉴 화면. "
        "메뉴는 이름 글자를 누른다(옆 ＋ · 담기 아님). 장바구니 담기 · 주문부터는 STOP."),
    "com.coupang.mobile.eats": (
        "쿠팡이츠. 첫 화면 카테고리 줄은 가로로 밀면 더 나온다(버거는 오른쪽). 카테고리 화면 위쪽에 브랜드 칩(맥도날드 등), "
        "칩을 누르면 그 브랜드 가게 목록. 가게 카드 → 메뉴 화면, 메뉴는 이름 글자. 카트 · 담기 · 주문부터는 STOP."),
}

SYS = (
    "너는 어르신 스마트폰 길잡이의 판단기야. 너는 누르지 않고, 어르신이 누를 버튼 하나를 골라 안내한다.\n"
    "목표에 가장 가까워지는 「다음 한 수」를 골라라.\n"
    "1) 목표를 칸(출발 · 도착 · 날짜 · 인원 · 메뉴 등)으로 나눠, 화면 글자로 이미 맞게 채워진 칸과 남은 칸을 progress에 적는다.\n"
    "2) 남은 칸 중 지금 화면에서 가장 앞 단계 버튼을 pick(c번호)으로 고른다. 이미 맞게 채워진 칸은 다시 누르지 않는다.\n"
    "3) 원하는 것이 화면에 없으면 [화면 기억](밀면 나왔던 것 · 누르면 갔던 화면)을 먼저 믿고, 기억이 없으면 [앱 지도]로 다음 화면을 예측한다. "
    "목록이면 SCROLL(scroll_dir), 탭 · 더보기 · 초성 · 다음달처럼 그쪽으로 가는 버튼이 있으면 그 버튼을 TAP.\n"
    "4) 팝업 · 광고 · 안내 창이 화면을 가리면 닫기 · 확인 · 나중에를 먼저 누른다.\n"
    "5) ⛔ 표시 버튼은 절대 pick하지 않는다. 목표가 결제 · 예매 · 주문 · 담기 · 로그인 · 전송 단계에 왔으면 STOP.\n"
    "6) 열차 시간 · 좌석 · 가게 · 사진처럼 어르신 마음대로 고를 것은 PICK_BY_USER(say에 무엇을 고를지).\n"
    "7) 목표에 값이 없는 칸(예: 출발역을 말 안 함)은 그 칸을 열기 전에 ASK(say에 짧은 질문 하나). 앱에 남아 있는 지난 값을 목표로 여기지 않는다.\n"
    "7-1) 광고 · 배너 · 추천 문구(「~어때요?」 · 할인 · 이벤트)보다 앱의 정식 카테고리 · 메뉴 · 탭 버튼을 고른다. 정식 버튼이 안 보이면 SCROLL.\n"
    "8) 버튼에 글자가 없거나 글자만으로는 판단이 안 되면 NEED_IMAGE.\n"
    "9) DONE은 목표의 마지막 버튼(조회 · 검색 등)까지 눌러 결과 화면이 나왔을 때만. 칸이 다 채워졌어도 조회 버튼이 남았으면 그 버튼을 TAP. [지금까지]에서 같은 버튼을 두 번 넘게 안내했는데 그대로면 다른 방법을 쓴다. 엉뚱한 화면이면 BACK.\n"
    "progress = 맨 먼저 적기: 「맞음: 칸들 / 남음: 칸들」 40자 이내, say = 카드 큰 글씨 14자 이내(예: '출발역' 누르세요), "
    "screen = 지금 화면 이름 12자 이내, confidence = 0 ~ 1. TAP이 아니면 pick은 빈 글자.")
SYS_VERBOSE = ("\nsub = 작은 글씨 20자 이내, speak = 소리로 읽을 쉬운 말 1 ~ 2문장, "
               "why = 고른 이유 한 줄, expect_next = 그 버튼을 누르면(또는 밀면) 나올 화면 예측 한 줄.")

# progress를 맨 앞에: 「채워진 칸 · 남은 칸」을 먼저 적게 해야 이미 채운 칸을 다시 누르지 않음
# (11/25 밤 brain_eval: progress를 빼니 medium 21/24 · low 16/24 · 생각 끔 12/24 — 「출발역 서울 선택됨」을 또 누름)
SHORT_FIELDS = ["progress", "action", "pick", "scroll_dir", "say", "screen", "confidence"]
LONG_FIELDS = SHORT_FIELDS + ["sub", "speak", "why", "expect_next"]
_TYPES = {"action": {"type": "string", "enum": ACTIONS}, "scroll_dir": {"type": "string", "enum": ["down", "up", "left", "right", "none"]},
          "confidence": {"type": "number"}}


def schema(verbose=None):
    f = LONG_FIELDS if (VERBOSE if verbose is None else verbose) else SHORT_FIELDS
    return {"type": "object", "properties": {k: _TYPES.get(k, {"type": "string"}) for k in f}, "required": f, "additionalProperties": False}


SCHEMA = schema(True)  # 옛 코드 호환


# ---------------------------------------------------------------- 화면 → 후보 버튼
def _labels_in(btn, ns):
    inner = [m for m in ns if m is not btn and m["click"] and m["b"] != btn["b"] and phone.inside(btn["b"], m["b"])]
    out = []
    for n in ns:
        L = phone.label(n)
        if not L or not phone.inside(btn["b"], n["b"]):
            continue
        if n is not btn and n["b"] != btn["b"] and any(phone.inside(m["b"], n["b"]) for m in inner):
            continue  # 안쪽 다른 버튼의 글자
        out.append(L)
    return list(dict.fromkeys(out))


def _big(b):
    return (b[2] - b[0]) >= 300 and (b[3] - b[1]) >= 150


def ban_reason(text, b):
    """길잡이가 안내하면 안 되는 버튼(phone.check와 같은 단어표). AI에게는 ⛔로 보여 주고, 골라도 하네스가 막음"""
    t = text.strip()
    if t in phone.OK_EXACT:
        return None
    for w in (phone.BANNED_CARD if _big(b) else phone.BANNED):
        if w in t:
            return f"금지 단어 '{w}'"
    if not _big(b) and phone.PRICE.search(t):
        return "작은 버튼에 금액"
    return None


def candidates(ns):
    W = max((n["b"][2] for n in ns), default=1080)
    H = max((n["b"][3] for n in ns), default=2400)
    seen = {}
    for n in ns:
        b = tuple(n["b"])
        if not n["click"] or b in seen or b[2] <= b[0] or b[3] <= b[1]:
            continue
        if (b[2] - b[0]) * (b[3] - b[1]) > 0.6 * W * H:  # 화면을 거의 덮는 칸 = 배경
            continue
        labs = _labels_in(n, ns)
        text = " ".join(labs)[:60]
        if not text and not _big(b):
            continue  # 글자 없는 작은 아이콘은 설명할 수 없음
        seen[b] = dict(b=list(b), text=text or "(글자 없는 큰 칸)", node=n, edit=bool(n.get("edit")))
    out = sorted(seen.values(), key=lambda c: (c["b"][1] // 20, c["b"][0]))
    if len(out) > MAXC:  # 11/25 밤 A6: 위에서만 자르면 맨 아래 「선택 완료 · 조회」가 잘림 → 맨 아래 12개는 남김
        out = out[:MAXC - 12] + out[-12:]
    for i, c in enumerate(out):
        c["id"] = f"c{i + 1}"
        c["ban"] = ban_reason(c["text"], c["b"])
    return out


def info_lines(ns, cands, limit=30):
    """누를 수 없는 글자(제목 · 안내) — 버튼 안 글자는 빼고"""
    out = []
    for n in ns:
        L = phone.label(n)
        if not L or n["click"] or any(phone.inside(c["b"], n["b"]) for c in cands):
            continue
        out.append(L[:40])
    return list(dict.fromkeys(out))[:limit]


def _norm(s):
    return re.sub(r"\d", "#", re.sub(r"\s+", "", s or ""))


def _repeated(cands):
    """목록 · 격자 칸(내용이 바뀌는 칸): 왼쪽 · 크기가 같은 칸이 위아래로 4개 이상, 또는 위 · 크기가 같은 칸이 옆으로 4개 이상.
    앱마다 이름을 몰라도 모양으로 앎(DroidBot · APE의 「바뀌는 내용 빼고 같은 화면」 생각, 11/25 밤 D2)"""
    col, row = {}, {}
    for c in cands:
        l, t, r, b = c["b"]
        col.setdefault((l // 24, (r - l) // 24, (b - t) // 40), []).append(c)   # 같은 크기 칸이 위아래로(배너는 크기가 달라 빠짐)
        row.setdefault((t // 24, (b - t) // 24, (r - l) // 40), []).append(c)
    rep = set()
    for g in list(col.values()) + list(row.values()):
        if len(g) >= 4:
            rep.update(id(c) for c in g)
    return rep


def _volatile(c):
    """목록이 아닌데 자주 바뀌는 칸(도는 배너 · 광고): 긴 글자, 광고 말(PROMO), 큰 칸에 12자 넘는 글자"""
    t = _norm(c["text"])
    return len(t) > 20 or bool(PROMO.search(c["text"])) or (_big(c["b"]) and len(t) > 12)


def _pkg(ns):
    return next((n["pkg"] for n in ns if n["pkg"]), "?")


_CLOCK = re.compile(r"\d{1,2}:\d{2}(:\d{2})?")  # 시계 · 남은 시간(4:59)만 지움
_VALS = re.compile(r"\d{1,2}월\d{1,2}일|\d+(?:명|매|장|석|시)")  # 긴 칸에서도 지문에 남길 값(띄어쓰기 지운 글자 기준) — 11/27


def fingerprint(ns):
    """화면 지문(바뀜 알아채기 · 이번 안내 기억용): 앱 + 칸 종류 + 짧은 버튼 글자(띄어쓰기 지움, 시계 모양 숫자만 지움).
    - 목록 칸은 앞 12자만(밀면 바뀐 걸 알아야 함), 목록 아닌 자주 바뀌는 칸(도는 배너 · 광고 문구, _volatile)은 뺌 (11/25 밤 B1)
    - 11/25 밤 실제 폰: 숫자를 다 지웠더니 「가는날, 11월 25일」 → 「27일」로 바뀌어도 같은 화면 → 옛 안내 「가는날」을 0초로 또 띄움.
      그래서 날짜 · 인원 숫자는 남기고 시계(12:34) · 남은 시간 모양만 지움"""
    cands = candidates(ns)
    rep = _repeated(cands)
    toks = set()
    for c in cands:
        t = _CLOCK.sub("#", _sp(c["text"]))
        if id(c) in rep:
            toks.add("L:" + t[:12])
        elif not _volatile(c):
            toks.add(c["node"].get("cls", "") + ":" + t)
        elif not PROMO.search(c["text"]):
            # 11/27 폰 시험: 「가는날, 2026년 11월 28일 (토) 0시 이후, 버튼」은 20자가 넘어 _volatile로 통째로 빠짐
            # → 27일 화면과 28일 화면이 같은 지문 → 옛 안내 「가는날」을 0초로 반복. 긴 칸도 「앞 이름 + 날짜 · 인원 · 시 값」은 남김
            vals = _VALS.findall(t)
            if vals:
                toks.add("V:" + t.split(",")[0][:8] + ":" + ",".join(vals))
    # 11/25 밤 실제 폰: 출발역 시트와 도착역 시트는 버튼이 똑같고 제목(누를 수 없는 글자)만 다름
    # → 같은 화면으로 봐서 도착역 시트에 「'서울' 누르세요」를 0초로 또 띄움. 짧은 제목 · 안내 글자도 지문에 넣음
    for x in info_lines(ns, cands):
        x = _CLOCK.sub("#", _sp(x))
        if len(x) <= 20 and not PROMO.search(x):
            toks.add("I:" + x)
    return hashlib.md5((_pkg(ns) + "|" + "|".join(sorted(toks))).encode()).hexdigest()[:12]


def _sp(s):
    return re.sub(r"\s+", "", s or "")  # 값 비교용: 띄어쓰기만 지움(숫자는 그대로 — 「11월 18일」 ≠ 「11월 25일」)


def _vals(slots):
    """목표 값 → 자리표시 이름, 긴 값 먼저(「11월 26일 (목)」이 「11월 26일」보다 먼저)"""
    out = []
    for k, v in (slots or {}).items():
        v = str(v or "").strip()
        if v and not re.match(r"^\d+$", v) and ":" not in v:  # 숫자만 · 「어른:2」 같은 내부 표기는 화면 글자가 아님
            out.append((_sp(v), "{" + ("DATE" if k == "DATE_SHORT" else k) + "}"))
    return sorted(set(out), key=lambda x: -len(x[0]))


def tmpl(text, slots):
    """글자 안의 목표 값을 자리표시로: 「부산」 → {ARRIVAL}. 경험을 다른 목표(대구)에도 쓰려고 (11/25 밤 D3)"""
    t = _sp(text)
    for v, k in _vals(slots):
        t = t.replace(v, k)
    return re.sub(r"\d", "#", t)  # 값을 자리표시로 바꾼 뒤 남은 숫자(시계 · 개수)만 지움


def fill(t, slots):
    for v, k in _vals(slots):
        t = t.replace(k, v)
    return _norm(t)


def visible_slots(ns, slots):
    alltxt = _sp(" ".join(phone.label(n) for n in ns if phone.label(n)))
    return sorted({k.strip("{}") for v, k in _vals(slots) if v in alltxt})


def exp_key(ns, slots):
    """경험 열쇠: 앱 + 목록 아닌 짧은 글자(목표 값은 자리표시) + 안내 글자 + 화면에 보이는 목표 칸 + 목표 칸 이름.
    → 「서울 → 부산」에서 배운 걸 「서울 → 대구」에도 씀. 값은 열쇠에 안 들어감"""
    cands = candidates(ns)
    rep = _repeated(cands)
    toks = {"B:" + tmpl(c["text"], slots) for c in cands if id(c) not in rep and not _volatile(c)}
    toks |= {"I:" + tmpl(x, slots) for x in info_lines(ns, cands) if len(_norm(x)) <= 20}
    names = sorted(k for k in (slots or {}) if k != "DATE_SHORT")
    raw = _pkg(ns) + "|" + "|".join(sorted(toks)) + "|see=" + ",".join(visible_slots(ns, slots)) + "|goal=" + ",".join(names)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- 쌓는 곳(화면 기억 · 경험 · 단계 기록)
def _load(name, default):
    p = os.path.join(LEARN, name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _save(name, obj):
    os.makedirs(LEARN, exist_ok=True)
    p = os.path.join(LEARN, name)
    json.dump(obj, open(p + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


def _log(rec):
    os.makedirs(LEARN, exist_ok=True)
    rec["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(LEARN, "steps.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


class Memory:
    def __init__(self):
        self.map = _load("screen_map.json", {})
        self.exp = _load("experience.json", {})

    def save(self):
        _save("screen_map.json", self.map)
        _save("experience.json", self.exp)

    def remember(self, ns, title=""):
        fp = fingerprint(ns)
        pkg = next((n["pkg"] for n in ns if n["pkg"]), "?")
        e = self.map.setdefault(fp, dict(pkg=pkg, labels=[], title="", seen=0, below={}, next={}))
        e["labels"] = [mask_text(c["text"]) for c in candidates(ns)][:MAXC]
        e["seen"] += 1
        if title:
            e["title"] = title[:40]
        return fp

    def similar(self, ns, min_j=0.6):
        """같은 지문, 없으면 버튼 글자가 60% 넘게 겹치는 같은 앱 화면(목록 내용이 조금 바뀌어도)"""
        fp = fingerprint(ns)
        if fp in self.map:
            return fp, self.map[fp]
        pkg = next((n["pkg"] for n in ns if n["pkg"]), "?")
        mine = {_norm(mask_text(c["text"])) for c in candidates(ns)}
        best, bj = None, min_j
        for k, e in self.map.items():
            if e["pkg"] != pkg:
                continue
            other = {_norm(x) for x in e["labels"]}
            j = len(mine & other) / max(1, len(mine | other))
            if j >= bj:
                best, bj = k, j
        return (best, self.map[best]) if best else (None, None)

    def recall_text(self, ns):
        """AI에게 줄 「화면 기억」: 밀면 나왔던 버튼, 누르면 갔던 화면과 그 화면의 버튼 몇 개(= 다음 화면 미리 보기)"""
        fp, e = self.similar(ns)
        if not e:
            return ""
        lines = []
        for d, labs in e["below"].items():
            if labs:
                lines.append(f"- {d}로 밀면 나왔던 버튼: " + ", ".join(labs[:15]))
        for lab, nfp in list(e["next"].items())[:8]:
            n = self.map.get(nfp)
            peek = ", ".join([x for x in (n or {}).get("labels", []) if len(x) >= 2][:12])  # 초성 탭(ㄱ · ㄴ) 같은 한 글자는 빼고
            lines.append(f"- '{lab}' 누르면 갔던 화면" + (f"({n['title']})" if n and n.get("title") else "") + (f": {peek}" if peek else ""))
        return ("이 화면(또는 아주 비슷한 화면)을 전에 봤어요.\n" + "\n".join(lines)) if lines else ""

    def examples(self, pkg, gk, ns, k=3):
        """비슷한 화면에서 성공한 선택(목표가 달라도 참고) → AI에게 예시로"""
        fp, _ = self.similar(ns)
        out = []
        for key, x in self.exp.items():
            if x.get("fp") == fp and trusted(x):
                out.append(f"- 목표 칸 {x.get('goal', '')} 일 때 {x['action']} '{x.get('pick_tmpl', '')}' → 다음 화면으로 넘어감")
        return out[:k]


def trusted(x):
    """다시 써도 되는 경험: 실패 0번 + (실제로 누른 버튼이 안내와 같았던 성공 1번 또는 확인 못 한 성공 2번) — 11/25 밤 D1 · A3"""
    return x.get("fail", 0) == 0 and (x.get("ok_v", 0) >= 1 or x.get("ok_u", 0) >= 2)


MEM = [None]
SESSION = {}   # 이번 안내: 화면 지문 → 판단 (같은 화면에 AI를 다시 부르지 않음)
HIST = []      # 이번 안내에서 한 일(AI에게 [지금까지]로)
TRAIL = []     # (지문, 판단) 지나온 화면
STATS = dict(ai=0, exp=0, guard=0, fast=0, rejected=0, wrong_click=0, done_refused=0)
REJ = {}       # 화면 지문 → 「안 됨」으로 다시 판단한 횟수(A2)


def mem():
    if MEM[0] is None:
        MEM[0] = Memory()
    return MEM[0]


def reset():
    SESSION.clear(); HIST.clear(); TRAIL.clear(); REJ.clear()
    for k in STATS:
        STATS[k] = 0


def goal_key(pkg, slots):
    return pkg + " " + json.dumps({k: v for k, v in sorted(slots.items()) if k != "DATE_SHORT"}, ensure_ascii=False)


# ---------------------------------------------------------------- 0 울타리 · 1 빠른 길
def guard(ns, pkg):
    """AI가 넘을 수 없는 것만. None이면 AI 판단으로"""
    why = G.capture_block_reason(ns, pkg)
    st, hint = G.screen_type(ns)
    if st in G.RULE_REPLY:
        a, say = G.RULE_REPLY[st]
        first, _, rest = say.partition(". ")
        return dict(layer="울타리", action=a, say=first.rstrip(".")[:18], sub=rest[:24], b=None, label=st)
    if why:  # 글자도 AI로 안 보냄(비밀번호 · 인증 · 카드 · 로그인 · 허용 앱 아님)
        return dict(layer="울타리", action="STOP", say="여기는 직접 해 주세요", sub="이 화면은 보지 않을게요", b=None, label=f"AI로 안 보냄: {why}")
    labels = [phone.label(n) for n in ns if phone.label(n)]
    if pkg == "com.korail.talk":  # 좌석: 자리는 어르신이, 다 고르면 「예매」 앞에서 끊음
        m = next((m for L in labels for m in [re.match(r"^(\d+)석 중 (\d+)석 선택됨$", L)] if m), None)
        if m:
            need, got = int(m.group(1)), int(m.group(2))
            if got < need:
                return dict(layer="울타리", action="PICK_BY_USER", say="앉을 자리를 골라 주세요", sub=f"{need - got}자리 · 창측이 창가예요", b=None, label=f"좌석 고르기 {got}/{need}")
            return dict(layer="울타리", action="STOP", say="여기부터는 직접 해 주세요", sub="'예매'부터 로그인 · 결제예요", b=None, label="예매 앞 멈춤")
    if st in ("ONBOARDING", "ALERT", "POPUP"):
        btn = G.find(ns, hint, contains=True)
        if btn:
            return dict(layer="빠른 길", action="TAP", say=f"'{hint}' 누르세요", sub="", b=btn["b"], label=hint, btn=btn, pick_text=hint)
    return None


# ---------------------------------------------------------------- 3 AI · 4 하네스
PROMO = re.compile(r"어때요\?|할인|쿠폰|이벤트|특가|광고|혜택|타임딜|증정")  # 막지는 않고 AI에게 표시만 (11/25 평가: 쿠팡이츠 「버거 어때요?」 배너를 카테고리로 앎)

def build_prompt(pkg, ns, cands, goal, slots):
    parts = [f"목표: {goal}", f"앱: {pkg}"]
    if APP_MAP.get(pkg):
        parts.append("[앱 지도]\n" + APP_MAP[pkg])
    if HIST:
        parts.append("[지금까지]\n" + "\n".join(f"{i + 1}) {h}" for i, h in enumerate(HIST[-6:])))
    r = mem().recall_text(ns)
    if r:
        parts.append("[화면 기억]\n" + r)
    ex = mem().examples(pkg, goal_key(pkg, slots), ns)
    if ex:
        parts.append("[비슷한 화면 성공 사례]\n" + "\n".join(ex))
    info = info_lines(ns, cands)
    if info:
        parts.append("[화면 글자(누를 수 없음)]\n" + " / ".join(mask_text(x) for x in info))
    rows = [f"{c['id']} [{','.join(map(str, c['b']))}] '{mask_text(c['text'])}'" + (" [입력칸]" if c["edit"] else "")
            + (" [광고 · 추천일 수 있음]" if PROMO.search(c["text"]) else "") + (" ⛔" if c["ban"] else "")
            for c in cands]
    parts.append("[누를 수 있는 버튼] 위 → 아래 순서, ⛔ = 길잡이가 안내할 수 없음\n" + "\n".join(rows))
    return "\n\n".join(parts)


def done_missing(ns, slots):
    """「다 됐어요」 확인(D5): 목표 값(앱 표기, normalize.to_app 결과)이 화면 글자에 다 보이나. 없는 값 목록.
    앱별 규칙 없이 값 표기만 봄 — 표기를 바꿀 일은 normalize 한 곳에서 (LlamaTouch의 「꼭 보여야 할 상태」)"""
    alltxt = _sp(" ".join(phone.label(n) for n in ns if phone.label(n)))
    miss = []
    for k, v in (slots or {}).items():
        if k == "DATE_SHORT":
            continue
        cand = [str(v)] + ([str(slots["DATE_SHORT"])] if k == "DATE" and slots.get("DATE_SHORT") else [])
        cand = [c for c in cand if c and not re.match(r"^\d+$", c) and ":" not in c]
        if cand and not any(_sp(c) in alltxt for c in cand):
            miss.append(f"{k}={v}")
    return miss


def check_plan(o, cands, ns=None, slots=None):
    """하네스 검사: (고친 답, 오류 또는 None)"""
    if not isinstance(o, dict):
        return None, "JSON 객체가 아님"
    act = str(o.get("action") or "").upper()
    if act not in ACTIONS:
        return None, f"action '{act}'은 없는 값"
    o["action"] = act
    if act == "TAP":
        c = next((c for c in cands if c["id"] == str(o.get("pick") or "").strip()), None)
        if not c:
            return None, f"pick '{o.get('pick')}'은 후보에 없음(c1 ~ c{len(cands)} 중 하나)"
        if c["ban"]:
            return None, f"{c['id']} '{c['text'][:20]}'은 ⛔ 버튼({c['ban']}) — 고르면 안 됨. 목표가 그 단계면 STOP"
        o["_cand"] = c
    if act == "SCROLL" and o.get("scroll_dir") in (None, "", "none"):
        return None, "SCROLL인데 scroll_dir이 없음"
    if act == "DONE" and ns is not None and slots:
        miss = done_missing(ns, slots)
        if miss:
            STATS["done_refused"] += 1
            return None, f"DONE인데 목표 값 {', '.join(miss)}이 화면 글자에 안 보임 — 그 칸을 채우거나 조회 버튼을 누르게 하세요"
    return o, None


def ask_ai(pkg, ns, cands, goal, slots):
    import ai
    user = build_prompt(pkg, ns, cands, goal, slots)
    err = None
    for attempt in range(2):
        content = user if not err else user + f"\n\n[앞 답이 틀렸어요] {err}\n다시 답해 주세요."
        txt = ai.call(ai.HAIKU, content, f"brain:{pkg}:{attempt}", system=SYS + (SYS_VERBOSE if VERBOSE else ""), schema=schema(),
                      quiet=True, effort=EFFORT, think=THINK, max_tokens=4096 if THINK else 1024)
        try:
            o = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        except Exception:
            o = None
        o, err = check_plan(o, cands, ns, slots)
        if o:
            return o, user
    return dict(action="STOP", say="직접 해 주세요", sub="제가 확실하지 않아요", pick="", why=f"하네스 2번 실패: {err}", screen="", progress="",
                expect_next="", speak="", scroll_dir="none", confidence=0), user


def scroll_area(ns, d):
    W = max((n["b"][2] for n in ns), default=1080)
    H = max((n["b"][3] for n in ns), default=2400)
    return [0, int(H * 0.3), W, int(H * 0.8)]


def _short(t):
    t = re.sub(r"^(출발역|도착역) .+ 선택됨$", lambda m: m.group(1), t.split(",")[0])
    return re.sub(r"\s*\([^)]*\)?$", "", t)[:10]


def to_decision(o, ns, source):
    act = o["action"]
    d = dict(layer=source, action=act, say=(o.get("say") or "")[:18], sub=(o.get("sub") or "")[:24], b=None, label="",
             speak=o.get("speak") or None, plan={k: v for k, v in o.items() if not k.startswith("_")})
    if act == "TAP":
        c = o["_cand"]
        d.update(b=c["b"], btn=c["node"], label=c["text"], pick_text=c["text"])
        if not d["say"]:
            d["say"] = f"'{_short(c['text'])}' 누르세요"
    elif act == "SCROLL":
        sd = o.get("scroll_dir") or "down"
        d.update(b=scroll_area(ns, sd), label=f"밀기({sd})", scroll_dir=sd,
                 sub=d["sub"] or {"down": "아래에 더 있어요", "up": "위에 있어요", "left": "왼쪽에 있어요", "right": "옆에 더 있어요"}.get(sd, ""))
    elif act == "NEED_IMAGE":
        d.update(action="AI", label="글자로 판단 안 됨 → 사진")
    else:
        d["label"] = f"AI {act}"
        if not d["say"]:
            d["say"] = {"BACK": "'뒤로' 누르세요", "WAIT": "잠깐 기다려 주세요", "DONE": "다 됐어요", "STOP": "직접 해 주세요"}.get(act, "직접 골라 주세요")
    return d


def decide(app, ns, slots, goal):
    pkg = _pkg(ns)
    fp = fingerprint(ns)
    if fp in SESSION:
        return SESSION[fp]
    g = guard(ns, pkg)
    if g:
        STATS["guard" if g["layer"] == "울타리" else "fast"] += 1
        g["fp"] = fp
        SESSION[fp] = g
        _log(dict(type="step", app=app, pkg=pkg, fp=fp, goal=mask_text(goal), source=g["layer"], action=g["action"], label=g.get("label")))
        return g
    if REJ.get(fp, 0) >= 2:  # 같은 화면에서 두 번 다시 판단해도 안 됨 → 사람에게
        d = dict(layer="AI", action="STOP", say="직접 해 주세요", sub="제가 잘 모르겠어요", b=None, label="두 번 다시 판단해도 안 됨", fp=fp)
        SESSION[fp] = d
        return d
    cands = candidates(ns)
    ek = exp_key(ns, slots)
    x = mem().exp.get(ek)
    o, prompt, source = None, None, "AI"
    if x and trusted(x):  # 2 경험: 같은 모양 화면 + 같은 목표 칸 + 같은 「보이는 목표 값」에서 성공했던 선택(값은 지금 목표로 채움)
        want = fill(x.get("pick_tmpl", ""), slots)
        c = next((c for c in cands if not c["ban"] and _norm(c["text"]) == want), None) if x["action"] == "TAP" else None
        if x["action"] != "TAP" or c:
            o = dict(x["plan"], action=x["action"], pick=c["id"] if c else "")
            o, _ = check_plan(o, cands, ns, slots)
            source = "경험"
    if not o:
        if STATS["ai"] >= AI_MAX:
            d = dict(layer="AI", action="STOP", say="직접 해 주세요", sub="제가 더 돕기 어려워요", b=None, label="AI 횟수 다 씀", fp=fp)
            SESSION[fp] = d
            return d
        STATS["ai"] += 1
        o, prompt = ask_ai(pkg, ns, cands, goal, slots)
    else:
        STATS["exp"] += 1
    d = to_decision(o, ns, source)
    d["fp"] = fp
    d["ek"] = ek
    d["step_id"] = f"{time.time():.3f}"
    SESSION[fp] = d
    mem().remember(ns, o.get("screen", ""))
    mem().save()
    HIST.append(f"{(o.get('screen') or '')[:20]}: {d['action']} '{d.get('pick_text') or d.get('label') or ''}'"[:80])
    _log(dict(type="step", id=d["step_id"], app=app, pkg=pkg, fp=fp, ek=ek, goal=mask_text(goal), slots=slots, source=source,
              cands=[dict(id=c["id"], text=mask_text(c["text"]), b=c["b"], ban=bool(c["ban"])) for c in cands],
              plan=d["plan"], pick_text=mask_text(d.get("pick_text") or "")))
    return d


def reject(fp, d, why="안내가 그대로라 안 되는 것 같음"):
    """A2: 같은 안내가 REJECT_SEC 동안 그대로 → 그 안내는 실패로 세고 이 화면을 다시 판단(두 번까지, 그다음은 STOP)"""
    REJ[fp] = REJ.get(fp, 0) + 1
    STATS["rejected"] += 1
    SESSION.pop(fp, None)
    ek = (d or {}).get("ek")
    if ek and ek in mem().exp:
        mem().exp[ek]["fail"] += 1
        mem().save()
    HIST.append(f"✗ '{(d or {}).get('pick_text') or (d or {}).get('label') or ''}' 안내: {why} → 다른 방법"[:80])
    _log(dict(type="reject", id=(d or {}).get("step_id"), fp=fp, why=why))


def click_matches(d, clicked):
    """사람이 실제로 누른 칸(시험 앱 CLICK 로그)이 안내한 칸인가. 가운데 점이 안내 칸 안 · 또는 글자가 겹침"""
    if not clicked or not d or not d.get("b"):
        return None
    c = clicked[-1]
    b = d["b"]
    if c.get("b"):
        cx, cy = (c["b"][0] + c["b"][2]) / 2, (c["b"][1] + c["b"][3]) / 2
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            return True
    a, p = _norm(c.get("label")), _norm(d.get("pick_text"))
    return bool(a and p and (a in p or p in a))


def observe(prev_ns, prev_d, new_ns, slots, clicked=None):
    """화면이 바뀐 뒤: 화면 기억(밀면 나온 것 · 누르면 간 곳)과 경험을 쌓음.
    clicked = 그사이 사람이 실제로 누른 칸(시험 앱 CLICK 로그, [{label, b}]). 있으면 안내와 같을 때만 성공(ok_v),
    없으면(옛 시험 앱) 「안내대로 했다」고 보되 ok_u로 따로 셈 → 2번 넘어야 다시 씀 (11/25 밤 D1 · A3 · A4)"""
    a, b = fingerprint(prev_ns), fingerprint(new_ns)
    if a == b or not prev_d:
        return
    m = mem()
    m.remember(prev_ns); m.remember(new_ns)
    undo = len(TRAIL) >= 2 and TRAIL[-2][0] == b and TRAIL[-1][0] == a
    act = prev_d.get("action")
    match = click_matches(prev_d, clicked) if act == "TAP" else None
    if clicked and match is False:  # 다른 걸 누름: 그 버튼이 어디로 가는지만 기억, 안내는 성공으로 안 셈
        lab = mask_text(clicked[-1].get("label") or "")
        if lab:
            m.map[a]["next"][lab] = b
        STATS["wrong_click"] += 1
        HIST.append(f"↪ 안내와 다른 '{lab[:15]}'을 누르심")
    elif act == "SCROLL":
        old = {c["text"] for c in candidates(prev_ns)}
        new = [mask_text(c["text"]) for c in candidates(new_ns) if c["text"] not in old]
        bl = m.map[a]["below"].setdefault(prev_d.get("scroll_dir", "down"), [])
        m.map[a]["below"][prev_d.get("scroll_dir", "down")] = list(dict.fromkeys(bl + new))[:30]
        match = bool(new)  # 밀었더니 새 버튼이 나옴 = 확인된 성공
    elif act == "TAP" and prev_d.get("pick_text"):
        m.map[a]["next"][mask_text(prev_d["pick_text"])] = b
    if undo:  # A →(안내) B →(뒤로) A : A에서 한 안내는 틀렸을 수 있음. B의 안내는 성공으로 안 셈(A4)
        pa, pd = TRAIL[-2]
        k = (pd or {}).get("ek")
        if k and k in m.exp:
            m.exp[k]["fail"] += 1
        HIST.append("↩ 앞 화면으로 되돌아옴(앞 안내가 틀렸을 수 있음)")
    elif act in ("TAP", "SCROLL") and prev_d.get("layer") in ("AI", "경험") and prev_d.get("plan") and match is not False:
        k = prev_d.get("ek") or exp_key(prev_ns, slots)
        x = m.exp.setdefault(k, dict(fp=a, goal=",".join(sorted(k2 for k2 in (slots or {}) if k2 != "DATE_SHORT")), action=act,
                                     pick_tmpl=tmpl(prev_d.get("pick_text") or "", slots), plan=prev_d["plan"], ok_v=0, ok_u=0, fail=0))
        x["ok_v" if match else "ok_u"] += 1
    exp_words = [w for w in re.split(r"[\s,·'()]+", (prev_d.get("plan") or {}).get("expect_next", "")) if len(w) >= 2]
    new_txt = " ".join(c["text"] for c in candidates(new_ns)) + " " + " ".join(info_lines(new_ns, candidates(new_ns)))
    hit = round(sum(1 for w in exp_words if w in new_txt) / len(exp_words), 2) if exp_words else None
    _log(dict(type="outcome", id=prev_d.get("step_id"), fp=a, next_fp=b, action=act, undo=undo, expect_hit=hit,
              clicked=[mask_text(c.get("label") or "") for c in (clicked or [])][-3:], click_match=match))
    notes = []
    if act == "TAP" and not clicked:  # 11/27 우석 ②안: 누른 칸 기록이 없으면 「안내대로 눌렀다」고 단정하지 않게 (기록 없으면 AI가 「이미 해 봤다」고 착각, W01 세션 시험 1/2)
        notes.append("누른 칸 확인 못 함")
    if hit is not None:
        notes.append(f"예측 맞음 {hit}")
    HIST.append("→ 화면 바뀜" + (f"({', '.join(notes)})" if notes else ""))
    m.save()


def track(fp, d):
    TRAIL.append((fp, d))
    del TRAIL[:-6]
