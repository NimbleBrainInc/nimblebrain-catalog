---
name: googlecalendar
description: >-
  How to use the Google Calendar connector's tools — finding events, creating
  and editing them, inviting attendees, responding to invites, and finding free
  time. Use when the user works with their calendar, schedule, meetings, events,
  invites, agenda, availability, or asks to book or reschedule a time.
metadata:
  nimblebrain:
    server: googlecalendar
---

You are using the **Google Calendar** connector, Google's own Calendar MCP server. Its tools act on the connected user's real calendars. Apply this
guidance whenever you touch the calendar.

## Times and time zones

- Pass times as local ISO 8601 with no offset and no `Z` (`2026-04-30T10:00:00`). The
  server applies the user's own time zone.
- When the person names a time zone ("3pm Eastern"), keep the time offset-free and set
  the request's `timeZone` to its IANA name (`America/New_York`), even if it looks like
  their own.
- Resolve "tomorrow" or "next Tuesday" to a date before you call a tool, and say the
  date, time, and time zone back in your answer so nothing is ambiguous.

## Finding events

- **A time window** ("what's on Thursday", "my week"): `list_events` with `startTime`
  and `endTime`. With no `startTime` it starts now and covers 7 days. Set
  `orderBy: startTime` for an agenda; `fullText` narrows by words in the title,
  description, location, or attendees. It reads any calendar by `calendarId`
  (default primary).
- **A topic with no date** ("my last call with Acme"): `search_events`. It takes only a
  `query`, searches the **primary** calendar, and has no date range, so check each
  result's dates yourself and drop the ones outside what was asked.
- `get_event` reads one event by id. Ids come from `list_events` or `search_events`;
  never invent one.
- `list_calendars` resolves "my team calendar" to its `calendarId` (an email-like id).
  Calendars shared with the user can be read by id even if they are not listed.

## Finding a time

- `suggest_time` finds free slots across people: `attendeeEmails`, a `startTime` and
  `endTime` window, `durationMinutes`, and optional `preferences` (`startHour`,
  `endHour` as `"HH:mm"`, `excludeWeekends`). Offer the person a few slots; don't book
  one until they pick.

## Creating and changing events

- `create_event` needs `summary`, `startTime`, and `endTime`. Add `attendees` as
  objects with an `email` (plain names don't work), `addGoogleMeetUrl: true` only when
  a video call is wanted, `recurrenceData` as RRULE strings, `allDay` for all-day
  events.
- `update_event` changes only the fields you pass. Add and remove guests with
  `addedAttendees` and `removedAttendeeEmails`; changing only `startTime` keeps the
  duration.
- `respond_to_event` accepts, declines, or marks tentative, with an optional comment.
- `delete_event` removes the event. There is no undo.

## Care

- Every write acts on a real calendar, and creating, updating, deleting, or responding
  can email attendees (`notificationLevel` defaults to `ALL` for create, update, and
  delete). Show the person the title, time, time zone, calendar, and guests, and get a
  yes before you write. Use `notificationLevel: NONE` only when they ask for no emails.
- Confirm the exact event (title and time) before deleting, and never change several
  events without the person agreeing to that scope.
- Google may require the person's confirmation for high-impact actions such as an
  event with attendees. If a tool returns an error saying a client capability is
  required, or suggests a safer alternative, use the alternative and tell the person.
