"""Bounded deterministic company facts: official identity -> exact source documents.

No model URLs. Search summaries never enter the document trust set. Documents are
inert text; retrieval errors remain explicit and separate from thesis conclusions.
"""
import csv
import hashlib
import io
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
from lxml import html

MAX_BYTES = 8_000_000
MAX_CHARS = 30000


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('NON_PUBLIC_SOURCE_URL')
    host = parsed.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('NON_PUBLIC_SOURCE_HOST')
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError('NON_PUBLIC_SOURCE_ADDRESS')
    # With an environment HTTP proxy, DNS and destination enforcement belong to that
    # proxy. Local DNS may intentionally be unavailable in managed execution.
    if requests.utils.get_environ_proxies(url):
        return url
    for info in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError('NON_PUBLIC_SOURCE_ADDRESS')
    return url


def acquire(source, timeout=12):
    from research_source_prefetch_v3 import _utcnow, USER_AGENT
    row = dict(source)
    try:
        url = row['source_url']
        for _ in range(4):
            public_url(url)
            response = requests.get(url, timeout=timeout, headers={'User-Agent': USER_AGENT}, stream=True, allow_redirects=False)
            if response.is_redirect:
                url = urljoin(url, response.headers['Location'])
                response.close()
                continue
            break
        response.raise_for_status()
        chunks, size = [], 0
        for part in response.iter_content(65536):
            size += len(part)
            if size > MAX_BYTES:
                raise ValueError('DOCUMENT_TOO_LARGE')
            chunks.append(part)
        response.close()
        raw = b''.join(chunks)
        if 'pdf' in response.headers.get('Content-Type', '') or raw.startswith(b'%PDF'):
            from pypdf import PdfReader
            text = '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(raw)).pages[:30])
            links = []
        else:
            tree = html.fromstring(raw)
            for node in tree.xpath('//script|//style|//nav|//footer'):
                node.drop_tree()
            text = tree.text_content()
            links = [(urljoin(url, a.get('href')), ' '.join(a.text_content().split())) for a in tree.xpath('//a[@href]')]
        text = ' '.join(text.split())[:MAX_CHARS]
        if len(text) < 100:
            raise ValueError('EMPTY_OR_UNREADABLE_DOCUMENT')
        observed = _utcnow()
        if not row.get('published_at'):
            row['published_at'] = observed
            row['date_basis'] = 'CURRENT_DOCUMENT_OBSERVED_AT; original publication unknown'
        row.update(document_text=text, document_sha256=hashlib.sha256(text.encode()).hexdigest(),
                   fetched_at=observed, available_at=observed, fetch_status='FETCHED', resolved_url=url)
        row['_links'] = links
    except Exception as exc:
        row.update(fetch_status='TRANSPORT_FAILED', fetch_error=f'{type(exc).__name__}: {exc}')
    return row


def official_profiles(targets, timeout=15):
    from research_source_prefetch_v3 import _utcnow, USER_AGENT
    wanted = {str(t['ticker']).split('.')[0]: t['ticker'] for t in targets}
    result = {}
    for suffix, table in [('.TW', 'L'), ('.TWO', 'O')]:
        if not any(str(t).endswith(suffix) for t in wanted.values()):
            continue
        url = f'https://mopsfin.twse.com.tw/opendata/t187ap03_{table}.csv'
        try:
            response = requests.get(url, timeout=timeout, headers={'User-Agent': USER_AGENT})
            response.raise_for_status()
            rows = csv.DictReader(io.StringIO(response.content.decode('utf-8-sig')))
            for row in rows:
                code = str(row.get('公司代號', '')).strip()
                if code not in wanted:
                    continue
                # Only business identity and official homepage, never personal contact data.
                facts = {k: row[k] for k in ['公司代號', '公司名稱', '公司簡稱', '主要經營業務', '網址'] if row.get(k)}
                import json
                text = json.dumps(facts, ensure_ascii=False)
                observed = _utcnow()
                result[wanted[code]] = dict(source_url=url, source_title='Official issuer business profile',
                    ticker=wanted[code], document_text=text, document_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    published_at=observed, available_at=observed, fetched_at=observed, fetch_status='FETCHED',
                    date_basis='CURRENT_OFFICIAL_PROFILE_OBSERVED_AT', search_lane='STRUCTURAL_IDENTITY',
                    official_homepage=row.get('網址'))
        except (requests.RequestException, ValueError):
            continue
    return result


