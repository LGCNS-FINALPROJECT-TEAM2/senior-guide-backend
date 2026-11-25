"""
Guide 서비스 판단 순서 시뮬레이션 (설계검토_1125.md 3절 검증용, AI 새 호출 없음)
  0 규칙(화면 종류) → 2 앱 지식(체크리스트 + 연결표) → 3 AI(저장된 v2 스크린숏+Haiku 답) → 검사 층(validate2)
결과: guide_sim_result.md
"""
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phone
from eval_v2 import nodes_of
from validate2 import validate2, own_text

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 앱 지식 (ERD '앱 지식' 표의 시제품)
KNOW = {
    "com.korail.talk": {
        "home": "어디로 떠나볼까요?",  # 시작 화면 표시 (02:38: 앱이 지난번 결과 화면에서 열림)
        "synonyms": {},
        "steps": [  # 체크리스트 칸 → 그 칸을 여는 버튼 / 고를 글자
            # check = 이미 맞게 채워졌는지 확인하는 글자 (02:25 추가: 남아 있던 값을 확인 안 하고 날짜를 건너뛸 뻔함)
            {"role": "DEPARTURE", "open": "출발역선택", "pick": "{DEPARTURE}", "tabs": ["주요역", "초성"], "check": "출발역 {DEPARTURE} 선택됨", "check_alt": "출발역 {DEPARTURE}", "sheet": "출발역 선택", "open_re": r"^출발역(선택| .+ 선택됨)$", "open_alt": r"^출발역 \S+$"},
            {"role": "ARRIVAL", "open": "도착역선택", "pick": "{ARRIVAL}", "tabs": ["주요역", "초성"], "check": "도착역 {ARRIVAL} 선택됨", "check_alt": "도착역 {ARRIVAL}", "sheet": "도착역 선택", "open_re": r"^도착역(선택| .+ 선택됨)$", "open_alt": r"^도착역 \S+$"},
            {"role": "DATE", "pick": "{DATE}", "check": "{DATE_SHORT}", "check_in": "가는날", "open_contains": "가는날", "then": "선택 완료", "sheet": "가는날 선택"},
            # 인원: 말했을 때만(선택 칸). 기본값은 어른 1명 (03:11: 「두 장」이 빠져 1명으로 조회할 뻔)
            {"role": "COUNT", "optional": True, "check": "어른 {COUNT}명", "check_in": "인원", "open_contains": "인원"},
            {"role": "SEARCH", "open": "열차 조회"},
        ],
        "station_group": {"서울": ["서울", "수서", "청량리"]},
        "unreadable": ["열차 목록"],
    },
    "com.sampleapp": {  # 배민
        "home": "음식배달에서 더보기",
        "search_entry": ["검색", "검색 버튼, 떡볶이? 김밥?"],  # 밀기 제한에 걸리면 음성 검색 안내 (03:24)
        "synonyms": {"햄버거": "패스트푸드"},
        "steps": [{"role": "CATEGORY", "pick": "{CATEGORY}", "check": "기본순"},  # 가게 목록 화면이면 카테고리는 끝
                  {"role": "STORE", "pick_contains": "{BRAND}", "card": True, "check": "가장 인기 있는 메뉴", "if_missing": {"action": "SCROLL", "dir": "up", "area": [0, 700, 1080, 1900], "max": 3}},
                  {"role": "ITEM", "pick_contains": "{ITEM}", "if_missing": {"action": "SCROLL", "dir": "up", "area": [0, 700, 1080, 1900], "max": 4}}],
        "danger_icons": ["장바구니 담기"],
    },
    "com.coupang.mobile.eats": {
        "search_entry": ["검색"],
        "synonyms": {"햄버거": "버거"},
        "steps": [{"role": "CATEGORY", "pick": "{CATEGORY}", "check": "추천순", "if_missing": {"action": "SCROLL", "dir": "left", "area": [0, 900, 1080, 1100], "max": 3}},
                  {"role": "BRAND", "pick": "{BRAND}", "check": "매장∙원산지정보"}, {"role": "STORE", "pick_contains": "{BRAND}", "card": True, "check": "매장∙원산지정보"},
                  {"role": "ITEM", "pick_contains": "{ITEM}", "if_missing": {"action": "SCROLL", "dir": "up", "area": [0, 700, 1080, 1900], "max": 4}}],
        "danger_icons": ["(이름 없는 카트 아이콘)"],
    },
}

