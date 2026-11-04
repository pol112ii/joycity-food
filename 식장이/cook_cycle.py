# -*- coding: utf-8 -*-
"""
식장이 자동 반복 — 아까비깡 먹기 → 완성품 바닥에 버리기 → 재료 줍기 → 요리(재료 떨어질 때까지) → 반복

  ① 아이템 창에서 아까비깡을 전부 먹기          (마결자동 ring_cycle.py 와 똑같이)
  ② 아이템 창의 완성품을 바닥(버릴 자리)으로 끌어다 놓기
  ③ 방 바닥에서 재료 무더기 줍기               (마결자동과 똑같이)
  ④ 요리 — auto_cook.py 의 재료 넣기/요리를 그대로 써서 재료가 떨어질 때까지
  ⑤ ①로
리어카(팔기) 없음. 쉬는 시간 없음. 매크로 방지 확인 창이 뜨면 멈추고 텔레그램 알림 (macro_guard.py).
auto_cook.py / ring_cycle.py / auto_match.py 는 고치지 않고 그대로 불러다 씀 (부품).

■ 준비 (한 번만) — 사용법.txt 의 '식장이 사이클' 참고
  1. 식장이 봇(auto_cook.py)이 이 폴더에서 잘 돌아가는 상태 (cook_layout.json, items, RECIPE)
  2. items 폴더에 완성품 / 아까비깡 그림 등록 (py auto_cook.py 캡처 → 이름 바꾸기)
  3. 아래 DROP 에 버릴 완성품 이름 적기
  4. py measure_cook_cycle.py  → 아이템 창 / 바닥 재료 무더기 / 버릴 자리 재기
  5. py cook_cycle.py 점검     → 빠진 게 있으면 전부 한 번에 알려줌 (아무것도 안 누름)
■ 실행:  py cook_cycle.py     F8 = 시작/정지,  F9 = 종료
"""

import os
import sys
import time
import random
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import auto_cook as ac          # 식장이 요리 (그대로)
import auto_match as am         # 창 찾기 / 칸 그림 비교 (부품 — 식장이 측정값으로 씀)
am.LAYOUT_FILE = ac.LAYOUT_FILE # cook_layout.json (제목 / 제작 창 칸 위치)
import ring_cycle as rc         # 아이템 창 / 줍기 / 먹기 (마결자동 그대로)
import mss
import keyboard
import pyautogui

# ==================== 설정 (여기만 고치면 됨) ====================
# 이름은 items 폴더의 그림 이름과 글자 하나까지 똑같이
RECIPE = None                       # ← 요리 1번에 넣는 재료와 개수. None = auto_cook.py 에 적은 레시피 그대로
                                    #   직접 적으려면 예)  RECIPE = [("밀가루", 1), ("우유", 1), ("설탕", 1)]
PILES = None                        # ← 한 바퀴에 바닥에서 주울 무더기 수. None = 레시피 개수만큼 (재료 1개면 1무더기)
                                    #   바닥에서 안 줍고 인벤토리에 있는 것만 쓰려면 PILES = {}
DROP = ("완성품",)                  # ← 바닥에 버릴 완성품 (items 그림 이름). 여러 개면 ("빵", "케이크")
FOOD = "아까비깡"                   # 버리기 전에 아이템 창에서 전부 먹을 것. 안 먹으려면 FOOD = ""
MAX_ROUNDS = 20                     # 한 바퀴에 요리 최대 횟수 (재료가 먼저 떨어지면 거기서 끝)
DROP_SPREAD = (30, 15)              # 버릴 자리에서 이만큼(px) 안쪽으로 매번 조금씩 다르게 놓음 (좌우, 위아래)

running = False
alive = True


# ==================== 멈추기 / 다시 시작 (모든 부품에 같이 전달) ====================

def set_running(v):
    global running
    running = v
    rc.running = am.running = ac.running = v
    if not v:
        ac.retry_at = None


def set_alive(v):
    global alive
    alive = v
    rc.alive = am.alive = ac.alive = v


def on():
    return running and alive


class _Link:
    """매크로 방지 감시(macro_guard)와 연결 — 멈추기/다시 시작을 줍기·버리기·요리 모두에 전달.
    텔레그램 설정은 auto_cook.py 에 적힌 것을 씀."""
    am = am

    @property
    def running(self):
        return running

    @running.setter
    def running(self, v):
        set_running(v)

    @property
    def alive(self):
        return alive

    @property
    def TELEGRAM_TOKEN(self):
        return ac.TELEGRAM_TOKEN

    @property
    def TELEGRAM_CHAT_ID(self):
        return ac.TELEGRAM_CHAT_ID

    @property
    def NOTIFY_NAME(self):
        return ac.NOTIFY_NAME

    def release_keys(self):
        ac.release_keys()


