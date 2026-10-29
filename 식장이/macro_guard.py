# -*- coding: utf-8 -*-
"""
'매크로 방지 확인' 창 감시 — 뜨면 봇을 바로 멈추고 텔레그램으로 계속 알림.

  - 1초마다 조이톡 창을 봐서 확인 창(남색 상자 + 파란 [확인] 버튼 + 빨간 '남은 시간')을 찾음
  - 찾으면: 봇 정지 · 키 떼기 → 텔레그램에 확인 창 사진 + 1초마다 알림 메시지
  - 텔레그램에 숫자 4자리를 답장하면 봇이 입력칸에 치고 [확인]을 누름
    (숫자를 읽는 건 사람 — 봇은 받은 숫자를 대신 쳐주기만 함. 다른 답장은 알림만 멈춤)
    컴퓨터가 여러 대면 '3042 규남' 처럼 이름 일부를 붙이면 그 컴퓨터만 입력
  - 확인 창이 사라지면(입력 완료) 잠깐 쉬었다가 하던 걸 이어서 함
  - 40초가 지나도 안 사라지면 정지한 채로 둠 (접속이 끊겼을 수 있음)

봇이 화면의 숫자를 읽지는 않음 (사람이 보낸 숫자만 입력).
시험:  py auto_cook.py 매크로검사   (지금 화면에 확인 창이 있는지만 검사하고 그림 저장)
"""

import os
import time
import json
import threading

import numpy as np

CHECK_SEC = 1.0          # 감시 간격(초)
ALERT_EVERY = 1.0        # 텔레그램 알림 간격(초) — 텔레그램은 1초에 1번보다 자주 보내면 막힘
ALERT_SECS = 32          # 알림을 계속 보내는 최대 시간(초) — 확인 창 제한시간 30초
GIVE_UP_SECS = 45        # 이만큼 지나도 확인 창이 안 사라지면 정지한 채로 둠
RESUME_WAIT = (3, 6)     # 확인 창이 사라진 뒤 다시 시작하기까지 쉬는 시간(초)
MAIN_TITLE = "조이톡"     # 게임 본 창 제목 (이 창 안에서 찾음. 못 찾으면 주 모니터 전체)

HERE = os.path.dirname(os.path.abspath(__file__))


# ==================== 화면에서 확인 창 찾기 ====================

