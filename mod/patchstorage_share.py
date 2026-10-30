# SPDX-FileCopyrightText: 2026 pi-Stomp
# SPDX-License-Identifier: AGPL-3.0-or-later

# Upload (share) user pedalboards to Patchstorage, see https://patchstorage.com/docs/api/beta/
# Everything here blocks on the network; webserver.py runs it on a worker thread.

import json
import logging
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from base64 import urlsafe_b64decode
from uuid import uuid4

TOKEN_LIFETIME = 7 * 24 * 3600
HTTP_TIMEOUT = 120
MAX_ARTWORK_SIZE = 5 * 1024 * 1024

# Leading bytes -> extension of the image formats accepted as artwork
ARTWORK_SIGNATURES = (
    (b'\x89PNG\r\n\x1a\n', 'png'),
    (b'\xff\xd8\xff', 'jpg'),
    (b'GIF87a', 'gif'),
    (b'GIF89a', 'gif'),
)

# Local bookkeeping, never uploaded
BUNDLE_METADATA_FILE = 'patchstorage.json'


class PatchstorageError(Exception):
    def __init__(self, message, auth_required=False, status=None, location=None):
        Exception.__init__(self, message)
        self.message = message
        self.auth_required = auth_required
        self.status = status
        self.location = location


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # urllib turns a redirected POST into a GET and drops the body; report redirects instead
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _clean_message(message):
    return re.sub(r'<[^>]+>', '', message or '').strip()


def _jwt_payload(token):
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(urlsafe_b64decode(payload.encode('ascii')).decode('utf-8'))
    except Exception:
        return {}


def _encode_form(fields):
    """urlencode, with list values sent as WordPress-style `key[]` repeats."""
    pairs = []
    for key, value in fields.items():
        if isinstance(value, (list, tuple)):
            pairs.extend(('%s[]' % key, str(v)) for v in value)
        elif value is not None:
            pairs.append((key, str(value)))
    return urllib.parse.urlencode(pairs).encode('utf-8')


def _encode_multipart(fields, filefield, filename, filedata):
    boundary = uuid4().hex
    lines = []
    for key, value in fields.items():
        lines.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (boundary, key, value)).encode('utf-8'))
    lines.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                  'Content-Type: application/octet-stream\r\n\r\n' % (boundary, filefield, filename.replace('"', ''))).encode('utf-8'))
    lines.append(filedata)
    lines.append(('\r\n--%s--\r\n' % boundary).encode('utf-8'))
    return b''.join(lines), 'multipart/form-data; boundary=%s' % boundary


def artwork_extension(data):
    """File extension for a PNG, JPEG, GIF or WebP image, or None for anything else."""
    for signature, extension in ARTWORK_SIGNATURES:
        if data.startswith(signature):
            return extension
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    return None


def bump_revision(revision):
    """'0.1' -> '0.2', '1.9' -> '1.10', 'v2' -> 'v3'; anything without a trailing number gets '.1'."""
    match = re.match(r'^(.*?)(\d+)$', (revision or '').strip())
    if match is None:
        return (revision.strip() + '.1') if revision and revision.strip() else '1.0'
    return match.group(1) + str(int(match.group(2)) + 1)


def read_bundle_metadata(bundlepath):
    path = os.path.join(bundlepath, BUNDLE_METADATA_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict) and 'id' in data:
            return data
    except (OSError, ValueError):
        pass
    return None


def write_bundle_metadata(bundlepath, patch_id, revision):
    with open(os.path.join(bundlepath, BUNDLE_METADATA_FILE), 'w', encoding='utf-8') as fh:
        json.dump({'id': int(patch_id), 'revision': str(revision)}, fh, ensure_ascii=False, indent=4)


