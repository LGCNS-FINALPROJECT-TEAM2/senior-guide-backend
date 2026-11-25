"""같은 화면을 가만히 두고 여러 번 읽어 지문이 얼마나 흔들리는지 (읽기만)"""
import hashlib, json, re, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "."); import phone
app, n, gap = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
def grid(b): return tuple(round(v / 40) for v in b)  # 40px 격자로 반올림
res = []
for i in range(n):
    _, ns = phone.dump()
    full = hashlib.md5(json.dumps([(phone.label(x), x["b"]) for x in ns if phone.label(x)], ensure_ascii=False).encode()).hexdigest()[:6]
    nodig = hashlib.md5(json.dumps([(re.sub(r"\d", "#", phone.label(x)), x["b"]) for x in ns if phone.label(x)], ensure_ascii=False).encode()).hexdigest()[:6]
    struct = hashlib.md5(json.dumps(sorted(grid(x["b"]) for x in ns if x["click"])).encode()).hexdigest()[:6]
    res.append((full, nodig, struct)); time.sleep(gap)
for k, name in enumerate(["글자 전체", "숫자 뺀 글자", "누름 칸 구조(40px 격자)"]):
    print(f"{app}: {name} → 서로 다른 지문 {len(set(r[k] for r in res))}개 / {n}번")
