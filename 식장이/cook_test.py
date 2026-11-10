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
   0. 완성품 칸 아무거나 하나 버리기 (20개가 아니어도 — 끌어다 놓기가 되는지 시험. 버린 건 눌러서 다시 주우면 됨)
   --- 클릭 안 하는 확인 ---
   7. 아이템 창 읽기 (칸마다 이름 / 20개 여부)  ※ 아이템 창이 닫혀 있으면 여는 것만
   8. 바닥 재료 / 빈 바닥 찾기 (찾은 개수, 빈 바닥과 내려놓을 자리를 floor_debug.png 로 저장)
   9. 지금 내려놓을 빈 자리로 마우스만 옮기기
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
 0. 완성품 칸 아무거나 하나 버리기 (20개 아니어도 — 끌어다 놓기 시험)
 --- 클릭 안 하는 확인 ---
 7. 아이템 창 읽기 (칸마다 이름 / 20개 여부)
 8. 바닥 재료 / 빈 바닥 찾기 (floor_debug.png 저장)
 9. 지금 내려놓을 빈 자리로 마우스만 옮기기
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
    if cc.FULL_ONLY and not cc._full:
        print("\n결과: 20개 칸 숫자 그림이 아직 없어요 — 20개 칸이 생기면 py measure_cook_cycle.py → 5번"
              "\n      (끌어다 놓기만 시험하려면 0번)")
        return False
    before = len(cc.product_cells(sct))
    if before == 0:
        print("\n결과: 버릴 칸이 없어요 (" + ("20개 칸이 없거나 못 알아봄" if cc.FULL_ONLY else "완성품 칸을 못 찾음")
              + " → 7번으로 확인)")
        return False
    ok = cc.drop_products(sct, limit=limit)
    after = len(cc.product_cells(sct, verbose=False))
    print(f"\n결과: {'성공' if ok else '실패'} — 버릴 칸 {before} → {after}")
    return ok


def t_drop_any(sct):
    """20개가 아니어도 완성품 칸 하나를 버려봄 (끌어다 놓기 시험)."""
    keep = cc.FULL_ONLY
    cc.FULL_ONLY = False
    try:
        ok = t_drop(sct, 1)
    finally:
        cc.FULL_ONLY = keep
    if ok:
        print("   (버린 완성품은 바닥에서 눌러 다시 주우면 됨)")
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
            if n in cc._full and cc.FULL_ONLY:
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
    import cv2
    w = rc.main_win()
    if w is None:
        print("\n결과: 게임 창을 못 찾음")
        return False
    img = rc.shot_bgr(sct, w.left, w.top, w.width, w.height)
    ok = True
    print()
    for name in rc.PILES:
        found = rc.find_sprite(sct, "spr_" + name, rc.SPRITE_SURE)
        sc = ", ".join(f"{s:.2f}" for _, _, s in found[:5])
        print(f"   {name}: {len(found)}개" + (f"  (점수 {sc}, 기준 {rc.SPRITE_SURE})" if found else "  ← 못 찾음"))
        ok = ok and bool(found)
        for x, y, s in found:
            cv2.circle(img, (int(x - w.left), int(y - w.top)), 14, (0, 0, 255), 2)
    # 빈 바닥: 봇이 '빈 바닥'으로 보는 곳만 밝게, 나머지는 어둡게
    try:
        m, _ = cc.floor_mask(sct)
        img[m == 0] = (img[m == 0] * 0.35).astype(np.uint8)
        spots = cc.empty_spots(sct, count=12)
        for i, (x, y, room) in enumerate(spots):
            p = (int(x - w.left), int(y - w.top))
            cv2.circle(img, p, 4, (0, 255, 255), -1)
            cv2.putText(img, str(i + 1), (p[0] + 6, p[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        x, y = rc.main_pt("drop_spot")
        cv2.drawMarker(img, (int(x - w.left), int(y - w.top)), (0, 0, 255), cv2.MARKER_CROSS, 26, 2)
        print(f"   빈 바닥: 화면의 {m.mean() * 100:.0f}%  / 내려놓을 자리 후보 {len(spots)}곳"
              + (f" (첫 자리 ({spots[0][0]}, {spots[0][1]}), 주변 여유 {spots[0][2]:.0f}px)" if spots else "  ← 못 찾음"))
        ok = ok and bool(spots)
    except Exception as e:
        print("   빈 바닥 찾기 오류:", e)
        ok = False
    path = os.path.join(HERE, "floor_debug.png")
    Image.fromarray(np.ascontiguousarray(img[:, :, ::-1])).save(path)
    print(f"   그림 저장: {path}")
    print("     밝은 곳 = 봇이 보는 빈 바닥 / 빨간 동그라미 = 찾은 재료 무더기")
    print("     노란 점 1, 2, 3… = 내려놓을 순서 / 빨간 + = 측정 때 찍은 버릴 곳")
    return ok


def t_spot(sct):
    spots = cc.empty_spots(sct)
    if not spots:
        print("\n결과: 내려놓을 빈 바닥을 못 찾음 (8번 그림으로 확인)")
        return False
    x, y, room = spots[0]
    am.smooth_move_to(x, y, 0.4, bow=6)
    print(f"\n결과: 마우스를 지금 내려놓을 자리 ({x}, {y}) 로 옮김 (주변 여유 {room:.0f}px) — 빈 바닥인지 눈으로 확인")
    return True


TESTS = {
    "1": ("아까비깡 먹기", t_eat),
    "2": ("20개 칸 버리기 — 하나만", lambda sct: t_drop(sct, 1)),
    "3": ("20개 칸 버리기 — 전부", lambda sct: t_drop(sct, None)),
    "4": ("바닥 재료 줍기", t_pick),
    "5": ("요리 1판", lambda sct: t_cook(sct, 1)),
    "6": ("한 바퀴 전체", t_cycle),
    "0": ("완성품 칸 아무거나 하나 버리기 (끌어다 놓기 시험)", t_drop_any),
    "7": ("아이템 창 읽기", t_read),
    "8": ("바닥 재료 / 빈 바닥 찾기", t_floor),
    "9": ("내려놓을 빈 자리로 마우스만", t_spot),
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
            print("0~9 중에서 고르세요")
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
