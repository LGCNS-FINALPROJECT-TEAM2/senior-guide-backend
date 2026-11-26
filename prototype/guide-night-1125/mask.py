"""스크린숏 가리기 한 곳으로 모음 (11/25 검수)
- 전에는 guide_unknown만 가리고, live_ai_step(12/12 시연 뼈대의 AI 단계)은 원본 스크린숏을 그대로 AI로 보냈음
- 패턴도 「○○구 ○○로 12」 · 빌딩/아파트 이름뿐이라 전화번호 · 동/호 · 지번 · 카드번호 · 이메일 · 「○○님」이 샘
- 접근성 글자 기반이라 시트 뒤로 비친 글자는 여전히 못 잡음 → 서비스에선 폰 안 글자 인식(ML Kit)으로 (설계검토 9절)
"""
import re, sys
sys.stdout.reconfigure(encoding="utf-8")
from PIL import ImageDraw

PRIV = re.compile("|".join([
    r"우리집[^']*",
    r"[가-힣]+(시|도|구|군) ?[가-힣0-9]+(로|길) ?[0-9-]+",            # 도로명
    r"[가-힣0-9]+(동|읍|면|리) ?\d+(-\d+)?(번지)?",                   # 지번
    r"\d+ ?동 ?\d+ ?호|\d{2,4} ?호",                                 # 동 · 호
    r"[가-힣A-Za-z0-9]+(빌딩|타워|아파트|빌라|오피스텔|맨션|하이츠|주택)",
    r"01[016789][- .]?\d{3,4}[- .]?\d{4}|0\d{1,2}[- .]\d{3,4}[- .]\d{4}",  # 전화
    r"\d{4}[- ]?\d{2,4}[-* ]+[\d*]{4}[- ]?[\d*]{3,4}",               # 카드 · 계좌처럼 긴 번호
    r"[\w.+-]+@[\w-]+\.[\w.]+",                                      # 이메일
    r"[가-힣]{2,4} ?(님|고객님)\b",                                   # 「홍길동님」
]))

TOP_BAND = (0, 60, None, 330)  # 처음 보는 앱: 맨 위 주소 줄 자리 기본 가림


def label(n):
    return ((n.get("text") or "") + " " + (n.get("desc") or "")).strip()


def mask_image(im, nodes, top_band=True):
    """PIL 이미지에 칠하고 가린 칸 수를 돌려줌"""
    d = ImageDraw.Draw(im)
    n_masked = 0
    if top_band:
        l, t, r, b = TOP_BAND
        d.rectangle((l, t, r or im.size[0], b), fill=(0, 0, 0)); n_masked += 1
    for n in nodes:
        if PRIV.search(label(n)):
            d.rectangle(n["b"], fill=(0, 0, 0)); n_masked += 1
    return n_masked


def mask_text(s):
    return PRIV.sub("[가림]", s or "")


if __name__ == "__main__":  # 패턴 자체 시험: python -I mask.py
    must = ["서울 강남구 테헤란로 123", "역삼동 123-45", "101동 1203호", "010-1234-5678", "02-123-4567",
            "1234-5678-****-1234", "abc@test.com", "홍길동님", "래미안아파트", "우리집 (기본)"]
    keep = ["열차 조회", "서울 → 대전", "KTX 001", "05:13", "53,900원", "어른 1명", "2026년 11월 27일", "치킨", "11월 26일"]
    bad = [x for x in must if not PRIV.search(x)] + [x for x in keep if PRIV.search(x)]
    print("가려야 하는데 못 가림 / 가리면 안 되는데 가림:", bad or "없음")
    raise SystemExit(1 if bad else 0)
