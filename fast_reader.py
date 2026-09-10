"""Build offline reader pages using the native lxml parser."""
import html as escape_html
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from lxml import etree, html

ROOT = Path(__file__).resolve().parent


def article(data):
    doc = html.fromstring(data)
    matches = doc.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," post ")]')
    if not matches:
        matches = doc.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," container ")]')
    content = matches[0] if matches else doc
    source = doc.xpath('//link[@rel="canonical"]/@href')
    if source:
        content.set('data-source-url', source[0])
    ids = {'comments', 'respond', 'footer', 'relevanssi_related'}
    classes = {'postmetadata', 'navi', 'wpfp-span'}
    tags = {'script', 'style', 'form', 'nav', 'noscript', 'link', 'base'}
    for node in list(content.iterdescendants()):
        if not isinstance(node.tag, str):
            continue
        if node.tag in tags or node.get('id') in ids or classes.intersection(node.get('class', '').split()):
            if node.getparent() is not None:
                node.drop_tree()
    return content


def build(pages, assets):
    from archive_site import CSS, canonical, save_json
    good = {u: p for u, p in pages.items() if 'error' not in p}
    available = {u: a for u, a in assets.items() if 'error' not in a}
    rows = []
    catalog_seen = set()
    unique_recipe_count = 0
    ordered = sorted(good.items(), key=lambda item: item[1]['title'].casefold())
    pool = ThreadPoolExecutor(max_workers=8)
    data_stream = pool.map(lambda item: (ROOT / 'originals' / Path(item[1]['path']).name).read_bytes(), ordered)
    for (url, record), data in zip(ordered, data_stream):
        content = article(data)
        for node in content.iter():
            if not isinstance(node.tag, str):
                continue
            for key in list(node.attrib):
                if key.startswith('on') or key in {'srcset', 'sizes', 'loading'}:
                    del node.attrib[key]
        for a in content.xpath('.//a[@href]'):
            original = urljoin(url, a.get('href'))
            u = canonical(original)
            frag = urlsplit(original).fragment
            child = a.find('.//img')
            if '/attachment/' in original and child is not None:
                image_url = canonical(child.get('data-src') or child.get('src', ''), url)
                if image_url in available:
                    a.set('href', '../' + available[image_url]['path'])
                    continue
            if u in good:
                a.set('href', Path(good[u]['path']).name + ('#' + frag if frag else ''))
            elif u in available:
                a.set('href', '../' + available[u]['path'])
            else:
                a.set('href', original)
                a.set('title', 'Online link / ссылка на исходный сайт')
        for img in content.xpath('.//img'):
            src = img.get('data-src') or img.get('data-lazy-src') or img.get('src')
            if not src:
                img.drop_tree()
                continue
            u = canonical(src, url) if src else None
            if u in available:
                img.set('src', '../' + available[u]['path'])
            else:
                img.set('alt', (img.get('alt') or '') + ' [изображение не сохранено]')
                img.attrib.pop('src', None)
        for frame in content.xpath('.//iframe'):
            a = etree.Element('a', href=urljoin(url, frame.get('src', '')))
            a.text = 'Видео на внешнем сайте (нужен интернет)'
            frame.getparent().replace(frame, a)
        title = escape_html.escape(record['title'])
        doc = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><link rel="stylesheet" href="../reader.css"><header><a href="../START_HERE.html">← Каталог и поиск</a> · <a href="' + escape_html.escape(url, quote=True) + '">Оригинал</a> · Личная копия, 10.09.2026 · © Amie Sue</header><main>' + html.tostring(content, encoding='unicode') + '</main></html>'
        (ROOT / record['path']).write_text(doc, encoding='utf-8')
        # Keep paragraph/list boundaries in the plain-text edition.
        for node in content.iter():
            if node.tag in {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'br', 'tr'}:
                node.tail = '\n' + (node.tail or '')
        (ROOT / 'texts' / (Path(record['path']).stem + '.txt')).write_text(record['title'] + '\n' + url + '\n\n' + content.text_content(), encoding='utf-8')
        category = urlsplit(url).path.strip('/').split('/')[0] or 'home'
        source_url = canonical(content.get('data-source-url', url)) or url
        if source_url not in catalog_seen:
            catalog_seen.add(source_url)
            unique_recipe_count += int(record['recipe'])
            rows.append('<li data-recipe="' + str(int(record['recipe'])) + '"><a href="' + record['path'] + '">' + title + '</a> <small>' + escape_html.escape(category) + '</small></li>')
    pool.shutdown()
    count = unique_recipe_count
    index = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NouveauRaw — локальная библиотека</title><link rel="stylesheet" href="reader.css"><main><h1>NouveauRaw / Amie Sue</h1><p>Локальная библиотека · сохранено 10 сентября 2026</p><p>Автор рецептов и фотографий — Amie Sue. Оригинальный английский текст сохранён. Открывайте этот файл двойным щелчком: сервер и интернет для сохранённых страниц и фотографий не нужны.</p>'''
    index += f'<p>В каталоге: <b>{len(catalog_seen)}</b> уникальных страниц. Из них с ингредиентами и инструкциями: <b>{count}</b> (определено автоматически). Старые адреса-дубли скрыты из каталога, но сохранены для переходов по ссылкам.</p>'
    index += '<input id="q" placeholder="Поиск по английскому названию…" aria-label="Поиск"> <label><input type="checkbox" id="recipes"> Только рецепты</label><p id="count"></p><ul id="list">' + ''.join(rows) + '</ul><p class="note">Внешние ссылки и видео требуют интернета. Исходный HTML находится в originals, текстовые копии — в texts. Подробности полноты — в report.json.</p></main>'
    index += '''<script>const q=document.getElementById('q'),r=document.getElementById('recipes'),rows=[...document.querySelectorAll('#list li')];function filter(){let n=0;const s=q.value.toLowerCase();rows.forEach(x=>{const show=x.textContent.toLowerCase().includes(s)&&(!r.checked||x.dataset.recipe==='1');x.hidden=!show;if(show)n++});document.getElementById('count').textContent='Показано: '+n}q.addEventListener('input',filter);r.addEventListener('change',filter);filter();</script></html>'''
    (ROOT / 'START_HERE.html').write_text(index, encoding='utf-8')
    (ROOT / 'reader.css').write_text(CSS, encoding='utf-8')
    report = {'date': '2026-09-10', 'saved_pages': len(good), 'recipe_pages_detected': count, 'saved_assets': len(available), 'asset_bytes': sum(a['bytes'] for a in available.values()), 'page_errors': [p for p in pages.values() if 'error' in p and '/attachment/' not in p['url']], 'asset_errors': [a for a in assets.values() if 'error' in a], 'limitations': ['External video streams are not downloaded.', 'Original HTML retained; offline reader excludes comments, forms and related-post widgets.', 'Recipe count is heuristic; all saved pages are searchable.']}
    report['unique_pages'] = len(catalog_seen)
    save_json('report.json', report)
    print('BUILT', len(good), 'pages;', count, 'recipe pages;', len(available), 'assets', flush=True)


if __name__ == '__main__':
    build(json.loads((ROOT / 'pages_manifest.json').read_text(encoding='utf-8')), json.loads((ROOT / 'assets_manifest.json').read_text(encoding='utf-8')))
