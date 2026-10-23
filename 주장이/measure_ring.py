# -*- coding: utf-8 -*-
"""
반지 자동(ring_cycle.py) 준비 도구 — 한 번만 하면 됨.

안내하는 지점에 마우스를 올리고 F1 을 누르면 위치를 기록하고,
바닥 재료 / 리어카맨 이름 글자는 '왼쪽 위 → 오른쪽 아래' 두 번 F1 으로 그림을 저장함.
결과: ring_layout.json + ring_sprites 폴더 (이 폴더 안에 생김)

■ 준비
  - 주장이 봇을 쓰던 그대로: match_layout.json 이 이 폴더에 있어야 함
  - 게임 화면에 제작 창과 방(바닥에 석분/철괴/상급키트가 떨어진 상태)이 보이게
■ 실행:  py measure_ring.py
  F1 = 기록 / F2 = 방금 것 다시 / ESC = 그만두기
"""

import os
import sys
import json
import time

try:
    import mss
    import keyboard
    import pyautogui
    import pygetwindow as gw
    from PIL import Image
except ImportError as e:
    print("[에러] 필요한 프로그램이 없습니다:", e)
    print("cmd 에서:  py -m pip install mss numpy pyautogui keyboard pillow pygetwindow")
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ring_layout.json")
SPRITE_DIR = os.path.join(HERE, "ring_sprites")
CRAFT_TITLE = "제작"

# (이름, 종류, 안내)
#   종류 main  : 게임 메인 창(조이톡) 안의 고정 위치 (아래 메뉴/HP 막대)
#        win   : 따로 뜨는 창(능력 / 되팔기) 안의 위치 — 창 제목은 자동으로 기록
#        box   : 그림 저장 (왼쪽 위, 오른쪽 아래 두 번)
#        say   : 안내만 (아무 키나 F1)
STEPS = [
    ("say", "say", "제작 창과 방 화면이 보이게 해두세요. 준비됐으면 F1"),
    ("item_icon", "main", "아래 메뉴 맨 왼쪽 [아이템] 아이콘 (상자 모양) 가운데"),
    ("job_icon", "main", "아래 메뉴의 [직업] 아이콘 (가방 모양) 가운데"),
    ("ability_icon", "main", "아래 메뉴의 [능력] 아이콘 (별 모양) 가운데"),
    ("say", "say", "아이템 창을 띄워 두세요 (아까비깡을 먹고, 주운 재료를 확인하는 곳). 띄웠으면 F1"),
    ("item_first", "win", "아이템 창 첫 칸(왼쪽 위) 가운데"),
    ("item_row1_last", "win", "아이템 창 첫 줄 맨 오른쪽 칸 가운데"),
    ("item_row5_first", "win", "아이템 창 맨 아래 줄(5번째 줄) 첫 칸 가운데"),
    ("say", "say", "이제 [능력] 아이콘을 직접 눌러서 능력 창을 띄우세요. 띄웠으면 F1"),
    ("summon", "win", "능력 창의 [고물소환] 줄 가운데  (누르지 말고 마우스만 올리기)"),
    ("ability_close", "win", "능력 창 오른쪽 위 빨간 동그라미 (닫기)"),
    ("spr_석분", "box", "바닥의 석분 무더기 하나 (안 가려진 것)"),
    ("spr_철괴", "box", "바닥의 철괴 무더기 하나 (안 가려진 것)"),
    ("spr_상급키트", "box", "바닥의 상급키트 무더기 하나 (안 가려진 것)"),
    ("say", "say", "능력 창에서 [고물소환]을 한 번 누르고, 빨간 버튼으로 능력 창을 닫은 뒤\n"
                   "   리어카맨이 나타나면 F1"),
    ("cart_label", "box", "리어카맨 머리 위 이름 글자 ('...의 리어카맨' 전체를 감싸게)"),
    ("cart_body", "main", "리어카맨 몸통 가운데 (봇이 클릭할 곳)"),
    ("say", "say", "리어카맨을 직접 눌러서 '고물상 — 되팔기' 창을 띄우세요. 띄웠으면 F1"),
    ("sell_first", "win", "되팔기 창 '오른쪽'(내 인벤토리) 첫 칸 가운데"),
    ("sell_row1_last", "win", "되팔기 창 오른쪽 첫 줄 맨 오른쪽 칸 가운데"),
    ("sell_row5_first", "win", "되팔기 창 오른쪽 맨 아래 줄(5번째 줄) 첫 칸 가운데"),
    ("sell_btn", "win", "되팔기 창 초록 [팔기] 버튼"),
    ("sell_close", "win", "되팔기 창 [닫기] 버튼"),
]
WIN_KIND = {"item_first": "item", "item_row1_last": "item", "item_row5_first": "item",
            "summon": "ability", "ability_close": "ability",
            "sell_first": "sell", "sell_row1_last": "sell", "sell_row5_first": "sell",
            "sell_btn": "sell", "sell_close": "sell"}


