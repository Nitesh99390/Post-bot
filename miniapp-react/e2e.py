"""Playwright smoke test for the React Mini App (dev only). Run: python e2e.py [dark|light]
Needs: python tools/devserver.py 8080  +  npx vite preview --port 4173"""
import sys, json, asyncio, subprocess, time, urllib.request, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.devserver import init_data
from playwright.async_api import async_playwright

BASE = "http://localhost:4173"
OUT = Path("/tmp/shots")
STUB = """
window.__tg = {haptic: [], log: []};
window.Telegram = {WebApp: {
  initData: %s, colorScheme: %s, themeParams: {},
  ready(){}, expand(){}, close(){window.__tg.log.push('close')}, disableVerticalSwipes(){}, isVersionAtLeast(){return true},
  enableClosingConfirmation(){}, disableClosingConfirmation(){},
  setHeaderColor(){}, setBackgroundColor(){}, setBottomBarColor(){}, onEvent(){}, offEvent(){},
  BackButton:{show(){},hide(){}},
  HapticFeedback:{impactOccurred(s){window.__tg.haptic.push('impact:'+s)},notificationOccurred(t){window.__tg.haptic.push('notify:'+t)},selectionChanged(){window.__tg.haptic.push('select')}},
  openLink(u){window.__tg.log.push('link:'+u)}, openTelegramLink(u){window.__tg.log.push('tglink:'+u)},
}};
"""

def fresh_backend():
    """The dev backend keeps drafts, saved posts and chat rights in memory (and a failed send flips a chat to
    'bot can't post'), so every run gets a brand-new process to stay deterministic."""
    subprocess.run(["pkill", "-f", "[d]evserver.py 808[0]"], check=False)
    time.sleep(0.6)
    proc = subprocess.Popen([sys.executable, str(ROOT / "tools" / "devserver.py"), "8080"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen("http://localhost:8080/api/state", timeout=1)
        except urllib.error.HTTPError:
            return proc          # 401 = server is up (no initData sent)
        except Exception:
            time.sleep(0.2)
    raise SystemExit("dev backend did not start")

def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))
    return cond

async def box(page, sel):
    return await page.eval_on_selector(sel, "e=>{const r=e.getBoundingClientRect();return {t:r.top,b:r.bottom,l:r.left,r:r.right,h:r.height}}")

