# -*- coding: utf-8 -*-
"""
의장이 자동 반복 — 줍기 → 의장이(박음질) → 먹기 → 팔기 → 다시 줍기 ...

  ① 방 바닥에서 재료 줍기                     (마결자동 ring_cycle.py 와 똑같이)
  ② 의장이 — 재료 넣기 → 넣은 재료 확인 → 시작 → 박음질 (auto_sew.py 그대로) — 재료가 떨어질 때까지
  ③ 아이템 창에서 아까비깡을 전부 먹기       (마결자동과 똑같이)
  ④ 능력 → 고물소환 → 리어카맨 클릭 → 완성품 팔기 → 닫기   (마결자동과 똑같이, 리어카맨 따라가기 포함)
  ⑤ ①로

쉬는 시간 없음. 매크로 방지 확인 창이 뜨면 멈추고 텔레그램으로 알림 (macro_guard.py).
ring_cycle.py / auto_sew.py / auto_match.py 는 고치지 않고 그대로 불러다 씀 (부품).

■ 준비 (한 번만) — 사용법.txt 의 10번 참고
  1. 의장이 봇(auto_sew.py)이 이 폴더에서 잘 돌아가는 상태 (match_layout.json, items 폴더)
  2. 아래 설정에 SELL(팔 것) 적기 (레시피는 비워 두면 auto_sew.py 에 적은 것 그대로)
  3. py measure_cycle.py  → 마결자동 폴더의 측정값을 가져오고, 바닥 재료 무더기 그림만 잼
  4. py sew_cycle.py 점검  → 빠진 게 있으면 전부 한 번에 알려줌 (아무것도 안 누름)
■ 실행:  py sew_cycle.py     F8 = 시작/정지,  F9 = 종료
"""

import os
import sys
import time
import random
import threading
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ring_cycle as rc         # 줍기 / 먹기 / 리어카맨 팔기 / 창 정리 (마결자동 그대로)
import auto_sew as sew          # 의장이 박음질 (그대로)
import auto_match as am         # 제작 창 열기 / 재료 넣기 (그대로)
import numpy as np
import mss
import keyboard
import pyautogui

# ==================== 설정 (여기만 고치면 됨) ====================
# 이름은 items 폴더의 그림 이름과 글자 하나까지 똑같이 (py auto_match.py 캡처 → 이름 바꾸기)
RECIPE = None                       # ← 의장이 1번에 넣는 재료와 개수. None = auto_sew.py 에 적은 레시피 그대로
                                    #   직접 적으려면 예)  RECIPE = [("실", 1), ("천조각", 1), ("단추", 1)]
NUM_SLOTS = 3                       # 제작 창 재료 칸 수
PILES = None                        # ← 한 바퀴에 바닥에서 주울 무더기 수. None = 레시피 개수만큼 (재료 1개면 1무더기)
                                    #   직접 적으려면 예)  PILES = {"실": 1, "천조각": 1, "단추": 1}
                                    #   바닥에서 안 줍고 인벤토리에 있는 것만 쓰려면 PILES = {}
SELL = ("완성품",)                  # ← 리어카맨에게 팔 것 (items 그림 이름). 안 팔려면 SELL = ()
FOOD = "아까비깡"                   # 팔기 전에 아이템 창에서 전부 먹을 것. 안 먹으려면 FOOD = ""
MAX_ROUNDS = 20                     # 한 바퀴에 의장이 최대 횟수 (재료가 먼저 떨어지면 거기서 끝)
SELL_AT = (5, 10)                   # 완성품이 이 사이 개수(매번 랜덤)만큼 쌓이면 팔러 감 (딱 정하려면 10)
CHECK_SLOTS = True                  # 재료를 넣은 뒤 칸마다 레시피와 같은지 확인하고 시작
                                    # (다르면 제작 창을 닫아 재료를 돌려받고 다시 넣음)
SLOT_LOOSE = 1.4                    # 재료 확인 때 칸 그림이 기준보다 이만큼(배)까지 흐려도 레시피 재료로 봄
GAME_FAIL_STOP = 3                  # 의장이가 연속 이만큼 실패(점수 못 채움)하면 이번 바퀴를 멈추고 정리

running = False
alive = True


# ==================== 멈추기 / 다시 시작 (모든 부품에 같이 전달) ====================

def set_running(v):
    global running
    running = v
    rc.running = am.running = sew.running = v


