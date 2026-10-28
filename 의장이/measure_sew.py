# -*- coding: utf-8 -*-
"""
의장이(재봉틀) 창 위치 측정 도구 — 한 번만 하면 됨.

차례대로 안내하는 지점에 마우스를 올리고 F1 을 누르면, 그 지점이
'어느 창의 어디쯤(창 크기의 몇 %)'인지를 기록해서 match_layout.json 에 저장함.

auto_sew.py 는 이 파일을 보고 매번 창을 제목으로 찾아서 좌표를 계산하므로
  - 창을 어디로 옮겨도 다시 잴 필요 없음
  - 화면 배율이 다른 컴퓨터도 match_layout.json 을 그대로 복사해 쓰면 됨

■ 사용법
  1. 게임에서 직업 창(F2)과 제작 창(직업활동)을 띄워 둠
  2. cmd 에서:  py measure_sew.py
  3. 안내대로 마우스를 올리고 F1.  잘못 찍었으면 F2 로 그 지점 다시
  ESC = 중간에 그만두기 (저장 안 함)

  ※ 의장이 창(천)은 봇이 화면에서 알아서 찾으므로 보통은 안 잼.
    봇이 "천을 못 찾음" 이라고 할 때만, 다시 실행해서 3번 묶음(의장이 창)을 고르면 잼
"""

import os
import sys
import json
import time

try:
    import keyboard
    import pyautogui
    import pygetwindow as gw
except ImportError as e:
    print("[에러] 필요한 프로그램이 없습니다:", e)
    print("cmd 에서:  py -m pip install pyautogui keyboard pygetwindow")
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)

# 게임 창 제목 (띄어쓰기는 무시하고 비교)
TITLES = {"job": "직업", "craft": "제작", "card": "의장이"}     # card = 재봉틀 게임 창

# (기록 이름, 어느 창, 안내 문구)
STEPS = [
    ("job_act",         "job",   "직업 창의 [직업활동] 버튼 가운데"),
    ("slot1",           "craft", "제작 창 재료 슬롯 1번(맨 왼쪽 검은 칸) 가운데"),
    ("slot2",           "craft", "제작 창 재료 슬롯 2번 가운데"),
    ("cell_first",      "craft", "제작 창 인벤토리 첫 칸(왼쪽 위) 가운데"),
    ("cell_row1_last",  "craft", "제작 창 인벤토리 첫 줄 맨 오른쪽 칸 가운데"),
    ("cell_row5_first", "craft", "제작 창 인벤토리 맨 아래 줄(5번째 줄) 첫 칸 가운데"),
    ("start",           "craft", "제작 창 초록 [시작] 버튼 가운데"),
]
# 의장이 창(천) — 봇이 화면에서 자동으로 찾으므로 보통은 안 잼 (못 찾을 때만 3번 묶음으로)
CARD_STEPS = [
    ("fab_tl",          "card",  "의장이 창 회색 천의 왼쪽 위 모서리  ※ 재료를 넣고 시작을 눌러 의장이 창을 띄운 뒤"),
    ("fab_br",          "card",  "회색 천의 오른쪽 아래 모서리"),
    ("line",            "card",  "빨간 실선(바늘이 있는 가로줄) 위 아무 곳"),
]
ALL_STEPS = STEPS + CARD_STEPS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "match_layout.json")


def norm(t):
    return "".join(str(t).split())


def shown(w):
    try:
        return (w.visible and w.width > 0 and w.height > 0
                and not getattr(w, "isMinimized", False)
                and w.left > -10000 and w.top > -10000)
    except Exception:
        return False


def window_at(kind, x, y):
    """제목이 TITLES[kind] 이고 (x, y) 를 품은 떠 있는 창. 없으면 (None, 같은 제목 창 목록)."""
    want = norm(TITLES[kind])
    same = [w for w in gw.getAllWindows() if norm(w.title) == want and shown(w)]
    for w in same:
        if w.left <= x < w.left + w.width and w.top <= y < w.top + w.height:
            return w, same
    return None, same


def wait_key():
    """F1(기록) / F2(다시) / ESC(그만) 중 눌린 키를 반환."""
    while True:
        ev = keyboard.read_event(suppress=False)
        if ev.event_type != "down":
            continue
        if ev.name in ("f1", "f2", "esc"):
            while keyboard.is_pressed(ev.name):
                time.sleep(0.02)
            return ev.name


# 일부만 다시 잴 때 고르는 묶음 (STEPS 의 번호, 0부터)
GROUPS = [
    ("직업 창 [직업활동] 버튼", [0]),
    ("제작 창 (재료 슬롯 / 인벤토리 칸 / 시작 버튼)", [1, 2, 3, 4, 5, 6]),
    ("의장이 창 (천 / 빨간 실선) — 보통은 필요 없음. 봇이 천을 못 찾을 때만", [7, 8, 9]),
]


