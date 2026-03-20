pageTour([
  { selector: 'h1', title: 'Admin Panel', text: 'Welcome to the admin panel. From here you can manage every aspect of the platform.' },
  { selector: '.bg-white.p-6', title: 'Platform Stats', text: 'A quick overview of total users, live challenges, pending submissions awaiting review, and community posts.' },
  { selector: 'a[href*="admin/users"]', title: 'Manage Users', text: 'View all registered users, promote or demote admins, hide users from the scoreboard, assign legendary ranks, or delete accounts.' },
  { selector: 'a[href*="admin/challenges"]', title: 'Approve Challenges', text: 'Review user-submitted challenges. Approve them to make them live or reject them. You can also edit and delete live challenges.' },
  { selector: 'a[href*="admin/posts"]', title: 'Moderate Posts', text: 'Edit or delete community posts that violate guidelines.' },
  { selector: 'a[href*="admin/badges"]', title: 'Manage Badges', text: 'Create custom badges with animated border tiers (Common → GOD) and award them to users to recognise achievements.' },
  { selector: 'a[href*="notifications"]', title: 'Notifications & Announcements', text: 'Send bell notifications to all users, or schedule timed announcement banners that appear at the top of every page.' },
  { selector: 'a[href*="audit-log"]', title: 'Audit Log', text: 'View a searchable log of all admin actions — who did what and when. You can also download it as a CSV.' },
], 'tour_admin');
