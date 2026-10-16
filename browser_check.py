"""Browser QA against an isolated database; never uses the user's saved records.
Run after installing requirements-dev.txt. Uses the installed Microsoft Edge.
"""
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import create_app
from create_sample_template import build
from models import UploadedDocument, db_session
from routes.helpers import get_schedule, upsert_entries


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    artifacts = Path('.qa').resolve()
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='logbook_browser_') as tmp:
        root = Path(tmp)
        app = create_app({'DATABASE_URI': 'sqlite:///' + str(root / 'test.db').replace('\\', '/'),
                          'UPLOAD_FOLDER': str(root / 'uploads'), 'GENERATED_FOLDER': str(root / 'generated'),
                          'EXPORT_FOLDER': str(root / 'exports'), 'TESTING': True, 'SECRET_KEY': 'browser-test'})
        with app.app_context():
            engine = db_session.get_bind()
        server = make_server('127.0.0.1', 0, app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(origin)
                page.get_by_role('heading', name='Small steps. Real progress.').wait_for()
                page.screenshot(path=str(artifacts / 'overview-empty.png'), full_page=True)
                with app.app_context():
                    upsert_entries([
                        {'date': '2026-09-01', 'task': 'Built the first playable prototype.', 'project': 'Cube Runner', 'tools': 'Unity, C#', 'learning': 'Component-based game architecture'},
                        {'date': '2026-09-02', 'task': 'Refined player movement and collision detection.', 'project': 'Cube Runner', 'tools': 'Unity, C#', 'learning': 'Rigidbody interactions'},
                        {'date': '2026-09-03', 'task': 'Designed the score display and pause menu.', 'project': 'Cube Runner', 'tools': 'Unity UI', 'learning': 'Responsive layouts'},
                        {'date': '2026-09-04', 'task': 'Tested gameplay and resolved input issues.', 'project': 'Cube Runner', 'tools': 'Unity, Git', 'learning': 'Debugging input events'},
                    ], get_schedule())
                page.reload()
                page.screenshot(path=str(artifacts / 'overview-desktop.png'), full_page=True)
                page.get_by_role('link', name='New daily entry', exact=True).click()
                page.locator('#date').fill('2026-09-07')
                page.wait_for_function("document.querySelector('#day').value === 'Monday'")
                page.locator('#task').fill('Browser-tested daily entry')
                page.locator('#project').fill('QA project')
                page.locator('#learning').fill('Verified the redesigned flow')
                page.screenshot(path=str(artifacts / 'daily-desktop.png'), full_page=True)
                page.get_by_role('button', name='Save entry', exact=True).click()
                page.wait_for_url('**/entries')
                page.locator('#entry-search').fill('Browser-tested')
                assert page.locator('#entries-body tr:visible').count() == 1
                page.locator('#entry-search').fill('no-such-record-xyz')
                assert page.locator('#search-empty').is_visible()
                page.get_by_role('button', name='Clear search').click()
                assert page.locator('#entries-body tr:visible').count() == 5
                page.screenshot(path=str(artifacts / 'entries-desktop.png'), full_page=True)
                page.goto(origin + '/weekly')
                page.locator('#week').fill('2')
                page.locator('#project').fill('Browser QA')
                page.locator('#progress').fill('Design, development, testing, review, polish, documentation')
                page.get_by_role('button', name='Distribute across days').click()
                page.wait_for_url('**/weekly/preview/*')
                first_row = page.locator('#records-body tr').first
                first_row.locator('[data-field=day]').fill('Friday')
                first_row.locator('[data-field=check_in]').fill('9am')
                page.get_by_role('button', name='Save changes', exact=True).click()
                page.wait_for_function("document.querySelector('#save-state').textContent.startsWith('Saved')")
                assert first_row.locator('[data-field=day]').input_value() == 'Monday'
                assert first_row.locator('[data-field=check_in]').input_value() == '09:00 AM'
                page.get_by_role('button', name='Save to database', exact=True).click()
                page.get_by_text('Saved to database:').wait_for()
                page.screenshot(path=str(artifacts / 'editor-desktop.png'), full_page=True)
                sample = build(output_file=str(root / 'sample.docx'))
                page.goto(origin + '/analyzer')
                page.locator('input[name=document]').set_input_files(sample)
                page.get_by_role('button', name='Upload & analyze').click()
                page.get_by_text('Uploaded documents', exact=True).wait_for()
                assert page.get_by_text('Attendance', exact=True).count() > 0
                page.screenshot(path=str(artifacts / 'templates-desktop.png'), full_page=True)
                page.goto(origin + '/generate')
                page.get_by_role('button', name='Preview changes').click()
                page.get_by_role('heading', name='Preview of changes').wait_for()
                page.get_by_role('button', name='Confirm and Generate', exact=True).click()
                page.get_by_role('heading', name='Document generated', exact=True).wait_for()
                assert len(list((root / 'generated').glob('*.docx'))) == 1
                page.goto(origin + '/json/import')
                page.locator('#json_text').fill(json.dumps({'date': '2026-09-01', 'task': 'JSON browser check'}))
                page.get_by_role('button', name='Validate & preview').click()
                json_preview = page.url.removeprefix(origin)
                page.get_by_role('heading', name='JSON validation & preview').wait_for()
                page.goto(origin + '/extract')
                page.get_by_role('button', name='Extract records').click()
                # A blank template has no populated rows; include empty dated rows.
                page.locator('#skip_empty').uncheck()
                page.get_by_role('button', name='Extract records').click()
                extraction_preview = page.url.removeprefix(origin)
                page.get_by_role('heading', name='Extraction preview', exact=True).wait_for()
                print('PASS browser: daily entry, search, weekly editor normalization, save, upload, generation, JSON import, extraction', flush=True)
                routes = ['/', '/daily', '/weekly', '/entries', '/json/import', '/analyzer', '/mappings', '/extract', '/generate', '/history', '/weekly/preview/1', json_preview, extraction_preview]
                for width, height in [(1440, 1000), (768, 1024), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    for route in routes:
                        response = page.goto(origin + route)
                        assert response.status == 200, (route, response.status)
                        overflow = page.evaluate('document.documentElement.scrollWidth > window.innerWidth + 1')
                        if overflow:
                            page.screenshot(path=str(artifacts / 'overflow.png'), full_page=True)
                            print(page.evaluate("Array.from(document.querySelectorAll('main,main *,.topbar')).filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0,15).map(e => ({tag:e.tagName, cls:e.className, width:e.getBoundingClientRect().width, right:e.getBoundingClientRect().right}))"), flush=True)
                        assert not overflow, f'Horizontal page overflow: {route} at {width}px'
                        # Every mutation form must carry a token; native forms still work without JS.
                        assert page.locator('form[method=post]').count() == page.locator('form[method=post] input[name=csrf_token]').count(), route
                    print(f'PASS browser: {len(routes)} pages at {width}px, no page overflow, all forms protected', flush=True)
                page.goto(origin)
                page.screenshot(path=str(artifacts / 'overview-mobile.png'), full_page=True)
                menu = page.get_by_role('button', name='Open navigation')
                menu.click()
                assert page.locator('body').evaluate("el => el.classList.contains('nav-open')")
                assert page.locator('main').evaluate('el => el.inert')
                page.keyboard.press('Escape')
                assert menu.get_attribute('aria-expanded') == 'false'
                assert menu.evaluate('el => document.activeElement === el')
                menu.click()
                page.locator('.nav').get_by_role('link', name='All entries').click()
                page.wait_for_url('**/entries')
                assert not page.locator('main').evaluate('el => el.inert')
                page.screenshot(path=str(artifacts / 'entries-mobile.png'), full_page=True)
                print('PASS browser: mobile navigation, Escape, focus restoration')
                assert not errors, errors
                print('PASS browser: no JavaScript errors')
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            db_session.remove()
            engine.dispose()
    print('Screenshots:', artifacts)


if __name__ == '__main__':
    main()
