"""시나리오 요청 문장 → 말 해석(/intent)만 돌려 되묻기 · 칸을 표로 (폰 · 앱 안 씀, 11/25)"""
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai, intent_test  # intent_test가 ai.SYS를 말 해석용으로 맞춤
SETS = {
    "s1_kakao": ["민지한테 아까 찍은 사진 두 장 카톡으로 보내줘", "손녀한테 이 사진 좀 보내 줘", "우리 민지 카톡에 꽃 사진 두 개 넣어 줘",
                 "방금 찍은 거 민지한테 보내고 싶은데 어떻게 해?", "사진 두 장 손녀 카톡방에 좀 올려 줘", "어제 찍은 사진 민지 보여 주게 보내 줘",
                 "카톡으로 손녀딸한테 사진 보내는 거 좀 해 줘", "이거랑 이거 민지한테 보내 줘", "그 사진 애한테 좀 보내 봐", "손녀가 사진 보내 달라는데 좀 해 줘"],
    "s2_baemin": ["집으로 찜닭 하나 시켜 줘", "치킨 시켜 먹자", "짜장면 두 그릇이랑 탕수육", "저녁에 먹을 거 좀 시켜 줘",
                  "아까 먹은 그 집 또 시켜 줘", "회사로 커피 두 잔"],
}
out = {}
for name, utts in SETS.items():
    rows = []
    for u in utts:
        txt = ai.call(ai.HAIKU, f"어르신 말: \"{u}\"", f"batch-intent:{name}")
        try:
            o = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        except Exception:
            o = {"error": txt[:200]}
        rows.append({"utt": u, **o})
    out[name] = rows
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs", "intent_batch.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for name, rows in out.items():
    print("==", name)
    for r in rows:
        print(f"- {r['utt']} → {r.get('taskType')} {json.dumps(r.get('slots'), ensure_ascii=False)} missing={r.get('missing')}")
