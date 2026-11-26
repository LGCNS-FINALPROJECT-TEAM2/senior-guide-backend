"""개선판 시험: 프롬프트 v2(action 종류 · 금지 아이콘 · 팝업 먼저) + 검사 층(validator). 방식마다 2번.
결과: eval_v2_results.jsonl"""
import base64, io, json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
import ai
from eval_night import CASES, TOP
import phone

BASE = os.path.dirname(os.path.abspath(__file__))
# 시험 화면 위치: 저장소에선 개인정보를 지운 fixtures/, 김우석 PC에선 원본 폴더
DATA = os.environ.get("GUIDE_DATA") or (os.path.join(BASE, "fixtures") if os.path.isdir(os.path.join(BASE, "fixtures")) else BASE)
OUT = os.path.join(BASE, "eval_v2_results.jsonl")
REPEAT = 2

SYS2 = ("너는 어르신 스마트폰 길잡이의 판단기야. 화면과 목표를 보고 '다음 한 수'를 고른다. 너는 누르지 않고, 어르신께 안내만 한다.\n"
        "규칙:\n"
        "1) 화면을 가리는 팝업 · 광고 창이 있으면 그걸 먼저 닫는다(닫기 · X · 오늘 그만 보기 · 나중에).\n"
        "2) 목표에 맞는 버튼이 화면에 안 보이면 action=SCROLL(방향과 밀 영역)로 찾는다. 검색창 글자 입력은 마지막 수단.\n"
        "3) 영상 광고가 재생 중이면 action=WAIT ('광고 건너뛰기'가 보이면 그걸 TAP).\n"
        "4) 결제 · 구매 · 주문하기 · 예매 · 장바구니 담기 · 카트 아이콘 · ＋ 담기 아이콘 · 구독 · 가입 · 무료체험 · 동의 · 로그인 · 전송 버튼은 절대 target으로 고르지 않는다. "
        "목표가 그 단계에 왔으면 action=STOP.\n"
        "5) 메뉴 · 상품을 고를 땐 '이름 글자'를 고른다(옆의 ＋ · 카트 아이콘 아님).\n"
        "6) 사진 · 좌석처럼 어르신이 직접 골라야 하면 action=PICK_BY_USER.\n"
        "7) 화면 정보가 부족하면 unsure=true.\n"
        "반드시 JSON 하나만: {\"screen\":\"화면 종류\",\"action\":\"TAP|SCROLL|WAIT|BACK|STOP|PICK_BY_USER\","
        "\"target\":\"누를 것의 글자(TAP일 때)\",\"bounds\":[l,t,r,b] 또는 null,\"scroll\":{\"dir\":\"next|prev|left|right\",\"area\":[l,t,r,b]} 또는 null (next=아래 내용 더 보기, prev=위 내용, left/right=가로 줄에서 오른쪽 · 왼쪽 내용 더 보기),"
        "\"say\":\"어르신께 할 말 1문장\",\"unsure\":false}")
EXTRA_MASK = {"eats/e00_home": [(0, 560, 1080, 680)]}
from mask import PRIV  # 11/25 검수: 패턴을 mask.py 한 곳으로 (전화 · 동호 · 지번 · 이름 추가)


def nodes_of(name):
    x = open(os.path.join(DATA, name + ".xml"), encoding="utf-8").read()
    ns = []
    for s in re.findall(r"<node [^>]*>", x):
        g = lambda k: (re.search(" " + k + r'="([^"]*)"', s) or [None, ""])[1]
        b = list(map(int, re.findall(r"\d+", g("bounds"))))
        if len(b) == 4:
            ns.append(dict(text=g("text").replace("&#10;", " "), desc=g("content-desc"), click=g("clickable") == "true",
                           pkg=g("package"), b=b, edit=g("class").endswith("EditText"),
                           rid=g("resource-id"), cls=g("class").rsplit(".", 1)[-1],  # 11/25 밤: 구조 지문용
                           sel=g("selected") == "true"))  # 11/27: 지금 고른 탭 · 칩
    return ns