def enrich_company_sources(targets, company_sources, timeout=12):
    """Two complementary roles, with bounded official-page traversal per issuer."""
    profiles = official_profiles(targets, timeout)
    def enrich(target):
        ticker = target['ticker']
        profile = profiles.get(ticker)
        sources = target['candidate_sources']
        if profile:
            sources.insert(0, profile)
            home = profile.get('official_homepage')
            if home:
                if not home.startswith(('https://', 'http://')):
                    home = 'https://' + home
                root = acquire(dict(source_url=home, source_title='Issuer official website', search_lane='STRUCTURAL_EXPOSURE'), timeout)
                sources.append(root)
                links = root.pop('_links', [])
                # Separate durable business evidence and current investor disclosures.
                for lane, pattern in [('STRUCTURAL_EXPOSURE', r'產品|應用|業務|product|solution|business'),
                                      ('CURRENT_TRANSMISSION', r'投資|法說|財務|investor|financial|presentation')]:
                    picked = next((u for u,label in links if urlparse(u).hostname == urlparse(home).hostname
                                   and re.search(pattern, label, re.I)), None)
                    if picked:
                        page = acquire(dict(source_url=picked, source_title=lane, search_lane=lane), timeout)
                        sources.append(page)
                        if lane == 'CURRENT_TRANSMISSION':
                            reports = [(u,label) for u,label in page.pop('_links', [])
                                       if '.pdf' in urlparse(u).path.lower()]
                            # A bounded second hop gets actual issuer disclosures instead of
                            # treating an investor-relations index as operating evidence.
                            for report,label in reports[:2]:
                                sources.append(acquire(dict(source_url=report, source_title=label or 'Issuer disclosure', search_lane=lane), timeout))
        seen, final = set(), []
        for source in sources:
            url = source['source_url']
            if url in seen:
                continue
            seen.add(url)
            if source.get('search_lane') == 'OFFICIAL_COMPANY_REVENUE':
                source = dict(source, document_text=source['snippet'], fetch_status='FETCHED',
                    document_sha256=hashlib.sha256(source['snippet'].encode()).hexdigest(),
                    evidence_role='GENERIC_REVENUE_ONLY')
            elif 'fetch_status' not in source:
                source = acquire(source, timeout)
            source.pop('_links', None)
            source['ticker'] = ticker
            final.append(source)
        target['candidate_sources'] = final
        target['candidate_source_count'] = len(final)
        target['document_count'] = sum(s.get('fetch_status') == 'FETCHED' for s in final)
        target['retrieval_status'] = 'FETCHED' if target['document_count'] else 'TRANSPORT_FAILED'
        print(f"company documents {ticker}: fetched={target['document_count']} candidates={len(final)}", flush=True)
        return target
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        company_sources = list(pool.map(enrich, company_sources))
    return company_sources


def verify_document_claim(item, documents, *, specific=False):
    """Exact quote/source/scope verification; semantic conclusions remain model work."""
    source = documents.get(item.get('source_url'))
    if not source or source.get('fetch_status') != 'FETCHED':
        raise ValueError('UNFETCHED_COMPANY_DOCUMENT')
    quote = ' '.join(str(item.get('source_quote') or '').split())
    text = ' '.join(str(source.get('document_text') or '').split())
    if len(quote) < 12 or quote not in text:
        raise ValueError('COMPANY_CLAIM_QUOTE_NOT_IN_DOCUMENT')
    if specific and source.get('evidence_role') == 'GENERIC_REVENUE_ONLY':
        raise ValueError('GENERIC_REVENUE_CANNOT_PROVE_SPECIFIC_DRIVER')
    if source.get('ticker') != item.get('ticker'):
        raise ValueError('COMPANY_DOCUMENT_SCOPE_MISMATCH')
