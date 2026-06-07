// Render a small subset of inline markdown to safe HTML for display.
//
// Mirrors the PDF builders' `md_inline()` (_tools/_styles.py) token set —
// **bold** / __bold__, *italic* / _italic_, `code` — and decodes the HTML
// entities `_strip_entities()` (_tools/make_cards_pdf.py) handles, so the web
// detail view formats text the same way the printed cards do.
//
// Safe for use with Svelte's {@html}: the input is HTML-escaped first, so the
// only markup in the output is the tags we add and the entities we re-permit
// (named/numeric character references, which render as characters, never tags).

const TOKEN_RE = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_|`[^`]+`)/g;

// Re-permit only well-formed character references (named, decimal, hex) that
// got neutralized by the HTML-escape step. Nothing else is un-escaped.
const ENTITY_RE = /&amp;(#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/g;

/** @param {string} s */
function escapeHtml(s) {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** @param {string} tok */
function tokenToHtml(tok) {
	if (tok.startsWith('**') || tok.startsWith('__')) return `<strong>${tok.slice(2, -2)}</strong>`;
	if (tok.startsWith('*') || tok.startsWith('_')) return `<em>${tok.slice(1, -1)}</em>`;
	if (tok.startsWith('`')) return `<code>${tok.slice(1, -1)}</code>`;
	return tok;
}

/**
 * Convert inline markdown to safe HTML.
 * @param {string | null | undefined} raw
 * @returns {string}
 */
export function renderInline(raw) {
	if (!raw) return '';
	let s = escapeHtml(String(raw));
	s = s.replace(TOKEN_RE, (m) => tokenToHtml(m));
	s = s.replace(ENTITY_RE, (_m, name) => `&${name};`);
	return s;
}
