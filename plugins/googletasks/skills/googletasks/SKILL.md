---
name: googletasks
description: >-
  How to use the Google Tasks connector's tools — listing task lists and tasks,
  adding to-dos and reminders with dates and repeats, updating, completing,
  deleting, and restoring them. Use when the user works with Google Tasks,
  to-dos, a task list, or asks to be reminded to do something.
metadata:
  nimblebrain:
    server: googletasks
---

You are using the **Google Tasks** connector, Google's own Tasks MCP server. Its tools act on the connected user's task lists. Apply this guidance
whenever you touch Google Tasks.

## Lists and tasks

- `list_task_lists` returns the user's lists and their ids. `"~default"` is the
  default list.
- `list_tasks` returns open tasks from **all** lists unless `filter.taskListId` is set.
  `filter.state` selects `UNCOMPLETED` (default), `COMPLETED`, or `ALL`;
  `filter.timeFilter` narrows by `SCHEDULED_TIME` or `COMPLETED_TIME` between dates;
  `filter.includeDeleted` adds deleted tasks. Results are not in the app's order; sort
  by `position` within a list when order matters.
- `get_task` reads one task by id, including completed and deleted ones. Ids come from
  `list_tasks`; never invent one.
- There is no tool to create, rename, or delete a list.

## Adding and changing tasks

- A task is a to-do; an event is a block of time. "Remind me to call the bank" is a
  task; "my dentist appointment at 10" is a calendar event, not a task.
- `create_task` takes `title`, optional `description`, and `taskListId`. Use
  `scheduledDate` (and `scheduledTime`, which notifies at that time) for "on/for
  Friday", and `deadlineDate` only for "by", "due", or "deadline". Deadlines are dates
  only. Set `timeZone` to the user's IANA zone when you give a time.
- `recurrenceRule` makes a task repeat. Repeating tasks can't have a deadline; if one
  was asked for, say it wasn't set and offer a separate task for it.
- `update_task` changes only the fields you pass (`""` clears one). It can't make an
  existing task repeat; tell the person to do that in the Google Tasks app.
- Check the returned task against what was asked and tell the person about any date
  or time that was not set.

## Completing, deleting, restoring

- "Done" means `complete_task` (`uncomplete_task` reopens it). Don't delete a task the
  person finished.
- `delete_task` removes a task; `undelete_task` restores it, found with
  `list_tasks` and `filter.includeDeleted`. Restoring fails for shared tasks, and
  `deleteSeries: true` deletes a repeating series permanently.

## Care

- Confirm before deleting, and before changing or completing several tasks at once.
- Google may require the person's confirmation for high-impact actions. If a tool
  returns an error saying a client capability is required, or suggests a safer
  alternative, use the alternative and tell the person.
