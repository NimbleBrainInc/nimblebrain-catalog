---
name: googledocs
description: >-
  How to use the Google Docs connector's tools — reading a document's structure
  and editing it with batch updates: inserting and replacing text, styling,
  lists, tables, and comments. Use when the user works with Google Docs,
  documents, reports, write-ups, or meeting notes, or wants to edit a doc.
metadata:
  nimblebrain:
    server: googledocs
---

You are using the **Google Docs** connector, Google's own Docs MCP server. It has two tools, `read_doc` and `update_doc`, and acts on the connected
user's documents. Apply this guidance whenever you touch Google Docs.

## Find the document

- Both tools need a `documentId`, the token in the URL
  (`docs.google.com/document/d/<id>/edit`), which is the same id Drive uses. Take it
  from a pasted link. This connector can't search; if the Google Drive connector is
  connected, find the doc with its `search_files`, otherwise ask for the link.
- This connector can't create a document. With Google Drive connected, create a blank
  Doc with its `create_file` (`application/vnd.google-apps.document`), then write into
  it with `update_doc`.

## Reading

- `read_doc` returns the whole document as structural JSON (`documents.get`): every
  paragraph, run, style, and index. It is very large, often far bigger than the text,
  and a long doc can exceed what the host accepts in one result.
- If the Google Drive connector is connected, read text for summaries and questions
  with its `read_file_content` (Markdown, compact). Otherwise use `read_doc` and expect
  a long, structural result.
- Use `read_doc` when you need exact positions for `update_doc`, or comments
  (`commentsIncluded: true`).

## Editing

- `update_doc` takes `requests`, a `documents.batchUpdate` list. The requests in one
  call apply together, in order.
- **Prefer `replaceAllText`** for targeted edits: it finds text and needs no index.
  Use a distinctive anchor so it doesn't change unintended matches.
- **Append** with `insertText` and `endOfSegmentLocation: {}` to add to the end without
  computing an index.
- Index-based edits (`insertText` at a `location`, `deleteContentRange`,
  `updateTextStyle`, `createParagraphBullets`) count UTF-16 code units. The body
  starts at index 1, never 0. Take indexes from a fresh `read_doc`, and in one batch
  order edits from the highest index to the lowest so earlier edits don't shift later
  ones.
- Write line breaks as real newline characters in the string; an escaped backslash-n
  lands in the doc as the literal characters `\n`.
- Comments and suggestions are requests too: `insertComment`, `addCommentReply`
  (also resolves a thread), `acceptSuggestion`, `rejectSuggestion`.

## Care

- Edits are live for everyone with access, and the API has no undo. Confirm the
  document and show the person what will change before writing; read the doc first
  when an edit replaces or deletes text.
- After a structural edit, read the doc again to check it landed where you meant.
- A doc that isn't found may not be shared with the connected account. Say so rather
  than inventing content.
- Google may require the person's confirmation for high-impact actions. If a tool
  returns an error saying a client capability is required, or suggests a safer
  alternative, use the alternative and tell the person.
