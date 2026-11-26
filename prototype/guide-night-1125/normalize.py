"""정규화 층 시제품: /intent 칸(말 표기) → 앱 지식 칸(앱 표기). Guide 서비스 안에 둘 층."""
import datetime, re
WEEK = "월화수목금토일"
FOOD_CAT = [("버거", "햄버거"), ("햄버거", "햄버거"), ("치킨", "치킨"), ("통닭", "치킨"), ("피자", "피자"), ("족발", "족발"),
            ("짜장", "중식"), ("짬뽕", "중식"), ("떡볶이", "분식"), ("김밥", "분식"),
            ("찜닭", "찜·탕"), ("아구찜", "찜·탕"), ("탕수육", "중식"), ("커피", "카페·디저트")]  # 11/25 시나리오 2 문장
STATION_ALIAS = {"서울역": "서울", "부산역": "부산", "대전역": "대전", "경주역": "경주", "용산역": "용산"}


def to_app(task, slots, pkg):
    out = {}
    for k, v in (slots or {}).items():
        v = str(v)
        if k in ("DEPARTURE", "ARRIVAL") and pkg == "com.korail.talk":
            out[k] = STATION_ALIAS.get(v, re.sub(r"역$", "", v))
        elif k == "DATE" and re.match(r"\d{4}-\d{2}-\d{2}", v):
            d = datetime.date.fromisoformat(v)
            out["DATE"] = f"{d.month}월 {d.day}일 ({WEEK[d.weekday()]})"
            out["DATE_SHORT"] = f"{d.month}월 {d.day}일"
        elif k == "ITEM" and task == "ORDER_FOOD":
            # 메뉴 이름 → 카테고리 (03:11: 「불고기버거」를 카테고리로 써서 첫 화면에서 못 찾음)
            cat = next((c for kw, c in FOOD_CAT if kw in v), v)
            out["CATEGORY"] = cat
            out["ITEM"] = v
        else:
            out[k] = v
    if task in ("BOOK_TRAIN", "BOOK_BUS") and "COUNT" in out and "PAX" not in out:
        out["PAX"] = f"{out.get('PAX_TYPE', '어른')}:{int(re.sub(r'\D', '', out['COUNT']) or 1)}"  # 어르신 프로필이 65세 이상이면 PAX_TYPE=경로 (프로필 연동은 미구현)
    if task == "ORDER_FOOD" and "CATEGORY" not in out and "ITEM" in out:
        out["CATEGORY"] = out["ITEM"]
    return out
