"""/v1/guide/intent 시험: 어르신 말 → taskType · slots · missing (Haiku). 결과 intent_results.jsonl
칸 이름은 질문_메모 Q15 초안 + 밤 작업 제안(TRAVEL · MODE)"""
import json, os, re, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai

WEEK = "월화수목금토일"


def sys_prompt(today=None):
    """11/27 폰 시험: 「오늘은 2026-11-25」가 글자로 박혀 있어 「내일」이 늘 11/26(지난 날짜)이 됨 → 실행하는 날 기준으로.
    GUIDE_TODAY=2026-11-25 처럼 주면 그 날로(시험 재현용)"""
    t = today or (datetime.date.fromisoformat(os.environ["GUIDE_TODAY"]) if os.environ.get("GUIDE_TODAY") else datetime.date.today())
    nxt = (t + datetime.timedelta(days=1)).isoformat()
    return SYS_T.replace("{TODAY}", f"{t.isoformat()} {WEEK[t.weekday()]}요일").replace("{EX}", nxt)


SYS_T = ("너는 어르신 스마트폰 길잡이의 '말 해석기'야. 어르신 말에서 업무 종류와 칸을 뽑는다. 추측으로 채우지 말고, 말에 없으면 missing에 넣는다.\n"
          "업무 종류(taskType): BOOK_TRAIN(기차표) · BOOK_BUS(버스표) · TRAVEL(어디 가고 싶은데 수단을 안 정함) · ORDER_FOOD(배달) · SEND_PHOTO(사진 보내기) · WATCH(영상 보기) · UNSUPPORTED\n"
          "칸 이름: DEPARTURE · ARRIVAL · DATE · TIME · COUNT · MODE(TRAIN/BUS/ANY) · ITEM · BRAND · RECIPIENT · CONTENT · QUERY\n"
          "날짜는 '{EX}'처럼(오늘은 {TODAY}). 범위 날짜(주말 등)는 DATE에 'YYYY-MM-DD~YYYY-MM-DD'로, 시간은 '08:00' 또는 '오전'처럼. 업무마다 꼭 필요한 칸: BOOK_TRAIN/BOOK_BUS=DEPARTURE,ARRIVAL,DATE / TRAVEL=ARRIVAL,DATE,MODE / ORDER_FOOD=ITEM / SEND_PHOTO=RECIPIENT / WATCH=QUERY\n"
          "반드시 JSON 하나만: {\"taskType\":\"...\",\"slots\":{칸:값},\"missing\":[칸],\"say\":\"되물을 말 1문장(빠진 게 없으면 시작 안내)\"}")
ai.SYS = sys_prompt()

CASES = [  # (말, 기대 taskType, 기대 slots 일부, 기대 missing 일부)
    ("내일 아침에 부산 가는 기차 알아봐 줘", "BOOK_TRAIN", {"ARRIVAL": "부산", "DATE": "2026-11-26"}, ["DEPARTURE"]),
    ("서울역에서 대전 가는 기차표 모레 두 장", "BOOK_TRAIN", {"DEPARTURE": "서울", "ARRIVAL": "대전", "DATE": "2026-11-27", "COUNT": "2"}, []),
    ("부산 가고 싶어", "TRAVEL", {"ARRIVAL": "부산"}, ["DATE", "MODE"]),
    ("동서울에서 강릉 가는 버스 오늘 오후", "BOOK_BUS", {"DEPARTURE": "동서울", "ARRIVAL": "강릉", "DATE": "2026-11-25"}, []),
    ("햄버거 시켜 먹고 싶어", "ORDER_FOOD", {"ITEM": "햄버거"}, []),
    ("맥도날드 불고기버거 하나 시켜줘", "ORDER_FOOD", {"BRAND": "맥도날드", "ITEM": "불고기버거"}, []),
    ("아들한테 손주 사진 좀 보내줘", "SEND_PHOTO", {"RECIPIENT": "아들"}, []),
    ("사진 보내야 되는데", "SEND_PHOTO", {}, ["RECIPIENT"]),
    ("트로트 틀어줘", "WATCH", {"QUERY": "트로트"}, []),
    ("임영웅 노래 듣고 싶어", "WATCH", {"QUERY": "임영웅"}, []),
    ("은행에 돈 좀 보내줘", "UNSUPPORTED", {}, []),
    ("거시기 그 기차 그거 예약하는 거 있잖어 경주", "BOOK_TRAIN", {"ARRIVAL": "경주"}, ["DEPARTURE", "DATE"]),
]


