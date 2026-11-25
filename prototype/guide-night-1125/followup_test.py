"""되묻기 뒤 짧은 대답을 세션과 이어 붙이기 (/intent 두 번째 호출). Haiku"""
import json, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "."); import ai, intent_test  # SYS 재사용
ai.SYS = intent_test.ai.SYS + ("\n세션이 주어지면: 이전 칸은 그대로 두고, 이번 대답으로 채우거나 고친다. 대답이 '응/네'처럼 내용이 없으면 칸을 채우지 말고 다시 묻는다. "
                                 "'몰라'면 그 칸을 missing에 두고 다른 방법(예: 가까운 역)을 제안한다. 이번 대답이 이전 칸을 바꾸면 바꾼다.")
BASE = {"taskType": "BOOK_TRAIN", "slots": {"ARRIVAL": "부산", "DATE": "2026-11-26"}, "asked": "DEPARTURE", "lastSay": "어디에서 출발하시나요?"}
CASES = [
    ("서울역이요", {"DEPARTURE": "서울", "ARRIVAL": "부산", "DATE": "2026-11-26"}, []),
    ("응", {"ARRIVAL": "부산", "DATE": "2026-11-26"}, ["DEPARTURE"]),
    ("몰라 집 근처에서", {"ARRIVAL": "부산"}, ["DEPARTURE"]),
    ("아 부산 말고 대구로 갈래 서울에서", {"DEPARTURE": "서울", "ARRIVAL": "대구", "DATE": "2026-11-26"}, []),
    ("수원", {"DEPARTURE": "수원", "ARRIVAL": "부산"}, []),
    ("내일 말고 모레", {"ARRIVAL": "부산", "DATE": "2026-11-27"}, ["DEPARTURE"]),
]
ok = 0
for ans, es, em in CASES:
    txt = ai.call(ai.HAIKU, f"세션: {json.dumps(BASE, ensure_ascii=False)}\n어르신 대답: \"{ans}\"", "followup")
    try:
        o = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
    except Exception:
        o = {}
    sl = o.get("slots") or {}
    good = all(k in sl and intent_test.norm(es[k]) in intent_test.norm(sl[k]) for k in es) and all(k in (o.get("missing") or []) for k in em) \
        and (o.get("taskType") == BASE["taskType"])
    lost = [k for k in ("ARRIVAL", "DATE") if k in BASE["slots"] and k not in sl]
    ok += good and not lost
    print("✅" if good and not lost else "❌", ans, "→", sl, "missing", o.get("missing"), ("| 잃은 칸 " + str(lost)) if lost else "", "|", (o.get("say") or "")[:45])
print(f"{ok}/{len(CASES)}")
