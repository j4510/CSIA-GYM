pageTour([
  { selector: 'h1', title: 'My Account', text: 'Your personal profile page — shows your public information, rank, stats, badges, and recent activity.' },
  { selector: '.bg-black.border-4', title: 'Profile Card', text: 'Your avatar, username, rank, bio, and social links are shown here. Everything visible to other players on your public profile.' },
  { selector: '.text-5xl.font-black.text-red-600', title: 'Your Stats', text: 'Total points, challenges solved, community posts, accepted/rejected submissions at a glance.' },
  { selector: 'a[href*="ranks"]', title: 'Your Rank', text: 'Your rank is calculated from your percentile among all players. Click it to see the full rank tier list.' },
  { selector: 'canvas', title: 'Skill Radar', text: 'The radar chart shows your solve distribution across all challenge categories. Add other players to compare your skills side by side.' },
  { selector: 'a[href*="settings"]', title: 'Edit Profile', text: 'Click here to update your username, avatar, bio, social links, and password.' },
], 'tour_account');
