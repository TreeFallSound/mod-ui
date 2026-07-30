function objectEmpty(obj) {
    for (var _ in obj) return false
    return true
}

JqueryClass('patchstoragePedalboardsBox', {
    init: function (options) {
        var self = $(this)

        options = $.extend({
            resultCanvas: self.find('.js-patchstorage-pedalboards'),
            removePedalboard: function (bundle, callback) {
                callback(false)
            },
            loadPedalboard: function (bundle, callback) {
                callback(false)
            },
            windowName: "Patchstorage Pedalboards",
            info: null,
            isMainWindow: true,
            localPedalboards: null,
            cloudPedalboards: null,
            cloudPedalboardsLoaded: false,
            localPedalboardsLoaded: false,
            mergedPedalboards: null,
            xhrs: []
        }, options)

        self.data(options)

        var searchbox = self.find('input[type=search]')
        searchbox.val("")
        self.data('searchbox', searchbox)
        searchbox.cleanableInput()

        var lastKeyTimeout = null
        function scheduleSearch() {
            if (lastKeyTimeout != null) {
                clearTimeout(lastKeyTimeout)
            }
            lastKeyTimeout = setTimeout(function () {
                self.patchstoragePedalboardsBox('search')
            }, 400);
        }

        searchbox.keydown(function (e) {
            if (e.keyCode == 13) {
                if (lastKeyTimeout != null) {
                    clearTimeout(lastKeyTimeout)
                    lastKeyTimeout = null
                }
                self.patchstoragePedalboardsBox('search')
                return false
            }
            else if (e.keyCode == 8 || e.keyCode == 46) {
                scheduleSearch()
            }
        })
        searchbox.keypress(function (e) {
            if (e.which == 13)
                return
            scheduleSearch()
        })
        searchbox.on('paste', function () {
            scheduleSearch()
        })

        self.find('input:checkbox[name=installed]').click(function () {
            self.find('input:checkbox[name=non-installed]').prop('checked', false)
            self.find('input:checkbox[name=outdated]').prop('checked', false)
            self.patchstoragePedalboardsBox('search')
        })
        self.find('input:checkbox[name=non-installed]').click(function () {
            self.find('input:checkbox[name=installed]').prop('checked', false)
            self.find('input:checkbox[name=outdated]').prop('checked', false)
            self.patchstoragePedalboardsBox('search')
        })
        self.find('input:checkbox[name=outdated]').click(function () {
            self.find('input:checkbox[name=non-installed]').prop('checked', false)
            self.find('input:checkbox[name=installed]').prop('checked', false)
            self.patchstoragePedalboardsBox('search')
        })

        self.find('#patchstorage_pedalboards_update_all').click(function () {
            self.data('cloudPedalboards', null)
            self.data('localPedalboards', null)
            self.data('mergedPedalboards', null)
            self.patchstoragePedalboardsBox('search')
        })

        options.open = function () {
            self.removeClass('mod-hidden')
            self.css({ display: 'block', opacity: 1, 'z-index': 1000 })
            self.patchstoragePedalboardsBox('search')
            return false
        }

        self.removeClass('mod-hidden')
        self.window(options)
        return self
    },

    cleanResults: function () {
        var self = $(this)
        self.find('.plugins-wrapper').html('')
    },

    transformCloudPedalboard: function (p) {
        p.psid = p.id.toString()
        p.cloud_revision = p.revision
        p.name = unescape(p.title)
        p.label = unescape(p.title)
        p.comment = (p.content) ? unescape(p.content) : unescape(p.excerpt || '')
        p.thumbnail_href = (p.artwork && p.artwork.thumbnail_url) ? p.artwork.thumbnail_url : ''
        p.screenshot_href = (p.artwork && p.artwork.url) ? p.artwork.url : p.thumbnail_href
        p.state = (p.state && p.state.slug) ? p.state.slug : null
        p.uploader = (p.author && p.author.slug) ? p.author.slug : ''
        p.status = 'available'
        p.uri = 'ps-pedalboard:' + p.psid
        p.supported = true

        // Prefer a .pedalboard.zip file; otherwise first file
        p.file = null
        if (p.files && p.files.length > 0) {
            p.files.forEach(function (f) {
                if (!p.file && f.filename && f.filename.indexOf('.pedalboard') >= 0) {
                    p.file = f
                }
            })
            if (!p.file) {
                p.file = p.files[0]
            }
        }

        var tags = []
        if (p.categories) {
            p.categories.forEach(function (item) {
                var name = item.slug.replace(/-/g, '').toLowerCase()
                if (!tags.includes(name)) tags.push(name)
            })
        }
        if (p.tags) {
            p.tags.forEach(function (item) {
                var name = item.slug.replace(/-/g, '').toLowerCase()
                if (!tags.includes(name)) tags.push(name)
            })
        }
        p.category = tags.length ? [tags[0]] : ['Other']
        p.tags = tags.join(', ')

        delete p.id
        delete p.artwork
        delete p.author
        delete p.content
        delete p.categories
        delete p.code
        delete p.created_at
        delete p.preview_url
        delete p.title
        delete p.updated_at
        delete p.slug
        delete p.platform
        delete p.excerpt

        return p
    },

    transformLocalPedalboard: function (p) {
        p.psid = (p.patchstorage && p.patchstorage.id) ? String(p.patchstorage.id) : null
        p.local_revision = (p.patchstorage && p.patchstorage.revision) ? p.patchstorage.revision : null
        p.name = p.title
        p.label = p.title
        p.uri = p.bundle
        p.comment = ''
        p.status = 'installed'

        var ver = p.version || 0
        var hasThumb = true
        p.thumbnail_href = "/pedalboard/image/thumbnail.png?bundlepath=" + escape(p.bundle) + "&v=" + ver
        p.screenshot_href = "/pedalboard/image/screenshot.png?bundlepath=" + escape(p.bundle) + "&v=" + ver
        // Prefer local images; cloud artwork filled in on merge if needed
        p._hasLocalImages = hasThumb

        return p
    },

    mergePedalboardsData: function (lPb, cPb) {
        if (!cPb && !lPb) {
            return {}
        }

        if (lPb == null || lPb == undefined || objectEmpty(lPb)) {
            return $.extend(true, {}, cPb)
        }

        if (cPb == null || cPb == undefined || objectEmpty(cPb)) {
            return $.extend(true, {}, lPb)
        }

        lPb.psid = cPb.psid
        lPb.files = cPb.files
        lPb.file = cPb.file
        lPb.cloud_revision = cPb.cloud_revision
        lPb.download_count = cPb.download_count
        lPb.state = cPb.state
        lPb.url = cPb.url
        lPb.uploader = cPb.uploader
        lPb.tags = cPb.tags
        lPb.donate_url = cPb.donate_url
        lPb.comment = cPb.comment || lPb.comment
        lPb.name = cPb.name || lPb.name
        lPb.label = cPb.label || lPb.label
        lPb.uri = 'ps-pedalboard:' + cPb.psid

        // Prefer cloud artwork for list cards when available (more reliable than missing thumbs)
        if (cPb.thumbnail_href) {
            lPb.cloud_thumbnail_href = cPb.thumbnail_href
            lPb.cloud_screenshot_href = cPb.screenshot_href
        }

        if (lPb.local_revision && lPb.cloud_revision && lPb.cloud_revision != lPb.local_revision) {
            lPb.status = 'outdated'
        } else {
            lPb.status = 'installed'
        }

        return lPb
    },

    getCloudPedalboards: function (callback) {
        var self = $(this)
        var base = PATCHSTORAGE_API_URL
        var platform_id = PATCHSTORAGE_PEDALBOARD_PLATFORM_ID
        var tag_id = PATCHSTORAGE_PEDALBOARD_TAG_ID
        var url = `${base}?per_page=100&platforms=${platform_id}`
        if (tag_id) {
            url += `&tags=${tag_id}`
        }
        var page = 1
        var pb_map = {}
        var cloudPedalboards = self.data('cloudPedalboards')

        self.data('cloudPedalboardsLoaded', false)

        if (cloudPedalboards != null) {
            self.data('cloudPedalboardsLoaded', true)
            callback()
            return
        }

        var loading = new Notification('info', 'Fetching pedalboards from Patchstorage...', 7000)

        function getNextPage() {
            var xhr = $.ajax({
                url: url + `&page=${page}`,
                method: 'GET',
                async: true,
                cache: false,
                dataType: 'json',
                success: function (data, status, xhr) {
                    if (!data || data.length < 1) {
                        self.data('cloudPedalboards', pb_map)
                        self.data('cloudPedalboardsLoaded', true)
                        loading.close()
                        callback()
                        return
                    }

                    var pages = xhr.getResponseHeader('x-wp-totalpages')

                    for (var i = 0; i < data.length; i++) {
                        var pb = self.patchstoragePedalboardsBox('transformCloudPedalboard', data[i])
                        if (pb.supported) {
                            pb_map[pb.psid] = pb
                        }
                    }

                    if (pages && pages > page) {
                        page++
                        getNextPage()
                    } else {
                        self.data('cloudPedalboards', pb_map)
                        self.data('cloudPedalboardsLoaded', true)
                        loading.close()
                        callback()
                    }
                },
                error: function (xhr, status) {
                    if (status == 'abort') return
                    loading.close()
                    new Notification('error', "Connection to Patchstorage failed!", 5000)
                    self.data('cloudPedalboards', {})
                    self.data('cloudPedalboardsLoaded', true)
                    callback()
                }
            });
            self.data('xhrs').push(xhr)
        }

        getNextPage()
    },

    getLocalPedalboards: function (callback) {
        var self = $(this)
        var pb_map = {}
        var localPedalboards = self.data('localPedalboards')

        self.data('localPedalboardsLoaded', false)

        if (localPedalboards != null) {
            self.data('localPedalboardsLoaded', true)
            callback()
            return
        }

        var xhr = $.ajax({
            method: 'GET',
            url: '/pedalboard/list',
            success: function (pedals) {
                for (var i in pedals) {
                    var transformed = self.patchstoragePedalboardsBox('transformLocalPedalboard', pedals[i])
                    if (transformed.psid) {
                        pb_map[transformed.psid] = transformed
                    }
                }
                self.data('localPedalboards', pb_map)
                self.data('localPedalboardsLoaded', true)
                callback()
            },
            error: function (xhr, status) {
                if (status == 'abort') return
                self.data('localPedalboards', {})
                self.data('localPedalboardsLoaded', true)
                callback()
            },
            cache: false,
            dataType: 'json'
        })
        self.data('xhrs').push(xhr)
    },

    mergePedalboards: function (lPbs, cPbs) {
        var self = $(this)

        if (self.data('mergedPedalboards') != null) {
            return self.data('mergedPedalboards')
        }

        var mPbs = {}
        var lMap = $.extend(true, {}, lPbs)
        var cMap = $.extend(true, {}, cPbs)

        function buildIndex(data) {
            data.index = `${data.comment} ${data.name} ${data.label} ${data.uploader} ${data.tags}`.toLowerCase()
            return data
        }

        for (var psid in cMap) {
            var cPb = cMap[psid]
            if (psid in lMap) {
                var merged = self.patchstoragePedalboardsBox('mergePedalboardsData', lMap[psid], cPb)
                mPbs[psid] = buildIndex(merged)
                delete lMap[psid]
            } else {
                cPb.status = 'available'
                mPbs[psid] = buildIndex(cPb)
            }
        }

        // Local pedalboards previously installed from Patchstorage but no longer listed
        for (var psid in lMap) {
            var lPb = lMap[psid]
            lPb.status = 'unavailable'
            mPbs[psid] = buildIndex(lPb)
        }

        self.data('mergedPedalboards', mPbs)
        return mPbs
    },

    search: function () {
        var self = $(this)
        var query = {
            text: self.data('searchbox').val()
        }

        var xhrs = self.data('xhrs')
        for (var i in xhrs) {
            if (xhrs[i].abort) xhrs[i].abort()
            delete xhrs[i]
        }
        self.data('xhrs', [])

        var filterAvailable = function (pb) {
            return pb.status != 'available'
        }
        var filterInstalled = function (pb) {
            return !(pb.status == 'installed' || pb.status == 'outdated')
        }
        var filterOutdated = function (pb) {
            return pb.status != 'outdated'
        }
        var filterAll = function () {
            return false
        }

        if (self.find('input:checkbox[name=non-installed]:checked').length)
            return self.patchstoragePedalboardsBox('searchPedalboards', query, filterAvailable)

        if (self.find('input:checkbox[name=installed]:checked').length)
            return self.patchstoragePedalboardsBox('searchPedalboards', query, filterInstalled)

        if (self.find('input:checkbox[name=outdated]:checked').length)
            return self.patchstoragePedalboardsBox('searchPedalboards', query, filterOutdated)

        return self.patchstoragePedalboardsBox('searchPedalboards', query, filterAll)
    },

    searchPedalboards: function (query, shouldSkip) {
        var self = $(this)

        var renderResultsCallback = function () {
            if (self.data('localPedalboardsLoaded') == false || self.data('cloudPedalboardsLoaded') == false) {
                return
            }

            var pedalboards = []
            var mPbs = self.patchstoragePedalboardsBox('mergePedalboards',
                self.data('localPedalboards'), self.data('cloudPedalboards'))

            for (var id in mPbs) {
                var pb = mPbs[id]
                if (shouldSkip(pb)) {
                    continue
                }
                if (query && query.text && !pb.index.includes(query.text.toLowerCase())) {
                    continue
                }
                pedalboards.push(pb)
            }

            self.patchstoragePedalboardsBox('renderPedalboards', pedalboards)
        }

        self.data('localPedalboardsLoaded', false)
        self.data('cloudPedalboardsLoaded', false)
        self.patchstoragePedalboardsBox('getCloudPedalboards', renderResultsCallback)
        self.patchstoragePedalboardsBox('getLocalPedalboards', renderResultsCallback)
    },

    renderPedalboards: function (pedalboards) {
        var self = $(this)
        self.patchstoragePedalboardsBox('cleanResults')

        pedalboards.sort(function (a, b) {
            a = a.label.toLowerCase()
            b = b.label.toLowerCase()
            if (a > b) return 1
            if (a < b) return -1
            return 0
        })

        var canvas = self.find('#patch-pedalboard-content-All')
        for (var i in pedalboards) {
            var render = self.patchstoragePedalboardsBox('renderPedalboardCard', pedalboards[i])
            render.appendTo(canvas)
        }

        self.find('#patchstorage-pedalboards-tab-All').html(
            'All <span class="plugin_count">(' + pedalboards.length + ')</span>')
    },

    renderPedalboardCard: function (pb) {
        var self = $(this)
        var data = self.patchstoragePedalboardsBox('getPedalboardCardData', pb, false)
        var rendered = $(Mustache.render(TEMPLATES.patchstorage_pedalboard, data))
        rendered.click(function () {
            self.patchstoragePedalboardsBox('showPedalboardInfo', pb)
        })
        return rendered
    },

    getPedalboardCardData: function (pb, full) {
        var data = $.extend(true, {}, pb)

        // Prefer Patchstorage artwork for cards — local pedalboard screenshots are full
        // dashboard captures that look wrong in the small plugin-style thumb slot, and
        // may show default "tuna can" icons until a fresh screenshot is generated.
        var thumb = data.cloud_thumbnail_href || data.thumbnail_href
        var shot = data.cloud_screenshot_href || data.screenshot_href || thumb

        // Detail modal: prefer local screenshot when installed (actual board capture)
        if (full && data.bundle && (data.status == 'installed' || data.status == 'outdated')) {
            shot = data.screenshot_href || shot
            thumb = data.thumbnail_href || thumb
        }

        var basic = {
            uri: data.uri,
            escaped_uri: escape(data.uri),
            comment: (data.comment) ? data.comment.trim() : "No description available",
            has_comment: (data.comment) ? null : "no_description",
            screenshot_href: shot,
            thumbnail_href: thumb,
            status: data.status,
            brand: data.uploader,
            label: data.label,
            download_count: data.download_count,
            state: data.state,
            tags: data.tags
        }

        if (basic.status == 'available') {
            delete basic.status
        }

        if (full === false) {
            return basic
        }

        return $.extend(true, basic, {
            name: data.name,
            url: data.url,
            category: (data.category && data.category[0]) || "None",
            local_revision: data.local_revision,
            cloud_revision: data.cloud_revision,
            uploader: data.uploader,
            donate_url: data.donate_url
        })
    },

    ensureCloudFile: function (pb, callback) {
        var self = $(this)

        if (pb.file && pb.file.url) {
            callback(pb)
            return
        }

        var xhr = $.ajax({
            url: `${PATCHSTORAGE_API_URL}/${pb.psid}`,
            method: 'GET',
            async: true,
            cache: false,
            dataType: 'json',
            success: function (data) {
                var detail = self.patchstoragePedalboardsBox('transformCloudPedalboard', data)
                pb.files = detail.files
                pb.file = detail.file
                callback(pb)
            },
            error: function () {
                callback(null)
            }
        })
        self.data('xhrs').push(xhr)
    },

    installPedalboard: function (pb, callback) {
        var self = $(this)

        self.patchstoragePedalboardsBox('ensureCloudFile', pb, function (ready) {
            if (!ready || !ready.file || !ready.file.url) {
                alert('No downloadable pedalboard file found on Patchstorage.')
                return
            }

            var file = ready.file
            var notification = new Notification('warning')
            var installationMsg = 'Downloading: ' + file.filename

            notification.open()
            notification.html(installationMsg)
            notification.type('warning')
            notification.bar(1)

            var trans = new SimpleTransference(file.url, '/pedalboard/install',
            { to_args: { headers:
                { 'Patchstorage-Item' : pb.psid, 'Patchstorage-Item-Version' : pb.cloud_revision }
            }})

            trans.reportPercentageStatus = function (percentage) {
                notification.bar(percentage * 100)
                if (percentage == 1) {
                    installationMsg = installationMsg.replace("Downloading", "Installing")
                    notification.html(installationMsg)
                }
            }

            trans.reportError = function (reason) {
                notification.close()
                new Notification('error', "Could not install pedalboard: " + reason, 5000)
            }

            trans.reportFinished = function (resp) {
                var result = resp.result || resp
                if (result.ok) {
                    notification.html(installationMsg.replace("Installing:", "Done! Installed:"))
                    notification.bar(0)
                    notification.type('success')
                    notification.closeAfter(3000)
                    if (desktop.previousPedalboardList !== undefined) {
                        desktop.previousPedalboardList = null
                    }
                } else {
                    notification.closeAfter(1000)
                    new Notification('error', "Could not install pedalboard: " + (result.error || 'unknown error'), 5000)
                }
                callback(result)
            }

            trans.start()
        })
    },

    showPedalboardInfo: function (mPb) {
        var self = $(this)

        // Refresh cloud detail for files / latest metadata
        var xhr = $.ajax({
            url: `${PATCHSTORAGE_API_URL}/${mPb.psid}`,
            method: 'GET',
            async: true,
            cache: false,
            dataType: 'json',
            success: function (data) {
                var cloud = self.patchstoragePedalboardsBox('transformCloudPedalboard', data)
                var local = self.data('localPedalboards')[mPb.psid] || {}
                var pb = self.patchstoragePedalboardsBox('mergePedalboardsData', local, cloud)
                // Preserve installed status if local missing (available)
                if (!local || objectEmpty(local)) {
                    pb.status = 'available'
                }

                var metadata = self.patchstoragePedalboardsBox('getPedalboardCardData', pb, true)
                var info = self.data('info')
                if (info) {
                    info.remove()
                    self.data('info', null)
                }

                info = $(Mustache.render(TEMPLATES.patchstorage_pedalboard_info, metadata))

                info.find('.js-install').hide()
                info.find('.js-upgrade').hide()
                info.find('.js-remove').hide()
                info.find('.js-load').hide()

                if (pb.status == 'available') {
                    info.find('.js-install').show().click(function () {
                        self.patchstoragePedalboardsBox('installPedalboard', pb, function () {
                            info.window('close')
                            self.data('localPedalboards', null)
                            self.data('mergedPedalboards', null)
                            self.patchstoragePedalboardsBox('search')
                        })
                    })
                }

                if (pb.status == 'outdated') {
                    info.find('.js-upgrade').show().click(function () {
                        self.patchstoragePedalboardsBox('installPedalboard', pb, function () {
                            info.window('close')
                            self.data('localPedalboards', null)
                            self.data('mergedPedalboards', null)
                            self.patchstoragePedalboardsBox('search')
                        })
                    })
                }

                if (pb.status == 'installed' || pb.status == 'outdated' || pb.status == 'unavailable') {
                    info.find('.js-remove').show().click(function () {
                        var bundle = pb.bundle
                        if (!bundle) {
                            alert('Cannot determine local pedalboard path')
                            return
                        }
                        self.data('removePedalboard')(bundle, function (ok) {
                            info.window('close')
                            self.data('localPedalboards', null)
                            self.data('mergedPedalboards', null)
                            self.patchstoragePedalboardsBox('search')
                        })
                    })
                    info.find('.js-load').show().click(function () {
                        if (!pb.bundle) return
                        self.data('loadPedalboard')(pb.bundle, function () {
                            info.window('close')
                        })
                    })
                }

                info.appendTo($('body'))
                info.window({
                    windowName: "Patchstorage Pedalboard Info"
                })
                info.window('open')
                self.data('info', info)
            },
            error: function () {
                new Notification('error', 'Failed to load pedalboard details', 4000)
            }
        })
        self.data('xhrs').push(xhr)
    }
})
