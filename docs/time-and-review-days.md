# UTC timestamps and local review days

All ORM timestamp fields require timezone-aware values, normalize writes to UTC,
and return UTC-aware datetimes. Naive input is rejected. PostgreSQL columns use
`timestamptz` (absolute instants); SQLite stores UTC values without an offset and
the ORM restores the UTC offset when reading. Database-generated timestamps are
absolute instants on PostgreSQL and UTC on SQLite. Existing timestamp columns
already use these types, so no timestamp conversion migration is needed.
Raw SQL writers must use aware timestamps on PostgreSQL and UTC on SQLite.

`User.timezone` holds an IANA name such as `Australia/Adelaide`, validated by the
ORM using system timezone data. Migration `0006` defaults existing accounts to
`UTC`. Account creation defaults to UTC until a user preference is supplied;
future settings APIs should validate and persist a device/user-selected IANA zone.
Do not infer a permanent timezone from an IP address or store a fixed UTC offset.

“Due today” includes overdue words and anything scheduled before the user's next
local midnight: `due_at < next_local_midnight_in_UTC`. The next-midnight instant
is excluded. This daily workload may include words scheduled later today.
“Ready to review” means `due_at <= now`, independent of timezone. Both queries
filter by word owner; caller authentication remains the API's responsibility.
For reporting entries scheduled strictly on today's date, use the half-open range
`local_midnight_in_UTC <= due_at < next_local_midnight_in_UTC`.

Day boundaries come from the user's local date and IANA zone, then convert to UTC.
Do not add 24 hours to a UTC boundary: daylight-saving days can differ in length.
Changing timezone immediately changes the daily workload boundary without changing
stored due times, history, or review counts. API timestamps should include `Z` or
an explicit UTC offset; clients display them in the user's selected zone.

Implementation: `app/core/time.py` and `app/services/reviews/queries.py`.
