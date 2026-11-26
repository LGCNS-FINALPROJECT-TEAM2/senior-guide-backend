"""
brain.py AI 판단 평가 (API 키 필요, 폰 없음): regress.py의 「화면 → 규칙이 고른 행동」을 정답 후보로 두고 AI가 고른 것과 비교
python -I brain_eval.py          결과: brain_eval_result.md (같음 / 다름 — 다름은 사람이 보고 '그것도 맞음'인지 판단 → 골든셋)
화면 기억 · 경험 없이(빈 learn) 처음 보는 상태로 잼
"""
import os, sys, tempfile, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["GUIDE_LEARN"] = tempfile.mkdtemp(prefix="brain_eval_")
import warnings; warnings.filterwarnings("ignore")
import eval_v2, regress
import brain as B

GOALS = {"com.korail.talk": "기차표 조회(예매는 어르신이 직접)", "com.sampleapp": "배달 음식 메뉴 고르기(담기 · 주문은 어르신이 직접)",
         "com.coupang.mobile.eats": "배달 음식 메뉴 고르기(담기 · 주문은 어르신이 직접)"}
NAMES = {"DEPARTURE": "출발", "ARRIVAL": "도착", "DATE": "날짜", "COUNT": "인원", "PAX": "인원", "CATEGORY": "종류", "BRAND": "브랜드", "ITEM": "메뉴"}


def goal_of(pkg, slots, done):
    s = ", ".join(f"{NAMES.get(k, k)} {v}" for k, v in slots.items() if k != "DATE_SHORT")
    g = f"{GOALS.get(pkg, '')} — {s}"
    if done:
        g += " / 이미 끝낸 칸: " + ", ".join(NAMES.get(d, d) for d in done)
    return g


def main():
    rows, same, diff, t0 = [], 0, 0, time.time()
    for name, slots, done, exp in regress.CASES:
        if not isinstance(exp, tuple):
            continue  # 울타리 · 빠른 길 화면은 brain_regress.py에서
        ns = eval_v2.nodes_of(name)
        pkg = next((n["pkg"] for n in ns if n["pkg"]), "?")
        if B.guard(ns, pkg):
            continue
        B.reset()
        goal = goal_of(pkg, slots, done)
        t1 = time.time()
        d = B.decide("eval", ns, slots, goal)
        sec = time.time() - t1
        got = (d["action"], d.get("pick_text") or d.get("label") or "")
        import re as _re
        want = (_re.search(r"'([^']+)'", exp[1]) or [None, exp[1]])[1]  # 「초성 탭 'ㅂ'」 → ㅂ
        good = got[0] == exp[0] and want.replace(" ", "") in got[1].replace(" ", "")
        if exp[0] in ("SCROLL", "ASK") and got[0] == exp[0]:
            good = True  # 규칙 글자는 「찾는 것」, AI 글자는 「밀기(방향)」 → 행동이 같으면 같음
        elif exp[0] == "TAP" and "초성" in exp[1] and got[0] == "SCROLL":
            good = "비슷(밀기)"
        same += good is True; diff += good is not True
        p = d.get("plan") or {}
        rows.append((name, f"{exp[0]} {exp[1]}", f"{got[0]} {got[1][:24]}", "✅" if good is True else ("🟡" if good else "❌"),
                     f"{sec:.1f}s", (p.get("why") or "")[:60], (p.get("expect_next") or "")[:40]))
        print(rows[-1][3], name.ljust(24), "| 규칙", rows[-1][1], "| AI", rows[-1][2], "|", rows[-1][4], "|", rows[-1][5])
    conf = f"effort {B.EFFORT} · 생각 {'켬' if B.THINK else '끔'} · 답 {'긴 답(VERBOSE)' if B.VERBOSE else '짧은 답'}"
    out = ["# brain.py AI 판단 평가 (brain_eval.py)", "", "정답 = 규칙 · 앱 지식 표가 고른 행동. 처음 보는 상태(화면 기억 · 경험 없음), Haiku 글자 판단, JSON 스키마 강제.",
           f"설정: {conf}", "",
           "| 화면 | 규칙 | AI | 같음 | 시간 | AI 이유 | AI 예측(다음 화면) |", "|---|---|---|---|---|---|---|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    out += ["", f"**{same}/{same + diff} 같음**, 화면당 평균 {(time.time() - t0) / max(1, len(rows)):.1f}초"]
    tag = os.environ.get("GUIDE_EVAL_TAG", "")
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"brain_eval_result{'_' + tag if tag else ''}.md"), "w", encoding="utf-8").write("\n".join(out))
    print(f"\n{same}/{same + diff} 같음 | {conf} | 화면당 평균 {(time.time() - t0) / max(1, len(rows)):.1f}초")


if __name__ == "__main__":
    main()
