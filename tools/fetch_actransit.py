#!/usr/bin/env python3
"""Download AC Transit's GTFS timetable for tools/build_schedule.py.

Uses AC Transit's API with the ACT_TOKEN secret (the active schedule). Without the secret there is no
sanctioned keyless source: AC Transit's open-data portal refuses scripted requests. Records the result in
act_path.txt / act_source.txt and never fails the job; no feed just means the page keeps its built-in bus times.
"""
import json, os, re, ssl, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request, zipfile

API = 'https://api.actransit.org/transit/gtfs/download?token='


_contexts = {}                                        # host -> SSL context that includes a fetched intermediate


def trusted_roots():
    paths = ssl.get_default_verify_paths()
    for f in (os.environ.get('FETCH_ROOTS'), os.environ.get('SSL_CERT_FILE'), paths.cafile, paths.openssl_cafile,
              '/etc/ssl/certs/ca-certificates.crt'):
        if f and os.path.exists(f):
            return f
    raise RuntimeError('no CA bundle found')


def as_pem(raw):
    if b'-----BEGIN CERTIFICATE-----' in raw:
        return raw.decode()
    for cmd in (['openssl', 'x509', '-inform', 'DER'], ['openssl', 'pkcs7', '-inform', 'DER', '-print_certs']):
        out = subprocess.run(cmd, input=raw, capture_output=True)
        if out.returncode == 0 and b'BEGIN CERTIFICATE' in out.stdout:
            return out.stdout.decode()
    raise ValueError('issuer certificate in an unknown format')


def complete_chain(host, port=443):
    """The server left out its intermediate certificate. Fetch it from the address the server's own certificate
    names (Authority Information Access), as browsers do. The chain must still end at a trusted root."""
    leaf = ssl.get_server_certificate((host, port), timeout=30)
    text = subprocess.run(['openssl', 'x509', '-noout', '-text'], input=leaf, capture_output=True, text=True).stdout
    m = re.search(r'CA Issuers - URI:(\S+)', text)
    if not m:
        raise RuntimeError('the certificate names no issuer to fetch')
    with urllib.request.urlopen(m.group(1), timeout=30) as r:
        issuer = as_pem(r.read())
    bundle = tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False)
    with open(trusted_roots()) as roots:
        bundle.write(roots.read() + '\n' + issuer)
    bundle.close()
    _contexts[host] = ssl.create_default_context(cafile=bundle.name)
    print(f'  {host}: fetched its missing intermediate certificate from {m.group(1)}', file=sys.stderr)


def get(url, dest=None, tries=3):
    host = urllib.parse.urlsplit(url).hostname
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'mcgee-morning-board timetable job'})
            ctx = _contexts.get(host) or ssl.create_default_context(cafile=os.environ.get('FETCH_ROOTS') or None)
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                data = r.read()
            if dest:
                with open(dest, 'wb') as f:
                    f.write(data)
            return data
        except Exception as e:                        # noqa: BLE001
            print(f'  {url.split("?")[0]}: {e} (try {n + 1})', file=sys.stderr)
            code = getattr(e, 'code', None)
            if isinstance(code, int) and 400 <= code < 500 and code != 429:
                return None                           # a refusal, not a hiccup: don't knock again
            if 'CERTIFICATE_VERIFY_FAILED' in str(e) and host not in _contexts:
                try:
                    complete_chain(host, urllib.parse.urlsplit(url).port or 443)
                    continue
                except Exception as e2:               # noqa: BLE001
                    print(f'  {host}: could not complete the certificate chain: {e2}', file=sys.stderr)
            time.sleep(3 * (n + 1))
    return None


def done(path, source):
    open('act_path.txt', 'w').write(path)
    open('act_source.txt', 'w').write(source)
    print(f'AC Transit timetable: {source} -> {path or "none"}')
    sys.exit(0)


def main():
    token = os.environ.get('ACT_TOKEN', '').strip()
    if not token:
        print('::notice::No ACT_TOKEN secret, so no AC Transit timetable today. Add it to use AC Transit\'s API.', file=sys.stderr)
        done('', 'none')
    if get(API + token, 'act.zip') and zipfile.is_zipfile('act.zip'):
        done('act.zip', 'api')
    print('::warning::AC Transit\'s API did not return a timetable zip; keeping the previous bus times.', file=sys.stderr)
    done('', 'none')


if __name__ == '__main__':
    main()