def zip_bundle(bundlepath, destfile):
    """Zip as `<name>.pedalboard/...`, the layout the pedalboard installer expects."""
    bundlepath = bundlepath.rstrip(os.sep)
    topname = os.path.basename(bundlepath)
    with zipfile.ZipFile(destfile, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(bundlepath):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
            relroot = os.path.relpath(root, bundlepath)
            arcroot = topname if relroot == '.' else os.path.join(topname, relroot)
            zf.write(root, arcroot)
            for name in sorted(files):
                if name.startswith('.') or (relroot == '.' and name == BUNDLE_METADATA_FILE):
                    continue
                zf.write(os.path.join(root, name), os.path.join(arcroot, name))


class PatchstorageClient(object):
    def __init__(self, api_base, auth_file, platform_id, category_id, user_agent):
        self.api_base = api_base.rstrip('/')
        self.auth_file = auth_file
        self.platform_id = int(platform_id)
        self.category_id = int(category_id)
        self.user_agent = user_agent

    # --- auth ------------------------------------------------------------------------------

    def _load_auth(self):
        try:
            with open(self.auth_file, 'r', encoding='utf-8') as fh:
                auth = json.load(fh)
        except (OSError, ValueError):
            return None
        if not isinstance(auth, dict) or not auth.get('token'):
            return None
        if auth.get('expires', 0) <= time.time() + 60:
            self.logout()
            return None
        return auth

    def status(self):
        auth = self._load_auth()
        if auth is None:
            return {'logged_in': False}
        return {
            'logged_in': True,
            'username': auth.get('username'),
            'display_name': auth.get('display_name'),
            'expires': auth.get('expires'),
        }

    def login(self, username, password):
        resp = self._request('POST', '/auth/token',
                             body=_encode_form({'username': username, 'password': password}),
                             content_type='application/x-www-form-urlencoded',
                             authenticated=False)
        token = resp.get('token')
        if not token:
            raise PatchstorageError('Patchstorage did not return a login token')
        payload = _jwt_payload(token)
        user_id = payload.get('data', {}).get('user', {}).get('id')
        auth = {
            'token': token,
            'username': resp.get('username') or username,
            'display_name': resp.get('display_name') or resp.get('username') or username,
            'user_id': int(user_id) if user_id is not None and str(user_id).isdigit() else None,
            'expires': int(payload.get('exp') or (time.time() + TOKEN_LIFETIME)),
        }
        tmpfile = self.auth_file + '.tmp'
        fd = os.open(tmpfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(auth, fh)
        os.replace(tmpfile, self.auth_file)
        return self.status()

    def logout(self):
        try:
            os.remove(self.auth_file)
        except FileNotFoundError:
            pass

    def owns(self, patch):
        auth = self._load_auth()
        author = (patch or {}).get('author') or {}
        if auth is None or not author:
            return False
        if auth.get('user_id') is not None and author.get('id') == auth['user_id']:
            return True
        names = {(auth.get('username') or '').lower(), (auth.get('display_name') or '').lower()}
        return bool(names & {(author.get('slug') or '').lower(), (author.get('name') or '').lower()})

    # --- http ------------------------------------------------------------------------------

    def _request(self, method, path, body=None, content_type=None, authenticated=True):
        headers = {'User-Agent': self.user_agent, 'Accept': 'application/json'}
        if content_type:
            headers['Content-Type'] = content_type
        if authenticated:
            auth = self._load_auth()
            if auth is None:
                raise PatchstorageError('Log in to Patchstorage first', auth_required=True)
            headers['Authorization'] = 'Bearer ' + auth['token']

        req = urllib.request.Request(self.api_base + path, data=body, headers=headers, method=method)
        try:
            with _opener.open(req, timeout=HTTP_TIMEOUT) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                location = e.headers.get('Location') or '(no location)'
                logging.warning('[patchstorage] %s %s was redirected (%d) to %s', method, path, e.code, location)
                raise PatchstorageError('Patchstorage redirected %s %s to %s' % (method, path, location),
                                        status=e.code, location=e.headers.get('Location'))
            raw = e.read()
            try:
                err = json.loads(raw.decode('utf-8'))
            except ValueError:
                err = {}
            if not isinstance(err, dict):
                err = {}
            code = err.get('code') or ''
            logging.warning('[patchstorage] %s %s failed (%d): %s', method, path, e.code, raw[:500])
            message = _clean_message(err.get('message')) or 'Patchstorage error %d' % e.code
            if authenticated and (e.code == 401 or code.startswith('jwt_auth')):
                self.logout()
                raise PatchstorageError('Your Patchstorage login has expired, log in again', auth_required=True, status=e.code)
            raise PatchstorageError(message, status=e.code)
        except (urllib.error.URLError, OSError) as e:
            raise PatchstorageError('Cannot reach Patchstorage: %s' % getattr(e, 'reason', e))

        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8'))
        except ValueError:
            raise PatchstorageError('Unexpected response from Patchstorage')

    def get_patch(self, patch_id):
        return self._request('GET', '/patches/%d' % int(patch_id), authenticated=False)

    def _confirm_after_redirect(self, error, patch_id, file_id, artwork_id):
        """
        Patchstorage answers a successful PUT with a redirect to the patch (with a broken host),
        so read the patch back and accept it if it now carries the new uploads.
        """
        match = re.search(r'/patches/(\d+)', error.location or '')
        target = int(match.group(1)) if match else patch_id
        if target is None:
            raise error
        patch = self._request('GET', '/patches/%d?_=%d' % (int(target), int(time.time())), authenticated=False)
        files = {f.get('id') for f in patch.get('files') or []}
        if file_id not in files or (patch.get('artwork') or {}).get('id') != artwork_id:
            raise PatchstorageError('Patchstorage did not confirm the upload; check the pedalboard on patchstorage.com',
                                    status=error.status)
        return patch

    def _upload_file(self, filename, filedata):
        body, content_type = _encode_multipart({}, 'file', filename, filedata)
        resp = self._request('POST', '/files', body=body, content_type=content_type)
        if not resp.get('id'):
            raise PatchstorageError('Patchstorage did not accept %s' % filename)
        return int(resp['id'])

    def _delete_file(self, file_id):
        try:
            self._request('DELETE', '/files/%d' % int(file_id))
        except PatchstorageError as e:
            logging.warning('[patchstorage] could not delete file %s: %s', file_id, e.message)

    # --- share -----------------------------------------------------------------------------

    def share(self, bundlepath, fields, patch_id=None, artwork=None):
        """
        Upload the bundle and create (patch_id None) or update a patch.
        fields: title, content, revision, tags (list of str), license (int), state (int).
        artwork: image bytes, used only when the bundle has no screenshot.png.
        Returns {'id', 'url', 'revision'} and stamps patchstorage.json into the bundle.
        """
        title = (fields.get('title') or '').strip()
        content = (fields.get('content') or '').strip()
        revision = (fields.get('revision') or '').strip()
        tags = [t.strip() for t in fields.get('tags') or [] if t and t.strip()]
        if not title or not content or not revision:
            raise PatchstorageError('Title, description and revision are required')
        bad_tags = [t for t in tags if not 2 <= len(t) <= 25]
        if bad_tags:
            raise PatchstorageError('Tags must be 2 to 25 characters: %s' % ', '.join(bad_tags))
        try:
            license_id, state = int(fields['license']), int(fields['state'])
        except (KeyError, TypeError, ValueError):
            raise PatchstorageError('Choose a license and state')

        screenshot = os.path.join(bundlepath, 'screenshot.png')
        if os.path.isfile(screenshot):
            with open(screenshot, 'rb') as fh:
                artwork = fh.read()
            artwork_ext = 'png'
        elif artwork is None:
            raise PatchstorageError('This pedalboard has no screenshot; choose an artwork image')
        elif len(artwork) > MAX_ARTWORK_SIZE:
            raise PatchstorageError('The artwork image is too big; the limit is %d MB' % (MAX_ARTWORK_SIZE // (1024 * 1024)))
        else:
            artwork_ext = artwork_extension(artwork)
            if artwork_ext is None:
                raise PatchstorageError('The artwork must be a PNG, JPEG, GIF or WebP image')

        if self._load_auth() is None:
            raise PatchstorageError('Log in to Patchstorage first', auth_required=True)

        old_files = []
        if patch_id is not None:
            existing = self.get_patch(patch_id)
            if not self.owns(existing):
                raise PatchstorageError('You can only publish new revisions of your own Patchstorage pedalboards')
            old_files = [f['id'] for f in existing.get('files') or [] if f.get('id')]
            if (existing.get('artwork') or {}).get('id'):
                old_files.append(existing['artwork']['id'])

        bundlename = os.path.basename(bundlepath.rstrip(os.sep))
        uploaded = []
        submitted = False
        try:
            artwork_id = self._upload_file('%s.%s' % (os.path.splitext(bundlename)[0], artwork_ext), artwork)
            uploaded.append(artwork_id)

            fd, zippath = tempfile.mkstemp(suffix='.zip')
            os.close(fd)
            try:
                zip_bundle(bundlepath, zippath)
                with open(zippath, 'rb') as fh:
                    file_id = self._upload_file(bundlename + '.zip', fh.read())
                uploaded.append(file_id)
            finally:
                os.remove(zippath)

            # JSON, not a form: Patchstorage rejects ids that arrive as strings
            body = json.dumps({
                'title': title,
                'content': content,
                'revision': revision,
                'files': [file_id],
                'artwork': artwork_id,
                'tags': tags,
                'categories': [self.category_id],
                'license': license_id,
                'state': state,
                'platform': self.platform_id,
            }).encode('utf-8')
            submitted = True
            try:
                if patch_id is None:
                    patch = self._request('POST', '/patches', body=body, content_type='application/json')
                else:
                    patch = self._request('PUT', '/patches/%d' % int(patch_id), body=body, content_type='application/json')
            except PatchstorageError as e:
                if e.status is None or not 300 <= e.status < 400:
                    raise
                patch = self._confirm_after_redirect(e, patch_id, file_id, artwork_id)
            if not patch.get('id'):
                raise PatchstorageError('Patchstorage did not return the published pedalboard')
        except Exception as e:
            # A 4xx means the patch was refused; after a redirect, 5xx or lost connection it may
            # exist and point at these uploads, so they are left in place.
            status = getattr(e, 'status', None)
            if not submitted or (status is not None and 400 <= status < 500):
                for orphan in uploaded:
                    self._delete_file(orphan)
            else:
                logging.warning('[patchstorage] outcome of the patch submit is unknown, keeping uploads %s', uploaded)
            raise

        # Only drop the old uploads once the patch is confirmed to point at the new ones.
        now_attached = {f.get('id') for f in patch.get('files') or []}
        now_attached.add((patch.get('artwork') or {}).get('id'))
        if file_id in now_attached and artwork_id in now_attached:
            for old in old_files:
                if old not in now_attached:
                    self._delete_file(old)

        write_bundle_metadata(bundlepath, patch['id'], patch.get('revision') or revision)
        return {'id': int(patch['id']), 'url': patch.get('url'), 'revision': patch.get('revision') or revision}
