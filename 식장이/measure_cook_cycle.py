# -*- coding: utf-8 -*-
"""
식장이 사이클(cook_cycle.py) 준비 도구 — 한 번만 하면 됨.

안내하는 지점에 마우스를 올리고 F1. 바닥 재료 무더기는 그림의 왼쪽 위 → 오른쪽 아래 두 번 F1.
결과: ring_layout.json + ring_sprites 폴더 (이 폴더 안)

  1. 아래 메뉴 [아이템] 아이콘
  2. 아이템 창 칸 (첫 칸 / 첫 줄 맨 오른쪽 / 5번째 줄 첫 칸)
  3. 바닥 재료 무더기 그림 (레시피 재료마다)
  4. 완성품을 버릴 바닥 빈 자리 (재료 무더기와 떨어진 곳)
  5. 아이템 창의 완성품 20개 꽉 찬 칸 (왼쪽 위 숫자 20 그림 — 20개 칸만 버릴 때)

■ 준비: 게임 화면에 제작 창을 띄우고, 바닥에 재료 무더기를 하나씩 떨어뜨려 두기
         인벤토리에 완성품 20개 꽉 찬 칸이 하나 있어야 함 (5번)
■ 실행:  py measure_cook_cycle.py      F1 = 기록 / F2 = 방금 것 다시 / ESC = 그만두기
  ring_layout.json 이 이미 있으면 바뀐 부분 번호만 골라서 다시 잴 수 있음
"""

import os
import re
import sys
import json
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import measure_ring as mr       # 마결자동 측정 도구의 창 찾기/키 입력 (그대로)
import mss
import pyautogui
from PIL import Image