async def main(theme):
    errors, ok = [], True
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 390, "height": 780}, device_scale_factor=2, has_touch=True, is_mobile=True)
        page = await ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append("PAGEERR " + str(e)))
        await page.route("**/telegram-web-app.js", lambda r: r.fulfill(content_type="application/javascript", body=STUB % (json.dumps(init_data()), json.dumps(theme))))
        # tools/devserver.py's FakeBot returns messages without a `photo`, so the real /api/media cannot succeed
        # there. Stub ONLY that endpoint (contract = bot/api.py upload_media/get_media/delete_media).
        PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a52a1c4b0000000049454e44ae426082")
        DRAFT = {"media_type": "photo", "media_name": "pic.png", "splits": False, "empty": False, "chars": 0, "text": "", "buttons": [], "link_preview": True}
        async def media(route):
            m = route.request.method
            if m == "POST":
                await asyncio.sleep(0.4)
                await route.fulfill(content_type="application/json", body=json.dumps({"ok": True, "draft": DRAFT}))
            elif m == "GET":
                await route.fulfill(content_type="image/png", body=PNG)
            else:
                await route.fulfill(content_type="application/json", body=json.dumps({"ok": True, "draft": {**DRAFT, "media_type": None, "media_name": "", "empty": True}}))
        await page.route("**/api/media", media)
        await page.goto(BASE + "/")
        await page.wait_for_selector("nav[aria-label=Main]", timeout=10000)
        await page.wait_for_timeout(600)
        ok &= check("dark class matches theme", (await page.evaluate("document.documentElement.classList.contains('dark')")) == (theme == "dark"))

        # ---- floating bar vs bottom nav ----
        bar = await box(page, "button[aria-label='Choose groups'] >> xpath=../..")
        nav = await box(page, "nav[aria-label=Main]")
        ok &= check("action bar sits above nav (no overlap)", bar["b"] <= nav["t"] + 0.5, f"bar.bottom={bar['b']:.1f} nav.top={nav['t']:.1f} gap={nav['t']-bar['b']:.1f}")
        await page.screenshot(path=OUT / f"1-compose-{theme}.png")

        # ---- pb-36 on scroll container ----
        pb = await page.evaluate("getComputedStyle(document.querySelector('main > div.absolute.overflow-y-auto')).paddingBottom")
        ok &= check("scroll container has pb-36 (144px)", pb == "144px", pb)

        # ---- glass classes ----
        cls = await page.eval_on_selector("button[aria-label='Choose groups'] >> xpath=..", "e=>e.className")
        ok &= check("bar has backdrop-blur-lg + bg-white/80 + dark variants", all(k in cls for k in ["backdrop-blur-lg", "bg-white/80", "dark:bg-zinc-900/80", "border-slate-200/60", "dark:border-zinc-800"]))
        bf = await page.eval_on_selector("button[aria-label='Choose groups'] >> xpath=..", "e=>getComputedStyle(e).backdropFilter||getComputedStyle(e).webkitBackdropFilter")
        ok &= check("backdrop-filter computed", "blur" in (bf or ""), bf)

        # ---- toolbar: type, select, bold -> active solid ----
        await page.click("[role=textbox]")
        await page.keyboard.type("Big sale today! Visit our shop")
        await page.keyboard.press("Control+A")
        await page.click("button[aria-label=Bold]")
        await page.wait_for_timeout(200)
        pressed = await page.get_attribute("button[aria-label=Bold]", "aria-pressed")
        bg = await page.eval_on_selector("button[aria-label=Bold]", "e=>getComputedStyle(e).backgroundColor")
        ok &= check("Bold segment active + solid accent", pressed == "true" and bg != "rgba(0, 0, 0, 0)", f"{pressed} {bg}")
        html = await page.eval_on_selector("[role=textbox]", "e=>e.innerHTML")
        ok &= check("editor has <b>", "<b>" in html, html[:60])
        await page.click("button[aria-label=Code]")
        html = await page.eval_on_selector("[role=textbox]", "e=>e.innerHTML")
        ok &= check("Code wraps selection", "<code>" in html, html[:80])
        await page.click("button[aria-label=Code]")
        html = await page.eval_on_selector("[role=textbox]", "e=>e.innerHTML")
        ok &= check("Code toggles off", "<code>" not in html, html[:80])

        # ---- counter + sync ----
        await page.wait_for_timeout(1200)
        ok &= check("sync chip returns to Synced", await page.locator("[role=status]", has_text="Synced").count() == 1)

        # ---- link preview switch ----
        sw = page.locator("button[role=switch][aria-label='Link preview']")
        before = await sw.get_attribute("aria-checked")
        await sw.click()
        after = await sw.get_attribute("aria-checked")
        ok &= check("link-preview switch toggles", before != after, f"{before}->{after}")

        # ---- add link button ----
        await page.get_by_text("Add link button").click()
        await page.fill("input[placeholder^='Button text']", "Join channel")
        await page.fill("input[placeholder^='Link:']", "t.me/dailydeals")
        await page.get_by_role("button", name="Add button").click()
        await page.wait_for_timeout(300)
        ok &= check("button added", await page.get_by_text("Join channel").count() >= 1)

        # ---- attach photo (1x1 png) ----
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a52a1c4b0000000049454e44ae426082")
        await page.set_input_files("input[type=file]", files=[{"name": "pic.png", "mimeType": "image/png", "buffer": png}])
        await page.wait_for_selector("text=Photo attached", timeout=8000)
        ok &= check("photo attachment card shown", True)
        await page.evaluate("document.querySelector('main > div.absolute.overflow-y-auto').scrollTo(0,0)")
        await page.wait_for_timeout(400)
        await page.screenshot(path=OUT / f"2-compose-filled-{theme}.png")

        # ---- scroll to bottom: last section clear of bar ----
        await page.evaluate("const s=document.querySelector('main > div.absolute.overflow-y-auto');s.scrollTo(0,s.scrollHeight)")
        await page.wait_for_timeout(300)
        last = await box(page, "main section:last-of-type >> nth=0") if False else await page.evaluate("""()=>{const s=document.querySelector('main > div.absolute.overflow-y-auto');const secs=s.querySelectorAll('section');const l=secs[secs.length-1].getBoundingClientRect();const bar=document.querySelector(\"button[aria-label='Choose groups']\").parentElement.getBoundingClientRect();return {lb:l.bottom,bt:bar.top}}""")
        ok &= check("last section scrolls clear of action bar", last["lb"] <= last["bt"] + 0.5, f"section.bottom={last['lb']:.0f} bar.top={last['bt']:.0f}")
        await page.screenshot(path=OUT / f"3-compose-bottom-{theme}.png")

        # ---- Groups ----
        await page.get_by_role("button", name="Groups").last.click()
        await page.wait_for_timeout(500)
        await page.screenshot(path=OUT / f"4-groups-initial-{theme}.png")
        await page.get_by_role("button", name="All", exact=True).click()
        await page.wait_for_timeout(300)
        sub = await page.locator("text=/\\d+ of \\d+ selected/").inner_text()
        ok &= check("All selects postable chats", sub.startswith("3 of 4"), sub)
        await page.screenshot(path=OUT / f"5-groups-all-{theme}.png")
        bar = await box(page, "button[aria-label='Choose groups'] >> xpath=../..")
        nav = await box(page, "nav[aria-label=Main]")
        ok &= check("groups: bar above nav", bar["b"] <= nav["t"] + 0.5, f"gap={nav['t']-bar['b']:.1f}")
        await page.get_by_role("button", name="None", exact=True).click()
        ok &= check("None clears", "Nothing selected" in await page.locator("p[aria-live]").first.inner_text())
        await page.get_by_role("button", name="Default only").click()
        await page.wait_for_timeout(200)
        ok &= check("Default only selects 1", "1 of 4" in await page.locator("p[aria-live]").first.inner_text())
        await page.get_by_text("Crypto Alerts").first.click()   # a chat that will fail
        await page.get_by_text("Design Team").first.click()
        await page.wait_for_timeout(500)   # let selection debounce flush

        # ---- Send flow (confirm -> progress, one chat fails) ----
        await page.get_by_role("button", name="Send").first.click()
        try:
            await page.wait_for_selector("text=/Send to 3 chats/", timeout=5000)
        except Exception:
            await page.screenshot(path=OUT / f"debug-send-{theme}.png")
            print("DEBUG body:", (await page.inner_text("body"))[:600].replace("\n", " | "))
            raise
        await page.screenshot(path=OUT / f"6-confirm-{theme}.png")
        await page.get_by_role("button", name="Send now").click()
        await page.wait_for_selector("text=/Finished with issues|Posted!/", timeout=15000)
        await page.wait_for_timeout(400)
        await page.screenshot(path=OUT / f"7-progress-{theme}.png")
        ok &= check("send finished with 1 failed (Crypto Alerts)", await page.get_by_text("Retry 1 failed").count() == 1)
        await page.get_by_role("button", name="Close", exact=True).click()

        # ---- Saved ----
        await page.get_by_role("button", name="Compose").last.click()
        await page.get_by_role("button", name="Saved").last.click()
        await page.wait_for_timeout(300)
        await page.get_by_label("Save current draft").click()
        await page.fill("input[placeholder^='e.g.']", "Weekly update")
        await page.get_by_role("button", name="Save", exact=True).click()
        await page.wait_for_selector("text=Weekly update", timeout=5000)
        await page.wait_for_timeout(500)
        await page.screenshot(path=OUT / f"8-saved-{theme}.png")
        ok &= check("saved card has Edit + Delete", await page.get_by_role("button", name="Edit").count() == 1 and await page.get_by_role("button", name="Delete").count() == 1)
        bar_visible = await page.eval_on_selector("button[aria-label='Choose groups'] >> xpath=../..", "e=>getComputedStyle(e).opacity")
        ok &= check("action bar hidden on Saved", bar_visible == "0", bar_visible)
        await page.get_by_role("button", name="Delete").click()
        await page.wait_for_selector("text=/Delete \"Weekly update\"/")
        await page.screenshot(path=OUT / f"9-delete-sheet-{theme}.png")
        await page.get_by_role("button", name="Delete", exact=True).last.click()
        await page.wait_for_selector("text=Nothing saved", timeout=5000)
        ok &= check("delete removes card", True)

        # ---- Profile ----
        await page.get_by_role("button", name="Profile").last.click()
        await page.wait_for_timeout(600)
        await page.screenshot(path=OUT / f"10-profile-{theme}.png")
        txt = await page.inner_text("main")
        ok &= check("profile stats labels", all(k in txt for k in ["Posts sent", "Deliveries", "Groups", "Saved"]))
        grid = await page.evaluate("""()=>{const g=[...document.querySelectorAll('.grid-cols-2')][0];const k=[...g.children].map(c=>c.getBoundingClientRect());return {n:k.length,rows:new Set(k.map(r=>Math.round(r.top))).size,cols:new Set(k.map(r=>Math.round(r.left))).size}}""")
        ok &= check("bento is 2x2", grid == {"n": 4, "rows": 2, "cols": 2}, str(grid))
        await page.evaluate("document.querySelector('main > div.absolute.overflow-y-auto:not(.hidden)').scrollTo(0,99999)")
        await page.wait_for_timeout(300)
        await page.screenshot(path=OUT / f"11-profile-bottom-{theme}.png")

        # ---- haptics ----
        h = await page.evaluate("window.__tg.haptic")
        ok &= check("haptic impact:light fired", h.count("impact:light") >= 15, f"{h.count('impact:light')} light impacts, {len([x for x in h if x.startswith('notify')])} notifications")
        sw = page.locator("button[role=switch][aria-label='Haptic feedback']")
        await sw.click()   # turn OFF
        n0 = len(await page.evaluate("window.__tg.haptic"))
        await page.get_by_role("button", name="Groups").last.click()
        n1 = len(await page.evaluate("window.__tg.haptic"))
        ok &= check("haptic toggle off silences taps", n1 == n0, f"{n0}->{n1}")

        await b.close()
    real = [e for e in errors if "favicon" not in e]
    ok &= check("no console errors/warnings", not real, "; ".join(real)[:300])
    print("ALL PASS" if ok else "SOME FAILED")
    return ok

if __name__ == "__main__":
    backend = fresh_backend()
    try:
        result = asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "dark"))
    finally:
        backend.terminate()
    sys.exit(0 if result else 1)
