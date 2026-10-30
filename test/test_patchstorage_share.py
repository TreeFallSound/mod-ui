#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 pi-Stomp
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Sharing pedalboards to Patchstorage, against a local stand-in for its API.

The stand-in records every request, so the tests can check what would reach
patchstorage.com without touching it.
"""

import base64
import email.policy
import io
import json
import os
import shutil
import stat
import tempfile
import threading
import time
import unittest
import urllib.parse
import zipfile
from collections import namedtuple
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mod.patchstorage_share import PatchstorageClient, PatchstorageError, bump_revision

USER_ID = 19718

UploadedFile = namedtuple('UploadedFile', 'filename value')
JPEG = b'\xff\xd8\xff\xe0' + b'jpeg'


def make_token(user_id=USER_ID, exp=None):
    def part(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip('=')
    exp = exp or int(time.time()) + 7 * 24 * 3600
    return '%s.%s.sig' % (part({'alg': 'HS256'}), part({'exp': exp, 'data': {'user': {'id': str(user_id)}}}))


class FakePatchstorage(object):
    def __init__(self):
        self.requests = []
        self.files = {}
        self.patches = {}
        self.next_id = 1000
        self.reject_token = False
        self.fail_patch = False
        self.redirect_after_write = False
        self.password = 'secret'

    def new_id(self):
        self.next_id += 1
        return self.next_id

    def patch_response(self, pid):
        p = self.patches[pid]
        return dict(p, id=pid, url='https://patchstorage.com/%d/' % pid,
                    files=[{'id': f} for f in p['files']], artwork={'id': p['artwork']})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def form(self):
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length)
        ctype = self.headers.get('Content-Type', '')
        if ctype.startswith('multipart/form-data'):
            msg = BytesParser(policy=email.policy.HTTP).parsebytes(b'Content-Type: ' + ctype.encode() + b'\r\n\r\n' + raw)
            return {part.get_param('name', header='content-disposition'):
                    UploadedFile(part.get_filename(), part.get_payload(decode=True)) for part in msg.iter_parts()}
        if ctype.startswith('application/json'):
            return json.loads(raw.decode())
        return urllib.parse.parse_qs(raw.decode())

    def handle_any(self, method):
        api = self.server.api
        path = self.path.split('?')[0].rstrip('/')
        form = self.form() if method in ('POST', 'PUT') else {}
        auth = self.headers.get('Authorization')
        api.requests.append({'method': method, 'path': path, 'form': form, 'auth': auth,
                             'agent': self.headers.get('User-Agent')})

        if path == '/auth/token':
            if form.get('password') != [api.password]:
                return self.reply(403, {'code': 'incorrect_password',
                                        'message': '<strong>Error:</strong> The password is incorrect.'})
            return self.reply(200, {'token': make_token(), 'username': form['username'][0], 'display_name': 'TFS'})

        if path.startswith('/patches/') and method == 'GET':
            pid = int(path.split('/')[2])
            if pid not in api.patches:
                return self.reply(404, {'code': 'rest_post_invalid_id', 'message': 'Invalid post ID.'})
            return self.reply(200, api.patch_response(pid))

        if not auth or api.reject_token:
            return self.reply(403, {'code': 'jwt_auth_invalid_token', 'message': 'Expired token'})

        if path == '/files' and method == 'POST':
            fid = api.new_id()
            api.files[fid] = (form['file'].filename, form['file'].value)
            return self.reply(201, {'id': fid, 'filename': form['file'].filename})

        if path.startswith('/files/') and method == 'DELETE':
            api.files.pop(int(path.split('/')[2]), None)
            return self.reply(200, {'deleted': True})

        if path == '/patches' and method == 'POST' or path.startswith('/patches/') and method == 'PUT':
            # Like the real API: id fields must arrive as JSON integers, not strings
            def is_int(v):
                return isinstance(v, int) and not isinstance(v, bool)
            invalid = [k for k in ('files', 'artwork', 'categories', 'license', 'platform', 'state')
                       if not (all(map(is_int, form.get(k))) if isinstance(form.get(k), list) else is_int(form.get(k)))]
            if invalid:
                return self.reply(400, {'code': 'rest_invalid_param', 'message': 'Invalid parameter(s): ' + ', '.join(invalid)})
            if api.fail_patch == 302:
                self.send_response(302)
                self.send_header('Location', 'https://patchstorage.com/elsewhere/')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if api.fail_patch:
                return self.reply(api.fail_patch, {'code': 'broken', 'message': 'Something broke'})
            pid = api.new_id() if method == 'POST' else int(path.split('/')[2])
            if method == 'PUT' and api.patches[pid]['author']['id'] != USER_ID:
                return self.reply(403, {'code': 'rest_cannot_edit', 'message': 'Sorry, you are not allowed to edit this post.'})
            api.patches[pid] = {
                'title': form['title'], 'content': form['content'], 'revision': form['revision'],
                'files': form['files'], 'artwork': form['artwork'], 'categories': form['categories'],
                'license': form['license'], 'state': form['state'], 'preview_url': form.get('preview_url'),
                'tags': [{'name': t} for t in form.get('tags', [])], 'platform': form['platform'],
                'author': {'id': USER_ID, 'slug': 'treefallsound', 'name': 'treefallsound'},
            }
            if api.redirect_after_write:
                # what patchstorage.com does: apply the write, then redirect to a host without ".com"
                self.send_response(302)
                self.send_header('Location', 'https://patchstorage/api/beta/patches/%d' % pid)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            return self.reply(201 if method == 'POST' else 200, api.patch_response(pid))

        self.reply(404, {'code': 'rest_no_route', 'message': 'No route'})

    def do_GET(self):
        self.handle_any('GET')

    def do_POST(self):
        self.handle_any('POST')

    def do_PUT(self):
        self.handle_any('PUT')

    def do_DELETE(self):
        self.handle_any('DELETE')


class ShareTestCase(unittest.TestCase):
    def setUp(self):
        self.api = FakePatchstorage()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.api = self.api
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        self.tmp = tempfile.mkdtemp()
        self.bundle = os.path.join(self.tmp, 'pedalboards', 'Crunch.pedalboard')
        os.makedirs(os.path.join(self.bundle, 'effect-1'))
        for name, data in (('manifest.ttl', b'@prefix'), ('Crunch.ttl', b'board'), ('screenshot.png', b'PNG'),
                           ('effect-1/model.nam', b'nam'), ('.DS_Store', b'junk')):
            with open(os.path.join(self.bundle, name), 'wb') as fh:
                fh.write(data)

        self.client = PatchstorageClient('http://127.0.0.1:%d' % self.server.server_port,
                                         os.path.join(self.tmp, 'auth.json'), 12520, 372, 'pi-Stomp mod-ui/test')
        self.fields = {'title': 'Crunch', 'content': 'A crunchy board', 'revision': '1.0',
                       'tags': ['pedalboard', ' pi-stomp ', ''], 'license': '4181', 'state': '151'}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp)

    def login(self):
        return self.client.login('treefallsound', 'secret')


class TestAuth(ShareTestCase):
    def test_login_keeps_token_not_password(self):
        status = self.login()
        self.assertTrue(status['logged_in'])
        self.assertEqual(status['username'], 'treefallsound')
        with open(self.client.auth_file) as fh:
            saved = fh.read()
        self.assertNotIn('secret', saved)
        self.assertEqual(json.loads(saved)['user_id'], USER_ID)
        self.assertEqual(stat.S_IMODE(os.stat(self.client.auth_file).st_mode), 0o600)

    def test_wrong_password_message_has_no_html(self):
        self.api.password = 'other'
        with self.assertRaises(PatchstorageError) as ctx:
            self.login()
        self.assertEqual(ctx.exception.message, 'Error: The password is incorrect.')
        self.assertFalse(self.client.status()['logged_in'])

    def test_expired_token_is_dropped(self):
        with open(self.client.auth_file, 'w') as fh:
            json.dump({'token': make_token(exp=int(time.time()) - 5), 'expires': int(time.time()) - 5}, fh)
        self.assertFalse(self.client.status()['logged_in'])
        self.assertFalse(os.path.exists(self.client.auth_file))

    def test_logout(self):
        self.login()
        self.client.logout()
        self.assertFalse(self.client.status()['logged_in'])

    def test_user_agent_sent(self):
        self.login()
        self.assertEqual(self.api.requests[0]['agent'], 'pi-Stomp mod-ui/test')


class TestShare(ShareTestCase):
    def test_new_share(self):
        self.login()
        result = self.client.share(self.bundle, self.fields)

        patch = self.api.patches[result['id']]
        self.assertEqual(patch['platform'], 12520)
        self.assertEqual(patch['categories'], [372])
        self.assertEqual((patch['license'], patch['state']), (4181, 151))
        self.assertEqual([t['name'] for t in patch['tags']], ['pedalboard', 'pi-stomp'])
        self.assertEqual(self.api.files[patch['artwork']], ('Crunch.png', b'PNG'))
        self.assertTrue(all(r['auth'].startswith('Bearer ') for r in self.api.requests[1:]))

        name, data = self.api.files[patch['files'][0]]
        self.assertEqual(name, 'Crunch.pedalboard.zip')
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        self.assertIn('Crunch.pedalboard/manifest.ttl', names)
        self.assertIn('Crunch.pedalboard/effect-1/model.nam', names)
        self.assertNotIn('Crunch.pedalboard/.DS_Store', names)

        with open(os.path.join(self.bundle, 'patchstorage.json')) as fh:
            self.assertEqual(json.load(fh), {'id': result['id'], 'revision': '1.0'})

    def test_preview_url(self):
        self.login()
        first = self.client.share(self.bundle, dict(self.fields, preview_url=' https://youtu.be/abc '))
        self.assertEqual(self.api.patches[first['id']]['preview_url'], 'https://youtu.be/abc')
        self.client.share(self.bundle, dict(self.fields, revision='1.1'), patch_id=first['id'])
        self.assertEqual(self.api.patches[first['id']]['preview_url'], '', 'an empty field clears the link')

    def test_broken_links_are_left_out(self):
        self.login()
        os.symlink('@greenback', os.path.join(self.bundle, 'effect-1', '@greenback'))
        os.symlink('missing.wav', os.path.join(self.bundle, 'gone.wav'))
        os.symlink('Crunch.ttl', os.path.join(self.bundle, 'alias.ttl'))
        result = self.client.share(self.bundle, self.fields)
        name, data = self.api.files[self.api.patches[result['id']]['files'][0]]
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        self.assertNotIn('Crunch.pedalboard/effect-1/@greenback', names)
        self.assertNotIn('Crunch.pedalboard/gone.wav', names)
        self.assertIn('Crunch.pedalboard/alias.ttl', names)
        self.assertIn('Crunch.pedalboard/effect-1/model.nam', names)

    def test_bookkeeping_file_not_uploaded(self):
        self.login()
        first = self.client.share(self.bundle, self.fields)
        second = self.client.share(self.bundle, dict(self.fields, revision='1.1'), patch_id=first['id'])
        name, data = self.api.files[self.api.patches[second['id']]['files'][0]]
        self.assertNotIn('Crunch.pedalboard/patchstorage.json', zipfile.ZipFile(io.BytesIO(data)).namelist())

    def test_update_replaces_files_and_cleans_old_ones(self):
        self.login()
        first = self.client.share(self.bundle, self.fields)
        old = set(self.api.files)
        with open(os.path.join(self.bundle, 'screenshot.png'), 'wb') as fh:
            fh.write(b'PNG2')

        second = self.client.share(self.bundle, dict(self.fields, revision='1.1'), patch_id=first['id'])

        self.assertEqual(second['id'], first['id'])
        patch = self.api.patches[first['id']]
        self.assertEqual(patch['revision'], '1.1')
        self.assertEqual(self.api.files[patch['artwork']], ('Crunch.png', b'PNG2'))
        self.assertFalse(old & set(self.api.files), 'old zip and artwork should be deleted')
        self.assertEqual(len(self.api.files), 2)
        with open(os.path.join(self.bundle, 'patchstorage.json')) as fh:
            self.assertEqual(json.load(fh)['revision'], '1.1')

    def test_screenshot_wins_over_chosen_artwork(self):
        self.login()
        result = self.client.share(self.bundle, self.fields, artwork=JPEG)
        self.assertEqual(self.api.files[self.api.patches[result['id']]['artwork']], ('Crunch.png', b'PNG'))

    def test_chosen_artwork_without_screenshot(self):
        self.login()
        os.remove(os.path.join(self.bundle, 'screenshot.png'))
        result = self.client.share(self.bundle, self.fields, artwork=JPEG)
        self.assertEqual(self.api.files[self.api.patches[result['id']]['artwork']], ('Crunch.jpg', JPEG))

    def test_bad_artwork_is_rejected_before_upload(self):
        self.login()
        os.remove(os.path.join(self.bundle, 'screenshot.png'))
        for bad in (b'<svg/>', JPEG + b'0' * (5 * 1024 * 1024)):
            with self.assertRaises(PatchstorageError):
                self.client.share(self.bundle, self.fields, artwork=bad)
        self.assertEqual(len(self.api.requests), 1, 'only the login should have reached the server')

    def test_refused_publish_removes_uploads(self):
        self.login()
        self.api.fail_patch = 400
        with self.assertRaises(PatchstorageError) as ctx:
            self.client.share(self.bundle, self.fields)
        self.assertEqual(ctx.exception.message, 'Something broke')
        self.assertFalse(self.api.files, 'uploaded zip and artwork should be deleted')
        self.assertFalse(os.path.exists(os.path.join(self.bundle, 'patchstorage.json')))

    def test_uncertain_publish_keeps_uploads(self):
        self.login()
        for status in (500, 302):
            self.api.fail_patch = status
            with self.assertRaises(PatchstorageError):
                self.client.share(self.bundle, self.fields)
        self.assertEqual(len(self.api.files), 4, 'the patch may exist, so its uploads stay')

    def test_redirect_after_successful_write_is_success(self):
        self.login()
        self.api.redirect_after_write = True
        first = self.client.share(self.bundle, self.fields)
        old = set(self.api.files)

        second = self.client.share(self.bundle, dict(self.fields, revision='0.3'), patch_id=first['id'])

        self.assertEqual(second['id'], first['id'])
        self.assertEqual(second['revision'], '0.3')
        self.assertFalse(old & set(self.api.files), 'old zip and artwork should be deleted')
        with open(os.path.join(self.bundle, 'patchstorage.json')) as fh:
            self.assertEqual(json.load(fh), {'id': first['id'], 'revision': '0.3'})
        self.assertNotIn('patchstorage/api', ' '.join(r['path'] for r in self.api.requests),
                         'the broken redirect target must not be requested')

    def test_redirect_is_reported_not_followed(self):
        self.login()
        self.api.fail_patch = 302
        with self.assertRaises(PatchstorageError) as ctx:
            self.client.share(self.bundle, self.fields)
        self.assertEqual(ctx.exception.message,
                         'Patchstorage redirected POST /patches to https://patchstorage.com/elsewhere/')
        self.assertEqual([r['method'] for r in self.api.requests[-1:]], ['POST'], 'the redirect must not be followed')

    def test_cannot_update_someone_elses_patch(self):
        self.login()
        self.api.patches[555] = {'title': 'x', 'content': 'x', 'revision': '1', 'files': [], 'artwork': 0,
                                 'tags': [], 'platform': 12520, 'author': {'id': 1, 'slug': 'crosenau', 'name': 'crosenau'}}
        with self.assertRaises(PatchstorageError) as ctx:
            self.client.share(self.bundle, self.fields, patch_id=555)
        self.assertIn('your own', ctx.exception.message)
        self.assertFalse(self.api.files, 'nothing should be uploaded')

    def test_requires_login(self):
        with self.assertRaises(PatchstorageError) as ctx:
            self.client.share(self.bundle, self.fields)
        self.assertTrue(ctx.exception.auth_required)
        self.assertFalse(self.api.requests)

    def test_rejected_token_logs_out(self):
        self.login()
        self.api.reject_token = True
        with self.assertRaises(PatchstorageError) as ctx:
            self.client.share(self.bundle, self.fields)
        self.assertTrue(ctx.exception.auth_required)
        self.assertFalse(self.client.status()['logged_in'])

    def test_missing_screenshot(self):
        self.login()
        os.remove(os.path.join(self.bundle, 'screenshot.png'))
        with self.assertRaises(PatchstorageError) as ctx:
            self.client.share(self.bundle, self.fields)
        self.assertIn('screenshot', ctx.exception.message)

    def test_validation(self):
        self.login()
        for bad in ({'title': ' '}, {'revision': ''}, {'license': None}, {'state': 'x'}, {'tags': ['x']},
                    {'tags': [' ', '']}, {'preview_url': 'youtube.com/watch?v=1'}, {'preview_url': 'javascript:alert(1)'}):
            with self.assertRaises(PatchstorageError):
                self.client.share(self.bundle, dict(self.fields, **bad))
        self.assertEqual(len(self.api.requests), 1, 'only the login should have reached the server')

    def test_owns(self):
        self.login()
        self.assertTrue(self.client.owns({'author': {'id': USER_ID}}))
        self.assertTrue(self.client.owns({'author': {'id': 1, 'slug': 'treefallsound'}}))
        self.assertFalse(self.client.owns({'author': {'id': 1, 'slug': 'crosenau', 'name': 'crosenau'}}))


class TestRevision(unittest.TestCase):
    def test_bump(self):
        self.assertEqual(bump_revision('0.1'), '0.2')
        self.assertEqual(bump_revision('1.9'), '1.10')
        self.assertEqual(bump_revision('v2'), 'v3')
        self.assertEqual(bump_revision('beta'), 'beta.1')
        self.assertEqual(bump_revision(''), '1.0')
        self.assertEqual(bump_revision(None), '1.0')


if __name__ == '__main__':
    unittest.main()
