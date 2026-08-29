# -*- coding: utf-8 -*-
"""
'비정상적 입력' 이 어느 동작에서 뜨는지 찾는 진단 도구.

가구만들기에서 비정상적 입력 경고가 뜨는데, 원인이 아래 중 무엇인지 몰라서
하나씩 따로 시험해 봅니다. 각 시험은 아주 적은 동작만 하므로, 어떤 것에서
경고가 뜨는지 보면 원인이 바로 좁혀집니다.

■ 사용법
  1. 가구만들기 창을 열고 게임을 '시작' 해서 카드판이 보이게 함
     (카드가 안 보이면 1~4번은 그냥 빈 곳을 누르게 되니 의미가 없음)
  2. cmd 에서:  py input_test.py
  3. 아래 키를 하나 누르고, 경고가 뜨는지 봅니다. 뜨면 바로 F9 로 종료.
     한 번에 하나씩만 눌러보세요.

     F1 = 마우스만 움직임 (클릭 없음)           ← 이동만으로도 걸리는지
     F2 = 카드 1장 클릭 (딱 한 번)              ← 클릭 한 번으로 걸리는지
     F3 = 카드 3장을 사람 속도로 클릭 (1.5초 간격)
     F4 = 카드 6장을 봇 속도로 클릭 (0.6초 간격)
     F5 = 마우스를 순간이동시켜 클릭 (곡선 이동 없이)
     F6 = 화면 캡처만 100번 (마우스/키보드 입력 전혀 없음)

     --- F1~F6 이 전부 통과했다면, 양(누적)이 문제인지 확인 ---
     F7  = 봇 속도로 40번 클릭 (0.6초 간격)     ← 몇 번째에 뜨는지 보기
     F8  = 실제 봇 리듬으로 20턴 (2장씩)
     F10 = 느린 속도로 30번 클릭 (1.5초 간격)

     --- 카드 클릭이 전부 통과했다면, 카드 외의 동작 확인 ---
     F11 = '시작' 버튼 클릭      ← 봇이 제일 먼저 하는 동작
     F12 = 인벤토리 우클릭       ← 재료 넣기 동작
     F13 = 클릭 + 화면캡처 동시  ← 실제 봇과 같은 조합

     F9 = 종료

■ 결과로 알 수 있는 것
   F2 에서 이미 뜬다  → 프로그램이 만든 클릭 자체를 게임이 걸러냄
                        (움직임을 아무리 다듬어도 소용없음 = 다른 방법 필요)
   F3 은 괜찮고 F4 에서 뜬다 → 클릭이 너무 빠른 것이 문제 (간격을 늘리면 됨)
   F1 에서 뜬다       → 마우스 이동 방식이 문제
   F6 에서 뜬다       → 화면 캡처를 감지하는 것 (아주 드묾)
   전부 안 뜬다       → 오래 돌려야 뜨는 종류 (누적 감지)
"""

import sys
import time
import random
import threading

try:
    import mss
    import keyboard
    import pyautogui
except ImportError as e:
    print("[에러] 필요한 프로그램이 없습니다:", e)
    print("  py -m pip install mss numpy pyautogui keyboard pillow")
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)

try:
    import auto_match as am
except Exception as e:
    print("[에러] auto_match.py 를 못 불러왔습니다:", e)
    print("  auto_match.py 가 같은 폴더에 있어야 합니다.")
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

_alive = True
_busy = False


def cards(n):
    """시험에 쓸 카드 좌표 n개 (서로 떨어진 자리로)."""
    spots = [(0, 0), (0, 4), (4, 0), (4, 4), (2, 2), (1, 3), (3, 1), (0, 2)]
    return [am.card_center(r, c) for r, c in spots[:n]]


def guard(fn):
    """시험 중복 실행 방지."""
    def wrapper():
        global _busy
        if _busy:
            print("  (이전 시험이 아직 진행 중입니다)")
            return
        _busy = True
        try:
            fn()
        except pyautogui.FailSafeException:
            print("\n[비상정지] 마우스가 화면 구석으로 갔습니다.")
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            _busy = False
            print("  → 경고가 떴는지 확인하세요. 떴으면 F9 로 종료.\n")
    return wrapper


