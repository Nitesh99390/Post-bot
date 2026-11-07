"""Playwright smoke test of the Mini App against tools/devserver.py (dev only)."""
import sys, json, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.devserver import init_data
from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
OUT = Path("/tmp/shots")
STUB = """
window.__tg = {log: []};
window.Telegram = {WebApp: {
  initData: %s, colorScheme: %s, safeAreaInset:{top:0,bottom:0}, contentSafeAreaInset:{top:0,bottom:0},
  ready(){}, expand(){}, close(){window.__tg.log.push('close')}, disableVerticalSwipes(){}, isVersionAtLeast(){return true},
  enableClosingConfirmation(){window.__tg.log.push('confirm-on')}, disableClosingConfirmation(){window.__tg.log.push('confirm-off')},
  setHeaderColor(){}, setBackgroundColor(){}, setBottomBarColor(){}, onEvent(){}, BackButton:{show(){},hide(){}},
  HapticFeedback:{impactOccurred(){},notificationOccurred(){},selectionChanged(){}},
  openLink(u){window.__tg.log.push('link:'+u)}, openTelegramLink(u){window.__tg.log.push('tglink:'+u)},
}};
"""

async def main(theme="dark"):
    errors = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 390, "height": 800}, device_scale_factor=2, has_touch=True, is_mobile=True)
        page = await ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append("PAGEERR " + str(e)))
        await page.route("**/telegram-web-app.js", lambda r: r.fulfill(content_type="application/javascript", body=STUB % (json.dumps(init_data()), json.dumps(theme))))
        await page.goto(BASE + "/app/")
        await page.wait_for_selector("#app:not([hidden])", timeout=8000)
        await page.wait_for_timeout(900)
        await page.screenshot(path=OUT / f"1-compose-{theme}.png")

        # type with formatting, add button
        await page.click("#editor")
        await page.keyboard.type("Big sale today! Visit https://example.com now")
        await page.keyboard.press("Control+A"); await page.click('[data-fmt=bold]')
        await page.wait_for_timeout(900)
        await page.click('[data-act=openForm]'); await page.fill('#bLabel', 'Shop now'); await page.fill('#bUrl', 'example.com/shop')
        await page.click('[data-act=addButton]')
        await page.wait_for_timeout(1000)
        await page.screenshot(path=OUT / f"2-compose-filled-{theme}.png")

        # groups
        await page.click('[data-tab=groups]'); await page.wait_for_timeout(700)
        await page.screenshot(path=OUT / f"3-groups-{theme}.png")
        rows = await page.query_selector_all("#chatList .row")
        assert len(rows) == 4, len(rows)
        await page.click('[data-act=selAll]'); await page.wait_for_timeout(500)
        assert len(await page.query_selector_all("#chatList .row.sel")) == 3  # 4th can't post
        await page.screenshot(path=OUT / f"4-groups-all-{theme}.png")
        await page.click('#chatList .row:has-text("Design Team") .more'); await page.wait_for_timeout(700)
        await page.screenshot(path=OUT / f"5-menu-{theme}.png")
        await page.click('[data-act=makeDefault]'); await page.wait_for_timeout(700)
        d = await page.inner_text("#chatList .row:first-child")
        assert "default" in d.lower() and "Design Team" in d, d
        await page.click('[data-act=addChat]'); await page.wait_for_timeout(700)
        await page.screenshot(path=OUT / f"6-add-{theme}.png")
        await page.click('[data-act=closeSheet]'); await page.wait_for_timeout(600)

        # persistence of selection across reload
        await page.wait_for_timeout(600)
        await page.reload(); await page.wait_for_selector("#app:not([hidden])"); await page.wait_for_timeout(600)
        txt = await page.inner_text("#editor"); assert "Big sale" in txt, txt
        await page.click('[data-tab=groups]'); await page.wait_for_timeout(500)
        assert len(await page.query_selector_all("#chatList .row.sel")) == 3
        assert "default" in (await page.inner_text("#chatList .row:first-child")).lower()

        # send
        await page.click('[data-tab=compose]'); await page.wait_for_timeout(500)
        await page.click('[data-act=send]'); await page.wait_for_timeout(700)
        await page.screenshot(path=OUT / f"7-confirm-{theme}.png")
        await page.click('[data-act=confirmSend]'); await page.wait_for_timeout(500)
        await page.screenshot(path=OUT / f"8-progress-{theme}.png")
        await page.wait_for_selector('[data-act=retryFailed]', timeout=15000); await page.wait_for_timeout(500)
        await page.screenshot(path=OUT / f"9-result-{theme}.png")
        st = await page.eval_on_selector_all(".res .st", "e=>e.map(x=>x.className)")
        print("statuses", st)
        assert sum('ok' in s.split() for s in st) == 2 and sum('failed' in s.split() for s in st) == 1, st
        await page.click('[data-act=closeSheet]'); await page.wait_for_timeout(600)

        # saved + profile
        await page.click('[data-tab=saved]'); await page.wait_for_timeout(500)
        await page.click('[data-act=saveDraft]'); await page.fill('#saveName', 'Sale post'); await page.click('[data-act=saveYes]')
        await page.wait_for_timeout(900)
        await page.screenshot(path=OUT / f"10-saved-{theme}.png")
        assert "Sale post" in await page.inner_text("#view-saved")
        await page.click('[data-tab=profile]'); await page.wait_for_timeout(900)
        await page.screenshot(path=OUT / f"11-profile-{theme}.png")
        pt = await page.inner_text("#view-profile"); assert "Aarav Sharma" in pt and "@aarav_dev" in pt, pt
        await b.close()
    real = [e for e in errors if "telegram.org" not in e and "ERR_" not in e]
    print("console issues:", real)
    return real

if __name__ == "__main__":
    bad = asyncio.run(main(sys.argv[2] if len(sys.argv) > 2 else "dark"))
    sys.exit(1 if bad else 0)