def norm(t):
    return "".join(str(t).split())


def shown(w):
    try:
        return (w.visible and w.width > 0 and w.height > 0
                and not getattr(w, "isMinimized", False)
                and w.left > -10000 and w.top > -10000)
    except Exception:
        return False


def is_console(w):
    t = str(w.title)
    return any(k in t for k in ("명령 프롬프트", "cmd.exe", "python", "py.exe", "Windows PowerShell"))


def top_window_at(x, y):
    """(x, y) 에 있는 맨 위 창 (제목 있는 것, cmd 창 제외)."""
    for w in gw.getAllWindows():          # 화면에서 위에 있는 창부터 나옴
        if not str(w.title).strip() or not shown(w) or is_console(w):
            continue
        if w.left <= x < w.left + w.width and w.top <= y < w.top + w.height:
            return w
    return None


def main_window():
    """게임 메인 창(제목에 '조이톡'). 가장 큰 것."""
    ws = [w for w in gw.getAllWindows() if "조이톡" in str(w.title) and shown(w)]
    exact = [w for w in ws if norm(w.title) == "조이톡"]     # 브라우저 탭 제목 등은 제외
    ws = exact or ws
    return max(ws, key=lambda w: w.width * w.height) if ws else None


def craft_window():
    for w in gw.getAllWindows():
        if norm(w.title) == norm(CRAFT_TITLE) and shown(w):
            return w
    return None


def wait_key():
    while True:
        ev = keyboard.read_event(suppress=False)
        if ev.event_type == "down" and ev.name in ("f1", "f2", "esc"):
            while keyboard.is_pressed(ev.name):
                time.sleep(0.02)
            return ev.name


