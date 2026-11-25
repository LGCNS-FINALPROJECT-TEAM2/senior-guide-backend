"""모은 화면으로 3가지 판단 방식 비교. 개인정보(주소 등)는 보내기 전에 가림. 결과: eval_results.jsonl"""
import io, json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "eval_results.jsonl")

# (화면, 목표, 정답 설명, 이미지에서 가릴 영역)
TOP = [(0, 60, 1080, 360)]  # 배달 앱 위 주소 줄
CASES = [
    ("korail/k00_main", "서울에서 부산 가는 기차표 알아보고 싶어", "출발역선택", []),
    ("korail/k02_dep_station", "서울에서 부산 가는 기차표 알아보고 싶어", "서울(목록 줄)", []),
    ("korail/k06_arr_b", "서울에서 부산 가는 기차표 알아보고 싶어", "부산(맨 아래 줄)", []),
    ("korail/k08_result", "서울에서 부산 가는 기차 중 가장 빨리 출발하는 KTX", "첫 열차 줄(05:13 KTX 001), 글자 방식은 unsure여야 정상", []),
    ("korail/k10_date", "내일 부산 가는 기차 알아보고 싶어 (오늘은 11월 25일)", "11월 26일 (목)", []),
    ("baemin/b00_home", "햄버거 시켜 먹고 싶어", "패스트푸드", TOP),
    ("baemin/b02_list_scroll", "맥도날드 햄버거 시켜 먹고 싶어", "맥도날드 ○○점 카드(광고 가게 아님)", TOP),
    ("baemin/b04_store_menu", "불고기버거 하나 먹고 싶어", "불고기 버거 메뉴 이름(＋ 장바구니 담기 아님) 또는 stop", []),
    ("eats/e00_home", "햄버거 시켜 먹고 싶어", "버거 카테고리가 화면에 없음 → 카테고리 줄 옆으로 밀기 / unsure", TOP),
    ("eats/e06_menu", "트리플 치즈버거 세트 먹고 싶어", "트리플 치즈버거 라지 세트 메뉴 이름(카트 아이콘 아님)", []),
    ("coupang/c01_detail", "치약 사고 싶어", "stop=true (구매하기 앞)", []),
    ("nmap/n04_route_tomorrow", "내일 아침 기차로 부산 가는 제일 빠른 방법", "첫 경로(2시간 20분, 서울역→부산역), 예매는 stop", []),
    ("youtube/y02_player", "트로트 노래 듣고 싶어", "광고 중 → 기다리기 / 광고주 페이지 방문 누르면 안 됨", []),
    ("bustago/t08_next_day", "동서울에서 해운대 가는 버스 알아보고 싶어", "결과 없음 → 안내(다른 날 · 다른 수단), 누를 것 없음 또는 다음날 조회", []),
]
ADDR = re.compile(r"(우리집[^']*|[가-힣]+구 [가-힣0-9]+(로|길)[0-9가-힣 ]*\d+)")


def mask_text(t):
    from mask import PRIV  # 11/25 검수: 공용 패턴으로
    return PRIV.sub("[주소]", t)


def main():
    done = set()
    if os.path.exists(OUT):
        done = {(json.loads(l)["case"], json.loads(l)["method"]) for l in open(OUT, encoding="utf-8")}
    for name, goal, answer, rects in CASES:
        txt = os.path.join(BASE, name + ".txt")
        png = os.path.join(BASE, name + ".png")
        mt = os.path.join(BASE, "masked", name.replace("/", "_") + ".txt")
        mp = os.path.join(BASE, "masked", name.replace("/", "_") + ".png")
        os.makedirs(os.path.dirname(mt), exist_ok=True)
        open(mt, "w", encoding="utf-8").write(mask_text(open(txt, encoding="utf-8").read()))
        im = Image.open(png).convert("RGB"); d = ImageDraw.Draw(im)
        for r in rects:
            d.rectangle(r, fill=(0, 0, 0))
        im.save(mp)
        for method in ("text_haiku", "img_haiku", "img_sonnet"):
            if (name, method) in done:
                continue
            print(f"\n### {name} · {method}\n목표: {goal}\n정답: {answer}")
            if method == "text_haiku":
                body = open(mt, encoding="utf-8").read()
                out = ai.call(ai.HAIKU, f"목표: {goal}\n\n화면 글자 목록(C=누를 수 있음, [l,t,r,b]):\n{body[:12000]}", name + ":text")
            else:
                import base64
                model = ai.HAIKU if method == "img_haiku" else ai.SONNET
                im2 = Image.open(mp); w, h = im2.size
                im2 = im2.resize((540, int(h * 540 / w)))
                buf = io.BytesIO(); im2.save(buf, "JPEG", quality=80)
                b64 = base64.b64encode(buf.getvalue()).decode()
                out = ai.call(model, [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                                      {"type": "text", "text": f"목표: {goal}\n화면은 원래 {w}x{h}인데 540 폭으로 줄였어. bounds는 원래 크기 좌표로."}],
                              name + ":" + method)
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(case=name, method=method, goal=goal, answer=answer, out=out), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
