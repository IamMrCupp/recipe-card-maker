import assert from 'node:assert/strict';
import { test } from 'node:test';

import { renderInline } from '../src/lib/inline.js';

test('bold: ** and __', () => {
	assert.equal(renderInline('**Do not grease**'), '<strong>Do not grease</strong>');
	assert.equal(renderInline('__also bold__'), '<strong>also bold</strong>');
});

test('italic: * and _', () => {
	assert.equal(renderInline('the German *Konditorei* case'), 'the German <em>Konditorei</em> case');
	assert.equal(renderInline('_emphasis_'), '<em>emphasis</em>');
});

test('code spans', () => {
	assert.equal(renderInline('use `flour`'), 'use <code>flour</code>');
});

test('bold wins over italic (** before *)', () => {
	assert.equal(renderInline('**bold**'), '<strong>bold</strong>');
});

test('decodes &nbsp; (and keeps it as a rendered entity)', () => {
	assert.equal(renderInline('~1 hr &nbsp;|&nbsp; Chill'), '~1 hr &nbsp;|&nbsp; Chill');
});

test('decodes other known entities like &amp;', () => {
	assert.equal(renderInline('salt &amp; pepper'), 'salt &amp; pepper');
});

test('escapes raw HTML — no injection through {@html}', () => {
	assert.equal(
		renderInline('<script>alert(1)</script>'),
		'&lt;script&gt;alert(1)&lt;/script&gt;'
	);
	// a bare ampersand that is not an entity stays escaped
	assert.equal(renderInline('Maille & Co'), 'Maille &amp; Co');
});

test('mixed inline + entity', () => {
	assert.equal(
		renderInline('**Active:** ~1 hr &nbsp;| *chill*'),
		'<strong>Active:</strong> ~1 hr &nbsp;| <em>chill</em>'
	);
});

test('empty / nullish input', () => {
	assert.equal(renderInline(''), '');
	assert.equal(renderInline(null), '');
	assert.equal(renderInline(undefined), '');
});
