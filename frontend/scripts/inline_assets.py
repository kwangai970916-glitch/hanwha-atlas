"""빌드된 dist/index.html의 로컬 이미지 참조(/illustrations 등)를 base64 data URI로 인라인.

- 표시 크기 대비 과대한 래스터 이미지는 420px로 다운스케일 후 인라인(용량 절감).
- 폰트(@import CDN)는 한글 웹폰트라 용량이 커 인라인하지 않는다(인터넷 로드, 실패 시 시스템폰트 폴백 — 에러 없음).
실행: cd frontend && python scripts/inline_assets.py [출력경로]
"""
import base64
import io
import os
import re
import sys

FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(FRONTEND, 'dist', 'index.html')
DEFAULT_OUT = os.path.join(os.path.dirname(FRONTEND), '한화ATLAS_오프라인_제출본.html')
PUBLIC = os.path.join(FRONTEND, 'public')
MAX_DIM = 420

MIME = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml', '.webp': 'image/webp', '.gif': 'image/gif',
    '.ico': 'image/x-icon',
}


def _maybe_resize(ext, raw):
    if ext not in ('.png', '.jpg', '.jpeg', '.webp'):
        return raw, ext
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
        if max(w, h) <= MAX_DIM:
            return raw, ext
        scale = MAX_DIM / float(max(w, h))
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, 'PNG', optimize=True)
        return buf.getvalue(), '.png'
    except Exception as e:
        print('  resize skip:', e)
        return raw, ext


def datauri(path_rel):
    fp = os.path.join(PUBLIC, path_rel.lstrip('/'))
    if not os.path.exists(fp):
        return None
    ext = os.path.splitext(fp)[1].lower()
    with open(fp, 'rb') as f:
        raw = f.read()
    raw, ext = _maybe_resize(ext, raw)
    return 'data:%s;base64,%s' % (MIME.get(ext, 'application/octet-stream'),
                                  base64.b64encode(raw).decode('ascii'))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    with open(SRC, encoding='utf-8') as f:
        html = f.read()

    refs = set(re.findall(r'/[\w./-]+?\.(?:png|jpg|jpeg|svg|webp|gif|ico)', html))
    n_ok = n_miss = 0
    for ref in sorted(refs):
        uri = datauri(ref)
        if uri:
            cnt = html.count(ref)
            html = html.replace(ref, uri)
            n_ok += 1
            print('inlined %-52s x%d (%dKB)' % (ref, cnt, len(uri) // 1024))
        else:
            n_miss += 1
            print('skip (not in public): %s' % ref)

    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    leftover = re.findall(r'(?:src|href)=["\']/[\w./-]+?\.(?:png|jpg|jpeg|svg|webp)', html)
    print('---')
    print('inlined=%d skipped=%d | leftover_local_img_refs=%d' % (n_ok, n_miss, len(leftover)))
    print('WROTE %s | size=%.2fMB' % (out, os.path.getsize(out) / 1048576))


if __name__ == '__main__':
    main()