# ==================== 설정을 부품에 넘기기 ====================

_recipe = []
_piles = {}


def apply_settings():
    global _recipe, _piles
    _recipe = [(str(n), int(c)) for n, c in (RECIPE if RECIPE is not None else ac.RECIPE)]
    if PILES is not None:
        _piles = dict(PILES)
    else:
        _piles = {}
        for n, c in _recipe:
            _piles[n] = _piles.get(n, 0) + c
    ac.RECIPE = list(_recipe)
    ac.LOOP = True
    rc.RECIPE = list(_recipe)
    rc.PILES = dict(_piles)
    rc.SELL = tuple(DROP)               # (그림 확인용 — 리어카에 팔지는 않음)
    rc.FOOD = FOOD or "아까비깡"
    rc.MAX_ROUNDS = MAX_ROUNDS
    rc.REST = False
    if not FOOD:
        rc.eat_all = lambda sct: None


_orig_scan = ac._scan_with_retries


def _scan_stacked(sct, templates):
    """한 칸에 쌓인 재료도 레시피 개수만큼 쓸 수 있게 함 (예: 버섯 x2 인데 버섯 칸이 하나뿐일 때).

    auto_cook 은 '재료 칸 수 ≥ 넣을 개수' 여야 넣기를 시작해서, 한 칸에 20개가 있어도
    부족으로 보고 멈춤. 그래서 같은 칸을 개수만큼 후보로 적어둠 — 넣다가 칸이 비면
    auto_cook 이 바로 알아채고 다시 스캔함 (auto_cook.py 파일은 안 고침, 사이클에서만).
    """
    found, diffs = _orig_scan(sct, templates)
    need = {}
    for n, c in _recipe:
        need[n] = need.get(n, 0) + c
    for n, c in need.items():
        cells = found.get(n, [])
        if 0 < len(cells) < c:
            found[n] = (cells * c)[:c]
    return found, diffs


def load_am_layout():
    """auto_match 부품이 식장이 측정값(cook_layout.json)을 쓰게 함 (식장이 창 = card)."""
    lay = am.load_layout()
    if lay is not None:
        lay["titles"].setdefault("card", lay["titles"].get("cook", "식장이"))
    return lay


# ==================== 준비 점검 ====================

RING_POINTS = ("item_icon", "item_first", "item_row1_last", "item_row5_first", "drop_spot")


def precheck():
    """시작 전에 준비가 다 됐는지 전부 확인해서 한 번에 보여줌. 다 됐으면 True (아무것도 안 누름)."""
    import json
    apply_settings()
    bad = []

    def item(ok, what, fix=""):
        print(f"  {'✓' if ok else '✗'} {what}" + ("" if ok else f"\n      → {fix}"))
        if not ok:
            bad.append(what)

    print("\n[준비 점검]")
    lay = ac.load_layout()
    load_am_layout()
    item(lay is not None, "cook_layout.json (식장이 창 위치)", "py measure_cook.py")
    plan = [n for n, c in _recipe for _ in range(c)]
    item(bool(plan), "레시피: " + (", ".join(f"{n} x{c}" for n, c in _recipe) or "없음")
         + (" (auto_cook.py 에서 가져옴)" if RECIPE is None else ""),
         "auto_cook.py 의 RECIPE (또는 cook_cycle.py 맨 위 RECIPE) 에 재료 이름과 개수 적기")
    item(len(plan) <= ac.NUM_SLOTS, f"레시피 재료 수 {len(plan)} ≤ 재료 칸 {ac.NUM_SLOTS}",
         "auto_cook.py 의 NUM_SLOTS 확인")
    tpl = ac.load_templates()
    need = [n for n, _ in _recipe] + list(DROP)
    miss = [n for n in need if n not in tpl]
    item(not miss, "items 폴더 그림: " + ", ".join(need),
         f"없는 것: {', '.join(miss)} — 제작 창을 띄우고  py auto_cook.py 캡처  → 이름 바꾸기"
         + (" (DROP 에 버릴 완성품 이름을 적었는지도 확인)" if any(n in DROP for n in miss) else ""))
    if FOOD and FOOD in tpl:
        item(True, f"items 폴더 그림: {FOOD}")
    elif FOOD:
        print(f"  △ items 폴더 그림: {FOOD} 없음 — 먹기를 건너뜀"
              f"\n      → 인벤토리에 {FOOD}이(가) 있을 때 py auto_cook.py 캡처 → 이름 바꾸기")
    rl = None
    if os.path.exists(rc.LAYOUT_FILE):
        try:
            with open(rc.LAYOUT_FILE, encoding="utf-8") as f:
                rl = json.load(f)
        except Exception:
            rl = None
    item(rl is not None, "ring_layout.json (아이템 아이콘 / 아이템 창 칸 / 바닥 재료 / 버릴 자리)",
         "py measure_cook_cycle.py")
    if rl is not None:
        pts, spr = rl.get("points", {}), rl.get("sprites", {})
        miss = [n for n in RING_POINTS if n not in pts]
        item(not miss, "  아이템 아이콘 / 아이템 창 칸 / 버릴 자리",
             f"py measure_cook_cycle.py (빠진 것: {', '.join(miss)})")
        nofloor = [n for n in _piles if "spr_" + n not in spr
                   or not os.path.exists(os.path.join(rc.SPRITE_DIR, spr["spr_" + n]["file"]))]
        item(not nofloor, "바닥 무더기 그림: " + (", ".join(_piles) or "줍기 안 함"),
             f"없는 것: {', '.join(nofloor)} — 바닥에 무더기를 두고  py measure_cook_cycle.py → 3번")
    try:
        import cv2  # noqa: F401
        item(True, "opencv-python")
    except Exception:
        item(False, "opencv-python", "cmd 에서  py -m pip install opencv-python")
    print("  " + ("→ 준비 끝!" if not bad else f"→ ✗ 표시 {len(bad)}개를 고치고 다시 실행하세요"))
    return not bad


