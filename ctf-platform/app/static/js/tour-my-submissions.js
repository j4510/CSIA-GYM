pageTour([
  { selector: 'h1', title: 'My Submissions', text: 'Here you can track all the challenges you have submitted for admin review.' },
  { selector: '.space-y-4 > div', title: 'Submission Card', text: 'Each card shows the challenge title, category, difficulty, points, a description preview, and the current review status.' },
  { selector: 'a[href*="submit-challenge"], a[href*="submissions/new"]', title: 'Submit Another', text: 'Want to submit another challenge? Click here to go to the submission form.' },
], 'tour_my_submissions');
