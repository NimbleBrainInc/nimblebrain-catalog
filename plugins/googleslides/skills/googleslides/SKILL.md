---
name: googleslides
description: >-
  How to use the Google Slides connector's tools — reading a deck and its
  slides, rendering slide thumbnails, and editing with batch updates: adding
  slides, inserting and replacing text, images, and tables. Use when the user
  works with Google Slides, decks, presentations, or a pitch deck.
metadata:
  nimblebrain:
    server: googleslides
---

You are using the **Google Slides** connector, Google's own Slides MCP server. Its tools act on the connected user's presentations. Apply this guidance
whenever you touch Slides.

## Find the deck

- Every tool needs a `presentationId`, the token in the URL
  (`docs.google.com/presentation/d/<id>/edit`). Take it from a pasted link. This
  connector can't search or create; if the Google Drive connector is connected, find a
  deck with its `search_files`, copy a template with its `copy_file`, or create a blank
  deck with its `create_file` (`application/vnd.google-apps.presentation`).

## Reading

- `read_presentation` returns the deck as JSON, which is large. Pass a `fields` mask
  for what you need, such as `slides.objectId` and
  `slides.pageElements(objectId,shape.text)` for slide ids and their text.
- `read_slide_page` reads one slide by its `pageId` (the slide's `objectId`).
- `read_slide_page_thumbnail` returns an image URL for one slide; use it to show a
  slide or check that an edit looks right.
- If the Google Drive connector is connected, its `read_file_content` returns the
  deck's text compactly, which is enough for a summary.

## Editing

- `update_presentation` takes `requests`, a `presentations.batchUpdate` list that
  applies together. Slides and shapes are addressed by **object id** from a read;
  never invent one.
- `replaceAllText` swaps text across the deck with no ids, which suits filling a
  template's placeholders (`{{client}}`). Use distinctive placeholders.
- `createSlide` adds a slide (with a `predefinedLayout` such as `TITLE_AND_BODY`, or a
  `layoutId` from the deck's master); `insertText` writes into a shape by `objectId`;
  `deleteText`, `deleteObject`, `duplicateObject`, `updateSlidesPosition`,
  `createImage`, and `createTable` cover the rest. To fill a new slide's placeholders,
  give them ids with `placeholderIdMappings` when you create it.
- Read again after the update to confirm the result.

## Care

- Edits are live for everyone with access and the API has no undo. Confirm the deck
  and show the person the planned change before writing; scope `replaceAllText` and
  deletions tightly.
- Google may require the person's confirmation for high-impact actions. If a tool
  returns an error saying a client capability is required, or suggests a safer
  alternative, use the alternative and tell the person.