def _largest_box(mask, cell=4):
    """mask 를 cell 단위로 줄여서 가장 큰 덩어리의 (x0, y0, x1, y1, 채움비율)."""
    h, w = mask.shape
    H, W = h // cell, w // cell
    if H < 4 or W < 4:
        return None
    m = mask[:H * cell, :W * cell].reshape(H, cell, W, cell).mean(axis=(1, 3)) > 0.5
    seen = np.zeros_like(m)
    best = None
    for y in range(H):
        for x in range(W):
            if not m[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            n = 0
            y0 = y1 = y
            x0 = x1 = x
            while stack:
                cy, cx = stack.pop()
                n += 1
                y0, y1, x0, x1 = min(y0, cy), max(y1, cy), min(x0, cx), max(x1, cx)
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < H and 0 <= nx < W and m[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if best is None or n > best[0]:
                best = (n, x0, y0, x1, y1)
    if best is None:
        return None
    n, x0, y0, x1, y1 = best
    fill = n / float((x1 - x0 + 1) * (y1 - y0 + 1))
    return x0 * cell, y0 * cell, (x1 + 1) * cell, (y1 + 1) * cell, fill


def detect(img):
    """img: 조이톡 창 그림(RGB). 확인 창이 있으면 그 상자 (x0, y0, x1, y1), 없으면 None."""
    a = img.astype(np.int16)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    h, w = R.shape
    navy = (B >= 28) & (B <= 95) & (B - R >= 8) & (B - G >= 5) & (R <= 60) & (G <= 75)
    if navy.mean() < 0.03:
        return None
    box = _largest_box(navy, cell=max(4, w // 160))
    if box is None:
        return None
    x0, y0, x1, y1, fill = box
    bw, bh = x1 - x0, y1 - y0
    if not (0.15 * w <= bw <= 0.65 * w and 0.25 * h <= bh <= 0.85 * h):
        return None
    if fill < 0.5 or not (0.6 <= bh / max(bw, 1) <= 1.6):
        return None
    if abs((x0 + x1) / 2 - w / 2) > 0.25 * w:
        return None
    # 빨간 '남은 시간' 글자 (상자 가운데 높이)
    mid = a[y0 + int(bh * 0.4):y0 + int(bh * 0.75), x0:x1]
    r, g, b = mid[..., 0], mid[..., 1], mid[..., 2]
    red = ((r > 140) & (g < 115) & (b < 115) & (r - g > 60)).sum()
    # 아래쪽 파란 [확인] 버튼 (가로로 길게 파란 줄)
    low = a[y0 + int(bh * 0.7):y1, x0:x1]
    r, g, b = low[..., 0], low[..., 1], low[..., 2]
    blue_rows = ((b - r > 20) & (b > 50)).mean(axis=1) > 0.55
    run = best = 0
    for v in blue_rows:
        run = run + 1 if v else 0
        best = max(best, run)
    scale = max(1.0, bw / 300.0)
    if red >= 12 * scale or best >= max(3, int(bh * 0.04)):
        return (x0, y0, x1, y1)
    return None


def main_rect(bot):
    """조이톡 본 창의 (left, top, width, height). 못 찾으면 주 모니터."""
    try:
        if bot._gw is not None:
            want = "".join(MAIN_TITLE.split())
            for w in bot._gw.getAllWindows():
                if "".join(str(w.title).split()).startswith(want) and w.width > 300 and w.height > 300 \
                        and not getattr(w, "isMinimized", False) and w.left > -10000:
                    return w.left, w.top, w.width, w.height
    except Exception:
        pass
    return None


def grab(sct, rect):
    if rect is None:
        mon = sct.monitors[1]
        rect = (mon["left"], mon["top"], mon["width"], mon["height"])
    l, t, w, h = rect
    s = sct.grab({"left": int(l), "top": int(t), "width": int(w), "height": int(h)})
    return np.asarray(s)[:, :, :3][:, :, ::-1].copy()      # RGB


def save_png(img, name):
    try:
        from PIL import Image
        Image.fromarray(img.astype(np.uint8)).save(os.path.join(HERE, name))
    except Exception:
        pass


def jpeg_bytes(img, enlarge=1):
    import io
    from PIL import Image
    im = Image.fromarray(img.astype(np.uint8))
    if enlarge != 1:
        im = im.resize((im.width * enlarge, im.height * enlarge))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ==================== 텔레그램 ====================

def _tg_ok(bot):
    return bool(getattr(bot, "TELEGRAM_TOKEN", "") and getattr(bot, "TELEGRAM_CHAT_ID", ""))


def _latest_update(bot):
    """가장 최근 텔레그램 메시지의 (update_id, chat_id, 글자). 실패하면 None."""
    try:
        url = f"https://api.telegram.org/bot{bot.TELEGRAM_TOKEN}/getUpdates?offset=-1&timeout=0"
        resp = bot._tg_urlopen(url, timeout=5)
        res = json.loads(resp.read().decode()).get("result", [])
        if not res:
            return (0, "", "")
        u = res[-1]
        msg = u.get("message") or {}
        return (u.get("update_id", 0), str((msg.get("chat") or {}).get("id", "")),
                (msg.get("text") or "").strip())
    except Exception:
        return None


def _send(bot, text):
    try:
        bot._send_telegram(text)
        return True
    except Exception as e:
        if "429" in str(e):            # 너무 자주 보냄 → 잠깐 쉼
            time.sleep(2)
        return False


def parse_code(text, name):
    """답장에서 숫자 4자리 → '1234'. 이름이 붙어 있으면(예: '3042 규남') 이 컴퓨터일 때만."""
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 4:
        return None
    rest = "".join(ch for ch in text if not ch.isdigit() and not ch.isspace())
    if rest and rest not in name:
        return None
    return digits


# ==================== 확인 창이 떴을 때 ====================

def parts(img, box):
    """확인 창 안의 (입력칸 가운데, [확인] 버튼 가운데) — 창 그림 좌표."""
    x0, y0, x1, y1 = box
    bh = y1 - y0
    a = img[y0:y1, x0:x1].astype(np.int16)
    blue = ((a[..., 2] - a[..., 0] > 20) & (a[..., 2] > 50)).mean(axis=1) > 0.55
    rows = [y for y in range(int(bh * 0.7), bh) if blue[y]]
    by = (rows[0] + rows[-1]) / 2 if rows else bh * 0.90
    iy = bh * 0.695 if not rows else min(bh * 0.695, rows[0] - bh * 0.15)
    cx = (x0 + x1) / 2
    return (cx, y0 + iy), (cx, y0 + by)


def enter_code(bot, rect, box, img, code):
    """사람이 보낸 숫자를 입력칸에 치고 [확인]을 누름."""
    l, t = (rect[0], rect[1]) if rect else (0, 0)
    (ix, iy), (bx, by) = parts(img, box)
    bw = box[2] - box[0]
    bot.human_click((int(l + ix), int(t + iy)), jx=int(bw * 0.15), jy=2)
    time.sleep(np.random.uniform(0.2, 0.4))
    for ch in code:
        bot.keyboard.write(ch)
        time.sleep(np.random.uniform(0.08, 0.22))
    time.sleep(np.random.uniform(0.2, 0.4))
    bot.human_click((int(l + bx), int(t + by)), jx=int(bw * 0.2), jy=2)


def handle(bot, sct, rect, box, img):
    name = getattr(bot, "NOTIFY_NAME", "")
    was_running = bot.running or bot.retry_at is not None
    bot.running = False
    bot.retry_at = None
    try:
        bot.release_keys()
    except Exception:
        pass
    t0 = time.time()
    print("\n" + "!" * 56)
    print(" 🚨 매크로 방지 확인 창이 떴어요 — 봇을 멈췄습니다.")
    print("    숫자 4자리를 PC 에서 직접 입력하거나, 텔레그램으로 숫자를 보내주세요 (30초 안에)")
    print("!" * 56)
    save_png(img, "macro_debug.png")

    def cur():
        r = main_rect(bot) or rect
        im = grab(sct, r)
        return r, im, detect(im)

    tg = _tg_ok(bot)
    base_id = 0
    if tg:
        u = _latest_update(bot)
        base_id = u[0] if u else 0
        x0, y0, x1, y1 = box
        crop = img[y0:y1, x0:x1]
        def _photo(c=crop):
            try:
                bot._send_telegram_photo(
                    f"🚨🚨 [{name}] 매크로 방지 확인 창! 숫자 4자리를 답장으로 보내면 봇이 입력하고 [확인]을 누름"
                    f" (PC에서 직접 입력해도 됨)", jpeg_bytes(c, 2 if c.shape[1] < 500 else 1))
            except Exception as e:
                print(f"  (텔레그램 사진 전송 실패: {e})")
        threading.Thread(target=_photo, daemon=True).start()

    acked = False
    last_alert = 0.0
    n = 0
    gone_since = None
    while bot.alive and time.time() - t0 < GIVE_UP_SECS:
        now = time.time()
        if tg and not acked and now - t0 < ALERT_SECS and now - last_alert >= ALERT_EVERY:
            n += 1
            last_alert = now
            left = max(0, int(30 - (now - t0)))
            _send(bot, f"🚨 [{name}] 매크로 방지 창! 남은 약 {left}초 — 숫자 4자리 답장 ({n})")
        if tg:
            u = _latest_update(bot)
            if u and u[0] > base_id and u[1] == str(bot.TELEGRAM_CHAT_ID):
                base_id = u[0]
                code = parse_code(u[2], name)
                if code:
                    acked = True
                    r, im, b = cur()
                    if b is not None:
                        print(f"  텔레그램으로 받은 숫자 {code} 입력 → [확인]")
                        try:
                            enter_code(bot, r, b, im, code)
                        except Exception as e:
                            print(f"  (입력 실패: {e})")
                        time.sleep(1.5)
                        r, im, b = cur()
                        if b is not None:
                            _send(bot, f"⚠ [{name}] {code} 입력했는데 확인 창이 그대로예요 — 숫자를 다시 보내주세요")
                            try:
                                bot._send_telegram_photo(f"[{name}] 지금 확인 창",
                                                         jpeg_bytes(im[b[1]:b[3], b[0]:b[2]], 2))
                            except Exception:
                                pass
                elif u[2]:
                    if not acked:
                        _send(bot, f"[{name}] 알림 멈춤 — 숫자 4자리를 보내면 입력해요 (PC에서 직접 해도 됨)")
                    acked = True
        r, im, b = cur()
        if b is None:
            gone_since = gone_since or time.time()
            if time.time() - gone_since >= 1.5:
                break
        else:
            gone_since = None
        time.sleep(0.4)

    if gone_since is None or time.time() - gone_since < 1.5:
        print("[정지] 확인 창이 안 사라짐 — 봇은 멈춘 상태로 둡니다 (확인 후 F8)")
        if tg:
            _send(bot, f"🛑 [{name}] 매크로 방지 창이 안 풀렸어요 — 봇 정지 상태 (접속 끊겼을 수 있음)")
        return
    wait = np.random.uniform(*RESUME_WAIT)
    print(f"✅ 확인 창 사라짐 — {wait:.0f}초 뒤 이어서 진행")
    if tg:
        _send(bot, f"✅ [{name}] 매크로 방지 통과 — {wait:.0f}초 뒤 이어서 진행")
    time.sleep(wait)
    if was_running and bot.alive and not bot.running:
        bot.running = True
        print("▶ 다시 시작")


def _watch(bot):
    import mss
    hits = 0
    with mss.mss() as sct:
        while bot.alive:
            time.sleep(CHECK_SEC)
            if not (bot.running or bot.retry_at is not None):
                hits = 0
                continue
            try:
                rect = main_rect(bot)
                img = grab(sct, rect)
                box = detect(img)
            except Exception:
                continue
            if box is None:
                hits = 0
                continue
            hits += 1
            if hits < 2:                       # 두 번 연속 보일 때만 (잘못 알아보는 것 방지)
                time.sleep(0.3)
                continue
            hits = 0
            try:
                handle(bot, sct, rect, box, img)
            except Exception as e:
                print(f"  (매크로 방지 처리 중 오류: {e})")


def start(bot):
    threading.Thread(target=_watch, args=(bot,), daemon=True).start()
    print(" 매크로 방지 확인 창 감시 중 — 뜨면 봇을 멈추고 " +
          ("텔레그램으로 계속 알림" if _tg_ok(bot) else "알림 (텔레그램 설정이 없어서 화면에만)"))


def selftest(bot):
    """지금 화면에 확인 창이 있는지 검사하고 macro_test.png 로 저장."""
    import mss
    with mss.mss() as sct:
        rect = main_rect(bot)
        img = grab(sct, rect)
    box = detect(img)
    save_png(img, "macro_test.png")
    print(f"조이톡 창: {rect if rect else '못 찾음 → 주 모니터 전체'}")
    print("확인 창: " + (f"있음 {box}" if box else "없음") + "  (macro_test.png 저장)")
