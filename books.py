"""Download the book library, explicitly excluding magazines and articles."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, unquote, urljoin, urlparse, urldefrag
from bs4 import BeautifulSoup
from downloader import Downloader

SITE = 'https://www.stmark-kw.net'
ORIGINS = [SITE, 'https://stmark-media.s3.amazonaws.com', 'https://stmark-media.s3.us-east-1.amazonaws.com']
BOOK_EXT = {'.pdf', '.doc', '.docx', '.epub', '.djvu', '.zip', '.txt'}
EXCLUDED_CATEGORIES = {'20'}
EXCLUDED_LIBRARIES = {'2', '53'}


def page_url(url):
    """Only traverse category/library content; never articles or magazine libraries."""
    p = urlparse(url)
    q = {key.lower(): values for key, values in parse_qs(p.query).items()}
    if p.netloc != 'www.stmark-kw.net' or p.path.lower() not in ('/category.aspx', '/library.aspx'):
        return None
    if set(q.get('catid', [])) & EXCLUDED_CATEGORIES or set(q.get('libcatid', [])) & EXCLUDED_LIBRARIES:
        return None
    query = urlencode(sorted((key, value) for key, values in q.items() for value in values))
    return SITE + p.path.lower() + '?' + query


def client(max_files=25):
    return Downloader(SimpleNamespace(max_files=max_files, max_pages=200, max_mb=150, depth=10,
                                      authorized_origin=ORIGINS, skip_files=0))


def catalog(batch_size):
    d = client()
    pending = [SITE + '/category.aspx?catid=18']
    visited = set()
    resources = {}
    errors = []
    excluded = set()
    while pending and len(visited) < 200:
        url = pending.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            data, typ = d.read(url)
            if 'html' not in typ:
                raise ValueError('Expected a library HTML page')
            soup = BeautifulSoup(data, 'html.parser')
            content = soup.select_one('#content')
            if content is None:
                raise ValueError('Missing library content')
            section = soup.title.get_text(' ', strip=True) if soup.title else url
            for a in content.select('a[href]'):
                link = urldefrag(urljoin(d.final_url or url, a['href']))[0]
                p = urlparse(link)
                canonical = page_url(link)
                if canonical:
                    if canonical not in visited and canonical not in pending:
                        pending.append(canonical)
                elif p.netloc == 'www.stmark-kw.net' and p.path.lower() in ('/category.aspx', '/library.aspx'):
                    excluded.add(link)
                elif p.scheme in ('https', 'http') and Path(p.path).suffix.lower() in BOOK_EXT:
                    # The owner's authorization covers these exact storage origins only.
                    origin = f'{p.scheme}://{p.netloc}'
                    if origin not in ORIGINS:
                        errors.append({'url': link, 'error': 'Outside authorized book storage origins'})
                        continue
                    resources.setdefault(link, {'url': link, 'name': unquote(p.path.rsplit('/', 1)[-1]),
                                                'section': section, 'source_page': url})
        except Exception as exc:
            errors.append({'url': url, 'error': str(exc)})
    if pending:
        errors.append({'error': 'Page limit reached; catalog incomplete'})
    result = {'resources': list(resources.values()), 'pages': sorted(visited),
              'excluded_pages': sorted(excluded), 'errors': errors,
              'excluded_sections': ['مجلة الكرازة', 'مجلة ينبوع المحبة', 'مقالات']}
    Path('catalog.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    total = len(resources)
    batches = list(range(math.ceil(total / batch_size)))
    if len(batches) > 100:
        raise ValueError('Catalog exceeds 100 bounded batches')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write('batches=' + json.dumps(batches) + '\n')
    print(f'::notice title=Book catalog::{total} books; {len(visited)} pages; {len(errors)} catalog errors; magazines and articles excluded')
    d.s.close()
    if not total:
        raise ValueError('No books discovered')


def download(batch, batch_size):
    data = json.loads(Path('catalog.json').read_text())
    selected = data['resources'][batch * batch_size:(batch + 1) * batch_size]
    d = client(batch_size)
    for item in selected:
        d.save(item['url'])
        entry = d.log[-1]
        entry.update(original_name=item['name'], section=item['section'], source_page=item['source_page'])
        if 'file' in entry:
            safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', item['name'])[:170]
            name = hashlib.sha256(item['url'].encode()).hexdigest()[:8] + ' - ' + safe
            (d.out / entry['file']).rename(d.out / name)
            entry['file'] = name
    d.finish()
    d.s.close()
    # Artifacts contain all successes and the exact failures; aggregate reports partial status.


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['catalog', 'download'])
    parser.add_argument('--batch', type=int, default=0)
    parser.add_argument('--batch-size', type=int, default=25)
    args = parser.parse_args()
    if args.batch < 0 or not 1 <= args.batch_size <= 25:
        parser.error('Invalid bounded batch')
    if args.mode == 'catalog':
        catalog(args.batch_size)
    else:
        download(args.batch, args.batch_size)
