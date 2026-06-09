"""제출용 HTML에 Pretendard 폰트를 '앱에 실제로 쓰인 글자만' 서브셋해 base64 인라인.

- pretendard.min.css의 weight별 woff2를 받아 HTML 내 모든 문자로 subset → 작게.
- CDN @import(Pretendard/Noto)는 제거 → 인터넷 없이도 폰트 적용.
실행: cd frontend && python scripts/inline_fonts.py [html경로]
"""
import base64
import io
import os
import re
import string
import sys
import urllib.parse
import urllib.request

from fontTools import subset
from fontTools.ttLib import TTFont

FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_HTML = os.path.join(os.path.dirname(FRONTEND), '한화ATLAS_오프라인_제출본.html')
CSS_URL = 'https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css'
WANT_WEIGHTS = {400, 500, 600, 700, 800, 900}


def fetch(url, timeout=60):
    return urllib.request.urlopen(url, timeout=timeout).read()


def subset_woff2(raw, text):
    font = TTFont(io.BytesIO(raw))
    opt = subset.Options()
    opt.flavor = 'woff2'
    opt.desubroutinize = True
    opt.drop_tables = []
    ss = subset.Subsetter(options=opt)
    ss.populate(text=text)
    ss.subset(font)
    out = io.BytesIO()
    font.flavor = 'woff2'
    font.save(out)
    return out.getvalue()


def main():
    html_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HTML
    html = open(html_path, encoding='utf-8').read()

    # 1) 들어갈 문자 집합 = HTML 전체 유니크 문자 + 기본 ASCII/구두점
    text = ''.join(sorted(set(html) | set(string.printable) | set('·…—∙•※★☆°％‰')))
    print('unique chars to keep:', len(set(text)))

    # 2) CSS 파싱: (weight, woff2_url)
    css = fetch(CSS_URL).decode('utf-8')
    faces = re.findall(r'@font-face\{[^}]*\}', css)
    targets = []
    for fc in faces:
        wm = re.search(r'font-weight:\s*(\d+)', fc)
        um = re.search(r'url\(([^)]+\.woff2)\)', fc)
        if not wm or not um:
            continue
        w = int(wm.group(1))
        if w not in WANT_WEIGHTS:
            continue
        url = urllib.parse.urljoin(CSS_URL, um.group(1).strip('\'"'))
        targets.append((w, url))
    targets.sort()
    print('weights to inline:', [w for w, _ in targets])

    # 3) weight별 다운로드 → subset → base64 @font-face
    face_css = []
    total = 0
    for w, url in targets:
        raw = fetch(url)
        sub = subset_woff2(raw, text)
        total += len(sub)
        b64 = base64.b64encode(sub).decode('ascii')
        face_css.append(
            "@font-face{font-family:'Pretendard';font-style:normal;font-weight:%d;"
            "font-display:swap;src:url(data:font/woff2;base64,%s) format('woff2')}" % (w, b64)
        )
        print('  weight %d: %dKB raw -> %dKB subset' % (w, len(raw) // 1024, len(sub) // 1024))
    style = '<style id="inlined-pretendard">' + ''.join(face_css) + '</style>'

    # 4) CDN @import 제거(Pretendard/Noto/googleapis) + <head>에 인라인 폰트 주입
    before = len(html)
    html = re.sub(r'@import\s*(?:url\()?["\']https://[^"\']*(?:pretendard|Noto\+Sans\+KR|fonts\.googleapis)[^"\']*["\']\)?\s*;', '', html)
    removed = before - len(html)
    html = html.replace('</head>', style + '</head>', 1)

    open(html_path, 'w', encoding='utf-8').write(html)
    print('---')
    print('removed CDN @import bytes:', removed, '| inlined font bytes:', total)
    print('WROTE %s | size=%.2fMB' % (html_path, os.path.getsize(html_path) / 1048576))


if __name__ == '__main__':
    main()