def main():
    print("=" * 64)
    print(" 반지 자동 준비 (F1 = 기록, F2 = 방금 것 다시, ESC = 그만)")
    print("=" * 64)
    cw = craft_window()
    if cw is None:
        print("[중단] 제작 창이 안 보여요. 직업활동으로 제작 창을 띄우고 다시 실행하세요.")
        return
    mw = main_window()
    if mw is None:
        print("[중단] 게임 창(제목에 '조이톡')을 못 찾았어요.")
        return
    print(f"게임 창 '{mw.title}' {mw.width}x{mw.height} / 제작 창 폭 {cw.width}")
    os.makedirs(SPRITE_DIR, exist_ok=True)

    data = {"titles": {"main": mw.title}, "ref_craft_w": cw.width,
            "points": {}, "sprites": {}}
    i = 0
    box_first = None
    while i < len(STEPS):
        name, kind, guide = STEPS[i]
        if kind == "box":
            part = "왼쪽 위" if box_first is None else "오른쪽 아래"
            print(f"\n[{i + 1}/{len(STEPS)}] {guide}\n   → 그 그림의 {part} 모서리에 마우스 → F1")
        elif kind == "say":
            print(f"\n[{i + 1}/{len(STEPS)}] {guide}")
        else:
            print(f"\n[{i + 1}/{len(STEPS)}] {guide}\n   → 마우스를 올리고 F1")
        key = wait_key()
        if key == "esc":
            print("\n그만둠 — 저장하지 않았습니다.")
            return
        if key == "f2":
            if box_first is not None:
                box_first = None
            elif i > 0:
                i -= 1
            print("   (다시 잽니다)")
            continue
        if kind == "say":
            i += 1
            continue
        x, y = pyautogui.position()
        mw = main_window() or mw

        if kind == "box":
            if box_first is None:
                box_first = (x, y)
                continue
            x0, y0 = min(box_first[0], x), min(box_first[1], y)
            x1, y1 = max(box_first[0], x), max(box_first[1], y)
            box_first = None
            if x1 - x0 < 8 or y1 - y0 < 6:
                print("   [다시] 너무 작아요. 그림 전체를 감싸게 다시")
                continue
            with mss.mss() as sct:
                shot = sct.grab({"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0})
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            fn = name[4:] + ".png" if name.startswith("spr_") else name + ".png"
            img.save(os.path.join(SPRITE_DIR, fn))
            data["sprites"][name] = {"file": fn, "w": x1 - x0, "h": y1 - y0,
                                     "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2}
            print(f"   저장: ring_sprites/{fn}  ({x1 - x0}x{y1 - y0})")
            i += 1
            continue

        if kind == "main":
            if not (mw.left <= x < mw.left + mw.width and mw.top <= y < mw.top + mw.height):
                print("   [다시] 게임 창 밖이에요")
                continue
            pt = {"dx_left": x - mw.left, "dx_right": mw.left + mw.width - x,
                  "dy_top": y - mw.top, "dy_bottom": mw.top + mw.height - y,
                  "x": x, "y": y}
            if name == "cart_body":
                lab = data["sprites"].get("cart_label")
                if lab is None:
                    print("   [다시] 이름 글자를 먼저 저장해야 해요 (F2)")
                    continue
                pt["off_x"] = x - lab["cx"]
                pt["off_y"] = y - lab["cy"]
            data["points"][name] = pt
            print(f"   기록: ({x}, {y})")
            i += 1
            continue

        # win: 따로 뜨는 창 안
        w = top_window_at(x, y)
        if w is None or "조이톡" in str(w.title):
            print("   [다시] 그 위치에 따로 뜬 창이 없어요. 창이 떠 있는지 확인하세요.")
            continue
        wk = WIN_KIND[name]
        if wk in data["titles"] and norm(data["titles"][wk]) != norm(w.title):
            print(f"   [다시] 아까 잰 창('{data['titles'][wk]}')과 다른 창('{w.title}')이에요")
            continue
        data["titles"][wk] = w.title
        data["points"][name] = {"win": wk, "fx": round((x - w.left) / w.width, 5),
                                "fy": round((y - w.top) / w.height, 5),
                                "dx": x - w.left, "dy": y - w.top}
        print(f"   기록: '{w.title}' 창 안 ({x - w.left}, {y - w.top}) / 창 크기 {w.width}x{w.height}")
        i += 1

    p = data["points"]
    print("\n" + "-" * 64)
    print(" 점검")
    print(f"   창 제목: {data['titles']}")
    print(f"   되팔기 칸 간격: 가로 {(p['sell_row1_last']['dx'] - p['sell_first']['dx']) / 5:.1f}"
          f" / 세로 {(p['sell_row5_first']['dy'] - p['sell_first']['dy']) / 4:.1f}"
          f"  (둘이 거의 같아야 정상)")
    print(f"   아이템 칸 간격: 가로 {(p['item_row1_last']['dx'] - p['item_first']['dx']) / 5:.1f}"
          f" / 세로 {(p['item_row5_first']['dy'] - p['item_first']['dy']) / 4:.1f}")
    print(f"   그림: {', '.join(v['file'] for v in data['sprites'].values())}")
    data["saved_at"] = time.strftime("%Y-%m-%d %H:%M")
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