def load():
    if not precheck():
        return False
    if not rc.load():                       # 아이콘 / 바닥 그림 읽기
        return False
    load_am_layout()                        # (rc.load 가 다시 읽으므로 식장이 창 제목을 한 번 더 넣음)
    ac._scan_with_retries = _scan_stacked
    print("레시피:", ", ".join(f"{n} x{c}" for n, c in _recipe),
          "/ 줍기:", ", ".join(f"{n} {p}무더기" for n, p in _piles.items()) or "안 함",
          "/ 버리기:", ", ".join(DROP) or "안 함")
    return True


# ==================== ② 완성품 버리기 ====================

def drop_products(sct):
    """아이템 창의 완성품(DROP)을 하나씩 버릴 자리로 끌어다 놓음. 다 버렸으면 True.

    버리면 칸이 당겨질 수 있어서 매번 아이템 창을 새로 읽고, 완성품 칸 수가 줄었는지 확인.
    """
    if not DROP:
        return True
    left, fails, n_drop = None, 0, 0
    for _ in range(40):
        if not on():
            return False
        cells = [pos for pos, n in rc.item_contents(sct) if n in DROP]
        if left is not None:
            if len(cells) < left:
                n_drop += 1
                fails = 0
            else:
                fails += 1
                print("  [버리기] 안 버려진 것 같음 → 다시")
                if fails >= 2:
                    print("[문제] 완성품을 끌어다 놓아도 안 버려짐 — 버릴 자리(measure_cook_cycle.py 4번) 확인")
                    return False
        if not cells:
            break
        left = len(cells)
        x, y = rc.main_pt("drop_spot")
        dst = (x + random.randint(-DROP_SPREAD[0], DROP_SPREAD[0]),
               y + random.randint(-DROP_SPREAD[1], DROP_SPREAD[1]))
        print(f"  [버리기] 완성품 → 바닥 ({dst[0]}, {dst[1]})  (남은 칸 {left})")
        ac.human_drag(cells[0], dst)
    if n_drop:
        print(f"[버리기] 완성품 {n_drop}칸 버림")
    ac._scan_cache = None                   # 칸 배치가 바뀌었으니 요리 봇이 새로 스캔하게
    am._scan_cache = None
    return True


# ==================== ④ 요리 ====================