def set_alive(v):
    global alive
    alive = v
    rc.alive = am.alive = sew.alive = v


def on():
    return running and alive


def release_keys():
    for k in (sew.LEFT_KEY, sew.RIGHT_KEY):
        try:
            keyboard.release(k)
        except Exception:
            pass


class _Link:
    """매크로 방지 감시(macro_guard)와 연결 — 멈추기/다시 시작을 줍기·팔기·박음질 모두에 전달."""
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

    def release_keys(self):
        release_keys()


# ==================== 설정을 부품에 넘기기 ====================

_recipe = []          # 실제로 쓰는 레시피 / 무더기 (설정이 None 이면 auto_sew.py 에서 가져옴)
_piles = {}


def apply_settings():
    global _recipe, _piles
    _recipe = [(str(n), int(c)) for n, c in (RECIPE if RECIPE is not None else sew.RECIPE)]
    if PILES is not None:
        _piles = dict(PILES)
    else:
        _piles = {}
        for n, c in _recipe:
            _piles[n] = _piles.get(n, 0) + c
    rc.RECIPE = list(_recipe)
    rc.NUM_SLOTS = NUM_SLOTS
    rc.PILES = dict(_piles)
    rc.SELL = tuple(SELL)
    rc.FOOD = FOOD or "아까비깡"     # (그림이 없으면 마결자동 쪽에서 경고만 함)
    rc.MAX_ROUNDS = MAX_ROUNDS
    rc.SELL_AT = SELL_AT
    rc.REST = False                  # 쉬는 시간 없음
    sew.REST = False
    if not FOOD:
        rc.eat_all = lambda sct: None
    am.RECIPE = list(_recipe)
    am.NUM_SLOTS = NUM_SLOTS


RING_POINTS = ("item_icon", "job_icon", "ability_icon", "item_first", "item_row1_last", "item_row5_first",
               "summon", "ability_close", "cart_body", "sell_first", "sell_row1_last", "sell_row5_first",
               "sell_btn", "sell_close")


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
    lay = am.load_layout()
    item(lay is not None, "match_layout.json (의장이 창 위치)", "py measure_sew.py")
    if lay is not None:
        pts = lay.get("points", {})
        miss = [n for n in ("job_act", "slot1", "slot2", "cell_first", "cell_row1_last", "cell_row5_first", "start")
                if n not in pts]
        item(not miss, "  직업활동 / 재료 칸 / 인벤토리 / 시작 버튼 위치",
             f"py measure_sew.py 로 다시 (빠진 것: {', '.join(miss)})")
        item(am._norm(lay.get("titles", {}).get("card", "")) == am._norm("의장이"),
             "  의장이용 측정값인지", "주장이 폴더 것을 복사한 듯 — 이 폴더에서 py measure_sew.py")
    plan = [n for n, c in _recipe for _ in range(c)]
    placeholder = any(n.startswith("재료") for n, _ in _recipe)
    item(bool(plan) and not placeholder,
         "레시피: " + (", ".join(f"{n} x{c}" for n, c in _recipe) or "없음")
         + (" (auto_sew.py 에서 가져옴)" if RECIPE is None else ""),
         "sew_cycle.py 맨 위 RECIPE 에 재료 이름과 개수 적기 (또는 auto_sew.py 의 RECIPE)")
    item(len(plan) <= NUM_SLOTS, f"레시피 재료 수 {len(plan)} ≤ 재료 칸 {NUM_SLOTS}", "RECIPE / NUM_SLOTS 확인")
    tpl = am.load_templates()
    need = [n for n, _ in _recipe] + list(SELL)
    miss = [n for n in need if n not in tpl]
    item(not miss, "items 폴더 그림: " + ", ".join(need),
         f"없는 것: {', '.join(miss)} — 제작 창을 띄우고  py auto_match.py 캡처  → 이름 바꾸기"
         + (" (SELL 에 팔 물건 이름을 적었는지도 확인)" if any(n in SELL for n in miss) else ""))
    if FOOD and FOOD in tpl:
        item(True, f"items 폴더 그림: {FOOD}")
    elif FOOD:                              # 먹을 것 그림은 없어도 시작은 함 (먹기만 건너뜀)
        print(f"  △ items 폴더 그림: {FOOD} 없음 — 팔기 전에 먹기를 건너뜀 (체력이 모자라면 고물소환이 안 됨)"
              f"\n      → 인벤토리에 {FOOD}이(가) 있을 때 py auto_match.py 캡처 → 이름 바꾸기"
              f"  (py measure_cycle.py 가 마결자동 폴더에서 가져올 수도 있음)")
    rl = None
    if os.path.exists(rc.LAYOUT_FILE):
        try:
            with open(rc.LAYOUT_FILE, encoding="utf-8") as f:
                rl = json.load(f)
        except Exception:
            rl = None
    item(rl is not None, "ring_layout.json (아래 메뉴 / 아이템 창 / 능력 창 / 리어카맨 / 되팔기 창)",
         "py measure_cycle.py  (마결자동 폴더의 측정값을 찾아서 가져옴)")
    if rl is not None:
        pts, spr = rl.get("points", {}), rl.get("sprites", {})
        miss = [n for n in RING_POINTS if n not in pts]
        item(not miss, "  메뉴 아이콘 / 창 칸 / 리어카맨 위치", f"py measure_cycle.py (빠진 것: {', '.join(miss)})")
        nofloor = [n for n in _piles if "spr_" + n not in spr
                   or not os.path.exists(os.path.join(rc.SPRITE_DIR, spr["spr_" + n]["file"]))]
        item(not nofloor, "바닥 무더기 그림: " + (", ".join(_piles) or "줍기 안 함"),
             f"없는 것: {', '.join(nofloor)} — 바닥에 무더기를 두고  py measure_cycle.py → 4번")
        if SELL:
            ok = "cart_label" in spr and os.path.exists(os.path.join(rc.SPRITE_DIR, spr["cart_label"]["file"]))
            item(ok, "리어카맨 이름 그림", "py measure_cycle.py → 5번 (또는 마결자동의 ring_sprites 폴더 복사)")
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
    if not sew.check_layout():
        return False
    if not rc.load():                              # 아이콘 / 바닥 그림 / 리어카맨 그림 읽기
        return False
    sew.load_learned()
    print("레시피:", ", ".join(f"{n} x{c}" for n, c in _recipe),
          "/ 줍기:", ", ".join(f"{n} {p}무더기" for n, p in _piles.items()) or "안 함",
          "/ 팔기:", ", ".join(SELL) or "안 함")
    return True


