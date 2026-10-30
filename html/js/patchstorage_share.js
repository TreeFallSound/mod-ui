// SPDX-FileCopyrightText: 2026 pi-Stomp
// SPDX-License-Identifier: AGPL-3.0-or-later

// Share a user pedalboard on Patchstorage. The mod-ui server does the login and the
// upload (see mod/patchstorage_share.py); this window collects what to publish.
//
//   $('#patchstorage-share-window').patchstorageShareBox('open', bundlepath, onShared)

JqueryClass('patchstorageShareBox', {
    init: function () {
        var self = $(this)

        self.data('taxonomies', null)

        self.find('.js-close').click(function () {
            if (!self.data('busy')) {
                self.patchstorageShareBox('close')
            }
            return false
        })
        self.keydown(function (e) {
            if (e.keyCode == 27 && !self.data('busy')) {
                self.patchstorageShareBox('close')
                return false
            }
        })

        self.find('.js-step-login').submit(function () {
            self.patchstorageShareBox('login')
            return false
        })
        self.find('.js-step-form').submit(function () {
            self.patchstorageShareBox('publish')
            return false
        })
        self.find('.js-logout').click(function () {
            $.ajax({
                url: '/patchstorage/logout',
                method: 'POST',
                dataType: 'json',
                complete: function () {
                    self.patchstorageShareBox('showLogin', '')
                },
            })
            return false
        })
        self.find('input[name=mode]').change(function () {
            self.patchstorageShareBox('applyMode')
        })
        self.find('.js-artwork-choose').click(function () {
            self.find('input[name=artwork]').click()
            return false
        })
        self.find('input[name=artwork]').change(function () {
            self.patchstorageShareBox('chooseArtwork', this.files[0])
        })

        return self
    },

    open: function (bundlepath, onShared) {
        var self = $(this)
        self.data('bundlepath', bundlepath)
        self.data('onShared', onShared || function () {})
        self.data('info', null)
        self.find('.js-error').text('')
        self.patchstorageShareBox('showStep', 'loading', 'Preparing pedalboard...')
        self.removeClass('mod-hidden').show()
        self.focus()

        // the artwork is the pedalboard screenshot; let any pending one finish first
        desktop.waitForScreenshot(false, bundlepath, function () {
            self.patchstorageShareBox('loadInfo', true)
        })
    },

    close: function () {
        var self = $(this)
        self.data('busy', false)
        self.find('input[type=password]').val('')
        self.patchstorageShareBox('clearArtwork')
        self.addClass('mod-hidden').hide()
    },

    showStep: function (step, message) {
        var self = $(this)
        self.find('.ps-share-step').hide()
        self.find('.js-step-' + step).show()
        if (message !== undefined) {
            self.find('.js-step-' + step + ' .js-message').text(message)
        }
    },

    fail: function (message) {
        var self = $(this)
        self.patchstorageShareBox('close')
        new Notification('error', message, 6000)
    },

    loadInfo: function (generateIfMissing) {
        var self = $(this)
        var bundlepath = self.data('bundlepath')

        $.ajax({
            url: '/patchstorage/share/info',
            data: { bundlepath: bundlepath },
            cache: false,
            dataType: 'json',
            success: function (info) {
                if (!info.ok) {
                    self.patchstorageShareBox('fail', info.error)
                    return
                }
                if (!info.has_screenshot && generateIfMissing) {
                    self.patchstorageShareBox('showStep', 'loading', 'Taking a screenshot of the pedalboard...')
                    desktop.waitForScreenshot(true, bundlepath, function () {
                        self.patchstorageShareBox('loadInfo', false)
                    })
                    return
                }
                self.data('info', info)
                if (info.auth.logged_in) {
                    self.patchstorageShareBox('showForm')
                } else {
                    self.patchstorageShareBox('showLogin', '')
                }
            },
            error: function () {
                self.patchstorageShareBox('fail', 'Could not read the pedalboard')
            },
        })
    },

    showLogin: function (error) {
        var self = $(this)
        self.find('.js-step-login .js-error').text(error || '')
        self.patchstorageShareBox('showStep', 'login')
        self.find('.js-step-login input[name=username]').focus()
    },

    login: function () {
        var self = $(this)
        var form = self.find('.js-step-login')
        form.find('.js-error').text('')
        form.find('button').prop('disabled', true)

        $.ajax({
            url: '/patchstorage/login',
            method: 'POST',
            data: {
                username: form.find('input[name=username]').val(),
                password: form.find('input[name=password]').val(),
            },
            dataType: 'json',
            success: function (resp) {
                form.find('input[name=password]').val('')
                if (!resp.ok) {
                    form.find('.js-error').text(resp.error)
                    return
                }
                // ownership of an earlier upload depends on who is logged in
                self.patchstorageShareBox('showStep', 'loading', 'Loading...')
                self.patchstorageShareBox('loadInfo', false)
            },
            error: function () {
                form.find('.js-error').text('Could not reach the pi-Stomp')
            },
            complete: function () {
                form.find('button').prop('disabled', false)
            },
        })
    },

    loadTaxonomies: function (callback) {
        var self = $(this)
        if (self.data('taxonomies')) {
            callback(self.data('taxonomies'))
            return
        }

        var base = PATCHSTORAGE_API_URL.replace(/\/patches\/?$/, '')
        var names = ['licenses', 'states']
        var result = {}
        var failed = false

        names.forEach(function (name) {
            $.ajax({
                url: base + '/' + name + '?per_page=100',
                cache: true,
                dataType: 'json',
                success: function (items) {
                    result[name] = items
                },
                error: function () {
                    failed = true
                },
                complete: function () {
                    if (Object.keys(result).length + (failed ? 1 : 0) < names.length) {
                        return
                    }
                    if (failed) {
                        callback(null)
                        return
                    }
                    self.data('taxonomies', result)
                    callback(result)
                },
            })
        })
    },

    showForm: function () {
        var self = $(this)
        var info = self.data('info')
        var form = self.find('.js-step-form')

        self.patchstorageShareBox('showStep', 'loading', 'Loading Patchstorage options...')

        self.patchstorageShareBox('loadTaxonomies', function (taxonomies) {
            if (!taxonomies) {
                self.patchstorageShareBox('fail', 'Could not reach Patchstorage')
                return
            }

            function fillSelect(name, items, placeholder) {
                var select = form.find('select[name=' + name + ']').empty()
                if (placeholder) {
                    select.append($('<option value="">').text(placeholder))
                }
                items.forEach(function (item) {
                    select.append($('<option>').val(item.id).text(item.name).attr('data-slug', item.slug))
                })
            }
            // A license is a choice the author makes, so it is never preselected.
            // "custom" needs a license text, which this form does not collect.
            fillSelect('license', taxonomies.licenses.filter(function (l) { return l.slug != 'custom' }),
                       'Choose a license...')
            fillSelect('state', taxonomies.states)

            form.find('.js-username').text(info.auth.display_name || info.auth.username)

            var patch = info.patch
            var mode = form.find('.js-mode')
            if (patch && patch.owned) {
                mode.show().find('.js-patch-link').attr('href', patch.url).text(patch.title)
                mode.find('.js-current-revision').text(patch.revision)
                form.find('input[name=mode][value=update]').prop('checked', true)
                form.find('.js-not-owned').hide()
            } else {
                mode.hide()
                form.find('input[name=mode][value=new]').prop('checked', true)
                form.find('.js-not-owned').toggle(!!patch).find('.js-author').text(patch ? patch.author : '')
            }

            self.patchstorageShareBox('clearArtwork')
            form.find('.js-artwork').toggle(!info.has_screenshot)

            self.patchstorageShareBox('applyMode')
            self.patchstorageShareBox('showStep', 'form')
            form.find('input[name=title]').focus()
        })
    },

    // Fill the fields for "publish a new revision" or "share as a new pedalboard".
    applyMode: function () {
        var self = $(this)
        var info = self.data('info')
        var form = self.find('.js-step-form')
        var update = form.find('input[name=mode]:checked').val() == 'update'
        var patch = update ? info.patch : null

        function selectBySlug(name, slug) {
            var option = form.find('select[name=' + name + '] option[data-slug="' + slug + '"]')
            if (option.length) {
                form.find('select[name=' + name + ']').val(option.val())
            }
        }

        if (patch) {
            form.find('input[name=title]').val(patch.title)
            form.find('textarea[name=content]').val(htmlToText(patch.content))
            form.find('input[name=revision]').val(patch.next_revision)
            form.find('input[name=tags]').val(patch.tags.join(', '))
            form.find('select[name=license]').val(String(patch.license))
            form.find('select[name=state]').val(String(patch.state))
            form.find('.js-publish').text('Publish revision')
        } else {
            var description = 'A pedalboard for pi-Stomp.'
            if (info.plugins.length) {
                description += '\n\nPlugins: ' + info.plugins.join(', ')
            }
            form.find('input[name=title]').val(info.title)
            form.find('textarea[name=content]').val(description)
            form.find('input[name=revision]').val('1.0')
            form.find('input[name=tags]').val(info.default_tags.join(', '))
            form.find('select[name=license]').val('')
            selectBySlug('state', 'ready-to-go')
            form.find('.js-publish').text('Publish')
        }
    },

    chooseArtwork: function (file) {
        var self = $(this)
        var form = self.find('.js-step-form')
        if (!file) {
            return
        }
        self.patchstorageShareBox('clearArtwork')
        if (['image/png', 'image/jpeg', 'image/gif', 'image/webp'].indexOf(file.type) < 0) {
            form.find('.js-error').text('The artwork must be a PNG, JPEG, GIF or WebP image.')
            return
        }
        if (file.size > 5 * 1024 * 1024) {
            form.find('.js-error').text('The artwork image is too big; the limit is 5 MB.')
            return
        }
        form.find('.js-error').text('')
        self.data('artwork', file)
        self.data('artworkUrl', URL.createObjectURL(file))
        form.find('.js-artwork-preview').attr('src', self.data('artworkUrl')).show()
        form.find('.js-artwork-name').text(file.name)
    },

    clearArtwork: function () {
        var self = $(this)
        if (self.data('artworkUrl')) {
            URL.revokeObjectURL(self.data('artworkUrl'))
        }
        self.data('artwork', null)
        self.data('artworkUrl', null)
        self.find('input[name=artwork]').val('')
        self.find('.js-artwork-preview').removeAttr('src').hide()
        self.find('.js-artwork-name').text('No screenshot found; choose an image.')
    },

    publish: function () {
        var self = $(this)
        var form = self.find('.js-step-form')
        var data = {
            bundlepath: self.data('bundlepath'),
            mode: form.find('input[name=mode]:checked').val() || 'new',
            title: form.find('input[name=title]').val().trim(),
            content: form.find('textarea[name=content]').val().trim(),
            revision: form.find('input[name=revision]').val().trim(),
            tags: form.find('input[name=tags]').val(),
            license: form.find('select[name=license]').val(),
            state: form.find('select[name=state]').val(),
        }

        var missing = []
        if (!data.title) missing.push('a title')
        if (!data.content) missing.push('a description')
        if (!data.revision) missing.push('a revision')
        if (!data.license) missing.push('a license')
        if (!self.data('info').has_screenshot && !self.data('artwork')) missing.push('an artwork image')
        if (missing.length) {
            form.find('.js-error').text('Please enter ' + missing.join(', ') + '.')
            return
        }
        form.find('.js-error').text('')

        var body = new FormData()
        Object.keys(data).forEach(function (key) {
            body.append(key, data[key])
        })
        if (!self.data('info').has_screenshot && self.data('artwork')) {
            body.append('artwork', self.data('artwork'))
        }

        self.data('busy', true)
        self.patchstorageShareBox('showStep', 'loading', 'Uploading to Patchstorage...')

        $.ajax({
            url: '/patchstorage/share',
            method: 'POST',
            data: body,
            processData: false,
            contentType: false,
            dataType: 'json',
            success: function (resp) {
                self.data('busy', false)
                if (resp.ok) {
                    self.find('.js-step-done .js-patch-link').attr('href', resp.url)
                    self.find('.js-step-done .js-revision').text(resp.revision)
                    self.patchstorageShareBox('showStep', 'done')
                    self.data('onShared')(resp)
                } else if (resp.auth_required) {
                    self.patchstorageShareBox('showLogin', resp.error)
                } else {
                    self.patchstorageShareBox('showStep', 'form')
                    form.find('.js-error').text(resp.error)
                }
            },
            error: function () {
                self.data('busy', false)
                self.patchstorageShareBox('showStep', 'form')
                form.find('.js-error').text('Could not reach the pi-Stomp')
            },
        })
    },
})

// Patchstorage returns the description as HTML. DOMParser runs no scripts and loads no images.
function htmlToText(html) {
    var withBreaks = (html || '').replace(/<br\s*\/?>/gi, '\n').replace(/<\/p>\s*/gi, '\n\n')
    return new DOMParser().parseFromString(withBreaks, 'text/html').body.textContent.trim()
}