# ---------------------------------------------------------------- 0단계 규칙: 화면 종류
def screen_type(ns):
    lab = [phone.label(n) for n in ns if phone.label(n)]
    alltxt = " ".join(lab)
    clickl = [own_text(n, ns) for n in ns if n["click"]]
    if any(n["pkg"].endswith("permissioncontroller") for n in ns):
        return "SYSTEM_PERMISSION", None
    if ("동의" in clickl or "동의하지 않음" in clickl or "미동의" in clickl) and ("권한" in alltxt or "약관" in alltxt):
        return "CONSENT", None
    if re.search(r"스폰서 · \d/\d|광고 건너뛰기", alltxt) and re.search(r"\d분 \d+초 중", alltxt):
        return "AD_PLAYING", None
    if re.search(r"없습니다|결과가 없|배차정보가 없", alltxt):
        return "NO_RESULT", None
    # 돈 버튼: 화면 아래 25% 안의 짧은 버튼만 (위쪽 쿠폰 배너 「할인 받고 주문하기」는 제외 — 02:30 오탐 수정)
    H = max(n["b"][3] for n in ns)
    for n in ns:
        L = phone.label(n)
        if L and len(L) <= 12 and re.search(r"구매하기|결제하기|주문하기|예매하기", L) and n["b"][1] > H * 0.75:
            return "PAYMENT_NEAR", None
    if re.search(r"페이지 중 1 페이지", alltxt) and "닫기" in alltxt:
        return "ONBOARDING", "닫기"
    if {"네", "아니오"} <= {c.strip() for c in clickl} or {"예", "아니요"} <= {c.strip() for c in clickl}:
        return "CONFIRM", None  # 「~하시겠습니까? 네/아니오」 → 어르신이 고름 (03:05)
    m = [c for c in clickl if c.strip() in ("확인", "확인 확인")]
    if m and len([c for c in clickl if c]) <= 3:
        return "ALERT", "확인"
    # 홍보 팝업: 위쪽 절반에 '닫기' + 할인 · 쿠폰 · 이벤트 · 타임딜 글자 (02:48 요기요 「요-타임딜」 시트를 AI가 본문으로 여기고 4번 밂)
    H2 = max(n["b"][3] for n in ns)
    has_close_top = any(n["click"] and own_text(n, ns).strip() == "닫기" and n["b"][1] < H2 * 0.5 for n in ns)
    promo = re.search(r"할인|쿠폰|이벤트|타임딜|혜택|증정|특가", alltxt)
    if has_close_top and promo and "시트 닫기" not in alltxt:
        return "POPUP", "닫기"
    for w in ("나중에 할게요", "오늘 그만 보기", "오늘은 그만 보기", "오늘 하루 보지 않기", "오늘 하루 그만 보기", "다시 보지 않기", "배너 접기"):  # 02:45 요기요 「오늘은 그만 보기」 추가
        if any(w in c for c in clickl) or w in alltxt:
            return "POPUP", w
    return "NORMAL", None


