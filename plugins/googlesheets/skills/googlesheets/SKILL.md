---
name: googlesheets
description: >-
  How to use the Google Sheets connector's tools — reading tabs and cell ranges
  in A1 notation, writing values and formulas, inserting rows and columns, and
  structural edits such as adding tabs, formatting, sorting, and charts. Use
  when the user works with Google Sheets, a spreadsheet, tabs, cells, rows, or
  columns.
metadata:
  nimblebrain:
    server: googlesheets
---

You are using the **Google Sheets** connector, Google's own Sheets MCP server. Its tools act on the connected user's spreadsheets. Apply this guidance
whenever you touch a sheet.

## Identify the spreadsheet and its tabs

- Every tool needs a `spreadsheetId`, the token in the URL
  (`docs.google.com/spreadsheets/d/<id>/edit`). Take it from a pasted link. This
  connector can't search; if the Google Drive connector is connected, find the file
  with its `search_files`, otherwise ask for the link.
- Call `get_spreadsheet` with `fields: ["sheets.properties"]` to list the tabs, with
  each tab's `title`, numeric `sheetId`, and grid size. Leave out `includeGridData`
  unless you need formatting: it returns every cell.
- Ranges use **A1 notation** qualified by tab title: `Sheet1!A1:C10`, `Sheet1!A:A`,
  `'Q3 Plan'!2:2` (quote titles with spaces). Tools that work on structure
  (`insert_dimension`, most `update_spreadsheet` requests) take the numeric `sheetId`
  and 0-based indexes instead.

## Reading

- `get_values` reads one range as rows of cells. Read the header row first, then only
  the rows you need; summarize rather than echoing a large sheet.
- `get_spreadsheet` with `ranges` reads several ranges in one call.

## Writing

- `update_values` writes a 2D array (rows of cells) to a range, overwriting what is
  there. Values are strings, numbers, or booleans; `""` clears a cell, a null skips it.
- `update_formulas` writes formulas (`[["=SUM(B2:B10)"]]`). Use it, not
  `update_values`, for anything starting with `=`.
- There is no append tool. To add rows, read the column to find the last used row, then
  `update_values` the rows below it, or send an `appendCells` request through
  `update_spreadsheet`.
- `insert_dimension` inserts empty rows or columns (`ROWS`/`COLUMNS`, 0-based
  `startIndex` inclusive, `endIndex` exclusive) so you can write into the gap.
- `update_spreadsheet` takes a `spreadsheets.batchUpdate` list of `requests`: `addSheet`
  (new tab), `updateSheetProperties` (rename, freeze rows), `repeatCell` (format),
  `sortRange`, `setBasicFilter`, `addChart`, `findReplace`, `deleteDimension`,
  `deleteSheet`, comments, and more. Requests in one call apply together.
- This connector can't create a spreadsheet. With Google Drive connected, create a
  blank one with its `create_file` (`application/vnd.google-apps.spreadsheet`), then
  add tabs and headers here.

## Care

- Writes are live for everyone with access and the API has no undo. Read a range
  before overwriting it, keep headers intact, and show the person the rows or the
  change before writing.
- `deleteSheet`, `deleteDimension`, `deleteRange`, and broad `findReplace` remove data.
  Scope them tightly and get explicit confirmation first.
- Google may require the person's confirmation for high-impact actions. If a tool
  returns an error saying a client capability is required, or suggests a safer
  alternative, use the alternative and tell the person.
