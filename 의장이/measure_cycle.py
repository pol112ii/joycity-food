# -*- coding: utf-8 -*-
"""
의장이 사이클(sew_cycle.py) 준비 도구 — 마결자동의 measure_ring.py 를 그대로 쓰고,
바닥 무더기 그림만 sew_cycle.py 의 PILES 에 적은 재료로 바꿔서 잼.

결과: ring_layout.json + ring_sprites 폴더 (이 폴더 안)

■ 마결자동을 쓰던 컴퓨터 (제일 쉬움)
  1. 바닥에 의장이 재료 무더기를 떨어뜨려 두고, 제작 창을 띄운 채로:  py measure_cycle.py
  2. 바탕화면 등에서 마결자동 폴더의 ring_layout.json 을 찾아서 가져올지 물어봄 → 번호 입력
     (아래 메뉴 아이콘 / 아이템 창 / 능력 창 / 리어카맨 / 되팔기 창은 같은 게임 화면이라 그대로 씀)
  3. "다시 잴 번호" 에서 4 (바닥 무더기 그림) 만 → 재료마다 왼쪽 위/오른쪽 아래 F1 두 번
■ 마결자동 측정값이 없으면 처음부터 전부 잼 (마결자동 measure_ring.py 와 같은 순서)
■ 재료 이름: sew_cycle.py 의 PILES → RECIPE → auto_sew.py 의 RECIPE 순서로 찾음
  F1 = 기록 / F2 = 방금 것 다시 / ESC = 그만두기
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import measure_ring as mr       # 마결자동 측정 도구 (그대로)


def _setting(fn, name):
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


def read_piles():
    """바닥에서 주울 재료 이름 — sew_cycle.py 의 PILES, 없으면 RECIPE, 그것도 없으면 auto_sew.py 의 RECIPE."""
    piles = _setting("sew_cycle.py", "PILES")
    if piles is not None:
        return list(piles)
    recipe = _setting("sew_cycle.py", "RECIPE") or _setting("auto_sew.py", "RECIPE") or []
    names = []
    for n, _ in recipe:
        if n not in names:
            names.append(n)
    return names


def offer_copy():
    """이 폴더에 ring_layout.json 이 없으면, 근처(바탕화면 등) 마결자동 폴더에서 찾아서 가져올지 물어봄."""
    import glob
    import shutil
    if os.path.exists(mr.OUT):
        return
    up = os.path.dirname(HERE)
    found = []
    for pat in ("*/ring_layout.json", "*/*/ring_layout.json"):
        for f in glob.glob(os.path.join(up, pat)):
            d = os.path.dirname(os.path.abspath(f))
            if d != HERE and os.path.isdir(os.path.join(d, "ring_sprites")) and d not in found:
                found.append(d)
    if not found:
        print("(근처에서 마결자동 측정값(ring_layout.json)을 못 찾음 → 처음부터 전부 잽니다)")
        return
    print("\n마결자동 측정값을 찾았어요. 가져오면 바닥 재료 그림만 새로 재면 됩니다.")
    for i, d in enumerate(found, 1):
        print(f"   {i}. {d}")
    ans = input("가져올 번호 (가져오지 않고 처음부터 재려면 그냥 엔터): ").strip()
    if not ans.isdigit() or not 1 <= int(ans) <= len(found):
        return
    src = found[int(ans) - 1]
    shutil.copy2(os.path.join(src, "ring_layout.json"), mr.OUT)
    os.makedirs(mr.SPRITE_DIR, exist_ok=True)
    for f in os.listdir(os.path.join(src, "ring_sprites")):
        shutil.copy2(os.path.join(src, "ring_sprites", f), os.path.join(mr.SPRITE_DIR, f))
    print(f"→ ring_layout.json, ring_sprites 를 가져왔어요 ({src})")
    # 아까비깡 그림도 없으면 같이 (같은 게임 아이콘)
    food = _setting("sew_cycle.py", "FOOD") or ""
    mine, theirs = os.path.join(HERE, "items"), os.path.join(src, "items")
    if food and os.path.isdir(theirs):
        have = os.path.isdir(mine) and any(os.path.splitext(f)[0].rstrip("0123456789_-") == food
                                           for f in os.listdir(mine))
        if not have:
            pics = [f for f in os.listdir(theirs)
                    if f.lower().endswith(".png") and os.path.splitext(f)[0].rstrip("0123456789_-") == food]
            if pics:
                os.makedirs(mine, exist_ok=True)
                for f in pics:
                    shutil.copy2(os.path.join(theirs, f), os.path.join(mine, f))
                print(f"→ items 폴더에 {food} 그림도 가져왔어요")


def setup_steps(names):
    """measure_ring 의 바닥 그림 단계(석분/철괴/상급키트)를 이 재료들로 바꿈."""
    old = mr.STEPS
    spr = [i for i, s in enumerate(old) if s[0].startswith("spr_")]
    first, last = spr[0], spr[-1]
    new_spr = [("spr_" + n, "box", f"바닥의 {n} 무더기 하나 (안 가려진 것)") for n in names]
    shift = len(new_spr) - len(spr)
    steps = old[:first] + new_spr + old[last + 1:]
    groups = []
    for label, idx, wins in mr.GROUPS:
        if any(old[i][0].startswith("spr_") for i in idx):
            idx = [i for i in idx if not old[i][0].startswith("spr_")] + list(range(first, first + len(new_spr)))
            label = f"바닥 무더기 그림 ({'/'.join(names)})"
        else:
            idx = [i if i < first else i + shift for i in idx]
        groups.append((label, idx, wins))
    mr.STEPS, mr.GROUPS = steps, groups


def main():
    names = read_piles()
    if not names or any(n.startswith("재료") for n in names):
        print("[중단] 레시피(재료 이름)를 먼저 적어주세요 — sew_cycle.py 맨 위 RECIPE (또는 auto_sew.py 의 RECIPE)")
        print("       예)  RECIPE = [(\"실\", 1), (\"천조각\", 1), (\"단추\", 1)]   (이름은 items 폴더 그림 이름과 똑같이)")
        return
    print("의장이 사이클 준비 — 바닥 무더기 그림을 잴 재료:", ", ".join(names))
    offer_copy()
    setup_steps(names)
    mr.main()
    print("\n다 했으면  py sew_cycle.py 점검  으로 빠진 게 없는지 확인하세요")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
