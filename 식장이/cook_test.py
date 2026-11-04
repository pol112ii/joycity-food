# -*- coding: utf-8 -*-
"""
식장이 사이클 구간별 시험 — 한 구간만 한 번 해보고 결과를 보여줌 (사이클은 안 돌림).
cook_cycle.py 의 설정 / 측정값을 그대로 씀. 어느 구간이 잘 안 되는지 찾을 때.

  py cook_test.py      → 번호 고르기 (여러 번 해볼 수 있음, 그냥 엔터 = 끝)
  시험 중 F9 = 그 시험 중단

   1. 아까비깡 먹기
   2. 20개 칸 버리기 — 하나만
   3. 20개 칸 버리기 — 전부
   4. 바닥 재료 줍기 (레시피 무더기 수만큼)
   5. 요리 1판 (재료 넣기 → 요리)
   6. 한 바퀴 전체 (먹기 → 버리기 → 줍기 → 요리, 재료 떨어질 때까지)
   --- 클릭 안 하는 확인 ---
   7. 아이템 창 읽기 (칸마다 이름 / 20개 여부)  ※ 아이템 창이 닫혀 있으면 여는 것만
   8. 바닥 재료 찾기 (찾은 개수 / 일치 점수, floor_debug.png 저장)
   9. 버릴 자리로 마우스만 옮기기
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cook_cycle as cc
rc, ac, am = cc.rc, cc.ac, cc.am
import mss
import keyboard

MENU = """
------------------------------------------------------------
 1. 아까비깡 먹기
 2. 20개 칸 버리기 — 하나만
 3. 20개 칸 버리기 — 전부
 4. 바닥 재료 줍기
 5. 요리 1판
 6. 한 바퀴 전체 (먹기 → 버리기 → 줍기 → 요리)
 --- 클릭 안 하는 확인 ---
 7. 아이템 창 읽기 (칸마다 이름 / 20개 여부)
 8. 바닥 재료 찾기 (floor_debug.png 저장)
 9. 버릴 자리로 마우스만 옮기기
 그냥 엔터 = 끝          (시험 중 F9 = 중단)