def setting(fn, name):
    """파일에 적힌 설정값 하나 (파일을 실행하지 않고 그 줄만 읽음). 없으면 None."""
    import ast
    try:
        with open(os.path.join(HERE, fn), encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except Exception:
                return None
    return None


def full_names():
    """20개 칸 그림을 잴 완성품 이름 (cook_cycle.py 의 DROP, 끝 숫자 뺌). FULL_ONLY = False 면 없음."""
    if setting("cook_cycle.py", "FULL_ONLY") is False:
        return []
    out = []
    for n in setting("cook_cycle.py", "DROP") or ():
        b = re.sub(r"[_\-]?\d+$", "", str(n)) or str(n)
        if b not in out:
            out.append(b)
    return out


def recipe_names():
    """cook_cycle.py 의 PILES → RECIPE → auto_cook.py 의 RECIPE 순서로 재료 이름 (파일을 실행하지 않고 읽음)."""
    piles = setting("cook_cycle.py", "PILES")
    if piles is not None:
        return list(piles)
    recipe = setting("cook_cycle.py", "RECIPE") or setting("auto_cook.py", "RECIPE") or []
    names = []
    for n, _ in recipe:
        if n not in names:
            names.append(n)
    return names


def build_steps(names, fulls):
    steps = [
        ("say", "say", "게임 화면과 제작 창이 보이게 해두세요. 준비됐으면 F1"),
        ("item_icon", "main", "아래 메뉴 맨 왼쪽 [아이템] 아이콘 (상자 모양) 가운데"),
        ("say", "say", "아이템 창을 띄워 두세요 (아까비깡을 먹고, 완성품을 끌어다 버리는 곳). 띄웠으면 F1"),
        ("item_first", "win", "아이템 창 첫 칸(왼쪽 위) 가운데"),
        ("item_row1_last", "win", "아이템 창 첫 줄 맨 오른쪽 칸 가운데"),
        ("item_row5_first", "win", "아이템 창 맨 아래 줄(5번째 줄) 첫 칸 가운데"),
    ]
    first_spr = len(steps)
    steps += [("spr_" + n, "box", f"바닥의 {n} 무더기 하나 (안 가려진 것)") for n in names]
    drop = len(steps)
    steps.append(("drop_spot", "main", "완성품을 버릴 바닥 빈 자리 — 재료 무더기와 떨어진 곳 (창이 안 덮는 바닥)"))
    groups = [
        ("아래 메뉴 [아이템] 아이콘", [0, 1], []),
        ("아이템 창 칸", [2, 3, 4, 5], ["item"]),
        ("바닥 재료 무더기 그림 (" + "/".join(names) + ")", [0] + list(range(first_spr, drop)), []),
        ("완성품 버릴 자리", [0, drop], []),
    ]
    if fulls:
        first_full = len(steps)
        steps.append(("say", "say", "아이템 창에 " + "/".join(fulls) + " 20개 꽉 찬 칸이 보이게 해두세요. 됐으면 F1"))
        steps += [("full_" + n, "full", f"아이템 창의 {n} 20개 칸 (왼쪽 위 숫자가 20) 가운데") for n in fulls]
        groups.append(("완성품 20개 칸 숫자 그림 (" + "/".join(fulls) + ")", list(range(first_full, len(steps))), []))
    return steps, groups


ALIGN = 7                    # 위치 맞춤 여유 (cook_cycle.py 의 FULL_ALIGN 과 같은 값)


def grab_full(data, x, y):
    """(x, y) 가 가리키는 아이템 창 칸을 칸 가운데에 맞춰 저장할 그림으로. 실패면 None.

    마우스가 칸 위에 있으면 커서/설명 창이 그림을 가려서, 마우스를 창 밖으로 치운 뒤에 찍음.
    """
    p = data["points"]
    if not all(k in p for k in ("item_first", "item_row1_last", "item_row5_first")) or "item" not in data["titles"]:
        print("   [다시] 아이템 창 칸(2번)을 먼저 재야 해요")
        return None
    w = mr.top_window_at(x, y)
    if w is None or mr.norm(w.title) != mr.norm(data["titles"]["item"]):
        print("   [다시] 아이템 창 칸 위가 아니에요")
        return None
    a = (w.left + p["item_first"]["fx"] * w.width, w.top + p["item_first"]["fy"] * w.height)
    b = (w.left + p["item_row1_last"]["fx"] * w.width, w.top + p["item_row1_last"]["fy"] * w.height)
    c = (w.left + p["item_row5_first"]["fx"] * w.width, w.top + p["item_row5_first"]["fy"] * w.height)
    px, py = (b[0] - a[0]) / 5, (c[1] - a[1]) / 4
    col = min(5, max(0, int(round((x - a[0]) / px))))
    row = min(4, max(0, int(round((y - a[1]) / py))))
    cx, cy = int(round(a[0] + col * px)), int(round(a[1] + row * py))
    print("   마우스를 아이템 창 밖으로 치우세요 (치우면 바로 찍음)")
    t0 = time.time()
    while time.time() - t0 < 15:
        mx, my = pyautogui.position()
        if not (w.left <= mx < w.left + w.width and w.top <= my < w.top + w.height):
            break
        time.sleep(0.1)
    else:
        print("   [다시] 마우스가 계속 아이템 창 안에 있어요")
        return None
    time.sleep(0.8)                          # 설명 창이 사라질 때까지
    half = int(round(min(abs(px), abs(py)) * 0.40)) + ALIGN    # 칸 안쪽(칸 간격의 80%) + 여유
    with mss.mss() as sct:
        shot = sct.grab({"left": cx - half, "top": cy - half, "width": half * 2, "height": half * 2})
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return img, (cx, cy), (row, col)


def choose(steps, groups):
    if not os.path.exists(mr.OUT):
        return steps, None
    try:
        with open(mr.OUT, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return steps, None
    print("\n이미 잰 값(ring_layout.json)이 있어요. 바뀐 부분만 다시 잴 수 있어요.")
    for n, (label, _, _) in enumerate(groups, 1):
        print(f"   {n}. {label}")
    ans = input("다시 잴 번호 (예: 3  또는  3,4)  /  전부 다시 재려면 그냥 엔터: ").strip()
    picks = sorted({int(t) for t in ans.replace(" ", ",").split(",") if t.isdigit() and 1 <= int(t) <= len(groups)})
    if not picks:
        return steps, None
    for g in picks:
        for wk in groups[g - 1][2]:
            old.get("titles", {}).pop(wk, None)
    idx = sorted({i for g in picks for i in groups[g - 1][1]})
    print("→ " + ", ".join(groups[g - 1][0] for g in picks) + " 만 다시 잽니다 (나머지는 그대로)")
    return [steps[i] for i in idx], old


def main():
    names = recipe_names()
    if not names:
        print("[중단] 레시피(재료 이름)를 먼저 적어주세요 — auto_cook.py 의 RECIPE (또는 cook_cycle.py 맨 위 RECIPE)")
        return
    print("=" * 64)
    print(" 식장이 사이클 준비 (F1 = 기록, F2 = 방금 것 다시, ESC = 그만)")
    print(" 바닥 무더기 그림을 잴 재료:", ", ".join(names))
    if full_names():
        print(" 20개 칸 숫자 그림을 잴 완성품:", ", ".join(full_names()), " (20개 꽉 찬 칸이 아직 없으면 나중에 따로 재도 됨)")
    print("=" * 64)
    cw = mr.craft_window()
    if cw is None:
        print("[중단] 제작 창이 안 보여요. 직업활동으로 제작 창을 띄우고 다시 실행하세요.")
        return
    mw = mr.main_window()
    if mw is None:
        print("[중단] 게임 창(제목에 '조이톡')을 못 찾았어요.")
        return
    os.makedirs(mr.SPRITE_DIR, exist_ok=True)
    try:
        import ctypes
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        dpi = None
    fulls = full_names()
    all_steps, groups = build_steps(names, fulls)
    steps, old = choose(all_steps, groups)
    if old is None and fulls:
        ans = input(f"\n인벤토리에 {'/'.join(fulls)} 20개 꽉 찬 칸이 지금 있나요?  (있으면 그냥 엔터 / 없으면 n 엔터): ")
        if ans.strip().lower() in ("n", "no", "ㅜ", "없음", "없어", "아니", "아니오"):
            skip = set(groups[-1][1])
            steps = [s for i, s in enumerate(all_steps) if i not in skip]
            print("→ 20개 칸은 건너뜀 — 생기면  py measure_cook_cycle.py → 5번  만 재면 됨"
                  " (그때까지는 버리지 않고 요리만 함)")
    if old is not None:
        data = old
        data.setdefault("titles", {})["main"] = mw.title
        data.setdefault("points", {})
        data.setdefault("sprites", {})
    else:
        data = {"titles": {"main": mw.title}, "ref_craft_w": cw.width, "dpi": dpi, "points": {}, "sprites": {}}
    i, box_first = 0, None
    while i < len(steps):
        name, kind, guide = steps[i]
        if kind == "box":
            part = "왼쪽 위" if box_first is None else "오른쪽 아래"
            print(f"\n[{i + 1}/{len(steps)}] {guide}\n   → 그 그림의 {part} 모서리에 마우스 → F1")
        elif kind == "say":
            print(f"\n[{i + 1}/{len(steps)}] {guide}")
        else:
            print(f"\n[{i + 1}/{len(steps)}] {guide}\n   → 마우스를 올리고 F1")
        key = mr.wait_key()
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
        mw = mr.main_window() or mw
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
            fn = name[4:] + ".png"
            Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(os.path.join(mr.SPRITE_DIR, fn))
            data["sprites"][name] = {"file": fn, "w": x1 - x0, "h": y1 - y0, "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2}
            print(f"   저장: ring_sprites/{fn}  ({x1 - x0}x{y1 - y0})")
            i += 1
            continue
        if kind == "full":
            got = grab_full(data, x, y)
            if got is None:
                continue
            img, (cx, cy), (row, col) = got
            fn = name + ".png"
            img.save(os.path.join(mr.SPRITE_DIR, fn))
            data["sprites"][name] = {"file": fn, "w": img.size[0], "h": img.size[1], "cx": cx, "cy": cy}
            print(f"   저장: ring_sprites/{fn}  (아이템 창 {row + 1}줄 {col + 1}칸)")
            i += 1
            continue
        if kind == "main":
            if not (mw.left <= x < mw.left + mw.width and mw.top <= y < mw.top + mw.height):
                print("   [다시] 게임 창 밖이에요")
                continue
            if name == "drop_spot":
                over = mr.top_window_at(x, y)
                if over is not None and "조이톡" not in str(over.title):
                    print(f"   [다시] 거기는 '{over.title}' 창 위예요. 창이 안 덮는 바닥을 골라주세요")
                    continue
            data["points"][name] = {"dx_left": x - mw.left, "dx_right": mw.left + mw.width - x,
                                    "dy_top": y - mw.top, "dy_bottom": mw.top + mw.height - y, "x": x, "y": y}
            print(f"   기록: ({x}, {y})")
            i += 1
            continue
        # win: 아이템 창 안
        w = mr.top_window_at(x, y)
        if w is None or "조이톡" in str(w.title):
            print("   [다시] 그 위치에 아이템 창이 없어요. 창이 떠 있는지 확인하세요.")
            continue
        if "item" in data["titles"] and mr.norm(data["titles"]["item"]) != mr.norm(w.title):
            print(f"   [다시] 아까 잰 창('{data['titles']['item']}')과 다른 창('{w.title}')이에요")
            continue
        data["titles"]["item"] = w.title
        data.setdefault("sizes", {})["item"] = [w.width, w.height]
        data["points"][name] = {"win": "item", "fx": round((x - w.left) / w.width, 5),
                                "fy": round((y - w.top) / w.height, 5), "dx": x - w.left, "dy": y - w.top}
        print(f"   기록: '{w.title}' 창 안 ({x - w.left}, {y - w.top}) / 창 크기 {w.width}x{w.height}")
        i += 1

    p = data["points"]
    print("\n" + "-" * 64)
    print(" 점검")
    if all(k in p for k in ("item_first", "item_row1_last", "item_row5_first")):
        print(f"   아이템 칸 간격: 가로 {(p['item_row1_last']['dx'] - p['item_first']['dx']) / 5:.1f}"
              f" / 세로 {(p['item_row5_first']['dy'] - p['item_first']['dy']) / 4:.1f}  (둘이 거의 같아야 정상)")
    print(f"   그림: {', '.join(v['file'] for v in data['sprites'].values())}")
    if any(k.startswith("full_") for k in data["sprites"]):
        print("   20개 칸 숫자 그림이 맞게 찍혔는지:  py cook_cycle.py 숫자  (버리지 않고 칸마다 확인만)")
    elif full_names():
        print("   20개 칸 숫자 그림: 아직 없음 — 20개 꽉 찬 칸이 생기면  py measure_cook_cycle.py → 5번")
    data["saved_at"] = time.strftime("%Y-%m-%d %H:%M")
    tmp = mr.OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    os.replace(tmp, mr.OUT)
    print(f"\n저장 완료: {mr.OUT}")
    print("다 했으면  py cook_cycle.py 점검  으로 빠진 게 없는지 확인하세요")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