# ==================== ② 의장이 ====================

def inv_count(sct):
    """아이템 창에서 레시피 재료별 칸 수."""
    got = [n for _, n in rc.item_contents(sct)]
    return {n: got.count(n) for n, _ in _recipe}


def read_slots(sct):
    """재료 칸마다 (읽은 이름, 가장 비슷한 그림, 차이값).  읽은 이름: '' 빈 칸 / None 모르는 것."""
    am.apply_craft_layout()
    names = rc.all_names()
    out = []
    for i in range(NUM_SLOTS):
        if not am.slot_filled(sct, i):
            out.append(("", None, 0.0))
            continue
        pos = (int(am.SLOT1_CENTER[0] + i * am.SLOT_PITCH_X), int(am.SLOT1_CENTER[1]))
        region = am.grab_cell(sct, pos[0], pos[1])
        best, bd = None, 1e9
        for n in names:
            for t in rc._tpl.get(n, []):
                d = am.match_region(region, t)
                if d < bd:
                    best, bd = n, d
        ok = best is not None and bd <= am.threshold_for(best)
        out.append((best if ok else None, best, bd))
    return out


def save_slot_debug(sct):
    """재료 확인이 안 맞을 때 제작 창을 slot_debug.png 로 저장 (분홍 네모 = 재료 칸을 읽은 자리)."""
    try:
        from PIL import Image, ImageDraw
        w = am.find_win("craft")
        if w is None:
            return
        img = Image.fromarray(rc.shot_bgr(sct, w.left, w.top, w.width, w.height)[:, :, ::-1])
        d = ImageDraw.Draw(img)
        h = am.CELL_SIZE // 2
        for i in range(NUM_SLOTS):
            x = am.SLOT1_CENTER[0] + i * am.SLOT_PITCH_X - w.left
            y = am.SLOT1_CENTER[1] - w.top
            d.rectangle([x - h, y - h, x + h, y + h], outline=(255, 0, 255), width=2)
        img.save(os.path.join(HERE, "slot_debug.png"))
        print("  → 제작 창을 slot_debug.png 로 저장 (분홍 네모 = 재료 칸을 읽은 자리)")
    except Exception as e:
        print("  (그림 저장 실패:", e, ")")


