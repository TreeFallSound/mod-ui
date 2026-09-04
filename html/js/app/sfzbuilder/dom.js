// SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
// SPDX-License-Identifier: AGPL-3.0-or-later
// @ts-check

/**
 * A small set of tools that make elements.
 *
 * The island makes its own markup (architecture rule 4.3). These functions use
 * the browser API only. They exist so that the view code stays short, not to
 * replace a library.
 * @module
 */

/**
 * Makes an element.
 *
 * The tag can hold classes after a dot. Example: `h('div.sfz-pad.sfz-pad--on')`.
 * A property that starts with "on" becomes an event listener.
 * A child that is a string becomes a text node, thus the text is always safe.
 *
 * @param {string} tag
 * @param {object} [props]
 * @param {(Node|string|null|false|undefined)[]} [children]
 * @returns {HTMLElement}
 */
export function h(tag, props, children) {
    const parts = tag.split('.')
    const node = document.createElement(parts[0] || 'div')
    for (let i = 1; i < parts.length; i++) {
        node.classList.add(parts[i])
    }
    for (const key in props || {}) {
        const value = (props || {})[key]
        if (value === null || value === undefined || value === false) {
            continue
        }
        if (key.indexOf('on') === 0) {
            node.addEventListener(key.slice(2), value)
        } else if (key === 'text') {
            node.textContent = String(value)
        } else if (key === 'html') {
            node.innerHTML = String(value)
        } else if (key in node && key !== 'list' && key !== 'form') {
            // @ts-ignore - a direct property keeps the type, for example checked.
            node[key] = value
        } else {
            node.setAttribute(key, String(value))
        }
    }
    for (const child of children || []) {
        if (child === null || child === undefined || child === false) {
            continue
        }
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child)
    }
    return node
}

/**
 * Removes every child of an element.
 * @param {HTMLElement} node
 */
export function clear(node) {
    while (node.firstChild) {
        node.removeChild(node.firstChild)
    }
}

/**
 * Adds or removes a class.
 * @param {Element|null} node
 * @param {string} name
 * @param {boolean} on
 */
export function toggleClass(node, name, on) {
    if (node) {
        node.classList.toggle(name, !!on)
    }
}

/**
 * Shows or hides an element.
 * @param {HTMLElement|null} node
 * @param {boolean} on
 */
export function show(node, on) {
    if (node) {
        node.style.display = on ? '' : 'none'
    }
}