RULE_REPLY = {
    "CONFIRM": ("PICK_BY_USER", "휴대폰이 확인을 묻고 있어요. 내용을 보고 '네'나 '아니오'를 직접 골라 주세요."),
    "SYSTEM_PERMISSION": ("PICK_BY_USER", "휴대폰이 권한을 묻고 있어요. 직접 골라 주세요."),
    "CONSENT": ("PICK_BY_USER", "앱이 권한 동의를 묻고 있어요. 필수가 아니면 '동의하지 않음'을 골라도 돼요."),
    "AD_PLAYING": ("WAIT", "지금은 광고예요. 끝나거나 '건너뛰기'가 나올 때까지 기다려 주세요."),
    "NO_RESULT": ("ASK", "이 날은 결과가 없어요. 다른 날이나 다른 방법(기차 · 버스)으로 볼까요?"),
    "PAYMENT_NEAR": ("STOP", "여기부터는 돈이 나가는 단계예요. 직접 확인하고 누르세요."),
}


def find(ns, text, contains=False, card=False):
    for n in ns:
        L = phone.label(n)
        if not L:
            continue
        Lc, tc = L.replace(" ", ""), text.replace(" ", "")  # 띄어쓰기 무시 (03:10: 「불고기버거」 ↔ 메뉴 「불고기 버거」)
        ok = (tc in Lc) if contains else (Lc == tc or L == text + " 선택")
        if ok and "광고" not in own_text(phone.clickable_for(n, ns) or n, ns):
            btn = phone.clickable_for(n, ns)
            # 화면 60% 넘게 덮는 칸은 버튼이 아님(배경 · 시트 닫기) — 02:29 배민에서 화면 전체 칸을 누르려 함
            if btn and (btn["b"][2] - btn["b"][0]) * (btn["b"][3] - btn["b"][1]) < 0.6 * 1080 * 2400:
                # card=True(가게 · 상품 고르기)면 큰 카드만 — 02:36 쿠팡이츠: 가게 대신 '맥도날드' 필터 칩을 또 눌러 필터가 풀림
                if card and ((btn["b"][2] - btn["b"][0]) < 300 or (btn["b"][3] - btn["b"][1]) < 150):
                    continue
                return btn
    return None


CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def chosung(ch):
    c = ord(ch) - 0xAC00
    return CHO[c // 588] if 0 <= c < 11172 else ch


def knowledge(pkg, ns, slots, step_i, done=(), redo=()):
    k = KNOW.get(pkg)
    if not k:
        return None
    labels = [phone.label(n) for n in ns if phone.label(n)]
    fmt = {r: k["synonyms"].get(v, v) for r, v in slots.items()}
    # 인원 시트: 「○○ 인원증가 / 감소」로 목표 수 맞추기 (03:12: 어르신은 「경로(65세 이상)」 할인 대상일 수 있음)
    if "인원 선택" in labels and "PAX" in fmt:
        want = {}
        for part in fmt["PAX"].split(","):
            t, c = part.split(":"); want[t.strip()] = int(c)
        rows = []
        for t in ("어른", "어린이", "유아", "경로", "중증장애인", "경증장애인"):
            dec = next((n for n in ns if phone.label(n) == f"{t} 인원감소"), None)
            inc = next((n for n in ns if phone.label(n) == f"{t} 인원증가"), None)
            if not dec or not inc:
                continue
            cur = next((int(phone.label(n)) for n in ns if phone.label(n).isdigit() and dec["b"][2] <= n["b"][0] <= inc["b"][0]
                        and abs(n["b"][1] - dec["b"][1]) < 40), 0)
            rows.append((t, cur, want.get(t, 0), dec, inc))
        for t, cur, goal, dec, inc in rows:  # 늘릴 것 먼저 (총 0명이 되면 앱이 막을 수 있음)
            if cur < goal:
                b = phone.clickable_for(inc, ns) or inc
                return ("TAP", f"{t} 인원증가 ({cur}→{goal})", b["b"], "COUNT(고름)")
        for t, cur, goal, dec, inc in rows:  # 그다음 줄일 것
            if cur > goal:
                b = phone.clickable_for(dec, ns) or dec
                return ("TAP", f"{t} 인원감소 ({cur}→{goal})", b["b"], "COUNT(고름)")
        done_btn = find(ns, "선택 완료")
        if done_btn:
            return ("TAP", "선택 완료", done_btn["b"], "COUNT")
    steps = k["steps"][step_i:]
    if "시트 닫기" in labels:  # 시트가 열려 있으면 그 시트의 칸만 (서비스에선 Redis 세션이 '방금 연 칸'을 기억)
        steps = [st for st in steps if st.get("sheet") in labels] or steps
    # 출발 · 도착이 거꾸로 골라져 있으면 '바꾸기' 한 번 (02:37 추가)
    if "DEPARTURE" in fmt and "ARRIVAL" in fmt and any(L == f"출발역 {fmt['ARRIVAL']} 선택됨" for L in labels)             and any(L == f"도착역 {fmt['DEPARTURE']} 선택됨" for L in labels):
        sw = find(ns, "출발역과 도착역 바꾸기")
        if sw:
            return ("TAP", "출발역과 도착역 바꾸기", sw["b"], "DEPARTURE(바꾸기)")
    for st in steps:
        # 이 칸에 필요한 슬롯이 없으면 → 어르신께 되묻기 (03:05: 슬롯이 비면 오류로 죽음)
        need = set(re.findall(r"\{(\w+)\}", json.dumps(st, ensure_ascii=False)))
        if st["role"] not in done and need - set(fmt) and st.get("optional"):
            continue  # 선택 칸인데 말 안 함 → 기본값
        if st["role"] not in done and need - set(fmt):
            return ("ASK", f"{st['role']} 칸을 몰라요 → 되묻기", None, st["role"])
        if st["role"] in done:  # 세션이 '이미 고른 칸'으로 기억 (02:31: 밀어서 확인 글자가 사라지면 다시 고르려 함)
            continue
        val = None
        if "sheet" in st and "시트 닫기" in labels and st["sheet"] in labels:
            v = st["pick"].format(**fmt)
            if "then" in st and any(L.startswith("2026년 " + fmt.get("DATE_SHORT", "#") + " ") for L in labels):
                done_btn = find(ns, st["then"])  # 이미 골라짐 → '선택 완료'
                if done_btn:
                    return ("TAP", st["then"], done_btn["b"], st["role"])
            btn = find(ns, v)
            if btn:
                # 확정 버튼이 있는 칸은 '고름'만으론 끝이 아님 (02:40: 27일만 누르고 '선택 완료' 전에 끝으로 기억함)
                return ("TAP", v, btn["b"], st["role"] + ("(고름)" if "then" in st else ""))
        if "check" in st and st["role"] not in redo:  # redo = 잘못 누름으로 다시 해야 하는 칸(화면 확인을 믿지 않음)
            c = st["check"].format(**fmt)
            if any(c in L and (st.get("check_in", "") in L) for L in labels):
                continue  # 이미 맞게 채워짐
            # 큰글씨 모드처럼 글자가 「출발역」 · 「서울」로 나뉘면 → 누름 칸 안 글자를 합쳐 확인 (03:04)
            if "check_alt" in st:
                ca = st["check_alt"].format(**fmt)
                if any(own_text(n, ns).strip() == ca for n in ns if n["click"]):
                    continue
        for key in ("pick", "pick_contains"):
            if key in st:
                val = st[key].format(**{r: k["synonyms"].get(v, v) for r, v in slots.items()})
                btn = find(ns, val, contains=(key == "pick_contains"), card=st.get("card"))
                if not btn and st.get("card") and "if_missing" not in st:
                    return ("SCROLL", f"'{val}' 카드 안 보임 → 목록 아래로", [0, 700, 1080, 1900], st["role"])
                if btn:
                    return ("TAP", own_text(btn, ns)[:40], btn["b"], st["role"])
        # 목록(시트)이 이미 열려 있는데 고를 값이 안 보이면 → 초성 탭 → 그래도 없으면 밀기 (02:30 수정: 시트 제목을 열기 버튼으로 착각해 '시트 닫기'를 누르려 했음)
        if val and "tabs" in st and "시트 닫기" in labels:  # 목록 시트가 열려 있음
            tab = find(ns, chosung(val[0]))
            # 이미 그 초성 탭이면(같은 초성으로 시작하는 역들이 보이면) 탭 말고 밀기 (02:43)
            on_tab = sum(1 for L in labels if len(L) >= 2 and L[0] != val[0] and chosung(L[0]) == chosung(val[0]) and "선택" not in L) >= 3
            if tab and not on_tab:
                return ("TAP", f"초성 탭 '{chosung(val[0])}'", tab["b"], st["role"] + "(목록에서 안 보임)")
            return ("SCROLL", f"'{val}' 안 보임 → 목록 아래로", [0, 600, 1080, 2100], st["role"])
        if "open_contains" in st:
            for n in ns:
                L = phone.label(n)
                if L.startswith(st["open_contains"]) and "선택" not in L and "열기" not in st["role"]:
                    btn = phone.clickable_for(n, ns)
                    if btn:
                        return ("TAP", L[:40], btn["b"], st["role"] + "(열기)")
        if "open_alt" in st:  # 큰글씨 모드: 누름 칸 안 글자 「출발역 서울」
            for n in ns:
                if n["click"] and re.match(st["open_alt"], own_text(n, ns).strip()):
                    return ("TAP", own_text(n, ns)[:40], n["b"], st["role"] + "(열기)")
        if "open_re" in st:  # 한 번 고르면 버튼 글자가 「출발역 부산 선택됨」으로 바뀜 (02:43)
            for n in ns:
                if re.match(st["open_re"], phone.label(n)):
                    btn = phone.clickable_for(n, ns)
                    if btn:
                        return ("TAP", phone.label(n)[:40], btn["b"], st["role"] + "(열기)")
        if "open" in st:
            btn = find(ns, st["open"])
            if btn:
                return ("TAP", own_text(btn, ns)[:40], btn["b"], st["role"] + "(열기)")
        if "if_missing" in st and val:
            m = st["if_missing"]
            return (m["action"], f"'{val}' 안 보임 → {m['dir']}로 밀기", m["area"], st["role"])
        if "check" in st:
            return None  # 이 칸이 안 맞는데 할 게 없으면 뒤 칸으로 건너뛰지 않음 (02:43: 출발 · 도착이 틀린 채 조회함)
    return None


# ---------------------------------------------------------------- 시험 화면과 세션 상태
SLOTS_TRAIN = {"DEPARTURE": "서울", "ARRIVAL": "부산", "DATE": "11월 26일 (목)", "DATE_SHORT": "11월 26일"}
SLOTS_FOOD = {"CATEGORY": "햄버거", "BRAND": "맥도날드", "ITEM": "불고기 버거"}
SLOTS_FOOD2 = {"CATEGORY": "햄버거", "BRAND": "맥도날드", "ITEM": "트리플 치즈버거"}
SCREENS = [
    ("korail/k00_main", SLOTS_TRAIN, 0, "출발역선택"),
    ("korail/k02_dep_station", SLOTS_TRAIN, 0, "서울"),
    ("korail/k03_after_dep", SLOTS_TRAIN, 0, "도착역선택"),
    ("korail/k05_arr_major", SLOTS_TRAIN, 0, "부산 없음 → 초성/스크롤"),
    ("korail/k06_arr_b", SLOTS_TRAIN, 0, "부산"),
    ("korail/k07_both", SLOTS_TRAIN, 0, "가는날 열기(25일 → 26일)"),
    ("korail/k01_after_search", SLOTS_TRAIN, 0, "확인(안내 팝업)"),
    ("korail/k08_result", SLOTS_TRAIN, 9, "열차 줄(스크린숏)"),
    ("korail/k10_date", SLOTS_TRAIN, 0, "11월 26일 (목)"),
    ("baemin/b00_home", SLOTS_FOOD, 0, "팝업 닫기(숨은 팝업) / 패스트푸드"),
    ("baemin/b02_list_scroll", SLOTS_FOOD, 1, "맥도날드 ○○점"),
    ("baemin/b04_store_menu", SLOTS_FOOD, 2, "불고기 버거 이름"),
    ("eats/e00_home", SLOTS_FOOD2, 0, "카테고리 줄 밀기"),
    ("eats/e02_cat3", SLOTS_FOOD2, 0, "버거"),
    ("eats/e03_burger", SLOTS_FOOD2, 1, "맥도날드 칩"),
    ("eats/e06_menu", SLOTS_FOOD2, 3, "트리플 치즈버거 이름"),
    ("coupang/c01_detail", {}, 0, "STOP"),
    ("nmap/n00_home", {}, 0, "나중에 할게요"),
    ("youtube/y02_player", {}, 0, "WAIT"),
    ("bustago/t03", {}, 0, "확인(알림)"),
    ("bustago/t08_next_day", {}, 0, "결과 없음 안내"),
]


def cached_ai(name):
    from eval_v2 import DATA
    p = os.path.join(DATA, "eval_v2_results.jsonl")
    for l in open(p, encoding="utf-8"):
        r = json.loads(l)
        if r["case"] == name and r["method"] == "img_haiku" and r["rep"] == 0:
            return r["out"]
    return None


def main():
    rows, layer_count = [], {"규칙": 0, "앱 지식": 0, "AI": 0, "못 풂": 0}
    for name, slots, step, expect in SCREENS:
        ns = nodes_of(name)
        pkg = next((n["pkg"] for n in ns if n["pkg"]), "?")
        st, hint = screen_type(ns)
        if st in RULE_REPLY:
            act, say = RULE_REPLY[st]
            layer, res = "규칙", f"{st} → {act}"
        elif st in ("ONBOARDING", "ALERT", "POPUP"):
            btn = find(ns, hint, contains=True)
            layer, res = "규칙", f"{st} → TAP '{hint}'" + ("" if btn else " (버튼 못 찾음)")
        else:
            k = knowledge(pkg, ns, slots, step)
            if k:
                layer, res = "앱 지식", f"{k[0]} '{k[1]}' [{k[3]}]"
            else:
                o = cached_ai(name)
                if o:
                    fin, why = validate2(name, o)
                    layer, res = "AI", f"{o.get('action')} '{(o.get('target') or '')[:20]}' → 검사 {fin}"
                else:
                    layer, res = "못 풂", "AI 답 없음(이 화면은 AI 비교에 안 넣음)"
        layer_count[layer] += 1
        rows.append((name, expect, st, layer, res))
    out = ["# Guide 판단 순서 시뮬레이션 결과 (guide_sim.py)", "",
           "규칙 → 앱 지식 → AI(저장된 스크린숏+Haiku v2 답) → 검사 층. 새 AI 호출 없음.", "",
           "| 화면 | 기대 | 화면 종류 | 푼 단계 | 결과 |", "|---|---|---|---|---|"]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    n = len(rows)
    out += ["", f"**{n}화면 중 규칙 {layer_count['규칙']} · 앱 지식 {layer_count['앱 지식']} · AI {layer_count['AI']} · 못 풂 {layer_count['못 풂']}**",
            f"→ AI 호출이 필요한 화면 비율 {round(100 * (layer_count['AI'] + layer_count['못 풂']) / n)}% "
            f"(모든 화면을 스크린숏+Haiku로 물으면 {n}회 × $0.00037 ≈ ${n * 0.00037:.4f}, 이 순서면 ≈ ${(layer_count['AI'] + layer_count['못 풂']) * 0.00037:.4f})"]
    open(os.path.join(BASE, "guide_sim_result.md"), "w", encoding="utf-8").write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
