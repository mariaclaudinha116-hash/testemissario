#!/usr/bin/env python3
"""
Servidor local para o clone do Missario.
Roteia qualquer URL do Wix para o arquivo HTML local correto.
CORRIGIDO: arquivos estaticos (js/css/img) sao servidos antes do roteamento.
"""
import http.server
import urllib.parse
import os
import mimetypes

DIR = os.path.dirname(os.path.abspath(__file__))

SLUG_MAP = {
    'missario-2026-espiral':     'produto-missario-2026-espiral.html',
    'missario-2026':             'produto-missario-2026.html',
    'missario-2025':             'produto-missario-2025.html',
    'missario-2024':             'produto-missario-2024.html',
    'kit-10-missario-2026':      'kit-10-missario-2026.html',
    'kit-30-missario-2026':      'kit-30-missario-2026.html',
    'miss%c3%a1rio-2026-espiral':'produto-missario-2026-espiral.html',
    'miss%c3%a1rio-2026':        'produto-missario-2026.html',
    'miss%c3%a1rio-2025':        'produto-missario-2025.html',
    'miss%c3%a1rio-2024':        'produto-missario-2024.html',
    'kit-10-miss%c3%a1rio-2026': 'kit-10-missario-2026.html',
    'kit-30-miss%c3%a1rio-2026': 'kit-30-missario-2026.html',
}

PAGE_MAP = {
    '/':                     'loja.html',
    '/loja':                 'loja.html',
    '/shop':                 'loja.html',
    '/quem-somos':           'quem-somos.html',
    '/contato':              'contato.html',
    '/calendario-liturgico': 'calendario-liturgico.html',
    '/a-missa-em-partes':    'a-missa-em-partes.html',
    '/cart':                 'cart-page.html',
    '/cart-page':            'cart-page.html',
    '/checkout':             'checkout.html',
}


def resolve_html(raw_path):
    path = raw_path.split('?')[0].split('#')[0]
    decoded = urllib.parse.unquote(path).lower().rstrip('/')

    if decoded in PAGE_MAP:
        return PAGE_MAP[decoded]
    if path in PAGE_MAP:
        return PAGE_MAP[path]

    if 'product-page/' in decoded:
        slug = decoded.split('product-page/')[-1].strip('/')
        if slug in SLUG_MAP:
            return SLUG_MAP[slug]
        for key, val in SLUG_MAP.items():
            if key in slug or slug in key:
                return val

    # URL concatenada maluca do Wix (ex: /produto-missario-2026.htmlmissário-2026)
    if '.html' in decoded:
        part = decoded.split('.html')[0] + '.html'
        filename = os.path.basename(part)
        full = os.path.join(DIR, filename)
        if os.path.isfile(full):
            return filename

    for key, val in SLUG_MAP.items():
        if key in decoded:
            return val

    return 'loja.html'


class MissarioHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        raw = self.path
        clean = urllib.parse.unquote(raw.split('?')[0].split('#')[0]).lstrip('/')

        # ── PASSO 1: Servir arquivos estáticos existentes PRIMEIRO
        if clean:
            asset_path = os.path.join(DIR, clean)
            if os.path.isfile(asset_path):
                try:
                    with open(asset_path, 'rb') as f:
                        data = f.read()
                    mime, _ = mimetypes.guess_type(clean)
                    mime = mime or 'application/octet-stream'
                    self.send_response(200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    self.send_error(500, str(e))
                return

        # ── PASSO 2: Rotear URLs para HTMLs
        local_file = resolve_html(raw)
        full_path = os.path.join(DIR, local_file)

        if not os.path.isfile(full_path):
            self.send_error(404, 'Not found: ' + local_file)
            return

        try:
            with open(full_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(data)
            print('ROUTE: ' + raw + ' -> ' + local_file)
        except Exception as e:
            self.send_error(500, str(e))

    def do_HEAD(self):
        self.do_GET()

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    port = 3000
    os.chdir(DIR)
    mimetypes.add_type('application/javascript', '.js')
    mimetypes.add_type('text/css', '.css')
    mimetypes.add_type('font/woff2', '.woff2')
    mimetypes.add_type('font/woff', '.woff')

    with http.server.HTTPServer(('', port), MissarioHandler) as httpd:
        print('Servidor Missario: http://localhost:' + str(port))
        print('Dir: ' + DIR)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('Encerrado.')
