"""Headless UI smoke test with synthetic page data, no login or external requests.

Uses a readable shadow root only in this fixture; production keeps it closed.
The native control scripts are extracted unchanged from the kiosk's Python AST.
"""
import ast
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'app/thinksmart-kiosk.py').read_text(encoding='utf-8'))
functions = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
    and n.name.startswith('netease_')], type_ignores=[])
native = {'json': json}
exec(compile(functions, 'kiosk-music-functions', 'exec'), native)

FIXTURE = '''<!doctype html><meta charset="utf-8"><body>
<div id="g_player" class="m-playbar">
<div class="words"><a class="name">测试歌曲</a><span class="by"><a>测试歌手</a></span></div>
<a data-action="pause" class="pas" onclick="this.dataset.action=this.dataset.action==='pause'?'play':'pause';this.className=this.dataset.action==='pause'?'pas':'ply'">play</a>
<a data-action="mode" class="icn-loop" onclick="let a=['icn-loop','icn-one','icn-shuffle'];this.className=a[(a.indexOf(this.className)+1)%3]">mode</a>
<span class="time"><em>00:15</em> / 03:00</span></div>
<div class="listlyric"><p class="z-sel" data-time="0">这是测试歌词第一行</p><p data-time="20">这是测试歌词第二行</p></div>
<ul class="listbdc"><li data-id="1001" class="z-sel"><span class="col-2">测试歌曲</span><span class="col-3">测试歌手</span></li></ul>
<iframe id="g_iframe" srcdoc="<html><body></body></html>"></iframe>
</body>'''


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=os.environ.get('PLAYER_BROWSER_CHANNEL'))
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 800})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=FIXTURE))
            page.add_init_script('''
                const original=Element.prototype.attachShadow;
                Element.prototype.attachShadow=function(options){return original.call(this,{...options,mode:'open'});};
                window.testMessages=[];
                window.webkit={messageHandlers:{
                  thinksmartNav:{postMessage:m=>testMessages.push(JSON.parse(m))},
                  thinksmartPlayer:{postMessage:m=>testMessages.push(JSON.parse(m))}
                }};
            ''')
            # The route serves only the fixture; no traffic reaches the real music site.
            page.goto('https://music.163.com/', wait_until='networkidle')
            page.add_script_tag(content=(ROOT / 'app/kiosk-tools.js').read_text(encoding='utf-8'))
            host = page.locator('#thinksmart-music-home')
            expect(host.locator('#song-title')).to_have_text('测试歌曲')
            expect(host.locator('#lyric-current')).to_have_text('这是测试歌词第一行')
            # Inspect the rendered state before acting on its actual controls.
            button_labels = host.get_by_role('button').all_text_contents()
            assert '网易云登录 / 原页' in button_labels and '播放列表' in button_labels
            toggle = host.locator('#toggle')
            if not toggle.count():
                toggle = host.locator('button.control.main')
            expect(toggle).to_have_text('Ⅱ')
            toggle.click()
            assert page.evaluate('testMessages.some(x=>x.cmd==="control" && x.action==="pause")')
            page.evaluate(native['netease_control_script']('pause'))
            expect(toggle).to_have_text('▶', timeout=3000)
            toggle.click()
            page.evaluate(native['netease_control_script']('resume'))
            expect(toggle).to_have_text('Ⅱ', timeout=3000)
            page.evaluate("document.querySelectorAll('.listlyric p').forEach((p,i)=>p.classList.toggle('z-sel',i===1))")
            expect(host.locator('#lyric-current')).to_have_text('这是测试歌词第二行')
            host.locator('[data-mode="single"]').click()
            page.evaluate(native['netease_set_mode_script']('single'))
            expect(page.locator('#g_player [data-action="mode"]')).to_have_class('icn-one')
            host.get_by_role('button', name='播放列表', exact=True).click()
            expect(host.locator('#library-list')).to_contain_text('测试歌曲')
            host.locator('#library-back').click()
            host.get_by_role('button', name='网易云登录 / 原页', exact=True).click()
            expect(host.get_by_role('button', name='返回音乐播放器')).to_be_visible()
            host.get_by_role('button', name='返回音乐播放器').click()
            expect(host.locator('#song-title')).to_be_visible()
            screenshot = os.environ.get('PLAYER_SCREENSHOT')
            if screenshot:
                page.screenshot(path=screenshot)
            assert not errors, errors
            print('Player UI passed: mount, metadata, pause/resume, lyrics, mode, queue and login view.')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
