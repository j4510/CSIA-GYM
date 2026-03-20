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