HARD = [
    ("대전 가는 기차, 아 아니다 대전 말고 대구", "BOOK_TRAIN", {"ARRIVAL": "대구"}, ["DEPARTURE", "DATE"]),
    ("부산 가는데 기차 말고 버스로", "BOOK_BUS", {"ARRIVAL": "부산"}, ["DEPARTURE", "DATE"]),
    ("다음주 화요일에 광주 가는 버스", "BOOK_BUS", {"ARRIVAL": "광주", "DATE": "2026-12-01"}, ["DEPARTURE"]),
    ("이번 주말에 강릉 가고 싶은데", "TRAVEL", {"ARRIVAL": "강릉"}, ["MODE"]),
    ("케이티엑스 부싼 가는 거 내일", "BOOK_TRAIN", {"ARRIVAL": "부산", "DATE": "2026-11-26"}, ["DEPARTURE"]),
    ("서울서 대구 가는 기차 우리 영감이랑 둘이 낼모레", "BOOK_TRAIN", {"DEPARTURE": "서울", "ARRIVAL": "대구", "DATE": "2026-11-27", "COUNT": "2"}, []),
    ("짜장면 두 그릇이랑 탕수육", "ORDER_FOOD", {"ITEM": "짜장면"}, []),
    ("딸한테 사진 보내고 유튜브로 트로트도 틀어줘", "SEND_PHOTO", {"RECIPIENT": "딸"}, []),
    ("어제 보낸 사진 다시 보내", "SEND_PHOTO", {}, ["RECIPIENT"]),
    ("기차표 취소해줘", "UNSUPPORTED", {}, []),
]


def norm(v):
    return re.sub(r"[\s역]", "", str(v)).replace("개", "").replace("장", "").replace("명", "")


def main():
    ai.SYS = sys_prompt(datetime.date(2026, 11, 25))  # CASES 정답이 11/25 기준
    out_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intent_results.jsonl")
    score = {"type": 0, "slots": 0, "missing": 0, "invented": 0}
    cases = HARD if "--hard" in sys.argv else CASES
    for utt, et, es, em in cases:
        txt = ai.call(ai.HAIKU, f"어르신 말: \"{utt}\"", "intent")
        try:
            o = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        except Exception:
            o = {}
        sl = o.get("slots") or {}
        t_ok = o.get("taskType") == et
        s_ok = all(k in sl and norm(es[k]) in norm(sl[k]) for k in es)
        m_ok = all(k in (o.get("missing") or []) for k in em)
        # 지어낸 칸: 말에 없는 출발역 · 날짜를 채움
        invented = [k for k in ("DEPARTURE", "DATE", "RECIPIENT") if k in sl and k not in es and sl[k] not in (None, "", "null")]
        score["type"] += t_ok; score["slots"] += s_ok; score["missing"] += m_ok; score["invented"] += bool(invented)
        print(("✅" if t_ok and s_ok and m_ok and not invented else "❌"), utt, "→", o.get("taskType"), sl, "missing", o.get("missing"),
              ("| 지어냄 " + str(invented)) if invented else "", "|", o.get("say", "")[:40])
        with open(out_p, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(utt=utt, expect=[et, es, em], out=o, invented=invented), ensure_ascii=False) + "\n")
    n = len(cases)
    print(f"\n업무 종류 {score['type']}/{n} · 칸 값 {score['slots']}/{n} · 빠진 칸 짚기 {score['missing']}/{n} · 지어낸 칸 있음 {score['invented']}/{n}")


if __name__ == "__main__":
    main()
