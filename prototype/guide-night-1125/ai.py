"""
밤 작업용 AI 판단 시험 (비용 기록 · $5 상한).
python -I ai.py text  <txt파일> "<목표>"            글자 목록 + Haiku
python -I ai.py image <png파일> "<목표>" [sonnet|haiku]  스크린숏 + 모델
키는 Windows 사용자 환경 변수에서 읽음(출력 · 저장 안 함).
"""
import base64, datetime, io, json, os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
import anthropic
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
COST = os.path.join(BASE, "api_cost.jsonl")
LIMIT = 5.0
HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
PRICE = {HAIKU: (0.10, 0.50), SONNET: (2.00, 10.00)}  # $/100만 토큰 (live_guide.py와 같음)

SYS = ("너는 어르신 스마트폰 길잡이의 판단기야. 화면 정보와 목표를 보고 '다음에 누를 곳 하나'를 고른다. "
       "결제·주문·예매·전송·동의·로그인 버튼이면 stop=true. 사람이 직접 골라야 하면(사진, 좌석 등) pick_by_user=true. "
       "반드시 JSON 하나만: {\"screen\":\"화면 종류 한 줄\",\"target\":\"누를 것의 글자 또는 설명\","
       "\"bounds\":[l,t,r,b] 또는 null,\"say\":\"어르신께 할 말(쉬운 말 1문장)\",\"stop\":false,"
       "\"pick_by_user\":false,\"unsure\":false,\"read\":\"화면에서 읽은 핵심 정보(목록이면 3줄까지)\"}")


def key():
    k = os.environ.get("ANTHROPIC_API_KEY") or subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY','User')"],
        capture_output=True, text=True).stdout.strip()
    return k


def spent():
    if not os.path.exists(COST):
        return 0.0
    return sum(json.loads(l)["usd"] for l in open(COST, encoding="utf-8") if l.strip())


def call(model, content, tag):
    if spent() >= LIMIT:
        print(f"상한 ${LIMIT} 도달 — 호출 안 함"); sys.exit(2)
    c = anthropic.Anthropic(api_key=key())
    t = time.time()
    kw = dict(model=model, max_tokens=1024, system=SYS, messages=[{"role": "user", "content": content}],
              output_config={"effort": "low"})
    if model == SONNET:
        kw["thinking"] = {"type": "between_tools"}  # 생각 끄기 (live_guide.py와 같음)
    r = c.messages.create(**kw)
    dt = time.time() - t
    i, o = PRICE[model]
    usd = (r.usage.input_tokens * i + r.usage.output_tokens * o) / 1e6
    with open(COST, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(time=datetime.datetime.now().strftime("%H:%M:%S"), tag=tag, model=model,
                                inp=r.usage.input_tokens, out=r.usage.output_tokens, sec=round(dt, 1),
                                usd=round(usd, 5)), ensure_ascii=False) + "\n")
    txt = "".join(b.text for b in r.content if b.type == "text")
    print(f"[{model} · {dt:.1f}s · in {r.usage.input_tokens} out {r.usage.output_tokens} · ${usd:.4f} · 누적 ${spent():.3f}]")
    print(txt)
    return txt


def main():
    mode, path, goal = sys.argv[1], sys.argv[2], sys.argv[3]
    tag = os.path.basename(path)
    if mode == "text":
        body = open(path, encoding="utf-8").read()
        call(HAIKU, f"목표: {goal}\n\n화면 글자 목록(C=누를 수 있음, [l,t,r,b]):\n{body[:12000]}", tag)
    else:
        model = SONNET if (len(sys.argv) < 5 or sys.argv[4] == "sonnet") else HAIKU
        im = Image.open(path).convert("RGB")
        w, h = im.size
        im = im.resize((540, int(h * 540 / w)))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()
        call(model, [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                     {"type": "text", "text": f"목표: {goal}\n화면은 원래 {w}x{h}인데 540 폭으로 줄였어. bounds는 원래 크기 좌표로."}],
             tag + ":" + model)


if __name__ == "__main__":
    main()
