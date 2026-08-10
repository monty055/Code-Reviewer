# Product Requirements Document — Task Tracker API

## User Authentication

As a registered user, I want to log in with my email and password so that I
can access my personal task list securely.

### Acceptance Criteria

- AC-1: The system must reject login attempts with an incorrect password.
- AC-2: On successful login, the system must return a signed authentication token.
- AC-3: Passwords must never be stored or logged in plain text.
- AC-4: After 5 consecutive failed login attempts, the account must be temporarily locked.

## Task Creation

As a logged-in user, I want to create a new task with a title and optional
due date so that I can track my work.

### Acceptance Criteria

- AC-1: A task cannot be created without a title.
- AC-2: A newly created task defaults to status "pending".
- AC-3: The due date, if provided, must be a valid future date.
- AC-4: Each created task is assigned a unique identifier.

## Task Completion

As a logged-in user, I want to mark a task as complete so that I can track my
progress.

### Acceptance Criteria

- AC-1: Marking a task complete updates its status to "completed".
- AC-2: A completed task records the completion timestamp.
- AC-3: Completed tasks can be filtered/listed separately from pending tasks.

## Email Notifications

As a user, I want to receive an email reminder before a task's due date so
that I don't miss deadlines.

### Acceptance Criteria

- AC-1: A reminder email is sent 24 hours before a task's due date.
- AC-2: Users can opt out of reminder emails in their settings.
- AC-3: Failed email delivery is retried at least once.
