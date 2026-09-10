"""Check files and produce a readable archive status page."""
import html
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

import verify_archive

ROOT = Path(__file__).resolve().parent


def check_image(path):
    try:
        with Image.open(path) as picture:
            picture.verify()
        return None
    except Exception as exc:
        return {'path': str(path), 'error': str(exc)}


def main():
    verify_archive.main()
    report = json.loads((ROOT / 'report.json').read_text(encoding='utf-8'))
    validation = json.loads((ROOT / 'validation.json').read_text(encoding='utf-8'))
    assets = json.loads((ROOT / 'assets_manifest.json').read_text(encoding='utf-8'))
    saved = [a for a in assets.values() if 'error' not in a]
    size_errors = [a['path'] for a in saved if not (ROOT / a['path']).exists() or (ROOT / a['path']).stat().st_size != a['bytes']]
    images = sorted(ROOT / a['path'] for a in saved if Path(a['path']).suffix != '.pdf')
    sample = images[::max(1, len(images) // 40)][:40]
    with ThreadPoolExecutor(max_workers=4) as pool:
        image_errors = [e for e in pool.map(check_image, sample) if e]
    validation.update({'asset_size_errors': size_errors, 'image_samples_checked': len(sample), 'image_sample_errors': image_errors})
    (ROOT / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')
    if size_errors or image_errors or validation['sitemap_articles_not_saved']:
        raise RuntimeError('Archive validation failed; see validation.json')
    total = sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())
    pdf_count = sum(Path(a['path']).suffix == '.pdf' for a in saved)
    summary = f'''Локальная копия NouveauRaw / Amie Sue
Сохранено 10 сентября 2026.

Открыть: START_HERE.html
Уникальных страниц в каталоге: {report['unique_pages']}.
Страниц с ингредиентами и инструкциями: {report['recipe_pages_detected']} (автоматический фильтр).
Все {validation['sitemap_articles_expected']} статей из карты сайта сохранены.
Сохранено изображений: {len(saved) - pdf_count}; PDF: {pdf_count}.
Размер папки: приблизительно {total / 1024**3:.2f} ГБ.
Проверено локальных ссылок: {validation['local_references_checked']}; неработающих: 0.
Проверены размеры всех скачанных файлов и целостность {len(sample)} изображений из разных частей архива.

Тексты и фотографии принадлежат Amie Sue. Тексты оставлены на английском.
Каталог, поиск, рецепты и сохранённые фотографии работают без интернета.
Внешние видеоролики не скачивались. Исходный HTML, включая комментарии,
сохранён в originals; отдельные текстовые копии — в texts.

Недоступные изображения на исходном сайте: {len(report['asset_errors'])}.
'''
    for error in report['asset_errors']:
        summary += error['url'] + '\n' + error['error'] + '\n'
    (ROOT / 'ARCHIVE_STATUS.txt').write_text(summary, encoding='utf-8')
    page = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Сведения о сохранении NouveauRaw</title><link rel="stylesheet" href="reader.css"><main><a href="START_HERE.html">← Каталог рецептов</a><h1>Сведения о сохранении</h1><div style="white-space:pre-wrap;overflow-wrap:anywhere">' + html.escape(summary) + '</div></main></html>'
    (ROOT / 'archive_status.html').write_text(page, encoding='utf-8')
    index_path = ROOT / 'START_HERE.html'
    index = index_path.read_text(encoding='utf-8').replace('Подробности полноты — в report.json.', '<a href="archive_status.html">Сведения о сохранении и проверке архива</a>.')
    index_path.write_text(index, encoding='utf-8')
    print('COMPLETE', report['unique_pages'], 'unique pages;', len(saved), 'assets;', round(total / 1024**3, 2), 'GiB', flush=True)


if __name__ == '__main__':
    main()
