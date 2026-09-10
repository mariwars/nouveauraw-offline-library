"""Resumable personal offline archive of publicly accessible NouveauRaw pages."""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import html
import json
import re
import shutil
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
BASE = "https://nouveauraw.com/"
LOCAL = threading.local()
DISK_LOCK = threading.Lock()
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif", ".pdf"}
SKIP = ("/wp-admin", "/wp-login", "/wp-json", "/comment-subscriptions", "/feed", "/cart", "/checkout", "/estore", "/donations", "/mailpoet", "/my-favorite", "/tag/", "/author/")
CSS = """body{font:18px/1.65 Georgia,serif;color:#263a2e;background:#f6f4ed;margin:0}main{max-width:940px;margin:auto;background:white;padding:35px}a{color:#366e45}img{max-width:100%;height:auto!important}table{max-width:100%;display:block;overflow:auto}h1,h2,h3{line-height:1.25}header{font:15px/1.5 system-ui;padding:15px;background:#e4ecdf}input,select{font:18px system-ui;padding:10px;max-width:90%}li{margin:8px 0}.note{font:14px system-ui;color:#576155}iframe{display:none}@media(max-width:600px){main{padding:18px}}@media print{header{display:none}main{padding:0}a{color:inherit}}"""


CSS += '@media(max-width:600px){main p,main li{text-align:left!important}}'


def canonical(value, base=BASE):
    p = urlsplit(urljoin(base, value))
    # The site's former CDN mirrors the same WordPress upload paths.
    if p.hostname == 'd3qs7nqmro3u9a.cloudfront.net' and p.path.startswith('/wp-content/uploads/'):
        p = p._replace(netloc='nouveauraw.com', query='')
    if p.hostname not in {"nouveauraw.com", "www.nouveauraw.com"}:
        return None
    path = re.sub('/+', '/', p.path or '/')
    if any(path.startswith(s) for s in SKIP):
        return None
    if p.query and not all(x.startswith('utm_') for x in p.query.split('&')):
        return None
    if path.endswith('/feed/') or '/comment-page-' in path or '/attachment/' in path:
        return None
    return urlunsplit(('https', 'nouveauraw.com', path, '', ''))


def page_path(url):
    slug = re.sub(r'[^a-zA-Z0-9_-]', '-', unquote(urlsplit(url).path).strip('/'))[:105] or 'home'
    return 'pages/' + slug + '-' + hashlib.sha256(url.encode()).hexdigest()[:10] + '.html'


def asset_path(url):
    ext = Path(urlsplit(url).path).suffix.lower()
    return 'assets/' + hashlib.sha256(url.encode()).hexdigest()[:24] + (ext if ext in IMAGE_EXT else '.bin')


def fetch(url):
    if not hasattr(LOCAL, 'session'):
        LOCAL.session = requests.Session()
        LOCAL.session.headers['User-Agent'] = 'Mozilla/5.0 (compatible; PersonalOfflineArchive/1.0)'
    error = ''
    for attempt in range(3):
        try:
            time.sleep(.15)
            r = LOCAL.session.get(url, timeout=(12, 35))
            if r.status_code in {404, 410, 401, 403}:
                r.raise_for_status()
            r.raise_for_status()
            return r.content, r.headers.get('Content-Type', ''), r.url
        except Exception as exc:
            error = str(exc)
            if '404' in error or '410' in error or '403' in error or '401' in error:
                break
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(error)


def download_page(url):
    path = ROOT / 'originals' / Path(page_path(url)).name
    try:
        if path.exists():
            data = path.read_bytes()
        else:
            data, mime, final = fetch(url)
            if 'html' not in mime:
                return {'url': url, 'error': 'Not HTML: ' + mime}
            path.write_bytes(data)
        soup = BeautifulSoup(data, 'lxml')
        title = soup.title.get_text(' ', strip=True).split(' | ')[0] if soup.title else url
        content = soup.select_one('.post') or soup.select_one('.container') or soup.body or soup
        for node in content.select('#comments, #respond, #footer, #relevanssi_related, .postmetadata, .navi, .wpfp-span, script, style, form, nav, noscript'):
            node.decompose()
        text = content.get_text(' ', strip=True)
        links = set()
        assets = set()
        for a in content.select('a[href]'):
            u = canonical(a['href'], url)
            if not u:
                continue
            ext = Path(urlsplit(u).path).suffix.lower()
            if ext in IMAGE_EXT:
                assets.add(u)
            elif not ext and '/wp-content/' not in u:
                links.add(u)
        for img in content.select('img'):
            src = img.get('data-src') or img.get('data-lazy-src') or img.get('src')
            if src:
                u = canonical(src, url)
                if u:
                    assets.add(u)
        return {'url': url, 'title': title, 'path': page_path(url), 'links': sorted(links), 'assets': sorted(assets), 'recipe': bool(re.search(r'\bIngredients\b', text, re.I) and re.search(r'\b(Preparation|Directions|Instructions)\b', text, re.I)), 'characters': len(text)}
    except Exception as exc:
        return {'url': url, 'error': str(exc)}


