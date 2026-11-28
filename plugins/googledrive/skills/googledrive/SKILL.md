---
name: googledrive
description: >-
  How to use the Google Drive connector's tools — searching for files and
  folders, reading file text and comments, checking metadata and sharing,
  creating files, folders, and blank Docs, Sheets, or Slides, and copying.
  Use when the user works with Google Drive, files, folders, PDFs, Word files,
  or shared documents.
metadata:
  nimblebrain:
    server: googledrive
---

You are using the **Google Drive** connector, Google's own Drive MCP server. Its tools act on the connected user's Drive, including shared drives.
Apply this guidance whenever you touch Drive.

## Find the file first

- Every tool after discovery needs a **file id**. Get it from `search_files`,
  `list_recent_files`, or a pasted URL (`.../d/<id>/...`). Never guess one.
- `search_files` takes a structured query: `title contains 'budget'`,
  `fullText contains 'renewal'`, `mimeType = 'application/vnd.google-apps.spreadsheet'`,
  `modifiedTime > '2026-01-01T00:00:00Z'`, `parentId = '<folderId>'` (direct children),
  `'<folderId>' in ancestors` (anywhere below), `owner = 'me'`, `sharedWithMe = true`,
  `starred = true`. Combine with `and`, `or`, `not`; quote strings with single quotes.
- Put file types in a `mimeType` clause, never in the title words: search
  `title contains 'Q3' and mimeType = 'application/vnd.google-apps.presentation'`, not
  `title contains 'Q3 deck'`.
- `orderBy: modifiedTime desc` sorts by recency; `list_recent_files` lists recent
  files without a query. Set `excludeContentSnippets: true` when you only need names
  and ids, and page with `pageToken`.
- Several files can share a name. Disambiguate by folder, owner, or modified date
  (`includeRichMetadata: true` adds owner and last editor) before acting.

## Reading content

- `read_file_content` returns a file as text: Google Docs as Markdown, plus Sheets,
  Slides, PDF, Word (`.doc`, `.docx`), Excel, PowerPoint, OpenDocument, plain text,
  images, and video with a transcript. It reads files in shared drives too.
- If `textFormattingNotSupported` is true, the content is empty because Drive can't
  render that type as text; say so instead of calling the file empty.
- Long files are trimmed: about 50,000 characters reach you. For a long file, say you
  read only the first part and summarize what you read; don't present it as the whole.
- Emoji and other characters outside the Basic Multilingual Plane can come back
  garbled in exported Docs. That is an export artifact, not file corruption.
- `includeComments: true` adds comment threads (Docs, Sheets, and Slides only); use it
  for feedback, action items, or open questions.
- `download_file_content` returns raw base64 bytes, with `exportMimeType` for Google
  files (`application/pdf`, `text/csv`). Prefer `read_file_content` for anything you
  will read.

## Metadata and sharing

- `get_file_metadata` gives type, parents, size, and capabilities such as `canTrash`
  and `canMoveItemWithinDrive`. `get_file_permissions` lists who has access.
- This connector reads sharing but can't change it, and it has no move, rename, or
  trash tool. Point the person to Drive for those, with the file's link.

## Creating

- `create_file` makes a folder (`application/vnd.google-apps.folder`), a blank Google
  Doc, Sheet, or Slides file (its `application/vnd.google-apps.*` type, no content), or
  uploads content: `textContent` for text, `base64Content` for binary, with
  `contentMimeType` set. Text uploads convert to a Google Doc unless
  `disableConversionToGoogleType` is true. Set `parentId` at creation.
- `copy_file` duplicates a file, with an optional `title` and `parentId`; use it to
  start from a template.
- `upload_file_revision` replaces the content of an uploaded (non-Google) file. It
  overwrites what is there, so confirm first.

## Care

- Creating and copying are visible to anyone with access to the folder. Confirm the
  destination before writing, and never write to many files without explicit scope.
- A file "not found" may not be shared with the connected account. Say so rather than
  inventing its content.
- Google may require the person's confirmation for high-impact actions. If a tool
  returns an error saying a client capability is required, or suggests a safer
  alternative, use the alternative and tell the person.