def choose_steps():
    """match_layout.json 이 있으면 전부/일부 중 고르게 함. (단계 목록, 기존 데이터 또는 None)"""
    if not os.path.exists(OUT):
        return STEPS, None
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        old["points"], old["sizes"]
    except Exception:
        return STEPS, None
    print("\n이미 잰 값(match_layout.json)이 있어요. 게임 업데이트로 바뀐 부분만 다시 잴 수 있어요.")
    for n, (label, _) in enumerate(GROUPS, 1):
        print(f"   {n}. {label}")
    ans = input("다시 잴 번호 (예: 3  또는  2,3)  /  전부 다시 재려면 그냥 엔터: ").strip()
    picks = sorted({int(t) for t in ans.replace(" ", ",").split(",") if t.isdigit()
                    and 1 <= int(t) <= len(GROUPS)})
    if not picks:
        return STEPS, None
    print("→ " + ", ".join(GROUPS[g - 1][0] for g in picks) + " 만 다시 잽니다 (나머지는 그대로)")
    return [ALL_STEPS[i] for g in picks for i in GROUPS[g - 1][1]], old


def main():
    print("=" * 60)
    print(" 의장이 창 위치 측정  (F1 = 기록, F2 = 직전 것 다시, ESC = 그만)")
    print(" 창 제목:", ", ".join(f"{k}='{v}'" for k, v in TITLES.items()))
    print("=" * 60)
    steps, old = choose_steps()
    points = old["points"] if old else {}     # 안 다시 재는 값은 그대로 둠
    sizes = old["sizes"] if old else {}
    i = 0
    while i < len(steps):
        name, kind, guide = steps[i]
        print(f"\n[{i + 1}/{len(steps)}] {guide}")
        print("   → 마우스를 올리고 F1")
        key = wait_key()
        if key == "esc":
            print("\n그만둠 — 저장하지 않았습니다.")
            return
        if key == "f2":
            if i > 0:
                i -= 1
                print("   (직전 지점을 다시 잽니다)")
            continue
        x, y = pyautogui.position()
        w, same = window_at(kind, x, y)
        if w is None:
            if not same:
                print(f"   [다시] '{TITLES[kind]}' 창을 못 찾았어요. 창이 떠 있는지 확인하세요.")
            else:
                r = same[0]
                print(f"   [다시] 마우스({x}, {y})가 '{TITLES[kind]}' 창 밖이에요. "
                      f"(창 위치 {r.left},{r.top} 크기 {r.width}x{r.height})")
            continue
        fx = (x - w.left) / w.width
        fy = (y - w.top) / w.height
        points[name] = {"win": kind, "fx": round(fx, 5), "fy": round(fy, 5),
                        "dx": x - w.left, "dy": y - w.top}
        sizes[kind] = [w.width, w.height]
        print(f"   기록: ({x}, {y}) = '{w.title}' 창 안 ({x - w.left}, {y - w.top})"
              f" / 창 크기 {w.width}x{w.height}  → {fx*100:.1f}%, {fy*100:.1f}%")
        i += 1

    # 간단한 점검 (칸 간격이 이상하면 바로 보이게)
    def d(a, b, axis):
        return points[b]["d" + axis] - points[a]["d" + axis]
    print("\n" + "-" * 60)
    print(" 점검 (이 컴퓨터 픽셀 기준)")
    try:
        print(f"   슬롯 간격      : {d('slot1', 'slot2', 'x')}")
        print(f"   인벤토리 간격  : 가로 {d('cell_first', 'cell_row1_last', 'x') / 5:.1f}"
              f" / 세로 {d('cell_first', 'cell_row5_first', 'y') / 4:.1f}  (둘이 거의 같아야 정상)")
    except KeyError:
        pass
    if all(n in points for n in ("fab_tl", "fab_br", "line")):
        fw, fh = d('fab_tl', 'fab_br', 'x'), d('fab_tl', 'fab_br', 'y')
        print(f"   천 크기        : {fw} x {fh}  (칸 하나 폭 약 {fw / 5:.0f})")
        print(f"   빨간 실선 높이 : 천 위에서 {d('fab_tl', 'line', 'y')}  (천 높이의 "
              f"{d('fab_tl', 'line', 'y') / max(fh, 1) * 100:.0f}% — 보통 60~75%)")

    data = {"titles": TITLES, "sizes": sizes, "points": points,
            "saved_at": time.strftime("%Y-%m-%d %H:%M")}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"\n저장 완료: {OUT}")
    print("이 화면 내용을 복사해서 보내주세요 (점검용).")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