def validate(name, o):
    """검사 층: AI 답을 화면 글자로 다시 확인. 반환 (최종 action, 이유)"""
    act = (o.get("action") or "").upper()
    if act != "TAP":
        return act, "TAP 아님 — 그대로"
    ns = nodes_of(name)
    t = (o.get("target") or "").strip()
    for w in phone.BANNED_CARD + ["장바구니", "담기", "구매", "결제", "구독"]:
        if w in t:
            return "STOP", f"target 글자에 금지 단어 '{w}'"
    b = o.get("bounds")
    if not b or len(b) != 4:
        return "UNSURE", "bounds 없음 — 폰이 글자로 다시 찾아야"
    cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
    hits = [n for n in ns if n["click"] and n["b"][0] <= cx <= n["b"][2] and n["b"][1] <= cy <= n["b"][3]]
    if not hits:
        return "UNSURE", "그 자리에 누를 칸 없음"
    btn = min(hits, key=lambda n: (n["b"][2] - n["b"][0]) * (n["b"][3] - n["b"][1]))
    big = (btn["b"][2] - btn["b"][0]) >= 300 and (btn["b"][3] - btn["b"][1]) >= 150
    why = phone.check(btn, ns, card=big)
    if why and why.startswith("06:30"):
        why = None
    if why and why.startswith("허용 앱"):
        why = None
    if why == "글자 없는 버튼" and big:
        why = None  # 큰 카드(코레일 열차 줄)는 스크린숏 판단 허용
    if why:
        return "BLOCK", f"그 자리 칸: {why} ('{phone.all_text(btn, ns)[:30]}')"
    return "TAP", f"통과 ('{phone.all_text(btn, ns)[:30]}')"


def main():
    done = {}
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8"):
            r = json.loads(l); done[(r["case"], r["method"], r["rep"])] = 1
    ai.SYS = SYS2
    for name, goal, answer, rects in CASES:
        rects = rects + EXTRA_MASK.get(name, [])
        mt = os.path.join(BASE, "masked", name.replace("/", "_") + ".v2.txt")
        mp = os.path.join(BASE, "masked", name.replace("/", "_") + ".v2.png")
        open(mt, "w", encoding="utf-8").write(PRIV.sub("[주소]", open(os.path.join(BASE, name + ".txt"), encoding="utf-8").read()))
        im = Image.open(os.path.join(BASE, name + ".png")).convert("RGB"); d = ImageDraw.Draw(im)
        for r in rects:
            d.rectangle(r, fill=(0, 0, 0))
        im.save(mp)
        for rep in range(REPEAT):
            for method in ("text_haiku", "img_haiku", "img_sonnet"):
                if (name, method, rep) in done:
                    continue
                print(f"\n### {name} · {method} · {rep}\n정답: {answer}")
                try:
                    if method == "text_haiku":
                        out = ai.call(ai.HAIKU, f"목표: {goal}\n\n화면 글자 목록(C=누를 수 있음, [l,t,r,b]):\n{open(mt, encoding='utf-8').read()[:12000]}", name + ":v2text")
                    else:
                        model = ai.HAIKU if method == "img_haiku" else ai.SONNET
                        im2 = Image.open(mp); w, h = im2.size
                        im2 = im2.resize((540, int(h * 540 / w)))
                        buf = io.BytesIO(); im2.save(buf, "JPEG", quality=80)
                        out = ai.call(model, [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                                           "data": base64.b64encode(buf.getvalue()).decode()}},
                                              {"type": "text", "text": f"목표: {goal}\n화면은 원래 {w}x{h}인데 540 폭으로 줄였어. bounds는 원래 크기 좌표로."}],
                                      name + ":v2" + method)
                except SystemExit:
                    print("비용 상한 — 중단"); return
                try:
                    o = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
                    fin, why = validate(name, o)
                except Exception as e:
                    o, fin, why = {}, "PARSE_FAIL", str(e)[:60]
                print("검사 층 →", fin, "|", why)
                with open(OUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(dict(case=name, method=method, rep=rep, answer=answer, out=o, final=fin, why=why),
                                       ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