def check_slots(sct):
    """재료를 넣은 뒤, 시작 전에 칸마다 레시피대로 들어갔는지 확인. 맞으면 True.

    칸마다 등록된 그림 전부와 비교해서 가장 잘 맞는 것으로 읽음.
    레시피에 없는 것 / 못 알아본 것 / 개수가 다른 것이 있으면 False (시작 안 함).
    (칸 그림이 기준보다 살짝 흐려도, 가장 비슷한 게 레시피 재료이고 기준의 SLOT_LOOSE 배 안이면 그 재료로 봄
     — 다른 등록된 물건으로 읽히면 그건 확실히 틀린 것)
    """
    plan = [n for n, c in _recipe for _ in range(c)]
    am.park_mouse()                            # 커서가 칸을 가리지 않게
    for look in range(3):                      # 막 넣은 직후엔 칸이 반짝일 수 있어서 몇 번 봄
        slots = read_slots(sct)
        names = [s[0] for s in slots]
        for i, (n, guess, d) in enumerate(slots):
            if n is None and guess in plan and d <= am.threshold_for(guess) * SLOT_LOOSE:
                names[i] = guess
        if Counter(n for n in names if n) == Counter(plan) and None not in names:
            break
        time.sleep(0.4)
    shown = " / ".join(("빈 칸" if n == "" else f"{n if n else '?'}({d:.0f})")
                       for n, (_, _, d) in zip(names, slots))
    if Counter(n for n in names if n) == Counter(plan) and None not in names:
        print(f"  [재료 확인] {shown} → 레시피와 같음 ✓")
        return True
    print(f"  [재료 확인] 칸: {shown}  /  레시피: {', '.join(plan)}  → 다름! 시작 안 함")
    for i, (n, guess, d) in enumerate(slots):
        if n is None:
            print(f"    {i + 1}번 칸: 못 알아봄 (가장 비슷한 것 '{guess}' 차이 {d:.0f}, 기준 {am.threshold_for(guess)})"
                  " — 레시피에 없는 물건이 들어갔거나, 그 재료 그림을 다시 캡처해야 함")
    save_slot_debug(sct)
    return False


def craft_all(sct):
    """재료가 떨어질 때까지 의장이. 성공한 판 수 반환 (-1 = 오류로 멈춤)."""
    apply_settings()
    am.JOB_KEY = None                     # 마결자동처럼 아래 메뉴 직업 아이콘을 누름 (F2 대신)
    am._scan_cache = None
    # 등록된 그림 전부로 인벤토리를 읽음 — 완성품/아까비깡 같은 다른 물건을 재료로 착각하지 않게
    tpl = {n: rc._tpl[n] for n in rc.all_names() if n in rc._tpl}
    done = played = fails = lost = 0
    while on() and played < MAX_ROUNDS:
        w = sew.find_game_win()
        if w is None:
            am.JOB_BTN = rc.main_pt("job_icon")
            if not am.open_furniture_window(sct):
                return -1
            left = am.filled_slots(sct, NUM_SLOTS)
            if left:
                # 지난번에 넣다 만 재료가 칸에 남아 있음 → 그대로 넣으면 레시피가 틀어짐
                print(f"  [재료 확인] 넣기 전인데 칸 {[i + 1 for i in left]} 에 뭔가 남아 있음 → 제작 창 닫고 다시")
                am._scan_cache = None
                fails += 1
                if not rc.close_craft(sct) or fails >= 3:
                    print("[중단] 남은 재료가 안 빠짐")
                    return -1
                continue
            if not am.fill_slots(sct, tpl):
                if not on():
                    return done
                # 넣다가 실패 → 이미 넣은 재료는 칸에 남음. 무엇이 모자랐는지 보고, 창을 닫아서 돌려받음
                plan = [n for n, c in _recipe for _ in range(c)]
                for n, _, _ in read_slots(sct):
                    if n in plan:
                        plan.remove(n)
                am._scan_cache = None
                if not rc.close_craft(sct):
                    return -1
                have = inv_count(sct)
                out = [n for n, _ in _recipe if have.get(n, 0) == 0]
                fails += 1
                if not out and fails < 2:
                    print(f"  재료를 다 못 넣음 (재료는 있음: {have}) → 제작 창 다시 열어서 한 번 더")
                    continue
                short = out[0] if out else (plan[0] if plan else None)
                if short in _piles:
                    rc._short.add(short)
                print(f"[의장이] 재료를 다 못 넣음 → {done}번 성공하고 이번 바퀴 끝"
                      + (f" (모자란 것: {short}" + (" → 다음 바퀴에 한 무더기 더 주움)" if short in _piles else ")")
                         if short else ""))
                return done
            if CHECK_SLOTS and not check_slots(sct):
                print("  → 제작 창을 닫아서 재료를 돌려받고 처음부터 다시 넣음")
                am._scan_cache = None
                fails += 1
                if not rc.close_craft(sct) or fails >= 3:
                    print("[중단] 재료가 계속 레시피와 다르게 들어감 — slot_debug.png 와 cmd 창 내용을 보내주세요")
                    return -1
                continue
            w = sew.start_game(sct)
            if w is None:
                fails += 1
                if fails >= 3:
                    return -1
                continue
        else:
            print("  의장이 창이 이미 떠 있음 → 바로 박음질")
        res = sew.play_game(sct, w)
        t0 = time.time()
        while sew.find_game_win() is not None and time.time() - t0 < 3:
            time.sleep(0.2)
        if not on():
            return done
        played += 1
        fails = 0
        _stats["games"] += 1
        if res["ok"]:
            done += 1
            lost = 0
            _stats["wins"] += 1
            print(f"★ 의장이 {done}번째 성공 (점수 {res['score']:.0f} · {res['secs']:.0f}초 · 누름 {res['presses']}번"
                  f" · 빨간 실 {res['pen']}번)  누적 성공 {_stats['wins']}/{_stats['games']}")
        else:
            lost += 1
            print(f"✗ 의장이 실패 (점수 {res['score']:.0f} · {res['secs']:.0f}초 · 빨간 실 {res['pen']}번)"
                  f"  누적 성공 {_stats['wins']}/{_stats['games']}")
            if lost >= GAME_FAIL_STOP:
                print(f"[중단] 의장이가 {GAME_FAIL_STOP}판 연속 실패 — sew_debug.png 와 cmd 창 내용을 보내주세요")
                return -1
        time.sleep(random.uniform(1.0, 2.0))
    return done


