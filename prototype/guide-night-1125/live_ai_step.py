"""실제 폰: 지금 화면 스크린숏 + Haiku(v2 프롬프트) → 검사 층 → 길잡이 앱 SHOW. 누르지 않음."""
import base64, io, json, os, re, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
import ai, phone, eval_v2, validate2, mask
import guide_sim as G
from guide_live import show

goal, tag = sys.argv[1], sys.argv[2]
x, ns = phone.dump()
why_stop = G.capture_block_reason(ns, phone.focus())  # 캡처 · 저장 · AI 호출 전에 (11/25 우진님 리뷰)
if why_stop:
    print("캡처 안 함:", why_stop)
    show(None, "이 화면은 직접 확인해 주세요. 제가 화면을 보지 않을게요.")
    sys.exit(0)
d = os.path.join(eval_v2.BASE, "live"); png = os.path.join(d, tag + ".png")
raw = phone.adb("exec-out", "screencap", "-p", binary=True); open(png, "wb").write(raw)
open(os.path.join(d, tag + ".xml"), "w", encoding="utf-8").write(x)
im = Image.open(png).convert("RGB"); w, h = im.size
masked = mask.mask_image(im, ns)  # 11/25 검수: 전에는 원본을 그대로 AI로 보냄
im.save(os.path.join(d, tag + "_masked.png"))
im2 = im.resize((540, int(h * 540 / w))); buf = io.BytesIO(); im2.save(buf, "JPEG", quality=80)
ai.SYS = eval_v2.SYS2
t0 = time.time()
out = ai.call(ai.HAIKU, [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
                         {"type": "text", "text": f"목표: {goal}\n화면은 원래 {w}x{h}인데 540 폭으로 줄였어. bounds는 원래 크기 좌표로."}], "live:" + tag)
o = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
validate2.nodes_of = lambda name: ns  # 11/25 검수: eval_v2 쪽을 바꾸면 validate2가 import한 이름엔 안 먹어서 'live.xml'을 찾다 죽음(TAP 답일 때)
fin, why = validate2.validate2("live", o)
print(f"가림 {masked}칸 | 검사 층:", fin, why, f"| 화면→표시 {time.time()-t0:.1f}초")
if fin in ("TAP", "TAP_SCREEN_ONLY"):
    show(validate2.shown_bounds(o), o.get("say", ""))  # 위치 확인 못 한 닫기는 강조 없이 말만
    time.sleep(1.2)
    open(os.path.join(d, tag + "_shown.png"), "wb").write(phone.adb("exec-out", "screencap", "-p", binary=True))
