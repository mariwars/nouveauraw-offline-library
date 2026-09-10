"""Validate the completed archive without network access."""
import json
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import html

ROOT = Path(__file__).resolve().parent


def check_page(path):
    broken = []
    remote_images = []
    checked = 0
    missing_images = 0
    doc = html.fromstring(path.read_bytes())
    for element in doc.xpath('//*[@href] | //img[@src]'):
        value = element.get('href', element.get('src', ''))
        url = urlsplit(value)
        if element.tag == 'img' and url.scheme in {'http', 'https'}:
            remote_images.append([path.name, value])
        if url.scheme or url.netloc or not url.path:
            continue
        checked += 1
        if not (path.parent / unquote(url.path)).exists():
            broken.append([path.name, value])
    missing_images = len(doc.xpath('//img[not(@src)]'))
    return checked, broken, remote_images, missing_images


def main():
    pages = [ROOT / 'START_HERE.html', *(ROOT / 'pages').glob('*.html')]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check_page, pages))
    checked = sum(r[0] for r in results)
    broken = [v for r in results for v in r[1]]
    remote_images = [v for r in results for v in r[2]]
    manifest = json.loads((ROOT / 'pages_manifest.json').read_text(encoding='utf-8'))
    expected = {x.text for p in (ROOT / 'sources').glob('post-sitemap*.xml') for x in ET.fromstring(p.read_bytes()).findall('{*}url/{*}loc')}
    unsaved = sorted(u for u in expected if u not in manifest or 'error' in manifest[u])
    result = {'html_files_checked': len(pages), 'local_references_checked': checked,
              'broken_local_references': broken, 'remote_images': remote_images,
              'image_placeholders': sum(r[3] for r in results),
              'sitemap_articles_expected': len(expected), 'sitemap_articles_not_saved': unsaved}
    (ROOT / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in result.items()}))
    if broken or remote_images:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
