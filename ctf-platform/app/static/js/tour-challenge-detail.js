pageTour([
  {
    selector: 'h1',
    title: 'Challenge Info',
    text: 'This is the challenge title, category, difficulty, and point value. Higher points mean harder challenges.',
  },
  {
    selector: '#challenge-desc',
    title: 'Description',
    text: 'Read the challenge description carefully — it usually contains hints about the approach or tools you\'ll need.',
  },
  {
    selector: '#flag',
    title: 'Flag Submission',
    text: 'Once you find the flag, enter it here in CSIA{...} format and hit Submit. You only need to solve it once.',
  },
  {
    selector: '#solvers-section',
    title: 'Solvers Leaderboard',
    text: 'This shows everyone who has solved this challenge, ordered by who solved it first. Top 3 get gold, silver, and bronze.',
  },
], 'tour_challenge_detail');
