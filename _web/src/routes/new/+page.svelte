<script>
	import Editor from '$lib/Editor.svelte';

	// A starter skeleton matching the recipe schema so the box isn't blank.
	const STARTER = `---
title:
category:
tags: []
---
#

## Yield and timing
-

## Ingredients
-

## Method
1.
`;
</script>

<p><a href="/">← All recipes</a></p>
<h1>New recipe</h1>
<Editor mode="create" initialMarkdown={STARTER} />