_stats = {"games": 0, "wins": 0}


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
                if not rc.sell_all(sct):
                    problem = "팔기"
                elif not rc.pick_up(sct):
                    problem = "줍기"
                else:
                    n = craft_all(sct)
                    if n < 0:
                        problem = "의장이"
                release_keys()
                if problem:
                    if not running:                 # F8 / 매크로 방지 창으로 멈춘 것 — 실패 아님
                        continue
                    recover += 1
                    if recover > rc.RECOVER_MAX:
                        set_running(False)
                        recover = 0
                        print(f"⏸ {problem} 실패가 {rc.RECOVER_MAX + 1}번 연속 — 멈춤. 화면 확인 후 F8")
                        continue
                    # 멈추지 않고: 조이톡 말고 게임 안에 뜬 창을 다 닫고 처음부터 다시
                    print(f"[복구] {problem} 실패 → 게임 창 정리하고 처음부터 다시 ({recover}/{rc.RECOVER_MAX})")
                    rc.close_game_windows(sct)
                    time.sleep(random.uniform(1.5, 2.5))
                    continue
                if not running:
                    continue
                recover = 0
                zero = zero + 1 if n == 0 else 0
                if zero >= 3:
                    set_running(False)
                    zero = 0
                    print("⏸ 3바퀴 연속 하나도 성공 못 해서 멈춤 — 재료/화면 확인 후 F8")
    except pyautogui.FailSafeException:
        print("\n[비상정지] 마우스가 화면 구석으로 갔습니다. 완전히 종료합니다.")
        set_alive(False)
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        set_alive(False)
    finally:
        release_keys()


def toggle():
    set_running(not running)
    am._scan_cache = None
    print("\n▶ 시작됨" if running else "\n⏸ 정지됨 (지금 하던 동작이 끝나면 멈춤)")


def quit_all():
    set_running(False)
    set_alive(False)
    print("\n종료합니다...")


def main():
    sew.hires_timer()
    print("=" * 56)
    print(" 의장이 자동 반복 (줍기 → 의장이 → 먹기 → 팔기)")
    print(" F8 = 시작/정지    F9 = 종료")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print(" ※ auto_sew.py 와 동시에 켜지 마세요")
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