def cook_all(sct):
    """재료가 떨어질 때까지 요리. 끝낸 판 수 반환 (-1 = 오류로 멈춤)."""
    apply_settings()
    ac._scan_cache = None
    # 등록된 그림 전부로 인벤토리를 읽음 — 완성품/아까비깡 같은 다른 물건을 재료로 착각하지 않게
    tpl = ac.load_templates()
    done = fails = 0
    while on() and done < MAX_ROUNDS:
        if not ac.craft_open(sct):
            print("제작 창이 닫혀있음 → 다시 열기")
            if not ac.reopen_window(sct):
                return -1
        left = ac.filled_slot_list(sct, ac.NUM_SLOTS)
        if left:
            # 지난번에 넣다 만 재료가 칸에 남아 있음 → 그대로 넣으면 레시피가 틀어짐
            print(f"  [재료 확인] 넣기 전인데 칸 {[i + 1 for i in left]} 에 재료가 남아 있음 → 제작 창 닫고 다시")
            ac._scan_cache = None
            fails += 1
            if not rc.close_craft(sct) or fails >= 3:
                print("[중단] 남은 재료가 안 빠짐")
                return -1
            continue
        if not ac.fill_slots(sct, tpl):
            if not on():
                return done
            ac._scan_cache = None
            if ac.filled_slot_list(sct, ac.NUM_SLOTS):
                rc.close_craft(sct)          # 넣다 만 재료는 제작 창을 닫아서 돌려받음
            got = [n for _, n in rc.item_contents(sct)]
            have = {n: got.count(n) for n, _ in _recipe}
            out = [n for n, _ in _recipe if have.get(n, 0) == 0]
            fails += 1
            if not out and fails < 2:
                print(f"  재료를 다 못 넣음 (재료는 있음: {have}) → 한 번 더")
                continue
            short = out[0] if out else None
            if short in _piles:
                rc._short.add(short)
            print(f"[요리] 재료를 다 못 넣음 → {done}판 하고 이번 바퀴 끝"
                  + (f" (모자란 것: {short})" if short else ""))
            return done
        if not ac.cook_one_round(sct):
            if not on():
                return done
            fails += 1
            print(f"  [문제] 요리가 정상 종료되지 않음 ({fails}/3)")
            if fails >= 3:
                return -1
            ac.checkup(sct)
            continue
        done += 1
        fails = 0
        _stats["rounds"] += 1
        print(f"★ 요리 {done}판째 완료 (누적 {_stats['rounds']}판)")
        time.sleep(random.uniform(1.0, 2.0))
    return done


_stats = {"rounds": 0}


# ==================== 반복 ====================

def worker():
    try:
        if not load():
            set_alive(False)
            return
        print("준비 완료 — F8 로 시작")
        cycle = zero = recover = 0
        with mss.mss() as sct:
            while alive:
                if not running:
                    time.sleep(0.15)
                    continue
                set_running(True)
                cycle += 1
                print(f"\n========== {cycle}바퀴째 ==========")
                problem = None
                n = 0
                rc.eat_all(sct)
                if not on():
                    continue
                if not drop_products(sct):
                    problem = "버리기"
                elif not rc.pick_up(sct):
                    problem = "줍기"
                else:
                    ac._scan_cache = None
                    n = cook_all(sct)
                    if n < 0:
                        problem = "요리"
                ac.release_keys()
                if not running:                     # F8 / 매크로 방지 창으로 멈춘 것 — 실패 아님
                    continue
                if problem:
                    recover += 1
                    if recover > rc.RECOVER_MAX:
                        set_running(False)
                        recover = 0
                        print(f"⏸ {problem} 실패가 {rc.RECOVER_MAX + 1}번 연속 — 멈춤. 화면 확인 후 F8")
                        continue
                    print(f"[복구] {problem} 실패 → 게임 창 정리하고 처음부터 다시 ({recover}/{rc.RECOVER_MAX})")
                    rc.close_game_windows(sct)
                    time.sleep(random.uniform(1.5, 2.5))
                    continue
                recover = 0
                zero = zero + 1 if n == 0 else 0
                if zero >= 3:
                    set_running(False)
                    zero = 0
                    print("⏸ 3바퀴 연속 한 판도 못 해서 멈춤 — 바닥 재료/화면 확인 후 F8")
    except pyautogui.FailSafeException:
        print("\n[비상정지] 마우스가 화면 구석으로 갔습니다. 완전히 종료합니다.")
        set_alive(False)
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        set_alive(False)
    finally:
        ac.release_keys()


def toggle():
    set_running(not running)
    ac._scan_cache = None
    print("\n▶ 시작됨" if running else "\n⏸ 정지됨 (지금 하던 동작이 끝나면 멈춤)")


def quit_all():
    set_running(False)
    set_alive(False)
    print("\n종료합니다...")


def main():
    print("=" * 56)
    print(" 식장이 자동 반복 (먹기 → 버리기 → 줍기 → 요리)")
    print(" F8 = 시작/정지    F9 = 종료")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print(" ※ auto_cook.py 와 동시에 켜지 마세요")
    print("=" * 56)
    keyboard.add_hotkey("f8", toggle)
    keyboard.add_hotkey("f9", quit_all)
    try:
        import macro_guard              # 매크로 방지 확인 창이 뜨면 멈추고 알림
        macro_guard.start(_Link())
    except Exception as e:
        print(f" (매크로 방지 창 감시를 못 켬: {e})")
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    while alive:
        time.sleep(0.2)
    print("끝.")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "점검":
            precheck()                  # 준비가 다 됐는지만 확인 (아무것도 안 누름)
        else:
            main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
