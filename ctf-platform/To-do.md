- User profiles on public ✅
- More administrator actions on user
    - Filtering of user table
- Better favicon 
- User-agent detection instead of resolution for phones. ✅
- Email verification
- Media posting enabled on community
    - Previews (Thumbnails) - WebP
    - Making this md
- Identicon ✅
- Community-based challenges ✅
- Competitions
- Badges ✅


---

## Pending / In-Progress (from review session)

### Partially Done
- Hide solved on /challenges — logic exists but may have caching/UX issues; needs re-verification
- Dynamic flag hiding — backend strips flag from status responses, but frontend still renders plaintext flag in DOM and localStorage (visible in DevTools); needs full fix

### Not Yet Done

**UI / UX**
- Revamp "Choose Files" button on /submit to a modern styled button matching the platform theme
- Revamp /admin/challenges — unified searchable table, remove approved/rejected clutter
- Revamp /admin/users — add search/filter bar for quick lookup
- Revamp /admin/posts — table layout with search, flair display, easier navigation

**Badges**
- Add 10 editable border styles to badges (low-level → god-tier)
- Limited edition badge must require a count input (not just a checkbox)
- Add "From an Event" and "Unattainable" checkboxes to badge creation
- Badge image should be croppable (like profile picture on /settings)
- Add Badge model columns: border_style, limited_count, from_event, is_unattainable
- Create public /badges page listing all badges + descriptions (like /ranks)
- Badge click anywhere on site → redirect to /badges, scroll to badge, highlight for 2s

**Announcements & Notifications system**
- New Notification model: admin-created, per-user read tracking, navbar dropdown
- New Announcement model: timed (start + end), shown as banner on all pages
- Announcement times must sync browser time to server time (UTC offset handling)
- Admin dashboard section to create/manage both notifications and announcements

**Docker (Production)**
- docker-compose.prod.yml is correct for Linux (no network_mode: host needed)
- Challenge instance ports (dynamic web/nc) are not mapped in prod compose — decide on port range and add mapping (e.g. 10000-12000:10000-12000)


March 22, 2026:
- Hexagonal Tiles, still doesn't look like a hive. It should look like a honeycomb, it currently looks like shit.
- XP Numerical Value (not fixed), I have a test account that has 9 challenges solved, 2 community posts, 14 accepted submissions, and 2250 total score, why is my XP 0? Fix this.
- Let's have passkeys via WebAuthn enabled as well, after registration, ask users if they want to enable passkey so that in the login page it can either be a password or via passkey. Put the duo logo as well `DUO_LOGO.png`. Currently registered users can enable passkey when their passkey is not yet enabled, on their login, they will automatically receive a prompt to enable passkey.

- Create a "mail" system where all notifications will be sent there as well as a digest (daily GMT+8). The mail system will be a mail icon next to the notification bell (on mobile navbar it will be a full word "Messages"), the mail function will be able to send and receive messages to other users from other users. (Make sure the design of this is well-professional and is in accordance to our current design templates). 

- Also can we achieve this on Binary Exploitation (PWN) (Formerly Reverse Engineering):
Ah — that explains a lot. With **1 GB RAM and 1 vCPU**, running full Docker containers per challenge is too heavy. That’s why nsjail is a better choice: it’s **lightweight, fast, and doesn’t need a full container**.

- Deleting a challenge returns 500 error.