@guard
def t1_move_only():
    print("\n[F1] 마우스만 움직입니다 (클릭 없음) — 8번 이동")
    for p in cards(8):
        am.move_like_human(p[0], p[1])
        time.sleep(random.uniform(0.3, 0.6))


@guard
def t2_one_click():
    print("\n[F2] 카드 1장만 클릭합니다 (딱 한 번)")
    am.click_card(cards(1)[0])
    print("  클릭 1회 완료")


@guard
def t3_human_pace():
    print("\n[F3] 카드 3장을 사람 속도로 클릭합니다 (1.5초 간격)")
    for i, p in enumerate(cards(3), 1):
        am.click_card(p)
        print(f"  {i}번째 클릭")
        time.sleep(1.5)


@guard
def t4_bot_pace():
    print("\n[F4] 카드 6장을 봇 속도로 클릭합니다 (0.6초 간격)")
    for i, p in enumerate(cards(6), 1):
        am.click_card(p)
        print(f"  {i}번째 클릭")
        time.sleep(0.6)


@guard
def t5_teleport_click():
    print("\n[F5] 곡선 이동 없이 순간이동으로 클릭합니다 (3회)")
    for i, p in enumerate(cards(3), 1):
        pyautogui.moveTo(p[0], p[1])
        time.sleep(0.15)
        pyautogui.click()
        print(f"  {i}번째 클릭")
        time.sleep(1.2)


@guard
def t6_capture_only():
    print("\n[F6] 화면 캡처만 100번 합니다 (마우스/키보드 입력 없음)")
    with mss.mss() as sct:
        t0 = time.time()
        for i in range(100):
            am.read_board(sct)
            time.sleep(0.03)
        print(f"  캡처 100회 완료 ({time.time()-t0:.1f}초)")


@guard
def t7_volume():
    """양이 문제인지 — 봇 속도로 오래 클릭하며 몇 번째에 뜨는지 봄."""
    print("\n[F7] 봇 속도로 40번 클릭합니다 (0.6초 간격, 약 24초)")
    print("     경고가 뜨는 순간의 '번호'를 기억해 주세요!")
    spots = [am.card_center(r, c) for r in range(5) for c in range(5)]
    random.shuffle(spots)
    for i in range(1, 41):
        am.click_card(spots[(i - 1) % len(spots)])
        print(f"  {i}번째 클릭 ({0.6*i:.0f}초 경과)", flush=True)
        time.sleep(0.6)


@guard
def t8_real_rhythm():
    """실제 봇과 같은 리듬 — 두 장 연속으로 열고 잠깐 쉬는 것을 반복."""
    print("\n[F8] 실제 봇 리듬으로 20턴 (한 턴에 2장씩 = 40클릭)")
    print("     경고가 뜨는 순간의 '턴 번호'를 기억해 주세요!")
    spots = [am.card_center(r, c) for r in range(5) for c in range(5)]
    random.shuffle(spots)
    k = 0
    for turn in range(1, 21):
        for _ in range(2):                  # 한 턴에 두 장
            am.click_card(spots[k % len(spots)])
            k += 1
            time.sleep(random.uniform(0.25, 0.45))
        print(f"  {turn}번째 턴 완료 (누적 {k}클릭)", flush=True)
        time.sleep(random.uniform(0.5, 0.9))    # 턴 사이 쉬는 시간


@guard
def t9_slow_volume():
    """느리게 오래 — 간격을 넉넉히 줘도 양 때문에 걸리는지."""
    print("\n[F10] 느린 속도로 30번 클릭합니다 (1.5초 간격, 약 45초)")
    spots = [am.card_center(r, c) for r in range(5) for c in range(5)]
    random.shuffle(spots)
    for i in range(1, 31):
        am.click_card(spots[(i - 1) % len(spots)])
        print(f"  {i}번째 클릭 ({1.5*i:.0f}초 경과)", flush=True)
        time.sleep(1.5)


@guard
def t11_start_button():
    """봇이 제일 먼저 하는 동작 — 시작 버튼 클릭. (카드 클릭과 다른 함수를 씀)"""
    print("\n[F11] '시작' 버튼을 1번 클릭합니다")
    print(f"      좌표: {am.START_BTN}")
    print("      ※ 재료를 넣어서 시작을 누를 수 있는 상태여야 의미가 있습니다")
    am.human_click(am.START_BTN)
    print("  시작 버튼 클릭 완료")


