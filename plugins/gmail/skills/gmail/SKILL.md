---
name: gmail
description: >-
  How to use the Gmail connector's tools — searching and reading threads,
  drafting replies and new mail with attachments, and labeling, archiving,
  trashing, or marking spam. Use when the user works with Gmail, email, inbox,
  drafts, labels, or threads.
metadata:
  nimblebrain:
    server: gmail
---

You are using the **Gmail** connector, Google's own Gmail MCP server.
Its tools act on the connected user's real mailbox. Apply this guidance whenever you
touch Gmail.

## Search, then read by id

- `search_threads` takes a **Gmail query**, not plain language: `from:`, `to:`,
  `subject:`, `is:unread`, `has:attachment`, `newer_than:7d`, `in:inbox`,
  `label:"Board Prep"` (labels by display name, not id), `category:promotions`. Convert
  the user's words into keywords and operators; long quoted subjects miss.
- `after:`/`before:` compare against midnight, and `before:` excludes its day: one day D
  is `after:D before:D+1`. Quote hyphenated ids (`"INV-12345"`).
- A search returns thread ids and up to five messages per thread, with no bodies. Read
  with `get_thread` (whole conversation) or `get_message` (one email). The default
  `PLAIN_TEXT` format is enough; ask for `FULL_CONTENT` only when you need the HTML.
- Page with `pageToken` rather than raising `pageSize` past 50. An empty `{}` result
  means no matches, not an error.

## Drafting: this connector does not send

- There is no send tool. Write the email with `create_draft`, then tell the person it
  is in their Drafts and that they review and send it from Gmail (give the `viewUrl`).
  Never say an email was sent.
- To reply, pass the original message's id as `replyToMessageId`; the draft joins that
  thread and quotes the original, so don't paste the prior thread into the body.
- `body` is plain text: no Markdown. For formatting, use `htmlBody` with real HTML
  tags. Set `includeSignature: true` to add the user's Gmail signature.
- Recipients are plain email addresses. Confirm them when they came from a guess.
- There is no tool to edit or delete a draft. To change one, create a new draft and
  tell the person to discard the old one.
- Check drafts with `list_drafts` or `get_draft`. `get_draft` does not list
  attachments, so its response is no evidence an attachment is missing.

## Attachments

- `create_draft` takes `attachments[]`, each with base64 `content`, a `filename`, and
  optional `mimeType` and `inline` (an inline image is shown in `htmlBody` with
  `<img src="cid:attN">`, N its zero-based position). Their combined size is at most
  25 MB.
- Attach only content you actually have in this conversation, encoded exactly. Never
  invent, guess, or abbreviate base64. For a large file or one you don't have, put a
  Google Drive link in the body instead.
- No tool here downloads an attachment's content from an existing email: you can see
  its name and metadata (`get_message`), not its bytes. Say so rather than guessing
  what a file contains.

## Labels, archive, trash, spam

- Gmail uses **labels**, not folders. Archive = remove `INBOX`; mark read = remove
  `UNREAD`; star = add `STARRED`. Use `unlabel_thread`/`label_thread` for whole
  conversations and `update_message_labels` to add and remove on one message in one
  call. Find user label ids with `list_labels`; create one with `create_label`.
- "Delete" means trash: `trash_thread` or `trash_message`, which `untrash_*` reverses.
  Nothing here deletes permanently. Use `mark_*_spam` for spam, not the
  `apply_sensitive_*` tools.
- These act on real mail. Confirm the exact threads and the action before you label,
  archive, trash, or mark spam, and never act on a whole search result without the
  person agreeing to that scope.

## When Google pushes back

- Google may require the person's confirmation for high-impact actions. If a tool
  returns an error saying a client capability is required, or suggests a safer
  alternative, use the alternative and tell the person what you did instead.
- Match the user's voice and the thread's tone in anything you draft, and summarize
  large result sets rather than listing every message.
