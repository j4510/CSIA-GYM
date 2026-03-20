pageTour([
  { selector: '#title', title: 'Challenge Title', text: 'Give your challenge a clear, descriptive name that hints at the topic without giving it away.' },
  { selector: '#quill-desc', title: 'Description', text: 'Write your challenge description using the rich text editor. You can use headings, code blocks, bullet lists, and links.' },
  { selector: '#category', title: 'Category', text: 'Pick the category that best fits your challenge — Web, Crypto, Forensics, Reverse Engineering, etc.' },
  { selector: '#difficulty', title: 'Difficulty', text: 'Set the difficulty level. This helps players decide which challenges to attempt first.' },
  { selector: '#flag', title: 'Flag', text: 'Enter the correct flag in CSIA{...} format. This is what players must submit to solve your challenge.' },
  { selector: '#points', title: 'Points', text: 'Assign a point value. Easy challenges are typically 50–150 pts, medium 150–300, and hard 300–500.' },
  { selector: '#attach-btn', title: 'File Attachments', text: 'Click Choose Files to attach binaries, images, or archives for admin review. Selected filenames appear below the button.' },
  { selector: '#quota-bar', title: 'Storage Quota', text: 'This bar shows how much of your 250 MB pending file quota is used. Quota frees up when your submissions are approved.' },
], 'tour_submit_challenge');