@guard
def t12_right_click_item():
    """재료 넣기 동작 — 인벤토리 우클릭."""
    print("\n[F12] 인벤토리 첫 칸을 우클릭합니다 (재료 넣기와 같은 동작)")
    print(f"      좌표: {am.CELL1_CENTER}")
    am.right_click_item(am.CELL1_CENTER)
    print("  우클릭 완료")


@guard
def t13_click_and_capture():
    """클릭과 화면캡처를 동시에 — 실제 봇처럼 섞어서."""
    print("\n[F13] 클릭하면서 동시에 화면을 계속 캡처합니다 (실제 봇과 같은 조합)")
    print("      20번 클릭, 그 사이 계속 화면 읽기")
    spots = [am.card_center(r, c) for r in range(5) for c in range(5)]
    random.shuffle(spots)
    with mss.mss() as sct:
        for i in range(1, 21):
            am.click_card(spots[(i - 1) % len(spots)])
            t0 = time.time()
            while time.time() - t0 < 0.5:        # 실제 봇처럼 계속 읽기
                am.read_board(sct)
                time.sleep(0.04)
            print(f"  {i}번째 클릭 + 캡처", flush=True)


def quit_all():
    global _alive
    _alive = False
    print("\n종료합니다...")


def main():
    print("=" * 60)
    print(" 비정상적 입력 원인 찾기")
    print("=" * 60)
    print(" 가구만들기 창을 열고 게임을 '시작'해서 카드판이 보이게 한 뒤,")
    print(" 아래 키를 하나씩 눌러보세요. 경고가 뜨면 바로 F9.")
    print()
    print("   F1 = 마우스만 움직임 (클릭 없음)")
    print("   F2 = 카드 1장 클릭 (딱 한 번)")
    print("   F3 = 3장을 사람 속도로 (1.5초 간격)")
    print("   F4 = 6장을 봇 속도로 (0.6초 간격)")
    print("   F5 = 순간이동 후 클릭 (곡선 없이)")
    print("   F6 = 화면 캡처만 100번 (입력 없음)")
    print("   --- 위가 다 통과했다면 아래로 (양이 문제인지 확인) ---")
    print("   F7  = 봇 속도로 40번 클릭 (0.6초 간격, 약 24초)")
    print("   F8  = 실제 봇 리듬으로 20턴 (2장씩 = 40클릭)")
    print("   F10 = 느린 속도로 30번 클릭 (1.5초 간격, 약 45초)")
    print("   --- 카드 클릭이 전부 통과했다면, 카드 외의 동작 확인 ---")
    print("   F11 = '시작' 버튼 클릭 (봇이 제일 먼저 하는 동작)  ★유력")
    print("   F12 = 인벤토리 우클릭 (재료 넣기 동작)")
    print("   F13 = 클릭하면서 동시에 화면 캡처 (실제 봇과 같은 조합)")
    print("   F9 = 종료")
    print()
    print("   ※ F7/F8/F10 은 몇 번째에 경고가 뜨는지가 중요합니다.")
    print("     화면에 번호가 찍히니 뜨는 순간의 번호를 알려주세요.")
    print("=" * 60)
    print(f" 카드판 좌표: 1행1열 {am.CARD1_CENTER}, 간격 {am.CARD_PITCH_X}")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print()

    for key, fn in (("f1", t1_move_only), ("f2", t2_one_click),
                    ("f3", t3_human_pace), ("f4", t4_bot_pace),
                    ("f5", t5_teleport_click), ("f6", t6_capture_only),
                    ("f7", t7_volume), ("f8", t8_real_rhythm),
                    ("f10", t9_slow_volume), ("f11", t11_start_button),
                    ("f12", t12_right_click_item), ("f13", t13_click_and_capture)):
        keyboard.add_hotkey(key, lambda f=fn: threading.Thread(target=f, daemon=True).start())
    keyboard.add_hotkey("f9", quit_all)

    while _alive:
        time.sleep(0.2)
    print("끝.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