------------------------------------------------------------"""


def count(sct, name):
    """아이템 창에서 name 칸 수."""
    return sum(1 for _, n in rc.item_contents(sct) if n == name)


def t_eat(sct):
    before = count(sct, cc.FOOD)
    rc.eat_all(sct)
    after = count(sct, cc.FOOD)
    print(f"\n결과: {cc.FOOD} 칸 {before} → {after}")
    return after == 0 or after < before or before == 0


def t_drop(sct, limit):
    before = len(cc.product_cells(sct))
    if before == 0:
        print("\n결과: 버릴 칸이 없어요 (20개 칸이 없거나 못 알아봄 → 7번으로 확인)")
        return False
    ok = cc.drop_products(sct, limit=limit)
    after = len(cc.product_cells(sct, verbose=False))
    print(f"\n결과: {'성공' if ok else '실패'} — 버릴 칸 {before} → {after}")
    return ok


def t_pick(sct):
    before = rc.material_cells(sct)
    ok = rc.pick_up(sct)
    after = rc.material_cells(sct)
    print(f"\n결과: {'성공' if ok else '실패'} — 재료 칸 {before} → {after}  (필요 {rc.PILES})")
    return ok


def t_cook(sct, rounds):
    keep = cc.MAX_ROUNDS
    cc.MAX_ROUNDS = rounds
    try:
        n = cc.cook_all(sct)
    finally:
        cc.MAX_ROUNDS = keep
    print(f"\n결과: 요리 {n}판" + (" (오류로 멈춤)" if n < 0 else ""))
    return n > 0


def t_cycle(sct):
    steps = []
    t = time.time()
    rc.eat_all(sct)
    steps.append(("먹기", True, time.time() - t))
    for name, fn in (("버리기", lambda: cc.drop_products(sct)), ("줍기", lambda: rc.pick_up(sct))):
        if not cc.on():
            break
        t = time.time()
        ok = fn()
        steps.append((name, ok, time.time() - t))
        if not ok:
            break
    else:
        if cc.on():
            t = time.time()
            n = cc.cook_all(sct)
            steps.append((f"요리 {n}판", n > 0, time.time() - t))
    print("\n결과:")
    for name, ok, sec in steps:
        print(f"   {'✓' if ok else '✗'} {name}  ({sec:.0f}초)")
    return all(ok for _, ok, _ in steps)


def t_read(sct):
    rows = []
    for i, (pos, n) in enumerate(rc.item_contents(sct)):
        if n == "":
            label = "·"
        elif n is None:
            label = "?"
        else:
            label = n
            if n in cc._drop and cc.FULL_ONLY:
                d = cc.number_diff(sct, pos, cc._full[n])
                label += f"(20개)" if d <= cc.FULL_DIFF else f"({d})"
        rows.append(label)
    print("\n아이템 창 (· = 빈 칸, ? = 모르는 것, 완성품 옆 숫자 = 20개 칸과 다른 정도):")
    for r in range(5):
        print("   " + " | ".join(f"{x:^10}" for x in rows[r * 6:r * 6 + 6]))
    return True


def t_floor(sct):
    import numpy as np
    from PIL import Image
    w = rc.main_win()
    if w is None:
        print("\n결과: 게임 창을 못 찾음")
        return False
    img = rc.shot_bgr(sct, w.left, w.top, w.width, w.height)
    import cv2
    ok = True
    print()
    for name in rc.PILES:
        found = rc.find_sprite(sct, "spr_" + name, rc.SPRITE_SURE)
        sc = ", ".join(f"{s:.2f}" for _, _, s in found[:5])
        print(f"   {name}: {len(found)}개" + (f"  (점수 {sc}, 기준 {rc.SPRITE_SURE})" if found else "  ← 못 찾음"))
        ok = ok and bool(found)
        for x, y, s in found:
            cv2.circle(img, (int(x - w.left), int(y - w.top)), 14, (0, 0, 255), 2)
            cv2.putText(img, name[:1], (int(x - w.left) - 6, int(y - w.top) - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    try:
        x, y = rc.main_pt("drop_spot")
        cv2.drawMarker(img, (int(x - w.left), int(y - w.top)), (0, 255, 255), cv2.MARKER_CROSS, 30, 2)
    except Exception:
        pass
    path = os.path.join(HERE, "floor_debug.png")
    Image.fromarray(np.ascontiguousarray(img[:, :, ::-1])).save(path)
    print(f"   그림 저장: {path}  (빨간 동그라미 = 찾은 무더기, 노란 + = 버릴 자리)")
    return ok


def t_spot(sct):
    x, y = rc.main_pt("drop_spot")
    am.smooth_move_to(x, y, 0.4, bow=6)
    print(f"\n결과: 마우스를 버릴 자리 ({x}, {y}) 로 옮김 — 방 바닥 빈 곳인지 눈으로 확인"
          f"  (매번 좌우 {cc.DROP_SPREAD[0]} / 위아래 {cc.DROP_SPREAD[1]}px 안에서 조금씩 다르게 놓음)")
    return True


TESTS = {
    "1": ("아까비깡 먹기", t_eat),
    "2": ("20개 칸 버리기 — 하나만", lambda sct: t_drop(sct, 1)),
    "3": ("20개 칸 버리기 — 전부", lambda sct: t_drop(sct, None)),
    "4": ("바닥 재료 줍기", t_pick),
    "5": ("요리 1판", lambda sct: t_cook(sct, 1)),
    "6": ("한 바퀴 전체", t_cycle),
    "7": ("아이템 창 읽기", t_read),
    "8": ("바닥 재료 찾기", t_floor),
    "9": ("버릴 자리로 마우스만", t_spot),
}


def run(choice):
    name, fn = TESTS[choice]
    print(f"\n===== {choice}. {name} =====")
    cc.set_running(True)
    t0 = time.time()
    ok = False
    try:
        with mss.mss() as sct:
            ok = fn(sct)
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        stopped = not cc.running
        cc.set_running(False)
        ac.release_keys()
    print(f"({time.time() - t0:.0f}초" + (", F9 로 중단됨" if stopped else "") + ")")
    return ok


def stop():
    if cc.running:
        cc.set_running(False)
        print("\n⏸ 중단 — 하던 동작이 끝나면 멈춤")


def main():
    print("=" * 60)
    print(" 식장이 사이클 구간별 시험 (cook_cycle.py 설정 그대로)")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print("=" * 60)
    if not cc.load():
        return
    keyboard.add_hotkey("f9", stop)
    try:
        import macro_guard              # 시험 중에도 매크로 방지 확인 창이 뜨면 멈추고 알림
        macro_guard.start(cc._Link())
    except Exception as e:
        print(f" (매크로 방지 창 감시를 못 켬: {e})")
    while True:
        print(MENU)
        ans = input("번호: ").strip()
        if not ans:
            break
        if ans not in TESTS:
            print("1~9 중에서 고르세요")
            continue
        run(ans)
    cc.set_alive(False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