def download_asset(url):
    p = ROOT / asset_path(url)
    try:
        if not p.exists():
            if shutil.disk_usage(ROOT).free < 550 * 1024 * 1024:
                raise RuntimeError('Недостаточно места: сохранён резерв 550 МБ; можно продолжить на другом диске')
            data, mime, final = fetch(url)
            if 'html' in mime:
                raise ValueError('HTML returned instead of image/document')
            with DISK_LOCK:
                if shutil.disk_usage(ROOT).free - len(data) < 550 * 1024 * 1024:
                    raise RuntimeError('Недостаточно места: сохранён резерв 550 МБ; можно продолжить на другом диске')
                p.write_bytes(data)
        return {'url': url, 'path': asset_path(url), 'bytes': p.stat().st_size}
    except Exception as exc:
        return {'url': url, 'error': str(exc)}


def save_json(name, value):
    p = ROOT / name
    temp = p.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(p)


def build(pages, assets):
    good = {u: p for u, p in pages.items() if 'error' not in p}
    available = {u: a for u, a in assets.items() if 'error' not in a}
    rows = []
    for url, record in good.items():
        soup = BeautifulSoup((ROOT / 'originals' / Path(record['path']).name).read_bytes(), 'lxml')
        content = soup.select_one('.post') or soup.select_one('.container') or soup.body or soup
        for node in content.select('#comments, #respond, #footer, #relevanssi_related, .postmetadata, .navi, .wpfp-span, script, style, form, nav, noscript, link, base'):
            node.decompose()
        for node in content.find_all(True):
            for attr in list(node.attrs):
                if attr.startswith('on') or attr in {'srcset', 'sizes', 'loading'}:
                    del node[attr]
        for a in content.select('a[href]'):
            original = urljoin(url, a['href'])
            u = canonical(original)
            frag = urlsplit(original).fragment
            if '/attachment/' in original and a.find('img'):
                child = a.find('img')
                image_url = canonical(child.get('data-src') or child.get('src', ''), url)
                if image_url in available:
                    a['href'] = '../' + available[image_url]['path']
                    continue
            if u in good:
                a['href'] = Path(good[u]['path']).name + ('#' + frag if frag else '')
            elif u in available:
                a['href'] = '../' + available[u]['path']
            else:
                a['href'] = original
                a['title'] = 'Online link / ссылка на исходный сайт'
        for img in content.select('img'):
            src = img.get('data-src') or img.get('data-lazy-src') or img.get('src')
            u = canonical(src, url) if src else None
            if u in available:
                img['src'] = '../' + available[u]['path']
            else:
                img['alt'] = (img.get('alt') or '') + ' [изображение не сохранено]'
                img.attrs.pop('src', None)
        for frame in content.select('iframe'):
            a = soup.new_tag('a', href=urljoin(url, frame.get('src', '')))
            a.string = 'Видео на внешнем сайте (нужен интернет)'
            frame.replace_with(a)
        document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(record['title']) + '</title><link rel="stylesheet" href="../reader.css"><header><a href="../START_HERE.html">← Каталог и поиск</a> · <a href="' + html.escape(url, quote=True) + '">Оригинал</a> · Личная копия, 10.09.2026 · © Amie Sue</header><main>' + str(content) + '</main></html>'
        (ROOT / record['path']).write_text(document, encoding='utf-8')
        (ROOT / 'texts' / (Path(record['path']).stem + '.txt')).write_text(record['title'] + '\n' + url + '\n\n' + content.get_text('\n', strip=True), encoding='utf-8')
        category = urlsplit(url).path.strip('/').split('/')[0] or 'home'
        rows.append('<li data-recipe="' + str(int(record['recipe'])) + '" data-category="' + html.escape(category, quote=True) + '"><a href="' + record['path'] + '">' + html.escape(record['title']) + '</a> <small>' + html.escape(category) + '</small></li>')
    rows.sort(key=str.casefold)
    count = sum(p['recipe'] for p in good.values())
    index = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NouveauRaw — локальная библиотека</title><link rel="stylesheet" href="reader.css"><main><h1>NouveauRaw / Amie Sue</h1><p>Локальная библиотека · сохранено 10 сентября 2026</p><p>Автор рецептов и фотографий — Amie Sue. Оригинальный английский текст сохранён. Открывайте этот файл двойным щелчком: сервер и интернет для сохранённых страниц и фотографий не нужны.</p>'''
    index += f'<p>Сохранено страниц: <b>{len(good)}</b>. Страниц с ингредиентами и инструкциями: <b>{count}</b> (определено автоматически).</p>'
    index += '<input id="q" placeholder="Поиск по английскому названию…" aria-label="Поиск"> <label><input type="checkbox" id="recipes"> Только рецепты</label><p id="count"></p><ul id="list">' + ''.join(rows) + '</ul><p class="note">Внешние ссылки и видео требуют интернета. Исходный HTML находится в originals, текстовые копии — в texts. Подробности полноты — в report.json.</p></main>'
    index += '''<script>const q=document.getElementById('q'),r=document.getElementById('recipes'),rows=[...document.querySelectorAll('#list li')];function filter(){let n=0;const s=q.value.toLowerCase();rows.forEach(x=>{const show=x.textContent.toLowerCase().includes(s)&&(!r.checked||x.dataset.recipe==='1');x.hidden=!show;if(show)n++});document.getElementById('count').textContent='Показано: '+n}q.addEventListener('input',filter);r.addEventListener('change',filter);filter();</script></html>'''
    (ROOT / 'START_HERE.html').write_text(index, encoding='utf-8')
    (ROOT / 'reader.css').write_text(CSS, encoding='utf-8')
    report = {'date': '2026-09-10', 'saved_pages': len(good), 'recipe_pages_detected': count, 'saved_assets': len(available), 'asset_bytes': sum(a['bytes'] for a in available.values()), 'page_errors': [p for p in pages.values() if 'error' in p], 'asset_errors': [a for a in assets.values() if 'error' in a], 'limitations': ['External video streams are not downloaded.', 'Original HTML retained; offline reader excludes comments, forms and related-post widgets.', 'Recipe count is heuristic; all saved pages are searchable.']}
    save_json('report.json', report)
    print('BUILT', json.dumps({k: v for k, v in report.items() if k not in {'page_errors', 'asset_errors', 'limitations'}}), flush=True)


def main():
    for folder in ('originals', 'pages', 'texts', 'assets', 'sources'):
        (ROOT / folder).mkdir(exist_ok=True)
    seeds = {BASE, BASE + 'raw-recipes-list-view/', BASE + 'vegan-cooked-recipes/', BASE + 'reference-library-2/', BASE + 'kitchen-diary/amiesue-com/'}
    for p in (ROOT / 'sources').glob('*sitemap*.xml'):
        seeds.update(x.text for x in ET.fromstring(p.read_bytes()).findall('{*}url/{*}loc'))
    for file in (ROOT / 'sources').glob('list.html'):
        seeds.update(a['href'] for a in BeautifulSoup(file.read_bytes(), 'lxml').select('a[href]'))
    seeds = {u for x in seeds if (u := canonical(x)) and not Path(urlsplit(u).path).suffix}
    pages = json.loads((ROOT / 'pages_manifest.json').read_text(encoding='utf-8')) if (ROOT / 'pages_manifest.json').exists() else {}
    pages = {u: p for u, p in pages.items() if canonical(u)}
    seeds.update(u for p in pages.values() for u in p.get('links', []))
    seeds = {u for u in seeds if canonical(u)}
    queue = seeds - {u for u, p in pages.items() if 'error' not in p}
    attempted = set()
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        while queue:
            print('PAGES batch', len(queue), 'already saved', sum('error' not in p for p in pages.values()), flush=True)
            pending = {pool.submit(download_page, u): u for u in sorted(queue)}
            attempted.update(queue)
            queue = set()
            for n, future in enumerate(cf.as_completed(pending), 1):
                result = future.result()
                pages[result['url']] = result
                if 'error' not in result:
                    queue.update(u for u in result['links'] if u not in pages and u not in attempted)
                if n % 40 == 0:
                    save_json('pages_manifest.json', pages)
                    print('PAGES', len(pages), 'errors', sum('error' in p for p in pages.values()), 'next', len(queue), flush=True)
            save_json('pages_manifest.json', pages)
    assets = json.loads((ROOT / 'assets_manifest.json').read_text(encoding='utf-8')) if (ROOT / 'assets_manifest.json').exists() else {}
    wanted = {u for p in pages.values() for u in p.get('assets', [])}
    wanted -= {u for u, a in assets.items() if 'error' not in a}
    print('ASSETS needed', len(wanted), flush=True)
    if not (ROOT / 'START_HERE.html').exists():
        build(pages, assets)
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        for n, result in enumerate(pool.map(download_asset, sorted(wanted)), 1):
            assets[result['url']] = result
            if n % 100 == 0:
                save_json('assets_manifest.json', assets)
                print('ASSETS', n, '/', len(wanted), 'errors', sum('error' in a for a in assets.values()), flush=True)
    save_json('assets_manifest.json', assets)
    build(pages, assets)
    print('DONE', flush=True)


if __name__ == '__main__':
    from fast_reader import build
    main()
