"""시나리오 문장들을 실제 폰에서 차례로: guide_live를 문장마다 돌리고 기록 · 마지막 화면을 runs/에 저장 (11/25)
python scenario_runs.py korail      (PHONE_DEV · PHONE_UNTIL 필요, 누르기는 phone.py 안전 검사 경유)"""
import json, os, subprocess, sys, time, shutil
sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import phone

SETS = {
    "korail": [
        "내일 대전 가는 기차표 좀 끊어 줘",
        "서울에서 부산 가는 기차 내일 아침 9시쯤",
        "케이티엑스 부싼 가는 거 내일",
        "서울서 대구 가는 기차 우리 영감이랑 둘이 낼모레",
        "다음 주 금요일에 강릉 가는 기차",
        "거시기 그 기차 그거 예약하는 거 있잖어 경주",
        "대전 가는 기차, 아 아니다 대전 말고 대구",
        "기차표 취소해줘",
        "부산 가고 싶어",
    ],
    "baemin": [  # 담기 · 주문은 안전 도구가 막음. 메뉴 상세까지만
        "집으로 찜닭 하나 시켜 줘",
        "치킨 시켜 먹자",
        "맥도날드 불고기버거 하나 시켜줘",
        "저녁에 먹을 거 좀 시켜 줘",
    ],
}

app = sys.argv[1]
out_dir = os.path.join(BASE, "runs", app); os.makedirs(out_dir, exist_ok=True)
summary = []
for i, utt in enumerate(SETS[app]):
    phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide")
    subprocess.run([sys.executable, "-I", os.path.join(BASE, "phone.py"), "launch", app], capture_output=True)
    env = dict(os.environ, GUIDE_UTT=utt, GUIDE_YES="1", GUIDE_PAUSE="1.5", PYTHONIOENCODING="utf-8")
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, os.path.join(BASE, "guide_live.py"), app, "14"], env=env, capture_output=True, timeout=240)
        log = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        log = (e.stdout or b"").decode("utf-8", "replace") + "\n[시간 초과 240초]"
    sec = round(time.time() - t0)
    open(os.path.join(out_dir, f"{i:02d}.txt"), "w", encoding="utf-8").write(utt + "\n\n" + log)
    png = os.path.join(out_dir, f"{i:02d}_end.png")
    open(png, "wb").write(phone.adb("exec-out", "screencap", "-p", binary=True))
    taps = log.count("누름:"); asks = log.count("되묻기"); ai_calls = log.count("[claude-")
    end = [l for l in log.splitlines() if l.startswith(("멈춤", "되묻기 필요", "읽어 주기", "캡처 안 함", "안전 도구", "Traceback", "[시간 초과", "밀기"))]
    row = dict(i=i, utt=utt, sec=sec, taps=taps, asks=asks, ai=ai_calls, end=end[-1] if end else "(끝 표시 없음)")
    summary.append(row); print(json.dumps(row, ensure_ascii=False))
    time.sleep(2)
json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
phone.adb("shell", "am broadcast -a com.edu.guide.STOP -p com.edu.guide")
